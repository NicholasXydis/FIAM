# The forecaster's pieces on synthetic data, no data folder needed.

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.forecast import data, evaluate, prep, ridge


# A small panel: 30 months x 200 names, two real signals.
@pytest.fixture(scope="module")
def panel():
    rng = np.random.default_rng(0)
    eoms = pd.date_range("2015-01-31", periods=30, freq="ME")
    rows = []
    for e in eoms:
        a, b = rng.normal(size=200), rng.normal(size=200)
        y = 0.02 * a - 0.01 * b + rng.normal(scale=0.1, size=200)
        rows.append(
            pd.DataFrame(
                {
                    "eom": e,
                    "permno": np.arange(200),
                    "a": a,
                    "b": b,
                    "c": rng.normal(size=200),
                    "y": y,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


# Ranks stay inside (-0.5, 0.5), centred, missing at 0.
def test_ranks_are_centred_and_missing_is_zero(panel):
    p = panel.copy()
    p.loc[0, "a"] = np.nan
    x = prep.rank_features(p, ["a", "b"])
    assert x.min() > -0.5 and x.max() < 0.5
    assert x[0, 0] == 0.0
    assert abs(x[:, 1].mean()) < 1e-6


# Each month's weights sum to one.
def test_month_weights_sum_to_one(panel):
    w = prep.month_weights(panel)
    assert np.allclose(pd.Series(w).groupby(panel["eom"]).sum(), 1.0)


# EB ridge recovers the signs of the true slopes and shrinks noise.
def test_group_ridge_recovers_signs(panel):
    x = prep.rank_features(panel, ["a", "b", "c"])
    w = prep.month_weights(panel)
    s = ridge.stats(x, panel["y"].to_numpy(), w, panel["eom"].nunique())
    fit = ridge.empirical_bayes(s, np.array([0, 1, 2]))
    assert fit.theta[0] > 0 > fit.theta[1]
    assert abs(fit.theta[2]) < abs(fit.theta[0])
    assert 0 < fit.df <= 3
    assert ridge.scaled(s, fit, 4.0).df < fit.df


# Inference is n/a below twelve months, never an infinite t (X6).
def test_no_inference_below_twelve_months():
    assert evaluate.mean_t([0.05] * 11) is None
    assert evaluate.mean_t([0.01, 0.02] * 6)["n"] == 12


# The 1-SE rule picks the heaviest penalty within one SE of the best.
def test_one_se_prefers_heavier_penalty():
    idx = pd.date_range("2019-01-31", periods=24, freq="ME")
    rng = np.random.default_rng(1)
    base = rng.normal(0.03, 0.05, 24)
    scores = {
        0.25: pd.Series(base + 0.001, idx),
        1.0: pd.Series(base, idx),
        4.0: pd.Series(base - 0.001, idx),
    }
    assert evaluate.one_se(scores) == 4.0


# A -100% day keeps the label at -100%, never dropped (X6).
def test_minus_one_hundred_percent_label_kept():
    days = data.sessions("2019-01-01", "2019-03-31")
    eom = pd.Timestamp("2019-01-31")
    p = pd.DataFrame({"eom": [eom], "permno": [1]})
    d = pd.DataFrame({"permno": 1, "date": days, "daily_return": 0.0})
    s0 = data.formation_days([eom], days).iat[0]
    d.loc[d["date"] == days[days.get_loc(s0) + 2], "daily_return"] = -1.0
    lab = data.daily_labels(p, d, (5,), cut=pd.Timestamp("2019-03-31"))
    assert lab["y5"].iat[0] < -0.99


# A label whose window ends after the cutoff is blank.
def test_labels_after_cutoff_are_blank():
    days = data.sessions("2020-11-01", "2020-12-31")
    eom = pd.Timestamp("2020-11-30")
    p = pd.DataFrame({"eom": [eom], "permno": [1]})
    d = pd.DataFrame({"permno": 1, "date": days, "daily_return": 0.001})
    lab = data.daily_labels(p, d, (21, 42), cut=pd.Timestamp("2020-12-31"))
    assert np.isfinite(lab["y21"].iat[0]) and np.isnan(lab["y42"].iat[0])


# The formation day is the session after the eom: t -> t+1.
def test_formation_is_next_session():
    days = data.sessions("2019-05-01", "2019-06-30")
    assert data.formation_days(["2019-05-31"], days).iat[0] == pd.Timestamp("2019-06-03")


# The hierarchy shares evidence: a family of weak same-sign signals.
def test_hierarchical_ridge_pools_a_family():
    rng = np.random.default_rng(3)
    n, t = 200, 40
    common = rng.normal(size=n * t)
    x = np.column_stack(
        [common + rng.normal(size=n * t) for _ in range(5)]
        + [rng.normal(size=n * t) for _ in range(5)]
    )
    x = (x - x.mean(0)) / x.std(0) / 4
    y = 0.01 * x[:, :5].sum(1) + rng.normal(scale=0.1, size=n * t)
    groups = np.array([0] * 5 + [1, 2, 3, 4, 5])
    s = ridge.loadings(groups, ridge.orientations(x, groups))
    z = ridge.hierarchical(x, s)
    w = np.full(n * t, 1 / n)
    st = ridge.stats(z, y, w, t)
    lam = ridge.penalties(10.0, 6, 10)
    theta = np.linalg.solve(st.xx + np.diag(lam), st.xy)
    implied = s @ theta[:6] + theta[6:]
    assert (implied[:5] > 0).all()
    assert np.abs(implied[:5]).mean() > 3 * np.abs(implied[5:]).mean()


# The residual target has no exposure to the factors it removed.
def test_residual_target_removes_exposures():
    from fiam.v4b.forecast import targets

    rng = np.random.default_rng(4)
    rows = []
    for e in pd.date_range("2016-01-31", periods=3, freq="ME"):
        f = pd.DataFrame({c: rng.normal(size=300) for c in targets.EXPOSURES.values()})
        f["eom"], f["me"], f["gics"] = e, rng.uniform(500, 5000, 300), 45102010.0
        f["y"] = 0.05 * f["ret_12_1"].rank(pct=True) + rng.normal(scale=0.05, size=300)
        rows.append(f)
    p = pd.concat(rows, ignore_index=True)
    res, fac = targets.residual(p, "y")
    z = targets.zrank(p, "ret_12_1")
    w = np.sqrt(p["me"])
    assert abs((w * z * res).sum() / (w * z * z).sum()) < 1e-8
    assert (fac["momentum"] > 0).all()


# Dividends: a month's missing total-return gap is added back.
def test_dividends_added_back(monkeypatch, tmp_path):
    days = data.sessions("2019-01-01", "2019-01-31")
    d = pd.DataFrame({"permno": 1, "date": days, "daily_return": 0.0})
    panel = pd.DataFrame({"permno": [1], "eom": [pd.Timestamp("2019-01-31")], "ret": [0.01]})
    path = tmp_path / "p.parquet"
    panel.to_parquet(path)
    monkeypatch.setattr(data, "PANEL", path)
    out = data.with_dividends(d)
    assert abs(np.prod(1 + out["daily_return"]) - 1.01) < 1e-3


# Training rows end before the test year's first formation (purge).
def test_split_purges_labels_crossing_the_boundary():
    from fiam.v4b.forecast import initial_plan

    eoms = pd.date_range("2015-01-31", "2017-11-30", freq="ME")
    u = pd.DataFrame({"eom": eoms})
    days = data.sessions("2015-01-01", "2018-03-31")
    u["s0"] = data.formation_days(eoms, days).to_numpy()
    u["end21"] = [days[days.get_loc(s) + 21] for s in u["s0"]]
    train, test = initial_plan.split(u, 2017, "end21")
    assert u.loc[train, "end21"].max() < u.loc[test, "s0"].min()
    assert u.loc[test, "eom"].min() == pd.Timestamp("2016-12-31")
