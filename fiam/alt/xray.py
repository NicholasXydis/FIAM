# The live X-ray: an earnings preview card per big holding.

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt.common import CREDIT
from fiam.vfinal import clock, data, sources
from fiam.vfinal import links as link_table
from fiam.vfinal.desk.agents import SHRINKS
from fiam.vfinal.desk.triggers import EARNINGS_DAYS

# Saved inputs only, no network; outputs go to out/alt/xray alone.
ROOT = sources.ROOT
SNAPSHOT = sources.DATA / "carbon_arc" / "snapshot_1"
CATALOGUE = sources.DATA / "carbon_arc" / "catalogue"
OUT = ROOT / "out" / "alt" / "xray"
# The three owned activity series, by dataset id.
SERIES = {"card_spend": "CA0056", "foot_traffic": "CA0060", "web_traffic": "CA0030"}
LABELS = {"card_spend": "Card spend", "foot_traffic": "Foot traffic", "web_traffic": "Web traffic"}
BENZINGA = "CA0035"
# Columns that name the row, never a part of the measure.
ID_COLUMNS = {"date", "entity_id", "entity_name", "entity_representation"}
# Benzinga insights bought; None keeps the row's own deal type.
NEWS_TYPES = {461: "insider news", 497: "offerings", 501: None}
# Months in a window: one fiscal quarter, the quarter the print reports.
MONTHS = 3
# A latest month further behind than this is stale and casts no vote.
STALE_MONTHS = 2
# Weeks of Benzinga news counted, one quarter.
NEWS_WEEKS = 13
# Growth must speed up or slow by 2 points to read up or down.
FLAT = 0.02
# Card spend counts twice in the read, since the trim rests on it.
WEIGHTS = {"card_spend": 2, "foot_traffic": 1, "web_traffic": 1}
# The trim proposed when card spend contradicts the side, by confidence.
TRIM = {"low": 0.75, "medium": 0.5}
# Holdings carded by default.
TOP = 10
# Display labels for known book files.
BOOK_LABELS = {"september_final.csv": "v3 book, September 2026"}
# Where each card's ticker came from, in words.
TICKER_NOTES = {
    "book": "Ticker as the book file gives it",
    "none": "No ticker in the book and the dated links after 2020 stay sealed until the "
    "unseal, so no Carbon Arc or news match",
}
# Why the NOAA weather headwind is skipped for now.
WEATHER_SKIPPED = (
    "Skipped. The protocol defines the headwind (drought for farm and food industries, "
    "temperature for utilities and a warm winter for retail, footprint weighted) but no NOAA "
    "climate table is registered and the footprint and industry codes after 2020 stay sealed "
    "until the unseal, so a read now would rest on stale inputs"
)
# I/B/E/S is shown only, never used in a read or a trim.
IBES_NOTE = (
    "Shown with its date only. It feeds neither the read nor the trim (PLAN 1.2, B20, B27) "
    "and I/B/E/S ends 2025-12"
)
# The rules each run states beside its cards.
RULES = [
    "Live only on the final book (PLAN Appendix B). Nothing here enters a forecast, gate or "
    "backtest and no scored month changes",
    "Carbon Arc is current vintage (PLAN 1.2, B29). Growth rates only leave this tool, never raw "
    "values (PLAN 12.5)",
    "Each month counts only after its stated lag and only once complete (A14)",
    "Benzinga is counts by type and week only, never traded (B29)",
    "The next print is the registry's projection known by the as-of date (B22), read through "
    "blind mode",
    "The trim is shrink only, from the desk's set, logged and never applied",
    "I/B/E/S appears only if a file is given, as the last consensus with its date (B20)",
]


# One dataset's rows on one entity, with its clock and vintage notes.
@dataclass
class Series:
    rows: pd.DataFrame
    lag: int
    table_max: pd.Timestamp
    pulled_at: str
    notes: dict = field(default_factory=dict)


# Everything a card reads, loaded once; tests pass synthetic data.
@dataclass
class Inputs:
    series: dict
    news: pd.DataFrame
    news_lag: int
    news_pulled: str
    calendar: pd.DataFrame
    seal: pd.Timestamp
    ibes: pd.DataFrame | None = None
    opened: bool | None = None


# The day count in a stated lag such as "T + 3 Days".
def parse_lag(text: str) -> int:
    found = re.search(r"T\s*\+\s*(\d+)\s*Day", str(text), flags=re.IGNORECASE)
    if not found:
        raise ValueError(f"unreadable lag {text!r}")
    return int(found.group(1))


# The first value under a key anywhere in nested JSON.
def find_key(obj, key: str):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for item in obj:
            got = find_key(item, key)
            if got is not None:
                return got
    return None


# A dataset's lag in days as its catalogue page states it.
def stated_lag(dataset: str, catalogue: Path = CATALOGUE) -> int:
    info = json.loads((catalogue / dataset / "information.json").read_text())
    return parse_lag(find_key(info, "Lag"))


# One snapshot file's rows and its receipt, as saved at the pull.
def read_pull(path: Path) -> tuple[pd.DataFrame, str, dict]:
    with gzip.open(path) as fh:
        raw = json.load(fh)
    receipt = json.loads(path.with_name(path.name.replace(".json.gz", ".receipt.json")).read_text())
    return pd.DataFrame(raw["data"]), raw["insight_column"], receipt


# An activity series as long rows: ticker, part, month, value.
def load_series(dataset: str, snapshot: Path = SNAPSHOT, catalogue: Path = CATALOGUE) -> Series:
    frames, maxes, pulls, bad = [], [], [], 0
    for path in sorted(snapshot.glob(f"{dataset}_*.json.gz")):
        rows, col, receipt = read_pull(path)
        value = pd.to_numeric(rows[col], errors="coerce")
        bad += int(value.isna().sum() - rows[col].isna().sum())
        parts = [c for c in rows.columns if c not in ID_COLUMNS | {col}]
        part = rows[parts].astype(str).agg(" ".join, axis=1) if parts else "all"
        frames.append(
            pd.DataFrame(
                {
                    "ticker": rows["entity_name"].astype(str),
                    "part": part,
                    "month": pd.PeriodIndex(pd.to_datetime(rows["date"]), freq="M"),
                    "value": value,
                    "pulled_at": receipt["pulled_at"],
                }
            )
        )
        maxes.append(pd.Timestamp(receipt["metadata"]["table_max_date"]))
        pulls.append(receipt["pulled_at"])
    if not frames:
        empty = pd.DataFrame(columns=["ticker", "part", "month", "value"])
        return Series(empty, stated_lag(dataset, catalogue), pd.NaT, "never pulled")
    rows = pd.concat(frames).dropna(subset=["value"]).sort_values("pulled_at")
    # A later pull of the same month replaces the prior one.
    rows = rows.drop_duplicates(["ticker", "part", "month"], keep="last").drop(columns="pulled_at")
    notes = {"values_not_numeric_dropped": bad, "tickers": sorted(rows["ticker"].unique())}
    lag = stated_lag(dataset, catalogue)
    return Series(rows.reset_index(drop=True), lag, min(maxes), max(pulls), notes)


# Benzinga rows as ticker, week label and event type.
def load_news(snapshot: Path = SNAPSHOT) -> tuple[pd.DataFrame, str]:
    frames, pulls = [], []
    for insight, kind in NEWS_TYPES.items():
        path = snapshot / f"{BENZINGA}_{insight}.json.gz"
        if not path.exists():
            continue
        rows, col, receipt = read_pull(path)
        kinds = rows[col].astype(str).str.lower() if kind is None else kind
        frames.append(
            pd.DataFrame(
                {
                    "ticker": rows["entity_name"].astype(str),
                    "week": pd.to_datetime(rows["date"]),
                    "type": kinds,
                }
            )
        )
        pulls.append(receipt["pulled_at"])
    if not frames:
        return pd.DataFrame(columns=["ticker", "week", "type"]), "never pulled"
    return pd.concat(frames, ignore_index=True), max(pulls)


# Projected print dates for these stocks, through the registry's seal.
def load_calendar(permnos) -> pd.DataFrame:
    cols = ["projected", "basis", "known_from"]
    return data.table("earnings_calendar", cols, where={"permno": set(int(p) for p in permnos)})


# An optional I/B/E/S file, the last consensus per stock and date.
def load_ibes(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    frame = pd.read_csv(path)
    missing = {"permno", "consensus", "statpers"} - set(frame.columns)
    if missing:
        raise ValueError(f"I/B/E/S file lacks {sorted(missing)}")
    frame["statpers"] = pd.to_datetime(frame["statpers"])
    return frame.astype({"permno": "int64"})


# The book on the as-of date: permno, value, ticker and name.
def load_book(path: Path, as_of: pd.Timestamp) -> pd.DataFrame:
    book = pd.read_csv(path)
    value = "value" if "value" in book.columns else "weight"
    if value not in book.columns or "permno" not in book.columns:
        raise ValueError("a book needs permno and value (or weight)")
    # A dated book uses its latest date on or before the as-of date.
    if "date" in book.columns:
        book["date"] = pd.to_datetime(book["date"])
        book = book[book["date"] <= as_of]
        if book.empty:
            raise ValueError("no positions dated on or before the as-of date")
        book = book[book["date"] == book["date"].max()]
    out = pd.DataFrame({"permno": book["permno"].astype("int64"), "value": book[value]})
    out["ticker"] = book["ticker"] if "ticker" in book.columns else pd.NA
    out["name"] = book["company_name"] if "company_name" in book.columns else pd.NA
    return out[out["value"] != 0].reset_index(drop=True)


# The largest holdings by absolute value, ties broken by PERMNO.
def largest(book: pd.DataFrame, top: int) -> pd.DataFrame:
    order = book.assign(size=book["value"].abs()).sort_values(
        ["size", "permno"], ascending=[False, True]
    )
    return order.head(top).drop(columns="size").reset_index(drop=True)


# Months public by the as-of date: complete and past their lag.
def public_months(months: pd.PeriodIndex, as_of, lag: int, table_max) -> np.ndarray:
    ends = months.to_timestamp(how="end").normalize()
    public = ends + pd.Timedelta(days=lag) <= pd.Timestamp(as_of)
    if pd.notna(table_max):
        public &= ends <= pd.Timestamp(table_max)
    return np.asarray(public)


# A note when the data were pulled after the as-of date (PDF p15-16).
def vintage(pulled_at: str, as_of) -> str | None:
    try:
        stamp = pd.Timestamp(pulled_at)
    except ValueError:
        return None
    if pd.isna(stamp) or (pulled := stamp.date()) <= pd.Timestamp(as_of).date():
        return None
    return f"Current vintage pulled {pulled}, after the as-of date, so later revisions may show"


# Up, flat or down from the change in year-on-year growth.
def vote(acceleration: float) -> int:
    if acceleration > FLAT:
        return 1
    return -1 if acceleration < -FLAT else 0


# Latest months against the same months a year back, and the speed-up.
def trend(series: Series, ticker, as_of, months: int = MONTHS) -> dict:
    own = series.rows[series.rows["ticker"] == ticker] if isinstance(ticker, str) else None
    base = {"lag_days": series.lag, "pulled_at": series.pulled_at}
    if note := vintage(series.pulled_at, as_of):
        base["vintage"] = note
    if own is None or own.empty:
        return {**base, "status": "no data", "why": "No Carbon Arc rows for this name"}
    own = own[public_months(pd.PeriodIndex(own["month"]), as_of, series.lag, series.table_max)]
    if own.empty:
        return {**base, "status": "no data", "why": "No complete month public by the as-of date"}
    wide = own.pivot_table(index="month", columns="part", values="value", aggfunc="sum")
    last = wide.index.max()
    behind = (pd.Period(pd.Timestamp(as_of), "M") - 1 - last).n
    if behind > STALE_MONTHS:
        why = f"Stale. The latest public month {last} is {behind} months behind"
        return {**base, "status": "stale", "why": why, "latest_month": str(last)}
    recent = pd.period_range(last - (months - 1), last, freq="M")
    prior = recent.shift(-months)
    need = recent.append(prior).append(recent.shift(-12)).append(prior.shift(-12))
    # Only parts present in every month used, so a new part adds nothing.
    window = wide.reindex(need).dropna(axis=1, how="any")
    total = window.sum(axis=1)
    if window.empty or window.shape[1] == 0 or (total <= 0).any():
        why = f"Fewer than {2 * months + 12} usable months up to {last}"
        return {**base, "status": "too short", "why": why, "latest_month": str(last)}
    g_recent = total[recent].sum() / total[recent.shift(-12)].sum() - 1
    g_prior = total[prior].sum() / total[prior.shift(-12)].sum() - 1
    speed = g_recent - g_prior
    return {
        **base,
        "status": "ok",
        "months": [str(m) for m in recent],
        "latest_month": str(last),
        "months_behind": behind,
        "growth_recent": round(float(g_recent), 4),
        "growth_prior": round(float(g_prior), 4),
        "acceleration": round(float(speed), 4),
        "vote": {1: "up", 0: "flat", -1: "down"}[vote(speed)],
    }


# Benzinga rows by type over the last weeks, with a year's baseline.
def news(frame: pd.DataFrame, ticker, as_of, lag: int, pulled: str = "") -> dict:
    as_of, weeks = pd.Timestamp(as_of), NEWS_WEEKS
    own = frame[frame["ticker"] == ticker] if isinstance(ticker, str) else frame.iloc[:0]
    own = own[own["week"] + pd.Timedelta(days=lag) <= as_of]
    if own.empty:
        why = "No Benzinga rows for this name in the three insights bought"
        return {"status": "no data", "why": why, "weeks": weeks, "lag_days": lag}
    start = as_of - pd.Timedelta(weeks=weeks)
    recent = own[own["week"] > start]
    year = own[(own["week"] <= start) & (own["week"] > start - pd.Timedelta(weeks=52))]
    scale = weeks / 52
    out = {
        "status": "ok",
        "weeks": weeks,
        "lag_days": lag,
        "counts": {k: int(v) for k, v in recent["type"].value_counts().sort_index().items()},
        "total": len(recent),
        "year_before_per_window": round(len(year) * scale, 1),
        "last_week_seen": own["week"].max().date().isoformat(),
    }
    if note := vintage(pulled, as_of):
        out["vintage"] = note
    return out


# The next projected print known by the as-of date, else why not.
def next_print(calendar: pd.DataFrame, permno: int, as_of, seal: pd.Timestamp, opened=None) -> dict:
    as_of = pd.Timestamp(as_of)
    own = calendar[(calendar["permno"] == permno) & (calendar["projected"] > as_of)]
    own = own[pd.to_datetime(own["first_close"]) <= as_of]
    opened = sources.unsealed() if opened is None else opened
    if own.empty:
        # Only blind mode hides projections, so with the gate open none is.
        if as_of > seal and not opened:
            why = (
                f"Sealed. Blind mode hides projections made after {seal.date()} until the "
                "unseal, so none is known here"
            )
            return {"status": "sealed", "why": why}
        return {"status": "none known", "why": "No projection known by the as-of date"}
    row = own.sort_values("projected").iloc[0]
    day = pd.Timestamp(row["projected"])
    # Weekdays after the as-of date up to the print; holidays ignored.
    after = (as_of + pd.Timedelta(days=1)).date()
    ahead = int(np.busday_count(after, (day + pd.Timedelta(days=1)).date()))
    return {
        "status": "projected",
        "date": day.date().isoformat(),
        "basis": str(row["basis"]),
        "known_from": pd.Timestamp(row["known_from"]).date().isoformat(),
        "sessions_ahead": ahead,
    }


# The last consensus dated on or before the as-of date, shown only.
def consensus(ibes: pd.DataFrame | None, permno: int, as_of) -> dict:
    if ibes is None:
        return {"status": "not given", "why": "No I/B/E/S file was given"}
    own = ibes[(ibes["permno"] == permno) & (ibes["statpers"] <= pd.Timestamp(as_of))]
    if own.empty:
        return {"status": "no data", "why": "No consensus dated by the as-of date"}
    row = own.sort_values("statpers").iloc[-1]
    out = {
        "status": "shown",
        "consensus": float(row["consensus"]),
        "date": row["statpers"].date().isoformat(),
        "age_days": int((pd.Timestamp(as_of) - row["statpers"]).days),
        "note": IBES_NOTE,
    }
    for extra in ("fpedats", "numest"):
        if extra in row.index and pd.notna(row[extra]):
            out[extra] = str(row[extra])
    return out


# The direction of surprise and an honest confidence from the votes.
def read(trends: dict) -> dict:
    votes = {k: {"up": 1, "flat": 0, "down": -1}[t["vote"]] for k, t in trends.items()
             if t["status"] == "ok"}  # fmt: skip
    if not votes:
        why = "No Carbon Arc card spend, foot traffic or web traffic for this name, so no read"
        return {"direction": "none", "confidence": "none", "why": why}
    score = sum(WEIGHTS[k] * v for k, v in votes.items())
    direction = "up" if score > 0 else "down" if score < 0 else "flat"
    signs = set(votes.values())
    agree = "card_spend" in votes and len(votes) >= 2 and len(signs) == 1 and 0 not in signs
    # Medium at most, since no Carbon Arc read may ever be backtested.
    confidence = "medium" if agree else "low"
    used = " and ".join(LABELS[k].lower() for k in votes)
    why = (
        f"From {used}, growth against a year back speeding up or slowing versus the quarter "
        f"before. Untested by rule since Carbon Arc has no history we may backtest"
    )
    return {"direction": direction, "confidence": confidence, "why": why}


# Keep, or a shrink-only trim into the print when spend opposes it.
def suggest(value: float, trends: dict, view: dict, print_info: dict) -> dict:
    keep = {"action": "keep", "shrink": 1.0, "applied": False}
    card = trends.get("card_spend", {})
    if card.get("status") != "ok":
        return {**keep, "why": "No card spend data, so nothing contradicts the position"}
    side = 1 if value > 0 else -1
    against = {"up": 1, "flat": 0, "down": -1}[card["vote"]] == -side
    if not against:
        return {**keep, "why": "Card spend agrees with the position or reads flat"}
    proposed = TRIM[view["confidence"]]
    if proposed not in SHRINKS:
        raise AssertionError(f"shrink {proposed} is outside the desk's set")
    if print_info.get("status") != "projected":
        why = "Card spend contradicts the position but no print is known, so no trim yet"
        return {**keep, "proposed": proposed, "why": why}
    ahead = print_info["sessions_ahead"]
    if ahead > EARNINGS_DAYS:
        why = (
            f"Card spend contradicts the position. The print is {ahead} sessions away, so "
            f"rerun within {EARNINGS_DAYS} sessions of it"
        )
        return {**keep, "proposed": proposed, "why": why}
    why = f"Card spend contradicts the position and the print is {ahead} sessions away"
    return {
        "action": "trim",
        "shrink": proposed,
        "proposed": proposed,
        "applied": False,
        "why": why,
    }


# One holding's card from every input known by the as-of date.
def card(rank: int, row, gross: float, as_of, inputs: Inputs) -> dict:
    ticker = row["ticker"] if isinstance(row["ticker"], str) and row["ticker"] else None
    source = row.get("ticker_source")
    note = TICKER_NOTES["none"] if ticker is None else TICKER_NOTES.get(source, source)
    trends = {k: trend(s, ticker, as_of) for k, s in inputs.series.items()}
    view = read(trends)
    upcoming = next_print(inputs.calendar, int(row["permno"]), as_of, inputs.seal, inputs.opened)
    return {
        "rank": rank,
        "permno": int(row["permno"]),
        "ticker": ticker,
        "ticker_note": note,
        "name": row["name"] if isinstance(row["name"], str) else None,
        "side": "long" if row["value"] > 0 else "short",
        "share_of_gross": round(abs(float(row["value"])) / gross, 5),
        "next_print": upcoming,
        "activity": trends,
        "benzinga": news(inputs.news, ticker, as_of, inputs.news_lag, inputs.news_pulled),
        "weather": {"status": "skipped", "why": WEATHER_SKIPPED},
        "ibes": consensus(inputs.ibes, int(row["permno"]), as_of),
        "read": view,
        "suggestion": suggest(float(row["value"]), trends, view, upcoming),
    }


# How many cards each source reaches, by count and share of gross.
def coverage(cards: list) -> dict:
    out = {"cards": len(cards)}
    pick = {
        "with_ticker": lambda c: c["ticker"] is not None,
        **{k: (lambda c, k=k: c["activity"][k]["status"] == "ok") for k in SERIES},
        "benzinga_any_rows": lambda c: c["benzinga"]["status"] == "ok",
        "benzinga_recent": lambda c: c["benzinga"].get("total", 0) > 0,
        "next_print": lambda c: c["next_print"]["status"] == "projected",
        "ibes": lambda c: c["ibes"]["status"] == "shown",
        "a_read": lambda c: c["read"]["direction"] != "none",
        "trim_now": lambda c: c["suggestion"]["action"] == "trim",
    }
    for name, test in pick.items():
        hit = [c for c in cards if test(c)]
        out[name] = {
            "names": len(hit),
            "share_of_gross": round(sum(c["share_of_gross"] for c in hit), 5),
        }
    return out


# Tickers the book lacks, from the dated links once they are unsealed.
def fill_tickers(book: pd.DataFrame, as_of, seal: pd.Timestamp, unsealed: bool) -> pd.DataFrame:
    book = book.copy()
    given = book["ticker"].map(lambda t: isinstance(t, str) and bool(t.strip()))
    names = [t.strip() if ok else None for t, ok in zip(book["ticker"], given)]
    book["ticker"] = pd.Series(names, index=book.index, dtype=object)
    book["ticker_source"] = np.where(given, "book", "none").astype(object)
    if given.all() or not unsealed:
        return book
    # The link in force at the as-of date, or at the seal if that is sooner.
    when = min(pd.Timestamp(as_of), seal)
    gaps = book.index[~given]
    links = data.table("links", None, purpose=None)
    got = link_table.value_at(links, "ticker", book.loc[gaps, "permno"], [when] * len(gaps))
    found = got.notna().to_numpy()
    book.loc[gaps[found], "ticker"] = got[found].astype(str).to_numpy()
    book.loc[gaps[found], "ticker_source"] = f"Ticker from the dated links at {when.date()}"
    return book


# Book-wide reach: names whose ticker any owned source covers.
def book_coverage(book: pd.DataFrame, inputs: Inputs) -> dict:
    gross = float(book["value"].abs().sum())
    owned = {k: set(s.rows["ticker"]) for k, s in inputs.series.items()}
    owned["benzinga_ever"] = set(inputs.news["ticker"])
    out = {"names": int(len(book)), "with_ticker": int(book["ticker"].notna().sum())}
    for name, tickers in owned.items():
        hit = book["ticker"].isin(tickers)
        share = round(float(book.loc[hit, "value"].abs().sum()) / gross, 5)
        out[name] = {"names": int(hit.sum()), "share_of_gross": share}
    return out


# The registry and snapshot notes for each source the run read.
def source_notes(inputs: Inputs, ibes) -> dict:
    out = {}
    for k, s in inputs.series.items():
        out[k] = {
            "dataset": SERIES[k],
            "lag_days": s.lag,
            "pulled_at": s.pulled_at,
            "table_max_date": None if pd.isna(s.table_max) else s.table_max.date().isoformat(),
            "tickers_owned": s.notes.get("tickers", []),
            "values_not_numeric_dropped": s.notes.get("values_not_numeric_dropped", 0),
        }
    out["benzinga"] = {"dataset": BENZINGA, "lag_days": inputs.news_lag,
                       "pulled_at": inputs.news_pulled}  # fmt: skip
    out["ibes"] = "given" if ibes else "not given"
    out["earnings_calendar"] = f"registry, read through blind mode to {inputs.seal.date()}"
    return out


# Every card and its run record for a book on an as-of date.
def build_cards(book: pd.DataFrame, as_of, top: int, inputs: Inputs) -> list:
    gross = float(book["value"].abs().sum())
    chosen = largest(book, top)
    return [card(i + 1, row, gross, as_of, inputs) for i, row in chosen.iterrows()]


# A file's SHA-256, so the log names the exact book read.
def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Loads every live input from the saved snapshot and the registry.
def load_inputs(permnos, ibes: Path | None = None, snapshot: Path = SNAPSHOT) -> Inputs:
    series = {k: load_series(d, snapshot) for k, d in SERIES.items()}
    frame, pulled = load_news(snapshot)
    seal = sources.seal_at().tz_convert(clock.EASTERN).tz_localize(None).normalize()
    cal = load_calendar(permnos)
    return Inputs(
        series, frame, stated_lag(BENZINGA), pulled, cal, seal, load_ibes(ibes), sources.unsealed()
    )


# The whole X-ray: the cards, their coverage and the rules applied.
def run(path: Path, as_of, top: int = TOP, label: str | None = None, ibes=None) -> dict:
    as_of = pd.Timestamp(as_of).normalize()
    path = Path(path).resolve()
    book = load_book(path, as_of)
    inputs = load_inputs(book["permno"].unique(), ibes)
    book = fill_tickers(book, as_of, inputs.seal, sources.unsealed())
    cards = build_cards(book, as_of, top, inputs)
    sealed = not sources.unsealed()
    meta = {
        "tool": "fiam.alt.xray",
        "book": label or BOOK_LABELS.get(path.name, path.stem),
        "book_file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "book_sha256": digest(path),
        "book_names": int(len(book)),
        "as_of": as_of.date().isoformat(),
        "top": top,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "blind_mode": "on, rows public after 2020-12-31 are sealed" if sealed else "unsealed",
        "acts_on": "Nothing. Suggestions are logged for the leader and no scored month changes",
        "sources": source_notes(inputs, ibes),
        "credit": CREDIT,
        "rules": RULES,
        "settings": {
            "months": MONTHS,
            "news_weeks": NEWS_WEEKS,
            "flat_band": FLAT,
            "stale_months": STALE_MONTHS,
            "weights": WEIGHTS,
            "trim": TRIM,
            "shrink_set": list(SHRINKS),
            "print_window_sessions": EARNINGS_DAYS,
        },
    }
    return {
        "meta": meta,
        "book_coverage": book_coverage(book, inputs),
        "coverage": coverage(cards),
        "cards": cards,
    }


# Each coverage count in words for the HTML page.
PHRASES = {
    "with_ticker": "a ticker",
    "card_spend": "card spend",
    "foot_traffic": "foot traffic",
    "web_traffic": "web traffic",
    "benzinga_any_rows": "any Benzinga rows",
    "benzinga_recent": "Benzinga news in the last 13 weeks",
    "benzinga_ever": "Benzinga rows ever",
    "next_print": "a projected next print",
    "ibes": "an I/B/E/S consensus",
    "a_read": "a read",
    "trim_now": "a trim proposed now",
}


# A percentage with its sign, or n/a.
def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


# One activity line for the HTML card, growth only, never levels.
def activity_text(t: dict) -> str:
    if t["status"] == "no data":
        return f"No data. {t['why']}"
    if t["status"] != "ok":
        return t["why"]
    return (
        f"{pct(t['growth_recent'])} on a year back over {t['months'][0]} to {t['months'][-1]}, "
        f"{pct(t['acceleration'])} versus the quarter before, reads {t['vote']} "
        f"(lag {t['lag_days']} days)"
    )


# The print line for the HTML card.
def print_text(p: dict) -> str:
    if p["status"] != "projected":
        return p["why"]
    ahead = f"{p['sessions_ahead']} sessions ahead"
    return f"{p['date']}, {ahead} (projected, known from {p['known_from']})"


# The news line for the HTML card.
def news_text(n: dict) -> str:
    if n["status"] != "ok":
        return f"No data. {n['why']}"
    parts = ", ".join(f"{v} {k}" for k, v in n["counts"].items()) or "no rows"
    return (
        f"{parts} in the last {n['weeks']} weeks. A year before it ran "
        f"{n['year_before_per_window']} a window. Last week seen {n['last_week_seen']}"
    )


# The I/B/E/S line for the HTML card.
def ibes_text(i: dict) -> str:
    if i["status"] != "shown":
        return i["why"]
    return f"{i['consensus']:.2f} dated {i['date']} ({i['age_days']} days old). {i['note']}"


# One holding as an HTML card.
def card_html(c: dict) -> str:
    who = c["ticker"] or f"PERMNO {c['permno']}"
    name = html.escape(c["name"] or "")
    rows = [("Next print", print_text(c["next_print"]))]
    rows += [(LABELS[k], activity_text(t)) for k, t in c["activity"].items()]
    rows += [
        ("Benzinga", news_text(c["benzinga"])),
        ("Weather", c["weather"]["why"]),
        ("I/B/E/S", ibes_text(c["ibes"])),
        (
            "Read",
            f"{c['read']['direction']}, confidence {c['read']['confidence']}. {c['read']['why']}",
        ),
        (
            "Suggestion",
            f"{c['suggestion']['action']} at {c['suggestion']['shrink']}. {c['suggestion']['why']}",
        ),
    ]
    body = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows)
    head = (
        f"<h2>{c['rank']}. {html.escape(who)} <span>{name}</span></h2>"
        f"<p class=side>{c['side']}, {c['share_of_gross'] * 100:.2f}% of gross</p>"
    )
    return f"<section class=card>{head}<table>{body}</table></section>"


# The one-page HTML summary: coverage, cards, rules and credit.
def to_html(result: dict) -> str:
    m, cov = result["meta"], result["coverage"]
    lines = [
        f"{v['names']} of {cov['cards']} names with {PHRASES.get(k, k.replace('_', ' '))}"
        for k, v in cov.items()
        if k != "cards"
    ]
    style = (
        "body{font-family:system-ui,sans-serif;margin:24px;color:#1b1b1b;background:#fafafa}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}"
        ".card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px}"
        "h2{font-size:16px;margin:0}h2 span{font-weight:400;color:#666}"
        ".side{margin:2px 0 8px;color:#555;font-size:13px}"
        "table{border-collapse:collapse;font-size:12px}th{text-align:left;vertical-align:top;"
        "padding:3px 8px 3px 0;width:90px;color:#444}td{padding:3px 0}"
        "ul{font-size:13px}footer{margin-top:16px;font-size:12px;color:#555}"
    )
    cards = "".join(card_html(c) for c in result["cards"])
    whole = result.get("book_coverage")
    # The whole book's reach, so the top cards are not read as the book.
    if whole:
        reach = ", ".join(
            f"{v['names']} with {PHRASES.get(k, k.replace('_', ' '))}"
            for k, v in whole.items()
            if isinstance(v, dict)
        )
        lines.append(f"Across all {whole['names']} names in the book, {reach}")
    cover = "".join(f"<li>{html.escape(x)}</li>" for x in lines)
    rules = "".join(f"<li>{html.escape(x)}</li>" for x in m["rules"])
    return (
        "<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
        f"<title>X-ray {m['as_of']}</title><style>{style}</style></head><body>"
        f"<h1>Earnings preview X-ray</h1><p>{html.escape(m['book'])} as of {m['as_of']}, "
        f"the {m['top']} largest of {m['book_names']} holdings. {html.escape(m['acts_on'])}</p>"
        f"<ul>{cover}</ul><div class=grid>{cards}</div>"
        f"<footer><ul>{rules}</ul><p>{CREDIT}</p></footer></body></html>"
    )


# Writes the JSON, the HTML and one log line per suggestion.
def write(result: dict, folder: Path = OUT) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"xray_{result['meta']['as_of']}"
    paths = {"json": folder / f"{stem}.json", "html": folder / f"{stem}.html"}
    paths["json"].write_text(json.dumps(result, indent=1, default=str))
    paths["html"].write_text(to_html(result))
    paths["log"] = folder / "suggestions.jsonl"
    with paths["log"].open("a") as log:
        for c in result["cards"]:
            entry = {"run_at": result["meta"]["run_at"], "as_of": result["meta"]["as_of"],
                     "book": result["meta"]["book"], "book_sha256": result["meta"]["book_sha256"],
                     "permno": c["permno"], "ticker": c["ticker"], **c["suggestion"]}  # fmt: skip
            log.write(json.dumps(entry) + "\n")
    return paths


# uv run python -m fiam.alt.xray <positions.csv> <as_of> [--top 10]
def main(argv=None) -> int:
    ask = argparse.ArgumentParser(prog="fiam.alt.xray")
    ask.add_argument("positions", type=Path)
    ask.add_argument("as_of")
    ask.add_argument("--top", type=int, default=TOP)
    ask.add_argument("--label")
    ask.add_argument("--ibes", type=Path, help="optional last-consensus CSV (B20)")
    args = ask.parse_args(argv)
    result = run(args.positions, args.as_of, args.top, args.label, args.ibes)
    paths = write(result)
    print("book", json.dumps(result["book_coverage"]))
    print("cards", json.dumps(result["coverage"]))
    for c in result["cards"]:
        s = c["suggestion"]
        print(f"{c['rank']:>2} {c['permno']:>6} {str(c['ticker']):<6} {c['side']:<5} "
              f"print={c['next_print']['status']:<9} read={c['read']['direction']:<4} "
              f"news={c['benzinga'].get('total', 0):<3} {s['action']} {s['shrink']}")  # fmt: skip
    for kind, path in paths.items():
        print(kind, path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
