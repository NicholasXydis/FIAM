# The Q&A bank: the questions a portfolio manager will ask, answered from numbers our code wrote.
# facts() is also the one source of every number on the finals slides.

import re
from pathlib import Path

import numpy as np

from fiam import paths, v2
from fiam.agents import harness as H
from fiam.agents import rules_reader
from fiam.paths import read_json as load

OUT = Path("out") / "qa.md"
PCT, INT, ONE, TWO, SIGNED = "{:.1%}", "{:,.0f}", "{:.1f}", "{:.2f}", "{:+.3f}"
# AMD's total board power for our Radeon RX 9070 XT: an upper bound for the energy estimate.
BOARD_WATTS = 304


# A value from nested results, formatted, or a dash while the step that writes it has not run.
def get(data: dict, keys: str, fmt: str = TWO) -> str:
    for key in keys.split("/"):
        if not isinstance(data, dict) or key not in data:
            return "-"
        data = data[key]
    return fmt.format(data) if isinstance(data, (int, float)) else str(data)


# Every number the answers quote, each from the file that holds it.
def facts() -> dict:
    m, ev = load(paths.METRICS), load(v2.OUT / "evidence.json")
    crowd, stress = load(v2.OUT / "crowd_lab.json"), load(v2.OUT / "stress.json")
    naut, desk = load(v2.OUT / "nautilus" / "check.json"), load(v2.OUT / "desk.json")
    vol = load(Path("frozen") / "vol_check.json")
    honesty = load(v2.OUT / "honesty.json")
    book = crowd.get("v1@1e7 record", {})
    record = ev.get("comparison_at_10m", {}).get("record", {}).get("v1", {})
    losses = ev.get("weak_periods", {}).get("v1", {}).get("losses_2023_26", {})
    f = dict(
        ir=get(m, "performance/information_ratio"),
        net=get(m, "performance/return_net_annual", PCT),
        beta=get(m, "performance/beta_realized"),
        beta_se=get(m, "performance/beta_stderr"),
        alpha_t=get(m, "performance/alpha_tstat"),
        fits=get(m, "robustness/attempts_all", INT),
        dsr=get(m, "robustness/deflated_sharpe_probability_all", "{:.0%}"),
        trials=get(ev, "trials/full", INT),
        effective=get(ev, "trials/effective", INT),
        dsr_v1=get(ev, "deflated_sharpe/v1 full", "{:.0%}"),
        dsr_v1_eff=get(ev, "deflated_sharpe/v1 effective", "{:.0%}"),
        nw3=get(record, "alpha_t_hac3"),
        nw11=get(record, "alpha_t_hac11"),
        ewc=get(record, "alpha_t_ewc"),
        dimson=get(ev, "daily_at_10m/v1 record/dimson_beta"),
        drag_beta=get(ev, "weak_periods/v1/beta_drag_2016_20/beta"),
        drag=get(ev, "weak_periods/v1/beta_drag_2016_20/drag/mean", PCT),
        rest=get(ev, "weak_periods/v1/beta_drag_2016_20/rest/mean", PCT),
        ic_star=get(ev, "break_even_ic/v1/ic_star", "{:.3f}"),
        ic_real=get(ev, "break_even_ic/v1/ic_realized", "{:.3f}"),
        ic_star_v2=get(ev, "break_even_ic/v2/ic_star", "{:.3f}"),
        taq_large=get(ev, "spreads_vs_taq/large/ratio"),
        taq_micro=get(ev, "spreads_vs_taq/micro/ratio"),
        profit_share=(
            "{:.0%}".format(losses["themes"]["profitability"] / losses["loss"]) if losses else "-"
        ),
        did=get(honesty, "memorization_did/estimate", "{:+.1%}"),
        reid=get(honesty, "reidentification/after/share", "{:.0%}"),
        rerun=get(crowd, "retail/replay_checks/rerun/agreement", "{:.0%}"),
        moved=get(crowd, "retail/replay_checks/perturbed/agreement", "{:.0%}"),
        cost=get(m, "costs/cost_annual", PCT),
        cost_share=get(m, "costs/cost_share_of_gross", "{:.0%}"),
        v1_cost_1bn=get(ev, "verdicts/v2/1e9/v1_cost", PCT),
        v2_cost_1bn=get(ev, "verdicts/v2/1e9/cost", PCT),
        rmw=get(stress, "v1/loadings/rmw"),
        rmw_move=get(stress, "v1/reverse_stress/move/rmw", PCT),
        covid=get(stress, "v1/crises/Covid crash/loss", PCT),
        junk=get(stress, "v1/crises/Junk rally, momentum crash/loss", PCT),
        rates=get(stress, "v1/crises/Rate shock/loss", PCT),
        cover_v1=get(stress, "v1/liquidity/1e+09/short/weighted_mean", "{:.0f}"),
        cover_v2=get(stress, "v2/liquidity/1e+09/short/weighted_mean", "{:.0f}"),
        squeeze=get(stress, "v1/squeeze_2021/loss", PCT),
        borrow=get(ev, "verdicts/shorts/borrow", PCT),
        borrow_v1=get(ev, "verdicts/shorts/v1_borrow", PCT),
        agents=get(crowd, "retail/agreement/agents", INT),
        voters=get(crowd, "retail/agreement/effective_voters", ONE),
        lsv=get(crowd, "retail/herding/lsv", "{:.3f}"),
        crowd_beta=get(book, "crowding_beta/beta"),
        crowd_t=get(book, "crowding_beta/t", ONE),
        sell_50=get(book, "sell_off_cost/50bn", PCT),
        shorts_rho=get(crowd, "retail/vs_short_sellers/spearman_mean", SIGNED),
        warn_months=get(ev, "warning_signs/v1/daily_beta/months", INT),
        warn_next=get(ev, "warning_signs/v1/daily_beta/next_3_months", PCT),
        warn_avg=get(ev, "warning_signs/v1/next_3_months_average", PCT),
        naut_gap=get(naut, "v1@1e7/mean_abs_gap", "{:.4%}"),
        confirmed=get(desk, "advocate/confirmed", INT),
        asked=get(desk, "advocate/asked", INT),
        chance=get(desk, "advocate/chance", ONE),
        vol_lgbm=get(vol, "qlike_by_year/2020/lgbm"),
        vol_har=get(vol, "qlike_by_year/2020/har"),
        scorer_ic=get(load(paths.EXHIBITS / "scorer.json"), "ic_2021_2026/ic_mean", "{:.3f}"),
        scorer_t=get(load(paths.EXHIBITS / "scorer.json"), "ic_2021_2026/ic_t"),
        beta_error=get(load(paths.EXHIBITS / "teachers.json"), "teachers/beta/mean_abs_error"),
        beta_error_60m=get(
            load(paths.EXHIBITS / "teachers.json"), "teachers/beta/beta_60m_mean_abs_error"
        ),
    )
    verdicts = ev.get("verdicts", {})
    f["verdicts"] = ", ".join(
        f"{k}: {'pass' if v.get('passed') else 'fail'}" for k, v in verdicts.items() if k != "v2"
    )
    return f | more()


# Money as a reader says it: $205M, $1.2B.
def money(x) -> str:
    if not isinstance(x, (int, float)):
        return str(x)
    return f"${x / 1e9:.1f}B" if abs(x) >= 1e9 else f"${x / 1e6:.0f}M"


# The finals numbers added for capacity, the crowd insights, v2a and the desk, in the same form.
def more() -> dict:
    cap, ins = load(v2.OUT / "capacity.json"), load(v2.OUT / "crowd_insights.json")
    crowd, ev = load(v2.OUT / "crowd_lab.json"), load(v2.OUT / "evidence.json")
    books = cap.get("books", {})

    def at(book: str, capital: float, key: str):
        rows = books.get(book, {}).get("record", [])
        return next((r[key] for r in rows if r["capital"] == capital), None)

    def show(value, fmt: str = TWO) -> str:
        return fmt.format(value) if isinstance(value, (int, float)) else "-"

    v1_peak = books.get("v1", {}).get("peak")
    likes = list(ins.get("what_it_buys", {}).get("likes", {}))[:3]
    fear = ins.get("herding_and_fear", {}).get("retail", {})
    f = dict(
        v1_peak=money(v1_peak) if v1_peak else "-",
        v1_peak_dollars=money(at("v1", v1_peak, "dollars")) if v1_peak else "-",
        v1_breakeven=money(books.get("v1", {}).get("break_even", "-")),
        v2_breakeven=money(books.get("v2", {}).get("break_even", "-")),
        v1_breakeven_half=money(
            cap.get("stress", {}).get("impact_half v1", {}).get("break_even", "-")
        ),
        v2_ir_5bn=show(at("v2", 5e9, "information_ratio")),
        v1_ir_5bn=show(at("v1", 5e9, "information_ratio")),
        v2_cost_5bn=show(at("v2", 5e9, "cost_annual"), PCT),
        v1_cost_5bn=show(at("v1", 5e9, "cost_annual"), PCT),
        v2_dollars_5bn=money(at("v2", 5e9, "dollars")) if at("v2", 5e9, "dollars") else "-",
        v2a_ir=show(at("v2a", 1e7, "information_ratio")),
        pass_ir=show(at("v2-pass", 1e7, "information_ratio")),
        pass_name="+".join(
            k for k in ("shorts", "grinold") if ev.get("verdicts", {}).get(k, {}).get("passed")
        )
        or "-",
        grinold=("pass" if ev.get("verdicts", {}).get("grinold", {}).get("passed") else "fail")
        if "grinold" in ev.get("verdicts", {})
        else "-",
        copy_longs=get(ins, "copycat_test/v1/buys_our_longs", "{:.1f}x"),
        copy_shorts=get(ins, "copycat_test/v1/shorts_our_shorts", "{:.1f}x"),
        overlap_retail=get(ins, "overlap/retail/longs_in_favourites", "{:.0%}"),
        overlap_copycat=get(ins, "overlap/copycat/longs_in_favourites", "{:.0%}"),
        voters_copycat=get(crowd, "copycat/agreement/effective_voters", ONE),
        fear_rho=get(fear, "spearman", "{:+.2f}"),
        likes=", ".join(likes) or "-",
        tax_10bn=get(ins, "capacity_tax_bp_a_month/v1 at $1e9, copycats $10bn", ONE),
        before_costs=get(ins, "before_costs/retail/gross_ir"),
        after_costs=get(ins, "before_costs/retail/net_ir"),
    )
    # Each rules drill against its hand-made reference: this year's rules first, then 2025's.
    drills = load(v2.OUT / "drill.json")
    latest = drills.get("rules_2026") or drills.get("case_2025") or {}
    f["drill"] = show(latest.get("minutes"), ONE)
    ran = latest.get("books", {})
    bad = sum(b["breaches"] + b.get("empty", 0) for b in ran.values())
    f["drill_breaches"] = str(bad) if ran else "-"
    for name in ("case_2025", "rules_2026"):
        draft = load(Path("mandates") / f"{name}_draft.json")
        truth = load(Path("mandates") / f"{name}.json")
        limits = [k for k in rules_reader.NUMBERS if truth.get(k) is not None]
        same = sum(draft.get(k) == truth[k] for k in limits)
        f["rules" if name == "case_2025" else name] = f"{same} of {len(limits)}" if draft else "-"
    cross = crossover(books)
    f["crossover"] = money(cross) if cross else "-"
    halves = load(paths.EXHIBITS / "pack.json").get("subperiod", {})
    f["ir_2021_22"] = get(halves, "first_half_2021_2022/information_ratio")
    f["ir_2023_26"] = get(halves, "second_half_2023_2026/information_ratio")
    losses = ev.get("weak_periods", {}).get("v1", {}).get("losses_2023_26", {})
    f["junk_loss"] = get(losses, "themes/profitability", PCT)
    f["loss_months"] = str(losses.get("months", "-"))
    lines = sum(sum(1 for _ in p.open(encoding="utf-8")) for p in H.RUNS.glob("*.jsonl"))
    f["decisions_total"] = f"{lines:,}"
    f["check_ir"] = get(ev, "comparison_at_10m/check/v1/information_ratio")
    return f | final(ev, books, at) | compute(lines)


# What each of v3's parts does, in a sentence's words.
WORDS = dict(
    size="trades more slowly as the fund grows",
    lowvol="drops a hidden bet on calm stocks",
    voltarget="holds its risk steady",
    brake="brakes after a fall",
)
NOUNS = dict(
    size="slower trading at size",
    lowvol="the low-volatility rule",
    voltarget="the risk target",
    brake="the drawdown brake",
)


# v3, the final book (v2_amendment_2.md): its parts' verdicts and its figures at each fund size.
def final(ev: dict, books: dict, at) -> dict:
    verdicts = ev.get("verdicts", {})
    judged = [p for p in v2.PARTS if p in verdicts]
    f = dict(
        v3_parts=", ".join(
            f"{p}: {'pass' if verdicts[p].get('passed') else 'fail'}" for p in judged
        )
        or "-",
        v3_size="pass" if verdicts.get("size", {}).get("passed") else "fail",
        v3_rules=" and ".join(
            ", ".join(WORDS[p] for p in judged if verdicts[p].get("passed")).rsplit(", ", 1)
        )
        or "-",
        v3_dropped=", ".join(NOUNS[p] for p in judged if not verdicts[p].get("passed")) or "none",
        v3_passed=str(sum(bool(verdicts[p].get("passed")) for p in judged)),
        v3_beta_se=get(ev, "v3/1e7/books/v3/beta_stderr"),
        v3_breakeven=money(books.get("v3", {}).get("break_even", "-")),
        dsr_v3=get(ev, "v3/1e7/deflated_sharpe/v3 full", "{:.0%}"),
        dsr_v3_eff=get(ev, "v3/1e7/deflated_sharpe/v3 effective", "{:.0%}"),
    )
    shown = dict(
        information_ratio=("ir", TWO),
        sharpe_ratio=("sharpe", TWO),
        return_net_annual=("net", PCT),
        volatility_annual=("vol", PCT),
        max_drawdown_total=("dd", PCT),
        beta_realized=("beta", "{:+.2f}"),
    )
    for tag in ("1e7", "1e8", "1e9", "5e9"):
        for key, (name, fmt) in shown.items():
            f[f"v3_{name}_{tag}"] = get(ev, f"v3/{tag}/books/v3/{key}", fmt)
    dollars = at("v3", 5e9, "dollars")
    f["v3_dollars_5bn"] = money(dollars) if dollars is not None else "-"
    benchmarks = ("v1", "v2", "v2-pass")
    f |= wins(ev.get("v3", {}), "v3", benchmarks, "v3")
    return f | final_three(ev, books, at, shown)


# What each of final v3's rules and fixes does, in a sentence's words (v2_amendment_3.md).
FINAL_WORDS = dict(
    zerobeta="holds its beta at zero",
    target10="aims at 10% volatility with a risk forecast that corrects itself",
    riskcap="sizes volatile stocks smaller",
    adaptive="halves a signal on a 12-month losing streak",
)
FINAL_NOUNS = dict(riskcap="risk-sized positions", adaptive="adaptive signal weights")


# Final v3's figures at each fund size, its fixes' verdicts and its wins against every other book.
def final_three(ev: dict, books: dict, at, shown: dict) -> dict:
    verdicts = ev.get("verdicts", {})
    chosen = ev.get("v3", {}).get("final", {}).get("switches", [])
    passed = [p for p in v2.FINAL if p in chosen]
    failed = [p for p in v2.TESTED if p in verdicts and not verdicts[p].get("passed")]
    f = dict(
        fv3_rules=" and ".join(", ".join(FINAL_WORDS[p] for p in passed).rsplit(", ", 1)) or "-",
        fv3_dropped=" and ".join(", ".join(FINAL_NOUNS[p] for p in failed).rsplit(", ", 1))
        or "none",
        fv3_beta_se=get(ev, "v3/1e7/books/final v3/beta_stderr"),
        fv3_breakeven=money(books.get("final v3", {}).get("break_even", "-")),
        dsr_fv3=get(ev, "v3/1e7/deflated_sharpe/final v3 full", "{:.0%}"),
        dsr_fv3_eff=get(ev, "v3/1e7/deflated_sharpe/final v3 effective", "{:.0%}"),
        fv3_underwater=get(ev, "v3/1e7/books/final v3/months_underwater_max", "{:.0f}"),
        fv3_gross_max_daily=get(ev, "final_daily/gross_max_daily", "{:.0%}"),
        fv3_days_over=get(ev, "final_daily/days_over_200", "{:.0f}"),
    )
    for tag in ("1e7", "1e8", "1e9", "5e9"):
        for key, (name, fmt) in shown.items():
            f[f"fv3_{name}_{tag}"] = get(ev, f"v3/{tag}/books/final v3/{key}", fmt)
    dollars = at("final v3", 5e9, "dollars")
    f["fv3_dollars_5bn"] = money(dollars) if dollars is not None else "-"
    others = ("v1", "v2", "v2-pass", "v3")
    f |= wins(ev.get("v3", {}), "final v3", others, "fv3")
    # The deck's comparison: final v3 against the submitted book and the two benchmarks.
    f |= wins(ev.get("v3", {}), "final v3", ("v1", "v2", "v2-pass"), "fd")
    return f | final_exhibits(ev)


# Final v3's own exhibits (final_exhibits.md): its 2016-2020 check, the AI crowd against its book,
# the naive benchmarks, the risk table and what the agents said about it.
def final_exhibits(ev: dict) -> dict:
    name = ev.get("v3", {}).get("final", {}).get("name")
    if not name:
        return {}
    run = f"{name}@1e7"
    check = load(v2.OUT / run / "check" / "stats.json")
    crowd = load(v2.OUT / "crowd_lab.json").get(f"{run} record", {})
    insights = load(v2.OUT / "crowd_insights.json").get(f"book {run}", {})
    exhibits = load(v2.OUT / "final_exhibits" / "report.json")
    desk = load(v2.OUT / "desk_final.json")
    naive = exhibits.get("naive", {})
    risk = exhibits.get("risk_table", {}).get("averages", {})
    stress = load(v2.OUT / "stress.json").get("final v3", {})
    return dict(
        fv3_covid=get(stress, "crises/Covid crash/loss", PCT),
        fv3_junk=get(stress, "crises/Junk rally, momentum crash/loss", PCT),
        fv3_rates=get(stress, "crises/Rate shock/loss", PCT),
        fv3_check_ir=get(check, "information_ratio"),
        fv3_check_beta=get(check, "beta_realized", "{:+.2f}"),
        fv3_sell_50=get(crowd, "sell_off_cost/50bn", PCT),
        fv3_crowd_beta=get(crowd, "crowding_beta/beta"),
        fv3_crowd_t=get(crowd, "crowding_beta/t", ONE),
        fv3_overlap_retail=get(insights, "overlap/retail/longs_in_favourites", "{:.0%}"),
        naive_model_10m=get(naive, "naive_equal_model@1e7/information_ratio"),
        naive_holdings_10m=get(naive, "naive_equal_holdings@1e7/information_ratio"),
        naive_model_1bn=get(naive, "naive_equal_model@1e9/information_ratio"),
        naive_holdings_1bn=get(naive, "naive_equal_holdings@1e9/information_ratio"),
        naive_model_beta=get(naive, "naive_equal_model@1e7/beta_realized", "{:+.2f}"),
        risk_vol=get(risk, "corrected_vol_year", PCT),
        risk_factor_share=get(risk, "factor_share", "{:.0%}"),
        risk_top10=get(risk, "top10_pctr", "{:.0%}"),
        risk_var95=get(risk, "var_95", PCT),
        risk_names=get(risk, "names", "{:.0f}"),
        factor_story=desk.get("factor_story", {}).get("story") or "-",
        fv3_confirmed=get(desk, "advocate/confirmed", INT),
        fv3_asked=get(desk, "advocate/asked", INT),
        fv3_chance=get(desk, "advocate/chance", ONE),
    ) | edge(exhibits)


# Is the edge real (final_exhibits.md): random books, our favourites, large caps, the live view.
def edge(exhibits: dict) -> dict:
    null = exhibits.get("null", {})
    naive = exhibits.get("naive", {})
    large = exhibits.get("large", {})
    small = next((v for k, v in large.items() if "@1e7" in k), {})
    big = next((v for k, v in large.items() if "@1e9" in k), {})
    live = exhibits.get("projection", {}).get("1e7", {})
    beaten = round(null["percentile"] * null["draws"]) if null else None
    return dict(
        null_beaten=f"{beaten:,} of {null['draws']:,}" if null else "-",
        null_mean=get(null, "mean"),
        null_p95=get(null, "p95"),
        null_best=get(null, "best"),
        null_gross_beaten=f"{null['gross_percentile']:.0%}" if null else "-",
        fav_10m=get(naive, "favourites_held@1e7/information_ratio"),
        fav_1bn=get(naive, "favourites_held@1e9/information_ratio"),
        large_10m=get(small, "information_ratio"),
        large_1bn=get(big, "information_ratio"),
        live_low=get(live, "harvey_liu_2015"),
        live_high=get(live, "mclean_pontiff_2016"),
    )


# At how many fund sizes, $10M to $5B, a book beats the others named on each measure.
def wins(scored: dict, book: str, others: tuple, prefix: str) -> dict:
    tags = [
        t for t in ("1e7", "1e8", "5e8", "1e9", "5e9") if book in scored.get(t, {}).get("books", {})
    ]
    measures = dict(
        ir=("information_ratio", max),
        sharpe=("sharpe_ratio", max),
        vol=("volatility_annual", min),
        dd=("max_drawdown_total", max),
        beta=("beta_realized", lambda d, key: min(d, key=lambda b: abs(key(b)))),
    )
    out = {f"{prefix}_sizes": str(len(tags))}
    for name, (key, best) in measures.items():
        won = 0
        for t in tags:
            cards = {b: c for b, c in scored[t]["books"].items() if b in (book, *others)}
            if name == "beta":
                won += best(cards, lambda b: cards[b][key]) == book
            else:
                won += best(cards, key=lambda b: cards[b][key]) == book
        out[f"{prefix}_best_{name}"] = str(won)
    won = 0
    for t in tags:
        dsr = {b: scored[t]["deflated_sharpe"][f"{b} full"] for b in (book, *others)}
        won += max(dsr, key=dsr.get) == book
    out[f"{prefix}_best_dsr"] = str(won)
    return out


# What the agents cost to run, from the timings every llama-server log records, scaled from the
# calls it logged to every decision on file.
def compute(decisions: int) -> dict:
    timing = re.compile(r"(prompt eval|\beval) time =\s+([\d.]+) ms /\s+(\d+) tokens")
    calls, tokens, seconds = 0, 0, 0.0
    for log in H.RUNS.glob("server_*.log"):
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = timing.search(line)
            if m:
                seconds += float(m.group(2)) / 1000
                tokens += int(m.group(3))
                calls += m.group(1) == "prompt eval"
    if not calls:
        return dict(tokens_m="-", gpu_hours="-", kwh="-")
    hours = seconds / calls * decisions / 3600
    return dict(
        tokens_m=f"{tokens / calls * decisions / 1e6:,.0f}",
        gpu_hours=f"{hours:,.0f}",
        kwh=f"{hours * BOARD_WATTS / 1000:,.0f}",
    )


# finals.md: the smallest fund size where v2's information ratio passes v1's, in log capital.
def crossover(books: dict) -> float | None:
    one = {r["capital"]: r["information_ratio"] for r in books.get("v1", {}).get("record", [])}
    two = {r["capital"]: r["information_ratio"] for r in books.get("v2", {}).get("record", [])}
    caps = sorted(set(one) & set(two))
    gaps = [two[c] - one[c] for c in caps]
    for i, (cap, gap) in enumerate(zip(caps, gaps)):
        if gap > 0:
            if i == 0:
                return cap
            lo, hi = np.log10(caps[i - 1]), np.log10(cap)
            return 10 ** (lo + (hi - lo) * -gaps[i - 1] / (gap - gaps[i - 1]))
    return None


def main() -> None:
    f = facts()
    qa = [
        (
            "What is the edge?",
            f"Twelve published signals, ranked monthly and held long-short; information ratio "
            f"{f['ir']} after costs, {f['net']} a year net (2021-2026).",
        ),
        (
            "Is it really market neutral?",
            f"Monthly beta {f['beta']} (standard error {f['beta_se']}). On daily returns, with "
            f"a lead and a lag (Dimson), it is {f['dimson']}: a short tilt we report, not hide.",
        ),
        (
            "Why did 2016-2020 lose?",
            f"A market beta of {f['drag_beta']} in a rising market cost {f['drag']} a month; "
            f"everything else was {f['rest']}. v2's beta work targets exactly this.",
        ),
        (
            "Is the alpha statistically real?",
            f"Alpha t-stat {f['alpha_t']} against the market alone; against the five Fama-French "
            f"factors and momentum {f['nw3']} to {f['nw11']} (Newey-West, 3 to 11 lags) and "
            f"{f['ewc']} (EWC). All below the t > 3 bar. Deflated Sharpe: {f['dsr_v1']} at "
            f"{f['trials']} trials, {f['dsr_v1_eff']} at {f['effective']} effective. To beat cash "
            f"+ 4% after costs we need an IC of {f['ic_star']}; we realized {f['ic_real']} "
            f"(v2 lowers the bar to {f['ic_star_v2']}).",
        ),
        (
            "How many things did you try?",
            f"{f['trials']} trials in all ({f['fits']} fits before submission, the research "
            "runs and every v2 configuration since), all in the trial ledger.",
        ),
        (
            "What do costs eat?",
            f"{f['cost']} a year, {f['cost_share']} of gross: commission, half spread, square-root "
            "impact, borrow and financing. Checked against TAQ: our half spread is "
            f"{f['taq_large']}x the real one for large caps and {f['taq_micro']}x for micro caps.",
        ),
        (
            "How big can it get?",
            f"At $1B, v1's modelled cost is {f['v1_cost_1bn']} a year; v2's is {f['v2_cost_1bn']}.",
        ),
        (
            "What is v2?",
            "v1 with five switchable fixes: costs in the optimizer, slower-decaying signals "
            "weighted up, a better beta, safer shorts and liquidity caps, each judged on its own "
            "pre-registered test.",
        ),
        ("Which v2 fixes worked?", f["verdicts"] or "-"),
        (
            "What is the biggest risk?",
            f"Profitability (loading {f['rmw']}). The likeliest 10% monthly loss is a junk rally: "
            f"profitability {f['rmw_move']}. It explains {f['profit_share']} of our 2023-2026 "
            "losing months.",
        ),
        (
            "How did today's book do in past crises?",
            f"Same-name replay of v1: Covid {f['covid']}, 2009 junk rally {f['junk']}, 2022 "
            f"rate shock {f['rates']}. Final v3: {f.get('fv3_covid', '-')}, "
            f"{f.get('fv3_junk', '-')} and {f.get('fv3_rates', '-')}.",
        ),
        (
            "How fast can you get out?",
            f"At $1B, v1's shorts take {f['cover_v1']} days to cover at 10% of daily volume; "
            f"v2's take {f['cover_v2']}.",
        ),
        (
            "What about a short squeeze?",
            f"January 2021 replayed on today's book: {f['squeeze']}. v2's short rule keeps new "
            "shorts out of tiny, costly-to-borrow and event-driven names.",
        ),
        (
            "What does borrowing cost?",
            f"v2's short rule halves it: {f['borrow']} a year against v1's {f['borrow_v1']}.",
        ),
        (
            "What do the AI agents do?",
            "They research, test, explain and simulate a market. None sets or changes a position.",
        ),
        (
            "How do you know the AI is not remembering the future?",
            "Agents see no names, tickers or dates. Asked the same card again, the crowd gives "
            f"the same picks ({f['rerun']}); with the card's numbers moved, only {f['moved']} of "
            "picks survive, fewer as the move grows: it reads the card, not its memory."
            + (
                f" On filings, memorization difference-in-differences {f['did']}; it picks the "
                f"right company from 5 in {f['reid']} of post-cutoff filings (chance 20%)."
                if f["did"] != "-"
                else ""
            ),
        ),
        (
            "What is the AI Crowd Lab?",
            "30 AI retail investors (6 personas x 5 information sets) and 30 AI copycat funds "
            "pick stocks from anonymous cards every month after the model's training ended.",
        ),
        (
            "What did the AI crowd do?",
            f"It herds: {f['agents']} AI investors vote like {f['voters']} independent ones "
            f"(LSV {f['lsv']}). Its picks correlate {f['shorts_rho']} with short interest.",
        ),
        (
            "Are you exposed to AI crowding?",
            f"Yes, and we measure it: our returns load {f['crowd_beta']} on the AI crowd's "
            f"favourites (t {f['crowd_t']}).",
        ),
        (
            "What if the AI crowd sells?",
            f"A $50B AI crowd selling its favourites over five days would cost today's book "
            f"about {f['sell_50']}.",
        ),
        (
            "What would make you cut risk?",
            "Three warning signs fixed before we looked: daily beta outside +/-0.20 over 126 days "
            "(t > 2), borrow above twice its 2016-20 level, days to liquidate above 5; IR is "
            f"never one. On v1 the beta sign fired in {f['warn_months']} months, and the book "
            f"then made {f['warn_next']} over three months against {f['warn_avg']} on average, so "
            "we show the signs but would not trade on them alone.",
        ),
        (
            "Does your accounting hold up?",
            f"NautilusTrader replays every trade in whole shares; v1's monthly returns match to "
            f"{f['naut_gap']} on average.",
        ),
        (
            "Can your AI critique itself?",
            f"The devil's advocate's critiques are checked by code: {f['confirmed']} of "
            f"{f['asked']} confirmed ({f['chance']} by chance).",
        ),
        (
            "Why not use ML to pick stocks?",
            f"Our ML picker forecast returns (IC {f['scorer_ic']}, t {f['scorer_t']}) but "
            "turnover ate the gain. ML earns its place on risk: beta error "
            f"{f['beta_error']} vs {f['beta_error_60m']} for the 60-month beta. Our volatility "
            f"model was dropped when it broke in 2020 (QLIKE {f['vol_lgbm']} vs HAR "
            f"{f['vol_har']}).",
        ),
        (
            "What did the AI cost to run?",
            f"{f['decisions_total']} decisions on our own GPU, no API: about {f['tokens_m']} "
            f"million tokens and {f['gpu_hours']} GPU hours, at most {f['kwh']} kWh. Every answer "
            "is cached with its prompt hash, so replaying them costs nothing.",
        ),
        (
            "What if the finals rules change?",
            "The rules reader drafts a mandate from the text, every limit quoted (this year's "
            f"rules: {f['rules_2026']} found), a human approves, and one command rebuilds v1's "
            f"method and v2 in {f['drill']} minutes; nothing is retrained. A turnover budget and a "
            "net band are already rules the optimizer holds, and finals_book.py writes the full "
            "committee pack for whichever book we run.",
        ),
        (
            "What is v3, the final book?",
            f"v2-pass plus the rules that passed their own 2016-2020 test, each written down "
            f"before it ran: it {f['v3_rules']}. Failed and dropped: {f['v3_dropped']}. "
            f"Information ratio {f['v3_ir_1e7']} at $10M, {f['v3_ir_1e9']} at $1B and "
            f"{f['v3_ir_5e9']} at $5B; volatility {f['v3_vol_1e7']}, beta {f['v3_beta_1e7']} and "
            f"worst drawdown {f['v3_dd_1e7']} at $10M. Deflated Sharpe {f['dsr_v3']} at "
            f"{f['trials']} trials ({f['dsr_v1']} for v1).",
        ),
        (
            "Is the edge real, or could anyone get this?",
            f"Final v3 beats {f['null_beaten']} random large-cap long-short books with its "
            f"own number of legs, gross and holding time (their average information ratio "
            f"{f['null_mean']}, the luckiest 5% above {f['null_p95']}; final v3 "
            f"{f['fv3_ir_1e7']}). "
            f"Run on the 500 largest stocks only, our rule makes {f['large_10m']}. Equal weights "
            f"on our score make {f['naive_model_10m']}; our favourite names held still, chosen "
            f"with hindsight, {f['fav_10m']}. Deflated Sharpe {f['dsr_fv3']} after "
            f"{f['trials']} trials.",
        ),
        (
            "What do you expect live?",
            f"Less than the backtest. Published edges shrink: by 26% (McLean and Pontiff 2016) "
            f"to 50% (Harvey and Liu 2015). On final v3's {f['fv3_ir_1e7']} that is "
            f"{f['live_low']} to {f['live_high']} at $10M, still above the hurdle.",
        ),
        (
            "Is the final book the best on every measure?",
            "No book can be. Against v1, v2, v2-pass and v3, final v3 has the best information "
            f"ratio at {f['fv3_best_ir']} of {f['fv3_sizes']} fund sizes, the highest Sharpe at "
            f"{f['fv3_best_sharpe']}, the lowest volatility at {f['fv3_best_vol']}, the smallest "
            f"drawdown at {f['fv3_best_dd']}, the beta closest to zero at {f['fv3_best_beta']} and "
            f"the highest deflated Sharpe at {f['fv3_best_dsr']}. v2 trades least and so costs "
            "least; a calmer book wins on volatility by earning less. Beating every book on return "
            "and on calm at once would take a far higher Sharpe than any of them has.",
        ),
        (
            "What is our final strategy?",
            f"Final v3 is v3 plus rules fixed before any run: it {f['fv3_rules']}. Dropped after "
            "failing their 2016-2020 tests: "
            f"{f['fv3_dropped']}. At $10M: information ratio {f['fv3_ir_1e7']}, return "
            f"{f['fv3_net_1e7']} a year above cash, volatility {f['fv3_vol_1e7']}, beta "
            f"{f['fv3_beta_1e7']} (standard error {f['fv3_beta_se']}), worst drawdown "
            f"{f['fv3_dd_1e7']}; information ratio {f['fv3_ir_1e9']} at $1B and {f['fv3_ir_5e9']} "
            f"at $5B. Daily gross never above {f['fv3_gross_max_daily']} (2021-2025). Deflated "
            f"Sharpe {f['dsr_fv3']} after {f['trials']} trials.",
        ),
        (
            "Which book would you present at the finals?",
            "Written down before any run (v2_amendment_3.md): final v3 at every fund size, with "
            "v1, the submitted book, v2, v2-pass and v3 as benchmarks. Never picked by comparing "
            "2021-2026 results."
            if f["dsr_fv3"] != "-"
            else "Written down before any run (v2_amendment_2.md): v3 at every fund size, with "
            "v1, the submitted book, and v2 as benchmarks. Never picked by comparing 2021-2026 "
            "results."
            if f["v3_size"] == "pass"
            else f"Written down before the finals (finals.md): v1 with no stated fund size; with "
            f"one, v1's method below {f['crossover']} and v2 above. Never picked by comparing "
            "results under the new rules.",
        ),
    ]
    lines = ["# Q&A bank (every number regenerated by fiam.report.qa)", ""]
    for i, (question, answer) in enumerate(qa, 1):
        lines += [f"**{i}. {question}**", "", answer, ""]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}: {len(qa)} questions")


if __name__ == "__main__":
    main()
