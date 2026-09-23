# The experiment ledger behind the deflated-Sharpe probability. Writes config_log.csv.
#
# One row per experiment with its run count. "ridge 15/20/30/45/60" is five runs, not one.

import csv
from pathlib import Path

OUT = Path("submission/exhibits")

# Eligible means it could have shipped had it won. Attempts sum to pipeline.py's counts.
TRIALS = [
    # --- neutralization, the choices that shaped the book ---
    ("beta_60m only", "neutralization", True, 1, "realized beta -0.52", "rejected"),
    ("beta_60m + volatility complex", "neutralization", True, 1, "realized beta -0.10", "SHIPPED"),
    ("sector GICS-2", "neutralization", True, 1, "max tilt 1.1%", "SHIPPED"),
    ("sector ff49", "neutralization", True, 1, "7.3% of groups under 5 names", "rejected"),
    (
        "also neutral on size and value",
        "neutralization",
        True,
        1,
        "IR 0.85 to 0.75, DD -24%",
        "rejected",
    ),
    # --- construction ---
    ("equal-weight 12 signals", "construction", True, 1, "IR 0.85", "SHIPPED"),
    ("carry-in rule", "construction", True, 1, "IR 0.73 to 0.85", "SHIPPED, post-hoc"),
    ("conviction scaling", "construction", True, 1, "signal t 3.10 to 3.10", "rejected"),
    ("signal-agreement gate", "construction", True, 1, "signal t 3.07", "rejected"),
    ("within-sector ranking", "construction", True, 1, "signal t 2.94", "rejected"),
    ("median instead of mean", "construction", True, 1, "signal t 2.84", "rejected"),
    ("winsorised z +/-2", "construction", True, 1, "signal t 3.10", "rejected"),
    ("divided by dispersion", "construction", True, 1, "IR 0.93", "not adopted"),
    ("8 theme blocks", "construction", True, 1, "IR 0.97", "not adopted"),
    (
        "vol-matched legs",
        "construction",
        True,
        1,
        "IR 0.79 but net +0.83",
        "rejected, breaks mandate",
    ),
    ("inverse-vol weighting", "construction", True, 1, "IR 0.55", "rejected"),
    ("vol target 10/8/6%", "construction", True, 3, "IR 0.34/0.26/0.15", "rejected"),
    # --- optimizer settings, swept ---
    ("ridge 15/20/30/45/60", "optimizer", True, 5, "IR 0.81/0.84/0.85/0.78/0.76", "30 SHIPPED"),
    (
        "pool 100/150/200/300/400",
        "optimizer",
        True,
        5,
        "IR 0.75/0.82/0.85/0.85/0.85",
        "200 SHIPPED",
    ),
    ("turnover penalty 0.25-2.0", "optimizer", True, 4, "IR 0.49-0.54, all worse", "rejected"),
    ("shorts restricted to >$1bn", "optimizer", True, 1, "IR 0.52 to 0.41", "rejected"),
    # --- signals considered ---
    ("12 more theory-signed signals", "signals", True, 12, "IR 0.48", "rejected"),
    (
        "single best added signal",
        "signals",
        True,
        12,
        "IR 0.86, 6 of 12 helped",
        "rejected, coin flip",
    ),
    ("broad theme composite, 41 chars", "signals", True, 1, "IR 0.28, DD -45%", "rejected"),
    ("factor-agreement filter", "signals", True, 3, "IR 0.49/0.34/0.32", "rejected"),
    ("1m and 3m reversal", "signals", True, 2, "neutralized t -0.33 / -1.12", "rejected"),
    ("lottery demand, illiquidity", "signals", True, 2, "neutralized t -0.46 / -0.12", "rejected"),
    ("seasonality", "signals", True, 1, "neutralized t 1.22", "rejected"),
    # --- text, all rejected ---
    ("Loughran-McDonald tone", "text", True, 1, "t -2.41 raw, 0.44 neutralized", "rejected"),
    ("8-K filing intensity", "text", True, 1, "t 2.05 neutralized, decile table fails", "rejected"),
    ("8-K signed item codes", "text", True, 1, "t 0.06 neutralized", "rejected"),
    # --- models, comparison exhibits, never in contention ---
    ("ElasticNet on 147 chars", "model", False, 1, "IC t 2.55, IR -0.52", "exhibit"),
    ("LightGBM on 147 chars", "model", False, 1, "IC t 3.60, IR -0.37", "exhibit"),
    ("NN3 on 147 chars", "model", False, 1, "IC t 3.89, IR -0.24", "exhibit"),
    ("Ridge a=100/1000", "model", False, 2, "IC t 3.73 / 3.65", "exhibit"),
    ("PLS 5/15 components", "model", False, 2, "IC t 4.05 / 3.70", "exhibit"),
    ("RandomForest depth 6", "model", False, 1, "IC t 3.25", "exhibit"),
    ("ExtraTrees depth 6", "model", False, 1, "IC t 3.85", "exhibit"),
    ("LightGBM on residual target", "model", False, 1, "IC t 3.43", "exhibit"),
    ("composite + ML blends", "model", False, 1, "t 2.05 falls to 0.52", "exhibit"),
    ("MSE target instead of rank", "model", False, 1, "IC 0.0142 vs 0.0610", "exhibit"),
    ("page-23 fundamental forecast", "model", False, 1, "t 3.53 vs 3.66 for the level", "exhibit"),
    ("fundamental changes not levels", "model", False, 1, "t 1.72 vs 3.87", "exhibit"),
    # --- controls, run to answer a question ---
    (
        "792 five-signal subsets",
        "control",
        False,
        792,
        "IR 0.45-1.26, early-late corr -0.36",
        "control",
    ),
    ("200-combination search", "control", False, 200, "+1.87 in sample, +0.16 sealed", "control"),
    ("cost sensitivity 1x-4.8x", "control", False, 5, "break-even at 16.2%", "control"),
    ("drawdown override policy", "control", False, 1, "documented, not applied", "control"),
    # The pre-WRDS freeze. All controls, so none of them deflates the Sharpe.
    ("NN3 five-seed sweep", "control", False, 5, "IR -1.38 to -0.24, mean -0.80", "control"),
    (
        "constraint survival, 5 stages x 4 models",
        "control",
        False,
        20,
        "neutralization helps all, costs sink three",
        "control",
    ),
    ("permutation null, 200 draws", "control", False, 200, "see placebo_lab.json", "control"),
    ("inversion of the composite", "control", False, 1, "see placebo_lab.json", "control"),
    ("stale scores, one month lag", "control", False, 1, "see placebo_lab.json", "control"),
    # Slowing the models down. Eligible, a winner would have shipped. None beat us.
    (
        "cost-aware blend, 3 models x 5 weights",
        "model",
        True,
        15,
        "best IR -0.15 vs composite +0.85",
        "rejected",
    ),
    ("signal decay by model", "control", False, 4, "all retain 83-97% after a month", "control"),
]


# Writes the ledger and prints the two attempt counts the statistic deflates by.
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "config_log.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["experiment", "family", "eligible_for_deployment", "attempts", "result", "verdict"]
        )
        for name, family, eligible, attempts, result, verdict in TRIALS:
            writer.writerow([name, family, "yes" if eligible else "no", attempts, result, verdict])

    eligible = sum(row[3] for row in TRIALS if row[2])
    everything = sum(row[3] for row in TRIALS)
    print(f"{len(TRIALS)} experiment families, {eligible} eligible attempts, {everything} in all")
    print(f"  written to {path}")
    print("  pipeline.py deflates by these two numbers; they must match DESIGN_TRIALS/ALL_TRIALS")


if __name__ == "__main__":
    main()
