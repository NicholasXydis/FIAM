# The forecast models on synthetic data: bans, signs, purge, end to end.

import json

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import sources
from fiam.v4.forecast import dataset, grid, models

CHARS = ["o_score", "gp_at", "ret_12_1", "noa_at", "z1", "z2"]


# A has-data flag or a cost offered as an input is refused.
def test_flags_and_costs_are_refused():
    assert dataset.check_inputs([*CHARS, "syy", "sue_forecast"], CHARS)
    for bad in ("has_data", "cost_bps", "o_score_missing", "borrow_rate"):
        with pytest.raises(sources.NotForBacktest):
            dataset.check_inputs([*CHARS, bad], CHARS)


# Monotone: +1 on SYY-10 and the SUE forecast, SYY parts by sign.
def test_monotone_signs():
    got = models.monotone(["syy", "sue_forecast", "o_score", "gp_at", "ret_12_1", "noa_at", "z1"])
    assert got == [1, 1, -1, 0, 0, -1, 0]


# A synthetic table: 300 stocks, 2015-2020, a label driven by z1.
def fake_table(monkeypatch, n=300):
    rng = np.random.default_rng(7)
    rows = []
    for e in pd.date_range("2015-01-31", "2020-12-31", freq="ME"):
        base = rng.standard_normal((n, len(CHARS)))
        frame = pd.DataFrame(base, columns=CHARS).assign(permno=range(n), eom=e, T=e)
        frame["syy_raw"] = rng.standard_normal(n)
        frame["in_universe"] = np.arange(n) < 200
        frame["sector"] = np.where(np.arange(n) % 2 == 0, "10", "20")
        y = 0.5 * frame["z1"] + rng.standard_normal(n)
        for s in dataset.STOCKS:
            for h in grid.HORIZONS:
                frame[f"resid_rank_{s}_h{h}"] = y.rank(pct=True) * 2 - 1
        frame["resid_universe_h1"] = y
        frame["available_h1"] = e + pd.offsets.MonthEnd(1)
        frame["available_h3"] = e + pd.offsets.MonthEnd(3)
        frame["month_available_h1"] = e + pd.offsets.MonthEnd(2)
        frame["month_available_h3"] = e + pd.offsets.MonthEnd(4)
        frame["sue_target"] = 0.5 * frame["z2"] + rng.standard_normal(n)
        frame["sue_public"] = e + pd.offsets.MonthEnd(2)
        rows.append(frame)
    x = pd.concat(rows, ignore_index=True)
    t = object.__new__(grid.Table)
    t.chars, t.x, t.feats = CHARS, x, {}
    for s in dataset.STOCKS:
        f = dataset.ranked(x, [*CHARS, "syy_raw"], s).astype(np.float32)
        t.feats[s] = f.rename(columns={"syy_raw": "syy"})
    monkeypatch.setattr(grid, "close_of", lambda eom: pd.Timestamp(eom) + pd.offsets.MonthEnd(0))
    monkeypatch.setattr(models, "LEAVES", (7,))
    monkeypatch.setattr(models, "CHILDREN", (20,))
    monkeypatch.setattr(models, "ENET", [(0.001, 0.5)])
    monkeypatch.setattr(models, "NN_L1", (0.0001,))
    monkeypatch.setattr(models, "NN_SEEDS", range(1, 2))
    monkeypatch.setattr(models, "NN_EPOCHS", 2)
    monkeypatch.setattr(grid, "WEIGHTS", (0.5, 1.0))
    monkeypatch.setattr(grid, "TRAP_SEEDS", range(3))
    return t


# A fit's rows have labels public by its cut, never later.
def test_training_rows_are_purged(monkeypatch):
    t = fake_table(monkeypatch)
    cut = pd.Timestamp("2018-12-31")
    rows = grid.training_rows(t, "universe", 3, cut)
    assert (t.x.loc[rows, "month_available_h3"] <= cut).all()
    assert t.x.loc[rows, "eom"].max() == pd.Timestamp("2018-08-31")


# The blend: sector means are 0, and w = 0 is SYY-10 alone.
def test_blend(monkeypatch):
    t = fake_table(monkeypatch)
    rows = t.rows("universe", "2019-01-31", "2019-03-31", universe_only=True)
    ml = pd.Series(np.random.default_rng(1).standard_normal(len(rows)), index=rows)
    z = grid.blend(t, ml, 0.75)
    means = z.groupby([t.x.loc[rows, "eom"], t.x.loc[rows, "sector"]]).mean()
    assert np.allclose(means, 0, atol=1e-12)
    only = grid.blend(t, ml, 0.0)
    ranked = grid.month_rank(t, t.feats["universe"].loc[rows, "syy"])
    assert only.rank().corr(ranked.rank()) > 0.95


# The net repeats exactly for its seeds.
def test_net_repeats(monkeypatch):
    monkeypatch.setattr(models, "NN_SEEDS", range(1, 3))
    monkeypatch.setattr(models, "NN_EPOCHS", 2)
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.uniform(-1, 1, (500, 4)), columns=list("abcd"))
    y = x["a"].to_numpy() + rng.standard_normal(500) * 0.1
    a = models.predict(models.nn3(x, y, 0.0001), x)
    b = models.predict(models.nn3(x, y, 0.0001), x)
    assert np.array_equal(a, b)


# Validation, walk-forward and the noise trap run end to end.
def test_end_to_end(monkeypatch):
    t = fake_table(monkeypatch)
    v = grid.validate(t)
    assert v["sue_model"]["universe"]["passes"] and v["chosen"]["ic"] > 0.2
    v = json.loads(json.dumps(v, default=str))
    sue = {s: {"passes": r["passes"], "chosen": r["chosen"]} for s, r in v["sue_model"].items()}
    members = v["members"] | {"sue": sue}
    walked = grid.walk(t, v["chosen"], members)
    assert walked["eom"].min() == pd.Timestamp("2016-12-31")
    assert walked["eom"].max() == pd.Timestamp("2020-12-31")
    assert walked.groupby("eom").size().eq(200).all() and walked["z"].notna().all()
    trap = grid.trap(t, v["chosen"], members)
    assert len(trap["shares"]) == 3 and 0 <= trap["p95"] < 1


# Every fit in validate and walk sees only labels public by its cut.
def test_fits_only_see_public_labels(monkeypatch):
    t = fake_table(monkeypatch)
    seen, real = [], grid.training_rows

    # The real purge, with each call recorded.
    def spy(t_, stocks, horizon, cut):
        rows = real(t_, stocks, horizon, cut)
        seen.append((horizon, pd.Timestamp(cut), rows))
        return rows

    monkeypatch.setattr(grid, "training_rows", spy)
    v = json.loads(json.dumps(grid.validate(t), default=str))
    sue = {s: {"passes": r["passes"], "chosen": r["chosen"]} for s, r in v["sue_model"].items()}
    grid.walk(t, v["chosen"], v["members"] | {"sue": sue})
    for h, cut, rows in seen:
        assert (t.x.loc[rows, f"month_available_h{h}"] <= cut).all()
    last = {h: t.x.loc[r, "eom"].max() for h, c, r in seen if c == pd.Timestamp("2018-12-31")}
    assert last == {1: pd.Timestamp("2018-10-31"), 3: pd.Timestamp("2018-08-31")}


# A SUE target not yet public at the cut changes no fit's target rank.
def test_sue_rank_ignores_unpublished_targets(monkeypatch):
    t = fake_table(monkeypatch)
    # 2018-10's other targets are public by the cut, so look-ahead shows.
    late = (t.x["eom"] == pd.Timestamp("2018-10-31")) & (t.x["permno"] % 2 == 0)
    t.x.loc[late, "sue_public"] = pd.Timestamp("2019-03-31")
    before = grid.sue_column(t, "universe", 7, 20)
    t.x.loc[late, "sue_target"] = -100 * t.x.loc[late, "sue_target"]
    after = grid.sue_column(t, "universe", 7, 20)
    rows = t.rows("universe", "2018-12-31", "2019-11-30")
    assert np.array_equal(before.loc[rows], after.loc[rows])


# The inputs are the 147, SYY-10 and the SUE; a label is refused.
def test_inputs_are_exact(monkeypatch):
    t = fake_table(monkeypatch)
    off = {s: {"passes": False} for s in dataset.STOCKS}
    f = grid.inputs(t, "universe", off)
    assert list(f.columns) == [*CHARS, "syy"]
    leak = f.assign(resid_rank_universe_h1=t.x.loc[f.index, "resid_rank_universe_h1"])
    with pytest.raises(sources.NotForBacktest):
        grid.fit_members(t, leak, "universe", 1, pd.Timestamp("2018-12-31"), f.index[:5], [])


# The blend by hand at w = 0.5: z, mix, z again, then sector-demean.
def test_blend_by_hand(monkeypatch):
    t = fake_table(monkeypatch)
    rows = t.rows("universe", "2019-01-31", "2019-02-28", universe_only=True)
    ml = pd.Series(np.random.default_rng(2).standard_normal(len(rows)) ** 3, index=rows)
    x = t.x.loc[rows]

    # A within-month z-score.
    def z(v):
        return v.groupby(x["eom"]).transform(lambda g: (g - g.mean()) / g.std(ddof=0))

    mixed = z(0.5 * z(t.feats["universe"].loc[rows, "syy"]) + 0.5 * z(ml))
    want = mixed - mixed.groupby([x["eom"], x["sector"]]).transform("mean")
    assert np.allclose(grid.blend(t, ml, 0.5), want)


# The grid has 96 cells and LightGBM grows exactly 200 trees.
def test_grid_size_and_trees():
    n = len(models.LEAVES) * len(models.CHILDREN) * len(grid.WEIGHTS)
    assert n * len(grid.HORIZONS) * len(dataset.STOCKS) == 96
    rng = np.random.default_rng(3)
    x = pd.DataFrame(rng.uniform(-1, 1, (3000, 3)), columns=["syy", "gp_at", "z1"])
    model = models.lgbm(x, rng.standard_normal(3000), 7, 500)
    assert model.num_trees() == 200


# A missing score never wins the choice.
def test_missing_scores_never_win():
    assert grid.finite(float("nan")) == -np.inf and grid.finite(0.1) == 0.1


# One run per stage and commit; walk and trap need this commit's file.
def test_runner_needs_its_own_validate(monkeypatch, tmp_path):
    monkeypatch.setattr(grid, "OUT", tmp_path)
    with pytest.raises(SystemExit):
        grid.chosen_at("abc123")
    sha = grid.hashlib.sha256(grid.gates.PROTOCOL.read_bytes()).hexdigest()
    done = {"stamp": {"commit": "zzz999", "protocol_sha256": sha},
            "validate": {"chosen": {}, "members": {}, "sue_model": {}}}  # fmt: skip
    grid.result_path("validate", "abc123").write_text(json.dumps(done))
    with pytest.raises(SystemExit):
        grid.chosen_at("abc123")
    done["stamp"]["commit"] = "abc123"
    grid.result_path("validate", "abc123").write_text(json.dumps(done))
    assert grid.chosen_at("abc123")["members"] == {"sue": {}}
