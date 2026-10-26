# What the scores load on (shortable pool, validation) vs what pays there.
import numpy as np, pandas as pd
from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
CUT = pd.Timestamp("2020-12-31")
chars = data.characteristics()
u = pd.read_csv(f"{__import__('sys').argv[1]}", index_col=0)  # oracle: payoff in shortable pool 2015-2020
p = data.panel(cut=CUT); p = p.join(data.tradable(p))
p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()]
f = rj.scores("valid")[["permno","eom","tail_MaInf","mean_MaInf","up_MaInf","down_MaInf"]].merge(p[["permno","eom",*chars]], on=["permno","eom"])
# Correlation of each char with the score on the SHORT side only: mean z of the char in score D0 vs pool.
f["dec"] = f.groupby("eom")["tail_MaInf"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
f["decm"] = f.groupby("eom")["mean_MaInf"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
R = f.groupby("eom")[chars].rank(pct=True)
rows = {}
for c in chars:
    if c not in u.index: continue
    rows[c] = {"d0_tail_rank": R.loc[f.dec == 0, c].mean(), "d0_mean_rank": R.loc[f.decm == 0, c].mean(),
               "pay_t": u.loc[c, "t"], "t_h1": u.loc[c, "t_h1"], "t_h2": u.loc[c, "t_h2"]}
x = pd.DataFrame(rows).T
# Implied short-side payoff: if D0 sits at rank r on char c, and the char pays t (hi-lo>0 means high is good),
# the D0 tilt "agrees" with the char's payoff when (r-0.5)*t < 0  (D0 low on a char that pays high).
x["tail_tilt"] = x.d0_tail_rank - 0.5; x["mean_tilt"] = x.d0_mean_rank - 0.5
x["tail_agree"] = -np.sign(x.tail_tilt) * x.pay_t; x["mean_agree"] = -np.sign(x.mean_tilt) * x.pay_t
pd.set_option("display.width", 220)
print("Top 25 characteristics by |tilt| of the tail score's D0 (rank 0.5 = pool average):")
print(x.reindex(x.tail_tilt.abs().sort_values(ascending=False).index)[["d0_tail_rank","pay_t","t_h1","t_h2","tail_agree","d0_mean_rank"]].head(25).round(3).to_string())
print("Top 25 by |tilt| of the mean model's D0:")
print(x.reindex(x.mean_tilt.abs().sort_values(ascending=False).index)[["d0_mean_rank","pay_t","t_h1","t_h2","mean_agree","d0_tail_rank"]].head(25).round(3).to_string())
w = lambda tilt, ag: float((tilt.abs() * ag).sum() / tilt.abs().sum())
print("tilt-weighted agreement with large-cap payoff t: tail", w(x.tail_tilt, x.tail_agree), "mean", w(x.mean_tilt, x.mean_agree))
