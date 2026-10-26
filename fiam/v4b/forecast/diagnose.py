# Fold-1 diagnostics in return terms: spreads and per-day alpha by age.

import json

import numpy as np
import pandas as pd

from fiam.v4b.forecast import evaluate, run

COLS = ("blend", "nonlinear", "ridge")


# Top-minus-bottom mean label per month for a score and tail share.
def spread(v: pd.DataFrame, col: str, q: float) -> pd.Series:
    def one(g):
        r = g[col].rank(pct=True)
        return g[run.LABEL][r > 1 - q].mean() - g[run.LABEL][r <= q].mean()

    return v.groupby("eom").apply(one, include_groups=False)


# Writes diagnostics.json beside the fold-1 report.
def main() -> dict:
    _, _, p = run.build()
    v = pd.read_parquet(run.OUT / "predictions_valid.parquet")
    ys = [f"y{h}" for h in run.HORIZONS if h != 21]
    f = v.merge(p[["eom", "permno", *ys]], on=["eom", "permno"])
    out = {
        "paired_ic_mlp_minus_blend": evaluate.paired(
            evaluate.monthly_ic(v["eom"], v["nonlinear"], v[run.LABEL]),
            evaluate.monthly_ic(v["eom"], v["blend"], v[run.LABEL]),
        )
    }
    for col in COLS:
        tails = {}
        for q in (0.1, 0.2):
            s = spread(v, col, q)
            tails[f"top_minus_bottom_{int(q * 100)}"] = {
                "all": evaluate.mean_t(s),
                "by_year": {str(y): float(x.mean()) for y, x in s.groupby(s.index.year)},
            }
        slopes = evaluate.decay_slopes(f, col, run.BUCKETS)
        tails["per_day_slope_by_age"] = {
            c: {
                "mean": float(slopes[c].mean()),
                "se": float(slopes[c].std() / np.sqrt(slopes[c].count())),
            }
            for c in slopes.columns
        }
        out[col] = tails
    (run.OUT / "diagnostics.json").write_text(json.dumps(out, indent=2, default=run._plain) + "\n")
    return out


if __name__ == "__main__":
    main()
