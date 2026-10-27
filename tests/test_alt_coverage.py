# Carbon Arc coverage matching on synthetic entities and links only.

import pandas as pd

from fiam.alt import coverage

DAY = pd.Timestamp


# One synthetic Carbon Arc entity as the free entity list gives it.
def ent(carc_id: int, name: str, rep: str) -> dict:
    return {"carc_id": carc_id, "carc_name": name, "entity_representation_name": rep}


# Dated link rows in the shape of the links table.
def links(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["permno", "kind", "value", "valid_from", "valid_to"])
    frame["valid_from"] = pd.to_datetime(frame["valid_from"])
    frame["valid_to"] = pd.to_datetime(frame["valid_to"])
    return frame


# CRSP's surname-first, spelled-out names meet Carbon Arc's labels.
def test_compact_names_meet_across_spellings():
    assert coverage.compact("PENNEY J C CO INC (Last Known)") == coverage.compact("JCPenney")
    assert coverage.compact("G N C HOLDINGS INC") == coverage.compact("GNC Holdings")
    assert coverage.compact("WALMART INC") == coverage.compact("Walmart Inc.")
    assert coverage.compact("PIER 1 IMPORTS INC") != coverage.compact("Pier 1")


# Foreign tickers, categories, places and short names never become keys.
def test_carc_keys_keep_us_tickers_firms_and_brands_only():
    keys = coverage.carc_keys(
        [
            ent(1, "WMT", "ticker"),
            ent(2, "4578 JP", "ticker"),
            ent(3, "Walmart Inc.", "company"),
            ent(4, "Sears", "retailer"),
            ent(5, "Department Stores", "category"),
            ent(6, "10001", "zip"),
            ent(7, "GE", "company"),
        ]
    )
    got = dict(zip(keys["carc_id"], keys["how"]))
    assert got == {1: "ticker", 3: "name", 4: "brand"}


# A reused ticker belongs to its latest holder; old periods drop out.
def test_stock_keys_give_reused_tickers_to_the_latest_holder():
    table = links(
        [
            (1, "ticker", "ABC", "2010-01-01", "2016-06-30"),
            (2, "ticker", "ABC", "2018-01-01", None),
            (1, "name", "ALPHA BETA CORP", "2010-01-01", "2016-06-30"),
            (3, "ticker", "OLD", "2000-01-01", "2010-12-31"),
            (3, "name", "OLDCO INC", "2000-01-01", "2010-12-31"),
            (3, "name", "FRESHCO INC", "2011-01-01", None),
        ]
    )
    keys = coverage.stock_keys(table, [1, 2, 3])
    got = set(map(tuple, keys[["permno", "how", "key"]].to_numpy()))
    assert (2, "ticker", "ABC") in got and (1, "ticker", "ABC") not in got
    assert (1, "name", "ALPHABETA") in got
    assert (3, "name", "FRESHCO") in got and (3, "name", "OLDCO") not in got
    assert not any(k == "OLD" for _, _, k in got)


# Tickers meet tickers and names meet names or brands, never across.
def test_flags_never_cross_tickers_with_names():
    stocks = pd.DataFrame(
        [(1, "ticker", "TGT"), (1, "name", "TARGET"), (2, "name", "SEARS"), (3, "name", "KMART")],
        columns=["permno", "how", "key"],
    )
    carc = coverage.carc_keys(
        [ent(1, "TGT", "ticker"), ent(2, "Sears", "retailer"), ent(3, "KMART", "ticker")]
    )
    flag = coverage.flags(stocks, carc).set_index("permno")
    assert flag.loc[1, "ticker"] and flag.loc[1, "covered"] and not flag.loc[1, "name"]
    assert flag.loc[2, "brand"] and not flag.loc[2, "covered"]
    assert not flag.loc[3].any()


# Listed against delisted 2015-2020, merger and failure kept apart.
def test_summary_splits_listed_and_delisted():
    exits = pd.DataFrame(
        {
            "permno": [2, 3, 4],
            "exit_date": [DAY("2017-05-01"), DAY("2019-01-02"), DAY("2012-01-02")],
            "group": ["failure", "merger_or_exchange", "failure"],
        }
    )
    stat = coverage.status([1, 2, 3, 4], exits)
    assert stat.set_index("permno")["status"].to_dict() == {
        1: "listed",
        2: "delisted",
        3: "delisted",
        4: "listed",
    }
    flag = pd.DataFrame(
        {
            "permno": [1, 2, 3, 4],
            "ticker": [True, True, False, False],
            "name": [True, False, False, False],
            "brand": [False, False, True, False],
        }
    )
    flag["covered"] = flag["ticker"] | flag["name"]
    out = coverage.summary(flag, stat, last={1, 4})
    assert (out["universe"], out["covered"], out["brand_only"]) == (4, 2, 1)
    assert (out["listed"], out["listed_covered"]) == (2, 1)
    assert (out["delisted"], out["delisted_covered"]) == (2, 1)
    assert out["delisted_failure_covered"] == 1 and out["delisted_merger_or_exchange"] == 1
    assert (out["last_month"], out["last_month_covered"]) == (2, 1)
