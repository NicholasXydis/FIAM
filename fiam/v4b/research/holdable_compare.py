# Holdable-universe training vs the current model, judged where the book can
# trade (user, 2026-10-26: "change training with only possible universe or
# holdable stocks?"). Rule fixed before any result (2026-10-26):
#   pool     walkforward.holdable names at each eom (ADV >= $9m, cap >= $500m)
#   returns  next-month excess return less a beta_60m + GICS-sector fit
#            within that pool (tournament.judged)
#   scores   raw MaInf and its beta-matched rank (variants.betamatch) for the
#            current walk-forward (all long_ok) and the holdable walk-forward;
#            every score re-ranked within the pool
#   adopt    holdable training if, on 2017-2020, its D9-D0 spread t is higher
#            AND its short leg (-D0) is higher than the current model's, for
#            the raw score; 2021-2026 printed as a disclosed diagnostic only
# Usage: python -m fiam.v4b.research.holdable_compare

import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso.walkforward import ROOT, holdable
from fiam.v4b.forecast import data
from fiam.v4b.research import oos_causes as oc

OUT = ROOT / "holdable_compare.json"
RUNS = {"current": ROOT / "month" / "forecastElasso_raw.parquet",
        "holdable": ROOT / "month_holdable" / "forecastElasso_raw.parquet"}


def pool() -> pd.DataFrame:
    p = data.panel(cut=pd.Timestamp("2026-08-31"))
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & p["ret_exc_lead1m"].notna() & (p["me"] > 0)]
    p = p[holdable(p)][["permno", "eom", "gics", "beta_60m", "ret_exc_lead1m"]].copy()
    p["sector"] = p["gics"].astype(str).str[:2]

    def resid(d):
        b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
        X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
        y = d["ret_exc_lead1m"].to_numpy(float)
        c, *_ = np.linalg.lstsq(X, y, rcond=None)
        return pd.Series(y - X @ c, index=d.index)

    p["res"] = p.groupby("eom", group_keys=False).apply(resid, include_groups=False)
    return p


def scores(p: pd.DataFrame) -> pd.DataFrame:
    out = p
    for name, path in RUNS.items():
        f = pd.read_parquet(path, columns=["date", "permno", "MaInf"])
        f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
        out = out.merge(f[["eom", "permno", "MaInf"]].rename(columns={"MaInf": name}), on=["eom", "permno"], how="inner")
    bq = out.groupby("eom")["beta_60m"].transform(
        lambda s: pd.qcut(s.fillna(s.median()).rank(method="first"), 5, labels=False))
    for name in RUNS:
        out[f"{name}_bm"] = out.groupby([out["eom"], bq])[name].rank(pct=True)
    return out


def judge(g: pd.DataFrame, k: str) -> dict:
    dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    m = g["res"].groupby([g["eom"], dec]).mean().unstack()
    ic = g.groupby("eom").apply(lambda d: d[k].corr(d["res"], method="spearman"), include_groups=False)
    return {"ic": oc.tstat(ic / 100), "long": oc.tstat(m[9]), "short": oc.tstat(-m[0]), "spread": oc.tstat(m[9] - m[0])}


def main() -> dict:
    g0 = scores(pool())
    rep = {}
    for win, (lo, hi) in oc.WIN.items():
        g = g0[g0["eom"].between(pd.Timestamp(lo), pd.Timestamp(hi))]
        rep[win] = {k: judge(g, k) for k in ("current", "holdable", "current_bm", "holdable_bm")}
        rep[win]["names_per_month"] = float(g.groupby("eom").size().mean())
    v = rep["valid"]
    rep["adopt_holdable"] = bool(v["holdable"]["spread"][1] > v["current"]["spread"][1]
                                 and v["holdable"]["short"][0] > v["current"]["short"][0])
    OUT.write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    r = main()
    for win in ("valid", "oos"):
        print(f"===== {win}{'' if win == 'valid' else ' (disclosed diagnostic)'}  holdable pool, %/month (t)  "
              f"names/month {r[win]['names_per_month']:.0f}")
        for k in ("current", "holdable", "current_bm", "holdable_bm"):
            x = r[win][k]
            print(f"  {k:12s} IC {x['ic'][0]:+.3f} (t {x['ic'][1]:+.1f}) long {x['long'][0]:+.2f} ({x['long'][1]:+.1f}) "
                  f"short {x['short'][0]:+.2f} ({x['short'][1]:+.1f}) spread {x['spread'][0]:+.2f} ({x['spread'][1]:+.1f})")
    print("adopt holdable training (validation rule):", r["adopt_holdable"])
