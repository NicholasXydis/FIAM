# As-filed EPS and SUE, cleaned Compustat and the SYY rebuild.

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import asfiled, compustat, rebuild, sources

HAVE_SUE = (sources.DATA / "v4" / "clean" / "sue.parquet").exists()
DAY = pd.Timestamp


# One EPS fact as the clean table holds it.
def fact(permno, accn, filed, start, end, val, tag="EarningsPerShareBasic", form="10-Q"):
    days = (DAY(end) - DAY(start)).days
    return dict(permno=permno, accn=accn, filed=DAY(filed), start=DAY(start), end=DAY(end),
                val=val, tag=tag, form=form, days=days)  # fmt: skip


# Bad dates drop a fact; two values in one filing give none; first only.
def test_clean_rules():
    f = pd.DataFrame(
        [
            dict(cik=1, tag="Assets", unit="USD", start=None, end="2018-12-31", val=5,
                 accn="a1", form="10-K", filed="2019-02-01"),
            dict(cik=1, tag="Assets", unit="USD", start=None, end="2018-12-31", val=5,
                 accn="a2", form="10-K", filed="2020-02-01"),
            dict(cik=1, tag="Revenues", unit="USD", start="0202-01-01", end="2018-12-31",
                 val=9, accn="a1", form="10-K", filed="2019-02-01"),
            dict(cik=1, tag="NetIncomeLoss", unit="USD", start="2018-01-01", end="2018-12-31",
                 val=1, accn="a1", form="10-K", filed="2019-02-01"),
            dict(cik=1, tag="NetIncomeLoss", unit="USD", start="2018-01-01", end="2018-12-31",
                 val=2, accn="a1", form="10-K", filed="2019-02-01"),
            dict(cik=1, tag="EarningsPerShareBasic", unit="USD/shares", start="2019-01-01",
                 end="2019-03-31", val=1, accn="a3", form="10-Q", filed="2019-03-01"),
        ]
    )  # fmt: skip
    log = {}
    got = asfiled.clean(f, log)
    # The later Assets report is dropped; only the first report stays.
    assert got.loc[got["tag"] == "Assets", "accn"].tolist() == ["a1"]
    assert "Revenues" not in set(got["tag"]) and log["start_out_of_range"] == 1
    assert "NetIncomeLoss" not in set(got["tag"])
    assert log["facts_with_two_values_in_one_filing"] == 2
    # An EPS fact filed before its quarter ended is dropped.
    assert log["facts_filed_before_their_period_ended"] == 1


# Each seasonal difference comes from the first filing to report EPS_q.
def test_difference_takes_both_values_from_the_first_filing():
    eps = pd.DataFrame(
        [
            fact(1, "q1", "2019-05-01", "2019-01-01", "2019-03-31", 1.10),
            fact(1, "q1", "2019-05-01", "2018-01-01", "2018-03-31", 1.00),
            # A later filing restates the year-ago quarter: never used.
            fact(1, "k1", "2020-02-01", "2019-01-01", "2019-03-31", 1.10),
            fact(1, "k1", "2020-02-01", "2018-01-01", "2018-03-31", 0.50),
        ]
    )
    firsts = asfiled.first_reports(eps, asfiled.QUARTER)
    got = asfiled.first_tag(asfiled.tag_differences(eps, firsts, asfiled.QUARTER))
    row = got[got["end"] == DAY("2019-03-31")].iloc[0]
    assert row["accn"] == "q1" and row["diff"] == pytest.approx(0.10)


# The first tag in order with both values wins: continuing ops first.
def test_tag_order_prefers_continuing_operations():
    t1, t2 = asfiled.EPS_TAGS[0], asfiled.EPS_TAGS[1]
    eps = pd.DataFrame(
        [
            fact(1, "q", "2019-05-01", "2019-01-01", "2019-03-31", 2.0, tag=t2),
            fact(1, "q", "2019-05-01", "2018-01-01", "2018-03-31", 1.0, tag=t2),
            fact(1, "q", "2019-05-01", "2019-01-01", "2019-03-31", 1.5, tag=t1),
            fact(1, "q", "2019-05-01", "2018-01-01", "2018-03-31", 1.4, tag=t1),
        ]
    )
    firsts = asfiled.first_reports(eps, asfiled.QUARTER)
    got = asfiled.first_tag(asfiled.tag_differences(eps, firsts, asfiled.QUARTER))
    assert got.iloc[0]["tag"] == t1 and got.iloc[0]["diff"] == pytest.approx(0.1)


# A 2-for-1 split between two filings halves the earlier value.
def test_share_basis_puts_values_on_the_later_filing():
    dist = pd.DataFrame({"permno": [1], "disexdt": [DAY("2019-06-03")], "disfacshr": [1.0]})
    factor = asfiled.share_basis(dist)
    got = factor([1, 1, 2], [DAY("2019-05-01")] * 3, [DAY("2019-08-01"), DAY("2019-05-20"),
                                                     DAY("2019-08-01")])  # fmt: skip
    assert got.tolist() == [0.5, 1.0, 1.0]


# Q4 from annual less nine months, the nine on the 10-K's share basis.
def test_q4_by_annual_less_nine_months():
    eps = pd.DataFrame(
        [
            fact(1, "k", "2020-02-10", "2019-01-01", "2019-12-31", 4.0, form="10-K"),
            fact(1, "k", "2020-02-10", "2018-01-01", "2018-12-31", 3.0, form="10-K"),
            fact(1, "q3", "2019-11-01", "2019-01-01", "2019-09-30", 4.0),
            fact(1, "q3", "2019-11-01", "2018-01-01", "2018-09-30", 3.6),
        ]
    )
    # A 2-for-1 split after the Q3 10-Q halves the nine-month difference.
    dist = pd.DataFrame({"permno": [1], "disexdt": [DAY("2019-12-02")], "disfacshr": [1.0]})
    got = asfiled.q4_differences(eps, asfiled.share_basis(dist), {})
    row = got.iloc[0]
    assert row["start"] == DAY("2019-10-01") and row["end"] == DAY("2019-12-31")
    assert row["diff"] == pytest.approx((4.0 - 3.0) - (4.0 - 3.6) * 0.5)


# The SUE's scale needs at least 6 of the last 8 earlier differences.
def test_sue_scale_needs_six_prior_quarters():
    ends = pd.date_range("2016-03-31", periods=10, freq="QE")
    d = pd.DataFrame({"permno": 1, "end": ends, "filed": ends + pd.Timedelta(days=30),
                      "diff": np.arange(10, dtype=float)})  # fmt: skip
    out = asfiled.scales(d, lambda p, a, b: np.ones(len(np.asarray(p))))
    assert out["n_prior"].tolist()[:7] == [0, 1, 2, 3, 4, 5, 6]
    assert np.isnan(out["scale"].iloc[5]) and out["scale"].iloc[6] == pytest.approx(
        np.std(np.arange(6.0), ddof=1)
    )
    assert out["n_prior"].iloc[9] == 8


# Apple's Q2 FY2015 SUE sits on one share basis after its 7-for-1 split.
@pytest.mark.skipif(not HAVE_SUE, reason="no SUE table on this machine")
def test_real_apple_sue_after_its_split():
    s = sources.read("sue", ["sue", "scale", "n_prior"], purpose="label")
    row = s[(s["permno"] == 14593) & (s["end"].between("2015-03-20", "2015-04-05"))]
    # Rebuilt by hand it is 1.622; unadjusted it would be 0.51.
    assert len(row) == 1 and row["sue"].iloc[0] == pytest.approx(1.622, abs=0.002)


# Compustat: a report date before the period is missing; two calendars.
def test_compustat_quarterly_rules(tmp_path):
    base = dict(fyr="12", fyearq="2018", fqtr="1", datafqtr="2018Q1", curcdq="USD", fdateq=None)
    rows = [
        base | dict(gvkey="1", datadate="2018-03-31", datacqtr="2018Q1", rdq="2018-03-01"),
        base | dict(gvkey="2", datadate="2018-03-31", datacqtr="2018Q1", rdq="2018-04-20"),
        base | dict(gvkey="2", datadate="2018-03-31", datacqtr=None, rdq="2018-04-20", fyr="6"),
        base | dict(gvkey="3", datadate="2018-03-31", datacqtr=None, rdq="2018-04-25"),
        base | dict(gvkey="3", datadate="2018-03-31", datacqtr="2018Q1", rdq="2018-04-30"),
        base | dict(gvkey="4", datadate="2018-03-31", datacqtr="2018Q1", rdq="2018-04-20",
                    fdateq="2018-05-10"),
    ]  # fmt: skip
    frame = pd.DataFrame(rows)
    for c in compustat.ITEMS_Q:
        frame[c] = 1.0
    frame.to_parquet(tmp_path / "q.parquet")
    log = {}
    q = compustat.quarterly(tmp_path / "q.parquet", log).set_index("gvkey")
    assert pd.isna(q.loc["1", "rdq"]) and log["rdq_before_datadate_set_missing"] == 1
    # Equal report dates keep the calendar-quarter row; else the earlier.
    assert q.loc["2", "fyr"] == 12 and q.loc["3", "rdq"] == DAY("2018-04-25")
    assert log["two_calendar_pairs"] == 2
    # Results the day after rdq; other items wait for the 10-Q's day.
    eastern = pd.to_datetime(q["results_at"], utc=True).dt.tz_convert("America/New_York")
    assert eastern["4"].date() == DAY("2018-04-21").date()
    assert pd.to_datetime(q.loc["4", "items_at"]).tz_convert("America/New_York").day == 10
    # No report date at all: everything waits four months.
    assert eastern["1"].date() == DAY("2018-07-31").date()


# A year-ago row is matched by datadate alone, 350 to 380 days back.
def test_year_ago_by_datadate():
    f = pd.DataFrame({"gvkey": ["1"] * 3, "datadate": pd.to_datetime(
        ["2017-12-31", "2018-12-31", "2019-06-30"]), "at": [1.0, 2.0, 3.0]})  # fmt: skip
    got = compustat.year_ago(f, ["at"])
    assert np.isnan(got.iloc[0, 0]) and got.iloc[1, 0] == 1.0 and np.isnan(got.iloc[2, 0])


# The rebuild's parts follow their formulas on a hand-made firm.
def test_rebuild_parts_formulas():
    a = pd.DataFrame({"at": [100.0], "at_lag": [80.0], "sale": [50.0], "cogs": [30.0],
                      "ni": [5.0], "ni_lag": [-2.0], "oancf": [8.0], "che": [10.0],
                      "dltt": [20.0], "dlc": [5.0], "ceq": [40.0], "lt": [60.0],
                      "act": [30.0], "lct": [20.0], "ppegt": [50.0], "ppegt_lag": [45.0],
                      "invt": [10.0], "invt_lag": [8.0], "sstk": [3.0], "prstkc": [1.0],
                      "pi": [7.0], "dp": [4.0]}, index=[7])  # fmt: skip
    q = pd.DataFrame({"niq": [1.0], "atq": [100.0]}, index=[7])
    got = rebuild.parts(a, q).iloc[0]
    assert got["gp_at"] == pytest.approx(0.2) and got["at_gr1"] == pytest.approx(0.25)
    assert got["oaccruals_at"] == pytest.approx(-0.03)
    assert got["noa_at"] == pytest.approx(((100 - 10) - (100 - 20 - 5 - 40)) / 80)
    assert got["ppeinv_gr1a"] == pytest.approx((5 + 2) / 80)
    assert got["eqnetis_at"] == pytest.approx(0.02) and np.isnan(got["niq_at"])
    # JKP's O-score: debt (dltt + dlc) over assets, coefficient 0.52.
    o = (-1.32 - 0.407 * np.log(100) + 6.03 * 25 / 100 - 1.43 * 0.1 + 0.076 * 20 / 30
         - 2.37 * 0.05 - 1.83 * 11 / 60 - 0.52 * 7 / 7)  # fmt: skip
    assert got["o_score"] == pytest.approx(o)


# Splits after the earlier filing, up to the later's day, rebase it.
def test_split_factor_date_boundaries():
    dist = pd.DataFrame({"permno": [1, 1], "disexdt": [DAY("2019-05-01"), DAY("2019-08-01")],
                         "disfacshr": [1.0, 2.0]})  # fmt: skip
    factor = asfiled.share_basis(dist)
    got = factor([1], [DAY("2019-05-01")], [DAY("2019-08-01")])
    assert got.tolist() == [1 / 3]


# Earlier differences filed after the quarter's own filing never count.
def test_sue_scale_ignores_priors_filed_later():
    ends = pd.date_range("2016-03-31", periods=9, freq="QE")
    filed = list(ends + pd.Timedelta(days=30))
    filed[3] = filed[8] + pd.Timedelta(days=100)
    d = pd.DataFrame({"permno": 1, "end": ends, "filed": filed, "diff": np.arange(9.0)})
    out = asfiled.scales(d, lambda p, a, b: np.ones(len(np.asarray(p))))
    assert out["n_prior"].iloc[8] == 7
    # A quarter 59 days back is not an earlier quarter.
    near = d.iloc[:2].assign(end=[DAY("2016-03-31"), DAY("2016-05-29")])
    assert asfiled.scales(near, lambda p, a, b: np.ones(len(np.asarray(p))))["n_prior"].iloc[1] == 0


# Annual rows take their fiscal Q4's later clock, else four months on.
def test_compustat_annual_takes_its_q4_clock(tmp_path):
    a = pd.DataFrame({"gvkey": ["1", "2"], "datadate": ["2018-12-31", "2018-12-31"], "fyr": "12",
                      "fyear": "2018", "curcd": "USD"})  # fmt: skip
    for c in compustat.ITEMS_A:
        a[c] = 1.0
    a.to_parquet(tmp_path / "a.parquet")
    at = pd.Timestamp("2019-02-21 04:59:59", tz="UTC")
    q = pd.DataFrame(
        {"gvkey": ["1"], "datadate": [DAY("2018-12-31")], "fqtr": [4], "items_at": [at]}
    )
    got = compustat.annual(tmp_path / "a.parquet", q, {}).set_index("gvkey")["items_at"]
    assert got["1"] == at
    assert got["2"].tz_convert("America/New_York").date() == DAY("2019-04-30").date()


# Year to date to a trailing year: Q2 YTD + last Q4 YTD - year-ago Q2.
def test_jkp_frame_rolls_year_to_date():
    ends = pd.to_datetime(["2017-06-30", "2017-09-30", "2017-12-31", "2018-03-31", "2018-06-30"])
    q = pd.DataFrame({"gvkey": "1", "datadate": ends, "fqtr": [2, 3, 4, 1, 2],
                      "first_close": ends + pd.Timedelta(days=40)})  # fmt: skip
    for c in [*compustat.STOCKS, *compustat.FLOWS]:
        q[c] = 1.0
    q["oancfy"], q["sstky"], q["prstkcy"] = [20.0, 30.0, 40.0, 12.0, 25.0], 0.0, 0.0
    x = compustat.jkp_frame(q)
    assert x["oancf_ttm"].iloc[2] == 40.0
    assert x["oancf_ttm"].iloc[4] == pytest.approx(25.0 + 40.0 - 20.0)
    assert x["ni_ttm"].iloc[4] == 4.0 and np.isnan(x["ni_ttm"].iloc[2])


# The announcement is Compustat's rdq within 7 days, else the filing.
def test_announce_takes_rdq_within_seven_days(monkeypatch):
    from fiam.v4 import data, links

    d = pd.DataFrame({"permno": [1, 2], "end": [DAY("2019-03-30"), DAY("2019-06-30")],
                      "filed": [DAY("2019-05-01"), DAY("2019-08-01")]})  # fmt: skip
    q = pd.DataFrame({"gvkey": ["A", "B"], "datadate": [DAY("2019-03-31"), DAY("2019-06-10")],
                      "rdq": [DAY("2019-04-25"), DAY("2019-07-20")]})  # fmt: skip
    asked = {}

    # The registry stand-in records each purpose it was asked for.
    def table(name, columns=None, purpose=None, where=None):
        asked[name] = purpose
        return q if name == "compustat_quarterly" else pd.DataFrame()

    monkeypatch.setattr(data, "table", table)
    monkeypatch.setattr(links, "value_at", lambda lk, kind, p, e: pd.Series(["A", "B"]))
    got = asfiled.announce(d, {})
    assert got["announced"].tolist() == [DAY("2019-04-25"), DAY("2019-08-01")]
    assert got["announced_by"].tolist() == ["rdq", "filed"]
    assert asked["compustat_quarterly"] == "announce"


# The quarterly parts: trailing-year flows, lagged assets, JKP's niq_at.
def test_rebuild_parts_quarterly():
    x = pd.DataFrame({"at": [100.0], "at_l1": [90.0], "at_l4": [80.0], "ib": [2.0], "niq": [3.0],
                      "sale_ttm": [60.0], "cogs_ttm": [20.0], "ib_ttm": [9.0], "oancf_ttm": [12.0],
                      "ppegt": [50.0], "ppegt_l4": [40.0], "invt": [5.0], "invt_l4": [5.0],
                      "ceq": [40.0], "dltt": [20.0], "dlc": [None], "che": [10.0]})  # fmt: skip
    got = rebuild.parts_quarterly(x).iloc[0]
    assert got["niq_at"] == pytest.approx(2 / 90) and got["at_gr1"] == pytest.approx(0.25)
    assert got["gp_at"] == pytest.approx(0.4) and got["oaccruals_at"] == pytest.approx(-0.03)
    assert got["ppeinv_gr1a"] == pytest.approx(10 / 80)
    assert got["noa_at"] == pytest.approx(((100 - 10) - (100 - 20 - 40)) / 80)
    assert rebuild.total_debt(pd.Series([None]), pd.Series([None])).isna().all()


# The O-score's two flags: two loss years (0.285) and debts over assets.
def test_o_score_flags_and_guards():
    one = pd.Series([100.0])
    base = dict(at=one, lt=one * 0.5, debt=one * 0.2, ca=one * 0.3, cl=one * 0.2,
                nix=-one * 0.05, nix_lag=-one * 0.05, pi=one * 0.01, dp=one * 0.01)  # fmt: skip
    plain = rebuild.o_score(**(base | {"nix_lag": one * 0.05})).iloc[0]
    losses = rebuild.o_score(**base).iloc[0]
    change = -0.52 * ((-5 - 5) / 10)
    assert losses - plain == pytest.approx(0.285 - 0.52 * 0 - change)
    under = rebuild.o_score(**(base | {"lt": one * 1.5})).iloc[0]
    over = rebuild.o_score(**(base | {"lt": one * 0.5})).iloc[0]
    assert under - over == pytest.approx(-1.72 - 1.83 * 0.02 * (1 / 150 - 1 / 50) * 100)
    assert np.isnan(rebuild.o_score(**(base | {"ca": -one})).iloc[0])


# A quarter counts only once it and the quarters it uses are public.
def test_strict_clock_waits_for_every_quarter_used():
    ends = pd.to_datetime(["2018-03-31", "2018-06-30", "2018-09-30", "2018-12-31", "2019-03-31"])
    closes = pd.to_datetime(["2018-05-01", "2018-08-01", "2019-02-01", "2019-02-20", "2019-05-01"])
    x = pd.DataFrame({"gvkey": "1", "datadate": ends, "first_close": closes, "ni_ttm": 1.0})
    x["row_close"] = x["first_close"]
    for k in (1, 2, 3, 4):
        x = x.join(compustat.quarters_back(x, k, ["row_close"]))
    got = compustat.strict_clock(x)["first_close"]
    # Q4 2018 waits for nothing later; Q1 2019 is public on its own day.
    assert got.iloc[3] == DAY("2019-02-20") and got.iloc[4] == DAY("2019-05-01")
    # Q3 2018's late filing holds back nothing earlier.
    assert got.iloc[1] == DAY("2018-08-01")
