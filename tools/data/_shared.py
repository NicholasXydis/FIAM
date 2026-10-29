# Helpers the data tools share; standard library only, any env runs it.

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Where the read-only Stock Data archive usually sits, Mac then Windows.
STOCK_DATA_PLACES = (Path("/Applications/@Apps/Stock Data"), Path("E:/Stock Data"))


# The links on a web page matching one pattern, sorted and unique.
def listed(page: str, pattern: str) -> list[str]:
    return sorted(set(re.findall(rf'href="({pattern})"', page)))


# A setting from the environment or .env; secrets are never printed.
def setting(name: str, default: str = "") -> str:
    found = os.environ.get(name, "")
    env = ROOT / ".env"
    if not found and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                found = value.split("#")[0].strip()
    return found or default


# The data root: the repo's data/, or --into <folder> for a rebuild.
def data_root(argv: list[str]) -> Path:
    if "--into" in argv:
        at = argv.index("--into")
        folder = Path(argv[at + 1]).expanduser().resolve()
        del argv[at : at + 2]
        return folder
    return ROOT / "data"


# The Stock Data archive: FIAM_STOCK_DATA, else the first usual place.
def stock_data() -> Path:
    chosen = setting("FIAM_STOCK_DATA")
    if chosen:
        return Path(chosen).expanduser()
    return next((p for p in STOCK_DATA_PLACES if p.exists()), STOCK_DATA_PLACES[0])


# A file's SHA-256, read in chunks so large files stay out of memory.
def fingerprint(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


# The archive's own content fingerprint: SHA-1 in base 32.
def archive_digest(body: bytes) -> str:
    return base64.b32encode(hashlib.sha1(body).digest()).decode()


# The current time in UTC, as every receipt records it.
def stamp() -> str:
    return datetime.now(UTC).isoformat()


# A receipts file as a dict, empty when it does not exist yet.
def receipts(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# One GET with a polite pause, retried when the server is busy.
def fetch(url: str, headers: dict | None = None, pace: float = 0.0) -> bytes:
    last = None
    for wait in (0, 10, 30, 90):
        time.sleep(wait + pace)
        try:
            sent = {"User-Agent": "FIAM research"} | (headers or {})
            request = urllib.request.Request(url, headers=sent)
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise
            last = err
        except OSError as err:
            last = err
    raise last


# Checks each named file's SHA-256; returns the names that differ.
def check(folder: Path, expected: dict[str, str]) -> list[str]:
    bad = []
    for name, digest in expected.items():
        path = folder / name
        if not path.exists() or fingerprint(path) != digest:
            bad.append(name)
    return bad
