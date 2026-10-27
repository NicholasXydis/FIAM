# Rehearsal 1's synthetic world on a fake calendar and a sealed reader.

import re
import subprocess

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import clock, daily_book, data
from fiam.v4.construct import rehearsal

DAY = pd.Timestamp
ROOT = rehearsal.gates.ROOT


# Weekdays 2016-12 to 2026-09, Dec 24 and 25 2020 off, as sessions.
@pytest.fixture
def cal(monkeypatch):
    days = pd.bdate_range("2016-12-01", "2026-09-30")
    days = days[~days.isin([DAY("2020-12-24"), DAY("2020-12-25")])]
    fake = pd.Series(days.tz_localize("UTC") + pd.Timedelta(hours=21), index=days)
    monkeypatch.setattr(data, "calendar", lambda: fake)
    return days


# A registry stand-in: rows to the seal, filtered like the real one.
def sealed(frames: dict):
    # One read: the table's rows to 2020, by set or inclusive range.
    def read(name, columns=None, purpose=None, where=None):
        f = frames[name].copy()
        for k, v in (where or {}).items():
            if isinstance(v, (set, frozenset, list)):
                f = f[f[k].isin(pd.to_datetime(list(v)) if k != "permno" else list(v))]
            else:
                f = f[f[k].between(pd.Timestamp(v[0]), pd.Timestamp(v[1]))]
        return f.reset_index(drop=True)

    return read


# The same seed gives the same blocks; sources stay in the window.
def test_months_are_seeded_blocks():
    a, b = rehearsal.months(), rehearsal.months()
    assert a == b and len(a) == 68
    src = list(data.month_ends(*rehearsal.SOURCE))
    assert set(a.values()) <= set(src)
    steps = [src.index(y) - src.index(x) for x, y in zip(list(a.values()), list(a.values())[1:])]
    jumps = sum(1 for s in steps if s not in (1, 1 - len(src)))
    assert 3 <= jumps <= 30
    assert rehearsal.months(1) != a


# Session k of a target month is session k of its source holding month.
def test_sessions_map_in_order_and_wrap(cal):
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31"),
                         DAY("2021-03-31"): DAY("2020-11-30")})  # fmt: skip
    jan = w.days[w.days["month"] == DAY("2021-01-31")]
    feb17 = data.sessions("2017-02-01", "2017-02-28")
    assert list(jan["source"][: len(feb17)]) == list(feb17)
    # January 2021 is longer, so it runs on into March 2017.
    assert jan["source"].iloc[len(feb17)] == DAY("2017-03-01")
    mar = w.days[w.days["month"] == DAY("2021-03-31")]
    dec20 = data.sessions("2020-12-01", "2020-12-31")
    assert len(mar) > len(dec20)
    # Past 2020 it wraps to the window's first session, never to 2021.
    assert mar["source"].iloc[len(dec20)] == DAY("2017-02-01")
    assert w.days["source"].max() <= rehearsal.SEAL
    assert w.formation == {DAY("2020-12-31"): DAY("2017-01-31"),
                           DAY("2021-02-28"): DAY("2020-11-30")}  # fmt: skip


# Relabelled rows keep their clock lag; nothing real after 2020 is read.
def test_daily_rows_keep_clocks(cal):
    src = data.sessions("2017-02-01", "2017-03-31")
    dsf = pd.DataFrame({"permno": 7, "date": src, "ret": np.arange(len(src)) / 100})
    dsf["first_close"] = data.shift(dsf["date"], 1).to_numpy()
    dsf["available_at"] = dsf["date"].dt.tz_localize("UTC") + pd.Timedelta(hours=22)
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31")})
    seen = []
    real = sealed({"dsf": dsf})
    w.real = lambda *a: seen.append(a[3]) or real(*a)
    week = (DAY("2021-01-04"), DAY("2021-01-08"))
    got = w.rows("dsf", ["ret"], None, {"permno": {7}, "date": week})
    assert list(got["date"]) == list(data.sessions("2021-01-04", "2021-01-08"))
    # The fake January 2021 starts on Friday the 1st, session 0.
    assert list(got["ret"]) == pytest.approx([0.01, 0.02, 0.03, 0.04, 0.05])
    assert list(got["first_close"]) == list(data.shift(got["date"], 1))
    # available_at keeps its gap to its own first close, as at the source.
    src = w.days.set_index("target")["source"].loc[got["date"]]
    old = dsf.set_index("date")
    want = (old["available_at"].dt.tz_convert(None) - old["first_close"]).loc[src].to_numpy()
    assert ((got["available_at"].dt.tz_convert(None) - got["first_close"]).to_numpy() == want).all()
    assert all(pd.Timestamp(x["date"][1]) <= rehearsal.SEAL for x in seen)


# A table's own "source" column (the exits table has one) is kept.
def test_daily_rows_keep_a_source_column(cal):
    src = data.sessions("2017-02-01", "2017-02-28")
    dsf = pd.DataFrame({"permno": 7, "date": src, "source": "crsp"})
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31")})
    w.real = sealed({"dsf": dsf})
    got = w.rows("dsf", ["source"], None, {"date": (DAY("2021-01-04"), DAY("2021-01-08"))})
    assert len(got) == 5 and set(got["source"]) == {"crsp"}
    assert not {"_s", "_t", "_src"} & set(got.columns)


# The reader adds synthetic rows only past the seal, and lets go after.
def test_reader_swaps_in_and_out(cal, monkeypatch):
    feb = data.sessions("2017-02-01", "2017-02-28")
    src = data.sessions("2020-12-28", "2020-12-31").append(feb)
    dsf = pd.DataFrame({"permno": 7, "date": src, "ret": 0.01})
    dsf["first_close"], dsf["available_at"] = dsf["date"], dsf["date"].dt.tz_localize("UTC")
    monkeypatch.setattr(data, "table", sealed({"dsf": dsf}))
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31")})
    real = data.table
    with rehearsal.active(w):
        assert data.table.synthetic
        before = data.table("dsf", ["ret"], where={"date": (DAY("2017-02-01"), DAY("2017-02-28"))})
        both = data.table("dsf", ["ret"], where={"date": (DAY("2020-12-28"), DAY("2021-01-08"))})
    assert data.table is real
    assert len(before) == len(data.sessions("2017-02-01", "2017-02-28"))
    assert list(both["date"]) == list(data.sessions("2020-12-28", "2021-01-08"))


# A held name gone from the next source month exits at its last price.
def test_forced_exits(cal):
    feb, mar = data.sessions("2017-02-01", "2017-02-28"), data.sessions("2017-03-01", "2017-03-31")
    rows = [(1, d) for d in feb] + [(2, d) for d in feb.append(mar)]
    rows += [(1, DAY("2020-12-31")), (2, DAY("2020-12-31"))]
    dsf = pd.DataFrame(rows, columns=["permno", "date"]).assign(ret=0.0)
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31"),
                         DAY("2021-02-28"): DAY("2017-02-28")})  # fmt: skip
    w.real = sealed({"dsf": dsf})
    first_feb = data.sessions("2021-02-01", "2021-02-05")[0]
    assert w.forced()[first_feb] == {1}
    exits = w.forced_rows()
    row = exits[exits["permno"] == 1].iloc[0]
    assert row["exit_date"] == first_feb and row["delret"] == 0.0
    assert row["first_close"] == first_feb


# The panel at a decision close is its next source formation's rows.
def test_panel_rows_follow_the_decision_close(cal):
    eoms = [DAY("2017-01-31"), DAY("2017-02-28"), DAY("2017-03-31"), DAY("2017-04-30")]
    panel = pd.DataFrame([(p, e, 100.0 * (i + 1), 0.01 * (i + 1)) for i, e in enumerate(eoms)
                          for p in (1, 2)], columns=["permno", "eom", "me", "ret"])  # fmt: skip
    panel["first_close"] = data.eom_session(panel["eom"]).to_numpy()
    w = rehearsal.World({DAY("2021-01-31"): DAY("2017-01-31"),
                         DAY("2021-02-28"): DAY("2017-03-31")})  # fmt: skip
    days = data.sessions("2017-02-01", "2017-04-28")
    crsp = pd.DataFrame({"permno": 1, "date": days, "ret": 0.001, "delflg": "N"})
    w.real = sealed({"panel": panel, "crsp_daily": crsp})
    got = w.rows("panel", ["me", "ret"], None, None).set_index(["eom", "permno"])
    # The close of 2021-01 decides 2021-02 on source 2017-03's caps.
    assert got.loc[(DAY("2021-01-31"), 1), "me"] == 300.0
    assert got.loc[(DAY("2020-12-31"), 1), "me"] == 100.0
    # January 2021 ran on February 2017 and March 1st: those returns.
    jan = len(data.sessions("2021-01-01", "2021-01-31"))
    assert got.loc[(DAY("2021-01-31"), 1), "ret"] == pytest.approx(1.001**jan - 1)
    assert np.isnan(got.loc[(DAY("2021-01-31"), 2), "ret"])
    # February 2021 ran on April 2017 exactly: that month's own return.
    assert got.loc[(DAY("2021-02-28"), 1), "ret"] == pytest.approx(0.04)
    assert (
        got.loc[(DAY("2021-01-31"), 1), "first_close"]
        == data.eom_session([DAY("2021-01-31")]).iloc[0]
    )


# The engine refuses a synthetic run without the rehearsal's reader.
def test_engine_needs_the_reader():
    with pytest.raises(clock.SealedWindow):
        daily_book.run({}, "2020-12-31", "2026-08-31", synthetic=True)
    with pytest.raises(clock.SealedWindow):
        daily_book.run({}, "2020-12-31", "2026-08-31")


# No tracked file carries a rehearsal's synthetic hash.
def test_no_tracked_file_is_synthetic():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()  # fmt: skip
    mark = re.compile(re.escape(rehearsal.MARK) + ":[0-9a-f]{64}")
    for name in files:
        path = ROOT / name
        if path.suffix in (".json", ".csv", ".md", ".py", ".txt") and path.exists():
            assert not mark.search(path.read_text(errors="ignore")), name
