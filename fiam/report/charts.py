# The seven performance charts the rules list, and their shared style.

import matplotlib

matplotlib.use("Agg")

import textwrap

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fiam import paths
from fiam.benchmarks import benchmarks
from fiam.book import display_name, regress, universe

FIGURES = paths.SUBMISSION / "figures"
EXHIBITS = paths.EXHIBITS

# One colour per role, the same in every chart and on every slide.
OURS = "#0F5C7A"  # the strategy, deep petrol blue
BENCH = "#9AA3AE"  # the T-bill + 4% hurdle
MARKET = "#5B6470"  # the S&P 500, dashed so it reads as context
NEG = "#C2410C"  # losses and shortfalls only
ALT = "#7FA7BD"  # a second view of the strategy, a lighter petrol
MUTED = "#6B7280"  # labels and axis furniture
INK = "#0B1F33"  # titles

# One sans-serif with fallbacks, so any machine draws the same charts.
matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.titlesize": 12.5,
        "axes.labelsize": 10,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.fontsize": 9.5,
    }
)

# Two sizes in slide proportions: WIDE for dates, SQUARE for spreads.
WIDE, SQUARE = (9, 4.6), (7.5, 4.6)

# A line break inside a label.
BR = chr(10)
PERIOD = "Jan 2021 to Aug 2026, after all modelled costs"


# A month-keyed exhibit dict, "2024-03": value, as a dated series.
def monthly(values: dict) -> pd.Series:
    return pd.Series(list(values.values()), index=pd.to_datetime(list(values)), dtype=float)


# Loads our monthly returns and works out the benchmark we have to beat.
def load() -> pd.DataFrame:
    # The file has the T-bill rate, so add the 4% a year the rules require.
    df = paths.returns()
    df["benchmark"] = df["rf"] + 0.04 / 12
    return df


# The whole stock market's monthly return, to compare ourselves with.
def market_series(index: pd.DatetimeIndex) -> pd.Series:
    bm = benchmarks().set_index("month")
    # The source gives the market over cash, so add cash back for the total.
    return (bm["mkt_rf"] + bm["rf"]).reindex(index)


# One look for all: short title, grey period line, faint gridlines only.
def style(ax, title: str, ylabel: str = "", dates: bool = False, subtitle: str = "") -> None:
    ax.set_title(title, loc="left", weight="bold", color=INK, pad=24 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=9.5, color=MUTED, va="bottom")
    ax.set_ylabel(ylabel, color=MUTED)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D1D5DB")
    ax.tick_params(colors=MUTED, length=0, pad=6)
    if dates:
        # Yearly ticks read cleanly over 68 months.
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


# The x-axis label, muted like the y-axis.
def xlabel(ax, text: str) -> None:
    ax.set_xlabel(text, color=MUTED)


# A research chart's note: the period and basis the rules ask for.
def caption(ax, text: str) -> None:
    wrapped = textwrap.fill(text, width=110)
    ax.text(0, -0.16, wrapped, transform=ax.transAxes, fontsize=8, color=MUTED, va="top")


# A two-panel note, on the figure so it cannot push the panels apart.
def figure_caption(fig, text: str) -> None:
    fig.text(0.01, 0.0, textwrap.fill(text, width=160), fontsize=8, color=MUTED, va="top")


# A label at a line's right end, in its colour, instead of a legend box.
def end_label(ax, series: pd.Series, text: str, colour: str) -> None:
    last = series.dropna()
    ax.annotate(
        text,
        (last.index[-1], last.iloc[-1]),
        xytext=(8, 0),
        textcoords="offset points",
        color=colour,
        fontsize=9.5,
        va="center",
        weight="bold" if colour == OURS else "normal",
    )


# Saves one chart as an image file.
def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(
        FIGURES / f"{name}.png", dpi=220, facecolor="white", bbox_inches="tight", pad_inches=0.25
    )
    plt.close(fig)
    print(f"  {name}.png")


# What $1 would have grown to, for us, the benchmark and the market.
def cumulative(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=WIDE)
    for series, label, colour, width, dash in [
        (market_series(df.index), "S&P 500", MARKET, 1.4, (4, 3)),
        (df["benchmark"], "T-bill + 4%", BENCH, 1.6, ()),
        (df["portfolio_total_return"], "Strategy", OURS, 2.6, ()),
    ]:
        # Market data arrives a month late, so the line stops, not a fake zero.
        growth = (1 + series.dropna()).cumprod()
        ax.plot(growth.index, growth, color=colour, linewidth=width, dashes=dash)
        end_label(ax, growth, f"{label}  {growth.iloc[-1]:.2f}", colour)
    ax.axhline(1.0, color="#D1D5DB", linewidth=0.8)
    ax.margins(x=0.02)
    ax.set_xlim(right=df.index[-1] + pd.DateOffset(months=11))
    style(ax, "Growth of $1", dates=True, subtitle=f"{PERIOD} · total return")
    ax.set_xticks(pd.to_datetime([f"{y}-01-01" for y in range(2021, 2027)]))
    save(fig, "cumulative_return")


# Shows how far below its previous high the strategy fell, and when.
def underwater(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=WIDE)

    # Percent below the running high.
    def path(series):
        growth = (1 + series.dropna()).cumprod()
        return (growth / growth.cummax() - 1) * 100

    market = path(market_series(df.index))
    ax.plot(market.index, market, color=MARKET, linewidth=1.3, dashes=(4, 3), label="S&P 500")
    ours = path(df["portfolio_total_return"])
    ax.fill_between(ours.index, ours, 0, color=OURS, alpha=0.18, linewidth=0)
    ax.plot(ours.index, ours, color=OURS, linewidth=2.2, label="Strategy")
    ax.legend(frameon=False, loc="lower left")
    title = "Drawdown From the Previous Peak (%)"
    style(ax, title, dates=True, subtitle=f"{PERIOD} · total return")
    save(fig, "drawdown")


# The book's market beta over time, against a zero-beta book's range.
def rolling_beta(df: pd.DataFrame) -> None:
    market = market_series(df.index)
    excess, market_excess = df["portfolio_total_return"] - df["rf"], market - df["rf"]
    both = pd.concat([excess, market_excess], axis=1).dropna()
    # The headline table's HAC regression, so the two can never disagree.
    full = regress(both.iloc[:, 0], both.iloc[:, 1])
    now, se = float(full.params.iloc[1]), float(full.bse.iloc[1])
    window = paths.exhibit("pack.json")["beta_drift"]["rolling_12m"]
    beta = monthly({m: v["beta"] for m, v in window.items()})
    noise = monthly({m: v["noise_band"] for m, v in window.items()})
    daily = paths.exhibit("daily_risk.json").get("beta_to_sp500_daily", {})

    fig, ax = plt.subplots(figsize=WIDE)
    ax.fill_between(
        noise.index,
        -noise,
        noise,
        color="#E5E7EB",
        linewidth=0,
        label="range for a truly zero-beta portfolio (95%)",
    )
    if daily:
        days = monthly(daily["rolling_252d"])
        ax.plot(days.index, days, color=ALT, linewidth=1.6, label="252 trading days, daily")
    ax.plot(beta.index, beta, color=OURS, linewidth=2.4, label="12 months, monthly")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
    note = f" · daily, 2021-25: {daily['beta']:+.2f}" if daily else ""
    subtitle = f"{PERIOD} · full period {now:+.2f} (standard error {se:.2f}){note}"
    style(ax, "Rolling Beta to the S&P 500", dates=True, subtitle=subtitle)
    save(fig, "rolling_beta")


# A rolling 12-month line, losing stretches shaded, for IR or active.
def rolling(series: pd.Series, title: str, name: str) -> None:
    fig, ax = plt.subplots(figsize=WIDE)
    ax.fill_between(series.index, series, 0, where=series < 0, color=NEG, alpha=0.18, linewidth=0)
    ax.fill_between(series.index, series, 0, where=series >= 0, color=OURS, alpha=0.12, linewidth=0)
    ax.plot(series.index, series, color=OURS, linewidth=2.2)
    ax.axhline(0, color=INK, linewidth=0.8)
    share = (series.dropna() < 0).mean()
    style(ax, title, dates=True, subtitle=f"{PERIOD} · below zero in {share:.0%} of windows")
    save(fig, name)


# Whether we were beating the benchmark, over rolling 12-month windows.
def rolling_ir(df: pd.DataFrame) -> None:
    active = df["active_return"]
    ir = active.rolling(12).mean() / active.rolling(12).std() * np.sqrt(12)
    rolling(ir, "Rolling 12-Month Information Ratio", "rolling_ir")


# How much we beat the benchmark by, over rolling 12 months, compounded.
def rolling_active(df: pd.DataFrame) -> None:
    portfolio = (1 + df["portfolio_total_return"]).rolling(12).apply(np.prod, raw=True) - 1
    benchmark = (1 + df["benchmark"]).rolling(12).apply(np.prod, raw=True) - 1
    rolled = (portfolio - benchmark) * 100
    rolling(rolled, "Rolling 12-Month Return Over T-bill + 4% (%)", "rolling_active_return")


# The spread of monthly returns, with the benchmark's hurdle marked.
def histogram(df: pd.DataFrame) -> None:
    total = df["portfolio_total_return"] * 100
    fig, ax = plt.subplots(figsize=SQUARE)
    ax.hist(total, bins=13, color=OURS, alpha=0.9, edgecolor="white", linewidth=1.2)
    hurdle = df["benchmark"].mean() * 100
    ax.axvline(hurdle, color=NEG, linewidth=1.8, dashes=(4, 3), label=f"Hurdle {hurdle:.2f}%")
    ax.axvline(total.mean(), color=INK, linewidth=1.4, label=f"Average {total.mean():.2f}%")
    ax.legend(frameon=False)
    style(ax, "Monthly Total Returns", "Months", subtitle=PERIOD)
    xlabel(ax, "Monthly return (%)")
    save(fig, "return_histogram")


# The ten stocks that made us the most money and the ten that cost most.
def contributors() -> None:
    holdings = paths.holdings()
    # Holdings are dated the first, returns the month-end before. Step back.
    holdings["eom"] = holdings["Date"] - pd.offsets.MonthEnd(1)
    # The book's own universe, so delisting payouts count as in the book.
    earned = universe()[["permno", "eom", "ret_exc_lead1m"]]
    merged = holdings.merge(earned, left_on=["PERMNO", "eom"], right_on=["permno", "eom"])
    # Weight is a percentage, so divide by 100 before applying the return.
    merged["pnl"] = merged["WEIGHT"] / 100 * merged["ret_exc_lead1m"].fillna(0)

    # By security over all 68 months, labelled as last held, per the rules.
    total = (merged.groupby("PERMNO")["pnl"].sum() * 100).sort_values()
    both = pd.concat([total.head(10), total.tail(10)])
    label = merged.sort_values("Date").groupby("PERMNO")[["TICKER", "COMPANY NAME"]].last()

    fig, ax = plt.subplots(figsize=(11, 6.5))
    colours = [NEG if v < 0 else OURS for v in both.values]
    ax.barh(range(len(both)), both.values, color=colours, height=0.7)
    ax.set_yticks(range(len(both)))
    ax.set_yticklabels(label.loc[both.index, "TICKER"], fontsize=9)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    # Room on both sides, or the longest name runs into the ticker axis.
    span = max(abs(both.values.min()), abs(both.values.max()))
    ax.set_xlim(-span * 1.75, span * 1.75)
    # The full company name, uncut, beside its bar away from the axis.
    for y, (permno, value) in enumerate(both.items()):
        ax.annotate(
            display_name(label.loc[permno, "COMPANY NAME"]),
            (value, y),
            xytext=(6 if value > 0 else -6, 0),
            textcoords="offset points",
            fontsize=9,
            color=MUTED,
            va="center",
            ha="left" if value > 0 else "right",
        )
    # Before costs. Fees are charged on the whole book, not per company.
    style(
        ax,
        "Largest Winners and Losers",
        subtitle="Jan 2021 to Aug 2026 · contribution to cumulative return before costs (%)",
    )
    save(fig, "pnl_contributors")


# Clears the folder, draws the charts. research_charts.py runs after.
def main() -> None:
    # Cleared first, so the folder holds only the charts drawn here.
    for stale in FIGURES.glob("*.png"):
        stale.unlink()
    df = load()
    print(f"Writing charts to {FIGURES}/")
    for draw in (cumulative, underwater, rolling_beta, rolling_ir, rolling_active, histogram):
        draw(df)
    contributors()


if __name__ == "__main__":
    main()
