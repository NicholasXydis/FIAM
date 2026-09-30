# One command for everything: uv run run.py --help lists what it does and its options.

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
import time
import zipfile
from pathlib import Path

HELP = """uv run run.py [options]
  no data in data/     checks the submitted holdings and returns against the brief
  with data            builds the data bundle once, rebuilds the book into out/, compares it
  --official           rewrites submission/, RESULTS.md and BRIEF.md (needs the WRDS tables)
  --ml                 retrains every model        --agents   runs the local-LLM agents
  --all                --ml and --agents, in order, resuming where a stopped run left off
  --smoke              every step on a small slice, a rehearsal of --all in minutes
  --fresh              reruns finished slow steps  --import <folder or fiam_v1.zip>
  --export-data        zips the data bundle into fiam_v1.zip for a teammate"""

# The book and everything read from it, in order. Each step is a module run with python -m.
STEPS = [
    ("fiam.data", "checking the data bundle"),
    ("fiam.book", "building the portfolio"),
    ("fiam.exhibits.pack", "sub-periods, costs, risk and signal attribution"),
    ("fiam.exhibits.daily_risk", "marking the book every trading day, 2021-2025"),
    ("fiam.checks.wrds_checks", "checking exits, returns, market and report dates on WRDS"),
    ("fiam.exhibits.confirmation", "running the same book on 2016-2020"),
    ("fiam.evaluate", "scoring every candidate and the ship rule window by window, walked forward"),
    ("fiam.exhibits.config_log", "writing the configuration ledger"),
    ("fiam.exhibits.labels", "checking every label against CRSP, 8-K filings and EDGAR"),
]

# Charts, docs and the audit come last, after any agent has written what they show.
REPORT = [
    ("fiam.agents.harness export", "writing the agents' tool definitions"),
    ("fiam.checks.provenance", "recording which run wrote each artifact"),
    ("fiam.report.charts", "drawing the performance charts"),
    ("fiam.report.research_charts", "drawing the research charts"),
    ("fiam.report.docs", "filling RESULTS.md and BRIEF.md"),
    ("fiam.checks.reproducibility", "auditing for look-ahead and survivorship"),
    ("fiam.checks.verify", "checking the book against the brief's rules"),
]

# The agents that run before the models, because the crowd score feeds the scorer.
CROWD_STEPS = [
    ("fiam.agents.harness prepare", "downloading and checking the agents' models, once"),
    ("fiam.agents.crowd", "crowd agent: where AI assistants would buy, 60 months of 2016-2020"),
]

# The models, the ship decision, then the comparison and research controls. Each reads the last.
ML_STEPS = [
    ("fiam.ml.dataset", "building the training folds"),
    ("fiam.ml.teachers", "teachers: daily beta, crowding and revisions, learned year by year"),
    ("fiam.ml.crowd", "learning where the agents invest, for every month to 2026"),
    ("fiam.ml.scorer", "scorer: learning to rank what a neutral book earns, five seeds"),
    ("fiam.ml.ship", "the 3 x 2 x 2 candidate grid, the monthly trader, each year's choice"),
]

# The model comparison and research controls; a smoke rehearsal leaves them as they are.
RESEARCH_STEPS = [
    ("fiam.ml.train", "fitting ElasticNet, LightGBM and NN3, then scoring each into a book"),
    ("fiam.ml.selection", "subset sweep, budgeted search and the 147-signal atlas"),
    ("fiam.ml.summary", "decile tables and the model numbers"),
    ("fiam.ml.oos_r2", "measuring out-of-sample R-squared for every method"),
    ("fiam.exhibits.placebo_lab", "running the permutation and falsification controls"),
]

# The local-model agents that read the finished book.
AGENT_STEPS = [
    ("fiam.agents.director", "research director: each year's book from the months before it"),
    ("fiam.agents.discovery", "signal-discovery agent, named and coded runs"),
    ("fiam.agents.auditor", "reproducibility agent on planted and clean copies"),
    ("fiam.agents.critic", "devil's-advocate agent on the second vendor's model"),
    ("fiam.agents.critic --repeat", "the devil's advocate again, to prove the run repeats"),
    ("fiam.agents.explainer", "explainer: why the book held each of its largest positions"),
]

ROOT = Path(__file__).resolve().parent
PACKAGE, STAMPS, OUT, LOG = (
    Path("fiam"),
    Path("cache/steps.json"),
    Path("out"),
    Path("cache/run.log"),
)
# This run's command and each step's status so far, read by the provenance step.
THIS_RUN = Path("cache/this_run.json")

# The organizer's files. The first three build the data bundle every step reads.
REQUIRED = [
    "chars_final_with_names.parquet",
    "8k_20150101_20260831_identified.parquet",
    "factor_char_list.csv",
]
ORGANIZER = [*REQUIRED, "readme.md"]

# The bundle, found by the same rule as fiam/data.py, and the files it cannot run without.
BUNDLE = Path(os.environ.get("FIAM_DATA_DIR") or ROOT / "data" / "fiam_v1").expanduser()
CORE = ["features_monthly.parquet", "labels_monthly.parquet", "filings.parquet", "manifest.json"]
EXITS = BUNDLE / "wrds" / "exits.parquet"

PACKAGES = ["pandas", "numpy", "pyarrow", "scipy", "cvxpy", "statsmodels", "matplotlib"]
ML_PACKAGES = ["sklearn", "lightgbm", "torch"]

# Data any step may read. Large files are keyed on size and date, small ones on their bytes.
DATA = [*(BUNDLE / name for name in CORE), EXITS, Path("data/benchmarks/sources.json")]

# What an agent reads beyond its code: its prompt, its model, and the exhibits it argues about.
AGENT_READS = {
    "fiam.agents.discovery": ["prompts/agents/discovery.md", "submission/metrics.json"],
    "fiam.agents.critic": [
        "prompts/agents/critic.md",
        "submission/holdings.csv",
        "submission/metrics.json",
        "submission/exhibits/pack.json",
        "submission/exhibits/confirmation.json",
        "submission/exhibits/discovery.json",
    ],
    "fiam.agents.auditor": ["prompts/agents/auditor.md"],
    "fiam.agents.director": [
        "prompts/agents/director.md",
        "submission/exhibits/ship.json",
        "submission/exhibits/ship_candidates.csv",
    ],
}


# The file behind a module name, fiam.ml.train to fiam/ml/train.py.
def source(module: str) -> Path:
    return Path(*module.split(".")).with_suffix(".py")


# Every local module a step imports, followed through, so a change anywhere it reaches reruns it.
def closure(module: str) -> list[Path]:
    seen, todo = set(), [source(module)]
    while todo:
        path = todo.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fiam"):
                todo += [source(f"{node.module}.{a.name}") for a in node.names]
                todo.append(source(node.module))
    return sorted(seen)


# A hash of everything a step depends on. Equal to last time means its outputs are still right.
def stamp(command: str) -> str:
    module = command.split()[0]
    digest = hashlib.sha256(command.encode())
    reads = [*closure(module), *DATA, *map(Path, AGENT_READS.get(module, []))]
    if module == "fiam.agents.auditor":
        reads += sorted(p for p in PACKAGE.rglob("*.py") if "agents" not in p.parts)
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


# Unpacks a bundle zip, refusing it whole if any entry would land outside the bundle folder.
def unzip(source: Path, target: Path) -> None:
    root = (target / BUNDLE.name).resolve()
    with zipfile.ZipFile(source) as zf:
        outside = [
            n for n in zf.namelist() if not (target.resolve() / n).resolve().is_relative_to(root)
        ]
        if outside:
            raise SystemExit(
                f"--import: {source.name} has entries outside {BUNDLE.name}/: {outside[:3]}"
            )
        zf.extractall(target)


# A zip is unpacked into data/; a folder gives organizer files by name, WRDS exports by columns.
def import_from(source_path: Path) -> None:
    if source_path.suffix == ".zip":
        unzip(source_path, BUNDLE.parent)
        print(f"  unpacked {source_path.name} into {BUNDLE.parent}")
        return
    if not source_path.is_dir():
        print(f"--import: {source_path} is neither a folder nor a .zip.")
        return
    Path("data").mkdir(exist_ok=True)
    for name in ORGANIZER:
        src, target = source_path / name, Path("data") / name
        if src.exists() and not (target.exists() and target.stat().st_size == src.stat().st_size):
            shutil.copy2(src, target)
            print(f"  copied {name}")
    from fiam import wrds

    exports = []
    for path in sorted(source_path.glob("*.csv")):
        try:
            wrds.kind(path)
            exports.append(str(path))
        except ValueError:
            continue
    if exports and not bundle():
        print("  WRDS exports found, but converting them needs the organizer's files first.")
    elif exports:
        print(f"  converting {len(exports)} WRDS export(s)")
        if subprocess.run(
            [sys.executable, "-m", "fiam.wrds", *exports], env=child_env()
        ).returncode:
            print("  WRDS conversion failed; the run continues without WRDS.")


# The whole bundle as one zip for a teammate, with its SHA-256. Never commit or submit it.
def export_data() -> int:
    if not BUNDLE.is_dir():
        print(f"No bundle at {BUNDLE} to export.")
        return 1
    target = ROOT / "fiam_v1.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as zf:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(BUNDLE.parent))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"wrote {target.name}: {target.stat().st_size / 1e9:.2f} GB, SHA-256 {digest}")
    print("Share it privately with teammates covered by our WRDS access. It is gitignored.")
    return 0


# The bundle, built once from the organizer's files in data/ if it is not there yet.
def bundle() -> bool:
    if all((BUNDLE / name).is_file() for name in CORE):
        return True
    if not all((Path("data") / name).exists() for name in REQUIRED):
        return False
    print(f"Building the data bundle in {BUNDLE} from data/, once, under a minute.", flush=True)
    build = [sys.executable, "-m", "fiam.build_data", "data"]
    return subprocess.run(build, env=child_env()).returncode == 0


# The SEC records the labels were checked against, unpacked once from the pinned archive.
def unpack_edgar() -> None:
    archive = Path("data/edgar_cache.zip")
    target, partial = Path("cache/edgar"), Path("cache/unpacking")
    if archive.exists() and not target.exists():
        shutil.rmtree(partial, ignore_errors=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(partial)
        (partial / "edgar").rename(target)
        shutil.rmtree(partial)


# One thread for the numeric libraries: identical results, and no OpenMP clash on macOS.
def child_env(extra: dict | None = None) -> dict:
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)} | (extra or {})
    env.setdefault("OMP_NUM_THREADS", "1")
    return env


# Keeps the machine awake while a long run works; Windows and macOS release it when we exit.
def keep_awake() -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    elif platform.system() == "Darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])


# out/ starts as a copy of the official results, so steps that do not rerun keep official values.
def seed_out() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree("submission", OUT / "submission", dirs_exist_ok=True)
    for doc in ("RESULTS.md", "BRIEF.md"):
        shutil.copy2(doc, OUT / doc)


# Prints to the screen and to cache/run.log, so an overnight run can be read in the morning.
def say(text: str) -> None:
    print(text, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


# One step, its output streamed to the screen and the log. Returns its exit code.
def execute(command: str, env: dict) -> int:
    with subprocess.Popen(
        [sys.executable, "-m", *command.split()],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as process:
        for line in process.stdout:
            say(line.rstrip("\n"))
    return process.returncode


# Runs each step in order, stops at a failure, and skips a finished slow step whose inputs match.
def run(steps: list, env: dict, official: bool, fresh: bool) -> list[tuple[str, str, float]]:
    slow = {c for c, _ in CROWD_STEPS + ML_STEPS + RESEARCH_STEPS + AGENT_STEPS}
    stamps = json.loads(STAMPS.read_text(encoding="utf-8")) if STAMPS.exists() else {}
    done, reran = [], False
    record = dict(command=" ".join(["uv run run.py", *sys.argv[1:]]), steps={})
    for command, doing in steps:
        THIS_RUN.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
        started = time.monotonic()
        current = stamp(command) if command in slow else None
        if current and official and not fresh and not reran and stamps.get(command) == current:
            say(f"\n[{doing}] unchanged, skipped")
            done.append((doing, "skipped", 0.0))
            record["steps"][command] = "skipped, unchanged since the run that made it"
            continue
        reran = reran or command in slow
        say(f"\n[{doing}]")
        code = execute(command, env)
        took = time.monotonic() - started
        if code != 0:
            done.append((doing, "FAILED", took))
            # Outside an official run a failed audit is reported and the checks after it still run.
            if official or not command.startswith("fiam.checks.reproducibility"):
                say(f"\n{command} failed, stopping here.")
                return done
            continue
        done.append((doing, "done", took))
        record["steps"][command] = "ran"
        if current and official:
            stamps[command] = current
            STAMPS.parent.mkdir(exist_ok=True)
            STAMPS.write_text(json.dumps(stamps, indent=2), encoding="utf-8", newline="\n")
    return done


# The morning summary: every step, how long it took, and whether anything failed.
def summary(done: list[tuple[str, str, float]]) -> bool:
    say("\nSummary")
    for doing, status, took in done:
        say(f"  {status:<8} {took / 60:6.1f} min  {doing}")
    failed = any(status == "FAILED" for _, status, _ in done)
    say("Everything passed." if not failed else "A step failed; see above.")
    return not failed


# Reads the options, then runs every step they ask for, in order.
def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(HELP)
        return 0
    if "--export-data" in args:
        return export_data()
    everything = "--all" in args
    ml, agents = everything or "--ml" in args, everything or "--agents" in args
    fresh, smoke = "--fresh" in args, "--smoke" in args
    official = "--official" in args and not smoke
    if not ready(ml):
        return 1
    if "--import" in args:
        position = args.index("--import") + 1
        if position >= len(args):
            print(
                "--import needs a folder or fiam_v1.zip, e.g.  uv run run.py --import ~/Downloads"
            )
            return 1
        import_from(Path(args[position]).expanduser())

    # No data: check what was submitted, which needs nothing but this repo.
    if not bundle():
        if official or ml or agents:
            print("--official, --ml and --agents rebuild the book, which needs the data bundle or")
            print("the organizer's files. Add them with:  uv run run.py --import <folder or zip>")
            return 1
        print("No organizer data in data/, so checking the submitted files only.")
        print("To rebuild the book: uv run run.py --import <folder with the organizer's files>\n")
        return execute("fiam.checks.verify", child_env())

    if official and not EXITS.exists():
        print("--official needs the WRDS exports. Add them with: uv run run.py --import <folder>")
        return 1
    keep_awake()
    unpack_edgar()
    extra = {"FIAM_SMOKE": "1"} if smoke else {}
    if official:
        say("Official run: rewrites submission/ and RESULTS.md.")
        env = child_env({"FIAM_OFFICIAL": "1"})
    else:
        wrds = "with WRDS" if EXITS.exists() else "without WRDS, so provisional"
        say(f"Rebuilding into out/, {wrds}. The committed results are not touched.")
        try:
            seed_out()
        except PermissionError, shutil.Error:
            # Windows locks a file another program has open, a CSV in Excel say.
            print("A file in out/ is open in another program. Close it, then run again.")
            return 1
        env = child_env({"FIAM_OUT": str(OUT), **extra})

    # The manifest records the model section only on a run that rebuilt it.
    report = [(f"{c} --ml" if ml and c == "fiam.checks.provenance" else c, d) for c, d in REPORT]
    models = ML_STEPS + ([] if smoke else RESEARCH_STEPS)
    steps = (CROWD_STEPS if agents else []) + (models if ml else []) + STEPS
    steps += (AGENT_STEPS if agents else []) + report
    done = run(steps, env, official, fresh)
    passed = summary(done)
    # A run that reached the end is compared, even when the audit flagged something.
    if not official and len(done) == len(steps):
        execute("fiam.checks.compare", env)
        say("\nResults are in out/.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
