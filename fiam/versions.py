# The four versions as recipes built from the code that defines them.

import hashlib
import json
import sys
from pathlib import Path

from fiam.v2 import V2

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "versions"
# The switches final v3 runs with, the book the round-one site presents.
V3_SWITCHES = ("brake", "shorts", "size", "target10", "voltarget", "zerobeta")
V3_RUN = "+".join(V3_SWITCHES)
# Each version: its code, protocols, frozen files and results.
VERSIONS = {
    "v1": {
        "title": "Round one, the submitted book",
        "status": "closed",
        "code": ["fiam/book.py"],
        "command": "uv run run.py",
        "protocols": ["docs/protocols/README.md"],
        "frozen": ["frozen/september_v1.csv"],
        "results": ["submission/holdings.csv", "submission/returns.csv", "submission/metrics.json"],
    },
    "v2": {
        "title": "v2, the book with costs, persistence, beta, shorts and liquidity",
        "status": "closed",
        "code": ["fiam/v2.py"],
        "switches": sorted(V2),
        "command": "uv run run.py --v2",
        "protocols": [
            "docs/protocols/v2.md",
            "docs/protocols/v2_amendment_1.md",
            "docs/protocols/v2_amendment_2.md",
        ],
        "frozen": ["frozen/september_v2.csv", "frozen/v2_params.json"],
        "results": [],
    },
    "v3": {
        "title": "Final v3, the book the round-one site and deck present",
        "status": "closed",
        "code": ["fiam/v2.py"],
        "switches": list(V3_SWITCHES),
        "run": V3_RUN,
        "command": "uv run run.py --v2 --switch final",
        "protocols": ["docs/protocols/v2_amendment_3.md", "docs/protocols/final_exhibits.md"],
        "frozen": ["frozen/september_v3.csv", "frozen/september_final.csv"],
        "results": [],
    },
    "v4": {
        "title": "v4, the finals book",
        "status": "in progress",
        "code": ["fiam/v4/"],
        "command": "uv run run.py finals (built from step 5)",
        "protocols": ["versions/v4/protocol.md (written before any run, step 4)"],
        "frozen": ["frozen/v4/ (at the freeze, step 10)"],
        "results": ["out/v4/"],
    },
}


# A tracked file's SHA-256, or None for a folder or a file not made yet.
def sha(relative: str) -> str | None:
    path = ROOT / relative.split(" ")[0]
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# One version's recipe, fingerprinting its frozen and result files.
def recipe(name: str) -> dict:
    spec = VERSIONS[name]
    files = {p: sha(p) for p in [*spec["frozen"], *spec["results"]] if sha(p)}
    return {"version": name, **spec, "fingerprints": files}


# Writes versions/<name>/recipe.json for every version.
def write() -> None:
    for name in VERSIONS:
        folder = FOLDER / name
        folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(recipe(name), indent=1) + "\n"
        (folder / "recipe.json").write_text(text, encoding="utf-8")
        print(f"versions/{name}/recipe.json: {len(recipe(name)['fingerprints'])} fingerprints")


# Rewrites the recipes; only a deliberate run changes a closed version.
if __name__ == "__main__":
    if sys.argv[1:] != ["write"]:
        print("Usage: uv run -m fiam.versions write")
        sys.exit(2)
    write()
