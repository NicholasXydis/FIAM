# The long-job keeper: a crash retried, a stall stopped, done ends.

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "keep.py"


# Runs the keeper on a tiny Python job; returns its exit and the log.
def keep(tmp_path, code: str, *flags) -> tuple:
    log = tmp_path / "job.log"
    cmd = [sys.executable, str(TOOL), "--log", str(log), "--poll", "1", "--pause", "0", *flags,
           "--", sys.executable, "-c", code]  # fmt: skip
    got = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return got.returncode, log.read_text()


# A job that fails once then succeeds is retried until it is done.
def test_crash_is_retried(tmp_path):
    flag = tmp_path / "ran"
    code = (
        f"import pathlib,sys; p=pathlib.Path(r'{flag}'); ok=p.exists(); p.touch(); "
        "sys.exit(0 if ok else 3)"
    )
    rc, log = keep(tmp_path, code, "--tries", "3")
    assert rc == 0 and log.count("== keep: try") == 2


# A silent job is stopped and retried; a refused rerun counts as done.
def test_stall_is_stopped_and_done_ends(tmp_path):
    rc, log = keep(tmp_path, "import time; time.sleep(30)", "--tries", "2", "--stall", "2")
    assert rc == 1 and log.count("no progress for 2 s") == 2
    rc, _ = keep(tmp_path, "raise SystemExit('x.json exists: each stage runs once per commit')")
    assert rc == 0
