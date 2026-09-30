# The models, the ship rule and the agents' plumbing on tiny synthetic inputs. No data, no network.

import importlib
from operator import itemgetter

import numpy as np
import pandas as pd
import pytest
import torch

from fiam import book as P


# A blend stays dollar neutral at its gross, under the name cap and the rules' 500 names.
def test_blend_is_neutral_capped_and_sells_what_left_the_list():
    target = pd.Series([0.015] * 60 + [-0.015] * 60, index=range(120)) * (1.6 / 1.8)
    previous = pd.Series([0.02, -0.02, 0.01], index=[0, 60, 999])
    mixed = P.blend(target, previous, pd.Index(range(120)), rate=0.5, gross=1.4)
    assert 999 not in mixed.index
    assert abs(mixed.sum()) < 1e-12
    assert mixed.abs().sum() == pytest.approx(1.4, abs=1e-9)
    assert mixed.abs().max() <= P.LIMITS["name"] + 1e-12
    assert len(mixed) <= P.MAX_NAMES


# The composite ships unless another candidate beats it by the hurdle with a small beta.
def test_ship_rule_keeps_the_composite_without_a_clear_winner(monkeypatch):
    months = pd.date_range("2019-01-01", "2020-12-01", freq="MS")
    base = pd.Series(np.tile([0.02, -0.01], 12), index=months)
    books = {
        "composite": pd.DataFrame(dict(net=base)),
        "scorer50": pd.DataFrame(dict(net=base + 0.0005)),
        "scorer50+hedged": pd.DataFrame(dict(net=base * 2 + 0.01)),
    }
    judged = {"composite": 0.5, "scorer50": 0.6, "scorer50+hedged": 1.0}
    betas = {"composite": 0.0, "scorer50": 0.0, "scorer50+hedged": 0.3}

    # Returns the IR and beta set above for whichever book is passed.
    def fake(net, first, last):
        name = next(k for k, b in books.items() if b["net"].iloc[0] == net.iloc[0])
        return dict(information_ratio=judged[name], beta=betas[name])

    monkeypatch.setattr(P, "judge", fake)
    assert P.choose(books, 2021)[0] == "composite"
    betas["scorer50+hedged"] = 0.1
    assert P.choose(books, 2021)[0] == "scorer50+hedged"


# The 3 x 2 x 2 grid: every blend with and without each learned part, each named in words.
def test_candidate_grid():
    assert len(P.CANDIDATES) == 12 and "composite" in P.CANDIDATES
    assert P.candidate_name(0.25, True, True) == "scorer25+hedged+traded"
    label = P.candidate_label("scorer25+hedged+traded")
    assert label == "Composite + 25% scorer + hedge + trader"


# The same window trains the same policy twice, and a warm start moves on from where it was.
def test_trader_is_deterministic_and_warm_starts(monkeypatch):
    trader = importlib.import_module("fiam.ml.trader")
    monkeypatch.setattr(trader, "STEPS", 5)
    monkeypatch.setattr(trader, "MONTHLY_STEPS", 2)
    rng = np.random.default_rng(1)
    months, n = 30, 20
    aim = np.r_[np.full(10, 0.16), np.full(10, -0.16)][None, :].repeat(months, 0)
    t = dict(
        aim=aim,
        ret=rng.normal(0, 0.05, (months, n)),
        linear=np.full((months, n), 0.001),
        impact=np.full((months, n), 0.01),
        borrow=np.full((months, n), 0.0025),
        listed=np.ones((months, n)),
        rf=np.full(months, 0.003),
    )
    tt = {k: torch.as_tensor(v) for k, v in t.items()}
    f = torch.as_tensor(rng.normal(size=(months, 4)))
    window = np.arange(28)
    first, second = trader.train_deep(tt, f, window), trader.train_deep(tt, f, window)
    assert torch.equal(first.linear.weight, second.linear.weight)
    before = first.linear.weight.clone()
    assert trader.train_deep(tt, f, np.arange(29), first) is first
    assert not torch.equal(first.linear.weight, before)


# The director's room ends the December before its year, whatever the agent asks for.
def test_director_sees_only_earlier_months():
    director = importlib.import_module("fiam.agents.director")
    months = pd.date_range("2019-01-01", "2022-12-01", freq="MS")
    rows = [
        dict(candidate=c, holding_month=m, net=0.01, cost=0.001, turnover=0.5)
        for c in P.CANDIDATES
        for m in months
    ]
    table = pd.DataFrame(rows).set_index(["candidate", "holding_month"]).sort_index()
    room = director.Room(table, 2021)
    assert room.table.index.get_level_values("holding_month").max() == pd.Timestamp("2020-12-01")
    assert set(room.by_year("composite")) == {"2019", "2020"}


# The trader's two simulators, PyTorch for gradients and NumPy for PPO, give the same month.
def test_trader_steps_agree():
    trader = importlib.import_module("fiam.ml.trader")
    rng = np.random.default_rng(0)
    n = 30
    t = dict(
        aim=np.r_[np.full(15, 0.1), np.full(15, -0.1)][None, :].repeat(2, 0) * 1.6 / 3,
        ret=rng.normal(0, 0.05, (2, n)),
        linear=np.full((2, n), 0.001),
        impact=np.full((2, n), 0.01),
        borrow=np.full((2, n), 0.0025),
        listed=np.ones((2, n)),
        rf=np.full(2, 0.003),
    )
    held = t["aim"][0] * 0.9
    net_np, after_np = trader.step_numpy(held, t, 1, 0.5, 1.4, 1.2)
    tt = {k: torch.as_tensor(v) for k, v in t.items()}
    one = torch.tensor([[0.5]]), torch.tensor([[1.4]]), torch.tensor([1.2])
    net_t, after_t = trader.step_torch(torch.as_tensor(held)[None], tt, torch.tensor([1]), *one)
    assert float(net_t[0]) == pytest.approx(net_np, rel=1e-6)
    assert after_t[0].numpy() == pytest.approx(after_np, rel=1e-6)


# The crowd agent sees codes, percentiles and filings, never a name, a ticker or a date.
def test_crowd_cards_carry_no_names_or_dates():
    crowd = importlib.import_module("fiam.agents.crowd")
    C = importlib.import_module("fiam.ml.crowd")
    batch = pd.DataFrame(
        [
            dict(
                permno=12490,
                eom=pd.Timestamp("2016-03-31"),
                **{c: 50 for c in C.CARD},
                **{e: 0 for e in C.EVENTS},
            )
        ]
    )
    text = crowd.table(batch, ["S01"])
    assert "12490" not in text and "2016" not in text
    assert text.splitlines()[1].startswith("S01")


# The rehearsal swaps every model for the tiny one, and a machine can be chosen by hand.
def test_harness_resolves_models_and_machines(monkeypatch):
    harness = importlib.import_module("fiam.agents.harness")
    monkeypatch.setattr(harness.paths, "SMOKE", True)
    assert harness.resolve("qwen") == "tiny"
    monkeypatch.setenv("FIAM_LLAMA_BUILD", "linux-cpu")
    assert harness.machine() == "linux-cpu"
    assert all(len(sha) == 64 for builds in harness.BUILDS.values() for _, sha in builds)


# A walked-forward rule is shown only months before each year, and its picks' months are joined.
def test_nested_rule_sees_only_the_past():
    evaluate = importlib.import_module("fiam.evaluate")
    months = pd.date_range("2019-01-01", "2022-12-01", freq="MS")
    books = {
        n: pd.DataFrame(dict(net=np.full(len(months), r)), index=months)
        for n, r in (("a", 0.01), ("b", 0.02))
    }
    seen = {}

    # Records the last month each year's rule was shown, then picks by the year's parity.
    def rule(history: dict, year: int) -> str:
        seen[year] = max(b.index.max() for b in history.values())
        return "a" if year % 2 else "b"

    picks, joined = evaluate.nested(books, rule, range(2021, 2023))
    assert seen == {2021: pd.Timestamp("2020-12-01"), 2022: pd.Timestamp("2021-12-01")}
    assert picks == {"2021": "a", "2022": "b"} and len(joined) == 24
    assert joined.loc["2021", "net"].eq(0.01).all() and joined.loc["2022", "net"].eq(0.02).all()


# The current design keeps 1.5% everywhere; v2 shrinks illiquid and volatile names, bans specials.
def test_construction_v2_caps():
    month = pd.DataFrame(
        dict(
            rvol_21d=[0.02, 0.02, 0.08, 0.02],
            dolvol_126d=[1e8, 1e6, 1e8, 1e8],
            borrow=[0.003, 0.003, 0.003, 0.08],
        )
    )
    side = np.array([1.0, 1.0, -1.0, -1.0])
    assert (P.caps(month, month, side, P.CURRENT) == P.LIMITS["name"]).all()
    cap = P.caps(month, month, side, P.V2)
    impact = month["rvol_21d"] / np.sqrt(month["dolvol_126d"])
    assert cap[0] == P.LIMITS["name"]
    assert cap[1] == pytest.approx(P.LIMITS["name"] * impact.median() / impact[1])
    assert cap[2] == pytest.approx(P.LIMITS["name"] * min(impact.median() / impact[2], 0.02 / 0.08))
    assert cap[3] == 0.0


# The bear-market state follows the market's own past 24 months, known at each decision.
def test_bear_months_follow_the_past_two_years(monkeypatch):
    months = pd.date_range("2018-01-01", periods=30, freq="MS")
    down = [-0.02] * 24 + [0.05] * 6
    frame = pd.DataFrame(dict(month=months, mkt_rf_crsp=down, rf=0.0))
    monkeypatch.setattr(P, "benchmarks", lambda: frame)
    P.bear_months.cache_clear()
    bear = P.bear_months()
    P.bear_months.cache_clear()
    assert pd.Timestamp("2019-12-31") in bear and pd.Timestamp("2019-11-30") not in bear


# Text components are fitted on the training rows alone: test rows cannot change them.
def test_text_components_fit_on_training_rows_only():
    text = importlib.import_module("fiam.ml.text")
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(800, text.WIDTH)).astype(np.float32)
    matrix[700:, 0] = np.nan
    train = np.arange(800) < 500
    first = text.components(matrix, train)
    shifted = matrix.copy()
    shifted[500:700] += 100.0
    second = text.components(shifted, train)
    assert np.allclose(first[:500], second[:500], atol=1e-4)
    assert np.isnan(first[700:]).all()


# The stock picker's target carries no beta or style: it is uncorrelated with each exposure.
def test_stock_picker_target_is_free_of_style():
    scorer = importlib.import_module("fiam.ml.scorer")
    rng = np.random.default_rng(0)
    n = 400
    frame = pd.DataFrame({c: rng.normal(size=n) for c in scorer.STYLE})
    frame["holding_month"] = pd.Timestamp("2020-01-01")
    frame["sector"] = rng.choice(["10", "20"], n)
    frame[scorer.D.TARGET] = frame[scorer.STYLE].sum(axis=1) + rng.normal(size=n)
    out = scorer.residual(frame)
    assert all(abs(np.corrcoef(out, frame[c])[0, 1]) < 1e-8 for c in scorer.STYLE)


# The agents' answer log resumes: a second session sees what the first one saved.
def test_agent_answers_resume(tmp_path, monkeypatch):
    harness = importlib.import_module("fiam.agents.harness")
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    with harness.answers("demo", itemgetter("id")) as (done, save):
        save(dict(id="a", label="good"))
    with harness.answers("demo", itemgetter("id")) as (done, _):
        assert done == {"a": dict(id="a", label="good")}
