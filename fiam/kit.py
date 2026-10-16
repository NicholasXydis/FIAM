# The results kit: what the long and GPU runs made, zipped with a SHA-256 per file for any machine.

import json
import zipfile
from pathlib import Path

from fiam import paths

NAME = "fiam_results.zip"
MANIFEST = "kit_manifest.json"
# The research runs the trial count reads, agent answers and transcripts, v2's runs and verdicts,
# the crisis cache, the frozen inputs, the committee packs the finals deck presents, the film
# (ffmpeg to render again), the receipt rebuilt from the data, and the rules reader's drafts, which
# git ignores.
PARTS = (
    "research",
    "cache/agents",
    "out/v2",
    "cache/stress_daily.parquet",
    "frozen",
    "out/finals",
    "out/figures/ai_crowd.mp4",
    "out/figures/ai_crowd_short.mp4",
    "out/figures/ai_crowd_poster.png",
    "out/figures/receipt.json",
    "out/figures/clips",
    "mandates/case_2025_draft.json",
    "mandates/case_2025_draft_quotes.json",
    "mandates/rules_2026_draft.json",
    "mandates/rules_2026_draft_quotes.json",
)


# Every file the kit carries, in a fixed order.
def files(root: Path = Path(".")) -> list[Path]:
    out = []
    for part in PARTS:
        path = root / part
        out += sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else []
        out += [path] if path.is_file() else []
    return [p for p in out if "__pycache__" not in p.parts]


# Writes the kit and its manifest; returns the zip's own SHA-256.
def export(target: Path = Path(NAME)) -> str:
    chosen = files()
    manifest = {p.as_posix(): paths.sha256(p) for p in chosen}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in chosen:
            zf.write(path, path.as_posix())
        zf.writestr(MANIFEST, json.dumps(manifest, indent=1))
    return paths.sha256(target)


# True for a results kit, so --import can tell it from the data bundle.
def is_kit(source: Path) -> bool:
    with zipfile.ZipFile(source) as zf:
        return MANIFEST in zf.namelist()


# Unpacks a kit into the repo and checks every file against its recorded hash.
def restore(source: Path, root: Path = Path(".")) -> int:
    paths.safe_unzip(source, root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    bad = [name for name, digest in manifest.items() if paths.sha256(root / name) != digest]
    (root / MANIFEST).unlink()
    if bad:
        raise SystemExit(f"{source.name}: {len(bad)} files do not match their hashes: {bad[:3]}")
    return len(manifest)
