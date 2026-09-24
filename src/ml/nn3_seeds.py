# Refits NN3 on five seeds to show how much of its result is just the seed.

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
import train as T

import pipeline as P

OUT = Path("submission/exhibits")
PREDS = Path("cache/preds")

# 42 is the shipped seed, 43-46 added later. Consecutive, not picked. All five reported.
SEEDS = (42, 43, 44, 45, 46)


# Fits every fold on one seed, then scores it through the book, not on a correlation.
def one_seed(df: pd.DataFrame, cols: list[str], seed: int) -> dict:
    preds = T.fit_all(T.fit_nn3, df, cols, seed=seed)
    # The shipped seed is already cached as nn3.parquet, byte for byte.
    if seed != T.SEED:
        preds.to_parquet(PREDS / f"nn3_seed{seed}.parquet", index=False)
    ic = P.information_coefficient(preds)
    return dict(
        seed=seed,
        # Early stopping picks its own epoch per fold, so record it rather than average it.
        best_epoch_per_fold=preds.attrs["best_epoch"],
        ic_mean=ic["ic_mean"],
        ic_t=ic["ic_t"],
        ic_months=ic["months"],
        **P.book_stats(T.score_book(preds)),
    )


# Every seed and the spread. Never averaged, an ensemble is a different model.
def main() -> None:
    df = D.load_folds()
    cols = P.characteristics()
    PREDS.mkdir(parents=True, exist_ok=True)

    rows = []
    for seed in SEEDS:
        row = one_seed(df, cols, seed)
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
            # The range matters more than the mean. It says if one seed was worth quoting.
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
        code=P.source_fingerprint(),
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
