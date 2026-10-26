# Which training label gets the most information out of each month?
# Proxy of E-LASSO's univariate step (me-weighted FM slopes, expanding mean,
# equal-weight combination) on the competition pack only, labels <= 2020-12.
# Judged on: split-half reliability of the forecast ranking, and shortable-pool
# beta+sector residual decile returns over the validation formations.
import numpy as np
import pandas as pd
from scipy.stats import norm

from fiam.v4b.forecast import data

inp = pd.read_parquet("fiam/v4b/out/elasso/rolling/ret/input/data.parquet")
inp["date"] = pd.to_datetime(inp["date"])
inp = inp[inp.date <= "2020-12-31"].reset_index(drop=True)
chars = [c for c in inp.columns if c not in ("date", "permno", "exchcd", "me", "ret")]
Z = inp[chars].fillna(0).to_numpy()
w0 = inp["me"].to_numpy()
dt = inp["date"]
inp["eom"] = (dt - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")

# Ex-ante beta/ivol/sector at the formation eom (d-1) for residual labels and judging.
pan = pd.read_parquet(data.PANEL, columns=["permno", "eom", "beta_60m", "ivol_capm_252d", "gics", "me_company"])
pan["eom"] = pd.to_datetime(pan["eom"]).astype("datetime64[ns]")
pan = pan.rename(columns={"beta_60m": "rbeta", "ivol_capm_252d": "rivol"})
inp = inp.merge(pan, on=["permno", "eom"], how="left")
y = inp["ret"]
mkt = inp.groupby("date").apply(lambda d: np.average(d["ret"], weights=d["me"]), include_groups=False)
beta = inp["rbeta"].fillna(inp.groupby("date")["rbeta"].transform("median")).fillna(1.0)
res = y - beta * dt.map(mkt)
sig = (inp["rivol"].fillna(inp.groupby("date")["rivol"].transform("median")) * np.sqrt(21)).clip(lower=0.01)
u = y.groupby(dt).rank(pct=True)
ur = res.groupby(dt).rank(pct=True)
lo1, hi1 = y.groupby(dt).transform(lambda s: s.quantile(.01)), y.groupby(dt).transform(lambda s: s.quantile(.99))


def tail(q, k):
    return (q > 1 - k).astype(float) - (q <= k).astype(float)


def nscore(q):
    n = q.groupby(dt).transform("size")
    return pd.Series(norm.ppf((q * n - 0.5) / n), index=q.index)


labels = {
    "ret": y, "ret_w1": y.clip(lo1, hi1), "rank": u - 0.5, "nscore": nscore(u),
    "tail10": tail(u, .1), "tail20": tail(u, .2), "tail30": tail(u, .3),
    "res_rank": ur - 0.5, "res_nscore": nscore(ur), "res_tail20": tail(ur, .2),
    "z_rank": (res / sig).groupby(dt).rank(pct=True) - 0.5,
}

dates = np.sort(dt.unique())
idx = {d: np.flatnonzero(dt.to_numpy() == d) for d in dates}


def slopes(yv):
    B = []
    for d in dates:
        i = idx[d]
        w = w0[i] / w0[i].mean()
        z, yy = Z[i], yv[i]
        zm = (w[:, None] * z).sum(0) / w.sum()
        ym = (w * yy).sum() / w.sum()
        zc = z - zm
        B.append((w[:, None] * zc * (yy - ym)[:, None]).sum(0) / np.maximum((w[:, None] * zc**2).sum(0), 1e-12))
    return np.array(B)


# Judge frame: shortable pool, validation formations (rows dated 2017-01..2020-12).
cap = inp[["me", "me_company"]].min(axis=1)
J = inp[(cap >= 500) & inp.date.between("2017-01-31", "2020-12-31")].copy()
J["sector"] = J["gics"].astype(str).str[:2]


def resid(d):
    b = d["rbeta"].fillna(d["rbeta"].median()).to_numpy()
    X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
    c, *_ = np.linalg.lstsq(X, d["ret"].to_numpy(), rcond=None)
    return pd.Series(d["ret"].to_numpy() - X @ c, index=d.index)


J["jres"] = J.groupby("date", group_keys=False).apply(resid, include_groups=False)
J["loser"] = J.groupby("date")["jres"].transform(lambda s: s <= s.quantile(.1))
J["winner"] = J.groupby("date")["jres"].transform(lambda s: s >= s.quantile(.9))
jpos = {d: np.flatnonzero((J.date == d).to_numpy()) for d in J.date.unique()}
jrow = {d: J.index[(J.date == d).to_numpy()].to_numpy() for d in J.date.unique()}
T = lambda s: f"{s.mean()*100:+.2f} ({s.mean()/s.std()*np.sqrt(len(s)):+.1f})"
print(f"{'label':11s} {'rel@23':>6s} {'rel@46':>6s} {'rel@70':>6s} | {'D0 %/mo (t)':>13s} {'D0 2nd half':>11s} {'D0-2':>12s} {'D9':>12s} {'spread':>12s} {'lose/win D0':>11s}")
for name, lab in labels.items():
    B = slopes(lab.to_numpy())
    fc = np.full(len(inp), np.nan)
    rel = {}
    for k, d in enumerate(dates):
        if k < 3:
            continue
        h = B[:k]
        fc[idx[d]] = Z[idx[d]] @ h.mean(0)
        if d in jrow and k in (23, 46, 70):
            i = jrow[d]
            a, b = Z[i] @ h[0::2].mean(0), Z[i] @ h[1::2].mean(0)
            r = pd.Series(a).corr(pd.Series(b), method="spearman")
            rel[k] = 2 * r / (1 + r)
    J["s"] = fc[J.index.to_numpy()]
    J["dec"] = J.groupby("date")["s"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = J.groupby(["date", "dec"])["jres"].mean().unstack()
    h2 = m.index > pd.Timestamp("2018-12-31")
    lw = J.loc[J.dec == 0, ["loser", "winner"]].mean()
    print(f"{name:11s} {rel.get(23, np.nan):6.2f} {rel.get(46, np.nan):6.2f} {rel.get(70, np.nan):6.2f} | {T(m[0]):>13s} {m[0][h2].mean()*100:+11.2f} {T(m[[0,1,2]].mean(1)):>12s} {T(m[9]):>12s} {T(m[9]-m[0]):>12s} {lw['loser']:.3f}/{lw['winner']:.3f}")
