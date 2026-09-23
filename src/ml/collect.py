# Gathers every ML result into one file, so no write-up has to quote a terminal.
# Reads cache/preds/ and submission/exhibits/, writes submission/exhibits/ml_metrics.json.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

PREDS = Path("cache/preds")
EXHIBITS = Path("submission/exhibits")

# The three comparison families. The composite is handled separately because it is not a
# fitted model and has no prediction file.
MODELS = ["enet", "lgbm", "nn3"]


# The composite's own IC, measured the same way the models' is, so the comparison is fair.
def composite_ic() -> dict:
    df = P.build_signal(P.screen(P.load_panel()))
    scored = df.dropna(subset=["ret_exc_lead1m"])
    ic = (
        scored.groupby("eom")
        .apply(
            lambda g: g["signal"].corr(g["ret_exc_lead1m"], method="spearman"),
            include_groups=False,
        )
        .dropna()
    )
    return dict(
        ic_mean=float(ic.mean()),
        ic_t=float(ic.mean() / ic.std() * np.sqrt(len(ic))),
        months=int(len(ic)),
    )


# Pulls every per-model file into one artifact the write-up can read from.
def main() -> None:
    out = {
        "_about": {
            "what": "One run of the src/ml scripts. Every ML number in the write-up is from here.",
            "regenerate": "python run.py --ml",
            "note": "IR is after sector, beta and vol neutralization, the optimizer and costs.",
        }
    }

    # The composite's IR comes from the book itself, in submission/metrics.json, so it is
    # left blank here rather than duplicated and allowed to drift.
    out["composite"] = composite_ic() | {"information_ratio": None}
    for name in MODELS:
        entry = {}
        ic_file = PREDS / f"{name}_ic.json"
        if ic_file.exists():
            entry |= json.loads(ic_file.read_text())
        # A model that has been fitted but not yet scored into a book has no portfolio file.
        port = PREDS / f"{name}_portfolio.json"
        if port.exists():
            entry |= json.loads(port.read_text())
        out[name] = entry

    deciles = EXHIBITS / "decile_tables.csv"
    if deciles.exists():
        table = pd.read_csv(deciles, index_col=0)
        out["deciles"] = {i: {c: float(v) for c, v in row.items()} for i, row in table.iterrows()}

    sweep = EXHIBITS / "subset_sweep.csv"
    if sweep.exists():
        s = pd.read_csv(sweep)
        # What a team would have held if they had picked the best-looking subset early on.
        best = s.loc[s["ir_early"].idxmax()]
        out["subset_sweep"] = dict(
            n_subsets=int(len(s)),
            ir_full_min=float(s["ir_full"].min()),
            ir_full_max=float(s["ir_full"].max()),
            early_late_correlation=float(s["ir_early"].corr(s["ir_late"])),
            best_on_early_then_earned=float(best["ir_late"]),
            median_late_ir=float(s["ir_late"].median()),
        )

    EXHIBITS.mkdir(parents=True, exist_ok=True)
    (EXHIBITS / "ml_metrics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "_about"}, indent=2)[:1200])


if __name__ == "__main__":
    main()
