# The engine's one reader: registered tables only, cached, blind.

import hashlib
import os
from functools import cache

import numpy as np
import pandas as pd

# Every entry here turns blind mode on for the older reader too.
os.environ["FIAM_BLIND"] = "1"

from fiam.vfinal import clock, sources  # noqa: E402

# CRSP's daily file ends with WRDS; later days have the dsf alone.
CRSP_END = pd.Timestamp("2025-12-31")
CARDS = sources.CARDS
_CACHE: dict = {}


# A table's card hash: a rebuilt table reads fresh, else it is cached.
def card_sha(name: str) -> str:
    path = CARDS / f"{name}.json"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "none"


# Every engine read goes through the registry: bans, uses, cutoff.
def table(name: str, columns=None, purpose=None, where=None) -> pd.DataFrame:
    # A set and a (low, high) range never share a cache key.
    frozen = (
        None
        if where is None
        else tuple(
            (k, ("in", tuple(sorted(v))) if isinstance(v, (set, frozenset, list)) else ("range", v))
            for k, v in sorted(where.items())
        )
    )
    key = (name, None if columns is None else tuple(columns), purpose, frozen, card_sha(name))
    if key not in _CACHE:
        _CACHE[key] = sources.read(name, columns, purpose, where)
    return _CACHE[key].copy()


# The one trading calendar: sessions and their closes in UTC.
@cache
def calendar() -> pd.Series:
    return sources.trading_calendar()


# The sessions from start to end, inclusive.
def sessions(start, end) -> pd.DatetimeIndex:
    cal = calendar()
    return cal.index[(cal.index >= pd.Timestamp(start)) & (cal.index <= pd.Timestamp(end))]


# The dsf's price-only daily returns; its price only for the gap ratio.
def dsf(permnos, start, end, prices: bool = False) -> pd.DataFrame:
    where = {"permno": set(int(p) for p in permnos), "date": (start, end)}
    if not prices:
        return table("dsf", ["ret", "ret_null"], where=where)[["permno", "date", "ret", "ret_null"]]
    frame = table("dsf", ["ret", "ret_null", "prc"], purpose="gap_ratio", where=where)
    return frame[["permno", "date", "ret", "ret_null", "prc"]]


# CRSP daily total and price-only returns, which end with 2025.
def crsp_daily(permnos, start, end) -> pd.DataFrame:
    end = min(pd.Timestamp(end), CRSP_END)
    if pd.Timestamp(start) > end:
        return pd.DataFrame(columns=["permno", "date", "ret", "retx"])
    where = {"permno": set(int(p) for p in permnos), "date": (start, end)}
    frame = table("crsp_daily", ["ret", "retx", "delflg"], where=where)
    # A delisting row is no trade; its return is the exits table's.
    frame = frame[frame["delflg"] != "Y"]
    return frame[["permno", "date", "ret", "retx"]]


# The panel's monthly rows for these stocks, each with its first close.
def panel(permnos, start, end, columns=("ret", "me", "prc")) -> pd.DataFrame:
    where = {"permno": set(int(p) for p in permnos), "eom": (start, end)}
    frame = table("panel", list(columns), where=where)
    return frame[["permno", "eom", *columns, "first_close"]]


# Rows not public by a day's close stop the run (PDF p18).
def assert_public_by(first_closes, days, what: str) -> None:
    seen = pd.to_datetime(pd.Series(first_closes)).to_numpy()
    by = pd.to_datetime(pd.Series(days)).to_numpy() if np.ndim(days) else np.datetime64(days)
    late = pd.isna(seen) | (seen > by)
    if late.any():
        raise AssertionError(f"{what}: {int(late.sum())} rows not public by their use")


# Each dated exit with its delisting return and the day it is known.
def exits(permnos) -> pd.DataFrame:
    cols = ["exit_date", "category", "group", "delret", "known", "source", "first_close"]
    frame = table("exits", cols, purpose=None)
    return frame[frame["permno"].isin(set(int(p) for p in permnos))]


# The bill's daily rate (TB3MS / 252); `by` keeps rates public by then.
def rf_daily(days, by=None) -> pd.Series:
    bills = table("tb3ms", ["tb3ms"])
    if by is not None:
        bills = bills[bills["first_close"] <= pd.Timestamp(by)]
    bills = bills.set_index("month")["tb3ms"].sort_index()
    month = pd.DatetimeIndex(days).to_period("M").to_timestamp()
    # A month past the cutoff takes the last rate public by it (stated).
    known = bills.reindex(bills.index.union(month.unique())).ffill()
    return pd.Series(known.reindex(month).to_numpy(), index=pd.DatetimeIndex(days)) / 252


# The market's daily return: CRSP value-weighted, then the dsf weighted.
def market_daily(days) -> pd.Series:
    days = pd.DatetimeIndex(days)
    crsp = table("crsp_market_daily", ["vwretd"]).set_index("date")["vwretd"]
    out = pd.Series(crsp.reindex(days).to_numpy(), index=days)
    late = days[days > CRSP_END]
    if len(late):
        out.loc[late] = dsf_market(late).reindex(late).to_numpy()
    return out


# The dsf's own value-weighted return: month-end caps, drifted.
def dsf_market(days) -> pd.Series:
    days = pd.DatetimeIndex(days)
    first = (days.min() - pd.offsets.MonthEnd(1)).normalize()
    caps = table("panel", ["me"], where={"eom": (first, days.max())})
    rets = table("dsf", ["ret"], where={"date": (first + pd.Timedelta(days=1), days.max())})
    rets = rets.sort_values(["permno", "date"])
    rets["eom"] = (rets["date"] - pd.offsets.MonthEnd(1)).dt.normalize()
    caps = caps.rename(columns={"first_close": "cap_public"})
    both = rets.merge(caps[["permno", "eom", "me", "cap_public"]], on=["permno", "eom"])
    assert_public_by(both["cap_public"], both["date"], "dsf market caps")
    # Each cap grows with the stock's own price since the month end.
    growth = (1 + both["ret"].fillna(0.0)).groupby([both["permno"], both["eom"]]).cumprod()
    both["cap"] = both["me"] * growth.groupby([both["permno"], both["eom"]]).shift(fill_value=1.0)
    both = both.dropna(subset=["ret", "cap"])
    weight = both["cap"] / both.groupby("date")["cap"].transform("sum")
    out = (weight * both["ret"]).groupby(both["date"]).sum()
    return out.reindex(days)


# Each stock's company id (PERMCO) on each date, from the dated links.
def permcos(permnos, dates) -> pd.Series:
    from fiam.vfinal import links

    lk = table("links", None, purpose=None)
    got = links.value_at(lk, "permco", permnos, dates)
    return pd.to_numeric(got, errors="coerce")


# The month end whose panel row is public by a day's close.
def month_end_at(day) -> pd.Timestamp:
    day = pd.Timestamp(day).normalize()
    this = day + pd.offsets.MonthEnd(0)
    return this if eom_session([this]).iloc[0] <= day else day - pd.offsets.MonthEnd(1)


# The last session on or before each month end.
def eom_session(eoms) -> pd.Series:
    return clock.eom_session(eoms, calendar())


# The session n trading days after each day; NaT off the calendar.
def shift(days, n: int) -> pd.Series:
    return clock.shift_sessions(days, n, calendar())


# Month ends from start to end as normalised timestamps.
def month_ends(start, end) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME")


# Days with no value become NaN, never zero, in a returns matrix.
def matrix(frame: pd.DataFrame, value: str, days, permnos) -> pd.DataFrame:
    wide = frame.pivot_table(index="date", columns="permno", values=value, aggfunc="first")
    return wide.reindex(index=pd.DatetimeIndex(days), columns=sorted(set(permnos))).astype(float)
