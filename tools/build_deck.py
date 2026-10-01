# The deck the brief asks for, from the exhibits RESULTS.md reads: uv run tools/build_deck.py

import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
# The repo root goes on the path, so fiam imports from wherever this is run.
sys.path.insert(0, str(ROOT))
OUT = ROOT / "deck" / "FIAM.pptx"
FIGURES = ROOT / "submission" / "figures"
INK, MUTED, ACCENT = (
    RGBColor(0x1F, 0x29, 0x37),
    RGBColor(0x6B, 0x72, 0x80),
    RGBColor(0x1D, 0x4E, 0xD8),
)
WIDE, TALL = Inches(13.333), Inches(7.5)


# A markdown cell as plain text: no bold, no code marks, no italic underscores around it.
def plain(cell: str) -> str:
    cell = re.sub(r"\*\*|`", "", cell).strip()
    return cell[1:-1] if len(cell) > 1 and cell[0] == cell[-1] == "_" else cell


# A markdown table from the docs as rows of plain cells, and the note printed under it.
def parse(markdown: str) -> tuple[list[list[str]], str]:
    rows, note = [], []
    for line in markdown.strip().splitlines():
        if line.startswith("|") and not set(line) <= set("|-: "):
            rows.append([plain(c) for c in line.strip("|").split("|")])
        elif not line.startswith("|") and line.strip():
            note.append(plain(line))
    return rows, " ".join(note)


# A slide with a title and, when given, a one-line takeaway under it.
def slide(deck, title: str, takeaway: str = ""):
    page = deck.slides.add_slide(deck.slide_layouts[6])
    text(page, [title], Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7), 26, INK, bold=True)
    if takeaway:
        text(page, [takeaway], Inches(0.5), Inches(0.95), Inches(12.3), Inches(0.5), 14, ACCENT)
    return page


# Lines of text in a box, the first one bold when asked.
def text(page, lines, left, top, width, height, size=13, color=INK, bold=False):
    frame = page.shapes.add_textbox(left, top, width, height).text_frame
    frame.word_wrap = True
    for i, line in enumerate(lines):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.text = line
        para.font.size, para.font.color.rgb, para.font.bold = Pt(size), color, bold
        para.space_after = Pt(4)


# A docs table drawn on the slide, its note in small type underneath; returns where it ends.
def table(page, markdown: str, left, top, width, size=10):
    rows, note = parse(markdown)
    if not rows:
        text(page, [note or "Not built yet."], left, top, width, Inches(0.6), 11, MUTED)
        return top + Inches(0.7)
    shape = page.shapes.add_table(
        len(rows), len(rows[0]), left, top, width, Inches(0.28) * len(rows)
    )
    for r, row in enumerate(rows):
        for c, cell in enumerate(row[: len(rows[0])]):
            box = shape.table.cell(r, c)
            box.text = cell
            para = box.text_frame.paragraphs[0]
            para.font.size, para.font.bold = Pt(size), r == 0
    below = top + Inches(0.28) * len(rows) + Inches(0.1)
    if note:
        text(page, [note], left, below, width, Inches(0.8), 9, MUTED)
        below += Inches(0.8)
    return below


# A chart from submission/figures, or a placeholder when it has not been drawn.
def chart(page, name: str, left, top, width) -> None:
    path = FIGURES / f"{name}.png"
    if path.exists():
        page.shapes.add_picture(str(path), left, top, width=width)
    else:
        text(page, [f"{name}.png not drawn yet"], left, top, width, Inches(0.5), 11, MUTED)


# The twelve signals in words, for the discussion page.
NAMES = dict(
    ope_be="operating profitability",
    noa_gr1a="slow growth in operating assets",
    ret_12_1="12-month momentum",
    eqnetis_at="little new equity issued",
    o_score="low bankruptcy risk",
    be_me="book-to-market",
    niq_su="earnings surprise",
    chcsho_12m="few new shares",
    at_gr1="slow asset growth",
    qmj="quality",
    ivol_capm_21d="low idiosyncratic volatility",
    gp_at="gross profitability",
)


# Each candidate's net return by calendar year, and the composite's IR kept every year.
def candidates():
    import pandas as pd

    from fiam import book as P
    from fiam import paths

    books = pd.read_csv(paths.EXHIBITS / "ship_candidates.csv", parse_dates=["holding_month"])
    year = books["holding_month"].dt.year
    net = books.groupby([books["candidate"], year])["net"].sum()
    kept = books[(books["candidate"] == "composite") & (year >= 2021)]["net"]
    policy = paths.read_json(paths.SUBMISSION / "models" / "policy.json")["by_year"]
    return net, P.information_ratio(kept), policy


# The ship rule's switches away from the composite, in the candidates' own numbers.
def switches(R, m: dict) -> str:
    net, kept, policy = candidates()
    moved = [int(y) for y, name in policy.items() if name.split("+")[0] != "composite"]
    if not moved:
        return f"The AI: {plain(R.shipped(m))}"
    from fiam import book as P

    base, shipped = net["composite"], m["performance"]["information_ratio"]
    times = {1: "once", 2: "twice"}.get(len(moved), f"{len(moved)} times")
    each = "; ".join(
        f"{P.candidate_label(policy[str(y)])} in {y} ({net[policy[str(y)], y]:+.1%} against "
        f"{base[y]:+.1%})"
        for y in moved
    )
    return (
        f"The AI: our rule left the composite {times}, each after its worst stretch, "
        f"for the book that had lost less: {each}. Composite every year: IR {kept:.2f}; the "
        f"rule's book, which we ship: {shipped:.2f}."
    )


# Page 8 from the results: how each year went, which signals paid, where the losses came from.
def discussion(R, m: dict) -> list[str]:
    years = {row[0]: row for row in parse(R.years(m))[0][1:]}
    signals = R.load("exhibits/pack.json")["attribution"]
    total = {s: sum(y[s] for y in signals["by_year"].values()) for s in NAMES}
    ranked = sorted(total, key=total.get, reverse=True)
    worst = signals["worst_months"]
    health = sum(next(iter(w["worst_sectors"])) == "35" for w in worst)
    legs = {w["month"]: w["short"] for w in worst}
    crash = R.load("exhibits/confirmation.json")["confirmation_2016_2020"]["net_by_year"]["2020"]
    split = R.load("exhibits/pack.json")["risk"].get("style_by_year")
    lines = [
        f"Trained for and got: a neutral quality-and-value book. In 2022, {years['2022'][1]}, "
        f"rate hikes rewarded cheap, profitable firms while the S&P 500 fell "
        f"{years['2022'][3].lstrip('-')}.",
        f"Fell short: 2024 {years['2024'][1]} and 2025 {years['2025'][1]} against a hurdle near "
        f"9%. 2016-20 lost too, almost all in 2020 ({crash:+.1%}), when cheap, profitable stocks "
        "crashed and speculative ones soared after COVID.",
    ]
    if split:
        lines.append(
            f"Style or selection: the six styles paid {split['2021']['styles']:+.1%} of 2021 and "
            f"{split['2022']['styles']:+.1%} of 2022; the 2024 loss was stock-specific "
            f"({split['2024']['selection']:+.1%} from selection), not style. Appendix."
        )
    return [
        *lines,
        f"Signals that paid most: {', '.join(NAMES[s] for s in ranked[:3])}. The one that hurt: "
        f"{NAMES[ranked[-1]]}.",
        f"Short squeezes cost most: short leg {legs.get('2021-01', 0):+.1%} in the January 2021 "
        f"meme squeeze, {legs.get('2023-12', 0):+.1%} in December 2023 as markets priced rate "
        f"cuts. Health care led {health} of the 10 worst months.",
        switches(R, m),
        "Next: let the style-free stock picker carry more once it clears the rule; fewer "
        "squeezable shorts; more capacity. Largest contributors, right, by ticker and name.",
    ]


def main() -> None:
    from fiam import paths
    from fiam.report import docs as R

    m = R.load("metrics.json")
    perf = m["performance"]
    deck = Presentation()
    deck.slide_width, deck.slide_height = WIDE, TALL
    half, left, right = Inches(6.1), Inches(0.5), Inches(6.9)

    page = slide(
        deck,
        "A cost-realistic market-neutral book, and a disciplined test of whether AI adds to it",
        f"Jan 2021 - Aug 2026: IR {perf['information_ratio']:.2f} against T-bill + 4%, "
        f"net {perf['return_net_annual']:.1%} a year, beta {perf['beta_realized']:+.2f}",
    )
    text(
        page,
        [
            "Strategy: long the best, short the worst of US stocks on 12 classic measures; "
            "dollar, beta and sector neutral; about 275 names; every trade costed like IBKR.",
            "AI: FinBERT reads every 8-K; agents triage filings, act as analysts and as an AI "
            "crowd; a stock picker learns from it all; a rule written first decides if it ships.",
            f"Honest: two of our upgrades failed their pre-registered tests; we ship our rule's "
            f"book (IR {perf['information_ratio']:.2f}) though the composite alone scores "
            f"{candidates()[1]:.2f}.",
        ],
        left,
        Inches(1.5),
        half,
        Inches(3.5),
    )
    table(page, R.comparison(m), right, Inches(1.5), half, 9)
    # The team, as README.md's last line lists it.
    team = (ROOT / "README.md").read_text().strip().splitlines()[-1]
    text(page, [team], left, Inches(6.6), Inches(12.3), Inches(0.5), 12, MUTED)

    page = slide(deck, "Strategy: what we buy, what we short, and how we stay neutral")
    text(
        page,
        [
            "Score: 12 published signals (value, quality, investment, issuance, momentum, "
            "low risk), each ranked within the month, averaged equally.",
            "Neutral: long = short in dollars; beta within ±0.02; each sector within ±1%; "
            "neutral to the volatility complex. Gross 160%, so no day passed 200%.",
            "Positions: 100-500 names, at most 1.5% each, whole shares, rebalanced monthly.",
        ],
        left,
        Inches(1.2),
        half,
        Inches(2.4),
        12,
    )
    chart(page, "cumulative_return", left, Inches(3.7), half)
    table(page, R.top(m), right, Inches(1.2), half, 8)

    page = slide(
        deck,
        "Data, methodology and the agents",
        "Every model trains only on years before the one it trades; "
        "no language model reads 2021-26",
    )
    text(
        page,
        [
            "Data: the 147-characteristic panel and 373,139 8-Ks; from WRDS, delistings, CRSP "
            "daily prices, short interest, analyst data and Compustat report dates.",
            "Stock picker: LightGBM ranking on the brief's folds, learning returns net of sector, "
            "beta and style, from characteristics, FinBERT text, the agents and four teachers.",
            "Teachers: small models learn what WRDS data ending in 2025 would say, so it informs "
            "2026. Trader: deep hedging and PPO against Garleanu-Pedersen.",
            "OOS R-squared, right: every model's forecasts scaled on earlier years only.",
        ],
        left,
        Inches(1.4),
        half,
        Inches(2.6),
        11,
    )
    table(page, R.r2(m), right, Inches(1.4), half, 8)
    agents = "\n".join(
        [
            "| agent | model | sees | calls, tools | look-ahead blocked by |",
            "|---|---|---|---|---|",
            "| Triage | Gemma 4 26B-A4B | 6,000 masked 8-Ks, 2015-18 | 1 per filing, none "
            "| reads 2015-18 only; FinBERT + LightGBM label the rest |",
            "| Analyst | Qwen3.8-27B | masked material 8-Ks, 12 months of ranks "
            "| 1 per stock-month, 5,000, none "
            "| only verdicts to Nov 2020 teach a small model; "
            "its later ones never reach the book |",
            "| AI crowd | Gemma 4 and Qwen3.8 | anonymous percentile cards, 40 a call "
            "| 60 months of 2016-20, none "
            "| never sees 2021-26; a small model learns what it buys |",
            "| Director, discovery, auditor, critic | Qwen3.8, Gemma 4 | our exhibits, via tools "
            "| at most 15, 60, 60, 30 tool calls "
            "| none sets a weight; discovery sealed on 2021-26 |",
            "",
            "Local open models pinned by SHA-256, temperature 0; names, tickers and dates masked. "
            "Prompts and tool definitions: appendix.",
        ]
    )
    table(page, agents, left, Inches(4.15), Inches(12.3), 8)

    page = slide(deck, "Performance, January 2021 to August 2026", "Net of every modelled cost")
    table(page, R.headline(m), left, Inches(1.5), half, 9)
    table(page, R.committee(m), right, Inches(1.5), half, 9)

    window = "Jan 2021 - Aug 2026, net of every modelled cost"
    page = slide(deck, "Growth and drawdown against the benchmark and the S&P 500", window)
    chart(page, "cumulative_return", left, Inches(1.5), half)
    chart(page, "drawdown", right, Inches(1.5), half)

    title = "Neutral throughout, and how the edge came and went"
    page = slide(deck, title, f"{window}; rolling 12 months")
    quarter = Inches(5.0)
    chart(page, "rolling_beta", left, Inches(1.45), quarter)
    chart(page, "rolling_ir", right, Inches(1.45), quarter)
    chart(page, "rolling_active_return", left, Inches(4.2), quarter)
    chart(page, "return_histogram", right, Inches(4.2), quarter)

    page = slide(deck, "Exposure, costs and the short book", window)
    table(page, R.compliance(m), left, Inches(1.5), half, 9)
    table(page, R.costs(m), right, Inches(1.5), half, 9)
    table(page, R.legs(m), left, Inches(4.7), Inches(12.3), 8)

    page = slide(deck, "Discussion: what worked, what did not, what next", window)
    text(page, discussion(R, m), left, Inches(1.5), half, Inches(5.8), 11)
    chart(page, "pnl_contributors", right, Inches(1.5), half)

    for title, builds in (
        ("Appendix: calendar years, style or stock selection", [R.years, R.styles]),
        ("Appendix: costs, capacity and stress", [R.implementation, R.stress]),
        ("Appendix: neutrality, monthly and daily", [R.drift, R.factor_windows]),
        ("Appendix: a pre-registered construction we rejected", [R.construction]),
        ("Appendix: a pre-registered factor-neutral book we rejected", [R.neutral]),
        ("Appendix: the ship rule and its candidates", [R.ship]),
        ("Appendix: the machine learning and the recall firewall", [R.teachers, R.firewall]),
        ("Appendix: the agents", [R.crowd, R.agents, R.explained]),
        ("Appendix: robustness and multiple testing", [R.halves, R.placebo, R.deflation]),
    ):
        page = slide(deck, title)
        top = Inches(1.2)
        for build in builds:
            top = table(page, build(m), left, top, Inches(12.3), 8) + Inches(0.2)

    page = slide(deck, "Appendix: agent prompts and tools", "Full prompts: prompts/agents/")
    tools = paths.read_json(paths.EXHIBITS / "agents" / "tools.json")
    listed = [f"{agent}: " + ", ".join(t["name"] for t in items) for agent, items in tools.items()]
    prompts = sorted(p.stem for p in (ROOT / "prompts" / "agents").glob("*.md"))
    text(
        page,
        [*listed, "Prompts: " + ", ".join(prompts)],
        left,
        Inches(1.5),
        Inches(12.3),
        Inches(5),
    )

    OUT.parent.mkdir(exist_ok=True)
    deck.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(deck.slides)} slides")


if __name__ == "__main__":
    main()
