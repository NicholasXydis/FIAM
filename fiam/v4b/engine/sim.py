# Daily $1bn book: seen at t, traded at close t+1, earns t+1 to t+2.

from dataclasses import dataclass

import numpy as np
import pandas as pd

# SEC Section 31 fee on sales, $27.80 a million (stated, not fitted).
SEC_RATE = 27.80e-6

# Sessions in a year, for daily accruals of yearly rates.
YEAR = 252


# The simulator's dials; every cost line is one of these.
@dataclass(frozen=True)
class Setup:
    nav0: float = 1e9
    participation: float = 0.10
    spill_days: int = 4
    impact_y: float = 1.0
    commission: float = 0.00005
    sec_rate: float = SEC_RATE
    rebate_haircut: float = 0.0
    debit_spread: float = 0.0
    stub_days: int = 5
    stub_long: float = -0.30
    # Nautilus backend fee lines: "ibkr" (engine/fees.py, dated schedule) or
    # "flat" (commission + sec_rate per dollar, the legacy form tests use).
    fee_schedule: str = "ibkr"
    # Nautilus backend: spread each order evenly over the remaining
    # execution days (True) or fill to the participation cap at once.
    paced: bool = True


# Inputs as session x permno frames, all on one calendar.
@dataclass
class Market:
    returns: pd.DataFrame
    adv: pd.DataFrame
    sigma: pd.DataFrame
    half_spread: pd.DataFrame | float
    borrow: pd.DataFrame | float
    rf: pd.Series


# The session after each signal day; fails off the calendar.
def execution_days(signals, sessions: pd.DatetimeIndex) -> dict:
    pos = sessions.get_indexer(pd.DatetimeIndex(list(signals)))
    if (pos < 0).any() or (pos + 1 >= len(sessions)).any():
        raise ValueError("a signal day is not a session with a next session")
    return {sessions[i + 1]: s for i, s in zip(pos, signals)}


# A frame or scalar as an array over the run's permnos for one day.
def _row(x, k: int, n: int) -> np.ndarray:
    if isinstance(x, pd.DataFrame):
        return x.iloc[k].to_numpy(dtype=float)
    return np.full(n, float(x))


# Targets map signal session to weights or a builder(w_pre, nav). Builders
# run at the signal close, using actual fills and compounded NAV only.
def run(targets: dict, mkt: Market, setup: Setup = Setup()):
    sessions = pd.DatetimeIndex(mkt.returns.index)
    permnos = mkt.returns.columns
    n = len(permnos)
    execs = execution_days(sorted(targets), sessions)
    first = sessions.get_loc(min(execs)) - 1
    R = mkt.returns.to_numpy(dtype=float)
    # Trades at close k use ADV and vol known through k-1.
    adv = mkt.adv.shift(1).to_numpy(dtype=float)
    sig = mkt.sigma.shift(1).to_numpy(dtype=float)
    rf = mkt.rf.reindex(sessions).fillna(0.0).to_numpy(dtype=float)
    h = np.zeros(n)
    cash = setup.nav0
    order = np.zeros(n)
    left = 0
    missing = np.zeros(n, dtype=int)
    ledger, books = [], []
    nav_prev = setup.nav0

    def resolve(day, nav):
        target = targets[day]
        if callable(target):
            held = pd.Series(h / nav, index=permnos)
            target = target(held[held.abs() > 1e-12], nav)
        return target.reindex(permnos).fillna(0.0).to_numpy(dtype=float)

    pending = resolve(sessions[first], nav_prev)
    ledger.append(_line(sessions[first], setup.nav0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    for k in range(first + 1, len(sessions)):
        day = sessions[k]
        r = R[k]
        # A reported total loss is not proof that a short liability can be
        # settled at zero. Freeze it at its last mark until a tradable cover.
        seen = np.isfinite(r) & ~((h < 0) & (r <= -1.0))
        missing = np.where(seen, 0, missing + 1)
        pnl = float(h[seen] @ r[seen])
        h = np.where(seen, h * (1 + np.where(seen, r, 0.0)), h)
        stub = 0.0
        # A long missing stub_days is marked down and sold.
        # Unquoted shorts remain liabilities and continue paying borrow.
        # A missing quote never proves that a cover can be executed.
        gone = (missing >= setup.stub_days) & (h > 0)
        synthetic_exit = np.where(gone, -h, 0.0)
        if gone.any():
            longs = gone & (h > 0)
            stub = float(h[longs].sum() * setup.stub_long)
            cash += float(h[gone].sum()) + stub
            pnl += stub
            h[gone] = 0.0
            order[gone] = 0.0
        short_value = float(-h[h < 0].sum())
        b = _row(mkt.borrow, k, n)
        borrow = float((-h[h < 0]) @ b[h < 0]) / YEAR
        cash_rate = rf[k] if cash >= 0 else rf[k] + setup.debit_spread / YEAR
        interest = cash * cash_rate - short_value * setup.rebate_haircut / YEAR
        cash += interest - borrow
        nav = cash + float(h.sum())
        pre = h.copy()
        rebalance = day in execs
        if rebalance:
            order = pending * nav - h
            left = setup.spill_days + 1
        fill = np.zeros(n)
        if left > 0:
            cap = setup.participation * np.nan_to_num(adv[k], nan=0.0)
            can = seen & (cap > 0)
            fill = np.where(can, np.sign(order) * np.minimum(np.abs(order), cap), 0.0)
            order = order - fill
            left -= 1
            if left == 0:
                order[:] = 0.0
        traded = np.abs(fill)
        s = _row(mkt.half_spread, k - 1, n)
        spread = float(traded @ np.nan_to_num(s, nan=0.0))
        ok = traded > 0
        impact = float(
            setup.impact_y
            * (
                np.nan_to_num(sig[k][ok], nan=0.02) * traded[ok] * np.sqrt(traded[ok] / adv[k][ok])
            ).sum()
        )
        fees = float(traded.sum() * setup.commission + (-fill[fill < 0]).sum() * setup.sec_rate)
        h = h + fill
        cash -= float(fill.sum()) + spread + impact + fees
        nav_post = cash + float(h.sum())
        ret = nav_post / nav_prev - 1
        turnover = 0.5 * traded.sum() / nav
        ledger.append(
            _line(day, nav_post, ret, pnl, interest, spread, impact, fees, borrow, turnover, stub)
        )
        live = (h != 0) | (pre != 0) | (synthetic_exit != 0)
        if live.any():
            books.append(
                pd.DataFrame(
                    {
                        "date": day,
                        "permno": permnos[live],
                        "w": h[live] / nav_post,
                        "w_pre": pre[live] / nav,
                        "rebalance": rebalance,
                        "trade_dollars": fill[live],
                        "synthetic_exit_dollars": synthetic_exit[live],
                        "adv_dollars": adv[k][live],
                        "unfilled_dollars": order[live],
                        "adv_days": np.abs(h[live])
                        / np.where(adv[k][live] > 0, adv[k][live], np.nan),
                    }
                )
            )
        nav_prev = nav_post
        if day in targets:
            pending = resolve(day, nav_post)
    led = pd.DataFrame(ledger).set_index("date")
    pos = pd.concat(books, ignore_index=True) if books else pd.DataFrame()
    return led, pos


# One ledger row; costs are positive numbers in dollars.
def _line(day, nav, ret, pnl, interest, spread, impact, fees, borrow, turnover, stub) -> dict:
    return dict(
        date=day,
        nav=nav,
        ret=ret,
        pnl=pnl,
        interest=interest,
        spread=spread,
        impact=impact,
        fees=fees,
        borrow=borrow,
        turnover=turnover,
        stub=stub,
    )
