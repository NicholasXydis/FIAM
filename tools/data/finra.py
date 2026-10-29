# FINRA's public short interest and daily short-sale volume, receipted.

import gzip
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request

import pandas as pd
from _shared import ROOT, data_root, receipts, stamp

OUT = ROOT / "data" / "finra"
CDN = "https://cdn.finra.org/equity"
USAGE = "uv run run.py --data finra shortint | volume | build | verify"
# Exchange-listed names join FINRA's short interest files in June 2021.
SHORT_FROM = pd.Timestamp("2021-06-01")
# The consolidated daily file starts 2018-08-01, venue files before it.
CONSOLIDATED_FROM = pd.Timestamp("2018-08-01")
VENUES = ("FNYX", "FNSQ", "FNRA")
# The 2015-2020 check, and 2026 with its six-month lead-in.
WINDOWS = (("2015-01-01", "2020-12-31"), ("2025-06-01", "2026-09-30"))
# Candidate 2026 settlement days around mid-month and month end.
PROBE_DAYS = (*range(10, 21), *range(24, 32))
PACE = 0.25


# One GET: the bytes, or None when FINRA has no such file (403 or 404).
def get(url: str) -> bytes | None:
    last = None
    for wait in (0, 10, 30):
        time.sleep(wait + PACE)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "FIAM research"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            if err.code in (403, 404):
                return None
            last = err
        except OSError as err:
            last = err
    raise last


# One file saved gzipped through a temporary name, with its receipt.
def save(folder, name: str, url: str, body: bytes) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f"{name}.gz.part"
    part.write_bytes(gzip.compress(body))
    part.replace(folder / f"{name}.gz")
    digest = hashlib.sha256(body).hexdigest()
    return {"url": url, "bytes": len(body), "sha256": digest, "pulled_at": stamp()}


# The settlement days to fetch: WRDS's from June 2021, then 2026 probes.
def settlement_days() -> list[pd.Timestamp]:
    wrds = pd.read_parquet(ROOT / "data" / "v4" / "extracts" / "short_interest.parquet")
    days = pd.to_datetime(wrds["datadate"].drop_duplicates())
    known = sorted(d for d in days if d >= SHORT_FROM)
    probes = []
    for month in range(1, 11):
        for day in PROBE_DAYS:
            try:
                probes.append(pd.Timestamp(2026, month, day))
            except ValueError:
                continue
    return known + [d for d in probes if d > known[-1]]


# FINRA's biweekly short interest files for each settlement day.
def shortint() -> int:
    folder = OUT / "short_interest"
    book = folder / "receipts.json"
    saved = receipts(book)
    absent = 0
    for day in settlement_days():
        name = f"shrt{day:%Y%m%d}.csv"
        if name in saved:
            continue
        url = f"{CDN}/otcmarket/biweekly/{name}"
        body = get(url)
        if body is None:
            absent += 1
            continue
        saved[name] = save(folder, name, url, body)
        book.write_text(json.dumps(saved, indent=1))
        print(f"{name} ({len(body) >> 10} KB)", flush=True)
    print(f"Done: {len(saved)} short interest files, {absent} candidate days with none")
    return 0


# Every NYSE session in the volume windows, from the pinned calendar.
def volume_days() -> list[pd.Timestamp]:
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS", start="2014-01-01", end="2026-12-31")
    days = []
    for start, end in WINDOWS:
        days += list(cal.sessions_in_range(start, end))
    return [pd.Timestamp(d) for d in days]


# Daily short-sale volume: consolidated from 2018-08, venues before it.
def volume() -> int:
    folder = OUT / "volume"
    log = folder / "receipts.jsonl"
    folder.mkdir(parents=True, exist_ok=True)
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    done = {json.loads(line)["name"] for line in lines}
    todo = []
    for day in volume_days():
        venues = ("CNMS",) if day >= CONSOLIDATED_FROM else VENUES
        todo += [(venue, f"{venue}shvol{day:%Y%m%d}.txt") for venue in venues]
    todo = [(v, n) for v, n in todo if n not in done]
    print(f"{len(todo)} volume files to fetch", flush=True)
    with log.open("a", encoding="utf-8") as fh:
        for count, (venue, name) in enumerate(todo, 1):
            url = f"{CDN}/regsho/daily/{name}"
            body = get(url)
            entry = {"name": name, "absent": True} if body is None else {"name": name}
            if body is not None:
                entry |= save(folder / venue, name, url, body)
            fh.write(json.dumps(entry) + "\n")
            if count % 200 == 0:
                fh.flush()
                print(f"{count} of {len(todo)}", flush=True)
    print(f"Done: {len(todo)} fetched or marked absent, log in {log}")
    return 0


# One pipe-delimited FINRA file as a table, trailer rows dropped.
def table(path) -> pd.DataFrame:
    text = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
    frame = pd.read_csv(io.StringIO(text), sep="|", dtype=str, keep_default_na=False)
    first = frame.columns[0]
    return frame[frame[first].str.fullmatch(r"\d{8}|\d{4}-\d{2}-\d{2}", na=False)]


# Parses both into parquet: short interest, and volume summed by venue.
def build() -> int:
    files = sorted((OUT / "short_interest").glob("*.csv.gz"))
    si = pd.concat([table(p) for p in files], ignore_index=True)
    si = si.rename(
        columns={
            "settlementDate": "settlement",
            "symbolCode": "symbol",
            "issueName": "issue_name",
            "marketClassCode": "market",
            "currentShortPositionQuantity": "short",
            "previousShortPositionQuantity": "previous",
            "stockSplitFlag": "split_flag",
            "averageDailyVolumeQuantity": "adv",
            "daysToCoverQuantity": "days_to_cover",
            "revisionFlag": "revision",
        }
    )
    si["settlement"] = pd.to_datetime(si["settlement"])
    for col in ("short", "previous", "adv", "days_to_cover"):
        si[col] = pd.to_numeric(si[col], errors="coerce")
    keep = ["settlement", "symbol", "issue_name", "market", "short", "previous"]
    si[keep + ["split_flag", "adv", "days_to_cover", "revision"]].to_parquet(
        OUT / "short_interest.parquet", index=False
    )
    parts = []
    for path in sorted((OUT / "volume").glob("*/*.txt.gz")):
        t = table(path)
        t["venue"] = path.parent.name
        parts.append(t)
    vol = pd.concat(parts, ignore_index=True)
    for col in ("ShortVolume", "ShortExemptVolume", "TotalVolume"):
        vol[col] = pd.to_numeric(vol[col], errors="coerce")
    vol["date"] = pd.to_datetime(vol["Date"], format="%Y%m%d")
    summed = vol.groupby(["date", "Symbol"], as_index=False).agg(
        short_volume=("ShortVolume", "sum"),
        total_volume=("TotalVolume", "sum"),
        venues=("venue", "nunique"),
    )
    summed.rename(columns={"Symbol": "symbol"}).to_parquet(OUT / "volume.parquet", index=False)
    report = {"short_interest_rows": len(si), "settlements": int(si["settlement"].nunique())}
    report |= {"volume_rows": len(summed), "volume_days": int(summed["date"].nunique())}
    (OUT / "build.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


# Every saved file against its receipt.
def verify() -> int:
    bad = 0
    book = receipts(OUT / "short_interest" / "receipts.json")
    for name, entry in book.items():
        path = OUT / "short_interest" / f"{name}.gz"
        ok = path.exists() and hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()
        bad += ok != entry["sha256"]
    log = OUT / "volume" / "receipts.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    for entry in map(json.loads, lines):
        if entry.get("absent"):
            continue
        path = OUT / "volume" / entry["name"][:4] / f"{entry['name']}.gz"
        ok = path.exists() and hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()
        bad += ok != entry["sha256"]
    print(f"finra: {len(book)} short interest files, {len(lines)} volume entries, {bad} differ")
    return 1 if bad else 0


# One verb per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "finra"
    verbs = {"shortint": shortint, "volume": volume, "build": build, "verify": verify}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(verbs[verb]())
