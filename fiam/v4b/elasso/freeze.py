# Freezes the E-LASSO calibration scale and alpha-decay rate (D6, R§3).
#
# Everything is estimated on the held-out window shared with judge.py
# (formation eom 2016-12..2020-11, 48 months, tradable universe, earnable
# labels with dividends). Forecasts there are out of sample by construction:
# each month's E-LASSO coefficients use only earlier months.
#
# Calibration is the centred (within-month demeaned) Mincer-Zarnowitz slope:
# the raw forecast is mostly a market-level intercept (monthly means swing
# -4%..+8% against ~0.5% dispersion), which a dollar-neutral book cannot
# earn. The levels slope is reported as a diagnostic only.
# Decay is frozen from cumulative alpha A(H) = Ainf*(1-exp(-kappa*H)); the
# IC(H) fit is the Mandate §11 exhibit. If kappa is unidentified (its 90%
# block-bootstrap interval covers 0), kappa=0 is frozen and said so.

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from fiam.v4b.elasso import judge
from fiam.v4b.forecast import data, evaluate, initial_plan, run

OUT = Path(__file__).resolve().parents[1] / "out" / "elasso"
COLUMNS = ("Elasso_MaInf", "Elasso_Ma1")
HORIZONS = (1, 2, 3, 5, 10, 21, 42, 63)
SEED, DRAWS, BLOCK = 42, 2000, 3


# Held-out rows with forecasts (decimal) and every horizon label.
def frame() -> pd.DataFrame:
    u, *_ = initial_plan.prepare()
    fc = judge.forecasts()
    fc = fc[fc["eom"].between(pd.Timestamp(judge.WINDOW[0]), pd.Timestamp(judge.WINDOW[1]))]
    keep = ["eom", "permno", "ret_exc_lead1m", *[f"y{h}" for h in run.HORIZONS]]
    f = fc.merge(u[keep], on=["eom", "permno"], how="inner")
    for c in COLUMNS:
        f[c] = f[c] / 100.0
    f["y2"] = _y2(f)
    return f


# The 2-day label, built the same way as the others (dividends added back).
def _y2(f: pd.DataFrame) -> pd.Series:
    p = data.panel()
    d = data.with_dividends(data.daily())
    lab = data.daily_labels(p, d, (2,))
    got = f[["eom", "permno"]].merge(lab[["eom", "permno", "y2"]], on=["eom", "permno"], how="left")
    return got["y2"].to_numpy()


# Date-balanced centred slope of label on forecast, one number per month set.
def _slope(f: pd.DataFrame, score: str, label: str, months=None) -> float:
    g = f if months is None else f[f["eom"].isin(months)]
    g = g[["eom", score, label]].dropna()
    s = g[score] - g.groupby("eom")[score].transform("mean")
    y = g[label] - g.groupby("eom")[label].transform("mean")
    num = (s * y).groupby(g["eom"]).mean().sum()
    den = (s**2).groupby(g["eom"]).mean().sum()
    return float(num / den) if den else float("nan")


# Moving-block resamples of the month list (same design as evaluate).
def _month_draws(months: np.ndarray) -> list[np.ndarray]:
    rng = np.random.default_rng(SEED)
    n = len(months)
    starts = rng.integers(0, n - BLOCK + 1, size=(DRAWS, -(-n // BLOCK)))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(DRAWS, -1)[:, :n]
    return [months[row] for row in idx]


# Centred slope on one label with its block-bootstrap interval.
def calibration(f: pd.DataFrame, score: str, label: str, draws) -> dict:
    point = _slope(f, score, label)
    boot = np.array([_slope(f, score, label, m) for m in draws])
    boot = boot[np.isfinite(boot)]
    return {
        "slope": point,
        "se": float(boot.std(ddof=1)),
        "lo90": float(np.quantile(boot, 0.05)),
        "hi90": float(np.quantile(boot, 0.95)),
    }


# Mean rank IC at each horizon (the decay exhibit's points).
def ic_curve(f: pd.DataFrame, score: str, months=None) -> dict:
    g = f if months is None else f[f["eom"].isin(months)]
    return {
        str(h): float(evaluate.monthly_ic(g["eom"], g[score], g[f"y{h}"]).mean()) for h in HORIZONS
    }


# Fits IC(H) = ic0*exp(-kappa*H) + c; None when the curve cannot identify it.
def _fit_ic(curve: dict):
    h = np.array([float(k) for k in curve])
    y = np.array([curve[k] for k in curve], dtype=float)
    ok = np.isfinite(y)
    if ok.sum() < 5:
        return None
    try:
        (ic0, kappa, c), _ = curve_fit(
            lambda x, a, k, c: a * np.exp(-k * x) + c,
            h[ok],
            y[ok],
            p0=(max(y[ok][0], 0.01), 0.02, 0.0),
            bounds=([0, 0, -0.1], [1, 5, 0.1]),
            maxfev=10000,
        )
    except RuntimeError:
        return None
    return float(ic0), float(kappa), float(c)


# Cumulative alpha to each horizon: centred slope times forecast dispersion.
# A(H) is the 21d-style earnable alpha per unit centred forecast, in return.
def alpha_curve(f: pd.DataFrame, score: str, months=None) -> dict:
    return {str(h): _slope(f, score, f"y{h}", months) for h in HORIZONS}


# Fits A(H) = ainf*(1-exp(-kappa*H)); None when unidentified.
def _fit_alpha(curve: dict):
    h = np.array([float(k) for k in curve])
    y = np.array([curve[k] for k in curve], dtype=float)
    ok = np.isfinite(y)
    if ok.sum() < 5 or y[ok][-1] <= 0:
        return None
    try:
        (ainf, kappa), _ = curve_fit(
            lambda x, a, k: a * (1 - np.exp(-k * x)),
            h[ok],
            y[ok],
            p0=(y[ok][-1], 0.02),
            bounds=([0, 0], [np.inf, 5]),
            maxfev=10000,
        )
    except RuntimeError:
        return None
    return float(ainf), float(kappa)


# One decay fit (point + bootstrap CI on kappa) for a curve builder.
def decay(f, score, draws, builder, fitter) -> dict:
    curve = builder(f, score)
    point = fitter(curve)
    boot = []
    for m in draws[::4]:  # 500 fits are enough for a 90% interval
        got = fitter(builder(f, score, m))
        if got is not None:
            boot.append(got[-2] if len(got) == 3 else got[1])
    out = {"curve": curve, "fit": point, "kappa_boot_n": len(boot)}
    if point is not None and boot:
        kappa = point[-2] if len(point) == 3 else point[1]
        out |= {
            "kappa": kappa,
            "half_life_days": float(np.log(2) / kappa) if kappa > 0 else None,
            "kappa_lo90": float(np.quantile(boot, 0.05)),
            "kappa_hi90": float(np.quantile(boot, 0.95)),
        }
    return out


# Levels (uncentred) MZ slope, diagnostic: how much is market timing.
def levels_slope(f: pd.DataFrame, score: str, label: str = "ret_exc_lead1m") -> float:
    g = f[[score, label]].dropna()
    x = np.column_stack([np.ones(len(g)), g[score].to_numpy()])
    coef, *_ = np.linalg.lstsq(x, g[label].to_numpy(), rcond=None)
    return float(coef[1])


# Writes frozen.json; the config numbers are copied from it by hand once.
def main() -> dict:
    f = frame()
    months = np.array(sorted(f["eom"].unique()))
    draws = _month_draws(months)
    out = {
        "window_eom": [str(pd.Timestamp(months[0]).date()), str(pd.Timestamp(months[-1]).date())],
        "months": int(len(months)),
        "rows": int(len(f)),
        "bootstrap": {"draws": DRAWS, "block_months": BLOCK, "seed": SEED},
    }
    for c in COLUMNS:
        out[c] = {
            "calibration_y21": calibration(f, c, "y21", draws),
            "calibration_monthly": calibration(f, c, "ret_exc_lead1m", draws),
            "levels_slope_monthly_diagnostic": levels_slope(f, c),
            "ic_decay": decay(f, c, draws, ic_curve, _fit_ic),
            "alpha_decay": decay(f, c, draws, alpha_curve, _fit_alpha),
        }
        a = out[c]["alpha_decay"]
        identified = a.get("kappa") is not None and a.get("kappa_lo90", 0) > 0
        out[c]["frozen_kappa"] = a["kappa"] if identified else 0.0
        out[c]["kappa_identified"] = bool(identified)
    (OUT / "frozen.json").write_text(json.dumps(out, indent=2, default=run._plain) + "\n")
    return out


if __name__ == "__main__":
    r = main()
    for c in COLUMNS:
        x = r[c]
        print(c)
        for lab in ("calibration_y21", "calibration_monthly"):
            v = x[lab]
            print(f"  {lab}: slope {v['slope']:.3f} se {v['se']:.3f}", end=" ")
            print(f"[{v['lo90']:.3f}, {v['hi90']:.3f}]")
        print(f"  levels slope (diagnostic): {x['levels_slope_monthly_diagnostic']:.3f}")
        ic = {k: round(v, 4) for k, v in x["ic_decay"]["curve"].items()}
        al = {k: round(v, 3) for k, v in x["alpha_decay"]["curve"].items()}
        print(f"  IC curve: {ic}")
        print(f"  alpha curve (slope by H): {al}")
        a = x["alpha_decay"]
        print(f"  alpha kappa: {a.get('kappa')} CI [{a.get('kappa_lo90')},", end=" ")
        print(f"{a.get('kappa_hi90')}] half-life {a.get('half_life_days')}", end=" ")
        print(f"-> frozen {x['frozen_kappa']}")
