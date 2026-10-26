# Is the forecast sharp on the upside and noise on the downside, and why?
# Shortable pool, beta + sector residual of next-month excess return
# (tournament.judged); validation decides, 2021-26 printed as a diagnostic.
#   A decile curve of each score (+ = above the pool), with t
#   B rank IC inside the bottom half and inside the top half of each score
#   C realised residual sd and median by decile
#   D each characteristic's two arms: quintile residual means Q5 - Q3 (high
#     arm) and Q3 - Q1 (low arm), oriented by the sign of Q5 - Q1 on
#     validation; a linear model assumes the two arms are equal
# Usage: python -m fiam.v4b.research.short_side.asymmetry

import json

import numpy as np
import pandas as pd

from fiam.v4b.gpu.rolling import BASE
from fiam.v4b.research.short_side import tournament

OUT = BASE / "asymmetry.json"
SCORES = ("mean", "tail", "resrank")


def tt(s: pd.Series) -> list:
    s = s.dropna()
    return [float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s)))]


def chars(eoms: pd.Series) -> pd.DataFrame:
    # Row dated d carries eom d-1 characteristics (D13 input contract).
    x = pd.read_parquet(BASE / "resrank" / "input" / "data.parquet")
    x["eom"] = (pd.to_datetime(x["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    x = x[x["eom"].isin(eoms.unique())]
    return x.drop(columns=["date", "exchcd", "me", "ret"])


def score_tables(g: pd.DataFrame) -> dict:
    rep = {}
    for k in SCORES:
        dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        m = g["res"].groupby([g["eom"], dec]).mean().unstack()
        half = g.groupby("eom")[k].transform(lambda s: s > s.median())

        def ic(d):
            return d[k].corr(d["res"], method="spearman")

        lo = g[~half].groupby("eom").apply(ic, include_groups=False)
        hi = g[half].groupby("eom").apply(ic, include_groups=False)
        rep[k] = {
            "decile": {int(c): tt(m[c]) for c in m.columns},
            "ic_bottom_half": tt(lo),
            "ic_top_half": tt(hi),
            "sd": {int(c): float(v) for c, v in g["res"].groupby(dec).std().items()},
            "median": {int(c): float(v) for c, v in g["res"].groupby(dec).median().items()},
        }
    return rep


def arms(g: pd.DataFrame, x: pd.DataFrame, orient: dict | None) -> dict:
    d = g[["eom", "permno", "res"]].merge(x, on=["eom", "permno"])
    cols = [c for c in x.columns if c not in ("eom", "permno")]
    out = {}
    for c in cols:
        v = d[["eom", "res", c]]
        v = v[(v[c] != 0) & v[c].notna()]  # 0 = missing after FillCsm
        if v["eom"].nunique() < 24:
            continue
        q = np.clip(np.ceil(v.groupby("eom")[c].rank(method="first", pct=True) * 5) - 1, 0, 4).astype(int)
        m = v["res"].groupby([v["eom"], q]).mean().unstack()
        if m.shape[1] < 5:
            continue
        sgn = orient[c] if orient else float(np.sign((m[4] - m[0]).mean()) or 1.0)
        out[c] = {"sign": sgn, "high": tt(sgn * (m[4] - m[2])), "low": tt(sgn * (m[2] - m[0])),
                  "full": tt(sgn * (m[4] - m[0]))}
    return out


def summary(a: dict) -> dict:
    hi = np.array([v["high"][0] for v in a.values()])
    lo = np.array([v["low"][0] for v in a.values()])
    th = np.array([v["high"][1] for v in a.values()])
    tl = np.array([v["low"][1] for v in a.values()])
    strong = np.array([v["full"][1] for v in a.values()]) >= 2
    return {"n": len(a), "n_strong": int(strong.sum()),
            "mean_high_arm": float(hi.mean()), "mean_low_arm": float(lo.mean()),
            "strong_mean_high_arm": float(hi[strong].mean()) if strong.any() else None,
            "strong_mean_low_arm": float(lo[strong].mean()) if strong.any() else None,
            "share_high_gt_low": float((hi > lo).mean()),
            "n_high_t2": int((th >= 2).sum()), "n_low_t2": int((tl >= 2).sum())}


def main() -> dict:
    f = tournament.scores()
    rep, orient = {}, None
    for win in ("valid", "oos"):
        g = tournament.judged(f, win)
        a = arms(g, chars(g["eom"]), orient)
        if orient is None:
            orient = {c: v["sign"] for c, v in a.items()}
        rep[win] = {"scores": score_tables(g), "arms_summary": summary(a), "arms": a}
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = main()
    p = lambda v: f"{v[0]*100:+.2f}({v[1]:+.1f})"
    for win, v in r.items():
        print(f"===== {win}{'' if win == 'valid' else ' (diagnostic only)'}  residual %/month (t)")
        for k, s in v["scores"].items():
            print(f" {k:8s} deciles " + " ".join(p(s['decile'][i]) for i in range(10)))
            print(f"          IC bottom half {s['ic_bottom_half'][0]:+.3f} (t {s['ic_bottom_half'][1]:+.1f})  "
                  f"top half {s['ic_top_half'][0]:+.3f} (t {s['ic_top_half'][1]:+.1f})")
            print("          sd " + " ".join(f"{s['sd'][i]*100:.1f}" for i in range(10))
                  + " | median " + " ".join(f"{s['median'][i]*100:+.2f}" for i in range(10)))
        s = v["arms_summary"]
        print(f" characteristics: {s}")
        top = sorted(v["arms"].items(), key=lambda kv: -kv[1]["full"][1])[:15]
        for c, a in top:
            print(f"   {c:28s} full {p(a['full'])} high arm {p(a['high'])} low arm {p(a['low'])}")
