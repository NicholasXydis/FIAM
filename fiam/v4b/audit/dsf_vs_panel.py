# H5: does the organisers' daily return include dividends? 2015-2020 only.

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data

OUT = Path(__file__).resolve().parents[1] / "out" / "audit"


# Compounded daily returns per stock-month against the panel's monthly ret.
def main() -> dict:
    d = data.daily()
    d["eom"] = d["date"] + pd.offsets.MonthEnd(0)
    comp = d.groupby(["permno", "eom"])["daily_return"].apply(lambda r: np.prod(1 + r) - 1)
    p = pd.read_parquet(
        data.PANEL,
        columns=["permno", "eom", "ret", "div12m_me"],
        filters=[("eom", "<=", data.BLIND)],
    )
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    m = p.merge(comp.rename("daily").reset_index(), on=["permno", "eom"]).dropna()
    gap = m["ret"] - m["daily"]
    payers = m["div12m_me"] > 0.02
    out = {
        "stock_months": int(len(m)),
        "abs_gap_le_1e-4_share": float((gap.abs() <= 1e-4).mean()),
        "mean_gap": float(gap.mean()),
        "median_gap_yield_gt_2pct": float(gap[payers].median()),
        "mean_gap_yield_gt_2pct": float(gap[payers].mean()),
        "mean_gap_nonpayers": float(gap[m["div12m_me"] <= 0].mean()),
        "expected_monthly_div_yield_payers": float(m.loc[payers, "div12m_me"].mean() / 12),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dsf_vs_panel.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
