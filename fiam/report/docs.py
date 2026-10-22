# Fills every generated table and every number in the prose of RESULTS.md.

import json
import re
from pathlib import Path

from fiam import paths
from fiam.book import MARKET_NAME, display_name

SUBMISSION = paths.SUBMISSION
RESULTS = paths.RESULTS

# Prose uses a real minus sign, so a negative number has to match either form.
MINUS = "−"

# A number in the prose: <!--N:metrics.json:performance.information_ratio:.2f-->0.85<!--/N-->.
NUMBER = re.compile(r"<!--N:([^:]+):([^:]+):([^>]*)-->.*?<!--/N-->")


# An output under submission/, or nothing if its step has not run, so the rest still builds.
def load(name: str) -> dict:
    path = SUBMISSION / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# A markdown table, first column left; the rest right-aligned when every cell is a short figure.
def table(header: list[str], rows: list[list[str]]) -> str:
    rule = "---:|" if all(len(str(c)) <= 24 for row in rows for c in row[1:]) else "---|"
    lines = ["| " + " | ".join(header) + " |", "|---|" + rule * (len(header) - 1)]
    return "\n".join(lines + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


# A label and a value per row, the shape most of these tables take.
def pairs(rows: list[tuple[str, str]]) -> str:
    return table(["", ""], [list(r) for r in rows])


# The results table in RESULTS.md. Rounded hard on purpose, the figures are good to a tenth.
def headline(m: dict) -> str:
    perf, cost, comp, run = m["performance"], m["costs"], m["compliance"], m["run"]
    body = pairs(
        [
            ("Gross return (annualized)", f"{perf['return_gross_annual']:.1%}"),
            ("**Net return (annualized)**", f"**{perf['return_net_annual']:.1%}**"),
            ("CAGR (total return)", f"{perf['return_total_cagr']:.1%}"),
            ("Volatility", f"{perf['volatility_annual']:.1%}"),
            ("**Information ratio vs TB3MS + 4%**", f"**{perf['information_ratio']:.2f}**"),
            ("Information ratio before costs", f"{perf['information_ratio_before_costs']:.2f}"),
            ("Sharpe ratio", f"{perf['sharpe_ratio']:.2f}"),
            ("Max drawdown (total return)", f"{perf['max_drawdown_total']:.1%}"),
            ("Hit rate", f"{perf['hit_rate_positive_active_months']:.1%}"),
            (
                "**Alpha**",
                f"**{perf['alpha_annual']:.1%}** (se {perf['alpha_stderr_annual']:.1%}, "
                f"t = {perf['alpha_tstat']:.2f}, HAC)",
            ),
            (
                "**Realized beta**",
                f"**{perf['beta_realized']:.2f}** (se {perf['beta_stderr']:.2f})",
            ),
            ("Correlation with market", f"{perf['correlation_with_market']:.2f}"),
            ("Market series", m["notes"]["market_series"]),
            ("Positions", f"{comp['positions_average']:.0f}"),
            ("Turnover, one-way monthly", f"{cost['turnover_monthly_one_way']:.0%}"),
            ("Costs as share of gross", f"{cost['cost_share_of_gross']:.0%}"),
            ("Holding months", f"{run['holding_months']}, {run['window']}"),
        ]
    )
    # The code hash at the bottom is how you spot a table from other code.
    return f"{body}\n\n_From code `{run['code_sha256']}`._"


# The same book on 2016-2020 beside the record, both on the CRSP market. Seen, so not a clean test.
def clean(m: dict) -> str:
    c = load("exhibits/confirmation.json")
    old, new = c["confirmation_2016_2020"], c["shipped_2021_2026"]

    # Each year's compounded net return, in one line.
    def years(side: dict) -> str:
        return ", ".join(
            f"{y} {r:+.0%}".replace("-0%", "0%") for y, r in side["net_by_year"].items()
        )

    rows = [
        [
            "Information ratio",
            f"**{old['information_ratio']:+.2f}**",
            f"{new['information_ratio']:+.2f}",
        ],
        ["Net return", f"{old['net_annual']:+.1%} a year", f"{new['net_annual']:+.1%} a year"],
        [
            "Beta to the whole US market (CRSP)",
            f"**{old['beta_realized']:+.2f}** (standard error {old['beta_stderr']:.2f})",
            f"{new['beta_realized']:+.2f} (standard error {new['beta_stderr']:.2f})",
        ],
        [
            "Worst drawdown, net return",
            f"{old['max_drawdown_spread']:.0%}",
            f"{new['max_drawdown_spread']:.0%}",
        ],
        ["Turnover, one-way monthly", f"{old['turnover']:.0%}", f"{new['turnover']:.0%}"],
        ["Net return by year, compounded", years(old), years(new)],
    ]
    return table(["", "2016-2020, a historical check", "2021-2026, the record"], rows)


# Realized beta by era and in rolling years, against the full period.
def drift(m: dict) -> str:
    d, perf = load("exhibits/pack.json")["beta_drift"], m["performance"]
    rows = [
        [p.replace("_", "-"), f"{x['beta']:+.2f}", f"{x['stderr']:.2f}", f"{x['t']:+.2f}"]
        for p, x in d.items()
        if p in ("2021_2023", "2024_2026")
    ]
    full = perf["beta_realized"] / perf["beta_stderr"]
    rows.append(
        [
            "full period",
            f"{perf['beta_realized']:+.2f}",
            f"{perf['beta_stderr']:.2f}",
            f"{full:+.2f}",
        ]
    )
    daily = load("exhibits/daily_risk.json").get("beta_to_sp500_daily")
    if daily:
        t = daily["beta"] / daily["stderr"]
        rows.append(
            [
                f"2021-2025, {daily['days']:,} days",
                f"{daily['beta']:+.2f}",
                f"{daily['stderr']:.2f}",
                f"{t:+.2f}",
            ]
        )
    noise = d["rolling_12m_outside_noise_band"]
    note = (
        f"\n\n{d['rolling_12m_outside_band']:.0%} of the {d['rolling_12m_windows']} rolling "
        "12-month betas fall outside ±0.20, but "
        + ("none" if noise == 0 else f"{noise:.0%}")
        + " fall outside the range a truly zero-beta portfolio with our risk would show by "
        "chance (95%)."
    )
    return table(["period", "beta", "standard error", "t-stat"], rows) + note


# The five cost lines as the backtest recorded them, and how far they can rise.
def costs(m: dict) -> str:
    c = load("exhibits/pack.json")["costs"]
    parts, even = c["components"], c["break_even"]
    names = dict(
        commission="Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA)",
        spread="Bid-ask spread (half, from real quotes)",
        impact="Market impact (grows with trade size)",
        borrow="Borrow fees on shorts (by how heavily shorted)",
        financing="Financing (cash earns the T-bill less 0.5%)",
        total="**Total**",
    )
    rows = [(names[k], f"{parts[k]:.2%}") for k in names]
    rows.append(
        (
            "Costs could rise to this before the edge over the hurdle disappears",
            f"{even['break_even_annual_cost']:.1%} ({even['break_even_multiple']:.1f}x)",
        )
    )
    return table(["", "% of NAV a year"], [list(r) for r in rows])


# The book's trades under other cost models and capital levels, and how fast it could be sold.
def implementation(m: dict) -> str:
    d = load("exhibits/implementation.json")
    if not d:
        return "The implementation step has not run yet."
    names = dict(
        every_cost_doubled="Every cost doubled",
        impact_coefficient_half="Market impact halved",
    )
    rows = [
        [
            label,
            f"{s['information_ratio']:+.2f}",
            f"{s['net_annual']:+.1%}",
            f"{s['cost_annual']:.1%}",
            "",
        ]
        for key, label in names.items()
        for s in [d["sensitivities"][key]]
    ]
    for key, s in d["capacity"].items():
        liquid = d["liquidity"][key]
        exit_text = f"{liquid['share_of_book_out_in_one_day']:.0%}, {liquid['days_p95']:.1f} days"
        size = f"${key[:-1]}M of capital" if key != "1000m" else "$1B of capital"
        rows.append(
            [
                size + (", as modelled" if key == "10m" else ""),
                f"{s['information_ratio']:+.2f}",
                f"{s['net_annual']:+.1%}",
                f"{s['cost_annual']:.1%}",
                exit_text,
            ]
        )
    header = ["", "IR", "net return", "costs"]
    header += ["sellable in a day, days to exit 95% (at 20% of volume)"]
    return table(header, rows)


# The daily path through each stress window, and the cost of trading a day late.
def stress(m: dict) -> str:
    d = load("exhibits/daily_risk.json")
    windows, late = d.get("stress"), d.get("execution_delay")
    if not windows:
        return "No daily prices in the data bundle, so no stress windows."
    rows = [
        [
            name,
            f"{w['strategy']:+.1%}",
            "" if w["sp500"] is None else f"{w['sp500']:+.1%}",
            f"{w['worst_drawdown']:.1%}",
        ]
        for name, w in windows.items()
    ]
    note = ""
    if late:
        on_time, delayed = late["information_ratio_on_time"], late["information_ratio_one_day_late"]
        note = (
            f"\n\nTrading one day late changes little: IR {delayed:+.2f} against {on_time:+.2f} "
            f"on time, over the {late['months']} months with daily prices."
        )
    return table(["window", "strategy", "S&P 500", "worst drop within"], rows) + note


# The analyst behind the firewall: what taught the small model, and the recall test.
def firewall(m: dict) -> str:
    d = load("exhibits/analyst_learned.json")
    if not d:
        return "The analyst's verdicts have not been learned yet; they come from the agents' run."
    rows = [
        ("Analyst verdicts used for training, up to November 2020", f"{d['taught_on']:,}"),
        (
            "How well the small model copies the analyst, rank correlation on unseen data",
            f"{d['cross_validated_rank_correlation']:.2f}",
        ),
        ("Stock-months the small model scores", f"{d['scored_stock_months']:,}"),
    ]
    probe = load("exhibits/analyst.json").get("look_ahead_probe")
    if probe:
        rows.append(
            (
                f"Test: share of {probe['filings']} hidden filings where the analyst named the "
                "company / the year",
                f"{probe['company_named']:.0%} / {probe['year_named']:.0%}",
            )
        )
    test = d["recall_test"]

    def cell(period: str, who: str) -> str:
        x = test[period][who]
        return f"{x['rank_correlation']:+.3f} (t-stat {x['t']:.1f})"

    body = [[f"Predictive power (IC), {p}", cell(p, "analyst"), cell(p, "learned")] for p in test]
    recall = table(["", "analyst's own verdicts", "small model"], body)
    reading = (
        "IC: the average monthly rank correlation with next month's return. If the analyst "
        "remembered what happened, its 2021-2026 IC would far exceed the small model's. "
        "It does not."
    )
    return f"{pairs(rows)}\n\n{recall}\n\n{reading}"


# The brief's limits and our own, measured after rounding to whole shares.
def compliance(m: dict) -> str:
    c, perf = m["compliance"], m["performance"]
    n = load("exhibits/pack.json")["completeness"]["ranges"]["positions"]
    return table(
        ["rule", "limit", "measured"],
        [
            [
                "Positions",
                "100 to 500",
                f"{n['min']:.0f} to {n['max']:.0f}, {n['mean']:.0f} on average",
            ],
            ["Gross exposure", "up to 200%", f"largest {c['gross_exposure_max']:.2%}"],
            ["Net exposure", "−50% to +50%", f"largest {c['net_exposure_max_abs']:.2%}"],
            [
                "Each sector (our own limit)",
                "±1% before rounding to whole shares",
                f"largest {c['sector_tilt_max']:.2%} after rounding",
            ],
            [
                "Each position (our own limit)",
                "1.5% before rounding to whole shares",
                f"largest {c['position_weight_max']:.2%} after rounding",
            ],
            [
                "Predicted beta (our own limit)",
                "±0.02",
                f"average {c['beta_exante_weighted_mean']:+.3f}",
            ],
            [
                "Realized beta (our own check)",
                "run stops outside ±0.20",
                f"{perf['beta_realized']:+.2f} (standard error {perf['beta_stderr']:.2f})",
            ],
        ],
    )


# What each teacher learned to predict, and how well a year ahead.
def teachers(m: dict) -> str:
    d = load("exhibits/teachers.json").get("teachers", {})
    labels = dict(beta="next month's daily beta", crowding="next month's short interest")
    labels["revisions"] = "next month's analyst revisions"
    labels["surprise"] = "next quarter's earnings surprise"
    rows = []
    for k, v in d.items():
        by_year = v["rank_correlation_by_year"].values()
        error = v.get("mean_abs_error")
        note = (
            f"{error:.2f} against {v['beta_60m_mean_abs_error']:.2f} for the 60-month beta"
            if error
            else ""
        )
        rows.append([labels[k], f"{sum(by_year) / len(by_year):.2f}", note])
    return table(["helper model predicts", "rank correlation a year ahead", "average error"], rows)


# The scorer's information coefficient by year, the test years only.
def scorer(m: dict) -> str:
    d = load("exhibits/scorer.json")
    if not d:
        return "The scorer has not run yet."
    ic = d["ic_2021_2026"]
    rows = [[y, f"{v:+.3f}"] for y, v in d["ic_by_year"].items()]
    rows.append(["**2021-2026**", f"**{ic['ic_mean']:+.3f}** (t-stat {ic['ic_t']:.2f})"])
    return table(["year", "stock-picking model IC"], rows)


# Our book against the three models, all through the same optimizer and costs.
def models(m: dict) -> str:
    ml = load("exhibits/ml_metrics.json")
    if not ml:
        return "The model comparison has not run yet; it runs with --ml."
    perf, cost = m["performance"], m["costs"]
    rows = [
        [
            "**Our portfolio**",
            f"{ml['composite']['ic_t']:.2f}",
            f"{perf['return_gross_annual']:.1%}",
            f"{cost['cost_annual']:.1%}",
            f"**{perf['return_net_annual']:+.1%}**",
            f"{cost['turnover_monthly_one_way']:.0%}",
            f"**{perf['information_ratio']:+.2f}**",
        ]
    ]
    for key, name in (("lgbm", "LightGBM"), ("nn3", "Neural network"), ("enet", "Elastic net")):
        x = ml[key]
        rows.append(
            [
                name,
                f"{x['ic_t']:.2f}",
                f"{x['gross_annual']:.1%}",
                f"{x['cost_annual']:.1%}",
                f"{x['net_annual']:+.1%}",
                f"{x['turnover']:.0%}",
                f"{x['information_ratio']:+.2f}",
            ]
        )
    return table(["", "IC t-stat", "gross", "costs", "net", "turnover", "**IR**"], rows)


# Out-of-sample R-squared for every method, both forms.
def r2(m: dict) -> str:
    o = load("exhibits/oos_r2.json")
    names = dict(
        template_ols="Linear regression (template)",
        template_ridge="Ridge (template)",
        template_enet="Elastic net (template)",
        enet="Elastic net, on ranks",
        lgbm="LightGBM",
        nn3="Neural network, 3 layers",
        scorer="Stock-picking model",
        composite="Our 12-signal score",
    )
    rows = [
        [name, f"{o['methods'][k]['r2_zero_benchmark']:+.2%}"]
        for k, name in names.items()
        if k in o["methods"]
    ]
    return table(["model", "out-of-sample R², 2021-2026"], rows)


# The record in pieces, with block-bootstrap intervals.
def halves(m: dict) -> str:
    s = load("exhibits/pack.json")["subperiod"]
    names = dict(
        full_2021_2026="**Full, 2021-2026**",
        first_half_2021_2022="2021-2022",
        second_half_2023_2026="**2023-2026**",
        excluding_2021="2022-2026",
        crsp_era_2021_2025="2021-2025, the years with daily prices",
    )
    rows = [
        [
            name,
            s[k]["months"],
            f"{s[k]['gross_annual']:.1%}",
            f"{s[k]['cost_annual']:.1%}",
            f"{s[k]['net_annual']:.1%}",
            f"{s[k]['information_ratio']:.2f}",
            f"[{s[k]['ir_ci_low']:.2f}, {s[k]['ir_ci_high']:.2f}]",
        ]
        for k, name in names.items()
    ]
    return table(["period", "months", "gross", "costs", "net", "IR", "IR, 95% range"], rows)


# Six-factor loadings, and alpha as factors are added.
def factors(m: dict) -> str:
    risk = load("exhibits/pack.json")["risk"]
    six, three = risk["five_factor_momentum"], risk["attribution"]
    names = dict(
        mkt_rf="Market",
        smb="Size",
        hml="Value",
        rmw="Profitability",
        cma="Investment",
        mom="Momentum",
    )
    rows = [[n, f"{six['betas'][k]:+.2f}", f"{six['t_stats'][k]:+.2f}"] for k, n in names.items()]
    rows += [
        ["**Alpha after all six**", f"**{six['alpha_annual']:.1%}**", f"**{six['alpha_t']:+.2f}**"],
        ["Alpha after three", f"{three['alpha_annual']:.1%}", f"{three['alpha_t']:+.2f}"],
        [
            "Alpha after the S&P 500 alone",
            f"{m['performance']['alpha_annual']:.1%}",
            f"{m['performance']['alpha_tstat']:+.2f}",
        ],
    ]
    note = (
        f"\n\nThese six factors explain {six['r_squared']:.0%} of the monthly ups and downs, "
        f"over {six['months']} months."
    )
    return table(["", "exposure", "t-stat"], rows) + note


# Each year split into what the market and five styles paid and what stock selection added.
def styles(m: dict) -> str:
    years = load("exhibits/pack.json").get("risk", {}).get("style_by_year")
    if not years:
        return "The split by year is written by the next run."
    rows = [
        [
            y if v["months"] == 12 else f"{y} ({v['months']} months)",
            f"{v['total']:+.1%}",
            f"{v['styles']:+.1%}",
            f"{v['selection']:+.1%}",
        ]
        for y, v in years.items()
    ]
    note = (
        "\n\nNet return by year (monthly sums), split into what the six factors explain and "
        "stock selection. French's data end in July 2026."
    )
    return (
        table(["year", "net return", "from the six factors", "from stock selection"], rows) + note
    )


# Each signal's share of gross return, exposure times its pure return.
def attribution(m: dict) -> str:
    full = load("exhibits/pack.json")["attribution"]["full"]
    signals = sorted(
        (k for k in full if k not in ("residual", "explained_total")),
        key=lambda k: -full[k]["contribution_annual"],
    )
    rows = [
        [f"`{k}`", f"{full[k]['contribution_annual']:+.1%}", f"{full[k]['t']:+.2f}"]
        for k in signals
    ]
    rows.append(
        ["from the twelve signals", f"{full['explained_total']['contribution_annual']:+.1%}", ""]
    )
    rows.append(["not explained by them", f"{full['residual']['contribution_annual']:+.1%}", ""])
    return table(["signal", "added to gross return a year", "t-stat"], rows)


# Three controls that should make the result disappear, and what each did.
def placebo(m: dict) -> str:
    p = load("exhibits/placebo_lab.json")
    null, inv, stale = p["permutation_null"], p["inversion"], p["stale_scores"]
    return table(
        ["test", "what changes", "what happened"],
        [
            [
                "Random scores",
                f"scores shuffled within sector and liquidity, {null['draws']} times",
                f"gross {null['gross_annual_mean']:+.1%} a year on average, against our "
                f"{p['shipped']['gross_annual']:+.1%}",
            ],
            [
                "Reversed scores",
                "long the worst, short the best",
                f"gross {inv['gross_annual']:+.1%} against our {inv['baseline_gross_annual']:+.1%}",
            ],
            [
                "One-month-old scores",
                "last month's ranking traded this month",
                f"IR {stale['net_ir']:+.2f} against {stale['baseline_net_ir_matched']:+.2f} "
                f"over the same {stale['months']} months",
            ],
        ],
    )


# The explainer's three largest winners and losers, each with its reason in the agent's words.
def explained(m: dict) -> str:
    e = load("exhibits/explainer.json")
    names = sorted(e.get("positions", []), key=lambda p: -p["facts"].get("realized_pnl_pct", 0))
    if not names or "realized_pnl_pct" not in names[0]["facts"]:
        return "The explainer has not run on the winners and losers yet; it runs with --agents."
    rows = [
        [
            f"{p['ticker']}, {p['company']}",
            p["side"].lower(),
            f"{p['facts']['realized_pnl_pct']:+.2f}%",
            # The first sentence carries the reason; the rest is in explainer.json.
            p["why"].replace("|", "/").replace("\n", " ").split(". ")[0].rstrip(".") + ".",
        ]
        for p in [*names[:3], *names[-3:]]
    ]
    header = ["name", "side", "P&L, % of NAV", "why it was held, in the explainer's words"]
    return table(header, rows)


# The deflated-Sharpe probability at both attempt counts, with the Sharpe luck alone produces.
def deflation(m: dict) -> str:
    r = m["robustness"]
    rows = [
        [
            f"**At {r['attempts_eligible']} eligible attempts**",
            f"{r['sharpe_luck_alone_eligible']:.2f}",
            f"**{r['deflated_sharpe_probability_eligible']:.2f}**",
        ],
        [
            f"At {r['attempts_all']:,}, every fit we ever ran",
            f"{r['sharpe_luck_alone_all']:.2f}",
            f"{r['deflated_sharpe_probability_all']:.2f}",
        ],
        [
            "Missing returns at −30%, longs / both sides",
            "",
            f"IR {r['ir_missing_returns_conservative']:.2f} / "
            f"{r['ir_missing_returns_symmetric']:.2f}",
        ],
    ]
    return table(["", "Sharpe luck alone produces", "deflated-Sharpe probability"], rows)


# The statistics the rules list for the committee pack that the headline does not carry.
def committee(m: dict) -> str:
    c, perf = load("exhibits/pack.json")["completeness"], m["performance"]
    r = c["ranges"]

    # An average with its range.
    def spread(key: str, fmt: str) -> str:
        x = r[key]
        text = f"{x['mean']:{fmt}} ({x['min']:{fmt}} to {x['max']:{fmt}})"
        return text.replace("-0.00%", "0.00%")

    return pairs(
        [
            ("Average monthly return, total", f"{c['average_monthly_return']:.2%}"),
            (
                "Annualized, arithmetic / geometric (CAGR)",
                f"{c['average_monthly_return'] * 12:.1%} / {perf['return_total_cagr']:.1%}",
            ),
            (
                "Cumulative return, Jan 2021 to Aug 2026",
                f"{c['cumulative_return_full_period']:.1%}",
            ),
            ("Best month", f"{c['best_month']['value']:+.1%}, {c['best_month']['month'][:7]}"),
            ("Worst month", f"{c['worst_month']['value']:+.1%}, {c['worst_month']['month'][:7]}"),
            ("Months beating the benchmark", f"{perf['hit_rate_positive_active_months']:.0%}"),
            (
                "Holdings, long / short",
                f"{c['average_long_positions']:.0f} / {c['average_short_positions']:.0f}",
            ),
            ("Gross exposure, average (range)", spread("gross_exposure", ".2%")),
            ("Net exposure, average (range)", spread("net_exposure", ".2%")),
            (
                "Position weight, average / largest",
                f"{c['average_absolute_position_weight']:.2%} / "
                f"{m['compliance']['position_weight_max']:.2%}",
            ),
            ("Share of gross in the ten largest names", f"{c['legs']['top10_share_of_gross']:.1%}"),
            ("Turnover, one-way monthly, average (range)", spread("turnover_one_way", ".0%")),
        ]
    )


# The book marked every trading day, beside what month-end numbers say.
def daily(m: dict) -> str:
    d = load("exhibits/daily_risk.json")
    if not d:
        return "No daily prices in the data bundle, so nothing is measured daily."
    r, g, rec = d["risk"], d["risk"]["gross_exposure"], d["reconciliation"]
    return pairs(
        [
            ("Trading days", f"{d['days']:,}, 2021-01 to 2025-12"),
            ("Gross exposure at rebalancing, highest", f"{g['at_rebalance_max']:.1%}"),
            (
                "Gross exposure on any day, highest",
                f"{g['intra_month_max']:.1%}, {g['intra_month_max_month']}",
            ),
            (
                "Months with any day above 200% gross",
                f"{g['months_above_200pct_on_any_day']} of {rec['months']}",
            ),
            (
                "Net exposure on any day, furthest from zero",
                f"{r['net_exposure']['intra_month_max_abs']:.1%}",
            ),
            (
                "Volatility, daily / monthly, same 60 months",
                f"{r['volatility_annual']['daily']:.1%} / {r['volatility_annual']['monthly']:.1%}",
            ),
            (
                "Max drawdown, daily / monthly, same 60 months",
                f"{r['max_drawdown']['daily']:.1%} / {r['max_drawdown']['monthly']:.1%}",
            ),
            (
                "One-day Value at Risk, 95% / 99%",
                f"{r['var_one_day']['p95']:.2%} / {r['var_one_day']['p99']:.2%}",
            ),
            ("Expected shortfall, 95%, one day", f"{r['var_one_day']['cvar_95']:.2%}"),
            ("Worst day", f"{r['worst_day']['value']:+.2%}, {r['worst_day']['date']}"),
            (
                "Daily returns rebuilt into months, against returns.csv",
                f"correlation {rec['correlation']:.4f}, largest gap {rec['largest_gap']:.3%}",
            ),
        ]
    )


# Calendar years for the strategy, the benchmark and the S&P 500, compounded.
def years(m: dict) -> str:
    rows = [
        [
            f"{y} (Jan-Aug)" if v["partial_year"] else y,
            f"{v['strategy']:+.1%}",
            f"{v['benchmark']:+.1%}",
            f"{v['market']:+.1%}" if v["market"] is not None else "",
            f"{v['active']:+.1%}",
        ]
        for y, v in load("exhibits/pack.json")["completeness"]["by_year"].items()
    ]
    header = ["year", "strategy, total return", "T-bill + 4%", "S&P 500 (price)"]
    return table(header + ["strategy minus hurdle"], rows)


# The long and the short leg separately, and what the short book is made of.
def legs(m: dict) -> str:
    g = load("exhibits/pack.json")["completeness"]["legs"]
    rows = [
        [
            side,
            f"{g[side]['annual_contribution']:+.1%}",
            f"{g[side]['volatility']:.1%}",
            f"{g[side]['names_per_month']:.0f}",
            f"${g[side]['mean_market_cap_musd'] / 1e3:.1f}bn",
            f"${g[side]['median_market_cap_musd'] / 1e3:.1f}bn",
            f"${g[side]['mean_dollar_volume'] / 1e6:.0f}m",
            f"${g[side]['median_dollar_volume'] / 1e6:.0f}m",
        ]
        for side in ("long", "short")
    ]
    for row, side in zip(rows, ("long", "short")):
        row.insert(2, f"{g[side]['return_per_dollar_annual']:+.1%}")
    htb, short = m["costs"]["hard_to_borrow_share_of_short_book"], g["short"]
    note = (
        f"\n\nShorts by weight: {short['share_small_or_micro']:.0%} small or micro caps "
        f"({short['share_micro']:.0%} micro), and {htb:.0%} cost 3% a year or more to borrow."
    )
    crowd = load("exhibits/daily_risk.json").get("short_interest") or {}
    if crowd:
        note += (
            f" In 2021-2025, the years with short-interest data, "
            f"{crowd['short_book_weight_crowded']:.0%} were in stocks with over "
            f"{crowd['crowded_threshold']:.0%} of their shares already sold short."
        )
    header = ["leg", "return added a year", "return per $1 in the leg", "volatility", "stocks"]
    header += ["market cap, average", "market cap, median"]
    header += ["daily $ traded, average", "daily $ traded, median"]
    return table(header, rows) + note


# The ten largest longs and shorts by average weight over every month, by ticker and full name.
def top(m: dict) -> str:
    t = load("exhibits/pack.json")["completeness"]["top_positions"]
    rows = [
        [
            i,
            f"{a['ticker']}, {display_name(a['company'])}",
            f"{a['average_weight']:.2%}",
            f"{b['ticker']}, {display_name(b['company'])}",
            f"{b['average_weight']:.2%}",
        ]
        for i, (a, b) in enumerate(zip(t["long"], t["short"]), 1)
    ]
    return table(["", "long", "weight", "short", "weight"], rows)


# Every family of ideas we tried, how many attempts each took, and what came of it.
def tried(m: dict) -> str:
    from fiam.exhibits import config_log

    rows = [[r[0], f"{r[3]:,}", r[4], r[5]] for r in config_log.rows()]
    eligible, everything = config_log.attempts()
    chance = m["robustness"]["deflated_sharpe_probability_eligible"]
    note = (
        f"\n\n{everything:,} fits in all, {eligible} of them shippable portfolios. Adjusted for "
        f"this many tries (deflated Sharpe ratio), the chance our edge is real is {chance:.0%}."
    )
    return table(["what we tried", "attempts", "result", "verdict"], rows) + note


# What each agent did, from its exhibit, one row each.
def agents(m: dict) -> str:
    rows = []
    t = load("exhibits/triage.json")
    if t:
        routine = t["labelled_by_kind"].get("routine", 0) / max(t["labelled"], 1)
        rows.append(
            [
                "**Triage**",
                "Gemma 4 26B-A4B",
                f"{t['labelled']:,} 8-Ks from 2015-18 labelled with names hidden. A small "
                f"FinBERT-based model learns them, {t['cross_validated_accuracy']:.0%} correct "
                f"against {routine:.0%} for always guessing routine, then labels every filing",
            ]
        )
    a, learned = load("exhibits/analyst.json"), load("exhibits/analyst_learned.json")
    if a:
        probe = a["look_ahead_probe"]
        late = learned.get("recall_test", {}).get("2021-2026", {}).get("analyst", {})
        text = (
            f"{a['stock_months']:,} verdicts. Named the company in {probe['company_named']:.0%} "
            f"of {probe['filings']} test filings"
        )
        if late:
            ic = late["rank_correlation"]
            text += f". Its 2021-26 verdicts have no predictive power (IC {ic:+.3f})"
        rows.append(["**Analyst**", "Qwen3.8-27B", text])
    c, pack = load("exhibits/crowd.json"), load("exhibits/pack.json")
    if c:
        likes = sorted(c["what_the_crowd_likes"].items(), key=lambda kv: -kv[1])[:2]
        text = (
            f"{c['picks']:,} picks from anonymous stock cards, 2016-20. The two models' picks "
            f"correlate {c['agreement_between_models']:.2f}, and both favour "
            f"{' and '.join(k for k, _ in likes)}"
        )
        crowded = (pack.get("crowding") or {}).get("long")
        if crowded:
            share = crowded["share_in_top_crowd_decile"]
            text += f". {share:.0%} of our longs are in their top tenth"
        rows.append(["**AI crowd**", "Gemma 4 and Qwen3.8", text])
    k = load("exhibits/critic.json")
    if k:
        text = f"{len(k['critiques'])} critiques, {k['unsupported']} citing a number no tool showed"
        repeat = k.get("repeatability", {}).get("comparison", {})
        if repeat:
            same, calls = repeat["identical_prefix"], repeat["calls_first"]
            text += (
                ". Run twice, identical both times"
                if same == calls
                else (f". Run twice, {same} of {calls} calls identical")
            )
        rows.append(["**Devil's advocate**", "Gemma 4 26B-A4B", text])
    e = load("exhibits/explainer.json")
    if e:
        text = f"{len(e['positions'])} winners and losers explained from their facts alone"
        rows.append(["**Explainer**", "Qwen3.8-27B", text])
    return table(["agent", "model", "what happened"], rows)


TABLES = dict(
    headline=headline,
    committee=committee,
    years=years,
    legs=legs,
    top=top,
    compliance=compliance,
    costs=costs,
    implementation=implementation,
    drift=drift,
    daily=daily,
    stress=stress,
    factors=factors,
    styles=styles,
    attribution=attribution,
    tried=tried,
    teachers=teachers,
    scorer=scorer,
    models=models,
    r2=r2,
    agents=agents,
    firewall=firewall,
    explained=explained,
    halves=halves,
    clean=clean,
    placebo=placebo,
    deflation=deflation,
)


# Replaces what sits between each pair of markers, building only the tables the file holds.
def fill(target: Path, tables: dict, m: dict) -> None:
    text = target.read_text(encoding="utf-8")
    for marker, build in tables.items():
        start, end = f"<!--AUTO:{marker}-->", f"<!--/AUTO:{marker}-->"
        if start in text:
            a, b = text.index(start) + len(start), text.index(end)
            text = text[:a] + "\n\n" + build(m) + "\n\n" + text[b:]
    target.write_text(numbers(text), encoding="utf-8", newline="\n")


# "performance.sharpe_ratio" means that group, then that key. A number steps into a list.
def dig(data, path: str):
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


# Each inline number, read from the exhibit it names in the format it names.
def numbers(text: str) -> str:
    # One marker refilled from its exhibit.
    def value(match: re.Match) -> str:
        name, key, fmt = match.groups()
        data = load(name)
        shown = format(dig(data, key), fmt).replace("-", MINUS) if data else "?"
        return f"<!--N:{name}:{key}:{fmt}-->{shown}<!--/N-->"

    return NUMBER.sub(value, text)


# Fills RESULTS.md from the latest exhibits.
def main() -> None:
    m = load("metrics.json")
    assert m["notes"]["market_series"] == MARKET_NAME, "metrics.json is from an older run"
    fill(RESULTS, TABLES, m)
    # The README's few numbers too, where a README sits beside RESULTS.md.
    readme = RESULTS.parent / "README.md"
    if readme.exists():
        fill(readme, {}, m)
    perf = m["performance"]
    print(f"filled: IR {perf['information_ratio']:.2f}, net {perf['return_net_annual']:.1%}")


if __name__ == "__main__":
    main()
