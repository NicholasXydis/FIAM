# Dated exits (PLAN §6.4): CRSP groups and the 2026 SEC-form rule.

import pandas as pd

from fiam.v4 import exits


# CRSP actions map to merger-or-exchange and failure groups.
def test_crsp_actions_map_to_groups(tmp_path):
    folder = tmp_path / "v4" / "extracts"
    folder.mkdir(parents=True)
    pd.DataFrame(
        {
            "permno": ["1", "2", "3", "4"],
            "delistingdt": ["2019-05-01"] * 4,
            "delnextdt": ["2019-05-20", None, None, None],
            "delactiontype": ["MER", "GEX", "GLI", "GDR"],
            "delret": [0.01, 0.0, 0.0, -0.3],
        }
    ).to_parquet(folder / "crsp_delistings.parquet")
    got = exits.crsp_exits(tmp_path).set_index("permno")
    assert got["group"].tolist() == ["merger_or_exchange"] * 2 + ["failure"] * 2
    assert got.loc[1, "known"] == pd.Timestamp("2019-05-20")


# A 2026 stop is a merger (8-K 2.01), delisting (Form 25 or 15) or gap
def test_2026_stops_are_classified_by_forms_near_the_last_row(tmp_path):
    folder = tmp_path / "v4" / "clean"
    folder.mkdir(parents=True)
    day = pd.Timestamp("2026-05-15")
    pd.DataFrame(
        {
            "permno": [1, 2, 3],
            "form": ["8-K", "25-NSE", "25-NSE"],
            "items": ["2.01,9.01", None, None],
            "filing_date": [day, day - pd.Timedelta(days=10), day + pd.Timedelta(days=200)],
            "accession": ["a1", "a2", "a3"],
            "available_at": pd.to_datetime(["2026-05-15 20:00"] * 3, utc=True),
        }
    ).to_parquet(folder / "edgar_filings.parquet")
    last = pd.Series([day, day, day], index=pd.Index([1, 2, 3], name="permno"))
    got = exits.sec_exits(tmp_path, last).set_index("permno")["category"]
    assert got.to_dict() == {1: "merger", 2: "delisted", 3: "data_gap"}
