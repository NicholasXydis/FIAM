# fiam.v2 and finals mechanics on synthetic data. No data or network.

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiam import book as P
from fiam import mandate as M
from fiam import stats, v2
from fiam.agents import honesty, rules_reader


# A thousand names with the book's inputs and a price (test_mechanics).
@pytest.fixture
def month():
    rng = np.random.default_rng(0)
    risk = rng.normal(size=1000)
    return pd.DataFrame(
        dict(
            permno=range(1000),
            signal=-risk + rng.normal(scale=0.7, size=1000),
            risk_rank=risk,
            hedge_beta=1 + 0.3 * rng.normal(size=1000),
            sector=rng.choice(["10", "20", "30"], size=1000),
            prc=rng.uniform(5, 500, size=1000),
        )
    )


# With every switch off, the optimizer matches book.optimize_month.
def test_v2_off_is_v1(month):
    mine = v2.optimize(month, None, v2.Settings())
    theirs = P.optimize_month(month)
    assert mine.index.equals(theirs.index)
    assert np.abs(mine.to_numpy() - theirs.to_numpy()).max() < 1e-9


# A long-only mandate holds no more names than allowed, fully invested.
def test_long_only_keeps_its_name_limit(month):
    rules = M.Mandate(
        name="t",
        gross=1.0,
        net=1.0,
        name_cap=0.05,
        sector=None,
        beta=None,
        risk=None,
        names_min=50,
        names_max=100,
        long_only=True,
    )
    weights = v2.optimize(month, None, v2.Settings(frozenset(), 1e7, rules))
    assert 50 <= len(weights) <= 100
    assert (weights >= 0).all() and weights.sum() == pytest.approx(1.0, abs=0.005)


# A net target survives whole shares; the plain repair pulls it to zero.
def test_net_target_survives_whole_shares(month):
    rules = M.Mandate(
        name="t",
        gross=2.0,
        net=1.0,
        name_cap=0.10,
        sector=None,
        beta=None,
        risk=None,
        names_max=300,
    )
    weights = v2.optimize(month, None, v2.Settings(frozenset(), 1e7, rules))
    assert weights.sum() == pytest.approx(1.0, abs=0.005)
    assert weights.abs().sum() == pytest.approx(2.0, abs=0.01)


# Impossible mandates are named, and an unknown rule field is refused.
def test_mandate_check_names_impossible_rules(tmp_path):
    assert M.check(M.Mandate()) == []
    bad = M.Mandate(long_only=True, net=1.6, gross=1.6, names_max=10, name_cap=0.05)
    problems = " ".join(M.check(bad))
    assert "beta neutral" in problems and "cannot reach" in problems
    path = tmp_path / "m.json"
    path.write_text(json.dumps(dict(name="x", leverage=2)), encoding="utf-8")
    with pytest.raises(ValueError):
        M.load(path)


# A turnover cap holds from month two, a net band is checked up front.
def test_turnover_cap_and_net_band(month):
    rules = M.Mandate(name="t", turnover=0.1)
    first = v2.optimize(month, None, v2.Settings(frozenset(), 1e7, rules))
    moved = month.assign(signal=month["signal"].sample(frac=1, random_state=2).to_numpy())
    second = v2.optimize(moved, first, v2.Settings(frozenset(), 1e7, rules))
    idx = first.index.union(second.index)
    traded = second.reindex(idx, fill_value=0) - first.reindex(idx, fill_value=0)
    assert traded.abs().sum() / 2 <= 0.1 + 1e-3
    assert "outside the band" in " ".join(M.check(M.Mandate(net=0.6, gross=2.0, net_band=0.5)))


# The month with the quotes the cost model reads and long-run vol rank.
@pytest.fixture
def quoted(month):
    rng = np.random.default_rng(1)
    return month.assign(
        bidaskhl_21d=rng.uniform(0.001, 0.01, 1000),
        size_grp=rng.choice(["large", "small", "micro"], 1000),
        rvol_21d=rng.uniform(0.01, 0.04, 1000),
        dolvol_126d=rng.uniform(1e6, 1e8, 1000),
        borrow=0.0025,
        low_vol=rng.normal(size=1000),
    )


# Sizing keeps the budget and caps; held names never grow on a flip.
def test_size_part_keeps_budget_caps_and_held_sides(quoted, monkeypatch):
    monkeypatch.setattr(v2, "params", lambda: dict(cost_budget=0.002))
    settings = v2.Settings(frozenset({"size", "lowvol"}), 1e8)
    first = v2.optimize(quoted, None, settings)
    moved = quoted.assign(signal=quoted["signal"].sample(frac=1, random_state=3).to_numpy())
    second = v2.optimize(moved, first, settings)
    pool = moved[moved["permno"].isin(first.index.union(second.index))]
    prev = first.reindex(pool["permno"]).fillna(0.0).to_numpy()
    w = second.reindex(pool["permno"]).fillna(0.0).to_numpy()
    linear, selling, impact, _ = v2.cost_terms(pool, 1e8)
    trade = w - prev
    spent = linear @ np.abs(trade) + selling @ np.maximum(-trade, 0) + impact @ np.abs(trade) ** 1.5
    assert spent <= 0.002 * 1.05
    cap = np.minimum(0.015, 0.4 * pool["dolvol_126d"].to_numpy() / 1e8)
    assert (np.abs(w) <= cap + 1e-4).all()
    turned = (prev != 0) & (np.sign(prev) != np.sign(pool["signal"].to_numpy()))
    assert (np.abs(w[turned]) <= np.abs(prev[turned]) + 1e-4).all()
    low = moved.set_index("permno")["low_vol"].reindex(second.index).to_numpy()
    assert abs(low @ second.to_numpy()) <= 0.02 + 1e-3


# The risk target scales gross in range; the brake cuts it to the floor.
def test_vol_target_and_brake_set_gross(month, monkeypatch):
    monkeypatch.setattr(v2, "params", lambda: dict(vol_target=0.02))
    settings = v2.Settings(frozenset({"voltarget", "brake"}))
    for predicted, gross in ((0.02, 1.6), (0.04, 1.0), (0.016, 1.8), (0.019, 1.6 * 0.02 / 0.019)):
        monkeypatch.setattr(v2, "book_vol", lambda *_, p=predicted: p)
        v2.BRAKE.clear()
        assert v2.target_gross(month, None, settings) == pytest.approx(gross)
    v2.BRAKE["on"] = True
    assert v2.target_gross(month, None, settings) == pytest.approx(1.0)
    v2.BRAKE.clear()


# The brake engages 5% off peak, releases at half regained, then resets.
def test_brake_path():
    v2.BRAKE.clear()
    states = []
    for net in (0.02, -0.08, 0.01, 0.04, -0.05, 0.10):
        v2.track(net)
        states.append(v2.BRAKE["on"])
    assert states == [False, True, True, False, True, False]
    v2.BRAKE.clear()


# Zero beta within +/-0.005, and name caps shrunk by volatility.
def test_zero_beta_and_risk_caps(quoted):
    month = quoted.assign(vol_scale=np.where(np.arange(1000) % 2 == 0, 1 / 3, 1.0))
    weights = v2.optimize(month, None, v2.Settings(frozenset({"zerobeta", "riskcap"})))
    info = month.set_index("permno").loc[weights.index]
    assert abs((weights * info["hedge_beta"]).sum()) <= 0.005 + 1e-3
    assert (weights.abs() <= 0.015 * info["vol_scale"] + 1e-6).all()


# A signal whose last 12 realized months sum below zero counts half.
def test_adaptive_weights_use_only_realized_months():
    months = pd.date_range("2020-01-01", periods=13, freq="MS")
    paid = pd.DataFrame(dict(good=0.01, bad=-0.01), index=months)
    paid.loc[months[-1], "bad"] = 1.0
    late, early = pd.Timestamp("2020-12-31"), pd.Timestamp("2020-04-30")
    weights = v2.halved(paid, [early, late])
    assert weights.loc[late].tolist() == [1.0, 0.5]
    assert weights.loc[early].tolist() == [1.0, 1.0]


# Risk error learns from ended months, the 10% target sets safe gross.
def test_risk_forecast_learns_and_targets_ten_percent(month, monkeypatch):
    monkeypatch.setattr(v2, "params", lambda: dict(vol_bias=1.2, gross_ceiling=1.7))
    settings = v2.Settings(frozenset({"voltarget", "target10"}))
    v2.reset()
    assert v2.RISK["error"] == pytest.approx(1.44)
    monkeypatch.setattr(v2, "book_vol", lambda *_: 0.03)
    expected = 1.6 * (0.10 / np.sqrt(12)) / (1.2 * 0.03)
    assert v2.target_gross(month, None, settings) == pytest.approx(expected)
    v2.learn(0.06, 1.6, settings)
    assert v2.RISK["error"] == pytest.approx(
        v2.BIAS_DECAY * 1.44 + (1 - v2.BIAS_DECAY) * (0.06 / 0.03) ** 2
    )
    monkeypatch.setattr(v2, "book_vol", lambda *_: 0.001)
    assert v2.target_gross(month, None, settings) == pytest.approx(1.7)
    v2.reset()


# Benchmark 2 favourites: ranked by summed |weight| on their net side.
def test_favourites_rank_by_weight_and_time():
    from fiam.exhibits import final_exhibits as F

    a, b = pd.Timestamp("2021-01-31"), pd.Timestamp("2021-02-28")
    held = pd.DataFrame(
        dict(eom=[a, a, b, b], permno=[1, 2, 1, 3], weight=[0.02, -0.01, 0.02, -0.03])
    )
    assert F.favourites(held) == ([1], [3])


# A rule survives only with a word-for-word quote.
def test_rules_reader_keeps_only_verbatim_quotes():
    text = "Leverage is 150/50.\n\nNo single stock may exceed 10%."
    answer = dict(
        gross=2.0,
        gross_quote="Leverage is 150/50.",
        name_cap=0.1,
        name_cap_quote="No stock may exceed ten percent.",
    )
    assert list(rules_reader.verified(answer, text)) == ["gross"]


# A 150/50 draft drops neutral sector and beta limits; neutral keeps.
def test_directional_draft_drops_neutral_limits():
    rules = dict(gross=dict(value=2.0, quote="q"), net=dict(value=1.0, quote="q"))
    draft = rules_reader.drafted(rules, "t")
    assert draft["sector"] is None and draft["beta"] is None
    assert M.check(M.Mandate(**draft)) == []
    assert "sector" not in rules_reader.drafted(dict(gross=dict(value=2.0, quote="q")), "t")


# The reversed text swaps direction words and flips percent signs.
def test_honesty_reversal_flips_words_and_signs():
    row = pd.Series(
        dict(
            excerpt="[COMPANY] said revenue increased 12% and costs fell.",
            company_name="Acme",
            filing_date=pd.Timestamp("2024-05-01"),
        )
    )
    texts = honesty.conditions(row)
    assert texts["reversed"] == "[COMPANY] said revenue decreased -12% and costs rose."
    assert texts["named"].startswith("Acme said")


# On independent noise Patton's quadrant is near a quarter, CI covers.
def test_patton_and_bootstrap_on_independent_noise():
    rng = np.random.default_rng(1)
    a, b = pd.Series(rng.normal(size=240)), pd.Series(rng.normal(size=240))
    p = stats.patton(a, b)
    assert abs(p["quadrant"] - 0.25) < 0.08 and p["quadrant_p"] > 0.01
    boot = stats.bootstrap_mean(a, reps=500)
    assert boot["ci95"][0] < boot["mean"] < boot["ci95"][1]


# Break-even size: log-capital IR zero crossing, else a bound.
def test_capacity_break_even():
    from fiam.exhibits import capacity

    rows = [dict(capital=c, information_ratio=ir) for c, ir in ((1e8, 0.5), (1e9, -0.5))]
    assert capacity.break_even(rows) == pytest.approx(10**8.5)
    assert capacity.break_even([dict(capital=1e6, information_ratio=0.3)]) == "above $5B"
    assert capacity.break_even([dict(capital=1e6, information_ratio=-0.3)]) == "below $1M"


# Our longs among a crowd's favourites: one of two longs is a half.
def test_crowd_overlap_counts_our_longs_among_favourites():
    from fiam.exhibits import crowd_insights

    month = pd.Timestamp("2025-01-31")
    stocks = list(range(20))
    picks = pd.DataFrame(
        [dict(eom=month, permno=s, agent=a, picked=(s == 0)) for s in stocks for a in range(3)]
    )
    book = pd.DataFrame(dict(eom=month, permno=[0, 5, 6], weight=[0.01, 0.01, -0.01]))
    out = crowd_insights.overlap({"retail": picks}, book)["retail"]
    assert out["longs_in_favourites"] == pytest.approx(0.5)
    assert out["shorts_in_favourites"] == pytest.approx(0.0)


# V2A names itself; passing() reads the verdicts, grinold over costs.
def test_v2a_and_v2_pass(tmp_path, monkeypatch):
    assert v2.Settings(v2.V2A).name == "v2a@1e7"
    verdicts = dict(shorts=dict(passed=True), grinold=dict(passed=True), costs=dict(passed=True))
    (tmp_path / "evidence.json").write_text(json.dumps(dict(verdicts=verdicts)))
    monkeypatch.setattr(v2, "OUT", tmp_path)
    assert v2.passing() == frozenset({"shorts", "grinold"})


# The film's easing stays in bounds; the deck's Morph XML is valid.
def test_film_easing_and_deck_motion():
    import sys
    from types import SimpleNamespace

    from lxml import etree

    from fiam.report import animation

    assert animation.ease(-1) == 0 and animation.ease(2) == 1
    assert animation.fade(0.4, 0.0) < animation.fade(0.6, 0.0)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import motion

    assert etree.fromstring(motion.MORPH) is not None
    shapes = [SimpleNamespace(shape_id=i, has_text_frame=i % 2 == 0) for i in (2, 3, 4)]
    steps = motion.stagger(shapes, "zoom") + [(shapes[0], "wipe", 900)]
    film = SimpleNamespace(shape_id=9)
    timing = etree.fromstring(motion.timeline(steps, film))
    tags = timing.findall(".//{%s}cTn[@presetClass]" % motion.P)
    assert [t.get("presetClass") for t in tags].count("entr") == 4
    assert [t.get("presetClass") for t in tags].count("mediacall") == 1
