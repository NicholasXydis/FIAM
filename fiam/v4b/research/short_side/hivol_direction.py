# Among high-volatility shortable names (where the model's shorts sit), which
# characteristics predict the sign of the residual return? 2015-01..2020-11 only.
import numpy as np, pandas as pd
from fiam.v4b.forecast import data
CUT = pd.Timestamp("2020-12-31")
chars = data.characteristics()
p = data.panel(cut=CUT); p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()].copy()
p["sector"] = p["gics"].astype(str).str[:2]; p["y"] = p["ret_exc_lead1m"].astype(float)
def resid(d):
    b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
    X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
    c, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    return pd.Series(d["y"].to_numpy() - X @ c, index=d.index)
p["res"] = p.groupby("eom", group_keys=False).apply(resid, include_groups=False)
p["vt"] = p.groupby("eom")["ivol_capm_252d"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
T = lambda s: s.mean() / s.std() * np.sqrt(len(s))
half = pd.Timestamp("2017-12-31")
rows = []
for c in chars:
    if p[c].notna().mean() < 0.6: continue
    r = {}
    for v in (0, 2):
        d = p[p.vt == v]
        q = d.groupby("eom")[c].rank(pct=True)
        lo = d.loc[q <= 0.2].groupby("eom")["res"].mean(); hi = d.loc[q >= 0.8].groupby("eom")["res"].mean()
        sp = (hi - lo).dropna()
        r[f"t_v{v}"] = T(sp); r[f"h1_v{v}"] = T(sp[sp.index <= half]); r[f"h2_v{v}"] = T(sp[sp.index > half])
        r[f"lo_v{v}"] = lo.mean(); r[f"hi_v{v}"] = hi.mean()
    rows.append({"char": c, **r})
u = pd.DataFrame(rows).set_index("char")
u["stable_hv"] = (np.sign(u.h1_v2) == np.sign(u.h2_v2)) & (u.h1_v2.abs() > 1) & (u.h2_v2.abs() > 1)
pd.set_option("display.width", 250)
print("HIGH-VOL tercile, top 30 by |t|:")
print(u.sort_values("t_v2", key=abs, ascending=False)[["t_v2","h1_v2","h2_v2","lo_v2","hi_v2","stable_hv","t_v0"]].head(30).round(3).to_string())
print("stable in both halves (|t|>1 each):", u.index[u.stable_hv].tolist())
print("high-vol tercile mean res", p[p.vt==2].groupby("eom")["res"].mean().mean(), "median", p[p.vt==2]["res"].median())
