# Structural fix for the short leg (lessons 85-86), rule fixed before any run
# (2026-10-26):
#   cands  base     - resrank deciles across the shortable pool (D13 winner)
#          volneut  - resrank deciles taken within each ivol tercile, pooled
#                     (both legs vol-matched; removes the score's vol loading)
#          exhivol  - longs as base; shorts = bottom decile of resrank among
#                     names outside the month's top ivol tercile (up-jumps are
#                     unpredictable in direction, so high-vol names are not
#                     shorted; longs keep them, where the upside is predicted)
#   gate   validation short profit t >= 1 and long profit t >= 1
#   choose highest validation spread t; 2021-26 printed as diagnostic only
#   trials +2 in the registry
# ivol = ivol_capm_252d at the formation eom. + = profit for that leg.
# Usage: python -m fiam.v4b.research.short_side.vol_fix
import json

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.gpu.rolling import BASE
from fiam.v4b.research.short_side import tournament

OUT = BASE / "vol_fix.json"
dec10 = lambda s: pd.qcut(s.rank(method="first"), 10, labels=False)


def legs(g: pd.DataFrame, k: str = "resrank") -> dict:
    base = g.groupby("eom")[k].transform(dec10)
    neut = g.groupby(["eom", "ivt"])[k].transform(dec10)
    lo = g["ivt"] < 2
    exs = pd.Series(np.nan, index=g.index)
    exs[lo] = g[lo].groupby("eom")[k].transform(dec10)
    sel = {"base": (base == 0, base == 9), "volneut": (neut == 0, neut == 9), "exhivol": (exs == 0, base == 9)}
    t = lambda s: [float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s)))]
    rep = {}
    for name, (s, l) in sel.items():
        sp = -g["res"][s].groupby(g["eom"][s]).mean()
        lp = g["res"][l].groupby(g["eom"][l]).mean()
        worst = float(sp.min())
        rep[name] = {"short": t(sp), "long": t(lp), "spread": t(sp + lp), "short_worst_month": worst,
                     "short_ivol": float(g["iv"][s].mean() * np.sqrt(252)),
                     "long_ivol": float(g["iv"][l].mean() * np.sqrt(252))}
    return rep


def main() -> dict:
    f = tournament.scores()
    rep = {}
    for win in ("valid", "oos"):
        g = tournament.judged(f, win)
        cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
        g = g.merge(data.panel(cut=cut)[["permno", "eom", "ivol_capm_252d"]], on=["permno", "eom"], how="left")
        g["iv"] = g["ivol_capm_252d"].fillna(g.groupby("eom")["ivol_capm_252d"].transform("median"))
        g["ivt"] = g.groupby("eom")["iv"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
        rep[win] = legs(g)
    v = rep["valid"]
    gated = [k for k in v if v[k]["short"][1] >= 1 and v[k]["long"][1] >= 1]
    rep["gated"], rep["winner"] = gated, max(gated, key=lambda k: v[k]["spread"][1]) if gated else None
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = main()
    p = lambda x: f"{x[0]*100:+.2f} (t {x[1]:+.1f})"
    for win in ("valid", "oos"):
        print(f"== {win}{'' if win == 'valid' else ' (diagnostic only)'}: %/month, + = profit for that leg")
        for k, x in r[win].items():
            print(f" {k:8s} short {p(x['short'])} long {p(x['long'])} spread {p(x['spread'])} | worst short month "
                  f"{x['short_worst_month']*100:+.1f}% | ivol short {x['short_ivol']*100:.0f}% long {x['long_ivol']*100:.0f}%")
    print("gated:", r["gated"], "winner:", r["winner"])
