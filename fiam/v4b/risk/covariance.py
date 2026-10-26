# Factor covariance F: EWMA with Newey-West autocovariances (R§4).
#
# F at a formation uses factor returns strictly before the formation
# session. Half-life is selected from {42, 84} sessions by the pre-OOS bias
# statistic (validate.py); diagonal shrinkage delta=0.2 is a stated
# judgement, not searched. Horizon scaling keeps autocovariances:
#   F_H = H*G0 + sum_{j<H} (H-j)*(Gj + Gj'),  Gj = EWMA lag-j autocovariance,
# which is the exact H-session variance under the estimated dynamics and
# reduces to H*F when factor returns are serially uncorrelated. Specific
# variance scales by H (serially uncorrelated specifics, stated).

import numpy as np
import pandas as pd

HALF_LIVES = (42, 84)
DELTA = 0.2  # [Judgement] shrink F toward its diagonal.
NW_LAGS = 5  # Bartlett lags in the 1-session Newey-West adjustment.
MIN_DAYS = 126


# EWMA autocovariances G0..G_{maxlag} from rows before `date`.
def autocovariances(
    factors: pd.DataFrame, date, half_life: int, maxlag: int
) -> list[np.ndarray] | None:
    hist = factors[factors.index < pd.Timestamp(date)].dropna()
    if len(hist) < MIN_DAYS + maxlag:
        return None
    x = hist.to_numpy(dtype=float)
    age = np.arange(len(x) - 1, -1, -1)
    w = 0.5 ** (age / half_life)
    w = w / w.sum()
    mu = w @ x
    xc = x - mu
    out = []
    for j in range(maxlag + 1):
        if j == 0:
            out.append((xc * w[:, None]).T @ xc)
        else:
            wj = w[j:]
            wj = wj / wj.sum()
            out.append((xc[j:] * wj[:, None]).T @ xc[:-j])
    return out


# Nearest sane covariance: symmetrise, floor eigenvalues, shrink diagonal-ward.
def _regularise(cov: np.ndarray, delta: float = DELTA) -> np.ndarray:
    cov = 0.5 * (cov + cov.T)
    vals, vecs = np.linalg.eigh(cov)
    floor = max(float(vals.max()), 0.0) * 1e-8
    cov = (vecs * np.clip(vals, floor, None)) @ vecs.T
    return (1 - delta) * cov + delta * np.diag(np.diag(cov))


# One-session contemporaneous covariance, without long-run autocovariances.
def factor_cov_daily(factors: pd.DataFrame, date, half_life: int = 84) -> pd.DataFrame | None:
    g = autocovariances(factors, date, half_life, 0)
    if g is None:
        return None
    return pd.DataFrame(_regularise(g[0]), index=factors.columns, columns=factors.columns)


# One-session factor covariance with the Newey-West pre-adjustment.
def factor_cov(factors: pd.DataFrame, date, half_life: int = 84) -> pd.DataFrame | None:
    g = autocovariances(factors, date, half_life, NW_LAGS)
    if g is None:
        return None
    cov = g[0] + sum((1 - j / (NW_LAGS + 1)) * (g[j] + g[j].T) for j in range(1, NW_LAGS + 1))
    return pd.DataFrame(_regularise(cov), index=factors.columns, columns=factors.columns)


# H-session factor covariance from the same autocovariances (no rescaling fudge).
def factor_cov_horizon(
    factors: pd.DataFrame, date, half_life: int = 84, horizon: int = 21
) -> pd.DataFrame | None:
    if horizon == 1:
        return factor_cov(factors, date, half_life)
    g = autocovariances(factors, date, half_life, horizon - 1)
    if g is None:
        return None
    cov = horizon * g[0] + sum((horizon - j) * (g[j] + g[j].T) for j in range(1, horizon))
    return pd.DataFrame(_regularise(cov), index=factors.columns, columns=factors.columns)


# Correlation-stressed F: correlations halfway to +-1, vols x1.5 (R§4).
def stressed(cov: pd.DataFrame) -> pd.DataFrame:
    v = np.sqrt(np.diag(cov.to_numpy()))
    corr = cov.to_numpy() / np.outer(v, v)
    stressed_corr = corr + 0.5 * (np.sign(corr) - corr)
    np.fill_diagonal(stressed_corr, 1.0)
    sv = v * 1.5
    out = stressed_corr * np.outer(sv, sv)
    return pd.DataFrame(_regularise(out, delta=0.0), index=cov.index, columns=cov.columns)
