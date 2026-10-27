# Book construction on synthetic data: rules, costs, alignment, drift.

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal.construct import book, costs, inputs, optimizer


# A synthetic formation: 600 names, sectors, styles, betas, liquidity.
def fake(n=600, seed=0):
    rng = np.random.default_rng(seed)
    x = pd.DataFrame(index=pd.Index(range(1, n + 1), name="permno"))
    x["me"] = rng.lognormal(8, 1, n) + 600
    x["prc"] = rng.uniform(10, 200, n)
    x["dolvol_126d"] = rng.lognormal(18, 1, n)
    x["new_long"] = x["new_short"] = True
    x["squeezed"] = x["crowded"] = False
    x["sector"] = rng.choice(["G10", "G20", "G30", "G40"], n)
    for k in (*inputs.NEUTRAL, *inputs.CAPPED):
        x[k] = rng.standard_normal(n)
    x["welch"] = 1 + 0.3 * rng.standard_normal(n)
    x["beta_60m"] = 1 + 0.3 * rng.standard_normal(n)
    x["dimson"] = 1 + 0.4 * rng.standard_normal(n)
    x["borrow"] = 0.003
    x["half_spread"] = 0.0005
    x["sigma_d"] = 0.02
    x["adv_cost"] = x["dolvol_126d"]
    alpha = pd.Series(rng.standard_normal(n) * 0.001, index=x.index)
    loadings = pd.get_dummies(x["sector"], dtype=float).join(x[list(inputs.CAPPED)])
    cov = np.eye(loadings.shape[1]) * 0.0004
    spec = np.full(n, 0.003)
    return x, alpha, loadings, np.linalg.cholesky(cov), spec


# The solved book holds every rule: net, gross, betas, sectors, caps.
def test_solution_holds_every_rule():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.7, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001)
    w, step, _ = optimizer.optimise(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, True)
    assert w is not None and step.startswith("none")
    assert abs(w.sum()) < 1e-3 and w.abs().sum() == pytest.approx(1.7, abs=1e-3)
    for b in ("welch", "dimson", *inputs.NEUTRAL):
        assert abs(x.loc[w.index, b] @ w) < 1e-3
    nets = w.groupby(x.loc[w.index, "sector"]).sum()
    assert (nets.abs() <= 0.01 + 1e-3).all()
    assert (w <= optimizer.LONG_CAP + 1e-6).all() and (w >= -optimizer.SHORT_CAP - 1e-6).all()
    assert (w.abs() >= optimizer.MIN_WEIGHT - 1e-6).all() and len(w) <= optimizer.NAMES_MAX
    assert abs(x.loc[w.index, "beta_60m"] @ w) <= optimizer.MONTHLY_BAND + 1e-3


# Longs come from the top decile of alpha and shorts from the bottom.
def test_new_positions_come_from_the_pool():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.0, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001)
    w = optimizer.solve(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, pool=0.2)
    pct = alpha.rank(pct=True)
    assert (pct[w[w > 0].index] > 0.8).all() and (pct[w[w < 0].index] <= 0.2).all()


# A name without leave to add (squeezed, crowded) may only shrink.
def test_screened_names_only_shrink():
    x, alpha, loadings, chol, spec = fake()
    x["squeezed"] = False
    worst = alpha.idxmin()
    x.loc[worst, "squeezed"] = True
    prev = pd.Series({worst: -0.002})
    side, lo, hi, a, room = optimizer.bounds(x, alpha, prev, optimizer.NAV, 0.2)
    i = x.index.get_loc(worst)
    assert lo[i] == pytest.approx(-0.002) and hi[i] == 0.0


# A held name above its cap shrinks toward it, as fast as allowed.
def test_held_above_cap_shrinks():
    x, alpha, *_ = fake()
    best = alpha.idxmax()
    x.loc[best, "dolvol_126d"] = x.loc[best, "adv_cost"] = 1e8
    prev = pd.Series({best: 0.05})
    side, lo, hi, a, room = optimizer.bounds(x, alpha, prev, optimizer.NAV, 0.2)
    i = x.index.get_loc(best)
    assert hi[i] == pytest.approx(max(0.015, 0.05 - room[i])) and hi[i] < 0.05


# A held name with no ADV may still trade, on the 5th-percentile floor.
def test_missing_adv_still_trades():
    x, alpha, *_ = fake()
    name = alpha.idxmax()
    x.loc[name, "dolvol_126d"] = np.nan
    x.loc[name, "adv_cost"] = 1e7
    side, lo, hi, a, room = optimizer.bounds(x, alpha, pd.Series({name: 0.01}), optimizer.NAV, 0.2)
    i = x.index.get_loc(name)
    cap = min(optimizer.LONG_CAP, optimizer.LONG_ADV * 1e7 / optimizer.NAV)
    assert room[i] > 0 and hi[i] == pytest.approx(max(cap, 0.01 - room[i])) and lo[i] == 0.0


# Alignment leaves no sector, size, value or beta exposure in alpha.
def test_alignment_is_orthogonal():
    x, alpha, *_ = fake()
    aligned = book.align(alpha, x)
    design = pd.get_dummies(x["sector"], dtype=float).join(x[[*inputs.NEUTRAL, "welch", "dimson"]])
    assert np.abs(design.to_numpy().T @ aligned.to_numpy()).max() < 1e-12


# Dollar costs: sale fees, commission, spread, whole-month impact.
def test_dollar_costs_by_hand():
    x = pd.DataFrame({"prc": [50.0, 50.0], "half_spread": [0.001, 0.001], "sigma_d": [0.02, 0.02],
                      "adv_cost": [1e7, 1e7]}, index=[1, 2])  # fmt: skip
    moved = pd.Series({1: 1e6, 2: -1e6})
    got = costs.dollars(moved, x, pd.Series({1: 4e6, 2: 1e6}))
    shares = 1e6 / 50
    impact_1 = 0.02 * np.sqrt(4e6 / 1e7) * 1e6
    impact_2 = 0.02 * np.sqrt(1e6 / 1e7) * 1e6
    fee = costs.SEC_FEE * 1e6 + min(costs.TAF * shares, costs.TAF_CAP)
    # Commission is 0.5 cents a share.
    assert got[1] == pytest.approx(0.005 * shares + 1000 + impact_1)
    assert got[2] == pytest.approx(fee + 0.005 * shares + 1000 + impact_2)


# A name missing from the frame trades at costly values, never free.
def test_conservative_fill():
    x = pd.DataFrame({"prc": np.arange(1.0, 21.0), "half_spread": np.linspace(1e-4, 2e-3, 20),
                      "sigma_d": np.linspace(0.01, 0.05, 20), "adv_cost": np.arange(1, 21) * 1e6,
                      "borrow": 0.003}, index=range(1, 21))  # fmt: skip
    got = costs.conservative(x, [99])
    assert got.loc[99, "prc"] == pytest.approx(10.5)
    assert got.loc[99, "half_spread"] == pytest.approx(2e-3)
    assert got.loc[99, "sigma_d"] == pytest.approx(x["sigma_d"].quantile(0.9))
    assert got.loc[99, "adv_cost"] == pytest.approx(x["adv_cost"].quantile(0.05))
    assert got.loc[1:20].equals(x)


# Borrow tiers: 0.3% under 5%, then 1%, 3% and 8%.
def test_borrow_tiers():
    got = inputs.borrow_tier(pd.Series([0.0, 0.049, 0.05, 0.1, 0.2, 0.5])).tolist()
    assert got == [0.003, 0.003, 0.01, 0.03, 0.08, 0.08]


# Drift: each weight grows with its return, the NAV with the book's.
def test_drift():
    w = pd.Series({1: 0.5, 2: -0.5})
    days = pd.bdate_range("2019-01-01", periods=3)
    r = pd.DataFrame({1: [0.1, 0.0, 0.0], 2: [0.0, 0.0, 0.0]}, index=days)
    got = book.drift(w, r, days[0] - pd.Timedelta(days=1), days[-1])
    assert got[1] == pytest.approx(0.55 / 1.05) and got[2] == pytest.approx(-0.5 / 1.05)


# The largest gross every rule allows is feasible, in 0.01 steps.
def test_largest_gross_is_feasible():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.7, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001)
    top = optimizer.largest_gross(x, alpha, pd.Series(dtype=float), s, 1.7678)
    assert 0 < top <= 1.7678 and top * 100 == pytest.approx(round(top * 100))
    s = optimizer.replace(s, gross=top)
    w = optimizer.solve(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, pool=0.2)
    assert w is not None and w.abs().sum() == pytest.approx(top, abs=1e-3)
    assert optimizer.largest_gross(x, alpha, pd.Series(dtype=float), s, 1.2) == 1.2
    # Under 1.00 counts as none: the solve then takes the relax ladder.
    assert optimizer.largest_gross(x, alpha, pd.Series(dtype=float), s, 0.5) is None


# A book left net long by covers returns to neutral past a cost budget.
def test_shocked_book_returns_to_neutral():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.6, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001)
    w, *_ = optimizer.optimise(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, True)
    prev = w.where(w > 0, w * 0.4)
    tight = optimizer.replace(s, cost_budget=1e-7)
    got, step, used = optimizer.optimise(x, alpha, loadings, chol, spec, prev, tight, False)
    assert prev.sum() > 0.4 and got is not None and step.startswith("no budget")
    assert abs(got.sum()) < 1e-3 and used.cost_budget is None and used.participation


# A partial step: the blend moved onto every rule, nearer than optimum.
def test_partial_projection():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.6, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001)
    empty = pd.Series(dtype=float)
    prev, *_ = optimizer.optimise(x, -alpha.sample(frac=1, random_state=1).set_axis(alpha.index),
                                 loadings, chol, spec, empty, s, True)  # fmt: skip
    w, *_ = optimizer.optimise(x, alpha, loadings, chol, spec, empty, s, True)
    half = optimizer.replace(s, speed=0.5, participation=False)
    got = book.partial(w, prev, x, half, alpha)
    assert abs(got.sum()) < 1e-3 and got.abs().sum() == pytest.approx(w.abs().sum(), abs=1e-3)
    for b in ("welch", "dimson", *inputs.NEUTRAL):
        assert abs(x.loc[got.index, b] @ got) < 1e-3
    assert abs(x.loc[got.index, "beta_60m"] @ got) <= optimizer.MONTHLY_BAND + 1e-3
    nets = got.groupby(x.loc[got.index, "sector"]).sum()
    assert (nets.abs() <= 0.01 + 1e-3).all() and len(got) <= optimizer.NAMES_MAX
    assert (got.abs() >= optimizer.MIN_WEIGHT - 1e-6).all()
    blend = (prev.reindex(x.index).fillna(0.0) + w.reindex(x.index).fillna(0.0)) / 2
    far = (w.reindex(x.index).fillna(0.0) - blend).abs().sum()
    assert (got.reindex(x.index).fillna(0.0) - blend).abs().sum() < far / 2
    assert book.partial(w, prev, x, s, alpha) is w


# HAR fits on the 24 month ends before T's month, each once.
@pytest.mark.parametrize("T", ["2019-04-30", "2019-06-28", "2019-03-01"])
def test_har_month_ends(T):
    from fiam.vfinal.construct import risk

    ends = risk.har_ends(T)
    month = pd.Timestamp(T) + pd.offsets.MonthEnd(0)
    assert len(set(ends)) == 24 and ends == sorted(ends)
    assert ends[-1] == month - pd.offsets.MonthEnd(1)
    assert ends[0] == month - pd.offsets.MonthEnd(24)


# Betas come from the total returns given, never a day after T.
def test_total_betas(monkeypatch):
    from fiam.vfinal import data
    from fiam.vfinal.construct import risk

    days = pd.bdate_range("2018-01-01", periods=300)
    m = pd.Series(np.random.default_rng(1).normal(0, 0.01, 300), index=days)
    monkeypatch.setattr(data, "rf_daily", lambda d, by=None: pd.Series(0.0, index=d))
    monkeypatch.setattr(data, "market_daily", lambda d: m.reindex(d))
    returns = pd.DataFrame({7: 1.5 * m, 8: 0.5 * m})
    T = days[-2]
    returns.loc[days[-1]] = [5.0, -5.0]
    got = risk.total_betas(returns, T, [7, 8])
    assert got.loc[7].tolist() == pytest.approx([1.5, 1.5])
    assert got.loc[8].tolist() == pytest.approx([0.5, 0.5])


# After 2025 a month compounds to the panel's total; big δ on its fall.
def test_with_delta(monkeypatch):
    from fiam.vfinal import data
    from fiam.vfinal.construct import risk

    days = pd.bdate_range("2026-02-02", "2026-02-27")
    raw = pd.DataFrame({7: 0.0, 8: 0.001}, index=days)
    raw.loc[days[5], 7] = -0.20
    panel = pd.DataFrame({"permno": [7, 8], "eom": pd.Timestamp("2026-02-28"),
                          "ret": [0.05, 0.03], "first_close": days[-1]})  # fmt: skip
    monkeypatch.setattr(data, "calendar", lambda: pd.Series(0, index=days))
    monkeypatch.setattr(data, "panel", lambda *a, **k: panel)
    none = pd.DataFrame({"permno": [], "exit_date": pd.Series(dtype="datetime64[ns]")})
    monkeypatch.setattr(data, "exits", lambda p: none)
    got = risk.with_delta(raw)
    assert (1 + got).prod().tolist() == pytest.approx([1.05, 1.03])
    assert got.loc[days[5], 7] == pytest.approx(0.05) and (got[7].drop(days[5]) == 0).all()
    assert got.loc[days[-1], 8] > got.loc[days[0], 8]


# A side's pool widens until 130 names may take it.
def test_short_pool_widens_until_130():
    x, alpha, *_ = fake(n=2000)
    x["adv_cost"] = x["dolvol_126d"] = 1e9
    pct = alpha.rank(pct=True)
    x.loc[pct.index[pct <= 0.10][:120], "squeezed"] = True
    pools = optimizer.start_pools(x, alpha, pd.Series(dtype=float), optimizer.NAV)
    assert pools == (0.10, 0.15)


# Exam design 2: the same optimiser with a name cap of 275.
def test_name_cap_275():
    x, alpha, loadings, chol, spec = fake(n=2000)
    s = optimizer.Settings(gross=1.6, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001,
                           names_max=275)  # fmt: skip
    w, *_ = optimizer.optimise(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, True)
    assert w is not None and 0 < len(w) <= 275


# Each side scaled to half the gross; an empty side stays empty.
def test_rescale():
    got = optimizer.rescale(pd.Series({1: 0.3, 2: 0.1, 3: -0.2}), 1.0)
    assert got.tolist() == pytest.approx([0.375, 0.125, -0.5])
    assert optimizer.rescale(pd.Series({1: 0.2}), 1.0).tolist() == pytest.approx([0.5])


# A neutral design holds high-vol and liquidity at 0, as size and value.
def test_neutral_styles_held_at_zero():
    x, alpha, loadings, chol, spec = fake()
    s = optimizer.Settings(gross=1.6, ridge=30, risk_lambda=0.5, style_cap=0.5, norm=0.001,
                           neutral_styles=("high_ivol", "liquidity"))  # fmt: skip
    w, step, _ = optimizer.optimise(x, alpha, loadings, chol, spec, pd.Series(dtype=float), s, True)
    for k in ("high_ivol", "liquidity"):
        assert abs(x.loc[w.index, k] @ w) <= 1e-3


# The exam's halves are reported beside it, months split at 2018-12.
def test_exam_halves():
    from fiam.vfinal.construct import exam

    days = pd.bdate_range("2016-12-30", "2020-12-31")
    rng = np.random.default_rng(7)
    daily = pd.DataFrame({"ret": rng.normal(0.0003, 0.004, len(days)), "rf": 0.0001},
                         index=days)  # fmt: skip
    halves = exam.by_period(daily)
    assert halves["2017-2018"]["months"] == 23 and halves["2019-2020"]["months"] == 24
    assert exam.scores(daily)["months"] == 47
