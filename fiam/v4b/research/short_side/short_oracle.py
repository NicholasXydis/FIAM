# What predicts shortable losers pre-2021, and what does the model load on?
# Shortable pool (short_ok), formations 2015-01..2020-11, labels end <= 2020-12.
import json
import sys

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data

CUT = pd.Timestamp("2020-12-31")
OUT = sys.argv[1]

chars = data.characteristics()
p = data.panel(cut=CUT)
p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()].copy()
p["sector"] = p["gics"].astype(str).str[:2]
p["y"] = p["ret_exc_lead1m"].astype(float)


def resid(d):
    b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
    S = pd.get_dummies(d["sector"]).to_numpy(float)
    X = np.column_stack([b, S])
    coef, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    return pd.Series(d["y"].to_numpy() - X @ coef, index=d.index)


p["res"] = p.groupby("eom", group_keys=False).apply(resid, include_groups=False)
months = np.sort(p["eom"].unique())
half = pd.Timestamp("2017-12-31")
print("rows", len(p), "months", len(months), "names/month", int(p.groupby("eom").size().median()))

g = p.groupby("eom")
rows = []
for c in chars:
    if p[c].notna().mean() < 0.5:
        continue
    r = g[c].rank(pct=True)
    lo, hi = r <= 0.2, r >= 0.8
    m_lo = p.loc[lo, "res"].groupby(p.loc[lo, "eom"]).mean()
    m_hi = p.loc[hi, "res"].groupby(p.loc[hi, "eom"]).mean()
    med_lo = p.loc[lo, "res"].groupby(p.loc[lo, "eom"]).median()
    med_hi = p.loc[hi, "res"].groupby(p.loc[hi, "eom"]).median()
    sp = (m_hi - m_lo).dropna()
    e1, e2 = sp[sp.index <= half], sp[sp.index > half]
    t = lambda s: s.mean() / s.std() * np.sqrt(len(s))
    rows.append({"char": c, "cov": p[c].notna().mean(), "spread": sp.mean(), "t": t(sp),
                 "t_h1": t(e1), "t_h2": t(e2), "lo_mean": m_lo.mean(), "hi_mean": m_hi.mean(),
                 "lo_med": med_lo.mean(), "hi_med": med_hi.mean()})
u = pd.DataFrame(rows).set_index("char")
# The short end of each characteristic is the quintile with the lower mean residual.
u["short_end"] = np.where(u["spread"] > 0, "lo", "hi")
u["short_mean"] = np.where(u["spread"] > 0, u["lo_mean"], u["hi_mean"])
u["short_med"] = np.where(u["spread"] > 0, u["lo_med"], u["hi_med"])
u["stable"] = np.sign(u["t_h1"]) == np.sign(u["t_h2"])
u = u.sort_values("t", key=abs, ascending=False)

# Model alignment: cross-sectional rank corr of scores with each characteristic.
f = pd.concat([rj.scores(w) for w in ("valid",)])
early = rj._load("up")
print("forecast eom range", early["eom"].min(), early["eom"].max())
f = f[f["short_ok"]]
q = f.merge(p[["permno", "eom", "res", "sector", *chars]], on=["permno", "eom"], how="inner")
corr = {}
for s in ("tail_MaInf", "mean_MaInf", "up_MaInf", "down_MaInf"):
    corr[s] = {c: q.groupby("eom").apply(lambda d: d[s].corr(d[c], method="spearman"), include_groups=False).mean()
               for c in u.index[:40]}
u = u.join(pd.DataFrame(corr), how="left")
pd.set_option("display.width", 250, "display.max_rows", 200)
cols = ["cov", "spread", "t", "t_h1", "t_h2", "short_end", "short_mean", "short_med", "tail_MaInf", "mean_MaInf", "down_MaInf"]
print(u[cols].head(40).round(4).to_string())

# Model D0 vs oracle losers (bottom decile of res) in validation.
q["dec"] = q.groupby("eom")["tail_MaInf"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
q["loser"] = q.groupby("eom")["res"].transform(lambda s: s <= s.quantile(0.1))
q["winner"] = q.groupby("eom")["res"].transform(lambda s: s >= s.quantile(0.9))
by = q.groupby("dec").agg(res=("res", "mean"), res_med=("res", "median"), loser=("loser", "mean"), winner=("winner", "mean"))
print(by.round(4).to_string())
u.to_csv(OUT)
