# exhibits/pack.json: sub-periods, costs, statistics, risk and signals.


import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import data, paths

OUT = paths.EXHIBITS

HURDLE = 0.04 / 12

# The write-up's two halves, so the attribution reads alongside them.
HALVES = {"2021_2022": ("2021-01-01", "2022-12-01"), "2023_2026": ("2023-01-01", "2026-08-01")}


# What monthly returns actually earned, compounded, never summed.
def compound(monthly: pd.Series) -> float:
    return float((1 + monthly.dropna()).prod() - 1)


# The five cost lines as the backtest recorded them, annualized.
def cost_components(df: pd.DataFrame) -> dict:
    names = dict(
        commission="cost_commission",
        spread="cost_spread",
        impact="cost_impact",
        borrow="cost_borrow",
        financing="cost_financing",
        total="cost",
    )
    return {name: float(df[column].mean() * 12) for name, column in names.items()}


# Costs' room before active return hits zero; a level, not a multiple.
def break_even(df: pd.DataFrame) -> dict:
    gross, cost = df["gross"].mean() * 12, df["cost"].mean() * 12
    multiple = (gross - 0.04) / cost
    ladder = {}
    # Runs past break-even so the chart crosses zero, not stopping short.
    for m in (1.0, 1.5, 2.0, 2.5, 3.0, multiple, multiple * 1.15):
        active = df["gross"] - df["cost"] * m - HURDLE
        ladder[f"x{m:.2f}"] = dict(
            annual_cost=float(cost * m),
            active_annual=float(active.mean() * 12),
            information_ratio=float(active.mean() / active.std() * np.sqrt(12)),
        )
    return dict(
        current_annual_cost=float(cost),
        break_even_annual_cost=float(gross - 0.04),
        break_even_multiple=float(multiple),
        ladder=ladder,
    )


# A 6-month block bootstrap, as 68 months cannot back a point estimate.
def ir_interval(active: pd.Series, draws: int = 5000, block: int = 6) -> tuple[float, float]:
    rng = np.random.default_rng(42)
    values = active.to_numpy()
    n_blocks = int(np.ceil(len(values) / block))
    out = []
    for _ in range(draws):
        # High bound is exclusive, so +1 or the last month can never be sampled.
        starts = rng.integers(0, max(1, len(values) - block + 1), n_blocks)
        sample = np.concatenate([values[s : s + block] for s in starts])[: len(values)]
        if sample.std() > 0:
            out.append(sample.mean() / sample.std() * np.sqrt(12))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


# One era's gross, cost and net: mean monthly times 12, not compounded.
def period(part: pd.DataFrame) -> dict:
    gross, cost = part["gross"].mean() * 12, part["cost"].mean() * 12
    low, high = ir_interval(part["net"] - HURDLE)
    return dict(
        months=int(len(part)),
        gross_annual=float(gross),
        cost_annual=float(cost),
        net_annual=float(part["net"].mean() * 12),
        cost_share_of_gross=float(cost / gross) if gross > 0 else None,
        information_ratio=P.information_ratio(part["net"]),
        ir_ci_low=low,
        ir_ci_high=high,
    )


# The record split in time, the first half beside the second.
def subperiods(df: pd.DataFrame) -> dict:
    year = df.index.year
    masks = {
        "full_2021_2026": year >= 2021,
        "first_half_2021_2022": year <= 2022,
        "second_half_2023_2026": year >= 2023,
        "excluding_2021": year >= 2022,
        # CRSP returns to 2025 and Compustat in 2026, so CRSP is shown alone.
        "crsp_era_2021_2025": year <= 2025,
    }
    out = {name: period(df[mask]) for name, mask in masks.items()}
    # Year by year too, compounded, so nobody takes the split on trust.
    out["by_year"] = {
        int(y): dict(
            gross=compound(g["gross"]),
            cost=float((1 + g["gross"]).prod() - (1 + g["net"]).prod()),
            net=compound(g["net"]),
        )
        for y, g in df.groupby(year)
    }
    return out


# Strategy, benchmark and market by calendar year, as the rules ask.
def by_year(df: pd.DataFrame) -> dict:
    market = B.benchmarks().set_index("month")["mkt_rf"]
    out = {}
    for year, g in df.groupby(df.index.year):
        mkt = market.reindex(g.index)
        hurdle = compound(g["rf"] + HURDLE)
        out[int(year)] = dict(
            months=int(len(g)),
            # 2026 stops in August, so do not compare it flat.
            partial_year=bool(len(g) < 12),
            strategy=compound(g["portfolio_total_return"]),
            benchmark=hurdle,
            market=compound(mkt + g["rf"]) if mkt.notna().any() else None,
            active=compound(g["portfolio_total_return"]) - hurdle,
        )
    return out


# The universe by year, so a break in how 2026 is built shows vs CRSP.
def data_by_year(universe: pd.DataFrame) -> dict:
    # Keyed on the holding month's year, the year the return belongs to.
    year = universe["eom"].dt.year + (universe["eom"].dt.month == 12)
    return {
        int(y): dict(
            names_per_month=float(part.groupby("eom").size().mean()),
            cross_sectional_std=float(part.groupby("eom")["ret_exc_lead1m"].std().median()),
            share_beyond_50pct=float((part["ret_exc_lead1m"].abs() > 0.5).mean()),
            share_missing=float(part["ret_exc_lead1m"].isna().mean()),
            returns_from="Compustat" if y == 2026 else "CRSP",
        )
        for y, part in universe.groupby(year)
    }


# What each leg contributed, since a market-neutral book is two books.
def legs(book: pd.DataFrame, universe: pd.DataFrame) -> dict:
    cols = ["permno", "holding_month", "ret_exc_lead1m", "me", "dolvol_126d", "size_grp"]
    universe = universe.assign(
        holding_month=(universe["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    )
    merged = book.merge(
        universe[cols], left_on=["PERMNO", "Date"], right_on=["permno", "holding_month"]
    )
    merged["pnl"] = merged["w"] * merged["ret_exc_lead1m"].fillna(0.0)
    out = {}
    for side, part in (("long", merged[merged["w"] > 0]), ("short", merged[merged["w"] < 0])):
        monthly = part.groupby("Date")["pnl"].sum()
        size = part["w"].abs()
        # Per dollar in the leg, so a short leg earns when its stocks fall.
        per_dollar = monthly / size.groupby(part["Date"]).sum()
        out[side] = dict(
            annual_contribution=float(monthly.mean() * 12),
            return_per_dollar_annual=float(per_dollar.mean() * 12),
            volatility=float(monthly.std() * np.sqrt(12)),
            names_per_month=float(part.groupby("Date").size().mean()),
            mean_market_cap_musd=float(part["me"].mean()),
            median_market_cap_musd=float(part["me"].median()),
            mean_dollar_volume=float(part["dolvol_126d"].mean()),
            median_dollar_volume=float(part["dolvol_126d"].median()),
            # NYSE size groups: micro and nano below the 20th pct, small below 50th.
            share_micro=float(size[part["size_grp"].isin(["micro", "nano"])].sum() / size.sum()),
            share_small_or_micro=float(
                size[part["size_grp"].isin(["small", "micro", "nano"])].sum() / size.sum()
            ),
        )
    # How much of the book sits in its ten largest positions.
    size = book.assign(a=book["w"].abs()).groupby("Date")["a"]
    top10 = size.nlargest(10).groupby(level=0).sum()
    out["top10_share_of_gross"] = float((top10 / size.sum()).mean())
    return out


# The ten largest longs and shorts by average weight, with full names.
def top_positions(book: pd.DataFrame) -> dict:
    average = book.groupby("PERMNO")["w"].sum() / book["Date"].nunique()
    label = book.sort_values("Date").groupby("PERMNO")[["TICKER", "COMPANY NAME"]].last()
    months = book.groupby("PERMNO").size()
    pick = {"long": average.nlargest(10), "short": average.nsmallest(10)}
    return {
        side: [
            dict(
                ticker=label.loc[p, "TICKER"],
                company=label.loc[p, "COMPANY NAME"],
                average_weight=float(w),
                months_held=int(months[p]),
            )
            for p, w in names.items()
        ]
        for side, names in pick.items()
    }


# The rules' statistics for the strategy, benchmark and S&P 500 alike.
def comparison(df: pd.DataFrame) -> dict:
    market = B.benchmarks().set_index("month")["mkt_rf"].reindex(df.index) + df["rf"]
    series = dict(strategy=df["portfolio_total_return"], benchmark=df["rf"] + HURDLE, sp500=market)
    out = {}
    for name, monthly in series.items():
        excess = monthly - df["rf"]
        growth = (1 + monthly).cumprod()
        # The benchmark's excess return is a constant 4%, so it has no Sharpe.
        sharpe = excess.mean() / excess.std() * np.sqrt(12) if excess.std() > 1e-9 else None
        out[name] = dict(
            annual_arithmetic=float(monthly.mean() * 12),
            annual_geometric=float(growth.iloc[-1] ** (12 / len(monthly)) - 1),
            cumulative=float(growth.iloc[-1] - 1),
            volatility=float(monthly.std() * np.sqrt(12)),
            sharpe_ratio=None if sharpe is None else float(sharpe),
            max_drawdown=float((growth / growth.cummax() - 1).min()),
            best_month=dict(month=f"{monthly.idxmax():%Y-%m}", value=float(monthly.max())),
            worst_month=dict(month=f"{monthly.idxmin():%Y-%m}", value=float(monthly.min())),
        )
    return out


# The statistics the rules list that the headline table does not carry.
def completeness(df: pd.DataFrame, book: pd.DataFrame, universe: pd.DataFrame) -> dict:
    monthly = df["portfolio_total_return"]
    per_month = book.groupby("Date")["WEIGHT"]
    ranges = dict(gross_exposure="gross_exposure", net_exposure="net_exposure")
    ranges |= dict(turnover_one_way="turnover", positions="n")
    return dict(
        average_monthly_return=float(monthly.mean()),
        cumulative_return_full_period=float((1 + monthly).prod() - 1),
        average_long_positions=float(per_month.apply(lambda s: (s > 0).sum()).mean()),
        average_short_positions=float(per_month.apply(lambda s: (s < 0).sum()).mean()),
        average_absolute_position_weight=float(book["WEIGHT"].abs().mean() / 100),
        by_year=by_year(df),
        comparison=comparison(df),
        # The rules ask for averages and extremes, not just averages.
        ranges={
            name: dict(mean=float(df[c].mean()), min=float(df[c].min()), max=float(df[c].max()))
            for name, c in ranges.items()
        },
        legs=legs(book, universe),
        top_positions=top_positions(book),
        best_month=dict(month=str(monthly.idxmax().date()), value=float(monthly.max())),
        worst_month=dict(month=str(monthly.idxmin().date()), value=float(monthly.min())),
    )


# Factor regression; the intercept is what none explain, what we earn.
def factor_fit(excess: pd.Series, factors: pd.DataFrame) -> dict:
    names = list(factors.columns)
    both = pd.concat([excess.rename("r"), factors], axis=1, sort=True).dropna()
    fit = P.regress(both["r"], both[names])
    # Each factor's squared-beta share, not summing as factors correlate.
    individual = {n: float((fit.params[n] ** 2) * both[n].var() / both["r"].var()) for n in names}
    fitted_share = float(np.var(fit.fittedvalues, ddof=1) / both["r"].var())
    return dict(
        alpha_annual=float(fit.params["const"] * 12),
        alpha_t=float(fit.tvalues["const"]),
        betas={k: float(fit.params[k]) for k in names},
        t_stats={k: float(fit.tvalues[k]) for k in names},
        r_squared=float(fit.rsquared),
        individual_variance_contribution=individual,
        unallocated_after_individual_contributions=float(1 - sum(individual.values())),
        explained_by_all_three=fitted_share,
        residual_share=float(1 - fitted_share),
        months=int(len(both)),
    )


# Each year's excess at full-period loadings: style part plus selection.
def style_by_year(excess: pd.Series, factors: pd.DataFrame) -> dict:
    names = list(factors.columns)
    both = pd.concat([excess.rename("r"), factors], axis=1, sort=True).dropna()
    fit = P.regress(both["r"], both[names])
    style = both[names] @ fit.params[names]
    return {
        str(year): dict(
            months=int(len(part)),
            total=float(part["r"].sum()),
            styles=float(style.loc[part.index].sum()),
            selection=float(part["r"].sum() - style.loc[part.index].sum()),
        )
        for year, part in both.groupby(both.index.year)
    }


# Beta by era and rolling year, since a full-period beta can hide drift.
def beta_drift(df: pd.DataFrame) -> dict:
    market = B.benchmarks().set_index("month")["mkt_rf"].reindex(df.index)
    excess = df["portfolio_total_return"] - df["rf"]
    out = {}
    for name, (a, b) in {"2021_2023": ("2021", "2023"), "2024_2026": ("2024", "2026")}.items():
        fit = P.regress(excess.loc[a:b], market.loc[a:b])
        out[name] = dict(
            beta=float(fit.params.iloc[1]),
            stderr=float(fit.bse.iloc[1]),
            t=float(fit.tvalues.iloc[1]),
            months=int(fit.nobs),
        )
    rolling = (excess.rolling(12).cov(market) / market.rolling(12).var()).dropna()
    band = P.REALIZED_BETA_LIMIT
    out["rolling_12m_outside_band"] = float((rolling.abs() > band).mean())
    out["rolling_12m_windows"] = int(len(rolling))
    # The 95% 12-month band for a zero-beta book with our residual risk.
    residual = P.regress(excess, market).resid.std()
    spread = market.rolling(12).std() * np.sqrt(11)
    noise = (1.96 * residual / spread).reindex(rolling.index)
    out["rolling_12m_outside_noise_band"] = float((rolling.abs() > noise).mean())
    out["rolling_12m"] = {
        f"{m:%Y-%m}": dict(beta=float(b), noise_band=float(n))
        for m, b, n in zip(rolling.index, rolling, noise)
    }
    return out


# Each leg's AI crowd score percentile: 50 is the middle, 100 the top.
def crowding(book: pd.DataFrame) -> dict | None:
    path = P.MODELS / "book_inputs.parquet"
    inputs = data.read(path) if path.exists() else pd.DataFrame()
    if "crowd_score" not in inputs:
        return None
    inputs["crowd"] = inputs.groupby("eom")["crowd_score"].rank(pct=True) * 100
    held = book.assign(eom=(book["Date"] - pd.offsets.MonthEnd(1)).astype("datetime64[s]"))
    held = held.merge(
        inputs[["permno", "eom", "crowd"]],
        left_on=["PERMNO", "eom"],
        right_on=["permno", "eom"],
        how="left",
    )
    sides = dict(long=held[held["w"] > 0], short=held[held["w"] < 0])
    return {
        side: dict(
            weighted_crowd_percentile=float(
                (part["crowd"] * part["w"].abs()).sum()
                / part.loc[part["crowd"].notna(), "w"].abs().sum()
            ),
            share_in_top_crowd_decile=float(
                part.loc[part["crowd"] >= 90, "w"].abs().sum() / part["w"].abs().sum()
            ),
        )
        for side, part in sides.items()
    }


# FF3, then FF5 plus momentum, as our signals hold value and momentum.
def risk(df: pd.DataFrame) -> dict:
    excess = df["portfolio_total_return"] - df["rf"]
    active = (df["net"] - HURDLE).sort_values()
    three = B.french("ff_factors.zip", ["mkt_rf", "smb", "hml", "rf"]).drop(columns="rf")
    five = B.french("ff5_factors.zip", ["mkt_rf", "smb", "hml", "rmw", "cma", "rf"])
    extended = five.drop(columns="rf").join(B.french("ff_momentum.zip", ["mom"]), how="inner")
    rolling = df["net"].sub(HURDLE).rolling(12)
    ratio = (rolling.mean() / rolling.std() * np.sqrt(12)).dropna()
    return dict(
        attribution=factor_fit(excess, three),
        five_factor_momentum=factor_fit(excess, extended),
        style_by_year=style_by_year(excess, extended),
        # Twelve months cannot pin six loadings, so split by window, not year.
        five_factor_momentum_by_window={
            k: factor_fit(excess.loc[a:b], extended) for k, (a, b) in HALVES.items()
        },
        book={
            leg: dict(
                annual=float(df[leg].mean() * 12),
                volatility=float(df[leg].std() * np.sqrt(12)),
                worst_month=float(df[leg].min()),
                best_month=float(df[leg].max()),
            )
            for leg in ("gross", "net")
        },
        # Tail risk that monthly volatility hides; a committee asks by name.
        tails=dict(
            var_95_monthly=float(np.percentile(active, 5)),
            cvar_95_monthly=float(active.iloc[: int(np.ceil(len(active) * 0.05))].mean()),
            skew=float(active.skew()),
            excess_kurtosis=float(active.kurtosis()),
            worst_three_months=[float(x) for x in active.iloc[:3]],
        ),
        # Rolling 12-month IR; time under water says more than its average.
        consistency=dict(
            windows=int(len(ratio)),
            share_negative=float((ratio < 0).mean()),
            median=float(ratio.median()),
            worst=float(ratio.min()),
            best=float(ratio.max()),
        ),
    )


# A month's pure signal returns, joint so none gets neighbours' credit.
def pure_returns(month: pd.DataFrame, cols: list[str]) -> pd.Series:
    month = month.dropna(subset=["ret_exc_lead1m"])
    y = (month["ret_exc_lead1m"] - month["ret_exc_lead1m"].mean()).to_numpy()
    x = np.c_[np.ones(len(month)), month[cols].to_numpy()]
    return pd.Series(np.linalg.lstsq(x, y, rcond=None)[0][1:], index=cols)


# Annualized mean and t, as a sign that flips monthly is noise.
def contribution_summary(frame: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for c in cols:
        s = frame[f"con_{c}"]
        out[c] = dict(
            contribution_annual=float(s.mean() * 12),
            t=float(s.mean() / s.std() * np.sqrt(len(s))) if s.std() else 0.0,
            average_exposure=float(frame[f"exp_{c}"].mean()),
            sign=P.SIGNALS[c],
        )
    out["residual"] = dict(contribution_annual=float(frame["residual"].mean() * 12))
    out["explained_total"] = dict(contribution_annual=float(frame["explained"].mean() * 12))
    return out


# Which of twelve signals earned the gross: exposure times pure return.
def attribution(book: pd.DataFrame, universe: pd.DataFrame, gross: pd.Series) -> dict:
    cols = list(P.SIGNALS)
    # Scored as the composite scores them: ranked, signed, gaps at zero.
    for col, sign in P.SIGNALS.items():
        universe[col] = (P.rank_z(universe, col) * sign).fillna(0.0)
    held = book.assign(eom=book["Date"] - pd.offsets.MonthEnd(1)).merge(
        universe[["permno", "eom", "sector", "ret_exc_lead1m", *cols]],
        left_on=["PERMNO", "eom"],
        right_on=["permno", "eom"],
        how="left",
    )
    rows = []
    for month, cross in universe.groupby("eom"):
        pure = pure_returns(cross, cols)
        mine = held[held["eom"] == month]
        exposure = mine[cols].fillna(0.0).mul(mine["w"], axis=0).sum()
        rows.append(
            dict(
                holding_month=(month + pd.offsets.MonthBegin(1)).normalize(),
                **{f"exp_{c}": float(exposure[c]) for c in cols},
                **{f"con_{c}": float(exposure[c] * pure[c]) for c in cols},
            )
        )
    table = pd.DataFrame(rows).set_index("holding_month")
    table["explained"] = table[[f"con_{c}" for c in cols]].sum(axis=1)
    table["residual"] = gross - table["explained"]
    return dict(
        what="Gross return split across the twelve signals by exposure times each signal's pure "
        "monthly return, from a joint cross-sectional regression. Before costs.",
        months=int(len(table)),
        full=contribution_summary(table, cols),
        halves={k: contribution_summary(table.loc[a:b], cols) for k, (a, b) in HALVES.items()},
        by_year={
            str(y): {c: float(g[f"con_{c}"].sum()) for c in cols}
            for y, g in table.groupby(table.index.year)
        },
        worst_months=worst_months(held, table, gross, cols),
    )


# The ten worst months by leg, sector and signal, to trace each loss.
def worst_months(held: pd.DataFrame, table: pd.DataFrame, gross: pd.Series, cols: list) -> list:
    held = held.assign(earned=held["w"] * held["ret_exc_lead1m"].fillna(0.0))
    out = []
    for month in gross.nsmallest(10).index:
        mine = held[held["Date"] == month]
        by_sector = mine.groupby("sector")["earned"].sum()
        signals = {c: float(table.loc[month, f"con_{c}"]) for c in cols}
        out.append(
            dict(
                month=f"{month:%Y-%m}",
                gross=float(gross[month]),
                long=float(mine.loc[mine["w"] > 0, "earned"].sum()),
                short=float(mine.loc[mine["w"] < 0, "earned"].sum()),
                worst_sectors={k: float(v) for k, v in by_sector.nsmallest(3).items()},
                worst_signals=dict(sorted(signals.items(), key=lambda kv: kv[1])[:3]),
            )
        )
    return out


# Every committee statistic, written to pack.json.
def main() -> None:
    df = paths.returns()
    book = paths.holdings()
    book["w"] = book["WEIGHT"] / 100
    out = dict(
        what="The book-side exhibits, each from submission/returns.csv and holdings.csv.",
        subperiod=subperiods(df),
        costs=dict(components=cost_components(df), break_even=break_even(df)),
        completeness=completeness(df, book, P.universe()),
        data_by_year=data_by_year(P.universe()),
        risk=risk(df),
        beta_drift=beta_drift(df),
        crowding=crowding(book),
        attribution=attribution(book, P.universe(), df["gross"]),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    paths.write_json(OUT / "pack.json", out, rounded=False)

    for name in ("full_2021_2026", "first_half_2021_2022", "second_half_2023_2026"):
        s = out["subperiod"][name]
        low, high = s["ir_ci_low"], s["ir_ci_high"]
        print(f"{name:<24} IR {s['information_ratio']:+.2f}, 95% CI [{low:.2f}, {high:.2f}]")
    b = out["costs"]["break_even"]
    print(f"costs {b['current_annual_cost']:.1%}/yr, break-even {b['break_even_annual_cost']:.1%}")
    e = out["risk"]["five_factor_momentum"]
    print(f"six-factor alpha {e['alpha_annual']:+.1%}/yr, t = {e['alpha_t']:.2f}")


if __name__ == "__main__":
    main()
