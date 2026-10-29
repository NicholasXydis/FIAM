# Labels, ranks and SYY-10 on a fake market.

import numpy as np
import pandas as pd
import pytest

from fiam.vfinal import clock, data, labels, ranks, sources, universe
from fiam.vfinal.signals import syy

HAVE_LABELS = (sources.DATA / "v4" / "clean" / "labels.parquet").exists()


# Weekday sessions, CRSP daily rows, the panel and exits in memory.
class Market:
    # Sessions over a span with no stocks yet.
    def __init__(self, start="2019-10-01", end="2021-02-26"):
        self.days = pd.bdate_range(start, end).as_unit("ns")
        self.crsp, self.panel, self.exits = [], [], []

    # One stock's daily CRSP return, the sessions it lacks, its panel cap.
    def stock(self, permno, ret=0.01, missing=(), me=1000.0, last=None):
        gone = pd.DatetimeIndex(missing)
        for d in self.days:
            if d not in gone and (last is None or d <= pd.Timestamp(last)):
                self.crsp.append((permno, d, ret, ret))
        for month in self.days.to_period("M").unique():
            eom = month.to_timestamp(how="end").normalize()
            if last is None or eom <= pd.Timestamp(last) + pd.offsets.MonthEnd(0):
                g = (1 + ret) ** 21 - 1
                self.panel.append((permno, eom, g, me, self.days[self.days <= eom][-1]))

    # An exit on a stock's last trade, its return and the day it is known.
    def exit(self, permno, day, delret, known=None, category="merger"):
        group = "merger_or_exchange" if category == "merger" else "failure"
        first = pd.Timestamp(known or day) + pd.Timedelta(days=1)
        self.exits.append((permno, pd.Timestamp(day), category, group, delret, first))

    # The registry and calendar calls answered from the rows above.
    def install(self, monkeypatch):
        cal = pd.Series(self.days + pd.Timedelta(hours=21), index=self.days)
        crsp = pd.DataFrame(self.crsp, columns=["permno", "date", "ret", "retx"])
        cols = ["permno", "eom", "ret", "me", "first_close"]
        panel = pd.DataFrame(self.panel, columns=cols)
        cols = ["permno", "exit_date", "category", "group", "delret", "first_close"]
        exits = pd.DataFrame(self.exits, columns=cols).assign(source="crsp_delistings")

        # The panel through the registry: its rows in an eom range.
        def table(name, columns=None, purpose=None, where=None):
            assert name == "panel"
            lo, hi = where["eom"]
            return panel[(panel["eom"] >= lo) & (panel["eom"] <= hi)].copy()

        # CRSP daily rows for these stocks between two days.
        def crsp_daily(p, s, e):
            ok = crsp["permno"].isin(set(p))
            return crsp[ok & (crsp["date"] >= pd.Timestamp(s)) & (crsp["date"] <= e)]

        monkeypatch.setattr(data, "calendar", lambda: cal)
        monkeypatch.setattr(data, "table", table)
        monkeypatch.setattr(data, "crsp_daily", crsp_daily)
        monkeypatch.setattr(data, "exits", lambda p: exits[exits["permno"].isin(set(p))].copy())


# Average ranks onto [-1, 1]; missing stays missing; one value is 0.
def test_unit_rank():
    got = ranks.unit_rank([3.0, 1.0, np.nan, 2.0, 2.0])
    assert got.tolist()[:2] == [1.0, -1.0] and np.isnan(got[2])
    assert got[3] == got[4] == 0.0
    assert ranks.unit_rank([5.0, np.nan]).tolist()[0] == 0.0


# Root-cap weighted z-scores are centred, scaled and clipped at 3.
def test_zscore_is_weighted_and_clipped():
    x = pd.Series([0.0, 1.0, 2.0, 100.0])
    z = ranks.zscore(x, [1.0, 1.0, 1.0, 1.0])
    assert z.max() <= ranks.Z_CLIP and z.idxmax() == 3
    w = [1.0, 2.0, 3.0]
    z2 = ranks.zscore([1.0, 2.0, 3.0], w)
    assert abs(np.average(z2, weights=w)) < 1e-12


# Weighted least squares takes a sector's mean and a slope out exactly.
def test_wls_residuals_remove_the_design():
    x = pd.Series(np.arange(6.0))
    design = pd.DataFrame({"a": [1.0, 1, 1, 0, 0, 0], "b": [0.0, 0, 0, 1, 1, 1], "x": x})
    y = 2 * design["a"] - 1 * design["b"] + 0.5 * x
    r = ranks.wls_residuals(y, design, np.ones(6))
    assert np.abs(r).max() < 1e-10


# A label runs from the close of T+1 to the close after the next month.
def test_label_window_and_compounding(monkeypatch):
    m = Market()
    m.stock(1, ret=0.01)
    m.install(monkeypatch)
    got = labels.raw(pd.DatetimeIndex(["2019-11-30"]), 1)
    row = got.set_index("permno").loc[1]
    assert row["start"] == pd.Timestamp("2019-12-02") and row["end"] == pd.Timestamp("2020-01-01")
    n = len(pd.bdate_range("2019-12-03", "2020-01-01"))
    assert row["sessions"] == n and abs(row["label"] - (1.01**n - 1)) < 1e-12


# A delisting return is booked once, the session after its last trade.
def test_delisting_return_is_booked_once(monkeypatch):
    m = Market()
    m.stock(2, ret=0.0, last="2019-12-31")
    m.exit(2, "2019-12-31", -0.5)
    m.install(monkeypatch)
    got = labels.raw(pd.DatetimeIndex(["2019-11-30", "2019-12-31"]), 1).set_index("eom")
    # 2020-01-01, the delisting session, ends November's window: booked.
    assert got.loc["2019-11-30", "label"] == pytest.approx(-0.5)
    assert got.loc["2019-11-30", "exit_booked"]
    # December's window starts after the stock had gone: no label at all.
    assert np.isnan(got.loc["2019-12-31", "label"])


# Missing CRSP days earn 0, counted; a stock without an exit is valued.
def test_missing_days_earn_zero(monkeypatch):
    m = Market()
    m.stock(3, ret=0.01, missing=pd.bdate_range("2019-12-10", "2019-12-12"))
    m.install(monkeypatch)
    row = labels.raw(pd.DatetimeIndex(["2019-11-30"]), 1).iloc[0]
    n = len(pd.bdate_range("2019-12-03", "2020-01-01")) - 3
    assert row["sessions"] == n and abs(row["label"] - (1.01**n - 1)) < 1e-12


# An exit whose return is public only past the cutoff refuses the label.
def test_label_public_after_the_seal_is_refused(monkeypatch):
    m = Market()
    m.stock(4, ret=0.0, last="2020-11-20")
    m.exit(4, "2020-11-20", -0.2, known="2021-01-05")
    m.stock(5, ret=0.0)
    m.install(monkeypatch)
    log = {}
    got = labels.raw(pd.DatetimeIndex(["2020-10-31"]), 1, log)
    assert set(got["permno"]) == {5} and log["refused_public_after_seal"] == 1


# The 2020-11 one-month label ends in 2021: formations stop at 2020-10.
def test_formations_stop_before_the_seal(monkeypatch):
    m = Market(start="2015-01-01", end="2021-03-31")
    m.install(monkeypatch)
    assert labels.formations(1)[-1] == pd.Timestamp("2020-10-31")
    assert labels.formations(3)[-1] == pd.Timestamp("2020-08-31")
    with pytest.raises(clock.SealedWindow):
        labels.windows([pd.Timestamp("2020-11-30")], 1)


# The residual label is orthogonal to its exposures and spans [-1, 1].
def test_residual_label_takes_the_exposures_out(monkeypatch):
    rng = np.random.default_rng(1)
    n = 60
    ids = list(range(100, 100 + n))
    z = pd.DataFrame({c: rng.normal(size=n) for c in labels.EXPOSURES}, index=ids)
    z["sector"], z["missing"] = np.where(np.arange(n) % 2, "G10", "G20"), 0
    lab = pd.DataFrame({"permno": ids, "eom": pd.Timestamp("2019-06-30"),
                        "T": pd.Timestamp("2019-06-28"), "horizon": 1,
                        "label": rng.normal(size=n), "me": rng.uniform(600, 5000, n)})  # fmt: skip
    monkeypatch.setattr(labels, "exposures", lambda p, eom, T, me: z.loc[sorted(p)])
    members = pd.DataFrame({"permno": ids, "new_long": True})
    monkeypatch.setattr(universe, "members", lambda eom: members)
    res = labels.residual(lab, "universe").set_index("permno")
    w = np.sqrt(lab.set_index("permno")["me"])
    for c in labels.EXPOSURES:
        assert abs(np.sum(w * res["resid"] * z[c])) < 1e-8
    assert res["resid_rank"].min() == -1 and res["resid_rank"].max() == 1


# SYY-10: signed ranks, missing as 0 over ten, at least 5 present.
def test_syy_combine_signs_and_eligibility():
    parts = pd.DataFrame({c: [1.0, 2.0, 3.0] for c in syy.PARTS})
    parts.loc[0, list(syy.PARTS)[:6]] = np.nan
    out = syy.combine(parts)
    assert np.isnan(out.loc[0, "raw"]) and out.loc[0, "present"] == 4
    # Every part rises with the row; the net sign is 4 plus minus 6 minus.
    signs = sum(syy.PARTS.values())
    assert out.loc[2, "raw"] == pytest.approx(signs / 10)


# On the real build, every kept label is public by the cutoff (PDF p15).
@pytest.mark.skipif(not HAVE_LABELS, reason="no labels on this machine")
def test_real_labels_are_public_by_the_seal():
    got = sources.read("labels", ["label", "available", "start", "T"], purpose="label")
    assert (pd.to_datetime(got["available"]) <= clock.LAST_LABEL_DAY).all()
    assert (got["start"] > got["T"]).all()
    one = got[got["horizon"] == 1] if "horizon" in got else got
    assert one["eom"].max() <= pd.Timestamp("2020-10-31")


# The ten SYY-10 parts and signs are exactly the written table.
def test_syy_parts_match_the_plan():
    assert syy.PARTS == {
        "o_score": -1, "chcsho_12m": -1, "eqnetis_at": -1, "oaccruals_at": -1, "noa_at": -1,
        "ret_12_1": 1, "gp_at": 1, "at_gr1": -1, "niq_at": 1, "ppeinv_gr1a": -1,
    }  # fmt: skip


# Shuffled rows give the same residuals: the design aligns by stock.
def test_residual_label_ignores_row_order(monkeypatch):
    rng = np.random.default_rng(2)
    n = 50
    ids = list(range(200, 200 + n))
    z = pd.DataFrame({c: rng.normal(size=n) for c in labels.EXPOSURES}, index=ids)
    z["sector"], z["missing"] = "G10", 0
    lab = pd.DataFrame({"permno": ids, "eom": pd.Timestamp("2019-06-30"),
                        "T": pd.Timestamp("2019-06-28"), "horizon": 1,
                        "label": rng.normal(size=n), "me": rng.uniform(600, 5000, n)})  # fmt: skip
    monkeypatch.setattr(labels, "exposures", lambda p, eom, T, me: z.loc[sorted(p)])
    members = pd.DataFrame({"permno": ids, "new_long": True})
    monkeypatch.setattr(universe, "members", lambda eom: members)
    a = labels.residual(lab, "universe").set_index("permno")["resid"]
    b = labels.residual(lab.sample(frac=1, random_state=3), "universe").set_index("permno")["resid"]
    assert np.abs(a - b.reindex(a.index)).max() < 1e-10


# A failure with no CRSP return takes the panel's exit-month residual.
def test_exit_without_a_return_takes_the_panel_residual(monkeypatch):
    m = Market()
    m.stock(6, ret=0.0, last="2019-12-16")
    m.exit(6, "2019-12-16", None, category="failure")
    m.install(monkeypatch)
    # The panel says December lost 40%; CRSP's December rows earned 0.
    panel = data.table
    monkeypatch.setattr(
        data, "table",
        lambda name, columns=None, purpose=None, where=None: panel(name, columns, purpose, where)
        .assign(ret=lambda f: np.where((f["permno"] == 6) & (f["eom"] == pd.Timestamp(
            "2019-12-31")), -0.4, f["ret"])),
    )  # fmt: skip
    row = labels.raw(pd.DatetimeIndex(["2019-11-30"]), 1).set_index("permno").loc[6]
    assert row["exit_booked"] and row["label"] == pytest.approx(-0.4)


# The 3-month label runs to the close after month t+3 ends.
def test_three_month_window(monkeypatch):
    m = Market()
    m.stock(7, ret=0.0)
    m.install(monkeypatch)
    w = labels.windows(pd.DatetimeIndex(["2019-10-31"]), 3).iloc[0]
    assert w["start"] == pd.Timestamp("2019-11-01") and w["end"] == pd.Timestamp("2020-02-03")


# No exit dated inside a label window is public only after the cutoff.
@pytest.mark.skipif(not HAVE_LABELS, reason="no labels on this machine")
def test_real_exits_in_label_windows_are_public_by_the_seal():
    path = sources.DATA / "v4" / "clean" / "exits.parquet"
    e = pd.read_parquet(path, columns=["exit_date", "first_close"])
    inside = e["exit_date"] <= pd.Timestamp("2020-12-01")
    assert not (inside & (e["first_close"] > clock.LAST_LABEL_DAY)).any()
