# The QP controller on synthetic formations (R§5); no data folder needed.

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.engine import optimize
from fiam.v4b.engine.mandate import load as load_mandate


# A synthetic liquid universe: 400 names over 10 sectors, known mu and betas.
@pytest.fixture
def formation():
    rng = np.random.default_rng(0)
    names = pd.Index(range(400), name="permno")
    mu = pd.Series(rng.normal(0, 0.005, 400), index=names)
    mu.iloc[:40] += 0.01
    mu.iloc[-40:] -= 0.01
    sectors = [f"s_{i}" for i in range(10)]
    styles = ["size", "value", "momentum", "profitability", "investment"]
    cols = ["mkt", *sectors, *styles]
    B = pd.DataFrame(0.0, index=names, columns=cols)
    B["mkt"] = rng.normal(1.0, 0.3, 400)
    sector_id = np.arange(400) % 10
    for i, s in enumerate(sectors):
        B.loc[sector_id == i, s] = 1.0
    for c in styles:
        B[c] = rng.normal(size=400)
    diag = [0.00014] + [0.00004] * 10 + [0.000015, 0.000008, 0.000015, 0.000008, 0.000004]
    F = pd.DataFrame(np.diag(diag), index=cols, columns=cols)
    month = pd.DataFrame(
        {
            "sector": [str(i) for i in sector_id],
            "long_ok": True,
            "short_ok": True,
            "me": np.full(400, 5000.0),
        },
        index=names,
    )
    snap = {
        "B": B,
        "F": F * 21,
        "F1": F,
        "d": pd.Series(np.full(400, 0.0004), index=names),
        "beta": B["mkt"],
        "sxx": 0.5,
        "month": month,
    }
    common = pd.Series(np.full(400, 1.0), index=names)
    return optimize.Formation(
        eom=pd.Timestamp("2019-12-31"),
        mu=mu,
        snap=snap,
        adv=pd.Series(np.full(400, 5e7), index=names),
        half_spread=pd.Series(np.full(400, 0.0005), index=names),
        borrow=pd.Series(np.full(400, 0.005), index=names),
        coverage=common,
    )


# Stage-2 books obey gross, caps, signs, minima and near-zero net.
def test_signed_book_obeys_rules(formation):
    m = load_mandate()
    step = optimize.Step("test", names=200)
    w, log = optimize.build_book(formation, m, step)
    assert w is not None, log
    assert w.abs().sum() == pytest.approx(m.policy.target_gross, abs=1e-4)
    assert w.abs().max() <= m.policy.position_cap + 1e-6
    assert w.abs().min() >= m.policy.position_min - 1e-6
    assert abs(w.sum()) <= 0.01
    assert (w > 0).sum() + (w < 0).sum() == len(w)
    # Longs are forecast-positive names on average; shorts the reverse.
    assert formation.mu[w[w > 0].index].mean() > formation.mu[w[w < 0].index].mean()


# Shorts only come from the short-eligible pool ($500m floor, D3).
def test_shorts_respect_floor_eligibility(formation):
    m = load_mandate()
    formation.snap["month"].loc[formation.mu.nsmallest(30).index, "short_ok"] = False
    w, log = optimize.build_book(formation, m, optimize.Step("test", names=200))
    assert w is not None, log
    ineligible = set(formation.mu.nsmallest(30).index)
    assert not (set(w[w < 0].index) & ineligible)


# Trade costs in the objective cut turnover against a held book (same support).
def test_trade_costs_reduce_turnover(formation):
    import dataclasses

    m = load_mandate()
    w0, _ = optimize.build_book(formation, m, optimize.Step("base", names=200))
    names, signs = w0.index, np.sign(w0)
    formation.w_pre = w0
    rng = np.random.default_rng(7)
    formation.mu = formation.mu + pd.Series(
        rng.normal(scale=0.002, size=len(formation.mu)), index=formation.mu.index
    )
    free, log_f = optimize.solve_qp(
        formation, m, optimize.Step("free", trade_costs=False), names, signs
    )
    dear = dataclasses.replace(formation, half_spread=formation.half_spread * 50)
    costly, log_c = optimize.solve_qp(
        dear, m, optimize.Step("costly", trade_costs=True), names, signs
    )
    assert free is not None and costly is not None, (log_f, log_c)

    def turn(w):
        return float((w.reindex(names).fillna(0) - w0.reindex(names)).abs().sum())

    assert turn(costly) < turn(free)


# Drift grows winners and shrinks losers, preserving dollar sums.
def test_drift_arithmetic():
    w = pd.Series([0.5, -0.5], index=[1, 2])
    rets = pd.DataFrame({1: [0.10], 2: [0.0]})
    out = optimize.drift(w, rets)
    assert out.loc[1] == pytest.approx(0.55 / 1.05)
    assert out.sum() == pytest.approx((0.55 - 0.5) / 1.05)


# The hurdle pick favours concentration at low IC and breadth at high IC.
def test_hurdle_pick_direction():
    costs = {250: 0.02, 300: 0.019, 450: 0.017}
    low, _ = optimize.hurdle_pick(0.03, costs)
    high, table = optimize.hurdle_pick(0.09, costs)
    assert low == 250
    assert high >= low
    assert table[250]["ic_needed"] < table[450]["ic_needed"]


# Scarce short capacity: gross settles below target instead of violating
# sector/net bands (gross is a ceiling; the Dec-2019 failure mode).
def test_scarce_capacity_settles_below_target_gross(formation):
    m = load_mandate()
    # ADV caps near 0.2% a name: 200 names can fund at most ~40% gross.
    formation.adv = pd.Series(np.full(400, 4e6), index=formation.mu.index)
    w, log = optimize.build_book(formation, m, optimize.Step("test", names=200))
    assert w is not None, log
    assert w.abs().sum() < m.policy.target_gross - 0.2
    assert abs(w.sum()) <= 0.02
    sector_net = w.groupby(formation.snap["month"]["sector"]).sum()
    assert sector_net.abs().max() <= m.policy.sector_band + 0.02


# An impossible gross (caps too small) fails loudly, never fabricates.
def test_infeasible_book_is_none(formation):
    m = load_mandate()
    formation.adv = pd.Series(np.full(400, 1e4), index=formation.mu.index)  # caps ~0
    w, log = optimize.build_book(formation, m, optimize.Step("test", names=200))
    assert w is None
    assert log.get("status") == "no rung within slack tolerance"


def test_sector_level_alpha_does_not_strand_signed_support(formation):
    # Sector means overwhelm stock dispersion. A free-sign solve without
    # bands goes long whole sectors, making the final neutral solve impossible.
    rng = np.random.default_rng(21)
    sector = formation.snap["month"]["sector"].astype(int)
    formation.mu = pd.Series(
        np.where(sector < 5, 0.02, -0.02) + rng.normal(0, 0.001, len(sector)),
        index=sector.index,
    )
    m = load_mandate()
    w, log = optimize.build_book(formation, m, optimize.Step("sector_alpha", names=300))
    assert w is not None, log
    assert 200 <= len(w) <= 500
    assert w.groupby(sector).sum().abs().max() <= 0.01001
    assert abs(formation.snap["beta"].reindex(w.index) @ w) <= 0.02001


def test_enlarges_support_before_reducing_feasible_gross(formation):
    # At 0.5% per-name capacity, a narrow selected book is infeasible at
    # 180% gross, but the broader universe can fund it with the same bands.
    formation.adv[:] = 1e7
    w, log = optimize.build_book(formation, load_mandate(), optimize.Step("test", names=200))
    assert w is not None, log
    assert w.abs().sum() == pytest.approx(1.8, abs=1e-5)
    assert len(w) <= 500


def test_entry_costs_are_per_dollar_return_units(formation):
    m = load_mandate()
    costly = formation.mu.nlargest(40).index.union(formation.mu.nsmallest(40).index)
    formation.half_spread.loc[costly] = 0.5
    names, _, _ = optimize.greedy_support(
        formation, m, optimize.Step("costs", trade_costs=True, names=200)
    )
    # A 50% entry spread overwhelms a 1-2% forecast; the remaining 320 names
    # can fund this book, so these names should never win an entry score.
    assert names.intersection(costly).empty


def test_impact_cost_is_the_five_day_square_root_law():
    # q is a portfolio weight; NAV/(D*ADV) converts dollars to the D-day
    # participation schedule. The 3/2 exponent is the simulator's fill law.
    q, sigma, adv, nav = 0.006, 0.02, 50e6, 1e9
    got = optimize.impact_cost(q, sigma, adv, nav, 1.0)
    want = 1.0 * sigma * np.sqrt(nav / (optimize.EXEC_DAYS * adv)) * q**1.5
    assert got == pytest.approx(want)


def test_impact_quadratic_matches_at_reference_and_is_conservative_above():
    q_ref = 0.006
    sig, adv, nav = np.array([0.02]), np.array([50e6]), 1e9
    c = optimize.impact_quadratic_coef(sig, adv, nav, 1.0, q_ref)
    assert c[0] * q_ref**2 == pytest.approx(
        optimize.impact_cost(q_ref, sig[0], adv[0], nav, 1.0)
    )
    # The proxy is a deliberate over-estimate for larger trades.
    assert c[0] * (2 * q_ref) ** 2 > optimize.impact_cost(
        2 * q_ref, sig[0], adv[0], nav, 1.0
    )


# E5: gross is a ceiling, so a book whose alpha cannot pay its risk stays smaller.
def test_gross_cap_lets_weak_alpha_settle_below_target(formation):
    m = load_mandate()
    formation.mu = formation.mu * 0.02
    w, log = optimize.build_book(formation, m, optimize.Step("e5", names=200, gross_cap=True))
    assert w is not None, log
    assert w.abs().sum() <= m.policy.target_gross + 1e-6
    assert w.abs().sum() < m.policy.target_gross - 0.05


# E5: the beta penalty pulls book beta toward zero inside the hard band.
def test_beta_penalty_shrinks_book_beta(formation):
    m = load_mandate()
    base, _ = optimize.build_book(formation, m, optimize.Step("e3", names=200))
    pen, log = optimize.build_book(formation, m, optimize.Step("e5", names=200, beta_penalty=True))
    assert pen is not None, log
    beta = formation.snap["beta"]
    b0 = abs(float(beta.reindex(base.index) @ base))
    b1 = abs(float(beta.reindex(pen.index) @ pen))
    assert b1 <= b0 + 1e-9
    assert b1 <= m.policy.beta_band + 1e-6


# E5: up-jump variance makes jump-prone shorts smaller than calm ones.
def test_jump_variance_shrinks_jump_prone_shorts(formation):
    m = load_mandate()
    names = formation.mu.index
    formation.p_up = pd.Series(0.02, index=names)
    formation.p_dn = pd.Series(0.02, index=names)
    risky = formation.mu.nsmallest(40).index[::2]
    formation.p_up.loc[risky] = 0.30
    w, log = optimize.build_book(formation, m, optimize.Step("e5", names=200, jump_var=True))
    assert w is not None, log
    shorts = w[w < 0]
    calm = shorts.index.difference(risky)
    hot = shorts.index.intersection(risky)
    assert len(hot) == 0 or shorts[hot].abs().mean() < shorts[calm].abs().mean()


# E5: held names plus new entries must fit the union room (exits and entries
# trade over the same days); held names keep their place, entries are trimmed.
def test_gross_cap_book_fits_union_with_held_names(formation, monkeypatch):
    m = load_mandate()
    monkeypatch.setattr(optimize, "UNION_HEADROOM", m.hard.names_max - 260)
    held = formation.mu.index[100:300]  # middling scores the book would rather swap out
    formation.w_pre = pd.Series(np.where(np.arange(200) % 2 == 0, 0.004, -0.004), index=held)
    w, log = optimize.build_book(formation, m, optimize.Step("e5", names=250, gross_cap=True, trade_costs=False))
    assert w is not None, log
    assert len(set(held) | set(w.index)) <= 260
    assert log["union_fits"]
