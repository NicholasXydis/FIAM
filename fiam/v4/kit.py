# The finals kit for clone + USB: export, setup and doctor (PLAN §15).

import hashlib
import json
import os
import platform
import re
import shutil
import string
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from fiam import kit as results

ROOT = Path(__file__).resolve().parents[2]
NAME = "fiam_finals"
MANIFEST = "MANIFEST.json"
LOCAL = ROOT / "out" / "kit"
HASHES = LOCAL / "hashes.json"
RECORD = ROOT / "data" / "KIT.json"
# The finals stick, FIAM_FINALS, when no drive is plugged in.
USB_GB = 249.3
GEMMA = "gemma-4-26B-A4B-it-UD-IQ4_XS.gguf"
# The Hugging Face models the text, voice and OCR steps load.
HF_MODELS = (
    "ProsusAI--finbert",
    "Systran--faster-whisper-small.en",
    "hexgrad--Kokoro-82M",
    "mlx-community--GLM-OCR-bf16",
    "mlx-community--Qwen3.5-9B-4bit",
)
# Never in the kit: SEC's nightly bulk file and scratch folders.
SKIP = ("data/edgar/submissions.zip", "data/amazon/raw/", "data/amazon/tmp/")
JUNK = (".part", ".partial", ".copy", ".DS_Store", ".pyc")
# Names Windows refuses, so a kit with them fails at export, not setup.
WINDOWS_BAD = re.compile(r'[<>:"|?*\x00-\x1f]|[. ]$|^(con|prn|aux|nul|com\d|lpt\d)(\.|$)', re.I)
# Already compressed, so stored in the zip as they are.
STORED = {".parquet", ".zip", ".gz", ".xz", ".gguf", ".safetensors", ".bin", ".pt"}
STORED |= {".mp4", ".mov", ".m4a", ".mp3", ".jpg", ".png", ".pdf", ".pptx", ".xlsx"}
# Each data folder every machine needs, and the part that holds it.
DATA = {
    "organisers": "data-organisers",
    "fiam_v1": "data-bundle",
    "edgar": "data-edgar",
    "noaa": "data-noaa",
    "v4/extracts": "data-stock",
    "carbon_arc": "data-carbon-arc",
    "amazon": "data-amazon",
    "finra": "data-finra",
}
# Installers and caches travel as plain files, needed before setup.
EXTRAS = ("installers", "caches")
# uv for each machine, the version the offline caches are built with.
UV = "0.12.18"
UV_BUILDS = {
    "mac-arm64": "uv-aarch64-apple-darwin.tar.gz",
    "mac-x64": "uv-x86_64-apple-darwin.tar.gz",
    "windows-x64": "uv-x86_64-pc-windows-msvc.zip",
    "linux-x64": "uv-x86_64-unknown-linux-gnu.tar.gz",
    "linux-arm64": "uv-aarch64-unknown-linux-gnu.tar.gz",
}
# Node 24 for each machine, as nodejs.org names its builds.
NODE = "https://nodejs.org/dist/latest-v24.x/"
NODE_BUILDS = {
    "mac-arm64": "darwin-arm64.tar.gz",
    "mac-x64": "darwin-x64.tar.gz",
    "windows-x64": "win-x64.zip",
    "linux-x64": "linux-x64.tar.xz",
    "linux-arm64": "linux-arm64.tar.xz",
}
# pnpm at the site's pinned version, as its releases name builds.
PNPM = "12.8.1"
PNPM_BUILDS = {
    "mac-arm64": "pnpm-darwin-arm64.tar.gz",
    "mac-x64": "pnpm-darwin-x64.tar.gz",
    "windows-x64": "pnpm-win32-x64.zip",
    "linux-x64": "pnpm-linux-x64.tar.gz",
    "linux-arm64": "pnpm-linux-arm64.tar.gz",
}
LICENSES = """# Licences and handling

- Organisers' files (data/organisers): competition use only, never redistributed.
- WRDS (data/fiam_v1, data/v4/extracts): licensed through McGill for the team's academic
  use. Private kit only, never public. Charts show derived results only.
- Carbon Arc (data/carbon_arc): derived results only, credited "Based in part on Carbon Arc
  data". Raw data never public. No training on MCP output. Human review on every use.
- SEC EDGAR, company facts and 13F (data/edgar): public, pulled under SEC's fair-access
  rules with a contact in the User-Agent and at most 5 requests a second.
- NOAA (data/noaa): US government public domain, cited as NOAA NCEI.
- Amazon Reviews 2023 (data/amazon): research use approved by the team leader, cited as
  Hou et al. 2024. Raw reviews never redistributed, only product-month summaries kept.
- Models (models/, huggingface/): each under its publisher's licence, unchanged.
"""
README = """FIAM finals kit

Private to the team. It holds licensed data, so never post or share it.

With a clone of the repo
  1. Install uv (https://docs.astral.sh/uv) or from installers/<your machine>/.
  2. In the clone:  uv run run.py setup     (finds this USB by itself)
  3. uv run run.py doctor   says what is missing and how to fix it.

Without a clone
  1. Copy MAIN.py from here into an empty folder on the computer. Never run it on the USB.
  2. In that folder:  uv run MAIN.py     (writes the code beside itself)
  3. Then:            uv run run.py setup <this fiam_finals folder>

Offline (no internet)
  1. Install uv from installers/<your machine>/.
  2. Unzip caches/<your machine>.zip into a folder on the computer, say C:/fiam_cache.
  3. Set these, then follow the steps above:
       UV_CACHE_DIR=C:/fiam_cache/uv  UV_PYTHON_INSTALL_DIR=C:/fiam_cache/python
       UV_OFFLINE=1  UV_LINK_MODE=copy  UV_PYTHON_PREFERENCE=only-managed
     (Windows PowerShell: $env:UV_OFFLINE="1" and so on.)
  4. The site offline: put Node and pnpm from installers/ on PATH, then in site/
       pnpm install --offline --frozen-lockfile --store-dir C:/fiam_cache/pnpm
     with PUPPETEER_SKIP_DOWNLOAD=1 set, since its browser is not in the kit.
  A machine without caches/<machine>.zip makes one with: uv run run.py caches <this folder>
  LightGBM's OpenMP library comes in the kit (models/openmp, part weights); nothing to install.

Before the day
  Rehearse once:  uv run run.py --world fake --finals mandates/case_2025.json
  Every book should show breaches 0 empty 0 and its largest country at 75% or less.

On the day, in the repo folder or the folder MAIN.py unpacked into
  1. Rules. uv run run.py --rules rules.pdf drafts mandates/<name>_draft.json with a quote
     for each limit, using the Gemma model the kit restored. Check it against the rules by
     hand. Without a GPU, edit a copy of mandates/case_2025.json instead. Add min_market_cap
     or exclude_sectors by hand if the rules set them.
  2. Data. uv run run.py --world <folder>. If their columns are named differently, copy
     fiam/world_columns.json into that folder as columns.json and change only what differs.
  3. Books. uv run run.py --world --finals mandates/<name>_draft.json. Add
     --window 2021-01 2025-06 or --capital 1e8 if the day asks for other months or size.
  4. Pack. Run the --pack command it prints.
  5. Deck. uv run run.py --finals-pack adds a slide with the day's book.
  The v4 finals command replaces steps 3 to 5 once it is built (plan step 11).

If something goes wrong
  uv is not found            py -m uv run run.py on Windows, python3 -m uv run run.py elsewhere
  No GPU or no model         write the mandate by hand, the books never need a GPU
  Other column names         columns.json beside the data
  Other currencies           name the currency column in columns.json, rates run to Oct 2026
  The rules cannot all hold  --finals names them before any run, then fix the mandate
  A film will not play       play deck/ai_crowd_short.mp4 on its own, the PDF has every page
  LightGBM will not load     setup restores it (part weights); else Mac brew install libomp,
                             Linux apt install libgomp1
  A file is damaged          setup names it, so export again from the Mac or use FIAM_COPY

Setup copies only missing files, checks each against MANIFEST.json and never overwrites
a file you already have, so running it twice is safe and a stopped run picks up again.
LICENSES.md says what each data source allows.
"""


# Now in UTC, for records.
def stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# This machine as the kit names it: mac-arm64, windows-x64, linux-x64.
def os_tag() -> str:
    system = {"Darwin": "mac", "Windows": "windows"}.get(platform.system(), "linux")
    arm = platform.machine().lower() in ("arm64", "aarch64")
    return f"{system}-{'arm64' if arm else 'x64'}"


# The Hugging Face cache, where every library looks for its models.
def hf_home() -> Path:
    return Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")


# Each part's sources and destinations; specific parts come first.
def parts() -> dict[str, list[tuple[Path, str]]]:
    def here(*names: str) -> list[tuple[Path, str]]:
        return [(ROOT / n, n) for n in names]

    hub = hf_home() / "hub"
    models = [(hub / f"models--{m}", f"huggingface/hub/models--{m}") for m in HF_MODELS]
    return {
        "data-organisers": here("data/organisers"),
        "data-bundle": here("data/fiam_v1"),
        "data-edgar-docs": here("data/edgar/docs"),
        "data-edgar-13f": here("data/edgar/13f"),
        "data-edgar": here("data/edgar"),
        "data-stock-taq": here("data/v4/extracts/taq_daily"),
        "data-stock": here("data/v4"),
        "data-noaa": here("data/noaa"),
        "data-carbon-arc": here("data/carbon_arc"),
        "data-amazon": here("data/amazon"),
        "data-finra": here("data/finra"),
        "data-other": here(
            "data/benchmarks", "data/edgar_cache.zip", "data/INVENTORY.json", "data/arcana"
        ),
        "results": here(*results.PARTS, "out/v4"),
        "media": here("deck", "out/media", "cache/vsco2"),
        "media-film": here("out/ad"),
        "weights-gemma": here(f"models/{GEMMA}", f"models/{GEMMA}.sha256.json"),
        "weights": here("models") + models,
        "docs": here("docs/PLAN.md", "docs/TEAM.md", "CLAUDE.md"),
    }


# Every file under a source as (file, kit name), junk left out.
def walk(source: Path, dest: str) -> list[tuple[Path, str]]:
    if source.is_file():
        found = [source]
    else:
        found = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else []
    out = []
    for path in found:
        name = dest if path == source else f"{dest}/{path.relative_to(source).as_posix()}"
        hidden = path.name.startswith("._") or "__pycache__" in name or "/blobs/" in name
        if not hidden and not name.endswith(JUNK) and not name.startswith(SKIP):
            out.append((path, name))
    return out


# The kit's files by part; each name once, case aside, Windows-safe.
def plan() -> dict[str, list[tuple[Path, str]]]:
    claimed, out = set(), {}
    for part, sources in parts().items():
        out[part] = []
        for source, dest in sources:
            for path, name in walk(source, dest):
                if name.lower() not in claimed:
                    claimed.add(name.lower())
                    out[part].append((path, name))
    unsafe = [n for items in out.values() for _, n in items if not portable(n)]
    if unsafe:
        raise SystemExit(f"Names Windows cannot hold, rename them first: {unsafe[:5]}")
    return out


# True when every piece of a name is legal on Windows, Mac and Linux.
def portable(name: str) -> bool:
    return all(piece and not WINDOWS_BAD.search(piece) for piece in name.split("/"))


# A file's SHA-256, reused while its size and time are unchanged.
def digest(path: Path, known: dict | None = None) -> str:
    known = {} if known is None else known
    stat = path.stat()
    mark = [stat.st_size, stat.st_mtime_ns]
    if known.get(str(path), [None])[:2] == mark:
        return known[str(path)][2]
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 24):
            sha.update(block)
    known[str(path)] = [*mark, sha.hexdigest()]
    return sha.hexdigest()


# Small text files compare without line endings, so a Windows checkout
# with CRLF still matches the kit's LF copy.
TEXT = {".json", ".sha256", ".csv", ".md", ".txt", ".py", ".toml", ".yml", ".yaml"}
TEXT_LIMIT = 50 << 20


# True when a file matches its kit entry: size, or hash when deep.
def matches(path: Path, entry: dict, deep: bool = False) -> bool:
    size = path.stat().st_size
    if path.suffix.lower() in TEXT and size <= TEXT_LIMIT and size != entry["size"]:
        data = path.read_bytes().replace(b"\r\n", b"\n")
        same = len(data) == entry["size"]
        return same and (not deep or hashlib.sha256(data).hexdigest() == entry["sha256"])
    if size != entry["size"]:
        return False
    return not deep or digest(path) == entry["sha256"]


# One fingerprint for a part: its names and hashes in order.
def fingerprint(entries: dict[str, str]) -> str:
    lines = "".join(f"{name} {sha}\n" for name, sha in sorted(entries.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


# The manifest on the kit, or an empty one for a new kit.
def load(folder: Path) -> dict:
    path = folder / MANIFEST
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"parts": {}, "files": {}, "extras": {}}


# Saves the manifest whole, so a stopped export leaves a true one.
def save(folder: Path, state: dict) -> None:
    temp = folder / (MANIFEST + ".part")
    temp.write_text(json.dumps(state | {"made_at": stamp()}, indent=1), encoding="utf-8")
    temp.replace(folder / MANIFEST)


# Copies a file through a part file, so the target is whole or absent.
def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    shutil.copyfile(source, temp)
    temp.replace(target)


# Writes one part's zip beside the old one, checked, then swaps it in.
def write_part(folder: Path, part: str, items: list, hashes: dict, state: dict) -> None:
    final = folder / "parts" / f"{part}.zip"
    temp = final.with_name(final.name + ".part")
    final.parent.mkdir(parents=True, exist_ok=True)
    need = sum(path.stat().st_size for path, _ in items) + 2**28
    # Short of room, the old copy goes first and the manifest says so.
    if shutil.disk_usage(folder).free < need and final.exists():
        drop(folder, part, state)
    with zipfile.ZipFile(temp, "w", allowZip64=True) as zf:
        for path, name in items:
            info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
            stored = path.suffix.lower() in STORED
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            sha = hashlib.sha256()
            with path.open("rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                while block := src.read(1 << 24):
                    sha.update(block)
                    dst.write(block)
            if sha.hexdigest() != hashes[name]:
                raise SystemExit(f"{name} changed while exporting. Fix: run export again")
    with zipfile.ZipFile(temp) as zf:
        bad, names = zf.testzip(), zf.namelist()
    if bad or names != [name for _, name in items]:
        temp.unlink()
        raise SystemExit(f"{part}: the written zip failed its check ({bad}). Fix: export again")
    temp.replace(final)
    entries = {name: hashes[name] for _, name in items}
    sizes = {name: path.stat().st_size for path, name in items}
    state["parts"][part] = {
        "zip": f"parts/{part}.zip",
        "zip_bytes": final.stat().st_size,
        "files": len(items),
        "bytes": sum(sizes.values()),
        "fingerprint": fingerprint(entries),
    }
    state["files"] = {n: e for n, e in state["files"].items() if e["part"] != part}
    for name, sha in entries.items():
        state["files"][name] = {"part": part, "size": sizes[name], "sha256": sha}
    save(folder, state)


# Removes a part from the kit and its manifest.
def drop(folder: Path, part: str, state: dict) -> None:
    state["parts"].pop(part, None)
    state["files"] = {n: e for n, e in state["files"].items() if e["part"] != part}
    save(folder, state)
    (folder / "parts" / f"{part}.zip").unlink(missing_ok=True)


# Writes MAIN.py from today's code, new files included.
def main_py(folder: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        built = Path(tmp) / "MAIN.py"
        command = [sys.executable, str(ROOT / "tools" / "build_main.py"), "--with-new"]
        subprocess.run([*command, "--out", str(built)], cwd=ROOT, check=True)
        copy(built, folder / "MAIN.py")


# The installers and caches made here, as (file, kit name).
def extras() -> list[tuple[Path, str]]:
    found = [p for e in EXTRAS if (LOCAL / e).is_dir() for p in (LOCAL / e).rglob("*")]
    files = sorted(p for p in found if p.is_file() and not p.name.endswith(JUNK))
    return [(p, p.relative_to(LOCAL).as_posix()) for p in files]


# Prints each part's size and the total against the USB.
def budget(chosen: dict, skip: set[str], folder: Path | None) -> float:
    total = 0
    for part, items in chosen.items():
        size = sum(path.stat().st_size for path, _ in items)
        mark = "  (skipped)" if part in skip else ""
        total += 0 if part in skip else size
        print(f"  {part:17} {len(items):8,} files {size / 1e9:7.2f} GB{mark}")
    more = sum(path.stat().st_size for path, _ in extras())
    print(f"  {'installers+caches':17} {'':14} {more / 1e9:7.2f} GB")
    longest = max((len(n) for items in chosen.values() for _, n in items), default=0)
    drive = folder.parent if folder and folder.parent.exists() else None
    room = shutil.disk_usage(drive).total / 1e9 if drive else USB_GB
    print(f"Kit: {(total + more) / 1e9:.1f} GB of {room:.0f}; longest name {longest}")
    if drive:
        print(f"Free on {drive}: {shutil.disk_usage(drive).free / 1e9:.1f} GB")
    for items in parts().values():
        for source, _ in items:
            if not source.exists():
                print(f"  not found, left out: {source}")
    return (total + more) / 1e9


# Writes the kit into folder, rewriting only the parts that changed.
def export(folder: Path, dry: bool = False, skip: set[str] = frozenset()) -> int:
    chosen = plan()
    budget(chosen, set(skip), folder)
    if dry:
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    known = json.loads(HASHES.read_text(encoding="utf-8")) if HASHES.exists() else {}
    state, changed = load(folder), {}
    for part, items in chosen.items():
        if part in skip or not items:
            continue
        hashes = {name: digest(path, known) for path, name in items}
        old, zipped = state["parts"].get(part, {}), folder / "parts" / f"{part}.zip"
        same = old.get("fingerprint") == fingerprint(hashes) and zipped.exists()
        if same and zipped.stat().st_size == old.get("zip_bytes"):
            print(f"{part}: unchanged")
        else:
            changed[part] = hashes
    HASHES.parent.mkdir(parents=True, exist_ok=True)
    HASHES.write_text(json.dumps(known), encoding="utf-8")
    # Room check before writing anything: new parts less the old ones.
    new = sum(p.stat().st_size for part in changed for p, _ in chosen[part])
    new += sum(p.stat().st_size for p, n in extras() if not (folder / n).exists()) + 2**27
    old = sum(state["parts"].get(part, {}).get("zip_bytes", 0) for part in changed)
    free = shutil.disk_usage(folder).free
    if new - old > free:
        print(f"Needs {(new - old) / 1e9:.1f} GB more and {free / 1e9:.1f} GB is free.")
        print("Fix: export --skip <part>, or a bigger drive")
        return 1
    for part, hashes in changed.items():
        print(f"{part}: writing {len(chosen[part]):,} files", flush=True)
        write_part(folder, part, chosen[part], hashes, state)
    for part in [p for p in state["parts"] if p not in chosen]:
        drop(folder, part, state)
    for path, name in extras():
        sha = digest(path, known)
        if state["extras"].get(name, {}).get("sha256") != sha or not (folder / name).exists():
            copy(path, folder / name)
        state["extras"][name] = {"size": path.stat().st_size, "sha256": sha}
    main_py(folder)
    (folder / "LICENSES.md").write_text(LICENSES, encoding="utf-8")
    (folder / "README.txt").write_text(README, encoding="utf-8")
    state["extras"]["MAIN.py"] = {"sha256": digest(folder / "MAIN.py")}
    save(folder, state)
    # Anything else in the folder is reported and left alone.
    own = {*EXTRAS, "parts", MANIFEST, "MAIN.py", "LICENSES.md", "README.txt"}
    for path in sorted(folder.iterdir()):
        if path.name not in own and not path.name.startswith("._"):
            print(f"Not part of the kit, left alone: {path.name}")
    print(f"Kit written to {folder}: {len(state['files']):,} files in {len(state['parts'])} parts")
    return 0


# The kit folder: the one given, else fiam_finals on any drive.
def find(given: str | None = None) -> Path | None:
    if given:
        path = Path(given).expanduser()
        return next((p for p in (path, path / NAME) if (p / MANIFEST).exists()), None)
    roots = [Path("/Volumes"), Path("/media"), Path("/mnt"), Path("/run/media")]
    roots += [Path(f"{letter}:/") for letter in string.ascii_uppercase[2:]]
    found = []
    for root in roots:
        for depth in ("", "*/", "*/*/"):
            try:
                found += [p.parent for p in root.glob(f"{depth}{NAME}/{MANIFEST}")]
            except OSError:
                break
    found = sorted(set(found))
    if len(found) > 1:
        print(f"Several kits found, pass one: {[str(p) for p in found]}")
    return found[0] if len(found) == 1 else None


# A drive to export to: the one given, else the only USB plugged in.
def target(given: str | None = None) -> Path | None:
    if given:
        path = Path(given).expanduser()
        return path if path.name == NAME else path / NAME
    kit = find()
    if kit:
        return kit
    drives = [p for p in Path("/Volumes").glob("*") if p.is_dir() and not p.is_symlink()]
    return drives[0] / NAME if len(drives) == 1 else None


# A kit name as a path here; refuses one that would land outside.
def destination(name: str, root: Path = ROOT) -> Path:
    inner = name.removeprefix("huggingface/")
    base = hf_home() if inner != name else root
    if not portable(inner) or Path(inner).is_absolute() or ".." in Path(inner).parts:
        raise ValueError(f"unsafe name in the kit: {name}")
    return base / inner


# Restores every missing file, each checked, and never overwrites one.
def setup(kit: Path, skip: set[str] = frozenset(), root: Path = ROOT) -> int:
    state = load(kit)
    todo, kept, differs = {}, 0, []
    for name, entry in state["files"].items():
        if entry["part"] in skip:
            continue
        path = destination(name, root)
        if path.exists():
            kept += 1
            if not matches(path, entry):
                differs.append(name)
        else:
            todo.setdefault(entry["part"], []).append(name)
    need = sum(state["files"][n]["size"] for names in todo.values() for n in names)
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    if need + 1e9 > free:
        print(f"Setup needs {need / 1e9:.1f} GB here and {free / 1e9:.1f} GB is free.")
        print("Fix: free some space, or setup --skip <part> (parts in MANIFEST.json)")
        return 1
    damaged = []
    for part, names in todo.items():
        bad = restore(kit / state["parts"][part]["zip"], names, state["files"], root)
        print(f"{part}: {len(names) - len(bad):,} restored", flush=True)
        damaged += bad
    files = {n: e for n, e in state["files"].items() if e["part"] not in skip}
    record = {"kit": str(kit), "restored_at": stamp(), "skipped": sorted(skip), "files": files}
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / RECORD.name).write_text(json.dumps(record, indent=1), encoding="utf-8")
    restored = sum(map(len, todo.values())) - len(damaged)
    print(f"Kept {kept:,} files already here; restored {restored:,}.")
    for name in differs[:10]:
        print(f"  yours differs from the kit, kept yours: {name}")
    for name in damaged[:10]:
        print(f"  damaged on the kit, not restored: {name}")
    if damaged:
        print("Fix: export again from the Mac, or use the second drive's copy")
        return 1
    return 0


# Extracts named files from one zip through part files, checked.
def restore(zipped: Path, names: list[str], files: dict, root: Path) -> list[str]:
    if not zipped.exists():
        return names
    damaged = []
    with zipfile.ZipFile(zipped) as zf:
        for name in names:
            path = destination(name, root)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".part")
            sha = hashlib.sha256()
            try:
                with zf.open(name) as src, temp.open("wb") as out:
                    while block := src.read(1 << 24):
                        sha.update(block)
                        out.write(block)
            except KeyError, OSError, zipfile.BadZipFile:
                temp.unlink(missing_ok=True)
                damaged.append(name)
                continue
            if sha.hexdigest() != files[name]["sha256"]:
                temp.unlink()
                damaged.append(name)
                continue
            temp.replace(path)
    return damaged


# A setting from the environment or .env; values are never printed.
def setting(name: str) -> str:
    found = os.environ.get(name, "")
    env = ROOT / ".env"
    if not found and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                found = value.split("#")[0].strip()
    return found


# Checks this machine end to end, with one fix per problem.
def doctor(deep: bool = False) -> int:
    problems, notes = [], []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    low = tuple(int(x) for x in project["requires-python"].split(",")[0].strip(">=").split("."))
    if sys.version_info[:2] != low[:2]:
        fix = f"uv python install {low[0]}.{low[1]}"
        problems.append((f"Python {sys.version.split()[0]}", fix))
    if not shutil.which("uv"):
        problems.append(("uv not found", "install uv, or from the kit's installers/ folder"))
    missing = packages(project["dependencies"])
    problems += missing or openmp()
    skipped = json.loads(RECORD.read_text(encoding="utf-8"))["skipped"] if RECORD.exists() else []
    for folder, part in DATA.items():
        path = ROOT / "data" / folder
        if path.is_dir() and any(path.iterdir()):
            continue
        rows = notes if part in skipped else problems
        rows.append((f"data/{folder} is missing", f"uv run run.py setup (part {part})"))
    if not missing:
        from fiam import data

        if (data.DIR / "manifest.json").exists() and data.checksum_mismatches():
            problems.append(("organisers' files differ from the readme", "copy them again"))
    problems += kit_files(deep)
    if not RECORD.exists():
        notes.append(("no kit restored here", "uv run run.py --data verify checks each file"))
    for key, use in (("SEC_CONTACT", "SEC downloads"), ("API_AUTH_TOKEN", "Carbon Arc")):
        if not setting(key):
            notes.append((f"{key} not set, needed only for {use}", "add it to .env"))
    notes += llm()
    for tool, use in (("git", "commits"), ("node", "the site"), ("pnpm", "the site")):
        if not shutil.which(tool):
            notes.append((f"{tool} not found, needed for {use}", f"install {tool}"))
    if shutil.disk_usage(ROOT).free < 5e9:
        notes.append(("under 5 GB free", "free some space before a full run"))
    for label, rows in (("Problem", problems), ("Note", notes)):
        for what, fix in rows:
            print(f"{label}: {what}. Fix: {fix}")
    print(f"Doctor: {len(problems)} problems, {len(notes)} notes.")
    return 1 if problems else 0


# Every pinned package installed at its pinned version.
def packages(pins: list[str]) -> list[tuple[str, str]]:
    from packaging.requirements import Requirement

    out = []
    for pin in pins:
        need = Requirement(pin)
        if need.marker and not need.marker.evaluate():
            continue
        try:
            have = metadata.version(need.name)
        except metadata.PackageNotFoundError:
            have = None
        if have is None or have.split("+")[0] not in need.specifier:
            out.append((f"{need.name} {have or 'missing'}, pinned {need.specifier}", "uv sync"))
    return out


# LightGBM loads, with the system's OpenMP or the kit's copy (B9).
def openmp() -> list[tuple[str, str]]:
    try:
        from fiam import openmp as runtime

        runtime.preload()
        import lightgbm  # noqa: F401
    except (ImportError, OSError) as err:
        fixes = {"Darwin": "uv run run.py setup (part weights), or brew install libomp"}
        fixes["Linux"] = "uv run run.py setup (part weights), or sudo apt install libgomp1"
        fix = fixes.get(platform.system(), "install the OpenMP runtime LightGBM needs")
        return [(f"lightgbm cannot load ({str(err)[:60]})", fix)]
    return []


# Restored files still match the kit: sizes, or hashes when deep.
def kit_files(deep: bool) -> list[tuple[str, str]]:
    if not RECORD.exists():
        return []
    files = json.loads(RECORD.read_text(encoding="utf-8"))["files"]
    out = []
    # Inputs only: results, media and docs are meant to change.
    for name, entry in files.items():
        if not entry["part"].startswith(("data-", "weights")):
            continue
        path = destination(name)
        if not path.exists():
            out.append((f"{name} is missing", "uv run run.py setup"))
        elif not matches(path, entry, deep):
            out.append((f"{name} differs from the kit", "delete it, then uv run run.py setup"))
    return out[:20]


# The AI desk: the Windows server if set, else saved answers.
def llm() -> list[tuple[str, str]]:
    url = os.environ.get("FIAM_LLM_URL", "").rstrip("/")
    if not url:
        return [("FIAM_LLM_URL not set, the AI desk replays saved answers", "set it on the day")]
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as response:
            if response.status == 200:
                return []
    except OSError:
        pass
    return [("the LLM at FIAM_LLM_URL is not answering", "start llama-server, check Tailscale")]


# Downloads uv, Node and pnpm for every machine, each checked.
def installers() -> int:
    folder = LOCAL / "installers"
    for tag, name in UV_BUILDS.items():
        base = f"https://github.com/astral-sh/uv/releases/download/{UV}/{name}"
        with urllib.request.urlopen(base + ".sha256", timeout=60) as response:
            fetch(base, folder / tag / name, response.read().decode().split()[0])
    with urllib.request.urlopen(NODE + "SHASUMS256.txt", timeout=60) as response:
        sums = dict(reversed(line.split()) for line in response.read().decode().splitlines())
    for tag, ending in NODE_BUILDS.items():
        name = next(n for n in sums if n.startswith("node-v24") and n.endswith(ending))
        fetch(NODE + name, folder / tag / name, sums[name])
    api = f"https://api.github.com/repos/pnpm/pnpm/releases/tags/v{PNPM}"
    with urllib.request.urlopen(api, timeout=60) as response:
        assets = {a["name"]: a for a in json.load(response)["assets"]}
    for tag, name in PNPM_BUILDS.items():
        asset = assets[name]
        fetch(asset["browser_download_url"], folder / tag / name, asset["digest"][7:])
    print(f"Installers in {folder}")
    return 0


# One download, kept only when it matches its published SHA-256.
def fetch(url: str, path: Path, sha: str) -> None:
    if path.exists() and digest(path) == sha:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=300) as response, temp.open("wb") as out:
        shutil.copyfileobj(response, out, 1 << 22)
    if digest(temp) != sha:
        temp.unlink()
        raise SystemExit(f"{path.name} does not match its published SHA-256")
    temp.replace(path)
    print(f"  {path.parent.name}/{path.name}", flush=True)


# The kit's own uv for this machine, so caches match the installer.
def kit_uv(kit: Path | None) -> str:
    tag, name = os_tag(), UV_BUILDS.get(os_tag(), "")
    archives = [f / "installers" / tag / name for f in (kit, LOCAL) if f]
    archive = next((a for a in archives if a.exists()), None)
    if archive is None:
        print(f"No kit uv for {tag}; using the uv on PATH, which may differ from {UV}")
        return "uv"
    home = LOCAL / "build" / "uv"
    shutil.rmtree(home, ignore_errors=True)
    shutil.unpack_archive(archive, home)
    found = next(p for p in home.rglob("uv*") if p.name in ("uv", "uv.exe"))
    found.chmod(found.stat().st_mode | 0o111)
    return str(found)


# This machine's offline packages: uv cache, Python and pnpm store.
def caches(kit: Path | None = None) -> int:
    tag, uv = os_tag(), kit_uv(kit)
    # Windows builds at a short path, inside its 260-character limit.
    short = Path(os.environ.get("SystemDrive", "C:") + "/fiam_kit_build")
    work = (short if tag.startswith("windows") else LOCAL / "build") / tag
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # The MAIN.py export writes, so its packages are the ones cached.
    main_py(work)
    env = os.environ | {
        "UV_CACHE_DIR": str(work / "uv"),
        "UV_PYTHON_INSTALL_DIR": str(work / "python"),
        "UV_PROJECT_ENVIRONMENT": str(work / "venv"),
    }
    steps = [
        [uv, "python", "install", "3.14"],
        [uv, "sync", "--frozen"],
        [uv, "sync", "--script", str(work / "MAIN.py")],
        [uv, "sync", "--script", str(ROOT / "site" / "ad" / "web.py")],
    ]
    # pnpm fetches into a scratch copy; site/node_modules stays as is.
    if shutil.which("pnpm"):
        scratch = work / "site"
        scratch.mkdir(parents=True)
        for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
            if (ROOT / "site" / name).exists():
                shutil.copyfile(ROOT / "site" / name, scratch / name)
        pnpm = ["pnpm", "--dir", str(scratch), "fetch", "--config.ignore-scripts=true"]
        steps.append([*pnpm, "--store-dir", str(work / "pnpm")])
    for step in steps:
        print(" ".join(Path(step[0]).name if i == 0 else s for i, s in enumerate(step)))
        subprocess.run(step, cwd=ROOT, env=env, check=True)
    # Environments are rebuilt offline from the cache, so they stay out.
    for built in [work / "venv", work / "site", *(work / "uv").glob("environments-v*")]:
        shutil.rmtree(built, ignore_errors=True)
    (work / "MAIN.py").unlink(missing_ok=True)
    out = LOCAL / "caches" / f"{tag}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, True, strict_timestamps=False) as zf:
        for path in sorted(p for p in work.rglob("*") if p.is_file()):
            zf.write(path, path.relative_to(work).as_posix())
    temp.replace(out)
    shutil.rmtree(work, ignore_errors=True)
    print(f"{out}: {out.stat().st_size / 1e9:.2f} GB")
    if kit:
        state = load(kit)
        copy(out, kit / "caches" / out.name)
        state["extras"][f"caches/{out.name}"] = {"size": out.stat().st_size, "sha256": digest(out)}
        save(kit, state)
        print(f"Copied to {kit / 'caches' / out.name}")
    return 0


# Splits a command line into the verb, a folder and --skip parts.
def options(args: list[str]) -> tuple[str, str | None, set[str]]:
    verb, given, skip = (args[0] if args else ""), None, set()
    rest = iter(args[1:])
    for arg in rest:
        if arg == "--skip":
            skip = {p for p in next(rest, "").split(",") if p}
        elif not arg.startswith("--") and given is None:
            given = arg
    return verb, given, skip


# export | setup | doctor | installers | caches, with their options.
def main(args: list[str]) -> int:
    verb, given, skip = options(args)
    if verb == "export":
        folder = target(given)
        if folder is None and "--dry-run" not in args:
            print("No USB found. Fix: uv run run.py export <folder>")
            return 1
        return export(folder, "--dry-run" in args, skip)
    if verb == "setup":
        kit = find(given)
        if kit is None:
            print("No kit found. Fix: plug in the USB, or uv run run.py setup <kit folder>")
            return 1
        return setup(kit, skip) or doctor()
    if verb == "doctor":
        return doctor("--deep" in args)
    if verb == "installers":
        return installers()
    if verb == "caches":
        return caches(find(given) if given else None)
    print("Usage: uv run run.py export | setup | doctor | installers | caches")
    return 2
