# The Carbon Arc catalogue screen, from documentation only.

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "data" / "carbon_arc" / "catalogue"
OUT = ROOT / "out" / "alt" / "catalogue"
# History labelled from this date covers the 2017-2020 window.
START_BY = pd.Timestamp("2017-01-01")
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
# A history label date: 3Q2023, 03/2008, March 2024, 03-2026 or 2015.
DATE = re.compile(
    r"(?:(?P<q>[1-4])Q\s*)?"
    r"(?:(?P<mon>[A-Za-z]{3,9})\.?\s+|(?P<mm>\d{1,2})[/-](?:\d{1,2}/)?)?"
    r"(?P<y>(?:19|20)\d{2})(?P<dash>\s*(?:-|–|to\b))?"
)
# Columns that say when a row became known (as-of stamps).
ASOF = re.compile(r"knowledge|as_of|first_seen|on_event_date|^filed$|vendor_published")
# Columns that stamp a delivery or a vendor edition, not the knowledge.
VERSION = re.compile(
    r"^version$|generation_id|drop_partition|receipt_date|ingest|processing_ts|"
    r"^load(ed)?_(at|date)|load_date|publish_datetime"
)
# Columns that record a later overwrite of the same row.
OVERWRITE = re.compile(r"updated|last_update")
# Entity key kinds, from the dictionary's column names, firm first.
KEYS = {
    "ticker": r"ticker",
    "company": r"company_id|company_name|^company$|cik|cusip|isin|figi|lei",
    "brand": r"brand_id|brand_name",
    "zip": r"zip",
    "county": r"county",
    "cbsa": r"cbsa",
    "dma": r"dma",
    "state": r"^state|_state",
    "country": r"country",
    "product": r"product_id|asin|sku",
    "app": r"app_id|bundle_id",
    "artist": r"artist_id",
    "location": r"location_id|store_id|poi",
}
# Documented words that a source's history changes after the fact.
REVISED_TEXT = re.compile(
    r"restates its panel|reweighted|fill rate|claim maturity|reach(?:es|ing) ~?\d+%|"
    r"backfill\w*|dropping out|inorganic decline|data (?:is|are) (?:revised|restated)",
    re.I,
)
# Documented words that a firm panel keeps firms that left.
DEAD_TEXT = re.compile(
    r"(?:delisted|retired|inactive|defunct)[^.]{0,30}(?:names|stocks|companies|firms)|"
    r"live and inactive|survivorship",
    re.I,
)
# Stable ids beside Carbon Arc's own, and ids dated at the event.
STABLE_IDS = re.compile(r"^(cik|cusip|isin|figi|lei)$|cik_current")
DATED_IDS = re.compile(r"on_event_date|period_key")
NO_LAG = {"", "n/a", "none", "historic"}


# A JSON file, or None when missing or saved as an error stub.
def read_json(path: Path):
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return None if isinstance(data, dict) and "missing" in data else data


# The starts named in a history label, earliest first; none if unread.
def history_starts(label) -> list[pd.Timestamp]:
    if not isinstance(label, str):
        return []
    found = []
    for m in DATE.finditer(label):
        month = 1
        if m.group("q"):
            month = 3 * int(m.group("q")) - 2
        elif m.group("mon") and m.group("mon")[:3].lower() in MONTHS:
            month = MONTHS[m.group("mon")[:3].lower()]
        elif m.group("mm") and 1 <= int(m.group("mm")) <= 12:
            month = int(m.group("mm"))
        found.append((pd.Timestamp(int(m.group("y")), month, 1), bool(m.group("dash"))))
    # Dates before a dash open a range; a lone date is a start itself.
    starts = [d for d, dash in found if dash] or [d for d, _ in found]
    return sorted(starts)


# The longest lag a label states, in days; None if it gives no number.
def lag_days(label) -> float | None:
    if not isinstance(label, str):
        return None
    unit = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30}
    if not re.search(r"T\s*\+", label):
        return None
    pat = r"(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*(hour|day|week|month)"
    got = [int(b or a) * unit[u.lower()] for a, b, u in re.findall(pat, label, re.I)]
    return max(got) if got else None


# Whether a lag is stated at all, numeric or not.
def lag_stated(label) -> bool:
    return isinstance(label, str) and label.strip().lower() not in NO_LAG


# Every column a dictionary names, with its description.
def dictionary_columns(dic) -> dict[str, str]:
    cols = {}
    for topic in dic or []:
        for name, spec in (topic.get("columns") or {}).items():
            cols.setdefault(name, (spec or {}).get("description") or "")
    return cols


# Columns sorted into as-of, delivery or version, and overwrite stamps.
def classify_columns(cols) -> dict[str, list[str]]:
    names = sorted(cols)
    asof = [c for c in names if ASOF.search(c)]
    version = [c for c in names if VERSION.search(c) and c not in asof]
    over = [c for c in names if OVERWRITE.search(c) and c not in asof + version]
    return {"asof": asof, "version": version, "overwrite": over}


# The entity key kinds a dictionary carries, firm keys first.
def entity_keys(cols) -> list[str]:
    names = [c.lower() for c in cols]
    return [k for k, pat in KEYS.items() if any(re.search(pat, c) for c in names)]


# Sample rows whose delivery partition marks the history back-filled.
def backfill_in_sample(sample) -> int:
    hits = set()
    for block in (sample or {}).get("samples", []) if isinstance(sample, dict) else []:
        for row in block.get("data") or []:
            for col in ("drop_partition", "ca_drop_partition"):
                if "backfill" in str(row.get(col, "")).lower():
                    hits.add(str(row[col]))
    return len(hits)


# Every text value in a nested document, in order.
def strings(doc) -> list[str]:
    if isinstance(doc, str):
        return [doc]
    if isinstance(doc, dict):
        doc = list(doc.values())
    return [t for item in doc for t in strings(item)] if isinstance(doc, list) else []


# The documentation sentence part around a match, for the evidence.
def snippet(text: str, m: re.Match) -> str:
    start = max(text.rfind(" . ", 0, m.start()) + 3, m.start() - 60)
    end = text.find(" . ", m.end())
    end = min(end if end >= 0 else len(text), m.end() + 60)
    return " ".join(text[start:end].split())


# The four screening answers for one asset, each with its evidence.
def four_answers(info_text: str, facts: dict) -> dict:
    cls, firm = facts["columns"], facts["firm_key"]
    lag, added, first = facts["lag_days"], facts["date_added"], facts["history_start"]
    # When first knowable: an as-of stamp, else the stated lag and listing.
    if cls["asof"]:
        knowable = "dated by " + " and ".join(cls["asof"])
    elif lag is not None or facts["lag_stated"]:
        when = f"T+{lag:g} days" if lag is not None else "a stated lag with no number"
        knowable = f"live rows {when} after their date"
        if added is not None and first is not None and first < added:
            knowable += f" and rows before {added.date()} loaded when listed"
    else:
        knowable = "unknown"
    if facts["backfill_labels"] and knowable != "unknown":
        knowable += " (sample rows carry back-fill loads)"
    # Whether revised: overwrite stamps, documented words, versions.
    said = [snippet(info_text, m) for m in REVISED_TEXT.finditer(info_text)][:1]
    if cls["overwrite"] or said or facts["backfill_labels"]:
        revised = "yes"
        bits = [f"overwrite stamp {c}" for c in cls["overwrite"]] + said
        bits += ["back-filled history"] if facts["backfill_labels"] else []
        revised_evidence = " | ".join(bits)
    elif cls["version"]:
        revised, revised_evidence = "versioned", "delivery stamps " + " ".join(cls["version"])
    else:
        revised, revised_evidence = "unknown", ""
    # Whether dead firms are in: only a firm panel's own words count.
    dead = [snippet(info_text, m) for m in DEAD_TEXT.finditer(info_text)][:1]
    if not firm:
        dead_firms, dead_evidence = "not a firm panel", ""
    elif dead:
        dead_firms, dead_evidence = "yes", dead[0]
    else:
        dead_firms, dead_evidence = "unknown", ""
    # The entity map: dated ids, stable ids, or today's Carbon Arc ids.
    dated = [c for c in facts["column_names"] if DATED_IDS.search(c)]
    stable = [c for c in facts["column_names"] if STABLE_IDS.search(c)]
    if dated:
        emap = "dated ids " + " ".join(dated)
    elif stable:
        emap = "stable ids " + " ".join(stable) + " beside Carbon Arc ids"
    elif firm:
        emap = "Carbon Arc ticker and company ids from today's ontology"
    else:
        emap = "no firm key"
    return {
        "first_knowable": knowable,
        "revised": revised,
        "revised_evidence": revised_evidence,
        "dead_firms": dead_firms,
        "dead_firms_evidence": dead_evidence,
        "entity_map": emap,
    }


# A date like 10/08/2024 or 9/9/2026 as a timestamp, else None.
def added_date(text) -> pd.Timestamp | None:
    got = pd.to_datetime(text, format="%m/%d/%Y", errors="coerce")
    return None if pd.isna(got) else got


# The screen's rules in order: each failure and its pass, by name.
RULES = [
    ("blocked", "open to us"),
    ("no dictionary saved", "dictionary saved"),
    ("history not labelled from 2017 or earlier", "history labelled from 2017 or earlier"),
    ("no firm key", "firm key"),
    ("no as-of column", "as-of column"),
    ("no stated lag", "stated lag, usable for a backtest"),
]


# The first rule a real dataset fails on the way to a backtest.
def first_failure(row: dict) -> str:
    start = row["all_parts_start"]
    ok = [
        not row["blocked"],
        "dictionary" not in row["missing_documents"],
        start is not None and start <= START_BY,
        row["firm_key"],
        row["pit_capable"] == "yes",
        row["lag_stated"],
    ]
    return next((fail for (fail, _), good in zip(RULES, ok) if not good), "")


# One source's row: metadata, dictionary reading and the four answers.
def screen_one(source: dict, folder: Path) -> dict:
    meta, ids = source.get("data") or {}, source["dataset_id"]
    cols, insights, backfill, missing = {}, [], 0, []
    # A source may span several ids: their documents are read together.
    for i in ids:
        dic = read_json(folder / i / "dictionary.json")
        missing += [f"{i} dictionary"] if dic is None else []
        cols.update({k: v for k, v in dictionary_columns(dic).items() if k not in cols})
        sample = read_json(folder / i / "sample.json")
        missing += [f"{i} sample"] if sample is None else []
        backfill += backfill_in_sample(sample)
        got = read_json(folder / i / "insights.json") or {}
        insights += got.get("items", []) if isinstance(got, dict) else []
    info = read_json(folder / ids[0] / "information.json") or source
    text = " . ".join(strings(info))
    web = meta.get("is_webcontent") == "true"
    label = meta.get("Start Date") if web else meta.get("History")
    starts = history_starts(label)
    keys = entity_keys(cols)
    cls = classify_columns(cols)
    lag_text = meta.get("Lag")
    facts = {
        "columns": cls,
        "column_names": sorted(cols),
        "firm_key": bool({"ticker", "company"} & set(keys)),
        "lag_days": lag_days(lag_text),
        "lag_stated": lag_stated(lag_text),
        "date_added": added_date(meta.get("Date Added")),
        "history_start": starts[0] if starts else None,
        "backfill_labels": backfill,
    }
    row = {
        "dataset_id": " ".join(ids),
        "kind": "web catalogue" if web else "dataset",
        "name": source.get("dataset_name") or meta.get("Name"),
        "provider": source.get("provider_name") or meta.get("Provider Name") or "not stated",
        "type": meta.get("Type"),
        "frequency": meta.get("Frequency"),
        "blocked": bool(source.get("blocked")),
        "history_label": label,
        "history_start": facts["history_start"],
        "all_parts_start": starts[-1] if starts else None,
        "date_added": facts["date_added"],
        "lag_label": lag_text,
        "lag_days": None if facts["lag_days"] is None else round(facts["lag_days"], 3),
        "lag_stated": facts["lag_stated"],
        "entity_keys": " ".join(keys) or "none found",
        "firm_key": facts["firm_key"],
        "asof_columns": " ".join(cls["asof"]),
        "version_columns": " ".join(cls["version"]),
        "overwrite_columns": " ".join(cls["overwrite"]),
        "pit_capable": "yes"
        if cls["asof"]
        else ("delivery stamps only" if cls["version"] else "no"),
        "n_columns": len(cols),
        "n_insights": len(insights),
        "n_insights_blocked": sum(1 for x in insights if x.get("blocked")),
        "missing_documents": " ".join(missing),
        **four_answers(text, facts),
    }
    row["fails_at"] = first_failure(row)
    row["usable_for_backtest"] = row["fails_at"] == ""
    return row


# Every source in the saved catalogue, screened; datasets first.
def screen(folder: Path = CATALOGUE) -> pd.DataFrame:
    listing = json.loads((folder / "datasets.json").read_text(encoding="utf-8"))
    rows = [screen_one(s, folder) for s in listing["datasources"]]
    frame = pd.DataFrame(rows)
    frame["traded"] = False
    return frame.sort_values(["kind", "dataset_id"]).reset_index(drop=True)


# The funnel from screened to usable, one rule at a time, for datasets.
def funnel(frame: pd.DataFrame) -> list[dict]:
    fails = frame.loc[frame["kind"] == "dataset", "fails_at"]
    steps = [{"step": "screened", "left": len(fails)}]
    # Each rule removes the datasets that first fail it.
    for i, (_, good) in enumerate(RULES):
        gone = [fail for fail, _ in RULES[: i + 1]]
        steps.append({"step": good, "left": int((~fails.isin(gone)).sum())})
    return steps


# A column's value counts as a plain dict for JSON.
def tally(values: pd.Series) -> dict:
    return {str(k): int(v) for k, v in values.value_counts().items()}


# The headline counts and the denominator line, for summary.json.
def summary(frame: pd.DataFrame) -> dict:
    real = frame[frame["kind"] == "dataset"]
    web = frame[frame["kind"] == "web catalogue"]
    usable = real[real["usable_for_backtest"]]
    n, m = len(real), len(usable)
    return {
        "denominator": f"{n} screened, {m} usable for a backtest, none traded",
        "sources_in_catalogue": len(frame),
        "datasets": n,
        "web_catalogues": len(web),
        "blocked": {"datasets": int(real["blocked"].sum()), "web": int(web["blocked"].sum())},
        "usable_for_backtest": usable["dataset_id"].tolist(),
        "web_catalogues_usable": int(web["usable_for_backtest"].sum()),
        "start_rule": f"every labelled part starts by {START_BY.date()}",
        "funnel": funnel(frame),
        "fails_at": tally(real["fails_at"].replace("", "usable")),
        "pit_capable": tally(real["pit_capable"]),
        "first_knowable_unknown": int((real["first_knowable"] == "unknown").sum()),
        "revised": tally(real["revised"]),
        "dead_firms": tally(real["dead_firms"]),
        "entity_map": tally(real["entity_map"].str.split(" ").str[:2].str.join(" ")),
        "history_start_by_year": tally(real["history_start"].dropna().dt.year),
        "history_unread": int(real["history_start"].isna().sum()),
        "lag_stated": int(real["lag_stated"].sum()),
        "missing_documents": real.loc[real["missing_documents"] != "", "dataset_id"].tolist(),
        "traded": 0,
    }


# The funnel as one horizontal bar chart in the project's petrol blue.
def chart(steps: list[dict], path: Path, saved: str = "") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, bar = "#0B1F33", "#6B7280", "#0F5C7A"
    fig, ax = plt.subplots(figsize=(9, 4.6))
    labels = [s["step"].capitalize() for s in steps][::-1]
    left = [s["left"] for s in steps][::-1]
    ax.barh(labels, left, color=bar, height=0.6)
    # Each bar carries its own count, so no axis is needed.
    for y, v in enumerate(left):
        ax.text(v + 0.8, y, str(v), va="center", fontsize=10, color=ink)
    ax.set_xlim(0, max(left) * 1.12)
    ax.set_xticks([])
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.spines["left"].set_color("#D1D5DB")
    ax.tick_params(axis="y", colors=ink, length=0)
    first, last = steps[0]["left"], steps[-1]["left"]
    ax.set_title(
        "Carbon Arc datasets screened from their documentation",
        loc="left",
        weight="bold",
        color=ink,
        pad=24,
    )
    ax.text(
        0,
        1.03,
        f"{first} screened, {last} usable for a backtest, none traded",
        transform=ax.transAxes,
        fontsize=9.5,
        color=muted,
        va="bottom",
    )
    fig.text(
        0.01,
        0.01,
        f"Based in part on Carbon Arc data. Catalogue saved {saved}.",
        fontsize=8,
        color=muted,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# Writes table, summary, chart: python -m fiam.alt.catalogue_screen
def main(folder: Path = CATALOGUE, out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    frame = screen(folder)
    frame.to_csv(out / "catalogue_screen.csv", index=False)
    result = summary(frame)
    manifest = read_json(folder / "manifest.json") or {}
    result["catalogue_pulled_at"] = str(manifest.get("pulled_at", "unknown"))[:10]
    (out / "summary.json").write_text(json.dumps(result, indent=1, default=str))
    chart(result["funnel"], out / "catalogue_funnel.png", result["catalogue_pulled_at"])
    return result


if __name__ == "__main__":
    report = main()
    print(report["denominator"])
    print(json.dumps({k: report[k] for k in ("funnel", "fails_at", "pit_capable")}, indent=1))
    sys.exit(0)
