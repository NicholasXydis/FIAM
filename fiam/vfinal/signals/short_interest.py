# Short interest over shares outstanding (Boehmer-Huszar-Jordan 2010).

import pandas as pd

from fiam.vfinal import data
from fiam.vfinal import inputs as engine_inputs
from fiam.vfinal.signals import base

# Heavily shorted stocks do worse: the gate takes the negative.
SIGN = -1
# A settlement older than this at T is stale: carried at most 2 months.
CARRY = pd.DateOffset(months=2)


# Every settlement public by a day over the shares on its session.
def history(permnos=None, by=None) -> pd.DataFrame:
    where = None if permnos is None else {"permno": set(int(p) for p in permnos)}
    s = data.table("short_interest", ["shortint"], where=where)
    if by is not None:
        s = s[s["first_close"] <= pd.Timestamp(by)]
    # Shares outstanding on the settlement day, or the session before it.
    days = data.calendar().index
    s["session"] = days[days.searchsorted(s["settlement"], side="right") - 1]
    s = s.merge(engine_inputs.shares_on(s["session"]), on=["permno", "session"], how="left")
    s["value"] = s["shortint"] / s["shares"]
    return s


# The latest public settlement's short interest over the shares then.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    f = base.formations(eoms)
    s = history(by=f["T"].max())
    log["settlements_without_crsp_shares"] = int(s["shares"].isna().sum())
    s = s.dropna(subset=["value"]).sort_values(["first_close", "settlement"], kind="stable")
    out = []
    for eom, T in f.itertuples(index=False):
        seen = s[(s["first_close"] <= T) & (s["settlement"] >= T - CARRY)]
        last = seen.drop_duplicates("permno", keep="last")
        data.assert_public_by(last["first_close"], T, "short interest")
        data.assert_public_by(last["shares_close"], T, "short interest shares")
        out.append(last[["permno", "settlement", "value"]].assign(eom=eom))
    return pd.concat(out, ignore_index=True)
