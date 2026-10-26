# One forecast from the two E-LASSO runs by the authors' own encompassing step,
# weights estimated in real time (no hand-picked blend).
#
# 1. The tail score is put in return units the way E-LASSO treats any
#    predictor: a month-t value-weighted slope of ret on the score, averaged
#    over all months realised by the formation (MaInf), applied to the score.
# 2. Encompassing as in programForecastElasso.R: each month, the WLS slope of
#    e_A on (e_A - e_B), clipped to [0, 1], averaged over realised months; the
#    forecast is (1 - lambda) * A + lambda * B with A = mean E-LASSO, B = step 1.
# Usage: python -m fiam.v4b.research.short_side.encompass valid|oos
import sys

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data


def wls_slope(x, y, w):
    w = w / w.sum()
    xm, ym = (w * x).sum(), (w * y).sum()
    return ((w * (x - xm) * (y - ym)).sum() / max((w * (x - xm) ** 2).sum(), 1e-18), ym - xm * 0)


def forecasts() -> pd.DataFrame:
    m, up, dn = (rj._load(k) for k in ("ret", "up", "down"))
    key = ["eom", "permno"]
    f = m[key + ["me", "ret", "MaInf"]].rename(columns={"MaInf": "A"})
    t = up[key + ["MaInf"]].merge(dn[key + ["MaInf"]], on=key, suffixes=("_u", "_d"))
    f = f.merge(t.assign(tail=t.MaInf_u - t.MaInf_d)[key + ["tail"]], on=key)
    f = f.sort_values(key, ignore_index=True)
    eoms = np.sort(f["eom"].unique())
    rows = {e: np.flatnonzero(f["eom"].to_numpy() == e) for e in eoms}
    ret, A, S, w = (f[c].to_numpy(float) for c in ("ret", "A", "tail", "me"))
    # Month-e slope/intercept of ret (realised in month e+1) on the tail score.
    a_e, b_e = [], []
    for e in eoms:
        i = rows[e]
        ww = w[i] / w[i].sum()
        sm, rm = (ww * S[i]).sum(), (ww * ret[i]).sum()
        b = (ww * (S[i] - sm) * (ret[i] - rm)).sum() / (ww * (S[i] - sm) ** 2).sum()
        a_e.append(rm - b * sm)
        b_e.append(b)
    B = np.full(len(f), np.nan)
    lam_e = np.full(len(eoms), np.nan)
    L = np.full(len(f), np.nan)
    for k, e in enumerate(eoms):
        i = rows[e]
        # Month e's return is realised at eom e+1, so formation e uses months < e.
        if k >= 1:
            B[i] = np.mean(a_e[:k]) + np.mean(b_e[:k]) * S[i]
        if np.isfinite(B[i]).all():
            eA, eB = ret[i] - A[i], ret[i] - B[i]
            d = eA - eB
            ww = w[i] / w[i].sum()
            dm, am = (ww * d).sum(), (ww * eA).sum()
            lam_e[k] = np.clip((ww * (d - dm) * (eA - am)).sum() / (ww * (d - dm) ** 2).sum(), 0, 1)
        prior = lam_e[:k][np.isfinite(lam_e[:k])]
        if len(prior):
            L[i] = prior.mean()
    f["B"], f["lam"] = B, L
    f["enc"] = (1 - f["lam"]) * f["A"] + f["lam"] * f["B"]
    return f


def judge(win: str, f: pd.DataFrame) -> None:
    lo, hi = (pd.Timestamp(x) for x in rj.WINDOWS[win])
    cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()][["permno", "eom", "gics", "beta_60m", "ret_exc_lead1m"]]
    g = f[f["eom"].between(lo, hi)].merge(p, on=["permno", "eom"])
    g["sector"] = g["gics"].astype(str).str[:2]
    g["y"] = g["ret_exc_lead1m"].astype(float)

    def resid(d):
        b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
        X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
        c, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        return pd.Series(d["y"].to_numpy() - X @ c, index=d.index)

    g["res"] = g.groupby("eom", group_keys=False).apply(resid, include_groups=False)
    gg = g.groupby("eom")
    g["blend50"] = gg["A"].rank(pct=True) + gg["tail"].rank(pct=True)
    T = lambda s: f"{s.mean()*100:+.2f} ({s.mean()/s.std()*np.sqrt(len(s)):+.1f})"
    lam = g.groupby("eom")["lam"].first()
    print(f"== {win}: encompassing weight on the tail forecast, by year:",
          lam.groupby(lam.index.year).mean().round(2).to_dict())
    for k in ("A", "tail", "blend50", "enc"):
        g["dec"] = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        m = g.groupby(["eom", "dec"])["res"].mean().unstack()
        print(f" {k:8s} D0 {T(m[0])}  D0-1 {T(m[[0, 1]].mean(1))}  D9 {T(m[9])}  D8-9 {T(m[[8, 9]].mean(1))}  spread {T(m[9] - m[0])}")


if __name__ == "__main__":
    fc = forecasts()
    for w in sys.argv[1:] or ["valid"]:
        judge(w, fc)
