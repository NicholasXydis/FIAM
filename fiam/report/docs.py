# Fills every generated table and every number in the prose of RESULTS.md and BRIEF.md.

import json
import re
from pathlib import Path

from fiam import paths
from fiam.book import MARKET_NAME, candidate_label, display_name

SUBMISSION = paths.SUBMISSION
RESULTS, BRIEF = paths.RESULTS, paths.BRIEF

# Prose uses a real minus sign, so a negative number has to match either form.
MINUS = "−"

AUTO = re.compile(r"<!--AUTO:(\w+)-->.*?<!--/AUTO:\1-->", re.S)

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


# One statistic in a row, the same cell applied to each column's data in turn.
def across(columns: list, label: str, cell) -> list[str]:
    return [label, *(cell(c) for c in columns)]


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
    # The code hash at the bottom is how you spot a table from other code.
    return f"{body}\n\n_From code `{run['code_sha256']}`._"


# Which command made these numbers and which trained the models, as the provenance step recorded.
def made(m: dict) -> str:
    manifest = load("exhibits/run_manifest.json")
    run, ml = manifest.get("run") or {}, manifest.get("ml") or {}
    text = f"Made by `{run.get('command', 'uv run run.py --official')}`"
    reused = sum(v.startswith("skipped") for v in run.get("steps", {}).values())
    if reused:
        text += f", reusing {reused} slow steps unchanged since the run that made them"
    if ml.get("command") and ml["command"] != run.get("command"):
        text += f"; models trained by `{ml['command']}`"
    return text + "."


# What the ship rule chose, in one sentence.
def shipped(m: dict) -> str:
    chosen = load("exhibits/ship.json").get("chosen", {})
    others = {y: n for y, n in chosen.items() if n != "composite"}
    if not chosen:
        return "The ship rule has not run, so the composite ships."
    if not others:
        return (
            f"It shipped the composite in all {len(chosen)} years: no learned book beat it clearly."
        )
    picks = "; ".join(f"{candidate_label(n)} in {y}" for y, n in others.items())
    return f"It shipped {picks}, and the composite in the other years."


# The plain-English table in BRIEF.md, with the 2016-2020 check beside the headline.
def brief(m: dict) -> str:
    perf, split = m["performance"], load("exhibits/pack.json").get("subperiod", {})
    clean = load("exhibits/confirmation.json").get("confirmation_2016_2020", {})
    rows = [
        ("Net return", f"**{perf['return_net_annual']:.1%} a year** after every modelled fee"),
        ("Information ratio", f"**{perf['information_ratio']:.2f}**"),
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


# What the WRDS checks found, each line from wrds.json or pack.json.
def wrds(m: dict) -> str:
    w, pack = load("exhibits/wrds.json"), load("exhibits/pack.json")
    if not w:
        return "_Not built: no WRDS exports. Add them with `uv run run.py --import <folder>`._"
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


# The daily path through each pre-registered stress window, and the cost of trading a day late.
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


# Each signal's gross contribution by calendar year, to see which ones stopped working.
def signal_years(m: dict) -> str:
    years = load("exhibits/pack.json")["attribution"]["by_year"]
    columns = sorted(years)
    signals = sorted(years[columns[0]], key=lambda c: -sum(years[y][c] for y in columns))
    rows = [[f"`{c}`", *(f"{years[y][c]:+.1%}" for y in columns)] for c in signals]
    return table(["signal", *columns], rows)


# The ten worst months, traced to legs, sectors and signals.
def worst(m: dict) -> str:
    months = load("exhibits/pack.json")["attribution"]["worst_months"]
    rows = [
        [
            w["month"],
            f"{w['gross']:+.1%}",
            f"{w['long']:+.1%} / {w['short']:+.1%}",
            ", ".join(f"{k} {v:+.1%}" for k, v in list(w["worst_sectors"].items())[:2]),
            ", ".join(f"`{k}` {v:+.1%}" for k, v in list(w["worst_signals"].items())[:2]),
        ]
        for w in months
    ]
    return table(
        ["month", "gross", "long / short leg", "worst sectors (GICS)", "worst signals"], rows
    )


# Six-factor loadings in each half, since one full-period fit can hide a change of style.
def factor_windows(m: dict) -> str:
    split = load("exhibits/pack.json")["risk"]["five_factor_momentum_by_window"]
    names = dict(
        mkt_rf="Market",
        smb="Size",
        hml="Value",
        rmw="Profitability",
        cma="Investment",
        mom="Momentum",
    )
    windows = list(split)
    rows = [
        [label, *(f"{split[w]['betas'][k]:+.2f} ({split[w]['t_stats'][k]:+.1f})" for w in windows)]
        for k, label in names.items()
    ]
    rows.append(
        [
            "Alpha a year",
            *(f"{split[w]['alpha_annual']:+.1%} ({split[w]['alpha_t']:+.1f})" for w in windows),
        ]
    )
    return table(["loading (t)", *(w.replace("_", "-") for w in windows)], rows)


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


# The ship rule's choice for each year, and every candidate book over 2021-2026.
def ship(m: dict) -> str:
    d = load("exhibits/ship.json")
    if not d:
        return "The ship rule has not run yet."
    name = candidate_label
    years = []
    for y, chosen in d["chosen"].items():
        v = d["validation"][y]
        other = max((k for k in v if k != "composite"), key=lambda k: v[k]["information_ratio"])
        base, best = v["composite"]["information_ratio"], v[other]["information_ratio"]
        years.append([y, name(chosen), f"{base:+.2f}", f"{best:+.2f}, {name(other)}"])
    header = ["holding year", "shipped book", "composite IR, two years before", "best other"]
    rows = [
        [
            f"**{name(n)}**" if n in d["chosen"].values() else name(n),
            f"{c['information_ratio']:+.2f}",
            f"{c['net_annual']:+.1%}",
            f"{c['cost_annual']:.1%}",
            f"{c['turnover']:.0%}",
            f"{c['beta']:+.2f}",
        ]
        for n, c in d["candidates_2021_2026"].items()
    ]
    both = ["candidate, 2021-2026", "IR", "net", "cost", "turnover", "beta"]
    return table(header, years) + "\n\n" + table(both, rows)


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


# The trader's methods replayed on each test year of one book: net return a year after costs.
def trader(m: dict) -> str:
    card = load("exhibits/ship.json").get("trader", {})
    methods = dict(deep_hedging="deep hedging, monthly", ppo="PPO, yearly")
    methods["fixed_rate"] = "Gârleanu-Pedersen constant rate"
    methods["trade_all_the_way"] = "trade all the way"
    rows = [[y, *(f"{v[k]['net_annual']:+.1%}" for k in methods)] for y, v in card.items()]
    return table(["year", *methods.values()], rows)


# What the AI crowd buys, and whether betting against it paid.
def crowd(m: dict) -> str:
    d = load("exhibits/crowd.json")
    if not d:
        return "The crowd agent has not run yet; it runs with --agents."
    likes = sorted(d["what_the_crowd_likes"].items(), key=lambda kv: -kv[1])[:4]
    ic = d["against_the_crowd_ic_by_year"]
    early = [v for y, v in ic.items() if "2016" <= y <= "2020"]
    late = [v for y, v in ic.items() if y >= "2021"]
    agree = d["agreement_between_models"]
    rows = [
        ("Picks", f"{d['picks']:,} stock-months, models {', '.join(d['models'])}"),
        ("Agreement between the two models", "one model only" if agree is None else f"{agree:.2f}"),
        ("What the crowd buys most", ", ".join(k for k, _ in likes)),
        (
            "Against the crowd, IC 2016-2020 / 2021-2026",
            f"{sum(early) / max(len(early), 1):+.3f} / {sum(late) / max(len(late), 1):+.3f}",
        ),
    ]
    exposure = load("exhibits/pack.json").get("crowding") or {}
    if exposure:
        long, short = (exposure[s]["weighted_crowd_percentile"] for s in ("long", "short"))
        rows.append(("Our longs / shorts, crowd percentile", f"{long:.0f} / {short:.0f}"))
    return pairs(rows)


# The composite against the three models, all through the same optimizer and costs.
def models(m: dict) -> str:
    ml = load("exhibits/ml_metrics.json")
    base = load("exhibits/ship.json").get("candidates_2021_2026", {}).get("composite")
    perf, cost = m["performance"], m["costs"]
    base = base or dict(
        gross_annual=perf["return_gross_annual"],
        cost_annual=cost["cost_annual"],
        net_annual=perf["return_net_annual"],
        turnover=cost["turnover_monthly_one_way"],
        information_ratio=perf["information_ratio"],
    )
    rows = [
        [
            "**12-signal composite**",
            f"{ml['composite']['ic_t']:.2f}",
            f"{base['gross_annual']:.1%}",
            f"{base['cost_annual']:.1%}",
            f"**{base['net_annual']:+.1%}**",
            f"{base['turnover']:.0%}",
            f"**{base['information_ratio']:+.2f}**",
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
    r = load("exhibits/director.json")
    if r:
        agree, n, own = r["agreed_with_rule"], len(r["years"]), r["director"]
        text = (
            f"chose each year's book from earlier months: IR **{own['information_ratio']:+.2f}**, "
            f"above {own['share_of_random_beaten']:.0%} of random picks; the rule "
            f"{r['rule']['information_ratio']:+.2f}; agreed with it {agree} of {n} years"
        )
        rows.insert(0, ["**Research director**", "Qwen3.8-27B", text])
    e = load("exhibits/explainer.json")
    if e:
        text = f"{len(e['positions'])} positions explained from their facts alone"
        rows.append(["**Explainer**", "Qwen3.8-27B", text])
    runners = {
        a["runner"] for a in (load("exhibits/run_manifest.json").get("agents") or {}).values()
    }
    older = sorted(r for r in runners if r != "fiam.agents.harness")
    note = (
        f"\n\n_From the earlier harness ({', '.join(older)}); the next `--all` run replaces them._"
        if older
        else ""
    )
    return table(["agent", "model", "what happened"], rows) + note


# Each way of choosing a book, window by window, beside random picks over the same years.
def walk(m: dict) -> str:
    e = load("exhibits/evaluation.json")
    if not e:
        return "The research harness has not run yet."
    names = ["2016-2020", "2021-2022", "2023-2026", "2021-2026"]

    # IR with its months, and the months it really covers when fewer than the window's name.
    def cells(windows: dict) -> list[str]:
        out = []
        for w in names:
            x = windows.get(w)
            # Results written before spans were recorded count as covering the whole window.
            span = x.get("span", "") if x else ""
            full = x and (not span or (span[:4] == w[:4] and span[-7:-3] == w[-4:]))
            if not x:
                out.append("")
            elif full:
                out.append(f"{x['information_ratio']:+.2f} ({x['months']})")
            else:
                out.append(f"{x['information_ratio']:+.2f} ({x['months']}, {span})")
        return out

    tracks = e["tracks"]
    rows = [
        ["Shipped book", *cells(e["shipped"])],
        ["Ship rule, walked forward", *cells(tracks["ship_rule"]["windows"])],
        ["Composite every year", *cells(tracks["always_composite"]["windows"])],
    ]
    ch = tracks["ship_rule"]["against_chance"]
    note = (
        f"\n\nIR by window, months in brackets, on the CRSP market. Picks start in "
        f"{e['first_pick']}, the first year with two years of candidates behind it. Random picks "
        f"of one candidate a year average IR {ch['random_mean']:+.2f}; the rule beats "
        f"{ch['share_of_random_beaten']:.0%} of them."
    )
    return table(["", *names], rows) + note


# Construction v2 against the current book, the four pre-registered rules, and each rule alone.
def construction(m: dict) -> str:
    d = load("exhibits/construction.json")
    if not d:
        return "The construction v2 test has not run yet."
    now, v2, verdict = d["current"], d["v2"], d["verdict"]

    columns = [now, v2]

    rows = [
        across(columns, "IR, 2016-2026", lambda b: f"{b['information_ratio']:+.2f}"),
        across(columns, "IR, 2016-2020", lambda b: f"{b['by_window']['y2016_2020']:+.2f}"),
        across(columns, "IR, 2021-2026", lambda b: f"{b['by_window']['y2021_2026']:+.2f}"),
        across(
            columns,
            "Net a year / costs a year",
            lambda b: f"{b['net_annual']:+.1%} / {b['cost_annual']:.1%}",
        ),
        across(
            columns,
            "Beta, monthly (se)",
            lambda b: f"{b['beta_monthly']:+.2f} ({b['beta_monthly_stderr']:.2f})",
        ),
        across(
            columns,
            "Beta, daily 2016-2025 (se)",
            lambda b: f"{b['beta_daily']:+.3f} ({b['beta_daily_stderr']:.3f})",
        ),
        across(columns, "Worst drawdown", lambda b: f"{b['max_drawdown']:.1%}"),
        across(columns, "Largest gross on any day", lambda b: f"{b['gross_max_any_day']:.1%}"),
    ]
    marks = {True: "passed", False: "**failed**"}
    names = dict(
        ir_at_least_current="IR at least the current book's",
        beta_closer_to_zero="beta closer to zero, monthly and daily",
        drawdown_no_deeper="worst drawdown no deeper",
        every_rule_every_month="every rule, every month and day",
    )
    rules = "; ".join(f"{label}: {marks[verdict[k]]}" for k, label in names.items())
    alone = ", ".join(
        f"{k.replace('_', ' ')} {v['information_ratio']:+.2f}"
        for k, v in d["each_rule_alone"].items()
    )
    outcome = "Shipped." if verdict["ships"] else "Not shipped: the current construction stays."
    note = f"\n\n{rules}. **{outcome}** Each rule alone, IR on 2016-2026: {alone}."
    return table(["", "current", "v2"], rows) + note


# The factor-neutral book against the current one: what is left once style is taken out.
def neutral(m: dict) -> str:
    d = load("exhibits/factor_neutral.json")
    if not d:
        return "The factor-neutral test has not run yet."
    now, flat, verdict = d["current"], d["factor_neutral"], d["verdict"]

    columns = [now, flat]

    loadings = ("smb", "hml", "rmw", "cma", "mom")
    rows = [
        across(columns, "IR, 2016-2026", lambda b: f"{b['information_ratio']:+.2f}"),
        *(
            across(columns, f"IR, {w[1:5]}-{w[6:]}", lambda b, w=w: f"{b['by_window'][w]:+.2f}")
            for w in ("y2016_2020", "y2021_2022", "y2023_2026")
        ),
        across(
            columns,
            "Beta, monthly / daily",
            lambda b: f"{b['beta_monthly']:+.2f} / {b['beta_daily']:+.3f}",
        ),
        across(columns, "Worst drawdown", lambda b: f"{b['max_drawdown']:.1%}"),
        across(
            columns,
            "Loadings: size, value, profitability, investment, momentum",
            lambda b: ", ".join(f"{b['factors']['betas'][k]:+.2f}" for k in loadings),
        ),
        across(
            columns,
            "**Six-factor alpha a year (t)**",
            lambda b: f"{b['factors']['alpha_annual']:+.1%} ({b['factors']['alpha_t']:+.2f})",
        ),
    ]
    outcome = "Shipped." if verdict["ships"] else "Not shipped: the current construction stays."
    return table(["", "current", "factor-neutral"], rows) + f"\n\n**{outcome}**"


# How the learned models did year by year as their training data grew: the learning curve.
def learning(m: dict) -> str:
    ic = load("exhibits/scorer.json").get("ic_every_year", {})
    taught = load("exhibits/teachers.json").get("teachers", {})
    if not ic:
        return "The stock picker has not run yet."
    names = [t for t in ("surprise", "beta", "crowding", "revisions") if t in taught]
    rows = []
    for year in sorted(ic):
        cells = [taught[t]["rank_correlation_by_year"].get(year) for t in names]
        rows.append(
            [year, int(year) - 2015, f"{ic[year]:+.3f}"]
            + ["" if c is None else f"{c:.2f}" for c in cells]
        )
    header = ["year", "years of training", "stock picker IC", *(f"{t} teacher" for t in names)]
    return table(header, rows)


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


# The rules' statistics for the strategy, the benchmark and the S&P 500 side by side.
def comparison(m: dict) -> str:
    c = load("exhibits/pack.json")["completeness"]["comparison"]
    names = dict(strategy="strategy", benchmark="T-bill + 4%", sp500="S&P 500 (price)")

    # A month's return with its date.
    def month(x: dict) -> str:
        return f"{x['value']:+.1%}, {x['month']}"

    columns = [c[k] for k in names]
    return table(
        ["", *names.values()],
        [
            across(columns, "Return a year, arithmetic", lambda x: f"{x['annual_arithmetic']:.1%}"),
            across(
                columns, "Return a year, geometric (CAGR)", lambda x: f"{x['annual_geometric']:.1%}"
            ),
            across(columns, "Cumulative", lambda x: f"{x['cumulative']:.1%}"),
            across(columns, "Volatility", lambda x: f"{x['volatility']:.1%}"),
            across(
                columns,
                "Sharpe ratio",
                lambda x: "" if x["sharpe_ratio"] is None else f"{x['sharpe_ratio']:.2f}",
            ),
            across(columns, "Max drawdown", lambda x: f"{x['max_drawdown']:.1%}"),
            across(columns, "Best month", lambda x: month(x["best_month"])),
            across(columns, "Worst month", lambda x: month(x["worst_month"])),
        ],
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


TABLES = dict(
    made=made,
    headline=headline,
    committee=committee,
    comparison=comparison,
    ship=ship,
    teachers=teachers,
    scorer=scorer,
    trader=trader,
    crowd=crowd,
    firewall=firewall,
    years=years,
    legs=legs,
    top=top,
    clean=clean,
    wrds=wrds,
    drift=drift,
    daily=daily,
    costs=costs,
    compliance=compliance,
    models=models,
    r2=r2,
    halves=halves,
    factors=factors,
    styles=styles,
    attribution=attribution,
    tails=tails,
    placebo=placebo,
    walk=walk,
    implementation=implementation,
    stress=stress,
    signal_years=signal_years,
    worst=worst,
    factor_windows=factor_windows,
    construction=construction,
    neutral=neutral,
    learning=learning,
    agents=agents,
    labels=labels,
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


# Fills RESULTS.md and BRIEF.md from the latest exhibits.
def main() -> None:
    m = load("metrics.json")
    assert m["notes"]["market_series"] == MARKET_NAME, "metrics.json is from an older run"
    fill(RESULTS, TABLES, m)
    fill(BRIEF, {**TABLES, "brief": brief, "shipped": shipped}, m)
    perf = m["performance"]
    print(f"filled: IR {perf['information_ratio']:.2f}, net {perf['return_net_annual']:.1%}")


if __name__ == "__main__":
    main()
