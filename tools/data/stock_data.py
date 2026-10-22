# Read-only extracts from the Stock Data folder; it is never edited.

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from _shared import ROOT, check, data_root, fingerprint, receipts, stamp, stock_data

OUT = ROOT / "data" / "v4" / "extracts"
USAGE = "uv run run.py --data stock events | restatements | verify"
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


# A file's size, time and SHA-256, to prove exactly what was read.
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


# Every extract against its receipt; prints and counts any mismatch.
def verify() -> int:
    saved = receipts(OUT / "receipts.json")
    expected = {f"{name}.parquet": r["output"]["sha256"] for name, r in saved.items()}
    wrong = check(OUT, expected)
    print(f"stock extracts: {len(expected)} files, {len(wrong)} wrong {wrong[:5]}")
    return 1 if wrong else 0


# One or more verbs per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "v4" / "extracts"
    verbs = {"events": events, "restatements": restatements, "verify": verify}
    asked = sys.argv[1:]
    if not asked or any(v not in verbs for v in asked):
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(max(verbs[v]() for v in asked))
