# Builds the bundle: uv run -m fiam.build_data <folder> [--archive <d>].

import os
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from fiam import data, paths

CHARS = "chars_final_with_names.parquet"
FILINGS = "8k_20150101_20260831_identified.parquet"
CHAR_LIST = "factor_char_list.csv"

FIRST_DAY, LAST_MONTH = pd.Timestamp("2015-01-01"), pd.Timestamp("2026-08-31")
# WRDS archive panels stop here, so they never drive a 2026 decision.
LAST_ARCHIVE_MONTH = pd.Timestamp("2025-12-31")

# IDs and extras kept beside the 147. The rest of the 51 is unused.
IDENTIFIERS = ["permco", "gvkey", "iid", "date", "ticker", "company_name", "gics", "sic", "naics"]
IDENTIFIERS += ["ff49", "common", "primary_sec", "exch_main", "obs_main", "prc", "me"]
IDENTIFIERS += ["me_company", "shares", "adjfct", "dolvol", "bidask", "size_grp"]
LABEL_COLUMNS = ["ret", "ret_exc", "ret_exc_wins", "ret_local", "source_crsp"]

ITEMS = {
    "item_101_contract": "1.01",
    "item_102_contract_termination": "1.02",
    "item_201_acquisition": "2.01",
    "item_202_earnings": "2.02",
    "item_205_impairment": "2.05",
    "item_206_distress": "2.06",
    "item_401_auditor_change": "4.01",
    "item_402_nonreliance": "4.02",
    "item_502_management_change": "5.02",
    "item_701_regfd": "7.01",
    "item_801_other_event": "8.01",
}

# Word counts, a simple tone gauge for research. No book signal uses it.
TERMS = {
    "text_negative": r"\b(?:loss|losses|decline|impair(?:ed|ment)|restatement|investigation"
    r"|litigation|default|bankruptcy)\b",
    "text_uncertainty": r"\b(?:uncertain|uncertainty|risk|risks|material weakness|going concern)\b",
    "text_positive": r"\b(?:growth|increase|approval|contract|agreement|award|partnership"
    r"|acquisition)\b",
}

FILING_COLUMNS = ["document_id", "permno", "gvkey", "iid", "cik", "ticker", "company_name"]
FILING_COLUMNS += ["filing_date", "form_type", "is_amendment", "items", "word_count"]
# Each name and ticker from the provider, CRSP and Compustat, masked.
NAMES = ["provider_company_name", "content_company_name", "historical_crsp_company_name"]
NAMES += ["compustat_header_company_name"]
TICKERS = ["provider_ticker", "compustat_header_ticker"]

# The excerpt a model reads, masked, this long from the first heading.
EXCERPT = 3000
HEADING = re.compile(r"\bitem\s+\d{1,2}\.\d{2}", re.I)
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATES = re.compile(
    rf"\b{MONTHS}\s+(?:\d{{1,2}}(?!\d)(?:st|nd|rd|th)?,?(?:\s+\d{{4}})?|\d{{4}})"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    re.I,
)
YEARS = re.compile(r"\b(?:19[89]\d|20[0-3]\d)\b")
# First words too common to mask when a company goes by its short name.
COMMON = set(
    "american general united national first international global pacific southern northern "
    "western eastern central great capital financial energy health home bank community royal "
    "standard federal universal advanced applied digital service services systems technologies "
    "resources holdings group trust silver gold premier select summit liberty".split()
)
SUFFIX = re.compile(
    r"[\s,.]+(?:inc|corp|corporation|co|company|ltd|llc|plc|lp|/[a-z]{2}/)\.?$", re.I
)

# What each extra layer is for, in the manifest and the data card.
LAYERS = {
    "daily_market": "CRSP daily prices to 2025: teaches beta, marks the book day by day",
    "ibes_monthly_research_only": "analyst price targets to 2025: teaches revisions",
    "short_interest_monthly_research_only": "short interest to 2025: teaches crowding",
}


# Each date moved to its calendar month's last day.
def month_end(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M").dt.to_timestamp("M")


# Written beside its target and moved whole, so no half file is left.
def write(frame: pd.DataFrame, name: str) -> None:
    path = data.DIR / f"{name}.parquet"
    partial = path.with_suffix(".partial")
    frame.to_parquet(partial, index=False, compression="zstd")
    os.replace(partial, path)
    print(f"  {name}: {len(frame):,} rows", flush=True)


# The organizer panel split: predictors, and next-month return alone.
def organizer(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    listed = pd.read_csv(folder / CHAR_LIST)["variable"].tolist()
    columns = sorted({"permno", "eom", data.TARGET, *listed, *IDENTIFIERS, *LABEL_COLUMNS})
    panel = pq.read_table(folder / CHARS, columns=columns).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    assert not panel.duplicated(data.KEYS).any(), "the panel repeats a stock-month"
    panel["holding_month"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    panel["eligible_price_5"] = panel["prc"].abs().ge(5.0)
    panel["eligible_me_300"] = panel["me"].ge(300.0)
    panel["characteristic_missing_count"] = panel[listed].isna().sum(axis=1).astype("int16")
    keys = [*data.KEYS, "holding_month"]
    labels = panel[[*keys, data.TARGET, *LABEL_COLUMNS]]
    labels = labels.rename(columns={data.TARGET: "next_month_excess_return"})
    features = panel.drop(columns=[data.TARGET, *LABEL_COLUMNS[:-1]])
    return features, labels, listed


# One filing's names, tickers and CIK, each name also without suffix.
def identities(row: dict) -> tuple[list[str], list[str]]:
    names, short = set(), set()
    for raw in [row.get(c) for c in ("company_name", *NAMES)]:
        if isinstance(raw, str) and raw.strip(" ."):
            core = SUFFIX.sub("", raw.strip(" ."))
            names |= {raw.strip(" ."), core}
            first = core.split()[0].strip(",.") if core.split() else ""
            if len(first) >= 5 and first.lower() not in COMMON:
                short |= {first.title(), first.upper()}
    cik = row.get("cik")
    words = {cik.lstrip("0")} if isinstance(cik, str) and cik.strip("0") else set()
    tickers = (row.get(c) for c in ("ticker", *TICKERS))
    words |= {t for t in tickers if isinstance(t, str) and len(t) >= 2}
    words |= short
    return sorted((n for n in names if len(n) >= 4), key=len, reverse=True), sorted(words)


# The excerpt from the first heading, names, tickers, CIK, dates masked.
def excerpt(text: str, row: dict) -> str:
    found = HEADING.search(text)
    body = text[found.start() if found else 0 :][: EXCERPT + 500]
    names, words = identities(row)
    for name in names:
        body = re.sub(re.escape(name), "[COMPANY]", body, flags=re.I)
    for word in words:
        body = re.sub(rf"\b{re.escape(word)}\b", "[ID]", body)
    body = YEARS.sub("[YEAR]", DATES.sub("[DATE]", body))
    return body[:EXCERPT]


# Every 8-K once, no text, with item flags and word counts. One pass.
def filing_table(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts, texts = [], []
    source = pq.ParquetFile(folder / FILINGS)
    columns = [*FILING_COLUMNS, *NAMES, *TICKERS, "text"]
    for batch in source.iter_batches(batch_size=30_000, columns=columns):
        part = batch.to_pandas()
        part["filing_date"] = pd.to_datetime(part["filing_date"])
        part = part[part["filing_date"].between(FIRST_DAY, LAST_MONTH)].copy()
        raw = part.pop("text").fillna("")
        rows = part.to_dict("records")
        texts.append(
            part[["document_id", "permno", "filing_date"]].assign(
                eom=month_end(part["filing_date"]),
                excerpt=[excerpt(t, r) for t, r in zip(raw, rows)],
            )
        )
        text = raw.str.lower()
        for name, pattern in TERMS.items():
            part[name] = text.str.count(pattern).astype("int32")
        parts.append(part.drop(columns=[*NAMES, *TICKERS]))
    table = pd.concat(parts, ignore_index=True)
    table["items"] = table["items"].apply(lambda x: [] if x is None else [str(i) for i in x])
    for name, code in ITEMS.items():
        table[name] = table["items"].apply(lambda x, code=code: code in x).astype("int8")
    return table, pd.concat(texts, ignore_index=True)


# Filings summed into their filing month, known by that month's end.
def monthly_events(table: pd.DataFrame) -> pd.DataFrame:
    table = table.assign(eom=month_end(table["filing_date"]), filing_count=1)
    table["amendment_count"] = table["is_amendment"].fillna(False).astype("int8")
    counts = ["filing_count", "amendment_count", "word_count", *ITEMS, *TERMS]
    events = table.groupby(data.KEYS)[counts].sum().reset_index()
    latest = table.groupby(data.KEYS)["filing_date"].max().reset_index(drop=True)
    events["filing_days_before_eom"] = (events["eom"] - latest).dt.days.astype("int16")
    return events


# No filing counts as zero. Days-before stays empty, 0 means same day.
def join_events(features: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    out = features.merge(events, on=data.KEYS, how="left", validate="one_to_one")
    counts = [c for c in events.columns if c not in {*data.KEYS, "filing_days_before_eom"}]
    out[counts] = out[counts].fillna(0)
    return out


# CRSP daily rows for the panel's names, streamed to spare the memory.
def daily_market(archive: Path, permnos: set) -> None:
    renamed = dict(PERMNO="permno", DlyCalDt="date", DlyPrc="close", DlyRet="total_return")
    renamed |= dict(DlyRetx="price_return", DlyVol="volume", DlyBid="bid", DlyAsk="ask")
    renamed |= dict(DlyCap="market_cap", ShrOut="shares_outstanding", Ticker="ticker")
    renamed |= dict(PrimaryExch="primary_exchange")
    numeric = ["close", "total_return", "price_return", "volume", "bid", "ask", "market_cap"]
    numeric += ["shares_outstanding"]
    path, writer = data.DIR / "daily_market.parquet", None
    partial = path.with_suffix(".partial")
    for name in ("stocks_daily_3.csv", "stocks_daily_4.csv"):
        for chunk in pd.read_csv(archive / name, usecols=list(renamed), chunksize=100_000):
            chunk["DlyCalDt"] = pd.to_datetime(chunk["DlyCalDt"])
            keep = chunk["PERMNO"].isin(permnos)
            keep &= chunk["DlyCalDt"].between(FIRST_DAY, LAST_ARCHIVE_MONTH)
            chunk = chunk[keep].rename(columns=renamed)
            if chunk.empty:
                continue
            chunk[numeric] = chunk[numeric].apply(pd.to_numeric, errors="coerce").astype("float32")
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            writer = writer or pq.ParquetWriter(partial, table.schema, compression="zstd")
            writer.write_table(table)
    writer.close()
    os.replace(partial, path)


# IBES ratings and targets on WRDS's dated CRSP link, not a bare ticker.
def ibes(archive: Path) -> pd.DataFrame:
    link = pd.read_csv(archive / "ibes_crsp_link.csv", dtype={"TICKER": "string"})
    link = link[["TICKER", "PERMNO", "sdate", "edate", "SCORE"]]
    link[["sdate", "edate"]] = link[["sdate", "edate"]].apply(pd.to_datetime)
    link["SCORE"] = pd.to_numeric(link["SCORE"], errors="coerce")
    tables = []
    for name, prefix, fields in (
        (
            "ibes_recommendations.csv",
            "ibes_rec_",
            ["MEANREC", "MEDREC", "STDEV", "NUMREC"]
            + ["NUMUP", "NUMDOWN", "BUYPCT", "SELLPCT", "HOLDPCT"],
        ),
        (
            "ibes_price_targets.csv",
            "ibes_pt_",
            ["NUMEST", "NUMUP4W", "NUMDOWN4W", "NUMUP1M"]
            + ["NUMDOWN1M", "MEANPTG", "MEDPTG", "STDEV", "PTGHIGH", "PTGLOW"],
        ),
    ):
        raw = pd.read_csv(
            archive / name,
            usecols=["TICKER", "STATPERS", "USFIRM", *fields],
            dtype={"TICKER": "string"},
        )
        raw["STATPERS"] = pd.to_datetime(raw["STATPERS"])
        raw = raw[raw["USFIRM"].eq(1) & raw["STATPERS"].between(FIRST_DAY, LAST_ARCHIVE_MONTH)]
        mapped = raw.merge(link, on="TICKER")
        live = mapped["STATPERS"].ge(mapped["sdate"])
        live &= mapped["edate"].isna() | mapped["STATPERS"].le(mapped["edate"])
        # The lowest link score is WRDS's best match, so it breaks ties.
        mapped = mapped[live].sort_values(["PERMNO", "STATPERS", "SCORE"])
        mapped = mapped.drop_duplicates(["PERMNO", "STATPERS"]).assign(
            eom=lambda d: month_end(d["STATPERS"])
        )
        mapped = mapped.sort_values("STATPERS").groupby(["PERMNO", "eom"]).tail(1)
        renamed = {f: f"{prefix}{f.lower()}" for f in fields} | {"PERMNO": "permno"}
        tables.append(mapped[["PERMNO", "eom", *fields]].rename(columns=renamed))
    return tables[0].merge(tables[1], on=data.KEYS, how="outer", validate="one_to_one")


# Short interest on the panel's dated gvkey and issue, new wins a tie.
def short_interest(archive: Path, features: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for name, source in (("short_interest.csv", "new"), ("short_interest_legacy.csv", "legacy")):
        frame = pd.read_csv(
            archive / name,
            dtype={"gvkey": "string", "iid": "string"},
            usecols=["datadate", "gvkey", "iid", "shortint", "shortintadj"],
        )
        frame["datadate"] = pd.to_datetime(frame["datadate"])
        frame = frame[frame["datadate"].between(FIRST_DAY, LAST_ARCHIVE_MONTH)]
        parts.append(frame.assign(eom=month_end(frame["datadate"]), short_source=source))
    short = pd.concat(parts)
    short["gvkey"], short["iid"] = short["gvkey"].str.zfill(6), issue(short["iid"])
    short = short.sort_values(["datadate"]).groupby(["gvkey", "iid", "eom"]).tail(1)
    short = short.assign(new=short["short_source"].eq("new")).sort_values("new")
    short = short.groupby(["gvkey", "iid", "eom"]).tail(1)
    keys = features[["permno", "gvkey", "iid", "eom"]].copy()
    keys["gvkey"], keys["iid"] = keys["gvkey"].astype(str).str.zfill(6), issue(keys["iid"])
    out = keys.merge(
        short[["gvkey", "iid", "eom", "shortint", "shortintadj", "short_source"]],
        on=["gvkey", "iid", "eom"],
        how="left",
        validate="many_to_one",
    )
    renamed = dict(shortint="short_interest", shortintadj="short_interest_adjusted")
    return out.rename(columns=renamed)


# Numeric issue ids from CSV lose their leading zero. Letters stay.
def issue(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return text.where(~text.str.fullmatch(r"\d+"), text.str.zfill(2))


# The short guide that travels with the bundle.
def card(listed: dict) -> str:
    rows = "\n".join(f"| `{name}` | {what} |" for name, what in listed.items())
    return (
        "# FIAM data bundle\n\n"
        "Private, derived from the organizer's files and WRDS. Never commit or submit it.\n"
        "Check it with `uv run -m fiam.data`. Rebuild it with\n"
        "`uv run -m fiam.build_data <folder>`.\n"
        "Keep it at `data/fiam_v1/`, or anywhere with `FIAM_DATA_DIR` pointing at it.\n\n"
        "| file | what it is |\n|---|---|\n" + rows + "\n\n"
        "- `next_month_excess_return` is only in `labels_monthly`. It is the answer, never a "
        "predictor.\n"
        "- 8-K counts in a month use filings dated in that month, known by its last day.\n"
        "- Layers that stop in 2025 teach models and measure the book; none feeds a decision "
        "directly.\n"
    )


# Builds the bundle from organizer files, --archive adds 2025 layers.
def main(args: list[str]) -> None:
    if not args or args[0].startswith("-"):
        raise SystemExit("usage: uv run -m fiam.build_data <organizer folder> [--archive <folder>]")
    folder = Path(args[0]).expanduser()
    archive = Path(args[args.index("--archive") + 1]).expanduser() if "--archive" in args else None
    missing = [n for n in (CHARS, FILINGS, CHAR_LIST) if not (folder / n).exists()]
    if missing:
        raise SystemExit(f"{folder} is missing {missing}")
    data.DIR.mkdir(parents=True, exist_ok=True)
    before = data.manifest() if data.MANIFEST.exists() else {}

    print(f"Building {data.DIR} from {folder}", flush=True)
    features, labels, listed = organizer(folder)
    table, texts = filing_table(folder)
    features = join_events(features, monthly_events(table))
    write(features, "features_monthly")
    write(labels, "labels_monthly")
    write(table, "filings")
    write(texts, "filing_text")

    if archive:
        permnos = set(features["permno"].astype(int))
        daily_market(archive, permnos)
        write(ibes(archive), "ibes_monthly_research_only")
        write(short_interest(archive, features), "short_interest_monthly_research_only")

    present = {"features_monthly": "the 147 characteristics, identifiers and 8-K counts"}
    present |= {"labels_monthly": "next month's excess return, kept apart"}
    present |= {"filings": "one row per 8-K: dates, identifiers, item codes, no text"}
    present |= {"filing_text": "each 8-K from its first item heading, 3,000 characters, masked"}
    present |= {n: w for n, w in LAYERS.items() if (data.DIR / f"{n}.parquet").exists()}
    if data.WRDS.exists():
        present["wrds/"] = "CRSP monthly, S&P 500 index, Compustat dates and dated exits"
    sources = {
        n: dict(sha256=paths.sha256(folder / n), bytes=(folder / n).stat().st_size)
        for n in (CHARS, FILINGS, CHAR_LIST)
    }
    manifest = dict(
        schema_version=2,
        what="Private FIAM data bundle. Never commit or submit it.",
        organizer_characteristics=listed,
        sources=sources,
        # An archive layer from a prior run keeps that run's record.
        archive=str(archive) if archive else before.get("archive"),
        last_archive_month=str(LAST_ARCHIVE_MONTH.date()),
        timing=dict(
            decision="permno, eom: everything in a row is known at that month's end",
            label="next_month_excess_return, labels_monthly only, earned in holding_month",
            filings="counted in the month of filing_date",
        ),
        files=present,
        stock_months=len(features),
    )
    paths.write_json(data.MANIFEST, manifest, rounded=False, end="\n")
    (data.DIR / "DATA_CARD.md").write_text(card(present), encoding="utf-8")
    mismatched = data.checksum_mismatches()
    print(
        "organizer files "
        + (
            f"differ from the published SHA-256: {mismatched}"
            if mismatched
            else "match the published SHA-256"
        )
    )


if __name__ == "__main__":
    main(sys.argv[1:])
