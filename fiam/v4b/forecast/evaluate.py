# Forecast evidence: monthly ICs, HAC t, paired bootstrap, decay (R§3, R§8).

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

# Inference needs this many independent months, else it is n/a.
MIN_MONTHS = 12
# Bootstrap draws and block length in months, fixed before any run.
DRAWS, BLOCK = 2000, 3


# Monthly Spearman IC of score vs label over the rows in mask.
def monthly_ic(eom, score, label, mask=None, min_names: int = 50) -> pd.Series:
    f = pd.DataFrame({"eom": eom, "s": score, "y": label})
    if mask is not None:
        f = f[np.asarray(mask)]
    f = f.dropna()
    out = {}
    for month, g in f.groupby("eom"):
        if len(g) >= min_names:
            out[month] = g["s"].rank().corr(g["y"].rank())
    return pd.Series(out, dtype=float).sort_index()


# Mean, Newey-West s.e. and t; None below MIN_MONTHS.
def mean_t(values, lags: int = 3) -> dict | None:
    x = pd.Series(values, dtype=float).dropna().to_numpy()
    n = len(x)
    if n < max(MIN_MONTHS, lags + 2):
        return None
    e = x - x.mean()
    s = float(e @ e) / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    se = (max(s, 0.0) / n) ** 0.5
    return {"n": n, "mean": float(x.mean()), "se": se, "t": float(x.mean() / se) if se else None}


# Moving-block bootstrap draws of a monthly series' mean.
def block_means(x: np.ndarray, draws: int = DRAWS, block: int = BLOCK, seed: int = 42):
    rng = np.random.default_rng(seed)
    n = len(x)
    starts = rng.integers(0, max(n - block + 1, 1), size=(draws, -(-n // block)))
    idx = (starts[:, :, None] + np.arange(block)).reshape(draws, -1)[:, :n]
    return x[np.minimum(idx, n - 1)].mean(axis=1)


# Paired difference a-b: mean, bootstrap s.e., and the 90% interval.
def paired(a: pd.Series, b: pd.Series) -> dict | None:
    both = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(both) < MIN_MONTHS:
        return None
    d = (both.iloc[:, 0] - both.iloc[:, 1]).to_numpy()
    m = block_means(d)
    return {
        "n": len(d),
        "mean": float(d.mean()),
        "se": float(m.std(ddof=1)),
        "lo90": float(np.quantile(m, 0.05)),
        "hi90": float(np.quantile(m, 0.95)),
    }


# Within 1 SE of the best, the most regularised option wins.
def one_se(scores: dict[float, pd.Series]) -> float:
    means = {k: s.mean() for k, s in scores.items()}
    best = max(means, key=means.get)
    se = block_means(scores[best].dropna().to_numpy()).std(ddof=1)
    near = [k for k, v in means.items() if v >= means[best] - se]
    return max(near)


# Summary of one IC series: overall, by year, with HAC t.
def summary(ic: pd.Series) -> dict:
    years = {str(y): float(v.mean()) for y, v in ic.groupby(ic.index.year)}
    return {"all": mean_t(ic), "by_year": years, "sd": float(ic.std()) if len(ic) > 1 else None}


# Per-day return per unit score in each age bucket, per month.
def decay_slopes(frame: pd.DataFrame, score: str, buckets) -> pd.DataFrame:
    rows = []
    for month, g in frame.groupby("eom"):
        z = g[score].rank(pct=True) - 0.5
        z = z / z.std()
        row = {"eom": month}
        for start, end in buckets:
            y_end = g[f"y{end}"]
            y_start = g[f"y{start}"] if start > 0 else 0.0
            part = (1 + y_end) / (1 + y_start) - 1
            ok = part.notna() & z.notna()
            if ok.sum() >= 50:
                slope = np.polyfit(z[ok], part[ok], 1)[0]
                row[f"{start}-{end}"] = slope / (end - start)
        rows.append(row)
    return pd.DataFrame(rows).set_index("eom")


# Fits alpha_per_day(a) = a0 * exp(-kappa * a); returns kappa and half-life.
def decay_fit(slopes: pd.DataFrame, buckets) -> dict | None:
    mids = np.array([(s + e) / 2 for s, e in buckets], dtype=float)
    cols = [f"{s}-{e}" for s, e in buckets]

    def fit(table: pd.DataFrame):
        y = table[cols].mean().to_numpy()
        ok = np.isfinite(y)
        if ok.sum() < 3 or y[ok][0] <= 0:
            return None
        try:
            (a0, kappa), _ = curve_fit(
                lambda a, a0, k: a0 * np.exp(-k * a),
                mids[ok],
                y[ok],
                p0=(y[ok][0], 0.05),
                bounds=([0, 0], [np.inf, 5]),
                maxfev=10000,
            )
        except RuntimeError:
            return None
        return float(a0), float(kappa)

    point = fit(slopes)
    if point is None or len(slopes) < MIN_MONTHS:
        return None
    rng = np.random.default_rng(42)
    draws = []
    for _ in range(500):
        pick = rng.integers(0, len(slopes), size=len(slopes))
        got = fit(slopes.iloc[pick])
        if got is not None:
            draws.append(got[1])
    k = point[1]
    return {
        "a0_per_day": point[0],
        "kappa": k,
        "half_life_days": float(np.log(2) / k) if k > 0 else None,
        "kappa_lo90": float(np.quantile(draws, 0.05)) if draws else None,
        "kappa_hi90": float(np.quantile(draws, 0.95)) if draws else None,
        "per_day_by_bucket": {c: float(v) for c, v in slopes[cols].mean().items()},
    }
