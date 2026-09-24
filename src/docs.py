# Fills every generated table in RESULTS.md and BRIEF.md, then fails if a prose number is stale.

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import ALL_TRIALS, DESIGN_TRIALS, MARKET_NAME, display_name

SUBMISSION = Path("submission")
RESULTS, BRIEF = Path("RESULTS.md"), Path("BRIEF.md")

# Prose uses a real minus sign, so a negative number has to match either form.
MINUS = "−"

AUTO = re.compile(r"<!--AUTO:(\w+)-->.*?<!--/AUTO:\1-->", re.S)

# The construction stages in the order the survival exhibit adds them.
STAGES = ("equal_weight", "optimizer", "constrained", "whole_shares", "after_costs")

# The record before the WRDS corrections, 2026-09-23, kept as history beside today's numbers.
BEFORE = dict(
    ir="0.85",
    net="16.3%",
    cost="3.9%",
    turnover="50%",
    beta="-0.11 (se 0.11), CRSP market, 67 months",
    alpha="18.2% (t 2.57)",
    drawdown="-12.5%",
    dsr="0.57 / 0.23 at 1,575",
    missing="0.074% / 0.363%",
    clean_beta="-0.36 (se 0.04), 12 months by mistake",
)

# Numbers the prose repeats, by the file that holds them. Everything else sits in a generated table.
WATCHED = {
    "metrics.json": [("performance.information_ratio", "{:.2f}")],
    "exhibits/confirmation.json": [
        ("confirmation_2016_2020.information_ratio", "{:+.2f}"),
        ("confirmation_2016_2020.beta_realized", "{:+.2f}"),
    ],
    "exhibits/pack.json": [
        ("subperiod.crsp_era_2021_2025.information_ratio", "{:.2f}"),
        ("subperiod.second_half_2023_2026.information_ratio", "{:+.2f}"),
    ],
    "exhibits/nn3_seeds.json": [
        ("spread.information_ratio.min", "{:.2f}"),
        ("spread.information_ratio.mean", "{:.2f}"),
    ],
    "exhibits/ml_metrics.json": [("subset_sweep.early_late_correlation", "{:.2f}")],
    "exhibits/selection.json": [
        ("atlas.before_after_t_correlation", "{:+.2f}"),
        ("atlas.share_keeping_direction", "{:.0%}"),
        ("search_control.chosen_ir_in_search", "{:+.2f}"),
        ("search_control.chosen_ir_in_sealed", "{:+.2f}"),
    ],
    "exhibits/earnings_module.json": [
        ("availability.same_month_as_release", "{:.0%}"),
        ("accounting_lag_stress.lag_3m.information_ratio", "{:.2f}"),
        ("accounting_lag_stress.lag_6m.information_ratio", "{:.2f}"),
    ],
    "exhibits/wrds.json": [("release_day_sensitivity.information_ratio", "{:.2f}")],
}


# An output under submission/, or nothing if its step has not run, so the rest still builds.
def load(name: str) -> dict:
    path = SUBMISSION / name
    return json.loads(path.read_text()) if path.exists() else {}


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
    # The date and commit at the bottom are how you spot a table from an older run.
    return f"{body}\n\n_Generated {run['generated_utc']} from commit `{run['git_commit']}`._"


# The plain-English table in BRIEF.md, with the clean test beside the headline.
def brief(m: dict) -> str:
    perf, split = m["performance"], load("exhibits/pack.json").get("subperiod", {})
    clean = load("exhibits/confirmation.json").get("confirmation_2016_2020", {})
    rows = [
        ("Net return", f"**{perf['return_net_annual']:.1%} a year** after every modelled fee"),
        ("Information ratio", f"**{perf['information_ratio']:.2f}**"),
        ("Alpha", f"{perf['alpha_annual']:.1%} a year, t = {perf['alpha_tstat']:.2f}"),
        (
            "Beta to the S&P 500",
            f"{perf['beta_realized']:.2f}, standard error {perf['beta_stderr']:.2f}",
        ),
        ("Worst drawdown", f"{perf['max_drawdown_total']:.1%}"),
    ]
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
        rows.append(("2016-2020, never looked at", f"IR {clean['information_ratio']:+.2f}, {beta}"))
    return pairs(rows)


# The frozen book on the window design never saw, beside the record, both on the CRSP market.
def clean(m: dict) -> str:
    c = load("exhibits/confirmation.json")
    old, new = c["confirmation_2016_2020"], c["shipped_2021_2026"]

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
    return table(["", "2016-2020, never looked at", "2021-2026, the record"], rows)


# The record before and after the WRDS corrections, so every changed number is explained.
def corrections(m: dict) -> str:
    perf, cost, rob = m["performance"], m["costs"], m["robustness"]
    clean = load("exhibits/confirmation.json")["confirmation_2016_2020"]
    now = dict(
        ir=f"{perf['information_ratio']:.2f}",
        net=f"{perf['return_net_annual']:.1%}",
        cost=f"{cost['cost_annual']:.1%}",
        turnover=f"{cost['turnover_monthly_one_way']:.0%}",
        beta=f"{perf['beta_realized']:.2f} (se {perf['beta_stderr']:.2f}), S&P 500, "
        f"{m['notes']['regression_months']} months",
        alpha=f"{perf['alpha_annual']:.1%} (t {perf['alpha_tstat']:.2f})",
        drawdown=f"{perf['max_drawdown_total']:.1%}",
        dsr=f"{rob[f'deflated_sharpe_probability_{DESIGN_TRIALS}_eligible_attempts']:.2f} / "
        f"{rob[f'deflated_sharpe_probability_{ALL_TRIALS}_all_attempts']:.2f}",
        missing=f"{rob['missing_long_weight_monthly']:.3%} / "
        f"{rob['missing_short_weight_monthly']:.3%}",
        clean_beta=f"{clean['beta_realized']:.2f} (se {clean['beta_stderr']:.2f}), 60 months",
    )
    names = dict(
        ir="Information ratio",
        net="Net return",
        cost="Costs a year",
        turnover="Turnover, one-way monthly",
        beta="Realized beta",
        alpha="Alpha",
        drawdown="Max drawdown",
        dsr=f"Deflated-Sharpe probability, {DESIGN_TRIALS} / {ALL_TRIALS:,}",
        missing="Weight with no return, long / short",
        clean_beta="2016-2020 beta, CRSP market",
    )
    return table(["", "before", "now"], [[names[k], BEFORE[k], now[k]] for k in names])


# What the WRDS checks found, each line from wrds.json or pack.json.
def wrds(m: dict) -> str:
    w, pack = load("exhibits/wrds.json"), load("exhibits/pack.json")
    if not w:
        return "_Not built: no WRDS exports. Run `python src/wrds.py <exports>` first._"
    e, r, mk = w["exits"], w["returns_against_crsp"], w["market_with_dividends"]
    held, dates, day = (
        e["held_exiting_during_holding_month"],
        w["report_dates"],
        w["release_day_sensitivity"],
    )
    years = pack["data_by_year"]
    crsp_std = [v["cross_sectional_std"] for y, v in years.items() if v["returns_from"] == "CRSP"]
    crsp_tail = [v["share_beyond_50pct"] for y, v in years.items() if v["returns_from"] == "CRSP"]
    late = years["2026"]
    total, price = mk["total_return_crsp"], mk["price_only_fred"]
    alone = w["organizer_data_only"]
    return pairs(
        [
            (
                "Dated delistings and deletions applied",
                f"{sum(e['by_source'].values()):,} securities",
            ),
            (
                "Rows already delisted at the decision, screened out",
                f"{e['rows_already_delisted_at_decision_screened']}",
            ),
            ("Held names already delisted", f"{e['held_and_already_dead']}"),
            (
                "Held names taken over in their holding month",
                f"{held['securities']}, {held['by_kind'].get('MER CASH', 0)} for cash; payouts "
                f"{held['payout_contribution_annual'] * 1e4:+.1f} bp a year, closing cost "
                f"{held['closing_cost_annual_already_charged'] * 1e4:.1f} bp, already charged",
            ),
            (
                "Panel returns against CRSP, 2021-2025",
                f"{r['share_within_1bp']:.1%} within 1 bp, correlation {r['correlation']:.4f}, "
                f"{r['share_off_by_over_1pct']:.2%} off by over 1%",
            ),
            (
                f"Beta, S&P 500 with dividends, {mk['window']}",
                f"{total['beta']:+.2f} (se {total['beta_stderr']:.2f}) against "
                f"{price['beta']:+.2f} price-only; "
                f"dividends {mk['dividend_gap_annual']:.1%} a year",
            ),
            (
                "Accounting updates with no new report behind them",
                f"worst signal {dates['worst_early_share']:.2%}, rule 1%; a random month holds a "
                f"release {dates['chance_a_month_has_a_release']:.0%} of the time",
            ),
            (
                "Updates from a report dated on the decision day, held back a month",
                f"IR {day['information_ratio']:.2f}, net {day['net_annual']:.1%}; "
                f"{day['panel_rows_affected_share']:.1%} of rows",
            ),
            (
                "Same code without WRDS, as a judge rebuilds it",
                f"IR {alone['information_ratio']:.2f}, net {alone['return_net_annual']:.1%}, "
                f"beta {alone['beta_realized']:+.2f}",
            ),
            (
                "IR on CRSP years only, 2021-2025",
                f"{pack['subperiod']['crsp_era_2021_2025']['information_ratio']:.2f} over "
                f"{pack['subperiod']['crsp_era_2021_2025']['months']} months",
            ),
            (
                "2026, returns from Compustat",
                f"monthly spread {late['cross_sectional_std']:.3f} against "
                f"{min(crsp_std):.3f}-{max(crsp_std):.3f}; moves past ±50% "
                f"{late['share_beyond_50pct']:.2%} against "
                f"{min(crsp_tail):.2%}-{max(crsp_tail):.2%}",
            ),
        ]
    )


# Realized beta by era and in rolling years, against the full period.
def drift(m: dict) -> str:
    d, perf = load("exhibits/pack.json")["beta_drift"], m["performance"]
    rows = [
        [p.replace("_", "-"), f"{x['beta']:+.2f}", f"{x['stderr']:.2f}", f"{x['t']:+.2f}"]
        for p, x in d.items()
        if isinstance(x, dict)
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
    note = (
        f"\n\n{d['rolling_12m_outside_band']:.0%} of {d['rolling_12m_windows']} rolling 12-month "
        "windows sit outside ±0.20."
    )
    return table(["period", "beta", "se", "t"], rows) + note


# The five cost lines as the backtest recorded them, and how far they can rise.
def costs(m: dict) -> str:
    c = load("exhibits/pack.json")["costs"]
    parts, even = c["components"], c["break_even"]
    names = dict(
        commission="Commission, exchange, regulatory",
        impact="Market impact",
        borrow_general_collateral="Borrow, general collateral",
        borrow_hard_to_borrow="Borrow, hard-to-borrow surcharge",
        spread="Half-spread (scaled Corwin-Schultz)",
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


# The limits the rules set, measured after rounding to whole shares.
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
            ["Sector, 11 GICS + `XX`", "1% target", f"max {c['sector_tilt_max']:.2%}"],
            ["Single name", "1.5% target", f"max {c['position_weight_max']:.2%}"],
            ["Ex-ante beta", "±0.02", f"mean {c['beta_exante_weighted_mean']:+.3f}"],
            [
                "Realized beta",
                "build fails outside ±0.20",
                f"{perf['beta_realized']:+.2f} (se {perf['beta_stderr']:.2f})",
            ],
        ],
    )


# The composite against the three models, all through the same optimizer and costs.
def models(m: dict) -> str:
    ml, perf, cost = load("exhibits/ml_metrics.json"), m["performance"], m["costs"]
    rows = [
        [
            "**12-signal composite**",
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


# Net IR at each construction stage, the last one being the shipped book.
def stages(m: dict) -> str:
    survival = load("exhibits/constraint_survival.json")["models"]
    names = (("composite", "**12-signal composite**"), ("lgbm", "LightGBM"), ("nn3", "NN3"))
    rows = [
        [name, *[f"{survival[key]['portfolio'][s]['net_ir']:+.2f}" for s in STAGES]]
        for key, name in (*names, ("enet", "ElasticNet"))
    ]
    header = ["", "equal-weight", "optimizer", "+ neutrality", "+ whole shares", "**+ costs**"]
    return table(header, rows)


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
        composite="12-signal composite",
    )
    rows = [
        [
            name,
            f"{o['methods'][k]['r2_zero_benchmark']:+.2%}",
            f"{o['methods'][k]['r2_cross_sectional']:+.2%}",
        ]
        for k, name in names.items()
    ]
    seeds = o["nn3_seed_range"]
    note = f"\n\nNN3 across five seeds: {seeds['min']:+.2%} to {seeds['max']:+.2%}, zero benchmark."
    return table(["method", "R², zero benchmark", "R², cross-sectional"], rows) + note


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


# Tail risk and consistency, which monthly volatility hides.
def tails(m: dict) -> str:
    risk = load("exhibits/pack.json")["risk"]
    t, c = risk["tails"], risk["consistency"]
    return pairs(
        [
            ("95% VaR, monthly", f"{t['var_95_monthly']:.2%}"),
            ("95% CVaR, monthly", f"{t['cvar_95_monthly']:.2%}"),
            ("Skew", f"{t['skew']:+.2f}"),
            ("Excess kurtosis", f"{t['excess_kurtosis']:+.2f}"),
            (
                "Rolling 12-month windows with a negative IR",
                f"{c['share_negative']:.0%} of {c['windows']}",
            ),
        ]
    )


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


# The earnings module: judged on 2016-2020 by a rule written first, then 2021-2026.
def earnings(m: dict) -> str:
    d, e = load("exhibits/earnings_decision.json"), load("exhibits/earnings_module.json")
    names = dict(
        frozen_book="Frozen book",
        announcement_premium="Announcement premium (Frazzini-Lamont 2007)",
        combined_surprise="Earnings plus revenue surprise (Jegadeesh-Livnat 2006)",
        fresh_surprise="Fresh surprise only",
    )

    def pick(source, key):
        return source["frozen_book"] if key == "frozen_book" else source["variants"][key]

    rows = []
    for key, name in names.items():
        early, late = pick(d, key), pick(e, key)
        rows.append(
            [
                name,
                f"{early['information_ratio']:+.2f}",
                f"{early['beta_realized']:+.2f}",
                "monotone" if early["tails_monotone"] else "not monotone",
                f"{late['information_ratio']:+.2f}",
            ]
        )
    rule = d["rule"]
    note = (
        f"\n\nRule: +{rule['min_ir_gain']:.2f} IR on 2016-2020, beta inside "
        f"±{rule['max_abs_beta']:.2f}, monotone tails. Shipped: {'yes' if e['ship'] else '**no**'}."
    )
    return table(["variant", "2016-20 IR", "2016-20 beta", "tails", "2021-26 IR"], rows) + note


# What each agent did, from its exhibit.
def agents(m: dict) -> str:
    d, c, a = (
        load("exhibits/discovery.json"),
        load("exhibits/critic.json"),
        load("exhibits/auditor.json"),
    )
    rows = []
    if d:
        runs, ctl = d["runs"], d["random_search_control"]
        text = "; ".join(
            f"{'real' if tag == 'named' else tag} names: {r['backtests_used']} backtests, "
            + (
                f"best in sample {r['best_design_ir_seen']:.2f}, "
                if r["best_design_ir_seen"]
                else ""
            )
            + "sealed IR "
            + (f"**{r['sealed']['information_ratio']:+.2f}**" if r.get("sealed") else "no pick")
            for tag, r in runs.items()
        )
        text += f"; random search, same budget, sealed IR {ctl['sealed']['information_ratio']:+.2f}"
        rows.append(["**Signal discovery**", "Qwen3.8-27B", text])
    if c:
        repeat = c.get("repeatability", {}).get("comparison", {})
        text = (
            f"{len(c['critiques'])} critiques, {c['unsupported']} quoting a number no tool showed"
        )
        if repeat:
            same, calls = repeat["identical_prefix"], repeat["calls_first"]
            text += f"; run twice, {same} of {calls} calls identical"
        rows.append(["**Devil's advocate**", "Gemma 4 26B-A4B", text])
    if a:
        planted, clean = a["runs"]["planted"], a["runs"]["clean"]
        text = (
            f"found **{planted['score']['found']} of {planted['score']['planted']}** planted bugs; "
            f"{clean['score']['false_alarms']} false alarms on the clean copy"
        )
        rows.append(["**Reproducibility**", "Qwen3.8-27B", text])
    return table(["agent", "model", "what happened"], rows)


# Every holding label, by the source that confirmed it.
def labels(m: dict) -> str:
    lab = load("exhibits/labels.json")
    rows = [
        [period.replace("_", " "), source, f"{count:,}"]
        for period, sources in lab["by_period"].items()
        for source, count in sources.items()
    ]
    fixed = ", ".join(
        f"{c['was']} → {c['now']} from {c['from_decisions_on_or_after']}" for c in lab["corrected"]
    )
    note = (
        f"\n\n{lab['confirmed_share']:.2%} of {lab['holding_rows']:,} holding rows confirmed. "
        f"Corrected from SEC's dated record: {fixed}."
    )
    return table(["period", "confirmed by", "rows"], rows) + note


# The one strictly out-of-sample result, and today's code beside it.
def live(m: dict) -> str:
    f = load("exhibits/live_forecast.json")
    now = f.get("current_code", {})
    rows = [
        (
            "Sealed book",
            f"{f['positions']} names, SHA-256 `{f['sha256'][:16]}`, "
            f"first hashed {f['first_hashed_utc']}",
        ),
        ("Holding month", f"{f['holding_month']}; the clean test is October 2026, same book"),
    ]
    if now:
        same = (
            "identical"
            if now["identical_to_sealed"]
            else f"{now['positions']} names, `{now['sha256'][:16]}`"
        )
        rows.append(("Today's code, same month", f"{same}; the sealed file is never rewritten"))
    # Scored on public prices once live_score.py has run; a month still open says so.
    scored = load("exhibits/live_score.json").get("sealed", {})
    if scored:
        c = scored["check_2026"]
        rows.append(
            (
                "2026 panel returns against public prices",
                f"{c['share_within_half_percent']:.0%} within 0.5%; {c['names_verified']} of "
                f"{c['names_priced']} tickers confirmed",
            )
        )
    labels = {"2026-09": "September, hashed mid-month", "2026-10": "October, the clean test"}
    for month, r in scored.get("months", {}).items():
        state = "final" if r["final"] else f"to {r['sp500_through']}"
        rows.append(
            (
                labels.get(month, month),
                f"total {r['total_return']:+.2%}, active {r['active_return']:+.2%}, "
                f"S&P 500 {r['sp500']:+.2%}; {state}",
            )
        )
    return pairs(rows)


# The deflated-Sharpe probability at both attempt counts, with the Sharpe luck alone produces.
def deflation(m: dict) -> str:
    r = m["robustness"]
    rows = [
        [
            f"**At {DESIGN_TRIALS} eligible attempts**",
            f"{r[f'sharpe_luck_alone_produces_at_{DESIGN_TRIALS}']:.2f}",
            f"**{r[f'deflated_sharpe_probability_{DESIGN_TRIALS}_eligible_attempts']:.2f}**",
        ],
        [
            f"At {ALL_TRIALS:,}, every fit we ever ran",
            f"{r[f'sharpe_luck_alone_produces_at_{ALL_TRIALS}']:.2f}",
            f"{r[f'deflated_sharpe_probability_{ALL_TRIALS}_all_attempts']:.2f}",
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
    htb = m["costs"]["hard_to_borrow_share_of_short_book"]
    note = f"\n\nShort positions flagged small-cap or hard to borrow: {htb:.0%} of the short book."
    header = ["leg", "return a year", "volatility", "names", "median size", "median daily $ volume"]
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


TABLES = dict(
    headline=headline,
    committee=committee,
    years=years,
    legs=legs,
    top=top,
    clean=clean,
    corrections=corrections,
    wrds=wrds,
    drift=drift,
    costs=costs,
    compliance=compliance,
    models=models,
    stages=stages,
    r2=r2,
    halves=halves,
    factors=factors,
    attribution=attribution,
    tails=tails,
    placebo=placebo,
    earnings=earnings,
    agents=agents,
    labels=labels,
    live=live,
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
    target.write_text(text, encoding="utf-8")


# "performance.sharpe_ratio" means that group, then that key. A number steps into a list.
def dig(data, path: str):
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


# Every watched number missing from the prose. The generated tables are cut first, or they pass all.
def stale() -> tuple[list[tuple[str, str]], int]:
    prose = AUTO.sub("", RESULTS.read_text(encoding="utf-8"))
    missing, checked = [], 0
    for name, watched in WATCHED.items():
        data = load(name)
        if not data:
            continue
        for key, fmt in watched:
            checked += 1
            value = fmt.format(dig(data, key))
            if value not in prose and value.replace("-", MINUS) not in prose:
                missing.append((f"{name}: {key}", value))
    return missing, checked


def main() -> int:
    m = load("metrics.json")
    assert m["notes"]["market_series"] == MARKET_NAME, "metrics.json is from an older run"
    fill(RESULTS, TABLES, m)
    fill(BRIEF, {**TABLES, "brief": brief}, m)
    perf = m["performance"]
    print(f"tables filled: IR {perf['information_ratio']:.2f}, net {perf['return_net_annual']:.1%}")

    missing, checked = stale()
    if missing:
        print("RESULTS.md is out of date. These numbers are not in it anywhere:")
        for key, value in missing:
            print(f"  {key} is now {value}")
        return 1
    print(f"RESULTS.md matches the generated numbers ({checked} values checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
