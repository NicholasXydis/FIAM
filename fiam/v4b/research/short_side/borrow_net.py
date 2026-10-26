# D0 short profit net of a month's borrow under three schedules (diagnostic):
# flat 0.5%/5% (config), short-interest tiers (fiam/costs.py; WRDS short interest,
# outside the competition pack), flat GC 0.3%. + = profit; beta + sector residuals.
# Usage: python -m fiam.v4b.research.short_side.borrow_net
import numpy as np, pandas as pd
from fiam import costs
from fiam.v4b.forecast import data
from fiam.v4b.research.short_side import tournament
f = tournament.scores()
sr = costs.short_ratio().rename("si").reset_index()
sr["eom"] = pd.to_datetime(sr["eom"]).astype("datetime64[ns]")
for win in ("valid", "oos"):
    g = tournament.judged(f, win)
    cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
    g = g.merge(data.panel(cut=cut)[["permno", "eom", "me"]], on=["permno", "eom"], how="left")
    g = g.merge(sr, on=["permno", "eom"], how="left")
    sched = {
        "flat 0.5/5%": np.where(g["me"] >= 10_000, 0.005, 0.05),
        "SI tiers": costs.tier(g["si"]).to_numpy(),
        "GC 0.3%": np.full(len(g), 0.003),
    }
    print(f"== {win}; SI coverage {g['si'].notna().mean():.2f}")
    for k in ("mean", "tail", "resrank"):
        dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        d0 = dec == 0
        line = []
        for n, b in sched.items():
            s = (-g["res"] - b / 12)[d0].groupby(g["eom"][d0]).mean()
            line.append(f"{n}: {s.mean()*100:+.2f} (t {s.mean()/s.std()*np.sqrt(len(s)):+.1f}) avg borrow {b[d0].mean()*100:.2f}%")
        print(f" {k:8s} " + " | ".join(line))
