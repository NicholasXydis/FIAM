# Does the E-LASSO score rank direction among similar-volatility names?
# Validation (2016-12..2020-11) decides; OOS printed as a diagnostic only.
import sys, numpy as np, pandas as pd
from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
win = sys.argv[1]
CUT = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
p = data.panel(cut=CUT); p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()][["permno","eom","gics","beta_60m","ivol_capm_252d","ret_exc_lead1m"]].copy()
f = rj.scores(win)[["permno","eom","tail_MaInf","mean_MaInf","up_MaInf","down_MaInf"]].merge(p, on=["permno","eom"])
f["sector"] = f["gics"].astype(str).str[:2]; f["y"] = f["ret_exc_lead1m"].astype(float)
def resid(d):
    b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
    X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
    c, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    return pd.Series(d["y"].to_numpy() - X @ c, index=d.index)
f["res"] = f.groupby("eom", group_keys=False).apply(resid, include_groups=False)
f["vt"] = f.groupby("eom")["ivol_capm_252d"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
f["ext"] = f["up_MaInf"] + f["down_MaInf"]
T = lambda s: f"{s.mean()*100:+.2f}% (t {s.mean()/s.std()*np.sqrt(len(s)):+.2f})"
for k in ("tail_MaInf", "mean_MaInf"):
    print("==", win, k)
    for v in range(5):
        d = f[f.vt == v].copy()
        d["q"] = d.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
        m = d.groupby(["eom","q"])["res"].mean().unstack()
        print(f" vol quintile {v}: Q0 {T(m[0])} Q4 {T(m[4])} spread {T(m[4]-m[0])}  ivol med {d.ivol_capm_252d.median():.4f}")
    # vol-neutral score: rank within vol quintile, pooled deciles
    f["vn"] = f.groupby(["eom","vt"])[k].rank(pct=True)
    f["dec"] = f.groupby("eom")["vn"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = f.groupby(["eom","dec"])["res"].mean().unstack()
    print(f" vol-neutral deciles: D0 {T(m[0])} D9 {T(m[9])} spread {T(m[9]-m[0])}")
    f["dec2"] = f.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = f.groupby(["eom","dec2"])["res"].mean().unstack()
    print(f" plain deciles:       D0 {T(m[0])} D9 {T(m[9])} spread {T(m[9]-m[0])}")
print("corr(tail, ivol)", f.groupby("eom").apply(lambda d: d.tail_MaInf.corr(d.ivol_capm_252d, method="spearman"), include_groups=False).mean(),
      "corr(ext, ivol)", f.groupby("eom").apply(lambda d: d.ext.corr(d.ivol_capm_252d, method="spearman"), include_groups=False).mean())
