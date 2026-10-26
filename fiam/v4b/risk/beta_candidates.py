# Market-beta candidates at a formation (DECISIONS D20 step A), all from data
# through eom. Welch and Dimson are v4's (fiam/v4/betas.py, commit 67e39da),
# estimated here on CRSP total excess returns against the Fama-French market
# excess, as risk/beta.py does.
#   B0 engine hedge beta, calibrated (the risk model's snapshot beta)
#   B1 engine hedge beta, uncalibrated (Vasicek 252d, 50/50 with beta_60m)
#   B2 Welch (2022) slope-winsorised, 252 sessions, half-life 126
#   B3 Dimson (1979), 126 sessions, one lag and one lead
#   B4 panel beta_60m
#   B5 mean of B2 and B3

import numpy as np
import pandas as pd

WELCH_DAYS, WELCH_HALF, DIMSON_DAYS = 252, 126, 126
NAMES = ("B0", "B1", "B2", "B3", "B4", "B5")


# Welch (2022): each excess return clipped to [-2, 4] x the market's.
def welch(stock: pd.DataFrame, market: pd.Series, half: int = WELCH_HALF) -> pd.Series:
    x = market.to_numpy(dtype=float)
    y = stock.to_numpy(dtype=float)
    lo, hi = np.minimum(-2 * x, 4 * x)[:, None], np.maximum(-2 * x, 4 * x)[:, None]
    y = np.clip(y, lo, hi)
    decay = 0.5 ** (np.arange(len(x) - 1, -1, -1) / half)
    weight = np.where(np.isnan(y), 0.0, decay[:, None])
    total = weight.sum(axis=0)
    xm = (weight * x[:, None]).sum(axis=0) / np.where(total > 0, total, np.nan)
    ym = np.nansum(weight * y, axis=0) / np.where(total > 0, total, np.nan)
    dx = x[:, None] - xm
    cov = np.nansum(weight * dx * (y - ym), axis=0)
    var = (weight * dx**2).sum(axis=0)
    enough = ((weight > 0).sum(axis=0) >= len(x) // 2) & (var > 0)
    out = np.divide(cov, var, out=np.full(len(total), np.nan), where=enough)
    return pd.Series(out, index=stock.columns, name="welch")


# Dimson (1979): slopes on the market's lag, day and lead, summed. Days whose
# lead is after eom are not in the window (the last regression day is eom - 1).
def dimson(stock: pd.DataFrame, market: pd.Series) -> pd.Series:
    m = market.to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(m) - 2), m[:-2], m[1:-1], m[2:]])
    Y = stock.iloc[1:-1].to_numpy(dtype=float)
    out = np.full(Y.shape[1], np.nan)
    full = ~np.isnan(Y).any(axis=0)
    if full.any():  # names with every day: one solve
        coef, *_ = np.linalg.lstsq(x, Y[:, full], rcond=None)
        out[full] = coef[1:].sum(axis=0)
    for j in np.flatnonzero(~full):
        ok = ~np.isnan(Y[:, j])
        if ok.sum() >= len(ok) // 2:
            coef, *_ = np.linalg.lstsq(x[ok], Y[ok, j], rcond=None)
            out[j] = coef[1:].sum()
    return pd.Series(out, index=stock.columns, name="dimson")


# All six candidates for these names at eom; snap is the risk model's snapshot.
def at(rm, snap: dict, excess: pd.DataFrame, mkt_rf: pd.Series, eom, names) -> pd.DataFrame:
    eom = pd.Timestamp(eom)
    hist = excess.loc[excess.index <= eom].reindex(columns=names)
    m = mkt_rf.reindex(hist.index)
    hb = rm.betas[rm.betas["eom"] == eom].set_index("permno")
    b60 = rm.exp[rm.exp["eom"] == eom].set_index("permno")["beta_60m"]
    out = pd.DataFrame(index=pd.Index(names, name="permno"))
    out["B0"] = snap["beta"].reindex(names)
    out["B1"] = hb["beta_hedge"].reindex(names)
    out["B2"] = welch(hist.iloc[-WELCH_DAYS:], m.iloc[-WELCH_DAYS:]).reindex(names)
    out["B3"] = dimson(hist.iloc[-(DIMSON_DAYS + 2):], m.iloc[-(DIMSON_DAYS + 2):]).reindex(names)
    out["B4"] = b60.reindex(names)
    out["B5"] = out[["B2", "B3"]].mean(axis=1, skipna=False)
    return out


# A candidate in force: missing names take the cross-sectional median (v4's rule).
def filled(beta: pd.Series) -> pd.Series:
    return beta.fillna(beta.median())


# Policy beta_source -> candidate (D20); "engine" leaves the snapshot alone.
SOURCES = {"hedge_uncal": "B1", "welch": "B2", "dimson": "B3", "beta_60m": "B4", "welch_dimson": "B5"}


# The snapshot with this beta as its market column (and its "beta").
def apply(snap: dict, beta: pd.Series) -> dict:
    B = snap["B"].copy()
    b = filled(beta.reindex(B.index))
    B["mkt"] = b.to_numpy()
    return snap | {"B": B, "beta": b, "beta_source_median_fill": int(beta.reindex(B.index).isna().sum())}
