# SEC 13F holdings on PERMNO, one report per filer and date.

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pc

from fiam.vfinal import links as link_table

# Only holdings reports carry holdings; notices never do.
HOLDINGS_FORMS = {"13F-HR", "13F-HR/A"}
# A filing's median VALUE per share decides its units.
THOUSANDS_BELOW, DOLLARS_ABOVE = 0.5, 2.0
# Under 5 share lines, the SEC's switch date decides the units.
FEW_LINES, SWITCH = 5, pd.Timestamp("2023-01-03")
# The first full report quarter in the SEC's 13F data sets.
FIRST_PERIOD = pd.Timestamp("2013-06-30")
# A filer counts with at least this many distinct matched stocks.
MIN_STOCKS = 20
INFO_COLS = ["ACCESSION_NUMBER", "CUSIP", "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]
INFO_COLS += ["INVESTMENTDISCRETION"]
INFO_TYPES = {"VALUE": pa.float64(), "SSHPRNAMT": pa.float64()}


# One member of a 13F zip, whatever case the quarter's layout uses.
def member(zf: zipfile.ZipFile, name: str) -> str:
    return next(n for n in zf.namelist() if n.upper().endswith(name.upper()))


# One zip's TSV table with every listed column read as text or numbers.
def tsv(zf: zipfile.ZipFile, name: str, cols: list[str], types: dict | None = None):
    kinds = {c: pa.string() for c in cols} | (types or {})
    with zf.open(member(zf, name)) as fh:
        table = pc.read_csv(
            fh,
            parse_options=pc.ParseOptions(delimiter="\t", quote_char=False),
            convert_options=pc.ConvertOptions(include_columns=cols, column_types=kinds),
        )
    return table.to_pandas()


# Adds a count to the build log.
def tally(log: dict, key: str, n) -> None:
    log[key] = log.get(key, 0) + int(n)


# A zip's new reports and their share lines summed per report and CUSIP.
def read_zip(path: Path, seen: set, log: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(path) as zf:
        sub = tsv(zf, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE",
                                         "CIK", "PERIODOFREPORT"])  # fmt: skip
        cover = tsv(zf, "COVERPAGE.tsv", ["ACCESSION_NUMBER", "ISAMENDMENT", "AMENDMENTTYPE",
                                          "REPORTTYPE"])  # fmt: skip
        info = tsv(zf, "INFOTABLE.tsv", INFO_COLS, INFO_TYPES)
    reports = sub.merge(cover, on="ACCESSION_NUMBER", how="left")
    # A filing in two zips is read from the first only, never twice.
    again = reports["ACCESSION_NUMBER"].isin(seen)
    tally(log, "filings_already_read_elsewhere", again.sum())
    reports = reports[~again].drop_duplicates("ACCESSION_NUMBER")
    seen.update(reports["ACCESSION_NUMBER"])
    tally(log, "submissions", len(reports))
    held = reports["SUBMISSIONTYPE"].isin(HOLDINGS_FORMS)
    tally(log, "notices_and_other_forms_left_out", (~held).sum())
    reports = reports[held]
    info = info[info["ACCESSION_NUMBER"].isin(set(reports["ACCESSION_NUMBER"]))]
    tally(log, "lines", len(info))
    # Options and principal amounts out first.
    option = info["PUTCALL"].fillna("").str.strip().str.lower().isin({"put", "call"})
    prn = info["SSHPRNAMTTYPE"].fillna("").str.strip().str.upper() == "PRN"
    tally(log, "option_lines_dropped", option.sum())
    tally(log, "principal_lines_dropped", (prn & ~option).sum())
    info = info[~option & ~prn].copy()
    info["CUSIP"] = info["CUSIP"].fillna("").str.strip().str.upper()
    per_share = info["VALUE"] / info["SSHPRNAMT"].where(info["SSHPRNAMT"] > 0)
    units = per_share.groupby(info["ACCESSION_NUMBER"]).agg(["median", "count"])
    reports = reports.merge(
        units.rename(columns={"median": "value_per_share", "count": "share_lines"}),
        left_on="ACCESSION_NUMBER", right_index=True, how="left",
    )  # fmt: skip
    # Sole-discretion shares, for construction: shared lines double count.
    sole = info["INVESTMENTDISCRETION"].fillna("").str.strip().str.upper() == "SOLE"
    info["SOLE"] = info["SSHPRNAMT"].where(sole, 0.0)
    lines = info.groupby(["ACCESSION_NUMBER", "CUSIP"], as_index=False)[
        ["VALUE", "SSHPRNAMT", "SOLE"]
    ]
    return reports, lines.sum(min_count=1)


# Thousands, dollars or unclear per filing, by its own lines.
def unit_class(reports: pd.DataFrame) -> pd.Series:
    v, n = reports["value_per_share"], reports["share_lines"].fillna(0)
    out = pd.Series("unclear", index=reports.index)
    out[v < THOUSANDS_BELOW] = "thousands"
    out[v > DOLLARS_ABOVE] = "dollars"
    few = n < FEW_LINES
    out[few] = np.where(reports.loc[few, "filing_date"] < SWITCH, "thousands", "dollars")
    return out


# Zips in filing order: the old quarters, then the new 3-month windows.
def zip_order(path: Path) -> pd.Timestamp:
    stem = path.name.split("_form13f")[0]
    if "q" in stem and "-" not in stem:
        return pd.Period(stem.replace("q", "Q"), freq="Q").start_time
    return pd.to_datetime(stem.split("-")[0], format="%d%b%Y")


# Every 13F holdings report and its matched US common-stock lines.
def build(data: Path, log: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    reports, lines, seen = [], [], set()
    for path in sorted((data / "edgar" / "13f").glob("*_form13f.zip"), key=zip_order):
        r, li = read_zip(path, seen, log)
        reports.append(r)
        lines.append(li)
    r = pd.concat(reports, ignore_index=True).drop_duplicates("ACCESSION_NUMBER")
    r = r.rename(columns=str.lower).rename(
        columns={"accession_number": "accession", "cik": "filer_cik", "periodofreport": "period",
                 "submissiontype": "form"}
    )  # fmt: skip
    for col in ("filing_date", "period"):
        r[col] = pd.to_datetime(r[col], format="%d-%b-%Y", errors="coerce").astype("datetime64[ns]")
    r["filer_cik"] = pd.to_numeric(r["filer_cik"], errors="coerce").astype("Int64")
    r["units"] = unit_class(r)
    log["reports_by_units"] = r["units"].value_counts().to_dict()
    # Unit classes by filing quarter, as the gate rules ask (counts).
    by_q = r.groupby([r["filing_date"].dt.to_period("Q").astype(str), "units"]).size()
    log["units_by_filing_quarter"] = {q: g.droplevel(0).to_dict() for q, g in by_q.groupby(level=0)}
    log["reports_before_first_period"] = int((r["period"] < FIRST_PERIOD).sum())
    li = pd.concat(lines, ignore_index=True).rename(
        columns={"ACCESSION_NUMBER": "accession", "CUSIP": "cusip", "VALUE": "value",
                 "SSHPRNAMT": "shares", "SOLE": "shares_sole"}
    )  # fmt: skip
    cols = ["value", "shares", "shares_sole"]
    li = li.groupby(["accession", "cusip"], as_index=False)[cols].sum(min_count=1)
    li = li.merge(r[["accession", "period", "units"]], on="accession")
    scale = li["units"].map({"thousands": 1000.0, "dollars": 1.0})
    li["value_usd"] = li["value"] * scale
    holdings = match(li, data, log)
    log["universe_match_by_period"] = universe_match(r, holdings, data)
    return r, holdings


# Share of $600m+ panel stocks with a matched holder, periods to 2020.
def universe_match(r: pd.DataFrame, holdings: pd.DataFrame, data: Path) -> dict:
    p = pd.read_parquet(
        data / "v4" / "clean" / "panel.parquet",
        columns=["permno", "eom", "me"],
        filters=[("eom", "<=", pd.Timestamp("2020-12-31"))],
    )
    big = p[p["me"] >= 600][["permno", "eom"]]
    held = holdings[["accession", "permno"]].merge(r[["accession", "period"]], on="accession")
    held = set(zip(held["permno"], held["period"]))
    big = big[big["eom"].isin(set(r["period"].dropna()))]
    hit = [(a, b) in held for a, b in zip(big["permno"], big["eom"])]
    rate = pd.Series(hit, index=big.index).groupby(big["eom"].dt.to_period("Q").astype(str))
    return rate.mean().round(4).to_dict()


# CUSIP to PERMNO by the CRSP CUSIP in force at the report's period.
def match(li: pd.DataFrame, data: Path, log: dict) -> pd.DataFrame:
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    pairs = li[["cusip", "period"]].drop_duplicates().reset_index(drop=True)
    pairs["permno"] = link_table.permno_at(lk, "cusip", pairs["cusip"], pairs["period"]).to_numpy()
    li = li.merge(pairs, on=["cusip", "period"], how="left")
    log["lines_matched_share"] = round(float(li["permno"].notna().mean()), 4)
    matched = li.loc[li["permno"].notna(), "value_usd"].sum()
    log["value_matched_share"] = round(float(matched / li["value_usd"].sum()), 4)
    li = li.dropna(subset=["permno"]).astype({"permno": "int64"})
    # US common stock only: CRSP's last row on or before the period.
    m = pd.read_parquet(
        data / "v4" / "clean" / "crsp_monthly.parquet", columns=["permno", "date", "sharetype",
                                                                  "securitytype"]
    )  # fmt: skip
    m = m.sort_values("date")
    li = pd.merge_asof(
        li.sort_values("period"), m, left_on="period", right_on="date", by="permno",
        direction="backward",
    )  # fmt: skip
    common = (li["sharetype"] == "NS") & (li["securitytype"] == "EQTY")
    log["matched_lines_not_common_dropped"] = int((~common).sum())
    li = li[common]
    # Lines summed per PERMNO within the report.
    cols = ["value_usd", "shares", "shares_sole"]
    out = li.groupby(["accession", "permno"], as_index=False)[cols].sum(min_count=1)
    log["holdings_rows"] = len(out)
    return out
