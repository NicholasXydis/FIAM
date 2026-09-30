# The models, the ship rule and the agents' plumbing on tiny synthetic inputs. No data, no network.

import importlib

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
    ship = importlib.import_module("fiam.ml.ship")
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
    assert ship.choose(books, 2021)[0] == "composite"
    betas["scorer50+hedged"] = 0.1
    assert ship.choose(books, 2021)[0] == "scorer50+hedged"


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
        spread=np.full((months, n), 0.01),
        htb=np.zeros((months, n)),
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
        spread=np.full((2, n), 0.01),
        htb=np.zeros((2, n)),
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
