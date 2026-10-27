# The result tools: file stems, ADV, flat borrow rates and crisis sums.

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from fiam.v4.construct import optimizer
from tools import crises, exhibits, flat_borrow, whatif


# The stem is the design and the commit, found from the daily file.
def test_stem_of_reads_the_daily_file(tmp_path):
    (tmp_path / "daily_7_abcdef123456.parquet").write_bytes(b"")
    assert exhibits.stem_of(tmp_path, "abcdef1234567890") == "7_abcdef123456"
    with pytest.raises(SystemExit):
        exhibits.stem_of(tmp_path, "ffffffffffff")


# Each kept frame's ADV becomes one dated row per name.
def test_adv_of_dates_each_frame():
    frame = pd.DataFrame({"adv_cost": [1e7, 2e7]}, index=pd.Index([10, 11], name="permno"))
    got = exhibits.adv_of({pd.Timestamp("2021-02-01"): frame})
    assert list(got.columns) == ["date", "permno", "adv"]
    assert got["adv"].tolist() == [1e7, 2e7]


# Large caps borrow cheaply; small or unknown caps pay the dear rate.
def test_flat_rate_by_market_cap():
    caps = pd.Series([20_000.0, 10_000.0, 600.0, np.nan])
    got = flat_borrow.flat_rate(caps).tolist()
    assert got == [0.005, 0.005, 0.05, 0.05]


# The crisis summary reads only replays that ran.
def test_crisis_summary_skips_missing_replays():
    got = crises.summary({"a": {"loss": -0.02}, "b": {"loss": 0.01}, "c": {"loss": None}})
    assert got == {"crises_replayed": 2, "worst": -0.02, "mean": -0.005, "best": 0.01}
    assert crises.summary({}) == {"crises_replayed": 0}


# The last day's positions become weights as shares of that day's NAV.
def test_last_weights_are_shares_of_nav(tmp_path):
    days = pd.to_datetime(["2026-08-28", "2026-08-31"])
    pd.DataFrame({"nav": [1e9, 2e9]}, index=days).to_parquet(tmp_path / "daily_7_x.parquet")
    pd.DataFrame({
        "date": [days[0], days[1], days[1]],
        "permno": [1, 1, 2],
        "value": [5e7, 4e7, -2e7],
    }).to_parquet(tmp_path / "positions_7_x.parquet")  # fmt: skip
    day, w = crises.last_weights(tmp_path, "7_x")
    assert day == days[1]
    assert w.to_dict() == {1: 0.02, 2: -0.01}


# A variant scales the cost budget and risk aversion, replaces the rest.
def test_varied_scales_or_replaces():
    s = optimizer.Settings(gross=1.5, ridge=30, risk_lambda=2.0, style_cap=0.2,
                           cost_budget=0.001, names_max=275, speed=1.0)  # fmt: skip
    got = whatif.varied(s, {"cost_budget": 0.5, "risk_lambda": 2.0, "names_max": 480})
    assert (got.cost_budget, got.risk_lambda, got.names_max, got.speed) == (0.0005, 4.0, 480, 1.0)
    assert whatif.varied(replace(s, cost_budget=None), {"cost_budget": 2.0}).cost_budget is None
    assert whatif.varied(s, {"cost_budget": None}).cost_budget is None


# Every variant changes only known settings, the cadence or the limits.
def test_variants_name_known_settings():
    for change in whatif.VARIANTS.values():
        assert set(change) <= whatif.SETTINGS | {
            "cadence",
            "limits",
            "alpha_vol",
            "free_styles",
            "vol_reliability",
            "stress",
            "entry_musd",
            "hold_musd",
        }


# Reliability multipliers read only months public by the close.
def test_multipliers_use_only_public_months():
    eoms = pd.date_range("2017-01-31", periods=20, freq="ME")
    lag = pd.Timedelta(days=40)
    rows = [{"eom": e, "third": k, "ic": 0.01 * (k + 1), "public": e + lag}
            for e in eoms for k in range(3)]  # fmt: skip
    ics = pd.DataFrame(rows)
    T = pd.Timestamp("2018-06-29")
    got = whatif.multipliers(ics, T)
    late = ics.assign(ic=np.where(ics["public"] > T, 9.0, ics["ic"]))
    assert whatif.multipliers(late, T) == got
    assert got[2] > got[1] > got[0]
    assert whatif.multipliers(ics, pd.Timestamp("2017-06-30")) == [1.0, 1.0, 1.0]


# The stress share ignores the close itself and every later session.
def test_stress_share_reads_only_the_past():
    days = pd.bdate_range("2019-01-01", periods=300)
    market = pd.Series(np.random.default_rng(1).normal(0, 0.01, len(days)), index=days)
    T = days[250]
    later = market.copy()
    later[later.index >= T] = 0.5
    assert whatif.stress_share(market, T) == whatif.stress_share(later, T)
    assert 0.0 <= whatif.stress_share(market, T) <= 1.0


# The stressed covariance keeps its shape and scales every vol by 1.5.
def test_stressed_covariance_is_valid():
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]], index=["a", "b"], columns=["a", "b"])
    got = whatif.stressed(cov)
    assert np.allclose(np.sqrt(np.diag(got)), 1.5 * np.sqrt(np.diag(cov)))
    assert np.all(np.linalg.eigvalsh(got.to_numpy()) > 0)
    assert got.loc["a", "b"] > cov.loc["a", "b"] * 2.25


# A factor with no variance still gives a matrix Cholesky accepts.
def test_stressed_covariance_handles_a_flat_factor():
    cov = pd.DataFrame(np.diag([0.04, 0.0, 0.09]), index=list("abc"), columns=list("abc"))
    cov.loc["a", "c"] = cov.loc["c", "a"] = 0.05
    mixed = whatif.definite(0.5 * cov.to_numpy() + 0.5 * whatif.stressed(cov).to_numpy())
    np.linalg.cholesky(mixed + 1e-12 * np.eye(3))


# The size variant moves both caps and leaves the daily short floor.
def test_cap_variant_moves_the_universe_caps(monkeypatch):
    from fiam.v4 import universe
    from fiam.v4.construct import execution

    monkeypatch.setattr(universe, "ENTRY_MUSD", universe.ENTRY_MUSD)
    monkeypatch.setattr(universe, "HOLD_MUSD", universe.HOLD_MUSD)
    monkeypatch.setattr(whatif.revised, "install_settings", lambda loose: None)
    monkeypatch.setattr(whatif.exam, "settings_for", whatif.exam.settings_for)
    whatif.install(whatif.VARIANTS["cap_3bn"], True)
    assert (universe.ENTRY_MUSD, universe.HOLD_MUSD) == (3000.0, 2500.0)
    assert execution.FLOOR_MUSD == 500.0
