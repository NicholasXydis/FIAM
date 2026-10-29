# The fund's lock: code, recipe, inputs and outputs by sha256.

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

from fiam.vfinal import config

ROOT = config.ROOT
SHA = config.FROZEN / "vfinal.sha256"
RECIPE, INPUTS, OUTPUTS = (config.FROZEN / f"{n}.json" for n in ("recipe", "inputs", "outputs"))
# The record file the data gate needs; never rewritten.
OPENED = config.FROZEN / "opened.json"
# The record's fields that must hold a value for the window to open.
FIELDS = ("window", "first_freeze", "first_opened")
# Saved results the build reads, pinned by hash.
PINNED = config.FROZEN / "pinned"
# The lock's own files, never counted as a build's inputs.
OWN = (SHA, RECIPE, INPUTS, OUTPUTS, OPENED)
# The code the lock holds: the package and its tests.
CODE = ("fiam/vfinal", "tests/test_vfinal.py")
# Packages whose versions the inputs file records.
PACKAGES = ("numpy", "pandas", "scipy", "pyarrow", "cvxpy", "clarabel", "numba", "llvmlite",
            "lightgbm", "statsmodels")  # fmt: skip
# Outputs that hold a clock time, never hashed.
TIMED = ("logs/",)
TIMED_NAMES = ("report_",)


# The sha256 of one file, read in blocks.
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# A path as the repository root names it, else absolute.
def rel(path: Path) -> str:
    for p, root in ((Path(path).absolute(), config.ROOT.absolute()),
                    (Path(path).resolve(), config.ROOT.resolve())):  # fmt: skip
        if p.is_relative_to(root):
            return p.relative_to(root).as_posix()
    return str(path)


# Every code file the lock covers, as repository paths.
def code() -> list[str]:
    out = []
    for part in CODE:
        p = config.ROOT / part
        found = p.rglob("*.py") if p.is_dir() else [p]
        out += [rel(f) for f in found if "__pycache__" not in f.parts and f.is_file()]
    return sorted(out)


# The record and the pinned results, hashed beside the code.
def kept() -> list[str]:
    return sorted([rel(OPENED), *(rel(p) for p in PINNED.rglob("*") if p.is_file())])


# Every deterministic output under a run folder, by its own path.
def outputs(folder: Path) -> dict:
    found = {}
    for p in sorted(Path(folder).rglob("*")):
        name = p.relative_to(folder).as_posix()
        if not p.is_file() or name.startswith(TIMED) or name.startswith("evidence/"):
            continue
        if p.name.startswith(TIMED_NAMES) or p.suffix == ".tmp":
            continue
        found[name] = digest(p)
    return found


# Files the build opened for reading, by a hook on Python and pyarrow.
@contextmanager
def traced():
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    seen: set = set()

    # Records one path the build reads.
    def note(path) -> None:
        if isinstance(path, (str, Path)):
            seen.add(os.path.abspath(path))

    # Python's own opens, read modes only.
    def hook(event, args):
        if event == "open" and args and (len(args) < 2 or "r" in str(args[1] or "r")):
            note(args[0])

    keep = (pq.read_table, pq.ParquetFile.__init__, ds.dataset)

    # pyarrow's reads, which bypass Python's open.
    def table(source, *a, **k):
        note(source)
        return keep[0](source, *a, **k)

    # A ParquetFile's own path.
    def pfile(self, source, *a, **k):
        note(source)
        return keep[1](self, source, *a, **k)

    # A dataset's own path.
    def dataset(source, *a, **k):
        note(source)
        return keep[2](source, *a, **k)

    sys.addaudithook(hook)
    pq.read_table, pq.ParquetFile.__init__, ds.dataset = table, pfile, dataset
    try:
        yield seen
    finally:
        pq.read_table, pq.ParquetFile.__init__, ds.dataset = keep


# The data inputs among the paths read: not code, not this run's own.
def data_inputs(seen: set) -> dict:
    out_dir, root = config.OUT.absolute(), config.ROOT.absolute()
    own = {p.absolute() for p in OWN}
    keep = {}
    # A partitioned table read as a folder counts every file in it.
    found = set()
    for s in seen:
        p = Path(s)
        found |= {str(f) for f in p.rglob("*") if f.is_file()} if p.is_dir() else {s}
    for s in sorted(found):
        p = Path(s)
        if not p.is_file() or p.suffix in (".py", ".pyc", ".so", ".pth", ".dylib"):
            continue
        if p.absolute() in own:
            continue
        if out_dir in p.parents or "site-packages" in p.parts or ".venv" in p.parts:
            continue
        if not p.is_relative_to(root) or p.name.startswith("."):
            continue
        if p.parts[len(root.parts)] in ("fiam", "tests", ".git"):
            continue
        keep[rel(p)] = digest(p)
    return keep


# The package versions the build ran under.
def versions() -> dict:
    return {k: metadata.version(k) for k in PACKAGES} | {"python": sys.version.split()[0]}


# Writes recipe, inputs, outputs and the hash list; returns the list.
def lock(inputs: dict) -> list[str]:
    if not record():
        raise SystemExit(f"refused: {rel(OPENED)} is missing or incomplete")
    config.FROZEN.mkdir(parents=True, exist_ok=True)
    RECIPE.write_text(json.dumps(config.recipe(), indent=1) + "\n")
    INPUTS.write_text(json.dumps({"files": inputs, "versions": versions()}, indent=1) + "\n")
    OUTPUTS.write_text(json.dumps({"folder": rel(config.OUT), "files": outputs(config.OUT)},
                                  indent=1) + "\n")  # fmt: skip
    names = [*code(), *kept(), rel(RECIPE), rel(INPUTS), rel(OUTPUTS)]
    lines = [f"{digest(config.ROOT / n)}  {n}" for n in names]
    SHA.write_text("\n".join(lines) + "\n")
    return lines


# Every lock hash, the recipe and the inputs recomputed: the problems.
def verify(data: bool = True) -> list[str]:
    if not SHA.is_file():
        return [f"{rel(SHA)}: missing"]
    bad, listed = [], set()
    for line in SHA.read_text().splitlines():
        want, _, name = line.partition("  ")
        listed.add(name)
        path = config.ROOT / name
        if not path.is_file():
            bad.append(f"{name}: missing")
        elif digest(path) != want:
            bad.append(f"{name}: changed")
    bad += [f"{n}: not in the lock" for n in [*code(), *kept()] if n not in listed]
    if json.loads(RECIPE.read_text()) != json.loads(json.dumps(config.recipe())):
        bad.append(f"{rel(RECIPE)}: config.py no longer gives this recipe")
    # The gate stops here: code, record, pins and recipe, no data hashing.
    if not data:
        return bad
    got = json.loads(INPUTS.read_text())
    for name, want in got["files"].items():
        path = config.ROOT / name if not Path(name).is_absolute() else Path(name)
        if not path.is_file():
            bad.append(f"input {name}: missing")
        elif digest(path) != want:
            bad.append(f"input {name}: changed")
    for k, v in got["versions"].items():
        now = versions().get(k)
        if now != v:
            bad.append(f"package {k}: {now}, locked {v}")
    return bad


# A rebuild folder's outputs against the locked ones.
def compare(folder: Path) -> tuple[list[str], list[str], int]:
    want = json.loads(OUTPUTS.read_text())["files"]
    have = outputs(folder)
    changed = [n for n, h in want.items() if n in have and have[n] != h]
    absent = [n for n in want if n not in have]
    extra = [n for n in have if n not in want]
    return changed + [f"{n}: not in the lock" for n in extra], absent, len(want)


# Whether the gate record holds every field it must.
def record() -> bool:
    if not OPENED.is_file():
        return False
    body = json.loads(OPENED.read_text())
    return all(body.get(k) for k in FIELDS)


# One git command in the repository, never raising on a refusal.
def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


# Whether HEAD is clean, pushed and holds the gate record.
def recorded() -> bool:
    if not record():
        return False
    status = git("status", "--porcelain", "--untracked-files=all")
    if status.returncode or status.stdout.strip():
        return False
    pushed = git("branch", "-r", "--contains", "HEAD")
    if pushed.returncode or not pushed.stdout.strip():
        return False
    return git("cat-file", "-e", f"HEAD:{rel(OPENED)}").returncode == 0


# The data gate: open if the record holds and the lock verifies.
def opened() -> bool:
    try:
        if not SHA.is_file():
            return recorded()
        return record() and not verify(data=False)
    except OSError, ValueError, subprocess.SubprocessError:
        return False
