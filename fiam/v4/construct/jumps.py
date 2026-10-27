# Lee-Mykland jumps on market-relative daily returns (reading 23 (m)).

import numpy as np
import pandas as pd

# Sessions tested, the bipower window before each and its least count.
YEAR, WINDOW, MIN_VALID = 252, 63, 42
# Lee and Mykland's (2008) significance; the screen's percentile.
ALPHA, SCREEN_PCT = 0.01, 0.90


# Their critical value for the largest |L| of n tests at alpha.
def critical(n: int = YEAR, alpha: float = ALPHA) -> float:
    c = np.sqrt(2 / np.pi)
    root = np.sqrt(2 * np.log(n))
    cn = root / c - (np.log(np.pi) + np.log(np.log(n))) / (2 * c * root)
    sn = 1 / (c * root)
    return float(cn + sn * -np.log(-np.log(1 - alpha)))


# Up and down jump counts over the 252 sessions to T, T's close in.
def counts(returns: pd.DataFrame, market: pd.Series, T, names) -> pd.DataFrame:
    r = returns.loc[returns.index <= pd.Timestamp(T)].reindex(columns=names)
    r = r.iloc[-(YEAR + WINDOW + 1) :]
    e = r.sub(market.reindex(r.index), axis=0)
    # B_d: the mean of |e_k||e_(k-1)| over the 63 sessions before d.
    b = (e.abs() * e.abs().shift(1)).rolling(WINDOW, min_periods=MIN_VALID).mean().shift(1)
    stat = (e / np.sqrt(b.where(b > 0))).iloc[-YEAR:]
    k = critical()
    out = pd.DataFrame({"jump_up": (stat > k).sum(), "jump_down": (stat < -k).sum()})
    return out.reindex(names).fillna(0).astype(int)


# Flags: a count of at least max(1, the interpolated 90th percentile).
def flags(c: pd.DataFrame) -> pd.DataFrame:
    up = c["jump_up"] >= max(1.0, float(c["jump_up"].quantile(SCREEN_PCT)))
    down = c["jump_down"] >= max(1.0, float(c["jump_down"].quantile(SCREEN_PCT)))
    return c.assign(jumpy_up=up, jumpy_down=down)
