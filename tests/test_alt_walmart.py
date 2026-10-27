# The Walmart deep dive on synthetic months; no network, no sealed rows.

import json

import numpy as np
import pandas as pd
import pytest

from fiam.alt import common, walmart

MONTHS = pd.date_range("2019-01-31", "2020-12-31", freq="ME")


# Walmart's year ends in January: Feb to Apr is Q1 of the next year.
def test_fiscal_quarter_walmart_january_year_end():
    days = ["2019-01-31", "2019-02-28", "2019-04-30", "2019-05-31", "2019-10-31"]
    days += ["2019-11-30", "2020-01-31", "2020-02-29", "2021-01-31"]
    got = common.fiscal_quarter(days, walmart.YEAR_END_MONTH)
    assert got["fiscal_year"].tolist() == [2019, 2020, 2020, 2020, 2020, 2020, 2020, 2021, 2021]
    assert got["quarter"].tolist() == [4, 1, 1, 2, 3, 4, 4, 1, 4]
    cal = common.fiscal_quarter(["2020-01-31", "2020-12-31"], 12)
    assert cal["fiscal_year"].tolist() == [2020, 2020] and cal["quarter"].tolist() == [1, 4]


# Growth is on the same fiscal quarter a year back, NaN without one.
def test_yoy_math():
    frame = pd.DataFrame(
        {"fiscal_year": [2020, 2020, 2021, 2021], "quarter": [1, 2, 1, 3], "v": [100, 50, 125, 9]}
    )
    got = common.yoy(frame, "v")
    assert np.isnan(got[0]) and np.isnan(got[1]) and np.isnan(got[3])
    assert got[2] == pytest.approx(0.25)


# Synthetic months: spend 100 then 150 in 2020, users 10 then 12.
def months() -> pd.DataFrame:
    late = MONTHS.year == 2020
    return pd.DataFrame(
        {
            "date": MONTHS,
            "spend": np.where(late, 150.0, 100.0),
            "users": np.where(late, 12.0, 10.0),
            "debiased": 1.0,
            "foot_traffic": np.where(late, 80.0, 100.0),
            "web_visits": np.where(MONTHS >= "2020-06-30", 5.0, np.nan),
            "launch_weeks": 1.0,
        }
    )


# Only whole fiscal quarters count; 2020 against 2019 gives the growth.
def test_quarterly_whole_quarters_and_growth():
    q = walmart.quarterly(months())
    keys = list(zip(q["fiscal_year"], q["quarter"]))
    assert (2019, 4) not in keys and (2021, 4) not in keys
    assert keys == [(2020, 1), (2020, 2), (2020, 3), (2020, 4), (2021, 1), (2021, 2), (2021, 3)]
    row = q.set_index(["fiscal_year", "quarter"]).loc[(2021, 1)]
    assert row["spend_yoy"] == pytest.approx(0.5)
    assert row["per_user_yoy"] == pytest.approx(150 / 12 / 10 - 1)
    assert row["foot_traffic_yoy"] == pytest.approx(-0.2)
    assert np.isnan(row["web_visits_yoy"])
    # Q4 FY2020 mixes 2019 months with January 2020.
    q4 = q.set_index(["fiscal_year", "quarter"]).loc[(2020, 4)]
    assert q4["spend"] == pytest.approx(350.0)


# SEC quarters land on Walmart's fiscal labels with their own growth.
def test_revenue_labels_and_growth():
    sec = pd.DataFrame(
        {
            "end": pd.to_datetime(["2019-04-30", "2020-04-30", "2020-01-31"]),
            "val": [100.0, 110.0, 130.0],
            "tag": "Revenues",
        }
    )
    got = walmart.revenue(sec).set_index(["fiscal_year", "quarter"])
    assert got.loc[(2021, 1), "revenue_yoy"] == pytest.approx(0.1)
    assert got.loc[(2020, 4), "revenue"] == 130.0


# A free debias reply written the way Carbon Arc sends it.
def probe(path, dates, online, store) -> None:
    rows = []
    for d, a, b in zip(dates, online, store):
        for channel, users in (("Online", a), ("Physical", b)):
            rows.append(
                {
                    "date": f"{d}T00:00:00",
                    "transaction_method": channel,
                    "credit_card_spend": 1.0,
                    "credit_card_users_reference": users,
                    "credit_card_spend_debiased": 1.0,
                }
            )
    path.write_text(json.dumps({"insight_column": "credit_card_spend", "data": rows}))


# Users: first month, each January, last full month and the multiple.
def test_panel_summary_and_seal(tmp_path):
    days = ["2019-01-31", "2019-06-30", "2020-01-31", "2020-12-31", "2021-01-31"]
    path = tmp_path / "users.json"
    probe(path, days, [10, 12, 15, 25, 30], [20, 22, 24, 30, 31])
    got = walmart.panel(common.CUTOFF, path)
    assert got["rows_after_end_dropped"] == 2
    on = got["channels"]["online"]
    assert (on["first"], on["last"], on["last_full_month"]) == (10, 25, "2020-12-31")
    assert on["januaries"] == {"2019": 10, "2020": 15}
    assert on["growth_multiple"] == pytest.approx(2.5)
    assert got["channels"]["both"]["growth_multiple"] == pytest.approx(55 / 30, abs=1e-4)
    # A month ending after the pull day is partial and never last.
    frame = walmart.load_probe(path)
    late = walmart.panel_summary(frame, pulled="2021-01-15")
    assert late["in store"]["last_full_month"] == "2020-12-31"


# Past 2020 the run is refused while sealed and writes nothing.
def test_refuses_past_2020_while_sealed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(common.sources, "unsealed", lambda: False)
    assert walmart.build("2021-06-30", out=tmp_path / "w") is None
    assert capsys.readouterr().out.strip() == common.WAITS
    assert not (tmp_path / "w").exists()
    assert common.run_end() == common.CUTOFF
    assert common.run_end("2021-06-30", opened=True) == pd.Timestamp("2021-06-30")


# Rows after the end are dropped and counted; few pairs give no r.
def test_drop_after_and_correlation_floor():
    frame = pd.DataFrame({"date": ["2020-12-31", "2021-01-31"], "v": [1, 2]})
    kept, dropped = common.drop_after(frame, common.CUTOFF)
    assert len(kept) == 1 and dropped == 1
    assert common.correlation([1, 2], [2, 4]) == {"r": None, "n": 2}
    assert common.correlation([1, 2, 3], [2, 4, 7])["r"] > 0.98
