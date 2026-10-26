# Risk model pieces on synthetic data (R§4); no data folder needed.

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk import covariance, exposures, factors, model, specific


# Constrained WLS recovers true factor returns and obeys c'f = 0.
def test_constrained_wls_recovers_and_obeys():
    rng = np.random.default_rng(0)
    n, k = 500, 6
    x = rng.normal(size=(n, k))
    x[:, 1:4] = np.eye(3)[rng.integers(0, 3, n)]  # sector-like dummies
    f_true = np.array([0.02, 0.01, -0.005, -0.005, 0.003, -0.002])
    y = x @ f_true + rng.normal(scale=0.01, size=n)
    c = np.array([0.0, 2.0, 1.0, 1.0, 0.0, 0.0])
    f = factors.constrained_wls(x, y, np.ones(n), c)
    assert abs(c @ f) < 1e-10
    assert np.allclose(f[[0, 4, 5]], f_true[[0, 4, 5]], atol=0.003)


# Sector dummies partition the liquid names; design is indexed by permno.
def test_design_partitions_sectors():
    month = pd.DataFrame(
        {
            "permno": [1, 2, 3, 4],
            "sector": ["45", "45", "10", "10"],
            "long_ok": [True, True, True, False],
            **{s: [0.1, -0.2, 0.3, 0.0] for s in exposures.STYLES},
        }
    )
    x, sectors = exposures.design(month)
    assert list(x.index) == [1, 2, 3]
    assert x[sectors].sum(axis=1).eq(1.0).all()


# IID factor returns: H-session covariance is H times the 1-session one.
def test_horizon_scaling_iid_limit():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2018-01-02", periods=800)
    fac = pd.DataFrame(rng.normal(scale=0.01, size=(800, 4)), index=days, columns=list("abcd"))
    date = days[-1] + pd.offsets.BDay(1)
    f21 = covariance.factor_cov_horizon(fac, date, half_life=10_000, horizon=21)
    f1 = covariance.factor_cov(fac, date, half_life=10_000)
    ratio = np.diag(f21) / (21 * np.diag(f1))
    assert np.allclose(ratio, 1.0, atol=0.35)


# Covariance at a date ignores factor returns on/after it (no lookahead).
def test_covariance_has_no_lookahead():
    rng = np.random.default_rng(2)
    days = pd.bdate_range("2018-01-02", periods=400)
    fac = pd.DataFrame(rng.normal(scale=0.01, size=(400, 3)), index=days, columns=list("abc"))
    date = days[300]
    a = covariance.factor_cov(fac, date, half_life=84)
    shocked = fac.copy()
    shocked.loc[days[300] :] = 5.0
    b = covariance.factor_cov(shocked, date, half_life=84)
    assert np.allclose(a.to_numpy(), b.to_numpy())


# Stressed covariance scales vols by 1.5 and pushes correlations outward.
def test_stressed_covariance():
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]], index=list("ab"), columns=list("ab"))
    s = covariance.stressed(cov)
    assert np.sqrt(s.iloc[0, 0]) == pytest.approx(1.5 * 0.2, rel=0.02)
    corr_before = 0.01 / (0.2 * 0.3)
    corr_after = s.iloc[0, 1] / np.sqrt(s.iloc[0, 0] * s.iloc[1, 1])
    assert corr_after == pytest.approx(corr_before + 0.5 * (1 - corr_before), rel=0.02)


# Vasicek pulls noisy extremes toward the sector mean, precise betas less.
def test_vasicek_shrinks_noisy_more():
    idx = range(100)
    beta_s = pd.Series(np.full(100, 1.0), index=idx, dtype=float)
    beta_s.iloc[0], beta_s.iloc[1] = 3.0, 3.0
    se = pd.Series(np.full(100, 0.1), index=idx)
    se.iloc[0], se.iloc[1] = 1.0, 0.05
    out = beta_mod.vasicek(beta_s, se, pd.Series("45", index=idx))
    assert abs(out.iloc[0] - 1.0) < abs(out.iloc[1] - 1.0) < 2.0


# Weekly-carried beta is constant inside a week and lags the raw series.
def test_weekly_carried_lags():
    days = pd.bdate_range("2020-06-01", periods=15)
    raw = pd.DataFrame({"x": np.arange(15, dtype=float)}, index=days)
    carried = beta_mod.weekly_carried(raw)
    monday = pd.Timestamp("2020-06-08")
    assert carried.at[monday, "x"] == raw.at[pd.Timestamp("2020-06-05"), "x"]
    week = carried.loc["2020-06-08":"2020-06-12", "x"]
    assert week.nunique() == 1


# QLIKE is minimised when forecast variance equals realised variance.
def test_qlike_minimum_at_truth():
    r = pd.Series([0.04, 0.09])
    assert specific.qlike(r, r).abs().max() < 1e-12
    assert specific.qlike(r, r * 2).mean() > 0


# The shipped half-life is the one validate.py froze in its report.
def test_frozen_half_life_matches_report():
    import json
    from pathlib import Path

    report = json.loads(
        (Path(__file__).resolve().parents[1] / "out" / "risk" / "report.json").read_text()
    )
    assert model.FACTOR_HL == report["factor_hl_chosen"] == 84
    assert report["specific_race"]["winner"] == "ewma168"


# Factor-form variance and gradient match the dense BFB' + D computation.
def test_variance_and_marginal_match_dense():
    rng = np.random.default_rng(3)
    names = pd.Index(range(30), name="permno")
    cols = ["mkt", "s_10", "size"]
    B = pd.DataFrame(rng.normal(size=(30, 3)), index=names, columns=cols)
    B["s_10"] = (np.arange(30) % 2).astype(float)
    F = pd.DataFrame(np.eye(3) * 0.001 + 0.0002, index=cols, columns=cols)
    d = pd.Series(np.full(30, 0.0004), index=names)
    snap = {"B": B, "F": F, "F1": F / 21, "d": d, "horizon": 21, "beta": B["mkt"], "sxx": 0.5}
    w = pd.Series(rng.normal(size=30), index=names)
    w = w / w.abs().sum() * 2
    dense = B.to_numpy() @ F.to_numpy() @ B.to_numpy().T + np.diag(d.to_numpy() * 21)
    var, share = model.variance(snap, w)
    assert var == pytest.approx(float(w.to_numpy() @ dense @ w.to_numpy()), rel=1e-10)
    assert 0 <= share <= 1
    grad = model.marginal(snap, w).to_numpy()
    eps = 1e-7
    numeric = np.empty(30)
    for i in range(30):
        up, dn = w.copy(), w.copy()
        up.iloc[i] += eps
        dn.iloc[i] -= eps
        numeric[i] = (model.variance(snap, up)[0] - model.variance(snap, dn)[0]) / (2 * eps)
    assert np.allclose(grad, numeric, rtol=1e-4, atol=1e-8)
    beta_v, se_v = model.beta_of(snap, w)
    assert beta_v == pytest.approx(float(B["mkt"] @ w), rel=1e-10)
    assert se_v > 0
