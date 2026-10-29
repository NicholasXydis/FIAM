# Options informed trading (Cremers-Weinbaum; Xing-Zhang-Zhao, 2010).

import pandas as pd

from fiam.vfinal import data, ranks
from fiam.vfinal.signals import base

# The composite is already signed: a higher value means a better stock.
SIGN = 1
# Values are averaged over the last 5 sessions public by T.
SESSIONS = 5
# A wide window to find those sessions, in calendar days.
LOOKBACK = pd.Timedelta(days=14)


# The mean rank of the call-put IV spread and of minus the OTM put skew.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    out = []
    for eom, T in base.formations(eoms).itertuples(index=False):
        rows = data.table("options_daily", ["iv_CATM", "iv_PATM", "Skew_OTM"],
                          where={"date": (T - LOOKBACK, T)})  # fmt: skip
        rows = rows[rows["first_close"] <= T]
        data.assert_public_by(rows["first_close"], T, "options rows")
        days = sorted(rows["date"].unique())[-SESSIONS:]
        rows = rows[rows["date"].isin(days)]
        rows = rows.assign(spread=rows["iv_CATM"] - rows["iv_PATM"])
        both = rows.groupby("permno")[["spread", "Skew_OTM"]].mean().dropna()
        value = (ranks.unit_rank(both["spread"]) - ranks.unit_rank(both["Skew_OTM"])) / 2
        out.append(pd.DataFrame({"permno": value.index, "eom": eom, "value": value.to_numpy()}))
        log[str(eom.date())] = int(len(both))
    return pd.concat(out, ignore_index=True)
