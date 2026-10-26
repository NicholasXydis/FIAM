# Training targets: raw excess, sector-demeaned, factor residual (initial plan).

import numpy as np
import pandas as pd

# Pre-formation exposures for the residual target, from the panel at eom.
EXPOSURES = {
    "beta": "beta_60m",
    "size": "market_equity",
    "value": "be_me",
    "momentum": "ret_12_1",
    "profitability": "gp_at",
    "investment": "at_gr1",
}


# Within-month z-scores of ranks; missing at 0.
def zrank(frame: pd.DataFrame, col: str) -> pd.Series:
    r = frame.groupby("eom")[col].rank(pct=True) - 0.5
    z = r / r.groupby(frame["eom"]).transform("std")
    return z.fillna(0.0)


# Two-digit GICS sector as a string; missing stays missing.
def sector(frame: pd.DataFrame) -> pd.Series:
    g = pd.to_numeric(frame["gics"], errors="coerce")
    return (g // 1e6).astype("Int64").astype(str).where(g.notna())


# The label minus its sector-month mean.
def sector_demeaned(frame: pd.DataFrame, col: str) -> pd.Series:
    return frame[col] - frame.groupby(["eom", sector(frame)])[col].transform("mean")


# Residual of the label on pre-formation exposures, sqrt(me) WLS per month.
# Returns the residual and each month's factor returns (the slopes).
def residual(frame: pd.DataFrame, col: str) -> tuple[pd.Series, pd.DataFrame]:
    z = pd.DataFrame({k: zrank(frame, v) for k, v in EXPOSURES.items()}, index=frame.index)
    dummies = pd.get_dummies(sector(frame), prefix="s", dtype=float)
    out = pd.Series(np.nan, index=frame.index)
    factors = {}
    for eom, idx in frame.groupby("eom").groups.items():
        y = frame.loc[idx, col]
        ok = y.notna().to_numpy()
        if ok.sum() < 100:
            continue
        rows = np.asarray(idx)[ok]
        d = dummies.loc[rows]
        d = d.loc[:, d.sum() > 0]
        x = np.column_stack([z.loc[rows].to_numpy(), d.to_numpy()])
        w = np.sqrt(frame.loc[rows, "me"].clip(lower=0).fillna(0.0).to_numpy())
        sw = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(x * sw[:, None], y.loc[rows].to_numpy() * sw, rcond=None)
        out.loc[rows] = y.loc[rows].to_numpy() - x @ beta
        factors[eom] = dict(zip(EXPOSURES, beta[: len(EXPOSURES)]))
    return out, pd.DataFrame(factors).T.sort_index()
