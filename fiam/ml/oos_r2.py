# Out-of-sample R-squared for every method, rules p.14. Rank scores are mapped to returns first.

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler

from fiam import book as P
from fiam import paths
from fiam.ml import dataset as D
from fiam.ml import train as T

PREDS = P.CACHE / "preds"
OUT = paths.EXHIBITS

# The template's lambda grids, stepped at 0.5 rather than 0.1 so a fold fits in minutes.
ENET_GRID = [10.0**e for e in np.arange(-4, 4.01, 0.5)]
RIDGE_GRID = [0.5 * 10.0**e for e in np.arange(-1, 8.01, 0.5)]
SEEDS = (43, 44, 45, 46)


# The rules' form: benchmark is zero, not the historical mean.
def r2_zero(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(1 - np.sum((actual - forecast) ** 2) / np.sum(actual**2))


# Both forms for one set of forecasts. The cross-sectional one ignores the market's own move.
def score(frame: pd.DataFrame, forecast: str) -> dict:
    s = frame.dropna(subset=["actual", forecast])
    month = s["holding_month"]
    actual_dm = s["actual"] - s.groupby(month)["actual"].transform("mean")
    forecast_dm = s[forecast] - s.groupby(month)[forecast].transform("mean")
    return dict(
        r2_zero_benchmark=r2_zero(s["actual"].to_numpy(), s[forecast].to_numpy()),
        r2_cross_sectional=r2_zero(actual_dm.to_numpy(), forecast_dm.to_numpy()),
        observations=int(len(s)),
        months=int(month.nunique()),
    )


# The template, adapted: standardize on train, demean the target, pick lambda on validation.
def template_fold(fold: dict, cols: list[str]) -> pd.DataFrame:
    train, validate = D.labelled(fold["train"]), D.labelled(fold["validate"])
    scaler = StandardScaler().fit(train[cols])
    x_train, x_val = scaler.transform(train[cols]), scaler.transform(validate[cols])
    x_test = scaler.transform(fold["test"][cols])
    y_mean = float(train[D.TARGET].mean())
    y_train, y_val = train[D.TARGET].to_numpy() - y_mean, validate[D.TARGET].to_numpy()

    out = fold["test"][["permno", "eom", "holding_month", D.TARGET]].rename(
        columns={D.TARGET: "actual"}
    )
    out["ols"] = LinearRegression(fit_intercept=False).fit(x_train, y_train).predict(x_test)
    out["ols"] += y_mean
    for name, make, grid in (
        ("ridge", lambda a: Ridge(alpha=a, fit_intercept=False), RIDGE_GRID),
        (
            "enet",
            lambda a: ElasticNet(alpha=a, fit_intercept=False, max_iter=5000),
            ENET_GRID,
        ),
    ):
        # Lowest validation error wins. The test year is never consulted.
        best, best_mse = None, np.inf
        for alpha in grid:
            model = make(alpha).fit(x_train, y_train)
            mse = float(np.mean((model.predict(x_val) + y_mean - y_val) ** 2))
            if mse < best_mse:
                best, best_mse = model, mse
        out[name] = best.predict(x_test) + y_mean
    return out


# Return per unit of predicted rank, from the years before the test year only.
def rank_slope(history: pd.DataFrame) -> float:
    h = D.labelled(history)
    rank = h.groupby("holding_month")[D.TARGET].rank(pct=True) - 0.5
    ret = h[D.TARGET] - h.groupby("holding_month")[D.TARGET].transform("mean")
    return float((rank * ret).sum() / (rank * rank).sum())


# A rank-target model's predictions turned into returns, fold by fold.
def calibrated(df: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for fold in D.folds(df):
        history = pd.concat([fold["train"], fold["validate"]])
        slope = rank_slope(history)
        part = preds[preds["holding_month"].dt.year == fold["test_year"]].copy()
        part["forecast"] = part["pred"] * slope
        frames.append(part)
    return pd.concat(frames)


# The composite's score mapped to returns, with a slope from earlier years only.
def composite_forecasts() -> pd.DataFrame:
    panel = P.load_panel()
    universe = P.build_signal(P.screen(panel, "2015-01-31", P.LAST_FORECAST))
    universe["holding_month"] = (universe["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    universe["z"] = P.rank_z(universe, "signal").fillna(0.0)
    universe = universe.rename(columns={"ret_exc_lead1m": "actual"})
    month = universe["holding_month"]
    universe["actual_dm"] = universe["actual"] - universe.groupby(month)["actual"].transform("mean")

    frames = []
    for year in range(D.FIRST_TEST_YEAR, D.LAST_TEST_YEAR + 1):
        start = pd.Timestamp(year=year, month=1, day=1)
        history = universe[(month < start)].dropna(subset=["actual_dm"])
        slope = float((history["z"] * history["actual_dm"]).sum() / (history["z"] ** 2).sum())
        test = (month >= start) & (month.dt.year == year) & (month <= D.LAST_HOLDING_MONTH)
        part = universe[test].copy()
        part["forecast"] = part["z"] * slope
        frames.append(part)
    return pd.concat(frames)


# The stock picker's ranks mapped to returns by a slope fitted on its own earlier scored years,
# 2019-2020 first. Its ranks span the whole month, so the perfect-rank slope would overstate it.
def scorer_forecasts(df: pd.DataFrame) -> pd.DataFrame | None:
    cache = P.CACHE / "scores.parquet"
    if not cache.exists():
        return None
    scores = pd.read_parquet(cache)[["permno", "eom", "holding_month", "score"]]
    frame = scores.merge(df[["permno", "eom", D.TARGET]], on=["permno", "eom"], how="left")
    frame = frame.rename(columns={D.TARGET: "actual"})
    month = frame["holding_month"]
    frame["actual_dm"] = frame["actual"] - frame.groupby(month)["actual"].transform("mean")
    frames = []
    for year in range(D.FIRST_TEST_YEAR, D.LAST_TEST_YEAR + 1):
        start = pd.Timestamp(year=year, month=1, day=1)
        history = frame[month < start].dropna(subset=["actual_dm", "score"])
        x, y = history["score"], history["actual_dm"]
        slope = float((x * y).sum() / (x**2).sum())
        part = frame[(month.dt.year == year) & (month <= D.LAST_HOLDING_MONTH)].copy()
        part["forecast"] = part["score"] * slope
        frames.append(part)
    return pd.concat(frames)


# Out-of-sample R-squared for every method, both benchmarks.
def main() -> None:
    df = D.load_folds()
    cols = P.characteristics()
    out = dict(
        what="Out-of-sample R-squared, zero benchmark as the rules define it, plus the "
        "cross-sectional form that removes each month's average return.",
        how="Template models forecast returns directly. Rank-target models and the composite are "
        "scaled to returns by a slope estimated only on years before each test year.",
        template_note="Organizer's template on our folds, lambda grid stepped at 0.5 not 0.1.",
        code=P.source_fingerprint(),
        methods={},
    )

    # The template refits only when the folds or this file change, never for a book change.
    inputs = [*T.fit_inputs(cols), Path(__file__).read_bytes()]
    frames = P.cached(
        "template_linear", inputs, lambda: [template_fold(f, cols) for f in D.folds(df)]
    )
    template = pd.concat(frames, ignore_index=True)
    D.assert_holding_months(template)
    template.to_parquet(PREDS / "template_linear.parquet", index=False)
    for name in ("ols", "ridge", "enet"):
        out["methods"][f"template_{name}"] = score(template, name)
        print(f"  template {name}: {out['methods'][f'template_{name}']}")

    for model in ("enet", "lgbm", "nn3"):
        if not (PREDS / f"{model}.parquet").exists():
            continue
        preds = pd.read_parquet(PREDS / f"{model}.parquet")
        out["methods"][model] = score(calibrated(df, preds), "forecast")
        print(f"  {model}: {out['methods'][model]}")
    picked = scorer_forecasts(df)
    if picked is not None:
        out["methods"]["scorer"] = score(picked, "forecast")
        print(f"  scorer: {out['methods']['scorer']}")

    out["methods"]["composite"] = score(composite_forecasts(), "forecast")
    print(f"  composite: {out['methods']['composite']}")

    OUT.mkdir(parents=True, exist_ok=True)
    paths.write_json(OUT / "oos_r2.json", out, rounded=False)


if __name__ == "__main__":
    main()
