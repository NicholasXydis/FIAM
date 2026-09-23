# How fast each model's score goes stale, which is what forces it to trade.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

PREDS = Path("cache/preds")
OUT = Path("submission/exhibits")

MODELS = ("composite", "lgbm", "nn3", "enet")

# How old we let the score get. One that dies in a month must be redone monthly.
LAGS = (0, 1, 2, 3, 6)


# Score against its own return, then against later ones. The fall-off is the answer.
def decay_curve(scored: pd.DataFrame) -> dict:
    out = {}
    wide = scored.pivot_table(index="eom", columns="permno", values="score")
    rets = scored.pivot_table(index="eom", columns="permno", values="ret")
    for lag in LAGS:
        # Slide the returns back so this month's score meets a later month's return.
        shifted = rets.shift(-lag)
        ics = []
        for month in wide.index:
            a, b = wide.loc[month], shifted.loc[month]
            pair = pd.concat([a, b], axis=1).dropna()
            if len(pair) > 50:
                ics.append(pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman"))
        ics = pd.Series(ics).dropna()
        out[f"lag_{lag}"] = dict(
            ic_mean=float(ics.mean()),
            ic_t=float(ics.mean() / ics.std() * np.sqrt(len(ics))) if ics.std() else 0.0,
            months=int(len(ics)),
        )
    # The half-life a reader actually wants: what fraction of the fresh IC survives one month.
    fresh = out["lag_0"]["ic_mean"]
    out["one_month_retention"] = float(out["lag_1"]["ic_mean"] / fresh) if fresh else 0.0
    return out


# Score and return on one frame, on the shipped universe, so models are comparable.
def scored_frame(panel: pd.DataFrame, model: str) -> pd.DataFrame:
    base = P.build_signal(P.screen(panel))
    if model == "composite":
        return base.rename(columns={"signal": "score", "ret_exc_lead1m": "ret"})[
            ["permno", "eom", "score", "ret"]
        ]
    preds = pd.read_parquet(PREDS / f"{model}.parquet")
    preds["eom"] = pd.to_datetime(preds["eom"])
    merged = base.merge(preds[["permno", "eom", "pred"]], on=["permno", "eom"], how="inner")
    return merged.rename(columns={"pred": "score", "ret_exc_lead1m": "ret"})[
        ["permno", "eom", "score", "ret"]
    ]


def main() -> None:
    panel = P.load_panel()
    result = dict(
        what="How much of each model's predictive power survives being a month old. A score "
        "that decays fast has to be refreshed every month, and that refresh is the turnover "
        "the cost model charges for.",
        lags_in_months=list(LAGS),
        code=P.source_fingerprint(),
        models={},
    )
    for model in MODELS:
        curve = decay_curve(scored_frame(panel, model))
        result["models"][model] = curve
        print(
            f"{model:<10} fresh IC {curve['lag_0']['ic_mean']:+.4f}  "
            f"after 1m {curve['lag_1']['ic_mean']:+.4f}  "
            f"retained {curve['one_month_retention']:.0%}"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signal_decay.json").write_text(json.dumps(result, indent=2))
    print("\nwrote signal_decay.json")


if __name__ == "__main__":
    main()
