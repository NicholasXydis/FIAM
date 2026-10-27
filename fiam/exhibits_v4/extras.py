# The extra exhibits (PLAN §13.6): K1, capacity, 2026 on its own.

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fiam.exhibits_v4 import common as c
from fiam.exhibits_v4.common import BENCH, INK, MARKET, MUTED, OURS, Inputs
from fiam.v4.construct.optimizer import SPILL_ADV
from fiam.v4.report import table_9_1

# A fill this close to 10% of ADV was held at the cap (float noise).
AT_CAP = 1 - 1e-6
# The engine's event for an order with no price that day (not the cap).
UNFILLED = "unfilled"
# The sub-period shown on its own, beside the full window.
SUB_YEAR = 2026


# A frame drawn as a plain table on an axis, team colours.
def draw_table(ax, frame: pd.DataFrame, size: float = 9.0) -> None:
    ax.axis("off")
    t = ax.table(cellText=frame.to_numpy(), colLabels=list(frame.columns),
                 rowLabels=list(frame.index), loc="center", cellLoc="right")  # fmt: skip
    t.auto_set_font_size(False)
    t.set_fontsize(size)
    t.scale(1, 1.45)
    for (row, col), cell in t.get_celld().items():
        cell.set_edgecolor("#E5E7EB")
        cell.get_text().set_color(INK if row == 0 or col == -1 else MUTED)
        if row == 0:
            cell.get_text().set_weight("bold")


# K1's numbers: IR = IC x √breadth x TC, from the supplied inputs.
def k1_frame(k1: pd.DataFrame) -> pd.DataFrame:
    f = k1.copy()
    if "period" in f.columns:
        f = f.set_index("period")
    f["implied_ir"] = f["ic"] * np.sqrt(f["breadth"]) * f["tc"]
    return f


# K1 fundamental law: IC, breadth, TC and the IR they imply.
def fundamental_law(x: Inputs):
    f = k1_frame(x.k1)
    fig, (ax, tab) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [2, 3]})
    pos = np.arange(len(f))
    real = "realised_ir" in f.columns
    width = 0.36 if real else 0.6
    ax.bar(pos - (width / 2 if real else 0), f["implied_ir"], width, color=OURS,
           label="Implied by IC x √breadth x TC")  # fmt: skip
    if real:
        ax.bar(pos + width / 2, f["realised_ir"], width, facecolor="white", edgecolor=OURS,
               linewidth=1.4, label="Realised as supplied")  # fmt: skip
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(pos, [str(p) for p in f.index])
    low, high = ax.get_ylim()
    ax.set_ylim(min(low, 0), high + 0.35 * (high - min(low, 0)))
    ax.legend(frameon=False, loc="upper left")
    c.panel(ax, "Information ratio", "IR")
    shown = pd.DataFrame(
        {"IC": f["ic"].map("{:.3f}".format), "Breadth a year": f["breadth"].map("{:,.0f}".format),
         "TC": f["tc"].map("{:.2f}".format), "Implied IR": f["implied_ir"].map(c.num)},
        index=[str(p) for p in f.index],
    )  # fmt: skip
    if real:
        shown["Realised IR"] = f["realised_ir"].map(c.num).to_numpy()
    draw_table(tab, shown)
    sub = ("Grinold 1989 · breadth is N times the forecast's information turnover "
           "· TC is the book's correlation with the unconstrained paper book")  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, c.headline(fig, "The Fundamental Law (K1)", sub)))
    return fig, f


# Each planned trade and whether a fill reached 10% of its ADV.
def planned_trades(x: Inputs) -> pd.DataFrame:
    t = x.trades
    if t.empty:
        return pd.DataFrame(columns=["formed", "permno", "first", "closes", "held_back"])
    # The spill's ADV is the formation's, so the cap is read as of then.
    t = t.assign(formed=c.stamps(t["formed"]).to_numpy())
    t = c.as_of(t, x.adv, "adv", on="formed")
    t["capped"] = t["dollars"].abs() >= AT_CAP * SPILL_ADV * t["adv"]
    g = t.groupby(["formed", "permno"])
    return pd.DataFrame(
        {"first": g["date"].min(), "closes": g["date"].nunique(), "held_back": g["capped"].any()}
    ).reset_index()


# Capacity by year: NAV, trades held back by the cap, days to exit.
def capacity(x: Inputs):
    d = x.d
    years = sorted(d.index.year.unique())
    plan = planned_trades(x)
    plan["year"] = pd.DatetimeIndex(plan["first"]).year
    p = x.positions[x.positions["date"].isin(x.holding_days)]
    p = c.as_of(p, x.adv, "adv")
    # Days to exit: the position over 10% of its ADV (PLAN §10.2).
    p["exit_days"] = p["value"].abs() / (SPILL_ADV * p["adv"])
    p["year"] = pd.DatetimeIndex(p["date"]).year
    ev = x.events
    unfilled = ev[ev["kind"] == UNFILLED] if len(ev) else ev
    rows = []
    for y in years:
        mine, held = plan[plan["year"] == y], p[p["year"] == y]
        n = len(mine)
        rows.append({
            "year": y,
            "partial": c.partial(d.index, y),
            "nav_end_bn": float(d.loc[d.index.year == y, "nav"].iloc[-1]) / 1e9,
            "nav_avg_bn": float(d.loc[d.index.year == y, "nav"].mean()) / 1e9,
            "planned_trades": n,
            "held_back": int(mine["held_back"].sum()),
            "held_back_pct": 100 * mine["held_back"].mean() if n else np.nan,
            "over_one_close_pct": 100 * (mine["closes"] > 1).mean() if n else np.nan,
            "unfilled_events": int((pd.DatetimeIndex(unfilled["date"]).year == y).sum())
            if len(unfilled) else 0,
            "median_days_to_exit": held["exit_days"].median(),
            "p90_days_to_exit": held["exit_days"].quantile(0.9),
            "positions_without_adv": int(held["adv"].isna().sum()),
        })  # fmt: skip
    frame = pd.DataFrame(rows).set_index("year")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
    ticks = [f"{y}{c.charts.BR}partial" if frame.loc[y, "partial"] else str(y) for y in years]
    for ax, col, title, fmt in [
        (axes[0], "nav_end_bn", "NAV at the year's last session ($bn)", "{:.2f}"),
        (axes[1], "held_back_pct", "Planned trades held back by the 10% cap (%)", "{:.0f}"),
        (axes[2], "median_days_to_exit", "Median days to exit at 10% of ADV", "{:.2f}"),
    ]:
        v = frame[col]
        ax.bar(np.arange(len(v)), v.fillna(0), 0.6, color=OURS)
        for k, value in enumerate(v):
            if value == value:
                ax.annotate(fmt.format(value), (k, value), xytext=(0, 3), ha="center",
                            textcoords="offset points", fontsize=8, color=MUTED)  # fmt: skip
        ax.set_xticks(np.arange(len(v)), ticks)
        c.panel(ax, title)
    sub = (f"{x.period} · a planned trade is one name at one formation · held back when a "
           f"fill reached 10% of its ADV and the rest waited for a later close")  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, c.headline(fig, "Capacity Over Time", sub)))
    return fig, frame


# One period's numbers, all compounded, never annualised.
def period_stats(r, before, hurdle, sp, d) -> dict:
    cum = lambda s: float((1 + s).prod() - 1) * 100  # noqa: E731
    return {
        "Return (%)": cum(r),
        "Before costs (%)": cum(before),
        "T-bill + 4% (%)": cum(hurdle),
        "S&P 500 (%)": cum(sp),
        "Active over T-bill + 4% (points)": cum(r) - cum(hurdle),
        "Max drawdown (%)": table_9_1.drawdown(r) * 100,
        "Worst day (%)": float(r.min()) * 100,
        "Daily beta to the S&P 500": c.beta(r, d["rf"], sp),
        "Average gross (%)": float(d["gross"].mean()) * 100,
        "Average net (%)": float(d["net"].mean()) * 100,
        "Average names": float((d["n_long"] + d["n_short"]).mean()),
    }


# The variant run's rows over the sub-period (2026 ex-day rule B).
def variant(x: Inputs, days: pd.DatetimeIndex) -> pd.DataFrame | None:
    if x.rule_b is None:
        return None
    b = x.rule_b.set_index("date") if "date" in x.rule_b.columns else x.rule_b
    b = b.copy()
    b.index = pd.DatetimeIndex(c.stamps(b.index))
    return b.reindex(days)


# 2026 as its own sub-period beside the full window (PLAN §13.6).
def sub_period(x: Inputs):
    d, before = x.d, c.before_costs(x)
    days = d.index[d.index.year == SUB_YEAR]
    if days.empty:
        raise ValueError(f"the window holds no {SUB_YEAR} session")
    name = f"{SUB_YEAR} {days[0]:%b} to {days[-1]:%b}"
    cols = {
        name: period_stats(d.loc[days, "ret"], before[days], x.hurdle[days], x.sp[days],
                           d.loc[days]),
        "Full window": period_stats(d["ret"], before, x.hurdle, x.sp, d),
    }  # fmt: skip
    b = variant(x, days)
    if b is not None:
        cols[f"{SUB_YEAR} rule B"] = period_stats(
            b["ret"], b["ret"] + (b["cost"] + b["borrow"]) / b["nav"].shift(1).bfill(),
            x.hurdle[days], x.sp[days], b)  # fmt: skip
    frame = pd.DataFrame(cols)
    fig, (ax, tab) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [5, 6]})
    lines = [("S&P 500", x.sp[days], MARKET, 1.2, dict(dashes=(4, 3), alpha=0.45)),
             ("T-bill + 4%", x.hurdle[days], BENCH, 1.6, {}),
             ("Strategy", d.loc[days, "ret"], OURS, 2.2, {})]  # fmt: skip
    if b is not None:
        lines.append(("Rule B", b["ret"], OURS, 1.2, dict(dashes=(2, 2))))
    for label, r, colour, width, extra in lines:
        path = ((1 + r).cumprod() - 1) * 100
        ax.plot(path.index, path, color=colour, linewidth=width, label=label, **extra)
    ax.axhline(0, color="#D1D5DB", linewidth=0.8)
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=8.5)
    c.panel(ax, f"Cumulative return in {SUB_YEAR} (%)")
    ax.xaxis.set_major_formatter(c.charts.mdates.DateFormatter("%b"))
    ax.xaxis.set_major_locator(c.charts.mdates.MonthLocator())
    ax.set_xlim(days[0], days[-1])
    shown = frame.map(lambda v: c.num(v, 2 if abs(v) < 10 else 1))
    draw_table(tab, shown, 8.5)
    sub = f"{name} · after all modelled costs · every figure compounded, none annualised"
    top = c.headline(fig, f"{SUB_YEAR} as Its Own Sub-Period", sub)
    if x.notes_2026:
        c.footnote(fig, " · ".join(x.notes_2026))
    fig.tight_layout(rect=(0, 0, 1, top))
    return fig, frame


# The extras by file stem; K1 runs only when its inputs are given.
EXTRAS = (
    ("extra_k1_fundamental_law", fundamental_law),
    ("extra_capacity", capacity),
    ("extra_2026_sub_period", sub_period),
)
