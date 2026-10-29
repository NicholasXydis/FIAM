# The fund: past-only inputs, guards, caps and the checks.

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal import checks, config
from fiam.vfinal.execution import hook
from fiam.vfinal.forecast import inputs, midmonth, pool, regime

# The two books' settings as the saved run files hold them.
LOCKED = json.loads(
    '{"el_plus_bwf_lag": {"name": "el_plus_bwf_lag", "overlay": {"blend": 0.0, "stripped": '
    'false, "core": "p1_d69", "vol_target": null, "vol_window": 63, "gross_to": null, '
    '"brake_at": null, "brake_exit": null, "brake_scale": 0.5, "hrp": null, "plus": true, '
    '"biweekly": "fresh", "sue": 0.0, "rho_floor": null, "scale_k": null, "scale_cap": 1.95, '
    '"squeeze": false, "squeeze_mode": "both"}, "execution": {"sessions": 5, "participation": '
    '0.1, "gross_guard": 1.92, "gross_trim_to": 1.8, "trim_at": 0.0475, "trim_to": 0.0425, '
    '"short_hold_musd": 550.0, "lag_guard": true}, "policy": {"names_min": 200, "names_max": '
    '500, "name_cap": 0.05, "net_band": 0.5, "nav0": 1000000000.0, "premium": 0.04, '
    '"beta_band": 0.02, "sector_band": 0.01, "participation": 0.1, "days_to_exit_max": 5, '
    '"position_cap": 0.0425, "position_cap_short": 0.01, "position_min": 0.001, "impact_y": '
    '1.0, "borrow_flat_other": 0.05, "forecaster_scale": 0.04841426765809828, '
    '"forecaster_kappa": 0.00217388862207945, "target_gross": 1.8, "risk_aversion": 1.0, '
    '"uncertainty_scale": 0.25, "beta_penalty": 10.0, "vol_target": 0.12, '
    '"vol_target_risk_aversion": 0.25, "style_band_share": 0.25, "beta_bands_extra": '
    '["welch_dimson", "beta_60m"]}}, "bw_fresh_lag": {"name": "bw_fresh_lag", "overlay": '
    '{"blend": 0.0, "stripped": false, "core": "el_plus_bwf_lag", "vol_target": null, '
    '"vol_window": 63, "gross_to": null, "brake_at": null, "brake_exit": null, "brake_scale": '
    '0.5, "hrp": null, "plus": false, "biweekly": "fresh", "sue": 0.0, "rho_floor": null, '
    '"scale_k": 1.08, "scale_cap": 1.88, "squeeze": false, "squeeze_mode": "both"}, '
    '"execution": {"sessions": 5, "participation": 0.1, "gross_guard": 1.9, "gross_trim_to": '
    '1.85, "trim_at": 0.044, "trim_to": 0.039, "short_hold_musd": 550.0, "lag_guard": true}, '
    '"policy": {"names_min": 200, "names_max": 500, "name_cap": 0.05, "net_band": 0.5, '
    '"nav0": 1000000000.0, "premium": 0.04, "beta_band": 0.02, "sector_band": 0.01, '
    '"participation": 0.1, "days_to_exit_max": 5, "position_cap": 0.039, '
    '"position_cap_short": 0.0108, "position_min": 0.001, "impact_y": 1.0, '
    '"borrow_flat_other": 0.05, "forecaster_scale": 0.04841426765809828, "forecaster_kappa": '
    '0.00217388862207945, "target_gross": 1.8, "risk_aversion": 1.0, "uncertainty_scale": '
    '0.25, "beta_penalty": 10.0, "vol_target": 0.12, "vol_target_risk_aversion": 0.25, '
    '"style_band_share": 0.25, "beta_bands_extra": ["welch_dimson", "beta_60m"]}}}'
)


# The config gives both locked books, and the lock's recipe if present.
def test_config_equals_locked_recipe():
    for name, ref in LOCKED.items():
        assert config.mismatches(config.RUNS[name], ref) == []
    recipe = config.FROZEN / "recipe.json"
    if recipe.exists():
        assert json.loads(recipe.read_text()) == json.loads(json.dumps(config.recipe()))


# A change to any setting shows up as a mismatch.
def test_config_mismatch_is_seen():
    from dataclasses import replace

    moved = replace(config.BOOK, execution=replace(config.BOOK.execution, trim_at=0.045))
    assert config.mismatches(moved, LOCKED["bw_fresh_lag"]) == ["execution.trim_at"]


# A synthetic panel: months of names with a few characteristics.
def synthetic_panel(months: int = 30, names: int = 260, chars: int = 6, seed: int = 0):
    rng = np.random.default_rng(seed)
    eoms = pd.date_range("2014-01-31", periods=months, freq="ME")
    cols = ["rvol_21d", *(f"c{k}" for k in range(1, chars))]
    rows = []
    for e in eoms:
        x = rng.normal(size=(names, chars))
        ret = 0.02 * x[:, 0] - 0.01 * x[:, 1] + rng.normal(0, 0.08, names)
        frame = pd.DataFrame(x, columns=cols)
        frame.insert(0, "eom", e)
        frame.insert(0, "permno", np.arange(10000, 10000 + names))
        frame["me"] = rng.uniform(500, 50000, names)
        frame["me_company"] = frame["me"]
        frame["prc"] = rng.uniform(10, 200, names)
        frame["dolvol_126d"] = 5e7
        frame["gics"] = 10101010.0
        frame["ret_exc_lead1m"] = ret
        frame["beta_60m"] = rng.uniform(0.5, 1.5, names)
        frame["exchcd"] = 1.0
        rows.append(frame)
    return pd.concat(rows, ignore_index=True), [*cols, "beta_60m"]


# Points the forecast's data reads at a synthetic panel on disk.
@pytest.fixture
def panel_on_disk(tmp_path, monkeypatch):
    p, chars = synthetic_panel()
    p.to_parquet(tmp_path / "panel.parquet", index=False)
    pd.DataFrame({"variable": chars}).to_csv(tmp_path / "chars.csv", index=False)
    monkeypatch.setattr(config, "PANEL", tmp_path / "panel.parquet")
    monkeypatch.setattr(config, "CHARS", tmp_path / "chars.csv")
    return p


# Training rows cut at r equal the full frame's rows dated by r.
def test_training_rows_cut_at_r_match_the_full_frame(panel_on_disk):
    r = pd.Timestamp("2015-06-30")
    full = inputs.frame("resrank", pd.Timestamp("2016-12-31"))
    cut = inputs.frame("resrank", r)
    early = full[pd.to_datetime(full["date"]) <= r].reset_index(drop=True)
    pd.testing.assert_frame_equal(cut, early)
    assert pd.to_datetime(cut["date"]).max() <= r


# One refit gives the same forecast with or without rows after r.
def test_walkforward_refit_reads_only_rows_dated_by_r(panel_on_disk, tmp_path):
    r = pd.Timestamp("2015-10-31")
    train = inputs.frame("resrank", pd.Timestamp("2016-06-30"))
    feats = inputs.features(pd.Timestamp("2015-10-31"), pd.Timestamp("2015-10-31"))
    feats["date"] = pd.to_datetime(feats["date"]).astype("datetime64[ns]")
    got = []
    for keep_future in (True, False):
        data = train if keep_future else train[pd.to_datetime(train["date"]) <= r]
        parts = tmp_path / f"parts_{keep_future}"
        parts.mkdir()
        pool._STATE.update(data=data, dates=pd.to_datetime(data["date"]), feats=feats,
                           parts=parts)  # fmt: skip
        pool.fit_one(str(r.date()), str((r + pd.offsets.MonthEnd(1)).date()))
        got.append(pd.read_parquet(parts / f"forecast_{r:%Y%m%d}.parquet"))
    assert len(got[0]) > 200
    pd.testing.assert_frame_equal(got[0], got[1])


# A synthetic IC and market state, long enough to pass the warmup.
def synthetic_state(n: int = 60, seed: int = 3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2017-01-31", periods=n, freq="ME")
    ic = pd.Series(rng.normal(0.03, 0.05, n), index=idx)
    state = pd.DataFrame({"corr_share": rng.uniform(0.1, 0.5, n),
                          "hml12": rng.normal(0, 0.1, n)}, index=idx)  # fmt: skip
    return ic, state


# Rho at t ignores the ICs of t-1 and t, whose labels are still open.
def test_rho_reads_only_closed_ics():
    ic, state = synthetic_state()
    full = regime.rho_series(ic, state)["rho"]
    assert (full.iloc[40:] != 1.0).any()
    for t in ic.index[30:]:
        x = ic.loc[:t].copy()
        x.iloc[-1] = 9.0
        x.iloc[-2] = -9.0
        assert regime.rho_series(x, state.loc[:t])["rho"].iloc[-1] == full.loc[t]


# The mid-month inputs at T ignore every session after T.
def test_mid_month_inputs_read_only_the_past():
    rng = np.random.default_rng(2)
    days = pd.bdate_range("2024-01-01", periods=60)
    rets = pd.DataFrame(rng.normal(0, 0.02, size=(60, 5)), index=days, columns=range(5))
    mkt = pd.Series(rng.normal(0, 0.01, 60), index=days)
    T = days[40]
    before = midmonth.refresh(rets, mkt, T)
    later, lmkt = rets.copy(), mkt.copy()
    later.loc[later.index > T] = 0.5
    lmkt.loc[lmkt.index > T] = 0.3
    pd.testing.assert_frame_equal(midmonth.refresh(later, lmkt, T), before)
    moved = rets.copy()
    moved.loc[T] += 0.1
    assert not midmonth.refresh(moved, mkt, T).equals(before)


# The mid-month score reads its month end's weights and rows only.
def test_mid_month_score_ignores_other_months(panel_on_disk, tmp_path):
    train = inputs.frame("resrank", pd.Timestamp("2016-06-30"))
    feats = inputs.features(pd.Timestamp("2015-08-31"), pd.Timestamp("2015-09-30"))
    feats["date"] = pd.to_datetime(feats["date"]).astype("datetime64[ns]")
    r = pd.Timestamp("2015-08-31")
    pool._STATE.update(data=train, dates=pd.to_datetime(train["date"]), feats=feats,
                       parts=tmp_path)  # fmt: skip
    pool.fit_one(str(r.date()), str((r + pd.offsets.MonthEnd(1)).date()))
    names = feats["permno"].unique()
    raw = pd.DataFrame({"permno": names, "rvol_21d": np.linspace(0.01, 0.05, len(names))})
    raw = raw.assign(eom=r, T=pd.Timestamp("2015-09-15"))
    rho = pd.Series([0.7, 0.9], index=[r, r + pd.offsets.MonthEnd(1)])
    base = midmonth.score(raw, feats, tmp_path, rho)
    later = feats.copy()
    later.loc[later["date"] > r + pd.offsets.MonthEnd(1), "c1"] = 99.0
    again = midmonth.score(raw, later, tmp_path, rho)
    pd.testing.assert_frame_equal(base, again)
    assert (base["rho"] == 0.7).all()


# The mid-month review falls on the first session from the 15th.
def test_mid_month_closes_follow_their_month_end():
    from fiam.vfinal.construct import formation

    try:
        mids = formation.mid_months(formation.eoms())
    except OSError, ValueError:
        pytest.skip("no trading calendar in this clone")
    for eom, T in mids.items():
        assert eom < T <= eom + pd.offsets.MonthEnd(1)
        assert T.day >= 15


# A book stub: today's values and a cap for every short, asked by day.
def stub_book(values: dict, cap: float = 50_000.0, asked: list | None = None):
    # The cap, noting the day asked for.
    def cap_at(p, d):
        if asked is not None:
            asked.append(d)
        return cap

    return SimpleNamespace(values=values, m=SimpleNamespace(cap_at=cap_at))


# The hook's own state, the book's execution, no world behind it.
def stub_hook(run=config.BOOK):
    days = pd.bdate_range("2024-01-01", "2024-02-01")
    return SimpleNamespace(x=run.execution, wanted={}, days=days)


# The gross guard reads the previous close, never today's marks.
def test_gross_guard_reads_previous_close():
    closing, today = {1: 0.95e9, 2: -0.90e9}, {1: 1.10e9, 2: -0.95e9}
    assert abs(hook.guard_gross(True, today, 1e9, closing, 1e9) - 1.85) < 1e-12
    assert abs(hook.guard_gross(False, today, 1e9, closing, 1e9) - 2.05) < 1e-12
    assert hook.guard_gross(True, today, 1e9, {}, None) == 0.0
    assert config.CORE.execution.lag_guard and config.BOOK.execution.lag_guard


# The long trim reads the last close: today's jump trims nothing.
def test_name_trim_reads_previous_close():
    h = stub_hook()
    d = h.days[5]
    today = {1: 60e6}
    got = hook.Hook.forced(h, d, stub_book(today), {1: 40e6}, 1e9, 1.0e9)
    assert got == {}
    got = hook.Hook.forced(h, d, stub_book({1: 30e6}), {1: 45e6}, 1e9, 1.0e9)
    assert set(got) == {1} and abs(got[1] - 0.039 * 1.0e9) < 1e-6


# A short's cap is read at the previous session, covered under $550m.
def test_short_cover_reads_previous_session():
    h = stub_hook()
    asked = []
    got = hook.Hook.forced(h, h.days[5], stub_book({7: -9e6}, 540.0, asked), {}, 1e9, 1e9)
    assert got == {7: 0.0} and asked == [h.days[4]]
    got = hook.Hook.forced(h, h.days[5], stub_book({7: -9e6}, 560.0), {}, 1e9, 1e9)
    assert got == {}


# A trim never lifts a name the working plan already holds lower.
def test_trim_keeps_lower_plan():
    h = stub_hook()
    h.wanted = {1: 30e6}
    got = hook.Hook.forced(h, h.days[5], stub_book({1: 49e6}), {1: 49e6}, 1e9, 1e9)
    assert got[1] == 30e6


# The scale is k unless the formation gross would pass its cap.
def test_scale_keeps_formation_gross_under_cap():
    ov = config.BOOK.overlay
    w = pd.Series([0.4, 0.4, -0.4, -0.4])
    assert hook.scale(w, ov) == 1.08
    big = pd.Series([0.9, 0.9, -0.9, -0.9]) / 2 * 1.9 / 1.8
    s = hook.scale(big, ov)
    assert abs((big * s).abs().sum() - 1.88) < 1e-12
    assert hook.scale(w, config.CORE.overlay) == 1.0


# Scaled targets clip longs at 3.9% and shorts at 1.08%.
def test_targets_clip_to_the_caps():
    p = config.BOOK.policy
    w = pd.Series([0.045, 0.02, -0.012, -0.005]) * 1.08
    got = hook.clip(w, p.position_cap, p.position_cap_short)
    assert got.max() == 0.039 and got.min() == -0.0108
    assert got.iloc[1] == w.iloc[1] and got.iloc[3] == w.iloc[3]


# A clean synthetic book: 220 names over 11 sectors, inside every rule.
def clean_book():
    days = pd.bdate_range("2020-12-31", "2021-03-31")
    names = list(range(1, 221))
    side = np.where(np.arange(220) % 2 == 0, 1.0, -1.0)
    nav = pd.Series(1e9, index=days)
    rows = [(d, p, s * 0.004 * 1e9) for d in days[1:] for p, s in zip(names, side)]
    positions = pd.DataFrame(rows, columns=["date", "permno", "value"])
    rng = np.random.default_rng(5)
    ret = pd.Series(rng.normal(0.0002, 0.002, len(days)), index=days)
    ret.iloc[0] = 0.0
    daily = pd.DataFrame({"nav": 1e9 * (1 + ret).cumprod(), "nav_pre": nav, "ret": ret})
    daily["nav"] = 1e9
    daily["nav_pre"] = 1e9
    T = [days[0], days[20]]
    targets = pd.DataFrame([(t, p, s * 0.004) for t in T for p, s in zip(names, side)],
                           columns=["T", "permno", "target"])  # fmt: skip
    trades = pd.DataFrame({"date": [days[2], days[22]], "formed": T})
    caps = pd.DataFrame({"date": [days[1]], "permno": [2], "me": [5000.0]})
    rets = pd.DataFrame(0.0, index=days, columns=names)
    eoms = pd.date_range("2020-11-30", "2021-03-31", freq="ME")
    panel = pd.DataFrame([(p, e, 10.0 + (p % 11), 0, 5000.0) for e in eoms for p in names],
                         columns=["permno", "eom", "gics", "sic", "me"])  # fmt: skip
    panel["gics"] = (panel["gics"] * 1e6).astype(float)
    return positions, daily, targets, trades, caps, rets, panel


# The independent check passes a clean book and flags a planted breach.
def test_checker_flags_planted_breach():
    positions, daily, targets, trades, caps, rets, panel = clean_book()
    clean = checks.finals(positions, daily, targets, trades, caps, rets, panel)
    assert clean["violations"] == [] and clean["breaches"] == 0
    planted = positions.copy()
    hit = (planted["date"] == planted["date"].iloc[500]) & (planted["permno"] == 1)
    planted.loc[hit, "value"] = 0.06e9
    got = checks.finals(planted, daily, targets, trades, caps, rets, panel)
    assert "single_position" in got["violations"] and got["days_any_name_over_5pct"] >= 1
    early = trades.assign(date=trades["formed"])
    got = checks.finals(positions, daily, targets, early, caps, rets, panel)
    assert "look_ahead" in got["violations"]
    small = targets.copy()
    panel2 = panel.copy()
    panel2.loc[panel2["permno"] == 2, "me"] = 300.0
    got = checks.finals(positions, daily, small, trades, caps, rets, panel2)
    assert "short_floor_formation" in got["violations"]


# A short window of both books matches the locked full run day by day.
def test_smoke_short_window_matches_full_run(monkeypatch, tmp_path):
    from fiam.vfinal import book, sources, unseal

    have = [config.CACHE / "risk.pkl", config.FORECAST / "mid_month.parquet",
            config.folder(config.BOOK.name) / "daily.parquet"]  # fmt: skip
    if not all(p.exists() for p in have):
        pytest.skip("no vfinal build in this clone")
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    if not sources.unsealed():
        pytest.skip("the data gate is closed in this clone")
    full = {n: config.folder(n) for n in config.RUNS}
    monkeypatch.setattr(config, "folder", lambda name: tmp_path / name)
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    for n in config.RUNS:
        (tmp_path / n).mkdir()
    # Ends mid-month: a month's dividend true-up books at its month end.
    end = "2021-03-05"
    with unseal.opened():
        book.run(config.CORE.name, end=end)
        book.run(config.BOOK.name, end=end)
    for n in config.RUNS:
        a = pd.read_parquet(tmp_path / n / "daily.parquet")
        b = pd.read_parquet(full[n] / "daily.parquet").loc[a.index]
        assert len(a) > 30
        assert float((a["nav"] - b["nav"]).abs().max()) == 0.0
        ta = pd.read_parquet(tmp_path / n / "targets.parquet")
        tb = pd.read_parquet(full[n] / "targets.parquet")
        tb = tb[tb["T"].isin(ta["T"].unique())].reset_index(drop=True)
        pd.testing.assert_frame_equal(ta, tb)


# The data gate opens only with the record and a lock that verifies.
def test_gate_needs_the_record_and_the_lock(tmp_path, monkeypatch):
    from fiam.vfinal import lock

    code = tmp_path / "a.py"
    code.write_text("a")
    record = tmp_path / "opened.json"
    record.write_text(json.dumps({k: "x" for k in lock.FIELDS}))
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps(config.recipe()))
    sha = tmp_path / "vfinal.sha256"
    sha.write_text(f"{lock.digest(code)}  a.py\n")
    for name, value in (("SHA", sha), ("OPENED", record), ("RECIPE", recipe)):
        monkeypatch.setattr(lock, name, value)
    monkeypatch.setattr(lock.config, "ROOT", tmp_path)
    monkeypatch.setattr(lock, "code", lambda: ["a.py"])
    monkeypatch.setattr(lock, "kept", lambda: [])
    assert lock.opened()
    code.write_text("b")
    assert not lock.opened()
    code.write_text("a")
    record.write_text(json.dumps({"window": "x"}))
    assert not lock.opened()
    with pytest.raises(SystemExit):
        lock.lock({})
