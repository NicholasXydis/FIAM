# D13 label tournament on the corrected E-LASSO port. Rule fixed before any
# result was computed (2026-10-26):
#   window   validation formations 2016-12..2020-11 decide; 2021-26 printed as
#            a labelled diagnostic only (already opened for ret/tail, D11)
#   pool     shortable (cap >= $500m), returns = beta + GICS-sector residuals
#   gate     short-leg profit (-D0) t >= 1.0 and long D9 t >= 1.0
#   choose   highest t-stat of the D9 - D0 spread among gated candidates
#   cands    mean (ret), tail (up - down), blend (50/50 rank of mean, tail),
#            resrank, tail20 (up20 - down20), restail (resup - resdown)
#   trials   +4 in the registry (resrank, tail20, restail, blend); mean and
#            tail are re-runs of D11 candidates with the D13 code fix
# Profit is printed for each leg: + is good for that leg.
# Usage: python -m fiam.v4b.research.short_side.tournament

import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
from fiam.v4b.gpu.rolling import BASE

OUT = BASE / "tournament.json"


def scores() -> pd.DataFrame:
    load = lambda k: rj._load(k, run=BASE / k / "run")[["eom", "permno", "MaInf"]].rename(columns={"MaInf": k})
    f = load("ret")
    for k in ("up", "down", "resrank", "up20", "down20", "resup", "resdown"):
        f = f.merge(load(k), on=["eom", "permno"])
    f = f.rename(columns={"ret": "mean"})
    f["tail"] = f["up"] - f["down"]
    f["tail20"] = f["up20"] - f["down20"]
    f["restail"] = f["resup"] - f["resdown"]
    g = f.groupby("eom")
    f["blend"] = g["mean"].rank(pct=True) + g["tail"].rank(pct=True)
    return f


def judged(f: pd.DataFrame, win: str) -> pd.DataFrame:
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
    return g


CANDS = ["mean", "tail", "blend", "resrank", "tail20", "restail"]


def table(g: pd.DataFrame) -> dict:
    t = lambda s: (float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s))))
    res = {}
    for k in CANDS:
        dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        m = g["res"].groupby([g["eom"], dec]).mean().unstack()
        ic = g.groupby("eom").apply(lambda d: d[k].corr(d["res"], method="spearman"), include_groups=False)
        res[k] = {"short_profit": t(-m[0]), "long_profit": t(m[9]), "spread": t(m[9] - m[0]), "ic": t(ic),
                  "short_by_year": {int(y): float(v) for y, v in (-m[0]).groupby(m.index.year).mean().items()}}
    return res


def main() -> dict:
    f = scores()
    rep = {"rule": "gate short t>=1 & long t>=1; max spread t; validation only"}
    for win in ("valid", "oos"):
        rep[win] = table(judged(f, win))
    gated = [k for k in CANDS if rep["valid"][k]["short_profit"][1] >= 1 and rep["valid"][k]["long_profit"][1] >= 1]
    rep["gated"] = gated
    rep["winner"] = max(gated, key=lambda k: rep["valid"][k]["spread"][1]) if gated else None
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = main()
    fmt = lambda x: f"{x[0]*100:+.2f} ({x[1]:+.1f})"
    for win in ("valid", "oos"):
        print(f"== {win}{'' if win == 'valid' else ' (diagnostic only)'}: %/month (t), + = profit for that leg")
        for k in CANDS:
            v = r[win][k]
            print(f" {k:8s} short {fmt(v['short_profit'])}  long {fmt(v['long_profit'])}  spread {fmt(v['spread'])}  IC {fmt(v['ic'])}")
    print("gated:", r["gated"], "winner:", r["winner"])
