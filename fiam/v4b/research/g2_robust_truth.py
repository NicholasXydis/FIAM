"""D23: compare preregistered volatility intervals on synthetic data only."""

import json

import numpy as np
from scipy import stats


def bootstrap_intervals(samples: np.ndarray, indices: np.ndarray) -> dict:
    samples = np.asarray(samples, dtype=float)
    indices = np.asarray(indices, dtype=int)
    if samples.ndim != 2 or indices.ndim != 3 or indices.shape[0] != samples.shape[0]:
        raise ValueError("samples [batch, n] and indices [batch, draws, n] required")
    resamples = np.take_along_axis(samples[:, None, :], indices, axis=2)
    boot_sd = resamples.std(axis=2, ddof=1)
    lo, hi = np.quantile(boot_sd, [0.05, 0.95], axis=1)
    observed = samples.std(axis=1, ddof=1)
    if np.any(lo <= 0):
        raise ValueError("bootstrap standard deviations must be positive")
    return {"percentile": np.column_stack([lo, hi]),
            "basic_log": np.column_stack([observed**2 / hi, observed**2 / lo])}


def study(reps: int = 10_000, n: int = 160, draws: int = 500, batch: int = 50,
          seed: int = 20261027, bootstrap_seed: int = 20261028) -> dict:
    rng, boot_rng = np.random.default_rng(seed), np.random.default_rng(bootstrap_seed)
    q_lo = np.sqrt((n - 1) / stats.chi2.ppf(0.95, n - 1))
    q_hi = np.sqrt((n - 1) / stats.chi2.ppf(0.05, n - 1))
    methods = ("chi_square", "percentile", "basic_log")
    result = {"reps": reps, "sessions": n, "draws": draws, "seed": seed,
              "bootstrap_seed": bootstrap_seed, "distributions": {}}
    for distribution in ("gaussian", "student_t5"):
        counts = {k: {"covered": 0, "inside": 0} for k in methods}
        for start in range(0, reps, batch):
            m = min(batch, reps - start)
            x = (rng.normal(size=(m, n)) if distribution == "gaussian"
                 else rng.standard_t(5, size=(m, n)) / np.sqrt(5 / 3))
            indices = boot_rng.integers(0, n, size=(m, draws, n))
            intervals = bootstrap_intervals(x, indices)
            sd = x.std(axis=1, ddof=1)
            intervals["chi_square"] = np.column_stack([sd * q_lo, sd * q_hi])
            for name, ci in intervals.items():
                counts[name]["covered"] += int(((ci[:, 0] <= 1.0) & (ci[:, 1] >= 1.0)).sum())
                counts[name]["inside"] += int(((ci[:, 0] >= 2 / 3) & (ci[:, 1] <= 1.5)).sum())
        result["distributions"][distribution] = {
            k: {"coverage": v["covered"] / reps, "unit_power": v["inside"] / reps}
            for k, v in counts.items()
        }
    for method in methods:
        values = [result["distributions"][d][method] for d in result["distributions"]]
        result.setdefault("eligible", {})[method] = all(
            0.875 <= x["coverage"] <= 0.925 and x["unit_power"] >= 0.8 for x in values
        )
    result["pick"] = next((k for k in ("percentile", "basic_log") if result["eligible"][k]), None)
    return result


if __name__ == "__main__":
    print(json.dumps(study(), indent=2))
