# The dated PERMNO link table: each id and its period (PLAN §6.7).

import json
import sys
from pathlib import Path

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
        "eightk": data / "organisers" / "8k_20150101_20260831_identified.parquet",
        "cik_map": data / "edgar" / "cik_map.parquet",
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


# Gvkey before 2015 from WRDS ratios, one per stock and date (A16).
def ratios(path: Path, panel_path: Path) -> tuple[pd.DataFrame, dict]:
    r = pd.read_parquet(path, columns=["gvkey", "permno", "public_date"]).dropna()
    r["date"] = pd.to_datetime(r["public_date"])
    r = r[r["date"] < PANEL_START].copy()
    r["permno"] = pd.to_numeric(r["permno"]).astype("int64")
    r["start"] = r["date"].dt.to_period("M").dt.start_time
    first = first_panel_pairs(panel_path)
    # Two gvkeys on one date: the panel's own gvkey, else the usual one.
    r["panel_match"] = r["gvkey"].eq(r["permno"].map(first["gvkey"]))
    r["usual"] = r.groupby(["permno", "gvkey"])["date"].transform("size")
    r = r.sort_values(["permno", "date", "panel_match", "usual", "gvkey"])
    picked = r.drop_duplicates(["permno", "date"], keep="last")
    report = {"pre_2015_two_gvkey_dates_resolved": len(r) - len(picked)}
    gvkey = runs(picked.assign(value=picked["gvkey"]), "gvkey", "wrds_ratios", None)
    gvkey["valid_to"] = gvkey["valid_to"].clip(upper=PANEL_START - DAY)
    per_firm = picked.groupby("gvkey")["permno"].nunique()
    single = gvkey["value"].map(per_firm).eq(1)
    # A firm with several securities takes its 2015 panel iid if it agrees.
    carried = gvkey["value"].eq(gvkey["permno"].map(first["gvkey"]))
    iids = pd.Series(pd.NA, index=gvkey.index, dtype="string")
    iids[single] = "01"
    iids[~single & carried] = gvkey.loc[~single & carried, "permno"].map(first["iid"])
    known = iids.notna()
    iid = gvkey[known].assign(kind="iid", value=iids[known])
    pair = gvkey[known].assign(kind="gvkey_iid", value=gvkey["value"][known] + ":" + iids[known])
    report["pre_2015_iid_from_the_panel"] = int((~single & carried).sum())
    report["pre_2015_iid_unknown_periods"] = int((~known).sum())
    return pd.concat([gvkey, iid, pair]), report


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


# SEC ids by date: decisions, then 8-K pairs, else Compustat's header.
def ciks(cik_map: Path, eightk: Path, decisions: Path) -> tuple[pd.DataFrame, dict]:
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
    for firm in firms.itertuples():
        if str(firm.permno) in chosen:
            continue
        if firm.permno in one.index:
            rows.append((firm.permno, str(one[firm.permno]), None, None, "organisers_8k_pairs"))
        elif pd.notna(firm.cik_compustat):
            rows.append((firm.permno, str(int(firm.cik_compustat)), None, None, "compustat_header"))
    out = pd.DataFrame(rows, columns=["permno", "value", "valid_from", "valid_to", "source"])
    out["valid_from"] = pd.to_datetime(out["valid_from"]).fillna(pd.Timestamp("1900-01-01"))
    out["valid_to"] = pd.to_datetime(out["valid_to"])
    out = out.assign(kind="cik", score=pd.NA)[COLUMNS]
    report = {"cik_by_source": out.drop_duplicates("permno")["source"].value_counts().to_dict()}
    report["cik_none"] = int(len(firms) - out["permno"].nunique())
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
    ratio_links, ratio_report = ratios(p["ratios"], p["panel"])
    cik_links, cik_report = ciks(p["cik_map"], p["eightk"], p["decisions"])
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
