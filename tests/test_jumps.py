# The jump screen on synthetic returns: no later day.

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal.construct import exam, jumps, optimizer
from tests.test_construct import fake


# Calm daily returns for three names, a calm market, 400 sessions.
def calm(seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2018-01-01", periods=400)
    r = pd.DataFrame(rng.normal(0, 0.01, (400, 3)), index=days, columns=[1, 2, 3])
    return r, pd.Series(rng.normal(0, 0.005, 400), index=days)


# Lee and Mykland's 1% value for 252 daily tests, from their formula.
def test_critical_value():
    assert jumps.critical() == pytest.approx(5.3636, abs=1e-3)
    assert jumps.critical(alpha=0.05) < jumps.critical()


# A planted rise is an up-jump, a fall a down-jump; the market's is not.
def test_planted_jumps_and_market_moves():
    r, m = calm()
    T = r.index[-1]
    base = jumps.counts(r, m, T, [1, 2, 3])
    r.loc[r.index[-10], 1] += 0.15
    r.loc[r.index[-20], 2] -= 0.15
    m.loc[r.index[-30]] += 0.15
    r.loc[r.index[-30]] += 0.15
    got = jumps.counts(r, m, T, [1, 2, 3]) - base
    assert got.loc[1, "jump_up"] == 1 and got.loc[1, "jump_down"] == 0
    assert got.loc[2, "jump_down"] == 1 and got.loc[2, "jump_up"] == 0
    assert got.loc[3].sum() == 0


# B_d leaves out day d: a move just past the line is a jump only so.
def test_bipower_leaves_out_the_day():
    days = pd.bdate_range("2018-01-01", periods=120)
    e = pd.DataFrame({1: np.where(np.arange(120) % 2, 0.01, -0.01)}, index=days)
    e.iloc[-1, 0] = 0.055
    got = jumps.counts(e, pd.Series(0.0, index=days), days[-1], [1])
    assert got.loc[1, "jump_up"] == 1


# Counts at T never change when any later day changes.
def test_counts_read_no_later_day():
    r, m = calm(1)
    T = r.index[300]
    before = jumps.counts(r, m, T, [1, 2, 3])
    r.loc[r.index > T] = 0.5
    m.loc[m.index > T] = -0.3
    pd.testing.assert_frame_equal(jumps.counts(r, m, T, [1, 2, 3]), before)


# Only the 252 sessions up to T count; an older jump drops out.
def test_window_is_a_year():
    r, m = calm(2)
    r.loc[r.index[-300], 1] += 0.2
    assert jumps.counts(r, m, r.index[-1], [1])["jump_up"].iloc[0] == 0
    assert jumps.counts(r, m, r.index[-200], [1])["jump_up"].iloc[0] == 1


# Flags: a count at least max(1, the 90th percentile); zeros never.
def test_flags_top_decile_and_at_least_one():
    c = pd.DataFrame({"jump_up": [0] * 18 + [1, 3], "jump_down": [0] * 20})
    got = jumps.flags(c)
    assert got["jumpy_up"].sum() == 2 and not got["jumpy_down"].any()
    c = pd.DataFrame({"jump_up": [2] * 20, "jump_down": [0] * 20})
    assert jumps.flags(c)["jumpy_up"].all()
    c = pd.DataFrame({"jump_up": [0] * 19 + [3], "jump_down": [0] * 19 + [1]})
    got = jumps.flags(c)
    assert got["jumpy_up"].sum() == 1 and got["jumpy_down"].sum() == 1


# The screen stops a new short or long; a held name may stay or shrink.
def test_screen_blocks_only_new_entries():
    x, alpha, *_ = fake()
    x["jumpy_up"], x["jumpy_down"] = False, False
    short, long = alpha.idxmin(), alpha.idxmax()
    x.loc[short, "jumpy_up"], x.loc[long, "jumpy_down"] = True, True
    empty = pd.Series(dtype=float)
    i, j = x.index.get_loc(short), x.index.get_loc(long)
    _, lo, hi, *_ = optimizer.bounds(x, alpha, empty, 1e9, 0.1)
    assert lo[i] < 0 and hi[j] > 0
    _, lo, hi, *_ = optimizer.bounds(x, alpha, empty, 1e9, 0.1, screen=True)
    assert lo[i] == 0 and hi[j] == 0
    held = pd.Series({short: -0.002, long: 0.002})
    _, lo, hi, *_ = optimizer.bounds(x, alpha, held, 1e9, 0.1, screen=True)
    assert -0.002 - 1e-12 <= lo[i] < 0 and 0 < hi[j] <= 0.002 + 1e-12


# Design 15 is design 1 with the screen; a tie goes to design 1.
def test_design_15_is_design_1_screened():
    s = {"settings": {"risk_lambda": 3.0, "ridge": 30.0, "style_cap": 0.5, "sector_band": 0.01,
                      "beta_band": 0.0, "neutral_band": 0.0, "cost_budget": 0.001,
                      "participation": True, "nav": 1e9, "gross": 1.0, "norm": 1.0},
         "a4_rate": 0.4, "margin": 0.08}  # fmt: skip
    one, screened = (exam.settings_for(k, s)(None, None, 1.7678) for k in (1, 15))
    assert screened.jump_screen and not one.jump_screen
    assert optimizer.replace(screened, jump_screen=False) == one
    assert exam.DESIGNS[15] == exam.DESIGNS[1]
    assert exam.winner({k: {"ir": 0.2} for k in (1, 15)}) == 1
