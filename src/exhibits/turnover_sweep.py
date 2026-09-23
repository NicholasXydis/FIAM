# Asks whether trading less helps, by penalising turnover in the optimizer. Takes an hour.
#
# Repeats pipeline.run because the penalty changes the objective. Limits re-asserted below.

import json
import sys
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

OUT = Path("submission/exhibits")

# Zero is the shipped book. The rest trade less, so does any of them earn more?
LAMBDAS = (0.0, 0.25, 0.5, 1.0, 2.0)


# One month, with an optional penalty on moving away from last month's book.
def optimize(month: pd.DataFrame, previous: pd.Series | None, penalty: float) -> pd.Series | None:
    month = month.sort_values("signal")
    pool = pd.concat([month.tail(P.LIMITS["pool"]), month.head(P.LIMITS["pool"])])
    names = pool["permno"].to_numpy()

    # Held names outside the pool join at a target of zero, or we hide the cost of selling.
    if previous is not None:
        leaving = previous.index.difference(pd.Index(names))
        if len(leaving):
            extra = month[month["permno"].isin(leaving)]
            pool = pd.concat([pool, extra])
            names = pool["permno"].to_numpy()

    a = pool["signal"].to_numpy()
    beta = pool["beta_60m"].to_numpy()
    risk = pool["risk_rank"].to_numpy()
    sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)

    w = cp.Variable(len(pool))
    lo = np.where(a >= 0, 0.0, -P.LIMITS["name"])
    hi = np.where(a >= 0, P.LIMITS["name"], 0.0)
    constraints = [
        cp.sum(w) == 0,
        cp.norm1(w) <= P.LIMITS["gross"],
        w >= lo,
        w <= hi,
        cp.abs(beta @ w) <= P.LIMITS["beta"],
        cp.abs(risk @ w) <= P.LIMITS["risk"],
        cp.abs(sectors.T @ w) <= P.LIMITS["sector"],
    ]
    objective = a @ w - 0.5 * P.LIMITS["ridge"] * cp.sum_squares(w)
    if penalty > 0 and previous is not None:
        held = previous.reindex(names).fillna(0.0).to_numpy()
        objective = objective - penalty * cp.norm1(w - held)

    problem = cp.Problem(cp.Maximize(objective), constraints)
    problem.solve(solver=cp.CLARABEL)
    if w.value is None:
        return None
    weights = pd.Series(w.value, index=names)
    return weights[weights.abs() > 1e-5]


# The whole book at one penalty setting, charged the same way the pipeline charges it.
def backtest(universe: pd.DataFrame, penalty: float) -> pd.DataFrame:
    rows, previous, previous_spreads = [], None, None
    for month in sorted(universe["eom"].unique()):
        cross_section = universe[universe["eom"] == month]
        weights = optimize(cross_section, previous, penalty)
        if weights is None:
            continue
        info = cross_section.set_index("permno").loc[weights.index]
        weights = P.to_whole_shares(weights, info["prc"].abs())
        info = info.loc[weights.index]

        # The shipped cost model, called rather than copied, so the two cannot drift apart.
        spreads = cross_section.set_index("permno")["bidaskhl_21d"]
        cost, turnover = P.trading_cost(weights, previous, info, spreads, previous_spreads)
        gross = (weights * info["ret_exc_lead1m"].fillna(0.0)).sum()
        # Every scenario clears the book's limits, or a setting wins by breaking one.
        assert 100 <= len(weights) <= 500, f"{penalty}: {len(weights)} positions"
        assert weights.abs().sum() <= 2.0 + 1e-9, f"{penalty}: gross above 200%"
        assert abs(weights.sum()) < 0.005, f"{penalty}: net exposure outside tolerance"
        rows.append(
            dict(gross=gross, cost=cost, net=gross - cost, turnover=turnover, n=len(weights))
        )
        previous, previous_spreads = weights, spreads
    return pd.DataFrame(rows)


# Runs the book at each penalty setting and reports what trading less actually costs.
def main() -> None:
    universe = P.build_signal(P.screen(P.load_panel()))
    out = {}
    print(f"{'penalty':>8} {'turnover':>9} {'cost':>7} {'net':>8} {'IR':>6} {'names':>6}")
    for penalty in LAMBDAS:
        book = backtest(universe, penalty)
        active = book["net"] - 0.04 / 12
        out[f"lambda_{penalty:g}"] = dict(
            turnover=float(book["turnover"].mean()),
            cost_annual=float(book["cost"].mean() * 12),
            net_annual=float(book["net"].mean() * 12),
            information_ratio=float(active.mean() / active.std() * np.sqrt(12)),
            positions=float(book["n"].mean()),
        )
        s = out[f"lambda_{penalty:g}"]
        print(
            f"{penalty:>8.2f} {s['turnover']:>8.0%} {s['cost_annual']:>7.2%} "
            f"{s['net_annual']:>7.1%} {s['information_ratio']:>6.2f} {s['positions']:>6.0f}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "turnover_sweep.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
