# Catches numbers in RESULTS.md that we typed by hand and then forgot to update.
# Run it after report.py. It only tells you what to look at, it never changes the file.

import json
import re
import sys
from pathlib import Path

METRICS = Path("submission/metrics.json")
TARGET = Path("RESULTS.md")

# report.py already keeps the table between these markers up to date, so skip it.
AUTO = re.compile(r"<!--AUTO:headline-->.*?<!--/AUTO:headline-->", re.S)

# The numbers we also write out in the text, further down the file.
# We leave out old figures we quote deliberately, like "IR went from 0.47 to 0.73",
# because those are history and should never move.
WATCHED = [
    ("performance.information_ratio", "{:.2f}"),
    ("performance.sharpe_ratio", "{:.2f}"),
    ("robustness.deflated_sharpe_60_design_choices", "{:.2f}"),
    ("robustness.deflated_sharpe_860_all_configurations", "{:.2f}"),
]


# Finds one value in the results file. "performance.sharpe_ratio" means look in the
# performance group, then take sharpe_ratio.
def dig(data: dict, path: str):
    for key in path.split("."):
        data = data[key]
    return data


# Compares each number we watch against the results file and reports any that no longer match.
def main() -> int:
    metrics = json.loads(METRICS.read_text())
    # Cut out the table before searching. It already has every number in it, so leaving it in
    # would make everything look fine whether it is or not.
    written = AUTO.sub("", TARGET.read_text(encoding="utf-8"))

    stale = []
    for path, fmt in WATCHED:
        current = fmt.format(dig(metrics, path))
        if current not in written:
            stale.append((path, current))

    # Not an error. Sometimes we stop mentioning a number on purpose, so this just tells you
    # where to go and check.
    if stale:
        print("RESULTS.md might be out of date. These numbers are not in it anywhere:")
        for path, value in stale:
            print(f"  {path} is now {value}")
        print("\nCheck the sections that mention them, then run this again.")
        return 1

    print(f"RESULTS.md matches metrics.json ({len(WATCHED)} values checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
