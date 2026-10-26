# D21 phase 0a: the gates on synthetic data with known betas (no market data).
# Four 40-session windows (calm 0.6%/day, stressed 2.0%/day, alternating),
# 2,000 stocks with known betas (sd 0.4), 10 industry factors, t(5) residuals,
# 2% missing days; dollar-neutral 400-name books whose true beta is set exactly.

import numpy as np
import pytest

from fiam.v4b.research.e6_gates import HB_BAND, book_beta_gate, leg_return, ols_beta

N, NAMES, WINDOWS, DAYS = 2000, 400, 4, 40
MKT_VOL = (0.006, 0.020, 0.006, 0.020)
REPS = 1000
METHODS = ("hc3",)  # D21 Amendment 2
SIZE_MAX = 0.05 + 2 * np.sqrt(0.05 * 0.95 / REPS)


def world(rng):
    beta = np.clip(1 + 0.4 * rng.standard_normal(N), 0.1, 2.5)
    ind = rng.integers(0, 10, N)
    m = np.concatenate([v * rng.standard_normal(DAYS) for v in MKT_VOL])
    f = 0.008 * rng.standard_normal((len(m), 10))
    e = 0.02 * rng.standard_t(5, (len(m), N)) / np.sqrt(5 / 3)
    r = m[:, None] * beta + f[:, ind] + e
    return beta, m, r


# Dollar-neutral book with true beta exactly `target` (long leg rescaled).
def book(rng, beta, target):
    pick = rng.choice(N, NAMES, replace=False)
    w = np.zeros(N)
    w[pick[: NAMES // 2]], w[pick[NAMES // 2:]] = 0.9 / (NAMES // 2), -0.9 / (NAMES // 2)
    long_b, short_b = beta[w > 0] @ w[w > 0], beta[w < 0] @ w[w < 0]
    w[w > 0] *= (target - short_b) / long_b
    return w


def gapped(rng, r):
    return np.where(rng.random(r.shape) < 0.02, np.nan, r)


WIN = np.repeat(np.arange(WINDOWS), DAYS)


def pass_rate(target, seed, method):
    rng = np.random.default_rng(seed)
    hits, cover, bias = 0, 0, []
    for k in range(REPS):
        beta, m, r = world(rng)
        w = book(rng, beta, target)
        full = r @ w
        g = book_beta_gate(leg_return(w, gapped(rng, r)), m, draws=400, seed=k, method=method, window=WIN)
        hits += g["pass"]
        cover += g["ci90"][0] <= target <= g["ci90"][1]
        bias.append(g["beta"] - ols_beta(full, m))
    return hits / REPS, cover / REPS, float(np.mean(bias))


def checks(method):
    power, cover0, bias0 = pass_rate(0.0, 1, method)
    size, cover1, bias1 = pass_rate(HB_BAND, 2, method)
    ok = (power >= 0.80 and size <= SIZE_MAX and 0.85 <= cover0 <= 0.95 and 0.85 <= cover1 <= 0.95
          and abs(bias0) < 0.01 and abs(bias1) < 0.01)
    print(f"{method}: power {power:.3f} size {size:.3f} (max {SIZE_MAX:.3f}) coverage {cover0:.3f}/{cover1:.3f} "
          f"missing-return bias {bias0:+.4f}/{bias1:+.4f} -> {'PASS' if ok else 'fail'}")
    return ok


# The gate passes a truly neutral book (power) and rejects one at the band edge
# (size). Methods in the Amendment 1 order; the first that passes is HB's method.
def test_hb_power_and_size():
    chosen = next((mth for mth in METHODS if checks(mth)), None)
    print("HB method:", chosen)
    assert chosen is not None


# Stock-level slope of realised on true beta recovers 1 over the pooled windows.
def test_stock_slope_recovery():
    rng = np.random.default_rng(3)
    slopes = []
    for _ in range(50):
        beta, m, r = world(rng)
        slopes.append(ols_beta(ols_beta(r, m), beta))
    print(f"slope mean {np.mean(slopes):.3f} sd {np.std(slopes):.3f}")
    assert np.mean(slopes) == pytest.approx(1.0, abs=0.03)
