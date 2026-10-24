# The dated PERMNO link table: each id and its period (PLAN §6.7).

import json
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
# I/B/E/S links are kept at score 2 or better (§6.6).
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


# CUSIP, ticker, symbol, share class and PERMCO by date, CRSP monthly.
def crsp(path: Path) -> pd.DataFrame:
    keep = ["PERMNO", "MthCalDt", "SecInfoStartDt", "CUSIP9", "Ticker", "TradingSymbol"]
    m = pd.read_parquet(path, columns=keep + ["ShareClass", "PERMCO"])
    m["permno"] = pd.to_numeric(m["PERMNO"]).astype("int64")
    m["date"] = pd.to_datetime(m["MthCalDt"])
    start = pd.to_datetime(m["SecInfoStartDt"], errors="coerce")
    m["start"] = start.where(start <= m["date"], m["date"]).fillna(m["date"])
    end = m["date"].max()
    pairs = [("CUSIP9", "cusip"), ("Ticker", "ticker"), ("TradingSymbol", "symbol")]
    pairs += [("ShareClass", "share_class"), ("PERMCO", "permco")]
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


# WRDS ratios' gvkey per stock and month; two on one date resolved (A16).
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


# Pre-2015 gvkey and iid by month (A16, M2, 4A+, approved 2026-10-23):
# WRDS ratios first; then the stock's own 2015 pair carried back from the
# gvkey's first Compustat date; then Compustat's CUSIP matched to CRSP's
# CUSIP of that month; then a stock whose every link names one gvkey.
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
    # iid 01 only when CRSP shows one common stock for the company (M2);
    # else the stock's own 2015 panel iid when its gvkey agrees; else none.
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
        for cik, start, stop in entry["links"]:
            rows.append((int(permno), str(cik), start, stop, "decision_2026-10-23"))
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


# A symbol reduced to letters and digits, so BRK.B, BRK/B and BRKB match.
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
    return report


# Builds the link table: uv run python -m fiam.v4.links
if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str))
    sys.exit(0)
