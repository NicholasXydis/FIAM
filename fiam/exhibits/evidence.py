# Each switch's pass or fail test, and the switched book vs shipped.

import json
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam import benchmarks as B
from fiam import book as P
from fiam import costs as C
from fiam import data, layers, stats, v2
from fiam import mandate as M

OUT = v2.OUT / "evidence.json"
EXP = Path("research") / "exp" / "results"
# Trials 2 to 5 run outside this code, with their gate reruns.
ANDREW_TRIALS = 5
WINDOWS = {"check": v2.CHECK, "record": v2.RECORD}
PARTS = ("cost_commission", "cost_spread", "cost_impact", "cost_borrow", "cost_financing")
THEMES = dict(
    profitability=("ope_be", "gp_at", "qmj"),
    investment=("noa_gr1a", "at_gr1"),
    issuance=("eqnetis_at", "chcsho_12m"),
    momentum=("ret_12_1",),
    value=("be_me",),
    earnings=("niq_su",),
    risk=("o_score", "ivol_capm_21d"),
)


# One run's saved returns, holdings and summary.
def load(name: str, window: str) -> tuple[pd.DataFrame, pd.DataFrame, dict] | None:
    folder = v2.OUT / name / window
    if not (folder / "stats.json").exists():
        return None
    book = pd.read_csv(folder / "returns.csv", parse_dates=["holding_month", "forecast_eom"])
    held = data.read(folder / "holdings.parquet")
    return book.set_index("holding_month"), held, json.loads((folder / "stats.json").read_text())


# The monthly market excess return each window's stats use, by month.
def market(window: str) -> pd.Series:
    bm = B.benchmarks().set_index("month")
    return bm["mkt_rf_crsp" if window == "check" else "mkt_rf"]


# A window's universe with the shipped or switched signal, built once.
@cache
def frame(window: str, on: frozenset) -> pd.DataFrame:
    return v2.universe(WINDOWS[window], v2.Settings(on, 1e7, M.V1), v2.params())


# Mean monthly weight correlation of two books over names either holds.
def weight_correlation(a: pd.DataFrame, b: pd.DataFrame) -> float:
    out = []
    for eom, wa in a.groupby("eom"):
        wb = b[b["eom"] == eom]
        both = pd.concat(
            [wa.set_index("permno")["weight"], wb.set_index("permno")["weight"]], axis=1
        ).fillna(0.0)
        if len(both) > 2:
            out.append(both.corr().iloc[0, 1])
    return float(np.mean(out)) if out else float("nan")


# Each switch's test at every capital level, against the shipped book.
def verdicts() -> dict:
    caps = {c: f"{c:.0e}".replace("+0", "") for c in v2.CAPITALS}
    base = {c: load(f"v1@{tag}", "check") for c, tag in caps.items()}
    out = {}

    # The cost-aware switch's test, also used for the grinold switch.
    for member in ("costs", "grinold"):
        runs = {c: load(f"{member}@{tag}", "check") for c, tag in caps.items()}
        if not all(runs.values()):
            continue
        cheaper = all(runs[c][2]["cost_annual"] < base[c][2]["cost_annual"] for c in caps)
        calmer = all(runs[c][2]["turnover"] < base[c][2]["turnover"] for c in caps)
        corr = min(weight_correlation(runs[c][1], base[c][1]) for c in caps)
        out[member] = dict(cost_falls_everywhere=cheaper, turnover_falls_everywhere=calmer)
        out[member] |= dict(weight_correlation_min=corr, passed=cheaper and calmer and corr >= 0.7)

    p = load("persistence@5e8", "check")
    drop = 1 - p[2]["turnover"] / base[5e8][2]["turnover"]
    corr = weight_correlation(p[1], base[5e8][1])
    out["persistence"] = dict(turnover_drop=drop, weight_correlation=corr)
    out["persistence"]["passed"] = drop >= 0.10 and corr >= 0.7

    fixed = v2.params()
    errors = fixed.get("beta_errors", {})
    b = load("beta@1e7", "check")
    closer = abs(b[2]["beta_realized"]) < abs(base[1e7][2]["beta_realized"])
    better = errors.get(fixed.get("beta_choice"), 1) < errors.get("beta_60m", 0)
    out["beta"] = dict(forecast_better=better, realized_closer_to_zero=closer)
    out["beta"] |= dict(realized=b[2]["beta_realized"], v1=base[1e7][2]["beta_realized"])
    out["beta"]["passed"] = better and closer

    s = load("shorts@1e7", "check")
    borrow = s[2]["cost_borrow"] < base[1e7][2]["cost_borrow"]
    tail = s[2]["short_leg_worst"] >= base[1e7][2]["short_leg_worst"]
    out["shorts"] = dict(borrow_falls=borrow, worst_short_month_no_worse=tail)
    out["shorts"] |= dict(borrow=s[2]["cost_borrow"], v1_borrow=base[1e7][2]["cost_borrow"])
    out["shorts"]["passed"] = borrow and tail

    liq = {c: load(f"liquidity@{tag}", "check") for c, tag in caps.items()}
    binds = all(liq[c][2]["days_to_liquidate_max"] <= 2.0 + 1e-6 for c in caps if c <= 1e9)
    cheaper = all(liq[c][2]["cost_annual"] < base[c][2]["cost_annual"] for c in (1e9, 5e9))
    out["liquidity"] = dict(cap_binds=binds, cheaper_at_1b_and_5b=cheaper, passed=binds and cheaper)

    # Risk sizing 2017-20 (model from 2017-01): vol a unit gross vs shipped.
    def vol(run: tuple) -> float:
        b = run[0][run[0]["forecast_eom"] >= "2016-12-31"]
        return float(b["gross"].std() * np.sqrt(12) / b["gross_exposure"].mean())

    r = load("risk@1e7", "check")
    if r:
        calmer = vol(r) < vol(base[1e7])
        out["risk"] = dict(vol_per_gross=vol(r), v1=vol(base[1e7]), passed=calmer)

    out |= parts(out)
    out |= final_parts(out)

    whole = {c: load(f"v2@{tag}", "check") for c, tag in caps.items()}
    out["v2"] = {
        tag: dict(
            cost=whole[c][2]["cost_annual"],
            v1_cost=base[c][2]["cost_annual"],
            turnover=whole[c][2]["turnover"],
            v1_turnover=base[c][2]["turnover"],
            beta=whole[c][2]["beta_realized"],
            v1_beta=base[c][2]["beta_realized"],
        )
        for c, tag in caps.items()
    }
    return out


# Annualized Sharpe ratio of a monthly net return series.
def sharpe(net: pd.Series) -> float:
    return float(net.mean() / net.std() * np.sqrt(12))


# Each extra part alone on the passing-switch book, against that book.
def parts(members: dict) -> dict:
    base = v2.passing(members)
    ref = {c: load(v2.Settings(base, c).name, "check") for c in v2.CAPITALS}
    alone = {
        p: {c: load(v2.Settings(base | {p}, c).name, "check") for c in v2.CAPITALS}
        for p in v2.PARTS
    }
    out = {}
    s = alone["size"]
    if all(s.values()):
        big = (5e8, 1e9, 5e9)
        cheaper = all(s[c][2]["cost_annual"] < ref[c][2]["cost_annual"] for c in big)
        richer = all(s[c][2]["net_annual"] > ref[c][2]["net_annual"] for c in big)
        gap = s[1e7][2]["information_ratio"] - ref[1e7][2]["information_ratio"]
        out["size"] = dict(cheaper_at_scale=cheaper, more_net_at_scale=richer, ir_gap_at_10m=gap)
        out["size"]["passed"] = cheaper and richer and gap >= -0.10
    mine, theirs = alone["lowvol"][1e7], ref[1e7]
    if mine:
        vols = [float(r[0]["net"].std() * np.sqrt(12)) for r in (mine, theirs)]
        betas = [r[2]["beta_realized"] for r in (mine, theirs)]
        out["lowvol"] = dict(beta=betas[0], v2_pass_beta=betas[1], vol=vols[0], v2_pass_vol=vols[1])
        out["lowvol"]["passed"] = abs(betas[0]) < abs(betas[1]) and vols[0] < vols[1]

    # Risk model starts 2017-01, so holding months from 2017-02 judge it.
    def steadiness(run: tuple) -> dict:
        net = run[0].loc["2017-02-01":, "net"]
        yearly = net.groupby(net.index.year).std() * np.sqrt(12)
        return dict(
            yearly_vol_sd=float(yearly.std()), drawdown=stats.drawdown(net), sharpe=sharpe(net)
        )

    mine = alone["voltarget"][1e7]
    if mine:
        a, b = steadiness(mine), steadiness(theirs)
        out["voltarget"] = {**a, **{f"v2_pass_{k}": v for k, v in b.items()}}
        out["voltarget"]["passed"] = (
            a["yearly_vol_sd"] < b["yearly_vol_sd"]
            and a["drawdown"] > b["drawdown"]
            and a["sharpe"] >= b["sharpe"] - 0.10
        )
    mine = alone["brake"][1e7]
    if mine:
        a, b = (stats.drawdown(r[0]["net"]) for r in (mine, theirs))
        sa, sb = (sharpe(r[0]["net"]) for r in (mine, theirs))
        out["brake"] = dict(drawdown=a, v2_pass_drawdown=b, sharpe=sa, v2_pass_sharpe=sb)
        out["brake"]["passed"] = a > b and sa >= sb
    return out


# A book's submission figures, 2021-2026, with its 2016-2020 IR beside.
def scorecard(record: pd.DataFrame, check: dict) -> dict:
    full = P.performance(record)
    perf, costs = full["performance"], full["costs"]
    keys = ("information_ratio", "sharpe_ratio", "return_net_annual", "volatility_annual")
    keys += ("max_drawdown_total", "beta_realized", "beta_stderr", "alpha_annual", "alpha_tstat")
    keys += ("hit_rate_positive_active_months",)
    out = {k: perf[k] for k in keys}
    out |= dict(
        worst_month=float(record["net"].min()),
        cost_annual=costs["cost_annual"],
        turnover=costs["turnover_monthly_one_way"],
        positions=full["compliance"]["positions_average"],
        months_underwater_max=stats.underwater(record["net"]),
        rolling_12m_positive=float((record["net"].rolling(12).sum().dropna() > 0).mean()),
        gross_max=full["compliance"]["gross_exposure_max"],
        information_ratio_2016_2020=check["information_ratio"],
    )
    return out


# The two tested rules, each alone on `base_three` at $10M.
def final_parts(verdicts: dict) -> dict:
    base = v2.base_three(verdicts)
    ref = load(v2.Settings(base, 1e7).name, "check") if base else None
    if ref is None:
        return {}
    rising = market("check") > 0.03

    # A run's worst short-leg month and short-leg sum in 3%+ market months.
    def shorts(run: tuple) -> tuple[float, float]:
        leg = run[0]["short_leg"]
        return float(leg.min()), float(leg[rising.reindex(leg.index).fillna(False)].sum())

    out, ir0 = {}, ref[2]["information_ratio"]
    mine = load(v2.Settings(base | {"riskcap"}, 1e7).name, "check")
    if mine:
        (worst, rally), (worst0, rally0) = shorts(mine), shorts(ref)
        ir = mine[2]["information_ratio"]
        out["riskcap"] = dict(short_worst=worst, base_short_worst=worst0, short_in_rallies=rally)
        out["riskcap"] |= dict(base_short_in_rallies=rally0, ir=ir, base_ir=ir0)
        out["riskcap"]["passed"] = worst > worst0 and rally > rally0 and ir >= ir0 - 0.10
    mine = load(v2.Settings(base | {"adaptive"}, 1e7).name, "check")
    if mine:
        under, under0 = (stats.underwater(r[0]["net"]) for r in (mine, ref))
        ir = mine[2]["information_ratio"]
        out["adaptive"] = dict(underwater=under, base_underwater=under0, ir=ir, base_ir=ir0)
        out["adaptive"]["passed"] = under < under0 and ir > ir0
    return out


# The chosen book's daily path at $10M, 2021-25: risk, gross vs 200%.
def final_daily(chosen: frozenset | None) -> dict:
    run = load(v2.Settings(chosen, 1e7).name, "record") if chosen else None
    if run is None:
        return {}
    held = run[1]
    rows = data.research("daily_market", ["permno", "date", "total_return"])
    rows = rows[rows["permno"].isin(held["permno"].unique())]
    returns = rows.pivot_table(index="date", columns="permno", values="total_return")
    f = layers.load("market/factors_daily")
    mkt = f.set_index(pd.to_datetime(f["date"]))["mktrf"]
    path = stats.daily_gross(held, returns)
    return stats.daily_risk(held, returns, mkt) | dict(
        gross_max_daily=float(path["gross"].max()),
        days_over_200=int((path["gross"] > 2.0).sum()),
        days=len(path),
        last_day=str(path.index.max().date()),
    )


# The parts and chosen books vs the rest by capital: bootstrap, DSR.
def final_book(verdicts: dict, counts: dict) -> dict:
    final = v2.final(verdicts)
    if final is None:
        return {}
    chosen = v2.final_three(verdicts)
    out = dict(switches=sorted(final), name=v2.Settings(final).name.split("@")[0])
    if chosen:
        out["final"] = dict(switches=sorted(chosen), name=v2.Settings(chosen).name.split("@")[0])
    for cap in v2.CAPITALS:
        tag = f"{cap:.0e}".replace("+0", "")
        names = {
            "v1": f"v1@{tag}",
            "v2": f"v2@{tag}",
            "v2-pass": v2.Settings(v2.passing(verdicts), cap).name,
            "v3": v2.Settings(final, cap).name,
        }
        if chosen:
            names["final v3"] = v2.Settings(chosen, cap).name
        books = {k: load(name, "record") for k, name in names.items()}
        if not all(books.values()):
            continue
        net = {k: b[0]["net"] for k, b in books.items()}
        checks = {k: load(name, "check")[2] for k, name in names.items()}
        gaps = {
            f"{a.replace(' ', '_')}_minus_{b.replace('-', '_')}": stats.bootstrap_mean(
                (net[a] - net[b]).dropna()
            )
            for a, b in (("v3", "v1"), ("v3", "v2-pass"), ("final v3", "v1"), ("final v3", "v3"))
            if a in net
        }
        out[tag] = dict(
            books={k: scorecard(b[0], checks[k]) for k, b in books.items()},
            **gaps,
            deflated_sharpe={
                f"{name} {kind}": P.deflated_sharpe(series, counts[kind])[0]
                for name, series in net.items()
                for kind in ("full", "effective")
            },
        )
    return out


# Full counts each config once. Effective merges series with corr > 0.9.
def trial_counts() -> dict:
    series = {f"exp/{p.stem}": p for p in sorted(EXP.glob("*.csv"))}
    configs = pd.read_csv(v2.OUT / "trials.csv")["name"].str.split("@").str[0].unique()
    for config in configs:
        saved = sorted(v2.OUT.glob(f"{config}@*/record/returns.csv"))
        if saved:
            series[config] = saved[0]
    nets = {k: pd.read_csv(p, index_col="holding_month")["net"] for k, p in series.items()}
    groups: list[pd.Series] = []
    for net in nets.values():
        if not any(
            len(net.index.intersection(g.index)) >= 24 and net.corr(g) > 0.9 for g in groups
        ):
            groups.append(net)
    unsaved = sum(c not in series for c in configs)
    exp = len(series) - sum(c in series for c in configs)
    return dict(
        full=stats.TRIALS_PAST + exp + ANDREW_TRIALS + len(configs),
        effective=stats.TRIALS_PAST + ANDREW_TRIALS + len(groups) + unsaved,
        saved_series=len(nets),
        groups=len(groups),
    )


# Each month's Spearman IC with the sector- and beta-neutral return.
@cache
def monthly_ic(on: frozenset) -> pd.Series:
    parts = []
    for window in WINDOWS:
        df = frame(window, on)
        both = pd.DataFrame(
            dict(eom=df["eom"], s=df["signal"], r=P.neutralize(df, df["ret_exc_lead1m"]))
        ).dropna()
        parts.append(
            both.groupby("eom")[["s", "r"]].apply(lambda g: g["s"].corr(g["r"], "spearman"))
        )
    return pd.concat(parts)


# Break-even IC, gross = a + bIC + c mkt: IC* = (cost + hurdle - a)/b.
def break_even(name: str, on: frozenset) -> dict:
    ic, rows = monthly_ic(on), []
    for window in WINDOWS:
        book = load(f"{name}@1e7", window)[0]
        rows.append(
            pd.DataFrame(
                dict(
                    gross=book["gross"].to_numpy(),
                    cost=book["cost"].to_numpy(),
                    ic=ic.reindex(book["forecast_eom"]).to_numpy(),
                    mkt=market(window).reindex(book.index).to_numpy(),
                )
            )
        )
    both = pd.concat(rows).dropna()
    fit = sm.OLS(both["gross"], sm.add_constant(both[["ic", "mkt"]])).fit()
    a, b = float(fit.params["const"]), float(fit.params["ic"])
    return dict(
        a=a,
        b=b,
        b_t=float(fit.tvalues["ic"]),
        ic_star=(both["cost"].mean() + stats.HURDLE - a) / b,
        ic_realized=float(both["ic"].mean()),
        months=len(both),
    )


# Canary: a signal shuffled within months must show no IC (|t| < 2).
def shuffled_ic(seed: int = 42) -> dict:
    rng, ics = np.random.default_rng(seed), []
    for window in WINDOWS:
        df = frame(window, frozenset())
        r = P.neutralize(df, df["ret_exc_lead1m"])
        for _, rows in df.groupby("eom").groups.items():
            s = pd.Series(rng.permutation(df.loc[rows, "signal"].to_numpy()), index=rows)
            ics.append(s.corr(r.loc[rows], "spearman"))
    ics = pd.Series(ics).dropna()
    t = ics.mean() / ics.std() * np.sqrt(len(ics))
    return dict(mean=float(ics.mean()), t=float(t), passed=bool(abs(t) < 2))


# Switched minus shipped at $10M: bootstrapped net, cost, beta gaps.
def versus(window: str) -> dict:
    a, b = load("v1@1e7", window)[0], load("v2@1e7", window)[0]
    f = pd.DataFrame(
        dict(d=b["net"] - a["net"], c=b["cost"] - a["cost"], a=a["net"], b=b["net"])
    ).assign(m=market(window).reindex(a.index))

    # The switched book's market beta minus the shipped one's, same months.
    def beta_gap(g: pd.DataFrame) -> float:
        x = np.column_stack([np.ones(len(g)), g["m"]])
        fit = np.linalg.lstsq(x, g[["b", "a"]].to_numpy(), rcond=None)[0]
        return float(fit[1, 0] - fit[1, 1])

    return dict(
        net=stats.bootstrap(f, lambda g: g["d"].mean()),
        cost=stats.bootstrap(f[["c"]], lambda g: g["c"].mean()),
        beta=stats.bootstrap(f, beta_gap),
    )


# Monthly dashboard and neutrality tests, both books at $10M, by window.
def comparison() -> dict:
    out = {}
    for window in WINDOWS:
        mkt = market(window)
        out[window] = {}
        for name in ("v1", "v2"):
            book = load(f"{name}@1e7", window)[0]
            out[window][name] = stats.dashboard(book, mkt) | dict(
                neutrality=stats.neutrality(book["net"], mkt),
                patton=stats.patton(book["net"], mkt.reindex(book.index)),
            )
        out[window]["v2_minus_v1"] = versus(window)
    return out


# Base and switched books at $10M, their daily stock returns, market.
@cache
def daily_inputs() -> tuple[dict, pd.DataFrame, pd.Series]:
    held = {(n, w): load(f"{n}@1e7", w)[1] for n in ("v1", "v2") for w in WINDOWS}
    names = pd.concat(held.values())["permno"].unique()
    rows = data.research("daily_market", ["permno", "date", "total_return"])
    rows = rows[rows["permno"].isin(names)]
    returns = rows.pivot_table(index="date", columns="permno", values="total_return")
    f = layers.load("market/factors_daily")
    return held, returns, f.set_index(pd.to_datetime(f["date"]))["mktrf"]


# Daily risk at $10M, both books: Dimson beta, VaR, CVaR, concentration.
def daily() -> dict:
    held, returns, mkt = daily_inputs()
    return {f"{n} {w}": stats.daily_risk(h, returns, mkt) for (n, w), h in held.items()}


# Warning signs, shown only: when each fired, and the next 3 months net.
def warning_signs(name: str) -> dict:
    held, returns, mkt = daily_inputs()
    book = pd.concat([load(f"{name}@1e7", w)[0] for w in WINDOWS]).sort_index()
    # Keyed by decision month-end: the net of the next three holding months.
    ahead = pd.Series(
        book["net"][::-1].rolling(3).sum()[::-1].to_numpy(), index=book["forecast_eom"]
    )
    daily = pd.concat([stats.daily_book(held[(name, w)], returns) for w in WINDOWS]).sort_index()
    both = pd.concat([daily.rename("r"), mkt.rename("m")], axis=1).dropna()
    var_m, cov = both["m"].rolling(126).var(), both["r"].rolling(126).cov(both["m"])
    beta = cov / var_m
    resid = both["r"].rolling(126).var() - cov**2 / var_m
    t = beta * np.sqrt(124 * var_m / resid)
    fired = ((beta.abs() > 0.20) & (t.abs() > 2)).resample("ME").last()
    short = (book["gross_exposure"] - book["net_exposure"]) / 2
    fee = book["cost_borrow"] * 12 / short
    calm = fee[book["forecast_eom"] <= "2020-11-30"].median()
    signs = dict(
        # Known at the month-end of the daily data.
        daily_beta=set(fired[fired.fillna(False).astype(bool)].index),
        # Known when the holding month's borrow is billed, at its end.
        borrow_fee=set(book.index[fee > 2 * calm] + pd.offsets.MonthEnd(0)),
        # Known at the decision.
        days_to_liquidate=set(book["forecast_eom"][book["days_to_liquidate_max"] > 5]),
    )
    out = dict(next_3_months_average=float(ahead.mean()))
    for sign, months in signs.items():
        hit = ahead.reindex(sorted(months)).dropna()
        out[sign] = dict(
            months=len(months),
            first=[f"{m:%Y-%m}" for m in sorted(months)][:12],
            next_3_months=float(hit.mean()) if len(hit) else None,
        )
    return out


# 2016-20: beta x market each month against the rest, bootstrapped.
def beta_drag(name: str) -> dict:
    book = load(f"{name}@1e7", "check")[0]
    mkt = market("check").reindex(book.index)
    beta = float(P.regress(book["net"], mkt).params.iloc[1])
    drag = beta * mkt
    rest = book["net"] - drag
    return dict(beta=beta, drag=stats.bootstrap_mean(drag), rest=stats.bootstrap_mean(rest))


# Losing 2023-26 months split by theme exposure x payoff; rest is stock.
def themes(name: str, on: frozenset) -> dict:
    df = frame("record", on)
    scores = P.scores(df, P.SIGNALS).set_axis(list(P.SIGNALS), axis=1)
    z = pd.DataFrame({t: scores[list(cols)].mean(axis=1) for t, cols in THEMES.items()})
    z = (z - z.groupby(df["eom"]).transform("mean")) / z.groupby(df["eom"]).transform("std")
    z["permno"], z["eom"], z["ret"] = df["permno"], df["eom"], df["ret_exc_lead1m"]
    book, held = load(f"{name}@1e7", "record")[:2]
    losing = book[(book["net"] < 0) & (book["forecast_eom"] >= "2022-12-31")]
    total = dict.fromkeys(THEMES, 0.0)
    for eom in losing["forecast_eom"]:
        month = z[z["eom"] == eom].dropna()
        x = np.column_stack([np.ones(len(month)), month[list(THEMES)]])
        payoff = np.linalg.lstsq(x, month["ret"].to_numpy(), rcond=None)[0][1:]
        w = held[held["eom"] == eom].set_index("permno")["weight"]
        exposure = month.set_index("permno")[list(THEMES)].reindex(w.index).fillna(0.0).T @ w
        for theme, e, p in zip(THEMES, exposure, payoff):
            total[theme] += float(e * p)
    loss = float(losing["net"].sum())
    return dict(months=len(losing), loss=loss, themes=total, rest=loss - sum(total.values()))


# Months by VIX vs its 2000-20 p75 and market sign. Cells under 12 hide.
def regimes(name: str) -> dict:
    vix = layers.load("market/vix_daily")
    month_end = vix.set_index(pd.to_datetime(vix["date"]))["vix"].resample("ME").last()
    threshold = float(month_end[:"2020-12-31"].quantile(0.75))
    rows = []
    for window in WINDOWS:
        book = load(f"{name}@1e7", window)[0]
        rows.append(
            pd.DataFrame(
                dict(
                    net=book["net"].to_numpy(),
                    vix=month_end.reindex(book["forecast_eom"]).to_numpy(),
                    mkt=market(window).reindex(book.index).to_numpy(),
                )
            )
        )
    both = pd.concat(rows).dropna()
    out = dict(vix_threshold=threshold)
    for (high, up), cell in both.groupby([both["vix"] > threshold, both["mkt"] > 0]):
        key = f"{'high' if high else 'low'} VIX, market {'up' if up else 'down'}"
        out[key] = dict(months=len(cell))
        if len(cell) >= 12:
            out[key] |= dict(
                mean_net=float(cell["net"].mean()), hit=float((cell["net"] > 0).mean())
            )
    return out


# Annual cost by component, shipped vs switched, by capital, window.
def waterfall() -> dict:
    out = {}
    for c in v2.CAPITALS:
        tag = f"{c:.0e}".replace("+0", "")
        for window in WINDOWS:
            a, b = load(f"v1@{tag}", window), load(f"v2@{tag}", window)
            if a and b:
                out[f"{tag} {window}"] = {k: dict(v1=a[2][k], v2=b[2][k]) for k in PARTS}
    return out


# Our half spread vs half of TAQ's effective spread, by size, 2016-2024.
def spreads() -> dict:
    taq = layers.load("trading/spreads_monthly")
    taq = taq.assign(eom=pd.to_datetime(taq["eom"]), permno=taq["permno"].astype(int))
    df = pd.concat([frame(w, frozenset()) for w in WINDOWS])
    df = df[df["eom"] <= "2024-12-31"]
    ours = df[["permno", "eom", "size_grp"]].assign(ours=C.half_spread(df).to_numpy())
    both = ours.merge(taq, on=["permno", "eom"]).dropna(subset=["ours"])
    both["taq"] = both["EffectiveSpread_Percent_DW_median"] / 2
    both = both.dropna(subset=["taq"])
    return {
        str(group): dict(
            ours=float(g["ours"].median()),
            taq=float(g["taq"].median()),
            ratio=float((g["ours"] / g["taq"]).median()),
            n=len(g),
        )
        for group, g in both.groupby("size_grp")
    }


# Builds every switch verdict and exhibit and writes evidence.json.
def main() -> None:
    report = dict(protocol="docs/protocols/v2.md, evidence.md", verdicts=verdicts())
    counts = trial_counts()
    report["trials"] = counts
    # Deflated Sharpe over the T-bill, and over the +4% hurdle beside it.
    report["deflated_sharpe"] = {
        f"{name} {kind}{tag}": P.deflated_sharpe(
            load(f"{name}@1e7", "record")[0]["net"] - hurdle, counts[kind]
        )[0]
        for name in ("v1", "v2")
        for kind in ("full", "effective")
        for tag, hurdle in (("", 0.0), (" +4%", stats.HURDLE))
    }
    report["v3"] = final_book(report["verdicts"], counts)
    report["final_daily"] = final_daily(v2.final_three(report["verdicts"]))
    report["comparison_at_10m"] = comparison()
    report["daily_at_10m"] = daily()
    report["warning_signs"] = {n: warning_signs(n) for n in ("v1", "v2")}
    sets = {"v1": frozenset(), "v2": v2.V2}
    report["break_even_ic"] = {n: break_even(n, on) for n, on in sets.items()}
    report["canary_shuffled_ic"] = shuffled_ic()
    report["weak_periods"] = {
        n: dict(beta_drag_2016_20=beta_drag(n), losses_2023_26=themes(n, on))
        for n, on in sets.items()
    }
    report["regimes"] = {n: regimes(n) for n in sets}
    report["cost_waterfall"] = waterfall()
    report["spreads_vs_taq"] = spreads()
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(report["verdicts"], indent=1, default=float))


if __name__ == "__main__":
    main()
