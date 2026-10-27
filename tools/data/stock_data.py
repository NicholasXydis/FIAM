# Read-only extracts from the Stock Data folder; it is never edited.

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pv
import pyarrow.parquet as pq
from _shared import ROOT, check, data_root, fingerprint, receipts, stamp, stock_data
from pandas.tseries.holiday import USFederalHolidayCalendar

OUT = ROOT / "data" / "v4" / "extracts"
# Rows per parquet row group in every extract.
GROUP = 1_000_000
USAGE = "uv run run.py --data stock events | restatements | tables [name ...] | verify"
# Compustat fields describing today's company, not the period: dropped.
COMPUSTAT_TODAY = {
    "costat", "conm", "conml", "tic", "cusip", "exchg", "fic", "loc", "state", "county",
    "city", "add1", "add2", "add3", "add4", "addzip", "busdesc", "ein", "fax", "phone",
    "weburl", "fyrc", "ggroup", "gind", "gsector", "gsubind", "idbflag", "incorp",
    "naics", "sic", "spcindcd", "spcseccd", "spcsrc", "stko", "prican", "prirow", "priusa",
}  # fmt: skip
# CRSP header and end-date fields: today's values or future dates.
CRSP_FUTURE = {
    "HdrCUSIP", "HdrCUSIP9", "SecurityHdrFlg", "SecInfoEndDt", "SecurityEndDt", "ShrEndDt",
    "SecurityActiveFlg", "DelActionType", "DelStatusType", "DelReasonType", "DelPaymentType",
}  # fmt: skip
# Monthly copies of distributions; crsp_distributions has each, dated.
CRSP_DISTRIBUTIONS = {
    "DisExDt", "DisSeqNbr", "DisOrdinaryFlg", "DisType", "DisFreqType", "DisPaymentType",
    "DisDetailType", "DisTaxType", "DisOrigCurType", "DisDivAmt", "DisFacPr", "DisFacShr",
    "DisDeclareDt", "DisRecordDt", "DisPayDt", "DisPERMNO", "DisPERMCO",
}  # fmt: skip
# The eventual actual that I/B/E/S attaches to each forecast row.
IBES_LATER = {"ACTUAL", "ANNDATS_ACT", "ANNTIMS_ACT", "CURR_ACT"}
# TAQ daily measures kept: volume, spreads, impact, depth, retail flow.
TAQ_KEEP = [
    "DATE", "SYM_ROOT", "SYM_SUFFIX", "total_trade", "total_vol", "total_dv_LR", "BuyVol_LR",
    "SellVol_LR", "buy_dv_LR", "sell_dv_LR", "CPrc", "OPrc", "mid_before_close",
    "nbb_before_close", "nbo_before_close", "QuotedSpread_Dollar_tw", "QuotedSpread_Percent_tw",
    "BestOfrDepth_Dollar_tw", "BestBidDepth_Dollar_tw", "EffectiveSpread_Percent_Ave",
    "EffectiveSpread_Percent_DW", "EffectiveSpread_Percent_SW", "PercentRealizedSpread_LR_DW",
    "PercentPriceImpact_LR_DW", "PercentPriceImpact_LR_SW", "ivol_t", "ivol_q", "bs_ratio_vol",
    "BuyVol_Retail", "SellVol_Retail", "buy_dv_Retail", "sell_dv_Retail", "total_trade_retail",
    "total_vol_retail", "total_dv_retail",
]  # fmt: skip
# Each WRDS table: files, drops or keeps, year split, keys, filter.
TABLES = {
    "crsp_daily": {"files": [f"stocks_daily_{i}.csv" for i in range(1, 5)],
                   "drop": CRSP_FUTURE, "by_year": "DlyCalDt", "keys": ["PERMNO", "DlyCalDt"]},
    "crsp_monthly": {"files": ["stocks_monthly.csv"], "drop": CRSP_FUTURE | CRSP_DISTRIBUTIONS,
                     "keys": ["PERMNO", "MthCalDt"], "latest": "SecInfoStartDt"},
    "crsp_delistings": {"files": ["delistings.csv"]},
    "crsp_distributions": {"files": ["distributions.csv"]},
    "crsp_market_daily": {"files": ["market_daily.csv"], "keys": ["dlycaldt"]},
    "crsp_market_monthly": {"files": ["market_monthly.csv"], "keys": ["mthcaldt"]},
    "compustat_quarterly": {"files": ["fundamentals_quarterly.csv"], "drop": COMPUSTAT_TODAY},
    "compustat_annual": {"files": ["fundamentals_annual.csv"], "drop": COMPUSTAT_TODAY},
    "compustat_financials": {"files": ["financials_annual.csv"], "drop": COMPUSTAT_TODAY},
    # Header CUSIPs for the dated pre-2015 link only, never a signal.
    "compustat_ids": {"files": ["fundamentals_quarterly.csv"],
                      "keep": ["gvkey", "cusip", "datadate"]},
    "wrds_ratios": {"files": ["ratios_monthly.csv"]},
    "ibes_actuals": {"files": ["ibes_actuals.csv"]},
    "ibes_summary": {"files": ["ibes_summary.csv"], "drop": IBES_LATER, "rows": ("USFIRM", "1")},
    "ibes_recommendations": {"files": ["ibes_recommendations.csv"]},
    "ibes_price_targets": {"files": ["ibes_price_targets.csv"]},
    "ibes_adjustments": {"files": ["ibes_adjustments.csv"]},
    "ibes_companies": {"files": ["ibes_companies.csv"]},
    "ibes_crsp_link": {"files": ["ibes_crsp_link.csv"]},
    "short_interest": {"files": ["short_interest.csv"], "drop": {"conm", "tic"}},
    "short_interest_legacy": {"files": ["short_interest_legacy.csv"], "drop": {"conm", "tic"}},
    "options_daily": {"files": ["options_stock_daily.csv"], "drop": {"mdate", "wdate"},
                      "by_year": "date"},
    "options_link": {"files": ["options_link.csv"]},
    "taq_daily": {"files": ["intraday_daily.csv"], "keep": TAQ_KEEP, "by_year": "DATE"},
    "taq_link": {"files": ["taq_crsp_daily_link.csv"]},
    "ff_daily": {"files": ["ff_5f_mom_daily.csv"]},
    "ff_monthly": {"files": ["ff_5f_mom_monthly.csv"]},
    "ff_2x3_monthly": {"files": ["ff_2x3_monthly.csv"]},
    "ff_5x5_monthly": {"files": ["ff_5x5_monthly.csv"]},
    "liquidity_monthly": {"files": ["liquidity_monthly.csv"]},
    "vix_daily": {"files": ["volatility_daily.csv"]},
    "riskfree_short": {"files": ["riskfree_short.csv"]},
    "riskfree_medium": {"files": ["riskfree_medium.csv"]},
    "frb_rates_daily": {"files": ["frb_rates_daily.csv"]},
    "frb_fx_daily": {"files": ["frb_fx_daily.csv"]},
}  # fmt: skip
# Identifier, code and date columns, always read as text.
TEXT = re.compile(
    r"(?i)^(permno|permco|gvkey|iid|cusip.*|ncusip|ticker|tic|oftic|sym_.*|symbol|cik|secid|"
    r".*dt|.*date|.*dats.*|.*tims.*|statpers|datadate|rdq|anndats|date|dateff|.*flg|.*flag|"
    r".*type|.*cd|.*code|siccd|naics|.*exch.*|curcd.*|curr.*|measure|fiscalp|usfirm|"
    r"datafmt|indfmt|consol|popsrc|.*source|shareclass|issuer.*|security.*|trading.*|"
    r"kytreasnox|tidxfam|ttermtype|ttermlbl|cname|country|.*nm|yyyymm|fyr.*|fqtr|"
    r"datacqtr|datafqtr|.*_fkey|.*cqtr|.*fqtr|.*_flg|match_lvl|nasd.*|icbindustry)$"
)
# Snapshot fields that describe today, not the event, so they stay out.
EVENTS_DROP = {"companyname", "lastmodifieddate", "lastmodifieddateutc", "mostimportantdateutc"}
# Restatement fields about the event; the rest is today's metadata.
RESTATEMENT_KEEP = [
    "company_fkey", "file_date", "file_accepted", "form_fkey", "ftp_file_name_fkey",
    "http_file_name_html", "http_file_name_text", "file_size", "event_date",
    "restatement_notification_key", "restatement_type_fkey", "restatement_type",
    "currency_code_fkey", "general_type", "quarterly_restated_only", "res_begin_date",
    "res_end_date", "res_accounting", "res_accounting_res_cat_fke_lis",
    "res_accounting_res_cat_tit_lis", "res_fraud", "res_fraud_res_cat_fke_lis",
    "res_fraud_res_cat_tit_lis", "res_clerical_errors", "res_clerical_err_res_cat_fke_lis",
    "res_clerical_err_res_cat_tit_lis", "res_other", "res_other_res_cat_fke_lis",
    "res_other_res_cat_tit_lis", "res_adverse", "res_improves", "res_auditor_letter",
    "res_sec_investigation", "res_board_approval", "res_regulatory_investigation",
    "initial_cum_net_income_usd", "restated_cum_net_income_usd", "change_cum_net_income_usd",
    "initial_cum_tot_sto_equ_usd", "restated_cum_tot_sto_equ_usd", "change_cum_tot_sto_equ_usd",
    "date_of_8k_402", "form_fkey_of_8k_402", "http_file_name_html_of_8k_402",
    "file_date_auditor_name", "res_begin_auditor_name", "res_end_auditor_name",
    "disclosure_text",
]  # fmt: skip


# A file's size, time and SHA-256, to prove exactly what is read.
def describe(path: Path) -> dict:
    stat = path.stat()
    when = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
    return {"path": str(path), "bytes": stat.st_size, "modified": when, "sha256": fingerprint(path)}


# Every gvkey we could ever link: the panel, WRDS ratios and Compustat.
def our_gvkeys() -> set[str]:
    panel = ROOT / "data" / "organisers" / "chars_final_with_names.parquet"
    keys = set(pd.read_parquet(panel, columns=["gvkey"])["gvkey"].dropna().astype(str))
    for name in ("ratios_monthly.csv", "fundamentals_annual.csv", "fundamentals_quarterly.csv"):
        found = pd.read_csv(stock_data() / name, usecols=["gvkey"], dtype=str)["gvkey"]
        keys |= set(found.dropna())
    return {k.split(".")[0].zfill(6) for k in keys}


# Writes one extract as parquet with a receipt of what went in and out.
def write(name: str, table: pd.DataFrame, raw: Path, rows_in: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.parquet"
    part = path.with_suffix(".part")
    table.to_parquet(part, index=False, compression="zstd")
    part.replace(path)
    book = OUT / "receipts.json"
    saved = receipts(book)
    saved[name] = {"source": describe(raw), "rows_in": rows_in, "rows_out": len(table)}
    saved[name] |= {"columns": list(table.columns), "output": describe(path), "made_at": stamp()}
    book.write_text(json.dumps(saved, indent=1))
    print(f"{name}: {rows_in:,} rows read, {len(table):,} kept, {path}", flush=True)


# Capital IQ key developments for our gvkeys, minus snapshot fields.
def events() -> int:
    raw = stock_data() / "events_global.csv"
    keep = [c for c in pd.read_csv(raw, nrows=0).columns if c not in EVENTS_DROP]
    gvkeys, parts, rows_in = our_gvkeys(), [], 0
    for chunk in pd.read_csv(raw, usecols=keep, dtype=str, chunksize=1_000_000):
        rows_in += len(chunk)
        chunk["gvkey"] = chunk["gvkey"].str.split(".").str[0].str.zfill(6)
        parts.append(chunk[chunk["gvkey"].isin(gvkeys)])
        print(f"events: {rows_in:,} rows read", flush=True)
    write("events", pd.concat(parts, ignore_index=True), raw, rows_in)
    return 0


# Restatement events by CIK with their dates, without today's metadata.
def restatements() -> int:
    raw = stock_data() / "restatements.csv"
    table = pd.read_csv(raw, usecols=RESTATEMENT_KEEP, dtype=str)
    write("restatements", table[RESTATEMENT_KEEP], raw, len(table))
    return 0


# Column types: text for codes and dates, numbers where samples parse.
def column_types(path: Path, wanted: list[str], text: set[str]) -> dict:
    sample = pd.read_csv(path, usecols=wanted, dtype=str, nrows=50_000, keep_default_na=False)
    types = {}
    for column in wanted:
        values = sample[column].replace({"": None, "NA": None, ".": None}).dropna()
        numeric = len(values) and pd.to_numeric(values, errors="coerce").notna().all()
        textual = column in text or TEXT.match(column) or not numeric
        types[column] = pa.string() if textual else pa.float64()
    return types


# Streams one table's CSVs into parquet, by year when the table asks.
def convert(name: str, spec: dict, target: Path) -> dict:
    files = [stock_data() / f for f in spec["files"]]
    header = pd.read_csv(files[0], nrows=0).columns.tolist()
    wanted = spec.get("keep") or [c for c in header if c not in spec.get("drop", set())]
    text, rows_in, rows_out = set(), 0, 0
    for attempt in range(40):
        types = column_types(files[0], wanted, text)
        writers, schema = {}, pa.schema([(c, types[c]) for c in wanted])
        options = pv.ConvertOptions(
            include_columns=wanted, column_types=types, strings_can_be_null=True,
            null_values=["", "NA", "."],
        )  # fmt: skip
        try:
            rows_in = rows_out = 0
            for path in files:
                reader = pv.open_csv(
                    path, convert_options=options, read_options=pv.ReadOptions(block_size=1 << 26)
                )
                for batch in reader:
                    rows_in += batch.num_rows
                    table = pa.Table.from_batches([batch]).select(wanted).cast(schema)
                    if "rows" in spec:
                        column, value = spec["rows"]
                        table = table.filter(pc.equal(table[column], value))
                    rows_out += table.num_rows
                    if "by_year" in spec:
                        years = pc.utf8_slice_codeunits(table[spec["by_year"]], 0, 4)
                        for year in pc.unique(years).to_pylist():
                            part = table.filter(pc.equal(years, year))
                            key = str(year)
                            if key not in writers:
                                out = target / name / f"{key}.parquet"
                                out.parent.mkdir(parents=True, exist_ok=True)
                                writers[key] = pq.ParquetWriter(out, schema, compression="zstd")
                            writers[key].write_table(part)
                    else:
                        if "all" not in writers:
                            out = target / f"{name}.parquet"
                            writers["all"] = pq.ParquetWriter(out, schema, compression="zstd")
                        writers["all"].write_table(table)
            for writer in writers.values():
                writer.close()
            break
        except pa.ArrowInvalid as err:
            for writer in writers.values():
                writer.close()
            found = re.search(r"column #(\d+)", str(err))
            if not found:
                raise
            column = header[int(found.group(1))]
            if column in text:
                raise
            text.add(column)
            print(f"{name}: {column} holds text, reading it as text and starting again", flush=True)
    else:
        raise RuntimeError(f"{name}: too many columns changed type")
    return {"rows_in": rows_in, "rows_after_filter": rows_out, "text_after_sampling": sorted(text)}


# Drops exact copies, keeps the description in force, else stops.
def dedupe(path: Path, keys: list[str], latest: str | None = None) -> int:
    table = pd.read_parquet(path)
    left = table[~table.duplicated(keep="first")]
    # The latest description begun by the date, else the first one.
    if latest:
        left = left.sort_values([*keys, latest], kind="stable")
        known = pd.to_datetime(left[latest]) <= pd.to_datetime(left[keys[-1]])
        some = known.groupby([left[k] for k in keys]).transform("any")
        before, after = left[known], left[~some]
        kept = [before[~before.duplicated(keys, keep="last")]]
        kept.append(after[~after.duplicated(keys, keep="first")])
        left = pd.concat(kept).sort_values([*keys, latest], kind="stable")
    if left.duplicated(keys, keep=False).any():
        raise RuntimeError(f"{path.name}: rows share {keys} but differ; not guessed")
    if len(left) < len(table):
        left.to_parquet(path, index=False, compression="zstd")
    return len(table) - len(left)


# Rewrites in set million-row groups, smaller and rebuild-identical.
def compact(path: Path) -> None:
    temp, held = path.with_name(path.name + ".part"), None
    with (
        pq.ParquetFile(path) as source,
        pq.ParquetWriter(temp, source.schema_arrow, compression="zstd") as writer,
    ):
        for batch in source.iter_batches(batch_size=GROUP):
            table = pa.Table.from_batches([batch])
            held = table if held is None else pa.concat_tables([held, table])
            while held.num_rows >= GROUP:
                writer.write_table(held.slice(0, GROUP).combine_chunks())
                held = held.slice(GROUP)
        if held is not None and held.num_rows:
            writer.write_table(held.combine_chunks())
    temp.replace(path)


# Short interest dated when public: 8 trading days after settlement.
def published(path: Path, calendar: list[str]) -> None:
    table = pd.read_parquet(path)
    days = pd.DatetimeIndex(pd.to_datetime(sorted(calendar)))
    settle = pd.to_datetime(table["datadate"])
    at = days.searchsorted(settle, side="right") + 7
    beyond = at >= len(days)
    later = pd.Series(days[at.clip(max=len(days) - 1)], index=table.index)
    holidays = USFederalHolidayCalendar()
    step = pd.offsets.CustomBusinessDay(8, calendar=holidays)
    later[beyond] = settle[beyond] + step
    table["available_date"] = later.dt.strftime("%Y-%m-%d")
    table.to_parquet(path, index=False, compression="zstd")


# The WRDS tables, read-only from Stock Data, each with a full receipt.
def tables(asked: list[str]) -> int:
    names = asked or list(TABLES)
    unknown = [n for n in names if n not in TABLES]
    if unknown:
        print(f"Unknown tables {unknown}; choose from {list(TABLES)}")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    book = OUT / "receipts.json"
    for name in names:
        spec = TABLES[name]
        print(f"{name}: reading {', '.join(spec['files'])}", flush=True)
        made = convert(name, spec, OUT)
        outputs = (
            sorted((OUT / name).glob("*.parquet"))
            if "by_year" in spec
            else [OUT / f"{name}.parquet"]
        )
        if "keys" in spec:
            dropped = sum(dedupe(p, spec["keys"], spec.get("latest")) for p in outputs)
            made["duplicates_dropped"] = dropped
        if name.startswith("short_interest"):
            market = OUT / "crsp_market_daily.parquet"
            if not market.exists():
                tables(["crsp_market_daily"])
            calendar = pd.read_parquet(market, columns=["dlycaldt"])["dlycaldt"].tolist()
            published(outputs[0], calendar)
        for path in outputs:
            compact(path)
        sources = [describe(stock_data() / f) for f in spec["files"]]
        files = {p.relative_to(OUT).as_posix(): fingerprint(p) for p in outputs}
        rows = sum(pq.ParquetFile(p).metadata.num_rows for p in outputs)
        saved = receipts(book)
        saved[name] = {"sources": sources, "outputs": files, "rows_out": rows, "made_at": stamp()}
        saved[name] |= made | {"dropped": sorted(spec.get("drop", set()))}
        book.write_text(json.dumps(saved, indent=1))
        size = sum(p.stat().st_size for p in outputs) / 1e9
        print(f"{name}: {rows:,} rows, {len(outputs)} files, {size:.2f} GB", flush=True)
    return 0


# Every extract against its receipt; prints and counts any mismatch.
def verify() -> int:
    saved = receipts(OUT / "receipts.json")
    expected = {}
    for name, r in saved.items():
        if "outputs" in r:
            expected |= r["outputs"]
        else:
            expected[f"{name}.parquet"] = r["output"]["sha256"]
    wrong = check(OUT, expected)
    print(f"stock extracts: {len(expected)} files, {len(wrong)} differ {wrong[:5]}")
    return 1 if wrong else 0


# One or more verbs per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "v4" / "extracts"
    verbs = {"events": events, "restatements": restatements, "verify": verify}
    if sys.argv[1:2] == ["tables"]:
        sys.exit(tables(sys.argv[2:]))
    asked = sys.argv[1:]
    if not asked or any(v not in verbs for v in asked):
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(max(verbs[v]() for v in asked))
