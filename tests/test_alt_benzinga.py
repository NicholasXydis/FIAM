# The Benzinga vs SEC audit on synthetic rows and filings.

import gzip
import json

import pandas as pd

from fiam.alt import benzinga_audit as ba

SESSIONS = pd.bdate_range("2019-11-01", "2020-03-31")


# An Eastern wall-clock time as the UTC stamp the registry stores.
def eastern(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz=ba.EASTERN).tz_convert("UTC")


# Synthetic SEC filings: stock, kind and public instant.
def filings(items) -> pd.DataFrame:
    f = pd.DataFrame(items, columns=["permno", "kind", "available_at"])
    f["available_at"] = pd.to_datetime(f["available_at"], utc=True)
    f["day"] = ba.public_day(f["available_at"])
    return f


# A label's window runs 5 sessions before its week to 5 after it.
def test_windows():
    labels = pd.Series(pd.to_datetime(["2020-01-10", "2019-11-01"]))
    lo, hi = ba.windows(labels, SESSIONS)
    assert lo[0] == pd.Timestamp("2019-12-30") and hi[0] == pd.Timestamp("2020-01-17")
    # Too close to the calendar's start: no window, never a short one.
    assert pd.isna(lo[1]) and pd.isna(hi[1])


# The label's day ends at 23:59:59 Eastern, stored in UTC.
def test_label_end_and_public_day():
    end = ba.label_end(pd.Series(pd.to_datetime(["2020-01-10"])))
    assert end[0] == pd.Timestamp("2020-01-11 04:59:59", tz="UTC")
    day = ba.public_day(pd.Series([eastern("2020-01-10 22:30")]))
    assert day[0] == pd.Timestamp("2020-01-10")


# Rows of each kind meet only same-kind filings of their own stock.
def test_match_first_and_nearest():
    rows = pd.DataFrame({"permno": [1, 1, 2], "kind": ["deals", "insider", "deals"]})
    rows["label"] = pd.to_datetime(["2020-01-10"] * 3)
    rows["lo"], rows["hi"] = ba.windows(rows["label"], SESSIONS)
    f = filings(
        [
            (1, "deals", eastern("2020-01-02 10:00")),
            (1, "deals", eastern("2020-01-09 10:00")),
            (1, "deals", eastern("2020-02-20 10:00")),
            (1, "offerings", eastern("2020-01-09 10:00")),
            (3, "deals", eastern("2020-01-09 10:00")),
        ]
    )
    got = ba.match(rows, f)
    assert got["n_filings"].tolist() == [2, 0, 0]
    assert got.loc[0, "first_day"] == pd.Timestamp("2020-01-02")
    assert got.loc[0, "nearest_day"] == pd.Timestamp("2020-01-09")


# The full row audit: groups, look-ahead, the clock bound and chance.
def test_audit_lookahead_and_groups():
    rows = pd.DataFrame(
        {
            "kind": ["deals", "deals", "offerings", "insider"],
            "ticker": ["A", "B", "C", "Z"],
            "label": pd.to_datetime(["2020-01-10", "2020-01-10", "2020-01-10", "2020-01-10"]),
            "year": 2020,
        }
    )
    permno = pd.Series([1, 2, 3, None], dtype="Int64")
    f = filings(
        [
            (1, "deals", eastern("2020-01-13 09:00")),
            (2, "deals", eastern("2020-01-11 03:00")),
            (3, "offerings", eastern("2020-01-08 09:00")),
            (3, "offerings", eastern("2019-07-10 09:00")),
        ]
    )
    done = ba.audit(
        rows,
        SESSIONS.append(pd.bdate_range("2019-01-01", "2019-10-31")).sort_values(),
        f,
        permno,
        departed={2},
        covered={1, 2, 3},
    )
    assert done["group"].tolist() == ["listed", "departed", "listed", "unmapped"]
    assert done["matched"].tolist() == [True, True, True, False]
    # Monday's filing is after the label, at any clock reading.
    assert done.loc[0, "lookahead"] and done.loc[0, "lookahead_early"]
    # Saturday 03:00 may be Friday 22:00 under the other reading.
    assert done.loc[1, "lookahead"] and not done.loc[1, "lookahead_early"]
    assert not done.loc[2, "lookahead"]
    # Twenty-six weeks earlier only stock 3 has a filing in the window.
    assert done["placebo_matched"].tolist() == [False, False, True, False]
    table = ba.table(done)
    deals = table[(table["kind"] == "deals") & (table["year"] == "2014-2020")]
    whole = deals[deals["group"] == "all"].iloc[0]
    assert whole["match_rate"] == 1.0 and whole["lookahead_share"] == 1.0
    assert whole["lookahead_share_early_clock"] == 0.5
    insider = table[(table["kind"] == "insider") & (table["group"] == "unmapped")].iloc[0]
    assert insider["rows"] == 1 and insider["covered"] == 0 and pd.isna(insider["match_rate"])


# SEC filing-weeks seen by a Benzinga row, for listed and departed.
def test_recall():
    rows = pd.DataFrame({"kind": ["deals"], "permno": pd.Series([1], dtype="Int64")})
    rows["label"] = pd.to_datetime(["2020-01-10"])
    rows["lo"], rows["hi"] = ba.windows(rows["label"], SESSIONS)
    f = filings(
        [
            (1, "deals", eastern("2020-01-08 10:00")),
            (1, "deals", eastern("2020-01-09 10:00")),
            (2, "deals", eastern("2020-01-09 10:00")),
        ]
    )
    got = ba.recall(rows, f, departed={2})["deals"]["2014-2020"]
    assert got["listed"] == {"filing_weeks": 1, "with_a_benzinga_row": 1, "share": 1.0}
    assert got["departed"]["share"] == 0.0


# The bought files load as rows; labels after the pull are counted.
def test_load_and_label_check(tmp_path):
    cols = {
        "497": "capital_markets_activity",
        "501": "mergers_and_acquisitions",
        "461": "news_event",
    }
    for insight, col in cols.items():
        data = [
            {"entity_name": "AAA", "date": "2020-01-10", col: "x"},
            {"entity_name": "BBB", "date": "2026-10-23", col: "x"},
        ]
        with gzip.open(tmp_path / f"CA0035_{insight}.json.gz", "wt") as fh:
            json.dump({"insight_column": col, "data": data}, fh)
        receipt = {
            "rows": 2,
            "pulled_at": "2026-10-22T15:55:32+00:00",
            "metadata": {
                "table_max_date": "2026-10-16",
                "payload": {
                    "filters": {"date_resolution": "week", "date_range": {"end_date": "2026-10-16"}}
                },
            },
        }
        (tmp_path / f"CA0035_{insight}.receipt.json").write_text(json.dumps(receipt))
    rows = ba.load_benzinga(tmp_path)
    assert len(rows) == 6 and set(rows["kind"]) == {"offerings", "deals", "insider"}
    check = ba.label_check(rows, ba.receipts(tmp_path))
    assert check["weekday_counts"]["deals"] == {"Friday": 2}
    assert check["labels_after_pull"]["deals"]["rows"] == 1
    assert ba.drift(rows)["rows"].sum() == 6


# Bars cover every matched row, holidays past day 7 or -13 included.
def test_day_counts_sum_to_rows(tmp_path):
    label = pd.Timestamp("2020-01-10")
    part = pd.DataFrame({"kind": "deals", "label": label, "matched": True,
                         "nearest_day": label + pd.to_timedelta([-15, -13, 0, 3, 9], "D"),
                         "lookahead": [False, False, False, True, True],
                         "lookahead_nearest": [False, False, False, True, True]})  # fmt: skip
    counts = ba.day_counts(part)
    assert counts.sum() == len(part) and counts.index.min() == -15 and counts.index.max() == 9
    assert ba.day_counts(part.iloc[2:4]).index.tolist() == list(range(-13, 8))
    rows = pd.concat([part.assign(kind=k) for k in ("deals", "offerings", "insider")])
    ba.chart(rows, tmp_path / "b.png")
    assert (tmp_path / "b.png").stat().st_size > 0


# Order count to delivered rows to loaded rows, step by step.
def test_reconcile_order_count_to_audit_rows(tmp_path):
    folder = tmp_path / "snapshot_1"
    folder.mkdir()
    labels = {"497": "capital_markets_activity", "501": "mergers_and_acquisitions"}
    labels["461"] = "news_event"
    sizes = {"497": 2, "501": 3, "461": 1}
    for insight, col in labels.items():
        data = [
            {"entity_name": "AAA", "date": "2020-01-10", "entity_id": 1, col: "x"}
            for _ in range(sizes[insight])
        ]
        body = {"insight_column": col, "total": len(data), "data": data}
        (folder / f"CA0035_{insight}.json.gz").write_bytes(gzip.compress(json.dumps(body).encode()))
        (folder / f"CA0035_{insight}.receipt.json").write_text(json.dumps({"rows": len(data)}))
    order = {"order_id": "o1", "total_records_count": 9}
    (folder / "bundle_order.json").write_text(json.dumps(order))
    got = ba.reconcile(folder)
    steps = got["steps"]
    assert [s["rows"] for s in steps] == [9, 6, 6]
    assert steps[1]["change"] == -3 and steps[2]["change"] == 0
    assert steps[1]["by_insight"] == {"offerings": 2, "deals": 3, "insider": 1}
    assert got["kept_as_delivered"]["exact_duplicate_rows"]["deals"] == 2
    assert got["evidence_order_counts_are_pre_rollup"] == []
