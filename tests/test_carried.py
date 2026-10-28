# The carried-results check: rules, headline, lock and the replay.

import gzip
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal import carried, daily_book, lock
from fiam.vfinal.report import table_9_1

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "final"
OUT = ROOT / "out" / "vfinal" / "final"


# Two years of sessions with returns, a bill and an S&P 500 beside.
def run_frames():
    rng = np.random.default_rng(7)
    days = pd.bdate_range("2020-12-31", "2022-12-30")
    sp = pd.Series(rng.normal(0.0004, 0.01, len(days)), index=days)
    ret = 0.2 * sp + rng.normal(0.0001, 0.004, len(days))
    ret.iloc[0] = 0.0
    month = days.to_period("M")
    rate = pd.Series(np.linspace(0.001, 0.04, month.nunique()), index=month.unique())
    rf = pd.Series(rate.reindex(month).to_numpy() / 252, index=days)
    daily = pd.DataFrame({"nav": 1e9 * (1 + ret).cumprod(), "ret": ret, "rf": rf})
    daily["cost"], daily["borrow"], daily["turnover"] = 1e4, 2e3, 0.01
    daily["gross"], daily["net"], daily["n_long"], daily["n_short"] = 1.5, 0.01, 130, 140
    daily["traded"] = daily.index.isin(days[1::21])
    trades = pd.DataFrame({"date": days[1::21], "formed": days[0:-1:21], "permno": 1})
    trades[["dollars", "after"]] = 1e6
    positions = pd.DataFrame({"date": days[1:], "permno": 1, "value": 1e7})
    return daily, trades, positions, sp, rf


# The recomputed rows are the 23-row table's own, digit for digit.
def test_headline_matches_the_table():
    daily, trades, positions, sp, rf = run_frames()
    monthly = (rf * 252 / 12).groupby(rf.index.to_period("M")).first()
    t = table_9_1.table(daily, trades, positions, sp, rf_monthly=monthly)
    cell = t.set_index("row")["strategy"]
    got = carried.headline(daily[["nav", "ret"]], rf, sp)
    assert got[1] == cell[1] and got[8] == cell[8] and got[11] == cell[11]
    assert got[3] == cell[3] and got[6] == cell[6] and got[7] == cell[7]
    assert got[23] == cell[23].split(";")[0]
    rows = t.astype({"strategy": str}).to_dict("records")
    assert all(ok for _, ok, _ in carried.headline_checks(got, rows))


# A month's bill counts once posted; the last takes the one before.
def test_bill_takes_the_last_posted_month(tmp_path):
    path = tmp_path / "TB3MS.csv"
    path.write_text("observation_date,TB3MS\n2026-06-01,3.66\n2026-07-01,3.73\n2026-08-01,3.72\n")
    days = pd.DatetimeIndex(["2026-07-31", "2026-08-03", "2026-08-31"])
    got = carried.daily_bill(days, path) * 252 * 100
    assert got.round(6).tolist() == [3.73, 3.73, 3.73]


# A carried book: three names a day, every limit read from the mandate.
def book(weights: list[float]) -> dict:
    days = pd.DatetimeIndex(["2020-12-31", "2021-01-04", "2021-01-05"])
    nav = pd.Series([1e9, 1e9, 1e9], index=days)
    rows = [(d, p, w) for d in days[1:] for p, w in zip((1, 2, 3), weights)]
    pos = pd.DataFrame(rows, columns=["date", "permno", "weight"])
    value = pos["weight"] * 1e9
    long = value.where(value > 0, 0.0).groupby(pos["date"]).sum().reindex(days).fillna(0.0)
    short = value.where(value < 0, 0.0).groupby(pos["date"]).sum().reindex(days).fillna(0.0)
    daily = pd.DataFrame({"nav": nav, "ret": 0.0, "interest": 0.0, "stock_pnl": 0.0}, index=days)
    daily[["dividends", "exits", "cost", "borrow"]] = 0.0
    daily["long_usd"], daily["short_usd"] = long, short
    daily[["gross_pre", "net_pre", "max_weight_pre", "max_company_weight"]] = 0.0
    daily["max_company_weight_pre"], daily["names_pre"] = np.nan, np.nan
    daily["short_floor_breaches"] = 0.0
    daily["formed"] = ["", "2020-12-31", ""]
    hold = pos[pos["date"] == days[1]]
    return {"daily": daily, "positions": pos, "holdings": hold}


# A name over the cap and too few names both fail; a clean book passes.
def test_limits_catch_a_breach():
    rules = daily_book.mandate() | {"names_min": 3, "names_max": 5}
    clean = carried.limits(book([0.04, -0.04, 0.01]), rules)
    assert all(ok for _, ok, _ in clean), [c for c in clean if not c[1]]
    heavy = {name: ok for name, ok, _ in carried.limits(book([0.06, -0.04, 0.01]), rules)}
    assert not heavy["at most 5% in one name"]
    few = {
        n: ok for n, ok, _ in carried.limits(book([0.04, -0.04, 0.01]), rules | {"names_min": 4})
    }
    assert not few["4 to 5 names at each close"]


# Weights at the close of d earn d+1; an unpriced name is counted.
def test_replay_earns_the_next_session():
    days = pd.DatetimeIndex(["2021-01-04", "2021-01-05", "2021-01-06"])
    daily = pd.DataFrame({"nav": [1e9, 2e9, 2e9], "stock_pnl": [0.0, 1e7, -3e6]}, index=days)
    pos = pd.DataFrame({"date": days[[0, 0, 1]], "permno": [1, 2, 1], "weight": [0.5, -0.25, 0.1]})
    rets = pd.DataFrame(
        {"permno": [1, 2, 1, 1], "date": days[[0, 1, 1, 2]], "r": [9.0, 0.0, 0.02, -0.015]}
    )
    got = carried.replay(daily, pos, rets)
    assert got.loc["2021-01-05", "replay"] == pytest.approx(1e9 * 0.5 * 0.02)
    assert got.loc["2021-01-06", "replay"] == pytest.approx(2e9 * 0.1 * -0.015)
    assert got["gap"].abs().max() < 1e-6 and got["no_row"].sum() == 0
    lines, verdict = carried.replay_report(got)
    assert verdict[1] and "2 of 2 days" in lines[-1]
    gone = carried.replay(daily, pos, rets.iloc[:2])
    assert gone.loc["2021-01-06", "no_row"] == 1 and gone.loc["2021-01-06", "replay"] == 0.0


# Changed and missing code fail; absent pinned outputs are only counted.
def test_lock_lines(tmp_path, monkeypatch):
    (tmp_path / "fiam").mkdir()
    (tmp_path / "fiam" / "a.py").write_text("a")
    (tmp_path / "fiam" / "b.py").write_text("b")
    lines = [f"{lock.digest(tmp_path / 'fiam' / 'a.py')}  fiam/a.py", f"{'0' * 64}  out/x.json"]
    sha = tmp_path / "vfinal.sha256"
    sha.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(lock, "SHA", sha)
    monkeypatch.setattr(lock, "code", lambda: ["fiam/a.py"])
    checks, notes = carried.lock_checks(tmp_path)
    assert [ok for _, ok, _ in checks] == [True] and "1 of 1" in checks[0][2]
    assert "1 pinned data files are absent" in notes[-1]
    (tmp_path / "fiam" / "a.py").write_text("changed")
    monkeypatch.setattr(lock, "code", lambda: ["fiam/a.py", "fiam/b.py"])
    checks, notes = carried.lock_checks(tmp_path)
    assert [ok for _, ok, _ in checks] == [False, False]
    assert "  changed since the lock: fiam/a.py" in notes
    assert "  not in the lock: fiam/b.py" in notes


# The tracked final/ passes every rule and gives the table's headline.
@pytest.mark.skipif(not (FINAL / "metrics.json").is_file(), reason="final/ is not here")
def test_carried_results_pass():
    c = carried.load(FINAL)
    checks = [carried.provenance(c["metrics"]), *carried.limits(c, daily_book.mandate())]
    rf = carried.daily_bill(c["daily"].index)
    checks += carried.headline_checks(
        carried.headline(c["daily"], rf, carried.sp500()), c["metrics"]["table_9_1"]
    )
    assert [c for c in checks if not c[1]] == []


# final/ is rebuilt byte for byte from the locked run's files.
@pytest.mark.skipif(not (OUT / "pick_eab2349a0ce1.json").is_file(), reason="no out/vfinal")
def test_final_rebuilds_from_the_lock(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "final_results", ROOT / "tools" / "final_results.py"
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    if not (tool.CARDS / "dsf.json").is_file():
        pytest.skip("the input cards are not here")
    written = tool.build(tmp_path)
    for path in written:
        name = path.relative_to(tmp_path)
        assert path.read_bytes() == (FINAL / name).read_bytes(), name
    with gzip.open(tmp_path / "positions_daily.csv.gz", "rt") as fh:
        assert fh.readline().strip() == "date,permno,weight"
