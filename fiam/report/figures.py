# Every finals chart, drawn once into out/figures for report and deck.

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from fiam import book as P  # noqa: E402
from fiam import v2  # noqa: E402
from fiam.paths import read_json as load  # noqa: E402
from fiam.report.charts import ALT, BENCH, INK, MUTED, NEG, OURS  # noqa: E402

# Slide-sized type in the deck's font, so charts read from the back row.
matplotlib.rcParams.update(
    {
        "font.family": ["Calibri", "DejaVu Sans"],
        "font.size": 13,
        "axes.titlesize": 16,
        "axes.labelsize": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "legend.fontsize": 12,
    }
)
FIGURES = Path("out") / "figures"
PAGES = v2.OUT
CAPS = ["$1M", "$10M", "$100M", "$500M", "$1B", "$5B"]
BOOKS = {"v1": OURS, "v2": ALT, "v2a": "#2E8B57", "v2-pass": "#B07D2B", "v3": "#8A7FB5"}
BOOKS["final v3"] = INK
# Charted books: shipped, two benchmarks and the chosen one.
SHOWN = ("v1", "v2", "v2-pass", "final v3")
# What each book is called on a slide.
LABELS = {
    "v1": "First book",
    "v2": "Built for size",
    "v2-pass": "Short rule only",
    "final v3": "Final book",
}
FINAL = PAGES / "final_exhibits"


# Saves a figure for deck and report in one place at one resolution.
def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# The house look: no top or right spine, a left title, a muted y label.
def tidy(ax, title: str = "", ylabel: str = "") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    if title:
        ax.set_title(title, color=INK, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED)


# Log fund-size axis, $500M unlabelled as it sits too close to $1B.
def log_capital(ax) -> None:
    ax.set_xscale("log")
    ax.set_xticks(list(v2.CAPITALS))
    ax.set_xticklabels(["" if c == "$500M" else c for c in CAPS])
    ax.minorticks_off()


# Yearly dollars over cash and IR by fund size, every book, 2021-2026.
def capacity() -> None:
    report = load(PAGES / "capacity.json").get("books", {})
    if not report:
        return
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 4))
    for name, entry in report.items():
        if name not in SHOWN:
            continue
        rows = entry["record"]
        caps = [r["capital"] for r in rows]
        # The final book drawn heavier, the benchmarks beside it.
        style = dict(marker="o", color=BOOKS.get(name, MUTED), lw=3 if name == "final v3" else 1.6)
        left.plot(caps, [r["dollars"] / 1e6 for r in rows], label=LABELS[name], **style)
        right.plot(caps, [r["information_ratio"] for r in rows], **style)
    for ax in (left, right):
        log_capital(ax)
        ax.axhline(0, color=MUTED, lw=0.8)
    left.set_yscale("symlog", linthresh=10)
    tidy(left, "Dollars a year over cash, $M")
    tidy(right, "IR against cash plus 4%")
    left.legend(frameon=False)
    save(fig, "capacity")


# The chosen book by fund size: IR, beta, drawdown and volatility.
def final_book() -> None:
    scored = load(PAGES / "evidence.json").get("v3", {})
    sizes = [c for c in v2.CAPITALS if f"{c:.0e}".replace("+0", "") in scored]
    if not sizes:
        return
    panels = (
        ("information_ratio", "IR", 1),
        ("beta_realized", "Beta to the S&P 500", 1),
        ("max_drawdown_total", "Worst drawdown, %", 100),
        ("volatility_annual", "Volatility a year, %", 100),
    )
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.7))
    for ax, (key, title, scale) in zip(axes, panels):
        for name in SHOWN:
            if name not in scored[f"{sizes[0]:.0e}".replace("+0", "")]["books"]:
                continue
            values = [
                scored[f"{c:.0e}".replace("+0", "")]["books"][name][key] * scale for c in sizes
            ]
            style = dict(marker="o", color=BOOKS[name], lw=3 if name == "final v3" else 1.6)
            ax.plot(sizes, values, label=LABELS[name], **style)
        log_capital(ax)
        ax.axhline(0, color=MUTED, lw=0.8)
        if key == "beta_realized":
            ax.axhspan(-0.1, 0.1, color=INK, alpha=0.06)
        tidy(ax, title)
    axes[0].legend(frameon=False)
    fig.tight_layout()
    save(fig, "final_book")


# Our long and short weight in the AI crowd's favourites, each month.
def signature() -> None:
    from fiam.report.animation import our_run

    data = load(PAGES / "crowd_lab.json").get(f"{our_run()} record", {}).get("signature")
    if not data:
        return
    frame = pd.DataFrame(data).T
    frame.index = pd.to_datetime(frame.index)
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(frame["long"], color=OURS, label="Our long weight in its top 10%", lw=2)
    ax.plot(frame["short"], color=NEG, label="Our short weight in its top 10%", lw=2)
    ax.axhline(0.10, color=MUTED, ls="--", lw=1, label="Chance")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    tidy(ax, "A model of the AI crowd, fitted to its votes, scores every month from 2021")
    ax.legend(frameon=False, ncol=3, loc="upper left")
    save(fig, "crowd_signature")


# The 30 retail agents' pick correlations by group, showing a few herds.
def network() -> None:
    net = load(PAGES / "crowd_insights.json").get("network")
    if not net:
        return
    corr, groups = np.array(net["corr"]), np.array(net["groups"])
    order = np.argsort(groups, kind="stable")
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.imshow(corr[np.ix_(order, order)], cmap="Blues", vmin=0, vmax=0.6)
    edges = np.flatnonzero(np.diff(groups[order])) + 0.5
    for e in edges:
        ax.axhline(e, color="white", lw=2)
        ax.axvline(e, color="white", lw=2)
    ax.set_xticks([])
    ax.set_yticks([])
    tidy(ax, f"30 AI investors, {len(set(groups))} groups")
    save(fig, "crowd_network")


# The copycat test on the book the deck shows, else the shipped one.
def copycat_test() -> dict:
    from fiam.report.animation import our_run

    insights = load(PAGES / "crowd_insights.json")
    return insights.get(f"book {our_run()}", insights).get("copycat_test", {})


# How often copycat groups match our longs and shorts, against chance.
def copycats() -> None:
    test = copycat_test()
    if not test:
        return
    names = {"v1": "our recipe", "brief_2026": "the 2026 brief", "case_2025": "the 2025 case"}
    fig, ax = plt.subplots(figsize=(7, 3.8))
    x = np.arange(len(test))
    for i, (key, label, colour) in enumerate(
        (
            ("buys_our_longs", "Buys our longs", OURS),
            ("shorts_our_shorts", "Shorts our shorts", NEG),
        )
    ):
        values = [t[key] for t in test.values()]
        ax.bar(x + (i - 0.5) * 0.38, values, 0.36, color=colour, label=label)
    ax.axhline(1, color=MUTED, ls="--", lw=1, label="Chance")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Given {names.get(k, k)}" for k in test])
    tidy(ax, "AI copycats against chance, where 1 is chance")
    ax.set_ylim(
        0, max(t[k] for t in test.values() for k in ("buys_our_longs", "shorts_our_shorts")) * 1.25
    )
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.0))
    save(fig, "copycats")


# Today's books through past crises: same-name replays of both books.
def crises() -> None:
    stress = load(PAGES / "stress.json")
    rows = stress.get("v1", {}).get("crises", {})
    if not rows:
        return
    names = sorted(rows, key=lambda n: rows[n].get("loss") or 0.0)
    v1 = [rows[n].get("loss") or 0.0 for n in names]
    fig, ax = plt.subplots(figsize=(9, 7))
    y = np.arange(len(names))
    books = [("v1", v1)] + [
        (book, [stress[book]["crises"].get(n, {}).get("loss") or 0.0 for n in names])
        for book in ("v2", "final v3")
        if book in stress
    ]
    width = 0.8 / len(books)
    for i, (book, losses) in enumerate(books):
        shift = (len(books) - 1) / 2 - i
        ax.barh(y + shift * width, losses, width, color=BOOKS[book], label=LABELS[book])
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    tidy(ax, f"Our books through {len(names)} past crises, return over each window")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "crises")


# Where machine learning earned its place, where not, and what we did.
def ml_scoreboard() -> None:
    params, vol = load(Path("frozen") / "v2_params.json"), load(Path("frozen") / "vol_check.json")
    errors = params.get("beta_errors", {})
    if not errors or not vol:
        return
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.6))
    beta = {"60-month": errors["beta_60m"], "LightGBM": errors["learned"], "Welch": errors["welch"]}
    a.bar(list(beta), list(beta.values()), color=[BENCH, OURS, ALT])
    tidy(a, "Beta forecast error before 2021, lower is better")
    years = list(vol["qlike_by_year"])
    x = np.arange(len(years))
    b.bar(
        x - 0.2, [vol["qlike_by_year"][y]["lgbm"] for y in years], 0.4, color=OURS, label="LightGBM"
    )
    b.bar(x + 0.2, [vol["qlike_by_year"][y]["har"] for y in years], 0.4, color=BENCH, label="HAR")
    b.set_xticks(x)
    b.set_xticklabels(years)
    tidy(b, "Volatility forecast loss, lower is better")
    b.legend(frameon=False)
    save(fig, "ml_scoreboard")


# A saved copycat decision rebuilt from data, its prompt hash checked.
def receipt() -> None:
    import hashlib

    from fiam import book as P
    from fiam import data
    from fiam import mandate as M
    from fiam.agents import crowd_lab as L
    from fiam.agents import harness as H
    from fiam.report.animation import our_run

    log = H.RUNS / "crowdlab_copycat.jsonl"
    # The card is rebuilt from data. Without it the saved receipt stands.
    if not log.exists() or not data.MANIFEST.exists():
        return
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    month = max(r["eom"] for r in rows)
    row = next(r for r in rows if r["eom"] == month and r["agent"] == 0 and r["card"] == 0)
    agent, eom = L.copycat_agents()[0], pd.Timestamp(month)
    frame = L.universe()
    card = L.cards(frame[frame["eom"] == eom], agent["seed"], eom)[0]
    names = L.labels()
    text, codes = L.table(card, agent["columns"], names)
    code = dict(zip(card["permno"].tolist(), codes))
    chosen = [*row["picked"], *row["shorted"]]
    blank = pd.DataFrame(dict(PERMNO=chosen, eom=eom, Date=eom, TICKER=pd.NA, COMPANY_NAME=pd.NA))
    known = P.fill_labels(blank, P.load_panel()).set_index("PERMNO")
    held = pd.read_parquet(PAGES / our_run() / "record" / "holdings.parquet")
    ours = held[pd.to_datetime(held["eom"]) == eom].set_index("permno")["weight"]
    manifest = load(H.RUNS / "crowdlab_copycat.manifest.json")

    # One code's stock unmasked: ticker, name and how our book holds it.
    def reveal(permno: int, side: str) -> dict:
        weight = ours.get(permno, 0.0)
        label = known.loc[permno] if permno in known.index else {}
        return dict(
            code=code[permno],
            side=side,
            ticker=str(label.get("TICKER", "")),
            name=P.display_name(label.get("COMPANY_NAME", "")),
            ours="long" if weight > 0 else "short" if weight < 0 else "not held",
        )

    shown = agent["columns"][:5]
    out = dict(
        month=month,
        recipe=M.load(M.TEMPLATES / "v1.json").strategy_text,
        columns=[names[c] for c in shown],
        rows=[[codes[i], *map(int, card[shown].iloc[i])] for i in range(6)],
        size=[len(card), len(agent["columns"])],
        picks=[reveal(p, "buy") for p in row["picked"]]
        + [reveal(p, "short") for p in row["shorted"]],
        same_stocks=card["permno"].tolist() == row["shown"],
        hash_match=hashlib.sha256((agent["system"] + text).encode()).hexdigest()
        == row["prompt_sha256"],
        prompt_sha256=row["prompt_sha256"],
        model=manifest.get("model_file", ""),
        model_sha256=manifest.get("model_sha256", ""),
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    (FIGURES / "receipt.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


# The chosen book's forecast vol and top names' share of risk.
def final_risk() -> None:
    path = FINAL / "risk_months.csv"
    if not path.exists():
        return
    months = pd.read_csv(path, parse_dates=["eom"])
    table = pd.read_csv(FINAL / "risk_table.csv", parse_dates=["eom"])
    last = table[table["eom"] == table["eom"].max()].copy()
    last["share"] = last["weight"].abs() / last["weight"].abs().sum()
    top = last.sort_values("pctr", ascending=False).head(12).iloc[::-1]
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(13, 4.2), gridspec_kw=dict(width_ratios=[1.2, 1])
    )
    left.plot(
        months["eom"], months["corrected_vol_year"] * 100, color=INK, lw=2.4, label="Forecast"
    )
    left.plot(months["eom"], months["var_95"] * 100, color=NEG, lw=1.4, label="Monthly VaR at 95%")
    left.axhline(10, color=MUTED, lw=0.8, ls="--")
    left.legend(frameon=False)
    tidy(left, "Forecast volatility a year and monthly VaR, %")
    y = np.arange(len(top))
    named = top["ticker"].fillna(top["permno"].astype(str))
    labels = [f"{t} {'long' if w > 0 else 'short'}" for t, w in zip(named, top["weight"])]
    right.barh(y + 0.2, top["pctr"] * 100, 0.4, color=INK, label="Share of risk")
    right.barh(y - 0.2, top["share"] * 100, 0.4, color=ALT, label="Share of the book")
    right.set_yticks(y)
    right.set_yticklabels(labels)
    right.legend(frameon=False, loc="lower right")
    tidy(right, f"Largest risk contributors, {last['eom'].max():%B %Y}, %")
    fig.tight_layout()
    save(fig, "final_risk")


# The chosen book's exposure per unit of gross to each style, monthly.
def final_exposures() -> None:
    path = FINAL / "style_exposures.csv"
    if not path.exists():
        return
    styles = pd.read_csv(path, parse_dates=["eom"]).set_index("eom")
    colours = dict(size=MUTED, value=ALT, momentum="#B07D2B", low_vol=NEG, quality=INK)
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for name in styles:
        ax.plot(
            styles.index,
            styles[name],
            color=colours.get(name, OURS),
            lw=2,
            label=name.replace("_", " ").capitalize(),
        )
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    tidy(ax, "", "Exposure per unit of gross")
    save(fig, "final_exposures")


# The chosen book among 1,000 random lookalike books.
def edge_null() -> None:
    path = FINAL / "null_irs.csv"
    report = load(FINAL / "report.json").get("null", {})
    if not path.exists() or not report:
        return
    irs = pd.read_csv(path)["ir"]
    fig, ax = plt.subplots(figsize=(10, 3.9))
    ax.hist(irs, bins=40, color=ALT, alpha=0.85, label=f"{len(irs):,} random large-cap books")
    ax.axvline(report["final_ir"], color=INK, lw=3, label="Final book")
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, loc="upper left")
    tidy(ax, "", "Books")
    ax.set_xlabel("IR against cash plus 4%, 2021 to August 2026, after costs", color=MUTED)
    save(fig, "edge_null")


# Every benchmark on one axis, what the money made, market to ours.
def ladder_rows() -> list[tuple]:
    report = load(FINAL / "report.json")
    if not report.get("null"):
        return []
    market = P.benchmarks().set_index("month")["mkt_rf"]
    book = pd.read_csv(
        PAGES / v2.Settings(v2.final_three(), 1e7).name / "record" / "returns.csv",
        parse_dates=["holding_month"],
    )
    sp500 = P.information_ratio(market.reindex(book["holding_month"]).dropna())
    naive = report.get("naive", {})
    large = report.get("large", {})
    big = next((v for k, v in large.items() if "@1e7" in k), {})
    rows = [
        ("S&P 500, not market neutral", sp500, MUTED),
        ("Random large-cap books, average", report["null"]["mean"], ALT),
        (
            "Equal weights on our score",
            naive.get("naive_equal_model@1e7", {}).get("information_ratio"),
            ALT,
        ),
        (
            "Equal weights on our own names",
            naive.get("naive_equal_holdings@1e7", {}).get("information_ratio"),
            ALT,
        ),
        (
            "Our favourite names held still",
            naive.get("favourites_held@1e7", {}).get("information_ratio"),
            "#B07D2B",
        ),
        ("Our rule on the 500 largest only", big.get("information_ratio"), OURS),
        ("Final book", report["null"]["final_ir"], INK),
    ]
    return [r for r in rows if r[1] is not None]


# Draws the ladder rows as bars of IR over cash plus 4% at $10M.
def edge_ladder() -> None:
    rows = ladder_rows()
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(rows))
    ax.barh(y, [r[1] for r in rows], color=[r[2] for r in rows])
    for i, (_, value, _) in enumerate(rows):
        ax.text(
            value + (0.02 if value >= 0 else -0.02),
            i,
            f"{value:.2f}",
            va="center",
            ha="left" if value >= 0 else "right",
            color=INK,
            fontsize=12,
        )
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.axvline(0, color=MUTED, lw=0.8)
    tidy(ax, "", "")
    ax.set_xlabel("IR against cash plus 4% at $10M, 2021 to August 2026, after costs", color=MUTED)
    save(fig, "edge_ladder")


# What the optimizer adds: the chosen book vs equal weights.
def naive() -> None:
    report = load(FINAL / "report.json").get("naive", {})
    if not report:
        return
    final = {}
    for tag in ("1e7", "1e9"):
        cap = float(tag.replace("e", "e+"))
        name = v2.Settings(v2.final_three(), cap).name
        final[tag] = load(PAGES / name / "record" / "stats.json")
    books = [
        ("Equal weights on our score", "naive_equal_model", ALT),
        ("Equal weights on our own names", "naive_equal_holdings", "#B07D2B"),
        ("Final book", None, INK),
    ]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(2)
    for i, (label, key, colour) in enumerate(books):
        values = [
            (final[tag] if key is None else report.get(f"{key}@{tag}", {})).get(
                "information_ratio", 0.0
            )
            for tag in ("1e7", "1e9")
        ]
        ax.bar(x + (i - 1) * 0.27, values, 0.27, color=colour, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(["$10M", "$1B"])
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, fontsize=11)
    tidy(ax, "", "IR against cash plus 4%")
    save(fig, "naive")


# Draws every chart in order and lists the figure files that exist.
def draw_all() -> list[str]:
    for chart in (
        capacity,
        final_book,
        signature,
        network,
        copycats,
        crises,
        final_risk,
        final_exposures,
        edge_null,
        edge_ladder,
        naive,
        ml_scoreboard,
        receipt,
    ):
        chart()
    return sorted(p.stem for p in FIGURES.glob("*.png"))


if __name__ == "__main__":
    print(draw_all())
