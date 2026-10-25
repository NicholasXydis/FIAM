# Read-only data audit (PLAN §6.8); from 2021 on counts and dates only.

import gzip
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
# The repo root on the path, so the v4 checks read the registry's rules.
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
X = DATA / "v4" / "extracts"
CLEAN = DATA / "v4" / "clean"
OUT = ROOT / "out" / "audit"
SEALED = pd.Timestamp("2021-01-01")
FINDINGS: list[dict] = []
COVERAGE: list[dict] = []
LEVELS = ("fail", "warn", "info", "pass")


# Records one result with its evidence and, for problems, the fix.
def note(level: str, source: str, check: str, evidence: str, fix: str = "") -> None:
    FINDINGS.append(dict(level=level, source=source, check=check, evidence=evidence, fix=fix))
    print(f"[{level}] {source}: {check}: {evidence}", flush=True)


# A pass when the count is zero, else the given level with the fix.
def zero(count: int, source: str, check: str, level: str, fix: str, total: int = 0) -> None:
    share = f" of {total:,}" if total else ""
    if count:
        note(level, source, check, f"{count:,}{share} rows", fix)
    else:
        note("pass", source, check, f"0{share}")


# Rows and names per year for the coverage table.
def cover(source: str, dates: pd.Series, ids: pd.Series | None = None) -> None:
    years = pd.to_datetime(dates, errors="coerce").dt.year
    rows = years.value_counts()
    names = None
    if ids is not None:
        names = pd.Series(ids.to_numpy(), index=years).groupby(level=0).nunique()
    for year, count in rows.sort_index().items():
        entry = dict(source=source, year=int(year), rows=int(count))
        entry["names"] = int(names.get(year, 0)) if names is not None else None
        COVERAGE.append(entry)


# Rows per year added up across files of one source.
def cover_counts(source: str, counts: dict) -> None:
    for year, (rows, names) in sorted(counts.items()):
        COVERAGE.append(dict(source=source, year=int(year), rows=int(rows), names=names))


# One extract as a frame, only the columns asked for.
def extract(name: str, columns: list[str]) -> pd.DataFrame:
    return pd.read_parquet(X / f"{name}.parquet", columns=columns)


# CRSP delistings with numeric PERMNOs and the first delisting date.
def delistings() -> pd.DataFrame:
    dl = extract("crsp_delistings", ["permno", "delistingdt", "delret", "delactiontype"])
    return dl.assign(permno=dl["permno"].astype("int64"), when=pd.to_datetime(dl["delistingdt"]))


# The organisers' panel: the firms, months and the label.
def panel() -> pd.DataFrame:
    cols = ["id", "permno", "gvkey", "iid", "date", "eom", "ret", "ret_exc_lead1m", "me", "gics"]
    frame = pd.read_parquet(DATA / "organisers" / "chars_final_with_names.parquet", columns=cols)
    frame["eom"] = pd.to_datetime(frame["eom"])
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


# Firms that leave the panel before its end, with their last month.
def exits(p: pd.DataFrame) -> pd.Series:
    last = p.groupby("permno")["eom"].max()
    return last[last < p["eom"].max()]


# The organisers' panel: keys, dates, exits, delisting returns, sectors.
def organisers(p: pd.DataFrame) -> None:
    src = "organisers"
    zero(int(p.duplicated(["id", "eom"]).sum()), src, "duplicate (id, eom)", "fail", "dedupe")
    dupes = int(p.dropna(subset=["permno"]).duplicated(["permno", "eom"]).sum())
    zero(dupes, src, "duplicate (permno, eom)", "warn", "keep primary_sec rows")
    zero(int((p["date"] > p["eom"]).sum()), src, "observation date after eom", "fail", "drop")
    cover(src, p["eom"], p["permno"])
    gone = exits(p)
    per_year = gone.dt.year.value_counts().sort_index().to_dict()
    note("info", src, "firms leaving the panel by year", json.dumps(per_year))
    final_month(p, gone[gone < SEALED])
    changes = p.dropna(subset=["gics"]).groupby("permno")["gics"].nunique()
    note(
        "info",
        src,
        "stocks whose GICS changes over time (dated monthly)",
        f"{(changes > 1).sum():,}",
    )
    daily(gone)


# Before 2021: the delisting month's return reaches the panel.
def final_month(p: pd.DataFrame, gone: pd.Series) -> None:
    src = "organisers"
    rows = p.merge(gone.rename("last"), left_on="permno", right_index=True)
    final = rows[rows["eom"] == rows["last"]]
    blank = final[final["ret_exc_lead1m"].isna()]
    dl = delistings().groupby("permno")["when"].min()
    same = int(
        (
            dl.reindex(blank["permno"]).dt.to_period("M").to_numpy()
            == blank["eom"].dt.to_period("M").to_numpy()
        ).sum()
    )
    note(
        "info",
        src,
        "exits before 2021 with no label after their last month",
        f"{len(blank):,} of {len(final):,}; {same:,} delisted within it, so nothing to hold",
    )
    before = rows[rows["eom"] == rows["last"] - pd.offsets.MonthEnd(1)]
    present = int(before["ret_exc_lead1m"].notna().sum())
    zero(
        len(before) - present,
        src,
        "exits before 2021 missing the delisting-month label",
        "fail",
        "fill from CRSP",
        len(before),
    )
    m = extract("crsp_monthly", ["PERMNO", "MthCalDt", "MthRet", "MthDelFlg"])
    m = m.assign(
        permno=m["PERMNO"].astype("int64"),
        eom=pd.to_datetime(m["MthCalDt"]) + pd.offsets.MonthEnd(0),
    )
    j = final.merge(m, on=["permno", "eom"], how="inner")
    same = float(((j["ret"] - j["MthRet"]).abs() < 1e-4).mean())
    note(
        "pass" if same > 0.98 else "warn",
        src,
        "delisting-month return equals CRSP's (which includes the delisting payoff)",
        f"{same:.3f} of {len(j):,} within 1bp",
    )
    early = m[m["eom"] < SEALED]
    flagged = early[early["MthDelFlg"] != "N"]
    dk = set(zip(delistings()["permno"], delistings()["when"].dt.to_period("M")))
    inside = sum(k in dk for k in zip(flagged["permno"], flagged["eom"].dt.to_period("M")))
    note(
        "pass" if inside == len(flagged) and flagged["MthRet"].notna().all() else "warn",
        "crsp_monthly",
        "months CRSP codes as delisting months carry a return (before 2021)",
        f"{inside:,} of {len(flagged):,} in one, {flagged['MthRet'].count():,} with a return",
    )


# The organisers' daily prices: keys, prices, returns and exits.
def daily(gone: pd.Series) -> None:
    src = "organisers dsf"
    path = DATA / "organisers" / "dsf_mini_from_2014.csv"
    d = pd.read_csv(path, usecols=["permno", "date", "prc", "daily_return"])
    d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d")
    zero(
        int(d.duplicated(["permno", "date"]).sum()),
        src,
        "duplicate (permno, date)",
        "fail",
        "dedupe",
    )
    zero(int((d["prc"] <= 0).sum()), src, "zero or negative prices", "warn", "use |prc|, null zero")
    zero(int((d["daily_return"] < -1).sum()), src, "returns below -100%", "fail", "null them")
    zero(int(np.isinf(d["prc"]).sum()), src, "infinite prices", "warn", "null them (6.2 rule)")
    zero(int(np.isinf(d["daily_return"]).sum()), src, "infinite returns", "fail", "null them")
    cover(src, d["date"], d["permno"])
    end = d.groupby("permno")["date"].max().reindex(gone.index)
    left = gone[gone < SEALED]
    end = end.reindex(left.index)
    short = int((end < left - pd.offsets.MonthBegin(1)).sum())
    zero(
        short,
        src,
        "exits before 2021 whose daily rows end over a month early",
        "warn",
        "check the daily file's coverage of dying firms",
        len(left),
    )


# The bundle: labels kept apart, filings dated, the v1 layers.
def bundle() -> None:
    src = "bundle"
    b = DATA / "fiam_v1"
    names = pq.read_schema(b / "features_monthly.parquet").names
    leak = [n for n in names if "lead" in n or n.startswith(("next_", "ret_exc"))]
    zero(len(leak), src, "label columns among the features", "fail", f"remove {leak}")
    labels = pd.read_parquet(b / "labels_monthly.parquet", columns=["permno", "eom"])
    zero(int(labels.duplicated().sum()), src, "duplicate label (permno, eom)", "fail", "dedupe")
    f = pd.read_parquet(b / "filings.parquet", columns=["permno", "filing_date"])
    t = pd.read_parquet(b / "filing_text.parquet", columns=["filing_date", "eom"])
    late = int((pd.to_datetime(t["filing_date"]) > pd.to_datetime(t["eom"])).sum())
    zero(late, src, "filing text counted in a month before it was filed", "fail", "re-date")
    cover("organisers 8-K", f["filing_date"], f["permno"])
    old = pq.read_schema(b / "wrds" / "crsp_monthly.parquet").names
    ahead = [c for c in old if c.endswith("EndDt") or c.startswith("Del")]
    note(
        "warn",
        src,
        "v1's wrds/crsp_monthly keeps end-date and delisting fields",
        ", ".join(ahead),
        "v4 reads data/v4/extracts only; add a test that v4 never reads fiam_v1/wrds",
    )
    short_lag(b)


# v1's short interest layer, filed under settlement with no lag.
def short_lag(b: Path) -> None:
    layer = pd.read_parquet(b / "short_interest_monthly_research_only.parquet")
    layer = layer.dropna(subset=["short_interest"])
    si = extract("short_interest", ["gvkey", "iid", "datadate", "shortint", "available_date"])
    si["eom"] = pd.to_datetime(si["datadate"]) + pd.offsets.MonthEnd(0)
    joined = layer.assign(eom=pd.to_datetime(layer["eom"])).merge(
        si,
        left_on=["gvkey", "iid", "eom", "short_interest"],
        right_on=["gvkey", "iid", "eom", "shortint"],
        how="inner",
    )
    after = int((pd.to_datetime(joined["available_date"]) > joined["eom"]).sum())
    note(
        "warn" if after else "pass",
        "bundle",
        "v1 short interest used at month end before it was public",
        f"{after:,} of {len(joined):,} matched rows",
        "known: research-only in v1-v3; v4 uses available_date",
    )


# CRSP monthly and daily: descriptions in force, returns, prices, keys.
def crsp() -> None:
    src = "crsp_monthly"
    cols = ["PERMNO", "MthCalDt", "SecInfoStartDt", "SecurityBegDt", "MthRet", "MthPrc"]
    m = extract("crsp_monthly", cols)
    day = pd.to_datetime(m["MthCalDt"])
    names = pq.read_schema(X / "crsp_monthly.parquet").names
    ahead = [c for c in names if c.endswith("EndDt") or c.startswith("Hdr") or "DelAction" in c]
    zero(len(ahead), src, "end-date or header fields present", "fail", f"drop {ahead}")
    future = int((pd.to_datetime(m["SecInfoStartDt"]) > day).sum())
    zero(future, src, "descriptions starting after the month", "fail", "keep the one in force")
    began = int((pd.to_datetime(m["SecurityBegDt"]) > day).sum())
    zero(began, src, "security begins after its own row", "warn", "check the begin date")
    zero(int(m.duplicated(["PERMNO", "MthCalDt"]).sum()), src, "duplicate keys", "fail", "dedupe")
    zero(int((m["MthRet"] < -1).sum()), src, "returns below -100%", "fail", "null them")
    zero(int((m["MthPrc"] <= 0).sum()), src, "zero or negative prices", "info", "")
    cover(src, m["MthCalDt"], m["PERMNO"])
    counts, bad, low, dup = {}, 0, 0, 0
    for path in sorted((X / "crsp_daily").glob("*.parquet")):
        d = pd.read_parquet(path, columns=["PERMNO", "DlyCalDt", "SecInfoStartDt", "DlyRet"])
        bad += int((pd.to_datetime(d["SecInfoStartDt"]) > pd.to_datetime(d["DlyCalDt"])).sum())
        low += int((d["DlyRet"] < -1).sum())
        dup += int(d.duplicated(["PERMNO", "DlyCalDt"]).sum())
        counts[int(path.stem)] = (len(d), int(d["PERMNO"].nunique()))
    cover_counts("crsp_daily", counts)
    zero(bad, "crsp_daily", "descriptions starting after the day", "fail", "keep the one in force")
    zero(low, "crsp_daily", "returns below -100%", "fail", "null them")
    zero(dup, "crsp_daily", "duplicate keys within a year", "fail", "dedupe")
    dl = delistings()
    real = dl[dl["delactiontype"].isin(["MER", "GDR", "GLI", "GEX"])]
    missing = real["delret"].isna().groupby(real["when"].dt.year).mean().round(3).to_dict()
    note(
        "info",
        "crsp_delistings",
        "share of delistings without a separate return, by year",
        json.dumps(missing),
    )
    cover("crsp_delistings", dl["when"], dl["permno"])


# Compustat: report dates, deletion fields, keys and fiscal changes.
def compustat() -> None:
    tables = (
        ("compustat_quarterly", "rdq"),
        ("compustat_annual", None),
        ("compustat_financials", None),
    )
    for name, report in tables:
        names = pq.read_schema(X / f"{name}.parquet").names
        later = [c for c in ("dldte", "dlrsn") if c in names]
        note(
            "warn",
            name,
            "the company's later deletion date and reason are still in the table",
            ", ".join(later),
            "drop dldte and dlrsn in the extract and rebuild (never a predictor)",
        )
        state = [c for c in ("upd", "final", "finalq") if c in names]
        note("info", name, "update-state fields present (never used)", ", ".join(state))
        cols = ["gvkey", "datadate", "datafmt", "indfmt", "consol"] + ([report] if report else [])
        c = extract(name, cols)
        keys = ["gvkey", "datadate", "datafmt", "indfmt", "consol"]
        zero(
            int(c.duplicated(keys).sum()),
            name,
            "same period under two fiscal calendars",
            "warn",
            "keep the row with the earliest report date",
        )
        cover(name, c["datadate"], c["gvkey"])
        if report:
            rdq, end = pd.to_datetime(c[report]), pd.to_datetime(c["datadate"])
            zero(
                int((rdq < end).sum()),
                name,
                "report date before period end",
                "warn",
                "treat as missing and use the fallback lag",
            )
            by_year = rdq.isna().groupby(end.dt.year).mean().round(3)
            note(
                "warn",
                name,
                "share without a report date, by year",
                json.dumps(by_year.to_dict()),
                "fallback: datadate plus 4 months (stated in the clock)",
            )
            note(
                "info",
                name,
                "reports over 180 days after period end",
                f"{int(((rdq - end).dt.days > 180).sum()):,}",
            )
        else:
            note(
                "warn",
                name,
                "annual rows carry no report date",
                f"{len(c):,} rows",
                "date by the fiscal Q4 rdq, else datadate plus 4 months",
            )


# I/B/E/S: copies, actuals out of the summary, actual dates, links.
def ibes() -> None:
    names = pq.read_schema(X / "ibes_summary.parquet").names
    later = [c for c in ("ACTUAL", "ANNDATS_ACT", "ANNTIMS_ACT") if c in names]
    zero(len(later), "ibes_summary", "actuals inside the consensus rows", "fail", f"drop {later}")
    tickers = pq.read_table(X / "ibes_summary.parquet", columns=["TICKER"]).column(0)
    sample = pc.unique(tickers).to_pylist()[::50]
    part = pq.read_table(X / "ibes_summary.parquet", filters=[("TICKER", "in", sample)]).to_pandas()
    keys = ["TICKER", "STATPERS", "MEASURE", "FISCALP", "FPI"]
    copies = int(part.duplicated().sum())
    other = int(part.drop_duplicates().duplicated(keys).sum())
    zero(
        copies,
        "ibes_summary",
        f"exact copies ({len(sample)} sampled tickers)",
        "warn",
        "drop exact copies in the extract",
        len(part),
    )
    zero(other, "ibes_summary", "keys repeated with different values (sample)", "fail", "check")
    cover("ibes_summary (sample)", part["STATPERS"], part["TICKER"])
    a = extract("ibes_actuals", ["TICKER", "MEASURE", "FISCALP", "PYEAR", "PMON", "anndats"])
    end = pd.to_datetime(dict(year=a["PYEAR"], month=a["PMON"], day=1), errors="coerce")
    early = int((pd.to_datetime(a["anndats"]) < end + pd.offsets.MonthEnd(0)).sum())
    zero(
        early,
        "ibes_actuals",
        "actual announced before its period ended",
        "warn",
        "drop them",
        len(a),
    )
    dup = int(a.duplicated(["TICKER", "MEASURE", "FISCALP", "PYEAR", "PMON"]).sum())
    zero(dup, "ibes_actuals", "duplicate keys", "warn", "keep the first announcement")
    for name in ("ibes_recommendations", "ibes_price_targets"):
        r = extract(name, ["TICKER", "STATPERS"])
        zero(int(r.duplicated().sum()), name, "duplicate (TICKER, STATPERS)", "fail", "dedupe")
        cover(name, r["STATPERS"], r["TICKER"])
    links("ibes_crsp_link", "TICKER", "PERMNO", "sdate", "edate", "SCORE")
    links("options_link", "secid", "PERMNO", "sdate", "edate", "score")


# A dated link table: windows in order, scores, one target at a time.
def links(name: str, key: str, target: str, start: str, end: str, score: str) -> None:
    t = extract(name, [key, target, start, end, score])
    s, e = pd.to_datetime(t[start]), pd.to_datetime(t[end])
    zero(int((s > e).sum()), name, "windows that end before they start", "fail", "drop")
    note("info", name, "rows by score", json.dumps(t[score].value_counts().sort_index().to_dict()))
    t = t.assign(s=s, e=e).sort_values([key, "s"])
    nxt = t.groupby(key)["s"].shift(-1)
    other = t.groupby(key)[target].shift(-1) != t[target]
    overlap = int(((nxt <= t["e"]) & other).sum())
    zero(
        overlap,
        name,
        "one id linked to two targets at once",
        "warn",
        "pick the best score inside each overlap",
    )


# Short interest: public 8 trading days after settlement, unique keys.
def short_interest() -> None:
    days = pd.DatetimeIndex(pd.to_datetime(extract("crsp_market_daily", ["dlycaldt"])["dlycaldt"]))
    for name in ("short_interest", "short_interest_legacy"):
        s = extract(name, ["gvkey", "iid", "datadate", "available_date"])
        # The current file is stock-lending demand, never used (A10).
        name = "short_interest_lending (unused)" if name == "short_interest" else name
        settle, ready = pd.to_datetime(s["datadate"]), pd.to_datetime(s["available_date"])
        inside = ready <= days[-1]
        gap = days.searchsorted(ready[inside]) - days.searchsorted(settle[inside], side="right") + 1
        zero(int((gap < 8).sum()), name, "public sooner than 8 trading days", "fail", "re-date")
        linked = s.dropna(subset=["gvkey"])
        zero(
            int(linked.duplicated(["gvkey", "iid", "datadate"]).sum()),
            name,
            "duplicate keys among linked rows",
            "fail",
            "dedupe",
        )
        note(
            "info",
            name,
            "rows with no company id (cannot link, never used)",
            f"{len(s) - len(linked):,} of {len(s):,}",
        )
        cover(name, linked["datadate"], linked["gvkey"])


# OptionMetrics and TAQ daily: keys, links, prices, late dates.
def options_and_taq() -> None:
    names = pq.read_schema(next((X / "options_daily").glob("*.parquet"))).names
    zero(
        len({"mdate", "wdate"} & set(names)),
        "options_daily",
        "mdate or wdate present",
        "fail",
        "drop",
    )
    counts, dup, shared, rows = {}, 0, 0, 0
    for path in sorted((X / "options_daily").glob("*.parquet")):
        o = pd.read_parquet(path, columns=["PERMNO", "secid", "date"])
        dup += int(o.duplicated(["PERMNO", "secid", "date"]).sum())
        shared += int(o.duplicated(["secid", "date"]).sum())
        rows += len(o)
        counts[int(path.stem)] = (len(o), int(o["secid"].nunique()))
    cover_counts("options_daily", counts)
    zero(dup, "options_daily", "duplicate (PERMNO, secid, date)", "fail", "dedupe")
    zero(shared, "options_daily", "one option id on two share classes", "info", "", rows)
    counts, dup, bad, wide = {}, 0, 0, 0
    keys = ["DATE", "SYM_ROOT", "SYM_SUFFIX"]
    for path in sorted((X / "taq_daily").glob("*.parquet")):
        t = pd.read_parquet(path, columns=[*keys, "CPrc", "QuotedSpread_Percent_tw"])
        dup += int(t.duplicated(keys).sum())
        bad += int((t["CPrc"] <= 0).sum())
        wide += int((t["QuotedSpread_Percent_tw"] < 0).sum())
        counts[int(path.stem)] = (len(t), int(t["SYM_ROOT"].nunique()))
    cover_counts("taq_daily", counts)
    zero(dup, "taq_daily", "duplicate (DATE, symbol)", "fail", "dedupe")
    zero(bad, "taq_daily", "zero or negative closing prices", "info", "null them")
    zero(wide, "taq_daily", "negative quoted spreads", "warn", "null them")
    many, rows = 0, 0
    link = pq.ParquetFile(X / "taq_link.parquet")
    for batch in link.iter_batches(1 << 21, columns=[*keys, "PERMNO"]):
        b = batch.to_pandas()
        many += int((b.groupby(keys)["PERMNO"].nunique() > 1).sum())
        rows += len(b)
    zero(many, "taq_link", "symbol-days linked to two PERMNOs", "warn", "pick by match level", rows)


# Restatements and ratios: their own dates (key developments unused).
def events_and_ratios() -> None:
    # Key developments are refused by the registry, so only noted here.
    note("info", "events", "key developments", "not used: removed from every use 2026-10-24")
    r = extract("restatements", ["company_fkey", "file_date", "res_end_date"])
    filed = pd.to_datetime(r["file_date"], errors="coerce")
    zero(int(filed.isna().sum()), "restatements", "rows without a file date", "warn", "drop")
    ahead = int((pd.to_datetime(r["res_end_date"], errors="coerce") > filed).sum())
    note("info", "restatements", "restated periods ending after the filing", f"{ahead:,}")
    cover("restatements", filed, r["company_fkey"])
    q = extract("wrds_ratios", ["permno", "gvkey", "public_date", "qdate", "adate"])
    public = pd.to_datetime(q["public_date"])
    zero(
        int((public < pd.to_datetime(q["qdate"])).sum()),
        "wrds_ratios",
        "public before the quarter's data date",
        "fail",
        "re-date",
    )
    zero(
        int(q.duplicated(["permno", "public_date"]).sum()),
        "wrds_ratios",
        "one PERMNO with two company ids on a date",
        "warn",
        "pick by the link table (step 3)",
    )
    cover("wrds_ratios", public, q["permno"])


# Daily and monthly market tables: one row per date.
def market() -> None:
    tables = {
        "ff_daily": "date",
        "ff_monthly": "dateff",
        "vix_daily": "date",
        "crsp_market_daily": "dlycaldt",
        "crsp_market_monthly": "mthcaldt",
        "frb_rates_daily": "date",
        "frb_fx_daily": "date",
    }
    for name, column in tables.items():
        t = extract(name, [column])
        zero(int(t.duplicated().sum()), name, "duplicate dates", "warn", "keep one row per date")
        cover(name, t[column])


# SEC filings, the CIK map and the downloaded documents.
def edgar(p: pd.DataFrame) -> None:
    f = pd.read_parquet(DATA / "edgar" / "filings.parquet")
    when = pd.to_datetime(f["accepted"], utc=True, errors="coerce")
    when = when.dt.tz_convert("America/New_York").dt.tz_localize(None)
    filed = pd.to_datetime(f["filing_date"])
    early = when.dt.normalize() < filed
    minutes = when.dt.hour * 60 + when.dt.minute
    normal = early & ((minutes >= 17 * 60 + 30) | (when.dt.dayofweek >= 5))
    note(
        "info",
        "edgar filings",
        "accepted after 17:30 or at a weekend, dated the next day",
        f"{int(normal.sum()):,} (SEC's rule)",
    )
    odd = int((early & ~normal).sum())
    zero(
        odd,
        "edgar filings",
        "accepted on a weekday before 17:30 but dated a later day",
        "warn",
        "available_at = the later of acceptance and the filing date's open",
        len(f),
    )
    zero(
        int((when.dt.normalize() > filed + pd.Timedelta(days=3)).sum()),
        "edgar filings",
        "accepted days after the filing date",
        "warn",
        "use the later date",
    )
    zero(
        int(f.duplicated(["cik", "accession"]).sum()),
        "edgar filings",
        "duplicate accessions per filer",
        "warn",
        "dedupe",
    )
    # A joint filing sits once under each of its filers, by design.
    joint = int(f.duplicated(["accession"]).sum())
    note("info", "edgar filings", "joint filings kept once per filer", f"{joint:,} copies")
    after = int((pd.to_datetime(f["report_date"], errors="coerce") > filed).sum())
    zero(after, "edgar filings", "report period after the filing date", "info", "")
    cover("edgar filings", filed, f["cik"])
    m = pd.read_parquet(DATA / "edgar" / "cik_map.parquet")
    conflicts = int(m["conflict"].fillna(False).astype(bool).sum())
    note("info", "edgar cik_map", "CIK conflicts to settle in the link table", f"{conflicts}")
    log = DATA / "edgar" / "docs" / "log.jsonl"
    saved = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    ciks = {int(e["path"].split("/")[1]) for e in saved if "path" in e}
    u = m[m["universe"].fillna(False).astype(bool)].dropna(subset=["cik"]).copy()
    u["doc"] = u["cik"].astype(int).isin(ciks)
    rate = u.groupby(u["left_panel"].fillna(False).astype(bool))["doc"].mean().round(3).to_dict()
    gap = (rate.get(False) or 0) - (rate.get(True) or 0)
    note(
        "warn" if gap > 0.10 else "pass",
        "edgar docs",
        "universe firms with documents: stayed vs left the panel",
        json.dumps({"stayed": rate.get(False), "left": rate.get(True)}),
        "a gap over 10 points means the text misses dying firms",
    )
    facts()
    thirteen_f()


# SEC as-filed facts, every 40th company: filed after its period.
def facts() -> None:
    early = total = missing = 0
    with zipfile.ZipFile(DATA / "edgar" / "companyfacts.zip") as zf:
        for name in zf.namelist()[::40]:
            body = json.loads(zf.read(name))
            for tags in body.get("facts", {}).values():
                for tag in tags.values():
                    for rows in tag.get("units", {}).values():
                        for row in rows:
                            total += 1
                            if "filed" not in row or "accn" not in row:
                                missing += 1
                            elif row["filed"] < row.get("end", ""):
                                early += 1
    zero(missing, "sec facts", "facts without a filing date or accession", "warn", "drop", total)
    zero(early, "sec facts", "facts filed before their period ended", "warn", "drop them", total)


# One member of a 13F zip, wherever the quarter's layout puts it.
def member(zf: zipfile.ZipFile, name: str) -> str:
    return next(n for n in zf.namelist() if n.upper().endswith(name))


# SEC 13F: filed after the quarter, value units, CUSIP matches.
def thirteen_f() -> None:
    cusips = set(extract("crsp_monthly", ["CUSIP"])["CUSIP"].dropna().str[:8])
    early, rows, out = 0, 0, {}
    for path in sorted((DATA / "edgar" / "13f").glob("*.zip")):
        with zipfile.ZipFile(path) as zf:
            sub = pd.read_csv(
                zf.open(member(zf, "SUBMISSION.TSV")),
                sep="\t",
                dtype=str,
                usecols=["FILING_DATE", "PERIODOFREPORT"],
            )
            info = pd.read_csv(
                zf.open(member(zf, "INFOTABLE.TSV")),
                sep="\t",
                dtype=str,
                usecols=["CUSIP", "VALUE", "SSHPRNAMT"],
            )
        filed = pd.to_datetime(sub["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
        period = pd.to_datetime(sub["PERIODOFREPORT"], format="%d-%b-%Y", errors="coerce")
        early += int((filed < period).sum())
        rows += len(info)
        shares = pd.to_numeric(info["SSHPRNAMT"], errors="coerce")
        price = pd.to_numeric(info["VALUE"], errors="coerce") / shares.where(shares > 0)
        median = float(price.median())
        # A quarter filed after 2020 keeps its unit class, never a level.
        sealed = filed.max() >= SEALED
        out[path.name.split("_form13f")[0]] = dict(
            last_filed=str(filed.max().date()),
            value_per_share=None if sealed else round(median, 4),
            units="thousands" if median < 0.5 else "dollars" if median > 2 else "unclear",
            cusip_match=round(float(info["CUSIP"].str[:8].isin(cusips).mean()), 3),
            rows=len(info),
        )
    zero(early, "sec 13f", "filed before the quarter ended", "fail", "drop")
    (OUT / "thirteen_f.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    # Quarters sorted by when they were filed, not by file name.
    split = pd.DataFrame(out.values()).assign(last_filed=lambda f: pd.to_datetime(f["last_filed"]))
    before = split.loc[split["last_filed"] < SEALED, "value_per_share"].median()
    late = split[split["last_filed"] >= "2023-01-03"]
    dollars = int((late["units"] == "dollars").sum())
    note(
        "warn",
        "sec 13f",
        "median VALUE per share before 2021; unit class from 2023-01-03",
        f"{before:.4f} (thousands); {dollars} of {len(late)} later quarters in dollars",
        "units decided per filing (protocol, step 6 13F rules)",
    )
    matches = [v["cusip_match"] for v in out.values()]
    note(
        "info",
        "sec 13f",
        "holdings rows; CUSIP match to CRSP, lowest and highest quarter",
        f"{rows:,} rows; {min(matches)} to {max(matches)} (see thirteen_f.json)",
    )


# NOAA: missing values and the storm files' revision date.
def noaa() -> None:
    sentinel = total = 0
    for path in sorted((DATA / "noaa" / "climdiv").glob("climdiv-*-v1.0.0-*")):
        values = pd.read_csv(path, sep=r"\s+", header=None, dtype=str).iloc[:, 1:]
        sentinel += int((values == "-99.90").sum().sum() + (values == "-9.99").sum().sum())
        total += values.size
    note("info", "noaa climdiv", "missing-value sentinels to null", f"{sentinel:,} of {total:,}")
    files = sorted((DATA / "noaa" / "storms").glob("StormEvents_details*.csv.gz"))
    revised = sorted({p.name.split("_c")[-1][:8] for p in files})
    note(
        "warn",
        "noaa storms",
        "files are this year's revision of every year",
        f"revised {revised}",
        "use event dates and counts only, never damage or narrative fields",
    )
    counts, bad = {}, 0
    for path in files:
        s = pd.read_csv(path, usecols=["BEGIN_YEARMONTH", "BEGIN_DAY"], dtype=str)
        counts[int(s["BEGIN_YEARMONTH"].str[:4].iloc[0])] = (len(s), None)
        stamp = s["BEGIN_YEARMONTH"] + s["BEGIN_DAY"].str.zfill(2)
        bad += int(pd.to_datetime(stamp, format="%Y%m%d", errors="coerce").isna().sum())
    zero(bad, "noaa storms", "events with an impossible begin date", "warn", "drop")
    cover_counts("noaa storms", counts)


# Carbon Arc: rows dated after the pull, and the labelled weekdays.
def carbon_arc() -> None:
    for receipt in sorted((DATA / "carbon_arc" / "snapshot_1").glob("*.receipt.json")):
        r = json.loads(receipt.read_text(encoding="utf-8"))
        name = receipt.name.removesuffix(".receipt.json")
        body = json.loads(gzip.open(receipt.with_name(f"{name}.json.gz")).read())
        rows = pd.DataFrame(body.get("data") or [])
        if rows.empty or "date" not in rows:
            note("info", "carbon arc", f"{name} has no dated rows", f"{len(rows):,} rows")
            continue
        date = pd.to_datetime(rows["date"], errors="coerce")
        pulled = pd.to_datetime(r["pulled_at"], utc=True).tz_localize(None)
        after = int((date > pulled).sum())
        zero(
            after,
            "carbon arc",
            f"{name} rows labelled after the pull (unfinished periods)",
            "warn",
            "use only periods that had closed before the pull",
            len(rows),
        )
        cover(f"carbon arc {name}", date, rows.get("entity_name"))


# Amazon: no snapshot fields, no month past the snapshot.
def amazon() -> None:
    banned = {"average_rating", "rating_number", "price"}
    found = sum(
        bool(banned & set(pq.read_schema(p).names))
        for p in (DATA / "amazon" / "items").glob("*.parquet")
    )
    zero(found, "amazon", "item files with snapshot fields", "fail", "drop them")
    counts, late = {}, 0
    for path in sorted((DATA / "amazon" / "product_month").glob("*.parquet")):
        m = pd.read_parquet(path, columns=["month", "reviews"])
        month = pd.to_datetime(m["month"])
        late += int((month > pd.Timestamp("2023-09-30")).sum())
        for year, n in m.groupby(month.dt.year)["reviews"].sum().items():
            rows, _ = counts.get(int(year), (0, None))
            counts[int(year)] = (rows + int(n), None)
    zero(late, "amazon", "months after the 2023-09 snapshot", "fail", "drop")
    cover_counts("amazon reviews", counts)


# Exiting firms covered as well as staying ones, per source (counts).
def survivorship(p: pd.DataFrame) -> None:
    keys = p[["permno", "gvkey", "iid", "eom"]].dropna(subset=["permno"]).copy()
    keys["permno"] = keys["permno"].astype("int64")
    final = keys["permno"].map(exits(p))
    keys["leaving"] = final.notna() & (keys["eom"] > final - pd.DateOffset(months=12))
    month, quarter = keys["eom"].dt.to_period("M"), keys["eom"].dt.to_period("Q")
    m = extract("crsp_monthly", ["PERMNO", "MthCalDt"])
    o = pd.concat(
        [
            pd.read_parquet(f, columns=["PERMNO", "date"]).dropna()
            for f in sorted((X / "options_daily").glob("*.parquet"))
        ]
    )
    q = extract("compustat_quarterly", ["gvkey", "rdq"]).dropna()
    s = extract("short_interest_legacy", ["gvkey", "iid", "datadate"]).dropna(subset=["gvkey"])
    have = {
        "crsp_monthly": set(
            zip(m["PERMNO"].astype("int64"), pd.to_datetime(m["MthCalDt"]).dt.to_period("M"))
        ),
        "options_daily": set(
            zip(o["PERMNO"].astype("int64"), pd.to_datetime(o["date"]).dt.to_period("M"))
        ),
        "compustat_quarterly": set(zip(q["gvkey"], pd.to_datetime(q["rdq"]).dt.to_period("Q"))),
        "short_interest": set(
            zip(s["gvkey"], s["iid"], pd.to_datetime(s["datadate"]).dt.to_period("M"))
        ),
    }
    asks = {
        "crsp_monthly": zip(keys["permno"], month),
        "options_daily": zip(keys["permno"], month),
        "compustat_quarterly": zip(keys["gvkey"], quarter),
        "short_interest": zip(keys["gvkey"], keys["iid"], month),
    }
    for source, pairs in asks.items():
        covered = pd.Series([pair in have[source] for pair in pairs], index=keys.index)
        early = keys["eom"] < SEALED
        table = covered[early].groupby(keys["leaving"][early]).mean().round(3)
        stayed, leaving = float(table.get(False, 0)), float(table.get(True, 0))
        level = "warn" if stayed - leaving > 0.10 else "pass"
        fix = "smaller dying firms have fewer listed options; missing is never a signal"
        note(
            level,
            source,
            "coverage before 2021: firms in their last 12 months vs the rest",
            f"leaving {leaving}, others {stayed}",
            fix if source == "options_daily" else "",
        )


# Cross-source agreement on 2015-2020 only: returns, size and exits.
def agreement(p: pd.DataFrame) -> None:
    early = p[p["eom"] < SEALED].dropna(subset=["permno"]).copy()
    early["permno"] = early["permno"].astype("int64")
    m = extract("crsp_monthly", ["PERMNO", "MthCalDt", "MthRet", "MthCap"])
    m = m.assign(
        permno=m["PERMNO"].astype("int64"),
        eom=pd.to_datetime(m["MthCalDt"]) + pd.offsets.MonthEnd(0),
    )
    j = early.merge(m[m["eom"] < SEALED], on=["permno", "eom"], how="inner")
    same = float(((j["ret"] - j["MthRet"]).abs() < 1e-4).mean())
    note(
        "pass" if same > 0.97 else "warn",
        "agreement",
        "panel ret vs CRSP MthRet, 2015-2020",
        f"{same:.3f} within 1bp over {len(j):,} rows",
    )
    scale = float((j["MthCap"] / j["me"]).median())
    close = float(((j["MthCap"] / scale / j["me"] - 1).abs() < 0.01).mean())
    note(
        "pass" if close > 0.95 else "warn",
        "agreement",
        "panel me vs CRSP MthCap, 2015-2020",
        f"{close:.3f} within 1% (CRSP in $ thousands, scale {scale:,.0f})",
    )
    gone = exits(p)
    gone = gone[gone < SEALED]
    first = delistings().groupby("permno")["when"].min().reindex(gone.index.astype("int64"))
    near = int(((first.to_numpy() - gone.to_numpy()) / np.timedelta64(1, "D") <= 62).sum())
    note(
        "pass" if near / len(gone) > 0.9 else "warn",
        "agreement",
        "panel exits before 2021 with a CRSP delisting within 2 months",
        f"{near:,} of {len(gone):,}",
    )


# The v4 link table: ordered periods, one value per stock at a time.
def v4_links() -> None:
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    s = pd.to_datetime(lk["valid_from"])
    e = pd.to_datetime(lk["valid_to"]).fillna(pd.Timestamp("2262-01-01"))
    zero(int((e < s).sum()), "v4 links", "periods that end before they start", "fail", "rebuild")
    t = lk.assign(s=s, e=e).sort_values(["kind", "permno", "s"])
    nxt = t.groupby(["kind", "permno"])["s"].shift(-1)
    two = t[nxt <= t["e"]].groupby("kind").size()
    for kind in sorted(t["kind"].unique()):
        level = (
            "warn" if kind in ("cusip", "ticker", "symbol", "gvkey", "gvkey_iid", "cik") else "info"
        )
        fix = "one period per stock and kind" if level == "warn" else ""
        zero(
            int(two.get(kind, 0)),
            "v4 links",
            f"{kind}: one stock with two values at once",
            level,
            fix,
        )
    report = json.loads((DATA / "v4" / "links.json").read_text(encoding="utf-8"))
    shares = {k: v["all"] for k, v in report["panel_coverage"].items()}
    note("info", "v4 links", "panel stock-months with each id", json.dumps(shares))


# The v4 exits: one row per stock, date and source, each stamped.
def v4_exits() -> None:
    ex = pd.read_parquet(CLEAN / "exits.parquet")
    dupes = int(ex.duplicated(["permno", "exit_date", "source"]).sum())
    zero(dupes, "v4 exits", "repeated stock, date and source", "fail", "dedupe", len(ex))
    zero(int(ex["available_at"].isna().sum()), "v4 exits", "no available_at", "fail", "stamp them")
    late = ex[ex["exit_date"] >= SEALED]
    note(
        "info",
        "v4 exits",
        "2021 on by group (counts)",
        json.dumps(late["group"].value_counts().to_dict()),
    )
    cover("v4 exits", ex["exit_date"], ex["permno"])


# Every clean table: no banned field, stamped, read at its first close.
def v4_clean() -> None:
    import pyarrow.dataset as ds

    from fiam.v4 import sources

    cal = sources.trading_calendar()
    close = pd.Series(pd.DatetimeIndex(cal).tz_localize(None).as_unit("ns"), index=cal.index)
    for name, source in sources.REGISTRY.items():
        path = CLEAN / name if name == "crsp_daily" else CLEAN / f"{name}.parquet"
        if not path.exists():
            note("info", f"v4 {name}", "not converted yet", "converted in its step")
            continue
        fields = set(ds.dataset(path).schema.names)
        hit = sorted(set(source.banned) & fields)
        zero(len(hit), f"v4 {name}", "banned fields present", "fail", f"drop {hit}")
        f = pd.read_parquet(path, columns=["available_at", "first_close"])
        stamp = pd.to_datetime(f["available_at"], utc=True).dt.tz_localize(None)
        sealed = int((stamp > sources.SEAL.tz_localize(None)).sum())
        note("info", f"v4 {name}", "rows public after 2020 (sealed, counts)", f"{sealed:,}")
        # Link periods and the bill rate carry no close by design (§6.3).
        if source.use in ("links", "benchmark"):
            note("info", f"v4 {name}", "no first close by design", source.use)
            continue
        # Rows with no stamp, or public outside the calendar, are never read.
        market = source.clock in ("market", "eom", "month_end")
        last = (stamp > close.iloc[-1]) if market else (stamp >= close.iloc[-1])
        outside = (stamp < close.iloc[0]) | last
        never = int((stamp.isna() | outside).sum())
        note(
            "info",
            f"v4 {name}",
            "rows never readable (no stamp, or off the calendar)",
            f"{never:,}",
        )
        inside = stamp.notna() & ~outside
        lost = int((inside & f["first_close"].isna()).sum())
        zero(lost, f"v4 {name}", "rows public in range but no first close", "fail", "re-date")
        session = pd.DatetimeIndex(f["first_close"]).as_unit("ns")
        at = close.reindex(session).to_numpy()
        prev = close.shift(1).reindex(session).to_numpy()
        ok = inside.to_numpy() & ~pd.isna(at)
        off = int((f["first_close"].notna() & pd.isna(at)).sum())
        zero(off, f"v4 {name}", "first close not a session", "fail", "use the calendar")
        # Market data joins at that day's close; events at the next one.
        if market:
            wrong = int((ok & (at != stamp.to_numpy())).sum())
            zero(wrong, f"v4 {name}", "not at its own day's close", "fail", "re-date", len(f))
            continue
        early = int((ok & (at <= stamp.to_numpy())).sum())
        zero(early, f"v4 {name}", "first close not after the stamp", "fail", "re-date", len(f))
        skipped = int((ok & ~pd.isna(prev) & (prev > stamp.to_numpy())).sum())
        zero(skipped, f"v4 {name}", "an earlier close after the stamp", "fail", "re-date")


# v4 short interest: one source a date, public 8 sessions on (A10).
def v4_short_interest() -> None:
    from fiam.v4 import sources

    days = pd.DatetimeIndex(sources.trading_calendar().index)
    s = pd.read_parquet(CLEAN / "short_interest.parquet")
    zero(
        int(s.duplicated(["permno", "settlement"]).sum()),
        "v4 short interest",
        "repeated stock and settlement",
        "fail",
        "dedupe",
    )
    both = s.groupby("settlement")["source"].nunique()
    zero(int((both > 1).sum()), "v4 short interest", "dates from two sources", "fail", "one source")
    # Settlement and first close as session positions; NaT is never read.
    read = s.dropna(subset=["first_close"])
    gap = days.searchsorted(read["first_close"]) - days.searchsorted(read["settlement"])
    zero(
        int((gap < 9).sum()), "v4 short interest", "read before 8 full sessions", "fail", "re-date"
    )
    note("info", "v4 short interest", "never read (no first close)", f"{len(s) - len(read):,}")
    mix = s.groupby([s["settlement"].dt.year, "source"]).size().unstack(fill_value=0)
    note("info", "v4 short interest", "rows by source (counts)", json.dumps(mix.sum().to_dict()))
    banned = sorted({"shortintadj", "splitadjdate"} & set(s.columns))
    zero(len(banned), "v4 short interest", "adjusted fields present", "fail", "drop")
    cover("v4 short interest", s["settlement"], s["permno"])


# FINRA's files: one row per symbol and date, on sessions, sane sizes.
def finra() -> None:
    from fiam.v4 import sources

    sessions = pd.DatetimeIndex(sources.trading_calendar().index)
    days, last = set(sessions), sessions.max()
    si = pd.read_parquet(DATA / "finra" / "short_interest.parquet")
    dupes = int(si.duplicated(["symbol", "settlement"]).sum())
    zero(dupes, "finra short interest", "repeated symbol and settlement", "fail", "dedupe")
    off = int((~si["settlement"].isin(days) & (si["settlement"] <= last)).sum())
    zero(off, "finra short interest", "settlements off the calendar", "warn", "check the date")
    zero(int((si["short"] < 0).sum()), "finra short interest", "negative positions", "fail", "drop")
    note(
        "info",
        "finra short interest",
        "rows flagged revised (left out)",
        f"{(si['revision'] == 'R').sum():,}",
    )
    cover("finra short interest", si["settlement"], si["symbol"])
    v = pd.read_parquet(DATA / "finra" / "volume.parquet")
    zero(
        int(v.duplicated(["symbol", "date"]).sum()),
        "finra volume",
        "repeated symbol and date",
        "fail",
        "dedupe",
    )
    zero(
        int((~v["date"].isin(days) & (v["date"] <= last)).sum()),
        "finra volume",
        "days off the calendar",
        "warn",
        "check",
    )
    over = int((v["short_volume"] > v["total_volume"]).sum())
    zero(over, "finra volume", "short volume above total volume", "warn", "check the file")
    note("info", "finra volume", "not used: failed its 2015-2020 check (§6.5)", f"{len(v):,} rows")


# Every card's input hashes against the files on disk (final audit 11).
def v4_cards() -> None:
    import hashlib

    stale = 0
    for card in sorted((DATA / "v4" / "cards").glob("*.json")):
        raw = json.loads(card.read_text()).get("raw")
        if not isinstance(raw, dict):
            continue
        for rel, digest in raw.items():
            path = DATA / rel
            if not path.exists():
                continue
            h = hashlib.sha256()
            with path.open("rb") as fh:
                for block in iter(lambda: fh.read(1 << 24), b""):
                    h.update(block)
            if h.hexdigest() != digest:
                stale += 1
                note(
                    "warn", f"card {card.stem}", "input changed since conversion", rel, "reconvert"
                )
    zero(stale, "v4 cards", "input hashes that differ from the disk", "warn", "reconvert")


# Merge rule 1: per source, Apple's observation date beside its entry.
def merge_rule1() -> None:
    from fiam.v4 import sources

    rows = []
    for name, source in sources.REGISTRY.items():
        if source.ids != "permno" or source.use == "links":
            continue
        path = CLEAN / (name if name in sources.FOLDERS else f"{name}.parquet")
        if not path.exists():
            continue
        import pyarrow.dataset as ds

        table = ds.dataset(path)
        cols = [c for c in table.schema.names if c in (*source.key, "available_at", "first_close")]
        frame = table.to_table(columns=cols, filter=ds.field("permno") == 14593).to_pandas()
        stamp = pd.to_datetime(frame["available_at"], utc=True)
        frame = frame[(stamp >= "2018-06-01") & (stamp < "2018-07-01")]
        if frame.empty:
            continue
        first = frame.sort_values("available_at").iloc[0]
        seen = {k: str(first[k]) for k in source.key if k != "permno"}
        rows.append(f"| {name} | {seen} | {first['available_at']} | {first['first_close']} |")
    head = "| Source | Observation (Apple, June 2018) | Public at | Enters at close of |\n"
    head += "|---|---|---|---|"
    (OUT / "merge_rule1.md").write_text(head + "\n" + "\n".join(rows) + "\n")
    note(
        "info",
        "merge rule 1",
        "observation beside entry date, Apple June 2018",
        f"{len(rows)} sources",
    )


# Writes the findings, the coverage table and a short report.
def write() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ranked = sorted(FINDINGS, key=lambda f: LEVELS.index(f["level"]))
    (OUT / "findings.json").write_text(json.dumps(ranked, indent=1), encoding="utf-8")
    pd.DataFrame(COVERAGE).to_csv(OUT / "coverage.csv", index=False)
    counts = {level: sum(f["level"] == level for f in FINDINGS) for level in LEVELS}
    lines = ["# Data audit", "", f"Results: {counts}", ""]
    for f in ranked:
        fix = f" Fix: {f['fix']}" if f["fix"] and f["level"] in ("fail", "warn") else ""
        lines.append(f"- **{f['level']}** {f['source']}: {f['check']}: {f['evidence']}.{fix}")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Audit: {counts}; written to {OUT}")


# Runs every check in turn; one failing check never stops the rest.
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    p = panel()
    checks = {
        "organisers": lambda: organisers(p),
        "bundle": bundle,
        "crsp": crsp,
        "compustat": compustat,
        "ibes": ibes,
        "short_interest": short_interest,
        "options_and_taq": options_and_taq,
        "events_and_ratios": events_and_ratios,
        "market": market,
        "edgar": lambda: edgar(p),
        "noaa": noaa,
        "carbon_arc": carbon_arc,
        "amazon": amazon,
        "survivorship": lambda: survivorship(p),
        "agreement": lambda: agreement(p),
        "v4_links": v4_links,
        "v4_exits": v4_exits,
        "v4_clean": v4_clean,
        "v4_short_interest": v4_short_interest,
        "finra": finra,
        "v4_cards": v4_cards,
        "merge_rule1": merge_rule1,
    }
    for name, check in checks.items():
        try:
            check()
        except Exception as err:  # noqa: BLE001
            note(
                "fail",
                "audit",
                f"the {name} check could not run",
                repr(err)[:300],
                "fix the audit, then rerun",
            )
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
