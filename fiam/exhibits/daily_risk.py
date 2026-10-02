# The monthly book, weights fixed, marked every trading day of 2021-2025. Writes daily_risk.json.


import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import data, paths

OUT = paths.EXHIBITS / "daily_risk.json"

# CRSP daily prices stop at the end of 2025, so 2026 is measured monthly only.
FIRST, LAST = pd.Timestamp("2021-01-01"), pd.Timestamp("2025-12-31")

# Shares short above this share of shares outstanding: crowded, and plausibly costly to borrow.
CROWDED = 0.10

# The stress windows, by calendar day.
STRESS = {
    "2020 crash, Feb 19 to Mar 23": ("2020-02-19", "2020-03-23"),
    "2020 rebound, Mar 24 to Jun 8": ("2020-03-24", "2020-06-08"),
    "2022, rates up": ("2022-01-01", "2022-12-31"),
    "2023 AI rally, Jan to Jul": ("2023-01-01", "2023-07-31"),
    "October 2024, the worst month": ("2024-10-01", "2024-10-31"),
}


# One holding month, day by day: each position grows with its own return, fees paid on day one.
def month_path(weights: pd.Series, daily: pd.DataFrame, cost: float, rf: float) -> pd.DataFrame:
    # A name with no daily return, one that has left, is held flat as the monthly book holds it.
    growth = (1 + daily.reindex(columns=weights.index).fillna(0.0)).cumprod()
    value = growth * weights
    elapsed = np.arange(1, len(growth) + 1) / len(growth)
    nav = 1 - cost + (value.sum(axis=1) - weights.sum()) + rf * elapsed
    return pd.DataFrame(
        dict(nav=nav, gross=value.abs().sum(axis=1) / nav, net=value.sum(axis=1) / nav)
    )


# Every month of 2021-2025 marked daily, chained into one path of net asset value.
def paths_by_day(book: pd.DataFrame, returns: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    parts, level = [], 1.0
    for month, group in book.groupby("Date"):
        days = daily[(daily.index >= month) & (daily.index < month + pd.offsets.MonthBegin(1))]
        weights = group.set_index("PERMNO")["WEIGHT"] / 100
        part = month_path(weights, days, returns.loc[month, "cost"], returns.loc[month, "rf"])
        part["month"], part["level"] = month, level * part["nav"]
        part["rf"] = returns.loc[month, "rf"] / len(part)
        parts.append(part)
        level = part["level"].iloc[-1]
    out = pd.concat(parts)
    out["ret"] = out["level"].pct_change().fillna(out["level"].iloc[0] - 1)
    return out


# Beta on the S&P 500 day by day, which pins neutrality far tighter than 60 monthly points.
def daily_beta(path: pd.DataFrame) -> dict:
    close = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    market = close.set_index("observation_date")["SP500"].pct_change().reindex(path.index)
    excess, market = path["ret"] - path["rf"], market - path["rf"]
    fit = P.regress(excess, market)
    both = pd.concat([excess, market], axis=1).dropna()
    rolling = both.iloc[:, 0].rolling(252).cov(both.iloc[:, 1]) / both.iloc[:, 1].rolling(252).var()
    rolling = rolling.dropna().resample("ME").last()
    by_year = {}
    for year in range(FIRST.year, LAST.year + 1):
        part = P.regress(excess.loc[str(year)], market.loc[str(year)])
        by_year[str(year)] = dict(beta=float(part.params.iloc[1]), stderr=float(part.bse.iloc[1]))
    return dict(
        beta=float(fit.params.iloc[1]),
        stderr=float(fit.bse.iloc[1]),
        t=float(fit.tvalues.iloc[1]),
        days=int(fit.nobs),
        by_year=by_year,
        # Month-end samples of the 252-day beta, for the rolling-beta chart.
        rolling_252d={f"{day:%Y-%m}": float(beta) for day, beta in rolling.items()},
    )


# Drawdown on a path of levels, the deepest fall from any earlier peak.
def drawdown(level: pd.Series) -> float:
    return float((level / level.cummax() - 1).min())


# What the daily path shows that month-end numbers hide.
def risk(path: pd.DataFrame, returns: pd.DataFrame) -> dict:
    daily = path["ret"]
    monthly = returns.loc[FIRST:LAST, "portfolio_total_return"]
    peak = path.groupby("month")["gross"].max()
    ends = path.groupby("month")[["gross", "net"]].last()
    ordered = daily.sort_values()
    return dict(
        gross_exposure=dict(
            at_rebalance_max=float(returns.loc[FIRST:LAST, "gross_exposure"].max()),
            intra_month_max=float(peak.max()),
            intra_month_max_month=f"{peak.idxmax():%Y-%m}",
            months_above_200pct_on_any_day=int((peak > 2.0).sum()),
            month_end_mean=float(ends["gross"].mean()),
            month_end_max=float(ends["gross"].max()),
        ),
        net_exposure=dict(
            intra_month_max_abs=float(path["net"].abs().max()),
            month_end_max_abs=float(ends["net"].abs().max()),
        ),
        volatility_annual=dict(
            daily=float((daily - path["rf"]).std() * np.sqrt(252)),
            monthly=float((monthly - returns.loc[FIRST:LAST, "rf"]).std() * np.sqrt(12)),
        ),
        var_one_day=dict(
            p95=float(np.percentile(daily, 5)),
            p99=float(np.percentile(daily, 1)),
            cvar_95=float(ordered.iloc[: int(np.ceil(len(ordered) * 0.05))].mean()),
        ),
        max_drawdown=dict(daily=drawdown(path["level"]), monthly=drawdown((1 + monthly).cumprod())),
        worst_day=dict(date=f"{daily.idxmin():%Y-%m-%d}", value=float(daily.min())),
        best_day=dict(date=f"{daily.idxmax():%Y-%m-%d}", value=float(daily.max())),
    )


# The daily path compounded back to months, against returns.csv. CRSP daily against the panel.
def reconcile(path: pd.DataFrame, returns: pd.DataFrame) -> dict:
    compounded = path.groupby("month")["nav"].last() - 1
    monthly = returns.loc[compounded.index, "portfolio_total_return"]
    gap = (compounded - monthly).abs()
    return dict(
        months=int(len(gap)),
        correlation=float(compounded.corr(monthly)),
        median_abs_gap=float(gap.median()),
        largest_gap=float(gap.max()),
        largest_gap_month=f"{gap.idxmax():%Y-%m}",
        why="Delisting payouts and the panel's own return fixes are monthly only.",
    )


# The short book against reported short interest at each decision month. Descriptive, not a signal.
def short_interest(book: pd.DataFrame) -> dict | None:
    short = data.research(
        "short_interest_monthly_research_only", ["permno", "eom", "short_interest_adjusted"]
    )
    if short is None:
        return None
    known = data.features(["shares"]).merge(short, on=data.KEYS, how="left")
    known["ratio"] = known["short_interest_adjusted"] / (known["shares"] * 1e6)
    held = book.assign(eom=book["Date"] - pd.offsets.MonthEnd(1)).astype({"eom": "datetime64[s]"})
    held = held.merge(known, left_on=["PERMNO", "eom"], right_on=data.KEYS, how="left")
    sides = dict(long=held[held["w"] > 0], short=held[held["w"] < 0])
    shorts = sides["short"].assign(size=lambda d: d["w"].abs())
    covered = shorts[shorts["ratio"].notna()]
    return dict(
        months=int(held["Date"].nunique()),
        short_book_weight_with_data=float(covered["size"].sum() / shorts["size"].sum()),
        short_book_weight_crowded=float(
            covered.loc[covered["ratio"] > CROWDED, "size"].sum() / covered["size"].sum()
        ),
        crowded_threshold=CROWDED,
        median_short_interest=dict(
            long=float(sides["long"]["ratio"].median()), short=float(shorts["ratio"].median())
        ),
    )


# Daily total returns for a set of names over a span of days, one column per name.
def daily_returns(permnos, first, last) -> pd.DataFrame | None:
    filters = [("permno", "in", sorted(set(permnos))), ("date", ">=", pd.Timestamp(first))]
    filters.append(("date", "<=", pd.Timestamp(last)))
    daily = data.research("daily_market", ["permno", "date", "total_return"], filters)
    if daily is None:
        return None
    return daily.pivot_table(index="date", columns="permno", values="total_return")


# The same code's book through early 2020, marked daily, since the record starts in 2021.
def path_2020() -> pd.DataFrame:
    universe = P.build_signal(P.screen(P.load_panel(), "2015-12-31", "2020-05-31"))
    rf = B.benchmarks().set_index("month")["rf"]
    books, records = [], []
    for step in P.walk(universe):
        record = P.month_record(*step)
        if record["holding_month"] >= pd.Timestamp("2020-02-01"):
            month, weights = record["holding_month"], step[1]
            books.append(pd.DataFrame(dict(Date=month, PERMNO=weights.index, WEIGHT=weights * 100)))
            records.append(dict(month=month, cost=record["cost"], rf=rf.get(month, 0.0)))
    book = pd.concat(books, ignore_index=True)
    returns = pd.DataFrame(records).set_index("month")
    daily = daily_returns(book["PERMNO"], "2020-02-01", "2020-06-30")
    return paths_by_day(book, returns, daily)


# Each stress window on the daily path: return, the S&P 500 beside it, and the deepest fall.
def stress(path: pd.DataFrame) -> dict:
    close = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    market = close.set_index("observation_date")["SP500"]
    out = {}
    for name, (first, last) in STRESS.items():
        part = path.loc[first:last, "ret"]
        if part.empty:
            continue
        level = (1 + part).cumprod()
        # From the close before the window, so the S&P 500 counts its first day as the book does.
        index = market.loc[:last]
        start = index.loc[: pd.Timestamp(first) - pd.Timedelta(days=1)]
        out[name] = dict(
            strategy=float(level.iloc[-1] - 1),
            sp500=float(index.iloc[-1] / start.iloc[-1] - 1) if len(start) else None,
            worst_drawdown=drawdown(level),
            days=int(len(part)),
        )
    return out


# Trading a day late: the old book earns the first day, the new one only after it.
def delay(book: pd.DataFrame, returns: pd.DataFrame, daily: pd.DataFrame) -> dict:
    shift, previous = {}, None
    for month, group in book.groupby("Date"):
        days = daily[(daily.index >= month) & (daily.index < month + pd.offsets.MonthBegin(1))]
        first = days.iloc[0]
        weights = group.set_index("PERMNO")["w"]
        new = float((weights * first.reindex(weights.index).fillna(0.0)).sum())
        old = (
            new
            if previous is None
            else float((previous * first.reindex(previous.index).fillna(0.0)).sum())
        )
        shift[month], previous = old - new, weights
    shift = pd.Series(shift)
    actual = returns.loc[shift.index, "net"]
    return dict(
        months=int(len(shift)),
        information_ratio_on_time=P.information_ratio(actual),
        information_ratio_one_day_late=P.information_ratio(actual + shift),
        cost_annual=float(-shift.mean() * 12),
    )


# Marks the book every trading day of 2021-2025 and writes daily_risk.json.
def main() -> None:
    returns = paths.returns()
    book = paths.holdings()
    book = book[book["Date"].between(FIRST, LAST)].assign(w=lambda b: b["WEIGHT"] / 100)
    daily = daily_returns(book["PERMNO"], FIRST, LAST)
    if daily is None:
        print("skipped: the bundle has no daily prices, so the committed daily_risk.json stands")
        return
    path = paths_by_day(book, returns, daily)
    out = dict(
        what="The monthly book marked every trading day with CRSP daily total returns, "
        "2021-01 to 2025-12. Weights are fixed within each month; nothing trades mid-month. "
        "Net of the month's modelled costs, charged on its first day.",
        days=int(len(path)),
        risk=risk(path, returns),
        beta_to_sp500_daily=daily_beta(path),
        reconciliation=reconcile(path, returns),
        short_interest=short_interest(book),
        stress=stress(pd.concat([path_2020(), path])),
        execution_delay=delay(book, returns, daily),
    )
    paths.write_json(OUT, out)
    g, b = out["risk"]["gross_exposure"], out["beta_to_sp500_daily"]
    print(
        f"{out['days']} days: gross peaks at {g['intra_month_max']:.1%} within a month, "
        f"{g['months_above_200pct_on_any_day']} months above 200% on any day; "
        f"daily beta {b['beta']:+.3f} (se {b['stderr']:.3f})"
    )


if __name__ == "__main__":
    main()
