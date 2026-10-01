# The deck the brief asks for, from the exhibits RESULTS.md reads: uv run tools/build_deck.py

import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
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

# The pipeline, left to right: the book's path on top, the research that feeds it below.
BOOK_PATH = [
    "Organizer panel, 8-K filings, WRDS exits and daily prices, dated to the decision month",
    "12 published signals, ranked each month, averaged: the composite",
    "ML teacher learns each stock's next-month beta from daily returns",
    "Optimizer: dollar, beta, sector and volatility neutral; 1.5% cap; 160% gross",
    "Whole shares, IBKR-style costs, then the audit and the brief's rules",
]
RESEARCH_PATH = [
    "Agents read masked filings and anonymous cards: triage, analyst, AI crowd",
    "Small models learn their judgments from pre-2021 answers only: the firewall",
    "Stock picker learns style-free returns from all of it: reported, not shipped",
]


# A row of labelled boxes joined by arrows, across the slide at one height.
def boxes(page, labels: list[str], top, height, fill: RGBColor) -> None:
    gap, left, width = Inches(0.3), Inches(0.5), Inches(12.3)
    each = (width - gap * (len(labels) - 1)) / len(labels)
    for i, label in enumerate(labels):
        x = left + i * (each + gap)
        shape = page.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, top, each, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        shape.line.fill.background()
        frame = shape.text_frame
        frame.word_wrap = True
        frame.paragraphs[0].text = label
        frame.paragraphs[0].font.size, frame.paragraphs[0].font.color.rgb = Pt(10), INK
        if i:
            arrow = page.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW,
                x - gap + Inches(0.05),
                top + height / 2 - Inches(0.1),
                gap - Inches(0.1),
                Inches(0.2),
            )
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = MUTED
            arrow.line.fill.background()


# Page 8 from the results: how the book did, what drove it, what the AI found, what is next.
def discussion(R, m: dict) -> list[str]:
    years = {row[0]: row for row in parse(R.years(m))[0][1:]}
    pack = R.load("exhibits/pack.json")
    signals = pack["attribution"]
    total = {s: sum(y[s] for y in signals["by_year"].values()) for s in NAMES}
    ranked = sorted(total, key=total.get, reverse=True)
    worst = signals["worst_months"]
    health = sum(next(iter(w["worst_sectors"])) == "35" for w in worst)
    legs = {w["month"]: w["short"] for w in worst}
    crash = R.load("exhibits/confirmation.json")["confirmation_2016_2020"]["net_by_year"]["2020"]
    scorer = R.load("exhibits/scorer.json").get("ic_2021_2026", {})
    lines = [
        f"As trained: a neutral quality-and-value book. 2021 {years['2021'][1]}, 2022 "
        f"{years['2022'][1]} while rate hikes rewarded cheap, profitable firms and the S&P 500 "
        f"fell {years['2022'][3].lstrip('-')}.",
        f"Fell short: 2024 {years['2024'][1]} and 2025 {years['2025'][1]} against a hurdle "
        f"near 9%; the same style lost {-crash:.0%} in 2020, after COVID.",
        f"Signals that paid most: {', '.join(NAMES[s] for s in ranked[:3])}. The one that hurt: "
        f"{NAMES[ranked[-1]]}.",
    ]
    if "2021-01" in legs and "2023-12" in legs:
        lines.append(
            f"Short squeezes cost most: short leg {legs['2021-01']:+.1%} in the January 2021 meme "
            f"squeeze, {legs['2023-12']:+.1%} in December 2023 as markets priced rate cuts. "
            f"Health care led {health} of the 10 worst months."
        )
    if scorer:
        lines.append(
            f"The AI: the learned hedge is in the book; the stock picker predicts (IC "
            f"{scorer['ic_mean']:.3f}, t {scorer['ic_t']:.2f}) but trades too much to pay after "
            "costs; no language model's reading of 2021-26 reaches the book."
        )
    lines.append(
        "Next: the stock picker in cheap-to-trade names only; fewer squeezable shorts; more "
        "capacity. Largest contributors, right, by ticker and name."
    )
    return lines


def main() -> None:
    from fiam import paths
    from fiam.report import docs as R

    m = R.load("metrics.json")
    perf = m["performance"]
    deck = Presentation()
    deck.slide_width, deck.slide_height = WIDE, TALL
    half, left, right = Inches(6.1), Inches(0.5), Inches(6.9)
    window = "Jan 2021 - Aug 2026, net of every modelled cost"

    page = slide(
        deck,
        "A cost-realistic market-neutral book, made more neutral by machine learning",
        f"{window}: IR {perf['information_ratio']:.2f} against T-bill + 4%, net "
        f"{perf['return_net_annual']:.1%} a year, beta {perf['beta_realized']:+.2f}",
    )
    text(
        page,
        [
            "Strategy: long the best and short the worst US stocks on 12 published signals; "
            "dollar, beta and sector neutral; about 280 names; every trade costed like a broker.",
            "Machine learning: the beta we hedge is learned from daily prices. A stock picker, "
            "FinBERT and three LLM agents are research we report, never a black box in the book.",
            "Trust: no language model's reading of a 2021-26 filing reaches the book, and anyone "
            "can rebuild these numbers with one command.",
        ],
        left,
        Inches(1.5),
        half,
        Inches(4.0),
    )
    table(page, R.brief(m), right, Inches(1.5), half, 9)
    team = (ROOT / "README.md").read_text().strip().splitlines()[-1]
    text(page, [team], left, Inches(6.8), Inches(12.3), Inches(0.5), 12, MUTED)

    page = slide(deck, "Strategy: what we buy, what we short, and how we stay neutral", window)
    text(
        page,
        [
            "Score: 12 published signals (value, profitability, investment, issuance, momentum, "
            "low risk), each ranked within the month and averaged equally.",
            "Neutral: long equals short in dollars; beta within ±0.02 on the learned beta; each "
            "sector within ±1%; neutral to the volatility complex. Gross 160%, no day above 200%.",
            "Positions: 100-500 names, at most 1.5% each, whole shares, rebalanced monthly.",
        ],
        left,
        Inches(1.5),
        half,
        Inches(2.3),
        12,
    )
    chart(page, "cumulative_return", left, Inches(3.9), half)
    table(page, R.top(m), right, Inches(1.5), half, 8)

    page = slide(
        deck,
        "Data, methodology and the agents",
        "Every model learns only from years before the one it trades; no LLM reads 2021-26",
    )
    boxes(page, BOOK_PATH, Inches(1.45), Inches(0.95), RGBColor(0xDB, 0xEA, 0xFE))
    boxes(page, RESEARCH_PATH, Inches(2.6), Inches(0.7), RGBColor(0xF3, 0xF4, 0xF6))
    table(page, R.r2(m), left, Inches(3.55), half, 8)
    table(page, R.agents(m), right, Inches(3.55), half, 8)

    page = slide(deck, "Performance, January 2021 to August 2026", "Net of every modelled cost")
    table(page, R.headline(m), left, Inches(1.5), half, 9)
    table(page, R.committee(m), right, Inches(1.5), half, 9)

    page = slide(deck, "Growth and drawdown against the benchmark and the S&P 500", window)
    chart(page, "cumulative_return", left, Inches(1.5), half)
    chart(page, "drawdown", right, Inches(1.5), half)

    page = slide(deck, "Neutral throughout, and how the edge came and went", f"{window}; 12 months")
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
        ("Appendix: everything we tried", [R.tried]),
        ("Appendix: costs, capacity and stress", [R.implementation, R.stress]),
        ("Appendix: neutrality, monthly and daily", [R.drift, R.daily]),
        ("Appendix: the machine learning", [R.teachers, R.scorer, R.models]),
        ("Appendix: the agents and the recall firewall", [R.agents, R.firewall]),
        ("Appendix: the biggest winners and losers, explained", [R.explained]),
        ("Appendix: robustness", [R.halves, R.clean, R.placebo]),
    ):
        page = slide(deck, title)
        top = Inches(1.2)
        for build in builds:
            top = table(page, build(m), left, top, Inches(12.3), 8) + Inches(0.2)

    page = slide(deck, "Appendix: where the return came from", "Six-factor loadings; signals")
    table(page, R.factors(m), left, Inches(1.2), half, 8)
    table(page, R.attribution(m), right, Inches(1.2), half, 8)

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
