# The deck the brief asks for, built from the run's own results: uv run tools/build_deck.py

import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
# The repo root goes on the path, so fiam imports from wherever this is run.
sys.path.insert(0, str(ROOT))
OUT = ROOT / "deck" / "FIAM.pptx"
FIGURES = ROOT / "submission" / "figures"

# One palette, the charts' own: navy ink, one petrol accent, greys, and orange for losses only.
INK, ACCENT, MUTED = (
    RGBColor(0x0B, 0x1F, 0x33),
    RGBColor(0x0F, 0x5C, 0x7A),
    RGBColor(0x6B, 0x72, 0x80),
)
TINT, PANEL, BAND = (
    RGBColor(0xE6, 0xF0, 0xF4),
    RGBColor(0xF4, 0xF6, 0xF8),
    RGBColor(0xF7, 0xF9, 0xFA),
)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
# A font every copy of PowerPoint has, so the deck looks the same on the judges' machines.
FONT = "Calibri"
WIDE, TALL = Inches(13.333), Inches(7.5)
LEFT, WIDTH = Inches(0.6), Inches(12.13)
HALF, RIGHT = Inches(5.9), Inches(6.83)
PERIOD = "January 2021 to August 2026, after all modelled costs"


# A markdown cell as plain text: no bold, no code marks, no italic underscores around it.
def plain(cell: str) -> str:
    cell = re.sub(r"\*\*|`", "", cell).strip()
    return cell[1:-1] if len(cell) > 1 and cell[0] == cell[-1] == "_" else cell


# Each markdown table in a docs block as rows of plain cells, with the note printed under it.
def parse(markdown: str) -> list[tuple[list[list[str]], str]]:
    blocks, rows, note = [], [], []
    for line in markdown.strip().splitlines() + [""]:
        separator = "-" in line and re.fullmatch(r"[|\-: ]+", line.strip())
        if line.startswith("|") and not separator:
            if note and rows:
                blocks.append((rows, " ".join(note)))
                rows, note = [], []
            rows.append([plain(c) for c in line.strip("|").split("|")])
        elif line.startswith("|"):
            continue
        elif line.strip() and not line.startswith("_From code"):
            note.append(plain(line))
        elif not line.strip() and rows and not note:
            blocks.append((rows, ""))
            rows = []
    if rows or note:
        blocks.append((rows, " ".join(note)))
    return blocks


# Words a heading leaves in lower case unless they open it, and short forms written our way.
SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "per", "the"}
SMALL |= {"to", "vs", "with", "against", "over"}
FORMS = {"se": "SE", "t": "t", "ic": "IC"}


# Slide text without semicolons or dashes: a dash between numbers is a hyphen, any other a comma.
def tidy(text: str) -> str:
    text = re.sub(r"(?<=\d)[–—](?=\d)", "-", text)
    text = re.sub(r"\s*[–—]\s*", ", ", text)
    return text.replace("; ", ", ").replace(";", ",")


# A heading in title case, leaving acronyms, numbers and short joining words alone.
def heading(text: str) -> str:
    words = []
    for i, word in enumerate(text.split(" ")):
        if word.lower() in FORMS:
            words.append(FORMS[word.lower()])
        elif not word or any(c.isupper() or c.isdigit() for c in word) or (i and word in SMALL):
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


# One run of text in a paragraph, in the deck's font.
def run(para, text: str, size: float, color: RGBColor, bold: bool = False) -> None:
    piece = para.add_run()
    piece.text = tidy(text)
    piece.font.name, piece.font.size, piece.font.bold = FONT, Pt(size), bold
    piece.font.color.rgb = color


# An empty text frame at a place on the slide, wrapping, with no inner margins.
def frame(page, left, top, width, height):
    box = page.shapes.add_textbox(left, top, width, height).text_frame
    box.word_wrap = True
    box.margin_left = box.margin_right = box.margin_top = box.margin_bottom = 0
    return box


# Paragraphs in a box. An item is plain text, or (lead, rest) with the lead in bold.
def text(page, items, left, top, width, height, size=14, color=INK, gap=8) -> None:
    box = frame(page, left, top, width, height)
    for i, item in enumerate(items):
        para = box.paragraphs[0] if i == 0 else box.add_paragraph()
        para.space_after = Pt(gap)
        lead, rest = item if isinstance(item, tuple) else ("", item)
        if lead:
            run(para, lead + " ", size, ACCENT, bold=True)
        run(para, rest, size, color)


# A slide: a short accent bar, an optional section label, the title, the line under it, a footer.
def slide(deck, title: str, subtitle: str = "", section: str = ""):
    page = deck.slides.add_slide(deck.slide_layouts[6])
    flat(
        page.shapes.add_shape(MSO_SHAPE.RECTANGLE, LEFT, Inches(0.42), Inches(0.5), Inches(0.06)),
        ACCENT,
    )
    if section:
        label = frame(page, LEFT + Inches(0.65), Inches(0.33), Inches(4), Inches(0.25))
        run(label.paragraphs[0], section.upper(), 9.5, ACCENT, bold=True)
    head = frame(page, LEFT, Inches(0.6), WIDTH, Inches(0.6))
    run(head.paragraphs[0], title, 26, INK, bold=True)
    if subtitle:
        sub = frame(page, LEFT, Inches(1.18), WIDTH, Inches(0.35))
        run(sub.paragraphs[0], subtitle, 13, MUTED)
    foot = frame(page, LEFT, Inches(7.05), WIDTH, Inches(0.25))
    run(foot.paragraphs[0], "FIAM  ·  McGill-FIAM Asset Management Hackathon 2026", 9, MUTED)
    number = frame(page, Inches(12.2), Inches(7.05), Inches(0.53), Inches(0.25))
    number.paragraphs[0].alignment = PP_ALIGN.RIGHT
    run(number.paragraphs[0], str(len(deck.slides)), 9, MUTED)
    return page


# A number that should read as one: a sign, digits, a percent or a unit, and few words after.
def numeric(cell: str) -> bool:
    words = re.sub(r"\(.*?\)|[^A-Za-z]", "", cell)
    return bool(re.match(r"^[-+−$]?\d[\d.,]*(%|bn|m)?([ ,/]|$)", cell)) and len(words) <= 12


# How many lines a cell's text takes in a column, at a font size, roughly.
def lines(value: str, width: float, size: float) -> int:
    per_line = max(int(width / (size * 0.0062)), 1)
    return max(1, -(-len(value) // per_line))


# Every table in a docs block as clean slide tables: navy header, light bands, numbers right.
def table(page, markdown: str, left, top, width, size=10.5, row=0.3):
    for rows, note in parse(markdown) or [([], "")]:
        top = draw(page, rows, note, left, top, width, size, row) + Inches(0.12)
    return top - Inches(0.12)


# One table on the slide; returns where it ends, rows grown to fit their wrapped text.
def draw(page, rows, note, left, top, width, size, row):
    header = bool(rows) and any(rows[0])
    rows = rows if header else rows[1:]
    if not rows:
        text(page, [note or "Not built yet."], left, top, width, Inches(0.5), 11, MUTED)
        return top + Inches(0.55)
    cols = max(len(r) for r in rows)
    shape = page.shapes.add_table(len(rows), cols, left, top, width, Inches(row) * len(rows))
    grid = shape.table
    # No theme style or banding, so only the fills below show.
    props = grid._tbl.tblPr
    props.set("firstRow", "0")
    props.set("bandRow", "0")
    style = props.find("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId")
    if style is not None:
        style.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
    # Wider columns for longer text, so a sentence column does not squeeze the numbers.
    lengths = [min(max(len(r[c]) if c < len(r) else 0 for r in rows), 70) for c in range(cols)]
    lengths = [max(n, 11) for n in lengths]
    widths = [width * n / sum(lengths) for n in lengths]
    for c, w in enumerate(widths):
        grid.columns[c].width = Emu(int(w))
    # A column reads as numbers, right-aligned, when most of its filled cells are numbers.
    body = rows[1:] if header else rows
    filled = [[r[c] for r in body if c < len(r) and r[c]] for c in range(cols)]
    figures = [bool(f) and sum(map(numeric, f)) * 2 > len(f) for f in filled]
    height = 0
    for r, cells in enumerate(rows):
        values = [cells[c] if c < len(cells) else "" for c in range(cols)]
        tall = max(
            lines(v, (widths[c] - Inches(0.16)) / 914400, size) for c, v in enumerate(values)
        )
        grid.rows[r].height = Inches(max(row, 0.08 + tall * size * 0.0175))
        height += grid.rows[r].height
        dark = header and r == 0
        for c, value in enumerate(values):
            cell = grid.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = INK if dark else (BAND if r % 2 == 0 else WHITE)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            box = cell.text_frame
            box.word_wrap = True
            para = box.paragraphs[0]
            # Sized even when empty, or an empty cell falls back to 18 pt and stretches its row.
            para.font.size = Pt(size)
            para.alignment = PP_ALIGN.RIGHT if (c and figures[c]) else PP_ALIGN.LEFT
            if dark:
                value = heading(value)
            elif not numeric(value) and value.split(" ")[0] not in VERBATIM:
                value = value[:1].upper() + value[1:]
            run(para, value or " ", size, WHITE if dark else INK, bold=dark)
    below = top + height + Inches(0.06)
    if note:
        tall = lines(note, width / 914400, 9)
        text(page, [note], left, below, width, Inches(0.2 * tall + 0.1), 9, MUTED)
        below += Inches(0.17 * tall + 0.1)
    return below


# A chart from submission/figures, fitted inside a box with its proportions kept.
def chart(page, name: str, left, top, width, height=None) -> None:
    path = FIGURES / f"{name}.png"
    if not path.exists():
        text(page, [f"{name}.png not drawn yet"], left, top, width, Inches(0.4), 11, MUTED)
        return
    picture = page.shapes.add_picture(str(path), left, top, width=width)
    if height is not None and picture.height > height:
        ratio = height / picture.height
        picture.height, picture.width = int(height), int(picture.width * ratio)


# A flat shape: no theme shadow, outline or glow, only the fill we give it.
def flat(shape, fill: RGBColor):
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    style = shape._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
    if style is not None:
        shape._element.remove(style)
    return shape


# A headline number on a light card, its label under it.
def card(page, left, top, width, value: str, label: str) -> None:
    flat(page.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Inches(1.25)), PANEL)
    box = frame(page, left + Inches(0.25), top + Inches(0.18), width - Inches(0.5), Inches(1))
    run(box.paragraphs[0], value, 32, ACCENT, bold=True)
    para = box.add_paragraph()
    run(para, label, 12, MUTED)


# The twelve signals in words, for the discussion page.
NAMES = dict(
    ope_be="operating profitability",
    noa_gr1a="slow growth in net operating assets",
    ret_12_1="12-month momentum",
    eqnetis_at="low net equity issuance",
    o_score="low bankruptcy risk",
    be_me="book-to-market",
    niq_su="earnings surprise",
    chcsho_12m="low share issuance",
    at_gr1="slow total asset growth",
    qmj="quality score",
    ivol_capm_21d="low stock-specific volatility",
    gp_at="gross profitability",
)

# Each signal as a plain noun, so "high" or "low" can go in front of it.
WORDS = dict(
    ope_be="operating profitability",
    noa_gr1a="growth in net operating assets",
    ret_12_1="12-month momentum",
    eqnetis_at="net equity issuance",
    o_score="bankruptcy risk",
    be_me="book-to-market",
    niq_su="earnings surprise",
    chcsho_12m="share issuance",
    at_gr1="total asset growth",
    qmj="quality score",
    ivol_capm_21d="stock-specific volatility",
    gp_at="gross profitability",
)

# The pipeline, left to right: the book's path on top, the research that feeds it below.
BOOK_PATH = [
    "Organizer stock panel and 8-K filings, plus daily prices, dated to the month",
    "Twelve published signals, ranked each month and averaged into one score",
    "LightGBM predicts each stock's next-month beta",
    "The optimizer keeps the portfolio dollar, beta, sector and volatility neutral",
    "Whole shares and realistic costs, then automatic checks against the brief",
]
RESEARCH_PATH = [
    "AI agents read filings and stock profiles with names, tickers and dates hidden",
    "Small models learn the agents' answers from before 2021",
    "A stock-picking model uses all of it, reported but not traded",
]


# A row of labelled boxes joined by arrows, across the slide at one height.
def boxes(page, labels: list[str], top, height, fill: RGBColor) -> None:
    gap = Inches(0.32)
    each = (WIDTH - gap * (len(labels) - 1)) / len(labels)
    for i, label in enumerate(labels):
        x = LEFT + i * (each + gap)
        shape = flat(page.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, top, each, height), fill)
        box = shape.text_frame
        box.word_wrap = True
        box.margin_left = box.margin_right = Inches(0.12)
        box.paragraphs[0].alignment = PP_ALIGN.CENTER
        run(box.paragraphs[0], label, 11, INK)
        if i:
            arrow = page.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW,
                x - gap + Inches(0.08),
                top + height / 2 - Inches(0.09),
                gap - Inches(0.16),
                Inches(0.18),
            )
            flat(arrow, MUTED)


# The two signals that most put a name on its side of the book, from the explainer's facts.
def reasons(facts: dict, long: bool) -> str:
    pct, ways = facts["signal_percentiles"], facts["signal_directions"]
    # How strongly each signal argued for this side: 100 is the strongest case.
    case = {k: v if (ways[k] == "higher is better") == long else 100 - v for k, v in pct.items()}
    from fiam.agents import explainer

    plain = {explainer.NAMES[c]: word for c, word in WORDS.items()}
    out = []
    for k in sorted(case, key=case.get, reverse=True)[:1]:
        if pct[k] >= 50:
            out.append(f"high {plain[k]} (top {max(100 - int(round(pct[k])), 1)}% of stocks)")
        else:
            out.append(f"low {plain[k]} (bottom {max(int(round(pct[k])), 1)}% of stocks)")
    return " and ".join(out)


# The best long, the best short and the worst name, each with why the book held it.
def standouts() -> str:
    from fiam.report import docs as R

    names = R.load("exhibits/explainer.json").get("positions", [])
    if not names:
        return ""
    pnl = lambda p: p["facts"]["realized_pnl_pct"]  # noqa: E731
    longs = [p for p in names if p["side"] == "LONG"]
    shorts = [p for p in names if p["side"] == "SHORT"]
    picks = [max(longs, key=pnl), max(shorts, key=pnl), min(names, key=pnl)]
    parts = []
    for p in picks:
        side = p["side"].lower()
        # A loss on a short means the shares rose, on a long that they fell.
        moved = {("short", True): ", yet its shares rose", ("long", True): ", yet it fell"}
        parts.append(
            f"{side} {p['ticker']}, {known_as(p['ticker'], p['company'])}, "
            f"{pnl(p):+.1f}% of NAV, held for {reasons(p['facts'], side == 'long')}"
            + moved.get((side, pnl(p) < 0), "")
        )
    return ". ".join(s[:1].upper() + s[1:] for s in parts) + "."


# A name with the one it had before, when the company changed it during the period.
def known_as(ticker: str, name: str) -> str:
    import pandas as pd

    from fiam import book as P

    held = pd.read_csv(ROOT / "submission" / "holdings.csv")
    held = held[held["TICKER"] == ticker].sort_values("Date")
    first = held["COMPANY NAME"].iloc[0] if len(held) else name
    word = lambda n: re.sub(r"[^A-Z]", "", str(n).split()[0].upper())  # noqa: E731
    if not len(held) or word(first) == word(name):
        return P.display_name(name)
    return f"{P.display_name(name)} (formerly {P.display_name(first)})"


# Names shown exactly as a model received them, never capitalized.
VERBATIM: set[str] = set()


# Every "TICKER, Name" cell in a table, with the company's earlier name where it changed.
def renamed(body: str) -> str:
    for ticker, name in re.findall(r"\| ([A-Z.]+), ([^|]+?) \|", body):
        body = body.replace(f"{ticker}, {name} |", f"{ticker}, {known_as(ticker, name)} |")
    return body


# Page 8 from the results: how the book did, what drove it, what the AI found, what is next.
def discussion(R, m: dict) -> list[str]:
    years = {row[0]: row for row in parse(R.years(m))[0][0][1:]}
    pack = R.load("exhibits/pack.json")
    signals = pack["attribution"]
    total = {s: sum(y[s] for y in signals["by_year"].values()) for s in NAMES}
    ranked = sorted(total, key=total.get, reverse=True)
    worst = signals["worst_months"]
    health = sum(next(iter(w["worst_sectors"])) == "35" for w in worst)
    legs = {w["month"]: w["short"] for w in worst}
    crash = R.load("exhibits/confirmation.json")["confirmation_2016_2020"]["net_by_year"]["2020"]
    scorer = R.load("exhibits/scorer.json").get("ic_2021_2026", {})
    later = pack["subperiod"]["second_half_2023_2026"]["information_ratio"]
    perf = m["performance"]
    beaten = sum(row[4].startswith("+") for row in years.values())
    lines = [
        "Expectations: met over the full period, not every year. "
        f"IR {perf['information_ratio']:.2f} with beta {perf['beta_realized']:+.2f}, but most "
        f"of the edge came in 2021-22. From 2023 on, the IR is {later:+.2f}. It beat the hurdle "
        f"in {beaten} of {len(years)} years.",
        f"What worked: value and quality, total returns of {years['2021'][1]} in 2021 and "
        f"{years['2022'][1]} in 2022, as rising rates favoured cheap, profitable companies.",
        f"What did not: 2024 ({years['2024'][1]}) and 2025 ({years['2025'][1]}) missed a hurdle "
        f"near 9%. The same signals, run on 2020, had a net return of {crash:.0%}.",
        f"Signals: {NAMES[ranked[0]]}, {NAMES[ranked[1]]} and {NAMES[ranked[2]]} paid most. "
        f"{NAMES[ranked[-1]].capitalize()} hurt.",
    ]
    names = standouts()
    if names:
        lines.append(f"Names: {names}")
    if "2021-01" in legs and "2023-12" in legs:
        lines.append(
            f"Short squeezes: shorts lost {-legs['2021-01']:.1%} in the January 2021 meme "
            f"squeeze and {-legs['2023-12']:.1%} in December 2023 as rate cuts were priced. "
            f"Health care led {health} of the 10 worst months."
        )
    if scorer:
        lines.append(
            f"AI: the predicted beta is used in the portfolio. The stock-picking model does "
            f"predict returns (IC {scorer['ic_mean']:.3f}, t-stat {scorer['ic_t']:.2f}), but every "
            "machine-learning portfolio we built lost money after costs (page 15)."
        )
    lines.append(
        "Next: use the stock-picking model only on cheap-to-trade stocks, avoid shorts that are "
        "easy to squeeze, and raise capacity."
    )
    return lines


# The information ratio if the fund's cash had earned nothing, from the submitted returns.
def no_interest() -> str:
    import numpy as np
    import pandas as pd

    r = pd.read_csv(ROOT / "submission" / "returns.csv")
    active = r["net"] - (r["rf"] + 0.04 / 12)
    ir = np.sqrt(12) * active.mean() / active.std()
    return (
        f"If the fund's cash had earned no interest at all, the information ratio against "
        f"T-bill + 4% would be {ir:.2f} instead of the brief's measure, which credits it."
    )


# The daily beta over the years with daily prices, as the neutrality appendix reports it.
def daily_beta(R, m: dict) -> str:
    found = re.search(r"\| 2021-2025, [\d,]+ days \| ([+-]?\d\.\d\d)", R.drift(m))
    return found[1] if found else "n/a"


# How many calendar years beat the hurdle, as words for a title.
def hurdle_years(R, m: dict) -> str:
    rows = parse(R.years(m))[0][0][1:]
    words = "Zero One Two Three Four Five Six Seven".split()
    return f"{words[sum(r[4].startswith('+') for r in rows)]} of {words[len(rows)]} Years"


# Strategy, hurdle and S&P 500 side by side, as one markdown table.
def against(side: dict, rows: list[tuple[str, str, str]]) -> str:
    import pandas as pd

    lines = ["| After Costs | Strategy | T-bill + 4% | S&P 500 |", "|---|---:|---:|---:|"]
    for label, key, fmt in rows:
        cells = []
        for who in ("strategy", "benchmark", "sp500"):
            value = side[who][key]
            if isinstance(value, dict):
                month = pd.Timestamp(value["month"][:7] + "-01").strftime("%b %Y")
                cells.append(f"{value['value']:{fmt}}, {month}")
            else:
                cells.append(" " if value is None else f"{value:{fmt}}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


# Page 1's table: the strategy against its hurdle and the market, and the facts behind it.
def glance(side: dict, perf: dict, cost: dict, comp: dict) -> str:
    body = against(
        side,
        [
            ("Total return a year", "annual_geometric", ".1%"),
            ("Total return, Jan 2021 to Aug 2026", "cumulative", ".0%"),
            ("Volatility", "volatility", ".1%"),
            ("Sharpe ratio", "sharpe_ratio", ".2f"),
            ("Worst drawdown, monthly", "max_drawdown", ".1%"),
        ],
    )
    return body + (
        f"\n\nTotal return = net return plus "
        f"{side['benchmark']['annual_arithmetic'] - 0.04:.1%} a year of T-bill interest on the "
        "fund's cash, counted the same way as the hurdle."
    )


# Page 4's return table for all three, with how a month's total return is put together.
def returns(side: dict, R) -> str:
    monthly = {k: dict(v, monthly=v["annual_arithmetic"] / 12) for k, v in side.items()}
    # Every row here is a total return, the T-bill included, as the hurdle is.
    body = against(
        monthly,
        [
            ("Average monthly total return", "monthly", ".2%"),
            ("Annual, arithmetic", "annual_arithmetic", ".1%"),
            ("Annual, geometric (CAGR)", "annual_geometric", ".1%"),
            ("Total return, Jan 2021 to Aug 2026", "cumulative", ".1%"),
            ("Volatility", "volatility", ".1%"),
            ("Sharpe ratio", "sharpe_ratio", ".2f"),
            ("Max drawdown, monthly", "max_drawdown", ".1%"),
            ("Best month", "best_month", "+.1%"),
            ("Worst month", "worst_month", "+.1%"),
        ],
    )
    return body + (
        "\n\nNet return: long minus short, after trading, borrow and financing costs. Total "
        "return: net return plus T-bill interest on the fund's cash, as in the hurdle. Positions "
        "are % of NAV, 80% long and 80% short. S&P 500: FRED price index, without dividends."
    )


# Page 4's second table: the risk-adjusted numbers, the exposures and the costs.
def risk(R, m: dict) -> str:
    perf, cost, comp = m["performance"], m["costs"], m["compliance"]
    c = R.load("exhibits/pack.json")["completeness"]
    r = c["ranges"]

    def spread(key: str, fmt: str) -> str:
        x = r[key]
        out = f"{x['mean']:{fmt}} ({x['min']:{fmt}} to {x['max']:{fmt}})"
        return out.replace("-0.00%", "0.00%")

    rows = [
        ("Information ratio vs T-bill + 4%", f"{perf['information_ratio']:.2f}"),
        ("Information ratio, before costs", f"{perf['information_ratio_before_costs']:.2f}"),
        (
            "Alpha a year vs the S&P 500",
            f"{perf['alpha_annual']:.1%} (t-stat {perf['alpha_tstat']:.2f})",
        ),
        (
            "Beta to the S&P 500",
            f"{perf['beta_realized']:+.2f} (standard error {perf['beta_stderr']:.2f})",
        ),
        ("Correlation with the S&P 500", f"{perf['correlation_with_market']:+.2f}"),
        ("Hit rate, months beating the hurdle", f"{perf['hit_rate_positive_active_months']:.0%}"),
        ("Gross return, before costs", f"{perf['return_gross_annual']:.1%} a year"),
        ("Net return, after all costs", f"{perf['return_net_annual']:.1%} a year"),
        (
            "Holdings, long / short",
            f"{c['average_long_positions']:.0f} / {c['average_short_positions']:.0f}",
        ),
        ("Gross exposure, average (range)", spread("gross_exposure", ".2%")),
        (
            "Net exposure",
            f"{abs(r['net_exposure']['mean']):.2%}, never beyond "
            f"±{max(abs(r['net_exposure']['min']), abs(r['net_exposure']['max']), 0.0001):.2%}",
        ),
        (
            "Position weight, average / largest",
            f"{c['average_absolute_position_weight']:.2%} / {comp['position_weight_max']:.2%}",
        ),
        ("Ten largest positions, share of gross", f"{c['legs']['top10_share_of_gross']:.1%}"),
        ("Turnover, one-way monthly, average (range)", spread("turnover_one_way", ".0%")),
        (
            "Costs a year",
            f"{cost['cost_annual']:.1%} ({cost['cost_share_of_gross']:.0%} of gross)",
        ),
    ]
    body = "| Risk, Exposure and Costs | |\n|---|---:|\n"
    body += "\n".join(f"| {a} | {b} |" for a, b in rows)
    return body + "\n\nt-stats use Newey-West standard errors (6 lags)."


# Page 3's agent table: what each could see, its tools and steps, its model, what it found.
def architecture() -> str:
    from fiam.report import docs as R

    t = R.load("exhibits/triage.json")
    c, k = R.load("exhibits/crowd.json"), R.load("exhibits/critic.json")
    e, pack = R.load("exhibits/explainer.json"), R.load("exhibits/pack.json")
    crowded = (pack.get("crowding") or {}).get("long", {})
    one = "None, one answer each"
    rows = [
        (
            "Triage",
            "Gemma 4 26B-A4B",
            "One 8-K from 2015-18, names hidden",
            one,
            f"{t.get('labelled', 0):,} filings labelled, a small model matches "
            f"{t.get('cross_validated_accuracy', 0):.0%}",
        ),
        (
            "Analyst",
            "Qwen3.8-27B",
            "A stock's 8-Ks for one month, names hidden, and a year of its ranks",
            one,
            f"{R.load('exhibits/analyst.json').get('stock_months', 0):,} verdicts, no predictive "
            "power after 2020",
        ),
        (
            "AI crowd",
            "Gemma 4 and Qwen3.8",
            "Anonymous stock cards of percentiles, 2016-20",
            one,
            f"{c.get('picks', 0):,} picks. "
            f"{crowded.get('share_in_top_crowd_decile', 0):.0%} of our longs are its top tenth",
        ),
        (
            "Devil's advocate",
            "Gemma 4 26B-A4B",
            "Our finished portfolio, through 6 tools",
            "Up to 30 tool calls",
            f"{len(k.get('critiques', []))} critiques, "
            + (
                "every number backed by a tool"
                if not k.get("unsupported")
                else f"{k.get('unsupported')} numbers no tool showed"
            ),
        ),
        (
            "Explainer",
            "Qwen3.8-27B",
            "One position's name, P&L and signal ranks",
            one,
            f"{len(e.get('positions', []))} winners and losers explained",
        ),
    ]
    head = "| Agent | Model | What It Sees | Tools and Steps | Result |\n|---|---|---|---|---|\n"
    return head + "\n".join("| " + " | ".join(r) + " |" for r in rows)


# How look-ahead on the model side is ruled out, with the probe's numbers.
def recall() -> str:
    from fiam.report import docs as R

    probe = R.load("exhibits/analyst.json").get("look_ahead_probe", {})
    late = R.load("exhibits/analyst_learned.json").get("recall_test", {})
    ic = late.get("2021-2026", {}).get("analyst", {}).get("rank_correlation", 0)
    return (
        "Guarding against recall (a model remembering what happened later): agents that judge "
        "stocks never see a name, ticker or date, and only their pre-2021 answers are used. "
        f"Asked to guess, the analyst named the company in {probe.get('company_named', 0):.0%} of "
        f"filings, and its 2021-26 verdicts have no predictive power (IC {ic:+.3f}). The devil's "
        "advocate and explainer only review the finished portfolio."
    )


# The five system prompts as slide paragraphs, split over two columns.
def prompts() -> tuple[list, list]:
    from fiam.agents import explainer

    files = ROOT / "prompts" / "agents"
    found = {p.stem: p.read_text(encoding="utf-8") for p in files.glob("*.md")}
    found["explainer"] = explainer.SYSTEM
    models = dict(
        triage="Gemma 4 26B-A4B",
        analyst="Qwen3.8-27B",
        crowd="Gemma 4 and Qwen3.8",
        critic="Gemma 4 26B-A4B",
        explainer="Qwen3.8-27B",
    )
    titles = dict(crowd="AI crowd", critic="Devil's advocate")

    # One prompt as paragraphs: wrapped lines joined, list items kept on their own lines.
    def items(name: str) -> list:
        body = found[name].replace("`", "").strip()
        lines = re.sub(r"\n(?!\s*(?:- |\d+\. |\n))", " ", body).split("\n")
        lines = [re.sub(r"\s+", " ", line) for line in lines]
        out = [(f"{titles.get(name, name.capitalize())}, {models[name]}.", "")]
        out += [line.strip() for line in lines if line.strip()]
        return out

    return items("triage") + items("analyst") + items("crowd"), items("critic") + items("explainer")


# The explainer slips in its own words; said plainly beside them rather than edited away.
def slips() -> str:
    from fiam.report import docs as R

    wrong = [
        p["ticker"]
        for p in R.load("exhibits/explainer.json").get("positions", [])
        if p["side"] == "SHORT" and re.search(r"contradict|negative for a short", p["why"])
    ]
    if not wrong:
        return "Each answer is shown as the explainer wrote it."
    named = " and ".join(wrong)
    return (
        f"Shown as the explainer wrote them, slips included. For {named} it calls the signals "
        "a contradiction of the short, when a high bankruptcy-risk score and heavy share "
        "issuance are exactly why the portfolio shorted them. Fluent is not the same as right."
    )


def main() -> None:
    from fiam import paths
    from fiam.report import docs as R

    m = R.load("metrics.json")
    perf, cost, comp = m["performance"], m["costs"], m["compliance"]
    deck = Presentation()
    deck.slide_width, deck.slide_height = WIDE, TALL

    # 1. Executive summary.
    page = slide(
        deck,
        "A Market-Neutral US Equity Strategy, Hedged With Machine Learning",
        f"{PERIOD}. Benchmark: 3-month T-bill + 4% a year. S&P 500 for context",
    )
    side = R.load("exhibits/pack.json")["completeness"]["comparison"]
    cards = [
        (f"{perf['information_ratio']:.2f}", "Information Ratio vs T-bill + 4%"),
        (f"{perf['return_net_annual']:.1%}", "Net Return a Year (Hurdle: 4% Over the T-bill)"),
        (f"{perf['beta_realized']:+.2f}", "Beta to the S&P 500"),
        (f"{perf['max_drawdown_total']:.1%}", "Worst Monthly Drawdown"),
    ]
    width = (WIDTH - Inches(0.3) * 3) / 4
    for i, (value, label) in enumerate(cards):
        card(page, LEFT + i * (width + Inches(0.3)), Inches(1.75), width, value, label)
    text(
        page,
        [
            (
                "Strategy.",
                "Long the strongest US stocks and short the weakest on twelve published signals, "
                "dollar and beta neutral.",
            ),
            (
                "Machine learning.",
                "LightGBM predicts each stock's beta so the hedge is accurate. A stock-picking "
                "model and five AI agents were built and tested, and are reported, not traded.",
            ),
            (
                "Integrity.",
                "No AI opinion on a 2021-2026 filing affects a trade. Every trade pays realistic "
                "costs, and one command rebuilds the portfolio.",
            ),
        ],
        LEFT,
        Inches(3.35),
        HALF,
        Inches(3.2),
        14,
        gap=12,
    )
    table(page, glance(side, perf, cost, comp), RIGHT, Inches(3.35), HALF, 11.5, 0.34)
    team = (ROOT / "README.md").read_text().strip().splitlines()[-1]
    text(page, [team], LEFT, Inches(6.62), WIDTH, Inches(0.3), 11, MUTED)

    # 2. Strategy.
    page = slide(
        deck,
        "Long the Best, Short the Worst, Across Twelve Published Signals",
        f"Market neutral by design, {comp['positions_average']:.0f} stocks on average, "
        "rebalanced monthly",
    )
    signals = [NAMES[c] for c in NAMES]
    text(
        page,
        [
            (
                "Score.",
                "Each month every stock is ranked on twelve published signals, equally weighted: "
                + ", ".join(signals[:-1])
                + f" and {signals[-1]}.",
            ),
            (
                "Neutral.",
                "80% long and 80% short, so dollar neutral at 160% gross exposure (limit 200%). "
                "Portfolio beta held within ±0.02, each sector within ±1%.",
            ),
            (
                "Sized.",
                "Positions capped at 1.5% of NAV, bought in whole shares, every trade costed.",
            ),
        ],
        LEFT,
        Inches(1.7),
        HALF,
        Inches(2.4),
        12.5,
        gap=7,
    )
    chart(page, "cumulative_return", LEFT, Inches(4.15), HALF, Inches(2.8))
    top = renamed(R.top(m))
    top = top.replace("| weight |", "| average weight |")
    named = R.load("exhibits/labels.json")
    rows = named.get("holding_rows", 0)
    sure = round(rows * named.get("confirmed_share", 0))
    top += (
        "\n\nAverage weight over all 68 months, zero when not held. Names as spelled by their "
        f"dated source. {sure:,} of {rows:,} holding rows confirmed by CRSP, an 8-K, EDGAR or "
        "Compustat (labels.csv)."
    )
    table(page, top, RIGHT, Inches(1.75), HALF, 9.5, 0.29)

    # 3. Data, method and agents.
    page = slide(
        deck,
        "Every Model Learns Only From the Past",
        "Every model is trained only on data from before the year it predicts, and refit each "
        "January",
    )
    boxes(page, BOOK_PATH, Inches(1.65), Inches(0.8), TINT)
    boxes(page, RESEARCH_PATH, Inches(2.6), Inches(0.6), PANEL)
    error = re.search(r"(\d\.\d\d) against (\d\.\d\d)", R.teachers(m))
    why = (
        "Return models follow the brief: train from 2015, validate on the two years before, test "
        "the next year. The beta model trains on all earlier years. An 8-K is used only from the "
        "month after it is filed. Why LightGBM for beta: beta shifts with size, volatility and "
        "leverage in ways a straight line misses"
        + (f", and it cut the 60-month beta's error from {error[2]} to {error[1]}" if error else "")
        + ". Agents run on open models on our own machines, so every answer can be reproduced."
    )
    below = table(page, R.r2(m), LEFT, Inches(3.45), Inches(4.6), 9, 0.25)
    text(page, [why], LEFT, below + Inches(0.08), Inches(4.6), Inches(1.0), 9.5, MUTED)
    below = table(page, architecture(), Inches(5.45), Inches(3.45), Inches(7.28), 8.5, 0.25)
    text(page, [recall()], Inches(5.45), below + Inches(0.06), Inches(7.28), Inches(0.8), 9.5)

    # 4. Performance statistics.
    page = slide(
        deck,
        f"Information Ratio {perf['information_ratio']:.2f} After Costs, Alpha "
        f"{perf['alpha_annual']:.1%} a Year (t-stat {perf['alpha_tstat']:.2f})",
        PERIOD,
    )
    table(page, returns(side, R), LEFT, Inches(1.75), HALF, 10, 0.28)
    table(page, risk(R, m), RIGHT, Inches(1.75), HALF, 10, 0.27)

    # 5. Growth and drawdown.
    page = slide(
        deck,
        f"Ahead of the Hurdle in {hurdle_years(R, m)}, Worst Drawdown "
        f"{perf['max_drawdown_total']:.1%}",
        PERIOD,
    )
    chart(page, "cumulative_return", LEFT, Inches(1.75), HALF)
    chart(page, "drawdown", RIGHT, Inches(1.75), HALF)
    table(page, R.years(m), LEFT, Inches(5.0), WIDTH, 10.5, 0.27)

    # 6. Neutrality and the edge over time.
    page = slide(
        deck,
        f"Monthly Beta Near Zero ({perf['beta_realized']:+.2f}), but a Weak 2024 and 2025",
        f"Rolling 12-month windows, {PERIOD}. Measured on daily returns (2021-2025), beta is "
        f"{daily_beta(R, m)} (page 11)",
    )
    quarter, low = Inches(5.6), Inches(4.35)
    chart(page, "rolling_beta", LEFT, Inches(1.6), quarter, Inches(2.65))
    chart(page, "rolling_ir", RIGHT, Inches(1.6), quarter, Inches(2.65))
    chart(page, "rolling_active_return", LEFT, low, quarter, Inches(2.65))
    chart(page, "return_histogram", RIGHT, low, quarter, Inches(2.65))

    # 7. Costs, exposure and the short book.
    page = slide(
        deck,
        f"All Costs Modelled: {cost['cost_annual']:.1%} a Year, "
        f"{cost['cost_share_of_gross']:.0%} of Gross Return",
        PERIOD,
    )
    table(page, R.compliance(m), LEFT, Inches(1.75), HALF, 10, 0.29)
    table(page, R.costs(m), RIGHT, Inches(1.75), HALF, 10, 0.29)
    table(page, R.legs(m), LEFT, Inches(4.8), WIDTH, 10, 0.29)

    # 8. Discussion.
    page = slide(
        deck,
        "What Worked, What Did Not, and What Comes Next",
        "January 2021 to August 2026. Total returns after all modelled costs, position P&L before "
        "costs",
    )
    items = [tuple(line.split(": ", 1)) if ": " in line else line for line in discussion(R, m)]
    items = [(lead + ".", rest[:1].upper() + rest[1:]) for lead, rest in items]
    text(page, items, LEFT, Inches(1.65), Inches(5.75), Inches(5.3), 11, gap=6)
    chart(page, "pnl_contributors", Inches(6.55), Inches(1.7), Inches(6.18), Inches(5.2))

    net = PERIOD
    for title, subtitle, builds in (
        (
            "Everything We Tried, and What Came of It",
            "Every test as recorded when it ran. Information ratios after all modelled costs",
            [R.tried],
        ),
        (
            "Costs, Capacity and Stress Tests",
            f"{net}. Stress windows use daily returns, and the 2020 windows come before the test",
            [R.implementation, R.stress],
        ),
        (
            "Neutrality, Monthly and Daily",
            f"{net}. Daily figures cover January 2021 to December 2025",
            [R.drift, R.daily],
        ),
        (
            "The AI Agents, and the Firewall Against Recall",
            "Agent answers from 2015 to 2026. Information coefficients against next month's return",
            [R.agents, R.firewall],
        ),
        (
            "The Biggest Winners and Losers, Explained by Our Agent",
            "Position P&L from January 2021 to August 2026, before costs, as a share of NAV",
            [R.explained],
        ),
        (
            "Robustness Checks",
            "After all modelled costs. 2016 to 2020 is a historical check, not out of sample",
            [R.halves, R.clean, R.placebo],
        ),
    ):
        page = slide(deck, title, subtitle, section="Appendix")
        top = Inches(1.65)
        for build in builds:
            top = table(page, renamed(build(m)), LEFT, top, WIDTH, 9.5, 0.25)
            top += Inches(0.12)
        if build is R.explained:
            text(page, [slips()], LEFT, top, WIDTH, Inches(0.6), 10, MUTED)
        if build is R.placebo:
            text(page, [no_interest()], LEFT, top, WIDTH, Inches(0.4), 10, MUTED)

    page = slide(
        deck,
        "The Machine Learning",
        "Helper models scored a year ahead, 2018-2025. Stock-picking model and portfolios out of "
        "sample, 2021 to August 2026, after all modelled costs",
        section="Appendix",
    )
    below = table(page, R.teachers(m), LEFT, Inches(1.65), WIDTH, 9.5, 0.26)
    table(page, R.scorer(m), LEFT, below + Inches(0.25), Inches(3.6), 9.5, 0.26)
    table(page, R.models(m), Inches(4.5), below + Inches(0.25), Inches(8.23), 9.5, 0.26)

    page = slide(
        deck,
        "Where the Return Came From",
        f"{net}. Factors and the yearly split on net return, signals on gross return",
        section="Appendix",
    )
    below = table(page, R.factors(m), LEFT, Inches(1.6), HALF, 9, 0.22)
    table(page, R.styles(m), LEFT, below, HALF, 9, 0.22)
    signals = R.attribution(m)
    for code, name in NAMES.items():
        signals = signals.replace(f"`{code}`", name[:1].upper() + name[1:])
    table(page, signals, RIGHT, Inches(1.65), HALF, 9.5, 0.27)

    page = slide(
        deck,
        "The Agents' Prompts",
        "The system prompt each local model ran with, punctuation lightly edited. Exact text in "
        "prompts/agents/",
        section="Appendix",
    )
    left, right = prompts()
    text(page, left, LEFT, Inches(1.6), HALF, Inches(5.4), 8.5, gap=3.5)
    text(page, right, RIGHT, Inches(1.6), HALF, Inches(5.4), 8.5, gap=3.5)

    page = slide(
        deck,
        "Tools, Data and How to Run It",
        "The devil's advocate's tools as the model received them, and what the portfolio was built "
        "from",
        section="Appendix",
    )
    tools = paths.read_json(paths.EXHIBITS / "agents" / "tools.json")
    rows = ["| Tool | What It Returns | Arguments |", "|---|---|---|"]
    VERBATIM.update(t["name"] for t in tools["critic"])
    VERBATIM.update(k for t in tools["critic"] for k in t["parameters"].get("properties", {}))
    for item in tools["critic"]:
        args = item["parameters"].get("properties", {})
        extra = dict(critiques=", each a target, claim and severity")
        shown = ", ".join(f"{k} ({v.get('type', '')}{extra.get(k, '')})" for k, v in args.items())
        rows.append(f"| {item['name']} | {item['description']} | {shown or 'none'} |")
    below = table(page, "\n".join(rows), LEFT, Inches(1.65), WIDTH, 10, 0.28)
    text(
        page,
        [
            (
                "Data.",
                "The organizer's stock panel and 8-K filings. We also used WRDS data: CRSP "
                "delistings, daily prices and quotes, Compustat report dates and short interest, "
                "and I/B/E/S price targets. From public sources, FRED's T-bill and S&P 500, "
                "Kenneth French's factors and SEC EDGAR company names. Everything is joined on "
                "PERMNO and month.",
            ),
            (
                "Names.",
                "Every holding's ticker and company name, with its dated source, is in "
                "submission/exhibits/labels.csv.",
            ),
            (
                "Run it.",
                "pip install uv, then uv run MAIN.py. On its own it checks our files against the "
                "brief. With the organizer's three data files beside it, it rebuilds the portfolio "
                "within 0.01 of our IR without our WRDS data (0.728 against 0.736 in our test). "
                "MAIN.py holds no organizer data and no raw WRDS data. It carries our outputs "
                "(holdings, returns, exhibits, predicted betas, borrow tiers) and public FRED and "
                "French series, so every number can be checked.",
            ),
        ],
        LEFT,
        below + Inches(0.3),
        WIDTH,
        Inches(2.6),
        13,
        gap=10,
    )

    OUT.parent.mkdir(exist_ok=True)
    deck.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(deck.slides)} slides")


if __name__ == "__main__":
    main()
