"""Real nautilus_trader engine regressions; run with v4b/.venv/bin/python."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("nautilus_trader")
from fiam.v4b.engine.nautilus_backend import run
from fiam.v4b.engine.nautilus_data import Feed
from fiam.v4b.engine.sim import Setup


def market(prices, adv=100.0):
    days = pd.bdate_range("2020-01-02", periods=len(prices))
    px = pd.DataFrame({1: prices}, index=days, dtype=float)
    zero = px * 0
    return Feed(
        px,
        zero.fillna(0),
        px.notna(),
        zero.fillna(0) + adv,
        zero.fillna(0) + 0.02,
        0.0,
        0.0,
        pd.Series(0.0, index=days),
    )


def setup(**extra):
    return Setup(nav0=100.0, impact_y=0.0, commission=0.0, sec_rate=0.0, fee_schedule="flat", paced=False, **extra)


def test_liquidation_tracks_shares_when_prices_move():
    feed = market([1, 1, 1, 1, 2, 2, 2, 2])
    days = feed.prices.index
    result = run({days[0]: pd.Series({1: 0.2}), days[2]: pd.Series({1: 0.0})}, feed, setup())
    last = result.positions[result.positions.date == days[-1]]
    assert last.empty or last.quantity.abs().sum() == 0
    assert result.ledger.nav.iloc[-1] == pytest.approx(110.0)
    assert result.intents.iloc[-1].remaining_qty == 0


def test_expired_residual_is_retained():
    feed = market([1] * 7)
    result = run({feed.prices.index[0]: pd.Series({1: 0.9})}, feed, setup())
    expired = result.intents[result.intents.status == "EXPIRED"]
    assert expired.remaining_qty.iloc[-1] == 40
    assert result.positions.trade_dollars.sum() == 50


def test_execution_clock_excludes_signal_to_execution_move():
    feed = market([1, 2, 3])
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup())
    assert result.ledger.pnl.iloc[1] == 0
    assert result.ledger.nav.iloc[-1] == 105


def test_dividends_are_cash_and_do_not_change_share_quantity():
    feed = market([1] * 4)
    feed.dividends.iloc[2, 0] = 0.1
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup())
    assert result.ledger.nav.iloc[-1] == 101
    assert result.positions.quantity.iloc[-1] == 10
    assert result.ledger.distributions.sum() == 1


# A position unquoted for stub_days sessions is settled at its last mark (D12).
def test_stale_long_quote_settles_at_last_mark():
    feed = market([1, 1, 1.5, *[np.nan] * 7])
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup())
    assert result.ledger.nav.iloc[-1] == pytest.approx(105)
    assert result.positions.quantity.iloc[-1] == 0
    assert result.positions.synthetic_exit_dollars.sum() == pytest.approx(-15)
    assert result.ledger.stub.sum() == 0


def test_stale_short_quote_settles_at_last_mark():
    feed = market([1, 1, 0.5, *[np.nan] * 7], adv=1e7)
    result = run({feed.prices.index[0]: pd.Series({1: -0.1})}, feed, setup())
    assert result.ledger.nav.iloc[-1] == pytest.approx(105)
    assert result.positions.quantity.iloc[-1] == 0


# A short gap below stub_days keeps the position at its last mark.
def test_short_gap_keeps_position():
    feed = market([1, 1, *[np.nan] * 3, 1])
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup())
    assert result.positions.quantity.iloc[-1] == 10


# The dated schedule: $1 minimum commission, CAT, and SEC + TAF on sales.
def test_ibkr_fee_schedule_per_order():
    from fiam.v4b.engine import fees

    assert fees.order(1000, 10.0, sell=False) == pytest.approx(1.0 + 100 * 3e-6)
    big = fees.order(1e6, 50.0, sell=True)
    shares = 1e6 / 50
    assert big == pytest.approx(0.005 * shares + 3e-6 * shares + 27.8 + min(0.000195 * shares, 9.79))
    feed = market([1] * 3, adv=1e9)
    feed.raw_close = feed.prices * 50
    config = Setup(nav0=1e6, impact_y=0, commission=0, sec_rate=0, paced=False)
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, config)
    # Nautilus books money in cents.
    assert result.ledger.fees.sum() == pytest.approx(fees.order(1e5, 50.0, sell=False), abs=0.01)


def test_modeled_costs_reach_native_account():
    feed = market([1] * 3)
    feed.half_spread = 0.01
    config = Setup(nav0=100, impact_y=0, commission=0.001, sec_rate=0, fee_schedule="flat", paced=False)
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, config)
    assert result.ledger.nav.iloc[-1] == pytest.approx(99.89)
    assert result.ledger.spread.sum() == pytest.approx(0.1)
    assert result.ledger.fees.sum() == pytest.approx(0.01)
    assert not result.native_fills.empty


def test_native_reports_use_marked_equity_for_open_positions(tmp_path):
    feed = market([1, 1, 2])
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup(), report_dir=tmp_path)
    assert result.ledger.nav.iloc[-1] == 110
    assert (tmp_path / "orders.csv").exists()
    assert (tmp_path / "fills.csv").exists()
    assert (tmp_path / "positions.csv").exists()
    assert (tmp_path / "accounts.csv").exists()
    assert (tmp_path / "tearsheet.html").exists()
    returns = pd.read_parquet(tmp_path / "tearsheet_returns.parquet").iloc[:, 0]
    assert (1 + returns).prod() == pytest.approx(1.1)


def test_zero_price_short_does_not_create_uncollectible_gain():
    feed = market([1, 1, 0, 0, 0, 0], adv=1e7)
    feed.borrow = 0.05
    config = Setup(nav0=1e6, impact_y=0, commission=0, sec_rate=0, fee_schedule="flat", paced=False)
    result = run({feed.prices.index[0]: pd.Series({1: -0.1})}, feed, config)
    assert result.ledger.pnl.iloc[2] == 0
    assert result.ledger.borrow.iloc[-1] > 0
    assert result.positions.quantity.iloc[-1] < 0


def test_true_long_total_loss_remains_in_nav():
    feed = market([1, 1, 0, 0])
    result = run({feed.prices.index[0]: pd.Series({1: 0.1})}, feed, setup())
    assert result.ledger.nav.iloc[-1] == 90


def test_split_adjustment_and_cash_distribution_are_separate():
    from fiam.v4b.engine.nautilus_data import build_feed

    days = pd.bdate_range("2020-01-02", periods=3)
    frame = pd.DataFrame(
        {
            "permno": [1] * 3,
            "date": days,
            "close": [100.0, 50.0, 50.0],
            "price_return": [np.nan, 0.0, 0.0],
            "total_return": [np.nan, 0.0, 0.01],
            "volume": [1e6] * 3,
        }
    )
    base = market([100] * 3)
    feed = build_feed(
        frame,
        {"returns": base.prices, "adv": base.adv, "sigma": base.sigma, "half_spread": 0.0},
        0.0,
        base.rf,
    )
    assert feed.prices[1].tolist() == [100.0, 100.0, 100.0]
    assert feed.dividends[1].tolist() == [0.0, 0.0, 1.0]


def test_quote_reopening_marks_observed_price_instead_of_one_day_return():
    from fiam.v4b.engine.nautilus_data import build_feed

    days = pd.bdate_range("2020-01-02", periods=3)
    frame = pd.DataFrame(
        {
            "permno": [1] * 3,
            "date": days,
            "close": [100.0, np.nan, 120.0],
            "price_return": [np.nan, np.nan, 0.05],
            "total_return": [np.nan, np.nan, 0.05],
            "volume": [1e6, 0, 1e6],
        }
    )
    base = market([100] * 3)
    feed = build_feed(
        frame,
        {"returns": base.prices, "adv": base.adv, "sigma": base.sigma, "half_spread": 0.0},
        0.0,
        base.rf,
    )
    assert feed.prices.iloc[-1, 0] == 120.0
    assert feed.unverified_gaps.iloc[-1, 0]


# Paced execution splits an order evenly over the execution days.
def test_paced_execution_splits_evenly():
    feed = market([1] * 8, adv=1e9)
    config = Setup(nav0=100.0, impact_y=0.0, commission=0.0, sec_rate=0.0, fee_schedule="flat")
    result = run({feed.prices.index[0]: pd.Series({1: 0.5})}, feed, config)
    q = result.positions.groupby("date").quantity.sum()
    assert list(q.iloc[:5]) == [10, 20, 30, 40, 50]

