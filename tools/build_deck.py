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
            "Honest: two of our own upgrades failed their pre-registered tests and were dropped.",
        ],
        left,
        Inches(1.5),
        half,
        Inches(3.5),
    )
    table(page, R.comparison(m), right, Inches(1.5), half, 9)

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
        deck, "Data and methodology", "Every model trains only on years before the one it trades"
    )
    text(
        page,
        [
            "Data: the 147-characteristic panel and 373,139 8-Ks; from WRDS, delistings, CRSP "
            "daily prices, short interest, analyst data and Compustat report dates.",
            "Teachers: small models learn what 2025-only data would say, so it informs 2026.",
            "Stock picker: LightGBM ranking on the brief's folds, learning returns net of sector, "
            "beta and style, from characteristics, FinBERT text, agent verdicts and teachers.",
            "Trader: reinforcement learning (deep hedging, PPO) against Garleanu-Pedersen.",
            "Agents: local open models only, names and dates masked, a probe measures recall.",
        ],
        left,
        Inches(1.5),
        half,
        Inches(4.5),
        12,
    )
    table(page, R.r2(m), right, Inches(1.5), half, 9)

    page = slide(deck, "Performance, January 2021 to August 2026", "Net of every modelled cost")
    table(page, R.headline(m), left, Inches(1.5), half, 9)
    table(page, R.committee(m), right, Inches(1.5), half, 9)

    page = slide(deck, "Growth and drawdown against the benchmark and the S&P 500")
    chart(page, "cumulative_return", left, Inches(1.2), half)
    chart(page, "drawdown", right, Inches(1.2), half)

    page = slide(deck, "Neutral throughout, not only on average")
    chart(page, "rolling_beta", left, Inches(1.2), half)
    chart(page, "rolling_ir", right, Inches(1.2), half)

    page = slide(deck, "Exposure, costs and the short book")
    table(page, R.compliance(m), left, Inches(1.2), half, 9)
    table(page, R.costs(m), right, Inches(1.2), half, 9)
    table(page, R.legs(m), left, Inches(4.4), Inches(12.3), 8)

    page = slide(deck, "Discussion: what worked, what did not, what next")
    text(
        page,
        [
            "Worked: a quality and value tilt, neutral and cost-realistic; strong in 2021-22.",
            "Did not: 2023-26 was flat as the AI rally favoured expensive growth; 2016-20 lost "
            "money in value's worst stretch in decades. Six-factor alpha is not significant.",
            "AI: see the appendix for whether the stock picker earned its place, and the probe.",
            "Next: a second, style-independent source of return; more capacity; live tracking.",
        ],
        left,
        Inches(1.4),
        half,
        Inches(4.5),
        12,
    )
    chart(page, "pnl_contributors", right, Inches(1.2), half)

    for title, builds in (
        ("Appendix: calendar years and the halves", [R.years, R.halves]),
        ("Appendix: costs, capacity and stress", [R.implementation, R.stress]),
        ("Appendix: neutrality, monthly and daily", [R.drift, R.factor_windows]),
        ("Appendix: a pre-registered construction we rejected", [R.construction]),
        ("Appendix: a pre-registered factor-neutral book we rejected", [R.neutral]),
        ("Appendix: the ship rule and its candidates", [R.ship]),
        ("Appendix: the machine learning", [R.teachers, R.learning]),
        ("Appendix: the agents", [R.crowd, R.agents]),
        ("Appendix: robustness and multiple testing", [R.placebo, R.deflation]),
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
