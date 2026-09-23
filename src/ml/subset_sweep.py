# Every 5-signal subset of the menu, on an early window and a later one. 792 of them.

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

OUT = Path("submission/exhibits")

# 792 combinations. Small enough to run, large enough that picking a winner tempts you.
SUBSET_SIZE = 5

# First half is what a team would have seen when choosing, second is what they earned.
SPLIT = "2023-01-01"


# Neutralized monthly spread earned by one subset of the signals, per month.
def subset_spread(df: pd.DataFrame, cols: tuple[str, ...]) -> pd.Series:
    zs = []
    for col in cols:
        r = df.groupby("eom")[col].rank(pct=True)
        mu = r.groupby(df["eom"]).transform("mean")
        sd = r.groupby(df["eom"]).transform("std")
        zs.append(((r - mu) / sd) * P.SIGNALS[col])
    composite = pd.concat(zs, axis=1).mean(axis=1)

    # Same neutralization the book uses, so the comparison is like for like.
    demeaned = composite - composite.groupby([df["eom"], df["sector"]]).transform("mean")
    bx = df["beta_60m"] - df.groupby("eom")["beta_60m"].transform("mean")
    sy = demeaned - demeaned.groupby(df["eom"]).transform("mean")
    cov = (bx * sy).groupby(df["eom"]).transform("sum")
    var = (bx * bx).groupby(df["eom"]).transform("sum")
    signal = (sy - (cov / var) * bx).fillna(0.0)

    dm = df["ret_exc_lead1m"] - df.groupby("eom")["ret_exc_lead1m"].transform("mean")
    return (signal * dm).groupby(df["eom"]).mean()


# Annualized information ratio of a monthly spread series.
def ir(series: pd.Series) -> float:
    if series.std() == 0 or len(series) < 6:
        return np.nan
    return float(series.mean() / series.std() * np.sqrt(12))


# Scores every subset on both halves of the window and reports whether picking would pay.
def main() -> None:
    panel = P.load_panel()
    df = P.screen(panel)
    df["sector"] = df["gics"].astype("string").str[:2].fillna("XX")
    df = df.dropna(subset=["ret_exc_lead1m", "beta_60m"]).copy()

    rows = []
    for cols in itertools.combinations(P.SIGNALS, SUBSET_SIZE):
        spread = subset_spread(df, cols)
        early, late = spread[spread.index < SPLIT], spread[spread.index >= SPLIT]
        rows.append(
            dict(signals="+".join(cols), ir_early=ir(early), ir_late=ir(late), ir_full=ir(spread))
        )

    # The twelve-signal book on the same basis, so the histogram has an honest marker.
    full = subset_spread(df, tuple(P.SIGNALS))
    table = pd.DataFrame(rows)
    table.attrs["all_twelve_ir_full"] = ir(full)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "subset_sweep.csv", index=False)
    (OUT / "subset_sweep_baseline.json").write_text(
        json.dumps({"all_twelve_ir_full": ir(full)}, indent=2)
    )

    corr = table["ir_early"].corr(table["ir_late"])
    # What a team would have earned by picking the best subset on the early window.
    picked = table.loc[table["ir_early"].idxmax()]
    print(f"{len(table)} subsets of size {SUBSET_SIZE}")
    print(f"  full-window IR range {table['ir_full'].min():.2f} to {table['ir_full'].max():.2f}")
    print(f"  early-vs-late IR correlation {corr:+.2f}")
    print(
        f"  best-on-early subset then earned IR {picked['ir_late']:+.2f} "
        f"(median late IR {table['ir_late'].median():+.2f})"
    )


if __name__ == "__main__":
    main()
