# Market betas: Welch's slope-winsorised and Dimson's.

import numpy as np
import pandas as pd

from fiam.vfinal import data

# Welch on 252 sessions with a 126-day half-life; the trigger on 126/63.
WELCH_DAYS, WELCH_HALF = 252, 126
TRIGGER_DAYS, TRIGGER_HALF = 126, 63
# Dimson on 126 sessions with one lag and one lead of the market.
DIMSON_DAYS = 126


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
    # Half the window observed at least, for Welch's beta.
    enough = ((weight > 0).sum(axis=0) >= len(x) // 2) & (var > 0)
    out = np.divide(cov, var, out=np.full(len(total), np.nan), where=enough)
    return pd.Series(out, index=stock.columns, name="welch")


# Dimson (1979): slopes on the market's lag, day and lead, summed.
def dimson(stock: pd.DataFrame, market: pd.Series) -> pd.Series:
    m = market.to_numpy(dtype=float)
    # Day d needs the market on d-1 and d+1, so the ends drop out.
    x = np.column_stack([np.ones(len(m) - 2), m[:-2], m[1:-1], m[2:]])
    out = {}
    for permno, y in stock.iloc[1:-1].items():
        y = y.to_numpy(dtype=float)
        ok = ~np.isnan(y)
        if ok.sum() < len(y) // 2:
            out[permno] = np.nan
            continue
        coef, *_ = np.linalg.lstsq(x[ok], y[ok], rcond=None)
        out[permno] = float(coef[1:].sum())
    return pd.Series(out, name="dimson").reindex(stock.columns)


# Both betas for these stocks at the close of T, from data through T.
def at(T, permnos) -> pd.DataFrame:
    days = data.sessions(pd.Timestamp(T) - pd.Timedelta(days=400), T)[-WELCH_DAYS:]
    rets = data.dsf(permnos, days[0], days[-1])
    # Only bill rates public by T's close (the next business day).
    rf = data.rf_daily(days, by=T)
    stock = data.matrix(rets, "ret", days, permnos).sub(rf, axis=0)
    market = data.market_daily(days) - rf
    # A day with no market return drops out of every estimate.
    keep = market.notna().to_numpy()
    stock, market = stock[keep], market[keep]
    # 126 regression days whose last lead is T itself, never a later day.
    window = DIMSON_DAYS + 2
    both = pd.DataFrame(
        {
            "welch": welch(stock, market),
            "dimson": dimson(stock.iloc[-window:], market.iloc[-window:]),
            "trigger": welch(stock.iloc[-TRIGGER_DAYS:], market.iloc[-TRIGGER_DAYS:], TRIGGER_HALF),
        }
    )
    return both.rename_axis("permno").reset_index().assign(date=pd.Timestamp(T))
