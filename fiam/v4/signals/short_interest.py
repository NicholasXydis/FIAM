# Short interest over shares outstanding (Boehmer-Huszar-Jordan 2010).

import pandas as pd

from fiam.v4 import data
from fiam.v4.signals import base

# Heavily shorted stocks do worse: the gate takes the negative.
SIGN = -1
# A settlement older than this at T is stale: carried at most 2 months.
CARRY = pd.DateOffset(months=2)


# The latest public settlement's short interest over CRSP's shares then.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    f = base.formations(eoms)
    s = data.table("short_interest", ["shortint"])
    s = s[s["first_close"] <= f["T"].max()]
    # Shares outstanding on the settlement day, or the session before it.
    days = data.calendar().index
    s["session"] = days[days.searchsorted(s["settlement"], side="right") - 1]
    shares = data.table("crsp_daily", ["shrout_k"], where={"date": set(s["session"])})
    shares = shares.rename(columns={"date": "session", "first_close": "shares_close"})
    shares = shares[["permno", "session", "shrout_k", "shares_close"]]
    s = s.merge(shares, on=["permno", "session"], how="left")
    s["value"] = s["shortint"] / (s["shrout_k"] * 1000.0)
    log["settlements_without_crsp_shares"] = int(s["shrout_k"].isna().sum())
    s = s.dropna(subset=["value"]).sort_values(["first_close", "settlement"], kind="stable")
    out = []
    for eom, T in f.itertuples(index=False):
        seen = s[(s["first_close"] <= T) & (s["settlement"] >= T - CARRY)]
        last = seen.drop_duplicates("permno", keep="last")
        data.assert_public_by(last["first_close"], T, "short interest")
        data.assert_public_by(last["shares_close"], T, "short interest shares")
        out.append(last[["permno", "settlement", "value"]].assign(eom=eom))
    return pd.concat(out, ignore_index=True)
