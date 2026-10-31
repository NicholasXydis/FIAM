# The memo writer: the fund's August 2026 letter from its numbers.

from __future__ import annotations

import json
import re

from fiam.agents import desk as D
from fiam.agents import final_book as F

SYSTEM = (
    "You write the monthly letter of a market-neutral US equity fund to its investors. Plain "
    "words, short sentences, no jargon a trustee would not know. You are honest first. When "
    "the fund fell short you say so in the first sentence, and you never dress a shortfall up "
    "as a success. Use only the facts given. Every number you write is checked by code against "
    "the facts, and a sentence with any number not printed there is deleted. Never quote field "
    "names. Never give advice on trades or weights."
)
SCHEMA = dict(
    type="object",
    properties=dict(
        performance=dict(type="string"),
        drivers=dict(type="string"),
        risk=dict(type="string"),
        watch=dict(type="string"),
        closing=dict(type="string"),
    ),
    required=["performance", "drivers", "risk", "watch", "closing"],
)
SECTIONS = (
    ("performance", "Performance against the hurdle"),
    ("drivers", "What drove it"),
    ("risk", "Risk"),
    ("watch", "What we watch"),
    ("closing", "In short"),
)
TASK = (
    "Write the fund's investor letter for August 2026, about one page in total, to people who "
    "are not quants. It reviews the fund's simulated record from January 2021 to August 2026 "
    "on a start of $1 billion. Five parts, each 2 to 4 sentences, in the first person plural. "
    "performance, open with whether we beat the hurdle, then the ending value against it, the "
    "information ratio and its standard error with what that means in plain words, and the "
    "year to date. drivers, where the money came from and where it went, the long and short "
    "legs, interest, trading costs and borrow, and the best and worst years against the "
    "hurdle. risk, how calm the record was, the worst drawdown and month, how little it moved "
    "with the S&P 500 and the limits kept. watch, two or three things we are watching, each "
    "tied to a number in the facts. closing, one or two sentences that end honestly. Call the "
    "record a simulation or the record, and write only about this fund and its record. "
    "Quote numbers as the READABLE block prints them, never with more "
    "decimals. Answer in JSON with the keys performance, drivers, risk, watch and closing."
)
PROMPT_NUMBER = 2


# Rounds every float in a nested value for a readable facts table.
def rounded(value, places: int = 2):
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, dict):
        return {k: rounded(v, places) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v, places) for v in value]
    return value


# The letter's facts: numbers.json and plain sums of its own numbers.
def facts(n: dict) -> dict:
    h, legs, paths = n["headline"], n["legs"], n["paths"]
    years = n["calendar_years"]
    ytd = next(y for y in years if y["year"] == 2026)
    costs = h["trading_cost_musd"] + h["borrow_musd"]
    gap = (paths["hurdle_end_bn"] - paths["fund_end_bn"]) * 1000
    return rounded(
        dict(
            period="January 2021 to August 2026, 68 months, simulated, start $1 billion",
            ending_value_billion=h["ending_value_bn"],
            hurdle_ending_value_billion=paths["hurdle_end_bn"],
            hurdle_definition="3-month T-bill plus 4% a year, as the competition sets it",
            shortfall_to_hurdle_million=gap,
            hurdle_cumulative_return_pct=(paths["hurdle_end_bn"] - 1) * 100,
            cumulative_return_pct=h["cumulative_return_pct"],
            compound_annual_return_pct=h["cagr_pct"],
            information_ratio_after_costs=h["ir_after_costs"],
            information_ratio_standard_error=h["ir_after_costs_se"],
            information_ratio_before_costs=h["ir_before_costs"],
            sharpe_ratio=h["sharpe_pdf_bill"],
            alpha_vs_sp500_pct_a_year=h["alpha_pct"],
            alpha_standard_error_pct=h["alpha_se_pct"],
            year_to_date_2026_through_august=dict(
                fund_pct=ytd["fund_after_costs_pct"],
                hurdle_pct=ytd["hurdle_pct"],
                fund_less_hurdle_pts=ytd["after_less_hurdle_pct"],
            ),
            calendar_years=[
                dict(
                    year=y["year"],
                    fund_pct=y["fund_after_costs_pct"],
                    hurdle_pct=y["hurdle_pct"],
                    sp500_pct=y["sp500_pct"],
                    fund_less_hurdle_pts=y["after_less_hurdle_pct"],
                )
                for y in years
            ],
            money_million=dict(
                long_leg=legs["long"]["pnl_musd"],
                short_leg=legs["short"]["pnl_musd"],
                stocks_before_costs=h["stock_pnl_musd"],
                interest=h["interest_musd"],
                trading_costs=h["trading_cost_musd"],
                borrow=h["borrow_musd"],
                trading_costs_and_borrow=costs,
            ),
            shorted_stocks_cumulative_rise_pct=legs["short"][
                "stocks_return_per_dollar_cumulative_pct"
            ],
            months_up_pct=n["hit_rate"]["monthly_hit_rate_pct"],
            months_beating_hurdle=n["hit_rate"]["months_beating_hurdle"],
            months=n["hit_rate"]["months"],
            volatility_pct_a_year=h["vol_monthly_pct"],
            volatility_63_day_highest_pct=n["volatility"]["rolling63_max_pct"],
            volatility_63_day_highest_date=n["volatility"]["rolling63_max_date"],
            volatility_ceiling_pct=n["volatility"]["ceiling_pct"],
            max_drawdown_pct=h["max_drawdown_pct"],
            max_drawdown_date=paths["max_dd_date"],
            worst_month_pct=h["max_one_month_loss_pct"],
            beta_to_sp500_monthly=h["beta_monthly"],
            correlation_with_sp500_monthly=n["sp500_context"]["correlation_monthly_with_fund"],
            sp500_ending_value_billion=n["sp500_context"]["ending_bn_from_1bn"],
            names_held_min=h["names_min"],
            names_held_max=h["names_max"],
            gross_exposure_average_pct=h["gross_avg_pct"],
            limit_breaches=h["breaches"],
            rebalances=h["rebalances"],
        ),
        4,
    )


# Money in millions as made or lost, never a minus before a dollar.
def money(x: float, made: str = "made", lost: str = "lost") -> str:
    return f"{made if x >= 0 else lost} ${abs(x):.1f} million"


# The facts as short sentences a reader can quote without decoding.
def readable(f: dict) -> str:
    m, ytd = f["money_million"], f["year_to_date_2026_through_august"]
    years = "; ".join(
        f"{y['year']} fund {y['fund_pct']:.2f}% against hurdle {y['hurdle_pct']:.2f}% "
        f"({y['fund_less_hurdle_pts']:+.2f} points)"
        for y in f["calendar_years"]
    )
    return "\n".join(
        [
            f"The record runs {f['period']}.",
            f"It ended at ${f['ending_value_billion']:.3f} billion. The hurdle "
            f"({f['hurdle_definition']}) ended at ${f['hurdle_ending_value_billion']:.3f} "
            f"billion. We are ${f['shortfall_to_hurdle_million']:.1f} million short of it.",
            f"Cumulative return {f['cumulative_return_pct']:.1f}% against the hurdle's "
            f"{f['hurdle_cumulative_return_pct']:.1f}%. Compound annual return "
            f"{f['compound_annual_return_pct']:.2f}%.",
            f"Information ratio after costs {f['information_ratio_after_costs']:.2f}, standard "
            f"error {f['information_ratio_standard_error']:.2f}. Before trading costs and "
            f"borrow it is {f['information_ratio_before_costs']:.2f}. Sharpe ratio "
            f"{f['sharpe_ratio']:.2f}. Alpha against the S&P 500 "
            f"{f['alpha_vs_sp500_pct_a_year']:.2f}% a year, standard error "
            f"{f['alpha_standard_error_pct']:.2f}.",
            f"2026 to the end of August: fund {ytd['fund_pct']:.2f}%, hurdle "
            f"{ytd['hurdle_pct']:.2f}%, {abs(ytd['fund_less_hurdle_pts']):.2f} points behind.",
            f"By calendar year: {years}.",
            f"The long leg {money(m['long_leg'])}. The short leg {money(m['short_leg'])}, as "
            f"the stocks we shorted rose {f['shorted_stocks_cumulative_rise_pct']:.1f}%. "
            f"Stocks before costs {money(m['stocks_before_costs'])}. Interest "
            f"{money(m['interest'], 'earned', 'cost')}. Trading costs ${m['trading_costs']:.1f} "
            f"million and borrow ${m['borrow']:.1f} million, together "
            f"${m['trading_costs_and_borrow']:.1f} million.",
            f"{f['months_up_pct']:.0f}% of months were up and {f['months_beating_hurdle']} of "
            f"{f['months']} months beat the hurdle.",
            f"Volatility {f['volatility_pct_a_year']:.2f}% a year. The 63-day volatility "
            f"peaked at {f['volatility_63_day_highest_pct']:.2f}% on "
            f"{f['volatility_63_day_highest_date']}, against a ceiling of "
            f"{f['volatility_ceiling_pct']}%. Largest drawdown {f['max_drawdown_pct']:.2f}% on "
            f"{f['max_drawdown_date']}. Worst month {f['worst_month_pct']:.2f}%.",
            f"Monthly beta to the S&P 500 {f['beta_to_sp500_monthly']:.3f}, correlation "
            f"{f['correlation_with_sp500_monthly']:.2f}. $1 billion in the S&P 500 grew to "
            f"${f['sp500_ending_value_billion']:.3f} billion over the same months.",
            f"{f['names_held_min']:.0f} to {f['names_held_max']:.0f} names held, average gross "
            f"exposure {f['gross_exposure_average_pct']:.1f}%, {f['limit_breaches']:.0f} limit "
            f"breaches over {f['rebalances']:.0f} rebalances.",
        ]
    )


# Each sentence's word-triplet overlap with the explainer's answers.
def overlap(text: str, others: list[str]) -> float:
    # A text's lowercase word triplets.
    def grams(t: str) -> set:
        words = re.findall(r"[a-z0-9$%]+(?:\.\d+)?", t.lower())
        return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}

    pool = set().union(*(grams(o) for o in others)) if others else set()
    best = 0.0
    for s in D.sentences(text):
        g = grams(s)
        if g:
            best = max(best, len(g & pool) / len(g))
    return round(best, 3)


# The explainer's answers, to prove the letter says something else.
def explainer_texts() -> list[str]:
    ex = D.load(D.EXPLAINER) or {}
    return [p.get("explanation", "") for p in ex.get("positions", []) if isinstance(p, dict)]


# The letter as markdown: sections, then how code checked it.
def markdown(out: dict) -> str:
    lines = ["# QUARCC Purple investor letter, August 2026", ""]
    for key, title in SECTIONS:
        lines += [f"## {title}", "", out["letter"][key] or "(every sentence was dropped)", ""]
    c = out["check"]
    lines += [
        "---",
        "",
        f"Written by {out['model']} on the team's machine from the fund's numbers. Code "
        f"checked {c['numbers_checked']} numbers against numbers.json and dropped "
        f"{c['sentences_dropped']} {'sentence' if c['sentences_dropped'] == 1 else 'sentences'}. "
        "No AI sets a weight.",
    ]
    return "\n".join(lines)


# Writes letter.json and letter.md from one checked model answer.
def run() -> dict:
    n = D.load(D.NUMBERS)
    table = facts(n)
    source = json.dumps(table, indent=1)
    words = readable(table)
    values = D.shown(source + "\n" + words)
    user = TASK + "\n\nREADABLE\n" + words + "\n\nFACTS\n" + source
    with F.Asker(D.LOG, SYSTEM, SCHEMA) as asker:
        got = D.ask_checked(
            asker, f"memo_letter_2026-08_p{PROMPT_NUMBER}", user, [k for k, _ in SECTIONS], values
        )
        account = asker.accounting([], 0)
    letter, dropped = {}, []
    for key, _ in SECTIONS:
        kept, lost = D.check(str(got["answer"].get(key, "")), values, advice=True)
        letter[key] = kept
        dropped += [dict(section=key, **d) for d in lost]
    text = " ".join(letter.values())
    out = dict(
        what="The memo writer's August 2026 investor letter. A local model wrote it from "
        "numbers.json alone. Code kept a sentence only if every number in it is printed in the "
        "facts, rounded at most, and it breaks no honesty or advice rule. It sets no weight.",
        as_of="2026-08-31",
        model=f"Gemma 4 26B ({account['model_file']})",
        settings=dict(temperature=account["temperature"], seed=account["seed"]),
        source=D.rel(D.NUMBERS),
        calls_log=D.rel(D.LOG),
        calls=got["calls"],
        prompt_number=PROMPT_NUMBER,
        earlier_prompts_note="the first prompt gave the facts as JSON only and its answer "
        "quoted raw decimals and left out the information ratio; it stays in the log, unused",
        letter=letter,
        words=len(text.split()),
        check=dict(
            numbers_checked=len(D.numbers(text))
            + sum(len(d["unsupported_numbers"]) for d in dropped),
            numbers_kept=len(D.numbers(text)),
            sentences_kept=len(D.sentences(text)),
            sentences_dropped=len(dropped),
            dropped=dropped,
            overlap_with_explainer=overlap(text, explainer_texts()),
            overlap_means="largest share of one letter sentence's word triplets found in "
            "any explainer answer; 0 means no shared triplet",
        ),
        facts=table,
    )
    D.write_json(D.DESK / "letter.json", out)
    D.write_text(D.DESK / "letter.md", markdown(out))
    print(f"letter: {out['words']} words, {len(dropped)} sentences dropped", flush=True)
    return out
