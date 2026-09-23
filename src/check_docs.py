# Flags hand-typed numbers in RESULTS.md that no longer match. Never edits the file.
#
# It watches a named list, not every figure, so a clean run means those values match.

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import ALL_TRIALS, DESIGN_TRIALS

METRICS = Path("submission/metrics.json")
ML_METRICS = Path("submission/exhibits/ml_metrics.json")
SUBPERIOD = Path("submission/exhibits/subperiod.json")
SURVIVAL = Path("submission/exhibits/constraint_survival.json")
SEEDS = Path("submission/exhibits/nn3_seeds.json")
TARGET = Path("RESULTS.md")

# report.py already keeps the table between these markers up to date, so skip it.
MINUS = "−"

AUTO = re.compile(r"<!--AUTO:headline-->.*?<!--/AUTO:headline-->", re.S)

# Numbers repeated in the prose. Figures we quote as history are deliberately left out.
WATCHED = [
    ("performance.information_ratio", "{:.2f}"),
    ("performance.sharpe_ratio", "{:.2f}"),
    # Built from the pipeline's own constants, so a rename cannot leave these stale.
    (f"robustness.deflated_sharpe_probability_{DESIGN_TRIALS}_eligible_attempts", "{:.2f}"),
    (f"robustness.deflated_sharpe_probability_{ALL_TRIALS}_all_attempts", "{:.2f}"),
]

# Model comparison numbers, in their own file because that run is much slower.
ML_WATCHED = [
    ("composite.ic_t", "{:.2f}"),
    ("enet.ic_t", "{:.2f}"),
    ("lgbm.ic_t", "{:.2f}"),
    ("nn3.ic_t", "{:.2f}"),
    ("enet.information_ratio", "{:.2f}"),
    ("lgbm.information_ratio", "{:.2f}"),
    ("nn3.information_ratio", "{:.2f}"),
    ("subset_sweep.early_late_correlation", "{:.2f}"),
    # These drifted once, -0.013 against -0.012, so both are watched now.
    ("enet.oos_r2", "{:.3f}"),
    ("enet.months_with_no_view", "{:d}"),
]

# The sub-period split, because the prose quotes it and a judge will check it first.
SUBPERIOD_WATCHED = [
    ("full_2021_2026.information_ratio", "{:.2f}"),
    ("second_half_2023_2026.information_ratio", "{:.2f}"),
]

# The constraint-survival stages. M2 has been corrected twice, so check every one.
SURVIVAL_WATCHED = [
    ("models.composite.portfolio.constrained.net_ir", "{:+.2f}"),
    ("models.lgbm.portfolio.optimizer.net_ir", "{:+.2f}"),
    ("models.lgbm.portfolio.constrained.net_ir", "{:+.2f}"),
    ("models.enet.portfolio.optimizer.net_ir", "{:+.2f}"),
    ("models.lgbm.portfolio.after_costs.turnover", "{:.0%}"),
    ("models.nn3.portfolio.after_costs.turnover", "{:.0%}"),
    ("models.enet.portfolio.after_costs.turnover", "{:.0%}"),
    ("models.lgbm.portfolio.after_costs.gross_annual", "{:.1%}"),
    ("models.nn3.portfolio.after_costs.gross_annual", "{:.1%}"),
    ("models.enet.portfolio.after_costs.gross_annual", "{:.1%}"),
]

# The seed range, because quoting the single shipped seed without it would read as selection.
SEEDS_WATCHED = [
    ("spread.information_ratio.min", "{:.2f}"),
    ("spread.information_ratio.mean", "{:.2f}"),
]


# Finds one value. "performance.sharpe_ratio" means that group, then that key.
def dig(data: dict, path: str):
    for key in path.split("."):
        data = data[key]
    return data


# Compares each number we watch against the results file and reports any that no longer match.
def main() -> int:
    # Cut the table first. It holds every number, so leaving it in passes everything.
    written = AUTO.sub("", TARGET.read_text(encoding="utf-8"))

    # Collect every source first, so none is appended after the check and skipped.
    sources = [(METRICS, WATCHED)]
    if ML_METRICS.exists():
        sources.append((ML_METRICS, ML_WATCHED))
    if SUBPERIOD.exists():
        sources.append((SUBPERIOD, SUBPERIOD_WATCHED))
    if SURVIVAL.exists():
        sources.append((SURVIVAL, SURVIVAL_WATCHED))
    if SEEDS.exists():
        sources.append((SEEDS, SEEDS_WATCHED))

    stale, checked = [], 0
    for path, watched in sources:
        data = json.loads(path.read_text())
        for key, fmt in watched:
            checked += 1
            current = fmt.format(dig(data, key))
            # Prose uses a real minus sign, so a negative number has to match either form.
            if current not in written and current.replace("-", MINUS) not in written:
                stale.append((key, current))

    if stale:
        print("RESULTS.md might be out of date. These numbers are not in it anywhere:")
        for key, value in stale:
            print(f"  {key} is now {value}")
        print("Check the sections that mention them, then run this again.")
        return 1

    print(f"RESULTS.md matches the generated numbers ({checked} values checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
