# The devil's advocate on the final book, each attack answered by code.

from __future__ import annotations

import json

from fiam.agents import desk as D
from fiam.agents import final_book as F
from fiam.vfinal import config as C

SYSTEM = (
    "You are the devil's advocate on an investment committee reviewing a market-neutral US "
    "equity book. Your only job is to find what is wrong with it. You are not asked to be "
    "balanced. Use only the evidence given and quote only numbers printed there; every number "
    "is checked by code and a sentence with any other number is deleted. You may know these "
    "companies; do not bring in anything the evidence does not show. A weak objection is "
    "worse than none. Never advise a trade or a weight."
)
# What an attack may be about; each has an answer written by code.
TOPICS = (
    "hurdle",
    "short_leg",
    "costs",
    "crowding",
    "crowd_sell_off",
    "card_spend",
    "hype",
    "news",
    "reports",
    "concentration",
    "liquidity",
    "market_beta",
    "rules",
)
SEVERITY = ("high", "medium", "low", "none")
PROMPT_NUMBER = 2
TASK = (
    "Attack this final book, as held on 31 August 2026, and its record. Each line of the "
    "READABLE block is one topic and its facts, from the AI crowd, the Carbon Arc card spend "
    "counts, the 8-K news labels and the analyst's reading of the latest reports. For each "
    "topic write the strongest attack a sceptical investment committee would make, in 1 to 3 "
    "plain sentences that quote numbers as the READABLE block prints them, and a severity. "
    "Use severity none, with a short claim saying so, when the facts give no real case. Never "
    "quote field names. Answer in JSON with the key attacks, one item per topic, in the "
    "order given."
)


# The reply's shape: one attack per topic, in the order asked.
def schema(topics: list[str]) -> dict:
    item = dict(
        type="object",
        properties=dict(
            topic=dict(type="string", enum=topics),
            claim=dict(type="string"),
            severity=dict(type="string", enum=list(SEVERITY)),
        ),
        required=["topic", "claim", "severity"],
    )
    return dict(
        type="object",
        properties=dict(
            attacks=dict(type="array", items=item, minItems=len(topics), maxItems=len(topics))
        ),
        required=["attacks"],
    )


# Two decimals, the way every answer prints a number.
def r2(x: float) -> float:
    return round(float(x), 2)


# Money made or lost in millions, never a minus before a dollar.
def money(x: float) -> str:
    return f"{'made' if x >= 0 else 'lost'} ${abs(x)} million"


# The triage labels in aggregate, or None while that agent runs.
def triage_evidence() -> dict | None:
    t = D.load(D.TRIAGE)
    if not t:
        return None
    sides = {
        s: {
            k: v[k] for k in ("names_in_book", "names_with_8k", "filings", "good", "bad", "neutral")
        }
        for s, v in t["by_side"].items()
    }
    return dict(
        filings_labelled=t["filings"]["labelled"],
        passed_format_check=t["filings"]["passed_format_check"],
        by_side=sides,
        non_neutral_filings=t["non_neutral_filings"],
        share_for_our_side_pct=None
        if t["share_for_our_side"] is None
        else r2(t["share_for_our_side"] * 100),
        for_our_side_means="good news on a long or bad news on a short",
    )


# The analyst's balance by side, or None while that agent runs.
def analyst_evidence() -> dict | None:
    a = D.load(D.ANALYST)
    if not a:
        return None
    return dict(
        names_read=a["names_read"],
        answers_passed_checks=a["answers_passed_checks"],
        points_kept=a["points_kept"],
        points_dropped=a["points_dropped"],
        balance_by_side=a["balance_by_side"],
        what="latest 10-Q or 10-K of the 10 largest longs and 10 largest shorts",
    )


# The evidence the attack and the answers both read.
def evidence(n: dict, book: dict) -> dict:
    h, legs = n["headline"], n["legs"]
    crowd_old = D.load(D.CROWD) or {}
    pnl = crowd_old.get("pnl_musd_total", {})
    live = D.load(D.CROWD_LIVE) or {}
    worst = min(n["calendar_years"], key=lambda y: y["after_less_hurdle_pct"])
    rules = D.load(D.RULES) or {}
    return dict(
        fund=dict(
            ending_value_billion=round(h["ending_value_bn"], 3),
            hurdle_ending_value_billion=round(n["paths"]["hurdle_end_bn"], 3),
            shortfall_million=round((n["paths"]["hurdle_end_bn"] - h["ending_value_bn"]) * 1000, 1),
            information_ratio=r2(h["ir_after_costs"]),
            information_ratio_standard_error=r2(h["ir_after_costs_se"]),
            information_ratio_before_costs=r2(h["ir_before_costs"]),
            information_ratio_flat_costs=r2(n["flat_costs"]["ir"]),
            sharpe=r2(h["sharpe_pdf_bill"]),
            long_leg_million=round(legs["long"]["pnl_musd"], 1),
            short_leg_million=round(legs["short"]["pnl_musd"], 1),
            shorted_stocks_rise_pct=round(
                legs["short"]["stocks_return_per_dollar_cumulative_pct"], 1
            ),
            interest_million=round(h["interest_musd"], 1),
            trading_costs_million=round(h["trading_cost_musd"], 1),
            borrow_million=round(h["borrow_musd"], 1),
            costs_share_of_shortfall_pct=round(
                (h["trading_cost_musd"] + h["borrow_musd"])
                / ((n["paths"]["hurdle_end_bn"] - h["ending_value_bn"]) * 1000)
                * 100
            ),
            worst_year=worst["year"],
            worst_year_fund_pct=r2(worst["fund_after_costs_pct"]),
            worst_year_hurdle_pct=r2(worst["hurdle_pct"]),
            beta_monthly=round(h["beta_monthly"], 3),
            worst_month_pct=r2(h["max_one_month_loss_pct"]),
            max_drawdown_pct=r2(h["max_drawdown_pct"]),
            limit_breach_days=int(h["breaches"]),
        ),
        book=dict(
            date=book["date"],
            names=book["names"],
            longs=book["longs"],
            shorts=book["shorts"],
            gross_pct=r2(book["gross_pct"]),
            gross_limit_pct=round(C.HARD["gross"] * 100),
            net_pct=r2(book["net_pct"]),
            largest_long_pct=r2(book["largest_long"]["weight_pct"]),
            largest_short_pct=r2(book["largest_short"]["weight_pct"]),
            top10_long_share_pct=round(book["top10_long_share_of_long_gross"] * 100, 1),
            largest_sector_net_pct=r2(book["sector_net_max"]["net_pct"]),
            beta_of_weights=round(book["history"]["beta"], 3),
            volatility_63_day_pct=r2(book["history"]["realised_vol_63d_pct"]),
            sessions_to_exit_max=r2(book["liquidity"]["sessions_to_exit_max"]),
            sessions_limit=book["liquidity"]["sessions_limit"],
        ),
        ai_crowd=dict(
            long_percentile_2026_08=book["crowd"]["long_percentile"],
            short_percentile_2026_08=book["crowd"]["short_percentile"],
            long_percentile_average=live.get("round", {}).get("avg_long_pct"),
            short_percentile_average=live.get("round", {}).get("avg_short_pct"),
            average_from=live.get("spliced_retail", {}).get("first"),
            average_to=live.get("spliced_retail", {}).get("last"),
            crowd_factor_beta=r2(book["crowd"]["crowd_beta"]),
            crowd_factor_t=r2(book["crowd"]["crowd_beta_t"]),
            sell_off_worst_pct_of_capital=r2(book["crowd"]["sell_off_worst_pct_nav"]),
            sell_off_worst_case=book["crowd"]["sell_off_worst_case"],
            pnl_where_book_agreed_with_crowd_million=round(pnl.get("agree", 0.0), 1),
            pnl_where_book_disagreed_million=round(pnl.get("disagree", 0.0), 1),
        ),
        carbon_arc_counts={
            k: (r2(v) if isinstance(v, float) else v)
            for k, v in book["carbon_arc"].items()
            if k != "source"
        },
        news_8k=triage_evidence() or "not ready",
        analyst_reports=analyst_evidence() or "not ready",
        rules=dict(
            rules_read=rules.get("rules_read"),
            matched=rules.get("matched"),
            mismatch_reason="the reader filed the net band as a fixed net; the band matched",
        ),
    )


# Each topic with data, its facts as plain sentences for the attack.
def readable(ev: dict) -> dict[str, str]:
    f, b, c, ca = ev["fund"], ev["book"], ev["ai_crowd"], ev["carbon_arc_counts"]
    lines = dict(
        hurdle=f"The record ended at ${f['ending_value_billion']} billion against the hurdle's "
        f"${f['hurdle_ending_value_billion']} billion, ${f['shortfall_million']} million short. "
        f"The information ratio is {f['information_ratio']} with a standard error of "
        f"{f['information_ratio_standard_error']}, and {f['information_ratio_before_costs']:.2f} "
        f"before trading costs and borrow. Those costs are {f['costs_share_of_shortfall_pct']}% "
        f"of the gap. Sharpe ratio {f['sharpe']}.",
        short_leg=f"The short leg lost ${abs(f['short_leg_million'])} million and the long leg "
        f"made ${f['long_leg_million']} million. The stocks we shorted rose "
        f"{f['shorted_stocks_rise_pct']}% over the record. In {f['worst_year']}, the worst year "
        f"against the hurdle, the fund made {f['worst_year_fund_pct']}% against "
        f"{f['worst_year_hurdle_pct']}%.",
        costs=f"Trading costs were ${f['trading_costs_million']} million and borrow "
        f"${f['borrow_million']} million. On the competition's flat conservative costs the "
        f"information ratio is {f['information_ratio_flat_costs']}.",
        crowding=f"On {b['date']} our longs sit at the AI crowd's "
        f"{D.nth(c['long_percentile_2026_08'])} percentile and our shorts at the "
        f"{D.nth(c['short_percentile_2026_08'])}. From {c['average_from']} to "
        f"{c['average_to']} the averages are the "
        f"{D.nth(c['long_percentile_average'])} and {D.nth(c['short_percentile_average'])}. "
        f"The fund's return loads {c['crowd_factor_beta']} on the crowd factor, t "
        f"{c['crowd_factor_t']}. Over the record the book "
        f"{money(c['pnl_where_book_agreed_with_crowd_million'])} where it agreed with the "
        f"crowd and {money(c['pnl_where_book_disagreed_million'])} where it disagreed.",
        crowd_sell_off=f"In the worst crowd sell-off test ({c['sell_off_worst_case']} of its "
        f"favourites) the book would lose "
        f"{abs(c['sell_off_worst_pct_of_capital'])}% of capital. The record's worst month "
        f"lost {abs(f['worst_month_pct'])}%.",
        card_spend=f"Carbon Arc card spend covers {ca['longs_with_growth']} of {b['longs']} longs "
        f"and {ca['shorts_with_growth']} of {b['shorts']} shorts. Spend of those longs grew "
        f"{ca['long_spend_growth_pct']}% and of those shorts {ca['short_spend_growth_pct']}%, "
        f"p {ca['split_p_value']}. Carbon Arc is never an input to the fund.",
        hype=f"{ca['longs_in_hype']} longs sit in Hype, in the AI crowd's top half while card "
        f"spend falls, {ca['longs_in_hype_strong']} of them by 10% or more. "
        f"{ca['shorts_in_hidden_gems']} shorts sit in Hidden gems, in its bottom half while "
        "spend grows, "
        f"{ca['shorts_in_hidden_gems_strong']} of them by 10% or more. "
        f"{ca['crowd_favourites_in_hype']} of {ca['crowd_favourites_with_growth']} crowd "
        "favourites with data sit in Hype.",
        concentration=f"The book holds {b['names']} names, {b['longs']} long and {b['shorts']} "
        f"short. The largest long is {b['largest_long_pct']}% of capital and the largest short "
        f"{abs(b['largest_short_pct'])}%. The ten largest longs are "
        f"{b['top10_long_share_pct']}% of the long side. The largest sector net is "
        f"{b['largest_sector_net_pct']}%.",
        liquidity=f"At 10% of daily volume the slowest name takes {b['sessions_to_exit_max']} "
        f"sessions to exit. The fund's limit is {b['sessions_limit']} sessions.",
        market_beta=f"The record's monthly beta to the S&P 500 is {f['beta_monthly']}. Today's "
        f"weights carry {b['beta_of_weights']} over the last year. Gross exposure is "
        f"{b['gross_pct']}% and net {b['net_pct']}%.",
    )
    t = ev["news_8k"]
    if isinstance(t, dict) and t["share_for_our_side_pct"] is not None:
        sides = t["by_side"]
        lines["news"] = (
            f"{t['filings_labelled']} 8-Ks filed by the book's names from June to the book's "
            f"date were labelled. "
            + " ".join(
                f"On the {k} side {v['good']} were good news, {v['bad']} bad and {v['neutral']} "
                "neutral."
                for k, v in sides.items()
            )
            + f" Of the {t['non_neutral_filings']} that were not neutral, "
            f"{t['share_for_our_side_pct']}% were news for our side."
        )
    a = ev["analyst_reports"]
    if isinstance(a, dict):
        bal = a["balance_by_side"]
        lines["reports"] = " ".join(
            f"Of the 10 largest {k}s the latest report supports our side for "
            f"{v['supports']}, is mixed on {v['mixed']} and challenges {v['challenges']}."
            for k, v in bal.items()
        )
    return {k: D.plain(v) for k, v in lines.items()}


# The answer to one topic from the evidence alone, with a verdict.
def answer(topic: str, ev: dict) -> tuple[str, str]:
    f, b, c, ca = ev["fund"], ev["book"], ev["ai_crowd"], ev["carbon_arc_counts"]
    if topic == "hurdle":
        return (
            f"The record ends at ${f['ending_value_billion']} billion against the hurdle's "
            f"${f['hurdle_ending_value_billion']} billion, an information ratio of "
            f"{f['information_ratio']} with a standard error of "
            f"{f['information_ratio_standard_error']}. Before trading costs and borrow the "
            f"ratio is {f['information_ratio_before_costs']:.2f}, and those costs are "
            f"{f['costs_share_of_shortfall_pct']}% of the ${f['shortfall_million']} million gap.",
            "stands",
        )
    if topic == "short_leg":
        return (
            f"The short leg lost ${abs(f['short_leg_million'])} million while the long leg made "
            f"${f['long_leg_million']} million, and the stocks we shorted rose "
            f"{f['shorted_stocks_rise_pct']}% over the record.",
            "stands",
        )
    if topic == "costs":
        return (
            f"Trading costs were ${f['trading_costs_million']} million and borrow "
            f"${f['borrow_million']} million. On the flat conservative costs the information "
            f"ratio is {f['information_ratio_flat_costs']} instead of {f['information_ratio']}.",
            "partly stands",
        )
    if topic == "crowding":
        real = c["crowd_factor_t"] > 2
        return (
            f"On {b['date']} our longs sat at the AI crowd's {D.nth(c['long_percentile_2026_08'])} "
            f"percentile and our shorts at the {D.nth(c['short_percentile_2026_08'])}. The fund's "
            f"return loads {c['crowd_factor_beta']} on the crowd factor (t "
            f"{c['crowd_factor_t']}). Over the record, where the book agreed with the crowd it "
            f"{money(c['pnl_where_book_agreed_with_crowd_million'])} and where it disagreed it "
            f"{money(c['pnl_where_book_disagreed_million'])}.",
            "partly stands" if real else "does not stand",
        )
    if topic == "crowd_sell_off":
        loss, month = abs(c["sell_off_worst_pct_of_capital"]), abs(f["worst_month_pct"])
        return (
            f"In the worst crowd sell-off test ({c['sell_off_worst_case']}) the final book loses "
            f"{loss}% of capital, against the record's worst month of minus {month}%.",
            "does not stand" if loss < month / 2 else "partly stands",
        )
    if topic == "card_spend":
        return (
            f"Card spend data covers {ca['longs_with_growth']} of {b['longs']} longs and "
            f"{ca['shorts_with_growth']} of {b['shorts']} shorts. "
            f"Card spend of the {ca['longs_with_growth']} longs with data grew "
            f"{ca['long_spend_growth_pct']}% and of the {ca['shorts_with_growth']} shorts "
            f"{ca['short_spend_growth_pct']}% (p {ca['split_p_value']}), so real spend does not "
            "separate our sides. It neither confirms nor refutes the book, and Carbon Arc is "
            "never a fund input.",
            "stands",
        )
    if topic == "hype":
        return (
            f"{ca['longs_in_hype']} longs sit in Hype and {ca['shorts_in_hidden_gems']} shorts in "
            f"Hidden gems on card spend. {ca['crowd_favourites_in_hype']} of the "
            f"{ca['crowd_favourites_with_growth']} AI crowd favourites with data sit in Hype.",
            "partly stands",
        )
    if topic == "news":
        t = ev["news_8k"]
        if not isinstance(t, dict) or t["share_for_our_side_pct"] is None:
            return "The 8-K labels are not ready, so the data cannot answer this yet.", "no data"
        share = t["share_for_our_side_pct"]
        return (
            f"{t['filings_labelled']} 8-Ks filed by the book's names were labelled. Of the "
            f"{t['non_neutral_filings']} that were not neutral, {share}% were news for our side, "
            "good news on a long or bad news on a short.",
            "stands" if share < 50 else "does not stand",
        )
    if topic == "reports":
        a = ev["analyst_reports"]
        if not isinstance(a, dict):
            return (
                "The analyst's reading is not ready, so the data cannot answer this yet.",
                "no data",
            )
        bal = a["balance_by_side"]
        sup = sum(bal[s]["supports"] for s in bal)
        cha = sum(bal[s]["challenges"] for s in bal)
        text = " ".join(
            f"Of the {s}s read, the latest report supports {bal[s]['supports']}, is mixed on "
            f"{bal[s]['mixed']} and challenges {bal[s]['challenges']}."
            for s in ("long", "short")
            if s in bal
        )
        thin = any(bal[s]["supports"] * 2 < sum(bal[s].values()) for s in bal)
        verdict = (
            "stands" if cha > sup else "partly stands" if cha == sup or thin else "does not stand"
        )
        return text, verdict
    if topic == "concentration":
        ok = b["largest_long_pct"] < 5 and b["top10_long_share_pct"] < 50
        return (
            f"The book holds {b['names']} names. The largest long is {b['largest_long_pct']}% "
            f"and the largest short {abs(b['largest_short_pct'])}% of capital, under the 5% "
            f"cap, and the ten largest longs are {b['top10_long_share_pct']}% of the long side.",
            "does not stand" if ok else "partly stands",
        )
    if topic == "liquidity":
        return (
            f"At 10% of daily volume the slowest name exits in {b['sessions_to_exit_max']} "
            f"sessions, inside the fund's {b['sessions_limit']}.",
            "does not stand" if b["sessions_to_exit_max"] < b["sessions_limit"] else "stands",
        )
    if topic == "market_beta":
        return (
            f"The record's monthly beta to the S&P 500 is {f['beta_monthly']} and today's "
            f"weights carry {b['beta_of_weights']} over the last year. Gross exposure is "
            f"{b['gross_pct']}% against the finals limit of {b['gross_limit_pct']}%, with net "
            f"{b['net_pct']}%.",
            "does not stand" if abs(b["beta_of_weights"]) < 0.1 else "stands",
        )
    if topic == "rules":
        r = ev["rules"]
        return (
            f"The rules reader matched {r['matched']} of {r['rules_read']} rules it read from "
            f"the finals PDFs, the other {r['rules_read'] - r['matched']} being the net band "
            f"filed as a fixed net, and the record has {f['limit_breach_days']} breach days.",
            "does not stand",
        )
    return "No evidence speaks to this attack.", "no data"


# Topics in words, joined with commas and a last "and".
def listed(topics: list[str]) -> str:
    words = [t.replace("_", " ") for t in topics] or ["no topic"]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


# The attacks and answers as markdown, model words beside code words.
def markdown(out: dict) -> str:
    lines = ["# Devil's advocate on the final book, 31 August 2026", ""]
    for i, a in enumerate(out["attacks"], 1):
        lines += [
            f"## {i}. {a['topic'].replace('_', ' ')} ({a['severity']})",
            "",
            f"**Attack** {a['claim'] or '(every sentence was dropped by the checks)'}",
            "",
            f"**Answer from the data** {a['answer']}",
            "",
            f"**Verdict** {a['verdict']}",
            "",
        ]
    c = out["check"]
    lines += [
        f"{out['model']} wrote the attacks. Code wrote every answer and verdict from the "
        f"evidence, and dropped {c['sentences_dropped']} attack "
        f"{'sentence' if c['sentences_dropped'] == 1 else 'sentences'} whose numbers did "
        "not trace or that gave advice. The model saw no case on "
        f"{D.plain(listed(out['not_attacked']))}. "
        "No AI sets a weight.",
    ]
    return "\n".join(lines)


# Writes critic_final.json and critic_final.md from one checked call.
def run() -> dict:
    n = D.load(D.NUMBERS)
    risk = D.load(D.DESK / "risk_note.json")
    if risk is None:
        from fiam.agents import risk_desk

        risk = dict(facts=risk_desk.book_facts())
    ev = evidence(n, risk["facts"])
    source = json.dumps(ev, indent=1, default=str)
    lines = readable(ev)
    words = "\n".join(f"{k}: {v}" for k, v in lines.items())
    values = D.shown(source + "\n" + words)
    topics = list(lines)
    user = TASK + "\n\nREADABLE\n" + words + "\n\nEVIDENCE\n" + source
    with F.Asker(D.LOG, SYSTEM, schema(topics)) as asker:
        first = asker.ask(f"devil_2026-08-31_p{PROMPT_NUMBER}", user)
        account = asker.accounting([first], 0)
    attacks, dropped, no_case, seen = [], [], [], set()
    for a in (first["parsed"] or {}).get("attacks", []):
        topic = a.get("topic", "")
        if topic in seen or a.get("severity") == "none":
            no_case.append(dict(topic=topic, text=a.get("claim", "")))
            continue
        seen.add(topic)
        kept, lost = D.check(a.get("claim", ""), values, advice=True)
        dropped += [dict(topic=topic, **d) for d in lost]
        if not kept:
            continue
        text, verdict = answer(topic, ev)
        attacks.append(
            dict(
                topic=topic,
                severity=a.get("severity"),
                claim=kept,
                facts_shown=lines[topic],
                answer=D.plain(text),
                verdict=verdict,
            )
        )
    attacks.sort(key=lambda a: SEVERITY.index(a["severity"]))
    verdicts = {}
    for a in attacks:
        verdicts[a["verdict"]] = verdicts.get(a["verdict"], 0) + 1
    out = dict(
        what="The devil's advocate on the final book. A local model wrote the attacks from the "
        "evidence below. Code checked every number in them and wrote every answer and verdict "
        "from the same evidence. Carbon Arc appears as counts only. No agent sets a weight.",
        as_of=F.AS_OF,
        model=f"Gemma 4 26B ({account['model_file']})",
        settings=dict(temperature=account["temperature"], seed=account["seed"]),
        calls_log=D.rel(D.LOG),
        call=dict(key=first["key"], error=first["error"], seconds=first["seconds"]),
        prompt_number=PROMPT_NUMBER,
        earlier_prompts_note="prompt 1 gave the evidence as JSON only and let the model pick "
        "5 to 8 topics; it quoted field names and put attacks under the wrong topics, so the "
        "code answers did not match. It stays in the log, unused",
        topics_asked=topics,
        verdict_rules="stands, partly stands or does not stand, set in fiam/agents/devil.py",
        attacks=attacks,
        verdicts=verdicts,
        triage_ready=isinstance(ev["news_8k"], dict),
        analyst_ready=isinstance(ev["analyst_reports"], dict),
        check=dict(sentences_dropped=len(dropped), dropped=dropped),
        not_attacked=[t for t in topics if t not in seen],
        no_case_or_repeat=no_case,
        evidence=ev,
    )
    D.write_json(D.DESK / "critic_final.json", out)
    D.write_text(D.DESK / "critic_final.md", markdown(out))
    print(f"devil: {len(attacks)} attacks, verdicts {verdicts}", flush=True)
    return out
