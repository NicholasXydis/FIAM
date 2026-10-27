# The retailer accuracy check on synthetic rows and SEC quarters.

import pandas as pd
import pytest

from fiam.alt import common, retailers

DAY = pd.Timestamp


# Carbon Arc rows: ticker, date, PERMNO and the value it states.
def rows(items) -> pd.DataFrame:
    frame = pd.DataFrame(items, columns=["ticker", "date", "permno", "value"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["permno"] = frame["permno"].astype("Int64")
    return frame.assign(how="dated ticker")


# SEC quarters: stock, period end, value, tag, basis and filed day.
def sec(items) -> pd.DataFrame:
    frame = pd.DataFrame(items, columns=["permno", "end", "val"])
    frame["end"] = pd.to_datetime(frame["end"])
    return frame.assign(tag="SalesRevenueNet", basis="quarter", filed=DAY("2020-06-01"))


# Within 0.5% is tight, within 2% loose; a far period end never matches.
def test_match_within_half_percent_and_window():
    ca = rows(
        [
            ("AAA", "2020-02-01", 1, 1004.0),
            ("AAA", "2020-05-02", 1, 1010.0),
            ("AAA", "2020-08-01", 1, 900.0),
            ("BBB", "2020-02-01", None, 5.0),
        ]
    )
    s = sec([(1, "2020-02-01", 1000.0), (1, "2020-05-04", 1000.0), (1, "2020-08-20", 900.0)])
    got = retailers.match(ca, s)
    assert got["matched"].tolist() == [True, True, False, False]
    assert got.loc[0, "rel"] == pytest.approx(0.004)
    assert got.loc[1, "offset"] == 2
    out = retailers.summary(got)
    assert (out["rows"], out["mapped"], out["matched"]) == (4, 3, 2)
    assert (out["within_0_5pct"], out["within_2pct"]) == (1, 2)
    assert out["share_within_0_5pct"] == 0.5 and out["share_within_2pct"] == 1.0
    assert out["largest_misses"][0]["carbon_arc_date"] == "2020-05-02"
    assert retailers.unmatched(got)[1]["why"] == "dated ticker"


# Exactly 0.5% still counts as within; just over it does not.
def test_tight_band_edge():
    ca = rows([("A", "2020-02-01", 1, 1005.0), ("A", "2020-05-01", 1, 1005.1)])
    got = retailers.match(ca, sec([(1, "2020-02-01", 1000.0), (1, "2020-05-01", 1000.0)]))
    assert retailers.summary(got)["within_0_5pct"] == 1


# Q4 is the year less nine months when no three-month fact is filed.
def test_quarter_facts_q4_by_subtraction_and_first_filed():
    f = pd.DataFrame(
        [
            (1, "SalesRevenueNet", "2019-02-01", "2019-04-30", 100.0, "2019-06-01"),
            (1, "SalesRevenueNet", "2019-02-01", "2019-10-31", 300.0, "2019-12-01"),
            (1, "SalesRevenueNet", "2019-02-01", "2020-01-31", 450.0, "2020-03-20"),
            (1, "Revenues", "2019-02-01", "2019-04-30", 101.0, "2019-06-01"),
            (1, "SalesRevenueNet", "2019-05-01", "2019-07-31", 0.0, "2019-09-01"),
            (1, "Revenues", "2019-05-01", "2019-07-31", 99.0, "2020-09-01"),
        ],
        columns=["permno", "tag", "start", "end", "val", "filed"],
    )
    f["filed"] = pd.to_datetime(f["filed"])
    got = common.quarter_facts(f).set_index("end")
    q4 = got.loc[DAY("2020-01-31")]
    assert q4["val"] == 150.0 and q4["basis"] == "year_less_nine"
    assert q4["start"] == DAY("2019-11-01")
    # Same filing: the net sales tag wins over total revenue.
    assert got.loc[DAY("2019-04-30"), "tag"] == "SalesRevenueNet"
    # A zero figure is no figure, so the later Revenues fact stands.
    assert got.loc[DAY("2019-07-31"), "val"] == 99.0


# A gap takes the ticker's later PERMNO only while CRSP lists it.
def test_map_permnos_carries_back_only_while_listed():
    ca = rows([("W", "2013-05-31", None, 1.0), ("W", "2016-05-31", 7, 1.0)])
    ca = ca.drop(columns="how")
    links = pd.DataFrame({"permno": [7], "valid_from": [DAY("2010-01-01")], "valid_to": [pd.NaT]})
    got = retailers.map_permnos(ca, links, ca["permno"])
    assert got["permno"].tolist() == [7, 7]
    assert got.loc[0, "how"] == "same ticker's later PERMNO"
    late = links.assign(valid_from=DAY("2015-01-01"))
    got = retailers.map_permnos(ca, late, ca["permno"])
    assert pd.isna(got.loc[0, "permno"]) and got.loc[0, "how"] == "no PERMNO on the date"


# Staleness is the pull day less the table's last data date.
def test_staleness_days():
    frame = rows([("A", "2025-08-02", 1, 1.0), ("B", "2025-05-10", 2, 1.0)])
    receipt = {
        "pulled_at": "2026-10-26T20:11:10+00:00",
        "metadata": {"table_max_date": "2025-08-24 00:00:00"},
    }
    got = retailers.staleness(frame, receipt)
    assert got["pull_minus_table_max_days"] == 428
    assert got["pull_minus_last_row_days"] == 450
    assert got["pull_minus_last_row_days_by_ticker"]["B"] == 534


# Past 2020 the check is refused while sealed and writes nothing.
def test_refuses_past_2020_while_sealed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(common.sources, "unsealed", lambda: False)
    assert retailers.build("2022-01-01", out=tmp_path / "r") is None
    assert "unseal" in capsys.readouterr().out
    assert not (tmp_path / "r").exists()
