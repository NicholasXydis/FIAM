# One clock for every merge: when the public saw a row.

from datetime import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

EASTERN = ZoneInfo("America/New_York")
# NYSE closes at 16:00, or 13:00 on its early-close days.
CLOSE, EARLY_CLOSE = time(16, 0), time(13, 0)
# A date-only stamp means the end of that Eastern day.
END_OF_DAY = pd.Timedelta(hours=23, minutes=59, seconds=59)
# EDGAR's filing day opens at 06:00 Eastern.
EDGAR_OPEN = pd.Timedelta(hours=6)
# Short interest is public 8 trading days after settlement.
SHORT_INTEREST_LAG = 8


# Sessions as a sorted, unique, midnight DatetimeIndex in nanoseconds.
def sessions_of(days) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(days)).normalize().unique().sort_values()
    return index.as_unit("ns")


# The NYSE early-close days between two dates, from the pinned calendar.
def xnys_early_closes(start, end) -> set[pd.Timestamp]:
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS", start=pd.Timestamp(start), end=pd.Timestamp(end))
    return {pd.Timestamp(d).normalize() for d in cal.early_closes}


# The NYSE sessions between two dates, from the pinned calendar.
def xnys_sessions(start, end) -> pd.DatetimeIndex:
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS", start=pd.Timestamp(start), end=pd.Timestamp(end))
    return sessions_of(cal.sessions)


# Each session's close in UTC: 16:00 Eastern, 13:00 on early-close days.
def calendar(days, early: set | None = None) -> pd.Series:
    sessions = sessions_of(days)
    if early is None:
        early = xnys_early_closes(sessions[0], sessions[-1])
    late = pd.Timedelta(hours=CLOSE.hour)
    soon = pd.Timedelta(hours=EARLY_CLOSE.hour)
    hours = [soon if d in early else late for d in sessions]
    closes = (sessions + pd.TimedeltaIndex(hours)).tz_localize(EASTERN).tz_convert("UTC")
    return pd.Series(closes, index=sessions, name="close_utc")


# Data days against the NYSE calendar: extra or missing, as counts.
def cross_check(days) -> dict:
    ours = sessions_of(days)
    nyse = xnys_sessions(ours[0], ours[-1])
    early = xnys_early_closes(ours[0], ours[-1])
    return {
        "days": len(ours),
        "not_nyse_sessions": [str(d.date()) for d in ours.difference(nyse)],
        "nyse_sessions_missing": [str(d.date()) for d in nyse.difference(ours)],
        "early_closes": len(early),
        "early_closes_missing": sorted(str(d.date()) for d in early if d not in ours),
    }


# Stamps as a UTC series; naive stamps are refused, never guessed.
def utc(stamps) -> pd.Series:
    series = pd.Series(stamps)
    if not isinstance(series.dtype, pd.DatetimeTZDtype):
        raise ValueError("stamps need a time zone; use end_of_day or edgar_available")
    return series.dt.tz_convert("UTC").dt.as_unit("ns")


# The first close strictly after each stamp; NaT off the calendar.
def first_close(stamps, cal: pd.Series) -> pd.Series:
    when = utc(stamps)
    closes = pd.DatetimeIndex(cal).as_unit("ns").asi8
    sessions = cal.index.as_unit("ns")
    raw = when.dt.tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")
    pos = np.searchsorted(closes, raw, side="right")
    start = (sessions[0].tz_localize(EASTERN).tz_convert("UTC")).as_unit("ns").value
    ok = when.notna().to_numpy() & (pos < len(closes)) & (raw >= start)
    picked = sessions.asi8[np.minimum(pos, len(closes) - 1)]
    out = np.where(ok, picked, np.iinfo("int64").min).astype("datetime64[ns]")
    return pd.Series(out, index=when.index, name="first_close")


# A date-only stamp as the end of that Eastern day.
def end_of_day(dates) -> pd.Series:
    days = pd.Series(pd.to_datetime(pd.Series(dates))).dt.normalize()
    return (days + END_OF_DAY).dt.tz_localize(EASTERN)


# A vendor row is public at the end of its labelled day plus its lag.
def vendor_available(dates, lag_days: int) -> pd.Series:
    days = pd.Series(pd.to_datetime(pd.Series(dates))).dt.normalize()
    return end_of_day(days + pd.Timedelta(days=lag_days))


# EDGAR acceptance as the Eastern wall clock, never before 06:00.
def edgar_available(accepted, filing_date) -> pd.Series:
    text = pd.Series(np.asarray(accepted, dtype=object), dtype="string").str.slice(0, 19)
    wall = pd.to_datetime(text, format="%Y-%m-%dT%H:%M:%S", errors="coerce")
    # An ambiguous fall-back hour is read as standard time, the later one.
    standard = np.zeros(len(wall), dtype=bool)
    seen = wall.dt.tz_localize(EASTERN, ambiguous=standard, nonexistent="shift_forward")
    day = pd.Series(pd.to_datetime(np.asarray(filing_date, dtype=object))).dt.normalize()
    opens = (day + EDGAR_OPEN).dt.tz_localize(EASTERN)
    later = seen.where(seen.isna() | opens.isna() | (seen >= opens), opens)
    # No acceptance time: the end of the filing day, the later reading.
    return later.fillna(end_of_day(day))


# A Form 4 is public at its acceptance, never at its trade date.
def insider_available(accepted, filing_date) -> pd.Series:
    return edgar_available(accepted, filing_date)


# Market data is public at its own session's close: that session.
def market_session(days, cal: pd.Series) -> pd.Series:
    when = pd.Series(pd.to_datetime(pd.Series(days))).dt.normalize().dt.as_unit("ns")
    return when.where(when.isin(cal.index))


# A panel row's session: the last trading day on or before its eom.
def eom_session(eoms, cal: pd.Series) -> pd.Series:
    when = pd.Series(pd.to_datetime(pd.Series(eoms))).dt.normalize().dt.as_unit("ns")
    sessions = cal.index.as_unit("ns")
    pos = np.searchsorted(sessions.asi8, when.to_numpy().astype("int64"), side="right") - 1
    ok = when.notna().to_numpy() & (pos >= 0)
    picked = sessions.asi8[np.maximum(pos, 0)]
    out = np.where(ok, picked, np.iinfo("int64").min).astype("datetime64[ns]")
    return pd.Series(out, index=when.index, name="eom_session")


# The session n trading days after each session; NaT off the calendar.
def shift_sessions(days, n: int, cal: pd.Series) -> pd.Series:
    when = pd.Series(pd.to_datetime(pd.Series(days))).dt.normalize().dt.as_unit("ns")
    sessions = cal.index.as_unit("ns")
    pos = sessions.get_indexer(pd.DatetimeIndex(when))
    target = pos + n
    ok = (pos >= 0) & (target >= 0) & (target < len(sessions))
    picked = sessions.asi8[np.clip(target, 0, len(sessions) - 1)]
    out = np.where(ok, picked, np.iinfo("int64").min).astype("datetime64[ns]")
    return pd.Series(out, index=when.index, name="session")


# Information with first close d forms the book at the next close, d+1.
def formation(first_closes, cal: pd.Series) -> pd.Series:
    return shift_sessions(first_closes, 1, cal).rename("formation")


# The last day a label may reach while the data stay sealed.
LAST_LABEL_DAY = pd.Timestamp("2020-12-31")


# A label window that reaches past the seal: refused, never truncated.
class SealedWindow(ValueError):
    pass


# The t+1 label: close after T to close after month t+k ends.
def label_window(eom, months: int, cal: pd.Series, sealed: bool = True) -> tuple:
    last = eom_session([eom], cal).iloc[0]
    start = shift_sessions([last], 1, cal).iloc[0]
    end_month = pd.Timestamp(eom) + pd.offsets.MonthEnd(months)
    end = shift_sessions([eom_session([end_month], cal).iloc[0]], 1, cal).iloc[0]
    if sealed and (pd.isna(end) or end > LAST_LABEL_DAY):
        raise SealedWindow(f"the {months}-month label of {eom:%Y-%m} ends after 2020-12-31")
    return start, end


# Short interest is public at the end of settlement + 8 sessions.
def short_interest_available(settlements, cal: pd.Series) -> pd.Series:
    return end_of_day(shift_sessions(settlements, SHORT_INTEREST_LAG, cal))


# Fails when a feature row is not public before its formation close.
def assert_known_before(first_closes, formations, what: str) -> None:
    seen = pd.Series(pd.to_datetime(pd.Series(first_closes)))
    book = pd.Series(pd.to_datetime(pd.Series(formations)), index=seen.index)
    late = seen.isna() | book.isna() | (seen >= book)
    if late.any():
        raise AssertionError(f"{what}: {int(late.sum())} rows not public before formation")


# A monthly join keeps a row only if public by the month's last close.
def known_by_month_end(first_closes, eoms, cal: pd.Series) -> pd.Series:
    seen = pd.Series(pd.to_datetime(pd.Series(first_closes)))
    last = eom_session(pd.Series(eoms, index=seen.index), cal)
    return seen.notna() & last.notna() & (seen <= last)


# Each date's q-quantile of every value dated strictly before it.
def expanding_quantile(values, dates, q: float, min_count: int = 1) -> pd.Series:
    raw = pd.to_numeric(pd.Series(np.asarray(values, dtype=float)), errors="coerce")
    frame = pd.DataFrame({"v": raw, "d": pd.to_datetime(np.asarray(dates, dtype=object))})
    frame = frame.dropna().reset_index(drop=True)
    order = np.argsort(frame["v"].to_numpy(), kind="stable")
    ranked = frame["v"].to_numpy()[order]
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    width = max(1, int(np.sqrt(len(order))))
    have = np.zeros(len(order), dtype=np.int32)
    blocks = np.zeros(len(order) // width + 1, dtype=np.int64)
    out, seen = {}, 0
    for day, group in frame.groupby("d", sort=True):
        out[day] = _quantile(have, blocks, width, ranked, seen, q, min_count)
        picks = rank[frame.index.get_indexer(group.index)]
        have[picks] = 1
        blocks += np.bincount(picks // width, minlength=len(blocks))
        seen += len(picks)
    return pd.Series(out, name=f"q{q}").sort_index()


# The quantile of the values inserted so far, linear between ranks.
def _quantile(have, blocks, width, ranked, seen, q, min_count) -> float:
    if seen < max(1, min_count):
        return float("nan")
    k = q * (seen - 1)
    lo = int(np.floor(k))
    low = _kth(have, blocks, width, ranked, lo)
    if lo + 1 >= seen:
        return float(low)
    high = _kth(have, blocks, width, ranked, lo + 1)
    return float(low + (k - lo) * (high - low))


# The value of the (k+1)th smallest inserted rank, by block then slot.
def _kth(have, blocks, width, ranked, k) -> float:
    cum = np.cumsum(blocks)
    block = int(np.searchsorted(cum, k + 1))
    before = int(cum[block - 1]) if block else 0
    slots = np.cumsum(have[block * width : (block + 1) * width])
    slot = int(np.searchsorted(slots, k + 1 - before))
    return ranked[block * width + slot]


# Projected earnings dates: year-ago quarter + 364, else last + 91.
def project_earnings(table: pd.DataFrame, key: str = "gvkey", ahead: int = 4) -> pd.DataFrame:
    seen = table[[key, "fyearq", "fqtr", "rdq"]].copy()
    seen["rdq"] = pd.to_datetime(seen["rdq"])
    seen = seen.dropna(subset=["fyearq", "fqtr"]).astype({"fyearq": int, "fqtr": int})
    seen = seen.sort_values([key, "fyearq", "fqtr"]).drop_duplicates([key, "fyearq", "fqtr"])
    future = []
    for firm, rows in seen.groupby(key):
        year, quarter = int(rows["fyearq"].iat[-1]), int(rows["fqtr"].iat[-1])
        for _ in range(ahead):
            year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
            future.append({key: firm, "fyearq": year, "fqtr": quarter, "rdq": pd.NaT})
    grid = pd.concat([seen, pd.DataFrame(future, columns=seen.columns)], ignore_index=True)
    grid["rdq"] = pd.to_datetime(grid["rdq"])
    grid = grid.sort_values([key, "fyearq", "fqtr"], ignore_index=True)
    ago = seen.assign(fyearq=seen["fyearq"] + 1).rename(columns={"rdq": "year_ago"})
    grid = grid.merge(
        ago[[key, "fyearq", "fqtr", "year_ago"]], on=[key, "fyearq", "fqtr"], how="left"
    )
    grid["last"] = grid.groupby(key)["rdq"].transform(lambda s: s.shift(1).ffill())
    grid["projected"] = grid["year_ago"] + pd.Timedelta(days=364)
    grid["basis"] = np.where(grid["year_ago"].notna(), "year_ago", "none")
    fallback = grid["projected"].isna() & grid["last"].notna()
    grid.loc[fallback, "projected"] = grid.loc[fallback, "last"] + pd.Timedelta(days=91)
    grid.loc[fallback, "basis"] = "last_plus_91"
    grid["known_from"] = grid["year_ago"].where(grid["basis"] == "year_ago", grid["last"])
    keep = [key, "fyearq", "fqtr", "rdq", "projected", "basis", "known_from"]
    return grid[keep]
