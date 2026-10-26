# Where in the shortable pool the short edge sits, by the borrow schedule's
# cap tiers ($500m-$10bn pays 5%/yr flat, >= $10bn 0.5%/yr; config policy).
# Short-leg profit of each score's bottom decile, ranked within the whole
# shortable pool, split by tier; beta + sector residuals; validation decides,
# 2021-26 is a labelled diagnostic. + = shorted names fell.
# Usage: python -m fiam.v4b.research.short_side.cap_buckets

import json

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.gpu.rolling import BASE
from fiam.v4b.research.short_side import tournament

OUT = BASE / "cap_buckets.json"
TIERS = {"500m-2bn": (500, 2_000), "2bn-10bn": (2_000, 10_000), ">=10bn": (10_000, np.inf)}


def main() -> dict:
    f = tournament.scores()
    rep = {}
    for win in ("valid", "oos"):
        g = tournament.judged(f, win)
        cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
        p = data.panel(cut=cut)[["permno", "eom", "me"]]
        g = g.merge(p, on=["permno", "eom"], how="left")
        t = lambda s: [float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s))), int(len(s))]
        rep[win] = {}
        for k in ("mean", "tail", "resrank"):
            dec = g.groupby("eom")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
            r = {}
            for name, (lo, hi) in TIERS.items():
                m = g["me"].between(lo, hi, inclusive="left")
                d0 = g[m & (dec == 0)]
                r[name] = {"short_profit": t(-d0.groupby("eom")["res"].mean()),
                           "share_of_d0": float(len(d0) / (dec == 0).sum()),
                           "share_of_pool": float(m.mean())}
            rep[win][k] = r
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = main()
    for win, v in r.items():
        print(f"== {win}{'' if win == 'valid' else ' (diagnostic only)'}: D0 short profit %/month (t), share of D0 / of pool")
        for k, tiers in v.items():
            print(f" {k:8s} " + " | ".join(
                f"{n}: {x['short_profit'][0]*100:+.2f} ({x['short_profit'][1]:+.1f}) {x['share_of_d0']:.2f}/{x['share_of_pool']:.2f}"
                for n, x in tiers.items()))
