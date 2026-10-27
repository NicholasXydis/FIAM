# The dated link table on tiny synthetic inputs.

import json

import pandas as pd
import pytest

from fiam.vfinal import links

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


# An undated SEC id starts at its filer's first filing, never 1900.
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


# Both name keys agree, and spelled-out letters join into one word.
def test_entity_keys_agree_and_join_letters(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    tools = Path(links.__file__).resolve().parents[2] / "tools" / "data"
    monkeypatch.setattr(sys, "path", [str(tools), *sys.path])
    spec = importlib.util.spec_from_file_location("edgar_tool", tools / "edgar.py")
    edgar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edgar)
    cases = [("T C F FINANCIAL CORP", "FINL TCF"), ("WALT DISNEY CO/", "DISNEY WALT")]
    cases += [
        ("A T & T INC", "AND AT T"),
        ("Knight-Swift Transportation Holdings Inc.", "KNIGHT SWIFT TRANSPORTATION"),
    ]
    cases += [("U.S. SILICA HOLDINGS, INC.", "SILICA US"), ("U S SILICA HOLDINGS INC", "SILICA US")]
    cases += [("F 5 NETWORKS INC", "F5 NETWORKS"), ("B/E AEROSPACE INC", "AEROSPACE BE")]
    cases += [("LIBERTY MEDIA CORP 3RD NEW", "LIBERTY MEDIA"), ("1ST SOURCE CORP", "1ST SOURCE")]
    cases += [("INDEPENDENT BANK CORP MA", "BANK INDEPENDENT MA")]
    for name, key in cases:
        assert links.entity_key(name) == key == edgar.entity_key(name)
    # CRSP's short forms meet the SEC's full words; others stay apart.
    same = [("MONOLITHIC PWR SYS INC", "MONOLITHIC POWER SYSTEMS INC")]
    same += [("AMERICAN NATIONAL INS CO", "AMERICAN NATIONAL INSURANCE CO /TX/")]
    same += [("HARMAN INTL INDS INC NEW", "HARMAN INTERNATIONAL INDUSTRIES INC /DE/")]
    for crsp, sec in same:
        assert links.entity_key(crsp) == links.entity_key(sec) == edgar.entity_key(sec)
    assert links.entity_key("PENNYMAC FINANCIAL SVCS INC") != links.entity_key("PNC FINANCIAL")
    assert links.entity_key("ACME MANUFACTURING CO") == edgar.entity_key("ACME MFG CO")
    # "/OLD" marks a predecessor, so it stays a word; state tags go.
    assert links.entity_key("HarborOne Bancorp, Inc./OLD") == "BANCORP HARBORONE OLD"
    assert links.entity_key("INDEPENDENT BANK CORP /MA/") == "BANK INDEPENDENT"
    cases = [("WEB.COM GROUP, INC.", "COM WEB"), ("Zoe's Kitchen, Inc.", "KITCHEN ZOES")]
    cases += [
        ("O-I Glass, Inc. /DE/", "GLASS OI"),
        ("WORLD WRESTLING ENTERTAINMENTINC", "ENTMT WORLD WRESTLING"),
    ]
    for name, key in cases:
        assert links.entity_key(name) == key == edgar.entity_key(name)
    assert links.overlap("HLDGS KNIGHT SWIFT TRANSPORTATION", "KNIGHT SWIFT TRANSPORTATION") > 0.8
    assert links.overlap("AMERICAS CARMART", "AMERICAS CAR MART") == 1.0
    assert links.overlap("AMERICAS CAR", "AMERICAS CAR MART") == 0.8


# On real links, no stock takes a filer before its first SEC filing.
@pytest.mark.skipif(
    not (links.DATA / "edgar" / "cik_first_filing.parquet").exists(), reason="no data"
)
def test_real_links_never_precede_the_first_filing():
    lk = pd.read_parquet(links.DATA / "v4" / "links.parquet")
    lk = lk[(lk["kind"] == "cik") & lk["source"].eq("sec_dated_names")]
    first = pd.read_parquet(links.DATA / "edgar" / "cik_first_filing.parquet")
    first["value"] = first["cik"].astype(str)
    both = lk.merge(first[["value", "first_filing"]], on="value")
    early = both["valid_from"] + pd.offsets.MonthEnd(0) < both["first_filing"]
    assert int(early.sum()) == 0


# On real links, an SEC id sits on two companies only with equal names.
@pytest.mark.skipif(not (links.DATA / "v4" / "links.json").exists(), reason="no data")
def test_real_ciks_rarely_shared_between_companies():
    report = json.loads((links.DATA / "v4" / "links.json").read_text())
    assert report["cik_months_shared_by_equal_names"] <= 400
    assert report["cik_dated_stocks"] >= 7000
