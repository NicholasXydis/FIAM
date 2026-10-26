"""D22: evaluate the existing G2 volatility interval on synthetic paths only."""

import json

import numpy as np
from scipy import stats


def study(reps: int = 10_000, n: int = 160, seed: int = 20261026) -> dict:
    """Coverage of the D21 chi-square SD interval when true daily SD is one."""
    if reps < 1 or n < 3:
        raise ValueError("at least one replicate and three observations required")
    rng = np.random.default_rng(seed)
    q_lo = np.sqrt((n - 1) / stats.chi2.ppf(0.95, n - 1))
    q_hi = np.sqrt((n - 1) / stats.chi2.ppf(0.05, n - 1))
    result = {"reps": reps, "sessions": n, "seed": seed}
    for name in ("gaussian", "student_t5"):
        data = (rng.normal(size=(reps, n)) if name == "gaussian"
                else rng.standard_t(5, size=(reps, n)) / np.sqrt(5 / 3))
        sd = data.std(axis=1, ddof=1)
        covered = (sd * q_lo <= 1.0) & (1.0 <= sd * q_hi)
        coverage = float(covered.mean())
        result[name] = {"true_sd": 1.0, "coverage": coverage,
                        "mc_se": float(np.sqrt(coverage * (1 - coverage) / reps)),
                        "pass": 0.875 <= coverage <= 0.925}
    result["pass"] = result["gaussian"]["pass"] and result["student_t5"]["pass"]
    return result


if __name__ == "__main__":
    print(json.dumps(study(), indent=2))
