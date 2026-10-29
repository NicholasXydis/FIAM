# The mid-month forecast from fresh 21-day price inputs at T.

import numpy as np
import pandas as pd

from fiam.vfinal import data
from fiam.vfinal.forecast import inputs, walkforward

DAYS, MIN_OBS = 21, 15
COLS = ("ret_1_0", "rvol_21d", "ivol_capm_21d", "rmax1_21d", "rmax5_21d", "rmax5_rvol_21d",
        "rskew_21d", "iskew_capm_21d", "coskew_21d")  # fmt: skip


# Sample skewness down the rows of a matrix (NaN-aware).
def skew(x: np.ndarray) -> np.ndarray:
    m = np.nanmean(x, axis=0)
    d = x - m
    s2 = np.nanmean(d**2, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nanmean(d**3, axis=0) / s2**1.5


# The characteristics at close T from the 21 sessions up to T only.
def refresh(returns: pd.DataFrame, mkt: pd.Series, T) -> pd.DataFrame:
    past = returns.loc[returns.index <= pd.Timestamp(T)].tail(DAYS)
    m = mkt.reindex(past.index).to_numpy(float)
    r = past.to_numpy(float)
    ok = np.isfinite(r).sum(axis=0) >= MIN_OBS
    out = pd.DataFrame(index=past.columns)
    out["ret_1_0"] = np.nanprod(1 + r, axis=0) - 1
    out["rvol_21d"] = np.nanstd(r, axis=0, ddof=1)
    # CAPM residuals, name by name over the days each one traded.
    md = m - m.mean()
    beta = np.nansum((r - np.nanmean(r, axis=0)) * md[:, None], axis=0) / (md @ md)
    e = r - np.nanmean(r, axis=0) - beta * md[:, None]
    out["ivol_capm_21d"] = np.nanstd(e, axis=0, ddof=1)
    srt = -np.sort(-np.nan_to_num(r, nan=-np.inf), axis=0)
    out["rmax1_21d"] = srt[0]
    out["rmax5_21d"] = srt[:5].mean(axis=0)
    out["rmax5_rvol_21d"] = out["rmax5_21d"] / out["rvol_21d"]
    out["rskew_21d"] = skew(r)
    out["iskew_capm_21d"] = skew(e)
    with np.errstate(invalid="ignore", divide="ignore"):
        co = np.nanmean(e * (md**2)[:, None], axis=0)
        out["coskew_21d"] = co / (np.sqrt(np.nanmean(e**2, axis=0)) * np.mean(md**2))
    out = out.replace([np.inf, -np.inf], np.nan)
    out.loc[~ok] = np.nan
    return out


# Every mid-month close's rebuilt inputs, by (eom, T).
def raw(rets: pd.DataFrame, mids: dict) -> pd.DataFrame:
    mkt = data.market_daily(rets.index)
    rows = []
    for eom, T in mids.items():
        got = refresh(rets, mkt, T).reset_index(names="permno")
        rows.append(got.assign(eom=eom, T=T))
    return pd.concat(rows, ignore_index=True)


# One mid-month close's rows: the month end's with the fresh inputs.
def swapped(rows: pd.DataFrame, g: pd.DataFrame, eom, cols: list) -> pd.DataFrame:
    rows = rows.copy()
    new = rows[["permno"]].merge(g, on="permno", how="left").assign(eom=eom)
    for c in cols:
        z = inputs.ghz(new, c)
        # A name without 15 sessions keeps its month-end value.
        rows[c] = z.where(new[c].notna(), rows[c].to_numpy()).fillna(0.0).to_numpy()
    return rows


# The mid-month forecasts from el_plus's rows, weights and rho.
def score(raw_frame: pd.DataFrame, feats: pd.DataFrame, parts, rho: pd.Series) -> pd.DataFrame:
    raw_frame = raw_frame.copy()
    raw_frame["eom"] = pd.to_datetime(raw_frame["eom"]).astype("datetime64[ns]")
    cols = [c for c in raw_frame.columns if c not in ("permno", "eom", "T")]
    out = []
    for (eom, T), g in raw_frame.groupby(["eom", "T"]):
        rows = feats[feats["date"] == eom + pd.offsets.MonthEnd(1)]
        rows = swapped(rows, g, eom, cols)
        fw = pd.read_parquet(parts / f"weights_{eom:%Y%m%d}.parquet")
        f = walkforward.apply(fw, rows)
        out.append(pd.DataFrame({"T": T, "eom": eom, "permno": f["permno"].to_numpy(),
                                 "mainf": f["MaInf"].to_numpy(),
                                 "rho": float(rho.loc[eom])}))  # fmt: skip
    return pd.concat(out, ignore_index=True)
