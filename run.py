# Runs everything in the right order so the numbers and the write-up can never disagree.
# Use this instead of calling the four scripts by hand.

import subprocess
import sys

STEPS = [
    ("src/pipeline.py", "building the portfolio"),
    ("src/report.py", "copying the numbers into RESULTS.md"),
    ("src/charts.py", "drawing the charts"),
    ("src/check_docs.py", "checking nothing is out of date"),
]


def main() -> int:
    for script, doing in STEPS:
        print(f"\n[{doing}]")
        # Stop at the first failure. A later step reading half-written output would be worse
        # than no output at all.
        if subprocess.run([sys.executable, script]).returncode != 0:
            print(f"\n{script} failed, stopping here.")
            return 1
    print("\nDone. submission/ and RESULTS.md are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
