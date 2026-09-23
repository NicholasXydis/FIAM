# The research charts. Reads submission/exhibits/, writes submission/figures/.

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from charts import (
    ALT,
    BENCH,
    MARKET,
    MUTED,
    NEG,
    OURS,
    SQUARE,
    caption,
    save,
    style,
    xlabel,
)

EXHIBITS = Path("submission/exhibits")

# A line break inside a caption.
BR = chr(10)


# The IC trap in one picture. Every model's decile curve on one axis.
def decile_curves() -> None:
    table = pd.read_csv(EXHIBITS / "decile_tables.csv", index_col=0)
    metrics = json.loads((EXHIBITS / "ml_metrics.json").read_text())
    book = json.loads(Path("submission/metrics.json").read_text())
    deciles = [c for c in table.columns if c.startswith("d")]

    # Display names, so a deck reader does not have to know our script names.
    styles = {
        "composite": (OURS, 2.4, "-", "12-signal composite"),
        "nn3": (MARKET, 1.4, "--", "Neural net (NN3)"),
        "lgbm": (ALT, 1.4, "-.", "LightGBM"),
        "enet": (BENCH, 1.4, ":", "ElasticNet"),
    }

    # Only the four shipped models. The seed runs belong in their own exhibit.
    table = table.loc[[name for name in styles if name in table.index]]

    # Curves show each model can rank. The scatter shows ranking well is not earning well.
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.5, 4.3), width_ratios=[1.35, 1])

    for name, row in table.iterrows():
        colour, width, dash, display = styles.get(name, (BENCH, 1.2, "-", name))
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
        colour, _, _, display = styles.get(name, (BENCH, 1.2, "-", name))
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

    # Do not blame neutralization here. constraint_survival.png shows costs do it.
    caption(
        left,
        "Jan 2021 to Aug 2026. LightGBM's raw spread is the widest of the four and its IR is "
        "still the second worst: ranking skill is not the binding constraint. It trades at "
        "121% monthly turnover on 7.4% gross, so costs take more than it earns. See the "
        "constraint-survival exhibit for the stage-by-stage version.",
    )
    save(fig, "decile_curves")


# What a fixed-budget search found, and what it was worth in the period it never saw.
def search_control() -> None:
    # One source only. signal_discovery.json splits the window elsewhere, so never mix them.
    table = pd.read_csv(EXHIBITS / "subset_sweep.csv").dropna(subset=["ir_early", "ir_late"])
    correlation = table["ir_early"].corr(table["ir_late"])
    rank = int((table["ir_late"] > table.loc[table["ir_early"].idxmax(), "ir_late"]).sum() + 1)

    fig, ax = plt.subplots(figsize=SQUARE)
    # Every candidate, not just the winner. A cloud with no slope is the argument.
    ax.scatter(
        table["ir_early"],
        table["ir_late"],
        s=14,
        color=BENCH,
        alpha=0.45,
        edgecolors="none",
        label=f"all {len(table)} candidates",
    )
    picked = table.loc[table["ir_early"].idxmax()]
    ax.scatter(
        [picked["ir_early"]],
        [picked["ir_late"]],
        s=140,
        color=NEG,
        zorder=3,
        label="the one a search would pick",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.annotate(
        f"picked on the early window at {picked['ir_early']:+.2f},"
        + BR
        + f"earned {picked['ir_late']:+.2f} afterwards",
        (picked["ir_early"], picked["ir_late"]),
        xytext=(-12, 22),
        textcoords="offset points",
        fontsize=8,
        color=NEG,
        ha="right",
    )
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    style(ax, "Doing well where you looked predicts nothing", "IR in the sealed period")
    xlabel(ax, "IR in the window the search could see")
    caption(
        ax,
        f"Each point is one of the {len(table)} five-signal subsets, scored on 2021-22 and then "
        f"on 2023-26. Correlation between the two axes is {correlation:+.2f}, so the cloud has "
        f"no usable slope, and the pick ranked {rank} of {len(table)} in the sealed period.",
    )
    save(fig, "search_control")


# Where the gross went, year by year. Costs are flat, so thin years lose more of it.
def cost_drag() -> None:
    d = json.loads((EXHIBITS / "subperiod.json").read_text())["by_year"]
    years = sorted(d, key=int)
    gross = [d[y]["gross"] * 100 for y in years]
    cost = [d[y]["cost"] * 100 for y in years]
    net = [g - c for g, c in zip(gross, cost)]

    fig, ax = plt.subplots(figsize=SQUARE)
    # Gross up, cost down, net as a marker. Stacking them read as one quantity.
    ax.bar(years, gross, color=OURS, label="gross return", width=0.62)
    ax.bar(years, [-c for c in cost], color=NEG, label="cost", width=0.62)
    ax.scatter(years, net, s=70, color="black", zorder=3, label="net return")
    ax.axhline(0, color="black", linewidth=0.8)
    style(ax, "Costs are fixed; the gross return they come out of is not", "% of NAV")
    ax.legend(fontsize=8, frameon=False, ncols=3, loc="upper right")
    caption(
        ax,
        "Costs run near 4% of NAV every year. In 2021-22 that was a tenth of gross; "
        "in 2023-26 it was most of it.",
    )
    save(fig, "cost_drag")


# Trading less is the obvious fix. This is the measurement that says it does not work.
def turnover_frontier() -> None:
    d = json.loads((EXHIBITS / "turnover_sweep.json").read_text())
    turnover = [v["turnover"] * 100 for v in d.values()]
    ratios = [v["information_ratio"] for v in d.values()]
    fig, ax = plt.subplots(figsize=SQUARE)
    # Points, not a line. Each lambda is its own run, not a frontier we traced.
    ax.scatter(turnover, ratios, s=90, color=OURS, zorder=3)
    ax.scatter(
        [turnover[0]], [ratios[0]], s=170, color=OURS, zorder=4, edgecolors="white", linewidths=1.6
    )

    # The penalised points bunch up, so alternate labels above and below the line.
    for i, ((name, _), x, y) in enumerate(zip(d.items(), turnover, ratios)):
        penalty = name.split("_")[1]
        above = i % 2 == 0
        ax.annotate(
            "the shipped book" if i == 0 else f"λ = {penalty}",
            (x, y),
            fontsize=8,
            color=MUTED,
            xytext=(0, 11 if above else -17),
            textcoords="offset points",
            ha="center",
        )
    # Headroom so the labels never touch the frame.
    span = max(ratios) - min(ratios)
    ax.set_ylim(min(ratios) - span * 0.25, max(ratios) + span * 0.20)
    ax.set_xlim(0, max(turnover) * 1.15)

    style(ax, "Trading less costs more than it saves", "Information ratio")
    xlabel(ax, "One-way monthly turnover (%)")
    caption(
        ax,
        "Turnover penalty inside the shipped optimizer. Every penalised setting"
        + BR
        + "loses to the unpenalised book, and among themselves they are flat.",
    )
    save(fig, "turnover_frontier")


# How far every cost assumption can be wrong before the strategy stops clearing its hurdle.
def cost_ladder() -> None:
    d = json.loads((EXHIBITS / "cost_ladder.json").read_text())["break_even"]
    rungs = d["ladder"]
    costs = [v["annual_cost"] * 100 for v in rungs.values()]
    active = [v["active_annual"] * 100 for v in rungs.values()]
    fig, ax = plt.subplots(figsize=SQUARE)
    ax.plot(costs, active, color=OURS, marker="o", linewidth=1.6)
    ax.axhline(0, color=NEG, linewidth=1, linestyle="--")
    ax.axvline(
        d["current_annual_cost"] * 100,
        color=BENCH,
        linewidth=1,
        linestyle=":",
        label=f"our assumption, {d['current_annual_cost']:.1%}",
    )
    style(
        ax,
        "How wrong the cost model can be before the strategy stops working",
        "Active return over T-bill + 4% (% a year)",
    )
    xlabel(ax, "Total annual cost (% of NAV)")
    ax.legend(fontsize=8, frameon=False)
    caption(
        ax,
        f"Under our modelled cost schedule, costs would have to reach "
        f"{d['break_even_annual_cost']:.1%} a year, "
        f"{d['break_even_multiple']:.1f} times our assumption, before active return is zero.",
    )
    save(fig, "cost_ladder")


# Every five-signal subset on one axis, with ours marked. The case against selection.
def subset_histogram() -> None:
    table = pd.read_csv(EXHIBITS / "subset_sweep.csv")
    fig, ax = plt.subplots(figsize=SQUARE)
    ax.hist(table["ir_full"], bins=40, color=BENCH, alpha=0.75, edgecolor="white", linewidth=0.4)
    picked = table.loc[table["ir_early"].idxmax()]
    ax.axvline(
        picked["ir_full"],
        color=NEG,
        linewidth=1.6,
        label=f"best on the early window: {picked['ir_full']:.2f}",
    )
    ax.axvline(
        table["ir_full"].median(),
        color=OURS,
        linewidth=1.6,
        linestyle="--",
        label=f"median subset: {table['ir_full'].median():.2f}",
    )
    style(
        ax, f"All {len(table)} five-signal subsets, and why we did not choose", "Number of subsets"
    )
    xlabel(ax, "Information ratio over the full window")
    ax.legend(fontsize=8, frameon=False)
    caption(
        ax,
        f"Jan 2021 to Aug 2026. IR ranges {table['ir_full'].min():.2f} to "
        f"{table['ir_full'].max():.2f} purely on which five you pick, so we use all twelve.",
    )
    save(fig, "subset_histogram")


# Gross down to net, one cost line at a time. Judges ask where the money went.
def cost_waterfall() -> None:
    parts = json.loads((EXHIBITS / "cost_ladder.json").read_text())["components"]
    gross = json.loads((EXHIBITS / "subperiod.json").read_text())["full_2021_2026"]["gross_annual"]
    names = ["commission", "impact", "borrow_general_collateral", "borrow_hard_to_borrow", "spread"]
    labels = ["gross", "commission", "impact", "borrow GC", "borrow HTB", "spread", "net"]

    fig, ax = plt.subplots(figsize=SQUARE)
    running = gross * 100
    ax.bar(0, running, color=OURS, width=0.6)
    ax.text(0, running + 0.4, f"{running:.1f}", ha="center", fontsize=8)
    for i, key in enumerate(names, start=1):
        drop = parts[key] * 100
        ax.bar(i, drop, bottom=running - drop, color=NEG, width=0.6)
        ax.text(i, running + 0.4, f"-{drop:.2f}", ha="center", fontsize=8, color=NEG)
        running -= drop
    ax.bar(len(labels) - 1, running, color=OURS, width=0.6)
    ax.text(len(labels) - 1, running + 0.4, f"{running:.1f}", ha="center", fontsize=8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    style(ax, "From gross return to net, one cost at a time", "% a year")
    caption(
        ax,
        "Jan 2021 to Aug 2026. Every rate is a stated assumption, not observed "
        "execution data; the spread is a scaled estimator.",
    )
    save(fig, "cost_waterfall")


# What explains our return and what does not. The unexplained part is what we are paid for.
def factor_attribution() -> None:
    d = json.loads((EXHIBITS / "risk_decomposition.json").read_text())["attribution"]
    names = {"mkt_rf": "market", "smb": "size", "hml": "value"}

    # Two panels. The split adds to 100%, the per-factor terms do not. Never sum them.
    fig, (left, right) = plt.subplots(1, 2, figsize=(9.5, 4.2), width_ratios=[1, 1.35])

    explained = d["explained_by_all_three"] * 100
    left.barh(
        ["residual", "explained"],
        [d["residual_share"] * 100, explained],
        color=[OURS, BENCH],
        height=0.55,
    )
    for y, value in enumerate([d["residual_share"] * 100, explained]):
        left.text(value + 1.5, y, f"{value:.1f}%", va="center", fontsize=9)
    left.set_xlim(0, 100)
    style(left, "All three factors together", "")
    xlabel(left, "Share of variance (%)")

    per_factor = [d["individual_variance_contribution"][k] * 100 for k in names]
    # No red here. These are exposures, not losses, and red is only for losses.
    right.barh(list(names.values()), per_factor, color=[BENCH, MARKET, ALT], height=0.55)
    for y, value in enumerate(per_factor):
        right.text(value + 0.4, y, f"{value:.1f}%", va="center", fontsize=9)
    right.invert_yaxis()
    right.set_xlim(0, max(per_factor) * 1.25)
    style(right, "Each factor's own squared-beta term", "")
    xlabel(right, "Share of variance (%), does not sum to the left panel")

    caption(
        left,
        f"{d['months']} monthly observations to Jul 2026, HAC errors. Size loads "
        f"{d['betas']['smb']:+.2f} (t {d['t_stats']['smb']:.1f}) and value "
        f"{d['betas']['hml']:+.2f} (t {d['t_stats']['hml']:.1f}), both significant and neither "
        f"constrained. Alpha after all three is {d['alpha_annual']:.1%} a year, t = "
        f"{d['alpha_t']:.2f}, lower than the single-factor figure in the headline table.",
    )
    save(fig, "factor_attribution")


# Two panels. Prediction and portfolio are different metrics, never one line.
def constraint_survival() -> None:
    d = json.loads((EXHIBITS / "constraint_survival.json").read_text())
    names = {
        "composite": ("12-signal composite", OURS, 2.4, "-"),
        "nn3": ("Neural net (NN3)", MARKET, 1.4, "--"),
        "lgbm": ("LightGBM", ALT, 1.4, "-."),
        "enet": ("ElasticNet", BENCH, 1.6, ":"),
    }
    stages = d["predictive_stages"]
    labels = ["Raw score", "+ sector", "+ beta", "+ volatility"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.4))

    for model, (display, colour, width, dash) in names.items():
        pred = d["models"][model]["predictive"]
        left.plot(
            range(len(stages)),
            [pred[s]["decile_spread_annual"] * 100 for s in stages],
            color=colour,
            linewidth=width,
            linestyle=dash,
            marker="o",
            markersize=4,
            label=display,
        )
    left.axhline(0, color="black", linewidth=0.8)
    left.set_xticks(range(len(stages)))
    left.set_xticklabels(labels, fontsize=8)
    # Below the axis: inside the panel it covered the ElasticNet line at every width.
    left.legend(
        fontsize=8,
        frameon=False,
        ncol=4,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.19),
        columnspacing=1.1,
        handlelength=1.8,
    )
    style(left, "A. Neutralization does not destroy prediction", "Decile spread, % a year")
    xlabel(left, "Each step removes one exposure from the score")

    pstages = d["portfolio_stages"]
    plabels = [
        "Equal-weight",
        "+ optimizer," + BR + "name cap",
        "+ exposure" + BR + "constraints",
        "+ whole shares",
        "+ costs",
    ]
    for model, (display, colour, width, dash) in names.items():
        port = d["models"][model]["portfolio"]
        right.plot(
            range(len(pstages)),
            [port[s]["net_ir"] for s in pstages],
            color=colour,
            linewidth=width,
            linestyle=dash,
            marker="o",
            markersize=4,
            label=display,
        )
    right.axhline(0, color="black", linewidth=0.8)
    right.set_xticks(range(len(pstages)))
    right.set_xticklabels(plabels, fontsize=8, rotation=20, ha="right")
    style(right, "B. The cost stage is where they die", "Information ratio")
    xlabel(right, "Each step adds one construction choice to the one before")

    comp = d["models"]["composite"]["portfolio"]["after_costs"]
    lgbm = d["models"]["lgbm"]["portfolio"]["after_costs"]
    # Anchored to the axes. A figure offset drifts once bbox_inches="tight" crops.
    left.text(
        0,
        -0.42,
        textwrap.fill(
            "Neutralization raises every model's tradeable decile spread, so this is not a "
            "story about prediction. The composite clears its cost bill at "
            f"{comp['turnover']:.0%} monthly turnover on {comp['gross_annual']:.1%} gross. "
            f"LightGBM turns over {lgbm['turnover']:.0%} on {lgbm['gross_annual']:.1%} gross, "
            "so costs exceed everything it earned. Jan 2021 to Aug 2026, identical optimizer "
            "and cost model throughout.",
            width=132,
        ),
        transform=left.transAxes,
        fontsize=7.5,
        color=MUTED,
        va="top",
    )
    save(fig, "constraint_survival")


# Two panels, because the null is only zero before costs. Net IR alone would mislead.
def placebo_lab() -> None:
    d = json.loads((EXHIBITS / "placebo_lab.json").read_text())
    null = d["permutation_null"]
    shipped = d["shipped"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel A, gross. Older artifacts lack the single runs, so fall back to a band.
    if null.get("all_gross"):
        left.hist(
            [x * 100 for x in null["all_gross"]],
            bins=22,
            color=BENCH,
            alpha=0.6,
            edgecolor="white",
            linewidth=0.6,
        )
        left.set_ylabel("Number of runs", fontsize=9, color=MUTED)
    else:
        left.axvspan(
            null["gross_annual_p5"] * 100,
            null["gross_annual_p95"] * 100,
            color=BENCH,
            alpha=0.18,
            linewidth=0,
        )
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
    # Above the tallest bar rather than beside the line, which overlapped the distribution.
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
    if not null.get("all_gross"):
        left.set_yticks([])
    style(left, "A. Before costs, a shuffled score earns nothing", "")
    xlabel(left, "Gross return, % a year")

    # Panel B, net IR. The null is far below zero, and that distance is the cost of churn.
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


# Draws every research chart, skipping any whose exhibit has not been built yet.
def main() -> None:
    print("exhibit charts:")
    for draw in (
        decile_curves,
        search_control,
        subset_histogram,
        cost_drag,
        turnover_frontier,
        cost_ladder,
        cost_waterfall,
        factor_attribution,
        constraint_survival,
        placebo_lab,
    ):
        try:
            draw()
        except FileNotFoundError as exc:
            # That script has not run yet, which is no reason to lose the other charts.
            print(f"  skipped {draw.__name__}, {exc.filename} not built yet")
        except KeyError as exc:
            # An artifact with a model this chart does not know. Say so, do not fail.
            print(f"  skipped {draw.__name__}, no entry for {exc}")


if __name__ == "__main__":
    main()
