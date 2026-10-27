# The data passport: which bought datasets can be backtested.

import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt import coverage

ROOT = Path(__file__).resolve().parents[2]
CARBON = ROOT / "data" / "carbon_arc"
CATALOGUE = CARBON / "catalogue"
OUT = ROOT / "out" / "alt" / "passport"
PENDING = "pending snapshot 2"
# The free re-download of snapshot 1's sets, compared row by row.
REFETCH = "snapshot_1_refetch"
# Folders that hold bought sets, each with its receipts.
SNAPSHOTS = ("snapshot_1", "snapshot_2")
# Rows dated on or after this are the sealed years: counted, never read.
SEAL = pd.Timestamp("2021-01-01")
# Six named retail failures by CRSP PERMNO, plus aliases.
NAMED = {
    "Sears": (89757, ["Sears"]),
    "Bon-Ton": (76847, ["Bon-Ton"]),
    "Pier 1": (51692, ["Pier 1"]),
    "GNC": (12660, ["GNC"]),
    "Ascena": (30737, ["Ascena Retail"]),
    "J.C. Penney": (18403, ["JCPenney", "J. C. Penney"]),
}
# The scorecard's delisting years.
SCORE_FROM, SCORE_TO = pd.Timestamp("2017-01-01"), pd.Timestamp("2020-12-31")
# A year counts as full once it holds half the median year's rows.
FULL_SHARE = 0.5


# One saved reply as rows, with the name of its value column.
def load(path: Path) -> tuple[pd.DataFrame, str]:
    reply = json.loads(gzip.decompress(path.read_bytes()))
    return pd.DataFrame(reply.get("data") or []), reply.get("insight_column", "")


# The first year in a catalogue history note ("2019-Present").
def first_year(text) -> int | None:
    found = re.findall(r"(?:19|20)\d\d", str(text or ""))
    return int(found[0]) if found else None


# Days in a lag note: "T + 3 Days" is 3; other notes have no number.
def lag_days(text) -> int | None:
    found = re.match(r"\s*T\s*\+\s*(\d+)\s*Day", str(text or ""))
    return int(found.group(1)) if found else None


# Rows per year, and the first year with any and with a full share.
def true_start(dates: pd.Series) -> dict:
    years = pd.to_datetime(dates, errors="coerce").dropna().dt.year
    if years.empty:
        return {"rows_by_year": {}, "first_year": None, "first_full_year": None}
    counts = years.value_counts().sort_index()
    full = counts[counts >= FULL_SHARE * counts.median()]
    return {
        "rows_by_year": {str(y): int(n) for y, n in counts.items()},
        "first_year": int(counts.index[0]),
        "first_full_year": int(full.index[0]),
    }


# Whole days from one date to another, or None when either is missing.
def days(start, end) -> int | None:
    if start is None or end is None or pd.isna(start) or pd.isna(end):
        return None
    return (pd.Timestamp(str(end)[:10]) - pd.Timestamp(str(start)[:10])).days


# Claimed lag against the refresh and pull times in the receipt.
def lag(meta: dict, pulled: str, dates: pd.Series, claimed) -> dict:
    last = pd.to_datetime(dates, errors="coerce").max() if len(dates) else pd.NaT
    top = meta.get("table_max_date")
    out = {"claimed": claimed, "claimed_days": lag_days(claimed), "table_max_date": top}
    out |= {"refreshed": meta.get("refreshed_date"), "pulled": pulled}
    out["refresh_minus_table_max_days"] = days(top, meta.get("refreshed_date"))
    out["pull_minus_table_max_days"] = days(top, pulled)
    out["last_label"] = None if pd.isna(last) else str(last.date())
    # A label after the pull is a period's end, so that period was partial.
    out["last_label_after_pull"] = bool(not pd.isna(last) and days(pulled, last) > 0)
    return out


# Share of snapshot 1's rows rewritten or gone in snapshot 2.
def rewritten(old: pd.DataFrame, new: pd.DataFrame, value: str, pulled=None) -> dict:
    keys = [c for c in old.columns if c != value]
    a, b = old.drop_duplicates(keys), new.drop_duplicates(keys)
    dated = "date" in a.columns
    # The period still open at the first pull may change; it is left out.
    if dated and pulled is not None:
        a = a[pd.to_datetime(a["date"]) <= pd.Timestamp(str(pulled)[:10])]
    both = a.merge(b, on=keys, how="left", suffixes=("", "_new"), indicator=True)
    gone = (both["_merge"] == "left_only").to_numpy()
    x = pd.to_numeric(both[value], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(both[f"{value}_new"], errors="coerce").to_numpy(dtype=float)
    numeric = ~np.isnan(x) & ~np.isnan(y)
    text = both[value].astype(str).to_numpy() != both[f"{value}_new"].astype(str).to_numpy()
    changed = ~gone & np.where(numeric, ~np.isclose(x, y, rtol=1e-9, atol=0), text)
    early = pd.to_datetime(both["date"]).lt(SEAL).to_numpy() if dated else np.zeros(len(both), bool)
    # Rows new in snapshot 2 but dated inside snapshot 1's span: backfill.
    span = pd.to_datetime(a["date"]).max() if dated and len(a) else None
    added = b.merge(a[keys], on=keys, how="left", indicator=True)
    added = added[added["_merge"] == "left_only"]
    if span is not None:
        added = added[pd.to_datetime(added["date"]) <= span]
    out = {"rows_compared": len(both), "changed": int(changed.sum()), "gone": int(gone.sum())}
    out["added_inside_span"] = len(added)
    out["share_rewritten"] = round((out["changed"] + out["gone"]) / max(len(both), 1), 6)
    out["pre_2021_rows"] = int(early.sum())
    out["pre_2021_rewritten"] = int(((changed | gone) & early).sum())
    out["pre_2021_share"] = round(out["pre_2021_rewritten"] / max(int(early.sum()), 1), 6)
    return out


# Re-buy prices quoted for snapshot 2, by set name, if a plan was made.
def rebuy_quotes(root: Path = CARBON) -> dict:
    plan = root / "snapshot_2" / "rebuy.plan.json"
    if not plan.exists():
        return {}
    items = json.loads(plan.read_text(encoding="utf-8")).get("items") or []
    return {i["name"]: i.get("price") for i in items}


# Snapshot 2's same-name file against snapshot 1's, else why not.
def revision(name: str, pulled: str, root: Path = CARBON) -> dict:
    old, new = root / "snapshot_1" / f"{name}.json.gz", root / "snapshot_2" / f"{name}.json.gz"
    if old.exists() and new.exists():
        rows, value = load(old)
        return {"status": "compared"} | rewritten(rows, load(new)[0], value, pulled)
    if not old.exists():
        return {"status": "new in snapshot 2", "why": "first bought in snapshot 2, no earlier copy"}
    price = rebuy_quotes(root).get(name)
    # A zero quote cannot be bought by API, so nothing was re-bought.
    if price is not None and float(price) == 0.0:
        return {"status": "not re-bought", "why": "the re-buy quoted 0.0 and bought nothing"}
    return {"status": PENDING}


# A frame's columns as numbers where every value reads as one.
def numeric(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for c in out.columns:
        x = pd.to_numeric(out[c], errors="coerce")
        # Text stays text unless every present value is a number.
        if x.notna().sum() == out[c].notna().sum():
            out[c] = x.astype(float)
        else:
            out[c] = out[c].astype(str)
    return out


# Rows compared as sorted numbers to 1e-9, never as raw bytes.
def same_rows(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    out = {"rows_purchase": len(old), "rows_download": len(new)}
    if sorted(old.columns) != sorted(new.columns) or len(old) != len(new):
        return (
            {"status": "differs"}
            | out
            | {"columns_match": sorted(old.columns) == sorted(new.columns)}
        )
    cols = sorted(old.columns)
    a, b = numeric(old[cols]), numeric(new[cols])
    a = a.sort_values(cols, kind="stable").reset_index(drop=True)
    b = b.sort_values(cols, kind="stable").reset_index(drop=True)
    diff = np.zeros(len(a), dtype=bool)
    worst = 0.0
    for c in cols:
        both = a[c].dtype == float and b[c].dtype == float
        # Numbers agree within 1e-9 of their size; text must be equal.
        if both:
            x, y = a[c].to_numpy(), b[c].to_numpy()
            diff |= ~np.isclose(x, y, rtol=1e-9, atol=0, equal_nan=True)
            scale = np.maximum(np.abs(x), np.abs(y))
            rel = np.where(scale > 0, np.abs(x - y) / np.where(scale > 0, scale, 1), 0)
            worst = max(worst, float(np.nanmax(rel, initial=0.0)))
        else:
            diff |= a[c].astype(str).to_numpy() != b[c].astype(str).to_numpy()
    out |= {"rows_changed": int(diff.sum()), "largest_relative_change": worst}
    return {"status": "identical to the purchase" if not diff.any() else "differs"} | out


# The free re-download of a snapshot 1 set against the purchase.
def download(name: str, root: Path = CARBON) -> dict:
    old, again = root / "snapshot_1" / f"{name}.json.gz", root / REFETCH / f"{name}.json.gz"
    if not old.exists():
        return {"status": "not tried", "why": "bought in snapshot 2"}
    if not again.exists():
        return {"status": "refused (409)", "why": "no re-download file was saved"}
    return same_rows(load(old)[0], load(again)[0])


# Owned rows' entities in the form the coverage matcher reads.
def row_entities(rows: pd.DataFrame) -> list[dict]:
    if rows.empty or "entity_name" not in rows:
        return []
    ids = rows[["entity_id", "entity_name", "entity_representation"]].drop_duplicates()
    ids.columns = ["carc_id", "carc_name", "entity_representation_name"]
    return ids.to_dict("records")


# Stock keys for the six named firms, with their spoken names added.
def named_keys(links: pd.DataFrame) -> pd.DataFrame:
    keys = coverage.stock_keys(links, [p for p, _ in NAMED.values()])
    extra = [
        {"permno": p, "how": "name", "key": coverage.compact(n)}
        for p, names in NAMED.values()
        for n in names
    ]
    return pd.concat([keys, pd.DataFrame(extra)]).drop_duplicates()


# Per firm, the routes by which an entity list names it.
def seen(keys: pd.DataFrame, carc: pd.DataFrame) -> dict:
    flag = coverage.flags(keys, carc).set_index("permno")
    out = {}
    for firm, (permno, _) in NAMED.items():
        row = flag.loc[permno] if permno in flag.index else None
        routes = [] if row is None else [h for h in ("ticker", "name", "brand") if row[h]]
        out[firm] = routes
    return out


# The survivorship scorecard for one dataset: named six and delistings.
def scorecard(lists: dict, rows: dict) -> dict:
    out = {"named_in_list": lists["named"], "named_in_rows": rows["named"]}
    out["delistings_2017_2020"] = len(lists["dead"])
    out["delistings_in_list"] = int(lists["dead"].sum())
    out["delistings_in_rows"] = int(rows["dead"].sum())
    return out


# One owned file's entry, and which delistings its list and rows name.
def entry(receipt: Path, cover: dict, keys6: pd.DataFrame, dead: pd.DataFrame, dead_keys) -> tuple:
    book = json.loads(receipt.read_text(encoding="utf-8"))
    name = receipt.name.removesuffix(".receipt.json")
    meta = book.get("metadata") or {}
    payload = meta.get("payload") or {}
    insight = int(payload.get("insight", {}).get("insight_id"))
    dataset = name.split("_")[0]
    info = json.loads((CATALOGUE / dataset / "information.json").read_text(encoding="utf-8"))
    stated = (info.get("data") or {}).get("History")
    rows, _ = load(receipt.with_name(f"{name}.json.gz"))
    dates = rows["date"] if "date" in rows else pd.Series(dtype=str)
    start = {"stated": stated, "stated_year": first_year(stated)}
    start["requested"] = ((payload.get("filters") or {}).get("date_range") or {}).get("start_date")
    start |= true_start(dates)
    if start["stated_year"] and start["first_year"]:
        start["first_year_minus_stated"] = start["first_year"] - start["stated_year"]
    claimed = (info.get("data") or {}).get("Lag")
    carc_list = coverage.carc_keys(coverage.entities(insight))
    carc_rows = coverage.carc_keys(row_entities(rows))
    lists = {"named": seen(keys6, carc_list), "dead": flagged(dead_keys, carc_list, dead)}
    has = {"named": seen(keys6, carc_rows), "dead": flagged(dead_keys, carc_rows, dead)}
    out = {"file": name, "dataset": dataset, "insight": insight}
    out |= {"snapshot": receipt.parent.name, "bought": str(book.get("pulled_at"))[:10]}
    out["measures"] = coverage.INSIGHTS.get(insight, (dataset, ""))[1]
    out |= {"rows": book.get("rows"), "framework_id": book.get("framework_id")}
    out |= {"ontology_version": meta.get("ontology_version"), "entities": payload.get("entities")}
    out |= {"start": start, "lag": lag(meta, book.get("pulled_at"), dates, claimed)}
    out["coverage"] = cover.get(insight)
    out["revision"] = revision(name, book.get("pulled_at"))
    out["download"] = download(name)
    out["scorecard"] = scorecard(lists, has)
    return out, lists["dead"], has["dead"]


# Which delisted stocks an entity list covers, by ticker or name.
def flagged(keys: pd.DataFrame, carc: pd.DataFrame, dead: pd.DataFrame) -> pd.Series:
    flag = coverage.flags(keys, carc).set_index("permno")["covered"]
    return dead["permno"].map(flag).fillna(False).astype(bool)


# Every owned file's entry, the delisting list and the summary chart.
def build(snapshots=SNAPSHOTS) -> dict:
    from fiam.v4 import data

    found, uni, stat = coverage.stock_flags()
    last = set(uni.loc[uni["in_last"], "permno"])
    cover = {i: coverage.summary(f, stat, last) for i, f in found.groupby("insight")}
    links = data.table("links", None)
    dead = stat[(stat["exit_date"] >= SCORE_FROM) & (stat["exit_date"] <= SCORE_TO)]
    dead_keys = coverage.stock_keys(links, dead["permno"])
    keys6 = named_keys(links)
    receipts = [r for f in snapshots for r in sorted((CARBON / f).glob("*.receipt.json"))]
    made = [entry(r, cover, keys6, dead, dead_keys) for r in receipts]
    entries = [e for e, _, _ in made]
    add_panel(entries)
    # Each 2017-2020 delisting with the sets whose list or rows name it.
    gone = dead[["permno", "exit_date", "group"]].astype(str).assign(in_list="", in_rows="")
    gone["in_list"] = [[e["file"] for e, f, _ in made if f.iloc[i]] for i in range(len(dead))]
    gone["in_rows"] = [[e["file"] for e, _, r in made if r.iloc[i]] for i in range(len(dead))]
    passport = {
        "about": "Carbon Arc data passport, PLAN §12.4 piece 7; counts, dates and coverage only",
        "snapshot_2": snapshot_two(entries),
        "universe": "fiam.v4 universe new_long, month ends 2015-01 to 2020-12",
        "named_permnos": {k: v[0] for k, v in NAMED.items()},
        "delistings_2017_2020": gone.to_dict("records"),
        "datasets": entries,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "passport.json").write_text(json.dumps(passport, indent=1, default=str))
    chart(entries, OUT / "passport.png")
    return passport


# The card set's panel users from the free debias reply, sealed window.
def add_panel(entries: list[dict], end=None) -> None:
    from fiam.alt import common, walmart
    from fiam.v4 import sources

    last = pd.Timestamp(end) if end is not None else common.CUTOFF
    # Once unsealed the panel runs to the reply's last full month.
    if end is None and sources.unsealed():
        last = walmart.PROBE_DAY
    for e in entries:
        # Only the card spend set has a panel reply beside it.
        if e["dataset"] == "CA0056" and walmart.USERS.exists():
            e["panel"] = walmart.panel(last, walmart.USERS)


# The panel line for the text panel, or None without a panel field.
def panel_line(entries: list[dict]) -> str | None:
    found = [e["panel"] for e in entries if e.get("panel")]
    # No card set with a panel reply, so no line.
    if not found:
        return None
    c = found[0]["channels"]
    on, store = c.get("online"), c.get("in store")
    # Both channels are needed for the one line.
    if not on or not store:
        return None
    first, last = pd.Timestamp(on["first_month"]), pd.Timestamp(on["last_full_month"])
    return (
        f"Card panel users {first:%b %Y} to {last:%b %Y} grew "
        f"{on['growth_multiple']:.1f}x online, {store['growth_multiple']:.1f}x in store"
    )


# Snapshot 2 per set: compared, not re-bought or newly bought.
def snapshot_two(entries: list[dict]) -> dict:
    out: dict = {}
    for e in entries:
        out.setdefault(e["revision"]["status"], []).append(e["file"])
    out["download_again"] = {}
    for e in entries:
        out["download_again"].setdefault(e["download"]["status"], []).append(e["file"])
    return out


# Dots per dataset on one axis, one style per series, legend below.
def dots(ax, labels: list, series: list, title: str, unit: str) -> None:
    from fiam.report.charts import style

    at = np.arange(len(labels))
    for values, name, look in series:
        x = [np.nan if v is None else v for v in values]
        ax.scatter(x, at, s=64, label=name, zorder=3, **look)
    ax.set_yticks(at, labels)
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=3)
    style(ax, title, "", subtitle=unit)


# Snapshot 2 and the free download in words, one line each.
def snapshot_lines(entries: list[dict]) -> list[str]:
    rev = [e["revision"]["status"] for e in entries]
    got = [e["download"]["status"] for e in entries]
    out = []
    if rev.count("compared"):
        out.append(f"{rev.count('compared')} sets bought again and compared")
    if rev.count("not re-bought"):
        out.append(f"Rebuy of {rev.count('not re-bought')} sets quoted 0.0 so none was bought")
    if got.count("identical to the purchase"):
        out.append(f"Free download again identical for {got.count('identical to the purchase')}")
    if got.count("differs"):
        out.append(f"Free download again differs for {got.count('differs')}")
    if got.count("refused (409)"):
        out.append(f"Free download again refused for {got.count('refused (409)')}")
    new = [e for e in entries if e["revision"]["status"] == "new in snapshot 2"]
    # New sets named with their bought day written out in words.
    for e in new:
        day = pd.Timestamp(e["bought"]).strftime("%d %B %Y").lstrip("0")
        out.append(f"{e['dataset']} {e['measures']} new on {day}")
    if rev.count(PENDING):
        out.append(f"{rev.count(PENDING)} sets pending snapshot 2")
    return out


# One page: coverage of listed and delisted, true start, lag, revisions.
def chart(entries: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt

    from fiam.report.charts import ALT, BENCH, INK, MUTED, OURS, style

    rows = [e for e in entries if e["coverage"]]
    labels = [f"{e['dataset']} {e['measures']}" for e in rows]
    hollow = {"facecolors": "white", "edgecolors": MUTED, "linewidths": 1.5}
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5))
    ax, at = axes[0, 0], np.arange(len(rows))
    listed = [100 * e["coverage"]["listed_share"] for e in rows]
    gone = [100 * e["coverage"]["delisted_share"] for e in rows]
    ax.barh(at - 0.2, listed, 0.38, color=OURS, label="Still listed in 2020")
    ax.barh(at + 0.2, gone, 0.38, color=BENCH, label="Delisted 2015 to 2020")
    ax.set_yticks(at, labels)
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=2)
    style(ax, "Universe stocks each set's entity list names", "", subtitle="Percent of group")
    start = [
        ([e["start"]["stated_year"] for e in rows], "Catalogue says", hollow),
        ([e["start"]["first_year"] for e in rows], "First row", {"color": ALT}),
        ([e["start"]["first_full_year"] for e in rows], "First full year", {"color": OURS}),
    ]
    dots(axes[0, 1], labels, start, "Stated start against true start", "Year")
    # A table end date after the refresh is no data day, so it is left out.
    seen = [e["lag"]["refresh_minus_table_max_days"] for e in rows]
    seen = [None if s is None or s < 0 else s for s in seen]
    lags = [
        ([e["lag"]["claimed_days"] for e in rows], "Claimed", hollow),
        (seen, "Refresh after last data day", {"color": OURS}),
    ]
    dots(axes[1, 0], labels, lags, "Claimed lag against the receipts", "Days")
    ax = axes[1, 1]
    ax.axis("off")
    lines = ["Snapshot 2"] + snapshot_lines(entries) + [""]
    lines.append("Named failures in each set's entity list")
    for firm in rows[0]["scorecard"]["named_in_list"] if rows else []:
        hits = sum(bool(e["scorecard"]["named_in_list"][firm]) for e in rows)
        lines.append(f"{firm} in {hits} of {len(rows)} sets")
    if rows:
        dead = rows[0]["scorecard"]["delistings_2017_2020"]
        lines += ["", f"Universe delistings 2017 to 2020 number {dead}"]
        lines += [
            f"{e['dataset']} {e['measures']} lists {e['scorecard']['delistings_in_list']}"
            for e in rows
        ]
    extra = panel_line(entries)
    # The panel line closes the text, when the card set has one.
    if extra:
        lines += ["", extra]
    ax.text(0, 1, "\n".join(lines), va="top", fontsize=10, color=INK, linespacing=1.5)
    note = (
        "Based in part on Carbon Arc data. Counts, dates and coverage only, never a forecast input."
    )
    fig.text(0.01, 0.0, note, fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# Run with uv run python -m fiam.alt.passport
if __name__ == "__main__":
    book = build()
    for e in book["datasets"]:
        c = e["coverage"] or {}
        print(
            e["file"],
            e["start"]["first_year"],
            e["start"]["stated_year"],
            e["lag"]["claimed_days"],
            e["lag"]["refresh_minus_table_max_days"],
            c.get("listed_share"),
            c.get("delisted_share"),
            e["revision"]["status"],
            e["download"]["status"],
        )
    print(json.dumps(book["snapshot_2"], indent=1))
    print("\n".join(snapshot_lines(book["datasets"])))
