# Converts WRDS exports and dated exits into wrds/, never committed.

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.csv as pv
import pyarrow.parquet as pq

from fiam import data, paths

OUT = data.WRDS

# Real delisting actions. Others carry the data's end, not an exit date.
DELISTED = {"MER", "GDR", "GLI", "GEX"}

# Each export is known by a column only it has. Only used columns kept.
TABLES = {
    "crsp_monthly": (
        "MthRet",
        [
            "PERMNO",
            "YYYYMM",
            "MthCalDt",
            "MthRet",
            "MthDelFlg",
            "SecurityEndDt",
            "DelActionType",
            "DelReasonType",
            "DelPaymentType",
            "Ticker",
            "IssuerNm",
            "SecInfoStartDt",
            "SecInfoEndDt",
            "sprtrn",
        ],
    ),
    "sp500_index": ("MthTotRet", ["YYYYMM", "MthCalDt", "MthTotRet", "MthPrcRet", "IndNm"]),
    "compustat_quarterly": (
        "rdq",
        ["gvkey", "datadate", "rdq", "fyearq", "fqtr", "tic", "conm", "cik", "dldte", "dlrsn"],
    ),
}


# Which table an export is, from its header line alone.
def kind(path: Path) -> str:
    header = path.open(encoding="utf-8", errors="replace").readline().strip().split(",")
    matches = [name for name, (marker, _) in TABLES.items() if marker in header]
    if len(matches) != 1:
        raise ValueError(f"{path.name} is not a CRSP monthly, S&P index or Compustat export")
    return matches[0]


# Exits by PERMNO: CRSP delists to 2025, then Compustat, final returns.
def exits() -> pd.DataFrame:
    crsp = pd.read_parquet(OUT / "crsp_monthly.parquet")
    crsp["SecurityEndDt"] = pd.to_datetime(crsp["SecurityEndDt"])
    real = crsp[crsp["DelActionType"].isin(DELISTED)]
    events = real.groupby("PERMNO").agg(
        exit_date=("SecurityEndDt", "max"),
        action=("DelActionType", "last"),
        payment=("DelPaymentType", "last"),
    )
    # A delisted stock's last CRSP MthRet includes its delisting payment.
    final = crsp.sort_values("YYYYMM").groupby("PERMNO").tail(1).set_index("PERMNO")
    events = events.join(final[["YYYYMM", "MthRet"]].rename(columns={"MthRet": "final_return"}))
    events["final_month"] = pd.to_datetime(events.pop("YYYYMM").astype(str), format="%Y%m")
    events["source"] = "CRSP delisting " + events["action"] + " " + events["payment"].fillna("")

    # 2026 has no CRSP: Compustat dates the exit, the payout stays unknown.
    comp = pd.read_parquet(OUT / "compustat_quarterly.parquet").dropna(subset=["dldte", "dlrsn"])
    comp["dldte"] = pd.to_datetime(comp["dldte"])
    deleted = comp.groupby("gvkey").agg(exit_date=("dldte", "max"), reason=("dlrsn", "last"))
    deleted = deleted[deleted["exit_date"] >= "2026-01-01"]
    panel = data.features(["gvkey"])
    panel = panel[panel["eom"] >= "2026-01-01"].dropna(subset=["gvkey"])
    panel["gvkey"] = panel["gvkey"].astype("int64").astype(str).str.zfill(6)
    late = panel.drop_duplicates("permno").join(deleted, on="gvkey", how="inner")
    late = late.set_index("permno")[["exit_date", "reason"]]
    late["source"] = "Compustat deletion reason " + late.pop("reason")
    late = late.drop(index=events.index, errors="ignore")

    table = pd.concat([events, late]).rename_axis("permno")
    return table[["exit_date", "final_month", "final_return", "source"]]


# Converts each WRDS export found into the bundle's wrds/ folder.
def main(exports: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = OUT / "sources.json"
    record = json.loads(sources.read_text(encoding="utf-8")) if sources.exists() else {}
    for path in map(Path, exports):
        name = kind(path)
        columns = TABLES[name][1]
        # Codes and identifiers stay text so a gvkey or CUSIP keeps its zeros.
        text = {c: "string" for c in columns if c in {"gvkey", "cik", "tic", "Ticker", "dlrsn"}}
        table = pv.read_csv(
            path, convert_options=pv.ConvertOptions(include_columns=columns, column_types=text)
        )
        pq.write_table(table, OUT / f"{name}.parquet")
        record[name] = dict(
            source=path.name,
            bytes=path.stat().st_size,
            sha256=paths.sha256(path),
            rows=table.num_rows,
            converted_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        print(f"  {name}: {table.num_rows:,} rows from {path.name}")
    paths.write_json(sources, record, rounded=False)
    table = exits()
    table.to_parquet(OUT / "exits.parquet")
    print(f"  exits: {len(table):,} securities with a dated delisting or deletion")


if __name__ == "__main__":
    main(sys.argv[1:])
