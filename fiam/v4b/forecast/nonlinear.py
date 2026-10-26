# The blend's nonlinear member: 2-layer MLP or depth-3 GBT, fixed defaults.
# Baseline only: the forecaster is E-LASSO (DECISIONS.md D6, v4b/elasso/).

import warnings

import numpy as np

# Seeds fixed before any fit; the MLP is their average.
SEEDS = (42, 43, 44, 45, 46)
MLP = dict(
    hidden_layer_sizes=(64, 32),
    alpha=1e-3,
    batch_size=4096,
    learning_rate_init=1e-3,
    max_iter=25,
    n_iter_no_change=25,
    tol=0.0,
    early_stopping=False,
    shuffle=True,
)
GBT = dict(
    max_depth=3,
    num_leaves=8,
    n_estimators=300,
    learning_rate=0.05,
    min_child_samples=1000,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=10.0,
    deterministic=True,
    force_row_wise=True,
    n_jobs=4,
    verbose=-1,
)


# A fitted member: predict(x) returns one score per row.
class Member:
    def __init__(self, kind: str, models: list):
        self.kind, self.models = kind, models

    # The average score over the member's fitted models.
    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.mean([m.predict(x) for m in self.models], axis=0)


# Fits the MLP (seed average) on month-weighted rows.
def fit_mlp(x, y, w) -> Member:
    from sklearn.neural_network import MLPRegressor

    weight = w * len(w) / w.sum()
    models = []
    for seed in SEEDS:
        m = MLPRegressor(random_state=seed, **MLP)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m.fit(x, y, sample_weight=weight)
        models.append(m)
    return Member("mlp", models)


# Fits the depth-3 GBT on month-weighted rows.
def fit_gbt(x, y, w) -> Member:
    import lightgbm as lgb

    m = lgb.LGBMRegressor(random_state=42, **GBT)
    m.fit(x, y, sample_weight=w * len(w) / w.sum())
    return Member("gbt", [m])
