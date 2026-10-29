# The Arcana files, dated by trade day.

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import data, links
from fiam.vfinal.report.table_9_1 import rebalances

# The headline file's columns, as the guide names them.
WEIGHTS = ["Date", "Ticker", "Weights", "Asset Class", "ISIN", "AUM", "Custom Tag"]
# The reconciliation file's columns: dollars held and the day's P&L.
POSITIONS = ["Date", "Ticker", "Net Invested", "PNL", "Asset Class", "ISIN", "AUM", "Custom Tag"]
# Kept in our own copy only: the PERMNO and the company's name.
OWN = ["PERMNO", "Name"]
# The link kinds that give a position its names (the links card).
KINDS = ("ticker", "symbol", "share_class", "cusip", "name")
# CRSP's name for a company's last row before a change.
LAST_KNOWN = " (Last Known)"


# The ISIN check digit: letters to numbers, then Luhn on the digits.
def isin_check_digit(body: str) -> str:
    digits = "".join(str(int(c, 36)) for c in body.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n // 10 + n % 10
    return str((10 - total % 10) % 10)


# "US" and the 9-character CUSIP and the check digit; None if no CUSIP.
def isin(cusip) -> str | None:
    if pd.isna(cusip) or len(str(cusip)) != 9 or not str(cusip).isalnum():
        return None
    body = "US" + str(cusip).upper()
    return body + isin_check_digit(body)


# "MSFT US Equity"; a share class joins with a slash, "BRK/A US Equity".
def bloomberg(ticker, symbol, share_class) -> str | None:
    if pd.isna(ticker) or not str(ticker):
        return None
    t = str(ticker).upper()
    cls = "" if pd.isna(share_class) else str(share_class).upper()
    # CRSP's trading symbol runs the class on, BRKA for BRK and A.
    if cls and not pd.isna(symbol) and str(symbol).upper() == t + cls:
        t = f"{t}/{cls}"
    return f"{t} US Equity"


# Ticker, CUSIP, ISIN and name for each stock and day, from the links.
def identifiers(permnos, dates, table: pd.DataFrame | None = None) -> pd.DataFrame:
    table = data.table("links", None) if table is None else table
    pairs = pd.DataFrame({"permno": np.asarray(permnos), "date": pd.to_datetime(dates)})
    pairs = pairs.drop_duplicates().astype({"permno": "int64", "date": "datetime64[ns]"})
    pairs = pairs.sort_values(["permno", "date"], ignore_index=True)
    got = {k: links.value_at(table, k, pairs["permno"], pairs["date"]) for k in KINDS}
    ticker = [bloomberg(*row) for row in zip(got["ticker"], got["symbol"], got["share_class"])]
    cusip = got["cusip"].astype(object).where(got["cusip"].notna(), None)
    name = got["name"].astype(object).where(got["name"].notna(), None)
    pairs["ticker"] = ticker
    pairs["cusip"] = cusip
    pairs["isin"] = [isin(c) for c in cusip]
    pairs["name"] = [None if n is None else str(n).removesuffix(LAST_KNOWN) for n in name]
    return pairs


# A date column as nanosecond timestamps, so every merge matches.
def stamps(x) -> pd.Series:
    return pd.to_datetime(x).astype("datetime64[ns]")


# Every session with any trade, from the trades frame.
def trade_days(trades: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(sorted(stamps(trades["date"]).unique()))


# Each month's formation, dated by its first trade day (our reading).
def monthly_days(trades: pd.DataFrame) -> pd.DatetimeIndex:
    first = rebalances(trades).sort_index()
    last = first.groupby(pd.DatetimeIndex(first.index).to_period("M")).last()
    return pd.DatetimeIndex(sorted(stamps(last).unique()))


# Rows with no ticker or no ISIN, with the weight, never dropped.
def missing_ids(file: pd.DataFrame, value: str) -> pd.DataFrame:
    no_ticker, no_isin = file["Ticker"] == "", file["ISIN"] == ""
    lost = file[no_ticker | no_isin]
    out = lost[["Date", "PERMNO", "Name", value]].copy()
    return out.assign(ticker_missing=no_ticker[lost.index], isin_missing=no_isin[lost.index])


# The names for a frame of (permno, date): blanks where unknown.
def with_ids(frame: pd.DataFrame, ids: pd.DataFrame) -> pd.DataFrame:
    key = ids[["permno", "date", "ticker", "isin", "name"]]
    got = frame.merge(key, on=["permno", "date"], how="left")
    got["Ticker"] = got["ticker"].fillna("").astype(str)
    got["ISIN"] = got["isin"].fillna("").astype(str)
    got["Name"] = got["name"].fillna("").astype(str)
    got["PERMNO"] = got["permno"].astype("int64")
    got["Date"] = got["date"].dt.strftime("%Y-%m-%d")
    got["Asset Class"] = "Equity"
    return got


# The headline file and the names Arcana cannot fully resolve.
def weights_file(positions, daily, ids, dates=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = positions.assign(date=stamps(positions["date"]))
    if dates is not None:
        p = p[p["date"].isin(stamps(pd.Series(dates)))]
    nav = p["date"].map(daily["nav"])
    p = p.assign(Weights=p["value"] / nav, AUM=nav)
    out = with_ids(p, ids.assign(date=stamps(ids["date"])))
    out["Custom Tag"] = np.where(out["value"] < 0, "short", "long")
    out = out.sort_values(["date", "permno"], ignore_index=True)
    return out[WEIGHTS + OWN], missing_ids(out, "Weights")


# The reconciliation file: dollars held and the day's P&L by name.
def positions_file(positions, ledger, ids, daily=None, dates=None):
    held = positions.assign(date=stamps(positions["date"]))
    led = ledger.assign(date=stamps(ledger["date"]))
    pnl = led.groupby(["date", "permno"])["dollars"].sum().rename("PNL").reset_index()
    both = held.merge(pnl, on=["date", "permno"], how="outer")
    both["Net Invested"] = both.pop("value").fillna(0.0)
    both["PNL"] = both["PNL"].fillna(0.0)
    # A name closed today keeps its day's P&L on a zero position.
    both = both[(both["Net Invested"] != 0) | (both["PNL"] != 0)]
    if dates is not None:
        both = both[both["date"].isin(stamps(pd.Series(dates)))]
    out = with_ids(both, ids.assign(date=stamps(ids["date"])))
    out["AUM"] = out["date"].map(daily["nav"]) if daily is not None else np.nan
    side = np.where(out["Net Invested"] < 0, "short", "long")
    out["Custom Tag"] = np.where(out["Net Invested"] == 0, "closed", side)
    out = out.sort_values(["date", "permno"], ignore_index=True)
    return out[POSITIONS + OWN], missing_ids(out, "Net Invested")


# Writes the Arcana columns to path and the full copy beside it.
def write_csv(file: pd.DataFrame, path, columns: list[str]) -> Path:
    path = Path(path)
    file[columns].to_csv(path, index=False)
    file.to_csv(path.with_name(path.stem + "_own.csv"), index=False)
    return path
