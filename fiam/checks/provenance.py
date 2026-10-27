# Inputs, pass marks and each artifact's hash, in one run_manifest.json.

import hashlib
import json
import sys
from pathlib import Path

from fiam import data as D
from fiam import paths

EXHIBITS = paths.EXHIBITS
MANIFEST = EXHIBITS / "run_manifest.json"

# One pass mark per exhibit, set here before any result.
ACCEPTANCE = {
    "permutation_null": "Shipped result above the null's 95th percentile, null gross near zero.",
    "inversion": "Gross lands near minus the baseline gross, not near zero.",
    "stale_scores": "Degraded, but not necessarily to zero.",
    "confirmation": "Reported whatever it says. The signals were designed without 2016-2020.",
}

# Every rule stays as first written; none is swapped after a result.
PASS_MARKS_CHANGED = {
    "permutation_null": {
        "original": "The null's net IR should centre near zero.",
        "why_wrong": "A shuffled ranking re-sorts the book monthly, so it churns at about "
        "179% turnover and pays our real cost rates. Its net IR centres near -2.",
        "now": "Tested on gross return, which is the only place a null can be zero.",
    },
}

# Built by the slow --ml steps. The rest of submission/ rebuilds always.
ML_ARTIFACTS = [
    (paths.EXHIBITS / name).as_posix()
    for name in (
        "ml_metrics.json",
        "placebo_lab.json",
        "oos_r2.json",
        "teachers.json",
        "crowd.json",
        "scorer.json",
        "triage.json",
        "analyst_learned.json",
    )
] + [(paths.SUBMISSION / "models" / "book_inputs.parquet").as_posix()]

# The code those artifacts depend on. A chart edit never stales a model.
ML_CODE = [
    "fiam/book.py",
    "fiam/costs.py",
    "fiam/data.py",
    "fiam/ml",
    "fiam/exhibits/placebo_lab.py",
    "requirements.txt",
]

# Written after or by the manifest, so never matching a hash taken here.
SKIP = {"run_manifest.json", "reproducibility.json"}


# One hash over files and folders, in fixed order so machines all agree.
def fingerprint(entries: list[str]) -> str:
    files = []
    for entry in entries:
        path = Path(entry)
        files += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    digest = hashlib.sha256()
    for path in files:
        if path.exists() and "__pycache__" not in path.parts:
            digest.update(path.as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


# The book's inputs by SHA-256: organizer files, WRDS, benchmarks.
def inputs() -> dict:
    exports = D.WRDS / "sources.json"
    wrds = json.loads(exports.read_text(encoding="utf-8")) if exports.exists() else {}
    pinned = sorted(p for p in Path("data/benchmarks").glob("*") if p.suffix in {".csv", ".zip"})
    return dict(
        organizer={name: s["sha256"][:16] for name, s in D.manifest()["sources"].items()},
        wrds={name: s["sha256"][:16] for name, s in wrds.items()} or None,
        benchmarks={p.name: paths.sha256(p)[:16] for p in pinned},
    )


# This run's command and steps from run.py, or None when run on its own.
def this_run() -> dict | None:
    path = Path("cache/this_run.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# Each transcript's model and SHA-256, so a rehearsal is never mistaken.
def agents() -> dict:
    out = {}
    for path in sorted((EXHIBITS / "agents").glob("*.jsonl")):
        header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["header"]
        runner = header.get("runner", "fiam.agents.harness").split(" v")[0]
        out[path.stem] = dict(
            model=header["model"], sha256=header["model_sha256"][:16], runner=runner
        )
    return out


# One run's record: which code, and the hash of every file it left.
def section(files: list[str], code: str) -> dict:
    return dict(code=code, files={f: paths.sha256(Path(f)) for f in files if Path(f).exists()})


# Writes run_manifest.json: inputs, run flags and every artifact's hash.
def main() -> None:
    # Found rather than listed, so no book-side artifact is missed.
    found = sorted(paths.SUBMISSION.glob("*.csv")) + sorted(paths.SUBMISSION.glob("*.json"))
    found += sorted(EXHIBITS.glob("*"))
    book = [p.as_posix() for p in found if p.is_file() and p.name not in SKIP]
    book = [p for p in book if p not in ML_ARTIFACTS]
    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    out = dict(
        what="What the run read, the pass marks, and the hash of every artifact it wrote. The "
        "reproducibility audit checks every hash.",
        run=this_run(),
        inputs=inputs(),
        agents=agents(),
        acceptance_rules=ACCEPTANCE,
        pass_marks_changed=PASS_MARKS_CHANGED,
        book=section(book, fingerprint(["fiam", "run.py", "requirements.txt"])),
        # A book-only run keeps the last ML section, so the audit sees its age.
        ml=dict(
            **section(ML_ARTIFACTS, fingerprint(ML_CODE)), command=(this_run() or {}).get("command")
        )
        if "--ml" in sys.argv
        else previous.get("ml"),
    )
    paths.write_json(MANIFEST, out, rounded=False)
    models = f"{len(out['ml']['files'])} model artifacts" if out["ml"] else "no model run yet"
    print(f"{len(out['book']['files'])} book artifacts, {models}")


if __name__ == "__main__":
    main()
