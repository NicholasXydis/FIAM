# Shared file helpers: frozen inputs, hashes, safe unzips and JSON.

import hashlib
import json
import os
import zipfile
from pathlib import Path

import numpy as np

# Small frozen inputs, so git holds them. Relative like cache/.
FROZEN = Path("frozen")

# Small-run switch: slow steps shrink, so the chain tests in minutes.
SMOKE = os.environ.get("FIAM_SMOKE") == "1"


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


# Read in blocks, so a multi-gigabyte file never has to fit in memory.
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()
