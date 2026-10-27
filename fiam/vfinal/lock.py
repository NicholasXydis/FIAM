# The data gate: rows public after 2020 open only while it holds.

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "frozen" / "vfinal"
OPENED = FROZEN / "opened.json"
SHA, OUTPUTS = FROZEN / "vfinal.sha256", FROZEN / "outputs.json"
# The record's fields that must hold a value for the window to open.
FIELDS = ("window", "first_freeze", "first_opened")
# The code and settings folders, hashed whole, as repository paths.
CODE, SETTINGS = "fiam/vfinal", "versions/vfinal"
# Single files the stages read beside the code folder.
EXTRA = ("fiam/agents/harness.py",)


# A path as the repository root names it.
def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# The sha256 of one file, read in blocks.
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# Every code and settings file on disk, so a new file is noticed.
def code() -> list[str]:
    found = [p for p in (ROOT / CODE).rglob("*.py") if "__pycache__" not in p.parts]
    found += [p for p in (ROOT / SETTINGS).rglob("*") if p.suffix in (".json", ".md")]
    return sorted({*(rel(p) for p in found), *EXTRA})


# The files under out/ the headline stages read and never rewrite.
def pins() -> list[str]:
    from fiam.vfinal import final, headline
    from fiam.vfinal.construct import book, exam
    from fiam.vfinal.forecast import grid

    files = [
        book.FORECASTS,
        grid.OUT / f"validate_{final.MODELS_AT}.json",
        *(book.OUT / f"exam_{s}_{exam.EXAM_AT}.json" for s in ("designs", "tests", "brake")),
        final.OUT / "labels_sealed.parquet",
        headline.SUE_BACKUP,
        headline.CARD_BACKUP,
    ]
    return sorted(rel(p) for p in files)


# Everything the lock hashes: code, settings, the record and the pins.
def hashed() -> list[str]:
    return sorted({*code(), rel(OPENED), rel(OUTPUTS), *pins()})


# The headline folder and run files of each final pick, by commit.
def final_picks() -> dict[str, Path]:
    from fiam.vfinal import headline

    found = {}
    for path in sorted(headline.BASE.glob("pick_*.json")):
        body = json.loads(path.read_text())
        if body.get("final"):
            at = path.stem.removeprefix("pick_")
            found[at] = headline.folder(body["cadence"], body["limits"])
    return found


# Every file one headline run wrote, by repository path and digest.
def outputs(at: str | None = None) -> dict:
    from fiam.vfinal import headline

    picks = final_picks()
    if at is None and len(picks) != 1:
        raise SystemExit(f"refused: {len(picks)} final picks found, name one commit to lock")
    at = (at or next(iter(picks)))[:12]
    if at not in picks:
        raise SystemExit(f"refused: no final pick at {at}")
    files = [*headline.BASE.glob(f"*_{at}.*"), *picks[at].glob(f"*_{at}.*")]
    found = {rel(p): digest(p) for p in sorted(files) if p.is_file()}
    return {"run_at": at, "headline": rel(picks[at]), "files": found}


# Writes outputs.json, then the sorted hash list; returns the list.
def lock(at: str | None = None) -> list[str]:
    if not OPENED.is_file():
        raise SystemExit(f"refused: {rel(OPENED)} is missing")
    missing = [n for n in pins() if not (ROOT / n).is_file()]
    if missing:
        raise SystemExit("refused: pinned files missing\n  " + "\n  ".join(missing))
    made = outputs(at)
    FROZEN.mkdir(parents=True, exist_ok=True)
    OUTPUTS.write_text(json.dumps(made, indent=1) + "\n")
    lines = [f"{digest(ROOT / name)}  {name}" for name in hashed()]
    SHA.write_text("\n".join(lines) + "\n")
    return lines


# Every hash in the lock recomputed: the mismatches, none if sound.
def verify() -> list[str]:
    if not SHA.is_file():
        return [f"{rel(SHA)}: missing"]
    bad, listed = [], set()
    for line in SHA.read_text().splitlines():
        want, _, name = line.partition("  ")
        listed.add(name)
        path = ROOT / name
        if not name or not path.is_file():
            bad.append(f"{name}: missing")
        elif digest(path) != want:
            bad.append(f"{name}: changed")
    # Every code and settings file must be listed, a new one included.
    must = {*code(), rel(OPENED), rel(OUTPUTS)}
    bad += [f"{n}: not in the lock" for n in sorted(must - listed)]
    return bad


# Each recorded output against the disk: changed, and not present here.
def compare() -> tuple[list[str], list[str]]:
    if not OUTPUTS.is_file():
        return [f"{rel(OUTPUTS)}: missing"], []
    changed, absent = [], []
    for name, want in json.loads(OUTPUTS.read_text())["files"].items():
        path = ROOT / name
        if not path.is_file():
            absent.append(name)
        elif digest(path) != want:
            changed.append(f"{name}: changed")
    return changed, absent


# One git command in the repository, never raising on a refusal.
def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


# Whether HEAD is clean, pushed and holds the opening record.
def recorded() -> bool:
    if not OPENED.is_file():
        return False
    body = json.loads(OPENED.read_text())
    if not all(body.get(k) for k in FIELDS):
        return False
    status = git("status", "--porcelain", "--untracked-files=all")
    if status.returncode or status.stdout.strip():
        return False
    pushed = git("branch", "-r", "--contains", "HEAD")
    if pushed.returncode or not pushed.stdout.strip():
        return False
    return git("cat-file", "-e", f"HEAD:{rel(OPENED)}").returncode == 0


# Open if the lock verifies; with no lock, if HEAD holds the record.
def opened() -> bool:
    try:
        return not verify() if SHA.is_file() else recorded()
    except OSError, ValueError, subprocess.SubprocessError:
        return False


# python -m fiam.vfinal.lock lock [commit] | verify
if __name__ == "__main__":
    verb, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if verb == "lock" and len(rest) < 2:
        done = lock(rest[0] if rest else None)
        print(f"wrote {rel(SHA)}: {len(done)} files hashed, and {rel(OUTPUTS)}")
    elif verb == "verify" and not rest:
        problems = verify()
        print("\n".join(problems) if problems else f"{rel(SHA)} verifies")
        sys.exit(1 if problems else 0)
    else:
        raise SystemExit("python -m fiam.vfinal.lock lock [commit] | verify")
