# The one-word commands behind uv run fiam <verb>.

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELP = """uv run fiam <verb>

  check                     tests, ruff, the comment scan and doctor
  rerun [folder]            rebuilds the whole fund from the data, every stage
                            in order, into out/vfinal or the folder given
  compare [folder]          compares a rebuild (default out/vfinal) with the
                            locked outputs, file by file
  verify                    checks the lock (code, record, pinned files, recipe,
                            inputs and package versions), then the outputs
  export [folder]           writes the finals kit and repo.bundle to the USB
                            (--dry-run, --skip)
  setup [kit]               restores the finals kit from the USB, then doctor
  doctor [--deep]           checks Python, packages, data, the kit and the AI link
  help                      this list

Rows public after 2020-12-31 stay closed unless the data gate holds. It
holds only while frozen/vfinal/vfinal.sha256 verifies and
frozen/vfinal/opened.json holds its record. Tests always run blind.
"""
# The rebuild's stages in order, as fiam/vfinal/run.py runs them.
STAGES = ("forecast", "plus", "risk", "mid", "books", "report")
# What each stage does, as MAIN.py's header lists them.
WHAT = {
    "forecast": "E-LASSO's inputs, its monthly walk-forward refits and the regime rho",
    "plus": "the three extras (SYY-10, SUE forecast, short interest) and el_plus's refits",
    "risk": "the risk model, the market frames and the coverage on our prices",
    "mid": "the mid-month inputs from refreshed prices and their forecasts",
    "books": "the core book from US$1bn, then the scaled book, every rule each day",
    "report": "the 23 rows, flat costs, Arcana files, holdings, months, finals check",
}
# The checks run by check, each a command from the repository root.
CHECKS = [
    ("tests", ["-m", "pytest", "-q"]),
    ("ruff", ["-m", "ruff", "check", "."]),
    ("format", ["-m", "ruff", "format", "--check", "fiam", "run.py", "tests", "tools"]),
    ("comments", ["tools/comments.py"]),
]


# One Python module or script from the root; its exit code.
def python(*args: str, env: dict | None = None) -> int:
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env).returncode


# Tests, ruff, the comment scan and doctor; every one runs.
def check() -> int:
    failed = [name for name, args in CHECKS if python(*args)]
    from fiam.vfinal import kit

    if kit.main(["doctor"]):
        failed.append("doctor")
    print("check passed" if not failed else f"check failed: {', '.join(failed)}")
    return 1 if failed else 0


# Every stage in its own process, into out/vfinal or a folder given.
def rerun(args: list[str]) -> int:
    if len(args) > 1:
        print("uv run fiam rerun [folder]")
        return 2
    env = os.environ | ({"FIAM_VFINAL_OUT": str(Path(args[0]).resolve())} if args else {})
    return python("-m", "fiam.vfinal", "run", env=env)


# The lock checked in full, then the outputs it records.
def verify() -> int:
    from fiam.vfinal import config, lock

    bad = lock.verify()
    print("\n".join(bad) if bad else f"{lock.rel(lock.SHA)} verifies, the gate is open")
    if not config.OUT.is_dir():
        print(f"{lock.rel(config.OUT)} is not here, so no output is compared")
        return 1 if bad else 0
    return compare([]) or (1 if bad else 0)


# A rebuild's outputs against the locked ones, file by file.
def compare(args: list[str]) -> int:
    if len(args) > 1:
        print("uv run fiam compare [folder]")
        return 2
    return python("-m", "fiam.vfinal", "compare", *args)


# Reads the verb and runs it; help for anything else.
def main(args: list[str]) -> int:
    verb, rest = (args[0] if args else "help"), args[1:]
    if verb == "check":
        return check()
    if verb == "rerun":
        return rerun(rest)
    if verb == "verify" and not rest:
        return verify()
    if verb == "compare":
        return compare(rest)
    if verb in ("export", "setup", "doctor", "installers", "caches"):
        from fiam.vfinal import kit

        return kit.main([verb, *rest])
    print(HELP)
    return 0 if verb in ("help", "-h", "--help") else 2
