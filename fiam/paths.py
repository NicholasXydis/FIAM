# Where steps write: submission/ officially, else out/ via FIAM_OUT.

import hashlib
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

OUT_ROOT = Path(os.environ.get("FIAM_OUT", "."))
SUBMISSION = OUT_ROOT / "submission"
EXHIBITS = SUBMISSION / "exhibits"
HOLDINGS = SUBMISSION / "holdings.csv"
RETURNS = SUBMISSION / "returns.csv"
METRICS = SUBMISSION / "metrics.json"
RESULTS = OUT_ROOT / "RESULTS.md"

# Small-run switch: slow steps shrink, so the chain tests in minutes.
SMOKE = os.environ.get("FIAM_SMOKE") == "1"


# A JSON file, or an empty dict if the step that writes it has not run.
def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# An exhibit by name, from wherever this run writes.
def exhibit(name: str) -> dict:
    return read_json(EXHIBITS / name)


# Six decimals on write only. The maths keeps full precision.
def round_floats(obj, places: int = 6):
    if isinstance(obj, dict):
        return {k: round_floats(v, places) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, places) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return round(float(obj), places)
    # A bool is an int to Python, so it passes before it turns into 1.
    if isinstance(obj, (int, np.integer)) and not isinstance(obj, bool):
        return int(obj)
    return obj


# Every pipeline JSON: indented, LF endings, rounded unless told not to.
def write_json(path: Path, obj, rounded: bool = True, end: str = "", default=None) -> None:
    text = json.dumps(round_floats(obj) if rounded else obj, indent=2, default=default)
    path.write_text(text + end, encoding="utf-8", newline="\n")


# Unzips, refusing the whole zip if any entry lands outside its folder.
def safe_unzip(source: Path, target: Path, inside: Path | None = None) -> None:
    root = (inside or target).resolve()
    with zipfile.ZipFile(source) as zf:
        names = zf.namelist()
        outside = [n for n in names if not (target.resolve() / n).resolve().is_relative_to(root)]
        if outside:
            raise ValueError(f"{source.name} has entries outside {root.name}/: {outside[:3]}")
        zf.extractall(target)


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


# A file still matches its recorded hash byte for byte. All text is LF.
def matches(path: Path, digest: str) -> bool:
    return path.exists() and sha256(path) == digest
