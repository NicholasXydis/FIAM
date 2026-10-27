# The revised run's helpers: the bill, the SUE checks and the settings.

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from fiam.v4.construct import book, exam, optimizer
from tools import revised


# The month's bill is TB3MS / 1200 whatever the month's length.
def test_monthly_rate_is_the_pdf_bill():
    days = pd.bdate_range("2023-01-02", "2023-02-28")
    rf = pd.Series(np.where(days.month == 1, 0.045, 0.048) / 252, index=days)
    got = revised.monthly_rate(rf)
    assert np.allclose(got.to_numpy(), [0.045 / 12, 0.048 / 12])
    assert [str(p) for p in got.index] == ["2023-01", "2023-02"]


# A small SUE table: two rows public in 2020, one in 2021.
def sue_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    old = pd.DataFrame({
        "permno": [1, 2],
        "end": pd.to_datetime(["2020-03-31", "2020-09-30"]),
        "sue": [0.5, -1.0],
        "available_at": pd.to_datetime(["2020-05-01", "2020-11-02"], utc=True),
    })  # fmt: skip
    late = pd.DataFrame({
        "permno": [1],
        "end": pd.to_datetime(["2021-03-31"]),
        "sue": [2.0],
        "available_at": pd.to_datetime(["2021-05-03"], utc=True),
    })  # fmt: skip
    return old, pd.concat([late, old], ignore_index=True)


# A rebuilt table passes only if no row public by 2020 moved.
def test_same_before_flags_any_moved_row():
    old, new = sue_rows()
    assert revised.same_before(old, new)["sue_unchanged_before_2021"]
    moved = new.assign(sue=np.where(new["permno"] == 2, -0.9, new["sue"]))
    assert not revised.same_before(old, moved)["sue_unchanged_before_2021"]
    assert not revised.same_before(old, new.iloc[:2])["sue_unchanged_before_2021"]


# The joined table keeps sealed rows and adds only later public rows.
def test_joined_keeps_sealed_rows_and_adds_later_ones():
    old, new = sue_rows()
    moved = new.assign(sue=np.where(new["permno"] == 2, -0.9, new["sue"]))
    got = revised.joined(old, moved)
    assert revised.same_before(old, got)["sue_unchanged_before_2021"]
    assert len(got) == 3 and got.loc[got["permno"] == 2, "sue"].item() == -1.0
    assert got["end"].max() == pd.Timestamp("2021-03-31")


# Rows to 2020 take the pinned target; later rows keep the rebuilt one.
def test_pin_rows_keeps_sealed_targets():
    x = pd.DataFrame({
        "permno": [1, 2, 1],
        "eom": pd.to_datetime(["2020-08-31", "2020-10-31", "2021-03-31"]),
        "sue_target": [9.0, 9.0, 9.0],
        "sue_public": pd.to_datetime(["2021-01-05"] * 3),
    })  # fmt: skip
    pinned = pd.DataFrame({
        "permno": [1],
        "eom": pd.to_datetime(["2020-08-31"]),
        "sue_target": [0.3],
        "sue_public": pd.to_datetime(["2020-11-02"]),
    })  # fmt: skip
    got = revised.pin_rows(x, pinned)
    assert got["sue_target"].iloc[0] == 0.3 and np.isnan(got["sue_target"].iloc[1])
    assert got["sue_target"].iloc[2] == 9.0
    assert got["sue_public"].iloc[0] == pd.Timestamp("2020-11-02")
    assert pd.isna(got["sue_public"].iloc[1])


# Every formation trades at full speed; nothing else changes.
def test_settings_trade_at_full_speed(monkeypatch):
    base = optimizer.Settings(gross=1.5, ridge=30, risk_lambda=2.0, style_cap=0.2, speed=0.2)
    monkeypatch.setattr(exam, "settings_for", lambda k, s: lambda eom, x, cap: base)
    revised.install_settings(False)
    got = exam.settings_for(7, {})(None, None, 1.77)
    assert got.speed == 1.0 and replace(got, speed=0.2) == base


# Loose settings widen sectors and styles and keep everything else.
def test_loose_settings_widen_only_the_limits():
    base = optimizer.Settings(gross=1.5, ridge=30, risk_lambda=2.0, style_cap=0.2, speed=0.2)
    got = revised.changed(base, loose=True)
    assert (got.sector_band, got.style_cap, got.speed) == (0.05, 0.8, 1.0)
    assert replace(got, sector_band=0.01, style_cap=0.2, speed=0.2) == base


# Yearly blocks run December to November; quarterly ones split them.
def test_blocks_cover_every_formation_once():
    years, quarters = revised.blocks(12), revised.blocks(3)
    assert len(years) == 10 and len(quarters) == 40
    assert years[0] == (pd.Timestamp("2016-12-31"), pd.Timestamp("2017-11-30"))
    assert quarters[:2] == [(pd.Timestamp("2016-12-31"), pd.Timestamp("2017-02-28")),
                            (pd.Timestamp("2017-03-31"), pd.Timestamp("2017-05-31"))]  # fmt: skip
    assert quarters[-1][0] == pd.Timestamp("2026-09-30")


# The cadence and the limits follow the pre-2021 rules, ties tight.
def test_choices_follow_the_rules():
    assert revised.picked({"yearly": 0.02, "quarterly": 0.021}) == "quarterly"
    assert revised.picked({"yearly": 0.02, "quarterly": 0.02}) == "yearly"
    tight, loose = {"ir": -0.7, "breach_days": 0}, {"ir": -0.5, "breach_days": 0}
    assert revised.loose_wins(tight, loose)
    assert not revised.loose_wins(tight, {"ir": -0.7, "breach_days": 0})
    assert not revised.loose_wins(tight, {"ir": 0.4, "breach_days": 2})
    assert revised.loose_wins({"ir": 0.1, "breach_days": 1}, {"ir": -0.9, "breach_days": 0})


# Looser limits: sectors never tighten, size and value become capped.
def test_limits_keep_the_wider_sector_band(monkeypatch):
    for module, name in ((optimizer, "ladder"), (optimizer, "inputs"), (book, "align")):
        monkeypatch.setattr(module, name, getattr(module, name))
    revised.install_limits()
    s = optimizer.Settings(gross=1.5, ridge=30, risk_lambda=2.0, style_cap=0.8, sector_band=0.05)
    assert all(t.sector_band >= 0.05 for _, t in optimizer.ladder(s, False))
    assert optimizer.inputs.NEUTRAL == ()
    assert {"size", "value"} <= set(optimizer.inputs.CAPPED)


# Alpha aligned to the betas loses them and its mean, nothing else.
def test_align_betas_removes_only_betas():
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(size=(60, 3)), columns=["welch", "dimson", "beta_60m"])
    got = revised.align_betas(pd.Series(rng.normal(size=60)), x)
    for k in x.columns:
        assert abs(float(x[k] @ got)) < 1e-9
    assert abs(float(got.sum())) < 1e-9


# The command line takes each stage with its cadence and limits only.
def test_parse_checks_the_arguments():
    assert revised.parse(["forecasts", "quarterly"]) == ("forecasts", ("quarterly",))
    assert revised.parse(["book", "yearly", "loose"]) == ("book", ("yearly", "loose"))
    for bad in ([], ["book", "yearly"], ["early", "monthly", "tight"], ["pick", "yearly"]):
        with pytest.raises(SystemExit):
            revised.parse(bad)


# Books and reports go to their own folder; the rest stay shared.
def test_where_keeps_each_run_apart():
    head = "a" * 40
    assert (
        revised.where("early", ("yearly", "loose"), head).name
        == f"early_yearly_loose_{'a' * 12}.json"
    )
    assert (
        revised.where("book", ("quarterly", "tight"), head).parent.name == "revised_quarterly_tight"
    )


# The pick waits for every piece and then applies both rules.
def test_pick_follows_the_rules_and_lists_what_is_left(tmp_path, monkeypatch):
    monkeypatch.setattr(revised, "BASE", tmp_path)
    head = "b" * 40
    put = lambda stage, args, body: revised.where(stage, args, head).write_text(json.dumps(body))  # noqa: E731
    put("forecasts", ("yearly",), {"ic_2017_2020": 0.02})
    got = revised.pick(head)
    assert not got["final"] and got["cadence"] == "yearly" and "forecasts quarterly" in got["next"]
    put("forecasts", ("quarterly",), {"ic_2017_2020": 0.03})
    put("early", ("quarterly", "tight"), {"ir": -0.6, "breach_days": 0})
    put("early", ("quarterly", "loose"), {"ir": -0.4, "breach_days": 0})
    got = revised.pick(head)
    assert (got["cadence"], got["limits"]) == ("quarterly", "loose")
    assert got["next"] == ["book quarterly loose", "report quarterly loose"]
    for stage in ("book", "report"):
        path = revised.where(stage, ("quarterly", "loose"), head)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    assert revised.pick(head)["final"]
