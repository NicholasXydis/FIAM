# Draws the charts the competition asks for, straight into submission/figures/.
# Run it after the pipeline. Every chart says what period it covers and whether the returns
# are before or after costs, because an unlabelled chart is not evidence.

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

RETURNS = Path("submission/returns.csv")
HOLDINGS = Path("submission/holdings.csv")
CHARS = Path("data/chars_final_with_names.parquet")
FIGURES = Path("submission/figures")

# One colour for us, one for the benchmark, one for the market, reused on every chart so a
# reader only has to learn the key once.
OURS, BENCH, MARKET, NEG = "#1f4e79", "#7f7f7f", "#c00000", "#c00000"
PERIOD = "Jan 2021 to Aug 2026, net of all modelled costs"


# Loads our monthly returns and works out the benchmark we have to beat.
def load() -> pd.DataFrame:
    # The file already has the T-bill rate in it, so we just add the 4% a year the rules
    # require on top. No need to download anything.
    df = pd.read_csv(RETURNS, parse_dates=["holding_month"]).set_index("holding_month")
    df["benchmark"] = df["rf"] + 0.04 / 12
    return df


# The overall stock market return, month by month, to compare ourselves against.
def market_series(index: pd.DatetimeIndex) -> pd.Series:
    # This is a broad market index, not the S&P 500 the rules ask for. We do not have a free
    # S&P series that includes dividends, so the charts say which one this is.
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from pipeline import benchmarks
    bm = benchmarks().set_index("month")
    # The source gives the market return above cash, so add cash back to get the full return.
    return (bm["mkt_rf"] + bm["rf"]).reindex(index)


# Every chart goes through style() and save(), so they share fonts, gridlines and dpi. A deck
# where the charts look like one family reads as more finished than one where each is different.
def style(ax, title: str, ylabel: str = "") -> None:
    ax.set_title(title, fontsize=11, loc="left", weight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(alpha=0.25, linewidth=0.6)          # faint, so it never competes with the line
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)


# Saves one chart as an image file.
def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()                          # stops long titles getting cut off
    fig.savefig(FIGURES / f"{name}.png", dpi=200)   # sharp enough for a projector
    plt.close(fig)
    print(f"  {name}.png")


# Shows what $1 would have grown to, for us, the benchmark, and the market.
def cumulative(df: pd.DataFrame) -> None:
    # All three on one axis, so you can see we beat the benchmark without following the market
    # up and down.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for series, label, colour in [
        (df["portfolio_total_return"], "Strategy (net)", OURS),
        (df["benchmark"], "T-bill + 4%", BENCH),
        (market_series(df.index), "Market (CRSP VW, not S&P 500)", MARKET),
    ]:
        # The market data arrives a month late. Filling the gap with zero would draw a flat
        # month that never happened, so the line just stops where the data stops.
        growth = (1 + series.dropna()).cumprod()
        ax.plot(growth.index, growth, label=label, color=colour, linewidth=1.6)
    ax.axhline(1.0, color="black", linewidth=0.6)
    ax.legend(fontsize=8, frameon=False)
    style(ax, f"Cumulative return, {PERIOD}", "Growth of $1")
    save(fig, "cumulative_return")


# Shows how far below its previous high the strategy fell, and when.
def underwater(df: pd.DataFrame) -> None:
    # The market is drawn on top because our bad months land in different months from its.
    # That is exactly what a market-neutral strategy should look like.
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for series, label, colour in [(df["portfolio_total_return"], "Strategy", OURS),
                                  (market_series(df.index), "Market", MARKET)]:
        growth = (1 + series.dropna()).cumprod()
        dd = growth / growth.cummax() - 1
        ax.fill_between(dd.index, dd * 100, 0, alpha=0.30, color=colour)
        ax.plot(dd.index, dd * 100, color=colour, linewidth=1.2, label=label)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    style(ax, f"Drawdown, {PERIOD}", "Drawdown (%)")
    save(fig, "drawdown")


# Shows how much the strategy moved with the market, measured over rolling 12-month windows.
def rolling_beta(df: pd.DataFrame) -> None:
    market = market_series(df.index)
    excess, market_excess = df["portfolio_total_return"] - df["rf"], market - df["rf"]
    both = pd.concat([excess, market_excess], axis=1).dropna()
    # Beta over a moving 12-month window. Near zero means we are not following the market.
    beta = (both.iloc[:, 0].rolling(12).cov(both.iloc[:, 1])
            / both.iloc[:, 1].rolling(12).var())

    fig, ax = plt.subplots(figsize=(8, 4.0))
    ax.plot(beta.index, beta, color=OURS, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhspan(-0.2, 0.2, color=BENCH, alpha=0.15)   # the range investors accept as neutral
    # Headroom so the line never touches the frame, and the band label sits inside the shading
    # instead of colliding with the axis numbers above it.
    ax.set_ylim(beta.min() - 0.08, max(beta.max(), 0.2) + 0.08)
    ax.text(0.99, 0.5, "investors treat this band as neutral", transform=ax.transAxes,
            ha="right", va="center", fontsize=7, color="#555")
    # The single full-period number hides a real drift between the two halves, so we show both.
    # Calculated here rather than typed in, so they cannot go stale when the numbers change.
    import statsmodels.api as sm

    def slope(sub):
        return sm.OLS(sub.iloc[:, 0], sm.add_constant(sub.iloc[:, 1])).fit()

    full = slope(both)
    early, late = slope(both[both.index.year <= 2023]), slope(both[both.index.year >= 2024])
    style(ax, "Rolling 12-month beta to the market\n"
              f"Full period {full.params.iloc[1]:+.2f} (se {full.bse.iloc[1]:.2f})"
              f" · 2021-23 {early.params.iloc[1]:+.2f}"
              f" · 2024-26 {late.params.iloc[1]:+.2f}", "Beta")
    save(fig, "rolling_beta")


# Shows whether we were beating the benchmark, over rolling 12-month windows.
def rolling_ir(df: pd.DataFrame) -> None:
    # 12 months is short enough to show when conditions changed, long enough to mean something.
    # The share of negative windows in the title is the honest headline here.
    active = df["active_return"]
    ir = active.rolling(12).mean() / active.rolling(12).std() * np.sqrt(12)   # yearly scale
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(ir.index, ir, color=OURS, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.fill_between(ir.index, ir, 0, where=ir < 0, color=NEG, alpha=0.20)
    share = (ir.dropna() < 0).mean()
    style(ax, f"Rolling 12-month information ratio, negative in {share:.0%} of windows", "IR")
    save(fig, "rolling_ir")


# Shows how much we beat the benchmark by, over rolling 12-month windows.
def rolling_active(df: pd.DataFrame) -> None:
    # The rules ask for this next to the chart above. Same window and shading, so the two
    # read as a pair.
    rolled = df["active_return"].rolling(12).sum() * 100   # added up, not averaged
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(rolled.index, rolled, color=OURS, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.fill_between(rolled.index, rolled, 0, where=rolled < 0, color=NEG, alpha=0.20)
    share = (rolled.dropna() < 0).mean()
    style(ax, "Rolling 12-month active return over T-bill + 4%\n"
              f"Negative in {share:.0%} of windows", "Active return (%)")
    save(fig, "rolling_active_return")


# Shows the spread of monthly returns and how many months cleared the benchmark.
def histogram(df: pd.DataFrame) -> None:
    # The dashed line is the point. Months to its right beat the benchmark, months to its
    # left did not.
    net = df["portfolio_total_return"] * 100
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(net, bins=24, color=OURS, alpha=0.80, edgecolor="white")
    hurdle = df["benchmark"].mean() * 100
    ax.axvline(hurdle, color=NEG, linewidth=1.6, linestyle="--",
               label=f"Monthly hurdle ({hurdle:.2f}%)")
    ax.axvline(net.mean(), color="black", linewidth=1.2, label=f"Mean ({net.mean():.2f}%)")
    ax.legend(fontsize=8, frameon=False)
    style(ax, f"Monthly returns, {PERIOD}", "Months")
    ax.set_xlabel("Monthly return (%)", fontsize=9)
    save(fig, "return_histogram")


# Shows the ten stocks that made us the most money and the ten that cost us the most.
def contributors(df: pd.DataFrame) -> None:
    holdings = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    # The holding month is the month after the forecast, so step back to join the panel.
    # Our holdings file is dated the first of the month we held them. The returns data is
    # dated the month-end before, so step back a month to line them up.
    holdings["eom"] = (holdings["Date"] - pd.offsets.MonthEnd(1)).dt.normalize()
    panel = pq.read_table(CHARS, columns=["permno", "eom", "ret_exc_lead1m"]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    merged = holdings.merge(panel, left_on=["PERMNO", "eom"], right_on=["permno", "eom"],
                            how="left")
    # Weight is stored as a percentage, so divide by 100 before multiplying by the return.
    merged["pnl"] = merged["WEIGHT"] / 100 * merged["ret_exc_lead1m"].fillna(0)

    # Added up across all 68 months, so each company appears once with its total effect.
    total = (merged.groupby(["TICKER", "COMPANY_NAME"])["pnl"].sum() * 100).sort_values()
    worst, best = total.head(10), total.tail(10)   # ten at each end, as the rules ask
    both = pd.concat([worst, best])
    labels = [f"{t}  {c[:26]}" for t, c in both.index]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(range(len(both)), both.values,
            color=[NEG if v < 0 else OURS for v in both.values])
    ax.set_yticks(range(len(both)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.axvline(0, color="black", linewidth=0.8)
    # Before costs. We charge fees on the portfolio as a whole, not company by company.
    style(ax, "Ten largest and smallest P&L contributors\n"
              "Jan 2021 to Aug 2026, gross contribution before costs", "")
    ax.set_xlabel("Contribution to cumulative return (%)", fontsize=9)
    save(fig, "pnl_contributors")


# Draws all seven charts.
def main() -> None:
    df = load()
    print(f"Writing charts to {FIGURES}/")
    cumulative(df)
    underwater(df)
    rolling_beta(df)
    rolling_ir(df)
    rolling_active(df)
    histogram(df)
    contributors(df)


if __name__ == "__main__":
    main()
