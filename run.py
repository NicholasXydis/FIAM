# One command for the final fund; uv run run.py --help lists options.

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HELP = """uv run run.py [verb]   (MAIN.py passes its arguments here)
  no verb              checks the carried results in frozen/vfinal/final/: every PDF
                       rule on every day, the headline recomputed from daily.csv and
                       the FRED series, and the code against the lock, in seconds.
                       With the organisers' files in data/organisers/ or beside
                       MAIN.py it also checks their SHA-256 against our receipts and
                       replays our daily stock P&L on their daily returns
  check, rerun, compare, verify
                       the final fund's verbs, the same as uv run fiam <verb>;
                       uv run fiam help lists them
  setup [kit]          restores the finals kit from the USB, missing files only, then doctor
  doctor [--deep]      checks Python, packages, data, the kit's files, settings and the AI link
  export [folder]      writes the finals kit and repo.bundle to the USB, rewriting only
                       parts that changed; --dry-run shows sizes, --skip PART,PART leaves
                       parts out
  installers, caches   uv, Node and pnpm for every machine; this machine's offline packages
  --data status        every data source: files, sizes, USB budget, licence (data/INVENTORY.json)
  --data verify        every saved file against its receipt, and the organisers' checksums
  --data rebuild <source> <verb ...>   rebuilds into a scratch folder and compares with ours
  --data <source> <verb ...>   one data tool: edgar, noaa, stock, carbon or amazon, e.g.
                       --data carbon plan <spec> (prices, buys nothing); carbon buy and rebuy
                       spend tokens, so they run only by hand; --data amazon fetch [category]"""

# The final fund's verbs, passed to fiam/vfinal/cli.py as given.
FINAL_VERBS = ("check", "rerun", "compare", "verify")
# The finals kit's verbs, passed to fiam/vfinal/kit.py as given.
KIT_VERBS = ("setup", "doctor", "export", "installers", "caches")

ROOT = Path(__file__).resolve().parent

# Organizer files; the first three build the bundle --import feeds.
REQUIRED = [
    "chars_final_with_names.parquet",
    "8k_20150101_20260831_identified.parquet",
    "factor_char_list.csv",
]
ORGANIZER = [*REQUIRED, "readme.md"]

# The bundle, found as fiam/data.py finds it, and the files it needs.
BUNDLE = Path(os.environ.get("FIAM_DATA_DIR") or ROOT / "data" / "fiam_v1").expanduser()
CORE = ["features_monthly.parquet", "labels_monthly.parquet", "filings.parquet", "manifest.json"]

# What the carried check reads; uv brings them all.
PACKAGES = ["pandas", "numpy", "pyarrow", "statsmodels"]
# Carbon Arc's SDK, pinned, with nothing published after the cutoff.
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
    "finra": ("finra.py", None, "finra"),
    "french": ("french.py", None, "benchmarks/french_archive"),
    "fema": ("fema.py", None, "fema"),
    "openmp": ("openmp.py", None, "openmp"),
}


# The packages the carried check needs, named if any is missing.
def ready() -> bool:
    missing = [p for p in PACKAGES if not importlib.util.find_spec(p)]
    if missing:
        print(f"Missing Python packages: {', '.join(missing)}.")
        print("Run it with uv, which installs them:  uv run run.py")
        print("Or install them yourself:             python -m pip install -r requirements.txt")
    return not missing


# Unpacks a bundle zip, refusing it whole if any entry lands outside it.
def unzip(source: Path, target: Path) -> None:
    from fiam import paths

    try:
        paths.safe_unzip(source, target, target / BUNDLE.name)
    except ValueError as err:
        raise SystemExit(f"--import: {err}") from err


# A zip unpacks to data/; folders match organizer names, WRDS columns.
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


# The bundle, built once from the organizer's files in data/ if missing.
def bundle() -> bool:
    if all((BUNDLE / name).is_file() for name in CORE):
        return True
    if not all((Path("data") / name).exists() for name in REQUIRED):
        # Files beside MAIN.py or run.py count too.
        if not all(Path(name).exists() for name in REQUIRED):
            return False
        import_from(Path("."))
    print(f"Building the data bundle in {BUNDLE} from data/, once, about two minutes.", flush=True)
    build = [sys.executable, "-m", "fiam.build_data", "data"]
    return subprocess.run(build, env=child_env()).returncode == 0


# The steps' environment: one maths thread, so no OpenMP clash on macOS.
def child_env(extra: dict | None = None) -> dict:
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)} | (extra or {})
    # One maths thread and a set hash seed, so reruns repeat bit for bit.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(name, "1")
    env.setdefault("PYTHONHASHSEED", "0")
    return env


# One data tool; one needing its own package runs in an isolated env.
def data_tool(source: str, rest: list[str], light: bool = False) -> int:
    script, extra, _ = DATA_TOOLS[source]
    path = str(ROOT / "tools" / "data" / script)
    if extra is None or light:
        return subprocess.run([sys.executable, path, *rest]).returncode
    command = ["uv", "run", "--no-project", "--isolated", "--exclude-newer", CARBON_CUTOFF]
    command += ["--with", extra, "python", path, *rest]
    return subprocess.run(command).returncode


# --data: status, verify, rebuild <source> <verbs>, <source> <verb ...>.
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


# Reads the verb and runs it; no verb checks the carried results.
def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    # LightGBM's OpenMP from the kit when this machine lacks it.
    from fiam import openmp

    openmp.preload()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    # Kit verbs run before any data check, so a bare clone can use them.
    if args[:1] and args[0] in KIT_VERBS:
        from fiam.vfinal import kit

        return kit.main(args)
    if args[:1] and args[0] in FINAL_VERBS:
        from fiam.vfinal import cli

        return cli.main(args)
    if args[:1] in (["-h"], ["--help"], ["help"]):
        print(HELP)
        return 0
    if "--data" in args:
        return data_command(args[args.index("--data") + 1 :])
    if args:
        print(f"Unknown option {args[0]}. The options are:\n{HELP}")
        return 2
    if not ready():
        return 1
    from fiam.vfinal import carried

    return carried.main(ROOT)


if __name__ == "__main__":
    sys.exit(main())
