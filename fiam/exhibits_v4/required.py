# The PDF's eight required exhibits (PLAN §4.4, PDF p21).

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fiam.exhibits_v4 import common as c
from fiam.exhibits_v4.common import BENCH, INK, MARKET, MUTED, NEG, OURS, RULE, WIDE, Inputs
from fiam.v4 import daily_book
from fiam.v4.report import table_9_1

# Bars in a top or bottom list, and contributors each way.
TOP = 10
# Bins on a log axis for the liquidity and size distributions.
BINS = 40
# The "why it was on" line when no reason column is supplied.
DEFAULT_REASON = "forecast rank"


# 1. Cumulative active return over the hurdle, the paths beneath it.
def active_return(x: Inputs):
    strategy = (1 + x.d["ret"]).cumprod() - 1
    hurdle = (1 + x.hurdle).cumprod() - 1
    market = (1 + x.sp).cumprod() - 1
    frame = pd.DataFrame({"strategy": strategy, "benchmark": hurdle, "sp500": market}) * 100
    frame["active"] = frame["strategy"] - frame["benchmark"]
    fig, (top, low) = plt.subplots(
        2, 1, figsize=(9, 6.6), sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    a = frame["active"]
    top.fill_between(a.index, a, 0, where=a >= 0, color=OURS, alpha=0.12, linewidth=0)
    top.fill_between(a.index, a, 0, where=a < 0, color=NEG, alpha=0.15, linewidth=0)
    top.plot(a.index, a, color=OURS, linewidth=2.4)
    top.axhline(0, color=INK, linewidth=0.8)
    c.end_label(top, a, f"{a.iloc[-1]:+.1f} points", OURS)
    subtitle = f"{x.period} · after all modelled costs · strategy less T-bill + 4%"
    c.style(top, "Cumulative Active Return Over T-bill + 4%", "Percentage points",
            dates=True, subtitle=subtitle)  # fmt: skip
    # The S&P 500 faint, for context only (PLAN §4.4).
    for col, label, colour, width, extra in [
        ("sp500", "S&P 500", MARKET, 1.2, dict(dashes=(4, 3), alpha=0.45)),
        ("benchmark", "T-bill + 4%", BENCH, 1.6, {}),
        ("strategy", "Strategy", OURS, 2.2, {}),
    ]:
        low.plot(frame.index, frame[col], color=colour, linewidth=width, label=label, **extra)
        c.end_label(low, frame[col], f"{label}  {frame[col].iloc[-1]:+.1f}%", colour)
    low.axhline(0, color="#D1D5DB", linewidth=0.8)
    low.legend(frameon=False, loc="upper left", ncol=3)
    c.panel(low, "Cumulative return", "%", dates=True)
    c.years(low, x.first, x.last)
    low.set_xlim(right=frame.index[-1] + pd.Timedelta(days=200))
    return fig, frame


# 2. The book's 252-session beta to the S&P 500, excess of the bill.
def rolling_beta(x: Inputs):
    y, m = x.d["ret"] - x.d["rf"], x.sp - x.d["rf"]
    days = daily_book.BETA_DAYS
    rolled = y.rolling(days).cov(m) / m.rolling(days).var()
    _, _, b, se = table_9_1.ols(y, m, table_9_1.LAGS_DAILY)
    frame = pd.DataFrame({"beta_252d": rolled})
    fig, ax = plt.subplots(figsize=WIDE)
    shown = rolled.dropna()
    ax.plot(shown.index, shown, color=OURS, linewidth=2.2)
    ax.axhline(0, color=INK, linewidth=0.8)
    span = max(0.3, float(shown.abs().max()) * 1.25) if len(shown) else 0.3
    ax.set_ylim(-span, span)
    c.years(ax, x.first, x.last)
    ax.set_xlim(right=x.last)
    subtitle = (
        f"{x.period} · daily OLS over {days} sessions · full window {c.num(b)} "
        f"(s.e. {c.num(se)}, Newey-West {table_9_1.LAGS_DAILY} lags)"
    )
    c.style(ax, "Rolling 252-Day Beta to the S&P 500", "Beta", dates=True, subtitle=subtitle)
    return fig, frame


# 3. Calendar years before and after costs against the hurdle.
def calendar_years(x: Inputs):
    frame = (
        pd.DataFrame(
            {
                "before_costs": c.by_year(c.before_costs(x)),
                "after_costs": c.by_year(x.d["ret"]),
                "benchmark": c.by_year(x.hurdle),
            }
        )
        * 100
    )
    frame.index.name = "year"
    days = x.d.index
    frame["partial"] = [c.partial(days, y) for y in frame.index]
    frame["first"] = [days[days.year == y].min().date() for y in frame.index]
    frame["last"] = [days[days.year == y].max().date() for y in frame.index]
    fig, ax = plt.subplots(figsize=WIDE)
    pos, width = np.arange(len(frame)), 0.26
    bars = [
        ("before_costs", "Before costs", dict(facecolor="white", edgecolor=OURS, linewidth=1.4)),
        ("after_costs", "After costs", dict(color=OURS)),
        ("benchmark", "T-bill + 4%", dict(color=BENCH)),
    ]
    for k, (col, label, look) in enumerate(bars):
        at = pos + (k - 1) * (width + 0.02)
        ax.bar(at, frame[col], width, label=label, **look)
        for xx, v in zip(at, frame[col]):
            ax.annotate(f"{v:+.1f}", (xx, v), xytext=(0, 3 if v >= 0 else -3),
                        textcoords="offset points", ha="center", fontsize=7.5, color=MUTED,
                        va="bottom" if v >= 0 else "top")  # fmt: skip
    ax.axhline(0, color=INK, linewidth=0.8)
    names = []
    for k, (year, row) in enumerate(frame.iterrows()):
        if row["partial"]:
            ax.axvspan(k - 0.48, k + 0.48, color="#F3F4F6", zorder=0)
            span = f"{pd.Timestamp(row['first']):%b} to {pd.Timestamp(row['last']):%b}"
            names.append(f"{year}{c.charts.BR}partial, {span}")
        else:
            names.append(str(year))
    ax.set_xticks(pos, names)
    ax.legend(frameon=False, loc="upper left", ncol=3)
    low, high = ax.get_ylim()
    ax.set_ylim(low - 0.05 * (high - low), high + 0.22 * (high - low))
    subtitle = f"{x.period} · compounded within each calendar year · never annualised"
    c.style(ax, "Calendar-Year Returns Before and After Costs", "%", subtitle=subtitle)
    return fig, frame


# 4. Gross, net and names over time against the PDF's limits.
def exposure(x: Inputs):
    live = x.live
    frame = pd.DataFrame(
        {
            "gross": live["gross"] * 100,
            "net": live["net"] * 100,
            "names": live["n_long"] + live["n_short"],
        }  # fmt: skip
    )
    if x.compliance is not None and "companies" in x.compliance:
        frame["companies"] = x.compliance.set_index("date")["companies"].reindex(frame.index)
    r = x.rules
    fig, (top, low) = plt.subplots(2, 1, figsize=(9, 6.6), sharex=True)
    top.plot(frame.index, frame["gross"], color=OURS, linewidth=2.0, label="Gross")
    top.plot(frame.index, frame["net"], color=MARKET, linewidth=1.4, label="Net")
    for level, text in [(r["gross"], f"{r['gross'] * 100:.0f}% gross limit"),
                        (r["net_band"], f"+{r['net_band'] * 100:.0f}% net limit"),
                        (-r["net_band"], f"-{r['net_band'] * 100:.0f}% net limit")]:  # fmt: skip
        top.axhline(level * 100, **RULE)
        top.annotate(text, (frame.index[0], level * 100), xytext=(2, 3),
                     textcoords="offset points", fontsize=8.5, color=MUTED)  # fmt: skip
    top.axhline(0, color="#D1D5DB", linewidth=0.8)
    top.legend(frameon=False, loc="center right", ncol=2)
    sub = (f"{x.period} · daily closes from the first trade · average gross "
           f"{frame['gross'].mean():.0f}% · average names {frame['names'].mean():.0f}")  # fmt: skip
    c.style(top, "Gross, Net and Position Count", "% of NAV", dates=True, subtitle=sub)
    top.set_ylim(-r["net_band"] * 100 - 20, r["gross"] * 100 + 20)
    low.plot(frame.index, frame["names"], color=OURS, linewidth=2.0, label="Names by PERMNO")
    if "companies" in frame:
        low.plot(frame.index, frame["companies"], color=MARKET, linewidth=1.0, alpha=0.6,
                 label="Companies by PERMCO")  # fmt: skip
        low.legend(frameon=False, loc="center right")
    for level in (r["names_min"], r["names_max"]):
        low.axhline(level, **RULE)
        low.annotate(f"{level} names", (frame.index[0], level), xytext=(2, 3),
                     textcoords="offset points", fontsize=8.5, color=MUTED)  # fmt: skip
    low.set_ylim(r["names_min"] - 60, r["names_max"] + 60)
    c.panel(low, "Positions held", "Names", dates=True)
    c.years(low, x.first, x.last)
    return fig, frame


# Average weight per name over every live session, zero when unheld.
def average_weights(x: Inputs) -> pd.DataFrame:
    live = x.live
    p = x.positions[x.positions["date"].isin(live.index)]
    p = p.assign(w=p["value"] / p["date"].map(live["nav"]).to_numpy())
    g = p.groupby("permno")
    return pd.DataFrame(
        {"avg_weight": g["w"].sum() / len(live), "sessions": g.size(), "last_held": g["date"].max()}
    )


# The label table for chosen names, as of each name's last held day.
def named(x: Inputs, held: pd.DataFrame) -> pd.DataFrame:
    when = held.reset_index()[["permno", "last_held"]].rename(columns={"last_held": "date"})
    got = c.labels(x.ids, when).set_index("permno")
    return held.join(got)


# Horizontal bars, largest at the top, labelled beside each bar.
def bars(ax, values: pd.Series, labels, colour: str, fmt) -> None:
    y = np.arange(len(values))[::-1]
    ax.barh(y, values.to_numpy(), color=colour, height=0.68)
    ax.set_yticks(y, labels)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    for yy, v in zip(y, values):
        ax.annotate(fmt(v), (v, yy), xytext=(5 if v >= 0 else -5, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=MUTED,
                    ha="left" if v >= 0 else "right")  # fmt: skip


# 5. The ten largest longs and shorts by average weight, labelled.
def top_holdings(x: Inputs):
    avg = average_weights(x)
    longs = named(x, avg[avg["avg_weight"] > 0].nlargest(TOP, "avg_weight")).assign(side="long")
    shorts = named(x, avg[avg["avg_weight"] < 0].nsmallest(TOP, "avg_weight")).assign(side="short")
    frame = pd.concat([longs, shorts]).reset_index()
    frame["avg_weight_pct"] = frame["avg_weight"] * 100
    frame["label_source"] = "ids table as of the last held session"
    fig, (top, low) = plt.subplots(2, 1, figsize=(10, 8.4))
    pct = lambda v: f"{v:.2f}%"  # noqa: E731
    bars(top, longs["avg_weight"] * 100, longs["label"], OURS, pct)
    bars(low, shorts["avg_weight"].abs() * 100, shorts["label"], MARKET, lambda v: f"-{v:.2f}%")
    span = 1.18 * max(longs["avg_weight"].max(), shorts["avg_weight"].abs().max()) * 100
    for ax in (top, low):
        ax.set_xlim(0, span)
    sub = f"{x.period} · mean weight over every session from the first trade, zero when unheld"
    top_edge = c.headline(fig, "Top and Bottom Ten Holdings by Average Weight", sub)
    c.panel(top, "Ten largest longs")
    c.panel(low, "Ten largest shorts, shown by size")
    c.charts.xlabel(low, "Average weight (% of NAV)")
    fig.tight_layout(rect=(0, 0, 1, top_edge))
    return fig, frame


# Each name's "why it was on" text, from a reasons table or the default.
def reasons(x: Inputs, permnos) -> pd.Series:
    src = x.reasons
    if src is None and "reason" in x.positions.columns:
        src = x.positions[["date", "permno", "reason"]]
    if src is None:
        return pd.Series(DEFAULT_REASON, index=list(permnos))
    src = src.sort_values("date") if "date" in src.columns else src
    last = src.dropna(subset=["reason"]).groupby("permno")["reason"].last()
    return last.reindex(list(permnos)).fillna(DEFAULT_REASON).map(c.clean)


# 6. The ten largest positive and negative contributors, net of costs.
def contributors(x: Inputs):
    led = x.ledger
    by_kind = led.pivot_table(index="permno", columns="kind", values="dollars",
                              aggfunc="sum", fill_value=0.0)  # fmt: skip
    total = by_kind.sum(axis=1)
    pick = pd.concat([total[total > 0].nlargest(TOP), total[total < 0].nsmallest(TOP)])
    held = x.positions[x.positions["permno"].isin(pick.index)]
    g = held.groupby("permno")
    info = pd.DataFrame({"sessions": g.size(), "last_held": g["date"].max(),
                         "mean_value": g["value"].mean()}).reindex(pick.index)  # fmt: skip
    # A name traded but never held at a close takes its last ledger day.
    info["last_held"] = info["last_held"].fillna(led.groupby("permno")["date"].max())
    frame = named(x, info)
    frame["side"] = np.where(frame["mean_value"] < 0, "short", "long")
    frame["reason"] = reasons(x, frame.index)
    frame["dollars_m"] = pick / 1e6
    frame["pct_start_nav"] = pick / x.base * 100
    frame = frame.join(by_kind.reindex(pick.index).add_prefix("dollars_"))
    frame["why"] = [
        f"{side} for {int(n) if n == n else 0} sessions · {why}"
        for side, n, why in zip(frame["side"], frame["sessions"], frame["reason"])
    ]
    order = frame.sort_values("pct_start_nav", ascending=False)
    fig, ax = plt.subplots(figsize=(11, 10))
    text = [f"{lab}{c.charts.BR}{why}" for lab, why in zip(order["label"], order["why"])]
    colours = [NEG if v < 0 else OURS for v in order["pct_start_nav"]]
    y = np.arange(len(order))[::-1]
    ax.barh(y, order["pct_start_nav"].to_numpy(), color=colours, height=0.68)
    ax.set_yticks(y, text, fontsize=8.5)
    for yy, v in zip(y, order["pct_start_nav"]):
        ax.annotate(f"{v:+.2f}%", (v, yy), xytext=(5 if v >= 0 else -5, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=MUTED,
                    ha="left" if v >= 0 else "right")  # fmt: skip
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    span = float(order["pct_start_nav"].abs().max()) * 1.3
    ax.set_xlim(-span, span)
    subtitle = (f"{x.period} · each name's P&L after its trading and borrow costs, "
                f"% of the starting NAV")  # fmt: skip
    c.style(ax, "")
    c.charts.xlabel(ax, "Contribution (% of starting NAV)")
    top = c.headline(fig, "Ten Largest Positive and Negative Contributors", subtitle)
    fig.tight_layout(rect=(0, 0, 1, top))
    return fig, frame.drop(columns=["mean_value"]).reset_index()


# Short positions on every holdings date with cap and dollar ADV.
def short_book(x: Inputs) -> pd.DataFrame:
    s = x.positions[(x.positions["value"] < 0) & x.positions["date"].isin(x.holding_days)]
    s = c.as_of(s, x.caps, "me")
    return c.as_of(s, x.adv, "adv").assign(adv_m=lambda f: f["adv"] / 1e6)


# A distribution on a log axis in $ millions with optional rule line.
def log_hist(ax, values: pd.Series, colour: str) -> None:
    v = values.dropna()
    v = v[v > 0]
    if v.empty:
        return
    bins = np.geomspace(v.min() * 0.9, v.max() * 1.1, BINS)
    ax.hist(v, bins=bins, color=colour, alpha=0.9, edgecolor="white", linewidth=0.6)
    ax.set_xscale("log")


# 7. Short-book cap and dollar volume, the minimum every holdings date.
def short_liquidity(x: Inputs):
    s = short_book(x)
    floor = float(x.rules["short_min_market_cap"])
    g = s.groupby("date")
    frame = pd.DataFrame({"shorts": g.size(), "with_cap": g["me"].count(),
                          "min_cap_m": g["me"].min(), "median_cap_m": g["me"].median(),
                          "with_adv": g["adv"].count(), "min_adv_m": g["adv_m"].min(),
                          "median_adv_m": g["adv_m"].median()})  # fmt: skip
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.6))
    (a, b), (cc, dd) = axes
    log_hist(a, s["me"], MARKET)
    a.axvline(floor, **RULE)
    a.annotate(f"${floor:g}m floor", (floor, 1), xycoords=("data", "axes fraction"),
               xytext=(4, -12), textcoords="offset points", fontsize=8.5, color=MUTED)  # fmt: skip
    c.money_axis(a)
    c.panel(a, "Market cap of each short", "Short positions")
    log_hist(b, s["adv_m"], MARKET)
    c.money_axis(b)
    c.panel(b, "Dollar ADV of each short", "Short positions")
    cc.plot(frame.index, frame["median_cap_m"], color=BENCH, linewidth=1.4, label="Median")
    cc.plot(frame.index, frame["min_cap_m"], color=OURS, linewidth=1.8, marker="o",
            markersize=3, label="Minimum")  # fmt: skip
    cc.axhline(floor, **RULE)
    cc.set_yscale("log")
    c.money_axis(cc, "y")
    cc.annotate(f"${floor:g}m floor", (frame.index[0], floor), xytext=(2, -4), va="top",
                textcoords="offset points", fontsize=8.5, color=MUTED)  # fmt: skip
    c.panel(cc, "Short-book market cap each holdings date", dates=True)
    dd.plot(frame.index, frame["median_adv_m"], color=BENCH, linewidth=1.4, label="Median")
    dd.plot(frame.index, frame["min_adv_m"], color=OURS, linewidth=1.8, marker="o",
            markersize=3, label="Minimum")  # fmt: skip
    dd.set_yscale("log")
    c.money_axis(dd, "y")
    c.panel(dd, "Short-book dollar ADV each holdings date", dates=True)
    # Head room on the log axis so the legend clears both lines.
    for ax in (cc, dd):
        lo, hi = ax.get_ylim()
        ax.set_ylim(min(lo, floor * 0.6) if ax is cc else lo, hi * 4)
        ax.legend(frameon=False, loc="upper left", ncol=2)
        c.years(ax, x.first, x.last)
    low = frame["min_cap_m"].min()
    sub = (f"{x.period} · {len(frame)} holdings dates · smallest short ${low:,.0f}m "
           f"against the ${floor:g}m floor · caps known for {int(frame['with_cap'].sum()):,} "
           f"of {int(frame['shorts'].sum()):,} short rows")  # fmt: skip
    fig.tight_layout(
        rect=(0, 0, 1, c.headline(fig, "Short Book Market Cap and Dollar Volume", sub))
    )
    return fig, frame


# 8. Each position's size in days of ADV, long and short legs apart.
def days_of_adv(x: Inputs):
    p = x.positions[x.positions["date"].isin(x.holding_days)]
    p = c.as_of(p, x.adv, "adv")
    p = p.assign(days=p["value"].abs() / p["adv"], leg=np.where(p["value"] < 0, "short", "long"))
    rows = {}
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), sharey=False)
    for ax, leg, colour in zip(axes, ("long", "short"), (OURS, MARKET)):
        v = p.loc[p["leg"] == leg, "days"].dropna()
        q = v.quantile([0.5, 0.95]) if len(v) else pd.Series([np.nan, np.nan], index=[0.5, 0.95])
        missing = int(p.loc[p["leg"] == leg, "adv"].isna().sum())
        rows[leg] = {"positions": len(v), "median": q[0.5], "p95": q[0.95],
                     "max": v.max(), "missing_adv": missing}  # fmt: skip
        log_hist(ax, v, colour)
        for value, text, drop in ((q[0.5], "median", -12), (q[0.95], "95th percentile", -28)):
            if value == value:
                ax.axvline(value, color=INK, linewidth=0.9, dashes=(2, 2))
                ax.annotate(f"{text} {value:.3f}", (value, 1), xycoords=("data", "axes fraction"),
                            xytext=(4, drop), textcoords="offset points", fontsize=8.5,
                            color=MUTED, bbox=dict(facecolor="white", edgecolor="none",
                                                   alpha=0.85, pad=1))  # fmt: skip
        ax.xaxis.set_major_formatter(c.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(c.NullFormatter())
        c.panel(ax, f"{leg.capitalize()} leg", "Positions")
        c.charts.xlabel(ax, "Position size in days of ADV")
    frame = pd.DataFrame(rows).T
    frame.index.name = "leg"
    big = f"largest long {rows['long']['max']:.2f} and short {rows['short']['max']:.2f} days"
    sub = f"{x.period} · |position| over its 126-day dollar ADV · every holdings date · {big}"
    fig.tight_layout(rect=(0, 0, 1, c.headline(fig, "Position Size in Days of ADV", sub)))
    return fig, frame


# The eight in the PDF's order, by file stem.
EXHIBITS = (
    ("exhibit_1_active_return", active_return),
    ("exhibit_2_rolling_beta", rolling_beta),
    ("exhibit_3_calendar_years", calendar_years),
    ("exhibit_4_exposure_names", exposure),
    ("exhibit_5_top_holdings", top_holdings),
    ("exhibit_6_contributors", contributors),
    ("exhibit_7_short_liquidity", short_liquidity),
    ("exhibit_8_days_of_adv", days_of_adv),
)
