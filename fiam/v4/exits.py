# Dated exits: CRSP delistings to 2025, SEC-dated exits in 2026 (§6.4).

from pathlib import Path

import pandas as pd

from fiam.v4 import clock
from fiam.v4 import links as link_table

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
# CRSP's delisting actions, read from their payments and returns.
GROUPS = {
    "MER": ("merger", "merger_or_exchange"),
    "GEX": ("exchange", "merger_or_exchange"),
    "GLI": ("liquidation", "failure"),
    "GDR": ("dropped", "failure"),
}
# SEC forms that end a listing, searched 30 sessions either side (§6.4).
EXIT_FORMS = {"25", "25-NSE", "15-12B", "15-12G", "15-15D"}
WINDOW = 30
CRSP_END = pd.Timestamp("2025-12-31")


# CRSP's delistings with their action, group, return and known date.
def crsp_exits(data: Path) -> pd.DataFrame:
    d = pd.read_parquet(data / "v4" / "extracts" / "crsp_delistings.parquet")
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    d["exit_date"] = pd.to_datetime(d["delistingdt"]).astype("datetime64[ns]")
    d["known"] = pd.to_datetime(d["delnextdt"], errors="coerce").fillna(d["exit_date"])
    d["category"] = d["delactiontype"].map(lambda a: GROUPS.get(a, ("unknown", "unknown"))[0])
    d["group"] = d["delactiontype"].map(lambda a: GROUPS.get(a, ("unknown", "unknown"))[1])
    keep = ["permno", "exit_date", "category", "group", "delret", "known", "delactiontype"]
    return d[keep].assign(source="crsp_delistings", evidence="")


# Stocks whose daily rows stop in 2026, or on CRSP's last day with no
# CRSP exit (approved 2026-10-23, 2B), before the file's end.
def stoppers(data: Path, crsp_done: frozenset = frozenset()) -> pd.Series:
    d = pd.read_parquet(data / "v4" / "clean" / "dsf.parquet", columns=["permno", "date"])
    last = d.groupby("permno")["date"].max()
    late = (last > CRSP_END) & (last < d["date"].max())
    at_end = (last == CRSP_END) & ~last.index.isin(list(crsp_done))
    return last[late | at_end]


# 2026 exits from SEC forms near the last row; none found is a data gap.
def sec_exits(data: Path, last: pd.Series) -> pd.DataFrame:
    cal = clock.calendar(clock.xnys_sessions("2025-06-01", "2026-12-31"))
    cols = ["permno", "form", "items", "filing_date", "accession", "available_at"]
    f = pd.read_parquet(data / "v4" / "clean" / "edgar_filings.parquet", columns=cols)
    f = f[f["permno"].isin(last.index)]
    items = f["items"].fillna("").str.split(",")
    two01 = (f["form"] == "8-K") & items.map(lambda s: "2.01" in s)
    one03 = (f["form"] == "8-K") & items.map(lambda s: "1.03" in s)
    f = f[f["form"].isin(EXIT_FORMS) | two01 | one03].assign(merger=two01, bankrupt=one03)
    lo = clock.shift_sessions(last, -WINDOW, cal)
    hi = clock.shift_sessions(last, WINDOW, cal)
    span = pd.DataFrame({"permno": last.index.to_numpy(), "last": last.to_numpy()})
    span["lo"], span["hi"] = lo.to_numpy(), hi.to_numpy()
    near = f.merge(span, on="permno")
    near = near[(near["filing_date"] >= near["lo"]) & (near["filing_date"] <= near["hi"])]
    rows = []
    for permno, day in last.items():
        hits = near[near["permno"] == permno]
        if hits.empty:
            category, group, known, evidence = "data_gap", "data_gap", pd.NaT, ""
        else:
            # A bankruptcy (item 1.03) is a failure even with an asset sale (M5).
            broke, merged = bool(hits["bankrupt"].any()), bool(hits["merger"].any())
            category = "bankruptcy" if broke else "merger" if merged else "delisted"
            group = "merger_or_exchange" if merged and not broke else "failure"
            known = pd.to_datetime(hits["available_at"], utc=True).max().tz_localize(None)
            evidence = ";".join(sorted(hits["form"] + " " + hits["accession"]))
        rows.append((permno, day, category, group, known, evidence))
    cols = ["permno", "exit_date", "category", "group", "known", "evidence"]
    out = pd.DataFrame(rows, columns=cols)
    return out.assign(delret=float("nan"), delactiontype="", source="sec_forms_2026")


# Compustat's deletion date and reason, a cross-check only (B11).
def compustat_deletions(data: Path) -> pd.DataFrame:
    path = data / "v4" / "extracts" / "compustat_annual.parquet"
    a = pd.read_parquet(path, columns=["gvkey", "datadate", "dldte", "dlrsn"])
    a = a.dropna(subset=["dldte"]).sort_values("datadate").drop_duplicates("gvkey", keep="last")
    a["dldte"] = pd.to_datetime(a["dldte"]).astype("datetime64[ns]")
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    owner = link_table.permno_at(lk, "gvkey", a["gvkey"], a["dldte"] - pd.Timedelta(days=1))
    a["permno"] = owner.to_numpy()
    a = a.dropna(subset=["permno"]).astype({"permno": "int64"})
    out = a.rename(columns={"dldte": "compustat_dldte", "dlrsn": "compustat_dlrsn"})
    return out[["permno", "compustat_dldte", "compustat_dlrsn"]].drop_duplicates("permno")


# The exits table: CRSP to 2025, SEC in 2026, Compustat beside.
def build(data: Path = DATA) -> tuple[pd.DataFrame, dict]:
    crsp = crsp_exits(data)
    last = stoppers(data, frozenset(crsp["permno"]))
    sec = sec_exits(data, last)
    table = pd.concat([crsp, sec], ignore_index=True)
    table = table.merge(compustat_deletions(data), on="permno", how="left")
    # Compustat's date only when it falls near this exit (L8).
    far = (table["compustat_dldte"] - table["exit_date"]).dt.days.abs() > 90
    table.loc[far, ["compustat_dldte", "compustat_dlrsn"]] = None
    table["known"] = pd.to_datetime(table["known"]).astype("datetime64[ns]")
    report = {
        "crsp_exits": len(crsp),
        "crsp_by_category": crsp["category"].value_counts().to_dict(),
        "stocks_stopping_in_2026": len(last),
        "sec_2026_by_category": sec["category"].value_counts().to_dict(),
        "compustat_deletion_dates_matched": int(table["compustat_dldte"].notna().sum()),
    }
    return table, report
