# Mechanics tests on small synthetic data, with no real data or network.

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiam import book as P
from fiam import costs as C

ROOT = Path(__file__).resolve().parents[1]


# Three names held last month, one of which has no return this month.
@pytest.fixture
def held():
    weights = pd.Series([0.02, -0.01, -0.01], index=[1, 2, 3])
    info = pd.DataFrame(dict(ret_exc_lead1m=[0.10, -0.05, np.nan]), index=[1, 2, 3])
    return weights, info


# A month of zero returns leaves the weights as they were.
def test_drift_is_unchanged_by_a_flat_month(held):
    weights, _ = held
    flat = pd.DataFrame(dict(ret_exc_lead1m=[0.0, 0.0, 0.0]), index=weights.index)
    costs = dict(cost_commission=0.0)
    pd.testing.assert_series_equal(P.drift(weights, flat, costs, 0.0), weights)


# Winners grow, and a name with no return sits as cash.
def test_drift_grows_winners_and_holds_an_exit_as_cash(held):
    weights, info = held
    drifted = P.drift(weights, info, dict(cost_commission=0.0), 0.0)
    nav = 1 + 0.02 * 0.10 + 0.01 * 0.05
    assert drifted[1] == pytest.approx(0.02 * 1.10 / nav)
    assert drifted[2] == pytest.approx(-0.01 * 0.95 / nav)
    assert drifted[3] == pytest.approx(-0.01 / nav)


# An empty book carries nothing into next month.
def test_drift_of_an_empty_book_is_nothing():
    assert P.drift(pd.Series(dtype=float), pd.DataFrame(), {}, 0.0) is None


# One month's cost-model quotes, a known spread ratio per size group.
def quotes(prc, spread, vol, volume, borrow, index) -> pd.DataFrame:
    return pd.DataFrame(
        dict(
            prc=prc,
            bidaskhl_21d=spread,
            size_grp="large",
            rvol_21d=vol,
            dolvol_126d=volume,
            borrow=borrow,
        ),
        index=index,
    )


# Cost lines match a hand count. A sold-out name uses last month's data.
def test_costs_match_a_hand_calculation(held, monkeypatch):
    monkeypatch.setattr(C, "spread_ratios", lambda: {"large": 0.5})
    weights, _ = held
    today = pd.Series([0.02, -0.02], index=[1, 4])
    now = quotes(50.0, 0.01, 0.02, 1e8, [0.003, 0.03], [1, 4])
    before = quotes(20.0, 0.02, 0.03, 5e7, 0.003, [1, 2, 3])
    parts, turnover = P.trading_cost(today, weights, now, before)
    assert set(parts) == {
        "cost_commission",
        "cost_spread",
        "cost_impact",
        "cost_borrow",
        "cost_financing",
    }
    # Name 1 kept, 2 and 3 bought $100k each at $20, 4 shorted $200k at $50.
    assert turnover == pytest.approx(0.02)
    fees = 27.80e-6 * 200e3 + 0.000195 * 4000 + 0.000003 * 14000
    assert parts["cost_commission"] == pytest.approx((25 + 25 + 20 + fees) / 1e7)
    assert parts["cost_spread"] == pytest.approx((100e3 * 0.01 * 2 + 200e3 * 0.005) / 1e7)
    impact = 2 * 0.03 * np.sqrt(100e3 / 5e7) * 100e3 + 0.02 * np.sqrt(200e3 / 1e8) * 200e3
    assert parts["cost_impact"] == pytest.approx(impact / 1e7)
    assert parts["cost_borrow"] == pytest.approx(0.02 * 0.03 / 12)
    assert parts["cost_financing"] == pytest.approx(0.005 / 12)


# The first month pays to buy the whole book.
def test_first_month_is_a_full_entry(monkeypatch):
    monkeypatch.setattr(C, "spread_ratios", lambda: {"large": 0.5})
    today = pd.Series([0.01, -0.01], index=[1, 2])
    _, turnover = P.trading_cost(today, None, quotes(30.0, 0.01, 0.02, 1e8, 0.003, [1, 2]), None)
    assert turnover == pytest.approx(0.01)


# IBKR's minimum and 1% cap, FINRA's per-trade cap and the borrow tiers.
def test_commission_caps_and_borrow_tiers(monkeypatch):
    monkeypatch.setattr(C, "spread_ratios", lambda: {"large": 0.0})
    tiny = C.month_costs(
        pd.Series([1e-6]), pd.Series([1e-6]), quotes(10.0, 0.0, 0.0, 1e9, 0.003, [0])
    )
    assert tiny["cost_commission"] * 1e7 == pytest.approx(0.1 + 0.000003)
    sale = C.month_costs(
        pd.Series([-0.01]), pd.Series([0.0]), quotes(1.0, 0.0, 0.0, 1e9, 0.003, [0])
    )
    assert sale["cost_commission"] * 1e7 == pytest.approx(500 + 27.80e-6 * 1e5 + 9.79 + 0.3)
    rates = C.tier(pd.Series([0.0, 0.049, 0.05, 0.12, 0.25, np.nan]))
    assert rates.tolist() == [0.003, 0.003, 0.01, 0.03, 0.08, 0.003]


# Spread calibration reads only quotes from before the record starts.
def test_spread_calibration_stops_in_2020(monkeypatch):
    asked = []
    monkeypatch.setattr(C.data, "research", lambda name, cols, filters=None: asked.append(filters))
    assert C.calibrate_spreads() is None
    assert max(v for c, op, v in asked[0] if op == "<=") == pd.Timestamp("2020-12-31")


# Truncation and the repair each move shares, so one share is the bound.
def test_whole_shares_land_within_one_share_and_near_neutral():
    weights = pd.Series([0.015, 0.012, -0.013, -0.014], index=list("abcd"))
    prices = pd.Series([123.4, 87.1, 250.0, 33.3], index=list("abcd"))
    held = P.to_whole_shares(weights, prices)
    assert ((held - weights).abs() <= prices / P.NAV + 1e-12).all()
    assert (np.sign(held) == np.sign(weights)).all()
    assert abs(held.sum()) < 1e-4


# Tiny panel and exits: one name dead by decision, one exits next month.
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


# With no exits table the universe is left as it is.
def test_settle_changes_nothing_without_wrds(monkeypatch):
    panel = pd.DataFrame(
        dict(permno=[1], eom=[pd.Timestamp("2024-03-31")], ret_exc_lead1m=[np.nan])
    )
    monkeypatch.setattr(P, "exits", lambda: None)
    pd.testing.assert_frame_equal(P.settle(panel), panel)


# A missing return counts zero and is recorded by side.
def test_missing_returns_are_booked_at_zero_and_recorded():
    weights = pd.Series([0.01, -0.01], index=[1, 2])
    info = pd.DataFrame(
        dict(
            ret_exc_lead1m=[0.05, np.nan],
            hedge_beta=[1.0, 1.0],
            sector=["10", "10"],
            borrow=[0.003, 0.003],
        ),
        index=[1, 2],
    )
    record = P.month_record(
        pd.Timestamp("2024-03-31"), weights, info, pd.DataFrame(dict(n_signals=[12])), {}, 0.0
    )
    assert record["gross"] == pytest.approx(0.0005)
    assert record["missing_short_weight"] == pytest.approx(0.01)
    assert record["missing_long_weight"] == 0


# Importing a module must not run or write, so a bundler can take code.
def test_every_module_imports_without_side_effects(tmp_path):
    files = sorted((ROOT / "fiam").rglob("*.py"))
    # A teammate's separate research tree is not part of the kit.
    files = [p for p in files if "v4b" not in p.relative_to(ROOT).parts]
    # Modules on the optional backtest extra are checked only if installed.
    if importlib.util.find_spec("nautilus_trader") is None:
        files = [p for p in files if "nautilus_trader" not in p.read_text(encoding="utf-8")]
    names = [".".join(p.relative_to(ROOT).with_suffix("").parts) for p in files]
    script = f"import sys; sys.path[:0] = [{str(ROOT)!r}]\nfor n in {names!r}: __import__(n)"
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True, timeout=300)
    assert not any(tmp_path.iterdir()), "an import wrote a file"


# A missing benchmark file stops the run instead of downloading.
def test_benchmarks_refuse_to_download_on_their_own(tmp_path, monkeypatch):
    benchmarks = importlib.import_module("fiam.benchmarks")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="--refresh"):
        benchmarks.pinned("SP500.csv")


# Label rules: a cut-short panel name matches, typos or renames do not.
def test_label_names_allow_abbreviation_but_not_a_different_name():
    labels = importlib.import_module("fiam.exhibits.labels")
    assert labels.same_name("KULICKE & SOFFA INDS INC", "Kulicke & Soffa Industries, Inc.")
    assert labels.same_name("CLEARWATER ANALYTICS HLDGS INC", "Clearwater Analytics Holdings")
    assert not labels.same_name("H20 AMERICA", "H2O AMERICA")
    assert not labels.same_name("CONTANGO ORE INC", "Contango Silver & Gold Inc.")


# CRSP keeps share class apart: BFB is BF class B, BFXY is not the same.
def test_crsp_share_class_letter_is_accepted_once():
    labels = importlib.import_module("fiam.exhibits.labels")
    row = dict(eom=pd.Timestamp("2023-03-31"), crsp_ticker="BF", crsp_name="BROWN FORMAN CORP")
    assert (
        labels.verdict({**row, "TICKER": "BFB", "COMPANY NAME": "BROWN FORMAN CORP"})
        == "CRSP, dated"
    )
    wrong = labels.verdict({**row, "TICKER": "BFXY", "COMPANY NAME": "BROWN FORMAN CORP"})
    assert wrong == "differs from CRSP on ticker"


# Rounding for JSON keeps True and False as they are.
def test_saved_numbers_keep_booleans():
    assert P.round_floats(dict(passed=True, share=0.1234567)) == dict(passed=True, share=0.123457)


# Display names lose only SEC's state tag, so AT&T keeps its ampersand.
def test_display_name_drops_only_the_state_tag():
    assert P.display_name("APPLIED MATERIALS INC /DE") == "APPLIED MATERIALS INC"
    assert (
        P.display_name("SHENANDOAH TELECOMMUNICATIONS CO/VA/") == "SHENANDOAH TELECOMMUNICATIONS CO"
    )
    assert P.display_name("AT&T INC") == "AT&T INC"


# A file matches its hash only byte for byte. A missing file never does.
def test_hashes_match_byte_for_byte(tmp_path):
    paths = importlib.import_module("fiam.paths")
    lf, crlf = tmp_path / "a.csv", tmp_path / "b.csv"
    lf.write_bytes(b"x,y\n1,2\n")
    crlf.write_bytes(b"x,y\r\n1,2\r\n")
    digest = hashlib.sha256(b"x,y\n1,2\n").hexdigest()
    assert paths.matches(lf, digest) and not paths.matches(crlf, digest)
    assert not paths.matches(tmp_path / "missing.csv", digest)


# A book within limits passes. One name short or 60% net fails its rule.
def test_submission_rules_catch_each_breach():
    verify = importlib.import_module("fiam.checks.verify")
    months = pd.date_range("2021-01-01", "2026-08-01", freq="MS")

    # Long/short % of NAV: 95/95 neutral, 125/65 is 60% net in 190% gross.
    def book(names: int, long: float = 95, short: float = 95) -> pd.DataFrame:
        half = names // 2
        weight = np.r_[np.full(half, long / half), np.full(names - half, -short / (names - half))]
        rows = [(m, p, "T", "N", w) for m in months for p, w in enumerate(weight)]
        return pd.DataFrame(rows, columns=verify.COLUMNS)

    returns = pd.DataFrame(dict(holding_month=months.strftime("%Y-%m-%d")))

    # The names of the rules a book breaks.
    def failed(frame: pd.DataFrame) -> set[str]:
        return {n for n, ok, _ in verify.rules(frame, returns) if not ok}

    assert failed(book(200)) == set()
    assert failed(book(99)) == {"positions 100-500"}
    assert failed(book(200, long=125, short=65)) == {"net inside +/-50%"}
    assert failed(book(200, long=105, short=105)) == {"gross at most 200%"}
    short = book(200)
    short = short[short["Date"] < "2026-08-01"]
    assert failed(short) == {"months", "returns cover the same months"}
    assert failed(book(200).iloc[:0]) == {"holdings.csv has rows"}


# The comparison reads results, not run details like the date or commit.
def test_comparison_ignores_run_details(tmp_path):
    compare = importlib.import_module("fiam.checks.compare")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(dict(run=dict(git_commit="x"), ir=0.8341, n=[1, 2])))
    b.write_text(json.dumps(dict(run=dict(git_commit="y"), ir=0.8341, n=[1, 2])))
    assert compare.difference(a, b) == (0.0, "ir")
    b.write_text(json.dumps(dict(run=dict(git_commit="y"), ir=0.8326, n=[1, 2])))
    gap, key = compare.difference(a, b)
    assert key == "ir" and compare.verdict(gap) == "differs"


# --import copies the organizer's files by name and leaves a CV alone.
def test_import_takes_only_organizer_files(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("run", ROOT / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "factor_char_list.csv").write_text("variable\nbe_me\n")
    (downloads / "Someone_CV.pdf").write_bytes(b"%PDF")
    (downloads / "notes.csv").write_text("a,b\n1,2\n")
    monkeypatch.chdir(tmp_path)
    run.import_from(downloads)
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["factor_char_list.csv"]


# A number on one side and nothing on the other differs, never matches.
def test_comparison_counts_a_value_missing_on_one_side(tmp_path):
    compare = importlib.import_module("fiam.checks.compare")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(dict(ir=float("nan"))))
    b.write_text(json.dumps(dict(ir=0.83)))
    assert compare.verdict(compare.difference(a, b)[0]) == "differs"
    b.write_text(json.dumps(dict(ir=float("nan"))))
    assert compare.verdict(compare.difference(a, b)[0]) == "identical"


# A one-bet score can't be neutral at extremes, so the optimizer digs.
def test_optimizer_reaches_deeper_rather_than_trading_nothing():
    rng = np.random.default_rng(0)
    risk = rng.normal(size=1000)
    month = pd.DataFrame(
        dict(
            permno=range(1000),
            signal=-risk + rng.normal(scale=0.7, size=1000),
            risk_rank=risk,
            hedge_beta=1 + 0.3 * rng.normal(size=1000),
            sector=rng.choice(["10", "20", "30"], size=1000),
        )
    )
    weights = P.optimize_month(month)
    assert weights is not None and len(weights) >= 127
    assert weights.abs().sum() == pytest.approx(P.LIMITS["gross"], abs=1e-4)
    assert abs(weights.sum()) < 1e-6


# A share dearer than its target rounds to zero. Its gap gets spread.
def test_rounding_spreads_the_gap_of_a_name_too_dear_to_hold():
    weights = pd.Series([0.015] + [0.0015] * 10 + [-0.005] * 6, index=range(17))
    prices = pd.Series([700_000.0] + [1_000.0] * 16, index=range(17))
    held = P.to_whole_shares(weights, prices)
    assert 0 not in held.index
    longs = held[held > 0]
    assert longs.max() - longs.min() <= 1_000.0 / P.NAV + 1e-12
    assert abs(held.sum()) < 1e-5
