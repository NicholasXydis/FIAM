import dataclasses

import pandas as pd
import pytest

from fiam.v4b.engine import ladder, optimize
from fiam.v4b.engine.mandate import load


def test_noncompliant_run_cannot_pass_performance_gate():
    months = pd.date_range("2017-01-31", periods=48, freq="ME")
    old = pd.Series(0.0, index=months)
    new = pd.Series(0.01, index=months)
    base = {"net_ir_daily": 0.0, "breaches": 0, "reconcile": []}
    bad = {"net_ir_daily": 1.0, "breaches": 1, "reconcile": []}
    result = ladder.gate(base, bad, old, new)
    assert result["delta_ir"] == 1.0
    assert not result["promoted"]
    assert not result["process_passed"]


def test_promotion_cannot_skip_failed_predecessor():
    runs = {
        name: {"net_ir_daily": 1.0, "active_ann_mean": 0.01, "breaches": 0, "reconcile": []}
        for name in ("E0", "E1", "E2", "E2_Ma1", "E3", "fallback")
    }
    gates = {
        name: {"promoted": passed}
        for name, passed in (("E1_over_E0", False), ("E2_over_E1", True), ("E3_over_winner", True))
    }
    candidate, ship = ladder.select_candidate(runs, gates, ma1_wins=True)
    assert candidate == ship == "E0"


def test_no_ship_when_baseline_and_fallback_breach_rules():
    runs = {
        name: {"net_ir_daily": 1.0, "active_ann_mean": 0.01, "breaches": 1, "reconcile": []}
        for name in ("E0", "fallback")
    }
    candidate, ship = ladder.select_candidate(runs, {}, ma1_wins=False)
    assert candidate is None and ship is None


def test_target_cache_fingerprint_tracks_policy_and_column():
    m = load()
    step = optimize.Step("test")
    original = ladder.target_fingerprint(m, step)
    assert ladder.target_fingerprint(m, step) == original
    assert ladder.target_fingerprint(m, dataclasses.replace(step, column="Elasso_Ma1")) != original
    changed = dataclasses.replace(m, policy=dataclasses.replace(m.policy, impact_y=2.0))
    assert ladder.target_fingerprint(changed, step) != original


def test_insufficient_months_cannot_pass_gate():
    months = pd.date_range("2017-01-31", periods=3, freq="ME")
    m = {"net_ir_daily": 0.0, "breaches": 0, "reconcile": []}
    n = dict(m, net_ir_daily=2.0)
    result = ladder.gate(m, n, pd.Series(0.0, index=months), pd.Series(0.1, index=months))
    assert not result["promoted"]


def test_monthly_returns_exclude_initial_cash_snapshot():
    from types import SimpleNamespace

    dates = pd.to_datetime(["2016-12-30", "2017-01-03", "2017-01-04"])
    ledger = pd.DataFrame({"ret": [0.0, 0.1, 0.0]}, index=dates)
    world = SimpleNamespace(rf=pd.Series(0.0, index=dates), m=load())
    active = ladder.monthly_active(ledger, world)
    assert len(active) == 1
    assert active.iloc[0] == pytest.approx(0.1 - ((1 + 0.04 / 252) ** 2 - 1))


def test_ir_confidence_compares_ir_rather_than_mean_returns():
    months = pd.date_range("2017-01-31", periods=48, freq="ME")
    old = pd.Series([0.10, -0.08] * 24, index=months)
    new = pd.Series([0.004, 0.006] * 24, index=months)
    result = ladder.paired_ir(new, old, periods_per_year=12, block=3)
    # New has lower average return but much higher IR.
    assert result["lo90"] > 0


def test_review_horizon_counts_actual_sessions_to_next_month():
    world = ladder.World.__new__(ladder.World)
    world.sessions = pd.to_datetime(
        ["2019-12-30", "2019-12-31", "2020-01-02", "2020-01-03", "2020-01-31", "2020-02-03"]
    )
    assert world.holding_sessions(pd.Timestamp("2019-12-31")) == 3


def test_failed_2020_confirmation_blocks_full_window_point_gain():
    dates = pd.bdate_range('2019-01-01', '2020-12-31')
    old = pd.Series([0.005 if i % 2 else -0.004 for i in range(len(dates))], index=dates)
    new = pd.Series([0.002 if i % 2 else 0.0 for i in range(len(dates))], index=dates)
    new.loc[new.index.year == 2020] *= -1
    monthly_old = old.groupby(old.index.to_period('M')).sum()
    monthly_new = new.groupby(new.index.to_period('M')).sum()
    base = {'net_ir_daily': 0.1, 'breaches': 0, 'reconcile': []}
    improved = dict(base, net_ir_daily=0.8)
    result = ladder.gate(base, improved, monthly_old, monthly_new, old, new)
    assert result['by_year']['2019']['delta_ir'] > 0
    assert result['by_year']['2020']['delta_ir'] < 0
    assert not result['select_2019_confirm_2020']
    assert not result['promoted']
