# The global switch and its bundle on synthetic data.

import json

import numpy as np
import pandas as pd
import pytest

from fiam import data, v2, world
from fiam import mandate as M

GLOBAL = M.Mandate(
    name="t",
    gross=2.0,
    net=1.0,
    name_cap=0.10,
    sector=None,
    beta=None,
    risk=None,
    names_min=100,
    names_max=300,
    countries=("USA", "CAN"),
    country_cap=0.75,
)


# 1000 names, one in ten Canadian, so a 75% cap on the US has to bind.
@pytest.fixture
def month():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        dict(
            permno=range(1000),
            signal=rng.normal(size=1000),
            hedge_beta=1 + 0.3 * rng.normal(size=1000),
            sector=rng.choice(["10", "20", "30"], size=1000),
            prc=rng.uniform(5, 500, size=1000),
            country=np.where(np.arange(1000) % 10 == 0, "CAN", "USA"),
        )
    )


# Each country's share of the book's gross weight, to test the cap.
def shares(weights: pd.Series, month: pd.DataFrame) -> pd.Series:
    where = month.set_index("permno")["country"].reindex(weights.index)
    gross = weights.abs().groupby(where).sum()
    return gross / gross.sum()


# Off, the country column changes nothing; on, no country tops its cap.
def test_country_cap_only_with_the_switch(month):
    off = v2.optimize(month, None, v2.Settings(frozenset(), 1e7, GLOBAL))
    same = v2.optimize(month.drop(columns="country"), None, v2.Settings(frozenset(), 1e7, GLOBAL))
    assert off.index.equals(same.index) and np.allclose(off, same)
    assert shares(off, month)["USA"] > 0.75
    on = v2.optimize(month, None, v2.Settings(frozenset({"global"}), 1e7, GLOBAL))
    assert shares(on, month).max() <= 0.75 + 0.005
    assert on.sum() == pytest.approx(1.0, abs=0.005)
    info = month.set_index("permno")
    gaps = v2.breaches(on, info, v2.Settings(frozenset({"global"}), 1e7, GLOBAL))
    assert gaps["breach_max"] == 0.0


# A foreign finals layout maps to ours: US PERMNOs kept, CAD converted.
def test_world_bundle_from_a_foreign_layout(tmp_path, monkeypatch):
    # The bundle reader with blind mode off, so every year reads.
    monkeypatch.delenv("FIAM_BLIND", raising=False)
    months = pd.date_range("2024-01-31", periods=3, freq="ME")
    rows = []
    for i, eom in enumerate(months):
        rows += [
            dict(
                gid="crsp_10001", date=eom, excntry="usa", r=0.01 * (i + 1), me=500.0, permno=10001
            ),
            dict(gid="comp_77_01C", date=eom, excntry="CAN", r=0.02, me=1000.0, cur="CAD"),
        ]
    source = tmp_path / "finals"
    source.mkdir()
    pd.DataFrame(rows).to_csv(source / "panel.csv", index=False)
    fx = pd.DataFrame(
        dict(date=[*months, months[-1] + pd.offsets.MonthEnd(1)], currency="CAD", usd_per_unit=0.5)
    )
    fx.loc[1, "usd_per_unit"] = 1.0
    fx.to_csv(tmp_path / "fx.csv", index=False)
    columns = {
        "id": "gid",
        "eom": "date",
        "return": "r",
        "currency": "cur",
        "fx_file": str(tmp_path / "fx.csv"),
        "first": "2020-01-31",
    }
    (source / "columns.json").write_text(json.dumps(columns), encoding="utf-8")
    out = tmp_path / "bundle"
    report = world.build(source, out)
    assert report["countries"] == {"CAN": 3, "USA": 3}
    features = data.read(out / data.FEATURES.name)
    assert set(world.SCHEMA["features"]) <= set(features.columns) | {data.TARGET}
    ids = features.groupby("country")["permno"].first()
    assert ids["USA"] == 10001 and ids["CAN"] >= world.FIRST_ID
    can = features[features["country"] == "CAN"].set_index("eom")["me"]
    assert can.tolist() == [500.0, 1000.0, 500.0]
    paid = data.read(out / data.LABELS.name).merge(features, on=data.KEYS)
    first = paid[(paid["country"] == "CAN") & (paid["eom"] == months[0])]
    assert first["next_month_excess_return"].iloc[0] == pytest.approx(1.02 * 1.0 / 0.5 - 1)
    assert len(world.market(out, ("USA", "CAN"))) == 3
    held = pd.DataFrame(dict(eom=months[0], permno=[10001, ids["CAN"]], weight=[0.6, -0.2]))
    assert world.country_weights(held, out).iloc[0].to_dict() == pytest.approx(
        dict(CAN=0.25, USA=0.75)
    )


# Day-of options: a hurdle is checked, a window read from FIAM_WINDOW.
def test_hurdle_and_window(monkeypatch):
    assert "hurdle" in " ".join(M.check(M.Mandate(hurdle=0.9)))
    assert M.check(M.Mandate(hurdle=0.05)) == []
    monkeypatch.setenv("FIAM_WINDOW", "2019-06-15,2025-05")
    assert v2.finals_window() == ("2019-06-30", "2025-05-31")
    monkeypatch.delenv("FIAM_WINDOW")
    assert v2.finals_window() == v2.RECORD


# Entry rules: sector name or code, unknown refused, a no-op by default.
def test_entry_rules(tmp_path, month):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(dict(exclude_sectors=["Energy", "45"], min_market_cap=500)))
    rules = M.load(path)
    assert rules.exclude_sectors == ("10", "45") and M.check(rules) == []
    assert "unknown sectors" in " ".join(M.check(M.Mandate(exclude_sectors=("99",))))
    frame = month.assign(me=np.arange(1000) * 1.0, sector=np.where(np.arange(1000) % 2, "10", "20"))
    kept = v2.admitted(frame, rules)
    assert (kept["me"] >= 500).all() and set(kept["sector"]) == {"20"}
    assert v2.admitted(frame, M.Mandate()) is frame


# Pinned Fed rates cover every switch currency through September 2026.
def test_pinned_exchange_rates():
    months = pd.DatetimeIndex(["2015-01-31", "2026-09-30"])
    rates = world.usd_per_unit({}, sorted(world.FED), months)
    assert rates.notna().all().all() and 0.6 < rates.loc["2026-09-30", "CAD"] < 0.8
