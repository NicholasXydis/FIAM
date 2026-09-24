# Where a prediction stops being worth trading. Writes exhibits/constraint_survival.json.

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

# The prediction steps. Each takes one more thing out, so a drop has one cause.
PREDICTIVE = ("raw", "sector", "beta", "vol")

# The portfolio steps. Each row adds a choice to the one above, not one clean rule each.
PORTFOLIO = ("equal_weight", "optimizer", "constrained", "whole_shares", "after_costs")


# The four prediction steps for one score. They stack, each row keeping the ones above.
def predictive_stages(frame: pd.DataFrame, score: str) -> dict:
    out, current = {}, P.rank_z(frame, score).fillna(0.0)
    for stage in PREDICTIVE:
        if stage == "sector":
            current = current - current.groupby([frame["eom"], frame["sector"]]).transform("mean")
        elif stage == "beta":
            current = P.residualize(frame, current, frame["beta_60m"])
        elif stage == "vol":
            current = P.residualize(frame, current, frame["risk_rank"])
        # Derived here, because build_signal keys on the decision month only.
        work = frame.assign(
            s=current, holding_month=(frame["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
        ).dropna(subset=["ret_exc_lead1m"])
        # Both on the same score. A model can hold its IC and still lose the tails.
        ic = P.information_coefficient(work, "s", "ret_exc_lead1m")
        spread = work.groupby("holding_month", group_keys=False).apply(_decile_spread).dropna()
        out[stage] = dict(
            ic_mean=ic["ic_mean"],
            ic_t=ic["ic_t"],
            decile_spread_annual=float(spread.mean() * 12),
            months=ic["months"],
            # Some models say nothing some months, so report how many they were scored on.
            decile_months=int(len(spread)),
        )
    return out


# Top decile minus bottom for one month. Needs ten real buckets to mean anything.
def _decile_spread(group: pd.DataFrame) -> float:
    if len(group) < 20:
        return np.nan
    # A flat month ranked by row order would invent a spread, so it gets none.
    if group["s"].nunique() < 10:
        return np.nan
    buckets = pd.qcut(group["s"].rank(method="first"), 10, labels=False, duplicates="drop")
    if buckets.max() != 9:
        return np.nan
    top = group.loc[buckets == 9, "ret_exc_lead1m"].mean()
    bottom = group.loc[buckets == 0, "ret_exc_lead1m"].mean()
    return float(top - bottom)


# The simplest book. Buy the best, short the worst, equal size, budget only.
def naive_book(frame: pd.DataFrame, score: str, n: int, gross: float = 2.0) -> pd.DataFrame:
    rows = []
    for month, g in frame.groupby("eom"):
        g = g.sort_values(score)
        longs, shorts = g.tail(n), g.head(n)
        side = gross / 2
        weights = pd.concat(
            [
                pd.Series(side / len(longs), index=longs["permno"]),
                pd.Series(-side / len(shorts), index=shorts["permno"]),
            ]
        )
        info = g.set_index("permno").loc[weights.index]
        rows.append(
            dict(
                eom=month,
                gross=float((weights * info["ret_exc_lead1m"].fillna(0.0)).sum()),
                n=len(weights),
            )
        )
    return pd.DataFrame(rows)


# Runs the book once. Stages differ only in `constrained` and `round_shares`.
def run_book(universe: pd.DataFrame, constrained: bool, round_shares: bool) -> pd.DataFrame:
    return P.backtest(
        universe,
        lambda m, prev: P.optimize_month(m, prev, constrained=constrained),
        round_shares=round_shares,
    )


# One stage's row. Only the last stage charges costs, so every other one scores gross.
def stage(book: pd.DataFrame, returns: str, note: str) -> dict:
    turnover = float(book["turnover"].mean()) if "turnover" in book else None
    return dict(
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(book[returns].mean() * 12),
        turnover=turnover,
        positions=float(book["n"].mean()),
        net_ir=P.information_ratio(book[returns]),
        note=note,
    )


# The five portfolio stages, each adding one construction choice to the one before.
def portfolio_stages(universe: pd.DataFrame) -> dict:
    rounded = run_book(universe, constrained=True, round_shares=True)
    return dict(
        equal_weight=stage(
            naive_book(universe, "signal", n=P.LIMITS["pool"]),
            "gross",
            "equal-weight top and bottom 200 of a score already sector- and beta-adjusted",
        ),
        optimizer=stage(
            run_book(universe, constrained=False, round_shares=False),
            "gross",
            "convex optimizer, budget and per-name cap",
        ),
        constrained=stage(
            run_book(universe, constrained=True, round_shares=False),
            "gross",
            "plus the portfolio exposure constraints: sector, beta, volatility",
        ),
        whole_shares=stage(rounded, "gross", "plus whole-share rounding against a $10m NAV"),
        after_costs=stage(rounded, "net", "plus the full cost model, this row is the shipped book"),
    )


def main() -> None:
    base = P.universe()
    result = dict(
        what="Panel A is prediction, panel B is portfolio; the two are different metrics and "
        "are never drawn as one line. Each panel-B row adds one construction choice on top of "
        "the row above it. It is not one isolated restriction per row: the score entering row "
        "one is already sector-demeaned and beta-residualized, and moving from equal-weight to "
        "the optimizer also introduces the per-name cap.",
        predictive_stages=list(PREDICTIVE),
        portfolio_stages=list(PORTFOLIO),
        code=P.source_fingerprint(),
        models={},
    )
    for model in MODELS:
        # Same universe and months throughout, so the comparison is of scores and nothing else.
        preds = None if model == "composite" else pd.read_parquet(PREDS / f"{model}.parquet")
        universe = base if preds is None else P.swap_score(base, preds)
        score = "composite" if preds is None else "pred"
        print(f"[{model}] {len(universe):,} rows, {universe['eom'].nunique()} months")
        result["models"][model] = dict(
            predictive=predictive_stages(universe, score),
            portfolio=portfolio_stages(universe),
        )
        p = result["models"][model]["portfolio"]
        print(
            f"  IR: equal-weight {p['equal_weight']['net_ir']:+.2f} -> "
            f"constrained {p['constrained']['net_ir']:+.2f} -> "
            f"net {p['after_costs']['net_ir']:+.2f}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "constraint_survival.json").write_text(json.dumps(result, indent=2))
    print("\nwrote constraint_survival.json")


if __name__ == "__main__":
    main()
