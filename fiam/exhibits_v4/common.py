# Shared inputs, style, labels and checks for the exhibits.

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, NullFormatter

from fiam.book import display_name
from fiam.report import charts
from fiam.v4 import daily_book
from fiam.v4.report import table_9_1

# The shared colours, sizes and look, never redefined here.
OURS, BENCH, MARKET, NEG = charts.OURS, charts.BENCH, charts.MARKET, charts.NEG
ALT, MUTED, INK, WIDE = charts.ALT, charts.MUTED, charts.INK, charts.WIDE
# Rule lines (limits and floors) in ink, thin and dashed.
RULE = dict(color=INK, linewidth=0.9, dashes=(5, 3), alpha=0.7)
# On-screen copy bans em and en dashes, colons and semicolons.
FORBIDDEN = re.compile("[—–:;]")
# A list of three or more with a comma before "and" or "or".
OXFORD = re.compile(r",[^,]*, (?:and|or)\b")
# PNG at the shared resolution and SVG beside it, for the deck.
DPI = 220
# A Bloomberg ticker's suffix, dropped from the "TICKER, Name" label.
SUFFIX = " US Equity"


# The final run's tables as the exhibits read them, windowed once.
@dataclass
class Inputs:
    d: pd.DataFrame
    base: float
    sp: pd.Series
    hurdle: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    ledger: pd.DataFrame
    events: pd.DataFrame
    compliance: pd.DataFrame | None
    caps: pd.DataFrame
    adv: pd.DataFrame
    ids: pd.DataFrame
    reasons: pd.DataFrame | None
    k1: pd.DataFrame | None
    rule_b: pd.DataFrame | None
    rules: dict
    arm: str
    notes_2026: list

    # The window's first and last counted sessions.
    @property
    def first(self) -> pd.Timestamp:
        return self.d.index[0]

    # The last counted session.
    @property
    def last(self) -> pd.Timestamp:
        return self.d.index[-1]

    # "Jan 2021 to Aug 2026", for every subtitle.
    @property
    def period(self) -> str:
        return f"{self.first:%b %Y} to {self.last:%b %Y}"

    # Sessions from the first trade day on, as rows 14-16 count them.
    @property
    def live(self) -> pd.DataFrame:
        traded = self.d.index[self.d["traded"].astype(bool)]
        return self.d[self.d.index >= traded.min()] if len(traded) else self.d

    # Holdings dates: every session with a trade, as row 20 reads them.
    @property
    def holding_days(self) -> pd.DatetimeIndex:
        days = pd.DatetimeIndex(stamps(self.trades["date"]).unique()).sort_values()
        days = days[(days >= self.first) & (days <= self.last)]
        if len(days):
            return days
        return pd.DatetimeIndex(self.positions["date"].unique()).sort_values()


# A date column as nanosecond timestamps, so every merge matches.
def stamps(x) -> pd.Series:
    return pd.to_datetime(pd.Series(x)).astype("datetime64[ns]")


# A frame with its dates typed, or None when not supplied.
def dated(frame) -> pd.DataFrame | None:
    if frame is None:
        return None
    frame = frame.reset_index() if "date" not in frame.columns else frame.copy()
    frame["date"] = stamps(frame["date"]).to_numpy()
    return frame


# A dated table's one value column renamed to `name`.
def valued(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    frame = dated(frame)
    if name not in frame.columns:
        other = [c for c in frame.columns if c not in ("date", "permno")]
        frame = frame.rename(columns={other[0]: name})
    return frame[["date", "permno", name]].astype({"permno": "int64"})


# The S&P 500's daily return as a dated series.
def series(bench) -> pd.Series:
    if isinstance(bench, pd.DataFrame):
        frame = dated(bench)
        value = [c for c in frame.columns if c != "date"][0]
        bench = frame.set_index("date")[value]
    bench = bench.copy()
    bench.index = pd.DatetimeIndex(stamps(bench.index))
    return bench.astype(float)


# The daily hurdle whose months compound to the table's bill + 4%.
def daily_hurdle(d: pd.DataFrame, premium: float) -> pd.Series:
    month = d.index.to_period("M")
    rf_m = (1 + d["rf"]).groupby(month).prod() - 1
    n = d["rf"].groupby(month).size()
    # Each session takes an equal share of the month's premium.
    k = ((1 + rf_m + premium / 12) / (1 + rf_m)) ** (1 / n)
    return (1 + d["rf"]) * month.map(k).to_numpy() - 1


# The window from meta: (start, end), else the run's own bounds.
def window(meta: dict) -> tuple:
    start, end = meta.get("window", (meta.get("start"), meta.get("end")))
    end = table_9_1.END if end is None else pd.Timestamp(end)
    return (None if start is None else pd.Timestamp(start)), end


# The tables windowed: the endowment row dropped, as the table does.
def prepare(tables: dict, meta: dict) -> Inputs:
    daily = tables["daily"]
    if "date" in daily.columns:
        daily = daily.set_index("date")
    daily = daily.copy()
    daily.index = pd.DatetimeIndex(stamps(daily.index))
    start, end = window(meta)
    full = daily.loc[:end]
    d = full.iloc[1:]
    if start is not None:
        d = d.loc[start:]
    if d.empty:
        raise ValueError("no session of the run falls in the window")
    # The NAV the first counted session starts from.
    base = float(full["nav"].loc[: d.index[0]].iloc[-2])
    sp = series(tables["bench"]).reindex(d.index)
    if sp.isna().any():
        raise ValueError("the S&P 500 series misses a day of the run")
    rules = meta.get("rules") or daily_book.mandate()
    inside = lambda f: f[(f["date"] >= d.index[0]) & (f["date"] <= d.index[-1])]  # noqa: E731
    events = tables.get("events")
    k1 = tables.get("k1", meta.get("k1"))
    return Inputs(
        d=d,
        base=base,
        sp=sp,
        hurdle=daily_hurdle(d, float(rules["benchmark_premium"])),
        positions=inside(dated(tables["positions"])),
        trades=inside(dated(tables["trades"])),
        ledger=inside(dated(tables["ledger"])),
        events=inside(dated(events)) if events is not None else pd.DataFrame(),
        compliance=dated(tables.get("compliance")),
        caps=valued(tables["caps"], "me"),
        adv=valued(tables["adv"], "adv"),
        ids=dated(tables["ids"]),
        reasons=tables.get("reasons"),
        k1=None if k1 is None else pd.DataFrame(k1),
        rule_b=tables.get("rule_b"),
        rules=rules,
        arm=str(meta.get("arm", meta.get("headline_arm", ""))),
        notes_2026=list(meta.get("notes_2026", [])),
    )


# Each row's latest value of a dated table at or before its date.
def as_of(frame: pd.DataFrame, source: pd.DataFrame, column: str, on: str = "date"):
    left = frame.assign(_key=stamps(frame[on]).to_numpy(), _row=np.arange(len(frame)))
    right = source[["date", "permno", column]].dropna().rename(columns={"date": "_key"})
    right = right.sort_values("_key")
    out = pd.merge_asof(left.sort_values("_key"), right, on="_key", by="permno")
    return out.sort_values("_row").drop(columns=["_key", "_row"]).reset_index(drop=True)


# Text from data made safe for the slide: no dashes, colons, semicolons.
def clean(text) -> str:
    text = re.sub("[—–]", "-", str(text))
    return re.sub(r"\s+", " ", re.sub("[:;]", " ", text)).strip()


# "TICKER, Full Company Name" for each name, as last held.
def labels(ids: pd.DataFrame, when: pd.DataFrame) -> pd.DataFrame:
    keep = ids[["date", "permno", "ticker", "name"]].astype({"permno": "int64"})
    keep = keep.sort_values("date", kind="stable")
    rows = []
    for permno, at in zip(when["permno"].astype("int64"), stamps(when["date"])):
        mine = keep[keep["permno"] == permno]
        if mine.empty:
            rows.append((permno, "", "", f"PERMNO {permno}", pd.NaT))
            continue
        # The label on that date, else the name's earliest one.
        before = mine[mine["date"] <= at]
        row = before.iloc[-1] if len(before) else mine.iloc[0]
        ticker = "" if pd.isna(row["ticker"]) else clean(str(row["ticker"]).removesuffix(SUFFIX))
        name = "" if pd.isna(row["name"]) else clean(display_name(row["name"]))
        rows.append((permno, ticker, name, f"{ticker or permno}, {name}", row["date"]))
    return pd.DataFrame(rows, columns=["permno", "ticker", "name", "label", "label_date"])


# Every string a figure draws: titles, labels, ticks, notes, tables.
def texts(fig) -> list[str]:
    return [t.get_text() for t in fig.findobj(mtext.Text) if t.get_text()]


# Refuses a figure with a dash, colon, semicolon or Oxford comma.
def check_text(fig) -> None:
    bad = [t for t in texts(fig) if FORBIDDEN.search(t) or OXFORD.search(t)]
    if bad:
        raise ValueError(f"forbidden punctuation in on-chart text: {bad}")


# One exhibit's PNG, SVG and the CSV of every number it shows.
def save(fig, frame: pd.DataFrame, out: Path, name: str) -> list[Path]:
    # A titled several-panel figure has laid itself out already.
    if not fig.get_suptitle():
        fig.tight_layout()
    # Drawn first, so tick labels exist when the text is checked.
    fig.canvas.draw()
    check_text(fig)
    paths = [out / f"{name}.png", out / f"{name}.svg", out / f"{name}.csv"]
    for path in paths[:2]:
        fig.savefig(path, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    frame.to_csv(paths[2], index=not isinstance(frame.index, pd.RangeIndex))
    return paths


# The shared look on one axis, with an optional grey subtitle.
def style(ax, title: str, ylabel: str = "", dates: bool = False, subtitle: str = "") -> None:
    charts.style(ax, title, ylabel, dates=dates, subtitle=subtitle)


# A smaller title for one panel of a several-panel exhibit.
def panel(ax, title: str, ylabel: str = "", dates: bool = False) -> None:
    charts.style(ax, title, ylabel, dates=dates)
    ax.title.set_fontsize(10.5)


# The bold title and grey subtitle; returns the panels' top edge.
def headline(fig, title: str, subtitle: str) -> float:
    h = fig.get_figheight()
    fig.suptitle(title, x=0.01, y=1 - 0.06 / h, ha="left", va="top", weight="bold", color=INK,
                 fontsize=12.5)  # fmt: skip
    fig.text(0.01, 1 - 0.34 / h, subtitle, fontsize=9.5, color=MUTED, va="top")
    return 1 - 0.55 / h


# Year ticks only inside the window, the first year included.
def years(ax, first: pd.Timestamp, last: pd.Timestamp) -> None:
    ax.set_xticks([pd.Timestamp(y, 1, 1) for y in range(first.year, last.year + 1)])
    ax.xaxis.set_major_formatter(charts.mdates.DateFormatter("%Y"))
    ax.set_xlim(left=pd.Timestamp(first.year, 1, 1))


# A number with no negative zero, so -0.00 reads 0.00.
def num(v: float, places: int = 2) -> str:
    text = f"{v:,.{places}f}"
    return text[1:] if text.startswith("-") and float(text.replace(",", "")) == 0 else text


# A note under the figure, wrapped, in the muted ink.
def footnote(fig, text: str) -> None:
    fig.text(0.01, -0.01, textwrap.fill(text, width=150), fontsize=8, color=MUTED, va="top")


# A label at a line's right end, in its colour.
def end_label(ax, line: pd.Series, text: str, colour: str) -> None:
    charts.end_label(ax, line, text, colour)


# Dollar millions as "$500m" or "$5bn" on a log axis.
def money_axis(ax, axis: str = "x") -> None:
    fmt = FuncFormatter(lambda v, _: f"${v / 1000:g}bn" if v >= 1000 else f"${v:g}m")
    target = ax.xaxis if axis == "x" else ax.yaxis
    target.set_major_formatter(fmt)
    target.set_minor_formatter(NullFormatter())


# Calendar-year compounding of a daily return series.
def by_year(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.year).prod() - 1


# A year the window covers only in part, from its first and last days.
def partial(days: pd.DatetimeIndex, year: int) -> bool:
    mine = days[days.year == year]
    starts = mine.min() <= pd.Timestamp(year, 1, 10)
    ends = mine.max() >= pd.Timestamp(year, 12, 24)
    return not (starts and ends)


# The daily return before trading and borrow costs, as row 9 adds back.
def before_costs(x: Inputs) -> pd.Series:
    prev = x.d["nav"].shift(1)
    prev.iloc[0] = x.base
    return x.d["ret"] + (x.d["cost"] + x.d["borrow"]) / prev


# A daily OLS beta of excess returns on the S&P 500's, no errors.
def beta(r: pd.Series, rf: pd.Series, sp: pd.Series) -> float:
    y, m = r - rf, sp - rf
    var = float(m.var())
    return float(y.cov(m) / var) if var > 0 else np.nan
