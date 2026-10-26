# Alpha decay of the E-LASSO forecasts: per-day return per unit z by age.

import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso import judge
from fiam.v4b.forecast import evaluate, initial_plan, run

COLS = ("Elasso_Ma1", "Elasso_MaInf", "Classo_forecast")


# Writes decay.json beside the E-LASSO report.
def main() -> dict:
    u, *_ = initial_plan.prepare()
    fc = judge.forecasts()
    fc = fc[fc["eom"].between(pd.Timestamp(judge.WINDOW[0]), pd.Timestamp(judge.WINDOW[1]))]
    ys = [f"y{h}" for h in run.HORIZONS]
    f = fc.merge(u[["eom", "permno", *ys]], on=["eom", "permno"], how="inner")
    out = {}
    for col in COLS:
        s = evaluate.decay_slopes(f, col, run.BUCKETS)
        out[col] = {
            c: {
                "bp_per_day": float(s[c].mean() * 1e4),
                "se_bp": float(s[c].std() / np.sqrt(s[c].count()) * 1e4),
                "months": int(s[c].count()),
            }
            for c in s.columns
        }
    (judge.OUT / "decay.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    for col, rows in main().items():
        print(col)
        for b, v in rows.items():
            print(f"  days {b:>6}: {v['bp_per_day']:+6.2f} bp/day ± {v['se_bp']:.2f}")
