# One command for everything. It works out what it can do from the data present:
#   no data            checks the submitted holdings and returns against the brief
#   organizer data     rebuilds the book into out/ and compares it with the official results
#   --official         rewrites submission/ and RESULTS.md, and refuses without WRDS
# Other flags: --import <folder> (copy data in first), --ml (models, 20 min), --agents (GPU),
# --fresh (rerun cached model steps).

import ast
import hashlib
import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

STEPS = [
    (["src/pipeline.py"], "building the portfolio"),
    (["src/exhibits/pack.py"], "sub-periods, costs, risk and signal attribution"),
    (["src/controls/wrds_checks.py"], "checking exits, returns, market and report dates on WRDS"),
    (["src/exhibits/confirmation.py"], "running the frozen book on 2016-2020"),
    (["src/exhibits/live_forecast.py"], "building and hashing the live September 2026 book"),
    (["src/exhibits/live_score.py"], "scoring the live book on cached public prices"),
    (["src/exhibits/config_log.py"], "writing the configuration ledger"),
    (["src/exhibits/labels.py"], "checking every label against CRSP, 8-K filings and EDGAR"),
    (["src/agents/mcp_server.py", "--export"], "writing the agents' tool definitions"),
    (["src/charts.py"], "drawing the performance charts"),
    (["src/research_charts.py"], "drawing the research charts"),
    (["src/docs.py"], "filling RESULTS.md and BRIEF.md, then checking nothing is stale"),
    (["src/provenance.py"], "pinning the baseline and recording which run wrote each artifact"),
    (["src/controls/reproducibility.py"], "auditing for look-ahead and survivorship"),
    (["src/verify.py"], "checking the book against the brief's rules"),
]

# Model comparison and research controls, about 20 minutes from scratch. Each step reads the last.
ML_STEPS = [
    (["src/ml/dataset.py"], "building the training folds"),
    (["src/ml/train.py"], "fitting ElasticNet, LightGBM and NN3, then scoring each into a book"),
    (["src/controls/selection.py"], "subset sweep, budgeted search and the 147-signal atlas"),
    (["src/ml/summary.py"], "decile tables and the model numbers"),
    (["src/ml/nn3_seeds.py"], "refitting the neural net on five seeds"),
    (["src/ml/oos_r2.py"], "measuring out-of-sample R-squared for every method"),
    (["src/exhibits/earnings.py"], "the earnings module, decided on 2016-2020 first"),
    (["src/exhibits/placebo_lab.py"], "running the permutation and falsification controls"),
    (["src/exhibits/constraint_survival.py"], "tracing where prediction becomes tradeable"),
]

# Through Hermes on the local models, grouped so each loads once. No submitted number uses them.
AGENT_STEPS = [
    (["src/agents/discovery.py"], "signal-discovery agent, named and coded runs"),
    (["src/agents/auditor.py"], "reproducibility agent on planted and clean copies"),
    (["src/agents/critic.py"], "devil's-advocate agent on the second vendor's model"),
    (["src/agents/critic.py", "--repeat"], "the devil's advocate again, to prove the run repeats"),
]

ROOT = Path(__file__).resolve().parent
SRC, STAMPS, OUT = Path("src"), Path("cache/steps.json"), Path("out")

# The organizer's files. The first two are enough to rebuild the book.
REQUIRED = ["chars_final_with_names.parquet", "factor_char_list.csv"]
ORGANIZER = [*REQUIRED, "8k_20150101_20260831_identified.parquet", "readme.md"]
EXITS = Path("data/wrds/exits.parquet")

PACKAGES = ["pandas", "numpy", "pyarrow", "scipy", "cvxpy", "statsmodels", "matplotlib"]
ML_PACKAGES = ["sklearn", "lightgbm", "torch"]

# Data any step may read. Large files are keyed on size and date, small ones on their bytes.
DATA = [
    "data/chars_final_with_names.parquet",
    "data/factor_char_list.csv",
    "data/wrds/exits.parquet",
    "data/benchmarks/sources.json",
]

# What an agent reads beyond its code: its prompt, its model, and the exhibits it argues about.
AGENT_READS = {
    "src/agents/discovery.py": ["prompts/agents/discovery.md", "submission/metrics.json"],
    "src/agents/critic.py": [
        "prompts/agents/critic.md",
        "submission/holdings.csv",
        "submission/metrics.json",
        "submission/exhibits/pack.json",
        "submission/exhibits/confirmation.json",
        "submission/exhibits/discovery.json",
    ],
    "src/agents/auditor.py": [
        "prompts/agents/auditor.md",
        *sorted(p.as_posix() for p in (ROOT / SRC).rglob("*.py") if "agents" not in p.parts),
    ],
}


# Every local module a script imports, followed through, so a change anywhere it reaches reruns it.
def closure(script: Path) -> list[Path]:
    local = {p.stem: p for p in SRC.rglob("*.py")}
    seen, todo = set(), [script]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            todo += [local[n.split(".")[0]] for n in names if n.split(".")[0] in local]
    return sorted(seen)


# A hash of everything a step depends on. Equal to last time means its outputs are still right.
def stamp(command: list[str]) -> str:
    digest = hashlib.sha256(" ".join(command).encode())
    reads = [
        *closure(Path(command[0])),
        *map(Path, DATA),
        *map(Path, AGENT_READS.get(command[0], [])),
    ]
    if command[0].startswith("src/agents/"):
        reads += [Path("models/MANIFEST.txt"), *sorted(Path("models").glob("*.sha256.json"))]
    for path in reads:
        if not path.exists():
            digest.update(f"{path} missing".encode())
        elif path.stat().st_size > 50_000_000:
            digest.update(f"{path} {path.stat().st_size} {path.stat().st_mtime_ns}".encode())
        else:
            digest.update(path.read_bytes())
    return digest.hexdigest()


# Stops in the first second with the fix, rather than ten minutes in with a traceback.
def ready(ml: bool) -> bool:
    missing = [p for p in PACKAGES + (ML_PACKAGES if ml else []) if not importlib.util.find_spec(p)]
    if missing == ["torch"] and platform.system() == "Darwin":
        print("PyTorch 2.14 needs Apple silicon and macOS 14, so --ml cannot run on this Mac.")
        print("Everything else can:  uv run run.py")
        return False
    if missing:
        print(f"Missing Python packages: {', '.join(missing)}.")
        print("Run it with uv, which installs them:  uv run run.py")
        print("Or install them yourself:             python -m pip install -r requirements.txt")
        return False
    if ml:
        try:
            importlib.import_module("lightgbm")
        except OSError:
            print("LightGBM cannot load OpenMP. On macOS:  brew install libomp")
            return False
    return True


# Copies the organizer's files, known by their names, and converts WRDS exports, known by their
# columns, from a folder. Anything else in the folder, a CV say, is left alone.
def import_from(folder: Path) -> None:
    if not folder.is_dir():
        print(f"--import: {folder} is not a folder.")
        return
    Path("data").mkdir(exist_ok=True)
    for name in ORGANIZER:
        source, target = folder / name, Path("data") / name
        if source.exists() and not (
            target.exists() and target.stat().st_size == source.stat().st_size
        ):
            shutil.copy2(source, target)
            print(f"  copied {name}")
    sys.path.insert(0, str(SRC))
    import wrds

    exports = []
    for path in sorted(folder.glob("*.csv")):
        try:
            wrds.kind(path)
            exports.append(str(path))
        except ValueError:
            continue
    if exports and not (Path("data") / REQUIRED[0]).exists():
        print("  WRDS exports found, but converting them needs the organizer's files first.")
    elif exports:
        print(f"  converting {len(exports)} WRDS export(s)")
        if subprocess.run([sys.executable, "src/wrds.py", *exports], env=child_env()).returncode:
            print("  WRDS conversion failed; the run continues without WRDS.")


# The SEC records the labels were checked against, unpacked once from the pinned archive.
# Unpacked beside the cache and moved in whole, so an interrupted run never leaves half of it.
def unpack_edgar() -> None:
    archive = Path("data/edgar_cache.zip")
    target, partial = Path("cache/edgar"), Path("cache/unpacking")
    if archive.exists() and not target.exists():
        shutil.rmtree(partial, ignore_errors=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(partial)
        (partial / "edgar").rename(target)
        shutil.rmtree(partial)


def child_env(extra: dict | None = None) -> dict:
    env = os.environ | {"PYTHONUTF8": "1"} | (extra or {})
    # macOS: LightGBM, PyTorch and scikit-learn each bring an OpenMP runtime, and together they
    # crash or hang unless each keeps to one thread. Windows and Linux share one runtime.
    if platform.system() == "Darwin":
        env.setdefault("OMP_NUM_THREADS", "1")
    return env


# out/ starts as a copy of the official results, so steps that do not rerun keep official values.
def seed_out() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree("submission", OUT / "submission", dirs_exist_ok=True)
    for doc in ("RESULTS.md", "BRIEF.md"):
        shutil.copy2(doc, OUT / doc)


# Runs each step in order and stops at the first failure, or a later step reads half-written output.
# Outside an official run a failed audit is reported and the checks after it still run.
# None means a step stopped the run; False that only the audit failed.
def run(steps: list, env: dict, ml: bool, official: bool, fresh: bool) -> bool | None:
    groups = {tuple(c): "ml" for c, _ in ML_STEPS} | {tuple(c): "agents" for c, _ in AGENT_STEPS}
    stamps = json.loads(STAMPS.read_text(encoding="utf-8")) if STAMPS.exists() else {}
    reran, passed = set(), True
    for command, doing in steps:
        group, key = groups.get(tuple(command)), " ".join(command)
        if group:
            current = stamp(command)
            # Step records describe the committed files, so only an official run may skip by them.
            # Skipped only if nothing it reads changed and no earlier step in its group reran.
            unchanged = stamps.get(key) == current and group not in reran
            if official and not fresh and unchanged:
                print(f"\n[{doing}] unchanged, skipped", flush=True)
                continue
            reran.add(group)
        print(f"\n[{doing}]", flush=True)
        # The manifest records the model section only on a run that rebuilt it.
        flags = ["--ml"] if ml and command == ["src/provenance.py"] else []
        if subprocess.run([sys.executable, *command, *flags], env=env).returncode != 0:
            if official or command[0] != "src/controls/reproducibility.py":
                print(f"\n{command[0]} failed, stopping here.")
                return None
            passed = False
            continue
        if group and official:
            stamps[key] = current
            STAMPS.parent.mkdir(exist_ok=True)
            STAMPS.write_text(json.dumps(stamps, indent=2), encoding="utf-8", newline="\n")
    return passed


def main() -> int:
    os.chdir(ROOT)
    # Our lines and each step's output land in order, even when piped to a file.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        header = Path(__file__).read_text(encoding="utf-8").split("\n\n")[0]
        print("\n".join(line[2:] for line in header.splitlines()))
        return 0
    ml, agents, fresh, official = (f in args for f in ("--ml", "--agents", "--fresh", "--official"))
    if not ready(ml):
        return 1
    if "--import" in args:
        position = args.index("--import") + 1
        if position >= len(args):
            print("--import needs a folder, for example:  uv run run.py --import ~/Downloads")
            return 1
        import_from(Path(args[position]).expanduser())

    # No data: check what was submitted, which needs nothing but this repo.
    if not all((Path("data") / name).exists() for name in REQUIRED):
        if official or ml or agents:
            print("--official, --ml and --agents rebuild the book, which needs the organizer's")
            print("files in data/. Add them with:  uv run run.py --import <folder>")
            return 1
        print("No organizer data in data/, so checking the submitted files only.")
        print("To rebuild the book: put the organizer's files in a folder, then")
        print("  uv run run.py --import <folder>\n")
        return subprocess.run([sys.executable, "src/verify.py"], env=child_env()).returncode

    if official and not EXITS.exists():
        print(
            "--official needs the WRDS exports. Convert them with: uv run run.py --import <folder>"
        )
        return 1
    unpack_edgar()
    if official:
        print("Official run: rewrites submission/ and RESULTS.md.")
        env = child_env({"FIAM_OFFICIAL": "1"})
    else:
        wrds = "with WRDS" if EXITS.exists() else "without WRDS, so provisional"
        print(f"Rebuilding into out/, {wrds}. The committed results are not touched.")
        try:
            seed_out()
        except (PermissionError, shutil.Error):
            # Windows locks a file another program has open, a CSV in Excel say.
            print("A file in out/ is open in another program. Close it, then run again.")
            return 1
        env = child_env({"FIAM_OUT": str(OUT)})

    # Models first; agents after the exhibits they read and before the charts and docs show them.
    charts = STEPS.index((["src/charts.py"], "drawing the performance charts"))
    steps = (
        (ML_STEPS if ml else []) + STEPS[:charts] + (AGENT_STEPS if agents else []) + STEPS[charts:]
    )
    passed = run(steps, env, ml, official, fresh)
    if official or passed is None:
        return 0 if passed else 1
    print()
    subprocess.run([sys.executable, "src/compare.py"], env=env)
    print("\nResults are in out/." + ("" if passed else " The audit above failed a check."))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
