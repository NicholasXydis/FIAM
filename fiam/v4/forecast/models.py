# The three return models and the SUE model (PLAN §8.2, checklist).

import lightgbm as lgb
import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import ElasticNet

from fiam.v4.signals import syy

# LightGBM as PLAN §8.2 fixes it: lr 0.05, 200 trees, seed 42.
LGB_BASE = {
    "objective": "regression", "learning_rate": 0.05, "num_iterations": 200,
    "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0, "seed": 42,
    "deterministic": True, "force_row_wise": True, "num_threads": 4, "verbosity": -1,
}  # fmt: skip
LEAVES, CHILDREN = (7, 15, 31), (500, 2000)
# ElasticNet alpha x l1_ratio, and the net's L1 penalties (checklist).
ENET = [(a, r) for a in (0.0001, 0.001, 0.01) for r in (0.1, 0.5, 0.9)]
NN_L1 = (0.00001, 0.0001, 0.001)
# The net's five seeds, averaged; written here before any fit.
NN_SEEDS = range(20261700, 20261705)
NN_EPOCHS, NN_BATCH, NN_LR = 30, 10_000, 0.001
# A last partial batch under this many rows is skipped (batch norm).
NN_MIN_BATCH = 1_000
# One torch thread: its OpenMP and LightGBM's deadlock at more (macOS).
torch.set_num_threads(1)
# SYY parts that keep their published sign; these three are free.
FREE = {"gp_at", "at_gr1", "ret_12_1"}


# +1 on SYY-10 and the SUE forecast, each SYY part's sign, else free.
def monotone(cols: list[str]) -> list[int]:
    signs = {p: s for p, s in syy.PARTS.items() if p not in FREE}
    return [1 if c in ("syy", "sue_forecast") else signs.get(c, 0) for c in cols]


# One LightGBM fit with the grid cell's leaves and minimum leaf size.
def lgbm(x: pd.DataFrame, y: np.ndarray, leaves: int, children: int, mono: bool = True):
    params = LGB_BASE | {"num_leaves": leaves, "min_child_samples": children}
    if mono:
        params["monotone_constraints"] = monotone(list(x.columns))
    return lgb.train(params, lgb.Dataset(x.to_numpy(np.float32), y, free_raw_data=True))


# One ElasticNet fit on the ranked inputs.
def enet(x: pd.DataFrame, y: np.ndarray, alpha: float, l1_ratio: float) -> ElasticNet:
    model = ElasticNet(alpha=alpha, l1_ratio=l1_ratio, max_iter=5000, tol=1e-5, precompute=True)
    return model.fit(x.to_numpy(np.float32), y)


# Gu-Kelly-Xiu NN3: 32-16-8 ReLU with batch norm, L1 on the weights.
class Net(torch.nn.Module):
    # The three hidden layers and the output.
    def __init__(self, inputs: int):
        super().__init__()
        layers, width = [], inputs
        for out in (32, 16, 8):
            layers += [torch.nn.Linear(width, out), torch.nn.BatchNorm1d(out), torch.nn.ReLU()]
            width = out
        self.body = torch.nn.Sequential(*layers, torch.nn.Linear(width, 1))

    # The forecast for a batch.
    def forward(self, x):
        return self.body(x).squeeze(-1)


# One net per seed, trained 30 epochs; the forecast averages the seeds.
def nn3(x: pd.DataFrame, y: np.ndarray, l1: float) -> list:
    xs = torch.tensor(x.to_numpy(np.float32))
    ys = torch.tensor(np.asarray(y, np.float32))
    nets = []
    for seed in NN_SEEDS:
        torch.manual_seed(seed)
        gen = torch.Generator().manual_seed(seed)
        net = Net(xs.shape[1])
        opt = torch.optim.Adam(net.parameters(), lr=NN_LR)
        # L1 on the layers' weight matrices, never on biases or batch norm.
        weights = [p for n, p in net.named_parameters() if n.endswith("weight") and p.dim() > 1]
        for _ in range(NN_EPOCHS):
            order = torch.randperm(len(xs), generator=gen)
            for start in range(0, len(xs), NN_BATCH):
                idx = order[start : start + NN_BATCH]
                if len(idx) < 2 or (start > 0 and len(idx) < NN_MIN_BATCH):
                    continue
                opt.zero_grad()
                loss = torch.mean((net(xs[idx]) - ys[idx]) ** 2)
                loss = loss + l1 * sum(w.abs().sum() for w in weights)
                loss.backward()
                opt.step()
        net.eval()
        nets.append(net)
    return nets


# A fitted model's forecast, whatever its kind.
def predict(model, x: pd.DataFrame) -> np.ndarray:
    values = x.to_numpy(np.float32)
    if isinstance(model, list):
        with torch.no_grad():
            return np.mean([net(torch.tensor(values)).numpy() for net in model], axis=0)
    return np.asarray(model.predict(values), dtype=float)
