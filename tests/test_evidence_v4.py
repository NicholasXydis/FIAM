# Step 9 pre-freeze evidence on synthetic frames only.

import json

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import evidence as ev

N, NAV, RF = 252, 1e9, 0.00001
DAYS = pd.bdate_range("2017-01-02", periods=N)


# A daily frame from active returns, fees as a share of NAV (dollars).
def frame(active, cost=0.0, borrow=0.0) -> pd.DataFrame:
    ret = pd.Series(np.asarray(active) + RF - cost - borrow, index=DAYS[: len(active)])
    return pd.DataFrame({"ret": ret, "rf": RF, "cost": cost * NAV, "borrow": borrow * NAV,
                         "nav": NAV * (1 + ret)})  # fmt: skip


# Positions for a frame: two names held on each day.
def held(daily) -> pd.DataFrame:
    return pd.DataFrame([(d, p, 1e6) for d in daily.index for p in (1, 2)],
                        columns=["date", "permno", "value"])  # fmt: skip


# A sample of given mean and sample std exactly (so the IR is exact).
def exact(mean, std, n=N, seed=0) -> np.ndarray:
    x = np.random.default_rng(seed).standard_normal(n)
    return mean + std * (x - x.mean()) / x.std(ddof=1)


# One check's result from a fresh self-test on a daily frame.
def run(daily, name, **kw) -> dict:
    return ev.selftest(daily, held(daily), **kw)["checks"][name]


# Hit rate: 57% of days above the bill fires, 55% does not.
def test_hit_rate():
    for ups, fired in ((114, True), (110, False)):
        active = np.where(np.arange(200) < ups, 0.001, -0.001)
        got = run(frame(active), "hit_rate")
        assert got["fired"] is fired and got["threshold"] == 0.56
        assert got["value"] == pytest.approx(ups / 200)


# The IR before costs: costs and borrow come back, hurdle is rf + 4%.
def test_pre_cost_ir():
    hurdle = ev.PREMIUM / ev.YEAR
    for ir, fired in ((1.21, True), (1.19, False)):
        mean = ir / np.sqrt(252) * 0.005
        x = exact(mean, 0.005)
        got = run(frame(x + hurdle, cost=0.0004, borrow=0.0001), "pre_cost_ir")
        assert got["value"] == pytest.approx(ir) and got["fired"] is fired


# Costs are not added to a book that has none: the net IR matches.
def test_pre_cost_matches_net_without_costs():
    x = exact(0.0003, 0.005) + ev.PREMIUM / ev.YEAR
    got = run(frame(x), "pre_cost_ir")["value"]
    assert got == pytest.approx(exact(0.0003, 0.005).mean() / 0.005 * np.sqrt(252))


# The forecast IC passed in: 0.101 fires, 0.099 does not, none is noted.
def test_forecast_ic():
    daily = frame(exact(0, 0.005))
    assert run(daily, "forecast_ic", ic=0.101)["fired"] is True
    assert run(daily, "forecast_ic", ic=0.099)["fired"] is False
    got = run(daily, "forecast_ic")
    assert got["fired"] is False and got["value"] is None and got["note"]


# Ten days: a third of the P&L fires, just under does not.
def test_top_ten_days():
    for big, fired in ((4.7, True), (4.3, False)):
        active = np.full(100, 0.001)
        active[:10] = 0.001 * big
        got = run(frame(active), "top10_days")
        assert got["fired"] is fired and got["threshold"] == pytest.approx(1 / 3)


# A book that lost money has no share of its P&L to flag.
def test_top_days_needs_profit():
    got = run(frame(np.full(50, -0.001)), "top10_days")
    assert got["value"] is None and got["fired"] is False


# Ten names: the same bars on P&L per name; missing P&L is skipped.
def test_top_ten_names():
    daily = frame(exact(0, 0.005))
    for big, fired in ((4.7, True), (4.3, False)):
        pnl = pd.Series(np.where(np.arange(100) < 10, big, 1.0), index=range(100))
        assert run(daily, "top10_names", pnl=pnl)["fired"] is fired
    got = run(daily, "top10_names")
    assert got["fired"] is False and got["note"] == "needs name P&L"


# P&L per name: a value at a close earns the next session's return.
def test_name_pnl():
    pos = pd.DataFrame({"date": DAYS[:2].tolist() * 2, "permno": [1, 1, 2, 2],
                        "value": [100.0, 100.0, -50.0, -50.0]})  # fmt: skip
    rets = pd.DataFrame({1: [0.0, 0.1, 0.2], 2: [0.0, 0.1, -0.2]}, index=DAYS[:3])
    got = ev.name_pnl(pos, rets)
    assert got[1] == pytest.approx(100 * 0.1 + 100 * 0.2)
    assert got[2] == pytest.approx(-50 * 0.1 + -50 * -0.2)


# The idiosyncratic share is 1 - R^2: 0.905 fires, 0.895 does not.
def test_idiosyncratic_share():
    rng = np.random.default_rng(1)
    f = rng.standard_normal(N)
    e = rng.standard_normal(N)
    # The noise made orthogonal to the factor and the constant.
    x = np.column_stack([np.ones(N), f])
    e = e - x @ np.linalg.lstsq(x, e, rcond=None)[0]
    e = e / e.std()
    factors = pd.DataFrame({"mkt": f}, index=DAYS)
    for share, fired in ((0.905, True), (0.895, False)):
        k = np.sqrt((1 - share) / share) * e.std() / f.std()
        daily = frame(k * f + e)
        got = run(daily, "idiosyncratic_share", factors=factors)
        assert got["value"] == pytest.approx(share, abs=1e-6) and got["fired"] is fired
    got = run(frame(e), "idiosyncratic_share")
    assert got["fired"] is False and got["note"] == "not computed"


# The self-test lists what fired and reads a book without changing it.
def test_selftest_flags_only():
    active = np.where(np.arange(200) < 130, 0.002, -0.001)
    daily = frame(active)
    before = daily.copy()
    out = ev.selftest(daily, held(daily), ic=0.2)
    assert {"hit_rate", "forecast_ic"} <= set(out["fired"]) and out["any_fired"]
    pd.testing.assert_frame_equal(daily, before)
    assert out["book"]["names_held"] == 2


# A fake tree of step 6 and 7 results, names and counts only.
@pytest.fixture
def tree(tmp_path, monkeypatch):
    dirs = {k: tmp_path / k for k in ("gates", "forecast", "construct", "desk", "evidence")}
    for d in dirs.values():
        d.mkdir()
    stamp = {"run_utc": "2026-10-26T10:00:00+00:00"}
    gate = {"main": {}, "p_for_holm": 0.5}
    six = {k: gate for k in ev.SIX[:-1]} | {"customer_momentum": {"failed": "x"}}
    (dirs["gates"] / f"gates_{ev.GATES_AT}.json").write_text(
        json.dumps({"stamp": stamp, "gates": {"gates": six}})
    )
    cells = [{"leaves": 31, "children": c, "w_ml": 1, "horizon": 3, "stocks": "all"}
             for c in (2, 20, 200)]  # fmt: skip
    (dirs["forecast"] / "validate_abc123.json").write_text(
        json.dumps({"stamp": stamp, "validate": {"cells": cells}})
    )
    log = {
        "ridge_names": {"1": 480, "30": 480},
        "style_cap_shares": {"0.1": [0, 0]},
        "margin_costs": {"0.01": {}, "0.03": {}},
        "sector_band_tc": {"0.01": 0, "0.02": 0},
    }
    (dirs["construct"] / "settings_log.json").write_text(json.dumps(log))
    frame(exact(0, 0.005)).to_parquet(dirs["construct"] / "exam_daily_1_abc123.parquet")
    frame(exact(0, 0.005, 100)).to_parquet(dirs["construct"] / "exam_daily_2_abc123.parquet")
    for name in ("a0_daily_abc123", "arm_A1_abc123", "arm_A0_replay_abc123",
                 "arm_P1_20261800_abc123"):  # fmt: skip
        frame(exact(0, 0.005, 50)).to_parquet(dirs["desk"] / f"{name}.parquet")
    trials = tmp_path / "trials.csv"
    pd.DataFrame({"name": ["v1@1e9", "v2@1e9", "v2@5e9"]}).to_csv(trials, index=False)
    for attr, key in (("GATES", "gates"), ("FORECAST", "forecast"), ("CONSTRUCT", "construct"),
                      ("DESK", "desk"), ("OUT", "evidence")):  # fmt: skip
        monkeypatch.setattr(ev, attr, dirs[key])
    monkeypatch.setattr(ev, "V2_TRIALS", trials)
    return dirs


# One row per run, every count as the fake tree makes it.
def test_ledger_counts(tree):
    rows = ev.ledger()
    by = rows.groupby("kind")["status"].value_counts().to_dict()
    # Six gates (customer momentum not built) and two late ones not run.
    assert by[("gate", "run")] == 5 and by[("gate", "not built")] == 1
    assert by[("gate", "not run")] == 2
    assert (rows["kind"] == "model").sum() == 3
    # Current log: base, 2 ridges, 1 cap, 2 margins, the band's one new run.
    assert ((rows["kind"] == "setting") & (rows["status"] == "run")).sum() == 7
    # No void log kept: the grids as run, base plus 6, 5, 4 and 2.
    assert ((rows["kind"] == "setting") & (rows["status"] != "run")).sum() == 18
    assert by[("exam", "run")] == 2 and by[("exam", "not run")] == 5
    # A0, A1, one P1 seed ran; the replay is no arm; A2, 99 seeds left.
    assert by[("desk", "run")] == 3 and by[("desk", "not run")] == 100
    assert not rows["name"].str.contains("replay").any()
    assert rows["information_ratio"].isna().all()
    assert list(rows.columns) == ev.COLUMNS
    assert rows.loc[rows["kind"] == "exam", "days"].dropna().tolist() == [N, 100]


# A void log is marked by its commit and replaces the placeholders.
def test_ledger_void_log(tree):
    log = json.loads((tree["construct"] / "settings_log.json").read_text())
    (tree["construct"] / "settings_log_void.json").write_text(json.dumps(log | {"commit": "f00d"}))
    rows = ev.ledger()
    void = rows[rows["status"] == "void"]
    assert len(void) == 7 and void["name"].str.endswith("@f00d").all()
    assert not rows["status"].str.contains("not kept").any()


# The three counts and the CSV: v4 run, v1-v3 rows, and every fit.
def test_counts_and_csv(tree, monkeypatch):
    monkeypatch.setattr(ev, "older_fits", lambda: 1916)
    got = ev.run_ledger()
    rows = pd.read_csv(tree["evidence"] / "trials_v4.csv")
    assert got["v4"] == (rows["status"] != "not run").sum() == 5 + 1 + 3 + 7 + 18 + 2 + 3
    assert got["v1_v3"] == 3 and got["v4_v1_v3"] == got["v4"] + 3
    assert got["all"] == got["v4"] + 1916 and got["v4_not_run"] == 2 + 5 + 100


# The older count reads names only: past fits, runs, configs, Andrew.
def test_older_fits(tmp_path):
    exp = tmp_path / "exp"
    exp.mkdir()
    for n in ("a", "b"):
        (exp / f"{n}.csv").write_text("x\n")
    pd.DataFrame({"name": ["v1@1e9", "v2@1e9", "v2@5e9"]}).to_csv(tmp_path / "trials.csv")
    from fiam import stats
    from fiam.exhibits import evidence as old

    assert ev.older_fits(tmp_path, exp) == stats.TRIALS_PAST + 2 + old.ANDREW_TRIALS + 2


# The deflated Sharpe falls as the count rises, one entry per count.
def test_deflated_falls_with_count():
    x = pd.Series(exact(0.01, 0.03, 48), index=pd.period_range("2017-01", periods=48, freq="M"))
    got = ev.deflated(x, {"v4": 150, "v4_v1_v3": 700, "all": 2000})
    p = [got[k]["probability"] for k in ("v4", "v4_v1_v3", "all")]
    assert p[0] > p[1] > p[2] and all(0 <= v <= 1 for v in p)
    assert got["all"]["trials"] == 2000 and got["all"]["sr0_annual"] > got["v4"]["sr0_annual"]


# Days compound to months first, so the helper sees monthly returns.
def test_deflated_from_days():
    days = pd.bdate_range("2017-01-02", periods=4 * N)
    daily = pd.Series(exact(0.0005, 0.006, 4 * N, seed=3), index=days)
    months = ev.monthly(daily)
    assert len(months) == daily.index.to_period("M").nunique()
    got = ev.deflated(daily, {"a": 100, "b": 1000})
    assert got["a"]["probability"] > got["b"]["probability"]


# The code's constants match the runs they name.
def test_constants_match_the_runs():
    from fiam.v4 import gates
    from fiam.v4.construct import exam, settings

    assert set(ev.DESIGNS) == set(exam.DESIGNS)
    assert set(ev.LATE) == set(gates.LATE) and set(ev.SIX) == {*gates.SIGNALS, *gates.FAILED}
    assert ev.GATES_AT == gates.SIX
    assert (ev.GRIDS["ridge"], ev.GRIDS["style_cap"]) == (settings.RIDGES, settings.STYLE_CAPS)
    assert (ev.GRIDS["margin"], ev.GRIDS["sector_band"]) == (settings.MARGINS, settings.BANDS)
    assert ev.PREMIUM == exam.PREMIUM
