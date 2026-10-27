# The engine's per-close hook: the four-close spill and the daily rules.

import copy

import cvxpy as cp
import numpy as np
import pandas as pd

from fiam.vfinal import betas, data, universe
from fiam.vfinal.construct import book as bookmod
from fiam.vfinal.construct import optimizer
from fiam.vfinal.signals import short_interest

# Spill: 10% of ADV a close, the trade day and four more.
SPILL_ADV, CLOSES = optimizer.SPILL_ADV, optimizer.SPILL_CLOSES
# Rounds of the net and beta scale-backs, each only shrinking fills.
BAND_ROUNDS = 20
# Daily fixes: net band, name band, drift and beta triggers.
NET_BAND, NAMES_LOW, NAMES_HIGH, DRIFT, BETA_BAND = 0.45, 210, 490, 1.2, 0.10
# The trigger beta: Welch on 126 sessions, 63-day half-life (checklist).
BETA_DAYS, BETA_HALF = betas.TRIGGER_DAYS, betas.TRIGGER_HALF
# After a re-hedge the beta trigger rests 5 sessions.
REST = 5
# The re-hedge's weight on any beta left over against its trades.
HEDGE_WEIGHT = 100.0
# Squeeze watch: 5-day rises, short interest, borrow jumps, volume.
RISE_HALF, RISE_ALL, RISE_DAYS, SHORT_RATIO, VOLUME = 0.30, 0.50, 5, 0.20, 5.0
# A held short under the PDF's floor ($ millions) is covered in full.
FLOOR_MUSD = universe.HOLD_MUSD
# Brake (checklist): 5% under the peak, gross to 0.625 until half back.
BRAKE_FALL, BRAKE_GROSS, BRAKE_BACK = 0.05, 0.625, 0.5
# Overlays: a flagged long or short is halved, shrink-only.
OVERLAY_CUT = 0.5
# Triggers seen at a decision close still act on the formation's day.
KEPT = ("short_floor", "squeeze_cover", "overlay_long", "overlay_short", "desk")
# Covers and trims end a name's plan; book-wide fixes count toward it.
ENDS = ("short_floor", "squeeze_cover", "overlay_long", "overlay_short", "cap_trim",
        "names_low", "names_high", "desk")  # fmt: skip
# A weight that changes by less than this has not moved (solver noise).
MOVED = 1e-6
# What a card, the loss trigger and the cost gate read from a frame.
KEEP = ("size", "value", "momentum", "quality", "welch", "liquidity", "crowding", "sigma_d",
        "prc", "half_spread", "adv_cost")  # fmt: skip
# The confidence map's multipliers as terciles, 1 the most confident.
TERCILE = {1.0: 1, 0.9: 2, 0.75: 3}


# A formation's facts for the hook: target, trades, caps, ADV, betas.
class Formation:
    # Taken from the optimiser's frame at the formation.
    def __init__(self, formed, target: pd.Series, x: pd.DataFrame, cap: float, nav: float,
                 prev: pd.Series | None = None):  # fmt: skip
        self.formed, self.target, self.C, self.nav = pd.Timestamp(formed), target, cap, nav
        self.gross = float(target.abs().sum())
        # A name outside the frame takes the 5th-percentile ADV.
        self.adv = x["adv_cost"]
        self.floor_adv = float(self.adv.quantile(0.05))
        self.caps = self.cap_of(target)
        self.betas = x[["welch", "dimson"]]
        held = pd.Series(dtype=float) if prev is None else prev
        names = target.index.union(held.index)
        # The planned trade at T; the spill works it off.
        self.remaining = target.reindex(names).fillna(0.0) - held.reindex(names).fillna(0.0)

    # Each name's cap by its side, from its ADV or the floor ADV.
    def cap_of(self, w: pd.Series) -> pd.Series:
        adv = self.adv.reindex(w.index).fillna(self.floor_adv)
        long_cap, short_cap = optimizer.caps(adv, self.nav)
        return pd.Series(np.where(w > 0, long_cap, short_cap), index=w.index)


# The hook the engine calls each close, before any trade.
class Execution:
    # Formations by trade day; daily rules and switches between them.
    def __init__(self, formations: dict, squeeze=None, planner=None, trigger=None,
                 overlays=None, brake: bool = False):  # fmt: skip
        self.by_day, self.left, self.live = formations, 0, None
        self.planner, self.squeeze, self.trigger = planner, squeeze, trigger
        self.overlays, self.brake = overlays or {}, brake
        self.pending: list = []
        self.log: list = []
        self.halved, self.full, self.flagged = set(), set(), set()
        self.rest, self.forming = 0, False
        self.peak, self.trough, self.braking = 0.0, 0.0, False

    # Today's order: the spill's fills, then yesterday's triggers.
    def __call__(self, i, d, book, order):
        nav = book.nav_before
        cur = pd.Series(book.values, dtype=float) / nav
        self.forming = d in self.by_day
        # A new formation supersedes the triggers its target already saw.
        if self.forming:
            self.live, self.left = self.by_day[d], CLOSES
            self.halved, self.full, self.flagged = set(), set(), set()
            self.pending = [(k, a) for k, a in self.pending if k in KEPT]
        want = cur.copy()
        if self.live is not None and self.left > 0:
            want = self.spill(cur, nav)
        want = self.act(want)
        # At a decision close the plan starts from the book after its trades.
        if self.planner is not None and d in self.planner.decision:
            self.plan(d, book, want)
        self.watch(i, d, book, want)
        if want.equals(cur):
            return None
        return (self.live.formed if self.live is not None else d, want[want.abs() > 1e-9])

    # The next trade day's formation, planned from today's final book.
    def plan(self, d, book, want: pd.Series) -> None:
        nav = book.cash + sum(book.values.values())
        held = want[want.abs() > 1e-12] * book.nav_before / nav
        target, frame, cap, nav_t, planned, prev = self.planner.plan(d, book, held)
        day = data.shift([d], 1).iloc[0]
        formed = self.planner.decision[d] if d in self.planner.month_ends else d
        self.by_day[day] = Formation(formed, target, frame, cap, nav_t, prev)
        self.planner.hooks.add(day, frame, planned)

    # Yesterday's triggers on today's book, each name's plan kept in step.
    def act(self, want: pd.Series) -> pd.Series:
        for kind, action in self.pending:
            after = action(want)
            if self.live is not None:
                names = after.index.union(want.index)
                move = after.reindex(names).fillna(0.0) - want.reindex(names).fillna(0.0)
                moved = move.index[move.abs() > MOVED]
                f = self.live
                f.remaining = f.remaining.reindex(f.remaining.index.union(moved)).fillna(0.0)
                # A cover or trim ends the name's plan, so it is not rebought.
                if kind in ENDS:
                    f.target = f.target.reindex(f.target.index.union(moved)).fillna(0.0)
                    f.target.loc[moved] = after.reindex(moved).fillna(0.0)
                    f.remaining.loc[moved] = 0.0
                # A book-wide fix counts toward each name's remaining plan.
                else:
                    f.remaining.loc[moved] -= move[moved]
            want = after
        self.pending = []
        return want if self.live is None else self.braked(want)

    # One close of the spill: each planned trade at most 10% of its ADV.
    def spill(self, cur: pd.Series, nav: float) -> pd.Series:
        f = self.live
        names = cur.index.union(f.remaining.index)
        held = cur.reindex(names).fillna(0.0)
        room = SPILL_ADV * f.adv.reindex(names).fillna(f.floor_adv) / nav
        # Exits go exactly to 0; every other name works off its plan.
        out = f.target.reindex(names).fillna(0.0) == 0
        step = f.remaining.reindex(names).fillna(0.0).where(~out, -held).clip(-room, room)
        # A plan never crosses zero: past it, the name only closes.
        cross = (held != 0) & (held * (held + step) < 0)
        step[cross] = -held[cross]
        for _ in range(3):
            step = counted(step, held, f.target.reindex(names))
            step = bands(step, held, f.betas["welch"].reindex(names))
            alive = int(((held + step).abs() > 1e-9).sum())
            if NAMES_LOW <= alive <= NAMES_HIGH or alive == int((held != 0).sum()):
                break
        f.remaining = f.remaining.reindex(names).fillna(0.0) - step.where(~out, 0.0)
        f.remaining[out & ((held + step).abs() <= 1e-9)] = 0.0
        self.left -= 1
        if self.left == 0 or float(f.remaining.abs().max()) < 1e-6:
            self.left = 0
        return held + step

    # The brake's gross: 0.625 of the formation's while it is on.
    def braked(self, want: pd.Series) -> pd.Series:
        gross, cap = float(want.abs().sum()), BRAKE_GROSS * self.live.gross
        if self.braking and gross > cap + 1e-9:
            return want * cap / gross
        return want

    # Today's state seen at the close: the fixes act at the next close.
    def watch(self, i, d, book, want: pd.Series) -> None:
        if self.live is None:
            return
        f = self.live
        gross = float(want.abs().sum())
        # Gross above the crash-day cap: back to the formation gross.
        if gross > f.C:
            self.queue(d, "gross_trim", gross, lambda w, g=f.gross: w * g / float(w.abs().sum()))
        # A name drifted past 1.2 times its cap: back to its cap.
        caps = f.cap_of(want)
        over = want.index[(want.abs() > DRIFT * caps).to_numpy()]
        if len(over):
            self.queue(d, "cap_trim", len(over), lambda w, n=over, c=caps: w.where(
                ~w.index.isin(n), np.sign(w) * c.reindex(w.index)))  # fmt: skip
        names = int((want.abs() > 1e-9).sum())
        # Under 210 names: the formation's largest unheld targets come back.
        if names < NAMES_LOW:
            gone = f.target[(f.target != 0) & ~f.target.index.isin(want.index[want.abs() > 1e-9])]
            back = gone.abs().nlargest(NAMES_LOW - names).index
            self.queue(d, "names_low", names, lambda w, b=back, t=f.target: restore(w, b, t))
        # Over 490 names: the smallest positions go.
        if names > NAMES_HIGH:
            small = want[want.abs() > 1e-9].abs().nsmallest(names - NAMES_HIGH).index
            self.queue(d, "names_high", names, lambda w, n=small: w.where(~w.index.isin(n), 0.0))
        net = float(want.sum())
        # Net outside +/-45%: the heavier side scaled back inside.
        if abs(net) > NET_BAND:
            self.queue(d, "net_fix", net, fix_net)
        # A short under $500m, or with no cap, is covered at the next close.
        shorts = want.index[want < 0]
        low = [p for p in shorts if not book.m.cap_at(int(p), d) >= FLOOR_MUSD]
        if low:
            self.queue(d, "short_floor", len(low), lambda w, n=low: w.where(~w.index.isin(n), 0.0))
        self.hedge(d, f, want)
        self.squeezes(i, d, book, shorts)
        self.events(d, want)
        self.drawdown(d, book)

    # One trigger: logged now, its action queued for the next close.
    def queue(self, d, kind: str, value, action) -> None:
        self.pending.append((kind, action))
        self.log.append((d, kind, value))

    # The holdings' ex-ante trigger beta past 0.10: re-hedge, then rest.
    def hedge(self, d, f: Formation, want: pd.Series) -> None:
        self.rest = max(0, self.rest - 1)
        if self.trigger is None or self.rest > 0:
            return
        held = want[want.abs() > 1e-9]
        b = self.trigger(d, held.index)
        beta = float((held * b.reindex(held.index).fillna(b.median())).sum())
        if abs(beta) > BETA_BAND:
            loads = f.betas.reindex(held.index).assign(trigger=b.reindex(held.index))
            self.queue(d, "beta_rehedge", beta,
                       lambda w, ld=loads: rehedge(w, ld, f.cap_of(w), f.adv, f.nav))  # fmt: skip
            # The trade close and 5 more pass before the trigger looks again.
            self.rest = REST + 1

    # The squeeze watch: half once, then all once if a rise passes 50%.
    def squeezes(self, i, d, book, shorts) -> None:
        if self.squeeze is None:
            return
        half, whole = self.squeeze(i, d, book, shorts)
        half = [p for p in half if p not in self.halved and p not in self.full]
        whole = [p for p in whole if p not in self.full]
        self.halved |= set(half)
        self.full |= set(whole)
        if len(half) or len(whole):
            self.queue(d, "squeeze_cover", len(half) + len(whole),
                       lambda w, h=half, a=whole: cover(w, h, a))  # fmt: skip

    # Overlays (switched on by their tests): a flagged name halved once.
    def events(self, d, want: pd.Series) -> None:
        for side, days in self.overlays.items():
            held = want.index[(want > 0) if side == "long" else (want < 0)]
            today = days.get(pd.Timestamp(d), set()) - self.flagged
            hit = [p for p in held if p in today]
            if hit:
                self.flagged |= set(hit)
                self.queue(d, f"overlay_{side}", len(hit),
                           lambda w, n=hit: w.where(~w.index.isin(n), w * OVERLAY_CUT))  # fmt: skip

    # The brake (on by its test): 5% under the peak, off when half is back.
    def drawdown(self, d, book) -> None:
        if not self.brake:
            return
        nav = float(book.cash + sum(book.values.values()))
        self.peak = max(self.peak, nav)
        if not self.braking and nav <= self.peak * (1 - BRAKE_FALL):
            self.braking, self.trough = True, nav
            self.log.append((d, "brake_on", nav / self.peak - 1))
        elif self.braking:
            self.trough = min(self.trough, nav)
            if nav >= self.trough + BRAKE_BACK * (self.peak - self.trough):
                # Released: the peak restarts here, so it cannot flicker back.
                self.braking, self.peak = False, nav
                self.queue(d, "brake_off", nav,
                           lambda w, g=self.live.gross: w * g / float(w.abs().sum()))  # fmt: skip


# Entries wait above 490 names, exits below 210, the smallest first.
def counted(step: pd.Series, held: pd.Series, target: pd.Series) -> pd.Series:
    step = step.copy()
    alive = (held + step).abs() > 1e-9
    entering = alive & (held == 0)
    if int(alive.sum()) > NAMES_HIGH:
        late = target[entering].abs().sort_values().index[: int(alive.sum()) - NAMES_HIGH]
        step[late] = 0.0
    alive = (held + step).abs() > 1e-9
    if int(alive.sum()) < NAMES_LOW:
        gone = held.index[(held != 0) & ~alive]
        step[held[gone].abs().nsmallest(NAMES_LOW - int(alive.sum())).index] = 0.0
    return step


# Net within 45% and Welch beta within 0.10: fills scaled back.
def bands(step: pd.Series, held: pd.Series, beta: pd.Series) -> pd.Series:
    beta = beta.fillna(beta.median()).fillna(1.0)
    ones = pd.Series(1.0, index=step.index)
    for _ in range(BAND_ROUNDS):
        step = shrink(step, held, beta, BETA_BAND)
        step = shrink(step, held, ones, NET_BAND)
    # Both bands at once, if the rounds leave one out: one common cut.
    if within(held + step, beta) or not within(held, beta):
        return step
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if within(held + mid * step, beta) else (lo, mid)
    return lo * step


# Whether a book's net and Welch beta are inside their bands.
def within(w: pd.Series, beta: pd.Series) -> bool:
    return abs(float(w.sum())) <= NET_BAND + 1e-9 and abs(float(w @ beta)) <= BETA_BAND + 1e-9


# Names under 210: these formation targets set back at their weights.
def restore(w: pd.Series, names, target: pd.Series) -> pd.Series:
    w = w.copy()
    for p in names:
        w.loc[p] = target[p]
    return w


# Net back inside +/-45% by scaling the heavier side.
def fix_net(w: pd.Series) -> pd.Series:
    longs, shorts = w[w > 0].sum(), -w[w < 0].sum()
    if longs - shorts > NET_BAND:
        return w.where(w < 0, w * (shorts + NET_BAND) / longs)
    if shorts - longs > NET_BAND:
        return w.where(w > 0, w * (longs + NET_BAND) / shorts)
    return w


# Squeeze covers: half of each name in one list, all of the other.
def cover(w: pd.Series, half, whole) -> pd.Series:
    w = w.copy()
    w[w.index.isin(half)] *= 0.5
    w[w.index.isin(whole)] = 0.0
    return w


# The squeeze watch from data through t, on held shorts.
class SqueezeWatch:
    # Daily returns, short ratios and dollar volume read once.
    def __init__(self, permnos, start, end):
        ids = sorted(set(int(p) for p in permnos))
        days = data.sessions(pd.Timestamp(start) - pd.Timedelta(days=200), end)
        rows = data.table("crsp_daily", ["ret", "prc", "vol", "delflg"],
                          where={"permno": set(ids), "date": (days[0], days[-1])})  # fmt: skip
        rows = rows[(rows["delflg"] != "Y") & (rows["date"] <= data.CRSP_END)]
        self.ret = data.matrix(rows, "ret", days, ids)
        # After 2025 the dsf's returns; no volume, so no volume trigger.
        if days[-1] > data.CRSP_END:
            after = data.CRSP_END + pd.Timedelta(days=1)
            late = data.table("dsf", ["ret"], where={"permno": set(ids), "date": (after, days[-1])})
            self.ret = self.ret.combine_first(data.matrix(late, "ret", days, ids))
        self.dollars = data.matrix(rows.assign(dv=rows["prc"].abs() * rows["vol"]), "dv", days, ids)
        # Each publication's ratio over the shares on its settlement day.
        si = short_interest.history(ids).rename(columns={"value": "ratio"})
        si = si.dropna(subset=["ratio"]).sort_values(["permno", "first_close"])
        si["before"] = si.groupby("permno")["ratio"].shift(1)
        self.si = si[["permno", "first_close", "ratio", "before"]]

    # Names to cover half and in full, from data through day d.
    def __call__(self, i, d, book, shorts) -> tuple:
        if len(shorts) == 0:
            return [], []
        r = self.ret.loc[:d, self.ret.columns.intersection(shorts)].tail(RISE_DAYS)
        rise = (1 + r.fillna(0.0)).prod() - 1
        whole = list(rise.index[rise > RISE_ALL])
        half = set(rise.index[(rise > RISE_HALF) & (rise <= RISE_ALL)])
        dv = self.dollars.loc[:d, self.dollars.columns.intersection(shorts)]
        spike = dv.iloc[-1] / dv.iloc[-127:-1].mean()
        # A volume spike counts only on a rise.
        half |= set(spike.index[(spike > VOLUME) & (rise.reindex(spike.index) > 0)])
        # A report public at this close: crossed 20%, or the tier rose two.
        new = self.si[(self.si["first_close"] == d) & self.si["permno"].isin(shorts)]
        crossed = (new["before"] < SHORT_RATIO) & (new["ratio"] >= SHORT_RATIO)
        jumped = level(new["ratio"]) - level(new["before"].fillna(0.0)) >= 2
        half |= set(new.loc[crossed | jumped, "permno"])
        return sorted(half - set(whole)), whole


# A short ratio's borrow tier as a level: 0 cheapest to 3 dearest.
def level(ratio: pd.Series) -> pd.Series:
    return (ratio >= 0.05).astype(int) + (ratio >= 0.10) + (ratio >= 0.20)


# Each stock's 126-session Welch beta through day d.
class TriggerBeta:
    # Total returns, the market and the bill, over the run.
    def __init__(self, returns: pd.DataFrame, late: pd.DataFrame | None = None):
        self.returns, self.late = returns, pd.DataFrame() if late is None else late
        self.market = data.market_daily(returns.index)

    # These names' betas on the 126 sessions to d, bills public by d.
    def __call__(self, d, names) -> pd.Series:
        days = self.returns.index[self.returns.index <= pd.Timestamp(d)][-BETA_DAYS:]
        rf = data.rf_daily(days, by=d)
        stock = self.returns.reindex(index=days, columns=list(names))
        # In 2026 an open month has no δ yet: its days stay raw.
        d = pd.Timestamp(d)
        if len(self.late) and d > data.CRSP_END:
            month = days[days.to_period("M") == d.to_period("M")]
            if d != data.eom_session([d + pd.offsets.MonthEnd(0)]).iloc[0]:
                stock.loc[month] = self.late.reindex(index=month, columns=stock.columns)
        stock = stock.sub(rf, axis=0)
        market = self.market.reindex(days) - rf
        keep = market.notna().to_numpy()
        return betas.welch(stock[keep], market[keep], BETA_HALF)


# Fills pushing the book's exposure past its band are scaled back.
def shrink(step: pd.Series, held: pd.Series, load: pd.Series, band: float) -> pd.Series:
    exposure = float((held + step) @ load)
    push = (np.sign(exposure) * step * load).clip(lower=0.0)
    if abs(exposure) <= band or float(push.sum()) == 0:
        return step
    cut = max(0.0, 1 - (abs(exposure) - band) / float(push.sum()))
    return step.where(push == 0, step * cut)


# The least trade toward zero betas: sides, gross, net, 10% ADV kept.
def rehedge(w: pd.Series, loads: pd.DataFrame, caps: pd.Series, adv: pd.Series, nav: float):
    held = w[w != 0]
    b = loads.reindex(held.index)
    b = b.fillna(b.median()).fillna(1.0).to_numpy()
    h = held.to_numpy()
    room = SPILL_ADV * adv.reindex(held.index).fillna(adv.quantile(0.05)).to_numpy() / nav
    cap = np.maximum(caps.reindex(held.index).fillna(caps.median()).to_numpy(), np.abs(h))
    new = cp.Variable(len(held))
    side = np.sign(h)
    cons = [cp.multiply(side, new) >= 0, cp.abs(new) <= cap, cp.abs(new - h) <= room,
            side @ new == float(np.abs(h).sum()), cp.sum(new) == float(h.sum())]  # fmt: skip
    leftover = cp.sum(cp.abs(b.T @ new))
    problem = cp.Problem(cp.Minimize(cp.sum(cp.abs(new - h)) + HEDGE_WEIGHT * leftover), cons)
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.error.SolverError:
        return w
    if new.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
        return w
    return w.where(w == 0, pd.Series(new.value, index=held.index).reindex(w.index))


# The hook that keeps each formation and its frame as first made.
class Recording(Execution):
    # As the daily hook, with copies kept for the desk's replays.
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.made: dict = {}
        self.kept: dict = {}

    # The plan, then its formation copied before any close moves it.
    def plan(self, d, book, want) -> None:
        super().plan(d, book, want)
        day = max(self.by_day)
        self.made[day] = copy.deepcopy(self.by_day[day])
        eom = self.planner.decision[d]
        x, alpha, _, _, spec = self.planner.frames[eom]
        conf = bookmod.confidence(self.planner.ctx.f, eom).reindex(x.index).fillna(1.0)
        frame = x[[c for c in KEEP if c in x]].assign(alpha=alpha, spec=spec.reindex(x.index))
        self.kept[day] = frame.assign(confidence_tercile=conf.map(TERCILE).fillna(2).astype(int))
