# Hedge beta: the judges' object, estimated to be shrunk, not raw (R§4).
#
# Judged beta is contemporaneous OLS of excess returns on the S&P 500 excess
# (Mandate §9.2). Estimation here uses the Fama-French daily market excess
# (CRSP value-weighted total return): it covers 2015-2020 blind, while the
# local FRED SP500 file starts 2016-09 and is price-only. The S&P exhibit is
# reporting's job; this beta is the hedging input and the risk model's
# market column. Recipe, frozen before any OOS use (eval 03 F3.2):
#   252-session OLS per stock (returns clipped at ±50% against bad ticks,
#   >=200 paired sessions), Vasicek-shrunk toward its sector mean, then
#   blended 50/50 with the panel's 60-month beta. Dimson/downside betas in
#   the panel stay diagnostics; they never enter the constraint.
# Weekly refresh: the beta in force on a session was estimated on data
# ending before that week's first session.

import zipfile
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine import inputs
from fiam.v4b.forecast import data

FF_DAILY = Path(__file__).resolve().parents[3] / "data" / "benchmarks" / "ff5_daily.zip"
WINDOW, MIN_OBS, CLIP = 252, 200, 0.5
BLEND_DAILY = 0.5  # [Judgement] R§4: half daily Vasicek, half 60m monthly.


# Daily market excess and cash rate (decimals) to the blind cutoff.
def market_daily(cut: pd.Timestamp = data.BLIND) -> pd.DataFrame:
    with zipfile.ZipFile(FF_DAILY) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", errors="ignore")
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines) if ln.startswith(",Mkt-RF"))
    body = [ln for ln in lines[head + 1 :] if ln[:8].isdigit()]
    t = pd.read_csv(StringIO("\n".join(body)), header=None)
    t.columns = ["date", "mkt_rf", "smb", "hml", "rmw", "cma", "rf"]
    t["date"] = pd.to_datetime(t["date"].astype(str), format="%Y%m%d")
    t = t[t["date"] <= cut]
    return t.set_index("date")[["mkt_rf", "rf"]].astype(float) / 100.0


# Wide daily excess returns (sessions x permno) from CRSP total returns.
def excess_wide(
    start="2014-12-01", cut: pd.Timestamp = data.BLIND
) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = inputs.daily(start, blind_until=str(cut.date()))
    mkt = market_daily(cut)
    wide = d.pivot(index="date", columns="permno", values="total_return")
    days = wide.index.intersection(mkt.index)
    wide = wide.reindex(days)
    excess = wide.sub(mkt.loc[days, "rf"], axis=0).clip(-CLIP, CLIP)
    return excess, mkt.loc[days]


# Rolling 252d OLS beta, its standard error, count and market Sxx per stock.
# Pairwise-complete: each stock uses the sessions where it traded.
def rolling_beta(excess: pd.DataFrame, mkt_rf: pd.Series) -> dict:
    m = mkt_rf.to_numpy(dtype=float)
    present = excess.notna()
    x = excess.to_numpy(dtype=float)
    n = present.rolling(WINDOW, min_periods=MIN_OBS).sum()
    mm = pd.DataFrame(
        np.where(present, m[:, None], np.nan), index=excess.index, columns=excess.columns
    )
    sm = mm.rolling(WINDOW, min_periods=MIN_OBS).sum()
    sx = excess.rolling(WINDOW, min_periods=MIN_OBS).sum()
    smm = (mm**2).rolling(WINDOW, min_periods=MIN_OBS).sum()
    sxx_stock = (excess**2).rolling(WINDOW, min_periods=MIN_OBS).sum()
    smx = (
        pd.DataFrame(
            np.where(present, x * m[:, None], np.nan), index=excess.index, columns=excess.columns
        )
        .rolling(WINDOW, min_periods=MIN_OBS)
        .sum()
    )
    nn = n.to_numpy(dtype=float)
    sxx = smm.to_numpy() - sm.to_numpy() ** 2 / nn
    sxy = smx.to_numpy() - sm.to_numpy() * sx.to_numpy() / nn
    beta = np.where(sxx > 0, sxy / np.where(sxx > 0, sxx, np.nan), np.nan)
    syy = sxx_stock.to_numpy() - sx.to_numpy() ** 2 / nn
    rss = np.maximum(syy - beta * sxy, 0.0)
    se = np.sqrt(rss / np.maximum(nn - 2, 1) / np.where(sxx > 0, sxx, np.nan))
    def frame(a):
        return pd.DataFrame(a, index=excess.index, columns=excess.columns)

    return {"beta": frame(beta), "se": frame(se), "n": n, "sxx": frame(sxx)}


# Vasicek shrink toward the sector mean, precision-weighted, one cross-section.
def vasicek(beta: pd.Series, se: pd.Series, sector: pd.Series) -> pd.Series:
    f = pd.DataFrame({"b": beta, "se": se, "s": sector}).dropna(subset=["b"])
    prior_var = f.groupby("s")["b"].transform("var").clip(lower=0.01)
    prior_mean = f.groupby("s")["b"].transform("mean")
    own = 1.0 / f["se"].fillna(f["se"].median()).clip(lower=0.02) ** 2
    out = (f["b"] * own + prior_mean / prior_var) / (own + 1.0 / prior_var)
    return out.reindex(beta.index)


# Monthly hedge betas at each formation eom in the exposures table.
# The daily leg is the rolling beta at the last session on or before eom
# (known at the eom close; the book forms the next session).
def hedge_betas(exp: pd.DataFrame, rolled: dict | None = None) -> pd.DataFrame:
    if rolled is None:
        excess, mkt = excess_wide()
        rolled = rolling_beta(excess, mkt["mkt_rf"])
    rows = []
    days = rolled["beta"].index
    for eom, month in exp.groupby("eom"):
        pos = days.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 0:
            continue
        m = month.set_index("permno")
        names = m.index.intersection(rolled["beta"].columns)
        b = rolled["beta"].iloc[pos].reindex(names)
        se = rolled["se"].iloc[pos].reindex(names)
        bv = vasicek(b, se, m.loc[names, "sector"])
        monthly = m.loc[names, "beta_60m"]
        hedge = BLEND_DAILY * bv + (1 - BLEND_DAILY) * monthly
        hedge = hedge.fillna(bv).fillna(monthly)
        rows.append(
            pd.DataFrame(
                {
                    "eom": eom,
                    "permno": names,
                    "beta_raw": b.to_numpy(),
                    "beta_se": se.to_numpy(),
                    "beta_vasicek": bv.to_numpy(),
                    "beta_hedge": hedge.to_numpy(),
                    "beta_sxx": rolled["sxx"].iloc[pos].reindex(names).to_numpy(),
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    # Names with neither leg take their sector-month mean, then 1.0.
    joined = exp[["eom", "permno", "sector"]].merge(out, on=["eom", "permno"], how="left")
    fill = joined.groupby(["eom", "sector"])["beta_hedge"].transform("mean")
    joined["beta_hedge"] = joined["beta_hedge"].fillna(fill).fillna(1.0)
    return joined.drop(columns="sector")


# Daily beta in force: refreshed weekly, estimated before the week starts.
# Returns a sessions x permno frame aligned to the rolling beta's grid.
def weekly_carried(rolled_beta: pd.DataFrame) -> pd.DataFrame:
    days = rolled_beta.index
    week = days.to_period("W")
    first = pd.Series(days, index=days).groupby(week).transform("min")
    anchors = sorted(set(first))
    sampled = rolled_beta.shift(1).reindex(anchors)
    return sampled.reindex(days, method="ffill")


# Daily hedge-beta grid for the factor model: weekly Vasicek + monthly blend.
# At each weekly anchor the Vasicek cross-section uses the rolling beta of
# the prior session and sectors from the last eom before the anchor.
def hedge_beta_daily(exp: pd.DataFrame, rolled: dict) -> pd.DataFrame:
    days = rolled["beta"].index
    week = days.to_period("W")
    anchors = sorted(set(pd.Series(days, index=days).groupby(week).transform("min")))
    eoms = pd.DatetimeIndex(sorted(exp["eom"].unique()))
    by_month = {e: g.set_index("permno") for e, g in exp.groupby("eom")}
    out = {}
    for anchor in anchors:
        pos = days.get_loc(anchor) - 1
        epos = eoms.searchsorted(pd.Timestamp(anchor), side="left") - 1
        if pos < 0 or epos < 0:
            continue
        month = by_month[eoms[epos]]
        names = month.index.intersection(rolled["beta"].columns)
        b = rolled["beta"].iloc[pos].reindex(names)
        se = rolled["se"].iloc[pos].reindex(names)
        bv = vasicek(b, se, month.loc[names, "sector"])
        hedge = BLEND_DAILY * bv + (1 - BLEND_DAILY) * month.loc[names, "beta_60m"]
        out[anchor] = hedge.fillna(bv).fillna(month.loc[names, "beta_60m"])
    grid = pd.DataFrame(out).T.reindex(days).ffill()
    grid.index.name = "date"
    return grid
