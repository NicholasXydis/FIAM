# The history twin's rules: share classes and the latest public row.

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import data, links
from fiam.v4.signals import history


# One PERMNO per gvkey-month: the panel's 2015 stock first, else bigger.
def test_one_stock_per_gvkey_month(monkeypatch):
    eom = pd.Timestamp("2016-06-30")
    u = pd.DataFrame(
        {
            "permno": [1, 2, 3, 4, 5],
            "eom": [eom] * 5,
            "cap_musd": [900.0, 2000.0, 700.0, 800.0, 650.0],
        }
    )
    # build() gives each month the prior month end's cap from all of CRSP.
    u["prior_cap"] = u["cap_musd"]
    gv = pd.Series(["A", "A", "B", "B", None])
    monkeypatch.setattr(data, "table", lambda name, cols=None, **k: _tables(name))
    monkeypatch.setattr(links, "value_at", lambda lk, kind, p, d: gv)
    log = {}
    got = history.gvkeys(u, log).set_index("gvkey")["permno"]
    # Gvkey A: the panel's own stock 1 wins over the larger stock 2.
    assert got["A"] == 1 and got["B"] == 4
    # A month with no gvkey stays, uncovered, for the survivorship test.
    assert log["universe_months_without_gvkey"] == 1 and got.index.isna().sum() == 1
    assert log["share_class_months_dropped"] == 2


# The registry stand-ins the share-class rule reads.
def _tables(name):
    if name == "panel":
        return pd.DataFrame({"permno": [1], "eom": [history.PANEL_FROM], "gvkey": ["A"]})
    return pd.DataFrame(columns=["permno", "kind", "value", "valid_from", "valid_to"])


# The latest row public by T: the newest datadate, not an older restate.
def test_latest_row_public_by_each_day():
    table = pd.DataFrame(
        {
            "gvkey": ["A", "A", "A"],
            "datadate": pd.to_datetime(["2010-12-31", "2011-12-31", "2010-12-31"]),
            "first_close": pd.to_datetime(["2011-03-01", "2012-03-01", "2012-06-01"]),
            "at": [1.0, 2.0, 99.0],
        }
    ).drop_duplicates(["gvkey", "datadate"])
    days = pd.to_datetime(["2011-01-31", "2011-06-30", "2012-06-29"])
    keys = pd.DataFrame({"row": [0, 1, 2], "gvkey": ["A"] * 3, "T": days})
    got = history.latest(table, keys).sort_index()
    assert np.isnan(got.loc[0, "at"]) and got.loc[1, "at"] == 1.0 and got.loc[2, "at"] == 2.0


# The Spearman helper needs at least 31 stocks.
def test_spearman_needs_thirty_stocks():
    a = pd.DataFrame({"x": np.arange(40.0), "y": np.arange(40.0) ** 3})
    assert history.spearman(a) == 1.0
    assert np.isnan(history.spearman(a.iloc[:30]))


# Before 2015 there was no panel, so the larger cap picks the class.
def test_share_class_before_2015_by_cap_alone(monkeypatch):
    eom = pd.Timestamp("2012-06-30")
    u = pd.DataFrame({"permno": [1, 2], "eom": [eom] * 2, "cap_musd": [900.0, 2000.0]})
    u["prior_cap"] = u["cap_musd"]
    monkeypatch.setattr(data, "table", lambda name, cols=None, **k: _tables(name))
    monkeypatch.setattr(links, "value_at", lambda lk, kind, p, d: pd.Series(["A", "A"]))
    got = history.gvkeys(u, {}).set_index("gvkey")["permno"]
    assert got["A"] == 2


# niq_at: income at its release, once last quarter's 10-Q is public too.
def test_niq_at_on_the_results_clock(monkeypatch):
    from fiam.v4 import compustat

    days = pd.bdate_range("2018-01-01", "2018-12-31")
    cal = pd.Series(days + pd.Timedelta(hours=21), index=days).dt.tz_localize("UTC")

    # Two quarters; the first's 10-Q comes out on the given day.
    def quarters(q1_filed):
        q = pd.DataFrame({"gvkey": "1", "datadate": pd.to_datetime(["2018-03-31", "2018-06-30"]),
                          "fqtr": [1, 2], "first_close": pd.to_datetime([q1_filed, "2018-08-10"]),
                          "results_at": pd.to_datetime(["2018-04-26", "2018-07-26"]).tz_localize(
                              "UTC")})  # fmt: skip
        for c in [*compustat.STOCKS, *compustat.FLOWS, *compustat.YEAR_TO_DATE]:
            q[c] = 1.0
        q["atq"], q["ibq"] = [100.0, 200.0], [3.0, 5.0]
        return q

    annual = pd.DataFrame({"gvkey": pd.Series(dtype=str),
                           "datadate": pd.Series(dtype="datetime64[ns]"),
                           "first_close": pd.Series(dtype="datetime64[ns]")})  # fmt: skip
    for c in history.ANNUAL:
        annual[c] = pd.Series(dtype=float)
    u = pd.DataFrame({"gvkey": ["1"], "T": [pd.Timestamp("2018-07-31")]})
    monkeypatch.setattr(data, "calendar", lambda: cal)
    for filed, want in (("2018-05-10", 5.0 / 100.0), ("2018-08-05", np.nan)):
        q = quarters(filed)
        tables = {"compustat_annual": annual, "compustat_quarterly": q}
        monkeypatch.setattr(data, "table", lambda name, cols=None, **k: tables[name].copy())
        got = history.accounting_parts(u)["niq_at"].iloc[0]
        assert (np.isnan(got) and np.isnan(want)) or got == pytest.approx(want)
