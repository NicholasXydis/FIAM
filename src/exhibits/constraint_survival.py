# Where a prediction stops being worth trading. Writes exhibits/constraint_survival.json.

from __future__ import annotations

import json
import sys
from pathlib import Path

import cvxpy as cp
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


# Rank within month, then z-score. Every stage starts from the same place.
def zscore(frame: pd.DataFrame, col: str) -> pd.Series:
    r = frame.groupby("eom")[col].rank(pct=True)
    mu = r.groupby(frame["eom"]).transform("mean")
    sd = r.groupby(frame["eom"]).transform("std")
    return ((r - mu) / sd.replace(0.0, np.nan)).fillna(0.0)


# Takes the part of y that moves with x back out, month by month. Beta and volatility.
def residualize(frame: pd.DataFrame, y: pd.Series, x: pd.Series) -> pd.Series:
    bx = x - x.groupby(frame["eom"]).transform("mean")
    sy = y - y.groupby(frame["eom"]).transform("mean")
    cov = (bx * sy).groupby(frame["eom"]).transform("sum")
    var = (bx * bx).groupby(frame["eom"]).transform("sum")
    return sy - (cov / var.replace(0.0, np.nan)).fillna(0.0) * bx


# The four prediction steps for one score. They stack, each row keeping the ones above.
def predictive_stages(frame: pd.DataFrame, score: str) -> dict:
    out, current = {}, zscore(frame, score)
    for stage in PREDICTIVE:
        if stage == "sector":
            current = current - current.groupby([frame["eom"], frame["sector"]]).transform("mean")
        elif stage == "beta":
            current = residualize(frame, current, frame["beta_60m"])
        elif stage == "vol":
            current = residualize(frame, current, frame["risk_rank"])
        # Derived here, because build_signal keys on the decision month only.
        work = frame.assign(
            s=current, holding_month=(frame["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
        ).dropna(subset=["ret_exc_lead1m"])
        # Both on the same score. A model can hold its IC and still lose the tails.
        ic = (
            work.groupby("holding_month")
            .apply(lambda g: g["s"].corr(g["ret_exc_lead1m"], method="spearman"))
            .dropna()
        )
        spread = work.groupby("holding_month", group_keys=False).apply(_decile_spread).dropna()
        out[stage] = dict(
            ic_mean=float(ic.mean()),
            ic_t=float(ic.mean() / ic.std() * np.sqrt(len(ic))) if ic.std() else 0.0,
            decile_spread_annual=float(spread.mean() * 12),
            months=int(len(ic)),
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


# The book's optimizer with one switch. constrained=False keeps budget and name cap only.
def optimize(
    month: pd.DataFrame, previous: pd.Series | None, constrained: bool
) -> pd.Series | None:
    month = month.sort_values("signal")
    pool = pd.concat([month.tail(P.LIMITS["pool"]), month.head(P.LIMITS["pool"])])
    if previous is not None:
        held = month[month["permno"].isin(previous.index) & ~month["permno"].isin(pool["permno"])]
        if not held.empty:
            pool = pd.concat([pool, held])

    a = pool["signal"].to_numpy()
    w = cp.Variable(len(pool))
    lo = np.where(a >= 0, 0.0, -P.LIMITS["name"])
    hi = np.where(a >= 0, P.LIMITS["name"], 0.0)
    constraints = [cp.sum(w) == 0, cp.norm1(w) <= P.LIMITS["gross"], w >= lo, w <= hi]
    if constrained:
        beta = pool["beta_60m"].to_numpy()
        risk = pool["risk_rank"].to_numpy()
        sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)
        constraints += [
            cp.abs(beta @ w) <= P.LIMITS["beta"],
            cp.abs(risk @ w) <= P.LIMITS["risk"],
            cp.abs(sectors.T @ w) <= P.LIMITS["sector"],
        ]
    problem = cp.Problem(
        cp.Maximize(a @ w - 0.5 * P.LIMITS["ridge"] * cp.sum_squares(w)), constraints
    )
    problem.solve(solver=cp.CLARABEL)
    if w.value is None:
        return None
    weights = pd.Series(w.value, index=pool["permno"].to_numpy())
    return weights[weights.abs() > 1e-5]


# Runs the book once. Stages differ only in `constrained` and `round_shares`.
def run_book(universe: pd.DataFrame, constrained: bool, round_shares: bool) -> pd.DataFrame:
    rows, previous, previous_spreads = [], None, None
    for month in sorted(universe["eom"].unique()):
        cross = universe[universe["eom"] == month]
        weights = optimize(cross, previous, constrained)
        if weights is None or not len(weights):
            continue
        info = cross.set_index("permno").loc[weights.index]
        if round_shares:
            weights = P.to_whole_shares(weights, info["prc"].abs())
            info = info.loc[weights.index]
            if not len(weights):
                continue
        spreads = cross.set_index("permno")["bidaskhl_21d"]
        cost, turnover = P.trading_cost(weights, previous, info, spreads, previous_spreads)
        rows.append(
            dict(
                holding_month=(month + pd.offsets.MonthBegin(1)).normalize(),
                gross=float((weights * info["ret_exc_lead1m"].fillna(0.0)).sum()),
                cost=cost,
                turnover=turnover,
                n=len(weights),
            )
        )
        previous, previous_spreads = weights, spreads
    return pd.DataFrame(rows).set_index("holding_month")


# IR against T-bill plus 4%. The T-bill cancels, so only the 4% comes off.
def information_ratio(returns: pd.Series) -> float:
    active = returns - 0.04 / 12
    return float(active.mean() / active.std() * np.sqrt(12)) if active.std() else 0.0


# The five portfolio stages. The first two charge no costs, so net equals gross there.
def portfolio_stages(universe: pd.DataFrame) -> dict:
    out = {}

    naive = naive_book(universe, "signal", n=P.LIMITS["pool"])
    naive.index = (naive["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    out["equal_weight"] = dict(
        gross_annual=float(naive["gross"].mean() * 12),
        net_annual=float(naive["gross"].mean() * 12),
        turnover=None,
        positions=float(naive["n"].mean()),
        net_ir=information_ratio(naive["gross"]),
        note="equal-weight top and bottom 200 of a score already sector- and beta-adjusted",
    )

    unconstrained = run_book(universe, constrained=False, round_shares=False)
    out["optimizer"] = dict(
        gross_annual=float(unconstrained["gross"].mean() * 12),
        net_annual=float(unconstrained["gross"].mean() * 12),
        turnover=float(unconstrained["turnover"].mean()),
        positions=float(unconstrained["n"].mean()),
        net_ir=information_ratio(unconstrained["gross"]),
        note="convex optimizer, budget and per-name cap",
    )

    constrained = run_book(universe, constrained=True, round_shares=False)
    out["constrained"] = dict(
        gross_annual=float(constrained["gross"].mean() * 12),
        net_annual=float(constrained["gross"].mean() * 12),
        turnover=float(constrained["turnover"].mean()),
        positions=float(constrained["n"].mean()),
        net_ir=information_ratio(constrained["gross"]),
        note="plus the portfolio exposure constraints: sector, beta, volatility",
    )

    rounded = run_book(universe, constrained=True, round_shares=True)
    out["whole_shares"] = dict(
        gross_annual=float(rounded["gross"].mean() * 12),
        net_annual=float(rounded["gross"].mean() * 12),
        turnover=float(rounded["turnover"].mean()),
        positions=float(rounded["n"].mean()),
        net_ir=information_ratio(rounded["gross"]),
        note="plus whole-share rounding against a $10m NAV",
    )

    net = rounded["gross"] - rounded["cost"]
    out["after_costs"] = dict(
        gross_annual=float(rounded["gross"].mean() * 12),
        net_annual=float(net.mean() * 12),
        turnover=float(rounded["turnover"].mean()),
        positions=float(rounded["n"].mean()),
        net_ir=information_ratio(net),
        note="plus the full cost model, this row is the shipped book",
    )
    return out


# Swaps a model's predictions in for the composite, same universe and months throughout.
def universe_for(panel: pd.DataFrame, model: str) -> pd.DataFrame:
    base = P.build_signal(P.screen(panel))
    if model == "composite":
        return base
    preds = pd.read_parquet(PREDS / f"{model}.parquet")
    preds["eom"] = pd.to_datetime(preds["eom"])
    merged = base.merge(preds[["permno", "eom", "pred"]], on=["permno", "eom"], how="inner")
    # Same treatment the composite gets, so the comparison is of scores and nothing else.
    merged["signal"] = residualize(
        merged,
        (lambda z: z - z.groupby([merged["eom"], merged["sector"]]).transform("mean"))(
            zscore(merged, "pred")
        ),
        merged["beta_60m"],
    )
    return merged


def main() -> None:
    panel = P.load_panel()
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
        universe = universe_for(panel, model)
        score = "composite" if model == "composite" else "pred"
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
