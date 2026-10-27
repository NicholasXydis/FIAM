# NOAA's free climate and storm records, saved once with receipts.

import hashlib
import json
import re
import sys
from pathlib import Path

from _shared import ROOT, archive_digest, check, data_root, fetch, receipts, stamp

OUT = ROOT / "data" / "noaa"
CLIMDIV = "https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/"
STORMS = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
USAGE = "uv run run.py --data noaa climdiv | storms | archive | verify"
# Pre-2021 Internet Archive copies for the vintage check.
CDX = "http://web.archive.org/cdx/search/cdx?output=json&fl=timestamp,original,digest"
CDX += "&matchType=prefix&to=20201231&filter=statuscode:200"
STORM_COPIES = "www1.ncdc.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details"
CLIMATE_COPIES = (
    "ftp.ncdc.noaa.gov/pub/data/cirs/climdiv/climdiv-",
    "www1.ncdc.noaa.gov/pub/data/cirs/climdiv/climdiv-",
)
STORM_YEARS, CLIMATE_KINDS = range(2000, 2021), ("tmpcst", "pcpnst")
# State-level temperature, rainfall, drought, degree days and normals.
KINDS = ("tmpcst", "pcpnst", "pdsist", "hddcst", "cddcst", "norm-tmpcst", "norm-pcpnst")
PACE = 0.5
FOLDERS = ("climdiv", "storms", "archive")


# The file names a NOAA folder page links to, matching one pattern.
def listed(page: str, pattern: str) -> list[str]:
    return sorted(set(re.findall(rf'href="({pattern})"', page)))


# The newest version of each kind, by the date at the end of its name.
def newest(names: list[str]) -> dict[str, str]:
    best = {}
    for kind in KINDS:
        own = [n for n in names if re.fullmatch(rf"climdiv-{kind}-v[\d.]+-\d{{8}}", n)]
        if own:
            best[kind] = max(own, key=lambda n: n[-8:])
    return best


# Saves files from one folder into a subfolder with one receipt each.
def save(base: str, names: list[str], folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    book = folder / "receipts.json"
    saved = receipts(book)
    failed = 0
    for n, name in enumerate(names, 1):
        if name in saved and (folder / name).exists():
            continue
        try:
            body = fetch(base + name, pace=PACE)
        except Exception as err:  # noqa: BLE001
            print(f"{name}: failed ({type(err).__name__}: {err})", flush=True)
            failed += 1
            continue
        part = folder / f"{name}.part"
        part.write_bytes(body)
        part.replace(folder / name)
        saved[name] = {"url": base + name, "bytes": len(body)}
        saved[name] |= {"sha256": hashlib.sha256(body).hexdigest(), "pulled_at": stamp()}
        book.write_text(json.dumps(saved, indent=1))
        print(f"{n} of {len(names)} {name} ({len(body) / 1e6:.1f} MB)", flush=True)
    print(f"{folder.name}: {len(saved)} saved, {failed} failed")
    return 1 if failed else 0


# State climate series: the newest file of each kind plus the readmes.
def climdiv() -> int:
    page = fetch(CLIMDIV, pace=PACE).decode("utf-8", "replace")
    chosen = newest(listed(page, r"climdiv-[a-z0-9.-]+"))
    missing = [k for k in KINDS if k not in chosen]
    if missing:
        print(f"Not listed by NOAA: {missing}")
        return 1
    readmes = [n for n in listed(page, r"[a-z0-9-]*readme[a-z0-9.-]*") if n.endswith(".txt")]
    return save(CLIMDIV, sorted(chosen.values()) + readmes, OUT / "climdiv")


# Every year of storm event details, 1950 on, plus the format guide.
def storms() -> int:
    page = fetch(STORMS, pace=PACE).decode("utf-8", "replace")
    names = listed(page, r"StormEvents_details-ftp_v1\.0_d\d{4}_c\d{8}\.csv\.gz")
    guides = listed(page, r"[A-Za-z0-9_-]*[Ff]ormat[A-Za-z0-9_.-]*\.(?:pdf|docx?|txt)")
    print(f"{len(names)} yearly files listed", flush=True)
    return save(STORMS, names + guides, OUT / "storms")


# Captures to fetch: storm years 2000-2020 and the two climate kinds.
def copies() -> list[tuple[str, str, str, str]]:
    found = {}
    for prefix in (STORM_COPIES, *CLIMATE_COPIES):
        rows = json.loads(fetch(f"{CDX}&url={prefix}", pace=PACE) or b"[]")[1:]
        for when, original, digest in rows:
            name = original.rsplit("/", 1)[-1]
            year = re.search(r"_d(\d{4})_c\d{8}", name)
            kind = re.match(r"climdiv-([a-z]+)-", name)
            wanted = (year and int(year.group(1)) in STORM_YEARS) or (
                kind and kind.group(1) in CLIMATE_KINDS
            )
            # One fetch per distinct file content, its newest capture.
            if wanted and (digest not in found or when > found[digest][0]):
                found[digest] = (when, original, name)
    return sorted((w, o, n, d) for d, (w, o, n) in found.items())


# Pre-2021 archived copies, each checked against the archive's digest.
def archive() -> int:
    folder = OUT / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    book = folder / "receipts.json"
    saved = receipts(book)
    todo = copies()
    print(f"{len(todo)} archived copies", flush=True)
    failed = 0
    for n, (when, original, name, digest) in enumerate(todo, 1):
        key = f"{when}_{name}"
        if key in saved and (folder / key).exists():
            continue
        url = f"http://web.archive.org/web/{when}id_/{original}"
        try:
            body = fetch(url, pace=PACE)
        except Exception as err:  # noqa: BLE001
            print(f"{key}: failed ({type(err).__name__})", flush=True)
            failed += 1
            continue
        if archive_digest(body) != digest:
            print(f"{key}: content does not match the archive's digest; not saved", flush=True)
            failed += 1
            continue
        part = folder / f"{key}.part"
        part.write_bytes(body)
        part.replace(folder / key)
        saved[key] = {"url": url, "captured": when, "bytes": len(body)}
        saved[key] |= {
            "archive_digest": archive_digest(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        saved[key]["pulled_at"] = stamp()
        book.write_text(json.dumps(saved, indent=1))
        print(f"{n} of {len(todo)} {key} ({len(body) / 1e6:.1f} MB)", flush=True)
    print(f"archive: {len(saved)} saved, {failed} failed")
    return 1 if failed else 0


# Every saved file against its receipt; prints and counts any mismatch.
def verify() -> int:
    bad = 0
    for name in FOLDERS:
        folder = OUT / name
        listed_files = {k: v["sha256"] for k, v in receipts(folder / "receipts.json").items()}
        wrong = check(folder, listed_files)
        print(f"noaa {name}: {len(listed_files)} files, {len(wrong)} wrong {wrong[:5]}")
        bad += len(wrong)
    return 1 if bad else 0


# One or more verbs per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "noaa"
    verbs = {"climdiv": climdiv, "storms": storms, "archive": archive, "verify": verify}
    asked = sys.argv[1:]
    if not asked or any(v not in verbs for v in asked):
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(max(verbs[v]() for v in asked))
