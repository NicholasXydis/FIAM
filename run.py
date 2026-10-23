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
import tempfile
import time
import zipfile
from pathlib import Path

HELP = """uv run run.py [options]
  no data in data/     checks the submitted holdings and returns against the brief
  with data            builds the data bundle once, rebuilds the book into out/, compares it
  --official           rewrites submission/ and RESULTS.md (needs the WRDS tables)
  --ml                 retrains every model        --agents   runs the local-LLM agents
  --all                --ml and --agents, in order, resuming where a stopped run left off
  --smoke              every step on a small slice, a rehearsal of --all in minutes
  --fresh              reruns finished slow steps  --import <folder or fiam_v1.zip>
  --export-data        zips the data bundle into fiam_v1.zip for a teammate
  --v2                 runs v2 on both windows into out/v2/; --switch NAME (repeatable) runs
                       one switch instead, --capital X sets the fund size (default 1e7)
  --crowd-quick        a short live AI crowd on the newest months (needs a GPU or FIAM_LLM_URL):
                       --agents N, --months M, --minutes T
  --world <folder>     turns the finals data (any countries) into data/world/ once, then runs
                       the steps after it on that data with the global switch on
                       (--world fake: the rehearsal's two-country copy of our panel)
  --rules <txt or pdf> rules -> a draft mandate in mandates/ for a person to approve (GPU)
  --finals <file>      checks a finals mandate, then runs final v3, v1's method and v2 under it;
                       --window FIRST LAST and --capital X change the months and the fund size
  --pack <run folder>  a finals book's committee pack: holdings, returns, metrics and charts
  --finals-drill <txt> rules text -> draft mandate -> both books, timed (GPU or FIAM_LLM_URL)
  --finals-pack        rebuilds the charts, Q&A, both finals decks and the PDF from the results
                       (needs fiam_results.zip: --import fiam_results.zip --finals-pack)
  --export-results     zips agent answers, v2 runs and frozen inputs into fiam_results.zip
                       (--import takes either zip, and can be given twice)
  --data status        every data source: files, sizes, USB budget, licence (data/INVENTORY.json)
  --data verify        every saved file against its receipt, and the organizer's checksums
  --data rebuild <source> <verb ...>   rebuilds into a scratch folder and compares with ours
  --data <source> <verb ...>   one data tool: edgar, noaa, stock, carbon or amazon, e.g.
                       --data carbon plan <spec> (prices, buys nothing); carbon buy and rebuy
                       spend tokens, so the leader runs them; --data amazon fetch [category]
  setup [kit]          restores the finals kit from the USB, missing files only, then doctor
  doctor [--deep]      checks Python, packages, data, the kit's files, settings and the AI link
  export [folder]      writes the finals kit to the USB, rewriting only parts that changed;
                       --dry-run shows sizes, --skip PART,PART leaves parts out
  installers, caches   uv, Node and pnpm for every machine; this machine's offline packages"""

# The book and everything read from it, in order. Each step is a module run with python -m.
STEPS = [
    ("fiam.data", "checking the data bundle"),
    ("fiam.costs", "calibrating spreads to CRSP quotes and borrow to short interest"),
    ("fiam.book", "building the portfolio"),
    ("fiam.exhibits.pack", "sub-periods, costs, risk and signal attribution"),
    ("fiam.exhibits.daily_risk", "marking the book every trading day, with stress tests"),
    ("fiam.exhibits.implementation", "cost sensitivities, capacity and liquidity"),
    ("fiam.checks.wrds_checks", "checking exits, returns, market and report dates on WRDS"),
    ("fiam.exhibits.confirmation", "running the same book on 2016-2020"),
    ("fiam.exhibits.config_log", "writing the ledger of everything we tried"),
    ("fiam.exhibits.labels", "checking every label against CRSP, 8-K filings and EDGAR"),
]

# Charts, docs and the audit come last, after any agent has written what they show.
REPORT = [
    ("fiam.agents.harness export", "writing the agents' tool definitions"),
    ("fiam.checks.provenance", "recording which run wrote each artifact"),
    ("fiam.report.charts", "drawing the performance charts"),
    ("fiam.report.research_charts", "drawing the research charts"),
    ("fiam.report.docs", "filling RESULTS.md"),
    ("fiam.checks.reproducibility", "auditing for look-ahead and survivorship"),
    ("fiam.checks.verify", "checking the book against the brief's rules"),
]

# The agents that run before the models, because the crowd score feeds the scorer.
CROWD_STEPS = [
    ("fiam.agents.harness prepare", "downloading and checking the agents' models, once"),
    ("fiam.agents.crowd", "crowd agent: where AI assistants would buy, 60 months of 2016-2020"),
    ("fiam.agents.triage", "triage agent: labels 6,000 masked 8-Ks from 2015-2018"),
]

# The models, then the comparison and research controls. Each reads the last.
ML_STEPS = [
    ("fiam.ml.dataset", "building the training folds"),
    ("fiam.ml.text", "FinBERT reads every masked 8-K, once; a stopped run resumes"),
    ("fiam.ml.triage", "the triage labels learned from the text, applied to every filing"),
    ("fiam.ml.teachers", "teachers: daily beta, crowding and revisions, learned year by year"),
    ("fiam.ml.crowd", "learning where the agents invest, for every month to 2026"),
    ("fiam.agents.analyst", "analyst agent: material filings in the composite's tails"),
    ("fiam.ml.analyst", "the analyst's pre-2021 verdicts learned from the text, every month"),
    ("fiam.ml.scorer", "scorer: learning to rank what a neutral book earns, five seeds"),
]

# The model comparison and research controls; a smoke rehearsal leaves them as they are.
RESEARCH_STEPS = [
    ("fiam.ml.train", "fitting ElasticNet, LightGBM and NN3, then scoring each into a book"),
    ("fiam.ml.summary", "decile tables and the model numbers"),
    ("fiam.ml.oos_r2", "measuring out-of-sample R-squared for every method"),
    ("fiam.exhibits.placebo_lab", "running the permutation and falsification controls"),
]

# The local-model agents that read the finished book.
AGENT_STEPS = [
    ("fiam.agents.critic", "devil's-advocate agent on the second vendor's model"),
    ("fiam.agents.critic --repeat", "the devil's advocate again, to prove the run repeats"),
    ("fiam.agents.explainer", "explainer: why the book held its biggest winners and losers"),
]

ROOT = Path(__file__).resolve().parent
STAMPS, OUT, LOG = (
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
# Carbon Arc's SDK, pinned, with nothing published after the freeze.
CARBON_SDK, CARBON_CUTOFF = "carbonarc==1.1.19", "2026-10-14T00:00:00Z"
# DuckDB for the Amazon reviews, in its own environment, same cutoff.
AMAZON_ENGINE = "duckdb"
# Each data tool, the package its env adds, and its folder in data/
DATA_TOOLS = {
    "edgar": ("edgar.py", None, "edgar"),
    "noaa": ("noaa.py", None, "noaa"),
    "stock": ("stock_data.py", None, "v4/extracts"),
    "carbon": ("carbon_arc.py", CARBON_SDK, "carbon_arc"),
    "amazon": ("amazon.py", AMAZON_ENGINE, "amazon"),
}

# Data any step may read. Large files are keyed on size and date, small ones on their bytes.
DATA = [*(BUNDLE / name for name in CORE), EXITS, Path("data/benchmarks/sources.json")]

# What an agent reads beyond its code: its prompt, its model, and the exhibits it argues about.
AGENT_READS = {
    "fiam.agents.critic": [
        "prompts/agents/critic.md",
        "submission/holdings.csv",
        "submission/metrics.json",
        "submission/exhibits/pack.json",
        "submission/exhibits/confirmation.json",
        "submission/exhibits/analyst_learned.json",
    ],
    "fiam.agents.triage": ["prompts/agents/triage.md"],
    "fiam.agents.analyst": ["prompts/agents/analyst.md"],
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
    from fiam import paths

    try:
        paths.safe_unzip(source, target, target / BUNDLE.name)
    except ValueError as err:
        raise SystemExit(f"--import: {err}") from err


# A zip is unpacked into data/; a folder gives organizer files by name, WRDS exports by columns.
def import_from(source_path: Path) -> None:
    from fiam import kit

    if source_path.suffix == ".zip" and kit.is_kit(source_path):
        print(f"  restored {kit.restore(source_path)} result files from {source_path.name}")
        return
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
        # The organizer's files beside MAIN.py or run.py count as imported: judges place them there.
        if not all(Path(name).exists() for name in REQUIRED):
            return False
        import_from(Path("."))
    print(f"Building the data bundle in {BUNDLE} from data/, once, about two minutes.", flush=True)
    build = [sys.executable, "-m", "fiam.build_data", "data"]
    return subprocess.run(build, env=child_env()).returncode == 0


# The SEC records the labels were checked against, unpacked once from the pinned archive.
def unpack_edgar() -> None:
    archive = Path("data/edgar_cache.zip")
    target, partial = Path("cache/edgar"), Path("cache/unpacking")
    if archive.exists() and not target.exists():
        shutil.rmtree(partial, ignore_errors=True)
        from fiam import paths

        paths.safe_unzip(archive, partial)
        (partial / "edgar").rename(target)
        shutil.rmtree(partial)


# One thread for the numeric libraries: identical results, and no OpenMP clash on macOS.
def child_env(extra: dict | None = None) -> dict:
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)} | (extra or {})
    # One thread for every maths library and a fixed hash seed, so reruns repeat bit for bit.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(name, "1")
    env.setdefault("PYTHONHASHSEED", "0")
    return env


# Keeps the machine awake while a long run works; Windows and macOS release it when we exit.
def keep_awake() -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    elif platform.system() == "Darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])


# out/ starts as a copy of the official results, so steps that do not rerun keep official values.
# Only the book's part is reset; v2 runs and the trial ledger beside it in out/ are kept.
def seed_out() -> None:
    shutil.rmtree(OUT / "submission", ignore_errors=True)
    shutil.copytree("submission", OUT / "submission", dirs_exist_ok=True)
    shutil.copy2("RESULTS.md", OUT / "RESULTS.md")


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


# The value after a flag, or None when the flag is absent or nothing follows it.
def value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    position = args.index(flag) + 1
    return args[position] if position < len(args) and not args[position].startswith("--") else None


# What every finals step reads from the day's options: the world bundle, the months, the fund size.
# --world <folder> builds the bundle once; --world alone reuses it. None if it cannot be had.
def day_env(args: list[str]) -> dict | None:
    extra = {}
    if "--world" in args:
        given = value(args, "--world")
        target = ROOT / "data" / ("world_fake" if given == "fake" else "world")
        reuse = given == "fake" and (target / "features_monthly.parquet").exists()
        if given and not reuse:
            build = (
                ["fake"] if given == "fake" else ["build", str(Path(given).expanduser().resolve())]
            )
            command = [sys.executable, "-m", "fiam.world", *build]
            if subprocess.run(command, env=child_env()).returncode:
                return None
        if not (target / "features_monthly.parquet").exists():
            print("--world needs the finals data once:  uv run run.py --world <folder>")
            return None
        extra["FIAM_DATA_DIR"] = str(target)
    if "--window" in args:
        position = args.index("--window")
        months = args[position + 1 : position + 3]
        if len(months) < 2:
            print("--window needs two months, e.g.  --window 2021-01 2025-12")
            return None
        extra["FIAM_WINDOW"] = ",".join(months)
    if value(args, "--capital"):
        extra["FIAM_CAPITAL"] = value(args, "--capital")
    return extra


# One data tool; one needing its own package runs in an isolated env.
def data_tool(source: str, rest: list[str], light: bool = False) -> int:
    script, extra, _ = DATA_TOOLS[source]
    path = str(ROOT / "tools" / "data" / script)
    if extra is None or light:
        return subprocess.run([sys.executable, path, *rest]).returncode
    command = ["uv", "run", "--no-project", "--isolated", "--exclude-newer", CARBON_CUTOFF]
    command += ["--with", extra, "python", path, *rest]
    return subprocess.run(command).returncode


# --data: status, verify, rebuild <source> <verbs>, or <source> <verb ...>.
def data_command(rest: list[str]) -> int:
    status = [sys.executable, str(ROOT / "tools" / "data" / "status.py")]
    if rest == ["status"]:
        return subprocess.run([*status, "status"]).returncode
    if rest == ["verify"]:
        failed = [s for s in DATA_TOOLS if data_tool(s, ["verify"], light=True)]
        from fiam import data as bundle

        wrong = bundle.checksum_mismatches()
        print(f"bundle: organizer checksums {'match' if not wrong else f'DIFFER {wrong}'}")
        failed += ["bundle"] if wrong else []
        print("All data verified." if not failed else f"Problems in: {failed}")
        return 1 if failed else 0
    if rest[:1] == ["rebuild"] and len(rest) > 2 and rest[1] in DATA_TOOLS:
        source, verbs = rest[1], rest[2:]
        with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="rebuild_") as scratch:
            code = data_tool(source, [*verbs, "--into", scratch])
            folder = DATA_TOOLS[source][2]
            compare = [*status, "compare", f"{scratch}/{folder}", str(ROOT / "data" / folder)]
            return code or subprocess.run(compare).returncode
    if rest[:1] and rest[0] in DATA_TOOLS:
        return data_tool(rest[0], rest[1:])
    print("Usage: uv run run.py --data status | verify | rebuild <source> <verb> | <source> <verb>")
    return 2


# Reads the options, then runs every step they ask for, in order.
def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    # Kit verbs run before any data check, so a bare clone can use them.
    if args[:1] and args[0] in ("setup", "doctor", "export", "installers", "caches"):
        from fiam.v4 import kit

        return kit.main(args)
    if "-h" in args or "--help" in args:
        print(HELP)
        return 0
    if "--export-data" in args:
        return export_data()
    if "--data" in args:
        return data_command(args[args.index("--data") + 1 :])
    everything = "--all" in args
    ml, agents = everything or "--ml" in args, everything or "--agents" in args
    if not ready(ml):
        return 1
    # Imports come first, so one command can add data or results and then use them.
    for position, flag in enumerate(args):
        if flag != "--import":
            continue
        if position + 1 >= len(args):
            print(
                "--import needs a folder or fiam_v1.zip, e.g.  uv run run.py --import ~/Downloads"
            )
            return 1
        import_from(Path(args[position + 1]).expanduser())
    day = day_env(args)
    if day is None:
        return 1
    if "--v2" in args:
        names = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--switch"] or ["v2"]
        return execute("fiam.v2 " + " ".join(names), child_env(day))
    if "--crowd-quick" in args:
        extra = {}
        for flag in ("--agents", "--months", "--minutes"):
            if flag in args and args.index(flag) + 1 < len(args):
                extra[f"FIAM_{flag[2:].upper()}"] = args[args.index(flag) + 1]
        return execute("fiam.agents.crowd_lab quick", child_env(extra))
    if "--rules" in args:
        if not value(args, "--rules"):
            print("--rules needs the rules as text or PDF, e.g.  --rules finals_rules.pdf")
            return 1
        source = Path(value(args, "--rules")).expanduser().resolve()
        command = [sys.executable, "-m", "fiam.agents.rules_reader", str(source)]
        code = subprocess.run(command, env=child_env(day)).returncode
        if not code:
            print(f"Check mandates/{source.stem}_draft.json against the rules, then run:")
            print(f"  uv run run.py --finals mandates/{source.stem}_draft.json")
        return code
    if "--finals-drill" in args:
        position = args.index("--finals-drill") + 1
        if position >= len(args):
            print("--finals-drill needs the rules as text, e.g. out/v2/inputs/case_2025.txt")
            return 1
        env = child_env({"FIAM_RULES": str(Path(args[position]).resolve())} | day)
        return execute("fiam.agents.rules_reader drill", env)
    if "--finals-pack" in args:
        if not (ROOT / "out" / "v2" / "evidence.json").exists():
            print("--finals-pack rebuilds the decks from our results, which this folder lacks.")
            print("Add them first:  uv run run.py --import fiam_results.zip --finals-pack")
            return 1
        env = child_env({})
        # The submitted book's charts are redrawn only with its data; without it the committed ones
        # stand, and the decks read final v3's charts from its pack.
        data = all((BUNDLE / name).is_file() for name in CORE)
        modules = ["fiam.report.charts"] if data else []
        for module in [*modules, "fiam.report.figures", "fiam.report.clips", "fiam.report.qa"]:
            if execute(module, env):
                return 1
        deck = [sys.executable, str(ROOT / "tools" / "build_deck_finals.py"), "--pdf"]
        # The deck presents final v3 (v2_amendment_3.md) over its own pack once that exists.
        evidence = ROOT / "out" / "v2" / "evidence.json"
        report = json.loads(evidence.read_text()) if evidence.exists() else {}
        name = report.get("v3", {}).get("final", {}).get("name")
        pack = ROOT / "out" / "finals" / f"{name}@1e7"
        if name and (pack / "submission" / "metrics.json").exists():
            env = child_env({"FIAM_OUT": str(pack)})
        return subprocess.call(deck, env=env)
    if "--finals" in args:
        position = args.index("--finals") + 1
        if position >= len(args):
            print("--finals needs a mandate, e.g.  uv run run.py --finals mandates/case_2025.json")
            return 1
        env = child_env({"FIAM_MANDATE": str(Path(args[position]).resolve())} | day)
        return execute("fiam.v2 finals", env)
    if "--pack" in args:
        if not value(args, "--pack"):
            print("--pack needs a finals book's folder, e.g.  --pack out/v2/<run>/finals")
            return 1
        folder = Path(value(args, "--pack")).expanduser().resolve()
        command = [sys.executable, "-m", "fiam.exhibits.finals_book", str(folder)]
        return subprocess.run(command, env=child_env(day)).returncode
    if "--export-results" in args:
        from fiam import kit

        digest = kit.export()
        print(f"wrote {kit.NAME}, SHA-256 {digest}. Teammates only: it holds WRDS-derived results.")
        return 0
    fresh, smoke = "--fresh" in args, "--smoke" in args
    official = "--official" in args and not smoke
    if "--world" in args:
        print("The finals data is ready. Next:  uv run run.py --world --finals <mandate>")
        return 0

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
    # The analyst is an agent inside the model steps, so a run without --agents skips it.
    learning = [s for s in ML_STEPS if agents or not s[0].startswith("fiam.agents.")]
    models = learning + ([] if smoke else RESEARCH_STEPS)
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
