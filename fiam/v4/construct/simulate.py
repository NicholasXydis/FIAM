# Books through the daily engine, each planned at its decision close.

from dataclasses import replace

import numpy as np
import pandas as pd

from fiam.v4 import daily_book, data
from fiam.v4.construct import book, costs, execution, optimizer

# Decision closes: month ends, then each week's last session or day.
CADENCES = ("monthly", "weekly", "daily")


# Each decision close in the run and the month end whose inputs it uses.
def decisions(months, end, cadence: str) -> dict:
    ends = data.eom_session(months)
    out = dict(zip(ends, months))
    if cadence not in CADENCES:
        raise ValueError(f"cadence must be one of {CADENCES}")
    if cadence == "monthly":
        return out
    days = data.sessions(ends.iloc[0], end)[:-1]
    if cadence == "weekly":
        days = pd.DatetimeIndex(pd.Series(days, index=days.to_period("W")).groupby(level=0).max())
    known = set(months)
    # Between month ends a close re-plans on the last public month end.
    for d in days:
        eom = data.month_end_at(d)
        if d not in out and eom in known:
            out[d] = eom
    return dict(sorted(out.items()))


# Plans each formation's target from the engine's own holdings at T.
class Planner:
    # The context, the settings, the 0.97 rule and the decision closes.
    def __init__(self, ctx, settings_at, full_gross: bool = True, cadence: str = "monthly",
                 end=None):  # fmt: skip
        self.ctx, self.settings_at, self.full = ctx, settings_at, full_gross
        end = ctx.months[-1] + pd.offsets.MonthEnd(1) if end is None else end
        self.decision = decisions(ctx.months, end, cadence)
        self.month_ends = set(data.eom_session(ctx.months))
        self.hooks, self.info, self.frames = costs.Hooks(), [], {}

    # One month end's inputs, built at its own close and kept for re-plans.
    def inputs(self, eom, prev):
        ctx = self.ctx
        if eom not in self.frames:
            self.frames = {eom: book.month(eom, prev, ctx.f, ctx.fr, ctx.scale, ctx.returns,
                                           ctx.history, ctx.holdings, ctx.z,
                                           ctx.neutral)}  # fmt: skip
            data._CACHE.clear()
        return self.frames[eom]

    # At T's close: the book after T's trades, the optimiser, lever A4.
    def plan(self, T, held_book, held: pd.Series | None = None):
        ctx, eom = self.ctx, self.decision[T]
        nav = held_book.cash + sum(held_book.values.values())
        prev = pd.Series(held_book.values, dtype=float) / nav if held is None else held
        prev = prev[prev.abs() > 1e-12]
        x, alpha, loadings, cov, spec = self.inputs(eom, prev)
        cap = ctx.caps[eom]
        s = self.settings_at(eom, x, cap)
        s = replace(s, nav=nav, norm=ctx.scale * float(np.sqrt(spec).median()))
        # Formation gross = min(C_t - d, 0.97 x the largest feasible gross).
        top = optimizer.largest_gross(x, alpha, prev, s, cap) if self.full else None
        # None feasible unrelaxed from 1.00: C_t - d and the relax ladder.
        if top is not None:
            s = replace(s, gross=min(s.gross, 0.97 * top))
        chol = np.linalg.cholesky(cov.to_numpy() + 1e-12 * np.eye(len(cov)))
        w, step, used = optimizer.optimise(x, alpha, loadings, chol, spec.to_numpy(), prev, s,
                                           initial=prev.empty)  # fmt: skip
        # No answer: the held book stays as it is, never blended.
        if w is None:
            w, step = prev, "held"
        else:
            # Lever A4 at the settings the optimum was solved at (review M).
            w = book.partial(w, prev, x, used, alpha)
        trade = w.reindex(x.index).fillna(0.0) - prev.reindex(x.index).fillna(0.0)
        self.info.append({"T": T, "eom": eom, "names": len(w), "step": step,
                          "gross": float(w.abs().sum()), "target_gross": s.gross,
                          "largest_gross": top,
                          "cost": costs.share_of_nav(trade.to_numpy(), x, nav),
                          "beta_60m": float(x["beta_60m"].reindex(w.index).fillna(0.0) @ w),
                          "squeezed": int(x["squeezed"].sum()),
                          "crowded": int(x["crowded"].sum())})  # fmt: skip
        both = w.index.union(prev.index)
        planned = (w.reindex(both).fillna(0.0) - prev.reindex(both).fillna(0.0)) * nav
        return w, x[book.FRAME_COLS], cap, nav, planned, prev


# One run of every formation, planned live, through the engine to end.
def run(ctx, settings_at, end, full_gross: bool = True, squeeze: bool = True,
        cadence: str = "monthly", overlays=None, brake: bool = False,
        hook_class=execution.Execution, unsealed: bool = False):  # fmt: skip
    planner = Planner(ctx, settings_at, full_gross, cadence, end)
    ids = sorted(ctx.f["permno"].unique())
    T0 = data.eom_session([ctx.months[0]]).iloc[0]
    watch = execution.SqueezeWatch(ids, T0, end) if squeeze else None
    trigger = execution.TriggerBeta(ctx.returns, ctx.late)
    hook = hook_class({}, watch, planner, trigger, overlays, brake)
    holders = {e: pd.Series(dtype=float) for e in ctx.months}
    # The final run checks its own breaches, so its days are kept first.
    result = daily_book.run(holders, T0, end, costs=planner.hooks.costs,
                            borrow=planner.hooks.borrow, hook=hook, permnos=ids,
                            unsealed=unsealed, strict=False)  # fmt: skip
    log = pd.DataFrame(hook.log, columns=["date", "kind", "value"])
    result.events = pd.concat([result.events, log], ignore_index=True)
    result.hook, result.hooks = hook, planner.hooks
    return result, planner.info
