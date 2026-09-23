# ElasticNet baseline, so our OOS R-squared is comparable to the competition's template.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet

sys.path.insert(0, str(Path(__file__).parent))
import dataset as D

OUT = Path("cache/preds")

# A coarser lambda grid than the template. The rank target is already well scaled.
ALPHAS = [10.0**i for i in range(-6, 1)]
L1_RATIO = 0.5


# Picks lambda on the validation fold, never on the test fold.
def fit_fold(fold: dict, cols: list[str]) -> pd.DataFrame:
    train, validate = D.labelled(fold["train"]), D.labelled(fold["validate"])
    x_train, y_train = train[cols].to_numpy(), D.rank_target(train)
    x_val, y_val = validate[cols].to_numpy(), D.rank_target(validate)

    # Lowest validation error wins. The test fold is never consulted.
    best, best_mse = None, np.inf
    for alpha in ALPHAS:
        model = ElasticNet(alpha=alpha, l1_ratio=L1_RATIO, max_iter=5000, random_state=42)
        model.fit(x_train, y_train)
        mse = float(np.mean((model.predict(x_val) - y_val) ** 2))
        if mse < best_mse:
            best, best_mse = model, mse

    test = fold["test"]
    return pd.DataFrame(
        dict(
            permno=test["permno"].to_numpy(),
            eom=test["eom"].to_numpy(),
            holding_month=test["holding_month"].to_numpy(),
            pred=best.predict(test[cols].to_numpy()),
            actual=test[D.TARGET].to_numpy(),
        )
    )


# Zero-benchmark R-squared, the GKX form the rules ask for. Not the usual demeaned version.
def oos_r2(preds: pd.DataFrame) -> float:
    s = preds.dropna(subset=["actual"])
    return float(1 - np.sum((s["actual"] - s["pred"]) ** 2) / np.sum(s["actual"] ** 2))


# Trains every fold and reports IC plus the zero-benchmark R-squared the rules ask for.
def main() -> None:
    df = D.load_folds()
    cols = D.predictors()
    preds = pd.concat([fit_fold(f, cols) for f in D.folds(df)], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    D.assert_holding_months(preds)
    preds.to_parquet(OUT / "enet.parquet", index=False)

    scored = preds.dropna(subset=["actual"])
    ic = (
        scored.groupby("holding_month")
        .apply(lambda g: g["pred"].corr(g["actual"], method="spearman"), include_groups=False)
        .dropna()
    )
    # Some months the penalty zeroes everything, so report both counts, not the smaller.
    scored_months = int(preds["holding_month"].nunique())
    stats = dict(
        ic_mean=float(ic.mean()),
        ic_t=float(ic.mean() / ic.std() * np.sqrt(len(ic))),
        oos_r2=oos_r2(preds),
        months=scored_months,
        months_with_a_defined_ic=int(len(ic)),
        months_with_no_view=scored_months - int(len(ic)),
    )
    (OUT / "enet_ic.json").write_text(json.dumps(stats, indent=2))
    print(
        f"enet: IC {stats['ic_mean']:.4f}  t = {stats['ic_t']:.2f}  "
        f"OOS R2 {stats['oos_r2']:.4f}  "
        f"no view in {stats['months_with_no_view']} of {stats['months']} months"
    )


if __name__ == "__main__":
    main()
