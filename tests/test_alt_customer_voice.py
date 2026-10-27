# The customer voice exhibit on synthetic stores and labels.

import numpy as np
import pandas as pd

from fiam.alt import customer_voice as cv


# Names lose punctuation and legal form; single letters join.
def test_stem():
    assert cv.stem("APPLE INC") == "APPLE"
    assert cv.stem("Apple Inc.") == "APPLE"
    assert cv.stem("H P INC") == "HP"
    assert cv.stem("LOGITECH INTERNATIONAL S A") == "LOGITECH"
    assert cv.stem("SANDISK CORP (Last Known)") == "SANDISK"
    assert cv.stem("The Home Depot") == "HOME DEPOT"
    assert cv.stem("WD 40 CO") == "WD 40"


# Synthetic dated names: one rename and two share classes.
def names() -> pd.DataFrame:
    return pd.DataFrame({
        "permno": [1, 2, 3, 4],
        "stem": ["ACME", "WIDGET", "TWIN", "TWIN"],
        "valid_from": pd.to_datetime(["2010-01-01", "2010-01-01", "2010-01-01", "2010-01-01"]),
        "valid_to": [pd.NaT, pd.Timestamp("2017-06-30"), pd.NaT, pd.NaT],
    })  # fmt: skip


# Whole names match; credits, hand exclusions and others do not.
def test_match_stores():
    stores = ["Acme", "ACME Inc.", "Acme (Author)", "Widget", "Spectrum", "Other"]
    m = cv.match_stores(stores, names())
    assert set(m["store"]) == {"Acme", "ACME Inc.", "Widget"}
    assert "Spectrum" in cv.NOT_THE_FIRM


# A store reaches a firm only while the name is in force, once.
def test_to_firms_dating_and_classes():
    m = cv.match_stores(["Acme", "Widget", "Twin"], names())
    months = pd.to_datetime(["2017-05-31", "2017-08-31"])
    sm = pd.DataFrame({
        "store": ["Acme", "Acme", "Widget", "Widget", "Twin", "Twin"],
        "eom": list(months) * 3,
        "reviews": [30, 40, 50, 60, 70, 80],
        "rating_sum": [120.0, 160.0, 200.0, 240.0, 280.0, 320.0],
    })  # fmt: skip
    firm, log = cv.to_firms(sm, m)
    assert set(firm["permno"]) == {1, 2}
    assert firm[firm["permno"] == 2]["eom"].tolist() == [months[0]]
    assert log["store_months_on_two_stocks_left_out"] == 4


# The abnormal rating needs 20 reviews now and 100 over 12 months.
def test_abnormal_thresholds():
    eoms = pd.date_range("2015-01-31", periods=14, freq="ME")
    reviews = [10] * 12 + [20, 19]
    firm = pd.DataFrame({"permno": 1, "eom": eoms, "reviews": reviews,
                         "rating_sum": [r * 4.0 for r in reviews[:12]] + [90.0, 95.0]})  # fmt: skip
    ab = cv.abnormal(firm)
    assert len(ab) == 1
    assert ab["eom"].iloc[0] == eoms[12]
    assert np.isclose(ab["abnormal"].iloc[0], 4.5 - 4.0)


# Too few trailing reviews leave no abnormal rating.
def test_abnormal_thin_history():
    eoms = pd.date_range("2015-01-31", periods=13, freq="ME")
    firm = pd.DataFrame({"permno": 1, "eom": eoms, "reviews": [8] * 12 + [50],
                         "rating_sum": [32.0] * 12 + [200.0]})  # fmt: skip
    assert cv.abnormal(firm).empty


# A perfect monthly rank relation gives IC 1; thin months drop out.
def test_monthly_ic_and_summary():
    rows, labs = [], []
    for k, eom in enumerate(pd.date_range("2016-01-31", periods=6, freq="ME")):
        n = 12 if k < 5 else 5
        for i in range(n):
            rows.append({"permno": i, "eom": eom, "abnormal": i * 0.1})
            labs.append({"permno": i, "eom": eom, "resid_panel": i * 0.01 + k})
    ic = cv.monthly_ic(pd.DataFrame(rows), pd.DataFrame(labs), "resid_panel")
    assert len(ic) == 5 and np.allclose(ic["ic"], 1.0)
    ic.loc[0, "ic"] = 0.5
    s = cv.summarise(ic)
    assert s["months"] == 5 and s["t"] > 0
    assert cv.summarise(ic.head(1))["t"] is None


# Only consumer-sector firm-months stay in the Amazon test.
def test_consumer_only():
    eom = pd.Timestamp("2018-01-31")
    sig = pd.DataFrame({"permno": [1, 2], "eom": [eom, eom], "abnormal": [0.1, 0.2]})
    panel = pd.DataFrame({"permno": [1, 2], "eom": [eom, eom], "gics": ["25202010", "40101010"]})
    assert cv.consumer_only(sig, panel)["permno"].tolist() == [1]


# Coverage counts linked, universe and leaver names.
def test_coverage():
    eom = pd.Timestamp("2018-01-31")
    sig = pd.DataFrame({"permno": [1, 2], "eom": [eom, eom], "abnormal": [0.1, 0.2]})
    labels = pd.DataFrame({"permno": [1, 2, 3], "eom": [eom] * 3,
                           "resid_universe": [0.1, np.nan, 0.2]})  # fmt: skip
    last = pd.Series({1: pd.Timestamp("2020-10-31"), 2: pd.Timestamp("2018-03-31"),
                      3: pd.Timestamp("2020-10-31")})  # fmt: skip
    c = cv.coverage(sig, labels, last, {1, 2, 3})
    assert c["stocks_linked"] == 3 and c["stocks_linked_ever_in_the_trading_universe"] == 2
    assert c["of_them_in_the_trading_universe_that_month"] == 1
    assert c["leavers_mapped"] == 1 and c["stayers_mapped"] == 1


# The chart writes one image from the summaries.
def test_chart(tmp_path):
    r = {"months": 30, "mean_ic": 0.02, "sd_ic": 0.1, "t": 1.1, "median_names": 20,
         "first": "2016-01-31", "last": "2020-10-31"}  # fmt: skip
    cv.chart({"Synthetic ratings": r}, tmp_path / "c.png")
    assert (tmp_path / "c.png").stat().st_size > 0


# CA0052 months move to the formation after their T+1 release.
def test_ca0052_lag_and_name_check():
    links = pd.DataFrame(
        [
            (1, "ticker", "ABC", "2012-01-01", None),
            (1, "name", "OLDCO INC", "2012-01-01", None),
            (2, "ticker", "REN", "2012-01-01", None),
            (2, "name", "FORMER NAME CORP", "2012-01-01", None),
            (3, "ticker", "GOOD", "2012-01-01", None),
            (3, "name", "GOOD WIDGETS INC", "2012-01-01", None),
        ],
        columns=["permno", "kind", "value", "valid_from", "valid_to"],
    )
    links[["valid_from", "valid_to"]] = links[["valid_from", "valid_to"]].apply(pd.to_datetime)
    ents = [{"carc_id": i, "carc_name": n, "entity_representation_name": r} for i, (n, r) in
            enumerate([("NewCo Inc", "company"), ("Renamed Holdings", "company"),
                       ("Good Widgets", "company")])]  # fmt: skip
    ca = pd.DataFrame({"entity_name": ["GOOD", "GOOD", "ABC", "REN"],
                       "date": ["2018-03-31", "2019-12-31", "2018-03-31", "2018-03-31"],
                       "star_rating": [4.0, 4.5, 3.0, 3.5],
                       "review_count": [30, 40, 50, 60]})  # fmt: skip
    firm, log = cv.ca0052_map(ca, links, ents)
    assert firm["permno"].tolist() == [3, 3]
    # 2018-03-30 is Good Friday: April 2 is the first session after.
    assert firm["eom"].tolist() == [pd.Timestamp("2018-04-30"), pd.Timestamp("2020-01-31")]
    assert log["ticker_matches_refused_name_mismatch"] == 2
    assert log["months_before_2021"] == 4 and "T + 1" in log["lag"]


# A summary with no t still draws, its label reading n/a.
def test_chart_without_t(tmp_path):
    r = {"months": 3, "mean_ic": 0.01, "sd_ic": 0.0, "t": None, "median_names": 12,
         "first": "2016-01-31", "last": "2016-03-31"}  # fmt: skip
    cv.chart({"Synthetic ratings": r}, tmp_path / "n.png")
    assert (tmp_path / "n.png").stat().st_size > 0
