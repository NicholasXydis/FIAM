# E6 two-step construction (D18) on a synthetic formation; no data folder needed.

import numpy as np
import pandas as pd
import pytest

from fiam.v4b.engine import optimize
from fiam.v4b.engine.mandate import load as load_mandate
from fiam.v4b.risk import model as risk_model

N = 1500


# 1,500 liquid names over 10 sectors; forecasts uncorrelated with beta.
@pytest.fixture
def formation():
    rng = np.random.default_rng(1)
    names = pd.Index(range(N), name="permno")
    sectors = [f"s_{i}" for i in range(10)]
    styles = ["size", "value", "momentum", "profitability", "investment"]
    cols = ["mkt", *sectors, *styles]
    B = pd.DataFrame(0.0, index=names, columns=cols)
    B["mkt"] = rng.normal(1.0, 0.3, N).clip(0.2, 2.5)
    sector_id = np.arange(N) % 10
    for i, s in enumerate(sectors):
        B.loc[sector_id == i, s] = 1.0
    for c in styles:
        B[c] = rng.normal(size=N)
    diag = [0.00014] + [0.00004] * 10 + [0.000015, 0.000008, 0.000015, 0.000008, 0.000004]
    F = pd.DataFrame(np.diag(diag), index=cols, columns=cols)
    me = pd.Series(np.exp(rng.normal(8.5, 1.0, N)) + 600.0, index=names)
    month = pd.DataFrame({"sector": [str(i) for i in sector_id], "long_ok": True, "short_ok": True, "me": me},
                         index=names)
    snap = {"B": B, "F": F * 21, "F1": F, "d": pd.Series(np.full(N, 0.0004), index=names), "beta": B["mkt"],
            "sxx": 0.5, "month": month, "horizon": 21}
    return optimize.Formation(
        eom=pd.Timestamp("2019-12-31"),
        mu=pd.Series(rng.normal(0, 0.01, N), index=names),
        snap=snap,
        adv=pd.Series(np.full(N, 5e7), index=names),
        half_spread=pd.Series(np.full(N, 0.0005), index=names),
        borrow=pd.Series(np.full(N, 0.005), index=names),
        coverage=pd.Series(1.0, index=names),
        nyse_me=me.iloc[::3],  # a third of the names are "NYSE"
    )


def step(weighting="vw"):
    return optimize.Step("E6t", support="twostep", weighting=weighting, trade_costs=True, beta_penalty=True,
                         bands=True, borrow_term=True)


def deciles(f, weighting="vw"):
    c = optimize._candidates(f, load_mandate())
    return optimize.hhrz_deciles(c, f.nyse_me, weighting)[1]


# Step 1 picks the top decile long and the bottom decile short; signs follow.
def test_selection_is_the_decile_sort_with_fixed_signs(formation):
    w, log = optimize.build_book(formation, load_mandate(), step())
    assert w is not None, log
    dec = deciles(formation)
    assert set(dec.loc[w[w > 0].index]) == {9}
    assert set(dec.loc[w[w < 0].index]) == {0}
    assert log["selected"] == len(w) and 200 <= len(w) <= 440


# Breakpoints come from each sector's NYSE names (vw): within a sector, a
# tenth of its NYSE names sits in the top decile, and every name above that
# sector's NYSE 90th percentile does too.
def test_vw_breakpoints_are_nyse_within_sector(formation):
    c = optimize._candidates(formation, load_mandate())
    _, dec = optimize.hhrz_deciles(c, formation.nyse_me, "vw")
    for _, g in c.groupby("sector"):
        nyse_mu = g.loc[g.index.intersection(formation.nyse_me.index), "mu"]
        assert (dec.loc[nyse_mu.index] == 9).mean() == pytest.approx(0.1, abs=0.03)
        assert dec.loc[g.index[g["mu"] > nyse_mu.quantile(0.9)]].eq(9).all()


# Every sector has both a long and a short side after step 1 (lesson 45).
def test_every_sector_is_two_sided(formation):
    w, log = optimize.build_book(formation, load_mandate(), step())
    assert w is not None, log
    side = formation.snap["month"].loc[w.index, "sector"]
    assert side[w > 0].nunique() == side[w < 0].nunique() == 10


# ew drops names below the NYSE 20th percentile of me before sorting.
def test_ew_drops_micro(formation):
    c = optimize._candidates(formation, load_mandate())
    kept, _ = optimize.hhrz_deciles(c, formation.nyse_me, "ew")
    assert kept["me"].min() >= formation.nyse_me.quantile(0.2)
    assert len(kept) < len(c)


# Step 2 holds the return floor, the gross, the beta band and the net band.
@pytest.mark.parametrize("weighting", ["vw", "ew"])
def test_floor_gross_beta_net(formation, weighting):
    m = load_mandate()
    w, log = optimize.build_book(formation, m, step(weighting))
    assert w is not None, log
    assert log["rho"] == 0.9
    assert log["mu_w"] >= 0.9 * log["mu_ref"] - 1e-6
    assert w.abs().sum() == pytest.approx(log["ladder_gross"], abs=1e-4)
    assert abs(log["pred_beta"]) <= m.policy.beta_band + 1e-6
    assert abs(w.sum()) <= m.hard.net_band + 1e-9
    assert w.abs().max() <= m.policy.position_cap + 1e-6


# The risk step lowers predicted vol against the same names at reference-like
# weights with the floor only (rho = 1 forces the paper's expected return).
def test_reweighting_lowers_risk_at_the_floor(formation):
    m = load_mandate()
    w9, _ = optimize.build_book(formation, m, step())
    w_eq = w9.apply(np.sign) * (w9.abs().sum() / len(w9))
    assert risk_model.vol(formation.snap, w9) < risk_model.vol(formation.snap, w_eq)


# Hysteresis: a held long still in decile 8 stays; one that fell to the middle goes.
def test_hysteresis_keeps_d9_holders_only(formation):
    dec = deciles(formation)
    stay = dec.index[dec == 8][0]
    go = dec.index[dec == 5][0]
    formation.w_pre = pd.Series({stay: 0.004, go: 0.004})
    w, log = optimize.build_book(formation, load_mandate(), step())
    assert w is not None, log
    assert stay in w.index and w[stay] > 0
    assert go not in w.index


# Entries are trimmed so held plus target names fit the union room.
def test_union_room_with_many_held(formation):
    m = load_mandate()
    dec = deciles(formation)
    held = dec.index[(dec > 1) & (dec < 8)][:250]  # 250 held names that all must exit
    formation.w_pre = pd.Series(0.002, index=held)
    w, log = optimize.build_book(formation, m, step())
    assert w is not None, log
    assert log["trimmed"] > 0 and log["union_fits"]
    assert len(set(held) | set(w.index)) <= m.hard.names_max - optimize.UNION_HEADROOM


# When the union room would leave fewer than names_min, names_min wins (hard rule).
def test_names_min_beats_union_room(formation):
    m = load_mandate()
    dec = deciles(formation)
    formation.w_pre = pd.Series(0.002, index=dec.index[(dec > 1) & (dec < 8)][:400])
    w, log = optimize.build_book(formation, m, step())
    assert w is not None, log
    assert len(w) >= m.hard.names_min and not log["union_fits"]
