# The dated link table (PLAN §6.7) on tiny synthetic inputs.

import json

import pandas as pd
import pytest

from fiam.v4 import links

DAY = pd.Timestamp


# A stock's ticker change becomes two periods, the last one open.
def test_runs_split_on_change_and_keep_the_last_open():
    rows = pd.DataFrame(
        {
            "permno": [1, 1, 1, 2],
            "date": [DAY("2020-01-31"), DAY("2020-02-29"), DAY("2020-03-31"), DAY("2020-01-31")],
            "start": [DAY("2020-01-01"), DAY("2020-02-10"), DAY("2020-02-10"), DAY("2020-01-01")],
            "value": ["OLD", "NEW", "NEW", "GONE"],
        }
    )
    got = links.runs(rows, "ticker", "test", end=DAY("2020-03-31")).reset_index(drop=True)
    assert got["value"].tolist() == ["OLD", "NEW", "GONE"]
    assert got.loc[0, "valid_to"] == DAY("2020-02-09")
    assert pd.isna(got.loc[1, "valid_to"])
    assert got.loc[2, "valid_to"] == DAY("2020-01-31")


# Lookups read the period that holds each date, both ways.
def test_value_and_permno_lookups_follow_the_dates():
    table = pd.DataFrame(
        {
            "permno": [1, 1, 2],
            "kind": ["ticker"] * 3,
            "value": ["ABC", "XYZ", "ABC"],
            "valid_from": [DAY("2019-01-01"), DAY("2020-06-01"), DAY("2021-01-01")],
            "valid_to": [DAY("2020-05-31"), pd.NaT, pd.NaT],
        }
    )
    values = links.value_at(table, "ticker", [1, 1, 2], ["2020-01-15", "2021-01-15", "2020-01-15"])
    assert values.tolist()[:2] == ["ABC", "XYZ"] and pd.isna(values.iat[2])
    owners = links.permno_at(table, "ticker", ["ABC", "ABC"], ["2020-01-15", "2021-06-01"])
    assert owners.tolist() == [1, 2]


# A value two stocks share on a date maps to neither.
def test_shared_values_are_left_empty():
    table = pd.DataFrame(
        {
            "permno": [1, 2],
            "kind": ["ticker"] * 2,
            "value": ["BRK", "BRK"],
            "valid_from": [DAY("2000-01-01")] * 2,
            "valid_to": [pd.NaT] * 2,
        }
    )
    assert links.permno_at(table, "ticker", ["BRK"], ["2010-01-01"]).isna().all()


# Decisions set dated SEC ids; an unsettled second id stops the build.
def test_cik_decisions_apply_and_unsettled_stocks_fail(tmp_path):
    pd.DataFrame(
        {"permno": [1, 2, 3], "cik": [10, 20, None], "cik_compustat": [10, 21, 30]}
    ).to_parquet(tmp_path / "map.parquet")
    pd.DataFrame({"permno": [1, 2, 2], "cik": ["10", "20", "22"]}).to_parquet(
        tmp_path / "eightk.parquet"
    )
    decision = {"stocks": {"2": {"links": [[20, None, "2024-09-30"], [22, "2024-10-01", None]]}}}
    (tmp_path / "decisions.json").write_text(json.dumps(decision))
    out, report = links.ciks(
        tmp_path / "map.parquet", tmp_path / "eightk.parquet", tmp_path / "decisions.json"
    )
    two = out[out["permno"] == 2].sort_values("valid_from")
    assert two["value"].tolist() == ["20", "22"]
    assert links.value_at(out, "cik", [2, 2], ["2024-09-30", "2024-10-01"]).tolist() == ["20", "22"]
    assert out.loc[out["permno"] == 3, "source"].tolist() == ["compustat_header"]
    (tmp_path / "decisions.json").write_text(json.dumps({"stocks": {}}))
    with pytest.raises(ValueError, match="no decision"):
        links.ciks(
            tmp_path / "map.parquet", tmp_path / "eightk.parquet", tmp_path / "decisions.json"
        )


# An undated SEC id starts at its filer's first filing, never 1900 (H4).
def test_undated_cik_starts_at_the_first_filing(tmp_path):
    pd.DataFrame({"permno": [1], "cik": [None], "cik_compustat": [30]}).to_parquet(
        tmp_path / "map.parquet"
    )
    pd.DataFrame({"permno": [9], "cik": ["90"]}).to_parquet(tmp_path / "eightk.parquet")
    (tmp_path / "decisions.json").write_text(json.dumps({"stocks": {}}))
    first = pd.Series({30: DAY("2020-10-29")})
    out, _ = links.ciks(
        tmp_path / "map.parquet", tmp_path / "eightk.parquet", tmp_path / "decisions.json", first
    )
    assert out.loc[out["permno"] == 1, "valid_from"].tolist() == [DAY("2020-10-29")]
    got = links.value_at(out, "cik", [1, 1], ["2019-12-31", "2021-01-04"]).tolist()
    assert pd.isna(got[0]) and got[1] == "30"


# FINRA-style symbols find their stock: class dots, "NA", and dates.
def test_permno_by_symbol_reads_classes_na_and_dates():
    table = pd.DataFrame(
        {
            "permno": [10, 20, 30, 40],
            "kind": ["symbol", "symbol", "ticker", "ticker"],
            "value": ["BRK.B", "NA", "OLD", "NEW"],
            "valid_from": [DAY("2000-01-01")] * 3 + [DAY("2022-01-01")],
            "valid_to": [pd.NaT, pd.NaT, DAY("2021-12-31"), pd.NaT],
        }
    )
    symbols = ["BRK/B", "NA", "OLD", "OLD", "NEW", None]
    dates = [DAY("2023-01-03")] * 6
    dates[2] = DAY("2021-06-15")
    got = links.permno_by_symbol(table, symbols, dates).astype(object)
    assert [None if pd.isna(v) else v for v in got] == [10, 20, 30, None, 40, None]
