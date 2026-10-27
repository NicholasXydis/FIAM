# The live X-ray (piece 6) on synthetic data: clocks, reads, trims.

import gzip
import html
import json
import re

import pandas as pd
import pytest

from fiam.alt import xray
from fiam.v4.desk.agents import SHRINKS

DAY = pd.Timestamp
SEAL = DAY("2020-12-31")


# A monthly series: flat 100 a year back, then 103, then 110 lately.
def monthly(levels=(100.0, 103.0, 110.0), parts=("x",), late_part=False) -> xray.Series:
    months = pd.period_range("2025-04", "2026-09", freq="M")
    rows = []
    for i, m in enumerate(months):
        level = levels[0] if i < 12 else levels[1] if i < 15 else levels[2]
        for part in parts:
            rows.append({"ticker": "AAA", "part": part, "month": m, "value": level})
        # A part that appears only lately must not move the growth.
        if late_part and i >= 15:
            rows.append({"ticker": "AAA", "part": "new", "month": m, "value": 1e6})
    return xray.Series(pd.DataFrame(rows), 3, DAY("2026-10-18"), "2026-10-22")


# A stated lag reads from the catalogue's text in its usual forms.
def test_parse_lag():
    assert xray.parse_lag("T + 3 Days") == 3
    assert xray.parse_lag("T+1 Days") == 1
    with pytest.raises(ValueError):
        xray.parse_lag("weekly")


# A month counts only once complete and past its stated lag.
def test_public_months_respect_lag_and_partial():
    months = pd.period_range("2026-08", "2026-10", freq="M")
    got = xray.public_months(months, DAY("2026-10-02"), 3, DAY("2026-10-18"))
    assert list(got) == [True, False, False]
    got = xray.public_months(months, DAY("2026-10-03"), 3, DAY("2026-10-18"))
    assert list(got) == [True, True, False]


# Growth on a year back and its speed-up, from the last three months.
def test_trend_growth_and_vote():
    t = xray.trend(monthly(), "AAA", DAY("2026-10-26"))
    assert t["status"] == "ok"
    assert t["months"] == ["2026-07", "2026-08", "2026-09"]
    assert t["growth_recent"] == pytest.approx(0.10)
    assert t["growth_prior"] == pytest.approx(0.03)
    assert t["acceleration"] == pytest.approx(0.07)
    assert t["vote"] == "up"


# A part that is new in the window is dropped, not counted as growth.
def test_trend_ignores_parts_missing_in_any_month():
    t = xray.trend(monthly(parts=("a", "b"), late_part=True), "AAA", DAY("2026-10-26"))
    assert t["growth_recent"] == pytest.approx(0.10)


# A month not yet past its lag is left out, so the window moves back.
def test_trend_lag_moves_the_window():
    t = xray.trend(monthly(), "AAA", DAY("2026-10-02"))
    assert (t["status"], t["latest_month"]) == ("too short", "2026-08")


# No rows, or too few months, say so instead of reading anything.
def test_trend_no_data_and_too_short():
    s = monthly()
    assert xray.trend(s, "ZZZ", DAY("2026-10-26"))["status"] == "no data"
    assert xray.trend(s, None, DAY("2026-10-26"))["status"] == "no data"
    short = xray.Series(s.rows.tail(6), 3, DAY("2026-10-18"), "x")
    assert xray.trend(short, "AAA", DAY("2026-10-26"))["status"] == "too short"
    assert xray.trend(s, "AAA", DAY("2024-01-01"))["status"] == "no data"


# The vote has a flat band of two points either way.
def test_vote_band():
    assert xray.vote(0.03) == 1
    assert xray.vote(-0.03) == -1
    assert xray.vote(0.01) == 0


# One series or a split gives low confidence, never more than medium.
def test_read_confidence():
    ok = {"status": "ok"}
    assert xray.read({"card_spend": {"status": "no data"}})["confidence"] == "none"
    one = xray.read({"card_spend": {**ok, "vote": "down"}})
    assert (one["direction"], one["confidence"]) == ("down", "low")
    both = xray.read({"card_spend": {**ok, "vote": "up"}, "web_traffic": {**ok, "vote": "up"}})
    assert (both["direction"], both["confidence"]) == ("up", "medium")
    split = xray.read({"card_spend": {**ok, "vote": "down"}, "foot_traffic": {**ok, "vote": "up"}})
    assert (split["direction"], split["confidence"]) == ("down", "low")
    no_card = xray.read({"foot_traffic": {**ok, "vote": "up"}, "web_traffic": {**ok, "vote": "up"}})
    assert no_card["confidence"] == "low"


# Trims only into a near print, only against the side, from the set.
def test_suggest_is_shrink_only():
    down = {"card_spend": {"status": "ok", "vote": "down"}}
    near = {"status": "projected", "sessions_ahead": 3}
    far = {"status": "projected", "sessions_ahead": 12}
    low, medium = {"confidence": "low"}, {"confidence": "medium"}
    got = xray.suggest(0.01, down, low, near)
    assert (got["action"], got["shrink"], got["applied"]) == ("trim", 0.75, False)
    assert xray.suggest(0.01, down, medium, near)["shrink"] == 0.5
    assert xray.suggest(-0.01, down, low, near)["action"] == "keep"
    kept = xray.suggest(0.01, down, low, far)
    assert (kept["action"], kept["shrink"], kept["proposed"]) == ("keep", 1.0, 0.75)
    assert xray.suggest(0.01, down, low, {"status": "sealed"})["shrink"] == 1.0
    assert xray.suggest(0.01, {"card_spend": {"status": "no data"}}, low, near)["shrink"] == 1.0
    assert set(xray.TRIM.values()) <= set(SHRINKS)


# The next print is the earliest projection public by the as-of date.
def test_next_print_known_by_as_of():
    cal = pd.DataFrame(
        {
            "permno": [1, 1, 1, 2],
            "projected": pd.to_datetime(["2026-11-04", "2026-11-20", "2026-10-30", "2027-01-01"]),
            "basis": ["year_ago"] * 4,
            "known_from": [DAY("2025-11-05")] * 3 + [DAY("2026-01-02")],
            "first_close": pd.to_datetime(["2025-11-05", "2025-11-21", "2026-10-28", "2026-01-02"]),
        }
    )  # fmt: skip
    got = xray.next_print(cal, 1, DAY("2026-10-26"), DAY("2026-12-31"))
    assert got["date"] == "2026-11-04" and got["sessions_ahead"] == 7
    assert xray.next_print(cal, 3, DAY("2026-10-26"), SEAL, False)["status"] == "sealed"
    assert xray.next_print(cal, 3, DAY("2019-10-26"), SEAL, False)["status"] == "none known"
    # After the unseal nothing is hidden, so the word is never sealed.
    late = xray.next_print(cal, 3, DAY("2026-10-26"), SEAL, True)
    assert late["status"] == "none known" and "Sealed" not in late["why"]


# Coverage lines on the page read as plain words, never key names.
def test_html_coverage_lines_in_words():
    cards = xray.build_cards(
        pd.DataFrame({"permno": [1], "value": [3.0], "ticker": ["AAA"], "name": ["A Co"],
                      "ticker_source": ["book"]}),
        DAY("2026-10-26"), 1, inputs(),
    )  # fmt: skip
    meta = {"book": "b", "as_of": "2026-10-26", "top": 1, "book_names": 1, "acts_on": "Nothing",
            "rules": xray.RULES}  # fmt: skip
    whole = {"names": 1, "with_ticker": 1, "benzinga_ever": {"names": 1, "share_of_gross": 1.0}}
    page = xray.to_html({"meta": meta, "coverage": xray.coverage(cards), "cards": cards,
                         "book_coverage": whole})  # fmt: skip
    assert set(xray.PHRASES) >= set(xray.coverage(cards)) - {"cards"}
    for bad in ("with with", "benzinga any rows", "trim now", "with a read now", "_"):
        assert bad not in page.split("<div class=grid>")[0].split("</style>")[1]
    assert "1 of 1 names with a ticker" in page and "with any Benzinga rows" in page
    assert "with a trim proposed now" in page and "1 with Benzinga rows ever" in page


# News counts by type over 13 weeks; a week counts after its lag.
def test_news_counts_and_lag():
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"] * 5 + ["BBB"],
            "week": [DAY("2026-10-23"), DAY("2026-10-16"), DAY("2026-09-04"), DAY("2026-02-06"),
                     DAY("2025-12-05"), DAY("2026-10-16")],
            "type": ["offerings", "mergers", "mergers", "insider news", "offerings", "mergers"],
        }
    )  # fmt: skip
    got = xray.news(frame, "AAA", DAY("2026-10-23"), 1)
    assert got["counts"] == {"mergers": 2}
    assert got["year_before_per_window"] == pytest.approx(0.5)
    assert xray.news(frame, "AAA", DAY("2026-10-24"), 1)["counts"]["offerings"] == 1
    assert xray.news(frame, "ZZZ", DAY("2026-10-24"), 1)["status"] == "no data"


# The consensus shows only with its date and only if given.
def test_consensus_shown_with_date():
    assert xray.consensus(None, 1, DAY("2026-10-26"))["status"] == "not given"
    ibes = pd.DataFrame(
        {
            "permno": [1, 1],
            "consensus": [1.2, 1.3],
            "statpers": [DAY("2025-11-20"), DAY("2025-12-18")],
        }
    )
    got = xray.consensus(ibes, 1, DAY("2026-10-26"))
    assert (got["consensus"], got["date"], got["age_days"]) == (1.3, "2025-12-18", 312)
    assert xray.consensus(ibes, 1, DAY("2025-12-01"))["consensus"] == 1.2


# A dated book uses its latest date by the as-of; weights stand in.
def test_load_book_and_largest(tmp_path):
    path = tmp_path / "book.csv"
    pd.DataFrame(
        {"date": ["2026-08-31"] * 3 + ["2026-11-30"], "permno": [1, 2, 3, 1],
         "value": [5.0, -9.0, 0.0, 99.0]}
    ).to_csv(path, index=False)  # fmt: skip
    book = xray.load_book(path, DAY("2026-10-26"))
    assert list(book["permno"]) == [1, 2]
    assert list(xray.largest(book, 1)["permno"]) == [2]
    path2 = tmp_path / "w.csv"
    pd.DataFrame({"permno": [7], "ticker": ["AAA"], "weight": [0.01]}).to_csv(path2, index=False)
    assert xray.load_book(path2, DAY("2026-10-26"))["ticker"].iat[0] == "AAA"


# A sealed registry leaves a missing ticker empty, never guessed.
def test_fill_tickers_sealed():
    book = pd.DataFrame({"permno": [1, 2], "value": [1.0, -1.0], "ticker": ["AAA", None]})
    got = xray.fill_tickers(book, DAY("2026-10-26"), SEAL, unsealed=False)
    assert list(got["ticker"]) == ["AAA", None]
    assert list(got["ticker_source"]) == ["book", "none"]


# Synthetic inputs for a two-name book, WMT-like coverage on one name.
def inputs() -> xray.Inputs:
    series = {k: monthly() for k in xray.SERIES}
    series["card_spend"] = monthly(levels=(100.0, 108.0, 101.0))
    news = pd.DataFrame({"ticker": ["BBB"], "week": [DAY("2026-10-16")], "type": ["offerings"]})
    cal = pd.DataFrame(
        {"permno": [1], "projected": [DAY("2026-10-29")], "basis": ["year_ago"],
         "known_from": [DAY("2025-10-30")], "first_close": [DAY("2025-10-30")]}
    )  # fmt: skip
    return xray.Inputs(series, news, 1, "x", cal, SEAL, opened=False)


# End to end: a covered long trims into its print, the rest say no data.
def test_build_cards_end_to_end(tmp_path):
    book = pd.DataFrame(
        {"permno": [1, 2, 3], "value": [3.0, -2.0, 1.0], "ticker": ["AAA", "BBB", None],
         "name": ["A Co", None, None], "ticker_source": ["book", "book", "none"]}
    )  # fmt: skip
    cards = xray.build_cards(book, DAY("2026-10-26"), 3, inputs())
    a, b, c = cards
    assert a["activity"]["card_spend"]["vote"] == "down"
    assert a["read"]["confidence"] == "low"
    assert (a["suggestion"]["action"], a["suggestion"]["shrink"]) == ("trim", 0.75)
    assert b["read"]["direction"] == "none" and b["benzinga"]["total"] == 1
    assert c["ticker"] is None and "sealed" in c["ticker_note"]
    assert all(x["suggestion"]["shrink"] in SHRINKS for x in cards)
    assert all(x["weather"]["status"] == "skipped" for x in cards)
    cov = xray.coverage(cards)
    assert cov["card_spend"]["names"] == 1 and cov["trim_now"]["share_of_gross"] == 0.5
    # No raw level ever leaves the tool, only growth rates.
    text = json.dumps(cards)
    assert not any(f"{v}" in text for v in (110.0, 108.0, 103.0, 101.0))


# The files written: JSON, HTML with clean copy, and the suggestion log.
def test_write_files_and_clean_copy(tmp_path):
    book = pd.DataFrame(
        {
            "permno": [1],
            "value": [3.0],
            "ticker": ["AAA"],
            "name": ["A Co"],
            "ticker_source": ["book"],
        }
    )
    cards = xray.build_cards(book, DAY("2026-10-26"), 1, inputs())
    meta = {"book": "test book", "as_of": "2026-10-26", "top": 1, "book_names": 1,
            "acts_on": "Nothing", "rules": xray.RULES, "run_at": "t",
            "book_sha256": "s"}  # fmt: skip
    paths = xray.write({"meta": meta, "coverage": xray.coverage(cards), "cards": cards}, tmp_path)
    assert json.loads(paths["json"].read_text())["cards"][0]["permno"] == 1
    page = paths["html"].read_text()
    assert xray.CREDIT in page
    copy = html.unescape(re.sub(r"<style>.*?</style>|<[^>]+>", " ", page, flags=re.S))
    assert not re.search("[:;–—]", copy)
    assert len(paths["log"].read_text().splitlines()) == 1


# A saved pull and its catalogue page load with the stated lag.
def test_load_series_from_snapshot(tmp_path):
    snap, cat = tmp_path / "snap", tmp_path / "cat"
    snap.mkdir()
    (cat / "CA0056").mkdir(parents=True)
    (cat / "CA0056" / "information.json").write_text(json.dumps({"data": {"Lag": "T + 3 Days"}}))
    rows = [{"entity_id": 1, "entity_name": "AAA", "transaction_method": m, "date": d,
             "credit_card_spend": v} for d in ("2026-09-30", "2026-10-31")
            for m, v in (("Online", "1.5"), ("Physical", 2.0))]  # fmt: skip
    raw = {"insight_column": "credit_card_spend", "data": rows}
    with gzip.open(snap / "CA0056_626_AAA.json.gz", "wt") as fh:
        json.dump(raw, fh)
    receipt = {"pulled_at": "2026-10-22", "metadata": {"table_max_date": "2026-10-18 00:00:00"}}
    (snap / "CA0056_626_AAA.receipt.json").write_text(json.dumps(receipt))
    s = xray.load_series("CA0056", snap, cat)
    assert s.lag == 3 and s.table_max == DAY("2026-10-18")
    assert len(s.rows) == 4 and s.rows["value"].sum() == pytest.approx(7.0)
    assert set(s.rows["part"]) == {"Online", "Physical"}


# Once unsealed, a missing ticker comes from the link at the seal.
def test_fill_tickers_unsealed(monkeypatch):
    links = pd.DataFrame(
        {"permno": [2, 2], "kind": ["ticker", "ticker"], "value": ["OLD", "NEW"],
         "valid_from": pd.to_datetime(["2010-01-01", "2026-09-15"]),
         "valid_to": pd.to_datetime(["2026-09-14", None])}
    )  # fmt: skip
    monkeypatch.setattr(xray.data, "table", lambda *a, **k: links)
    book = pd.DataFrame({"permno": [1, 2], "value": [1.0, -1.0], "ticker": ["AAA", None]})
    got = xray.fill_tickers(book, DAY("2026-10-26"), DAY("2026-08-31"), unsealed=True)
    assert list(got["ticker"]) == ["AAA", "OLD"]
    assert "2026-08-31" in got["ticker_source"].iat[1]


# An old latest month is stale and casts no vote; a later pull is noted.
def test_trend_stale_and_vintage():
    t = xray.trend(monthly(), "AAA", DAY("2027-03-15"))
    assert (t["status"], t["latest_month"]) == ("stale", "2026-09")
    assert xray.read({"card_spend": t})["direction"] == "none"
    early = xray.trend(monthly(), "AAA", DAY("2026-10-20"))
    assert early["status"] == "ok" and "2026-10-22" in early["vintage"]
    assert "vintage" not in xray.trend(monthly(), "AAA", DAY("2026-10-26"))
