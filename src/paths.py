# Where every step writes. An official run writes the committed files; any other run writes
# under out/ (FIAM_OUT), so checking the work on another machine never edits the repo.

import hashlib
import os
from pathlib import Path

OUT_ROOT = Path(os.environ.get("FIAM_OUT", "."))
SUBMISSION = OUT_ROOT / "submission"
EXHIBITS = SUBMISSION / "exhibits"
RESULTS = OUT_ROOT / "RESULTS.md"
BRIEF = OUT_ROOT / "BRIEF.md"


TEXT = {".csv", ".json", ".md"}


# Hashes of text with LF and with CRLF endings. Git stores LF, and runs before 2026-09-26 recorded
# Windows CRLF bytes, so a record matching either form is the same content.
def digests(body: bytes) -> set[str]:
    lf = body.replace(b"\r\n", b"\n")
    return {hashlib.sha256(lf).hexdigest(), hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()}


# A file still matches its recorded hash. Text in either line ending, anything else byte for byte.
def matches(path: Path, digest: str) -> bool:
    if not path.exists():
        return False
    body = path.read_bytes()
    return digest in (digests(body) if path.suffix in TEXT else {hashlib.sha256(body).hexdigest()})
