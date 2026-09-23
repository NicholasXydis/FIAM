# Draws the required charts into submission/figures/. Run after the pipeline.

import matplotlib

matplotlib.use("Agg")

import textwrap
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

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
    # A broad market index, not the S&P 500. No free S&P series includes dividends.
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from pipeline import benchmarks

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
        (market_series(df.index), "Market (CRSP VW, not S&P 500)", MARKET),
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
    ax.plot(market.index, market, color=MARKET, linewidth=1.1, alpha=0.75, label="Market")
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    style(ax, "Drawdown from the running peak", "Drawdown (%)", dates=True)
    caption(ax, PERIOD)
    save(fig, "drawdown")


# Shows how much the strategy moved with the market, measured over rolling 12-month windows.
def rolling_beta(df: pd.DataFrame) -> None:
    market = market_series(df.index)
    excess, market_excess = df["portfolio_total_return"] - df["rf"], market - df["rf"]
    both = pd.concat([excess, market_excess], axis=1).dropna()
    # Beta over a moving 12-month window. Near zero means we are not following the market.
    beta = both.iloc[:, 0].rolling(12).cov(both.iloc[:, 1]) / both.iloc[:, 1].rolling(12).var()

    fig, ax = plt.subplots(figsize=WIDE)
    ax.axhspan(-0.2, 0.2, color=BENCH, alpha=0.15, zorder=0)
    ax.plot(beta.index, beta, color=OURS, linewidth=1.8)
    ax.axhline(0, color="black", linewidth=0.8)
    # Scaled to the data. Stretching down to -0.52 made the series we own look flat.
    pad = (beta.max() - beta.min()) * 0.18
    ax.set_ylim(beta.min() - pad, max(beta.max(), 0.2) + pad)
    ax.text(
        0.99,
        0.04,
        "investors treat the shaded band as neutral",
        transform=ax.transAxes,
        ha="right",
        fontsize=7.5,
        color=MUTED,
    )

    # Computed here rather than typed in, so the caption cannot go stale.
    import statsmodels.api as sm

    def slope(sub):
        return sm.OLS(sub.iloc[:, 0], sm.add_constant(sub.iloc[:, 1])).fit()

    full = slope(both)
    early, late = slope(both[both.index.year <= 2023]), slope(both[both.index.year >= 2024])
    style(ax, "Rolling 12-month beta to the market", "Beta", dates=True)
    caption(
        ax,
        f"{len(both)} monthly observations. Full period {full.params.iloc[1]:+.2f} "
        f"(se {full.bse.iloc[1]:.2f}), 2021-23 {early.params.iloc[1]:+.2f}, "
        f"2024-26 {late.params.iloc[1]:+.2f}. Overlapping windows, so the path is noisy by "
        "construction.",
    )
    save(fig, "rolling_beta")


# The beta we thought we had next to the one we had, as two points with error bars.
def beta_before_after(df: pd.DataFrame) -> None:
    import statsmodels.api as sm

    market = market_series(df.index)
    both = pd.concat([df["portfolio_total_return"] - df["rf"], market - df["rf"]], axis=1).dropna()
    fit = sm.OLS(both.iloc[:, 0], sm.add_constant(both.iloc[:, 1])).fit(
        cov_type="HAC", cov_kwds={"maxlags": 6}
    )
    now, se = float(fit.params.iloc[1]), float(fit.bse.iloc[1])

    fig, ax = plt.subplots(figsize=SQUARE)
    ax.axhspan(-0.2, 0.2, color=BENCH, alpha=0.15, zorder=0)
    ax.axhline(0, color="black", linewidth=0.8)
    # The old beta is a figure we quote, not a regression we re-run, so no error bar.
    ax.scatter([0], [PRE_FIX_BETA], s=120, color=NEG, zorder=3)
    ax.errorbar(
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
        ax.annotate(text, (x, y), xytext=(14, -4), textcoords="offset points", fontsize=10)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(
        ["Before" + BR + "beta_60m only", "After" + BR + "+ volatility complex"], fontsize=9
    )
    ax.set_xlim(-0.5, 1.5)
    style(ax, "Realized beta, before and after the volatility constraint", "Beta")
    caption(
        ax,
        f"Bars are 95% intervals, HAC errors. The first book reported an ex-ante beta of "
        f"-0.002 and realized {PRE_FIX_BETA:+.2f}; only the regression tells you what you own.",
    )
    save(fig, "beta_before_after")


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
def contributors(df: pd.DataFrame) -> None:
    holdings = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    # Holdings are dated the first, returns the month-end before. Step back to line up.
    holdings["eom"] = (holdings["Date"] - pd.offsets.MonthEnd(1)).dt.normalize()
    panel = pq.read_table(CHARS, columns=["permno", "eom", "ret_exc_lead1m"]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    merged = holdings.merge(
        panel, left_on=["PERMNO", "eom"], right_on=["permno", "eom"], how="left"
    )
    # Weight is stored as a percentage, so divide by 100 before multiplying by the return.
    merged["pnl"] = merged["WEIGHT"] / 100 * merged["ret_exc_lead1m"].fillna(0)

    # Added up across all 68 months, so each company appears once with its total effect.
    total = (merged.groupby(["TICKER", "COMPANY_NAME"])["pnl"].sum() * 100).sort_values()
    worst, best = total.head(10), total.tail(10)  # ten at each end, as the rules ask
    both = pd.concat([worst, best])

    # Ticker only on the axis. Twenty full company names crowded the bars.
    labels = [ticker for ticker, _ in both.index]

    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    ax.barh(range(len(both)), both.values, color=[NEG if v < 0 else OURS for v in both.values])
    ax.set_yticks(range(len(both)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(0, color="black", linewidth=0.8)
    # Room both sides for the names, or the longest label hits the ticker axis.
    span = max(abs(both.values.min()), abs(both.values.max()))
    ax.set_xlim(-span * 1.55, span * 1.45)
    # Company name sits next to its bar, on the far side from the axis, so it never collides.
    for y, ((_, company), value) in enumerate(zip(both.index, both.values)):
        # Never .title() these. It turns AT&T into At&T. Only the suffix comes off.
        short = company.strip()
        for suffix in (" INC", " CORP", " CO", " PLC", " LTD", " CORPORATION", " COMPANY"):
            if short.endswith(suffix):
                short = short[: -len(suffix)].strip()
        short = short.rstrip(" .,&")[:26]
        ax.annotate(
            short,
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


# Draws the performance charts.
def main() -> None:
    df = load()
    print(f"Writing charts to {FIGURES}/")
    cumulative(df)
    underwater(df)
    rolling_beta(df)
    beta_before_after(df)
    rolling_ir(df)
    rolling_active(df)
    histogram(df)
    contributors(df)


if __name__ == "__main__":
    main()
