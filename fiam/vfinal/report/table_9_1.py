# The PDF's 23-row table, computed from the final run.

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam.vfinal import daily_book

COLUMNS = ["row", "name", "strategy", "benchmark", "note"]
# No September data in any statistic.
END = pd.Timestamp("2026-08-31")
# The hurdle is the bill plus 4% a year (PDF p20).
PREMIUM = 0.04
# Newey-West lags: monthly regressions 3, daily 5.
LAGS_MONTHLY, LAGS_DAILY = 3, 5
# Rebalances a year the cadences annualise by (row 17).
CADENCES = (12, 52, 252)
NA = "n/a"


# OLS with Newey-West errors: intercept, its s.e., slope, its s.e.
def ols(y: pd.Series, x: pd.Series, lags: int) -> tuple[float, float, float, float]:
    fit = sm.OLS(y.to_numpy(), sm.add_constant(x.to_numpy())).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags}
    )
    return float(fit.params[0]), float(fit.bse[0]), float(fit.params[1]), float(fit.bse[1])


# Dimson's beta: the slope summed over the market's lag, today and lead.
def dimson(y: pd.Series, x: pd.Series, lags: int) -> float:
    design = pd.concat({"lag": x.shift(1), "now": x, "lead": x.shift(-1)}, axis=1)
    ok = design.notna().all(axis=1)
    fit = sm.OLS(y[ok].to_numpy(), sm.add_constant(design[ok].to_numpy())).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags}
    )
    return float(fit.params[1:].sum())


# Daily returns compounded within calendar months.
def compound(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


# Mean over standard deviation times root 12 of monthly returns.
def annual_ratio(r: pd.Series) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(12)) if sd > 0 else np.nan


# The ratio's standard error: Lo (2002), independent months, annualised.
def ratio_se(r: pd.Series) -> float:
    sd = r.std(ddof=1)
    if not sd > 0:
        return np.nan
    monthly = r.mean() / sd
    return float(np.sqrt((1 + monthly**2 / 2) / len(r)) * np.sqrt(12))


# The worst fall of a compounded path that starts at 1.
def drawdown(r: pd.Series) -> float:
    wealth = np.concatenate([[1.0], (1 + r).cumprod().to_numpy()])
    return float((wealth / np.maximum.accumulate(wealth) - 1).min())


# Each formation that traded after its date, with its first trade day.
def rebalances(trades: pd.DataFrame) -> pd.Series:
    first = trades.groupby("formed")["date"].min()
    return first[first.index < first].sort_values()


# One-way turnover by rebalance, each traded day to the one before.
def turnover_by_rebalance(d: pd.DataFrame, trades: pd.DataFrame) -> pd.Series:
    firsts = rebalances(trades).to_numpy()
    days = d.index[d["traded"].astype(bool)]
    group = np.maximum(np.searchsorted(firsts, days.to_numpy(), side="right") - 1, 0)
    return d.loc[days, "turnover"].groupby(group).sum()


# Position-weighted run length in sessions, the plain mean beside it.
def holding_period(positions: pd.DataFrame, daily: pd.DataFrame) -> tuple[float, float]:
    place = pd.Series(range(len(daily)), index=daily.index)
    p = positions[positions["date"].isin(daily.index)].copy()
    p["i"] = p["date"].map(place)
    p = p.sort_values(["permno", "i"], kind="stable")
    side = np.sign(p["value"])
    # A run ends where the name, the side or the consecutive sessions break.
    new = (p["permno"] != p["permno"].shift()) | (p["i"].diff() != 1) | (side != side.shift())
    p["run"] = new.cumsum()
    p["w"] = p["value"].abs() / p["date"].map(daily["nav"])
    g = p.groupby("run").agg(days=("i", "size"), w=("w", "mean"))
    return float((g["days"] * g["w"]).sum() / g["w"].sum()), float(g["days"].mean())


# The short book's cap by holdings date: median, minimum, coverage.
def short_caps(positions, caps, days) -> tuple[float, float, int, int]:
    short = positions[(positions["value"] < 0) & positions["date"].isin(days)]
    got = short.merge(caps[["date", "permno", "me"]], on=["date", "permno"], how="left")
    seen = got.dropna(subset=["me"])
    by_day = seen.groupby("date")["me"]
    return float(by_day.median().median()), float(by_day.min().min()), len(seen), len(got)


# The monthly bill, from the caller or the daily bills compounded.
def monthly_bill(m: pd.DataFrame, rf_monthly) -> pd.Series:
    if rf_monthly is None:
        return m["rf"]
    rf = pd.Series(rf_monthly)
    if not isinstance(rf.index, pd.PeriodIndex):
        rf.index = pd.DatetimeIndex(rf.index).to_period("M")
    got = rf.reindex(m.index)
    if got.isna().any():
        raise ValueError("the monthly bill misses a month of the run")
    return got


# A cell of arithmetic and compound annual returns in percent.
def two_returns(m: pd.Series, end: float, start: float) -> str:
    arith, cagr = m.mean() * 12, (end / start) ** (12 / len(m)) - 1
    return f"arithmetic {arith * 100:.2f}, CAGR {cagr * 100:.2f}"


# A statistic and its standard error as one cell.
def with_se(value: float, se: float, places: int) -> str:
    return f"{value:.{places}f} ({se:.{places}f})"


# A count's average, minimum and maximum as one cell.
def avg_min_max(x: pd.Series, places: int) -> str:
    return f"avg {x.mean():.{places}f}, min {x.min():.{places}f}, max {x.max():.{places}f}"


# The 23 rows: row, name, strategy, benchmark and a note on each.
def table(daily, trades, positions, bench, rf_monthly=None, caps=None) -> pd.DataFrame:
    start = float(daily["nav"].iloc[0] / (1 + daily["ret"].iloc[0]))
    prev = daily["nav"].shift(1)
    # The first row is the endowment close; no statistic counts it.
    d = daily.iloc[1:].loc[:END]
    prev = prev.loc[d.index]
    sp = bench.reindex(d.index)
    if sp.isna().any():
        raise ValueError("the S&P 500 series misses a day of the run")
    m = daily_book.monthly(d)
    m["rf"] = monthly_bill(m, rf_monthly)
    m["excess"] = m["ret"] - m["rf"]
    sp_m = compound(sp)
    hurdle_m, hurdle_d = m["rf"] + PREMIUM / 12, d["rf"] + PREMIUM / 252
    active = m["ret"] - hurdle_m
    years = len(d) / 252
    end = start * float((1 + d["ret"]).prod())
    end_b = start * float((1 + hurdle_m).prod())
    rows = [
        (1, "Ending value (US$ bn)", end / 1e9, end_b / 1e9,
         "start to the last session, endowment row not counted"),
        (2, "Cumulative return (%)", (end / start - 1) * 100, (end_b / start - 1) * 100, ""),
        (3, "Annualised return (%)", two_returns(m["ret"], end, start),
         two_returns(hurdle_m, end_b, start), "monthly mean x 12, and CAGR over the months"),
        (4, "Annualised volatility (%)", m["ret"].std(ddof=1) * np.sqrt(12) * 100,
         hurdle_m.std(ddof=1) * np.sqrt(12) * 100, "monthly sd x sqrt 12"),
    ]  # fmt: skip
    # Alpha and beta against the S&P 500, excess of the bill, Newey-West.
    a, a_se, b, b_se = ols(m["excess"], sp_m - m["rf"], LAGS_MONTHLY)
    rows.append((5, "Alpha vs S&P 500 (%, s.e.)", with_se(a * 1200, a_se * 1200, 2), NA,
                 "monthly OLS, intercept x 12, Newey-West 3 lags"))  # fmt: skip
    rows.append((6, "Beta monthly (s.e.)", with_se(b, b_se, 3), NA, "same regression"))
    y_d, x_d = d["ret"] - d["rf"], sp - d["rf"]
    _, _, bd, bd_se = ols(y_d, x_d, LAGS_DAILY)
    rows.append((7, "Beta daily (s.e.)", with_se(bd, bd_se, 3), NA,
                 f"HAC 5 lags; Dimson beta {dimson(y_d, x_d, LAGS_DAILY):.3f}"))  # fmt: skip
    rows.append((8, "Sharpe ratio", annual_ratio(m["excess"]), "undefined, constant excess",
                 "monthly excess over the bill, mean / sd x sqrt 12"))  # fmt: skip
    # Row 9 adds back the engine's trading and borrow dollars.
    before = d["ret"] + (d["cost"] + d["borrow"]) / prev
    active_before = compound(before) - hurdle_m
    rows.append((9, "IR vs T-bill + 4%, before costs", annual_ratio(active_before), NA,
                 "cost and borrow added back over the last NAV; no financing "
                 "cost is booked apart from these"))  # fmt: skip
    rows.append((10, "Tracking error (%)", active.std(ddof=1) * np.sqrt(12) * 100, NA,
                 "sd of monthly net return less the hurdle x sqrt 12"))  # fmt: skip
    rows.append((11, "Max drawdown (%)", drawdown(d["ret"]) * 100, drawdown(hurdle_d) * 100,
                 "daily compounded NAV from the start"))  # fmt: skip
    rows.append((12, "Max one-month loss (%)", m["ret"].min() * 100, hurdle_m.min() * 100,
                 "worst calendar-month return"))  # fmt: skip
    rows.append((13, "Max one-day loss (%)", d["ret"].min() * 100, hurdle_d.min() * 100,
                 "worst daily return"))  # fmt: skip
    # Rows 14-16 count the sessions from the first trade day on.
    traded = d.index[d["traded"].astype(bool)]
    live = d[d.index >= traded.min()] if len(traded) else d
    names = live["n_long"] + live["n_short"]
    note = "daily, from the first trade day"
    count = f"avg {names.mean():.1f}, min {names.min():.0f}, max {names.max():.0f}"
    rows.append((14, "Positions held", count, NA, note))
    rows.append((15, "Gross exposure (%)", f"avg {live['gross'].mean() * 100:.1f}, "
                 f"max {live['gross'].max() * 100:.1f}", NA, note + ", drifted"))  # fmt: skip
    rows.append((16, "Net exposure (%)", avg_min_max(live["net"] * 100, 1), NA, note))
    rows.append((17, "One-way turnover (%)", *turnover_cell(d, trades, years)))
    held, plain = holding_period(positions, daily.loc[: d.index[-1]])
    rows.append((18, "Average holding period (sessions)", held, NA,
                 f"runs of one name and side, weighted by mean weight; plain mean {plain:.1f}; "
                 "runs cut by the window count as seen"))  # fmt: skip
    held_rows = positions[positions["date"].isin(live.index)]
    rows.append((19, "Average position size (US$ m)", held_rows["value"].abs().mean() / 1e6, NA,
                 "mean |value| over names and days"))  # fmt: skip
    rows.append((20, "Short book median market cap (US$ m)", *cap_cells(positions, caps, traded)))
    rows.append((21, "Trading cost (% NAV a year)", (d["cost"] / prev).mean() * 252 * 100, NA,
                 "fees, spread and impact as booked; flat variant is a separate run"))  # fmt: skip
    rows.append((22, "Borrow cost (% NAV a year)", (d["borrow"] / prev).mean() * 252 * 100, NA,
                 "tiers as booked; the flat variant is a separate run"))  # fmt: skip
    rows.append((23, "IR net of all costs", *net_cell(d, m, hurdle_m, active)))
    return pd.DataFrame(rows, columns=COLUMNS)


# Row 17's cells: with and without the build, all trade days beside.
def turnover_cell(d, trades, years: float) -> tuple[str, str, str]:
    per = turnover_by_rebalance(d, trades)
    if per.empty:
        return "no trades", NA, "no trade day in the run"
    measured = len(per) / years
    k = min(CADENCES, key=lambda c: abs(c - measured))
    after = per.iloc[1:].mean() * k * 100 if len(per) > 1 else np.nan
    cell = f"with build {per.mean() * k * 100:.0f}, without {after:.0f}; "
    cell += f"all trade days {d['turnover'].sum() / years * 100:.0f}"
    note = (
        f"half the sum of |w - w carried| a day; each traded day goes to the last rebalance "
        f"formed before it (spills and trades between rebalances added); {len(per)} "
        f"rebalances, {per.mean() * 100:.1f}% each, x {k} a year; first one is the build"
    )
    return cell, NA, note


# Row 20's cells: median and minimum cap, or the caps it still needs.
def cap_cells(positions, caps, days) -> tuple[str, str, str]:
    if caps is None:
        return "needs caps", NA, "a frame of date, permno and me ($m) is not given"
    median, low, seen, total = short_caps(positions, caps, days)
    note = f"median over trade days of each day's median; minimum {low:.0f}; "
    return f"{median:.0f}", NA, note + f"{seen} of {total} short rows had a cap"


# Row 23's cells: net IR with s.e., and the 100% gross pair beside it.
def net_cell(d, m, hurdle_m, active) -> tuple[str, str, str]:
    g = float(d.loc[d["gross"] > 0, "gross"].mean())
    # Excess of the bill scaled to 100% gross, against the hurdle.
    scaled = compound(d["rf"] + (d["ret"] - d["rf"]) / g)
    ir, se = annual_ratio(active), ratio_se(active)
    cell = f"{with_se(ir, se, 2)}; at 100% gross IR {annual_ratio(scaled - hurdle_m):.2f}, "
    cell += f"Sharpe {annual_ratio(scaled - m['rf']):.2f}"
    note = f"s.e. from independent months (Lo 2002); average gross {g * 100:.0f}% scales the excess"
    return cell, NA, note
