# Decile tables for every model and every ML number, in one file, ml_metrics.json.

from __future__ import annotations

import json

import pandas as pd

from fiam import book as P
from fiam import paths

PREDS = P.CACHE / "preds"
EXHIBITS = paths.EXHIBITS

# Named, not globbed, so a stray file in the cache can never become a row in the exhibit.
MODELS = ("enet", "lgbm", "nn3")


# Next-month excess return by decile of the score, annualized. How a signal earns its place.
def deciles(frame: pd.DataFrame, score: str, n: int = 10) -> pd.Series:
    scored = frame.dropna(subset=[score, "actual"]).copy()
    # Rank inside each month, so a decile means the same thing in every cross-section.
    scored["bucket"] = scored.groupby("holding_month")[score].transform(
        lambda s: pd.qcut(s.rank(method="first"), n, labels=False, duplicates="drop")
    )
    monthly = scored.groupby(["holding_month", "bucket"])["actual"].mean()
    return monthly.groupby("bucket").mean() * 12


# Decile tables and each model's numbers, written to ml_metrics.json.
def main() -> None:
    universe = P.universe()
    composite = universe.assign(
        holding_month=(universe["eom"] + pd.offsets.MonthBegin(1)).dt.normalize(),
        actual=universe["ret_exc_lead1m"],
    )
    rows = {"composite": deciles(composite.rename(columns={"signal": "score"}), "score")}
    for model in MODELS:
        rows[model] = deciles(pd.read_parquet(PREDS / f"{model}.parquet"), "pred")
    table = pd.DataFrame(rows).T
    table.columns = [f"d{int(c) + 1}" for c in table.columns]
    table["top_minus_bottom"] = table.iloc[:, -1] - table.iloc[:, 0]
    # A long-short book needs rising tails. The middle never enters it.
    table["top_beats_second"] = table["d10"] > table["d9"]
    EXHIBITS.mkdir(parents=True, exist_ok=True)
    print((table * 100).round(1).to_string())

    # Models are scored raw, so the composite's raw IC is the like-for-like comparison.
    ic = P.information_coefficient(universe, "signal", "ret_exc_lead1m", "eom")
    raw = P.information_coefficient(universe, "composite", "ret_exc_lead1m", "eom")
    out = {
        "_about": {
            "what": "One run of the fiam/ml scripts. Every ML number in the write-up is from here.",
            "regenerate": "uv run run.py --official --ml",
            "note": "IR is after sector, beta and vol neutralization, the optimizer and costs.",
        },
        # The composite's IR lives in metrics.json, so it is left blank rather than duplicated.
        "composite": dict(
            ic_mean=ic["ic_mean"],
            ic_t=ic["ic_t"],
            months=ic["months"],
            raw_ic_mean=raw["ic_mean"],
            raw_ic_t=raw["ic_t"],
            information_ratio=None,
        ),
    }
    for name in MODELS:
        out[name] = json.loads((PREDS / f"{name}_ic.json").read_text(encoding="utf-8"))
        out[name] |= json.loads((PREDS / f"{name}_portfolio.json").read_text(encoding="utf-8"))
    out["deciles"] = {i: {c: float(v) for c, v in row.items()} for i, row in table.iterrows()}
    paths.write_json(EXHIBITS / "ml_metrics.json", out, rounded=False)


if __name__ == "__main__":
    main()
