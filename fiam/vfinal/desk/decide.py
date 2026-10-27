# The desk's decision: bootstrap, memory gate, arm.

import numpy as np
from scipy import stats

# Paired daily differences: 21-day mean blocks, 2,000 draws (rules).
BLOCK, DRAWS, SEED = 21, 2000, 20261900
# The memory gate's chance: 1 company in 10 and 1 month in 12.
CHANCE_COMPANY, CHANCE_MONTH = 1 / 10, 1 / 12


# A daily series' annualised IR.
def ir(x: np.ndarray) -> float:
    return float(np.mean(x) / np.std(x, ddof=1) * np.sqrt(252))


# Stationary block bootstrap s.e. of IR(a) - IR(b) on paired days.
def paired_se(a: np.ndarray, b: np.ndarray, block=BLOCK, draws=DRAWS, seed=SEED) -> float:
    rng, n = np.random.default_rng(seed), len(a)
    out = np.empty(draws)
    for k in range(draws):
        # Politis-Romano: a new block starts with probability 1 / block.
        start = rng.integers(0, n, n)
        fresh = rng.random(n) < 1 / block
        idx = np.empty(n, dtype=int)
        idx[0] = start[0]
        for t in range(1, n):
            idx[t] = start[t] if fresh[t] else (idx[t - 1] + 1) % n
        out[k] = ir(a[idx]) - ir(b[idx])
    return float(np.std(out, ddof=1))


# The memory gate: both hit rates inside chance's 95% binomial band.
def memory_gate(n: int, company_hits: int, month_hits: int) -> dict:
    lo_c, hi_c = stats.binom.interval(0.95, n, CHANCE_COMPANY)
    lo_m, hi_m = stats.binom.interval(0.95, n, CHANCE_MONTH)
    ok = lo_c <= company_hits <= hi_c and lo_m <= month_hits <= hi_m
    return {"n": n, "company": company_hits, "company_band": [lo_c, hi_c],
            "month": month_hits, "month_band": [lo_m, hi_m], "passes": bool(ok)}  # fmt: skip


# The headline arm; an exact tie goes to the simpler arm (A0, then A1).
def headline(irs: dict, gate_passes: bool) -> str:
    if gate_passes and irs["A2"] > irs["A1"] and irs["A2"] > irs["A0"]:
        return "A2"
    return "A1" if irs["A1"] > irs["A0"] else "A0"
