# Where every step reads and writes: submission/ on an official run, out/ (FIAM_OUT) otherwise.

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

OUT_ROOT = Path(os.environ.get("FIAM_OUT", "."))
SUBMISSION = OUT_ROOT / "submission"
EXHIBITS = SUBMISSION / "exhibits"
HOLDINGS = SUBMISSION / "holdings.csv"
RETURNS = SUBMISSION / "returns.csv"
METRICS = SUBMISSION / "metrics.json"
RESULTS = OUT_ROOT / "RESULTS.md"
BRIEF = OUT_ROOT / "BRIEF.md"

# The small-run switch: every slow step shrinks to a slice, so the whole chain is tested in minutes.
SMOKE = os.environ.get("FIAM_SMOKE") == "1"


# A JSON file, or an empty dict if the step that writes it has not run.
def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# An exhibit by name, from wherever this run writes.
def exhibit(name: str) -> dict:
    return read_json(EXHIBITS / name)


# The monthly returns file, indexed by holding month.
def returns() -> pd.DataFrame:
    return pd.read_csv(RETURNS, parse_dates=["holding_month"]).set_index("holding_month")


# The holdings file, one row per stock and month.
def holdings() -> pd.DataFrame:
    return pd.read_csv(HOLDINGS, parse_dates=["Date"])


# Read in blocks, so a multi-gigabyte file never has to fit in memory.
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


# A file still matches its recorded hash, byte for byte. Every text file here is written with LF.
def matches(path: Path, digest: str) -> bool:
    return path.exists() and sha256(path) == digest
