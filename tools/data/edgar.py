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
from _shared import ROOT, check, data_root, fingerprint, receipts, setting, stamp

OUT = ROOT / "data" / "edgar"
BULK = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
# SEC rebuilds it nightly, so it stays on the Mac with its hash kept.
HOME_ONLY = {"submissions.zip"}
FACTS = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
F13 = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
USAGE = "uv run run.py --data edgar bulk | facts | 13f | map | filings | docs | verify [--deep]"
EIGHT_K = "8k_20150101_20260831_identified.parquet"
# Annual reports for Lazy Prices, and the 8-K items that are red flags.
ANNUAL = {"10-K", "10-K405", "10-KT", "10-KSB"}
FLAGS = {"1.03", "2.06", "3.01", "4.01", "4.02", "5.02"}
START = "2012-01-01"
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
        # A finished part that was never renamed: fetch it again.
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


# The 13F zip links on the SEC page, in whichever folder it files them.
def listed(page: str) -> list[str]:
    return sorted(set(re.findall(r'href="(/files/[^"]+_form13f\.zip)"', page)))


# Every 13F data set the SEC lists, each zip checked and receipted.
def thirteen_f() -> int:
    links = listed(fetch(F13).decode("utf-8", "replace"))
    folder = OUT / "13f"
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
    comp = pd.read_parquet(bundle() / "wrds" / "compustat_quarterly.parquet")
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
    return 0


# Our firms' annual reports and 8-Ks since 2012, from the bulk file.
def filings() -> int:
    firms = pd.read_parquet(OUT / "cik_map.parquet")
    ciks = sorted(int(c) for c in firms["cik"].dropna().unique())
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
                    if date < START or (form not in ANNUAL and form != "8-K"):
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
    table = pd.DataFrame(rows).drop_duplicates("accession")
    table["red_flag"] = table["items"].fillna("").map(lambda s: bool(FLAGS & set(s.split(","))))
    table.to_parquet(OUT / "filings.parquet", index=False)
    report = {"filers": len(ciks), "not_in_bulk": len(missing), "filings": len(table)}
    report["annual_reports"] = int(table["form"].isin(ANNUAL).sum())
    report["eight_k"] = int((table["form"] == "8-K").sum())
    report["red_flag_8k"] = int(table["red_flag"].sum())
    (OUT / "filings.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


# Our universe's annual reports and red-flag 8-Ks, saved gzipped.
def docs() -> int:
    firms = pd.read_parquet(OUT / "cik_map.parquet")
    universe = set(firms.loc[firms["universe"], "cik"].dropna().astype(int))
    table = pd.read_parquet(OUT / "filings.parquet")
    pick = table["form"].isin(ANNUAL) | ((table["form"] == "8-K") & table["red_flag"])
    want = table[pick & table["cik"].isin(universe) & (table["document"] != "")].copy()
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
    print(f"{len(want)} documents for {len(universe)} firms, {len(todo)} to fetch", flush=True)
    saved = failed = 0
    with ThreadPoolExecutor(WORKERS) as pool, log.open("a", encoding="utf-8") as fh:
        for n, entry in enumerate(pool.map(grab, todo), 1):
            fh.write(json.dumps(entry) + "\n")
            saved, failed = saved + ("error" not in entry), failed + ("error" in entry)
            if n % 500 == 0:
                fh.flush()
                print(f"{n} of {len(todo)}: {saved} saved, {failed} failed", flush=True)
    print(f"Done: {saved} saved this run, {failed} failed, log in {log}")
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
        print(f"edgar {name}: {'ok' if not wrong else 'WRONG'}")
        bad += len(wrong)
    thirteen = receipts(OUT / "13f" / "receipts.json")
    wrong = check(OUT / "13f", {k: v["sha256"] for k, v in thirteen.items()})
    print(f"edgar 13f: {len(thirteen)} files, {len(wrong)} wrong {wrong[:5]}")
    bad += len(wrong)
    log = OUT / "docs" / "log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    saved = {e["path"]: e["sha256"] for e in map(json.loads, lines) if "path" in e}
    missing = [p for p in saved if not (OUT / p).exists()]
    step = 1 if deep else max(1, len(saved) // 2000)
    sample = [(p, d) for p, d in list(saved.items())[::step] if (OUT / p).exists()]
    wrong_docs = [p for p, d in sample if unzipped(OUT / p) != d]
    counts = f"{len(saved)} logged, {len(missing)} missing, {len(sample)} rehashed"
    print(f"edgar docs: {counts}, {len(wrong_docs)} wrong")
    bad += len(missing) + len(wrong_docs)
    return 1 if bad else 0


# One verb per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "edgar"
    verbs = {"bulk": bulk, "facts": facts, "13f": thirteen_f, "map": link}
    verbs |= {"filings": filings, "docs": docs, "verify": verify}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    if verb == "verify":
        sys.exit(verify("--deep" in sys.argv))
    sys.exit(verbs[verb]())
