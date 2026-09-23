# Runs everything in order so the numbers and the write-up cannot disagree. --ml adds models.

import subprocess
import sys

STEPS = [
    (["src/pipeline.py"], "building the portfolio"),
    # Straight after the pipeline, which rewrites holdings.csv and drops repaired labels.
    (["src/exhibits/label_repair.py"], "filling in the missing tickers"),
    (["src/exhibits/freeze.py"], "pinning the baseline and the acceptance rules"),
    (["src/exhibits/subperiod.py"], "splitting the record into sub-periods"),
    (["src/exhibits/costs.py"], "breaking down the costs"),
    (["src/exhibits/completeness.py"], "collecting the statistics the rules list"),
    (["src/agents/event_triage.py"], "scoring filings with the item-code rule"),
    (["src/exhibits/risk_decomposition.py"], "decomposing the risk"),
    (["src/exhibits/config_log.py"], "writing the configuration ledger"),
    (["src/agents/devils_advocate.py"], "building the retrospective devil's-advocate pack"),
    (["src/report.py"], "copying the numbers into RESULTS.md"),
    (["src/charts.py"], "drawing the charts"),
    (["src/exhibit_charts.py"], "drawing the research charts"),
    (["src/check_docs.py"], "checking nothing is out of date"),
    (["src/agents/reproducibility.py"], "auditing for look-ahead and survivorship"),
]

# Model comparison and research controls. Behind a flag because they take hours.
#
# Order matters. Each model is fitted, then scored into a book, before collect.py reads it.
ML_STEPS = [
    (["src/ml/dataset.py"], "building the training folds"),
    (["src/ml/train_enet.py"], "fitting ElasticNet"),
    (["src/ml/train_lgbm.py"], "fitting LightGBM"),
    (["src/ml/train_nn3.py"], "fitting the neural net"),
    (["src/ml/run_through_optimizer.py", "enet"], "scoring ElasticNet into a book"),
    (["src/ml/run_through_optimizer.py", "lgbm"], "scoring LightGBM into a book"),
    (["src/ml/run_through_optimizer.py", "nn3"], "scoring the neural net into a book"),
    (["src/ml/decile_tables.py"], "building the decile tables"),
    (["src/ml/subset_sweep.py"], "sweeping the signal subsets"),
    (["src/ml/collect.py"], "collecting the model numbers"),
    (["src/ml/nn3_seeds.py"], "refitting the neural net on five seeds"),
    (["src/ml/signal_decay.py"], "measuring how fast each score goes stale"),
    (["src/ml/cost_aware.py"], "testing whether slowing the models down saves them"),
    # 200 shuffled runs of the whole book, so it sits with the slow work.
    (["src/exhibits/placebo_lab.py"], "running the permutation and falsification controls"),
    (["src/exhibits/constraint_survival.py"], "tracing where prediction becomes tradeable"),
    (["src/exhibits/turnover_sweep.py"], "testing whether trading less would help"),
    (["src/agents/signal_discovery.py"], "running the deterministic signal search"),
]


# Runs each step in order and stops at the first failure.
def main() -> int:
    # Models run before the report and charts, or those read last run's artifacts.
    steps = ML_STEPS + STEPS if "--ml" in sys.argv else STEPS
    for command, doing in steps:
        print(f"\n[{doing}]")
        # Stop at the first failure, or a later step reads half-written output.
        if subprocess.run([sys.executable, *command]).returncode != 0:
            print(f"\n{command[0]} failed, stopping here.")
            return 1
    print("\nDone. submission/ and RESULTS.md are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
