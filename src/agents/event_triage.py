# Scores 8-K filings on item codes, then checks if it survives neutralization. No model.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

FILINGS = Path("data/8k_20150101_20260831_identified.parquet")
OUT = Path("submission/exhibits")

# Item codes an analyst stops on, signed by theory and fixed before we measured.
SIGNED_ITEMS = {
    "4.01": -1,  # auditor resignation or dismissal
    "4.02": -1,  # previously issued statements should no longer be relied on
    "2.06": -1,  # material impairment
    "1.03": -1,  # bankruptcy or receivership
    "3.01": -1,  # delisting notice or failure to satisfy a listing rule
    "2.04": -1,  # an obligation has been accelerated
    "5.02": -1,  # director or officer departure
    "2.05": -1,  # costs of exit or disposal
    "1.02": -1,  # a material agreement has been terminated
    "8.01": +1,  # other events. Signed positive because managers disclose good news here
    # by choice, not because we have read the bodies. This rule sees item codes only.
}

# Scheduled item codes. A quarterly filing is not news, so the signal ignores them.
ROUTINE = {"2.02", "7.01", "9.01", "5.07", "5.03"}


# One signed score per stock-month from item codes. The floor prompts/triage.md must beat.
def triage_scores() -> pd.DataFrame:
    table = pq.read_table(FILINGS, columns=["permno", "filing_date", "items"]).to_pandas()
    table["eom"] = pd.to_datetime(table["filing_date"]) + pd.offsets.MonthEnd(0)

    def score(items) -> float:
        if items is None:
            return 0.0
        # Sum the signed codes present, ignoring the scheduled ones entirely.
        return float(sum(SIGNED_ITEMS.get(i, 0) for i in items if i not in ROUTINE))

    table["score"] = [score(i) for i in table["items"]]
    return table.groupby(["permno", "eom"], as_index=False)["score"].sum()


# Same treatment the book gives its own signal. What survives is real, not a proxy.
def neutralized(df: pd.DataFrame, column: str) -> pd.Series:
    r = df.groupby("eom")[column].rank(pct=True)
    mu = r.groupby(df["eom"]).transform("mean")
    sd = r.groupby(df["eom"]).transform("std")
    z = ((r - mu) / sd.replace(0.0, np.nan)).fillna(0.0)
    z = z - z.groupby([df["eom"], df["sector"]]).transform("mean")

    controls = []
    for col in ("ivol_capm_21d", "rvol_21d", "betadown_252d", "betabab_1260d", "beta_60m"):
        rr = df.groupby("eom")[col].rank(pct=True)
        m = rr.groupby(df["eom"]).transform("mean")
        s = rr.groupby(df["eom"]).transform("std")
        controls.append(((rr - m) / s).fillna(0.0))
    x = pd.concat(controls, axis=1).to_numpy()

    out = []
    for _, idx in df.groupby("eom").groups.items():
        rows = df.index.get_indexer(idx)
        design = np.c_[np.ones(len(rows)), x[rows]]
        y = z.loc[idx].to_numpy()
        out.append(pd.Series(y - design @ np.linalg.lstsq(design, y, rcond=None)[0], index=idx))
    return pd.concat(out)


# Monthly spread earned by a signal, and its t-statistic.
def spread_t(signal: pd.Series, demeaned: pd.Series, months: pd.Series) -> tuple[float, float]:
    monthly = (signal * demeaned).groupby(months).mean()
    return float(monthly.mean()), float(monthly.mean() / monthly.std() * np.sqrt(len(monthly)))


# Runs the triage rule over the corpus and reports whether it survives the gate.
def main() -> None:
    panel = P.screen(P.load_panel())
    panel = panel.dropna(subset=["ret_exc_lead1m", "beta_60m"]).reset_index(drop=True)
    merged = panel.merge(triage_scores(), on=["permno", "eom"], how="left")
    merged["score"] = merged["score"].fillna(0.0)
    merged["dm"] = merged["ret_exc_lead1m"] - merged.groupby("eom")["ret_exc_lead1m"].transform(
        "mean"
    )

    _, raw_t = spread_t(
        merged.groupby("eom")["score"].rank(pct=True) - 0.5, merged["dm"], merged["eom"]
    )
    _, neutral_t = spread_t(neutralized(merged, "score"), merged["dm"], merged["eom"])

    # Coverage matters. A signal that fires on a handful of names cannot carry a book.
    fired = merged["score"] != 0
    out = dict(
        stock_months_scored=int(len(merged)),
        stock_months_with_a_signed_event=int(fired.sum()),
        coverage=float(fired.mean()),
        raw_t=raw_t,
        neutralized_t=neutral_t,
        verdict="rejected" if abs(neutral_t) < 2.0 else "passes the t-gate, check the deciles",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "event_triage.json").write_text(json.dumps(out, indent=2))

    print(
        f"scored {out['stock_months_scored']:,} screened stock-months, "
        f"{out['coverage']:.1%} carry a signed event"
    )
    print(f"  raw t          {raw_t:+.2f}")
    print(f"  neutralized t  {neutral_t:+.2f}")
    print(f"  {out['verdict']}")


if __name__ == "__main__":
    main()
