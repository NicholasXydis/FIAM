# Research charts from submission/exhibits/ to figures/ after charts.py.

import textwrap

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from fiam import paths
from fiam.report.charts import (
    ALT,
    BENCH,
    MARKET,
    MUTED,
    NEG,
    OURS,
    caption,
    figure_caption,
    save,
    style,
    xlabel,
)

EXHIBITS = paths.EXHIBITS

# A line break inside a caption.
BR = chr(10)

# One look per model in every chart: colour, width, dash and name.
MODELS = {
    "composite": (OURS, 2.4, "-", "12-signal composite"),
    "nn3": (MARKET, 1.4, "--", "Neural net (NN3)"),
    "lgbm": (ALT, 1.4, "-.", "LightGBM"),
    "enet": (BENCH, 1.6, ":", "ElasticNet"),
}


# The IC trap in one picture. Every model's decile curve on one axis.
def decile_curves() -> None:
    metrics = paths.read_json(EXHIBITS / "ml_metrics.json")
    table = pd.DataFrame(metrics["deciles"]).T
    book = paths.read_json(paths.METRICS)
    deciles = [c for c in table.columns if c.startswith("d")]

    # Only the four shipped models. Seed runs belong in their own exhibit.
    table = table.loc[[name for name in MODELS if name in table.index]]

    # Curves show each model ranks, the scatter that ranking is not earning.
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.5, 4.3), width_ratios=[1.35, 1])

    for name, row in table.iterrows():
        colour, width, dash, display = MODELS[name]
        left.plot(
            range(1, len(deciles) + 1),
            row[deciles].to_numpy() * 100,
            color=colour,
            linewidth=width,
            linestyle=dash,
            marker="o",
            markersize=3,
            label=display,
        )
    left.axhline(0, color="black", linewidth=0.8)
    left.legend(fontsize=8, frameon=False)
    style(left, "Every model can rank the cross-section", "Annualized excess return (%)")
    xlabel(left, "Decile, 10 is the model's best-rated stocks")

    for name, row in table.iterrows():
        colour, _, _, display = MODELS[name]
        spread = row["top_minus_bottom"] * 100
        ratio = (
            book["performance"]["information_ratio"]
            if name == "composite"
            else metrics[name]["information_ratio"]
        )
        right.scatter([spread], [ratio], s=130, color=colour, zorder=3)
        right.annotate(
            display,
            (spread, ratio),
            xytext=(0, 12),
            textcoords="offset points",
            fontsize=8,
            ha="center",
            color=colour,
        )
    right.axhline(0, color="black", linewidth=0.8)
    right.set_ylim(-0.85, 1.25)
    style(right, "Only one of them earns anything", "IR after constraints and costs")
    xlabel(right, "Raw top-minus-bottom decile spread (pp)")

    lgbm = metrics["lgbm"]
    caption(
        left,
        "Jan 2021 to Aug 2026. LightGBM's raw spread is the widest of the four and its IR is "
        "still the second worst: ranking skill is not the binding constraint. It trades at "
        f"{lgbm['turnover']:.0%} monthly turnover on {lgbm['gross_annual']:.1%} gross, so costs "
        "take more than it earns.",
    )
    save(fig, "decile_curves")


# Where the money goes. A: gross to net by cost line. B: costs by year.
def costs() -> None:
    pack = paths.read_json(EXHIBITS / "pack.json")
    parts, even = pack["costs"]["components"], pack["costs"]["break_even"]
    split = pack["subperiod"]
    gross = split["full_2021_2026"]["gross_annual"]
    names = ["commission", "spread", "impact", "borrow", "financing"]
    labels = ["gross", "commission", "spread", "impact", "borrow", "financing", "net"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2))

    running = gross * 100
    left.bar(0, running, color=OURS, width=0.6)
    left.text(0, running + 0.4, f"{running:.1f}", ha="center", fontsize=8)
    for i, key in enumerate(names, start=1):
        drop = parts[key] * 100
        left.bar(i, drop, bottom=running - drop, color=NEG, width=0.6)
        left.text(i, running + 0.4, f"-{drop:.2f}", ha="center", fontsize=8, color=NEG)
        running -= drop
    left.bar(len(labels) - 1, running, color=OURS, width=0.6)
    left.text(len(labels) - 1, running + 0.4, f"{running:.1f}", ha="center", fontsize=8)
    left.set_xticks(range(len(labels)))
    left.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    style(left, "A. From gross to net, one cost at a time", "% a year")

    # Gross up, cost down, net a marker. Stacked, they read as one quantity.
    by_year = split["by_year"]
    years = sorted(by_year, key=int)
    year_gross = [by_year[y]["gross"] * 100 for y in years]
    year_cost = [by_year[y]["cost"] * 100 for y in years]
    right.bar(years, year_gross, color=OURS, label="gross return", width=0.62)
    right.bar(years, [-c for c in year_cost], color=NEG, label="cost", width=0.62)
    right.scatter(
        years,
        [g - c for g, c in zip(year_gross, year_cost)],
        s=70,
        color="black",
        zorder=3,
        label="net return",
    )
    right.axhline(0, color="black", linewidth=0.8)
    # Headroom so the legend sits above the tallest bar rather than on it.
    right.set_ylim(top=max(year_gross) * 1.25)
    right.legend(fontsize=8, frameon=False, ncols=3, loc="upper right")
    style(right, "B. Costs are fixed; the gross they come out of is not", "% of NAV")

    figure_caption(
        fig,
        f"Jan 2021 to Aug 2026; 2026 is January to August. Rates follow IBKR, the SEC and FINRA; "
        f"spread, impact and borrow are models, not observed fills. Costs would have to reach "
        f"{even['break_even_annual_cost']:.1%} a year, {even['break_even_multiple']:.1f} times our "
        f"{even['current_annual_cost']:.1%}, before active return over T-bill + 4% is zero.",
    )
    save(fig, "costs")


# A: variance the factors explain. B: each free loading, with its t.
def factor_attribution() -> None:
    risk = paths.read_json(EXHIBITS / "pack.json")["risk"]
    d, e = risk["attribution"], risk["five_factor_momentum"]
    names = {
        "mkt_rf": "market",
        "smb": "size",
        "hml": "value",
        "rmw": "profitability",
        "cma": "investment",
        "mom": "momentum",
    }

    fig, (left, right) = plt.subplots(1, 2, figsize=(10.5, 4.2), width_ratios=[1, 1.35])

    explained = e["explained_by_all_three"] * 100
    left.barh(
        ["residual", "explained"],
        [e["residual_share"] * 100, explained],
        color=[OURS, BENCH],
        height=0.55,
    )
    for y, value in enumerate([e["residual_share"] * 100, explained]):
        left.text(value + 1.5, y, f"{value:.1f}%", va="center", fontsize=9)
    left.set_xlim(0, 100)
    style(left, "A. Share of variance, six factors", "")
    xlabel(left, "Share of monthly return variance (%)")

    # No red here. These are exposures, not losses, and red means losses.
    betas = [e["betas"][k] for k in names]
    right.barh(list(names.values()), betas, color=BENCH, height=0.55)
    for y, key in enumerate(names):
        value, t = e["betas"][key], e["t_stats"][key]
        right.text(
            value + (0.02 if value >= 0 else -0.02),
            y,
            f"{value:+.2f} (t {t:+.1f})",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color=MUTED,
        )
    right.axvline(0, color="black", linewidth=0.8)
    right.invert_yaxis()
    span = max(abs(b) for b in betas)
    right.set_xlim(-span * 1.9, span * 1.9)
    style(right, "B. Loadings, none of them constrained", "")
    xlabel(right, "Regression loading, HAC t in brackets")

    figure_caption(
        fig,
        f"{e['months']} monthly observations to Jul 2026, Fama-French five factors plus momentum, "
        f"HAC errors. Alpha is {e['alpha_annual']:.1%} a year (t = {e['alpha_t']:.2f}) against "
        f"{d['alpha_annual']:.1%} (t = {d['alpha_t']:.2f}) with three factors. Size, value and "
        "profitability loadings are real and disclosed, not hedged: constraining every factor "
        "leaves nothing to earn.",
    )
    save(fig, "factor_attribution")


# Two panels, as the null is only zero before costs. Net IR misleads.
def placebo_lab() -> None:
    d = paths.read_json(EXHIBITS / "placebo_lab.json")
    null = d["permutation_null"]
    shipped = d["shipped"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel A, gross, where a shuffled score should earn nothing.
    left.hist(
        [x * 100 for x in null["all_gross"]],
        bins=22,
        color=BENCH,
        alpha=0.6,
        edgecolor="white",
        linewidth=0.6,
    )
    left.set_ylabel("Number of runs", fontsize=9, color=MUTED)
    left.axvline(null["gross_annual_mean"] * 100, color=MUTED, linewidth=1.4, linestyle=":")
    left.axvline(shipped["gross_annual"] * 100, color=OURS, linewidth=2.8)
    left.annotate(
        f"Shipped{BR}{shipped['gross_annual']:.1%}",
        xy=(shipped["gross_annual"] * 100, 0.62),
        xycoords=("data", "axes fraction"),
        xytext=(-10, 0),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        weight="bold",
        color=OURS,
    )
    # Above the tallest bar, as beside the line overlapped the distribution.
    left.annotate(
        f"Shuffled {null['gross_annual_mean']:+.2%}",
        xy=(null["gross_annual_mean"] * 100, 1.02),
        xycoords=("data", "axes fraction"),
        xytext=(0, 0),
        textcoords="offset points",
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )
    style(left, "A. Before costs, a shuffled score earns nothing", "")
    xlabel(left, "Gross return, % a year")

    # B: net IR. The null sits far below zero, the cost of churn.
    right.hist(null["all_irs"], bins=22, color=BENCH, alpha=0.6, edgecolor="white", linewidth=0.6)
    right.axvline(shipped["net_ir"], color=OURS, linewidth=2.8)
    right.annotate(
        f"Shipped{BR}{shipped['net_ir']:+.2f}",
        xy=(shipped["net_ir"], right.get_ylim()[1] * 0.66),
        xytext=(-10, 0),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        weight="bold",
        color=OURS,
    )
    style(right, "B. After costs, churn pushes it far below", "Number of runs")
    xlabel(right, "Net information ratio")

    left.text(
        0,
        -0.40,
        textwrap.fill(
            f"{null['draws']} runs, scores shuffled within sector and liquidity bucket, so only "
            "the link between score and return is broken and the structure the constraints act "
            f"on survives. The null cannot centre on zero after costs: a random ranking re-sorts "
            f"the book every month, trading at {null['turnover_mean']:.0%} one-way against our "
            f"{shipped['turnover']:.0%} and paying our rates for it. The shipped book sits at the "
            f"{null['shipped_percentile']:.0f}th percentile. Jan 2021 to Aug 2026.",
            width=132,
        ),
        transform=left.transAxes,
        fontsize=7.5,
        color=MUTED,
        va="top",
    )
    save(fig, "placebo_lab")


# Which signals earned the gross return, and what the twelve leave out.
def signal_attribution() -> None:
    d = paths.read_json(EXHIBITS / "pack.json")["attribution"]
    full = d["full"]
    names = sorted(
        (k for k in full if k not in ("residual", "explained_total")),
        key=lambda k: full[k]["contribution_annual"],
    )
    values = [full[k]["contribution_annual"] * 100 for k in names]

    fig, ax = plt.subplots(figsize=(8, 5.0))
    # Losses red, gains ours, the residual grey since it is no signal's.
    ax.barh(names, values, color=[NEG if v < 0 else OURS for v in values], height=0.6)
    residual = full["residual"]["contribution_annual"] * 100
    ax.barh(["not explained by the twelve"], [residual], color=BENCH, height=0.6)
    for y, value in enumerate([*values, residual]):
        ax.text(
            value + (0.1 if value >= 0 else -0.1),
            y,
            f"{value:+.1f}",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color=MUTED,
        )
    ax.axvline(0, color="black", linewidth=0.8)
    style(ax, "Where the gross return came from", "")
    xlabel(ax, "Contribution to gross return, % a year")
    caption(
        ax,
        f"Jan 2021 to Aug 2026, {d['months']} months, before costs. Each month, a joint "
        "cross-sectional regression gives each signal's pure return; our exposure times that "
        "return is its contribution. Signals are correlated, so no single bar is precise.",
    )
    save(fig, "signal_attribution")


# Draws every research chart, skipping any whose exhibit is not built.
def main() -> None:
    print("research charts:")
    for draw in (
        decile_curves,
        costs,
        factor_attribution,
        placebo_lab,
        signal_attribution,
    ):
        try:
            draw()
        except FileNotFoundError as exc:
            # That script has not run yet, no reason to lose the other charts.
            print(f"  skipped {draw.__name__}, {exc.filename} not built yet")
        except KeyError as exc:
            # An artifact with a model this chart does not know. Say so, not fail.
            print(f"  skipped {draw.__name__}, no entry for {exc}")


if __name__ == "__main__":
    main()
