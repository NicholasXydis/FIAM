# Stage 2, E-LASSO kept (user, 2026-10-26, choosing "Keep E-LASSO, tune
# construction" over v4's signals). IN-SAMPLE on 2021-2026 like stage2.py: the
# result is reported beside the clean D17 number, never in its place.
#
# stage2.py showed E-LASSO's legs carry after-beta alpha on 2021-2026 but lose
# it to ~8%/yr of costs and a realised beta of about -0.25. This screen tunes the
# construction levers that address those two, plus pool and score shape:
#   pool       holdable | v4 (stage2.panel)
#   transform  raw | volneut (rank within ivol terciles) | betamatch (within
#              beta_60m quintiles), then sector-demeaned and beta-residualised
#   smooth     mean of the last 1 / 3 / 6 months' z for the name (past only):
#              slower score, less turnover
#   n          names per side, 150 | 250
#   hedge      none | rolling: each month the book's beta on the cap-weighted
#              pool return over the previous 12 months (>= 6), taken out with
#              the market (past only; the case allows net +-50%)
# Pick = highest Sharpe after costs; every number is also shown at 12% vol.
# Usage: python -m fiam.v4b.research.stage2_el

import itertools
import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso.walkforward import ROOT
from fiam.v4b.research import stage2 as S2

OUT = ROOT / "stage2_el.json"
GRID = dict(pool=("holdable", "v4"), transform=("raw", "volneut", "betamatch"), smooth=(1, 3, 6), n=(150, 250),
            hedge=("none", "rolling"))


def score(p: pd.DataFrame, transform: str, smooth: int) -> pd.Series:
    if transform == "raw":
        s = p["MaInf"]
    else:
        key = p["iv"] if transform == "volneut" else p["beta"]
        k = 3 if transform == "volneut" else 5
        b = key.groupby(p["eom"]).transform(lambda x: pd.qcut(x.rank(method="first"), k, labels=False))
        s = p.groupby([p["eom"], b])["MaInf"].rank(pct=True)
    z = S2.rank_z(p, S2.neutral(p, s))
    if smooth > 1:
        z = z.groupby(p["permno"]).transform(lambda x: x.rolling(smooth, min_periods=1).mean())
    return S2.rank_z(p, z)


def hedged(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    gross = m["long"] + m["short"]
    beta = pd.Series(np.nan, index=m.index)
    for i in range(6, len(m)):
        lo = max(0, i - 12)
        beta.iloc[i] = np.polyfit(m["mkt"].iloc[lo:i], gross.iloc[lo:i], 1)[0]
    h = -beta.fillna(0.0)
    m["long"] = m["long"] + h.clip(lower=0) * m["mkt"]  # a long hedge adds to the long leg, a short one to the short
    m["short"] = m["short"] + h.clip(upper=0) * m["mkt"]
    m["net"] = m["long"] + m["short"] - m["cost"]
    return m


def main() -> dict:
    rows = []
    for pool in GRID["pool"]:
        p = S2.panel(pool)
        p = p.sort_values(["permno", "eom"]).reset_index(drop=True)
        for transform, smooth in itertools.product(GRID["transform"], GRID["smooth"]):
            s = score(p, transform, smooth)
            for n in GRID["n"]:
                m = S2.simulate(p, S2.book(p, s, n))
                for hedge in GRID["hedge"]:
                    cfg = dict(pool=pool, transform=transform, smooth=smooth, n=n, hedge=hedge)
                    rows.append(cfg | S2.stats(hedged(m) if hedge == "rolling" else m))
    best = max(rows, key=lambda r: r["sharpe"])
    rep = {"grid_size": len(rows), "pick": best, "rows": rows}
    OUT.write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


if __name__ == "__main__":
    r = main()
    for x in sorted(r["rows"], key=lambda x: -x["sharpe"])[:15]:
        print(f"{x['pool']:8s} {x['transform']:9s} sm{x['smooth']} n{x['n']} {x['hedge']:7s} net {x['net']*100:+5.1f}%/yr "
              f"vol {x['vol']*100:4.1f} SR {x['sharpe']:+.2f} beta {x['beta']:+.2f} long a {x['long_alpha']*100:+.1f} "
              f"(t {x['long_t']:+.1f}) short a {x['short_alpha']*100:+.1f} (t {x['short_t']:+.1f}) "
              f"turn {x['turnover_yr']:.1f}x cost {x['cost_yr']*100:.1f}% @12%vol {x['net_at_12vol']*100:+.1f}%")
    print("grid", r["grid_size"])
