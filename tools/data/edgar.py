# SEC EDGAR downloads, with the contact SEC asks for, and receipts.

import gzip
import hashlib
import io
import json
import re
import sys
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from _shared import ROOT, check, data_root, fingerprint, listed, receipts, setting, stamp

# One name key for both builders, kept in the link module only.
sys.path.insert(0, str(ROOT))
from fiam.vfinal.links import entity_key  # noqa: E402

OUT = ROOT / "data" / "edgar"
BULK = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
# SEC rebuilds it nightly, so it stays on the Mac with its hash kept.
HOME_ONLY = {"submissions.zip"}
FACTS = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
F13 = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
F13_FILES = r"/files/[^\"]+_form13f\.zip"
INSIDER_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
# SEC files recent quarters under another folder, so any folder counts.
INSIDER_FILES = r"/files/[^\"]+/insider-transactions-data-sets/\d{4}q\d_form345\.zip"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
USAGE = (
    "uv run run.py --data edgar bulk | facts | 13f | insiders | map | filings | forms | docs"
    " | verify [--deep] | relog | names"
)
EIGHT_K = "8k_20150101_20260831_identified.parquet"
# Annual reports for Lazy Prices, and the 8-K items that are red flags.
ANNUAL = {"10-K", "10-K405", "10-KT", "10-KSB"}
FLAGS = {"1.03", "2.06", "3.01", "4.01", "4.02", "5.02"}
START = "2012-01-01"
# Exits, insider trades and share offerings, indexed from 2006 on.
EXITS = {"25", "25-NSE", "15-12B", "15-12G", "15-15D"}
INSIDERS = {"4", "4/A"}
OFFERINGS = {"424B1", "424B2", "424B3", "424B4", "424B5", "S-1", "S-3"}
# A new filer taking over listed shares, the CIK decisions' dates.
SUCCESSION = {"8-K12B", "8-K12G3", "8-A12B"}
FORMS_START = "2006-01-01"
# The gap between requests across threads; SEC allows ten a second.
PACE, WORKERS = 0.2, 4
GATE = {"next": 0.0, "lock": threading.Lock()}


# The organisers' finals files, always in the data folder.
def organisers() -> Path:
    return ROOT / "data" / "organisers"


# Our data bundle: data/fiam_v1 unless FIAM_DATA_DIR points elsewhere.
def bundle() -> Path:
    return Path(setting("FIAM_DATA_DIR", str(ROOT / "data" / "fiam_v1")))


# Waits for this thread's turn, so all threads together stay under PACE.
def turn() -> None:
    with GATE["lock"]:
        now = time.monotonic()
        slot = max(GATE["next"], now)
        GATE["next"] = slot + PACE
    time.sleep(slot - now)


# One SEC request with the contact header, retried when SEC is busy.
def fetch(url: str, headers: dict | None = None) -> bytes:
    who = setting("SEC_CONTACT")
    base = {"User-Agent": f"FIAM research {who}", "Accept-Encoding": "identity"}
    for wait in (0, 10, 30, 90):
        time.sleep(wait)
        turn()
        try:
            request = urllib.request.Request(url, headers=base | (headers or {}))
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise
            last = err
        except OSError as err:
            last = err
    raise last


# One large SEC zip, resumed only if the server's copy is unchanged.
def download(url: str, name: str) -> int:
    if not setting("SEC_CONTACT"):
        print("Set SEC_CONTACT in .env to an email SEC can reach.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    final, part, stamp = OUT / name, OUT / f"{name}.part", OUT / f"{name}.part.stamp"
    have = part.stat().st_size if part.exists() and stamp.exists() else 0
    headers = {"User-Agent": f"FIAM research {setting('SEC_CONTACT')}"}
    headers["Accept-Encoding"] = "identity"
    if have:
        headers |= {"Range": f"bytes={have}-", "If-Range": stamp.read_text()}
    turn()
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as err:
        # A finished part never renamed: fetch it again.
        if err.code != 416:
            raise
        part.unlink()
        stamp.unlink()
        return download(url, name)
    with response:
        # A full reply to a range request means the file changed.
        if response.status == 200:
            have = 0
        modified = response.headers.get("Last-Modified", "")
        stamp.write_text(modified)
        size = have + int(response.headers.get("Content-Length", 0))
        with part.open("ab" if have else "wb") as fh:
            while chunk := response.read(1 << 20):
                fh.write(chunk)
                have += len(chunk)
                if have % (200 << 20) < (1 << 20):
                    print(f"{have >> 20} of {size >> 20} MB", flush=True)
    if have != size:
        print(f"{name} stopped at {have} of {size} bytes; rerun to resume.")
        return 1
    try:
        with zipfile.ZipFile(part) as zf:
            broken = zf.testzip()
    except zipfile.BadZipFile as err:
        broken = str(err)
    if broken:
        print(f"{name} failed its zip check ({broken}); rerun to fetch it again.")
        part.unlink()
        stamp.unlink()
        return 1
    part.replace(final)
    stamp.unlink()
    digest = fingerprint(final)
    receipt = {"url": url, "bytes": final.stat().st_size, "sha256": digest}
    receipt |= {"last_modified": modified, "pulled_at": stamp()}
    (OUT / "receipts").mkdir(exist_ok=True)
    (OUT / "receipts" / f"{name}.json").write_text(json.dumps(receipt, indent=1))
    print(f"Saved {final} ({receipt['bytes'] >> 20} MB), SHA-256 {digest[:16]}...")
    return 0


# Every filer's history in one file.
def bulk() -> int:
    return download(BULK, "submissions.zip")


# Every company's XBRL numbers, each with the filing that reported it.
def facts() -> int:
    return download(FACTS, "companyfacts.zip")


# Every data set an SEC page lists, each zip checked and receipted.
def data_sets(page_url: str, pattern: str, folder: Path) -> int:
    links = listed(fetch(page_url).decode("utf-8", "replace"), pattern)
    folder.mkdir(parents=True, exist_ok=True)
    book = folder / "receipts.json"
    saved = receipts(book)
    print(f"{len(links)} data sets listed", flush=True)
    for n, link in enumerate(links, 1):
        name = link.rsplit("/", 1)[1]
        if name in saved and (folder / name).exists():
            continue
        body = fetch("https://www.sec.gov" + link)
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            if zf.testzip():
                print(f"{name} failed its zip check; rerun to retry.")
                continue
        part = folder / f"{name}.part"
        part.write_bytes(body)
        part.replace(folder / name)
        saved[name] = {"url": "https://www.sec.gov" + link, "bytes": len(body)}
        saved[name] |= {"sha256": hashlib.sha256(body).hexdigest(), "pulled_at": stamp()}
        book.write_text(json.dumps(saved, indent=1))
        print(f"{n} of {len(links)} {name} ({len(body) >> 20} MB)", flush=True)
    missing = [link for link in links if link.rsplit("/", 1)[1] not in saved]
    print(f"Done: {len(saved)} of {len(links)} saved, {len(missing)} missing, in {folder}")
    return 1 if missing else 0


# Every 13F data set the SEC lists.
def thirteen_f() -> int:
    return data_sets(F13, F13_FILES, OUT / "13f")


# The Forms 3, 4 and 5 data sets from 2006q1.
def insiders() -> int:
    return data_sets(INSIDER_PAGE, INSIDER_FILES, OUT / "insiders")


# Each panel stock's SEC id, from Compustat or else the 8-K file.
def link() -> int:
    chars = pd.read_parquet(
        organisers() / "chars_final_with_names.parquet",
        columns=["permno", "gvkey", "eom", "me", "ticker", "company_name"],
    )
    chars["eom"] = pd.to_datetime(chars["eom"])
    firms = (
        chars.sort_values("eom")
        .groupby("permno")
        .agg(
            gvkey=("gvkey", "last"),
            first=("eom", "first"),
            last=("eom", "last"),
            me_max=("me", "max"),
            ticker=("ticker", "last"),
            name=("company_name", "last"),
        )
    )
    # The raw WRDS extract, never the bundle's copy; the values match.
    comp = pd.read_parquet(ROOT / "data" / "v4" / "extracts" / "compustat_quarterly.parquet")
    comp = comp[["gvkey", "datadate", "cik"]].dropna(subset=["cik"]).sort_values("datadate")
    by_gvkey = comp.groupby("gvkey")["cik"].last()
    filed = pd.read_parquet(organisers() / EIGHT_K, columns=["permno", "cik"]).dropna()
    by_permno = filed.groupby("permno")["cik"].agg(lambda s: s.mode().iat[0])
    as_int = lambda s: pd.to_numeric(s, errors="coerce").astype("Int64")  # noqa: E731
    firms["cik_compustat"] = as_int(firms["gvkey"].map(by_gvkey))
    firms["cik_8k"] = as_int(pd.Series(firms.index.map(by_permno), index=firms.index))
    firms["cik"] = firms["cik_compustat"].fillna(firms["cik_8k"])
    firms["source"] = "none"
    firms.loc[firms["cik_8k"].notna(), "source"] = "8-K file"
    firms.loc[firms["cik_compustat"].notna(), "source"] = "Compustat"
    both = firms["cik_compustat"].notna() & firms["cik_8k"].notna()
    firms["conflict"] = both & (firms["cik_compustat"] != firms["cik_8k"])
    firms["universe"] = firms["me_max"] >= 750
    firms["left_panel"] = firms["last"] < firms["last"].max()
    OUT.mkdir(parents=True, exist_ok=True)
    firms.reset_index().to_parquet(OUT / "cik_map.parquet", index=False)
    report = {"stocks": len(firms), "with_cik": int(firms["cik"].notna().sum())}
    for name in ("left_panel", "universe"):
        rows = firms[name]
        found = int(firms.loc[rows, "cik"].notna().sum())
        report[f"{name}_with_cik"] = f"{found} of {int(rows.sum())}"
    report["sources"] = firms["source"].value_counts().to_dict()
    report["conflicts"] = int(firms["conflict"].sum())
    (OUT / "cik_map.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    candidates(firms)
    return 0


# Every filer's names with their dates, from the bulk file's headers.
def names() -> int:
    rows, firsts = [], []
    with zipfile.ZipFile(OUT / "submissions.zip") as zf:
        for member in zf.namelist():
            if not re.fullmatch(r"CIK\d{10}\.json", member):
                continue
            d = json.loads(zf.read(member))
            former = d.get("formerNames") or []
            former = sorted(former, key=lambda f: (f.get("to") or "", f.get("from") or ""))
            ends = [pd.Timestamp(f["to"][:10]) for f in former if f.get("to")]
            starts = [(f.get("from") or "")[:10] for f in former]
            prev = ""
            for i, f in enumerate(former):
                stop = (f.get("to") or "")[:10]
                # The oldest name runs from the start; a gap keeps this one live.
                start = "" if i == 0 else starts[i] or prev
                later = starts[i + 1] if i + 1 < len(former) else ""
                stop = max(stop, later) if stop and later else stop
                rows.append((int(d["cik"]), f["name"], start, stop))
                prev = stop or prev
            start = max(ends).strftime("%Y-%m-%d") if ends else ""
            rows.append((int(d["cik"]), d.get("name", ""), start, ""))
            # The filer's first SEC filing, over every page of its history.
            recent = d["filings"]["recent"].get("filingDate", [])
            pages = [f.get("filingFrom", "") for f in d["filings"].get("files", [])]
            dates = [x for x in [*recent, *pages] if x]
            firsts.append((int(d["cik"]), min(dates) if dates else ""))
    table = pd.DataFrame(rows, columns=["cik", "name", "valid_from", "valid_to"])
    for col in ("valid_from", "valid_to"):
        table[col] = pd.to_datetime(table[col], errors="coerce")
    table.to_parquet(OUT / "cik_names.parquet", index=False)
    first = pd.DataFrame(firsts, columns=["cik", "first_filing"])
    first["first_filing"] = pd.to_datetime(first["first_filing"], errors="coerce")
    first.to_parquet(OUT / "cik_first_filing.parquet", index=False)
    print(f"{table['cik'].nunique():,} filers, {len(table):,} dated names")
    return 0


# Candidate SEC ids per stock from 2006: header, 8-K pairs, dated names.
def candidates(firms: pd.DataFrame) -> pd.DataFrame:
    cols = ["PERMNO", "MthCalDt", "MthCap", "ShareType", "SecurityType", "PrimaryExch", "IssuerNm"]
    crsp = pd.read_parquet(ROOT / "data" / "v4" / "extracts" / "crsp_monthly.parquet", columns=cols)
    crsp["permno"] = pd.to_numeric(crsp["PERMNO"]).astype("int64")
    crsp["date"] = pd.to_datetime(crsp["MthCalDt"])
    common = (crsp["ShareType"] == "NS") & (crsp["SecurityType"] == "EQTY")
    common &= crsp["PrimaryExch"].isin(["N", "A", "Q"])
    early = crsp["date"].between("2006-01-01", "2014-12-31") & (crsp["MthCap"] >= 600_000)
    stocks = set(firms.index) | set(crsp.loc[common & early, "permno"])
    rows = []
    lk = pd.read_parquet(ROOT / "data" / "v4" / "links.parquet")
    gv = lk[(lk["kind"] == "gvkey") & lk["permno"].isin(stocks)][["permno", "value"]]
    comp = pd.read_parquet(ROOT / "data" / "v4" / "extracts" / "compustat_quarterly.parquet")
    comp = comp[["gvkey", "datadate", "cik"]].dropna(subset=["cik"]).sort_values("datadate")
    header = comp.groupby("gvkey")["cik"].last()
    for r in gv.drop_duplicates().itertuples():
        if r.value in header.index:
            rows.append((r.permno, int(pd.to_numeric(header[r.value])), "compustat_header"))
    filed = pd.read_parquet(organisers() / EIGHT_K, columns=["permno", "cik"]).dropna()
    for r in filed.drop_duplicates().itertuples():
        rows.append((int(r.permno), int(pd.to_numeric(r.cik)), "organisers_8k_pairs"))
    # A dated EDGAR name equal to the stock's CRSP name of that time.
    names = pd.read_parquet(OUT / "cik_names.parquet")
    names["key"] = names["name"].map(entity_key)
    mine = (
        crsp[crsp["permno"].isin(stocks)]
        .groupby(["permno", "IssuerNm"])["date"]
        .agg(["min", "max"])
    )
    mine = mine.reset_index().assign(key=lambda d: d["IssuerNm"].map(entity_key))
    both = mine.merge(names, on="key")
    lo = both["valid_from"].fillna(pd.Timestamp("1900-01-01"))
    hi = both["valid_to"].fillna(pd.Timestamp("2100-01-01"))
    near = (lo <= both["max"] + pd.Timedelta(days=365)) & (
        hi >= both["min"] - pd.Timedelta(days=365)
    )
    both = both[near & (both["key"] != "")]
    # A name over 3 filers share keeps those that filed in the stock's life.
    width = both.groupby(["permno", "IssuerNm"])["cik"].transform("nunique")
    wide = both[width > 3][["permno", "IssuerNm", "cik", "min", "max"]].drop_duplicates()
    busy = filing_counts(wide)
    busy = busy[busy["filings"] > 0]
    for r in pd.concat([both[width <= 3], busy]).itertuples():
        rows.append((r.permno, int(r.cik), "name"))
    out = pd.DataFrame(rows, columns=["permno", "cik", "source"]).drop_duplicates()
    out.to_parquet(OUT / "cik_candidates.parquet", index=False)
    print(f"{out['permno'].nunique():,} stocks, {out['cik'].nunique():,} candidate filers")
    return out


# Each candidate's filings in its stock's life, from the bulk file.
def filing_counts(pairs: pd.DataFrame) -> pd.DataFrame:
    both = pairs.merge(submission_dates(sorted(pairs["cik"].unique())), on="cik")
    lo, hi = both["min"] - pd.Timedelta(days=365), both["max"] + pd.Timedelta(days=365)
    inside = (both["filing_date"] >= lo) & (both["filing_date"] <= hi)
    counts = both[inside].groupby(["permno", "IssuerNm", "cik"]).size().rename("filings")
    keys = ["permno", "IssuerNm", "cik"]
    out = pairs.merge(counts.reset_index(), on=keys, how="left")
    return out.fillna({"filings": 0})


# Filing dates per filer from the bulk file, every page of each filer.
def submission_dates(ciks: list[int]) -> pd.DataFrame:
    rows = []
    with zipfile.ZipFile(OUT / "submissions.zip") as zf:
        names = set(zf.namelist())
        for cik in ciks:
            main = f"CIK{cik:010d}.json"
            if main not in names:
                continue
            doc = json.loads(zf.read(main))
            pages = [doc["filings"]["recent"]]
            for extra in doc["filings"].get("files", []):
                if extra["name"] in names:
                    pages.append(json.loads(zf.read(extra["name"])))
            for page in pages:
                rows += [(cik, d) for d in page.get("filingDate", [])]
    out = pd.DataFrame(rows, columns=["cik", "filing_date"])
    out["filing_date"] = pd.to_datetime(out["filing_date"], errors="coerce")
    return out


# Every SEC id a panel stock may file under, from both sources.
def panel_ciks(firms: pd.DataFrame) -> list[int]:
    found = pd.concat([firms[c] for c in ("cik", "cik_compustat", "cik_8k") if c in firms])
    more = OUT / "cik_candidates.parquet"
    if more.exists():
        found = pd.concat([found, pd.read_parquet(more)["cik"]])
    # Every filer the saved CIK decisions name is indexed too.
    path = OUT.parent / "v4" / "cik_decisions.json"
    chosen = json.loads(path.read_text())["stocks"] if path.exists() else {}
    decided = [link[0] for entry in chosen.values() for link in entry["links"]]
    found = pd.concat([found, pd.Series(decided, dtype="float64")])
    return sorted(int(c) for c in found.dropna().unique())


# Each filing of the wanted forms since a date, from the bulk file.
def index(ciks: list[int], wanted, since: str) -> tuple[list[dict], list[int]]:
    rows, missing = [], []
    with zipfile.ZipFile(OUT / "submissions.zip") as zf:
        names = set(zf.namelist())
        for cik in ciks:
            main = f"CIK{cik:010d}.json"
            if main not in names:
                missing.append(cik)
                continue
            doc = json.loads(zf.read(main))
            pages = [doc["filings"]["recent"]]
            for extra in doc["filings"].get("files", []):
                if extra["name"] in names:
                    pages.append(json.loads(zf.read(extra["name"])))
            for page in pages:
                count = len(page.get("accessionNumber", []))
                for i in range(count):
                    form, date = page["form"][i], page["filingDate"][i]
                    if date < since or not wanted(form):
                        continue
                    rows.append(
                        {
                            "cik": cik,
                            "edgar_name": doc.get("name", ""),
                            "form": form,
                            "accession": page["accessionNumber"][i],
                            "filing_date": date,
                            "report_date": (page.get("reportDate") or [""] * count)[i],
                            "accepted": page["acceptanceDateTime"][i],
                            "items": (page.get("items") or [""] * count)[i],
                            "document": page["primaryDocument"][i],
                        }
                    )
    return rows, missing


# Our firms' annual reports and 8-Ks since 2012, from the bulk file.
def filings() -> int:
    ciks = panel_ciks(pd.read_parquet(OUT / "cik_map.parquet"))
    rows, missing = index(ciks, lambda form: form in ANNUAL or form == "8-K", START)
    # A joint filing stays once per filer, so a parent keeps its own copy.
    table = pd.DataFrame(rows).drop_duplicates(["cik", "accession"])
    table["red_flag"] = table["items"].fillna("").map(lambda s: bool(FLAGS & set(s.split(","))))
    table.to_parquet(OUT / "filings.parquet", index=False)
    report = {"filers": len(ciks), "not_in_bulk": len(missing), "filings": len(table)}
    report["annual_reports"] = int(table["form"].isin(ANNUAL).sum())
    report["eight_k"] = int((table["form"] == "8-K").sum())
    report["red_flag_8k"] = int(table["red_flag"].sum())
    (OUT / "filings.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


# Exit, insider and offering forms since 2006, for exits and the clock.
def forms() -> int:
    ciks = panel_ciks(pd.read_parquet(OUT / "cik_map.parquet"))
    wanted = EXITS | INSIDERS | OFFERINGS | SUCCESSION
    rows, missing = index(ciks, lambda form: form in wanted, FORMS_START)
    # A joint filing stays once per filer, as in the filings index.
    table = pd.DataFrame(rows).drop_duplicates(["cik", "accession"])
    groups = {"exit": EXITS, "insider": INSIDERS, "succession": SUCCESSION, "offering": OFFERINGS}
    kinds = {form: kind for kind, members in groups.items() for form in members}
    table["kind"] = table["form"].map(kinds)
    table.to_parquet(OUT / "forms.parquet", index=False)
    report = {"filers": len(ciks), "not_in_bulk": len(missing), "filings": len(table)}
    report["by_kind"] = table["kind"].value_counts().to_dict()
    report["by_form"] = table["form"].value_counts().to_dict()
    report["first"], report["last"] = table["filing_date"].min(), table["filing_date"].max()
    (OUT / "forms.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


# Every panel firm's annual reports and red-flag 8-Ks, gzipped.
def docs() -> int:
    table = pd.read_parquet(OUT / "filings.parquet")
    pick = table["form"].isin(ANNUAL) | ((table["form"] == "8-K") & table["red_flag"])
    want = table[pick & (table["document"] != "")].copy()
    # Only filers linked to a stock, inside the link's dates.
    lk = pd.read_parquet(ROOT / "data" / "v4" / "links.parquet")
    lk = lk[lk["kind"] == "cik"].assign(cik=lambda d: pd.to_numeric(d["value"]).astype("int64"))
    when = pd.to_datetime(want["filing_date"])
    both = want.assign(when=when).merge(lk[["cik", "valid_from", "valid_to"]], on="cik")
    inside = both["when"] >= both["valid_from"] - pd.Timedelta(days=90)
    inside &= both["valid_to"].isna() | (both["when"] <= both["valid_to"] + pd.Timedelta(days=365))
    linked = both.loc[inside, ["cik", "accession"]].drop_duplicates()
    want = want.merge(linked, on=["cik", "accession"]).copy()
    # Annual reports first, strong red flags next, officer changes last.
    strong = want["items"].fillna("").map(lambda s: bool((FLAGS - {"5.02"}) & set(s.split(","))))
    want["order"] = 2
    want.loc[strong, "order"] = 1
    want.loc[want["form"].isin(ANNUAL), "order"] = 0
    want = want.sort_values(["order", "filing_date"], kind="stable")
    folder, log = OUT / "docs", OUT / "docs" / "log.jsonl"
    folder.mkdir(parents=True, exist_ok=True)
    have = {f"{p.parent.name}/{p.stem}" for p in folder.glob("*/*.gz")}
    todo = [r for r in want.itertuples() if f"{r.cik}/{r.accession}" not in have]
    firms = want["cik"].nunique()
    print(f"{len(want)} documents for {firms} filers, {len(todo)} to fetch", flush=True)
    saved = failed = 0
    with ThreadPoolExecutor(WORKERS) as pool, log.open("a", encoding="utf-8") as fh:
        for n, entry in enumerate(pool.map(grab, todo), 1):
            # Each receipt is written at once, so a stopped run loses none.
            fh.write(json.dumps(entry) + "\n")
            fh.flush()
            saved, failed = saved + ("error" not in entry), failed + ("error" in entry)
            if n % 500 == 0:
                print(f"{n} of {len(todo)}: {saved} saved, {failed} failed", flush=True)
    print(f"Done: {saved} saved this run, {failed} failed, log in {log}")
    return 0


# Receipts for saved documents the log lacks (a run stopped mid-batch).
def relog() -> int:
    log = OUT / "docs" / "log.jsonl"
    logged = {json.loads(line).get("path") for line in log.read_text().splitlines()}
    table = pd.read_parquet(OUT / "filings.parquet").drop_duplicates("accession")
    where = table.set_index("accession")
    added = 0
    with log.open("a", encoding="utf-8") as fh:
        for path in sorted((OUT / "docs").glob("*/*.gz")):
            rel = path.relative_to(OUT).as_posix()
            if rel in logged:
                continue
            row = where.loc[path.name.removesuffix(".gz")]
            url = f"{ARCHIVE}/{path.parent.name}/{row.name.replace('-', '')}/{row.document}"
            body = gzip.decompress(path.read_bytes())
            entry = {"url": url, "path": rel, "bytes": len(body)}
            entry |= {"sha256": hashlib.sha256(body).hexdigest(), "relogged": True}
            fh.write(json.dumps(entry) + "\n")
            added += 1
    print(f"{added} receipts added to {log}")
    return 0


# One document saved gzipped through a temporary name, or its error.
def grab(row) -> dict:
    path = OUT / "docs" / str(row.cik) / f"{row.accession}.gz"
    url = f"{ARCHIVE}/{row.cik}/{row.accession.replace('-', '')}/{row.document}"
    try:
        body = fetch(url)
    except Exception as err:  # noqa: BLE001
        return {"url": url, "error": f"{type(err).__name__}: {err}"}
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    part.write_bytes(gzip.compress(body))
    part.replace(path)
    entry = {"url": url, "path": path.relative_to(OUT).as_posix(), "bytes": len(body)}
    return entry | {"sha256": hashlib.sha256(body).hexdigest()}


# A gzipped document's original SHA-256, as the log records it.
def unzipped(path: Path) -> str:
    return hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()


# Every saved file against its receipt; --deep rehashes every document.
def verify(deep: bool = False) -> int:
    bad = 0
    for book in sorted((OUT / "receipts").glob("*.json")):
        name = book.name.removesuffix(".json")
        if name in HOME_ONLY and not (OUT / name).exists():
            print(f"edgar {name}: kept on the Mac, not in the kit")
            continue
        wrong = check(OUT, {name: receipts(book)["sha256"]})
        print(f"edgar {name}: {'ok' if not wrong else 'DIFFERS'}")
        bad += len(wrong)
    thirteen = receipts(OUT / "13f" / "receipts.json")
    wrong = check(OUT / "13f", {k: v["sha256"] for k, v in thirteen.items()})
    print(f"edgar 13f: {len(thirteen)} files, {len(wrong)} differ {wrong[:5]}")
    bad += len(wrong)
    log = OUT / "docs" / "log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    saved = {e["path"]: e["sha256"] for e in map(json.loads, lines) if "path" in e}
    missing = [p for p in saved if not (OUT / p).exists()]
    step = 1 if deep else max(1, len(saved) // 2000)
    sample = [(p, d) for p, d in list(saved.items())[::step] if (OUT / p).exists()]
    wrong_docs = [p for p, d in sample if unzipped(OUT / p) != d]
    counts = f"{len(saved)} logged, {len(missing)} missing, {len(sample)} rehashed"
    print(f"edgar docs: {counts}, {len(wrong_docs)} differ")
    bad += len(missing) + len(wrong_docs)
    return 1 if bad else 0


# One verb per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "edgar"
    verbs = {"bulk": bulk, "facts": facts, "13f": thirteen_f, "insiders": insiders, "map": link}
    verbs |= {"filings": filings, "forms": forms, "docs": docs, "verify": verify, "relog": relog}
    verbs |= {"names": names}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    if verb == "verify":
        sys.exit(verify("--deep" in sys.argv))
    sys.exit(verbs[verb]())
