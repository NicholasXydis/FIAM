# Fast proxy of E-LASSO's univariate step (me-weighted FM slopes, expanding
# mean, equal-weight combination) to compare training labels before an R run.
# Pre-2021 only: labels end <= 2020-12; judged on shortable pool 2016-12..2020-11.
import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data

CUT = pd.Timestamp("2020-12-31")
chars = data.characteristics()
p = data.panel(cut=CUT)
p = p.join(data.tradable(p))
p = p[p["long_ok"] & p["ret_exc_lead1m"].notna() & (p["me"] > 0)].reset_index(drop=True)
p["y"] = p["ret_exc_lead1m"].astype(float)
e = p["eom"]

# Standardised characteristics (ghz: 1/99 winsor, z, missing -> 0).
g = p.groupby("eom")
lo, hi = g[chars].transform(lambda s: s.quantile(0.01)), g[chars].transform(lambda s: s.quantile(0.99))
x = p[chars].clip(lo, hi, axis=0)
gx = x.groupby(e)
Z = ((x - gx.transform("mean")) / gx.transform("std")).fillna(0.0).to_numpy()

# Labels.
mkt = p.groupby("eom").apply(lambda d: np.average(d["y"], weights=d["me"]), include_groups=False)
beta = p["beta_60m"].fillna(p.groupby("eom")["beta_60m"].transform("median")).fillna(1.0)
res = p["y"] - beta * e.map(mkt)
sig = (p["ivol_capm_252d"].fillna(p.groupby("eom")["ivol_capm_252d"].transform("median")) * np.sqrt(21)).clip(lower=0.01)
zres = (res / sig).clip(-10, 10)


def tails(v):
    q = v.groupby(e).rank(pct=True)
    return (q > 0.9).astype(float) - (q <= 0.1).astype(float)


labels = {"raw_tail": tails(p["y"]), "z_tail": tails(zres), "raw_mean": p["y"], "z_mean": zres,
          "res_tail": tails(res)}

months = np.sort(e.unique())
idx = {m: np.flatnonzero(e.to_numpy() == m) for m in months}
w_all = p["me"].to_numpy()


def slopes(yv):
    A, B = [], []
    for m in months:
        i = idx[m]
        w = w_all[i] / w_all[i].mean()
        z = Z[i]
        yy = yv[i]
        sw = w.sum()
        zm = (w[:, None] * z).sum(0) / sw
        ym = (w * yy).sum() / sw
        zc = z - zm
        b = (w[:, None] * zc * (yy - ym)[:, None]).sum(0) / np.maximum((w[:, None] * zc**2).sum(0), 1e-12)
        A.append(ym - b * zm)
        B.append(b)
    return np.array(A), np.array(B)


fc = {}
for name, yv in labels.items():
    A, B = slopes(yv.to_numpy())
    out = np.full(len(p), np.nan)
    for k, m in enumerate(months):
        if k < 13:
            continue
        # Labels of formations <= k-1 are realised by eom k.
        a, b = A[:k].mean(0), B[:k].mean(0)
        i = idx[m]
        out[i] = (a + Z[i] * b).mean(1)
    fc[name] = out
f = p[["permno", "eom", "me", "me_company", "y", "beta_60m", "gics"]].assign(sig=sig, **fc)
f = f.join(data.tradable(p)[["short_ok"]])
f = f[f["short_ok"] & f["eom"].between("2016-12-31", "2020-11-30")].copy()
f["sector"] = f["gics"].astype(str).str[:2]


def resid(d):
    b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
    S = pd.get_dummies(d["sector"]).to_numpy(float)
    X = np.column_stack([b, S])
    coef, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    return pd.Series(d["y"].to_numpy() - X @ coef, index=d.index)


f["res"] = f.groupby("eom", group_keys=False).apply(resid, include_groups=False)
f["loser"] = f.groupby("eom")["res"].transform(lambda s: s <= s.quantile(0.1))
f["winner"] = f.groupby("eom")["res"].transform(lambda s: s >= s.quantile(0.9))
el = rj.scores("valid")[["permno", "eom", "tail_MaInf", "mean_MaInf"]]
f = f.merge(el, on=["permno", "eom"], how="left")
for k in ("z_tail", "z_mean"):
    f[k + "_x_sig"] = f[k] * f["sig"]
print("rank corr with E-LASSO tail:", {k: round(f.groupby("eom").apply(lambda d: d[k].corr(d["tail_MaInf"], method="spearman"), include_groups=False).mean(), 3)
                                       for k in [*labels, "mean_MaInf"]})


def t(s):
    return f"{s.mean()*100:+.2f}% (t {s.mean()/s.std()*np.sqrt(len(s)):+.2f})"


for k in ["tail_MaInf", "mean_MaInf", *labels, "z_tail_x_sig", "z_mean_x_sig"]:
    d = f.dropna(subset=[k]).copy()
    d["dec"] = d.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = d.groupby(["eom", "dec"])["res"].mean().unstack()
    h1 = m.index <= pd.Timestamp("2018-11-30")
    rates = d[d["dec"] == 0][["loser", "winner"]].mean()
    print(f"{k:14s} D0 {t(m[0])}  D0 med {d.loc[d.dec==0,'res'].median()*100:+.2f}%  D9 {t(m[9])}  spread {t(m[9]-m[0])}"
          f"  D0 h1/h2 {m[0][h1].mean()*100:+.2f}/{m[0][~h1].mean()*100:+.2f}  D0 lose/win {rates['loser']:.3f}/{rates['winner']:.3f}"
          f"  D0-4 {t(m[[0,1,2,3,4]].mean(1))}")

print("cross-sectional mean/sd of forecasts:", {k: (round(f.groupby('eom')[k].mean().mean(), 4), round(f.groupby('eom')[k].std().mean(), 4)) for k in labels})
print("corr(z_tail, sig):", f.groupby("eom").apply(lambda d: d["z_tail"].corr(d["sig"], method="spearman"), include_groups=False).mean(),
      "corr(z_tail_x_sig, sig):", f.groupby("eom").apply(lambda d: d["z_tail_x_sig"].corr(d["sig"], method="spearman"), include_groups=False).mean(),
      "corr(raw_tail, sig):", f.groupby("eom").apply(lambda d: d["raw_tail"].corr(d["sig"], method="spearman"), include_groups=False).mean(),
      "corr(tail_MaInf, sig):", f.groupby("eom").apply(lambda d: d["tail_MaInf"].corr(d["sig"], method="spearman"), include_groups=False).mean())
for k in ("z_tail", "z_mean"):
    f[k + "_cx_sig"] = (f[k] - f.groupby("eom")[k].transform("mean")) * f["sig"]
for k in ("z_tail_cx_sig", "z_mean_cx_sig"):
    d = f.dropna(subset=[k]).copy()
    d["dec"] = d.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = d.groupby(["eom", "dec"])["res"].mean().unstack()
    h1 = m.index <= pd.Timestamp("2018-11-30")
    rates = d[d["dec"] == 0][["loser", "winner"]].mean()
    print(f"{k:14s} D0 {t(m[0])}  D9 {t(m[9])}  spread {t(m[9]-m[0])}  D0 h1/h2 {m[0][h1].mean()*100:+.2f}/{m[0][~h1].mean()*100:+.2f}  D0 lose/win {rates['loser']:.3f}/{rates['winner']:.3f}")
