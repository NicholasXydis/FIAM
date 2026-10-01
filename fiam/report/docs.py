# Fills every generated table and every number in the prose of RESULTS.md and BRIEF.md.

import json
import re
from pathlib import Path

from fiam import paths
from fiam.book import MARKET_NAME, display_name

SUBMISSION = paths.SUBMISSION
RESULTS, BRIEF = paths.RESULTS, paths.BRIEF

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


# The plain-English table in BRIEF.md, with the 2016-2020 check beside the headline.
def brief(m: dict) -> str:
    perf, split = m["performance"], load("exhibits/pack.json").get("subperiod", {})
    clean = load("exhibits/confirmation.json").get("confirmation_2016_2020", {})
    rows = [
        ("Net return", f"**{perf['return_net_annual']:.1%} a year** after every modelled fee"),
        ("Information ratio", f"**{perf['information_ratio']:.2f}**"),
        ("Information ratio before costs", f"{perf['information_ratio_before_costs']:.2f}"),
        ("Alpha", f"{perf['alpha_annual']:.1%} a year, t = {perf['alpha_tstat']:.2f}"),
        (
            "Beta to the S&P 500, monthly",
            f"{perf['beta_realized']:.2f}, standard error {perf['beta_stderr']:.2f}",
        ),
        ("Worst drawdown", f"{perf['max_drawdown_total']:.1%}"),
    ]
    daily = load("exhibits/daily_risk.json").get("beta_to_sp500_daily")
    if daily:
        t = daily["beta"] / daily["stderr"]
        tilt = "no clear tilt" if abs(t) < 2 else f"a {'short' if t < 0 else 'long'} market tilt"
        text = f"{daily['beta']:+.2f}, t = {t:.1f}: {tilt}"
        rows.insert(4, ("Beta, daily returns 2021-25", text))
    if split:
        first = split["first_half_2021_2022"]["information_ratio"]
        second = split["second_half_2023_2026"]["information_ratio"]
        rows.append(("Split in half", f"2021-22 IR {first:.2f}, 2023-26 IR {second:+.2f}"))
        rows.append(
            (
                "CRSP years only",
                f"2021-25 IR {split['crsp_era_2021_2025']['information_ratio']:.2f}",
            )
        )
    if clean:
        beta = f"beta {clean['beta_realized']:+.2f} (se {clean['beta_stderr']:.2f})"
        rows.append(
            ("2016-2020, a historical check", f"IR {clean['information_ratio']:+.2f}, {beta}")
        )
    return pairs(rows)


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
            "Realized beta, CRSP market",
            f"**{old['beta_realized']:+.2f}** (se {old['beta_stderr']:.2f})",
            f"{new['beta_realized']:+.2f} (se {new['beta_stderr']:.2f})",
        ],
        [
            "Worst spread drawdown",
            f"{old['max_drawdown_spread']:.0%}",
            f"{new['max_drawdown_spread']:.0%}",
        ],
        ["Turnover, one-way monthly", f"{old['turnover']:.0%}", f"{new['turnover']:.0%}"],
        ["Net by year, compounded", years(old), years(new)],
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
    note = (
        f"\n\n{d['rolling_12m_outside_band']:.0%} of {d['rolling_12m_windows']} rolling 12-month "
        f"windows sit outside ±0.20, and {d['rolling_12m_outside_noise_band']:.0%} outside the "
        "range a zero-beta book with our residual risk would reach 95% of the time."
    )
    return table(["period", "beta", "se", "t"], rows) + note


# The five cost lines as the backtest recorded them, and how far they can rise.
def costs(m: dict) -> str:
    c = load("exhibits/pack.json")["costs"]
    parts, even = c["components"], c["break_even"]
    names = dict(
        commission="Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA)",
        spread="Half-spread (calibrated to CRSP quotes)",
        impact="Market impact (square-root law)",
        borrow="Borrow (short-interest tiers)",
        financing="Financing (benchmark less 0.5% on cash)",
        total="**Total**",
    )
    rows = [(names[k], f"{parts[k]:.2%}") for k in names]
    rows.append(
        (
            "Annual cost at which active return reaches zero",
            f"{even['break_even_annual_cost']:.1%}, "
            f"{even['break_even_multiple']:.2f} times today's",
        )
    )
    return table(["", "% of NAV a year"], [list(r) for r in rows])


# The book's trades under other cost models and capital levels, and how fast it could be sold.
def implementation(m: dict) -> str:
    d = load("exhibits/implementation.json")
    if not d:
        return "The implementation step has not run yet."
    names = dict(
        as_modelled="As modelled, $10M",
        every_cost_doubled="Every cost doubled",
        impact_coefficient_half="Impact coefficient 0.5",
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
        exit_text = f"{liquid['share_of_book_out_in_one_day']:.0%}; {liquid['days_p95']:.1f} days"
        rows.append(
            [
                f"${key[:-1]}M of capital" if key != "1000m" else "$1B of capital",
                f"{s['information_ratio']:+.2f}",
                f"{s['net_annual']:+.1%}",
                f"{s['cost_annual']:.1%}",
                exit_text,
            ]
        )
    header = ["", "IR", "net", "cost", "sold in a day at 20% of volume; 95th percentile"]
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
            f"\n\nTrading a day late, {late['months']} months: IR {delayed:+.2f} against "
            f"{on_time:+.2f} on time, {late['cost_annual']:+.1%} a year."
        )
    return table(["window", "strategy", "S&P 500", "worst fall inside"], rows) + note


# The analyst behind the firewall: what taught the small model, and the recall test.
def firewall(m: dict) -> str:
    d = load("exhibits/analyst_learned.json")
    if not d:
        return "The analyst's verdicts have not been learned yet; they come from the agents' run."
    rows = [
        ("Verdicts that taught, up to November 2020", f"{d['taught_on']:,}"),
        (
            "Small model against the analyst, held-out rank correlation",
            f"{d['cross_validated_rank_correlation']:.2f}",
        ),
        ("Stock-months it scores for the stock picker", f"{d['scored_stock_months']:,}"),
    ]
    probe = load("exhibits/analyst.json").get("look_ahead_probe")
    if probe:
        rows.append(
            (
                f"Probe: masked filings where the analyst named the company / year, of "
                f"{probe['filings']}",
                f"{probe['company_named']:.0%} / {probe['year_named']:.0%}",
            )
        )
    test = d["recall_test"]

    def cell(period: str, who: str) -> str:
        x = test[period][who]
        return f"{x['rank_correlation']:+.3f} (t {x['t']:.1f})"

    body = [[f"IC, {p}", cell(p, "analyst"), cell(p, "learned")] for p in test]
    recall = table(["", "analyst's own verdicts", "small model"], body)
    return f"{pairs(rows)}\n\n{recall}\n\n_{d['reading']}_"


# The brief's limits and our own, measured after rounding to whole shares.
def compliance(m: dict) -> str:
    c, perf = m["compliance"], m["performance"]
    return table(
        ["rule", "limit", "measured"],
        [
            ["Positions", "100-500", f"{c['positions_average']:.0f} on average"],
            ["Gross exposure", "≤ 200%", f"max {c['gross_exposure_max']:.2%}"],
            [
                "Net exposure",
                "−50% to +50%; ours exact before rounding",
                f"max abs {c['net_exposure_max_abs']:.2%}",
            ],
            [
                "Sector, 11 GICS + `XX` (ours)",
                "1% before whole-share rounding",
                f"max {c['sector_tilt_max']:.2%} after it",
            ],
            [
                "Single name (ours)",
                "1.5% before whole-share rounding",
                f"max {c['position_weight_max']:.2%} after it",
            ],
            ["Ex-ante beta", "±0.02", f"mean {c['beta_exante_weighted_mean']:+.3f}"],
            [
                "Realized beta",
                "build fails outside ±0.20",
                f"{perf['beta_realized']:+.2f} (se {perf['beta_stderr']:.2f})",
            ],
        ],
    )


# What each teacher learned to predict, and how well a year ahead.
def teachers(m: dict) -> str:
    d = load("exhibits/teachers.json").get("teachers", {})
    labels = dict(beta="next month's daily beta", crowding="next month's short crowding")
    labels["revisions"] = "next month's analyst revisions"
    labels["surprise"] = "next quarter's earnings surprise"
    rows = []
    for k, v in d.items():
        by_year = v["rank_correlation_by_year"].values()
        error = v.get("mean_abs_error")
        note = (
            f"{error:.2f} against {v['beta_60m_mean_abs_error']:.2f} for beta_60m" if error else ""
        )
        rows.append([labels[k], f"{sum(by_year) / len(by_year):.2f}", note])
    return table(["teacher predicts", "rank correlation a year ahead", "mean error"], rows)


# The scorer's information coefficient by year, the test years only.
def scorer(m: dict) -> str:
    d = load("exhibits/scorer.json")
    if not d:
        return "The scorer has not run yet."
    ic = d["ic_2021_2026"]
    rows = [[y, f"{v:+.3f}"] for y, v in d["ic_by_year"].items()]
    rows.append(["**2021-2026**", f"**{ic['ic_mean']:+.3f}** (t = {ic['ic_t']:.2f})"])
    return table(["year", "IC"], rows)


# Our book against the three models, all through the same optimizer and costs.
def models(m: dict) -> str:
    ml = load("exhibits/ml_metrics.json")
    if not ml:
        return "The model comparison has not run yet; it runs with --ml."
    perf, cost = m["performance"], m["costs"]
    rows = [
        [
            "**Our book**",
            f"{ml['composite']['ic_t']:.2f}",
            f"{perf['return_gross_annual']:.1%}",
            f"{cost['cost_annual']:.1%}",
            f"**{perf['return_net_annual']:+.1%}**",
            f"{cost['turnover_monthly_one_way']:.0%}",
            f"**{perf['information_ratio']:+.2f}**",
        ]
    ]
    for key, name in (("lgbm", "LightGBM"), ("nn3", "NN3, seed 42"), ("enet", "ElasticNet")):
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
    return table(["", "IC t", "gross", "cost", "net", "turnover", "**net IR**"], rows)


# Out-of-sample R-squared for every method, both forms.
def r2(m: dict) -> str:
    o = load("exhibits/oos_r2.json")
    names = dict(
        template_ols="Template OLS",
        template_ridge="Template ridge",
        template_enet="Template ElasticNet",
        enet="ElasticNet, rank target",
        lgbm="LightGBM",
        nn3="NN3, seed 42",
        scorer="LambdaRank scorer",
        composite="12-signal composite",
    )
    rows = [
        [
            name,
            f"{o['methods'][k]['r2_zero_benchmark']:+.2%}",
            f"{o['methods'][k]['r2_cross_sectional']:+.2%}",
        ]
        for k, name in names.items()
        if k in o["methods"]
    ]
    return table(["method", "R², zero benchmark", "R², cross-sectional"], rows)


# The record in pieces, with block-bootstrap intervals.
def halves(m: dict) -> str:
    s = load("exhibits/pack.json")["subperiod"]
    names = dict(
        full_2021_2026="**Full, 2021-2026**",
        first_half_2021_2022="2021-2022",
        second_half_2023_2026="**2023-2026**",
        excluding_2021="2022-2026",
        crsp_era_2021_2025="CRSP years, 2021-2025",
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
    return table(["period", "months", "gross", "cost", "net", "IR", "95% interval"], rows)


# Six-factor loadings, and alpha as factors are added.
def factors(m: dict) -> str:
    risk = load("exhibits/pack.json")["risk"]
    six, three = risk["five_factor_momentum"], risk["attribution"]
    names = dict(
        mkt_rf="Market (CRSP)",
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
        f"\n\nThe six explain {six['r_squared']:.0%} of the variance, over {six['months']} months."
    )
    return table(["", "loading", "t"], rows) + note


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
        "\n\nReturn over cash, monthly sums, at the full-period loadings on the market, size, "
        "value, profitability, investment and momentum (Ken French's factors, which end a month "
        "before our last). Stock selection is everything the six do not explain."
    )
    return table(["year", "total", "from the six styles", "from stock selection"], rows) + note


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
        ["explained by the twelve", f"{full['explained_total']['contribution_annual']:+.1%}", ""]
    )
    rows.append(["residual", f"{full['residual']['contribution_annual']:+.1%}", ""])
    return table(["signal", "% a year of gross", "t"], rows)


# Three controls that should make the result disappear, and what each did.
def placebo(m: dict) -> str:
    p = load("exhibits/placebo_lab.json")
    null, inv, stale = p["permutation_null"], p["inversion"], p["stale_scores"]
    return table(
        ["control", "what changes", "what happened"],
        [
            [
                "Permutation null",
                f"scores shuffled within sector and liquidity, {null['draws']} draws",
                f"gross {null['gross_annual_mean']:+.2%} a year "
                f"(sd {null['gross_annual_std']:.2%}) against {p['shipped']['gross_annual']:+.1%}; "
                f"net IR {null['mean']:+.2f} at {null['turnover_mean']:.0%} turnover",
            ],
            [
                "Inversion",
                "every score times -1",
                f"gross {inv['gross_annual']:+.1%} against {inv['baseline_gross_annual']:+.1%}",
            ],
            [
                "Stale scores",
                "last month's ranking traded this month",
                f"net IR {stale['net_ir']:+.2f} against {stale['baseline_net_ir_matched']:+.2f} "
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
            ("Gross at rebalance, largest", f"{g['at_rebalance_max']:.1%}"),
            (
                "Gross within a month, largest",
                f"{g['intra_month_max']:.1%}, {g['intra_month_max_month']}",
            ),
            (
                "Months above 200% on some day",
                f"{g['months_above_200pct_on_any_day']} of {rec['months']}",
            ),
            (
                "Net within a month, largest absolute",
                f"{r['net_exposure']['intra_month_max_abs']:.1%}",
            ),
            (
                "Volatility, daily / monthly",
                f"{r['volatility_annual']['daily']:.1%} / {r['volatility_annual']['monthly']:.1%}",
            ),
            (
                "Max drawdown, daily / monthly",
                f"{r['max_drawdown']['daily']:.1%} / {r['max_drawdown']['monthly']:.1%}",
            ),
            (
                "One-day VaR 95% / 99%, CVaR 95%",
                f"{r['var_one_day']['p95']:.2%} / {r['var_one_day']['p99']:.2%}, "
                f"{r['var_one_day']['cvar_95']:.2%}",
            ),
            ("Worst day", f"{r['worst_day']['value']:+.2%}, {r['worst_day']['date']}"),
            (
                "Daily path compounded to months, against returns.csv",
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
    return table(["year", "strategy", "T-bill + 4%", "S&P 500 (price)", "active"], rows)


# The long and the short leg separately, and what the short book is made of.
def legs(m: dict) -> str:
    g = load("exhibits/pack.json")["completeness"]["legs"]
    rows = [
        [
            side,
            f"{g[side]['annual_contribution']:+.1%}",
            f"{g[side]['volatility']:.1%}",
            f"{g[side]['names_per_month']:.0f}",
            f"${g[side]['median_market_cap_musd'] / 1e3:.1f}bn",
            f"${g[side]['median_dollar_volume'] / 1e6:.0f}m",
        ]
        for side in ("long", "short")
    ]
    for row, side in zip(rows, ("long", "short")):
        row.insert(2, f"{g[side]['return_per_dollar_annual']:+.1%}")
    htb, short = m["costs"]["hard_to_borrow_share_of_short_book"], g["short"]
    note = (
        f"\n\nShort book by weight: {short['share_small_or_micro']:.0%} small-cap or below, "
        f"{short['share_micro']:.0%} micro-cap, {htb:.0%} in borrow tiers of 3% a year or more."
    )
    crowd = load("exhibits/daily_risk.json").get("short_interest") or {}
    if crowd:
        note += (
            f" In 2021-2025, {crowd['short_book_weight_crowded']:.0%} of it had more than "
            f"{crowd['crowded_threshold']:.0%} of its shares already sold short."
        )
    header = ["leg", "contribution a year", "per dollar in the leg", "volatility", "names"]
    header += ["median size", "median daily $ volume"]
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
        f"\n\n{everything:,} fits in all, {eligible} of them books we could have shipped. The book "
        "we ship was chosen by comparing these results; after counting every one, the deflated "
        f"Sharpe gives a {chance:.0%} chance its edge is real."
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
                f"{t['labelled']:,} masked 8-Ks from 2015-18 labelled; FinBERT + LightGBM learns "
                f"them at {t['cross_validated_accuracy']:.0%} against {routine:.0%} for always "
                "routine, then labels every filing",
            ]
        )
    a, learned = load("exhibits/analyst.json"), load("exhibits/analyst_learned.json")
    if a:
        probe = a["look_ahead_probe"]
        late = learned.get("recall_test", {}).get("2021-2026", {}).get("analyst", {})
        text = (
            f"{a['stock_months']:,} verdicts; named the company in {probe['company_named']:.0%} "
            f"of {probe['filings']} masked filings"
        )
        if late:
            ic = late["rank_correlation"]
            text += f"; its 2021-26 verdicts' IC {ic:+.3f}, no sign of recall"
        rows.append(["**Analyst**", "Qwen3.8-27B", text])
    c, pack = load("exhibits/crowd.json"), load("exhibits/pack.json")
    if c:
        likes = sorted(c["what_the_crowd_likes"].items(), key=lambda kv: -kv[1])[:2]
        text = (
            f"{c['picks']:,} picks from anonymous cards, 2016-20; the two models agree "
            f"{c['agreement_between_models']:.2f}; they buy {' and '.join(k for k, _ in likes)}"
        )
        crowded = (pack.get("crowding") or {}).get("long")
        if crowded:
            share = crowded["share_in_top_crowd_decile"]
            text += f"; {share:.0%} of our longs sit in their top tenth"
        rows.append(["**AI crowd**", "Gemma 4 and Qwen3.8", text])
    k = load("exhibits/critic.json")
    if k:
        text = f"{len(k['critiques'])} critiques, {k['unsupported']} citing a number no tool showed"
        repeat = k.get("repeatability", {}).get("comparison", {})
        if repeat:
            same, calls = repeat["identical_prefix"], repeat["calls_first"]
            text += f"; run twice, {same} of {calls} calls identical"
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
    brief=brief,
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


# Fills RESULTS.md and BRIEF.md from the latest exhibits.
def main() -> None:
    m = load("metrics.json")
    assert m["notes"]["market_series"] == MARKET_NAME, "metrics.json is from an older run"
    fill(RESULTS, TABLES, m)
    fill(BRIEF, TABLES, m)
    # The README's few numbers too, where a README sits beside RESULTS.md.
    readme = RESULTS.parent / "README.md"
    if readme.exists():
        fill(readme, {}, m)
    perf = m["performance"]
    print(f"filled: IR {perf['information_ratio']:.2f}, net {perf['return_net_annual']:.1%}")


if __name__ == "__main__":
    main()
