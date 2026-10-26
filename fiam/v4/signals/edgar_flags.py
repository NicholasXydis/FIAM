# Red-flag 8-Ks: bankruptcy, impairment, delisting, auditor, restated.

import pandas as pd

from fiam.v4 import data
from fiam.v4.signals import base

# A red flag is bad news: the gate takes the negative (Lerman-Livnat).
SIGN = -1
# The leader's window, 2026-10-24: a flag counts for 90 calendar days.
WINDOW = pd.Timedelta(days=90)


# 1 with a red-flag 8-K public in the 90 days to T, else 0; no CIK: NaN.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    f = base.formations(eoms)
    ev = data.table("events", ["red_flag"])
    ev = ev[ev["red_flag"].astype(bool)][["permno", "first_close", "accession"]]
    out = []
    for eom, T in f.itertuples(index=False):
        ids = base.universe_at(eom)
        recent = ev[(ev["first_close"] <= T) & (ev["first_close"] > T - WINDOW)]
        data.assert_public_by(recent["first_close"], T, "red flags")
        flagged = set(recent["permno"])
        linked = base.has_cik(ids, T)
        frame = pd.DataFrame({"permno": ids, "eom": eom})
        frame["value"] = [1.0 if p in flagged else 0.0 for p in ids]
        frame.loc[~linked.reindex(ids).to_numpy(), "value"] = float("nan")
        out.append(frame)
    table = pd.concat(out, ignore_index=True)
    log["flagged_stock_months"] = int((table["value"] == 1).sum())
    return table
