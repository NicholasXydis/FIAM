# The v4 formation optimiser (PLAN §8.3): a convex QP under every rule.

from dataclasses import dataclass, replace

import cvxpy as cp
import numpy as np
import pandas as pd

from fiam.v4.construct import costs, inputs

NAV = 1e9
# Name caps (PLAN §3.1): longs 1.5% and 0.4 ADV, shorts 1% and 0.3 ADV.
LONG_CAP, SHORT_CAP, LONG_ADV, SHORT_ADV = 0.015, 0.010, 0.4, 0.3
# Execution: 10% of ADV a close over the trade day and four more.
SPILL_ADV, SPILL_CLOSES = 0.10, 5
# Sign-fixed floors: 0.10% on the top 110 candidates of each side.
FLOOR, FLOOR_NAMES = 0.001, 110
# The internal name cap; a solve over it is trimmed and re-solved.
NAMES_MAX = 480
# New positions only from each side's best alpha: a decile, then wider.
POOLS = (0.10, 0.15, 0.20)
# A side's pool widens until this many names may hold it (PLAN §8.3).
ALLOWED = 130
# The book's panel beta_60m stays within this band (reading 8).
MONTHLY_BAND = 0.02
# The largest feasible gross is searched from 1.00 up (the checklist).
GROSS_FROM = 1.0
# A weight under 0.05% of NAV is dropped and the month solved again.
MIN_WEIGHT = 0.0005
# Exact rules hold to 1e-4; an answer counts if each holds to 1e-3.
TOL, CHECK = 1e-4, 1e-3


# One formation's settings; the relax ladder loosens them in order.
@dataclass(frozen=True)
class Settings:
    gross: float
    ridge: float
    risk_lambda: float
    style_cap: float
    sector_band: float = 0.01
    beta_band: float = TOL
    neutral_band: float = TOL
    cost_budget: float | None = None
    participation: bool = True
    nav: float = NAV
    # Alpha's size per unit z, so the ridge works in z units as v1's grid.
    norm: float = 1.0
    # Lever A4: the book moves this share of the way to the optimum.
    speed: float = 1.0
    # The name cap (480; 275 for exam design 2) and the monthly beta band.
    names_max: int = NAMES_MAX
    monthly_band: float = MONTHLY_BAND
    # Capped styles held at zero instead, as size and value (reading 17).
    neutral_styles: tuple = ()


# Each name's long and short cap from its ADV (PLAN §3.1).
def caps(adv, nav: float) -> tuple:
    return np.minimum(LONG_CAP, LONG_ADV * adv / nav), np.minimum(SHORT_CAP, SHORT_ADV * adv / nav)


# Each side scaled to half the gross; an empty side stays empty.
def rescale(w: pd.Series, gross: float) -> pd.Series:
    longs, shorts = w[w > 0].sum(), -w[w < 0].sum()
    if longs > 0:
        w = w.where(w < 0, w * gross / 2 / longs)
    if shorts > 0:
        w = w.where(w > 0, w * gross / 2 / shorts)
    return w


# PLAN §8.3's relax order for an infeasible month, each step cumulative.
def ladder(s: Settings, initial: bool) -> list[tuple[str, Settings]]:
    steps = [("none", s)]
    steps.append(("betas", replace(steps[-1][1], beta_band=0.02, monthly_band=2 * s.monthly_band)))
    steps.append(("sectors", replace(steps[-1][1], sector_band=0.015)))
    steps.append(("size_value", replace(steps[-1][1], neutral_band=0.05)))
    steps.append(("styles", replace(steps[-1][1], style_cap=2 * s.style_cap)))
    budget = None if s.cost_budget is None else 2 * s.cost_budget
    steps.append(("cost_budget", replace(steps[-1][1], cost_budget=budget)))
    if initial:
        steps.append(("participation", replace(steps[-1][1], participation=False)))
    return steps


# Each name's side and bounds from its alpha, holding and permissions.
def bounds(x: pd.DataFrame, alpha: pd.Series, prev: pd.Series, nav: float, pool):
    pool_long, pool_short = pool if isinstance(pool, tuple) else (pool, pool)
    a, held = alpha.to_numpy(), prev.reindex(x.index).fillna(0.0).to_numpy()
    # A held name whose alpha turned keeps its side and may only shrink.
    turned = (held != 0) & (np.sign(held) != np.sign(a))
    side = np.where(turned, np.sign(held), np.sign(a))
    known = np.isfinite(x["dolvol_126d"].to_numpy(dtype=float))
    # Caps and participation on ADV with its 5th-percentile floor (Step 7).
    adv = x["adv_cost"].to_numpy(dtype=float)
    long_cap, short_cap = caps(adv, nav)
    room = SPILL_ADV * SPILL_CLOSES * adv / nav
    crowded, squeezed = x["crowded"].to_numpy(bool), x["squeezed"].to_numpy(bool)
    # The pool: the top decile by alpha may open longs, the bottom shorts.
    pct = pd.Series(a).rank(pct=True).to_numpy()
    inside = np.where(a > 0, pct > 1 - pool_long, pct <= pool_short)
    may_long = x["new_long"].to_numpy(bool) & known & ~crowded & inside & ~turned
    may_short = x["new_short"].to_numpy(bool) & known & ~squeezed & inside & ~turned
    up, down = np.clip(held, 0, None), np.clip(held, None, 0)
    # No leave to add: stay or shrink, toward the cap as fast as allowed.
    hi_long = np.maximum(np.where(may_long, long_cap, np.minimum(up, long_cap)), up - room)
    lo_short = np.minimum(
        np.where(may_short, -short_cap, np.maximum(down, -short_cap)), down + room
    )
    hi = np.where(side > 0, hi_long, 0.0)
    lo = np.where(side < 0, lo_short, 0.0)
    return side, lo, hi, a, room


# Each side's first pool letting 130 names take that side (reading 7).
def start_pools(x, alpha, prev, nav: float) -> tuple:
    out = []
    for long_side in (True, False):
        for pool in POOLS:
            _, lo, hi, *_ = bounds(x, alpha, prev, nav, pool)
            # Allowed: may hold at least the 0.10% floor, as §8.3's candidates.
            allowed = int((hi >= FLOOR).sum()) if long_side else int((lo <= -FLOOR).sum())
            if allowed >= ALLOWED or pool == POOLS[-1]:
                out.append(pool)
                break
    return tuple(out)


# The floors: the 110 best of each side that may reach 0.10% must.
def floors(side, lo, hi, a):
    lo, hi = lo.copy(), hi.copy()
    longs = np.where((side > 0) & (hi >= FLOOR))[0]
    shorts = np.where((side < 0) & (lo <= -FLOOR))[0]
    lo[longs[np.argsort(-a[longs])][:FLOOR_NAMES]] = FLOOR
    hi[shorts[np.argsort(a[shorts])][:FLOOR_NAMES]] = -FLOOR
    return lo, hi


# Every rule but the gross: bounds, neutrality, styles, trading limits.
def rules(w, x, prev, s: Settings, keep, pool, alpha, fixed: bool = True):
    side, lo, hi, a, room = bounds(x, alpha, prev, s.nav, pool)
    if fixed:
        lo, hi = floors(side, lo, hi, a)
    if keep is not None:
        lo, hi = np.where(keep, lo, 0.0), np.where(keep, hi, 0.0)
    held = prev.reindex(x.index).fillna(0.0).to_numpy()
    cons = [cp.sum(w) == 0, w >= lo, w <= hi]
    cons += [cp.abs(x[k].fillna(x[k].median()).to_numpy() @ w) <= s.beta_band
             for k in ("welch", "dimson")]  # fmt: skip
    cons.append(cp.abs(x["beta_60m"].to_numpy() @ w) <= s.monthly_band)
    sectors = pd.get_dummies(x["sector"], dtype=float).to_numpy()
    cons.append(cp.abs(sectors.T @ w) <= s.sector_band)
    cons += [cp.abs(x[k].to_numpy() @ w) <= s.neutral_band for k in inputs.NEUTRAL]
    cons += [cp.abs(x[k].to_numpy() @ w) <= (s.neutral_band if k in s.neutral_styles
             else s.style_cap * s.gross) for k in inputs.CAPPED]  # fmt: skip
    trade = w - held
    started = np.abs(held).sum() > 0
    if s.participation and started:
        cons.append(cp.abs(trade) <= room)
    cost = costs.convex(trade, x, s.nav)
    if s.cost_budget is not None and started:
        cons.append(cost <= s.cost_budget)
    return cons, side, lo, hi, a, cost


# The problem at one setting; None if no answer meets every rule.
def solve(x, alpha, loadings, chol, spec, prev, s: Settings, keep=None, pool=POOLS[0]):
    w = cp.Variable(len(x))
    cons, side, lo, hi, a, cost = rules(w, x, prev, s, keep, pool, alpha)
    cons.append(side @ w == s.gross)
    b = loadings.to_numpy()
    risk = cp.sum_squares(chol.T @ (b.T @ w)) + cp.sum(cp.multiply(spec, cp.square(w)))
    borrow = x["borrow"].to_numpy() / 12 @ cp.neg(w)
    obj = (a @ w - s.risk_lambda * risk - borrow - cost) / s.norm - s.ridge * cp.sum_squares(w)
    value = answer(cp.Problem(cp.Maximize(obj), cons), w, cons)
    if value is None:
        return None
    out = pd.Series(np.clip(value, lo, hi), index=x.index)
    return out[out.abs() > 1e-6]


# A problem's answer if every rule holds to 1e-3, else None.
def answer(problem, w, cons):
    for solver in (cp.CLARABEL, cp.SCS):
        try:
            problem.solve(solver=solver)
        except cp.error.SolverError:
            continue
        # Proven infeasible stays so; SCS only for a numeric failure.
        if problem.status in ("infeasible", "infeasible_inaccurate"):
            return None
        if w.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
            continue
        if max(float(np.max(c.violation())) for c in cons) <= CHECK:
            return w.value
    return None


# The largest gross from 1.00 to C_t solvable unrelaxed, else None.
def largest_gross(x, alpha, prev, s: Settings, cap: float) -> float | None:
    w = cp.Variable(len(x))
    cons, side, *_ = rules(w, x, prev, s, None, POOLS[-1], alpha)
    problem = cp.Problem(cp.Maximize(side @ w), [*cons, side @ w <= cap])
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.error.SolverError:
        return None
    if problem.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
        return None
    top = float(np.floor(problem.value * 100) / 100)
    return top if top >= GROSS_FROM else None


# Lever A4's blend moved onto every rule: the nearest book that fits.
def project(blend: pd.Series, x, alpha, prev, s: Settings) -> pd.Series | None:
    target = blend.reindex(x.index).fillna(0.0).to_numpy()
    keep, first, kept = None, None, blend.index
    # Small and extra names out, then the same projection once more.
    for _ in range(2):
        w = cp.Variable(len(x))
        cons, side, lo, hi, *_ = rules(w, x, prev, s, keep, POOLS[-1], alpha, fixed=False)
        cons.append(side @ w == s.gross)
        value = answer(cp.Problem(cp.Minimize(cp.sum_squares(w - target)), cons), w, cons)
        if value is None:
            return None if first is None else trimmed(first, kept, s.gross)
        out = pd.Series(np.clip(value, lo, hi), index=x.index)
        out = out[out.abs() > 1e-6]
        kept = out[out.abs() >= MIN_WEIGHT].abs().nlargest(s.names_max).index
        if len(kept) == len(out):
            return out
        keep, first = x.index.isin(kept), out
    return trimmed(out, kept, s.gross)


# Over 480 names and a failed re-solve: the largest kept, rescaled.
def trimmed(w: pd.Series, keep, gross: float) -> pd.Series:
    return rescale(w[w.index.isin(keep)], gross)


# A formation's book, its log line and the settings it was solved at.
def optimise(x, alpha, loadings, chol, spec, prev, s: Settings, initial: bool):
    first = start_pools(x, alpha, prev, s.nav)
    pools = list(dict.fromkeys((max(first[0], p), max(first[1], p)) for p in POOLS))
    for step, setting in ladder(s, initial):
        for pool in pools:
            w = solve(x, alpha, loadings, chol, spec, prev, setting, pool=pool)
            if w is not None:
                w, how = finish(w, x, alpha, loadings, chol, spec, prev, setting, pool)
                return w, f"{step}, {label(pool)}{how}", setting
    # Then gross down to feasible, 0.01 a step from the target to 1.00.
    last = ladder(s, initial)[-1][1]
    for gross in np.arange(s.gross - 0.01, 0.995, -0.01):
        setting = replace(last, gross=float(gross))
        w = solve(x, alpha, loadings, chol, spec, prev, setting, pool=POOLS[-1])
        if w is not None:
            w, how = finish(w, x, alpha, loadings, chol, spec, prev, setting, POOLS[-1])
            return w, f"gross {gross:.2f}{how}", setting
    return None, "infeasible", s


# Under 0.05% out, over the name cap the smallest; then solved again.
def finish(w, x, alpha, loadings, chol, spec, prev, setting: Settings, pool) -> tuple:
    keep = w[w.abs() >= MIN_WEIGHT].abs().nlargest(setting.names_max).index
    if len(keep) == len(w):
        return w, ""
    again = solve(x, alpha, loadings, chol, spec, prev, setting, x.index.isin(keep), pool)
    if again is None:
        return trimmed(w, keep, setting.gross), ", trimmed"
    return again, ""


# A pool pair as text for the log: long pool / short pool.
def label(pool) -> str:
    return f"pools {pool[0]:.0%}/{pool[1]:.0%}"
