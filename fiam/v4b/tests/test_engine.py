import numpy as np
import pandas as pd
import pytest

from fiam.v4b.engine import checker, sim
from fiam.v4b.engine.mandate import load


def market(n=9):
    days = pd.bdate_range("2020-01-02", periods=n)
    returns = pd.DataFrame(0.0, index=days, columns=[1])
    return sim.Market(
        returns=returns,
        adv=returns + 100.0,
        sigma=returns + 0.02,
        half_spread=0.0,
        borrow=0.0,
        rf=pd.Series(0.0, index=days),
    )


def setup(**kwargs):
    return sim.Setup(nav0=100.0, impact_y=0.0, commission=0.0, sec_rate=0.0, **kwargs)


def test_target_builder_receives_executed_book_at_signal_close():
    mk = market()
    days = mk.returns.index
    seen = []

    def target(w_pre, nav):
        seen.append((w_pre.copy(), nav))
        return pd.Series({1: 0.5 if len(seen) == 1 else 0.0})

    # Three $10 fills by day 3, rather than the requested $50 position.
    # A jump on execution day 4 must not enter the day-3 decision.
    mk.returns.loc[days[4], 1] = 1.0
    sim.run({days[0]: target, days[3]: target}, mk, setup())
    assert len(seen) == 2
    assert seen[0][0].empty
    assert seen[0][1] == 100.0
    assert seen[1][0].loc[1] == pytest.approx(0.3)
    assert seen[1][1] == pytest.approx(100.0)


def test_missing_short_remains_frozen_and_pays_borrow():
    mk = market()
    days = mk.returns.index
    mk.returns.loc[days[3] :, 1] = np.nan
    mk.borrow = 0.05
    ledger, positions = sim.run({days[0]: pd.Series({1: -0.1})}, mk, setup(stub_days=2))
    assert positions[positions.date == days[-1]].w.iloc[0] < 0
    assert ledger.loc[days[4] :, "borrow"].gt(0).all()


def test_execution_uses_spread_known_before_close():
    mk = market(3)
    days = mk.returns.index
    mk.half_spread = pd.DataFrame({1: [0.01, 0.5, 0.5]}, index=days)
    ledger, _ = sim.run({days[0]: pd.Series({1: 0.1})}, mk, setup())
    assert ledger.loc[days[1], "spread"] == pytest.approx(0.1)


def test_total_loss_is_kept_and_trade_clock_starts_next_session():
    mk = market(4)
    days = mk.returns.index
    mk.returns.loc[days[1], 1] = 1.0
    mk.returns.loc[days[2], 1] = -1.0
    ledger, _ = sim.run({days[0]: pd.Series({1: 0.1})}, mk, setup())
    assert ledger.loc[days[1], "pnl"] == 0.0
    assert ledger.loc[days[2], "pnl"] == -10.0
    assert ledger.iloc[-1]["nav"] == pytest.approx(90.0)
    assert checker.reconcile(ledger) == []


def test_checker_does_not_hide_flat_book_days():
    day = pd.Timestamp("2020-01-02")
    positions = pd.DataFrame(
        {"date": [day], "permno": [1], "w": [0.0], "w_pre": [0.0], "rebalance": [False]}
    )
    panel = pd.DataFrame(columns=["permno", "eom", "me", "me_company"])
    breaches, days = checker.check(positions, panel, load())
    assert days.loc[day, "names"] == 0
    assert breaches.rule.tolist() == ["names"]


def test_short_total_loss_is_not_an_uncollectible_windfall():
    mk = market(5)
    days = mk.returns.index
    mk.returns.loc[days[2] :, 1] = -1.0
    mk.borrow = 0.05
    ledger, positions = sim.run({days[0]: pd.Series({1: -0.1})}, mk, setup())
    assert ledger.loc[days[2], "pnl"] == 0.0
    assert ledger.loc[days[-1], "borrow"] > 0
    assert positions[positions.date == days[-1]].w.iloc[0] < 0


def test_checker_flags_illiquid_executed_positions():
    day = pd.Timestamp("2020-01-02")
    pos = pd.DataFrame(
        {
            "date": [day] * 200,
            "permno": range(200),
            "w": [0.005] * 200,
            "w_pre": [0.005] * 200,
            "rebalance": [False] * 200,
            "adv_days": [100.0] * 200,
        }
    )
    panel = pd.DataFrame(columns=["permno", "eom", "me", "me_company"])
    breaches, _ = checker.check(pos, panel, load())
    assert len(breaches[breaches.rule == "liquidation_days"]) == 200


def test_missing_volatility_is_not_free_impact():
    mk = market(3)
    days = mk.returns.index
    mk.sigma[:] = np.nan
    config = sim.Setup(nav0=100, commission=0.0, sec_rate=0.0)
    ledger, _ = sim.run({days[0]: pd.Series({1: 0.1})}, mk, config)
    assert ledger.loc[days[1], "impact"] > 0


def test_executed_exposure_diagnostics_use_prior_month_rows():
    day = pd.Timestamp("2020-01-02")
    pos = pd.DataFrame({"date": [day, day], "permno": [1, 2], "w": [0.5, -0.5]})
    dated = pd.DataFrame(
        {
            "eom": pd.to_datetime(["2019-12-31"] * 2 + ["2020-01-31"] * 2),
            "permno": [1, 2, 1, 2],
            "sector": ["10"] * 4,
            "beta": [1.2, 0.8, 9.0, 9.0],
            "size": [1.0, -1.0, 0.0, 0.0],
            "size_band": [0.3] * 4,
        }
    )
    days = checker.policy_diagnostics(pos, dated, load())
    assert days.loc[day, "beta"] == pytest.approx(0.2)
    assert days.loc[day, "size"] == pytest.approx(1.0)
    assert days.loc[day, "violated"]


def test_monthly_reference_earns_only_after_the_actual_fill():
    from fiam.v4b.engine.reconcile import monthly_reference

    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    ledger = pd.DataFrame(
        {
            "nav": [100.0, 100.0, 101.0],
            "ret": [0.0, 0.0, 0.01],
            **{c: [0.0] * 3 for c in ("interest", "spread", "impact", "fees", "borrow", "stub")},
        },
        index=dates,
    )
    pos = pd.DataFrame(
        {
            "date": dates[1:],
            "permno": [1, 1],
            "w": [0.1, 11 / 101],
            "trade_dollars": [10.0, 0.0],
            "synthetic_exit_dollars": [0.0, 0.0],
        }
    )
    returns = pd.DataFrame({1: [0.0, 0.5, 0.1]}, index=dates)
    result = monthly_reference(ledger, pos, returns)
    assert result["max_return_gap"] < 1e-12
    assert result["months"] == 1


def test_short_floor_ignores_weight_change_without_short_sale():
    day = pd.Timestamp("2020-01-06")
    positions = pd.DataFrame(
        {
            "date": [day],
            "permno": [1],
            "w": [-0.0101],
            "w_pre": [-0.01],
            "rebalance": [False],
            "trade_dollars": [0.0],
        }
    )
    panel = pd.DataFrame(
        {"eom": pd.to_datetime(["2019-12-31"]), "permno": [1], "me": [400.0], "me_company": [400.0]}
    )
    assert checker._short_floor(positions, panel, 500.0) == []


def test_mixed_breach_rules_can_be_saved_as_parquet(tmp_path):
    day = pd.Timestamp("2020-01-02")
    positions = pd.DataFrame(
        {
            "date": [day] * 501,
            "permno": range(501),
            "w": [0.01] * 501,
            "w_pre": [0.01] * 501,
            "rebalance": [False] * 501,
        }
    )
    panel = pd.DataFrame(columns=["permno", "eom", "me", "me_company"])
    breaches, _ = checker.check(positions, panel, load())
    path = tmp_path / "breaches.parquet"
    breaches.to_parquet(path, index=False)
    assert set(pd.read_parquet(path).rule) == {"names", "gross", "net"}


def test_monthly_reference_matches_float64_simulation_of_float32_inputs():
    from fiam.v4b.engine.reconcile import monthly_reference

    mk = market(26)
    mk.returns[:] = 0.125
    mk.returns = mk.returns.astype("float32")
    ledger, positions = sim.run({mk.returns.index[0]: pd.Series({1: 0.1})}, mk, setup())
    result = monthly_reference(ledger, positions, mk.returns)
    assert result["passed"], result


def test_beta_market_returns_align_sessions_before_pct_change(tmp_path):
    from fiam.v4b.engine import inputs
    path=tmp_path/'sp.csv'
    pd.DataFrame({'observation_date':['2020-01-03','2020-01-04','2020-01-06'],
                  'SP500':[100.0,np.nan,110.0]}).to_csv(path,index=False)
    dates=pd.to_datetime(['2020-01-03','2020-01-06'])
    result=inputs.market_returns(dates,path=path)
    assert result.iloc[1] == pytest.approx(.1)
