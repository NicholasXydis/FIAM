# How much of each score's bottom is a volatility sort (follow-up to asymmetry.py).
# Shortable pool, validation decides, 2021-26 diagnostic. Per score: ivol by
# decile, monthly rank corr(score, ivol), and the short-leg profit of D0 when
# the score is ranked within ivol terciles (vol held fixed) vs across the pool.
# Usage: python -m fiam.v4b.research.short_side.vol_loading
import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.research.short_side import tournament

f = tournament.scores()
for win in ("valid", "oos"):
    g = tournament.judged(f, win)
    cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
    g = g.merge(data.panel(cut=cut)[["permno", "eom", "ivol_capm_252d"]], on=["permno", "eom"], how="left")
    g["iv"] = g["ivol_capm_252d"].fillna(g.groupby("eom")["ivol_capm_252d"].transform("median"))
    g["ivt"] = g.groupby("eom")["iv"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
    print(f"== {win}{'' if win == 'valid' else ' (diagnostic only)'}")
    for k in ("mean", "tail", "resrank"):
        dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        iv = g["iv"].groupby(dec).mean() * np.sqrt(252) * 100
        rc = g.groupby("eom").apply(lambda d: d[k].corr(d["iv"], method="spearman"), include_groups=False).mean()
        within = g.groupby(["eom", "ivt"])[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        line = []
        for t in range(3):
            m = (g["ivt"] == t)
            s0 = -g["res"][m & (within == 0)].groupby(g["eom"]).mean()
            s9 = g["res"][m & (within == 9)].groupby(g["eom"]).mean()
            line.append(f"ivol T{t}: short {s0.mean()*100:+.2f}({s0.mean()/s0.std()*np.sqrt(len(s0)):+.1f}) long {s9.mean()*100:+.2f}({s9.mean()/s9.std()*np.sqrt(len(s9)):+.1f})")
        print(f" {k:8s} corr(score, ivol) {rc:+.2f} | ann ivol D0 {iv[0]:.0f}% D5 {iv[5]:.0f}% D9 {iv[9]:.0f}%")
        print("          " + " | ".join(line))
