# Cross-section helpers every model input shares.

import numpy as np
import pandas as pd

# Exposures are z-scores clipped here, as the attribution factors are.
Z_CLIP = 3.0


# Average ranks mapped linearly onto [-1, 1]; missing stays missing.
def unit_rank(values) -> pd.Series:
    x = pd.Series(values, dtype=float)
    r = x.rank(method="average")
    n = int(x.notna().sum())
    if n < 2:
        return pd.Series(np.where(x.notna(), 0.0, np.nan), index=x.index)
    return 2 * (r - 1) / (n - 1) - 1


# unit_rank within each group, such as each formation month.
def unit_rank_by(values: pd.Series, groups) -> pd.Series:
    return values.groupby(groups, group_keys=False).transform(unit_rank)


# A weighted z-score clipped at 3; weights are root caps.
def zscore(values, weights) -> pd.Series:
    x = pd.Series(values, dtype=float)
    w = pd.Series(np.asarray(weights, dtype=float), index=x.index)
    ok = x.notna() & w.notna() & (w > 0)
    if ok.sum() < 2:
        return pd.Series(np.nan, index=x.index)
    mean = np.average(x[ok], weights=w[ok])
    sd = np.sqrt(np.average((x[ok] - mean) ** 2, weights=w[ok]))
    if not sd > 0:
        return pd.Series(np.nan, index=x.index)
    return ((x - mean) / sd).clip(-Z_CLIP, Z_CLIP)


# Weighted least squares residuals; a rank-deficient design still fits.
def wls_residuals(y, design: pd.DataFrame, weights) -> pd.Series:
    yv = np.asarray(y, dtype=float)
    X = design.to_numpy(dtype=float)
    root = np.sqrt(np.asarray(weights, dtype=float))
    coef, *_ = np.linalg.lstsq(X * root[:, None], yv * root, rcond=None)
    return pd.Series(yv - X @ coef, index=design.index)
