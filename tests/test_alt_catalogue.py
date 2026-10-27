# Piece 10's catalogue screen on a small synthetic catalogue.

import json

import pandas as pd

from fiam.alt import catalogue_screen as cs


# History labels give their starts, earliest first, in each format.
def test_history_starts():
    two = cs.history_starts("1960 - Present: Start Dates, 10/2022 - Present: Panel")
    assert two == [pd.Timestamp("1960-01-01"), pd.Timestamp("2022-10-01")]
    assert cs.history_starts("March 2024 - Present") == [pd.Timestamp("2024-03-01")]
    assert cs.history_starts("3Q2023–Present") == [pd.Timestamp("2023-07-01")]
    assert cs.history_starts("01/2019-8/2025") == [pd.Timestamp("2019-01-01")]
    assert cs.history_starts("2020") == [pd.Timestamp("2020-01-01")]
    assert cs.history_starts("N/A") == []
    assert cs.history_starts(None) == []


# Lags read as their longest stated number of days.
def test_lag_days():
    assert cs.lag_days("T + 1 Week to 6 months, depending on the County") == 180
    assert abs(cs.lag_days("T + 4 Hours") - 1 / 6) < 1e-9
    assert cs.lag_days("T + 4-8 Weeks") == 56
    assert cs.lag_days("Bi-Monthly Updates") is None
    assert cs.lag_stated("Bi-Monthly Updates")
    assert not cs.lag_stated("N/A") and not cs.lag_stated(None)


# Columns sort into as-of, delivery and overwrite stamps.
def test_classify_columns_and_keys():
    cols = {"knowledge_date": "", "drop_partition": "", "updated_at": "", "price": ""}
    got = cs.classify_columns(cols)
    assert got == {
        "asof": ["knowledge_date"],
        "version": ["drop_partition"],
        "overwrite": ["updated_at"],
    }
    assert cs.entity_keys({"ticker": "", "zip_code": ""}) == ["ticker", "zip"]
    assert cs.entity_keys({"value": ""}) == []


# Dead firms count only when a firm panel's own words say so.
def test_dead_firms_words():
    facts = {
        "columns": {"asof": [], "version": [], "overwrite": []},
        "column_names": ["ticker"],
        "firm_key": True,
        "lag_days": 1,
        "lag_stated": True,
        "date_added": pd.Timestamp("2024-01-01"),
        "history_start": pd.Timestamp("2015-01-01"),
        "backfill_labels": 0,
    }
    yes = cs.four_answers("Coverage . ~5,200 stocks (live and inactive)", facts)
    assert yes["dead_firms"] == "yes"
    cards = cs.four_answers("The vendor removes inactive cards each month", facts)
    assert cards["dead_firms"] == "unknown"
    assert "rows before 2024-01-01 loaded when listed" in cards["first_knowable"]
    assert cards["entity_map"].startswith("Carbon Arc ticker")


# Writes one source's five documents into a synthetic catalogue folder.
def write_source(folder, sid, columns, sample_rows=None, missing_dict=False):
    d = folder / sid
    d.mkdir(parents=True)
    dic = {"missing": "404"} if missing_dict else [{"label": "t", "columns": columns}]
    (d / "dictionary.json").write_text(json.dumps(dic))
    sample = {"samples": [{"data": sample_rows or []}]}
    (d / "sample.json").write_text(json.dumps(sample))
    (d / "information.json").write_text(json.dumps({"description": f"{sid} text"}))
    (d / "insights.json").write_text(json.dumps({"items": [{"blocked": 0}]}))


# The whole screen: denominator, funnel and the four answers per row.
def test_screen_and_summary(tmp_path):
    spec = {"description": "x"}
    write_source(
        tmp_path,
        "CA1",
        {"ticker": spec, "knowledge_date": spec, "date": spec},
        sample_rows=[{"drop_partition": "Full-backfill-2016-12-31"}],
    )
    write_source(tmp_path, "CA2", {"zip_code": spec, "updated_at": spec})
    write_source(tmp_path, "CA3", {"ticker": spec})
    write_source(tmp_path, "CA4", {}, missing_dict=True)
    write_source(tmp_path, "CA9_1", {"company_id": spec, "date": spec})
    meta = {"Date Added": "10/08/2024", "Type": "Wallet", "Frequency": "Daily"}
    listing = {
        "datasources": [
            {
                "dataset_id": ["CA1"],
                "dataset_name": "One",
                "provider_name": "P",
                "blocked": False,
                "data": {**meta, "History": "2014-Present", "Lag": "T + 1 Days"},
            },
            {
                "dataset_id": ["CA2"],
                "dataset_name": "Two",
                "provider_name": "",
                "blocked": False,
                "data": {**meta, "History": "2010-Present", "Lag": "T + 7 Days"},
            },
            {
                "dataset_id": ["CA3"],
                "dataset_name": "Three",
                "provider_name": "",
                "blocked": True,
                "data": {**meta, "History": "2010-Present", "Lag": "T + 7 Days"},
            },
            {
                "dataset_id": ["CA4"],
                "dataset_name": "Four",
                "provider_name": "",
                "blocked": False,
                "data": {**meta, "History": "2010-Present", "Lag": "N/A"},
            },
            {
                "dataset_id": ["CA9_1"],
                "dataset_name": "Web",
                "provider_name": "",
                "blocked": False,
                "data": {**meta, "is_webcontent": "true", "Start Date": "2023-03-01"},
            },
        ]
    }
    (tmp_path / "datasets.json").write_text(json.dumps(listing))
    (tmp_path / "manifest.json").write_text(json.dumps({"pulled_at": "2026-10-22T13:27"}))
    out = tmp_path / "out"
    got = cs.main(tmp_path, out)
    assert got["denominator"] == "4 screened, 1 usable for a backtest, none traded"
    assert got["usable_for_backtest"] == ["CA1"]
    assert got["web_catalogues"] == 1 and got["web_catalogues_usable"] == 0
    assert [s["left"] for s in got["funnel"]] == [4, 3, 2, 2, 1, 1, 1]
    table = pd.read_csv(out / "catalogue_screen.csv").set_index("dataset_id")
    assert table.loc["CA1", "first_knowable"].startswith("dated by knowledge_date")
    assert table.loc["CA1", "revised"] == "yes"
    assert table.loc["CA2", "fails_at"] == "no firm key"
    assert table.loc["CA2", "revised_evidence"] == "overwrite stamp updated_at"
    assert table.loc["CA3", "fails_at"] == "blocked"
    assert table.loc["CA4", "fails_at"] == "no dictionary saved"
    assert not table["traded"].any()
    assert (out / "catalogue_funnel.png").exists()
    assert got["catalogue_pulled_at"] == "2026-10-22"
