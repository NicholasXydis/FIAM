# Fixed 50/50 rank blend of the two E-LASSO runs; validation decides, OOS diagnostic.
import sys, numpy as np, pandas as pd
from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
win = sys.argv[1]
CUT = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
p = data.panel(cut=CUT); p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()][["permno","eom","gics","beta_60m","ret_exc_lead1m"]]
f = rj.scores(win)[["permno","eom","tail_MaInf","mean_MaInf"]].merge(p, on=["permno","eom"])
f["sector"] = f["gics"].astype(str).str[:2]; f["y"] = f["ret_exc_lead1m"].astype(float)
def resid(d):
    b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
    X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
    c, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    return pd.Series(d["y"].to_numpy() - X @ c, index=d.index)
f["res"] = f.groupby("eom", group_keys=False).apply(resid, include_groups=False)
g = f.groupby("eom")
f["blend"] = g["tail_MaInf"].rank(pct=True) + g["mean_MaInf"].rank(pct=True)
T = lambda s: f"{s.mean()*100:+.2f} ({s.mean()/s.std()*np.sqrt(len(s)):+.1f})"
print("==", win, "shortable pool, beta+sector residual, %/month (t)")
for k in ("tail_MaInf", "mean_MaInf", "blend"):
    f["dec"] = f.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = f.groupby(["eom","dec"])["res"].mean().unstack()
    ic = f.groupby("eom").apply(lambda d: d[k].corr(d["res"], method="spearman"), include_groups=False)
    yrs = m[0].groupby(m.index.year).mean().mul(100).round(2).to_dict()
    print(f" {k:11s} IC {T(ic*1)}  D0 {T(m[0])}  D0-1 {T(m[[0,1]].mean(1))}  D9 {T(m[9])}  D8-9 {T(m[[8,9]].mean(1))}  spread {T(m[9]-m[0])}  D0 by yr {yrs}")
print(" corr(tail, mean)", f.groupby("eom").apply(lambda d: d.tail_MaInf.corr(d.mean_MaInf, method="spearman"), include_groups=False).mean())
