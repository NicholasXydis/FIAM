# The desk on synthetic data: triggers, cards, agents, arms, rules.

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal.desk import after, agents, arms, cards, decide, triggers

DAY = pd.Timestamp


# Earnings within 5 sessions, from projections public by the day only.
def test_earnings_trigger():
    days = pd.bdate_range("2019-03-01", periods=30)
    cal = pd.DataFrame({"permno": [1, 2, 3, 4], "projected": [days[3], days[10], days[2], days[4]],
                        "first_close": [days[0], days[0], days[0], days[6]]})  # fmt: skip
    got = triggers.earnings([1, 2, 3, 4], days[1], cal, days)
    assert got == {1: 2, 3: 1}


# A loss counts when the signed move is beyond -3 daily sigmas.
def test_loss_trigger():
    w = pd.Series({1: 0.01, 2: -0.01, 3: 0.01})
    r = pd.Series({1: -0.07, 2: 0.07, 3: -0.02})
    got = triggers.losses(w, r, pd.Series(0.02, index=[1, 2, 3]))
    assert sorted(got) == [1, 2]


# Vol jumps against the 99th of every prior stock-day, never later.
def test_vol_jumps_are_past_only():
    days = pd.bdate_range("2019-01-01", periods=60)
    vol = pd.DataFrame(0.3, index=days, columns=[1, 2])
    vol.iloc[-1, 0] = 0.9
    j = triggers.Jumps(vol)
    assert j.at(days[-1], [1, 2]) == {1: pytest.approx(np.log(3), abs=0.01)}
    assert j.at(days[-2], [1, 2]) == {}


# The card holds no identity, and its key moves with every input.
def test_card_is_masked_and_keyed():
    w = pd.Series({7: 0.01, 8: 0.02, 9: -0.01})
    x = pd.DataFrame({"size": [1.0, 2.0, 3.0], "value": [0.0, 1.0, 2.0]}, index=[7, 8, 9])
    c = cards.card(7, w, pd.Series({7: 0.1, 8: 0.2, 9: -0.1}), x, {"loss": -3.5}, {"gross": 1.7})
    allowed = {"side", "weight_pct_in_side", "alpha_pct_in_side", "confidence_tercile",
               "size_pct", "value_pct", "triggers", "book", "red_flag_items_90d"}  # fmt: skip
    assert set(c) <= allowed and c["side"] == "long"
    k1 = cards.key("m", "b", (), [{"a": 1}], {}, 0.0, 42, 2048)
    assert k1 != cards.key("m", "b", (), [{"a": 2}], {}, 0.0, 42, 2048)


# A fake model through the three calls; a replay lists what is missing.
def test_agent_protocol_and_replay():
    meta = dict(model_sha="m", build="b", server_args=(), temperature=0.0, seed=42, tokens=2048,
                cutoff="2025-01")  # fmt: skip

    # Answers in order: a proposal, an argument, then a final shrink.
    class Model:
        # The advocate disagrees; the sizing agent halves.
        def chat(self, messages, schema):
            if "argument" in schema["properties"]:
                return {"argument": "no edge", "agree": False}
            return {"shrink": 0.5, "reason": "print"}

    store = {}
    desk = agents.Desk(store, meta, Model())
    shrink, log = desk.decide({"side": "long"}, DAY("2019-03-29"))
    assert shrink == 0.5 and len(store) == 3
    replay = agents.Desk(store, meta)
    assert replay.decide({"side": "long"}, DAY("2019-03-29"))[0] == 0.5
    assert agents.Desk({}, meta).decide({"side": "short"}, DAY("2019-03-29"))[0] is None


# An answer outside the allowed set is no shrink, never a guess.
def test_bad_answer_is_no_shrink():
    meta = dict(model_sha="m", build="b", server_args=(), temperature=0.0, seed=42, tokens=2048,
                cutoff="2025-01")  # fmt: skip

    # A model that answers a shrink the rules do not allow.
    class Model:
        # Always a shrink of 0.1, which the set does not hold.
        def chat(self, messages, schema):
            if "argument" in schema["properties"]:
                return {"argument": "x", "agree": True}
            return {"shrink": 0.1, "reason": "x"}

    assert agents.Desk({}, meta, Model()).decide({}, DAY("2019-03-29"))[0] == 1.0


# The cost gate: a shrink only where the risk saving beats the cost.
def test_cost_gate():
    assert after.worth(0.01, 0.5, 0.01, 3.0, lambda t: 0.0)
    assert not after.worth(0.01, 0.5, 0.01, 3.0, lambda t: 1.0)


# Freed gross goes to the same side's others within caps; rest is cash.
def test_enforce_keeps_gross_within_caps():
    w = pd.Series({1: 0.01, 2: 0.01, 3: 0.01, 4: -0.015, 5: -0.015})
    got, left = after.enforce(w, {1: 0.5}, pd.Series(0.015, index=w.index))
    assert got[got > 0].sum() == pytest.approx(0.03) and (got.abs() <= 0.015 + 1e-12).all()
    assert got[got < 0].sum() == pytest.approx(-0.03) and left[1] == pytest.approx(0.0)
    tight, left = after.enforce(w, {1: 0.5}, pd.Series(0.0101, index=w.index))
    assert left[1] == pytest.approx(0.0048) and (tight[tight > 0] <= 0.0101 + 1e-12).all()


# The arms: none, the set map with its floor, the agent, the placebo.
def test_arms():
    events = {(DAY("2019-03-04"), 1): {"earnings": 2}, (DAY("2019-03-04"), 2): {"vol_jump": 1.2,
              "loss": -3.4}, (DAY("2019-03-05"), 3): {"earnings": 1}}  # fmt: skip
    assert arms.shrinks(events, "A0") == {}
    a1 = arms.shrinks(events, "A1")
    assert a1[(DAY("2019-03-04"), 2)] == 0.25 and a1[(DAY("2019-03-04"), 1)] == 0.75
    agent = {(DAY("2019-03-04"), 1): 0.5}
    p1 = arms.shrinks(events, "P1", agent, seed=20261800)
    assert sorted(p1.values()) == [0.5] and arms.today(a1, "2019-03-05") == {3: 0.75}


# The paired bootstrap, the memory gate's band and the headline rule.
def test_decision():
    rng = np.random.default_rng(0)
    a = rng.normal(0.001, 0.01, 500)
    assert decide.paired_se(a, a, draws=50) == 0.0
    assert decide.paired_se(a, a + rng.normal(0, 0.002, 500), draws=50) > 0
    assert decide.memory_gate(200, 20, 17)["passes"]
    assert not decide.memory_gate(200, 60, 17)["passes"]
    irs = {"A0": 0.1, "A1": 0.2, "A2": 0.3}
    assert decide.headline(irs, True) == "A2" and decide.headline(irs, False) == "A1"
    assert decide.headline({"A0": 0.1, "A1": 0.1, "A2": 0.1}, True) == "A0"


# An arm replays A0's formation and applies its shrink one close late.
def test_arm_shrinks_at_the_next_close():
    from fiam.vfinal.construct import execution
    from fiam.vfinal.desk import hook

    ids = list(range(1, 251))
    target = pd.Series(np.where(np.arange(250) < 125, 0.0064, -0.0064), index=ids)
    x = pd.DataFrame({"adv_cost": 1e10, "welch": 1.0, "dimson": 1.0}, index=ids)
    f = execution.Formation(DAY("2019-01-31"), target, x, 1.7678, 1e9)
    arm = hook.Arm({DAY("2019-02-01"): f}, {(DAY("2019-02-05"), 3): 0.5})
    arm.live, arm.left = arm.by_day[DAY("2019-02-01")], 0

    # A book the hook can read, holding the formation's target.
    class Book:
        values, nav_before, cash, rows = (target * 1e9).to_dict(), 1e9, 1e9, []
        m = type("M", (), {"cap_at": staticmethod(lambda p, d: 1e6)})()

    assert arm(1, DAY("2019-02-05"), Book(), None) is None
    _, w = arm(2, DAY("2019-02-06"), Book(), None)
    assert w[3] == pytest.approx(0.0032) and w[w > 0].sum() == pytest.approx(0.8)


# The memory gate's two questions are closed choices over the options.
def test_memory_questions_are_closed():
    from fiam.vfinal.desk import run

    q = {"card": {"side": "long"}, "company": ["A", "B"], "months": ["2019-01", "2019-02"]}
    asks = run.memory_messages(q)
    assert [k for _, _, k in asks] == ["company", "month"]
    assert asks[0][1]["properties"]["choice"]["enum"] == ["A", "B"]


# A trigger's extra variance: earnings, vol jump and loss add.
def test_extra_variance():
    from fiam.vfinal.desk import run

    assert run.extra_var({}, 0.04, 0.01) == 0.0
    assert run.extra_var({"earnings": 3}, 0.04, 0.01) == 0.01
    assert run.extra_var({"loss": 2.5}, 0.04, 0.01) == 0.0
    assert run.extra_var({"loss": 6.0}, 0.04, 0.01) == pytest.approx(0.12)
    jump = 0.04 * (np.exp(0.6) - 1)
    assert run.extra_var({"vol_jump": 0.3}, 0.04, 0.01) == pytest.approx(jump)
    both = run.extra_var({"earnings": 1, "vol_jump": 0.3, "loss": 6.0}, 0.04, 0.01)
    assert both == pytest.approx(0.01 + jump + 0.12)


# The gate keeps a shrink only where the trigger's extra risk pays.
def test_gate_on_an_arm():
    from fiam.vfinal.desk import run

    d = DAY("2019-03-04")
    x = pd.DataFrame({"prc": 50.0, "half_spread": 0.001, "sigma_d": 0.02, "adv_cost": 1e8,
                      "spec": 0.04}, index=[1, 2, 3])  # fmt: skip
    pos = pd.DataFrame({"date": d, "permno": [1, 2, 3], "value": [2e7, 2e7, 2e7]})
    daily = pd.DataFrame({"nav": [1e9]}, index=[d])
    earn = pd.Series({DAY("2019-03-01"): 0.0})
    found = {(d, 1): {"loss": 12.0}, (d, 2): {"loss": 3.5}}
    plan = {(d, 1): 0.5, (d, 2): 0.5, (d, 3): 0.5}
    assert run.gated(plan, found, {d: x}, pos, daily, 3.0, earn) == {(d, 1): 0.5}
    # The month's earnings variance counts only for an earnings trigger.
    earn = pd.Series({DAY("2019-03-01"): 1.0})
    found[(d, 3)] = {"earnings": 2}
    assert run.gated(plan, found, {d: x}, pos, daily, 3.0, earn) == {(d, 1): 0.5, (d, 3): 0.5}


# Squared two-session market-adjusted moves on earnings 8-Ks, past year.
def test_earnings_variance(monkeypatch):
    from fiam.vfinal import data
    from fiam.vfinal.desk import run

    days = pd.bdate_range("2018-01-01", "2019-03-29")
    returns = pd.DataFrame(0.0, index=days, columns=[1, 2])
    returns.loc[DAY("2018-06-05"), 1] = 0.10
    returns.loc[DAY("2019-02-05"), 2] = -0.20
    ev = pd.DataFrame({"permno": [1, 2, 2, 1], "earnings_8k": [True, True, True, False],
                       "amendment": [False, False, True, False],
                       "first_close": [DAY("2018-06-05"), DAY("2019-02-05"), DAY("2018-09-04"),
                                       DAY("2018-09-04")]})  # fmt: skip
    monkeypatch.setattr(data, "table", lambda name, cols, **k: ev)
    monkeypatch.setattr(data, "market_daily", lambda d: pd.Series(0.0, index=d))
    monkeypatch.setattr(run.exam, "END", DAY("2019-03-31"))
    v = run.earnings_var(returns)
    assert np.isnan(v[DAY("2018-06-01")])
    assert v[DAY("2018-07-01")] == pytest.approx(0.01)
    assert v[DAY("2019-03-01")] == pytest.approx((0.01 + 0.04) / 2)


# Parts answered on two machines merge by key into one replay.
def test_parts_merge_and_cutoff_agreement(monkeypatch, tmp_path):
    from fiam.agents import harness
    from fiam.vfinal.desk import run

    # The sizing agent halves; the advocate argues; Pythia keeps or halves.
    class Model:
        # A set answer by schema and by the card's side.
        def __init__(self, keep):
            self.keep = keep

        # One answer.
        def chat(self, messages, schema):
            if "argument" in schema["properties"]:
                return {"argument": "no edge", "agree": False}
            long = '"long"' in messages[-1]["content"]
            return {"shrink": 1.0 if self.keep and long else 0.5, "reason": "r"}

    monkeypatch.setattr(harness, "RUNS", tmp_path)
    rows = [{"card": {"side": s, "n": k}, "formed": "2019-03-29"}
            for k, s in enumerate(["long", "short", "long", "short"])]  # fmt: skip
    for i in (1, 2):
        with harness.answers(f"desk_v4_part{i}of2", key=lambda r: r["key"]) as (done, save):
            desk = agents.Desk(done, run.META, Model(False), save)
            for r in rows[i - 1 :: 2]:
                desk.decide(r["card"], r["formed"])
    assert run.replay().decide(rows[1]["card"], "2019-03-29")[0] == 0.5
    assert not run.replay().missing
    assert run.agreement(rows, run.replay()) is None
    with harness.answers("cutoff_v4_part1of1", key=lambda r: r["key"]) as (done, save):
        old = agents.Desk(done, run.CUTOFF_META, Model(True), save)
        for r in rows:
            old.ask(agents.sizing(r["card"]), agents.SIZING, r["formed"])
    got = run.agreement(rows, run.replay())
    assert got == {"cards": 4, "missing": 0, "same_as_proposal": 0.5, "same_as_final": 0.5}


# The finals' window keeps its own files, days and A0 apart.
def test_final_window_keeps_apart(monkeypatch):
    from fiam.vfinal import final
    from fiam.vfinal.desk import run

    head = "a" * 40
    assert run.path("cards", head).name == f"cards_{'a' * 12}.json"
    assert run.span() == (run.exam.END, "2016-12-01")
    monkeypatch.setattr(run, "FINAL", True)
    assert run.path("cards", head).name == f"final_cards_{'a' * 12}.json"
    assert run.span()[0] == final.END
    plans, days, held = run.a0_files(head, 6)
    assert plans == final.path("plans_6", head, "pkl") and days.parent == final.OUT


# The mildest shrink passes the gate first, so cards are asked by it.
def test_mildest_shrink_passes_first():
    from fiam.vfinal.desk import run

    d = DAY("2019-03-04")
    x = pd.DataFrame({"prc": 50.0, "half_spread": 0.001, "sigma_d": 0.02, "adv_cost": 1e8,
                      "spec": 0.04}, index=[1])  # fmt: skip
    pos = pd.DataFrame({"date": d, "permno": [1], "value": [2e7]})
    daily = pd.DataFrame({"nav": [1e9]}, index=[d])
    earn = pd.Series({DAY("2019-03-01"): 0.0})
    seen = []
    for loss in np.arange(3.2, 20, 0.2):
        ok = {m: run.passes(m, d, 1, {"loss": loss}, {d: x}, pos, daily, 3.0, earn)
              for m in (0.75, 0.25)}  # fmt: skip
        assert not (ok[0.25] and not ok[0.75])
        seen.append(ok[0.75] and not ok[0.25])
    assert any(seen)


# A shrink on a name that left the book is skipped, never a KeyError.
def test_enforce_skips_a_gone_name():
    w = pd.Series({1: 0.02, 2: -0.02, 3: 0.01})
    out, unplaced = after.enforce(w, {9: 0.5, 1: 0.5}, pd.Series(0.05, index=w.index))
    assert unplaced["gone"] == {9: 0.5} and out.index.equals(w.index)


# A remote server's model file is named alike from Windows or Unix.
def test_served_name_reads_windows_paths():
    from fiam.agents import harness

    name = harness.MODELS["gemma"][1]
    assert harness.served_name(f"C:\\Code\\Forkfiam\\models\\{name}") == name
    assert harness.served_name(f"/Users/x/models/{name}") == name
    assert harness.served_name(None) == ""


# Shares split the placebos; part 1 alone takes A0's twin, A1 and A2.
def test_arm_shares_cover_every_arm_once():
    from fiam.vfinal.desk import run

    names = ["A0_replay", "A1", "A2", *(f"P1_{s}" for s in run.arms.PLACEBO_SEEDS)]
    mac, pc = run.share(names, (1, 2), 5), run.share(names, (3, 4, 5), 5)
    assert set(mac) | set(pc) == set(names) and not set(mac) & set(pc)
    assert set(run.SPECIAL) <= set(mac) and len(pc) == 60


# `--fixed` plans A0's twin and A1 alone, as the full arms do.
def test_fixed_arms_need_no_answers():
    from fiam.vfinal.desk import run

    found = {(DAY("2019-03-04"), 1): {"earnings": 2}, (DAY("2019-03-05"), 2): {"loss": -3.4}}
    seeds = run.arms.PLACEBO_SEEDS[:3]
    alone = run.arm_plans(found, None, seeds)
    full = run.arm_plans(found, {(DAY("2019-03-04"), 1): 0.5}, seeds)
    assert list(alone) == ["A0_replay", "A1"] and len(full) == 3 + len(seeds)
    assert all(full[a] == alone[a] for a in alone) and alone["A1"]


# The cost gate prices risk at the winning design's own lambda.
def test_gate_lambda_follows_the_ladder():
    from fiam.vfinal.desk import run

    assert run.risk_lambda(3.0, 12) == 0.75 and run.risk_lambda(3.0, 14) == 1.5
    assert run.risk_lambda(3.0, 1) == 3.0 and run.risk_lambda(3.0, 13) == 3.0


# A replay prices a name outside the frame by the rows known that close.
def test_replay_costs_read_no_later_row(monkeypatch):
    from fiam.vfinal.construct import costs

    # The next business day stands in for the next session.
    def shift(days, n):
        return pd.Series([DAY(d) + pd.offsets.BDay(n) for d in days])

    monkeypatch.setattr(costs.data, "shift", shift)

    # One formation's rows: every name at one price.
    def frame(names, prc):
        return pd.DataFrame({"prc": prc, "half_spread": 0.001, "sigma_d": 0.02,
                             "adv_cost": 1e7, "borrow": 0.003}, index=names)  # fmt: skip

    k0, k1, k2 = DAY("2019-01-02"), DAY("2019-02-01"), DAY("2019-03-01")
    done, live = costs.Hooks(), costs.Hooks()
    # The finished run holds all three; the live run two by mid-February.
    for k, x in ((k0, frame([1, 3], 10.0)), (k1, frame([1, 2], 10.0)), (k2, frame([1, 3], 200.0))):
        done.add(k, x, pd.Series(dtype=float))
        if k < k2:
            live.add(k, x, pd.Series(dtype=float))
    moved, d = pd.Series({3: -1e5}), DAY("2019-02-15")
    want = live.costs(d, moved)
    assert not done.costs(d, moved).equals(want)
    pd.testing.assert_series_equal(costs.Replay(done).costs(d, moved), want)
    replay = costs.Replay(done)
    replay.costs(DAY("2019-02-28"), moved)
    assert k2 in replay.frames
