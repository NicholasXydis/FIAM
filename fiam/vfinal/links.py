# The dated PERMNO link table: each id and its period.

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
COLUMNS = ["permno", "kind", "value", "valid_from", "valid_to", "source", "score"]
# Gvkeys come from the panel from 2015; before it from WRDS ratios.
PANEL_START = pd.Timestamp("2015-01-01")
# I/B/E/S links are kept at score 2 or better.
IBES_SCORE = 2
DAY = pd.Timedelta(days=1)


# The input files, under one data root so a rebuild can point elsewhere.
def paths(data: Path = DATA) -> dict[str, Path]:
    extracts = data / "v4" / "extracts"
    return {
        "crsp": extracts / "crsp_monthly.parquet",
        "ratios": extracts / "wrds_ratios.parquet",
        "ibes": extracts / "ibes_crsp_link.parquet",
        "options": extracts / "options_link.parquet",
        "taq": extracts / "taq_link.parquet",
        "panel": data / "organisers" / "chars_final_with_names.parquet",
        "ids": extracts / "compustat_ids.parquet",
        "eightk": data / "organisers" / "8k_20150101_20260831_identified.parquet",
        "cik_map": data / "edgar" / "cik_map.parquet",
        "filings": data / "edgar" / "filings.parquet",
        "forms": data / "edgar" / "forms.parquet",
        "decisions": data / "v4" / "cik_decisions.json",
        "candidates": data / "edgar" / "cik_candidates.parquet",
        "cik_names": data / "edgar" / "cik_names.parquet",
        "cik_first": data / "edgar" / "cik_first_filing.parquet",
        "carc": data / "carbon_arc" / "catalogue" / "entities" / "companies.json",
        "carc_manifest": data / "carbon_arc" / "catalogue" / "entities" / "manifest.json",
    }


# Consecutive equal values per stock collapsed into dated periods.
def runs(frame: pd.DataFrame, kind: str, source: str, end: pd.Timestamp | None) -> pd.DataFrame:
    rows = frame.dropna(subset=["value"]).sort_values(["permno", "date"], kind="stable")
    if rows.empty:
        return pd.DataFrame(columns=COLUMNS)
    value = rows["value"].astype(str)
    fresh = (rows["permno"] != rows["permno"].shift()) | (value != value.shift())
    rows = rows.assign(value=value, run=fresh.cumsum())
    got = rows.groupby("run").agg(
        permno=("permno", "first"),
        value=("value", "first"),
        valid_from=("start", "min"),
        last=("date", "max"),
    )
    following = got.groupby("permno")["valid_from"].shift(-1)
    closed = got["last"] if end is None else got["last"].where(got["last"] < end)
    got["valid_to"] = (following - DAY).fillna(closed)
    return got.assign(kind=kind, source=source, score=pd.NA)[COLUMNS]


# CUSIP, ticker, symbol, share class, PERMCO and name by date, CRSP.
def crsp(path: Path) -> pd.DataFrame:
    keep = ["PERMNO", "MthCalDt", "SecInfoStartDt", "CUSIP9", "Ticker", "TradingSymbol"]
    m = pd.read_parquet(path, columns=keep + ["ShareClass", "PERMCO", "IssuerNm"])
    m["permno"] = pd.to_numeric(m["PERMNO"]).astype("int64")
    m["date"] = pd.to_datetime(m["MthCalDt"])
    start = pd.to_datetime(m["SecInfoStartDt"], errors="coerce")
    m["start"] = start.where(start <= m["date"], m["date"]).fillna(m["date"])
    end = m["date"].max()
    pairs = [("CUSIP9", "cusip"), ("Ticker", "ticker"), ("TradingSymbol", "symbol")]
    pairs += [("ShareClass", "share_class"), ("PERMCO", "permco"), ("IssuerNm", "name")]
    return pd.concat([runs(m.assign(value=m[c]), k, "crsp_monthly", end) for c, k in pairs])


# Gvkey and iid by month from the organisers' panel, 2015 on.
def panel(path: Path) -> pd.DataFrame:
    p = pd.read_parquet(path, columns=["permno", "gvkey", "iid", "eom"])
    p["permno"] = pd.to_numeric(p["permno"]).astype("int64")
    p["date"] = pd.to_datetime(p["eom"])
    p["start"] = p["date"].dt.to_period("M").dt.start_time
    end = p["date"].max()
    gvkey = runs(p.assign(value=p["gvkey"]), "gvkey", "panel", end)
    iid = runs(p.assign(value=p["iid"]), "iid", "panel", end)
    both = p["gvkey"].astype(str) + ":" + p["iid"].astype(str)
    pair = runs(p.assign(value=both), "gvkey_iid", "panel", end)
    return pd.concat([gvkey, iid, pair])


# Common stocks per CRSP company and month, to tell one-security firms.
def common_per_company(crsp_path: Path) -> pd.Series:
    cols = ["PERMNO", "PERMCO", "MthCalDt", "ShareType", "SecurityType"]
    m = pd.read_parquet(crsp_path, columns=cols)
    m = m[(m["ShareType"] == "NS") & (m["SecurityType"] == "EQTY")]
    month = pd.to_datetime(m["MthCalDt"]).dt.to_period("M")
    counts = m.groupby([m["PERMCO"], month])["PERMNO"].transform("nunique")
    key = pd.MultiIndex.from_arrays([pd.to_numeric(m["PERMNO"]).astype("int64"), month])
    return pd.Series(counts.to_numpy(), index=key).groupby(level=[0, 1]).max()


# Compustat's header CUSIP and each gvkey's first and last data dates.
def compustat_ids(path: Path) -> pd.DataFrame:
    q = pd.read_parquet(path)
    q["datadate"] = pd.to_datetime(q["datadate"])
    life = q.groupby("gvkey")["datadate"].agg(born="min", died="max")
    head = q.dropna(subset=["cusip"]).sort_values("datadate").drop_duplicates("gvkey", keep="last")
    return life.join(head.set_index("gvkey")["cusip"].str[:8].rename("cusip8"))


# WRDS ratios' gvkey per stock and month; two on a date resolved.
def ratio_months(path: Path, first: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    r = pd.read_parquet(path, columns=["gvkey", "permno", "public_date"]).dropna()
    r["date"] = pd.to_datetime(r["public_date"])
    r = r[r["date"] < PANEL_START].copy()
    r["permno"] = pd.to_numeric(r["permno"]).astype("int64")
    r["panel_match"] = r["gvkey"].eq(r["permno"].map(first["gvkey"]))
    r["usual"] = r.groupby(["permno", "gvkey"])["date"].transform("size")
    r = r.sort_values(["permno", "date", "panel_match", "usual", "gvkey"])
    picked = r.drop_duplicates(["permno", "date"], keep="last")
    picked = picked.assign(month=picked["date"].dt.to_period("M"))
    return picked.drop_duplicates(["permno", "month"], keep="last"), len(r) - len(picked)


# Pre-2015 gvkey and iid by month, four routes in order.
def ratios(
    path: Path, panel_path: Path, crsp_path: Path, ids_path: Path | None = None
) -> tuple[pd.DataFrame, dict]:
    first = first_panel_pairs(panel_path)
    picked, resolved = ratio_months(path, first)
    report = {"pre_2015_two_gvkey_dates_resolved": resolved}
    cols = ["PERMNO", "MthCalDt", "CUSIP9", "PERMCO", "ShareType", "SecurityType"]
    g = pd.read_parquet(crsp_path, columns=cols)
    g["date"] = pd.to_datetime(g["MthCalDt"])
    g = g[g["date"] < PANEL_START].copy()
    g["permno"] = pd.to_numeric(g["PERMNO"]).astype("int64")
    g["month"] = g["date"].dt.to_period("M")
    g = g.sort_values(["permno", "date"]).drop_duplicates(["permno", "month"], keep="last")
    g = g.merge(picked[["permno", "month", "gvkey"]], on=["permno", "month"], how="left")
    g["source"] = np.where(g["gvkey"].notna(), "wrds_ratios", None)
    if ids_path is not None:
        ids = compustat_ids(ids_path)
        born, died = ids["born"], ids["died"] + pd.offsets.MonthEnd(3)
        alive = lambda gv: (g["date"] >= gv.map(born)) & (g["date"] <= gv.map(died))  # noqa: E731
        carry = g["permno"].map(first["gvkey"])
        by_cusip = ids.dropna(subset=["cusip8"]).reset_index()
        sole = by_cusip.groupby("cusip8")["gvkey"].agg(["nunique", "first"])
        cusip = g["CUSIP9"].astype("string").str[:8].map(sole.loc[sole["nunique"] == 1, "first"])
        found = pd.concat([g[["permno", "gvkey"]], g[["permno"]].assign(gvkey=carry)])
        found = pd.concat([found, g[["permno"]].assign(gvkey=cusip)]).dropna()
        panel = pd.read_parquet(panel_path, columns=["permno", "gvkey"]).dropna()
        found = pd.concat([found, panel.astype({"permno": "int64"})]).drop_duplicates()
        one = found.groupby("permno")["gvkey"].agg(["nunique", "first"])
        fill = g["permno"].map(one.loc[one["nunique"] == 1, "first"])
        # Each route checked against WRDS ratios where both name a gvkey.
        checks, ratio = {}, g["gvkey"].copy()
        for name, route in (
            ("carry_2015", carry),
            ("cusip_dated", cusip),
            ("fill_one_gvkey", fill),
        ):
            both = ratio.notna() & route.notna() & alive(route)
            checks[name] = round(float((route[both] == ratio[both]).mean()), 4)
            take = g["gvkey"].isna() & route.notna() & alive(route)
            g.loc[take, "gvkey"] = route[take]
            g.loc[take, "source"] = name
        report["pre_2015_route_agreement_with_ratios"] = checks
    g = g.dropna(subset=["gvkey"])
    report["pre_2015_months_by_source"] = g["source"].value_counts().to_dict()
    g["start"] = g["month"].dt.start_time
    # iid 01 only for a one-common-stock company (M2), else the 2015 iid.
    count = common_per_company(crsp_path)
    single = count.reindex(pd.MultiIndex.from_arrays([g["permno"], g["month"]])).eq(1)
    single = single.to_numpy()
    own = ~single & g["gvkey"].eq(g["permno"].map(first["gvkey"])).to_numpy()
    g["iid"] = pd.Series(pd.NA, index=g.index, dtype="string")
    g.loc[single, "iid"] = "01"
    g.loc[own, "iid"] = g.loc[own, "permno"].map(first["iid"]).to_numpy()
    # One pass per kind, so a period never spans another source's months.
    tagged = g.assign(value=g["gvkey"] + "|" + g["source"])
    known = g[g["iid"].notna()]
    parts = [runs(tagged, "gvkey", "", None)]
    parts.append(runs(known.assign(value=known["iid"] + "|" + known["source"]), "iid", "", None))
    pairs = known.assign(value=known["gvkey"] + ":" + known["iid"] + "|" + known["source"])
    parts.append(runs(pairs, "gvkey_iid", "", None))
    for frame in parts:
        frame[["value", "source"]] = frame["value"].str.split("|", n=1, expand=True)
    out = pd.concat(parts, ignore_index=True)
    out["valid_to"] = pd.to_datetime(out["valid_to"]).clip(upper=PANEL_START - DAY)
    report["pre_2015_iid_from_the_panel"] = int(own.sum())
    report["pre_2015_iid_unknown_rows"] = int(g["iid"].isna().sum())
    return out, report


# Each stock's gvkey and iid in its first panel month (2015 on).
def first_panel_pairs(panel_path: Path) -> pd.DataFrame:
    p = pd.read_parquet(panel_path, columns=["permno", "gvkey", "iid", "eom"])
    p["permno"] = pd.to_numeric(p["permno"]).astype("int64")
    p = p.sort_values("eom").drop_duplicates("permno")
    return p.set_index("permno")[["gvkey", "iid"]].astype(str)


# Dated id periods taken as given from a WRDS link table.
def periods(frame: pd.DataFrame, kind: str, source: str, value: str, score: str) -> pd.DataFrame:
    frame = frame[pd.to_numeric(frame["PERMNO"], errors="coerce").notna()]
    out = pd.DataFrame(
        {
            "permno": pd.to_numeric(frame["PERMNO"]).astype("int64"),
            "kind": kind,
            "value": frame[value].astype(str),
            "valid_from": pd.to_datetime(frame["sdate"], errors="coerce"),
            "valid_to": pd.to_datetime(frame["edate"], errors="coerce"),
            "source": source,
            "score": pd.to_numeric(frame[score], errors="coerce"),
        }
    )
    return out.dropna(subset=["permno", "valid_from"])


# I/B/E/S tickers at score 2 or better, and OptionMetrics secids.
def wrds_links(ibes_path: Path, options_path: Path) -> pd.DataFrame:
    ibes = pd.read_parquet(ibes_path)
    ibes = ibes[pd.to_numeric(ibes["SCORE"], errors="coerce") <= IBES_SCORE]
    options = pd.read_parquet(options_path)
    return pd.concat(
        [
            periods(ibes, "ibes", "ibes_crsp_link", "TICKER", "SCORE"),
            periods(options, "secid", "options_link", "secid", "score"),
        ]
    )


# TAQ symbols by first and last day seen in the daily link (to 2024-12).
def taq(path: Path) -> pd.DataFrame:
    cols = ["DATE", "SYM_ROOT", "SYM_SUFFIX", "PERMNO", "match_lvl"]
    table = pq.read_table(path, columns=cols)
    grouped = table.group_by(["PERMNO", "SYM_ROOT", "SYM_SUFFIX"], use_threads=True).aggregate(
        [("DATE", "min"), ("DATE", "max"), ("match_lvl", "min")]
    )
    g = grouped.to_pandas()
    g = g[pd.to_numeric(g["PERMNO"], errors="coerce").notna()]
    suffix = g["SYM_SUFFIX"].fillna("")
    symbol = g["SYM_ROOT"].astype(str) + suffix.map(lambda s: f".{s}" if s else "")
    return pd.DataFrame(
        {
            "permno": pd.to_numeric(g["PERMNO"]).astype("int64"),
            "kind": "taq",
            "value": symbol,
            "valid_from": pd.to_datetime(g["DATE_min"]),
            "valid_to": pd.to_datetime(g["DATE_max"]),
            "source": "taq_link",
            "score": pd.to_numeric(g["match_lvl_min"], errors="coerce"),
        }
    )


# Each SEC filer's first filing in our index, so a link starts there.
def first_filings(paths: list[Path]) -> pd.Series:
    parts = [pd.read_parquet(p, columns=["cik", "filing_date"]) for p in paths if p.exists()]
    f = pd.concat(parts, ignore_index=True)
    f["filing_date"] = pd.to_datetime(f["filing_date"], errors="coerce")
    return f.groupby(pd.to_numeric(f["cik"]).astype("int64"))["filing_date"].min()


# SEC ids by date: decisions, then 8-K pairs, else Compustat's header.
def ciks(
    cik_map: Path, eightk: Path, decisions: Path, first: pd.Series | None = None
) -> tuple[pd.DataFrame, dict]:
    chosen = json.loads(decisions.read_text(encoding="utf-8"))["stocks"]
    firms = pd.read_parquet(cik_map)
    pairs = pd.read_parquet(eightk, columns=["permno", "cik"])
    pairs["cik"] = pd.to_numeric(pairs["cik"], errors="coerce")
    pairs = pairs.dropna().astype({"permno": "int64", "cik": "int64"})
    several = pairs.groupby("permno")["cik"].nunique()
    unsettled = sorted(set(several[several > 1].index) - {int(p) for p in chosen})
    if unsettled:
        raise ValueError(f"stocks with several SEC ids and no decision: {unsettled}")
    one = pairs.drop_duplicates("permno").set_index("permno")["cik"]
    rows = []
    for permno, entry in chosen.items():
        # Each decision carries its approval day.
        source = f"decision_{entry.get('approved', '2026-10-23')}"
        for cik, start, stop in entry["links"]:
            rows.append((int(permno), str(cik), start, stop, source))
    first = pd.Series(dtype="datetime64[ns]") if first is None else first
    for firm in firms.itertuples():
        if str(firm.permno) in chosen:
            continue
        if firm.permno in one.index:
            cik, source = int(one[firm.permno]), "organisers_8k_pairs"
        elif pd.notna(firm.cik_compustat):
            cik, source = int(firm.cik_compustat), "compustat_header"
        else:
            continue
        # Undated sources start at the filer's first filing (H4).
        rows.append((firm.permno, str(cik), first.get(cik), None, source))
    out = pd.DataFrame(rows, columns=["permno", "value", "valid_from", "valid_to", "source"])
    out["valid_from"] = pd.to_datetime(out["valid_from"]).fillna(pd.Timestamp("1900-01-01"))
    out["valid_to"] = pd.to_datetime(out["valid_to"])
    out = out.assign(kind="cik", score=pd.NA)[COLUMNS]
    report = {"cik_by_source": out.drop_duplicates("permno")["source"].value_counts().to_dict()}
    report["cik_none"] = int(len(firms) - out["permno"].nunique())
    dated = out["source"].isin(["organisers_8k_pairs", "compustat_header"])
    report["cik_starting_at_first_filing"] = int((dated & (out["valid_from"].dt.year > 1900)).sum())
    return out, report


# Legal words that never tell two companies apart (as in edgar.py).
LEGAL = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "LLC"}
LEGAL |= {"PLC", "HOLDINGS", "HOLDING", "GROUP", "NV", "SA", "AG", "LP", "SE", "THE", "NEW", "DEL"}
LEGAL |= {"DE", "CL", "CLASS", "HLDGS", "HLDG", "HLDS", "HLD", "HLDNGS", "GRP"}
# CRSP's short forms, mined from trusted pairs, used on both names.
SHORT = {"ACQUISITION": "ACQ", "ACQUISITIONS": "ACQ", "INTERNATIONAL": "INTL"}
SHORT |= {"SERVICES": "SVCS", "SRVCS": "SVCS", "SERVICE": "SVC", "TECHNOLOGY": "TECH"}
SHORT |= {"TECHNOLOGIES": "TECH", "TECHS": "TECH", "INDUSTRIES": "INDS", "COMPANIES": "COS"}
SHORT |= {"FINANCIAL": "FINL", "SYSTEMS": "SYS", "CAPITAL": "CAP", "OPPORTUNITIES": "OPP"}
SHORT |= {"OPPORTUNITY": "OPP", "TRUST": "TR", "SOLUTIONS": "SOL", "SOLS": "SOL", "SOLNS": "SOL"}
SHORT |= {"SOLUTNS": "SOL", "BANCORPORATION": "BANCORP", "NATIONAL": "NATL", "MANAGEMENT": "MGMT"}
SHORT |= {"PARTNERS": "PTNRS", "PRODUCTS": "PRODS", "INFRASTRUCTURE": "INFR", "INFRA": "INFR"}
SHORT |= {"DEVELOPMENT": "DEV", "RESOURCES": "RES", "INSURANCE": "INS", "LABORATORIES": "LABS"}
SHORT |= {"INVESTMENT": "INVT", "INVESTMENTS": "INVT", "INFORMATION": "INFO", "ESTATE": "EST"}
SHORT |= {
    "ENTERTAINMENT": "ENTMT",
    "POWER": "PWR",
    "COMMUNICATIONS": "COMMS",
    "ASSOCIATES": "ASSOC",
}
SHORT |= {"PROPERTIES": "PPTYS", "PHARMACEUTICALS": "PHARM", "PHARMACEUTICAL": "PHARM"}
SHORT |= {"PHARMS": "PHARM", "BANCSHRS": "BANCSHARES", "CHEMICALS": "CHEM", "CHEMICAL": "CHEM"}
SHORT |= {"MANUFACTURING": "MFG"}
STRONG = {"compustat_header", "organisers_8k_pairs"}
SUCCESSION = ("8-K12B", "8-K12G3", "8-A12B")
FRESH = pd.DateOffset(months=3)
SILENT = pd.Timedelta(days=400)
INDEX_START = pd.Timestamp("2006-01-01")
NAME_GAP = 24
NEAR_FILING = pd.DateOffset(months=18)


# A company name as its sorted words, state tags and legal words out.
def entity_key(name) -> str:
    s = re.sub(r"\(LAST KNOWN\)", " ", str(name).upper()).replace("'", "").replace("\u2019", "")
    s = re.sub(r"/(?!OLD/?\s*$)[A-Z]{1,3}/?\s*$", " ", s.strip()).replace("&", " AND ")
    # Stops and hyphens split words ("WEB.COM", "O-I"); a glued "INC" too.
    s = re.sub(r"\b([A-Z]{5,})INC\b", r"\1 INC", s.replace(".", " ").replace("-", " "))
    # CRSP's "3RD NEW" tags a re-listing; a slash splits "B/E" in two.
    s = re.sub(r"\b\d+(?:ST|ND|RD|TH)\s+NEW\b", " ", s).replace("/", " ")
    # Letters or digits spelled one by one ("T C F", "F 5") are one word.
    s = re.sub(r"\b(?:[A-Z0-9]\s+)+[A-Z0-9]\b", lambda m: m.group(0).replace(" ", ""), s)
    words = {SHORT.get(w, w) for w in re.findall(r"[A-Z0-9]+", s)}
    return " ".join(sorted(words - LEGAL))


# Share of words matched both ways; four shared letters match "HLDGS".
def overlap(a: str, b: str) -> float:
    x, y = a.split(), b.split()
    if not x or not y:
        return 0.0

    # One word against another: equal, or the same first four letters.
    def same(u: str, v: str) -> bool:
        return u == v or (len(u) >= 4 and len(v) >= 4 and u[:4] == v[:4])

    # A word meets a word, or two words joined ("CARMART", "CAR MART").
    def found(u: str, own: list, other: list) -> bool:
        if any(same(u, v) for v in other):
            return True
        joined = {v + w for v in other for w in other if v != w}
        return u in joined or any(u + w in other or w + u in other for w in own if w != u)

    hits = sum(found(u, x, y) for u in x) + sum(found(v, y, x) for v in y)
    return hits / (len(x) + len(y))


# Each stock-month's SEC filer by dated names.
def dated_ciks(paths: dict) -> tuple[pd.DataFrame, dict]:
    cand = pd.read_parquet(paths["candidates"])
    names = pd.read_parquet(paths["cik_names"]).assign(key=lambda d: d["name"].map(entity_key))
    crsp = pd.read_parquet(paths["crsp"], columns=["PERMNO", "PERMCO", "MthCalDt", "IssuerNm"])
    crsp = crsp.assign(
        permno=pd.to_numeric(crsp["PERMNO"], errors="coerce"),
        month=pd.to_datetime(crsp["MthCalDt"]),
        stock_key=crsp["IssuerNm"].map(entity_key),
    ).dropna(subset=["permno", "month"])
    crsp = crsp[crsp["permno"].isin(cand["permno"])].astype({"permno": "int64"})
    crsp = crsp[["permno", "PERMCO", "month", "stock_key"]].drop_duplicates(["permno", "month"])
    # Filer links start with the SEC index in 2006, as no SEC data is older.
    crsp = crsp[crsp["month"] >= INDEX_START]
    f = pd.concat(
        [
            pd.read_parquet(paths[k], columns=["cik", "form", "filing_date", "accession"])
            for k in ("filings", "forms")
        ]
    )
    f = f.assign(
        cik=pd.to_numeric(f["cik"]).astype("int64"), filing_date=pd.to_datetime(f["filing_date"])
    )
    # Each filer's succession forms, every copy of a joint filing kept.
    succ = f[f["form"].isin(SUCCESSION)].sort_values("filing_date")
    reg = {
        c: np.sort(g.to_numpy().astype("datetime64[ns]"))
        for c, g in succ.groupby("cik")["filing_date"]
    }
    # A filer's own filings, those no other filer in the index shares.
    copies = f.groupby("accession")["cik"].transform("nunique")
    own = f[copies == 1]
    dates = {
        c: np.sort(g.to_numpy().astype("datetime64[ns]"))
        for c, g in own.groupby("cik")["filing_date"]
    }
    # A joint filing goes to the co-filer with more own filings in a year.
    joint = f[copies > 1].copy()
    joint["recent"] = 0
    for c, rows in joint.groupby("cik").groups.items():
        when = joint.loc[rows, "filing_date"].to_numpy().astype("datetime64[ns]")
        joint.loc[rows, "recent"] = [filed_in(dates, c, d, np.timedelta64(365, "D")) for d in when]
    joint = joint.sort_values(["recent", "cik"], ascending=[False, True])
    f = pd.concat([own, joint.drop_duplicates("accession").drop(columns="recent")])
    span = f.groupby("cik")["filing_date"].agg(first="min", last="max")
    # A filer counts only from its first SEC filing, on every page (H1).
    sec_first = pd.read_parquet(paths["cik_first"]).set_index("cik")["first_filing"]
    sec = pd.Series(span.index.map(sec_first), index=span.index)
    span["first"] = pd.concat([sec, span["first"]], axis=1).min(axis=1)
    # Every stock-month beside each candidate id and its SEC name then.
    grid = crsp.merge(cand, on="permno").merge(
        names[["cik", "key", "valid_from", "valid_to"]], on="cik"
    )
    live = grid["valid_from"].isna() | (grid["valid_from"] <= grid["month"])
    live &= grid["valid_to"].isna() | (grid["valid_to"] >= grid["month"] - pd.offsets.MonthBegin(1))
    grid = grid[live].join(span, on="cik")
    near = (grid["first"] <= grid["month"] + pd.offsets.MonthEnd(0)) & (
        grid["last"] >= grid["month"] - NEAR_FILING
    )
    grid = grid[near.fillna(False)]
    pairs = grid[["key", "stock_key"]].drop_duplicates()
    pairs["score"] = [overlap(a, b) for a, b in zip(pairs["key"], pairs["stock_key"])]
    grid = grid.merge(pairs, on=["key", "stock_key"])
    strong = grid["source"].isin(STRONG)
    # Both trusted sources on the only filer filing then (Wabtec's brand).
    trusted = grid[strong].groupby(["permno", "cik"])["source"].nunique().rename("trusted")
    grid = grid.join(trusted, on=["permno", "cik"])
    alone = grid.groupby(["permno", "month"])["cik"].transform("nunique") == 1
    agreed = (grid["trusted"] == len(STRONG)) & alone
    # A trusted source needs half its words matched; a name alone, all.
    named = (strong & (grid["score"] >= 0.5)) | (grid["score"] >= 1.0)
    agreed_only = grid[agreed & ~named][["permno", "month"]].drop_duplicates()
    grid = grid[named | agreed]
    grid = grid.assign(strong=strong[grid.index]).sort_values(["permno", "month", "score"])
    grid = grid.assign(agreed=grid["trusted"] == len(STRONG))
    best = grid.groupby(["permno", "month", "cik"], as_index=False).agg(
        score=("score", "max"),
        strong=("strong", "max"),
        agreed=("agreed", "max"),
        permco=("PERMCO", "first"),
    )
    # Both sources' filer is never taken by another company on a name.
    held = best[best["agreed"]]
    claimed = set(zip(held["cik"], held["month"]))
    owners = set(zip(held["cik"], held["month"], held["permco"]))
    keys = list(zip(best["cik"], best["month"], best["permco"]))
    blocked = pd.Series([(c, m) in claimed and (c, m, p) not in owners for c, m, p in keys])
    blocked = blocked.to_numpy() & ~best["agreed"].to_numpy() & ~best["strong"].to_numpy()
    lost = int(blocked.sum())
    best = best[~blocked]
    # An id-month belongs to the companies carrying its name best (Swift).
    top = best.groupby(["cik", "month"])["score"].transform("max")
    tied = best["score"] >= top
    held_by = best[tied & best["strong"]]
    trusted = set(zip(held_by["cik"], held_by["month"]))
    trusted_co = set(zip(held_by["cik"], held_by["month"], held_by["permco"]))
    keys = zip(best["cik"], best["month"], best["permco"])
    beaten = [(c, m) in trusted and (c, m, p) not in trusted_co for c, m, p in keys]
    tied &= ~pd.Series(beaten, index=best.index)
    owned = best[tied]
    chosen = pick_ids(owned, reg, span, dates)
    # An owner filing under another id that month leaves this one free.
    used = set(zip(chosen["cik"], chosen["month"]))
    lower = best[~tied]
    freed = lower[[(c, m) not in used for c, m in zip(lower["cik"], lower["month"])]]
    if len(freed):
        chosen = pick_ids(pd.concat([owned, freed]), reg, span, dates)
    report = {"candidate_months_owned_by_another_company": len(lower) - len(freed)}
    report["candidate_months_freed_as_owner_files_elsewhere"] = len(freed)
    report["stock_months_held_by_trusted_agreement"] = len(agreed_only)
    report["candidate_months_lost_to_trusted_agreement"] = lost
    # Two companies left on one id-month carry its name equally: counted.
    shared = chosen.groupby(["cik", "month"])["permco"].transform("nunique") > 1
    report["cik_months_shared_by_equal_names"] = int(shared.sum())
    out = month_periods(chosen, crsp)
    report["cik_dated_stocks"] = int(out["permno"].nunique())
    report["cik_dated_periods"] = len(out)
    return out, report


# Filings of one filer in the window up to a day, from its sorted dates.
def filed_in(dates: dict, cik: int, end: np.datetime64, window: np.timedelta64) -> int:
    got = dates.get(cik)
    if got is None:
        return 0
    hi = np.searchsorted(got, end, side="right")
    return int(hi - np.searchsorted(got, end - window, side="right"))


# A successor's latest succession form in the three months to a day.
def fresh_form(reg: dict, cik: int, end: np.datetime64, since: np.datetime64):
    got = reg.get(cik)
    if got is None:
        return None
    at = np.searchsorted(got, end, side="right") - 1
    return got[at] if at >= 0 and got[at] > since else None


# One id per stock-month: the sitting one while it still matches.
def pick_ids(best: pd.DataFrame, reg: dict, span: pd.DataFrame, dates: dict) -> pd.DataFrame:
    rows = []
    year, quiet_for = np.timedelta64(365, "D"), np.timedelta64(SILENT.days, "D")
    first = span["first"].to_dict()
    cols = ["permno", "month", "cik", "score", "strong", "permco"]
    for permno, g in best[cols].sort_values("month").groupby("permno", sort=False):
        sitting, by_month = None, {}
        for r in g.itertuples(index=False):
            by_month.setdefault(r.month, []).append(r)
        for month, options in by_month.items():
            end = np.datetime64(month + pd.offsets.MonthEnd(0), "ns")
            back = np.datetime64(month + pd.offsets.MonthEnd(0) - FRESH, "ns")
            busy = {o.cik: filed_in(dates, o.cik, end, year) for o in options}
            # Trusted first, then the best name, the busiest year, the oldest.
            order = sorted(
                options,
                key=lambda o: (
                    -o.strong,
                    -o.score,
                    -busy[o.cik],
                    first.get(o.cik, pd.Timestamp.max),
                ),
            )
            by_cik = {o.cik: o for o in options}
            since = pd.NaT
            if sitting in by_cik:
                held = by_cik[sitting].score
                # A successor is trusted, or carries the stock's name better.
                fresh = [
                    o
                    for o in order
                    if o.cik != sitting
                    and o.score >= held
                    and (o.strong or o.score > held)
                    and fresh_form(reg, o.cik, end, back) is not None
                ]
                # A filer silent for 13 months yields to an option that files.
                awake = [
                    o for o in order if o.cik != sitting and filed_in(dates, o.cik, end, quiet_for)
                ]
                if fresh:
                    pick = fresh[0]
                    since = max(
                        pd.Timestamp(fresh_form(reg, pick.cik, end, back)), month.replace(day=1)
                    )
                elif awake and not filed_in(dates, sitting, end, quiet_for):
                    pick = awake[0]
                else:
                    pick = by_cik[sitting]
            else:
                pick = order[0]
            sitting = pick.cik
            rows.append((permno, month, pick.cik, pick.score, pick.permco, since))
    return pd.DataFrame(rows, columns=["permno", "month", "cik", "score", "permco", "since"])


# Monthly ids into periods, with short name-lag gaps filled (24 months).
def month_periods(chosen: pd.DataFrame, crsp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    last_month = crsp["month"].max()
    for permno, g in chosen.sort_values("month").groupby("permno"):
        g = g.reset_index(drop=True)
        start = g.loc[0, "month"].replace(day=1)
        for i in range(1, len(g) + 1):
            done = i == len(g)
            if not done:
                same = g.loc[i, "cik"] == g.loc[i - 1, "cik"]
                gap = (g.loc[i, "month"].to_period("M") - g.loc[i - 1, "month"].to_period("M")).n
                if same and gap <= NAME_GAP:
                    continue
            # A period runs to its month end, or to the day before a dated switch.
            end = g.loc[i - 1, "month"]
            stop = pd.NaT if end >= last_month else end + pd.offsets.MonthEnd(0)
            since = g.loc[i, "since"] if not done else pd.NaT
            nxt = since if pd.notna(since) else None
            follows = not done and g.loc[i, "month"].to_period("M") == end.to_period("M") + 1
            if nxt is not None and follows:
                stop = nxt - pd.Timedelta(days=1)
            rows.append((permno, str(int(g.loc[i - 1, "cik"])), start, stop))
            if not done:
                start = nxt if nxt is not None else g.loc[i, "month"].replace(day=1)
    out = pd.DataFrame(rows, columns=["permno", "value", "valid_from", "valid_to"])
    return out.assign(kind="cik", source="sec_dated_names", score=pd.NA)[COLUMNS]


# Carbon Arc tickers to PERMNO by the CRSP ticker on the pull date.
def carbon_arc(companies: Path, manifest: Path, crsp_links: pd.DataFrame) -> tuple:
    pulled = pd.Timestamp(json.loads(manifest.read_text())["pulled_at"][:10])
    rows = pd.DataFrame(json.loads(companies.read_text(encoding="utf-8")))
    rows = rows[rows["representation"] == "ticker"]
    live = crsp_links[(crsp_links["kind"] == "ticker") & crsp_links["valid_to"].isna()]
    owners = live.groupby("value")["permno"].agg(["nunique", "first"])
    sole = owners[owners["nunique"] == 1]["first"]
    hit = rows[rows["label"].isin(sole.index)].copy()
    hit["permno"] = hit["label"].map(sole).astype("int64")
    base = {"valid_from": pulled, "valid_to": pd.NaT, "source": "carbon_arc_ticker", "score": pd.NA}
    ids = hit.assign(kind="carc", value=hit["entity_id"].astype(str), **base)
    figi = hit.dropna(subset=["figi_code"])
    figi = figi.assign(kind="figi", value=figi["figi_code"].astype(str), **base)
    report = {
        "carc_tickers": len(rows),
        "carc_matched_to_one_permno": len(hit),
        "carc_shared_tickers_left_out": int(
            rows["label"].isin(owners[owners["nunique"] > 1].index).sum()
        ),
        "carc_pulled": str(pulled.date()),
    }
    return pd.concat([ids[COLUMNS], figi[COLUMNS]]), report


# Link periods with both dates on the nanosecond unit lookups use.
def nanos(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in ("valid_from", "valid_to"):
        out[col] = pd.to_datetime(out[col]).astype("datetime64[ns]")
    return out


# Each (permno, date)'s value of one id kind, from its period.
def value_at(links: pd.DataFrame, kind: str, permnos, dates) -> pd.Series:
    left = pd.DataFrame({"permno": pd.Series(permnos).astype("int64").to_numpy()})
    left["date"] = pd.to_datetime(pd.Series(dates).to_numpy()).astype("datetime64[ns]")
    left["order"] = range(len(left))
    right = nanos(links[links["kind"] == kind]).sort_values("valid_from")
    got = pd.merge_asof(
        left.sort_values("date"),
        right[["permno", "value", "valid_from", "valid_to"]],
        left_on="date",
        right_on="valid_from",
        by="permno",
        direction="backward",
    )
    inside = got["valid_to"].isna() | (got["date"] <= got["valid_to"])
    got.loc[~inside, "value"] = pd.NA
    return got.sort_values("order")["value"].reset_index(drop=True)


# The PERMNO holding an id value on each date; shared values stay empty.
def permno_at(links: pd.DataFrame, kind: str, values, dates) -> pd.Series:
    left = pd.DataFrame({"value": pd.Series(values).astype(str).to_numpy()})
    left["date"] = pd.to_datetime(pd.Series(dates).to_numpy()).astype("datetime64[ns]")
    left["order"] = range(len(left))
    right = nanos(links.loc[links["kind"] == kind, ["permno", "value", "valid_from", "valid_to"]])
    both = left.merge(right, on="value", how="inner")
    live = (both["date"] >= both["valid_from"]) & (
        both["valid_to"].isna() | (both["date"] <= both["valid_to"])
    )
    both = both[live]
    count = both.groupby("order")["permno"].nunique()
    sole = both[both["order"].isin(count[count == 1].index)].drop_duplicates("order")
    out = pd.Series(pd.NA, index=range(len(left)), dtype="Int64")
    out[sole["order"].to_numpy()] = sole["permno"].to_numpy()
    return out


# A symbol in letters and digits only, so BRK.B, BRK/B and BRKB match.
def plain_symbol(symbols) -> pd.Series:
    text = pd.Series(symbols, dtype="string").fillna("").str.upper()
    return text.str.replace(r"[^A-Z0-9]", "", regex=True)


# A ticker-keyed source to PERMNO: CRSP trading symbol, then ticker.
def permno_by_symbol(links: pd.DataFrame, symbols, dates) -> pd.Series:
    keys = plain_symbol(symbols)
    days = pd.Series(pd.to_datetime(pd.Series(dates).to_numpy()))
    found = pd.Series(pd.NA, index=range(len(keys)), dtype="Int64")
    for kind in ("symbol", "ticker"):
        table = links[links["kind"] == kind].copy()
        table["value"] = plain_symbol(table["value"]).to_numpy()
        todo = found.isna().to_numpy()
        if todo.any():
            got = permno_at(table, kind, keys[todo], days[todo])
            found[found.index[todo]] = got.to_numpy()
    return found


# Share of panel stock-months with each id kind at that eom (counts).
def coverage(links: pd.DataFrame, panel_path: Path) -> dict:
    p = pd.read_parquet(panel_path, columns=["permno", "eom"])
    p["permno"] = pd.to_numeric(p["permno"]).astype("int64")
    p["eom"] = pd.to_datetime(p["eom"])
    out = {}
    for kind in ("cusip", "ticker", "permco", "gvkey", "iid", "cik", "ibes", "secid", "taq"):
        have = value_at(links, kind, p["permno"], p["eom"]).notna()
        by_year = have.groupby(p["eom"].dt.year.to_numpy()).mean().round(4)
        out[kind] = {"all": round(float(have.mean()), 4), "by_year": by_year.to_dict()}
    return out


# Builds the table and its report; writes both under data/v4.
def build(data: Path = DATA) -> dict:
    p = paths(data)
    crsp_links = crsp(p["crsp"])
    ratio_links, ratio_report = ratios(p["ratios"], p["panel"], p["crsp"], p["ids"])
    first = first_filings([p["filings"], p["forms"]])
    cik_links, cik_report = ciks(p["cik_map"], p["eightk"], p["decisions"], first)
    # The 17 decided stocks stand; every other stock takes dated ids.
    dated, dated_report = dated_ciks(p)
    decided = cik_links[cik_links["source"].str.startswith("decision")]
    dated = dated[~dated["permno"].isin(decided["permno"])]
    cik_links = pd.concat([decided, dated], ignore_index=True)
    # Every CIK link ends at its stock's last CRSP month (final audit L3).
    m = pd.read_parquet(p["crsp"], columns=["PERMNO", "MthCalDt"])
    m = m.assign(permno=pd.to_numeric(m["PERMNO"]), month=pd.to_datetime(m["MthCalDt"]))
    last = m.groupby("permno")["month"].max() + pd.offsets.MonthEnd(0)
    ended = cik_links["permno"].map(last.where(last < m["month"].max()))
    to = pd.to_datetime(cik_links["valid_to"])
    cik_links["valid_to"] = to.where(to.notna() & (to <= ended.fillna(to)), ended)
    cik_report |= dated_report
    carc_links, carc_report = carbon_arc(p["carc"], p["carc_manifest"], crsp_links)
    parts = [crsp_links, panel(p["panel"]), ratio_links, wrds_links(p["ibes"], p["options"])]
    parts += [taq(p["taq"]), cik_links, carc_links]
    links = pd.concat(parts, ignore_index=True)
    links["score"] = pd.to_numeric(links["score"], errors="coerce")
    for col in ("valid_from", "valid_to"):
        links[col] = pd.to_datetime(links[col]).astype("datetime64[ns]")
    links = links.astype({"permno": "int64", "kind": "string", "value": "string"})
    links = links.sort_values(["kind", "permno", "valid_from"], ignore_index=True)
    out = data / "v4" / "links.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    links.to_parquet(out, index=False)
    report = {"rows": len(links), "by_kind": links["kind"].value_counts().to_dict()}
    report |= ratio_report | cik_report | carc_report
    report["panel_coverage"] = coverage(links, p["panel"])
    (data / "v4" / "links.json").write_text(json.dumps(report, indent=1, default=str))
    # The build's receipt: its code and every input's hash (final audit L4).
    code = [Path(__file__), Path(__file__).parents[2] / "tools" / "data" / "edgar.py"]
    book = {"code": {c.name: digest(c) for c in code}}
    book["inputs"] = {k: digest(v) for k, v in p.items() if v.exists()}
    (data / "v4" / "links_build.json").write_text(json.dumps(book, indent=1))
    return report


# A file's SHA-256, read in chunks.
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Builds the link table: uv run python -m fiam.vfinal.links
if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str))
    sys.exit(0)
