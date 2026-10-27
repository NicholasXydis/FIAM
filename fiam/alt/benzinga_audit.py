# Benzinga CA0035 event rows checked against SEC filings.

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt.common import share

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "carbon_arc" / "snapshot_1"
OUT = ROOT / "out" / "alt" / "benzinga"
EASTERN = "America/New_York"
# Each bought insight, its kind and the column holding its event label.
INSIGHTS = {"497": "offerings", "501": "deals", "461": "insider"}
OFFER_FORMS = ("424B1", "424B2", "424B3", "424B4", "424B5", "S-1", "S-3")
DEAL_ITEMS = ("1.01", "2.01")
INSIDER_FORMS = ("4",)
# A filing matches within this many sessions either side of the week.
WINDOW = 5
# Blind mode: SEC rows after this day are sealed, so windows end by it.
SEAL_DAY = pd.Timestamp("2020-12-31")
# The chance rate: the same rows and firms, labels moved back 26 weeks.
PLACEBO_WEEKS = 26
# The filing clock may run up to 5 hours late: a sensitivity test.
EARLY_HOURS = 5
GROUPS = ("all", "listed", "departed", "unmapped")


# The three bought insights as one frame of kind, ticker and label.
def load_benzinga(folder: Path = SNAPSHOT) -> pd.DataFrame:
    parts = []
    for insight, kind in INSIGHTS.items():
        with gzip.open(folder / f"CA0035_{insight}.json.gz", "rt", encoding="utf-8") as fh:
            got = json.load(fh)
        rows = pd.DataFrame(got["data"])
        parts.append(
            pd.DataFrame(
                {
                    "kind": kind,
                    "ticker": rows["entity_name"].astype(str),
                    "label": pd.to_datetime(rows["date"]),
                    "event": rows[got["insight_column"]].astype(str),
                }
            )
        )
    frame = pd.concat(parts, ignore_index=True)
    frame["year"] = frame["label"].dt.year
    return frame


# The pull receipts: when each insight was pulled and its stated end.
def receipts(folder: Path = SNAPSHOT) -> dict:
    out = {}
    for insight, kind in INSIGHTS.items():
        r = json.loads((folder / f"CA0035_{insight}.receipt.json").read_text())
        out[kind] = {
            "rows": r["rows"],
            "pulled_at": r["pulled_at"],
            "resolution": r["metadata"]["payload"]["filters"]["date_resolution"],
            "requested_end": r["metadata"]["payload"]["filters"]["date_range"]["end_date"],
            "table_max_date": r["metadata"]["table_max_date"],
        }
    return out


# Owned sets whose order count and row count can be set side by side.
EVIDENCE = (
    "snapshot_1/CA0056_626_WMT",
    "snapshot_1/CA0060_45862_WMT",
    "snapshot_1/CA0030_379_WMT",
    "snapshot_1/CA0043B_11676",
    "snapshot_2/CA0038_343_ten_retail",
    "snapshot_2/CA0043D_450_WMT",
)


# Each owned set's order count beside its rows and its days by parts.
def record_evidence(root: Path = SNAPSHOT.parent) -> list[dict]:
    out = []
    for name in EVIDENCE:
        receipt, data = root / f"{name}.receipt.json", root / f"{name}.json.gz"
        # A set not saved on this machine is left out of the evidence.
        if not receipt.exists() or not data.exists():
            continue
        book = json.loads(receipt.read_text())
        filters = book["metadata"]["payload"].get("filters") or {}
        span = filters.get("date_range") or {}
        with gzip.open(data, "rt", encoding="utf-8") as fh:
            got = json.load(fh)
        rows = pd.DataFrame(got["data"])
        ids = {"date", "entity_id", "entity_name", "entity_representation", got["insight_column"]}
        parts = [c for c in rows.columns if c not in ids]
        n_parts = len(rows[parts].drop_duplicates()) if parts else 1
        days = None
        # Days in the asked range, the finest grain a set can hold.
        if span.get("start_date") and span.get("end_date"):
            days = len(pd.date_range(span["start_date"][:10], span["end_date"][:10]))
        out.append(
            {
                "set": name.split("/")[-1],
                "resolution": filters.get("date_resolution"),
                "order_records": (book.get("order") or {}).get("total_records_count"),
                "rows_delivered": book["rows"],
                "days_asked": days,
                "parts": n_parts,
                "days_times_parts": None if days is None else days * n_parts,
            }
        )
    return out


# The order's record count to the audited rows, one step at a time.
def reconcile(folder: Path = SNAPSHOT) -> dict:
    order = json.loads((folder / "bundle_order.json").read_text())
    steps = [
        {
            "step": "order record count",
            "rows": int(order["total_records_count"]),
            "why": f"Carbon Arc's count for order {order['order_id']}, the three insights together",
        }
    ]
    delivered, dupes, repeats = {}, {}, {}
    for insight, kind in INSIGHTS.items():
        book = json.loads((folder / f"CA0035_{insight}.receipt.json").read_text())
        with gzip.open(folder / f"CA0035_{insight}.json.gz", "rt", encoding="utf-8") as fh:
            got = json.load(fh)
        rows = pd.DataFrame(got["data"])
        # The saved rows must be the reply's own total and the receipt's.
        if not len(rows) == got["total"] == book["rows"]:
            raise ValueError(f"CA0035_{insight}: rows, reply total and receipt disagree")
        delivered[kind] = len(rows)
        dupes[kind] = int(rows.duplicated().sum())
        repeats[kind] = int(rows.duplicated(["entity_name", "date"]).sum())
    total = sum(delivered.values())
    steps.append(
        {
            "step": "rows delivered, the replies' own totals",
            "rows": total,
            "by_insight": delivered,
            "change": total - steps[0]["rows"],
            "why": (
                "the order counts Carbon Arc's records before the roll-up to the asked weekly "
                "resolution, the reply gives one row per ticker, week and label; the bundle has "
                "one order count only, so the gap cannot be split by insight from saved files"
            ),
        }
    )
    loaded = len(load_benzinga(folder))
    steps.append(
        {
            "step": "rows the audit loads",
            "rows": loaded,
            "change": loaded - total,
            "why": "load_benzinga keeps every delivered row, none is dropped or merged",
        }
    )
    return {
        "steps": steps,
        "kept_as_delivered": {
            "exact_duplicate_rows": dupes,
            "rows_repeating_a_ticker_and_week": repeats,
            "note": (
                "insider repeats differ by ticker_exclusively_mentioned and deal repeats by "
                "deal type; both are distinct rows in the reply and stay"
            ),
        },
        "evidence_order_counts_are_pre_rollup": record_evidence(folder.parent),
        "evidence_reading": (
            "daily sets rolled up to months have order records equal to the asked days times "
            "the parts (CA0056 and CA0060 exactly, CA0030 within 4), quarterly and undated "
            "sets have records equal to rows, and the CA0043D event set rolled up to weeks has "
            f"871 records for 352 rows, as CA0035 has {steps[0]['rows']:,} for {total:,}"
        ),
    }


# Rows and distinct tickers per kind and label year: the drift table.
def drift(rows: pd.DataFrame) -> pd.DataFrame:
    g = rows.groupby(["kind", "year"])
    return pd.DataFrame({"rows": g.size(), "tickers": g["ticker"].nunique()}).reset_index()


# Labels against the calendar: weekdays, and labels after the pull.
def label_check(rows: pd.DataFrame, pulls: dict) -> dict:
    out = {"weekday_counts": {}, "labels_after_pull": {}}
    for kind, part in rows.groupby("kind"):
        days = part["label"].dt.day_name().value_counts()
        out["weekday_counts"][kind] = {str(k): int(v) for k, v in days.items()}
        pulled = pd.Timestamp(pulls[kind]["pulled_at"]).tz_convert(EASTERN).tz_localize(None)
        late = part["label"] > pulled.normalize()
        out["labels_after_pull"][kind] = {
            "rows": int(late.sum()),
            "latest_label": str(part["label"].max().date()),
            "pulled_on": str(pulled.date()),
        }
    return out


# Each label's window: 5 sessions before its week to 5 sessions after.
def windows(labels: pd.Series, sessions: pd.DatetimeIndex, n: int = WINDOW):
    days = sessions.to_numpy()
    label = pd.to_datetime(labels).to_numpy()
    # The week ends on the label and starts six days before it.
    first = np.searchsorted(days, label - np.timedelta64(6, "D"), side="left")
    last = np.searchsorted(days, label, side="right") - 1
    lo_i, hi_i = first - n, last + n
    ok = (lo_i >= 0) & (hi_i < len(days)) & (last >= first)
    lo = np.where(ok, days[np.clip(lo_i, 0, len(days) - 1)], np.datetime64("NaT", "ns"))
    hi = np.where(ok, days[np.clip(hi_i, 0, len(days) - 1)], np.datetime64("NaT", "ns"))
    return pd.Series(lo, index=labels.index), pd.Series(hi, index=labels.index)


# A filing's public day: the Eastern date of its available_at.
def public_day(available_at: pd.Series) -> pd.Series:
    at = pd.to_datetime(available_at, utc=True).dt.tz_convert(EASTERN)
    return at.dt.tz_localize(None).dt.normalize()


# The end of each label's day in UTC, plus extra days of lag.
def label_end(labels: pd.Series, lag_days: int = 0) -> pd.Series:
    end = pd.to_datetime(labels) + pd.Timedelta(days=lag_days, hours=23, minutes=59, seconds=59)
    return end.dt.tz_localize(EASTERN).dt.tz_convert("UTC")


# Per row: same-kind filings of its stock in its window, first, nearest.
def match(rows: pd.DataFrame, filings: pd.DataFrame) -> pd.DataFrame:
    left = rows[["permno", "kind", "label", "lo", "hi"]].dropna(subset=["permno", "lo"])
    left = left.assign(rid=left.index, permno=left["permno"].astype("int64"))
    right = filings[["permno", "kind", "day", "available_at"]]
    both = left.merge(right, on=["permno", "kind"], how="inner")
    both = both[(both["day"] >= both["lo"]) & (both["day"] <= both["hi"])]
    out = pd.DataFrame(index=rows.index)
    out["n_filings"] = both.groupby("rid").size().reindex(rows.index).fillna(0).astype(int)
    # The earliest filing in the window: when SEC first showed the event.
    first = both.sort_values("available_at").drop_duplicates("rid").set_index("rid")
    out["first_public"] = first["available_at"].reindex(rows.index)
    out["first_day"] = first["day"].reindex(rows.index)
    both = both.assign(gap=(both["day"] - both["label"]).abs())
    near = both.sort_values(["gap", "available_at"]).drop_duplicates("rid").set_index("rid")
    out["nearest_public"] = near["available_at"].reindex(rows.index)
    out["nearest_day"] = near["day"].reindex(rows.index)
    return out


# A table cell as plain JSON: numbers as numbers, gaps as None.
def plain(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value.item() if isinstance(value, np.generic) else value


# Match rate, chance rate, look-ahead and lead days for a set of rows.
def stats(part: pd.DataFrame) -> dict:
    covered = part[part["covered"]]
    hit = covered[covered["matched"]]
    # Days from the nearest filing's acceptance to the label day's end.
    days = (label_end(hit["label"]) - hit["nearest_public"]).dt.total_seconds() / 86400

    # A quantile of the lead days, or None with no matched row.
    def q(p: float):
        return None if days.empty else round(float(days.quantile(p)), 2)

    return {
        "rows": len(part),
        "mapped": int(part["permno"].notna().sum()),
        "covered": len(covered),
        "matched": len(hit),
        "match_rate": share(len(hit), len(covered)),
        "placebo_rate": share(covered["placebo_matched"].sum(), len(covered)),
        "lookahead": int(hit["lookahead"].sum()),
        "lookahead_share": share(hit["lookahead"].sum(), len(hit)),
        "lookahead_share_t1": share(hit["lookahead_t1"].sum(), len(hit)),
        "lookahead_share_early_clock": share(hit["lookahead_early"].sum(), len(hit)),
        "lookahead_share_nearest": share(hit["lookahead_nearest"].sum(), len(hit)),
        "days_acceptance_to_label_median": q(0.5),
        "days_p25": q(0.25),
        "days_p75": q(0.75),
    }


# The audit table: kind by year by group, plus every year together.
def table(rows: pd.DataFrame) -> pd.DataFrame:
    out = []
    for kind, by_kind in rows.groupby("kind"):
        # Each year, then all audited years, for each group of firms.
        for year, part in [*by_kind.groupby("year"), ("2014-2020", by_kind)]:
            for group in GROUPS:
                sub = part if group == "all" else part[part["group"] == group]
                out.append({"kind": kind, "year": str(year), "group": group, **stats(sub)})
    return pd.DataFrame(out)


# Where the nearest matched filing falls against the label week.
def week_bucket(rows: pd.DataFrame) -> dict:
    out = {}
    for kind, part in rows[rows["matched"]].groupby("kind"):
        off = (part["nearest_day"] - part["label"]).dt.days
        out[kind] = {
            "matched": len(part),
            "in_week_ending_on_label": share(off.between(-6, 0).sum(), len(part)),
            "in_week_after_label": share(off.between(1, 7).sum(), len(part)),
            "before_label_week": share((off < -6).sum(), len(part)),
            "offset_days_counts": {
                int(k): int(v) for k, v in off.value_counts().sort_index().items()
            },
        }
    return out


# SEC filing-weeks of every indexed firm that Benzinga shows, by group.
def recall(rows: pd.DataFrame, filings: pd.DataFrame, departed: set) -> dict:
    f, start = filings, rows["lo"].min()
    f = f[(f["day"] >= start) & (f["day"] <= rows["hi"].max())]
    units = f.assign(week=f["day"] + pd.to_timedelta((4 - f["day"].dt.dayofweek) % 7, "D"))
    units = units[units["week"] <= SEAL_DAY].drop_duplicates(["permno", "kind", "week"])
    left = units.assign(uid=np.arange(len(units)))
    right = rows.dropna(subset=["permno", "lo"])[["permno", "kind", "lo", "hi"]]
    right = right.assign(permno=right["permno"].astype("int64"))
    both = left.merge(right, on=["permno", "kind"])
    seen = set(both.loc[(both["day"] >= both["lo"]) & (both["day"] <= both["hi"]), "uid"])
    left["seen"] = left["uid"].isin(seen)
    left["group"] = np.where(left["permno"].isin(departed), "departed", "listed")
    left["year"] = left["week"].dt.year.astype(str)
    out = {}
    # Coverage grows over time and leavers file early, so years apart too.
    for keys in (["kind", "group"], ["kind", "year", "group"]):
        for key, part in left.groupby(keys):
            period = key[1] if len(key) == 3 else "2014-2020"
            out.setdefault(key[0], {}).setdefault(period, {})[key[-1]] = {
                "filing_weeks": len(part),
                "with_a_benzinga_row": int(part["seen"].sum()),
                "share": share(part["seen"].sum(), len(part)),
            }
    return out


# SEC filings of each audited kind from the registry, on its clock.
def sec_filings() -> tuple[pd.DataFrame, set]:
    from fiam.v4 import data

    keep = ["permno", "kind", "available_at"]
    offers = data.table("edgar_filings", ["form"], where={"form": set(OFFER_FORMS)})
    deals = data.table("events", ["item", "amendment"], where={"item": set(DEAL_ITEMS)})
    deals = deals[~deals["amendment"]].drop_duplicates(["accession", "permno"])
    insider = data.table("sec_insiders", ["form"], where={"form": set(INSIDER_FORMS)})
    insider = insider.drop_duplicates(["accession", "permno"])
    frame = pd.concat(
        [
            offers.assign(kind="offerings")[keep],
            deals.assign(kind="deals")[keep],
            insider.assign(kind="insider")[keep],
        ],
        ignore_index=True,
    )
    frame["day"] = public_day(frame["available_at"])
    # A stock is covered if our SEC index holds any filing of it at all.
    index = data.table("edgar_filings", ["form"])["permno"]
    covered = set(index.astype("int64")) | set(insider["permno"].astype("int64"))
    return frame, covered


# Tickers to PERMNO on each label's date, through the dated links.
def map_permnos(rows: pd.DataFrame) -> tuple[pd.Series, set]:
    from fiam.v4 import data, links

    lk = data.table("links", None)
    permno = links.permno_by_symbol(lk, rows["ticker"].to_numpy(), rows["label"].to_numpy())
    exits = data.table("exits", ["exit_date"])
    departed = set(exits.loc[exits["exit_date"] <= SEAL_DAY, "permno"].astype("int64"))
    return pd.Series(permno.to_numpy(), index=rows.index, dtype="Int64"), departed


# Every row measured: windows, groups, matches, chance and look-ahead.
def audit(rows, sessions, filings, permno, departed, covered) -> pd.DataFrame:
    rows = rows.copy()
    rows["lo"], rows["hi"] = windows(rows["label"], sessions)
    rows["permno"] = permno
    rows["group"] = np.where(
        rows["permno"].isna(),
        "unmapped",
        np.where(rows["permno"].isin(departed), "departed", "listed"),
    )
    rows["covered"] = rows["permno"].isin(covered).fillna(False).astype(bool)
    got = match(rows, filings)
    rows = rows.join(got)
    rows["matched"] = rows["n_filings"] > 0
    end, end_t1 = label_end(rows["label"]), label_end(rows["label"], 1)
    rows["lookahead"] = rows["matched"] & (rows["first_public"] > end)
    rows["lookahead_t1"] = rows["matched"] & (rows["first_public"] > end_t1)
    rows["lookahead_nearest"] = rows["matched"] & (rows["nearest_public"] > end)
    # The clock reads some UTC digits as Eastern, up to 5 hours late.
    early = rows["first_public"] - pd.Timedelta(hours=EARLY_HOURS)
    rows["lookahead_early"] = rows["matched"] & (early > end)
    # The placebo: labels 26 weeks earlier, the same firms and kinds.
    moved = rows.assign(label=rows["label"] - pd.Timedelta(weeks=PLACEBO_WEEKS))
    moved["lo"], moved["hi"] = windows(moved["label"], sessions)
    rows["placebo_matched"] = match(moved, filings)["n_filings"] > 0
    return rows


# Runs the audit and writes audit.json, audit.csv and the chart.
def main(folder: Path = SNAPSHOT, out: Path = OUT) -> dict:
    from fiam.v4 import data

    out.mkdir(parents=True, exist_ok=True)
    every = load_benzinga(folder)
    pulls = receipts(folder)
    sessions = data.calendar().index
    lo, hi = windows(every["label"], sessions)
    # Only rows whose whole window is public by the seal are audited.
    inside = hi.notna() & (hi <= SEAL_DAY)
    rows = every[inside]
    permno, departed = map_permnos(rows)
    filings, covered = sec_filings()
    done = audit(rows, sessions, filings, permno, departed, covered)
    result = table(done)
    counts = drift(every)
    report = {
        "piece": "PLAN §12.4 piece 9, Benzinga CA0035 vs SEC filings",
        "rule": (
            f"a row matches if an SEC filing of its type for the same PERMNO is public within "
            f"{WINDOW} sessions before the first session of its labelled week (label minus 6 "
            f"days to the label) or {WINDOW} sessions after the label"
        ),
        "types": {
            "offerings": list(OFFER_FORMS),
            "deals": [f"8-K item {i}" for i in DEAL_ITEMS],
            "insider": ["Form 4"],
        },
        "receipts": pulls,
        "labels": label_check(every, pulls),
        "rows_total": int(len(every)),
        "row_reconciliation": reconcile(folder),
        "rows_audited": int(len(rows)),
        "rows_not_audited_sealed": int((~inside).sum()),
        "audit_window": [str(rows["label"].min().date()), str(rows["label"].max().date())],
        "drift_rows_per_year": {
            k: dict(zip(p["year"].astype(str), p["rows"].astype(int)))
            for k, p in counts.groupby("kind")
        },
        "drift_tickers_per_year": {
            k: dict(zip(p["year"].astype(str), p["tickers"].astype(int)))
            for k, p in counts.groupby("kind")
        },
        "headline": {
            r["kind"]: {k: plain(r[k]) for k in r.index if k not in ("kind", "year", "group")}
            for _, r in result[
                (result["year"] == "2014-2020") & (result["group"] == "all")
            ].iterrows()
        },
        "by_group": {
            f"{r['kind']} {r['group']}": {
                "rows": int(r["rows"]),
                "covered": int(r["covered"]),
                "match_rate": plain(r["match_rate"]),
                "placebo_rate": plain(r["placebo_rate"]),
                "lookahead_share": plain(r["lookahead_share"]),
            }
            for _, r in result[result["year"] == "2014-2020"].iterrows()
        },
        "week_bucket": week_bucket(done),
        "sec_recall": recall(done, filings, departed),
        "placebo_weeks": PLACEBO_WEEKS,
        "seal": str(SEAL_DAY.date()),
        "not_computed": [
            "match rates for 2021-2026 labels: the registry seals SEC rows after 2020-12-31 "
            "and offers only per-year counts for them",
            "departed firms after 2020: the exits and links tables are sealed after 2020-12-31",
            "today's Carbon Arc entity map: its links start at the 2026-10-22 pull, so the "
            "sealed reader drops them; tickers are mapped by the CRSP ticker on the label date",
        ],
        "traded": False,
    }
    report["row_reconciliation"]["steps"].append(
        {
            "step": "rows audited, whole window public by the seal",
            "rows": int(len(rows)),
            "change": int(len(rows)) - int(len(every)),
            "why": f"labels whose window ends after {SEAL_DAY.date()} stay sealed, counted only",
        }
    )
    result.insert(0, "section", "match")
    drift_rows = counts.assign(section="drift", year=counts["year"].astype(str), group="all")
    pd.concat([result, drift_rows], ignore_index=True).to_csv(out / "audit.csv", index=False)
    (out / "audit.json").write_text(json.dumps(report, indent=1, default=str))
    chart(done, out / "benzinga_vs_sec.png")
    return report


# Rows per day offset over the data's own span, so bars sum to rows.
def day_counts(part: pd.DataFrame) -> pd.Series:
    off = (part["nearest_day"] - part["label"]).dt.days.dropna().astype(int)
    lo, hi = (min(-13, int(off.min())), max(7, int(off.max()))) if len(off) else (-13, 7)
    return off.value_counts().reindex(range(lo, hi + 1), fill_value=0)


# Small multiples: earliest SEC filing day minus the label, per kind.
def chart(rows: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, bar, shade = "#0B1F33", "#6B7280", "#0F5C7A", "#F3F4F6"
    names = {"offerings": "Offerings", "deals": "Deals", "insider": "Insider news"}
    fig, axes = plt.subplots(1, 3, figsize=(10, 4.4), sharey=False)
    hit, first = rows[rows["matched"]], []
    for ax, kind in zip(axes, ["offerings", "deals", "insider"]):
        part = hit[hit["kind"] == kind]
        counts = day_counts(part)
        ax.axvspan(0.5, counts.index[-1] + 0.5, color=shade, zorder=0)
        ax.bar(counts.index, counts.to_numpy(), color=bar, width=0.8, zorder=2)
        ax.axvline(0, color=ink, linewidth=1, zorder=3)
        late = share(part["lookahead_nearest"].sum(), len(part))
        first.append(f"{share(part['lookahead'].sum(), len(part)) or 0:.0%}")
        pct = "n/a" if late is None else f"{late:.0%}"
        ax.set_title(
            f"{names[kind]}{chr(10)}{int(counts.sum()):,} matched rows",
            loc="left",
            fontsize=10.5,
            color=ink,
            weight="bold",
        )
        ax.text(
            0.98,
            0.95,
            f"{pct} filed{chr(10)}after the label",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color=ink,
        )
        ax.set_xticks([-13, -6, 0, 7])
        ax.set_xticklabels(["-13", "-6", "Friday label", "+7"], fontsize=8.5, color=muted)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#D1D5DB")
        ax.tick_params(colors=muted, labelsize=8.5)
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Benzinga rows", color=muted)
    fig.suptitle(
        "Days from the Friday label to the nearest matching SEC filing, 2014 to 2020",
        x=0.01,
        ha="left",
        fontsize=12,
        color=ink,
        weight="bold",
    )
    fig.text(
        0.01,
        0.01,
        "Shaded days are after the label. Counting the earliest filing in the window instead, "
        f"{', '.join(first[:2])} and {first[2]} come after it. "
        "Based in part on Carbon Arc data and SEC EDGAR.",
        fontsize=8,
        color=muted,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    got = main()
    print(json.dumps({k: got[k] for k in ("rows_total", "rows_audited", "headline")}, indent=1))
