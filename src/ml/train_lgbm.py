# Trains the LightGBM comparison model on the prescribed folds and scores each test year.
# Reads cache/folds/, writes cache/preds/lgbm.parquet and cache/preds/lgbm_ic.json.

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import dataset as D

OUT = Path("cache/preds")

# Heavy regularization on purpose. With 147 noisy predictors and a rank target, an
# unconstrained tree memorizes the training window and scores nothing out of sample.
PARAMS = dict(
    objective="regression",
    metric="l2",
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=500,
    reg_lambda=20.0,
    feature_fraction=0.7,
    bagging_fraction=0.7,
    bagging_freq=1,
    verbosity=-1,
    seed=42,
    deterministic=True,
    force_row_wise=True,
)
# Plenty of rounds, and early stopping decides how many we actually use.
ROUNDS, EARLY = 2000, 50


# Fits one fold and returns that year's test-set predictions.
def fit_fold(fold: dict, cols: list[str]) -> pd.DataFrame:
    train, validate = D.labelled(fold["train"]), D.labelled(fold["validate"])
    ds_train = lgb.Dataset(train[cols].to_numpy(), label=D.rank_target(train))
    ds_val = lgb.Dataset(validate[cols].to_numpy(), label=D.rank_target(validate))
    model = lgb.train(
        PARAMS,
        ds_train,
        num_boost_round=ROUNDS,
        valid_sets=[ds_val],
        callbacks=[lgb.early_stopping(EARLY, verbose=False)],
    )
    # Score the whole test cross-section, including names with no target. Filtering here
    # would drop the companies that failed, which is the survivorship trap.
    test = fold["test"]
    return pd.DataFrame(
        dict(
            permno=test["permno"].to_numpy(),
            eom=test["eom"].to_numpy(),
            holding_month=test["holding_month"].to_numpy(),
            pred=model.predict(test[cols].to_numpy(), num_iteration=model.best_iteration),
            actual=test[D.TARGET].to_numpy(),
        )
    )


# Monthly rank IC and its t-statistic, the standard way this is reported.
def information_coefficient(preds: pd.DataFrame) -> dict:
    scored = preds.dropna(subset=["actual"])
    ic = (
        scored.groupby("holding_month")
        .apply(lambda g: g["pred"].corr(g["actual"], method="spearman"), include_groups=False)
        .dropna()
    )
    t = ic.mean() / ic.std() * np.sqrt(len(ic))
    return dict(ic_mean=float(ic.mean()), ic_t=float(t), months=int(len(ic)))


# Trains every fold and reports the information coefficient over the whole test window.
def main() -> None:
    df = D.load_folds()
    cols = D.predictors()
    preds = pd.concat([fit_fold(f, cols) for f in D.folds(df)], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    D.assert_holding_months(preds)
    preds.to_parquet(OUT / "lgbm.parquet", index=False)
    stats = information_coefficient(preds)
    (OUT / "lgbm_ic.json").write_text(json.dumps(stats, indent=2))
    print(
        f"lgbm: IC {stats['ic_mean']:.4f}  t = {stats['ic_t']:.2f}  "
        f"over {stats['months']} months, {len(preds):,} predictions"
    )


if __name__ == "__main__":
    main()
