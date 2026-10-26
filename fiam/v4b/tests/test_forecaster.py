# The engine-facing E-LASSO interface: centring, calibration, decay (D6).

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.elasso import forecaster
from fiam.v4b.engine import mandate



# Centred forecasts have median zero every month and keep the ranking.
def test_centred_forecasts_have_zero_median():
    m = mandate.load()
    raw = forecaster.expected_returns(m)
    got = forecaster.centred_returns(m)
    assert got.groupby("eom")["mu"].median().abs().max() < 1e-12
    month = raw["eom"].iloc[0]
    a = raw[raw["eom"] == month].set_index("permno")["mu"]
    b = got[got["eom"] == month].set_index("permno")["mu"]
    assert a.rank().corr(b.rank()) == pytest.approx(1.0)
    # The centred spread is the raw spread times the frozen scale.
    assert (b.max() - b.min()) == pytest.approx(
        m.policy.forecaster_scale * (a.max() - a.min()), rel=1e-9
    )


# With no decay, alpha accrues linearly: 5 of 21 sessions earn 5/21.
def test_horizon_scale_without_decay_is_linear():
    assert forecaster.horizon_scale(0, 5, 0.0) == pytest.approx(5 / 21)
    assert forecaster.horizon_scale(10, 21, 0.0) == pytest.approx(1.0)
    assert forecaster.horizon_scale(0, 0, 0.5) == 0.0


# A full fresh 21-session hold earns the whole forecast, at any kappa.
def test_horizon_scale_full_fresh_hold_is_one():
    for k in (0.001, 0.0052, 0.07, 0.5):
        assert forecaster.horizon_scale(0, 21, k) == pytest.approx(1.0)


# Staleness only shrinks the remainder, faster for a faster kappa (the
# estimated kappas' order is data, not a property of the code).
def test_horizon_scale_staleness_shrinks():
    slow = forecaster.horizon_scale(21, 21, 0.002)
    fast = forecaster.horizon_scale(21, 21, 0.03)
    assert 0 < fast < slow < 1


# Config scales and kappas are the numbers freeze.py/tail.py estimated, not retyped.
def test_config_matches_frozen_estimates():
    m = mandate.load()
    frozen = json.loads((forecaster.run_dir(m) / "frozen.json").read_text())
    assert frozen["window_eom"][1] <= "2020-11-30"
    assert m.policy.forecaster_scale == frozen["Elasso_MaInf"]["calibration_y21"]["slope"]
    assert m.policy.forecaster_alternate_scale == frozen["Elasso_Ma1"]["calibration_y21"]["slope"]
    assert m.policy.forecaster_kappa == frozen["Elasso_MaInf"]["frozen_kappa"]
    assert m.policy.forecaster_alternate_kappa == frozen["Elasso_Ma1"]["frozen_kappa"]


# Only the primary and alternate columns have frozen scales.
def test_unknown_column_has_no_scale():
    m = mandate.load()
    with pytest.raises(ValueError, match="no frozen"):
        forecaster.scale_for(m, "Elasso_Ma36")
    with pytest.raises(ValueError, match="no frozen"):
        forecaster.kappa_for(m, "Slasso_MaInf")


# The rolling run is real-time (D11): its pre-2021 mean forecasts equal the
# run cut at 2020-12-31, so later data never reaches an earlier formation.
def test_rolling_forecasts_are_real_time():
    root = Path(__file__).resolve().parents[1] / "out" / "elasso"
    judged = json.loads((root / "rolling" / "judge_valid.json").read_text())
    assert judged["reproduce"]["rows"] == judged["reproduce"]["old_rows"]
    assert judged["reproduce"]["max_abs_MaInf"] < 1e-9
    f = forecaster.expected_returns()
    assert f["eom"].max() == np.datetime64("2026-07-31")
    # Walk-forward (D15): the first refit forecasts the first judged formation.
    assert f["eom"].min() <= forecaster.BURNIN_BEFORE
    months = pd.date_range(f["eom"].min(), f["eom"].max(), freq="ME")
    assert set(months) == set(f["eom"].unique())  # a refit for every formation
