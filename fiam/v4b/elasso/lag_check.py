# H2 vintage check: E-LASSO with characteristics one month staler (R§6, R§11).
#
# The lag input (build_input --lag1) is run through the authors' unchanged R
# code into out/elasso/run_lag1/. This judges MaInf/Ma1 from that run on the
# same held-out window and harness as judge.py and reports the paired cost
# of the extra month. Diagnostic only: the shipped forecaster is unlagged
# unless the deck's conservative case is adopted before the freeze.

import json
from pathlib import Path

import pandas as pd

from fiam.v4b.elasso import judge
from fiam.v4b.forecast import evaluate, initial_plan, run

BASE = Path(__file__).resolve().parents[1] / "out" / "elasso"
LAG_RUN = BASE / "run_lag1"
COLS = ("Elasso_MaInf", "Elasso_Ma1")


# Writes lag1.json: lagged ICs and paired (lagged - base) differences.
def main() -> dict:
    u, *_, factors, _ = initial_plan.prepare()
    key = u[["eom", "permno"]].reset_index().rename(columns={"index": "row"})

    def load(run_dir):
        fc = judge.forecasts(run_dir).merge(key, on=["eom", "permno"], how="inner")
        return fc[fc["eom"].between(pd.Timestamp(judge.WINDOW[0]), pd.Timestamp(judge.WINDOW[1]))]

    def series(fc, c):
        s = pd.Series(fc[c].to_numpy(), index=fc["row"].to_numpy()).dropna()
        f = u.loc[s.index]
        return (
            evaluate.monthly_ic(f["eom"], s.to_numpy(), f[run.LABEL]),
            initial_plan.spread(f["eom"], s.to_numpy(), f[run.LABEL]),
            s,
        )

    base, lag = load(judge.RUN), load(LAG_RUN)
    out = {}
    for c in COLS:
        bic, bsp, _ = series(base, c)
        lic, lsp, ls = series(lag, c)
        out[c] = {
            "lagged": initial_plan.judge(u, factors, ls),
            "paired_lagged_minus_base": {
                "ic": evaluate.paired(lic, bic),
                "spread10": evaluate.paired(lsp, bsp),
            },
        }
    (BASE / "lag1.json").write_text(json.dumps(out, indent=2, default=run._plain) + "\n")
    return out


if __name__ == "__main__":
    r = main()
    for c in COLS:
        p = r[c]["paired_lagged_minus_base"]
        ic = r[c]["lagged"]["ic"]["all"]
        print(f"{c}: lagged IC {ic['mean']:.4f} (t {ic['t']:.2f})")
        print(
            f"  paired dIC {p['ic']['mean']:+.4f} ± {p['ic']['se']:.4f} "
            f"[{p['ic']['lo90']:+.4f}, {p['ic']['hi90']:+.4f}]"
        )
        sp = p["spread10"]
        print(f"  paired dSpread {sp['mean'] * 100:+.2f}% ± {sp['se'] * 100:.2f}%")
