# Dated exits: CRSP delistings to 2025, SEC-dated exits in 2026.

from pathlib import Path

import pandas as pd

from fiam.vfinal import clock
from fiam.vfinal import links as link_table

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
# CRSP's delisting actions, read from their payments and returns.
GROUPS = {
    "MER": ("merger", "merger_or_exchange"),
    "GEX": ("exchange", "merger_or_exchange"),
    "GLI": ("liquidation", "failure"),
    "GDR": ("dropped", "failure"),
}
# SEC forms that end a listing, searched 30 sessions either side.
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


# Stocks whose rows stop in 2026 or end 2025 with no CRSP exit.
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
    # A bankruptcy filed in the year before the stop still names it.
    year = near["filing_date"] >= near["last"] - pd.Timedelta(days=365)
    broke_any = set(
        near.loc[near["bankrupt"] & year & (near["filing_date"] <= near["hi"]), "permno"]
    )
    near = near[(near["filing_date"] >= near["lo"]) & (near["filing_date"] <= near["hi"])]
    rows = []
    for permno, day in last.items():
        hits = near[near["permno"] == permno]
        if hits.empty:
            category, group, known, evidence = "data_gap", "data_gap", pd.NaT, ""
        else:
            # A bankruptcy (item 1.03) is a failure even with an asset sale.
            broke = bool(hits["bankrupt"].any()) or permno in broke_any
            merged = bool(hits["merger"].any())
            category = "bankruptcy" if broke else "merger" if merged else "delisted"
            group = "merger_or_exchange" if merged and not broke else "failure"
            # Known from the first form on or after the last row.
            stamps = pd.to_datetime(hits["available_at"], utc=True).dt.tz_localize(None)
            later = stamps[(hits["filing_date"] >= day).to_numpy()]
            known = later.min() if len(later) else stamps.max()
            evidence = ";".join(sorted(hits["form"] + " " + hits["accession"]))
        rows.append((permno, day, category, group, known, evidence))
    cols = ["permno", "exit_date", "category", "group", "known", "evidence"]
    out = pd.DataFrame(rows, columns=cols)
    return out.assign(delret=float("nan"), delactiontype="", source="sec_forms_2026")


# Compustat's deletion date and reason, a cross-check only.
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
    # Compustat's date only when it falls near this exit.
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


# A rebuilt table against a prior build: rows, categories, dates.
def diff(old: Path, new: Path = DATA / "v4" / "clean" / "exits.parquet") -> dict:
    cols = ["permno", "exit_date", "category", "delret", "known", "source"]
    a, b = pd.read_parquet(old, columns=cols), pd.read_parquet(new, columns=cols)
    # A 2021+ delisting return is a return: it is never compared.
    for frame in (a, b):
        frame.loc[frame["exit_date"] > clock.LAST_LABEL_DAY, "delret"] = float("nan")
    both = a.merge(
        b, on=["permno", "source"], how="outer", suffixes=("_old", "_new"), indicator=True
    )
    kept = both[both["_merge"] == "both"]
    # Returns to 2020 are compared; 2021+ rows by key, date and category.
    ret_changed = ~(
        (kept["delret_old"] == kept["delret_new"])
        | (kept["delret_old"].isna() & kept["delret_new"].isna())
    )
    late = kept["exit_date_new"] > clock.LAST_LABEL_DAY
    moved = kept[
        (kept["category_old"] != kept["category_new"])
        | (kept["exit_date_old"] != kept["exit_date_new"])
        | (kept["known_old"].fillna(pd.Timestamp(0)) != kept["known_new"].fillna(pd.Timestamp(0)))
    ]
    show = ["permno", "source", "exit_date_old", "exit_date_new", "category_old", "category_new"]
    show += ["known_old", "known_new"]
    import hashlib

    # Which builds were compared: the kit's and ours, by SHA-256 only.
    sha = {
        side: dict(file=Path(f).name, sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest())
        for side, f in (("old", old), ("new", new))
    }
    return {
        "compared": sha,
        "old_rows": len(a),
        "new_rows": len(b),
        "old_by_source_category": a.groupby(["source", "category"]).size().astype(int).to_dict(),
        "new_by_source_category": b.groupby(["source", "category"]).size().astype(int).to_dict(),
        "only_old": both.loc[both["_merge"] == "left_only", ["permno", "source"]].to_dict(
            "records"
        ),
        "only_new": both.loc[both["_merge"] == "right_only", ["permno", "source"]].to_dict(
            "records"
        ),
        "delret_changed_to_2020": int((ret_changed & ~late).sum()),
        "changed_rows": moved[show].astype(str).to_dict("records"),
    }


if __name__ == "__main__":
    import json
    import sys

    if sys.argv[1:2] == ["diff"]:
        out = diff(Path(sys.argv[2]))
        out = {str(k): v for k, v in out.items()}
        for key in ("old_by_source_category", "new_by_source_category"):
            out[key] = {" ".join(k): v for k, v in out[key].items()}
        target = ROOT / "out" / "audit" / "engine" / "inputs" / "exits_diff.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in out.items() if k != "changed_rows"}, indent=1))
        print(len(out["changed_rows"]), "changed rows")
