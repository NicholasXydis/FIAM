# Tests whether slowing a model's score saves it from its own trading bill.
#
# They predict as well as we do but rebuild the book monthly. signal_decay says why not.

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import run_through_optimizer as R

import pipeline as P

PREDS = Path("cache/preds")
OUT = Path("submission/exhibits")

MODELS = ("lgbm", "nn3", "enet")

# How much of last month's score to keep. Swept, and every setting reported.
BLENDS = (0.0, 0.3, 0.5, 0.7, 0.9)


# Carries each name's own last score forward on the calendar, never by row position.
def persist(scored: pd.DataFrame, weight: float) -> pd.Series:
    if weight == 0.0:
        return scored["signal"]
    frame = scored[["permno", "eom", "signal"]].copy()
    frame["prev_eom"] = frame["eom"] - pd.offsets.MonthEnd(1)
    previous = frame[["permno", "eom", "signal"]].rename(
        columns={"eom": "prev_eom", "signal": "prior"}
    )
    merged = frame.merge(previous, on=["permno", "prev_eom"], how="left")
    # No prior score keeps this month's. Dropping it would flatter the turnover.
    blended = (1 - weight) * merged["signal"] + weight * merged["prior"].fillna(merged["signal"])
    return pd.Series(blended.to_numpy(), index=scored.index)


# Scores one model at one blend weight through the shipped optimizer and cost model.
def run_blend(panel: pd.DataFrame, preds: pd.DataFrame, weight: float) -> dict:
    scored = R.neutralize(panel, preds)
    scored = scored.assign(signal=persist(scored, weight))
    book = R.backtest(scored)
    gross = float(book["gross"].mean() * 12)
    net = float(book["net"].mean() * 12)
    return dict(
        blend=weight,
        information_ratio=R.information_ratio(book),
        gross_annual=gross,
        net_annual=net,
        cost_annual=gross - net,
        turnover=float(book["turnover"].mean()),
        positions=float(book["n"].mean()),
        months=int(len(book)),
    )


def main() -> None:
    panel = P.load_panel()
    result = dict(
        what="Does damping a model's month-to-month churn rescue it? Each model is run through "
        "the shipped optimizer and cost model with its score blended toward last month's.",
        rule="Reported in full, every blend weight. A winner here does not replace the "
        "composite unless it beats the composite's realized net IR of 0.85, which is the same "
        "bar every other candidate faced.",
        blends=list(BLENDS),
        composite_net_ir=0.846125,
        code=P.source_fingerprint(),
        models={},
    )
    for model in MODELS:
        preds = pd.read_parquet(PREDS / f"{model}.parquet")
        preds["eom"] = pd.to_datetime(preds["eom"])
        rows = [run_blend(panel, preds, w) for w in BLENDS]
        result["models"][model] = rows
        print(f"[{model}]")
        for row in rows:
            print(
                f"  blend {row['blend']:.1f}: turnover {row['turnover'] * 100:5.0f}%  "
                f"gross {row['gross_annual'] * 100:+5.1f}%  net {row['net_annual'] * 100:+5.1f}%  "
                f"IR {row['information_ratio']:+.2f}"
            )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_aware.json").write_text(json.dumps(result, indent=2))

    best = max(
        (row for rows in result["models"].values() for row in rows),
        key=lambda r: r["information_ratio"],
    )
    print(f"\nbest of the sweep: IR {best['information_ratio']:+.2f} at blend {best['blend']:.1f}")
    print(f"composite still {result['composite_net_ir']:+.2f}")


if __name__ == "__main__":
    main()
