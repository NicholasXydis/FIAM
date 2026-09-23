# Refits NN3 on five predeclared seeds to show how much of its result is the seed.
# Reads cache/folds/, writes submission/exhibits/nn3_seeds.json.

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import dataset as D
import run_through_optimizer as R
import train_nn3 as N

OUT = Path("submission/exhibits")
PREDS = Path("cache/preds")

# Seed 42 is the one our shipped comparison used, 43-46 were added later to check it.
# Consecutive, not hand-picked. We report all five, and we knew 42's result first.
SEEDS = (42, 43, 44, 45, 46)


# Spearman IC by month, the same way the single-seed script measures it.
def information_coefficient(preds: pd.DataFrame) -> tuple[float, float, int]:
    scored = preds.dropna(subset=["actual"])
    ic = (
        scored.groupby("holding_month")
        .apply(lambda g: g["pred"].corr(g["actual"], method="spearman"), include_groups=False)
        .dropna()
    )
    return float(ic.mean()), float(ic.mean() / ic.std() * np.sqrt(len(ic))), int(len(ic))


# Fits every fold on one seed, then puts the predictions through the shipped optimizer so the
# seed is judged on a portfolio, not on a correlation.
def one_seed(df: pd.DataFrame, cols: list[str], panel: pd.DataFrame, seed: int) -> dict:
    frames = [N.fit_fold(fold, cols, seed=seed) for fold in D.folds(df)]
    # Early stopping picks its own epoch per fold, and that choice is part of what the seed
    # changes, so it is recorded rather than averaged away.
    epochs = [int(f.attrs.get("best_epoch", 0)) for f in frames]
    preds = pd.concat(frames, ignore_index=True)
    D.assert_holding_months(preds)
    preds.to_parquet(PREDS / f"nn3_seed{seed}.parquet", index=False)

    ic_mean, ic_t, months = information_coefficient(preds)
    book = R.backtest(R.neutralize(panel, preds))
    return dict(
        seed=seed,
        best_epoch_per_fold=epochs,
        ic_mean=ic_mean,
        ic_t=ic_t,
        ic_months=months,
        information_ratio=R.information_ratio(book),
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(book["net"].mean() * 12),
        turnover=float(book["turnover"].mean()),
        positions=float(book["n"].mean()),
        months=int(len(book)),
    )


# Every seed, then the spread across them. No averaging into an ensemble: that would be a
# different model and would need its own predeclaration and its own optimizer run.
def main() -> None:
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
    df = D.load_folds()
    cols = D.predictors()
    panel = R.P.load_panel()
    PREDS.mkdir(parents=True, exist_ok=True)

    rows = []
    for seed in SEEDS:
        row = one_seed(df, cols, panel, seed)
        rows.append(row)
        print(
            f"  seed {seed}: IC {row['ic_mean']:+.4f} (t {row['ic_t']:.2f})  "
            f"IR {row['information_ratio']:+.2f}  net {row['net_annual'] * 100:+.1f}%/yr"
        )

    table = pd.DataFrame(rows)
    spread = {
        field: dict(
            mean=float(table[field].mean()),
            median=float(table[field].median()),
            min=float(table[field].min()),
            max=float(table[field].max()),
            # The range matters more than the mean here: it is the number that says whether
            # a single-seed result was worth quoting in the first place.
            range=float(table[field].max() - table[field].min()),
        )
        for field in ["ic_mean", "ic_t", "information_ratio", "gross_annual", "net_annual"]
    }

    out = dict(
        what="NN3 refitted on a fixed consecutive five-seed sweep, everything else held fixed.",
        rule="Reported in full, every seed, whatever it says. Seed 42 was already known when "
        "43-46 were chosen, so this is a robustness sweep, not a predeclaration. Never "
        "averaged into a production model: an ensemble is a different model.",
        seeds=list(SEEDS),
        environment=dict(
            python=platform.python_version(),
            torch=torch.__version__,
            numpy=np.__version__,
            device="cpu",
            threads=int(torch.get_num_threads()),
        ),
        code=R.P.source_fingerprint(),
        per_seed=rows,
        spread=spread,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "nn3_seeds.json").write_text(json.dumps(out, indent=2))

    ir = spread["information_ratio"]
    print(
        f"\nIR across {len(SEEDS)} seeds: mean {ir['mean']:+.2f}, "
        f"range {ir['min']:+.2f} to {ir['max']:+.2f} (spread {ir['range']:.2f})"
    )


if __name__ == "__main__":
    main()
