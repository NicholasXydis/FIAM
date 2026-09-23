# A fixed-budget search, scored on one window and judged on one it never saw.
#
# A control, not an LLM agent. It measures the multiple-testing failure the rules warn of.

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

OUT = Path("submission/exhibits")

# Searches holding months through 2023, judged on 2024 on. Cut on the HOLDING month.
SEARCH_END = "2024-01-01"

# How many it may score before choosing. Without a budget, searching proves nothing.
BUDGET = 200
SUBSET_SIZE = 5
SEED = 42


# Monthly neutralized spread for one subset, the same treatment the book gives its own signal.
def spread(df: pd.DataFrame, cols: tuple[str, ...]) -> pd.Series:
    zs = []
    for col in cols:
        r = df.groupby("eom")[col].rank(pct=True)
        mu = r.groupby(df["eom"]).transform("mean")
        sd = r.groupby(df["eom"]).transform("std")
        zs.append(((r - mu) / sd) * P.SIGNALS[col])
    composite = pd.concat(zs, axis=1).mean(axis=1)

    demeaned = composite - composite.groupby([df["eom"], df["sector"]]).transform("mean")
    bx = df["beta_60m"] - df.groupby("eom")["beta_60m"].transform("mean")
    sy = demeaned - demeaned.groupby(df["eom"]).transform("mean")
    cov = (bx * sy).groupby(df["eom"]).transform("sum")
    var = (bx * bx).groupby(df["eom"]).transform("sum")
    signal = (sy - (cov / var) * bx).fillna(0.0)

    dm = df["ret_exc_lead1m"] - df.groupby("eom")["ret_exc_lead1m"].transform("mean")
    monthly = (signal * dm).groupby(df["eom"]).mean()
    # Re-index onto the month the return actually realizes, so the window cut below is honest.
    monthly.index = (pd.DatetimeIndex(monthly.index) + pd.offsets.MonthBegin(1)).normalize()
    return monthly


# Annualized information ratio of a monthly spread.
def ir(series: pd.Series) -> float:
    if len(series) < 6 or series.std() == 0:
        return float("nan")
    return float(series.mean() / series.std() * np.sqrt(12))


# Runs the search, records what it chose, and scores that choice on the sealed period.
def main() -> None:
    df = P.screen(P.load_panel())
    df["sector"] = df["gics"].astype("string").str[:2].fillna("XX")
    df = df.dropna(subset=["ret_exc_lead1m", "beta_60m"]).copy()

    everything = list(itertools.combinations(P.SIGNALS, SUBSET_SIZE))
    rng = np.random.default_rng(SEED)
    # Sampling within a budget, not sweeping everything. The seed keeps it reproducible.
    picks = rng.choice(len(everything), size=min(BUDGET, len(everything)), replace=False)

    rows = []
    for i in picks:
        cols = everything[i]
        s = spread(df, cols)
        rows.append(
            dict(
                signals="+".join(cols),
                ir_search=ir(s[s.index < SEARCH_END]),
                ir_sealed=ir(s[s.index >= SEARCH_END]),
            )
        )
    table = pd.DataFrame(rows).dropna()

    # What the agent hands back. The best thing it found in the window it could see.
    chosen = table.loc[table["ir_search"].idxmax()]
    baseline = spread(df, tuple(P.SIGNALS))
    out = dict(
        budget=int(len(table)),
        subset_size=SUBSET_SIZE,
        search_window=f"holding months 2021-01 to {SEARCH_END[:7]}, exclusive",
        chosen_signals=chosen["signals"],
        chosen_ir_in_search=float(chosen["ir_search"]),
        chosen_ir_in_sealed=float(chosen["ir_sealed"]),
        median_ir_in_sealed=float(table["ir_sealed"].median()),
        rank_of_chosen_in_sealed=int((table["ir_sealed"] > chosen["ir_sealed"]).sum() + 1),
        search_vs_sealed_correlation=float(table["ir_search"].corr(table["ir_sealed"])),
        all_twelve_ir_in_sealed=ir(baseline[baseline.index >= SEARCH_END]),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signal_discovery.json").write_text(json.dumps(out, indent=2))

    print(f"agent scored {out['budget']} combinations on {out['search_window']}")
    print(f"  it chose            {out['chosen_signals']}")
    print(f"  IR where it looked  {out['chosen_ir_in_search']:+.2f}")
    print(f"  IR in sealed period {out['chosen_ir_in_sealed']:+.2f}")
    print(
        f"  ranked {out['rank_of_chosen_in_sealed']} of {out['budget']} there, "
        f"median {out['median_ir_in_sealed']:+.2f}"
    )
    print(f"  using all twelve    {out['all_twelve_ir_in_sealed']:+.2f}")
    print(f"  search-vs-sealed IR correlation {out['search_vs_sealed_correlation']:+.2f}")


if __name__ == "__main__":
    main()
