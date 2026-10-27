# The data passport on synthetic snapshots and links; no network.

import gzip
import json

import pandas as pd

from fiam.alt import coverage, passport

SEARS, PIER = passport.NAMED["Sears"][0], passport.NAMED["Pier 1"][0]


# A synthetic snapshot file in the shape Carbon Arc's replies take.
def reply(path, rows: list[dict], value: str = "spend") -> None:
    body = {"type": "dataframe", "insight_column": value, "data": rows}
    path.write_bytes(gzip.compress(json.dumps(body).encode()))


# One synthetic monthly row.
def row(date: str, spend, who: str = "WMT") -> dict:
    return {"entity_id": 729, "entity_name": who, "date": date, "spend": spend}


# Snapshot 1: two rows pre-2021, one in 2021, one month past the pull.
OLD = [row("2019-01-31", 10.0), row("2020-06-30", 20.0), row("2021-03-31", 30.0)]
OLD += [row("2026-10-31", 5.0)]


# Changed, gone and backfilled rows count; the open month never does.
def test_rewritten_counts_changes_gone_rows_and_backfill():
    new = [row("2019-01-31", 10.0), row("2020-06-30", 21.5), row("2026-10-31", 9.0)]
    new += [row("2018-12-31", 7.0), row("2026-11-30", 1.0)]
    out = passport.rewritten(pd.DataFrame(OLD), pd.DataFrame(new), "spend", "2026-10-22T16:00")
    assert out["rows_compared"] == 3
    assert (out["changed"], out["gone"], out["added_inside_span"]) == (1, 1, 1)
    assert out["share_rewritten"] == round(2 / 3, 6)
    assert (out["pre_2021_rows"], out["pre_2021_rewritten"], out["pre_2021_share"]) == (2, 1, 0.5)


# Identical snapshots rewrite nothing; text values compare as text.
def test_rewritten_is_zero_for_identical_snapshots_and_reads_text():
    same = passport.rewritten(pd.DataFrame(OLD), pd.DataFrame(OLD), "spend", "2026-10-22")
    assert same["share_rewritten"] == 0 and same["added_inside_span"] == 0
    a = pd.DataFrame([{"date": "2019-01-04", "entity_name": "X", "news": "offering"}])
    b = a.assign(news="deal")
    assert passport.rewritten(a, b, "news")["changed"] == 1


# Compared only with a same-name file in both snapshots; else why not.
def test_revision_per_set(tmp_path):
    (tmp_path / "snapshot_1").mkdir()
    reply(tmp_path / "snapshot_1" / "S.json.gz", OLD)
    assert passport.revision("S", "2026-10-22", tmp_path) == {"status": passport.PENDING}
    (tmp_path / "snapshot_2").mkdir()
    plan = {"items": [{"name": "S", "price": 0.0}]}
    (tmp_path / "snapshot_2" / "rebuy.plan.json").write_text(json.dumps(plan))
    out = passport.revision("S", "2026-10-22", tmp_path)
    assert out["status"] == "not re-bought" and "quoted 0.0" in out["why"]
    reply(tmp_path / "snapshot_2" / "N.json.gz", OLD)
    assert passport.revision("N", "2026-10-26", tmp_path)["status"] == "new in snapshot 2"
    reply(tmp_path / "snapshot_2" / "S.json.gz", OLD[:2])
    out = passport.revision("S", "2026-10-22", tmp_path)
    assert out["status"] == "compared" and out["gone"] == 1 and out["changed"] == 0


# The free download compares sorted numbers to 1e-9, not raw bytes.
def test_download_identical_differs_and_refused(tmp_path):
    for f in ("snapshot_1", "snapshot_1_refetch"):
        (tmp_path / f).mkdir()
    reply(tmp_path / "snapshot_1" / "S.json.gz", OLD)
    assert passport.download("S", tmp_path)["status"] == "refused (409)"
    shuffled = [dict(r, spend=str(r["spend"] * (1 + 4e-16))) for r in OLD[::-1]]
    reply(tmp_path / "snapshot_1_refetch" / "S.json.gz", shuffled)
    same = passport.download("S", tmp_path)
    assert same["status"] == "identical to the purchase" and same["rows_changed"] == 0
    assert same["largest_relative_change"] < 1e-9
    reply(tmp_path / "snapshot_1_refetch" / "S.json.gz", [dict(OLD[0], spend=11.0)] + OLD[1:])
    out = passport.download("S", tmp_path)
    assert out["status"] == "differs" and out["rows_changed"] == 1
    reply(tmp_path / "snapshot_1_refetch" / "S.json.gz", OLD[:3])
    out = passport.download("S", tmp_path)
    assert (out["status"], out["rows_purchase"], out["rows_download"]) == ("differs", 4, 3)
    assert passport.download("N", tmp_path)["status"] == "not tried"


# The chart's snapshot lines count each outcome in plain words.
def test_snapshot_lines_plain_words():
    same = "identical to the purchase"
    e = [
        {"revision": {"status": "not re-bought"}, "download": {"status": "refused (409)"}},
        {"revision": {"status": "not re-bought"}, "download": {"status": same}},
        {"revision": {"status": "new in snapshot 2"}, "download": {"status": "not tried"},
         "dataset": "CA0038", "measures": "net sales", "bought": "2026-10-26"},
    ]  # fmt: skip
    lines = passport.snapshot_lines(e)
    assert lines == [
        "Rebuy of 2 sets quoted 0.0 so none was bought",
        "Free download again identical for 1",
        "Free download again refused for 1",
        "CA0038 net sales new on 26 October 2026",
    ]
    assert not any(c in "".join(lines) for c in ":;-\u2013\u2014")


# Start, lag and history notes read the way the catalogue writes them.
def test_start_and_lag_readings():
    assert passport.first_year("01/2019-8/2025") == 2019
    assert passport.first_year("Retailer 1: 2007-Present") == 2007
    assert passport.lag_days("T + 3 Days") == 3 and passport.lag_days("T+1 Days") == 1
    assert passport.lag_days("Bi-Monthly Updates") is None
    dates = pd.Series(["2014-01-03"] + ["2016-02-05"] * 10 + ["2017-03-03"] * 12)
    start = passport.true_start(dates)
    assert (start["first_year"], start["first_full_year"]) == (2014, 2016)
    meta = {"table_max_date": "2026-10-18 00:00:00", "refreshed_date": "2026-10-21 14:13:03"}
    got = passport.lag(meta, "2026-10-22T16:24:29+00:00", pd.Series(["2026-10-31"]), "T + 3 Days")
    assert got["refresh_minus_table_max_days"] == 3 and got["pull_minus_table_max_days"] == 4
    assert got["last_label_after_pull"]


# Named failures are found by CRSP name, alias and brand; tickers apart.
def test_survivorship_flags_for_named_firms_and_delistings():
    table = pd.DataFrame(
        [
            (SEARS, "name", "SEARS HOLDINGS CORP (Last Known)", "2005-03-01", "2019-02-28"),
            (SEARS, "ticker", "SHLD", "2005-03-01", "2019-02-28"),
            (PIER, "name", "PIER 1 IMPORTS INC", "2000-01-01", "2020-02-28"),
            (7, "name", "ACME WIDGETS INC", "2000-01-01", "2018-05-01"),
            (8, "name", "GONE FOREVER CORP", "2000-01-01", "2019-05-01"),
        ],
        columns=["permno", "kind", "value", "valid_from", "valid_to"],
    )
    table[["valid_from", "valid_to"]] = table[["valid_from", "valid_to"]].apply(pd.to_datetime)
    carc = coverage.carc_keys(
        [
            {"carc_id": 1, "carc_name": "Sears", "entity_representation_name": "retailer"},
            {"carc_id": 2, "carc_name": "Pier 1", "entity_representation_name": "company"},
            {"carc_id": 3, "carc_name": "Acme Widgets", "entity_representation_name": "company"},
        ]
    )
    named = passport.seen(passport.named_keys(table), carc)
    assert named["Sears"] == ["brand"] and named["Pier 1"] == ["name"]
    assert named["GNC"] == [] and named["J.C. Penney"] == []
    dead = pd.DataFrame({"permno": [7, 8]})
    flags = passport.flagged(coverage.stock_keys(table, [7, 8]), carc, dead)
    assert flags.tolist() == [True, False]


# The card set gains a panel field from the debias reply, sealed window.
def test_panel_field_on_card_set(tmp_path, monkeypatch):
    from fiam.alt import common, walmart
    from fiam.vfinal.exhibits.common import FORBIDDEN, OXFORD

    rows = []
    for d, a, b in [("2019-01-31", 10, 20), ("2020-01-31", 15, 25), ("2020-12-31", 24, 30)]:
        rows += [
            {"date": d, "transaction_method": c, "credit_card_spend": 1.0,
             "credit_card_users_reference": u, "credit_card_spend_debiased": 1.0}
            for c, u in (("Online", a), ("Physical", b))
        ]  # fmt: skip
    rows.append(dict(rows[0], date="2021-01-31", credit_card_users_reference=99))
    path = tmp_path / "users.json"
    path.write_text(json.dumps({"insight_column": "credit_card_spend", "data": rows}))
    monkeypatch.setattr(walmart, "USERS", path)
    monkeypatch.setattr(common.sources, "unsealed", lambda: False)
    entries = [{"dataset": "CA0056"}, {"dataset": "CA0060"}]
    passport.add_panel(entries)
    assert "panel" not in entries[1]
    got = entries[0]["panel"]
    assert got["run_end"] == "2020-12-31" and got["rows_after_end_dropped"] == 1
    on = got["channels"]["online"]
    assert (on["first"], on["last"], on["growth_multiple"]) == (10, 24, 2.4)
    assert on["januaries"] == {"2019": 10, "2020": 15}
    assert got["channels"]["in store"]["last_full_month"] == "2020-12-31"
    line = passport.panel_line(entries)
    assert line == "Card panel users Jan 2019 to Dec 2020 grew 2.4x online, 1.5x in store"
    assert not FORBIDDEN.search(line) and not OXFORD.search(line)
    assert passport.panel_line([{"dataset": "CA0060"}]) is None
