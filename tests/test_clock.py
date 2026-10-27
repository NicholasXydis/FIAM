# The one clock on the NYSE calendar alone, no data folder.

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import clock

DAY = pd.Timestamp


# The NYSE calendar around every case the tests need.
@pytest.fixture(scope="module")
def cal():
    return clock.calendar(clock.xnys_sessions("2020-10-01", "2024-12-31"))


# One EDGAR acceptance time to its first close, filed the same day.
def edgar_close(cal, accepted: str, filed: str | None = None) -> pd.Timestamp:
    filed = filed or accepted[:10]
    return clock.first_close(clock.edgar_available([accepted], [filed]), cal).iat[0]


# 15:59 counts for that close and 16:01 for the next, both sides of DST.
@pytest.mark.parametrize(
    "accepted, closes",
    [
        ("2024-03-08T15:59:00.000Z", "2024-03-08"),
        ("2024-03-08T16:01:00.000Z", "2024-03-11"),
        ("2024-03-11T15:59:00.000Z", "2024-03-11"),
        ("2024-03-11T16:01:00.000Z", "2024-03-12"),
        ("2024-11-01T15:59:00.000Z", "2024-11-01"),
        ("2024-11-04T16:01:00.000Z", "2024-11-05"),
    ],
)
def test_filings_either_side_of_the_close_and_of_dst(cal, accepted, closes):
    assert edgar_close(cal, accepted) == DAY(closes)


# A stamp at exactly 16:00:00 counts for the next close.
def test_a_stamp_at_the_close_counts_for_the_next_one(cal):
    assert edgar_close(cal, "2024-03-12T16:00:00.000Z") == DAY("2024-03-13")


# On an early-close day the close is 13:00; 13:30 counts next session.
def test_early_close_day_closes_at_one(cal):
    assert edgar_close(cal, "2024-11-29T12:59:00.000Z") == DAY("2024-11-29")
    assert edgar_close(cal, "2024-11-29T13:30:00.000Z") == DAY("2024-12-02")
    assert cal[DAY("2024-11-29")].tz_convert(clock.EASTERN).hour == 13


# A Friday evening and a date-only stamp before a holiday roll forward.
def test_friday_evening_and_holiday_roll_forward(cal):
    assert edgar_close(cal, "2024-03-08T19:00:00.000Z") == DAY("2024-03-11")
    july3 = clock.first_close(clock.end_of_day(["2024-07-03"]), cal).iat[0]
    assert july3 == DAY("2024-07-05")


# EDGAR's day opens at 06:00: earlier stamps wait, late ones move on.
def test_edgar_never_before_six_and_late_filings_wait(cal):
    assert edgar_close(cal, "2024-03-11T05:00:00.000Z") == DAY("2024-03-11")
    late = edgar_close(cal, "2024-03-08T18:30:00.000Z", "2024-03-11")
    assert late == DAY("2024-03-11")
    missing = clock.first_close(clock.edgar_available([None], ["2024-03-11"]), cal).iat[0]
    assert missing == DAY("2024-03-12")


# A day-t return forms the book at close t+1 and earns t+1 to t+2.
def test_day_t_feature_forms_next_close_and_earns_after(cal):
    seen = clock.market_session(["2024-03-08"], cal)
    book = clock.formation(seen, cal)
    earns = clock.shift_sessions(book, 1, cal)
    assert (seen.iat[0], book.iat[0], earns.iat[0]) == (
        DAY("2024-03-08"),
        DAY("2024-03-11"),
        DAY("2024-03-12"),
    )


# The eom 2020-12-31 row forms the first book, traded on 2021-01-04.
def test_last_2020_row_trades_on_the_first_2021_session(cal):
    seen = clock.eom_session(["2020-12-31"], cal)
    assert clock.formation(seen, cal).iat[0] == DAY("2021-01-04")
    assert clock.eom_session(["2021-01-31"], cal).iat[0] == DAY("2021-01-29")


# A Form 4 joins at its acceptance, never at its trade date.
def test_form_4_joins_at_acceptance_not_trade_date(cal):
    available = clock.insider_available(["2024-03-05T10:00:00.000Z"], ["2024-03-05"])
    assert clock.first_close(available, cal).iat[0] == DAY("2024-03-05")


# A CA0065S day-t row (lag T+1) acts at close t+3.
def test_vendor_row_with_a_one_day_lag_acts_three_closes_later(cal):
    seen = clock.first_close(clock.vendor_available(["2024-03-04"], 1), cal)
    assert clock.formation(seen, cal).iat[0] == clock.shift_sessions(["2024-03-04"], 3, cal).iat[0]


# Short interest is public at the end of settlement + 8 sessions.
def test_short_interest_waits_eight_sessions(cal):
    public = clock.short_interest_available(["2024-03-15"], cal)
    assert clock.first_close(public, cal).iat[0] == DAY("2024-03-28")


# A join fails when a row was not public before its formation close.
def test_join_assertion_refuses_a_same_close_row():
    clock.assert_known_before(["2024-03-08"], ["2024-03-11"], "ok")
    with pytest.raises(AssertionError, match="1 rows"):
        clock.assert_known_before(["2024-03-11"], ["2024-03-11"], "same close")


# A monthly join keeps only rows public by the month's last session.
def test_monthly_join_needs_public_by_month_end(cal):
    keep = clock.known_by_month_end(["2024-02-29", "2024-03-01"], ["2024-02-29"] * 2, cal)
    assert keep.tolist() == [True, False]


# Naive stamps and rows outside the calendar are refused or left empty.
def test_naive_stamps_refused_and_outside_rows_empty(cal):
    with pytest.raises(ValueError):
        clock.first_close(pd.Series([pd.Timestamp("2024-03-08 10:00")]), cal)
    outside = clock.first_close(clock.end_of_day(["2019-01-02", "2030-01-02"]), cal)
    assert outside.isna().all()


# A threshold at t reads no row on or after t and matches numpy.
def test_threshold_uses_only_earlier_days():
    rng = np.random.default_rng(7)
    dates = np.repeat(pd.date_range("2024-01-01", periods=40), 25)
    values = rng.normal(size=len(dates))
    got = clock.expanding_quantile(values, dates, 0.99, min_count=10)
    for day in got.index[1:]:
        past = values[dates < day]
        assert got[day] == pytest.approx(np.quantile(past, 0.99))
    spiked = values.copy()
    spiked[dates == dates[-1]] = 1e9
    again = clock.expanding_quantile(spiked, dates, 0.99, min_count=10)
    assert again[dates[-1]] == got[dates[-1]]
    assert np.isnan(got.iat[0])


# Earnings dates: same quarter a year earlier + 364, else last + 91.
def test_projected_earnings_dates():
    table = pd.DataFrame(
        {
            "gvkey": ["A"] * 5 + ["B"],
            "fyearq": [2023, 2023, 2023, 2023, 2024, 2024],
            "fqtr": [1, 2, 3, 4, 1, 1],
            "rdq": ["2023-04-20", "2023-07-20", None, "2024-01-25", "2024-04-18", None],
        }
    )
    out = clock.project_earnings(table, ahead=2).set_index(["gvkey", "fyearq", "fqtr"])
    assert out.loc[("A", 2024, 1), "projected"] == DAY("2023-04-20") + pd.Timedelta(days=364)
    assert out.loc[("A", 2024, 1), "basis"] == "year_ago"
    assert out.loc[("A", 2024, 3), "basis"] == "last_plus_91"
    assert out.loc[("A", 2024, 3), "projected"] == DAY("2024-04-18") + pd.Timedelta(days=91)
    assert out.loc[("B", 2024, 2), "basis"] == "none"


# The 2020-10 label ends 2020-12-01; 2020-11's reaches 2021.
def test_label_window_refuses_the_seal():
    cal = clock.calendar(pd.bdate_range("2020-09-01", "2021-02-26"))
    start, end = clock.label_window(pd.Timestamp("2020-10-31"), 1, cal)
    assert (start, end) == (pd.Timestamp("2020-11-02"), pd.Timestamp("2020-12-01"))
    with pytest.raises(clock.SealedWindow):
        clock.label_window(pd.Timestamp("2020-11-30"), 1, cal)
    assert (
        clock.label_window(pd.Timestamp("2020-11-30"), 1, cal, sealed=False)[1]
        > clock.LAST_LABEL_DAY
    )


# A fit at T may hold the label of t-2, never t-1's, which ends after T.
def test_purge_by_label_end_day():
    from fiam.v4 import guards

    guards.assert_label_window([pd.Timestamp("2020-06-01")], pd.Timestamp("2020-06-30"))
    with pytest.raises(AssertionError):
        guards.assert_label_window([pd.Timestamp("2020-07-01")], pd.Timestamp("2020-06-30"))
