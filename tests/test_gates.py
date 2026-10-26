# The step 6 gate machinery and the five signals on synthetic data.

import dataclasses
import json
import subprocess

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import agreement, data, gates, sources
from fiam.v4.signals import (
    base,
    best_ideas,
    edgar_flags,
    insiders,
    lazy_prices,
    short_interest,
)

DAY = pd.Timestamp


# The vectorised Newey-West t equals the reference one, row by row.
def test_nw_t_rows_matches_agreement():
    y = np.random.default_rng(0).standard_normal((5, 70))
    got = gates.nw_t_rows(y)
    want = [agreement.nw_t(pd.Series(r)) for r in y]
    assert np.allclose(got, want, atol=1e-10)


# The simulated nulls repeat exactly; an AR(1) null is the stricter.
def test_nulls_repeat_and_autocorrelation_raises_the_bar():
    a, b = gates.null_t(70, series=20_000), gates.null_t(70, series=20_000)
    assert np.array_equal(a, b)
    ar = gates.null_t(70, 0.5, series=20_000)
    assert np.quantile(ar, 1 - gates.HOLM[0]) > np.quantile(a, 1 - gates.HOLM[0])


# The larger of the two p-values counts; a negative rho is floored at 0.
def test_series_takes_the_larger_p(monkeypatch):
    monkeypatch.setattr(gates, "NULL_SERIES", 20_000)
    rng = np.random.default_rng(1)
    smooth = pd.Series(np.cumsum(rng.standard_normal(70)) * 0.01 + 0.02)
    res = gates.test_series(smooth)
    assert res["p"] == max(res["p_iid"], res["p_ar1"]) and 0 < res["rho"] <= gates.RHO_CAP
    flip = pd.Series(np.tile([0.03, -0.01], 35))
    assert gates.test_series(flip)["rho"] == 0.0
    # Were the AR(1) null the narrower, the iid p would still count.
    real = gates.null_t
    monkeypatch.setattr(
        gates, "null_t", lambda n, rho=0.0, series=None: real(n, 0.0, series) * (0.5 if rho else 1)
    )
    res = gates.test_series(smooth)
    assert res["p"] == res["p_iid"] > res["p_ar1"]


# Holm steps down: once one sorted p misses its bar, every later fails.
def test_holm_step_down():
    got = gates.holm({"a": 0.001, "b": 0.009, "c": 0.02, "d": 0.004, "e": 1.0, "f": 1.0})
    assert got["a"]["passes"] and got["d"]["passes"] and got["b"]["passes"]
    assert not got["c"]["passes"] and not got["e"]["passes"]
    assert got["a"]["bar"] == pytest.approx(0.05 / 6)


# The runner refuses an uncommitted tree before any gate runs.
def test_runner_refuses_a_dirty_tree(monkeypatch):
    done = subprocess.CompletedProcess([], 0, stdout=" M fiam/v4/gates.py\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: done)
    with pytest.raises(RuntimeError):
        gates.commit()


# A residualised signal is orthogonal to the design; uncovered at 0.
def test_month_residual_is_orthogonal():
    rng = np.random.default_rng(2)
    m = object.__new__(gates.Month)
    m.ids = list(range(300))
    m.x = pd.DataFrame(rng.standard_normal((300, 4)), index=m.ids, columns=["a", "b", "c", "d"])
    m.x.insert(0, "const", 1.0)
    v = pd.Series(rng.standard_normal(300), index=m.ids)
    v.iloc[:40] = np.nan
    r = m.residual(v, -1)
    assert np.abs(m.x.loc[r.index].T.to_numpy() @ r.to_numpy()).max() < 1e-8
    z = m.residual(v, -1, zero_uncovered=True)
    assert (z.iloc[:40] == 0).all() and len(z) == 300


# Labels never reach a feature reader; only their purpose opens them.
def test_labels_cannot_be_read_as_a_feature():
    with pytest.raises(sources.NotForBacktest):
        sources.read("labels", ["label"], purpose="model")


# 13F versions: restatements replace, new holdings add, untyped out.
def test_13f_versions():
    r = pd.DataFrame(
        {
            "accession": ["o", "n1", "x", "r", "n2"],
            "filer_cik": 1,
            "period": DAY("2019-06-30"),
            "form": ["13F-HR", "13F-HR/A", "13F-HR/A", "13F-HR/A", "13F-HR/A"],
            "amendmenttype": [None, "NEW HOLDINGS", None, "RESTATEMENT", "NEW HOLDINGS"],
            "first_close": pd.to_datetime(["2019-08-01", "2019-08-05", "2019-08-06",
                                           "2019-09-01", "2019-09-05"]),
        }
    )  # fmt: skip
    log = {}
    v = best_ideas.versions(r, log)
    assert log["amendments_without_a_type_left_out"] == 1
    assert [(x.base, x.adds) for x in v.itertuples()] == [
        ("o", ()), ("o", ("n1",)), ("r", ()), ("r", ("n2",))
    ]  # fmt: skip


# The best idea is the largest tilt; under 20 stocks a version has none.
def test_best_idea_is_the_largest_tilt():
    ids = list(range(1, 22))
    h = pd.DataFrame({"accession": "a", "permno": ids, "value_usd": [1.0] * 20 + [3.0]})
    period = DAY("2019-06-30")
    v = pd.DataFrame({"filer_cik": [1], "period": [period], "since": [DAY("2019-08-01")],
                      "base": ["a"], "adds": [()]})  # fmt: skip
    market = {period: pd.Series(1 / 21, index=ids)}
    got = best_ideas.best(v, h, market)
    assert got["best"].iloc[0] == 21
    assert best_ideas.best(v, h[h["permno"] <= 19], market)["best"].tolist() == [-1]


# Insiders: a same-month trader each of 3 years is routine; else not.
def test_insider_classes():
    rows = []
    for year in (2015, 2016, 2017):
        rows.append((1, DAY(f"{year}-03-10")))
        rows.append((2, DAY(f"{year}-{year - 2010:02d}-10")))
    t = pd.DataFrame(rows, columns=["owner_cik", "trans_date"])
    t["first_close"] = t["trans_date"] + pd.Timedelta(days=3)
    t["superseded_at"] = pd.Series(pd.NaT, index=t.index, dtype="datetime64[ns, UTC]")
    c = insiders.classes(t)
    y2018 = c[c["year"] == 2018].set_index("owner_cik")["routine"]
    assert y2018[1] and not y2018[2]
    # A trade made public only in the year itself classifies nobody then.
    late = t.assign(first_close=DAY("2018-02-01"))
    assert insiders.classes(late).query("year == 2018").empty
    # A 4/A that moved owner 1's 2017 trade to April before 2018 counts.
    moved = t.copy()
    moved.loc[(moved["owner_cik"] == 1) & (moved["trans_date"].dt.year == 2017),
              "superseded_at"] = pd.Timestamp("2017-06-01", tz="UTC")  # fmt: skip
    fix = pd.DataFrame({"owner_cik": [1], "trans_date": [DAY("2017-04-10")],
                        "first_close": [DAY("2017-06-02")], "superseded_at": [pd.NaT]})  # fmt: skip
    c = insiders.classes(pd.concat([moved, fix], ignore_index=True))
    assert not c.query("year == 2018").set_index("owner_cik")["routine"][1]


# Lazy Prices: the same text scores 1, disjoint words score 0.
def test_lazy_prices_cosine():
    m = lazy_prices.VECTORS.transform(["Revenue grew in Texas", "revenue grew in texas",
                                       "litigation risk remains"])  # fmt: skip
    assert m[0].multiply(m[1]).sum() == pytest.approx(1.0)
    assert m[0].multiply(m[2]).sum() == 0


# Red flags: (T - 90 days, T] counts; later or older is 0; no CIK NaN.
def test_red_flag_window(monkeypatch):
    T = DAY("2019-06-28")
    when = [T - pd.Timedelta(days=d) for d in (89, 90, 0, -1)]
    ev = pd.DataFrame({"permno": [1, 2, 3, 4], "accession": list("abcd"), "red_flag": True,
                       "first_close": when})  # fmt: skip
    monkeypatch.setattr(data, "table", lambda name, cols=None, **k: ev)
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [DAY("2019-06-30")],
                                                                     "T": [T]}))  # fmt: skip
    monkeypatch.setattr(base, "universe_at", lambda eom: [1, 2, 3, 4, 5])
    linked = pd.Series([True] * 4 + [False], index=[1, 2, 3, 4, 5])
    monkeypatch.setattr(base, "has_cik", lambda p, t: linked)
    got = edgar_flags.build([DAY("2019-06-30")]).set_index("permno")["value"]
    assert got[1] == 1.0 and got[2] == 0.0 and got[3] == 1.0 and got[4] == 0.0
    assert np.isnan(got[5])


# Every sign, window and bar is the protocol's (step 4 checklist).
def test_signs_windows_and_bars_match_the_protocol():
    signs = {m: m.SIGN for m in gates.SIGNALS.values()}
    assert signs == {short_interest: -1, edgar_flags: -1, insiders: 1, lazy_prices: 1,
                     best_ideas: 1}  # fmt: skip
    assert edgar_flags.WINDOW == pd.Timedelta(days=90)
    assert insiders.WINDOW == pd.DateOffset(months=6) and insiders.CODES == ("P", "S")
    assert short_interest.CARRY == pd.DateOffset(months=2)
    assert lazy_prices.GAP == (300, 500) and lazy_prices.CARRY == pd.DateOffset(months=12)
    assert best_ideas.MIN_STOCKS == 20 and gates.FAMILY == 6
    assert (gates.MIN_STOCKS, gates.MIN_MONTHS, gates.COVERAGE_T) == (100, 24, 2.0)
    assert (gates.NULL_SERIES, gates.NULL_SEED, gates.BURN, gates.RHO_CAP, gates.LAGS) == (
        100_000, 20261025, 50, 0.9, 6)  # fmt: skip
    assert gates.PILOT_SEEDS == range(20261500, 20261520) and gates.NOISE_HOLD == 12
    assert gates.POSITIVE_SEEDS == range(20261300, 20261400)
    assert gates.NEGATIVE_SEEDS == range(20261400, 20261500)
    assert (gates.POSITIVE_PASS, gates.NEGATIVE_MAX, gates.CONTROL_MONTHS) == (70, 10, 70)
    assert gates.POWER_LAST == DAY("2018-12-31")
    assert gates.HOLM == pytest.approx([0.05 / k for k in (6, 5, 4, 3, 2, 1)])


# Ancillary windows end by 2020-12-31 and the next formation would not.
def test_ancillary_windows_end_by_the_seal():
    last = gates.LAST_DAY
    assert gates.SUE_LAST + gates.FOUR_MONTHS <= last
    assert DAY("2020-09-30") + gates.FOUR_MONTHS > last
    assert gates.FLAGS_LAST + gates.YEAR <= last
    assert DAY("2020-01-31") + gates.YEAR > last
    with pytest.raises(AssertionError):
        gates.next_sue(pd.DataFrame(columns=["permno", "announced", "end", "sue"]),
                       DAY("2020-09-30"))  # fmt: skip


# The next SUE: after T, within 4 months, the earlier of two quarters.
def test_next_sue():
    T = DAY("2019-06-28")
    four = T + gates.FOUR_MONTHS
    sue = pd.DataFrame({
        "permno": [1, 1, 2, 2, 3, 4, 5, 5],
        "announced": [T, T + pd.Timedelta(days=10), T + pd.Timedelta(days=20),
                      T + pd.Timedelta(days=20), four, four + pd.Timedelta(days=1),
                      T + pd.Timedelta(days=60), T + pd.Timedelta(days=30)],
        "end": pd.to_datetime(["2019-03-31", "2019-06-30", "2019-06-30", "2019-03-31",
                               "2019-06-30", "2019-06-30", "2019-09-30", "2019-06-30"]),
        "sue": [9.0, 1.0, 3.0, 2.0, 4.0, 5.0, 7.0, 6.0],
    })  # fmt: skip
    got = gates.next_sue(sue, T)
    assert got.to_dict() == {1: 1.0, 2: 2.0, 3: 4.0, 5: 6.0}


# A red flag after T, up to 12 months on, is the Lazy Prices outcome.
def test_later_flags():
    T = DAY("2018-06-29")
    ev = pd.DataFrame({"permno": [1, 2, 3, 4],
                       "first_close": [T, T + pd.Timedelta(days=1), T + gates.YEAR,
                                       T + gates.YEAR + pd.Timedelta(days=1)]})  # fmt: skip
    got = gates.later_flags(ev, T, [1, 2, 3, 4, 5])
    assert got.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]


# p is (k + 1)/(B + 1) of null t at or above t; a missing t gives 1.
def test_p_value_tail_ties_and_missing():
    null = np.array([1.0, 2.0, 3.0])
    assert gates.p_value(2.0, null) == 0.75 and gates.p_value(10.0, null) == 0.25
    assert gates.p_value(-10.0, null) == 1.0 and gates.p_value(float("nan"), null) == 1.0
    assert gates.test_series(pd.Series(np.arange(5.0)))["p"] == 1.0


# rho is the textbook lag-1 autocorrelation of the demeaned series.
def test_autocorrelation():
    y = pd.Series([0.1, 0.3, -0.2, 0.4, 0.0, -0.1, 0.2])
    e = y - y.mean()
    want = (e.iloc[1:].to_numpy() * e.iloc[:-1].to_numpy()).sum() / (e * e).sum()
    assert gates.autocorrelation(y) == pytest.approx(want)
    assert gates.autocorrelation(pd.Series([0.2] * 10)) == 0.0


# Holm cascades: once a sorted p misses its bar, later ones fail too.
def test_holm_cascade():
    got = gates.holm({"a": 0.009, "b": 0.0095, "c": 1.0, "d": 1.0, "e": 1.0, "f": 1.0})
    assert not any(v["passes"] for v in got.values())


# Leave one out: X (X'X)^-1 / diagonal is each column's residual.
def test_loo_residuals():
    rng = np.random.default_rng(3)
    x = np.column_stack([np.ones(200), rng.standard_normal((200, 5))])
    got = gates.loo_residuals(x)
    for j in range(6):
        rest = np.delete(x, j, axis=1)
        coef, *_ = np.linalg.lstsq(rest, x[:, j], rcond=None)
        assert np.allclose(got[:, j], x[:, j] - rest @ coef)


# Synthetic months: random design, a label, every stock in the universe.
def fake_months(n_months=30, n=300, seed=4):
    rng, out = np.random.default_rng(seed), []
    for e in pd.date_range("2015-01-31", periods=n_months, freq="ME"):
        m = object.__new__(gates.Month)
        m.eom, m.T, m.ids = e, e, list(range(n))
        m.x = pd.DataFrame(rng.uniform(-1, 1, (n, 4)), index=m.ids, columns=["syy", "a", "b", "c"])
        m.x.insert(0, "const", 1.0)
        m.label = pd.Series(rng.standard_normal(n), index=m.ids)
        out.append(m)
    return out


# Each characteristic's residual IC sits in its own column.
def test_loo_ics_by_column():
    m = fake_months(1)[0]
    m.label = m.x["b"] + 0.05 * pd.Series(np.random.default_rng(5).standard_normal(300))
    got = gates.loo_ics(m, np.ones(300, bool), ["a", "b", "c"])
    assert got["b"] > 0.9 and abs(got["a"]) < 0.2 and abs(got["c"]) < 0.2


# A gate's series: the sign applies and thin months are skipped.
def test_gate_series_sign_and_thin_months():
    ms = fake_months(30)
    by = {m.eom: m.label.copy() for m in ms}
    by[ms[0].eom].iloc[gates.MIN_STOCKS - 1 :] = np.nan
    up, down = gates.gate_series(ms, by, 1), gates.gate_series(ms, by, -1)
    assert len(up) == 29 and (up > 0.5).all() and (down < -0.5).all()


# The controls: k makes the pilots' mean IC the detectable target.
def test_controls_bisection(monkeypatch):
    monkeypatch.setattr(gates, "NULL_SERIES", 2_000)
    monkeypatch.setattr(gates, "CONTROL_MONTHS", 30)
    monkeypatch.setattr(gates, "PILOT_SEEDS", range(20261500, 20261503))
    monkeypatch.setattr(gates, "POSITIVE_SEEDS", range(20261300, 20261310))
    monkeypatch.setattr(gates, "NEGATIVE_SEEDS", range(20261400, 20261410))
    ms = fake_months(30)
    nulls: dict = {}
    res = gates.controls(ms, nulls)
    k = res["noise_scale"]
    assert 0.01 < k < 100
    ics = [gates.planted_ic(ms, gates.planted(ms, k, s)) for s in gates.PILOT_SEEDS]
    c = float(np.quantile(nulls[30], 1 - gates.HOLM[0]))
    sd = np.mean([ic.std(ddof=1) for ic in ics])
    target = (c + gates.Z80) * sd / np.sqrt(len(ics[0]))
    assert np.mean([ic.mean() for ic in ics]) == pytest.approx(target, abs=0.002)
    assert res["pilot_mean_ic"] == pytest.approx(np.mean([ic.mean() for ic in ics]))
    assert res["negative_passes_at_5pct"] <= 3 and "iid_nulls" in res


# Short interest: the latest settlement public by T, 2 months at most.
def test_short_interest_build(monkeypatch):
    T = DAY("2019-06-28")
    days = pd.bdate_range("2019-01-01", "2019-07-31")
    si = pd.DataFrame({
        "permno": [1, 1, 2, 2, 3, 4],
        "settlement": pd.to_datetime(["2019-05-31", "2019-06-14", "2019-05-31", "2019-06-14",
                                      "2019-04-28", "2019-04-26"]),
        "shortint": [500.0, 1000.0, 500.0, 900.0, 300.0, 300.0],
        "first_close": pd.to_datetime(["2019-06-12", "2019-06-27", "2019-06-12", "2019-07-01",
                                       "2019-05-08", "2019-05-08"]),
    })  # fmt: skip

    # CRSP shares: 10,000 for every stock and session, public that day.
    def table(name, cols=None, **k):
        if name == "short_interest":
            return si
        rows = [(p, d) for p in (1, 2, 3, 4) for d in days]
        out = pd.DataFrame(rows, columns=["permno", "date"]).assign(shrout_k=10.0)
        return out.assign(first_close=out["date"])

    monkeypatch.setattr(data, "table", table)
    monkeypatch.setattr(data, "calendar", lambda: pd.Series(days, index=days))
    # Two formations: a row public in July is loaded, not used in June.
    eoms = [DAY("2019-06-30"), DAY("2019-07-31")]
    two = pd.DataFrame({"eom": eoms, "T": [T, DAY("2019-07-31")]})
    monkeypatch.setattr(base, "formations", lambda e: two)
    got = short_interest.build(eoms)
    june = got[got["eom"] == eoms[0]].set_index("permno")["value"]
    assert june.to_dict() == {1: 0.1, 2: 0.05, 3: 0.03}
    july = got[got["eom"] == eoms[1]].set_index("permno")["value"]
    assert july.to_dict() == {1: 0.1, 2: 0.09}


# Insiders: the window, the 4/A rule, roles, CIK, one trade per day.
def test_insiders_build(monkeypatch):
    T = DAY("2019-06-28")
    close = pd.Timestamp("2019-06-28 20:00", tz="UTC")
    six = T - insiders.WINDOW
    rows = [
        (1, 10, "P", "Officer", T - pd.DateOffset(months=1), pd.NaT),
        (1, 11, "S", "Director", T + pd.Timedelta(days=1), pd.NaT),
        (2, 12, "P", "Officer", six, pd.NaT),
        (2, 12, "P", "Officer", six + pd.Timedelta(days=1), pd.NaT),
        (3, 13, "P", "Officer", T - pd.Timedelta(days=5), close - pd.Timedelta(minutes=1)),
        (3, 13, "S", "Officer", T - pd.Timedelta(days=5), close),
        (4, 14, "P", "10% Owner", T - pd.Timedelta(days=5), pd.NaT),
        (4, 15, "P", "Officer", T - pd.Timedelta(days=5), pd.NaT),
        # Three lots of one buy, a second day's buy, a sale: 2 buys, 1 sale.
        (6, 16, "P", "Officer", T - pd.Timedelta(days=9), pd.NaT),
        (6, 16, "P", "Officer", T - pd.Timedelta(days=9), pd.NaT),
        (6, 16, "P", "Officer", T - pd.Timedelta(days=9), pd.NaT),
        (6, 16, "P", "Officer", T - pd.Timedelta(days=3), pd.NaT),
        (6, 17, "S", "Director", T - pd.Timedelta(days=9), pd.NaT),
    ]
    t = pd.DataFrame(rows, columns=["permno", "owner_cik", "trans_code", "relationship",
                                    "first_close", "superseded_at"])  # fmt: skip
    t["superseded_at"] = pd.to_datetime(t["superseded_at"], utc=True)
    t = t.assign(trans_date=t["first_close"] - pd.Timedelta(days=2), common_stock=True)
    kinds = pd.DataFrame([(o, y, o == 15) for o in range(10, 18) for y in (2018, 2019)],
                         columns=["owner_cik", "year", "routine"])  # fmt: skip
    monkeypatch.setattr(data, "table", lambda name, cols=None, **k: t)
    monkeypatch.setattr(data, "calendar", lambda: pd.Series([close], index=[T]))
    monkeypatch.setattr(insiders, "classes", lambda rows: kinds)
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [DAY("2019-06-30")],
                                                                     "T": [T]}))  # fmt: skip
    monkeypatch.setattr(base, "universe_at", lambda eom: [1, 2, 3, 4, 5, 6])
    linked = pd.Series([True] * 4 + [False, True], index=[1, 2, 3, 4, 5, 6])
    monkeypatch.setattr(base, "has_cik", lambda p, t: linked)
    got = insiders.build([DAY("2019-06-30")]).set_index("permno")["value"]
    assert got[1] == 1.0 and got[2] == 1.0 and got[3] == -1.0 and got[4] == 0.0
    assert np.isnan(got[5]) and got[6] == pytest.approx(1 / 3)


# Lazy Prices pairs: the latest same-form report 300 to 500 days back.
def test_lazy_prices_pairs(monkeypatch):
    d = DAY("2016-01-04")
    rows = [("a0", 1, "10-K", d), ("a1", 1, "10-K", d + pd.Timedelta(days=299)),
            ("b0", 2, "10-K", d), ("b1", 2, "10-K", d + pd.Timedelta(days=300)),
            ("c0", 3, "10-K", d), ("c1", 3, "10-K", d + pd.Timedelta(days=500)),
            ("d0", 4, "10-K", d), ("d1", 4, "10-K", d + pd.Timedelta(days=501)),
            ("e0", 5, "10-K", d), ("e1", 5, "10-KT", d + pd.Timedelta(days=365)),
            ("f0", 6, "10-K", d), ("f1", 6, "10-K", d + pd.Timedelta(days=100)),
            ("f2", 6, "10-K", d + pd.Timedelta(days=400))]  # fmt: skip
    meta = pd.DataFrame(rows, columns=["accession", "cik", "form", "filing_date"])
    monkeypatch.setattr(sources, "read_parts", lambda name, cols, **k: iter([meta]))
    got = set(lazy_prices.pairs().itertuples(index=False, name=None))
    assert got == {("b1", "b0"), ("c1", "c0"), ("f2", "f1")}


# Lazy Prices at T: the latest score public by T, 12 months at most.
def test_lazy_prices_build(monkeypatch):
    T = DAY("2019-06-28")
    s = pd.DataFrame({"accession": list("abcde"), "score": [0.1, 0.2, 0.3, 0.4, 0.5]})
    meta = pd.DataFrame({"accession": list("abcde"), "permno": [1, 1, 2, 3, 4], "form": "10-K",
                         "first_close": [T - pd.DateOffset(months=3), T, T - gates.YEAR,
                                         T - gates.YEAR + pd.Timedelta(days=1),
                                         T + pd.Timedelta(days=1)]})  # fmt: skip
    monkeypatch.setattr(lazy_prices, "scores", lambda log: s)
    monkeypatch.setattr(sources, "read_parts", lambda name, cols, **k: iter([meta]))
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [DAY("2019-06-30")],
                                                                     "T": [T]}))  # fmt: skip
    got = lazy_prices.build([DAY("2019-06-30")]).set_index("permno")["value"]
    assert got.to_dict() == {1: 0.2, 3: 0.4}


# 13F at T: each filer's latest public period, recent and 20 stocks.
def test_best_ideas_build(monkeypatch):
    T = DAY("2019-09-30")
    june, march, sept = DAY("2019-06-30"), DAY("2019-03-31"), DAY("2019-09-30")
    reports = pd.DataFrame({
        "accession": ["f1", "f2", "f2n", "f3", "f4"],
        "filer_cik": [1, 2, 2, 3, 4],
        "period": [june, june, sept, june, march],
        "form": "13F-HR", "amendmenttype": None, "units": "dollars",
        "first_close": pd.to_datetime(["2019-08-01", "2019-08-02", "2019-09-15", "2019-10-05",
                                       "2019-05-01"]),
    })  # fmt: skip
    lines = [(a, p, 3.0 if p == 21 else 1.0) for a in ("f1", "f2", "f3", "f4")
             for p in range(1, 22)]  # fmt: skip
    lines += [("f2n", p, 1.0) for p in range(1, 6)]
    h = pd.DataFrame(lines, columns=["accession", "permno", "value_usd"])
    monkeypatch.setattr(
        data, "table", lambda name, cols=None, **k: reports if name == "sec_13f_reports" else h
    )
    monkeypatch.setattr(best_ideas, "market_weights",
                        lambda periods: {p: pd.Series(1 / 21, index=range(1, 22))
                                         for p in set(periods)})  # fmt: skip
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [DAY("2019-09-30")],
                                                                     "T": [T]}))  # fmt: skip
    got = best_ideas.build([DAY("2019-09-30")]).set_index("permno")
    assert got.loc[21, "value"] == 1.0 and (got["holders"] == 1).all() and len(got) == 21


# Same-day versions: the original first, then its new holdings.
def test_13f_same_day_order():
    r = pd.DataFrame({"accession": ["b", "a"], "filer_cik": 1, "period": DAY("2019-06-30"),
                      "form": ["13F-HR", "13F-HR/A"], "amendmenttype": [None, "NEW HOLDINGS"],
                      "first_close": DAY("2019-08-01")})  # fmt: skip
    v = best_ideas.versions(r, {})
    assert [(x.base, x.adds) for x in v.itertuples()] == [("b", ()), ("b", ("a",))]


# The runner needs a pushed commit, and each stage the earlier ones.
def test_runner_needs_a_pushed_commit_and_earlier_stages(monkeypatch, tmp_path):
    answers = {"status": "", "branch": "", "rev-parse": "abc123\n"}

    # git's answers by subcommand.
    def run(args, **k):
        return subprocess.CompletedProcess(args, 0, stdout=answers[args[1]], stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError):
        gates.commit()
    answers["branch"] = "  origin/x\n"
    assert gates.commit() == "abc123"
    monkeypatch.setattr(gates, "OUT", tmp_path)
    head = "abc123"
    with pytest.raises(SystemExit):
        gates.require("nonsense", head)
    with pytest.raises(SystemExit):
        gates.require("gates", head)
    sha = gates.hashlib.sha256(gates.PROTOCOL.read_bytes()).hexdigest()
    stamp = {"commit": head, "protocol_sha256": sha}
    gates.result_path("power", head).write_text(json.dumps({"stamp": stamp, "power": {}}))
    gates.require("controls", head)
    done = {"stamp": stamp, "controls": {"controls_pass": False}}
    gates.result_path("controls", head).write_text(json.dumps(done))
    with pytest.raises(SystemExit):
        gates.require("gates", head)
    done["controls"]["controls_pass"] = True
    gates.result_path("controls", head).write_text(json.dumps(done))
    gates.require("gates", head)
    with pytest.raises(SystemExit):
        gates.require("gates", "other")


# The folder reader applies every registry check, not only the bans.
def test_read_parts_checks_like_read(monkeypatch):
    with pytest.raises(ValueError):
        next(sources.read_parts("panel", ["ret"]))
    src = sources.REGISTRY["sections"]
    monkeypatch.setitem(sources.REGISTRY, "sections", dataclasses.replace(src, banned=("item7",)))
    with pytest.raises(sources.BannedField):
        next(sources.read_parts("sections", ["item7"]))
    gated = dataclasses.replace(src, purposes=frozenset({"label"}))
    monkeypatch.setitem(sources.REGISTRY, "sections", gated)
    with pytest.raises(sources.NotForBacktest):
        next(sources.read_parts("sections", ["item1a"]))


# The known-by readers drop later rows and later 4/As, then restore.
def test_known_by_cuts_later_rows_and_restores(monkeypatch):
    T, close = DAY("2019-06-28"), pd.Timestamp("2019-06-28 20:00", tz="UTC")
    f = pd.DataFrame({"first_close": [T, T + pd.Timedelta(days=1)],
                      "superseded_at": [close, close - pd.Timedelta(minutes=1)]})  # fmt: skip
    monkeypatch.setattr(data, "table", lambda name, *a, **k: f)
    monkeypatch.setattr(sources, "read_parts", lambda *a, **k: iter([f]))
    monkeypatch.setattr(data, "calendar", lambda: pd.Series([close], index=[T]))
    with gates.known_by(T):
        got = data.table("sec_insiders")
        assert len(got) == 1 and got["superseded_at"].isna().all()
        assert len(next(sources.read_parts("sections", []))) == 1
        assert len(data.table("links")) == 2
    assert len(data.table("sec_insiders")) == 2
