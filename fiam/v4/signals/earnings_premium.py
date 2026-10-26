# The earnings-announcement premium (Frazzini-Lamont 2007; BDLT 2013).

import pandas as pd

from fiam.v4 import data
from fiam.v4.signals import base

# A scheduled announcement in the holding month earns a premium.
SIGN = 1


# 1 if the next projected announcement known by T falls by the next T.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    f = base.formations(eoms)
    cal = data.table("earnings_calendar", ["projected"])
    nxt = data.eom_session(f["eom"] + pd.offsets.MonthEnd(1)).to_numpy()
    out = []
    for (eom, T), end in zip(f.itertuples(index=False), nxt):
        seen = cal[(cal["first_close"] <= T) & (cal["projected"] > T)]
        data.assert_public_by(seen["first_close"], T, "earnings projections")
        first = seen.groupby("permno")["projected"].min()
        value = (first <= pd.Timestamp(end)).astype(float)
        out.append(pd.DataFrame({"permno": value.index, "eom": eom, "value": value.to_numpy()}))
        log[str(eom.date())] = int(value.sum())
    return pd.concat(out, ignore_index=True)
