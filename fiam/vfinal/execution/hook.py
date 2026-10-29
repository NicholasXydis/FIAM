# The daily hook: form, work in fifths at 10% ADV, guard, trim.

import numpy as np
import pandas as pd

from fiam.vfinal import config, data
from fiam.vfinal.construct import optimize


# The gross the guard reads: the previous close's (PDF p15).
def guard_gross(lag: bool, total: dict, nav: float, closing: dict, last_nav) -> float:
    if lag:
        return sum(abs(v) for v in closing.values()) / last_nav if last_nav else 0.0
    return sum(abs(v) for v in total.values()) / nav if nav > 0 else 0.0


# The scale at a formation: k, never past the formation gross cap.
def scale(weights: pd.Series, ov: config.Overlay) -> float:
    gross = float(weights.abs().sum())
    if ov.scale_k is not None:
        return float(min(ov.scale_k, ov.scale_cap / gross)) if gross > 0 else 1.0
    return 1.0


# Weights scaled, longs clipped to the long cap and shorts to theirs.
def clip(weights: pd.Series, long_cap: float, short_cap: float) -> pd.Series:
    return weights.clip(lower=-short_cap, upper=long_cap)


# The daily hook daily_book.run calls before each session's trades.
class Hook:
    # A book's world, settings and law; core targets for a scaled book.
    def __init__(self, world, run: config.Run, law, core: dict | None = None):
        self.world, self.x, self.ov = world, run.execution, run.overlay
        self.law, self.core = law, core
        self.by_signal = dict(world.reviews)
        self.days = data.sessions(config.START, config.END)
        # forming tells the book a formation's first trade day is today.
        self.forming, self.pending, self.formed, self.left = False, None, None, 0
        self.wanted, self.core_now, self.scale_now = {}, None, 1.0
        self.seen, self.targets, self.logs = 0, [], []

    # The target weights the book is heading for right now.
    def heading(self) -> pd.Series:
        p = self.world.p
        return clip(self.core_now * self.scale_now, p.position_cap, p.position_cap_short)

    # Starts a 5-session working toward the current target.
    def start(self, values: dict, nav: float) -> None:
        target = self.heading() * nav
        self.wanted = {p: 0.0 for p in values} | {int(p): float(v) for p, v in target.items()}
        self.left = self.x.sessions

    # One formation's core target: solved now, or the core book's.
    def form(self, eom, d, values: dict, nav: float, at=None) -> None:
        w_pre = pd.Series(values, dtype=float) / nav
        if self.core is not None:
            core, log = self.core[pd.Timestamp(d)], {"support": "core", "core": self.ov.core}
        else:
            # The QP sees its holdings in core units.
            w_core = w_pre / self.scale_now
            f = self.world.formation(eom, w_core, nav, at)
            core, log = optimize.relax_book(f, self.world.p, self.world.step)
            if core is None:
                raise RuntimeError(f"{eom:%Y-%m-%d}: no compliant book: {log.get('status')}")
        self.scale_now = scale(core, self.ov)
        self.core_now, self.pending = core, (d, eom)
        keep = ("status", "support", "support_fallback", "pred_vol_ann", "ladder_gross",
                "live_names", "objective")  # fmt: skip
        self.logs.append({"eom": f"{eom:%Y-%m-%d}", "nav": nav, "scale": self.scale_now,
                          "gross_core": float(core.abs().sum()), "names": int(len(core)),
                          **{k: log.get(k) for k in keep}})  # fmt: skip
        head = self.heading()
        self.targets.append(
            pd.DataFrame(
                {
                    "eom": eom,
                    "T": d,
                    "permno": core.index,
                    "core": core.to_numpy(),
                    "target": head.reindex(core.index).to_numpy(),
                }
            )
        )

    # Yesterday's closing weights from the book's recorded positions.
    def last_close(self, book) -> tuple[dict, float | None]:
        rows = book.positions[self.seen :]
        self.seen = len(book.positions)
        if not book.rows:
            return {}, None
        last = book.rows[-1]
        return {p: v for day, p, v in rows if day == last["date"]}, last["nav"]

    # Names to close now whatever the pace: drift and cap rules.
    def forced(self, d, book, closing: dict, last_nav, nav: float) -> dict:
        out = {}
        if last_nav:
            for p, v in closing.items():
                if v / last_nav > self.x.trim_at:
                    out[p] = min(self.wanted.get(p, np.inf), self.x.trim_to * nav)
        prev = self.days[self.days.searchsorted(d) - 1]
        for p, v in book.values.items():
            if v < 0 and not book.m.cap_at(p, prev) >= self.x.short_hold_musd:
                out[p] = 0.0
        return out

    # The hook: grow the plan, form, start, guard, then today's orders.
    def __call__(self, i: int, d, book, order):
        self.forming = False
        m, values = book.m, book.values
        nav = book.cash + sum(values.values())
        closing, last_nav = self.last_close(book)
        # The working plan holds shares: its dollars move with the price.
        for p in self.wanted:
            j = m.col.get(p)
            r = m.ret[i, j] if j is not None else np.nan
            self.wanted[p] *= 1 + (r if np.isfinite(r) else 0.0)
        total = values
        values = dict(total)
        started = False
        if self.pending is not None and d > self.pending[0]:
            self.formed, self.pending = self.pending[0], None
            self.start(values, nav)
            self.forming = started = True
        if d in self.by_signal:
            eom, at = self.by_signal[d]
            self.form(eom, d, dict(values), nav, at)
        gross = guard_gross(self.x.lag_guard, total, nav, closing, last_nav)
        if not started and gross > self.x.gross_guard:
            base = self.wanted if self.left > 0 else dict(values)
            head = sum(abs(v) for v in base.values()) / nav
            s = min(1.0, self.x.gross_trim_to / head) if head > 0 else 1.0
            self.wanted = {p: v * s for p, v in base.items()}
            self.left = max(self.left, 1)
        must = self.forced(d, book, closing, last_nav, nav)
        # On a formation's first close, shorts under the floor close whole.
        if started:
            for p, v in total.items():
                if v < 0 and not m.cap_at(p, self.formed) >= config.HARD["short_floor_musd"]:
                    must[p] = 0.0
        values = dict(total)
        steps = self.children(d, values, must)
        if self.left > 0:
            self.left -= 1
        if not steps:
            return None
        names = set(total) | set(steps)
        w = {p: (total.get(p, 0.0) + steps.get(p, 0.0)) / book.nav_before for p in names}
        return (self.formed or d, pd.Series(w, dtype=float))

    # Today's child orders: an equal share of what is left, <= 10% ADV.
    def children(self, d, values: dict, must: dict) -> dict:
        steps = {}
        if self.left > 0:
            names = list(self.wanted)
            adv = self.law.known("adv", d, names)
            for p in names:
                change = self.wanted[p] - values.get(p, 0.0)
                room = self.x.participation * adv.get(p, np.nan)
                if abs(change) < 1.0 or not np.isfinite(room) or room <= 0:
                    continue
                steps[p] = float(np.clip(change / self.left, -room, room))
        for p, goal in must.items():
            self.wanted[p] = goal
            steps[p] = goal - values.get(p, 0.0)
        return {p: s for p, s in steps.items() if abs(s) >= 1.0}

    # Every formation's core and target weights as one frame.
    def target_frame(self) -> pd.DataFrame:
        return pd.concat(self.targets, ignore_index=True) if self.targets else pd.DataFrame()
