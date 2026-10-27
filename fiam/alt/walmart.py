# Walmart deep dive: card panel, spend growth and reported revenue.

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt import common, passport
from fiam.vfinal import sources

ROOT = sources.ROOT
CARBON = sources.DATA / "carbon_arc"
SPEND = CARBON / "snapshot_1" / "CA0056_626_WMT.json.gz"
FOOT = CARBON / "snapshot_1" / "CA0060_45862_WMT.json.gz"
WEB = CARBON / "snapshot_1" / "CA0030_379_WMT.json.gz"
LAUNCHES = CARBON / "snapshot_2" / "CA0043D_450_WMT.json.gz"
PROBE = CARBON / "access" / "free_probe_2026-10-26"
USERS, TRANSACTIONS = PROBE / "debias_wmt_628.json", PROBE / "debias_wmt_627.json"
# The free replies carry no receipt; their folder names the pull day.
PROBE_DAY = pd.Timestamp("2026-10-26")
OUT = ROOT / "out" / "alt" / "walmart"
TICKER = "WMT"
# Walmart's fiscal year ends on 31 January.
YEAR_END_MONTH = 1
# Channel names as the card panel writes them and as the page says them.
CHANNELS = {"Online": "online", "Physical": "in store"}


# A free debias reply: month, channel, spend, reference and debiased.
def load_probe(path: Path = USERS) -> pd.DataFrame:
    reply = json.loads(path.read_text(encoding="utf-8"))
    rows = pd.DataFrame(reply["data"])
    ref = [c for c in rows.columns if c.endswith("_reference") and c.startswith("credit_card")]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(rows["date"]).dt.normalize(),
            "channel": rows["transaction_method"].astype(str),
            "spend": rows[reply["insight_column"]].astype(float),
            "reference": rows[ref[0]].astype(float),
            "debiased": rows["credit_card_spend_debiased"].astype(float),
        }
    )


# One owned monthly set summed over its parts, as date and value.
def load_monthly(path: Path) -> pd.DataFrame:
    rows, value = passport.load(path)
    frame = pd.DataFrame(
        {"date": pd.to_datetime(rows["date"]), "value": pd.to_numeric(rows[value], errors="coerce")}
    )
    return frame.groupby("date", as_index=False)["value"].sum(min_count=1)


# Weeks with a product launch, one row per labelled week.
def load_launches(path: Path = LAUNCHES) -> pd.DataFrame:
    rows, _ = passport.load(path)
    return pd.DataFrame({"date": pd.to_datetime(rows["date"]).drop_duplicates()})


# Users by channel: first month, each January, last full month, growth.
def panel_summary(frame: pd.DataFrame, pulled=PROBE_DAY) -> dict:
    full = frame[frame["date"] <= pd.Timestamp(pulled)]
    wide = full.pivot_table(index="date", columns="channel", values="reference", aggfunc="sum")
    wide["both"] = wide.sum(axis=1, min_count=len(wide.columns))
    out = {}
    # Each channel, then both summed, where a user of both counts twice.
    for name in wide.columns:
        s = wide[name].dropna()
        if s.empty:
            continue
        jan = s[s.index.month == 1]
        out[CHANNELS.get(name, name)] = {
            "first_month": str(s.index[0].date()),
            "first": int(s.iloc[0]),
            "januaries": {str(d.year): int(v) for d, v in jan.items()},
            "last_full_month": str(s.index[-1].date()),
            "last": int(s.iloc[-1]),
            "growth_multiple": round(float(s.iloc[-1] / s.iloc[0]), 4),
        }
    return out


# The panel users within the run window, with its rows dropped count.
def panel(end: pd.Timestamp, path: Path = USERS) -> dict:
    kept, dropped = common.drop_after(load_probe(path), end)
    out = {"source": path.name, "run_end": str(end.date()), "rows_after_end_dropped": dropped}
    out["note"] = (
        "users are the US card panel members who spent in each channel that month, "
        "as Carbon Arc's free debias reply gives them; the last full month is the last month "
        "ended by the reply's pull day and by the run's end"
    )
    return out | {"channels": panel_summary(kept)}


# Every monthly input in one frame: spend, users, debiased and context.
def monthly(end: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    spend, value = passport.load(SPEND)
    spend = spend.assign(date=pd.to_datetime(spend["date"]), spend=spend[value].astype(float))
    users = load_probe(USERS)
    dropped = {}
    parts = {
        "card_spend": spend[["date", "transaction_method", "spend"]],
        "panel_users": users,
        "panel_transactions": load_probe(TRANSACTIONS),
        "foot_traffic": load_monthly(FOOT),
        "web_visits": load_monthly(WEB),
        "launch_weeks": load_launches(),
    }
    # Every set loses its rows after the run's end before any comparison.
    for name, frame in parts.items():
        parts[name], dropped[name] = common.drop_after(frame, end)
    m = parts["card_spend"].groupby("date")["spend"].sum(min_count=2).to_frame()
    wide = parts["panel_users"].pivot_table(index="date", columns="channel", values="reference")
    m["users_online"], m["users_in_store"] = wide.get("Online"), wide.get("Physical")
    m["users"] = wide.sum(axis=1, min_count=2)
    m["transactions"] = parts["panel_transactions"].groupby("date")["reference"].sum(min_count=2)
    m["debiased"] = parts["panel_users"].groupby("date")["debiased"].sum(min_count=2)
    m["foot_traffic"] = parts["foot_traffic"].set_index("date")["value"]
    m["web_visits"] = parts["web_visits"].set_index("date")["value"]
    weeks = parts["launch_weeks"]["date"] + pd.offsets.MonthEnd(0)
    m["launch_weeks"] = weeks.value_counts().reindex(m.index).fillna(0)
    return m.reset_index(), dropped


# Fiscal quarters with all three months, summed, and their growth.
def quarterly(m: pd.DataFrame, last_month: int = YEAR_END_MONTH) -> pd.DataFrame:
    frame = pd.concat(
        [m.reset_index(drop=True), common.fiscal_quarter(m["date"], last_month)], axis=1
    )
    g = frame.groupby(["fiscal_year", "quarter"])
    cols = [c for c in m.columns if c != "date"]
    q = g[cols].sum(min_count=3)
    q["months"] = g["date"].nunique()
    q["first_month"], q["last_month"] = g["date"].min(), g["date"].max()
    q = q[q["months"] == 3].reset_index()
    q["per_user"] = q["spend"] / q["users"]
    for col in ("spend", "per_user", "debiased", "foot_traffic", "web_visits", "launch_weeks"):
        q[f"{col}_yoy"] = common.yoy(q, col)
    return q


# Reported revenue per fiscal quarter, as first filed, with growth.
def revenue(sec: pd.DataFrame, last_month: int = YEAR_END_MONTH) -> pd.DataFrame:
    sec = sec.sort_values("end").reset_index(drop=True)
    out = pd.concat([sec, common.fiscal_quarter(sec["end"], last_month)], axis=1)
    out = out.drop_duplicates(["fiscal_year", "quarter"], keep="first")
    out = out.rename(columns={"val": "revenue", "end": "period_end", "tag": "revenue_tag"})
    out["revenue_yoy"] = common.yoy(out, "revenue")
    return out[["fiscal_year", "quarter", "period_end", "revenue", "revenue_tag", "revenue_yoy"]]


# A quarter's name and months, "Q4 FY2020 Nov 2019 to Jan 2020".
def label(row) -> str:
    first, last = pd.Timestamp(row["first_month"]), pd.Timestamp(row["last_month"])
    start = f"{first:%b}" if first.year == last.year else f"{first:%b %Y}"
    return f"Q{row['quarter']} FY{row['fiscal_year']} {start} to {last:%b %Y}"


# The plain statement of the run's end and the quarters it leaves.
def statement(last: pd.Timestamp, both: pd.DataFrame) -> str:
    names = " and ".join(label(r) for r in both.to_dict("records")) or "none"
    return (
        f"The default run ends {last.date()}. Card data start in January 2019, so year on "
        f"year growth needs a fiscal quarter of 2020 against the same quarter of 2019, and "
        f"{len(both)} Walmart fiscal quarters have it ({names}). Rows dated later were dropped "
        "from every Carbon Arc set before any comparison and SEC revenue is read through the "
        "sealed reader"
    )


# A rounded float, or None for a gap.
def num(x, digits: int = 4):
    return None if x is None or pd.isna(x) else round(float(x), digits)


# The whole deep dive on the run window; None when it is refused.
def build(end=None, out: Path = OUT) -> dict | None:
    last = common.run_end(end)
    # A run past the cutoff while sealed stops before reading anything.
    if last is None:
        return None
    m, dropped = monthly(last)
    q = quarterly(m)
    permno = common.permnos([TICKER], [last]).iloc[0]
    sec = common.sec_quarters([permno], common.REVENUE_TAGS)
    q = q.merge(revenue(sec), on=["fiscal_year", "quarter"], how="left")
    both = q.dropna(subset=["spend_yoy", "revenue_yoy"])
    corr = {
        name: common.correlation(q[f"{col}_yoy"], q["revenue_yoy"])
        for name, col in (
            ("raw_card_spend", "spend"),
            ("spend_per_panel_user", "per_user"),
            ("carbon_arc_debiased_index", "debiased"),
            ("foot_traffic", "foot_traffic"),
        )
    }
    report = {
        "about": "Walmart deep dive, Carbon Arc card panel and context against SEC revenue",
        "credit": common.CREDIT,
        "seal": {
            "unsealed": sources.unsealed(),
            "run_end": str(last.date()),
            "rows_after_end_dropped": dropped,
            "yoy_quarters": len(both),
            "statement": statement(last, both),
        },
        "fiscal_calendar": (
            "Walmart's fiscal year ends 31 January and is named for the year it ends in, so Q1 "
            "is February to April, Q2 May to July, Q3 August to October and Q4 November to "
            "January"
        ),
        "panel": panel(last),
        "panel_by_month": [
            {
                "month": str(r["date"].date()),
                "users_online": num(r["users_online"], 0),
                "users_in_store": num(r["users_in_store"], 0),
            }
            for _, r in m.iterrows()
        ],
        "measures": {
            "raw_card_spend": "CA0056 spend, online plus in store, summed over the quarter",
            "spend_per_panel_user": (
                "the quarter's spend over its panel users summed over months and both channels "
                "(a user of both channels counts twice)"
            ),
            "carbon_arc_debiased_index": (
                "Carbon Arc's own credit_card_spend_debiased, summed over channels and months; "
                "its formula is not stated and it is not spend over the channel's users"
            ),
            "revenue": (
                "SEC as-filed total revenue (tag order "
                f"{', '.join(common.REVENUE_TAGS[:2])}, ...), consolidated over Walmart US, "
                "International and Sam's Club, while the card panel is US only"
            ),
        },
        "quarters": [
            {
                "quarter": label(r),
                "card_spend_yoy": num(r["spend_yoy"]),
                "spend_per_user_yoy": num(r["per_user_yoy"]),
                "debiased_index_yoy": num(r["debiased_yoy"]),
                "revenue_yoy": num(r["revenue_yoy"]),
                "foot_traffic_yoy": num(r["foot_traffic_yoy"]),
                "web_visits_yoy": num(r["web_visits_yoy"]),
                "launch_weeks": num(r["launch_weeks"], 0),
                "revenue_period_end": None
                if pd.isna(r["period_end"])
                else str(r["period_end"].date()),
                "revenue_tag": None if pd.isna(r["revenue_tag"]) else r["revenue_tag"],
            }
            for _, r in q.iterrows()
        ],
        "correlation_with_revenue_growth": corr,
        "context": context(m),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "walmart.json").write_text(json.dumps(report, indent=1, default=str))
    chart(m, q, report, out / "walmart.png")
    return report


# Foot traffic and web visits: their months beside the card months.
def context(m: pd.DataFrame) -> dict:
    out = {}
    # Each context set's own span inside the window and its overlap.
    for col in ("foot_traffic", "web_visits"):
        have = m.dropna(subset=[col, "spend"])
        out[col] = {
            "months_overlapping_card_spend": len(have),
            "first_month": None if have.empty else str(have["date"].min().date()),
            "last_month": None if have.empty else str(have["date"].max().date()),
            "monthly_growth_correlation_with_card_spend": common.correlation(
                have[col].pct_change(), have["spend"].pct_change()
            ),
        }
    return out


# Each series as an index, 100 in its first month shared by all three.
def indexed(m: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    frame = m.set_index("date")[cols]
    base = frame.dropna().index.min()
    return 100 * frame / frame.loc[base] if pd.notna(base) else frame * np.nan


# One page: panel users, growth by quarter, context and the notes.
def chart(m: pd.DataFrame, q: pd.DataFrame, report: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    from fiam.report.charts import ALT, BENCH, INK, MARKET, MUTED, OURS, style
    from fiam.vfinal.exhibits.common import check_text

    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5))
    ax = axes[0, 0]
    dates = m["date"]
    ax.plot(dates, m["users_online"] / 1e6, color=OURS, linewidth=2, label="Online")
    ax.plot(dates, m["users_in_store"] / 1e6, color=BENCH, linewidth=2, label="In store")
    ax.legend(frameon=False, loc="upper left")
    style(ax, "Card panel users by month", "Millions", subtitle="US card users in the panel")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax = axes[0, 1]
    both = q.dropna(subset=["spend_yoy"])
    at = np.arange(len(both))
    bars = [
        ("spend_yoy", "Card spend", OURS),
        ("per_user_yoy", "Spend per panel user", ALT),
        ("revenue_yoy", "Reported revenue", MARKET),
    ]
    # Three bars per quarter, one for each growth measure.
    for k, (col, name, colour) in enumerate(bars):
        ax.bar(at + (k - 1) * 0.27, 100 * both[col], 0.26, color=colour, label=name)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(at, [f"Q{r.quarter} FY{r.fiscal_year}" for r in both.itertuples()])
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.08), ncol=3)
    style(
        ax, "Year on year growth by fiscal quarter", "Percent", subtitle="Walmart fiscal quarters"
    )
    ax = axes[1, 0]
    idx = indexed(m, ["spend", "foot_traffic", "web_visits"])
    looks = [("spend", "Card spend", OURS), ("foot_traffic", "Foot traffic", BENCH)]
    looks.append(("web_visits", "Web visits", ALT))
    # One line per set, each 100 in the first month all three share.
    for col, name, colour in looks:
        ax.plot(idx.index, idx[col], color=colour, linewidth=2, label=name)
    ax.legend(frameon=False, loc="upper left")
    base = idx.dropna().index.min()
    sub = f"Index, {base:%B %Y} is 100" if pd.notna(base) else "Index"
    style(ax, "Card spend beside foot traffic and web visits", "", subtitle=sub)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax = axes[1, 1]
    ax.axis("off")
    ax.text(0, 1, "\n".join(lines(report)), va="top", fontsize=10, color=INK, linespacing=1.5)
    note = (
        f"{common.CREDIT}. Revenue from SEC filings as first filed. Rows after "
        f"{pd.Timestamp(report['seal']['run_end']):%d %B %Y} are sealed and left out."
    )
    fig.text(0.01, 0.0, note, fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.canvas.draw()
    check_text(fig)
    fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# The chart's reading panel, one plain line each.
def lines(report: dict) -> list[str]:
    seal, corr = report["seal"], report["correlation_with_revenue_growth"]
    end = pd.Timestamp(seal["run_end"])
    out = [f"The run ends {end:%d %B %Y}".replace(" 0", " ")]
    out.append(f"{seal['yoy_quarters']} fiscal quarters have year on year growth")
    out += ["", f"Correlation with revenue growth over {corr['raw_card_spend']['n']} quarters"]
    names = {
        "raw_card_spend": "Card spend",
        "spend_per_panel_user": "Spend per panel user",
        "carbon_arc_debiased_index": "Carbon Arc debiased index",
        "foot_traffic": "Foot traffic",
    }
    # Each measure's correlation, or a plain note when there is none.
    for key, name in names.items():
        r = corr[key]["r"]
        out.append(f"{name} {'not enough quarters' if r is None else f'{r:.2f}'}")
    out.append(f"{corr['raw_card_spend']['n']} quarters are too few for a firm correlation")
    out.append("")
    chan = report["panel"]["channels"]
    # Each channel's growth over the window in words.
    for key in ("online", "in store"):
        c = chan.get(key)
        if c:
            first, last = pd.Timestamp(c["first_month"]), pd.Timestamp(c["last_full_month"])
            out.append(
                f"Panel users {key} grew {c['growth_multiple']:.2f} times "
                f"from {first:%b %Y} to {last:%b %Y}"
            )
    out.append("The card panel is US only and revenue is consolidated")
    return out


# uv run python -m fiam.alt.walmart [--end YYYY-MM-DD]
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Walmart card panel against SEC revenue")
    parser.add_argument("--end", default=None, help="last date read, 2020-12-31 while sealed")
    args = parser.parse_args(argv)
    report = build(args.end)
    # A refused run has printed its one line already.
    if report is None:
        return 1
    print(report["seal"]["statement"])
    print(json.dumps(report["panel"]["channels"], indent=1))
    print(json.dumps(report["quarters"], indent=1))
    print(json.dumps(report["correlation_with_revenue_growth"], indent=1))
    print(json.dumps(report["context"], indent=1))
    return 0


# Run with uv run python -m fiam.alt.walmart
if __name__ == "__main__":
    sys.exit(main())
