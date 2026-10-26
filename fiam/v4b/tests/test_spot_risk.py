"""Known-truth tests for the one-session risk used in daily diagnostics."""

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.risk import covariance, model


def test_daily_covariance_uses_zero_lag_not_horizon_or_newey_west():
    rng = np.random.default_rng(21)
    innovation = rng.normal(0.0, 0.01, 800)
    values = np.zeros_like(innovation)
    for i in range(1, len(values)):
        values[i] = 0.7 * values[i - 1] + innovation[i]
    days = pd.bdate_range("2015-01-01", periods=len(values))
    factors = pd.DataFrame({"mkt": values}, index=days)
    formation = days[-1] + pd.offsets.BDay(1)
    lag0 = covariance.autocovariances(factors, formation, 84, 0)[0][0, 0]
    daily = covariance.factor_cov_daily(factors, formation, 84)
    nw = covariance.factor_cov(factors, formation, 84)
    assert daily.loc["mkt", "mkt"] == pytest.approx(lag0, rel=1e-12)
    assert nw.loc["mkt", "mkt"] > 2 * lag0
    shocked = factors.copy()
    shocked.loc[formation] = 20.0
    assert covariance.factor_cov_daily(shocked, formation, 84).equals(daily)


def test_daily_portfolio_variance_uses_daily_factor_covariance():
    names = pd.Index([1, 2], name="permno")
    B = pd.DataFrame({"mkt": [1.0, 2.0], "pca1": [0.5, -0.5]}, index=names)
    cols = B.columns
    Fdaily = pd.DataFrame([[0.0001, 0.0], [0.0, 1.0]], index=cols, columns=cols)
    snap = {"B": B, "F_daily": Fdaily, "F": Fdaily * 40,
            "F1": Fdaily * 3, "d": pd.Series([0.0004, 0.0009], index=names),
            "horizon": 20}
    w = pd.Series([0.6, -0.4], index=names)
    bw = B.T @ w
    expected = float(bw @ Fdaily @ bw + (w**2 * snap["d"]).sum())
    assert model.daily_variance(snap, w) == pytest.approx(expected)
    assert model.daily_vol(snap, w) == pytest.approx(np.sqrt(expected))
    assert model.vol(snap, w) / np.sqrt(252) != pytest.approx(np.sqrt(expected))


def test_coverage_study_is_reproducible_and_checks_true_unit_volatility():
    from fiam.v4b.research.g2_known_truth import study

    first = study(reps=500, n=160, seed=20261026)
    assert first == study(reps=500, n=160, seed=20261026)
    assert first["gaussian"]["coverage"] > 0.85
    assert first["student_t5"]["coverage"] < first["gaussian"]["coverage"]
    assert first["student_t5"]["true_sd"] == 1.0


def test_bootstrap_intervals_use_resampled_standard_deviation():
    from fiam.v4b.research.g2_robust_truth import bootstrap_intervals

    samples = np.array([[1., 2., 3., 4., 5.]])
    indices = np.array([[[0, 1, 2, 3, 4], [0, 0, 1, 1, 2],
                         [2, 3, 3, 4, 4], [0, 2, 2, 4, 4]]])
    result = bootstrap_intervals(samples, indices)
    resampled_sd = np.std(samples[0][indices[0]], axis=1, ddof=1)
    q05, q95 = np.quantile(resampled_sd, [0.05, 0.95])
    original_sd = np.std(samples[0], ddof=1)
    assert result["percentile"][0] == pytest.approx([q05, q95])
    assert result["basic_log"][0] == pytest.approx([original_sd**2 / q95, original_sd**2 / q05])
