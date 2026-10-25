# Each stock's volatility next month: LightGBM on the 147, versus HAR.

import json
import sys

import numpy as np
import pandas as pd

from fiam import data
from fiam.freeze import FROZEN

FORECAST = FROZEN / "vol_forecast.parquet"
REPORT = FROZEN / "vol_check.json"
CHECK_YEARS = range(2017, 2021)
WINDOWS = (5, 21, 63)


# Daily total returns, dates by permno, from the bundle's daily file.
def daily_returns() -> pd.DataFrame:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    return daily.pivot_table(index="date", columns="permno", values="total_return")


# Each stock's monthly realized volatility, needing 15 days or more.
def monthly_realized(returns: pd.DataFrame) -> pd.Series:
    month = returns.index.to_period("M").to_timestamp()
    sd = returns.groupby(month).std()
    days = returns.groupby(month).count()
    vol = (sd * np.sqrt(21)).where(days >= 15)
    out = vol.stack()
    out.index.names = ["month", "permno"]
    return out.swaplevel().sort_index()


# HAR inputs at month end: log realized vol over 5, 21 and 63 days.
def har_inputs(returns: pd.DataFrame, months: list) -> pd.DataFrame:
    rows = []
    for eom in months:
        window = returns.loc[:eom].tail(max(WINDOWS))
        if len(window) < max(WINDOWS) or (eom - window.index[-1]).days > 7:
            continue
        parts = {f"har_{n}": np.log(window.tail(n).std() * np.sqrt(21)) for n in WINDOWS}
        frame = pd.DataFrame(parts).assign(eom=eom)
        rows.append(frame.reset_index())
    out = pd.concat(rows, ignore_index=True)
    return out.replace([np.inf, -np.inf], np.nan)


# QLIKE on variances: (real/fcst)^2 - log((real/fcst)^2) - 1.
def qlike(realized: pd.Series, forecast: pd.Series) -> pd.Series:
    ratio = (realized / forecast) ** 2
    return ratio - np.log(ratio) - 1


# Diebold-Mariano t, Newey-West lag 3 (negative favours the model).
def diebold_mariano(diff: pd.Series, lags: int = 3) -> float:
    d = diff.dropna().to_numpy()
    n, mean = len(d), d.mean()
    centred = d - mean
    var = centred @ centred / n
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * (centred[lag:] @ centred[:-lag]) / n
    return float(mean / np.sqrt(var / n))


# LightGBM and HAR walk forward by year, scored before 2021, frozen.
def main() -> None:
    from fiam.ml import teachers as T

    frame, cols = T.inputs()
    returns = daily_returns()
    realized = monthly_realized(returns)
    key = pd.MultiIndex.from_arrays([frame["permno"], frame["holding_month"]])
    target = pd.Series(realized.reindex(key).to_numpy(), index=frame.index)
    frame["realized"] = target
    frame["lgbm"] = np.exp(T.walk_forward(frame, cols, np.log(target)))

    har = har_inputs(returns, sorted(frame["eom"].unique()))
    frame = frame.merge(har, on=data.KEYS, how="left")
    year = frame["holding_month"].dt.year
    names = [f"har_{n}" for n in WINDOWS]
    frame["har"] = np.nan
    for test in T.YEARS:
        train = (year < test) & frame[names].notna().all(axis=1) & frame["realized"].notna()
        test_rows = (year == test) & frame[names].notna().all(axis=1)
        if train.sum() < 10_000 or not test_rows.any():
            continue
        x = np.column_stack([np.ones(train.sum()), frame.loc[train, names]])
        coef, *_ = np.linalg.lstsq(x, np.log(frame.loc[train, "realized"]), rcond=None)
        xt = np.column_stack([np.ones(test_rows.sum()), frame.loc[test_rows, names]])
        frame.loc[test_rows, "har"] = np.exp(xt @ coef)

    scored = frame.dropna(subset=["realized", "lgbm", "har"])
    scored = scored[scored["holding_month"].dt.year.isin(CHECK_YEARS)]
    loss_l, loss_h = (
        qlike(scored["realized"], scored["lgbm"]),
        qlike(scored["realized"], scored["har"]),
    )
    by_year = {
        str(y): dict(lgbm=float(loss_l[g.index].mean()), har=float(loss_h[g.index].mean()))
        for y, g in scored.groupby(scored["holding_month"].dt.year)
    }
    monthly = (loss_l - loss_h).groupby(scored["holding_month"]).mean()
    wins = sum(v["lgbm"] < v["har"] for v in by_year.values())
    t = diebold_mariano(monthly)
    passed = wins >= 3 and t < -2
    choice = "lgbm" if passed else "har"
    out = frame[[*data.KEYS]].assign(vol_hat=frame[choice]).dropna()
    FROZEN.mkdir(exist_ok=True)
    out.to_parquet(FORECAST, index=False)
    report = dict(
        protocol="docs/protocols/risk.md section 1",
        qlike_by_year=by_year,
        lgbm_wins=wins,
        diebold_mariano_t=t,
        passed=passed,
        used=choice,
        rows_scored=int(len(scored)),
    )
    REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


# Forecast vol from the frozen table, else last 21 days scaled up.
def forecast(frame: pd.DataFrame) -> pd.Series:
    table = data.read(FORECAST).set_index(data.KEYS)["vol_hat"] if FORECAST.exists() else None
    found = pd.Series(np.nan, index=frame.index)
    if table is not None:
        key = pd.MultiIndex.from_frame(frame[data.KEYS])
        found = pd.Series(table.reindex(key).to_numpy(), index=frame.index)
    return found.fillna(frame["rvol_21d"] * np.sqrt(21))


if __name__ == "__main__":
    main() if sys.argv[1:] != ["check"] else print(REPORT.read_text(encoding="utf-8"))
