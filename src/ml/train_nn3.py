# Gu-Kelly-Xiu style NN3 on the prescribed folds. CPU only, fixed seed.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).parent))
import dataset as D

OUT = Path("cache/preds")

# Fixed so a judge rerunning this gets our numbers, not numbers near ours.
SEED = 42

# Three narrowing layers, the depth Gu-Kelly-Xiu found best. Deeper measured no better.
HIDDEN = (32, 16, 8)

# Stop as soon as the validation loss stalls. Left alone the net fits the training window.
EPOCHS, BATCH, PATIENCE = 60, 8192, 5

# Weight decay and dropout both fight the same thing: 147 noisy inputs and a faint signal.
LR, WEIGHT_DECAY, DROPOUT = 1e-3, 1e-4, 0.2


# Same architecture every fold. Batch-norm and dropout because 147 noisy inputs overfit fast.
def build(n_features: int) -> nn.Module:
    layers, prev = [], n_features
    for width in HIDDEN:
        layers += [nn.Linear(prev, width), nn.BatchNorm1d(width), nn.ReLU(), nn.Dropout(DROPOUT)]
        prev = width
    layers.append(nn.Linear(prev, 1))
    return nn.Sequential(*layers)


# Trains one fold with early stopping. The seed is an argument so the sweep can vary it.
def fit_fold(fold: dict, cols: list[str], seed: int = SEED) -> pd.DataFrame:
    torch.manual_seed(seed)
    np.random.seed(seed)

    train, validate = D.labelled(fold["train"]), D.labelled(fold["validate"])
    x_train = torch.tensor(train[cols].to_numpy(), dtype=torch.float32)
    y_train = torch.tensor(D.rank_target(train), dtype=torch.float32).unsqueeze(1)
    x_val = torch.tensor(validate[cols].to_numpy(), dtype=torch.float32)
    y_val = torch.tensor(D.rank_target(validate), dtype=torch.float32).unsqueeze(1)

    model = build(len(cols))
    opt = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    loss_fn = nn.MSELoss()

    # Keep the weights from the best validation epoch, not the last one.
    best_state, best_loss, stale, best_epoch = None, np.inf, 0, 0
    for epoch in range(EPOCHS):
        model.train()
        perm = torch.randperm(len(x_train))
        for i in range(0, len(perm), BATCH):
            idx = perm[i : i + BATCH]
            opt.zero_grad()
            loss_fn(model(x_train[idx]), y_train[idx]).backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(x_val), y_val))
        if val_loss < best_loss - 1e-6:
            best_state, best_loss, stale, best_epoch = (
                {k: v.clone() for k, v in model.state_dict().items()},
                val_loss,
                0,
                epoch + 1,
            )
        else:
            stale += 1
            if stale >= PATIENCE:
                break

    # Back to the best epoch before scoring, and out of training mode so dropout is off.
    model.load_state_dict(best_state)
    model.eval()
    test = fold["test"]
    with torch.no_grad():
        pred = model(torch.tensor(test[cols].to_numpy(), dtype=torch.float32)).squeeze(1).numpy()
    out = pd.DataFrame(
        dict(
            permno=test["permno"].to_numpy(),
            eom=test["eom"].to_numpy(),
            holding_month=test["holding_month"].to_numpy(),
            pred=pred,
            actual=test[D.TARGET].to_numpy(),
        )
    )
    out.attrs["best_epoch"] = best_epoch
    return out


# Trains every fold and reports the information coefficient over the whole test window.
def main() -> None:
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
    df = D.load_folds()
    cols = D.predictors()
    preds = pd.concat([fit_fold(f, cols) for f in D.folds(df)], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    D.assert_holding_months(preds)
    preds.to_parquet(OUT / "nn3.parquet", index=False)

    scored = preds.dropna(subset=["actual"])
    ic = (
        scored.groupby("holding_month")
        .apply(lambda g: g["pred"].corr(g["actual"], method="spearman"), include_groups=False)
        .dropna()
    )
    stats = dict(
        ic_mean=float(ic.mean()),
        ic_t=float(ic.mean() / ic.std() * np.sqrt(len(ic))),
        months=int(len(ic)),
    )
    (OUT / "nn3_ic.json").write_text(json.dumps(stats, indent=2))
    print(f"nn3: IC {stats['ic_mean']:.4f}  t = {stats['ic_t']:.2f}  over {stats['months']} months")


if __name__ == "__main__":
    main()
