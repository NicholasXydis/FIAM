# The seven performance charts the rules list, and the style every chart shares.

import matplotlib

matplotlib.use("Agg")

import sys
import textwrap
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from benchmarks import benchmarks  # noqa: E402
from pipeline import MARKET_NAME, display_name, regress, universe  # noqa: E402

RETURNS = Path("submission/returns.csv")
HOLDINGS = Path("submission/holdings.csv")
CHARS = Path("data/chars_final_with_names.parquet")
FIGURES = Path("submission/figures")

# One colour per role, colourblind-safe. RED MEANS LOSS AND NOTHING ELSE.
OURS = "#1f4e79"  # the strategy
BENCH = "#8c8c8c"  # the T-bill + 4% hurdle
MARKET = "#4a3b6b"  # the market index, charcoal-purple so it is never mistaken for a loss
NEG = "#c00000"  # losses only
ALT = "#7030a0"  # a fourth series where one is needed
MUTED = "#555555"  # captions and axis furniture

# Two sizes so nothing needs resizing. WIDE for date axes, SQUARE for distributions.
WIDE, SQUARE = (8, 4.2), (7, 4.2)

# Realized beta of the first pipeline, which reported -0.002 ex ante. Our strongest finding.
PRE_FIX_BETA = -0.52

# A line break inside a label.
BR = chr(10)
PERIOD = "Jan 2021 to Aug 2026, net of all modelled costs"


# Loads our monthly returns and works out the benchmark we have to beat.
def load() -> pd.DataFrame:
    # The file already has the T-bill rate, so just add the 4% a year the rules require.
    df = pd.read_csv(RETURNS, parse_dates=["holding_month"]).set_index("holding_month")
    df["benchmark"] = df["rf"] + 0.04 / 12
    return df


# The overall stock market return, month by month, to compare ourselves against.
def market_series(index: pd.DatetimeIndex) -> pd.Series:
    # Whatever pipeline.benchmarks() calls the market. MARKET_NAME says which.
    bm = benchmarks().set_index("month")
    # The source gives the market return above cash, so add cash back to get the full return.
    return (bm["mkt_rf"] + bm["rf"]).reindex(index)


# Every chart goes through style(), caption() and save(), so they share one look.
def style(ax, title: str, ylabel: str = "", dates: bool = False) -> None:
    ax.set_title(title, fontsize=11.5, loc="left", weight="bold", pad=10)
    ax.set_ylabel(ylabel, fontsize=9, color=MUTED)
    # Horizontal only and faint, so the gridlines never compete with the data.
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#cccccc")
    ax.tick_params(labelsize=8, colors=MUTED, length=3)
    if dates:
        # Six-month ticks. A tick a month is unreadable over 68 of them.
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        for label in ax.get_xticklabels():
            label.set_rotation(0)


# The x-axis label. Left-aligned and muted like the y-axis, so fourteen charts share one look.
def xlabel(ax, text: str) -> None:
    ax.set_xlabel(text, fontsize=9, loc="left", color=MUTED)


# The line under a chart. The rules want the period and gross/net basis on every exhibit.
def caption(ax, text: str) -> None:
    # Wrapped, because a caption longer than the axis silently runs off the canvas edge.
    wrapped = textwrap.fill(text, width=118)
    ax.text(0, -0.17, wrapped, transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")


# The caption for a two-panel chart. On the figure, not an axis, so it cannot push the panels apart.
def figure_caption(fig, text: str) -> None:
    fig.text(0.01, 0.0, textwrap.fill(text, width=170), fontsize=7.5, color=MUTED, va="top")


# Saves one chart as an image file.
def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()  # stops long titles getting cut off
    fig.savefig(
        FIGURES / f"{name}.png", dpi=220, facecolor="white", bbox_inches="tight", pad_inches=0.3
    )
    plt.close(fig)
    print(f"  {name}.png")


# Shows what $1 would have grown to, for us, the benchmark, and the market.
def cumulative(df: pd.DataFrame) -> None:
    # All three on one axis, so you see we beat the benchmark without tracking the market.
    fig, ax = plt.subplots(figsize=WIDE)
    for series, label, colour in [
        (df["portfolio_total_return"], "Strategy (net)", OURS),
        (df["benchmark"], "T-bill + 4%", BENCH),
        (market_series(df.index), MARKET_NAME, MARKET),
    ]:
        # Market data arrives a month late, so the line stops rather than faking a zero.
        growth = (1 + series.dropna()).cumprod()
        ax.plot(growth.index, growth, label=label, color=colour, linewidth=1.6)
    ax.axhline(1.0, color="black", linewidth=0.6)
    ax.legend(fontsize=8, frameon=False)
    style(ax, "Cumulative return", "Growth of $1", dates=True)
    caption(ax, PERIOD)
    save(fig, "cumulative_return")


# Shows how far below its previous high the strategy fell, and when.
def underwater(df: pd.DataFrame) -> None:
    # Only our drawdown is filled. Two overlapping fills go muddy right where you look.
    fig, ax = plt.subplots(figsize=WIDE)

    def path(series):
        growth = (1 + series.dropna()).cumprod()
        return (growth / growth.cummax() - 1) * 100

    ours = path(df["portfolio_total_return"])
    ax.fill_between(ours.index, ours, 0, alpha=0.28, color=OURS)
    ax.plot(ours.index, ours, color=OURS, linewidth=1.6, label="Strategy")
    market = path(market_series(df.index))
    ax.plot(
        market.index, market, color=MARKET, linewidth=1.1, alpha=0.75, label="S&P 500 (price index)"
    )
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    style(ax, "Drawdown from the running peak", "Drawdown (%)", dates=True)
    caption(ax, PERIOD)
    save(fig, "drawdown")


# The beta we thought we had, the beta we had, and how it moved. One chart, two panels.
def rolling_beta(df: pd.DataFrame) -> None:
    market = market_series(df.index)
    excess, market_excess = df["portfolio_total_return"] - df["rf"], market - df["rf"]
    both = pd.concat([excess, market_excess], axis=1).dropna()

    # The same HAC regression as the headline table, so the two can never disagree.
    def slope(sub):
        return regress(sub.iloc[:, 0], sub.iloc[:, 1])

    full = slope(both)
    now, se = float(full.params.iloc[1]), float(full.bse.iloc[1])
    early, late = slope(both[both.index.year <= 2023]), slope(both[both.index.year >= 2024])
    # Beta over a moving 12-month window. Near zero means we are not following the market.
    beta = both.iloc[:, 0].rolling(12).cov(both.iloc[:, 1]) / both.iloc[:, 1].rolling(12).var()

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2), width_ratios=[1, 2.4])

    # Panel A. The old beta is a figure we quote, not a regression we re-run, so no error bar.
    left.axhspan(-0.2, 0.2, color=BENCH, alpha=0.15, zorder=0)
    left.axhline(0, color="black", linewidth=0.8)
    left.scatter([0], [PRE_FIX_BETA], s=120, color=NEG, zorder=3)
    left.errorbar(
        [1],
        [now],
        yerr=[1.96 * se],
        fmt="o",
        markersize=11,
        color=OURS,
        capsize=6,
        capthick=1.4,
        elinewidth=1.4,
        zorder=3,
    )
    for x, y, text in [(0, PRE_FIX_BETA, f"{PRE_FIX_BETA:+.2f}"), (1, now, f"{now:+.2f}")]:
        left.annotate(text, (x, y), xytext=(14, -4), textcoords="offset points", fontsize=10)
    left.set_xticks([0, 1])
    left.set_xticklabels(
        ["Before" + BR + "beta_60m only", "After" + BR + "+ volatility"], fontsize=8
    )
    left.set_xlim(-0.5, 1.5)
    style(left, "A. Before and after the fix", "Beta")

    # Panel B. Scaled to the data. Stretching down to -0.52 made the series we own look flat.
    right.axhspan(-0.2, 0.2, color=BENCH, alpha=0.15, zorder=0)
    right.plot(beta.index, beta, color=OURS, linewidth=1.8)
    right.axhline(0, color="black", linewidth=0.8)
    pad = (beta.max() - beta.min()) * 0.18
    right.set_ylim(beta.min() - pad, max(beta.max(), 0.2) + pad)
    right.text(
        0.99,
        0.04,
        "investors treat the shaded band as neutral",
        transform=right.transAxes,
        ha="right",
        fontsize=7.5,
        color=MUTED,
    )
    style(right, "B. Rolling 12-month beta to the market", "", dates=True)

    figure_caption(
        fig,
        f"{len(both)} monthly observations against the {MARKET_NAME}, HAC errors, 95% interval. "
        f"The first book reported an ex-ante beta of -0.002 and realized {PRE_FIX_BETA:+.2f}. "
        f"Now {now:+.2f} (se {se:.2f}); 2021-23 {early.params.iloc[1]:+.2f}, 2024-26 "
        f"{late.params.iloc[1]:+.2f}. Rolling windows overlap, so the path is noisy by "
        "construction.",
    )
    save(fig, "rolling_beta")


# Shows whether we were beating the benchmark, over rolling 12-month windows.
def rolling_ir(df: pd.DataFrame) -> None:
    # 12 months shows when conditions changed. Losing-window share goes in the title.
    active = df["active_return"]
    ir = active.rolling(12).mean() / active.rolling(12).std() * np.sqrt(12)  # yearly scale
    fig, ax = plt.subplots(figsize=WIDE)
    ax.plot(ir.index, ir, color=OURS, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.fill_between(ir.index, ir, 0, where=ir < 0, color=NEG, alpha=0.20)
    share = (ir.dropna() < 0).mean()
    style(ax, "Rolling 12-month information ratio", "IR", dates=True)
    caption(ax, f"{PERIOD}. Negative in {share:.0%} of windows.")
    save(fig, "rolling_ir")


# Shows how much we beat the benchmark by, over rolling 12-month windows.
def rolling_active(df: pd.DataFrame) -> None:
    # Same window and shading as the chart above. Compounded, not summed.
    portfolio = (1 + df["portfolio_total_return"]).rolling(12).apply(np.prod, raw=True) - 1
    benchmark = (1 + df["benchmark"]).rolling(12).apply(np.prod, raw=True) - 1
    rolled = (portfolio - benchmark) * 100
    fig, ax = plt.subplots(figsize=WIDE)
    ax.plot(rolled.index, rolled, color=OURS, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.fill_between(rolled.index, rolled, 0, where=rolled < 0, color=NEG, alpha=0.20)
    share = (rolled.dropna() < 0).mean()
    style(ax, "Rolling 12-month active return over T-bill + 4%", "Active return (%)", dates=True)
    caption(ax, f"{PERIOD}. Negative in {share:.0%} of windows.")
    save(fig, "rolling_active_return")


# Shows the spread of monthly returns and how many months cleared the benchmark.
def histogram(df: pd.DataFrame) -> None:
    # The dashed line is the point. Months right of it beat the benchmark.
    net = df["portfolio_total_return"] * 100
    fig, ax = plt.subplots(figsize=SQUARE)
    # Thirteen bins for 68 observations. Twenty-four made noise look like structure.
    ax.hist(net, bins=13, color=OURS, alpha=0.85, edgecolor="white", linewidth=0.8)
    hurdle = df["benchmark"].mean() * 100
    ax.axvline(
        hurdle, color=NEG, linewidth=1.6, linestyle="--", label=f"Monthly hurdle ({hurdle:.2f}%)"
    )
    ax.axvline(net.mean(), color="black", linewidth=1.2, label=f"Mean ({net.mean():.2f}%)")
    ax.legend(fontsize=8, frameon=False)
    style(ax, "Distribution of monthly returns", "Months")
    caption(ax, PERIOD)
    xlabel(ax, "Monthly return (%)")
    save(fig, "return_histogram")


# Shows the ten stocks that made us the most money and the ten that cost us the most.
def contributors() -> None:
    holdings = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    # Holdings are dated the first, returns the month-end before. Step back to line up.
    holdings["eom"] = holdings["Date"] - pd.offsets.MonthEnd(1)
    # The book's own universe, so delisting payouts count here exactly as they did in the book.
    earned = universe()[["permno", "eom", "ret_exc_lead1m"]]
    merged = holdings.merge(earned, left_on=["PERMNO", "eom"], right_on=["permno", "eom"])
    # Weight is stored as a percentage, so divide by 100 before multiplying by the return.
    merged["pnl"] = merged["WEIGHT"] / 100 * merged["ret_exc_lead1m"].fillna(0)

    # By security across all 68 months, labelled as it was last held, as the rules ask.
    total = (merged.groupby("PERMNO")["pnl"].sum() * 100).sort_values()
    both = pd.concat([total.head(10), total.tail(10)])
    label = merged.sort_values("Date").groupby("PERMNO")[["TICKER", "COMPANY NAME"]].last()

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.barh(range(len(both)), both.values, color=[NEG if v < 0 else OURS for v in both.values])
    ax.set_yticks(range(len(both)))
    ax.set_yticklabels(label.loc[both.index, "TICKER"], fontsize=9)
    ax.axvline(0, color="black", linewidth=0.8)
    # Room both sides for the full names, or the longest one runs into the ticker axis.
    span = max(abs(both.values.min()), abs(both.values.max()))
    ax.set_xlim(-span * 2.3, span * 2.1)
    # The full company name, uncut, beside its bar on the far side from the axis.
    for y, (permno, value) in enumerate(both.items()):
        ax.annotate(
            display_name(label.loc[permno, "COMPANY NAME"]),
            (value, y),
            xytext=(6 if value > 0 else -6, 0),
            textcoords="offset points",
            fontsize=7,
            color=MUTED,
            va="center",
            ha="left" if value > 0 else "right",
        )
    # Before costs. We charge fees on the portfolio as a whole, not company by company.
    style(ax, "Ten largest and ten smallest P&L contributors", "")
    caption(ax, "Jan 2021 to Aug 2026, gross contribution before costs.")
    # Left-align like every other chart, not centred under bars that start halfway.
    xlabel(ax, "Contribution to cumulative return (%)")
    save(fig, "pnl_contributors")


# Clears the folder, then draws the performance charts. research_charts.py runs after this.
def main() -> None:
    # Cleared first, so a renamed or retired chart never lingers beside the current ones.
    for stale in FIGURES.glob("*.png"):
        stale.unlink()
    df = load()
    print(f"Writing charts to {FIGURES}/")
    for draw in (cumulative, underwater, rolling_beta, rolling_ir, rolling_active, histogram):
        draw(df)
    contributors()


if __name__ == "__main__":
    main()
