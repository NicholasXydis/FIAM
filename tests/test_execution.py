# Step 7's execution, screens and exam rules on synthetic data.

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import data
from fiam.v4.construct import book, crowding, exam, execution, screens

DAY = pd.Timestamp


# A formation of n names with equal targets and ample liquidity.
def formation(n=100, gross=1.6, adv=1e9):
    ids = list(range(1, n + 1))
    side = np.where(np.arange(n) < n // 2, 1.0, -1.0)
    target = pd.Series(side * gross / n, index=ids)
    x = pd.DataFrame({"adv_cost": adv, "welch": 1.0, "dimson": 1.0}, index=ids)
    return execution.Formation(DAY("2019-01-31"), target, x, 1.7678, 1e9)


# A minimal book the hook can read: values, NAV, caps, past rows.
class FakeBook:
    # Dollar positions, a sizing NAV and every cap at $1bn.
    def __init__(self, values=None, nav=1e9):
        self.values, self.nav_before, self.rows = dict(values or {}), nav, []
        self.cash = nav - sum(self.values.values())
        self.m = type("M", (), {"cap_at": staticmethod(lambda p, d: 1e6)})()


# The spill moves each name at most 10% of its ADV a close, five closes.
def test_spill_caps_and_closes():
    f = formation(adv=1e8)
    hook = execution.Execution({DAY("2019-02-01"): f})
    b = FakeBook()
    _, w = hook(1, DAY("2019-02-01"), b, (f.formed, f.target))
    assert w.abs().max() == pytest.approx(0.1 * 1e8 / 1e9)
    assert hook.left == execution.CLOSES - 1
    for k in range(execution.CLOSES - 1):
        hook(2 + k, DAY("2019-02-04") + pd.Timedelta(days=k), b, None)
    assert hook.left == 0


# New names wait while the book would pass 490 names.
def test_new_names_wait_at_490():
    f = formation(n=600, gross=1.6)
    held = {p: 1e6 * (1 if p <= 300 else -1) for p in range(1, 451)}
    hook = execution.Execution({DAY("2019-02-01"): f})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(held), (f.formed, f.target))
    assert int((w.abs() > 1e-9).sum()) <= execution.NAMES_HIGH


# A day's fills that would push net past 45% are scaled back.
def test_spill_keeps_net_inside_45():
    ids = list(range(1, 11))
    target = pd.Series(0.15, index=ids)
    x = pd.DataFrame({"adv_cost": 1e12, "welch": 0.0, "dimson": 0.0}, index=ids)
    f = execution.Formation(DAY("2019-01-31"), target, x, 1.7678, 1e9)
    hook = execution.Execution({DAY("2019-02-01"): f})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(), (f.formed, f.target))
    assert w.sum() == pytest.approx(execution.NET_BAND)


# A trigger seen at one close acts only at the next one.
def test_triggers_act_at_the_next_close():
    f = formation(n=250, gross=1.6)
    hook = execution.Execution({DAY("2019-02-01"): f})
    big = {p: 8e6 * (1 if p <= 125 else -1) for p in range(1, 251)}
    hook.live, hook.left = f, 0
    out = hook(5, DAY("2019-02-08"), FakeBook(big), None)
    assert out is None and len(hook.pending) == 1
    _, w = hook(6, DAY("2019-02-11"), FakeBook(big), None)
    assert w.abs().sum() == pytest.approx(f.gross)


# Under 210 names the formation's largest unheld targets come back.
def test_names_under_210_restored():
    f = formation(n=250, gross=1.6)
    hook = execution.Execution({DAY("2019-02-01"): f})
    held = {p: 6e6 * (1 if p <= 100 else -1) for p in range(1, 206)}
    hook.live, hook.left = f, 0
    hook(5, DAY("2019-02-08"), FakeBook(held), None)
    _, w = hook(6, DAY("2019-02-11"), FakeBook(held), None)
    assert int((w.abs() > 1e-9).sum()) >= execution.NAMES_LOW


# Net back inside 45%, half and full squeeze covers, tier levels.
def test_fixes():
    w = pd.Series({1: 0.9, 2: -0.3})
    assert execution.fix_net(w).sum() == pytest.approx(execution.NET_BAND)
    c = execution.cover(pd.Series({1: -0.01, 2: -0.02, 3: 0.01}), [1], [2])
    assert c.tolist() == [-0.005, 0.0, 0.01]
    got = execution.level(pd.Series([0.0, 0.05, 0.10, 0.20])).tolist()
    assert got == [0, 1, 2, 3]


# The re-hedge reaches beta 0 on both betas, sides and gross kept.
def test_rehedge():
    rng = np.random.default_rng(0)
    ids = list(range(1, 41))
    w = pd.Series(np.where(np.arange(40) < 20, 0.02, -0.02), index=ids)
    b = pd.DataFrame({"welch": 1 + 0.3 * rng.standard_normal(40),
                      "dimson": 1 + 0.3 * rng.standard_normal(40)}, index=ids)  # fmt: skip
    new = execution.rehedge(w, b, pd.Series(0.05, index=ids), pd.Series(1e12, index=ids), 1e9)
    assert abs(b["welch"] @ new) < 1e-5 and abs(b["dimson"] @ new) < 1e-5
    assert (np.sign(new) == np.sign(w)).all() and new.abs().sum() == pytest.approx(0.8)
    assert new.sum() == pytest.approx(w.sum())
    # With no room to trade, the book is left as it is.
    still = execution.rehedge(w, b, pd.Series(0.05, index=ids), pd.Series(0.0, index=ids), 1e9)
    assert still.equals(w) or (still - w).abs().max() < 1e-9


# TAQ imbalance and the history cut-off use only earlier stock-days.
def test_imbalance_and_cuts():
    rows = pd.DataFrame({"BuyVol_LR": [3.0, 1.0, 0.0], "SellVol_LR": [1.0, 1.0, 0.0]})
    assert screens.imbalance(rows).tolist()[:2] == [0.5, 0.0]
    h = object.__new__(screens.History)
    h.skew = pd.DataFrame({"first_close": pd.to_datetime(["2019-01-02", "2019-01-03"]),
                           "Skew_OTM": [0.1, 9.0]})  # fmt: skip
    h.imb = pd.DataFrame({"first_close": pd.to_datetime(["2019-01-02"]), "imb": [0.2]})
    assert h.cuts(DAY("2019-01-03"))["skew"] == pytest.approx(0.1)


# Churn in values: a held name that only moved in price did not trade.
def test_churn_in_values():
    h = object.__new__(crowding.Holdings)
    q1, q2 = DAY("2019-03-31"), DAY("2019-06-30")
    h.versions = pd.DataFrame({"filer_cik": [1, 1], "period": [q1, q2],
                               "since": [DAY("2019-05-01"), DAY("2019-08-01")],
                               "version": [0, 1]})  # fmt: skip
    h.held = pd.DataFrame({"version": [0, 1], "permno": [7, 7], "value_usd": [100.0, 110.0],
                           "shares_sole": [10.0, 10.0]})  # fmt: skip
    h.returns = pd.DataFrame({"permno": [7, 7], "period": [q1, q2], "retx": [0.0, 0.1],
                              "shares_out": [100.0, 100.0]})  # fmt: skip
    got = crowding.crowding(h, DAY("2019-08-30"))
    assert got[7] == pytest.approx(0.1)


# The crash-day cap: 2 over 1 plus the largest two-day market rise.
def test_crash_cap(monkeypatch):
    days = pd.bdate_range("2019-01-01", periods=6)
    monkeypatch.setattr(data, "sessions", lambda a, b: days)
    monkeypatch.setattr(
        data, "market_daily", lambda d: pd.Series([0.0, 0.1, 0.1, 0.0, 0.0, 0.5][: len(d)], index=d)
    )
    assert book.crash_cap(days[-1]) == pytest.approx(2 / 1.21)


# The exam: the highest IR wins, a tie to the simpler; PLAN's reading.
def test_exam_rules():
    runs = {1: {"ir": 0.3}, 2: {"ir": 0.3}, 3: {"ir": 0.3}, 4: {"ir": 0.1}}
    assert exam.winner(runs) == 3
    # A design that broke a limit cannot win, however high its IR.
    runs[2] = {"ir": 0.9, "breach_days": 1}
    assert exam.winner(runs) == 3
    assert exam.winner({1: {"ir": 0.1, "breach_days": 2}}) is None
    assert exam.reading({"ir": 0.1, "sharpe": 0.5}) == "freeze and run"
    assert exam.reading({"ir": -0.1, "sharpe": 0.2}).startswith("freeze anyway")
    assert exam.reading({"ir": -0.3, "sharpe": -0.1}).startswith("stop")


# A cover during the spill cuts its target, so it is not rebought.
def test_cover_during_spill_is_not_rebought():
    f = formation(n=250, gross=1.6, adv=3e7)
    hook = execution.Execution({DAY("2019-02-01"): f})
    b = FakeBook()
    _, w = hook(1, DAY("2019-02-01"), b, (f.formed, f.target))
    assert hook.left > 1
    b.values = (w * 1e9).to_dict()
    hook.pending.append(("short_floor", lambda w: w.where(w.index != 200, 0.0)))
    for k, day in enumerate(["2019-02-04", "2019-02-05", "2019-02-06"]):
        out = hook(2 + k, DAY(day), b, None)
        w = w if out is None else out[1]
        assert w.get(200, 0.0) == 0.0
        b.values = (w * 1e9).to_dict()


# The exam reads the derived settings: margin d and lever A4's speed.
def test_exam_reads_derived_settings():
    keys = {"gross": 0.0, "ridge": 30.0, "risk_lambda": 0.5, "style_cap": 0.3,
            "sector_band": 0.02, "cost_budget": 0.001, "speed": 1.0, "norm": 1.0}  # fmt: skip
    s = {"settings": keys, "a4_rate": 0.4, "margin": 0.03}
    got = exam.derived(s)(None, None, 1.7678)
    assert got.gross == pytest.approx(1.7378) and got.speed == 0.4 and got.sector_band == 0.02
    two = exam.derived(s, names_max=exam.CONCENTRATED)(None, None, 1.7678)
    assert two.names_max == 275 and got.names_max == 480


# A day's fills that would push Welch beta past 0.10 are scaled back.
def test_spill_keeps_beta_inside_band():
    f = formation(n=100, gross=1.6, adv=1e12)
    f.betas = pd.DataFrame({"welch": np.where(f.target > 0, 1.5, 0.5), "dimson": 1.0},
                           index=f.target.index)  # fmt: skip
    hook = execution.Execution({DAY("2019-02-01"): f})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(), (f.formed, f.target))
    assert abs(float(w @ f.betas["welch"].reindex(w.index))) <= execution.BETA_BAND + 1e-6
    assert abs(float(w.sum())) <= execution.NET_BAND + 1e-9


# A new formation clears yesterday's triggers: its target saw them.
def test_new_formation_clears_triggers():
    f = formation(n=250, gross=1.6)
    hook = execution.Execution({DAY("2019-02-01"): f})
    hook.pending.append(("gross_trim", lambda w: w * 0.0))
    _, w = hook(1, DAY("2019-02-01"), FakeBook(), (f.formed, f.target))
    assert w.abs().sum() == pytest.approx(f.gross)


# A floor cover queued at the decision close survives the formation.
def test_floor_cover_survives_a_new_formation():
    f = formation(n=250, gross=1.6)
    hook = execution.Execution({DAY("2019-02-01"): f})
    held = (f.target * 1e9).to_dict()
    hook.pending.append(("short_floor", lambda w: w.where(w.index != 200, 0.0)))
    _, w = hook(1, DAY("2019-02-01"), FakeBook(held), (f.formed, f.target))
    assert w.get(200, 0.0) == 0.0


# No new long is crowded when the top 1% cut is zero.
def test_crowded_zero_cut(monkeypatch):
    ids = list(range(1, 201))
    flat = pd.Series(0.0, index=ids)
    monkeypatch.setattr(crowding, "crowding", lambda h, T: flat)
    assert not crowding.crowded(ids, None, DAY("2019-08-30")).any()
    some = pd.Series(np.arange(200) / 200.0, index=ids)
    monkeypatch.setattr(crowding, "crowding", lambda h, T: some)
    assert crowding.crowded(ids, None, DAY("2019-08-30")).sum() == 2


# The latest row per stock keeps one day's columns together.
def test_latest_row_is_one_day(monkeypatch):
    rows = pd.DataFrame({"permno": [7, 7], "date": pd.to_datetime(["2019-01-03", "2019-01-02"]),
                         "first_close": pd.to_datetime(["2019-01-04", "2019-01-03"]),
                         "BuyVol_LR": [5.0, 1.0], "SellVol_LR": [2.0, 9.0]})  # fmt: skip
    monkeypatch.setattr(screens.data, "table", lambda *a, **k: rows)
    got = screens.latest("taq_daily", ["BuyVol_LR", "SellVol_LR"], [7], DAY("2019-01-04"))
    assert got.loc[7, ["BuyVol_LR", "SellVol_LR"]].tolist() == [5.0, 2.0]


# The spill trades only the plan: a name at its target keeps its drift.
def test_spill_never_trades_drift():
    f = formation(n=250, gross=1.6)
    x = pd.DataFrame({"adv_cost": 1e9, "welch": 1.0, "dimson": 1.0}, index=f.target.index)
    f = execution.Formation(f.formed, f.target, x, 1.7678, 1e9, f.target)
    hook = execution.Execution({DAY("2019-02-01"): f})
    drifted = (f.target * 1.03 * 1e9).to_dict()
    assert hook(1, DAY("2019-02-01"), FakeBook(drifted), (f.formed, f.target)) is None


# Exits wait while the book would fall under 210 names.
def test_exits_wait_at_210():
    ids = list(range(1, 221))
    target = pd.Series(np.where(np.arange(220) < 110, 0.007, -0.007), index=ids)
    target.iloc[100:110] = 0.0
    target.iloc[210:220] = 0.0
    x = pd.DataFrame({"adv_cost": 1e12, "welch": 1.0, "dimson": 1.0}, index=ids)
    held = (target.where(target != 0, np.sign(np.arange(220) - 109.5) * -0.007) * 1e9).to_dict()
    f = execution.Formation(DAY("2019-01-31"), target, x, 1.7678, 1e9, pd.Series(held) / 1e9)
    hook = execution.Execution({DAY("2019-02-01"): f})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(held), (f.formed, f.target))
    assert int((w.abs() > 1e-9).sum()) == execution.NAMES_LOW


# A name outside the frame still has a cap, from the floor ADV.
def test_caps_outside_the_frame():
    f = formation(n=100)
    caps = f.cap_of(pd.Series({1: 0.01, 999: -0.01}))
    assert caps.notna().all() and caps[999] > 0


# Squeeze covers: half once, then all once; a repeat is ignored.
def test_squeeze_escalates_once():
    f = formation(n=250)
    seen = iter([([200], []), ([], [200]), ([200], [200])])
    hook = execution.Execution({}, squeeze=lambda i, d, b, s: next(seen))
    hook.live, hook.left, start = f, 0, f.target.copy()
    book = FakeBook((f.target * 1e9).to_dict())
    hook(1, DAY("2019-02-05"), book, None)
    _, w = hook(2, DAY("2019-02-06"), book, None)
    assert w[200] == pytest.approx(start[200] / 2)
    book = FakeBook((w * 1e9).to_dict())
    _, w = hook(3, DAY("2019-02-07"), book, None)
    assert w.get(200, 0.0) == 0.0 and not hook.pending


# The volume trigger counts only when the stock has risen (reading 11).
def test_volume_trigger_needs_a_rise():
    days = pd.bdate_range("2019-01-01", periods=140)
    w = object.__new__(execution.SqueezeWatch)
    w.ret = pd.DataFrame({7: 0.0, 8: 0.0}, index=days)
    w.ret.loc[days[-3:], 7], w.ret.loc[days[-3:], 8] = 0.01, -0.01
    w.dollars = pd.DataFrame({7: 1.0, 8: 1.0}, index=days)
    w.dollars.iloc[-1] = 10.0
    w.si = pd.DataFrame(columns=["permno", "first_close", "ratio", "before"])
    half, whole = w(1, days[-1], None, [7, 8])
    assert half == [7] and whole == []


# The holdings' trigger beta past 0.10: one re-hedge, then 5 days' rest.
def test_beta_trigger_rests():
    f = formation(n=250)
    hook = execution.Execution({}, trigger=lambda d, names: pd.Series(
        np.where(np.asarray(names) <= 125, 1.2, 0.8), index=names))  # fmt: skip
    hook.live, hook.left = f, 0
    book = FakeBook((f.target * 1e9).to_dict())
    hook(1, DAY("2019-02-05"), book, None)
    assert [k for _, k, _ in hook.log] == ["beta_rehedge"] and hook.rest == execution.REST + 1
    for k in range(execution.REST):
        hook.pending = []
        hook(2 + k, DAY("2019-02-06") + pd.Timedelta(days=k), book, None)
    assert [k for _, k, _ in hook.log].count("beta_rehedge") == 1
    hook.pending = []
    hook(9, DAY("2019-02-15"), book, None)
    assert [k for _, k, _ in hook.log].count("beta_rehedge") == 2


# A switched-on overlay halves a flagged long at the next close.
def test_overlay_halves_a_flagged_long():
    f = formation(n=250)
    hook = execution.Execution({}, overlays={"long": {DAY("2019-02-05"): {3}}})
    hook.live, hook.left, start = f, 0, f.target.copy()
    book = FakeBook((f.target * 1e9).to_dict())
    hook(1, DAY("2019-02-05"), book, None)
    _, w = hook(2, DAY("2019-02-06"), book, None)
    assert w[3] == pytest.approx(start[3] / 2)


# The brake: 5% under the peak cuts gross to 0.625; half back lifts it.
def test_brake():
    f = formation(n=250)
    hook = execution.Execution({}, brake=True)
    hook.live, hook.left = f, 0
    values = (f.target * 1e9).to_dict()
    hook(1, DAY("2019-02-05"), FakeBook(values, nav=1e9), None)
    # Today's NAV decides, not the sizing NAV of the close before.
    fell = FakeBook(values, nav=0.94e9)
    fell.nav_before = 1e9
    hook(2, DAY("2019-02-06"), fell, None)
    assert hook.braking
    _, w = hook(3, DAY("2019-02-07"), FakeBook(values, nav=0.94e9), None)
    assert w.abs().sum() == pytest.approx(execution.BRAKE_GROSS * f.gross)
    hook(4, DAY("2019-02-08"), FakeBook(values, nav=0.975e9), None)
    assert not hook.braking
    # Released, the peak restarts there, so a small dip does not flicker.
    hook(5, DAY("2019-02-11"), FakeBook(values, nav=0.94e9), None)
    assert not hook.braking


# A short with no cap on record is covered, never left under the floor.
def test_short_without_cap_is_covered():
    f = formation(n=250)
    hook = execution.Execution({})
    hook.live, hook.left = f, 0
    book = FakeBook((f.target * 1e9).to_dict())
    book.m = type("M", (), {"cap_at": staticmethod(lambda p, d: np.nan if p == 200 else 1e6)})()
    hook(1, DAY("2019-02-05"), book, None)
    assert [k for _, k, _ in hook.log] == ["short_floor"]


# Weekly decisions re-plan on the last public month end's inputs.
def test_weekly_decisions(monkeypatch):
    from fiam.v4.construct import simulate

    days = pd.bdate_range("2019-01-01", "2019-03-29")

    # The month end public by a day: its own on the month's last session.
    def month_end(d):
        d = pd.Timestamp(d)
        last = d == d + pd.offsets.BMonthEnd(0)
        return d + pd.offsets.MonthEnd(0) if last else d - pd.offsets.MonthEnd(1)

    ends = lambda e: pd.Series([pd.Timestamp(x) + pd.offsets.BMonthEnd(0) for x in e])  # noqa: E731
    monkeypatch.setattr(data, "eom_session", ends)
    monkeypatch.setattr(data, "sessions", lambda a, b: days[(days >= a) & (days <= b)])
    monkeypatch.setattr(data, "month_end_at", month_end)
    months = pd.DatetimeIndex(["2019-01-31", "2019-02-28"])
    got = simulate.decisions(months, "2019-03-29", "weekly")
    assert got[DAY("2019-01-31")] == months[0] and got[DAY("2019-02-08")] == months[0]
    assert got[DAY("2019-03-08")] == months[1] and len(got) > 2
    monthly = simulate.decisions(months, "2019-03-29", "monthly")
    assert monthly == {DAY("2019-01-31"): months[0], DAY("2019-02-28"): months[1]}


# A half cover in the spill ends that name's plan: no buying back.
def test_half_cover_ends_the_plan():
    f = formation(n=250, gross=1.6, adv=3e7)
    hook = execution.Execution({DAY("2019-02-01"): f})
    b = FakeBook()
    _, w = hook(1, DAY("2019-02-01"), b, (f.formed, f.target))
    b.values = (w * 1e9).to_dict()
    hook.pending.append(("squeeze_cover", lambda w: execution.cover(w, [200], [])))
    _, w = hook(2, DAY("2019-02-04"), b, None)
    first = w[200]
    b.values = (w * 1e9).to_dict()
    out = hook(3, DAY("2019-02-05"), b, None)
    assert (w if out is None else out[1])[200] == pytest.approx(first)


# Only fills that push beta past 0.10 shrink; the others fill in full.
def test_only_pushing_fills_shrink():
    ids = list(range(1, 41))
    target = pd.Series(np.where(np.arange(40) < 20, 0.02, -0.02), index=ids)
    x = pd.DataFrame({"adv_cost": 1e12, "welch": np.where(np.arange(40) < 20, 1.5, 0.5),
                      "dimson": 1.0}, index=ids)  # fmt: skip
    f = execution.Formation(DAY("2019-01-31"), target, x, 1.7678, 1e9)
    hook = execution.Execution({DAY("2019-02-01"): f})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(), (f.formed, f.target))
    assert w[w < 0].sum() == pytest.approx(-0.4)
    assert float(w @ x["welch"]) == pytest.approx(execution.BETA_BAND)


# A plan never crosses zero: a drifted long past its plan only closes.
def test_spill_never_crosses_zero():
    f = formation(n=250, gross=1.6)
    prev = f.target.copy()
    prev[3] = 0.015
    target = f.target.copy()
    target[3] = 0.0006
    x = pd.DataFrame({"adv_cost": 1e12, "welch": 1.0, "dimson": 1.0}, index=target.index)
    g = execution.Formation(f.formed, target, x, 1.7678, 1e9, prev)
    held = (prev * 1e9).to_dict()
    held[3] = 0.0135e9
    hook = execution.Execution({DAY("2019-02-01"): g})
    _, w = hook(1, DAY("2019-02-01"), FakeBook(held), (g.formed, g.target))
    assert w.get(3, 0.0) >= 0.0


# A book-wide fix with tiny moves counts toward the plan, not ending it.
def test_book_wide_fix_keeps_the_plan():
    f = formation(n=250, gross=1.6, adv=3e7)
    hook = execution.Execution({DAY("2019-02-01"): f})
    b = FakeBook()
    _, w = hook(1, DAY("2019-02-01"), b, (f.formed, f.target))
    b.values = (w * 1e9).to_dict()
    hook.pending.append(("beta_rehedge", lambda w: w + 1e-5 * np.sign(w)))
    hook(2, DAY("2019-02-04"), b, None)
    assert float(f.remaining.abs().max()) > 1e-4


# The name counts hold after the band scale-backs: at most 490.
def test_counted_caps_names():
    held = pd.Series(0.001, index=range(1, 486))
    step = pd.concat([pd.Series(0.0, index=held.index), pd.Series(0.001, index=range(486, 506))])
    target = pd.concat([held, pd.Series(0.001, index=range(486, 506))])
    got = execution.counted(step, held.reindex(step.index).fillna(0.0), target)
    alive = (held.reindex(step.index).fillna(0.0) + got).abs() > 1e-9
    assert int(alive.sum()) == execution.NAMES_HIGH


# An overlay halves a name once a formation, however often flagged.
def test_overlay_once():
    f = formation(n=250)
    days = {DAY("2019-02-05"): {3}, DAY("2019-02-06"): {3}}
    hook = execution.Execution({}, overlays={"long": days})
    hook.live, hook.left = f, 0
    book = FakeBook((f.target * 1e9).to_dict())
    hook(1, DAY("2019-02-05"), book, None)
    hook(2, DAY("2019-02-06"), book, None)
    assert [k for _, k, _ in hook.log].count("overlay_long") == 1


# A decision close plans from the book after that close's own trades.
def test_plan_starts_after_the_close(monkeypatch):
    f = formation(n=250)
    seen = {}
    later = lambda d, n: pd.Series([pd.Timestamp(d[0]) + pd.offsets.BDay(n)])  # noqa: E731
    monkeypatch.setattr(data, "shift", later)

    # A stand-in planner that records the book it is handed.
    class Planner:
        decision, month_ends = {DAY("2019-02-28"): DAY("2019-02-28")}, {DAY("2019-02-28")}
        hooks = type("H", (), {"add": staticmethod(lambda *a: None)})()

        # Records the held book and returns the same targets.
        def plan(self, d, book, held):
            seen["held"] = held
            return f.target, f.adv.to_frame("adv_cost").assign(welch=1.0, dimson=1.0), 1.7, 1e9, \
                f.target * 0, held  # fmt: skip

    hook = execution.Execution({}, planner=Planner())
    hook.live, hook.left = f, 0
    hook.pending.append(("short_floor", lambda w: w.where(w.index != 200, 0.0)))
    hook(1, DAY("2019-02-28"), FakeBook((f.target * 1e9).to_dict()), None)
    assert 200 not in seen["held"].index and len(seen["held"]) == 249


# In 2026 the trigger beta reads an open month's days raw (review M).
def test_trigger_beta_open_month_is_raw(monkeypatch):
    days = pd.bdate_range("2025-06-02", "2026-01-15")
    m = pd.Series(np.random.default_rng(2).normal(0, 0.01, len(days)), index=days)
    monkeypatch.setattr(data, "market_daily", lambda d: m.reindex(d))
    monkeypatch.setattr(data, "rf_daily", lambda d, by=None: pd.Series(0.0, index=d))
    monkeypatch.setattr(data, "eom_session", lambda e: pd.Series([DAY("2026-01-30")]))
    cooked = pd.DataFrame({7: m * 1.0}, index=days)
    raw = cooked.loc[days > "2025-12-31"].copy()
    raw[7] = 2.0 * m.loc[raw.index]
    got = execution.TriggerBeta(cooked, raw)(days[-1], [7])
    plain = execution.TriggerBeta(cooked)(days[-1], [7])
    assert got[7] > plain[7]


# Seven exam runs; an exact tie goes to the neutral twin, then fewer.
def test_exam_designs_and_ties():
    assert set(exam.DESIGNS) == {1, 2, 4, 5, 6, 7, 8}
    runs = {k: {"ir": 0.2} for k in (1, 6, 2, 7, 5, 8)}
    assert exam.winner(runs) == 6
    assert exam.DESIGNS[8] == ("z", 220, exam.TILTS)
