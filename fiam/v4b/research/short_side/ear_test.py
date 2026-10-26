# Earnings-announcement-return drift as a shortable-pool signal, competition pack only.
# EAR = 3-session market-adjusted return around 8-K item 2.02; signal at eom t =
# latest EAR completed by eom t within 92 days. Pre-2021 formations only.
import sys

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data

CUT = pd.Timestamp("2020-12-31")
k = pd.read_parquet(data.ORG / "8k_20150101_20260831_identified.parquet",
                    columns=["permno", "items", "filing_date", "filing_timestamp_utc"])
k = k[k["permno"].notna() & k["items"].astype(str).str.contains("2.02", regex=False)].copy()
k["permno"] = k["permno"].astype("int64")
ts = pd.to_datetime(k["filing_timestamp_utc"], utc=True).dt.tz_convert("America/New_York")
k["day"] = pd.to_datetime(k["filing_date"])
after = ts.notna() & (ts.dt.hour >= 16)
sess = data.sessions("2014-01-01", "2021-03-31")
pos = np.searchsorted(sess.values, k["day"].values)  # first session >= filing date
pos = pos + after.to_numpy().astype(int)
k = k[pos < len(sess) - 2].copy()
k["d0"] = pos[pos < len(sess) - 2]
k = k[sess[k["d0"]] <= CUT]
print("2.02 filings", len(k), "names", k.permno.nunique())

d = data.daily(CUT)
d = d[d["date"] >= "2014-06-01"]
w = d.pivot_table(index="date", columns="permno", values="daily_return").reindex(sess[sess <= CUT])
ab = w.sub(w.mean(axis=1), axis=0)
A = ab.to_numpy()
col = {p: i for i, p in enumerate(ab.columns)}
ear = []
for p, d0 in zip(k["permno"], k["d0"]):
    j = col.get(p)
    if j is None or d0 + 1 >= len(A) or d0 < 1:
        ear.append(np.nan)
        continue
    x = A[d0 - 1:d0 + 2, j]
    ear.append(np.nansum(x) if np.isfinite(x).sum() >= 2 else np.nan)
k["ear"] = ear
k["known"] = sess[np.minimum(k["d0"] + 1, len(sess) - 1)]
k = k.dropna(subset=["ear"]).sort_values("known")

p = data.panel(cut=CUT)
p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()][["permno", "eom", "gics", "beta_60m", "ret_exc_lead1m", "me"]].copy()
p = p.sort_values("eom")
s = pd.merge_asof(p, k[["permno", "known", "ear"]].rename(columns={"known": "eom"}), on="eom", by="permno",
                  tolerance=pd.Timedelta(days=92), direction="backward")
s["sector"] = s["gics"].astype(str).str[:2]
s["y"] = s["ret_exc_lead1m"].astype(float)


def resid(x):
    b = x["beta_60m"].fillna(x["beta_60m"].median()).to_numpy()
    X = np.column_stack([b, pd.get_dummies(x["sector"]).to_numpy(float)])
    c, *_ = np.linalg.lstsq(X, x["y"].to_numpy(), rcond=None)
    return pd.Series(x["y"].to_numpy() - X @ c, index=x.index)


s["res"] = s.groupby("eom", group_keys=False).apply(resid, include_groups=False)
print("coverage of EAR in shortable pool:", round(s["ear"].notna().mean(), 3))
e = s.dropna(subset=["ear"]).copy()
e["q"] = e.groupby("eom")["ear"].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
m = e.groupby(["eom", "q"])["res"].mean().unstack()
T = lambda x: f"{x.mean()*100:+.2f}% (t {x.mean()/x.std()*np.sqrt(len(x)):+.2f})"
h1 = m.index <= pd.Timestamp("2017-12-31")
for q in range(5):
    print(f" EAR quintile {q}: {T(m[q])}  h1 {m[q][h1].mean()*100:+.2f}  h2 {m[q][~h1].mean()*100:+.2f}")
print(" Q4-Q0:", T(m[4] - m[0]), " h1", T((m[4] - m[0])[h1]), " h2", T((m[4] - m[0])[~h1]))
print(" EAR Q0 median res", e.loc[e.q == 0, "res"].median())
# Incremental to the E-LASSO scores in validation.
f = rj.scores("valid")[["permno", "eom", "tail_MaInf", "mean_MaInf"]]
v = e.merge(f, on=["permno", "eom"])
print(" corr(EAR, tail)", v.groupby("eom").apply(lambda x: x.ear.corr(x.tail_MaInf, method="spearman"), include_groups=False).mean(),
      " corr(EAR, mean)", v.groupby("eom").apply(lambda x: x.ear.corr(x.mean_MaInf, method="spearman"), include_groups=False).mean())
v["tq"] = v.groupby("eom")["tail_MaInf"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
v["eq"] = v.groupby("eom")["ear"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
mm = v.groupby(["eom", "tq", "eq"])["res"].mean().unstack([1, 2])
print(" validation double sort (tail tercile x EAR tercile), mean res %/mo:")
print((mm.mean().unstack() * 100).round(2).to_string())
print(" short cell (tail low, EAR low):", T(mm[(0, 0)].dropna()), " vs (tail low, EAR high):", T(mm[(0, 2)].dropna()))
