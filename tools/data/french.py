# French's daily factor files as archived before 2021, receipted (B23).

import base64
import hashlib
import json
import sys

from _shared import ROOT, fetch, receipts, stamp

OUT = ROOT / "data" / "benchmarks" / "french_archive"
USAGE = "uv run run.py --data french archive | verify"
SITE = "mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = ("F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "F-F_Momentum_Factor_daily_CSV.zip")
CDX = "http://web.archive.org/cdx/search/cdx?output=json&fl=timestamp,digest&filter=statuscode:200"
# Copies captured before 2021 only; the newest decides (protocol.md).
BEFORE = "20201231"
PACE = 1.0


# The archive's own content fingerprint: SHA-1 in base 32.
def archive_digest(body: bytes) -> str:
    return base64.b32encode(hashlib.sha1(body).digest()).decode()


# Every pre-2021 capture of one file: (timestamp, digest), oldest first.
def captures(name: str) -> list[tuple[str, str]]:
    url = f"{CDX}&url={SITE}{name}&to={BEFORE}"
    rows = json.loads(fetch(url, pace=PACE) or b"[]")
    return [(r[0], r[1]) for r in rows[1:]]


# Fetches each capture as archived, checks its digest, saves a receipt.
def archive() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    book = OUT / "receipts.json"
    saved = receipts(book)
    for name in FILES:
        for when, digest in captures(name):
            key = f"{when}_{name}"
            if key in saved:
                continue
            url = f"http://web.archive.org/web/{when}id_/https://{SITE}{name}"
            body = fetch(url, pace=PACE)
            if archive_digest(body) != digest:
                print(f"{key}: content does not match the archive's digest; not saved")
                return 1
            (OUT / key).write_bytes(body)
            saved[key] = {
                "url": url,
                "captured": when,
                "archive_digest": digest,
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "pulled_at": stamp(),
            }
            book.write_text(json.dumps(saved, indent=1))
            print(f"{key}: {len(body):,} bytes", flush=True)
    print(f"Done: {len(saved)} archived copies in {OUT}")
    return 0


# Every saved copy against its receipt.
def verify() -> int:
    saved = receipts(OUT / "receipts.json")
    bad = [k for k, e in saved.items() if not (OUT / k).exists()]
    bad += [
        k
        for k, e in saved.items()
        if (OUT / k).exists() and hashlib.sha256((OUT / k).read_bytes()).hexdigest() != e["sha256"]
    ]
    print(f"french archive: {len(saved)} files, {len(bad)} wrong {bad[:3]}")
    return 1 if bad else 0


# One verb per run.
if __name__ == "__main__":
    verbs = {"archive": archive, "verify": verify}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(verbs[verb]())
