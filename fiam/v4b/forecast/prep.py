# Within-month transforms only: no full-sample statistic anywhere (Mandate §7.7).

import numpy as np
import pandas as pd


# Each characteristic as a within-month rank in [-0.5, 0.5]; missing -> 0.
def rank_features(p: pd.DataFrame, cols: list[str]) -> np.ndarray:
    g = p.groupby("eom", sort=False)[cols]
    r = g.rank(pct=True, method="average")
    n = g.transform("count")
    # Map ranks to the open interval so a lone value sits at 0.
    x = (r * n - 0.5) / n - 0.5
    return x.fillna(0.0).to_numpy(dtype=np.float32)


# A label clipped at its own month's 1st and 99th percentiles.
def winsor_label(p: pd.DataFrame, col: str, q: float = 0.01) -> pd.Series:
    lo = p.groupby("eom")[col].transform(lambda s: s.quantile(q))
    hi = p.groupby("eom")[col].transform(lambda s: s.quantile(1 - q))
    return p[col].clip(lo, hi)


# Each row's loss weight: one unit per month, split equally or by sqrt ADV.
def month_weights(p: pd.DataFrame, scheme: str = "equal") -> np.ndarray:
    if scheme == "equal":
        base = pd.Series(1.0, index=p.index)
    elif scheme == "sqrt_adv":
        base = np.sqrt(p["dolvol_126d"].clip(lower=0).fillna(0.0))
        cap = base.groupby(p["eom"]).transform(lambda s: s.quantile(0.99))
        base = base.clip(upper=cap)
    else:
        raise ValueError(f"unknown weight scheme {scheme}")
    return (base / base.groupby(p["eom"]).transform("sum")).to_numpy(dtype=float)
