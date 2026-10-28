# The one-word commands behind uv run fiam <verb>.

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELP = """uv run fiam <verb>

  check                     tests, ruff, the comment scan and doctor
  rerun                     every headline stage at this commit in order, then pick
  stage <name> [args]       one headline stage, one of
                              labels
                              forecasts <yearly|quarterly>
                              early <yearly|quarterly> <tight|loose>
                              book <yearly|quarterly> <tight|loose>
                              report <yearly|quarterly> <tight|loose>
                              pick
  whatif <name> [commit] [early]
                            one in-sample what-if book (commit defaults to HEAD)
  whatif summary [commit]   every finished what-if's key rows in one table
  compare [commit]          compares a rerun's headline outputs at commit
                            (default HEAD) with the locked run, by content
  lock [commit]             hashes the code, settings and pinned files, and
                            records the digests of the headline run at commit
  verify                    checks the lock, then the headline outputs it records
  audit                     compares the headline outputs with the lock's record
  export [folder]           writes the finals kit and repo.bundle to the USB
                            (--dry-run, --skip)
  setup [kit]               restores the finals kit from the USB, then doctor
  doctor [--deep]           checks Python, packages, data, the kit and the AI link
  help                      this list

Rows public after 2020-12-31 stay closed unless the data gate holds.
Before the lock it holds when HEAD is clean, pushed and tracks
frozen/vfinal/opened.json. After it, only when frozen/vfinal/vfinal.sha256
verifies. Tests always run blind.
"""
# The headline's stages in order; pick runs last.
RERUN = [
    ("labels",),
    ("forecasts", "quarterly"),
    ("early", "quarterly", "loose"),
    ("book", "quarterly", "loose"),
    ("report", "quarterly", "loose"),
]
# Stages rerun only when pick still lists them as needed.
IF_NEEDED = {"forecasts yearly", "early quarterly tight"}
# What each stage does, as MAIN.py's header lists them.
WHAT = {
    "labels": "the sealed labels, and the as-filed SUE table rebuilt to 2026-08",
    "forecasts": "return models refit from 2017 on the cadence, forecasts to 2026-07",
    "early": "the limits on 2017-2020, blind, scored as the exam",
    "book": "the 2021-2026 book from US$1bn, every PDF limit checked each day",
    "report": "the 23-row table, the Arcana files and the market comparison",
    "pick": "cadence by pre-2021 IC, limits by pre-2021 IR; names the headline",
}
# The pick a rerun must reproduce.
HEADLINE = ("quarterly", "loose")
# The checks run by check, each a command from the repository root.
CHECKS = [
    ("tests", ["-m", "pytest", "-q"]),
    ("ruff", ["-m", "ruff", "check", "."]),
    ("format", ["-m", "ruff", "format", "--check", "fiam", "run.py", "tests", "tools"]),
    ("comments", ["tools/comments.py"]),
]


# One Python module or script from the root; its exit code.
def python(*args: str) -> int:
    return subprocess.run([sys.executable, *args], cwd=ROOT).returncode


# One headline stage in its own process, as its module runs it.
def stage(args: list[str]) -> int:
    return python("-m", "fiam.vfinal.headline", *args)


# Tests, ruff, the comment scan and doctor; every one runs.
def check() -> int:
    failed = [name for name, args in CHECKS if python(*args)]
    from fiam.vfinal import kit

    if kit.main(["doctor"]):
        failed.append("doctor")
    print("check passed" if not failed else f"check failed: {', '.join(failed)}")
    return 1 if failed else 0


# The stages in order, those done at this commit skipped, then pick.
def rerun() -> int:
    from fiam.vfinal import gates, headline

    try:
        head = gates.commit()
    except RuntimeError as err:
        print(f"refused: {err}")
        return 1
    done = lambda args: headline.where(args[0], args[1:], head).exists()  # noqa: E731
    for args in RERUN:
        if done(args):
            print(f"{' '.join(args)} done at {head[:12]}, skipped")
        elif stage(list(args)):
            return 1
    # Pick names any piece its rules still need; only listed ones run.
    while True:
        wanted = headline.pick(head)["next"]
        extra = [w for w in wanted if w in IF_NEEDED]
        if not extra:
            break
        if stage(extra[0].split()):
            return 1
    if stage(["pick"]):
        return 1
    got = json.loads(headline.where("pick", (), head).read_text())
    if not got["final"] or (got["cadence"], got["limits"]) != HEADLINE:
        print(f"pick did not reproduce {' '.join(HEADLINE)}: {got['cadence']} {got['limits']}")
        print(f"still needed: {got['next']}")
        return 1
    print(f"rerun done, headline {got['headline']}")
    return 0


# HEAD's full commit name, read from git.
def head_commit() -> str:
    got = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return got.stdout.strip()


# One what-if variant at a commit, or the summary of every variant.
def whatif(args: list[str]) -> int:
    from fiam.vfinal import whatif as w

    early = args[-1:] == ["early"]
    rest = args[:-1] if early else args
    if not rest or rest[0] not in (*w.VARIANTS, "summary") or len(rest) > 2:
        print("uv run fiam whatif <name> [commit] [early] | summary [commit]")
        print("names " + ", ".join(w.VARIANTS))
        return 2
    at = rest[1] if len(rest) == 2 else head_commit()
    return python("-m", "fiam.vfinal.whatif", rest[0], at, *(["early"] if early else []))


# The lock written, or checked with the headline outputs beside it.
def lock_verbs(verb: str, args: list[str]) -> int:
    from fiam.vfinal import lock

    if verb == "lock":
        if len(args) > 1:
            print("uv run fiam lock [commit]")
            return 2
        done = lock.lock(args[0] if args else None)
        print(f"wrote {lock.rel(lock.SHA)} ({len(done)} files) and {lock.rel(lock.OUTPUTS)}")
        return 0
    bad = []
    if verb == "verify" and not lock.SHA.is_file():
        bad = [f"{lock.rel(lock.SHA)} is not made yet"]
        state = "open" if lock.recorded() else "closed"
        print(f"no lock yet, so the record decides and the gate is {state}")
    elif verb == "verify":
        bad = lock.verify()
        print("\n".join(bad) if bad else f"{lock.rel(lock.SHA)} verifies, the gate is open")
    if not lock.OUTPUTS.is_file():
        print(f"{lock.rel(lock.OUTPUTS)} is not made yet, so no output is compared")
        return 1
    changed, absent = lock.compare()
    print("\n".join(changed) if changed else "headline outputs match the lock's record")
    if absent:
        print(f"{len(absent)} recorded outputs are not present here")
    return 1 if bad or changed else 0


# Reads the verb and runs it; help for anything else.
def main(args: list[str]) -> int:
    verb, rest = (args[0] if args else "help"), args[1:]
    if verb == "check":
        return check()
    if verb == "rerun":
        return rerun()
    if verb == "stage":
        return stage(rest)
    if verb == "whatif":
        return whatif(rest)
    if verb in ("lock", "verify", "audit"):
        return lock_verbs(verb, rest)
    if verb == "compare" and len(rest) <= 1:
        from fiam.vfinal import compare

        return compare.compare(*rest)
    if verb in ("export", "setup", "doctor"):
        from fiam.vfinal import kit

        return kit.main([verb, *rest])
    print(HELP)
    return 0 if verb in ("help", "-h", "--help") else 2
