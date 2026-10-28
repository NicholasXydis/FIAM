# Each version as a recipe built from the code that defines it.

import json
import sys
from pathlib import Path

from fiam import paths

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "versions"
# Each version: its code, documents, frozen files and results.
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
    "vfinal": {
        "title": "The final version, the finals book",
        "status": "in progress",
        "code": ["fiam/vfinal/"],
        "command": "uv run fiam rerun",
        "protocols": ["versions/vfinal/protocol.md"],
        "frozen": ["frozen/vfinal/"],
        "results": ["out/vfinal/"],
    },
}


# A tracked file's SHA-256, or None for a folder or a file not made yet.
def sha(relative: str) -> str | None:
    path = ROOT / relative.split(" ")[0]
    return paths.sha256(path) if path.is_file() else None


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
