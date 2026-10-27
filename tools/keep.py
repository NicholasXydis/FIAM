# Runs a long job to its end: restarts it on a crash or a stall.

import argparse
import glob
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


# The newest change among the log and the files being watched.
def progress(patterns: list[str]) -> float:
    stamps = [os.path.getmtime(p) for pattern in patterns for p in glob.glob(pattern)]
    return max(stamps, default=0.0)


# Stops the job and every process it started.
def stop(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


# One try: the job's output to the log, stopped if nothing moves.
def attempt(cmd: list[str], log_path: str, watch: list[str], stall: int, poll: int) -> int:
    env = os.environ | {"FIAM_PROGRESS": "1", "PYTHONUNBUFFERED": "1"}
    group = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # fmt: skip
    with open(log_path, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, **group)
        seen, quiet_since = progress([log_path, *watch]), time.time()
        while proc.poll() is None:
            time.sleep(poll)
            now = progress([log_path, *watch])
            if now > seen:
                seen, quiet_since = now, time.time()
            # Silent past the limit: the job is stuck, so it is restarted.
            elif time.time() - quiet_since > stall:
                log.write(f"\n== keep: no progress for {stall} s, stopping it\n")
                log.flush()
                stop(proc)
                return -1
    return proc.returncode


# uv run python tools/keep.py --log L [--watch G] [--before CMD] -- job
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--watch", action="append", default=[])
    ap.add_argument("--before", default=None)
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("--stall", type=int, default=2400)
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--pause", type=int, default=60)
    ap.add_argument("--done", default="each stage runs once per commit")
    ap.add_argument("job", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.job[1:] if a.job[:1] == ["--"] else a.job
    for n in range(1, a.tries + 1):
        # A check before each try, such as the PC's model server being up.
        if a.before:
            subprocess.run(a.before, shell=True)
        with open(a.log, "a", encoding="utf-8") as log:
            log.write(f"\n== keep: try {n} of {a.tries} at {time.strftime('%H:%M:%S')}\n")
        start = Path(a.log).stat().st_size
        code = attempt(cmd, a.log, a.watch, a.stall, a.poll)
        with open(a.log, encoding="utf-8", errors="ignore") as fh:
            fh.seek(start)
            said = fh.read()
        # Done now, or done before: a stage refuses to run twice.
        if code == 0 or a.done in said:
            print(f"keep: done after {n} tries, log {a.log}")
            return 0
        print(f"keep: try {n} ended with {code}", flush=True)
        if n < a.tries:
            time.sleep(a.pause)
    print(f"keep: gave up after {a.tries} tries, log {a.log}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
