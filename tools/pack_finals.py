# The finals package for the USB (docs/finals_day.md): everything GitHub does not hold, in one zip:
# the organizer's files, the data bundle, our results, the decks, the film, MAIN.py, uv and the
# runbook, every file hashed and the zip checked after writing. MAIN.py carries the committed files
# and any new ones not ignored: uv run tools/pack_finals.py <target folder>

import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

UV = "0.12.18"
UV_BUILDS = (
    "uv-x86_64-pc-windows-msvc.zip",
    "uv-x86_64-unknown-linux-gnu.tar.gz",
    "uv-aarch64-apple-darwin.tar.gz",
    "uv-x86_64-apple-darwin.tar.gz",
)
# In the zip under these names; the data and results zips are stored, not compressed again.
CONTENTS = {
    "organizer/chars_final_with_names.parquet": ROOT / "data" / "chars_final_with_names.parquet",
    "organizer/8k_20150101_20260831_identified.parquet": ROOT
    / "data"
    / "8k_20150101_20260831_identified.parquet",
    "organizer/factor_char_list.csv": ROOT / "data" / "factor_char_list.csv",
    # In git but too large for MAIN.py: the SEC names the label check confirms holdings against.
    "data/edgar_cache.zip": ROOT / "data" / "edgar_cache.zip",
    "fiam_v1.zip": ROOT / "fiam_v1.zip",
    "fiam_results.zip": ROOT / "fiam_results.zip",
    "deck/FIAM_finals.pptx": ROOT / "deck" / "FIAM_finals.pptx",
    "deck/FIAM_finals_print.pptx": ROOT / "deck" / "FIAM_finals_print.pptx",
    "deck/FIAM_finals.pdf": ROOT / "deck" / "FIAM_finals.pdf",
    "deck/ai_crowd_short.mp4": ROOT / "out" / "figures" / "ai_crowd_short.mp4",
    "deck/ai_crowd.mp4": ROOT / "out" / "figures" / "ai_crowd.mp4",
    "deck/FIAM_submitted.pdf": ROOT / "FIAM.pdf",
    "FINALS_DAY.md": ROOT / "docs" / "finals_day.md",
}
START = """FIAM finals: start here

1. pip install uv   (or use the installer in uv/ inside fiam_finals.zip)
2. Unzip fiam_finals.zip into an empty folder.
3. In that folder:
     uv run MAIN.py --import fiam_v1.zip --import fiam_results.zip
     uv run MAIN.py --world fake --finals mandates/case_2025.json      (the rehearsal)
4. On the day, FINALS_DAY.md has every command in order. The AI agents download their models the
   first time they run (internet needed); without them, write the mandate by hand.
organizer/ holds the organizer's original files: uv run MAIN.py --import organizer rebuilds the
data bundle from them, as a judge would.

The zip holds WRDS-derived data: team only, never posted. On Lightning AI keep the studio private.
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 24):
            digest.update(block)
    return digest.hexdigest()


# uv for every system, each checked against the release's own SHA-256.
def uv_builds(folder: Path) -> list[Path]:
    out = []
    for name in UV_BUILDS:
        base = f"https://github.com/astral-sh/uv/releases/download/{UV}/{name}"
        expected = urllib.request.urlopen(base + ".sha256", timeout=60).read().decode().split()[0]
        target = folder / name
        if not (target.exists() and sha256(target) == expected):
            target.write_bytes(urllib.request.urlopen(base, timeout=300).read())
        if sha256(target) != expected:
            raise SystemExit(f"{name} does not match its published SHA-256")
        out.append(target)
    return out


def main(target: Path) -> None:
    missing = [str(p) for p in CONTENTS.values() if not p.exists()]
    if missing:
        raise SystemExit(f"missing: {missing}")
    out = target / "FIAM_finals"
    out.mkdir(parents=True, exist_ok=True)
    sums = {}
    with tempfile.TemporaryDirectory() as tmp:
        main_py = Path(tmp) / "MAIN.py"
        build = [sys.executable, str(ROOT / "tools" / "build_main.py"), "--out", str(main_py)]
        build.append("--with-new")
        subprocess.run(build, cwd=ROOT, check=True)
        uv = Path(tmp) / "uv"
        uv.mkdir()
        files = {"MAIN.py": main_py} | CONTENTS | {f"uv/{p.name}": p for p in uv_builds(uv)}
        package = out / "fiam_finals.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for name, path in files.items():
                stored = path.suffix in (".zip", ".gz", ".mp4", ".pptx", ".pdf", ".parquet")
                kind = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                zf.write(path, name, compress_type=kind)
                sums[name] = sha256(path)
            zf.writestr("SHA256SUMS.json", json.dumps(sums, indent=1))
    with zipfile.ZipFile(package) as zf:
        bad = zf.testzip()
    if bad:
        raise SystemExit(f"{package.name}: {bad} is damaged")
    beside = {}
    (out / "START_HERE.txt").write_text(START, encoding="utf-8")
    beside["fiam_finals.zip"] = sha256(package)
    (out / "SHA256SUMS.json").write_text(json.dumps(beside, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e9
    print(f"wrote {out}: {len(sums)} files in the zip, {size:.1f} GB")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out")
