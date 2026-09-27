# Mechanics tests on small synthetic data. No organizer data, no WRDS, no network needed.

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pipeline as P

SRC = Path(__file__).resolve().parents[1] / "src"


# Three names held last month, one of which has no return this month.
@pytest.fixture
def held():
    weights = pd.Series([0.02, -0.01, -0.01], index=[1, 2, 3])
    info = pd.DataFrame(dict(ret_exc_lead1m=[0.10, -0.05, np.nan]), index=[1, 2, 3])
    return weights, info


def test_drift_is_unchanged_by_a_flat_month(held):
    weights, _ = held
    flat = pd.DataFrame(dict(ret_exc_lead1m=[0.0, 0.0, 0.0]), index=weights.index)
    costs = dict(cost_commission=0.0)
    pd.testing.assert_series_equal(P.drift(weights, flat, costs, 0.0), weights)


def test_drift_grows_winners_and_holds_an_exit_as_cash(held):
    weights, info = held
    drifted = P.drift(weights, info, dict(cost_commission=0.0), 0.0)
    nav = 1 + 0.02 * 0.10 + 0.01 * 0.05
    assert drifted[1] == pytest.approx(0.02 * 1.10 / nav)
    assert drifted[2] == pytest.approx(-0.01 * 0.95 / nav)
    assert drifted[3] == pytest.approx(-0.01 / nav)


def test_drift_of_an_empty_book_is_nothing():
    assert P.drift(pd.Series(dtype=float), pd.DataFrame(), {}, 0.0) is None


def test_costs_reconcile_and_an_exit_counts_as_a_trade(held):
    weights, _ = held
    today = pd.Series([0.02, -0.02], index=[1, 4])
    info = pd.DataFrame(dict(htb=[False, True]), index=[1, 4])
    spreads = pd.Series([0.01, 0.02], index=[1, 4])
    parts, turnover = P.trading_cost(today, weights, info, spreads, pd.Series(0.01, [1, 2, 3]))
    assert set(parts) == {
        "cost_commission",
        "cost_spread",
        "cost_borrow_gc",
        "cost_borrow_htb",
        "cost_impact",
    }
    # Name 1 unchanged, names 2 and 3 sold out, name 4 opened: 0.04 traded, one way 0.02.
    assert turnover == pytest.approx(0.02)
    assert parts["cost_commission"] == pytest.approx(0.04 * 5 / 1e4)
    assert parts["cost_borrow_htb"] == pytest.approx(0.02 * 250 / 1e4 / 12)


def test_first_month_is_a_full_entry():
    today = pd.Series([0.01, -0.01], index=[1, 2])
    info = pd.DataFrame(dict(htb=[False, False]), index=[1, 2])
    _, turnover = P.trading_cost(today, None, info, pd.Series(0.0, [1, 2]), None)
    assert turnover == pytest.approx(0.01)


# Truncation can leave net exposure, and the repair adds shares back, so one share is the bound.
def test_whole_shares_land_within_one_share_and_near_neutral():
    weights = pd.Series([0.015, 0.012, -0.013, -0.014], index=list("abcd"))
    prices = pd.Series([123.4, 87.1, 250.0, 33.3], index=list("abcd"))
    held = P.to_whole_shares(weights, prices)
    assert ((held - weights).abs() <= prices / P.NAV + 1e-12).all()
    assert (np.sign(held) == np.sign(weights)).all()
    assert abs(held.sum()) < 1e-4


# A tiny panel and exits table: one name gone before the decision, one leaving next month.
def test_settle_screens_dead_names_and_books_payouts(monkeypatch):
    eom = pd.Timestamp("2024-03-31")
    panel = pd.DataFrame(
        dict(permno=[1, 2, 3], eom=[eom] * 3, ret_exc_lead1m=[0.01, np.nan, np.nan])
    )
    exits = pd.DataFrame(
        dict(
            exit_date=pd.to_datetime(["2024-03-15", "2024-04-10"]),
            final_month=pd.to_datetime(["2024-03-01", "2024-04-01"]),
            final_return=[0.02, 0.05],
            source=["CRSP delisting MER CASH"] * 2,
        ),
        index=pd.Index([2, 3], name="permno"),
    )
    cash = pd.DataFrame(dict(month=[pd.Timestamp("2024-04-01")], rf=[0.004]))
    monkeypatch.setattr(P, "exits", lambda: exits)
    monkeypatch.setattr(P, "benchmarks", lambda: cash)
    settled = P.settle(panel).set_index("permno")["ret_exc_lead1m"]
    assert list(settled.index) == [1, 3]
    assert settled[1] == pytest.approx(0.01)
    assert settled[3] == pytest.approx(0.05 - 0.004)


def test_settle_changes_nothing_without_wrds(monkeypatch):
    panel = pd.DataFrame(
        dict(permno=[1], eom=[pd.Timestamp("2024-03-31")], ret_exc_lead1m=[np.nan])
    )
    monkeypatch.setattr(P, "exits", lambda: None)
    pd.testing.assert_frame_equal(P.settle(panel), panel)


def test_missing_returns_are_booked_at_zero_and_recorded():
    weights = pd.Series([0.01, -0.01], index=[1, 2])
    info = pd.DataFrame(
        dict(
            ret_exc_lead1m=[0.05, np.nan],
            beta_60m=[1.0, 1.0],
            sector=["10", "10"],
            htb=[False, False],
        ),
        index=[1, 2],
    )
    record = P.month_record(
        pd.Timestamp("2024-03-31"), weights, info, pd.DataFrame(dict(n_signals=[12])), {}, 0.0
    )
    assert record["gross"] == pytest.approx(0.0005)
    assert record["missing_short_weight"] == pytest.approx(0.01)
    assert record["missing_long_weight"] == 0


# Importing any module must not run it or write anything, so a bundler can pull in just the code.
def test_every_module_imports_without_side_effects(tmp_path):
    names = [p.stem for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]
    folders = sorted({str(p.parent) for p in SRC.rglob("*.py")})
    script = f"import sys; sys.path[:0] = {folders!r}\nfor n in {names!r}: __import__(n)"
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True, timeout=300)
    assert not any(tmp_path.iterdir()), "an import wrote a file"


def test_benchmarks_refuse_to_download_on_their_own(tmp_path, monkeypatch):
    benchmarks = importlib.import_module("benchmarks")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="--refresh"):
        benchmarks.pinned("SP500.csv")


# The label rules: a cut-short panel name matches, a typo or a renamed company does not.
def test_label_names_allow_abbreviation_but_not_a_different_name():
    sys.path.insert(0, str(SRC / "exhibits"))
    labels = importlib.import_module("labels")
    assert labels.same_name("KULICKE & SOFFA INDS INC", "Kulicke & Soffa Industries, Inc.")
    assert labels.same_name("CLEARWATER ANALYTICS HLDGS INC", "Clearwater Analytics Holdings")
    assert not labels.same_name("H20 AMERICA", "H2O AMERICA")
    assert not labels.same_name("CONTANGO ORE INC", "Contango Silver & Gold Inc.")


# CRSP keeps the share class apart, so BFB is BF class B, but BFXY is a different security.
def test_crsp_share_class_letter_is_accepted_once():
    labels = importlib.import_module("labels")
    row = dict(eom=pd.Timestamp("2023-03-31"), crsp_ticker="BF", crsp_name="BROWN FORMAN CORP")
    assert (
        labels.verdict({**row, "TICKER": "BFB", "COMPANY NAME": "BROWN FORMAN CORP"})
        == "CRSP, dated"
    )
    wrong = labels.verdict({**row, "TICKER": "BFXY", "COMPANY NAME": "BROWN FORMAN CORP"})
    assert wrong == "differs from CRSP on ticker"


def test_saved_numbers_keep_booleans():
    assert P.round_floats(dict(passed=True, share=0.1234567)) == dict(passed=True, share=0.123457)


# The live score: cash on capital, the entry cost, and a missing name at zero with its stress.
def test_live_score_books_cash_cost_and_missing_names(monkeypatch):
    sys.path.insert(0, str(SRC / "exhibits"))
    live = importlib.import_module("live_score")
    monkeypatch.setattr(live, "market", lambda month: dict(rf=0.003, sp500=0.01))
    weights = pd.Series([0.5, 0.5, -1.0], index=[1, 2, 3])
    result = live.score(weights, pd.Series([0.04, np.nan, 0.01], index=[1, 2, 3]), 0.001, "2026-09")
    assert result["gross"] == pytest.approx(0.5 * 0.04 - 0.01)
    assert result["total_return"] == pytest.approx(0.003 + 0.01 - 0.001)
    assert result["active_return"] == pytest.approx(0.01 - 0.001 - 0.04 / 12)
    assert result["missing_long_weight"] == pytest.approx(0.5)
    assert result["total_if_missing_longs_lose_30pct"] == pytest.approx(0.012 - 0.15)


# Daily closes become month-end to month-end returns, keyed on the holding month.
def test_live_score_monthly_returns_from_daily_closes(tmp_path, monkeypatch):
    live = importlib.import_module("live_score")
    monkeypatch.setattr(live, "PRICES", tmp_path)
    rows = [dict(date="2026-08-31", adjClose=100.0), dict(date="2026-09-15", adjClose=104.0)]
    rows.append(dict(date="2026-09-30", adjClose=110.0))
    (tmp_path / "ABC.json").write_text(json.dumps(dict(ticker="ABC", end="2026-10-01", rows=rows)))
    table, digest = live.monthly(pd.DataFrame(dict(PERMNO=[7], TICKER=["ABC"])))
    assert table.loc["2026-09", 7] == pytest.approx(0.10)
    assert len(digest) == 64


# Display names lose only SEC's state tag, so AT&T keeps its ampersand and nothing is renamed.
def test_display_name_drops_only_the_state_tag():
    assert P.display_name("APPLIED MATERIALS INC /DE") == "APPLIED MATERIALS INC"
    assert (
        P.display_name("SHENANDOAH TELECOMMUNICATIONS CO/VA/") == "SHENANDOAH TELECOMMUNICATIONS CO"
    )
    assert P.display_name("AT&T INC") == "AT&T INC"


# The same rows with LF or CRLF endings are the same file; a binary file must match byte for byte.
def test_hashes_ignore_line_endings_for_text_only(tmp_path):
    paths = importlib.import_module("paths")
    lf, crlf = tmp_path / "a.csv", tmp_path / "b.csv"
    lf.write_bytes(b"x,y\n1,2\n")
    crlf.write_bytes(b"x,y\r\n1,2\r\n")
    digest = next(iter(paths.digests(lf.read_bytes())))
    assert paths.matches(crlf, digest) and paths.matches(lf, digest)
    blob = tmp_path / "c.zip"
    blob.write_bytes(b"x,y\r\n")
    assert not paths.matches(blob, hashlib.sha256(b"x,y\n").hexdigest())
    assert not paths.matches(tmp_path / "missing.csv", digest)


# A book inside every limit passes; one name short or 60% net fails exactly that rule.
def test_submission_rules_catch_each_breach():
    verify = importlib.import_module("verify")
    months = pd.date_range("2021-01-01", "2026-08-01", freq="MS")

    # Longs and shorts as % of NAV: 95/95 is neutral, 125/65 is 60% net inside 190% gross.
    def book(names: int, long: float = 95, short: float = 95) -> pd.DataFrame:
        half = names // 2
        weight = np.r_[np.full(half, long / half), np.full(names - half, -short / (names - half))]
        rows = [(m, p, "T", "N", w) for m in months for p, w in enumerate(weight)]
        return pd.DataFrame(rows, columns=verify.COLUMNS)

    returns = pd.DataFrame(dict(holding_month=months.strftime("%Y-%m-%d")))
    failed = lambda frame: {n for n, ok, _ in verify.rules(frame, returns) if not ok}  # noqa: E731
    assert failed(book(200)) == set()
    assert failed(book(99)) == {"positions 100-500"}
    assert failed(book(200, long=125, short=65)) == {"net inside +/-50%"}
    assert failed(book(200, long=105, short=105)) == {"gross at most 200%"}
    short = book(200)
    short = short[short["Date"] < "2026-08-01"]
    assert failed(short) == {"months", "returns cover the same months"}
    assert failed(book(200).iloc[:0]) == {"holdings.csv has rows"}


# The comparison reads results, not run details such as the date or commit.
def test_comparison_ignores_run_details(tmp_path):
    compare = importlib.import_module("compare")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(dict(run=dict(git_commit="x"), ir=0.8341, n=[1, 2])))
    b.write_text(json.dumps(dict(run=dict(git_commit="y"), ir=0.8341, n=[1, 2])))
    assert compare.difference(a, b) == (0.0, "ir")
    b.write_text(json.dumps(dict(run=dict(git_commit="y"), ir=0.8326, n=[1, 2])))
    gap, key = compare.difference(a, b)
    assert key == "ir" and compare.verdict(gap) == "differs"


# --import copies the organizer's files by name and leaves everything else, a CV say, alone.
def test_import_takes_only_organizer_files(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("run", SRC.parent / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "factor_char_list.csv").write_text("variable\nbe_me\n")
    (downloads / "Someone_CV.pdf").write_bytes(b"%PDF")
    (downloads / "notes.csv").write_text("a,b\n1,2\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(SRC))
    run.import_from(downloads)
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["factor_char_list.csv"]


# A number on one side and nothing on the other is a difference, never a match.
def test_comparison_counts_a_value_missing_on_one_side(tmp_path):
    compare = importlib.import_module("compare")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(dict(ir=float("nan"))))
    b.write_text(json.dumps(dict(ir=0.83)))
    assert compare.verdict(compare.difference(a, b)[0]) == "differs"
    b.write_text(json.dumps(dict(ir=float("nan"))))
    assert compare.verdict(compare.difference(a, b)[0]) == "identical"
