# Daily factor returns by cross-sectional WLS (R§4, eval 03 F1.2).
#
# One regression per session on the liquid (long-eligible) universe:
# excess return on [hedge beta, sector dummies, five styles], weights
# sqrt(me), no intercept. Barra identification: cap-weighted sector factor
# returns sum to zero, so sectors are deviations from the market factor.
# Exposures for session s come from the last eom before s and the hedge-beta
# grid in force that week (both known before s). Residuals are kept wide:
# they are the specific-risk model's input. Results cache under v4b/cache/;
# the cache key carries the blind cutoff so OOS data can never leak in by
# reusing a file built with a later cut.

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk import exposures

CACHE = Path(__file__).resolve().parents[1] / "cache"
MIN_NAMES = 200


# Constrained WLS: min ||sqrt(W)(y - Xf)||^2 s.t. c'f = 0, solved by KKT.
def constrained_wls(x: np.ndarray, y: np.ndarray, w: np.ndarray, c: np.ndarray) -> np.ndarray:
    sw = np.sqrt(w)
    xw = x * sw[:, None]
    a = xw.T @ xw
    k = a.shape[0]
    kkt = np.zeros((k + 1, k + 1))
    kkt[:k, :k] = a
    kkt[:k, k] = c
    kkt[k, :k] = c
    rhs = np.concatenate([xw.T @ (y * sw), [0.0]])
    sol, *_ = np.linalg.lstsq(kkt, rhs, rcond=None)
    return sol[:k]


# Cap weights per sector column for the Barra constraint (sum to total cap).
def _barra_vector(sectors: list[str], me: pd.Series, sector: pd.Series) -> np.ndarray:
    caps = me.groupby(sector).sum()
    return np.array([caps.get(s.removeprefix("s_"), 0.0) for s in sectors])


# Runs every session; returns (factor returns, wide residuals).
def estimate(
    exp: pd.DataFrame | None = None, cut: pd.Timestamp = data.BLIND
) -> tuple[pd.DataFrame, pd.DataFrame]:
    exp = exposures.monthly(cut) if exp is None else exp
    excess, mkt = beta_mod.excess_wide(cut=cut)
    rolled = beta_mod.rolling_beta(excess, mkt["mkt_rf"])
    grid = beta_mod.hedge_beta_daily(exp, rolled)
    carry = exposures.carried(exp, excess.index)
    all_sectors = [f"s_{s}" for s in sorted(exp["sector"].dropna().unique())]
    style_cols = list(exposures.STYLES)
    by_month = {}
    for eom, month in exp.groupby("eom"):
        x, _ = exposures.design(month)
        x = x.reindex(columns=[*all_sectors, *style_cols], fill_value=0.0)
        by_month[eom] = (x, all_sectors, month.set_index("permno"))
    cols = ["mkt", *all_sectors, *style_cols]
    fac_rows, resid_arr = {}, np.full(excess.shape, np.nan)
    y_all = excess.to_numpy(dtype=float)
    g_all = grid.reindex(columns=excess.columns).to_numpy(dtype=float)
    col_pos = {p: j for j, p in enumerate(excess.columns)}
    for k, day in enumerate(excess.index):
        eom = carry[day]
        if eom is None:
            continue
        x_month, sectors, month = by_month[eom]
        names = x_month.index
        j = np.array([col_pos[p] for p in names])
        y = y_all[k, j]
        b = g_all[k, j]
        ok = np.isfinite(y) & np.isfinite(b)
        if ok.sum() < MIN_NAMES:
            continue
        x = np.column_stack([b[ok], x_month.to_numpy(dtype=float)[ok]])
        me = month.loc[names, "me"].clip(lower=1.0).to_numpy(dtype=float)[ok]
        c = np.zeros(x.shape[1])
        kept = names[ok]
        caps = _barra_vector(sectors, month.loc[kept, "me"], month.loc[kept, "sector"])
        c[1 : 1 + len(sectors)] = caps
        f = constrained_wls(x, y[ok], np.sqrt(me), c)
        fac_rows[day] = f
        resid_arr[k, j[ok]] = y[ok] - x @ f
    factors = pd.DataFrame.from_dict(fac_rows, orient="index", columns=cols).sort_index()
    factors.index.name = "date"
    resid = pd.DataFrame(resid_arr, index=excess.index, columns=excess.columns)
    return factors, resid


# Cached estimate for a blind cutoff; recomputes when the cache is absent.
def cached(cut: pd.Timestamp = data.BLIND) -> tuple[pd.DataFrame, pd.DataFrame]:
    CACHE.mkdir(parents=True, exist_ok=True)
    fp, rp = (
        CACHE / f"risk_factors_to_{cut:%Y%m%d}.parquet",
        CACHE / f"risk_resid_to_{cut:%Y%m%d}.parquet",
    )
    if fp.exists() and rp.exists():
        factors = pd.read_parquet(fp).set_index("date")
        resid = pd.read_parquet(rp).set_index("date")
        resid.columns = [int(c) for c in resid.columns]
        return factors, resid
    factors, resid = estimate(cut=cut)
    factors.reset_index().to_parquet(fp, index=False)
    r = resid.reset_index()
    r.columns = [str(c) for c in r.columns]
    r.to_parquet(rp, index=False)
    return factors, resid


if __name__ == "__main__":
    fac, res = cached()
    print(fac.shape, fac.index.min().date(), fac.index.max().date())
    print((fac.std() * np.sqrt(252) * 100).round(2).to_string())
    print("residual coverage:", float(res.notna().mean().mean()))
