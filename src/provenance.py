# The baseline, its pass marks and the hash of every artifact, in one run_manifest.json.

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import paths
import pipeline as P

EXHIBITS = paths.EXHIBITS
MANIFEST = EXHIBITS / "run_manifest.json"

# One pass mark per exhibit, written here instead of decided once we saw the answer.
ACCEPTANCE = {
    "nn3_seeds": "Reporting only. Report every seed, never average them into a model.",
    "constraint_survival": "Descriptive, no pass mark. Universe, months and parameters fixed.",
    "permutation_null": "Shipped result above the null's 95th percentile, null gross near zero.",
    "inversion": "Gross lands near minus the baseline gross, not near zero.",
    "stale_scores": "Degraded, but not necessarily to zero.",
    "confirmation": "Reported whatever it says. The design never looked at 2016-2020.",
    "factor_atlas": "A catalogue. Nothing in it is selected for the book.",
    "earnings_module": "Ships only if its best variant beats the frozen book by 0.10 IR on "
    "2016-2020, with realized beta inside 0.15 and both tails monotone. The decision is written "
    "to disk before 2021-2026 is computed and is not revisited.",
    "live_forecast": "Scored against public prices once October 2026 has closed.",
}

# Rules we got wrong. Kept, because swapping one after a failed result is the sin here.
AMENDMENTS = {
    "permutation_null": {
        "original": "The null's net IR should centre near zero.",
        "why_wrong": "A shuffled ranking re-sorts the book monthly, so it churns at about "
        "179% turnover and pays our real cost rates. Its net IR centres near -2.",
        "now": "Tested on gross return, which is the only place a null can be zero.",
    },
}

# Built by the slow --ml steps. Everything else in submission/ is rebuilt on every run.
ML_ARTIFACTS = [
    (paths.EXHIBITS / name).as_posix()
    for name in (
        "ml_metrics.json",
        "subset_sweep.csv",
        "selection.json",
        "nn3_seeds.json",
        "placebo_lab.json",
        "constraint_survival.json",
        "oos_r2.json",
        "factor_atlas.csv",
        "earnings_decision.json",
        "earnings_module.json",
    )
]

# The code those artifacts depend on. Editing a chart does not make a model result stale.
ML_CODE = [
    "src/pipeline.py",
    "src/ml",
    "src/controls/selection.py",
    "src/exhibits/earnings.py",
    "src/exhibits/placebo_lab.py",
    "src/exhibits/constraint_survival.py",
    "requirements.txt",
]

# Written after the manifest or by it, so they can never match a hash taken here.
SKIP = {"run_manifest.json", "reproducibility.json"}


# Read in blocks, so the 700 MB panel never has to fit in memory.
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# One hash over files and folders, in a fixed order so it is stable across machines.
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


# The baseline the research exhibits are measured against, with the data it ran on.
def freeze() -> dict:
    metrics = json.loads((paths.SUBMISSION / "metrics.json").read_text(encoding="utf-8"))
    perf, comp = metrics["performance"], metrics["compliance"]
    data = [p for p in sorted(Path("data").rglob("*")) if p.suffix in {".parquet", ".csv", ".zip"}]
    return dict(
        what="The baseline the pre-WRDS research exhibits are measured against.",
        code=P.source_fingerprint(),
        data={p.as_posix(): dict(sha256=sha256(p)[:16], bytes=p.stat().st_size) for p in data},
        environment=dict(
            python=platform.python_version(),
            platform=platform.platform(),
            requirements_sha256=sha256(Path("requirements.txt"))[:16],
        ),
        baseline=dict(
            information_ratio=perf["information_ratio"],
            sharpe_ratio=perf["sharpe_ratio"],
            return_gross_annual=perf["return_gross_annual"],
            return_net_annual=perf["return_net_annual"],
            max_drawdown_total=perf["max_drawdown_total"],
            beta_realized=perf["beta_realized"],
            turnover_monthly_one_way=metrics["costs"]["turnover_monthly_one_way"],
            positions_average=comp["positions_average"],
        ),
        # Whole-share rounding happens after the optimizer. This is how far it pushes.
        rounding_drift=dict(
            net_exposure_max_abs=comp["net_exposure_max_abs"],
            sector_tilt_max=comp["sector_tilt_max"],
            position_weight_max=comp["position_weight_max"],
        ),
        acceptance_rules=ACCEPTANCE,
        amended_rules=AMENDMENTS,
    )


# One run's record: when, which code, and the hash of every file it left behind.
def section(paths: list[str], code: str) -> dict:
    return dict(
        written_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        code=code,
        files={p: sha256(Path(p)) for p in paths if Path(p).exists()},
    )


def main() -> None:
    # Found rather than listed, so no book-side artifact is missed.
    found = sorted(paths.SUBMISSION.glob("*.csv")) + sorted(paths.SUBMISSION.glob("*.json"))
    found += sorted(EXHIBITS.glob("*"))
    book = [p.as_posix() for p in found if p.is_file() and p.name not in SKIP]
    book = [p for p in book if p not in ML_ARTIFACTS]
    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    out = dict(
        what="The baseline and its pass marks, and which run produced each artifact. The "
        "reproducibility audit checks every hash.",
        baseline=freeze(),
        book=section(book, fingerprint(["src", "run.py", "requirements.txt"])),
        # A book-only run keeps the last model section, so its age stays visible to the audit.
        ml=section(ML_ARTIFACTS, fingerprint(ML_CODE))
        if "--ml" in sys.argv
        else previous.get("ml"),
    )
    MANIFEST.write_text(json.dumps(out, indent=2), encoding="utf-8", newline="\n")
    models = f"{len(out['ml']['files'])} model artifacts" if out["ml"] else "no model run yet"
    print(f"baseline frozen, {len(out['book']['files'])} book artifacts, {models}")


if __name__ == "__main__":
    main()
