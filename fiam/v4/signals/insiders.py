# Opportunistic insider buying (Cohen-Malloy-Pomorski; Lakonishok-Lee).

import pandas as pd

from fiam.v4 import clock, data
from fiam.v4.signals import base

# Opportunistic insider buys are good news: the gate takes it as is.
SIGN = 1
# Trades public in the 6 months to T count (Lakonishok-Lee 2001).
WINDOW = pd.DateOffset(months=6)
# Open-market purchases and sales only.
CODES = ("P", "S")
# A decision's lines (lots, or a 4/A's split) count as one trade.
EVENT = ["permno", "owner_cik", "trans_date", "trans_code"]


# Each insider's class per calendar year from the 3 years before it.
def classes(t: pd.DataFrame) -> pd.DataFrame:
    rows = t[["owner_cik", "trans_date", "first_close", "superseded_at"]]
    rows = rows.dropna(subset=["trans_date"])
    rows = rows.assign(superseded_at=pd.to_datetime(rows["superseded_at"], utc=True))
    rows = rows.assign(year=rows["trans_date"].dt.year, month=rows["trans_date"].dt.month)
    out = []
    for year in range(int(rows["year"].min()) + 3, int(rows["year"].max()) + 2):
        # Only trades public before the year starts classify anyone in it.
        start = pd.Timestamp(year=year, month=1, day=1)
        # A line a 4/A replaced before the year starts no longer counts.
        kept = rows["superseded_at"].isna() | (
            rows["superseded_at"] >= start.tz_localize(clock.EASTERN)
        )
        past = rows[rows["year"].between(year - 3, year - 1) & (rows["first_close"] < start) & kept]
        years = past.groupby("owner_cik")["year"].nunique()
        traded = years[years == 3].index
        past = past[past["owner_cik"].isin(traded)]
        months = past.groupby(["owner_cik", "month"])["year"].nunique()
        routine = set(months[months == 3].index.get_level_values("owner_cik"))
        out.append(pd.DataFrame({"owner_cik": traded, "year": year,
                                 "routine": [c in routine for c in traded]}))  # fmt: skip
    return pd.concat(out, ignore_index=True)


# The opportunistic net purchase ratio over 6 months; 0 with no trade.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    cols = ["trans_date", "trans_code", "relationship", "owner_cik", "common_stock"]
    cols += ["superseded_at", "any_officer_or_director", "shares", "price"]
    t = data.table("sec_insiders", cols)
    t = t[t["trans_code"].isin(CODES) & t["common_stock"].astype(bool)]
    kinds = classes(t)
    # Officers and directors only; a filer that is only a 10% owner is out.
    role = t["relationship"].fillna("").str.contains("Director|Officer", case=False)
    t = t[role].assign(year=t["trans_date"].dt.year)
    t = t.merge(kinds, on=["owner_cik", "year"], how="left")
    log["lines_unclassified"] = int(t["routine"].isna().sum())
    t = t[t["routine"].eq(False)]
    f = base.formations(eoms)
    out = []
    for eom, T in f.itertuples(index=False):
        ids = base.universe_at(eom)
        live = t[(t["first_close"] <= T) & (t["first_close"] > T - WINDOW)]
        # A line a 4/A replaced counts until the 4/A is public before T's close.
        close = data.calendar().loc[T]
        live = live[live["superseded_at"].isna() | (live["superseded_at"] >= close)]
        data.assert_public_by(live["first_close"], T, "insider trades")
        # One trade per stock, insider, day and code (leader 2026-10-25).
        live = live.drop_duplicates(EVENT)
        buys = live[live["trans_code"] == "P"].groupby("permno").size()
        sells = live[live["trans_code"] == "S"].groupby("permno").size()
        both = pd.DataFrame({"b": buys, "s": sells}).reindex(ids).fillna(0.0)
        ratio = ((both["b"] - both["s"]) / (both["b"] + both["s"])).fillna(0.0)
        frame = pd.DataFrame({"permno": ids, "eom": eom, "value": ratio.to_numpy()})
        linked = base.has_cik(ids, T).reindex(ids).to_numpy()
        frame.loc[~linked, "value"] = float("nan")
        out.append(frame)
    return pd.concat(out, ignore_index=True)
