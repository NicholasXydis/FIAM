# The network map on synthetic books, filings and links.

import numpy as np
import pandas as pd

from fiam.alt import network as nw

T = pd.Timestamp("2020-12-31")
PERIODS = pd.to_datetime(["2019-09-30", "2019-12-31", "2020-03-31", "2020-06-30", "2020-09-30"])


# Synthetic 13F lines: a churner, a holder and a split in stock 3.
def held_frame() -> pd.DataFrame:
    rows = []
    for k, p in enumerate(PERIODS):
        # The churner swaps stock 1 for stock 2 every quarter.
        held = 1 if k % 2 == 0 else 2
        rows.append((1, p, held, 1000.0, 100.0, 100.0))
        # The holder keeps 100 shares of stock 3, which splits 2:1 at k=3.
        shares = 100.0 if k < 3 else 200.0
        rows.append((2, p, 3, 1000.0, shares, shares))
        # Five more holders of stock 3 so the split guard can see it.
        for f in range(3, 8):
            rows.append((f, p, 3, 500.0, shares / 2, shares / 2))
    cols = ["filer_cik", "period", "permno", "value_usd", "shares", "shares_sole"]
    return pd.DataFrame(rows, columns=cols)


# A positions file with values becomes weights over gross.
def test_read_book_values(tmp_path):
    p = tmp_path / "book.csv"
    p.write_text("date,permno,value\n2026-08-31,1,300\n2026-08-31,2,-100\n")
    book, day = nw.read_book(p)
    assert day == pd.Timestamp("2026-08-31")
    assert np.isclose(book["weight"].abs().sum(), 1.0)
    assert np.isclose(book.set_index("permno").loc[1, "weight"], 0.75)


# A weights file without a date takes the date given.
def test_read_book_weights(tmp_path):
    p = tmp_path / "book.csv"
    p.write_text("permno,ticker,weight\n1,AAA,0.02\n2,,-0.01\n")
    book, day = nw.read_book(p, "2026-08-31")
    assert day == pd.Timestamp("2026-08-31")
    assert book["weight"].tolist() == [0.02, -0.01]


# A dated book keeps only its latest date on or before the date asked.
def test_read_book_two_dates(tmp_path):
    p = tmp_path / "book.csv"
    p.write_text("date,permno,value\n2026-07-31,1,100\n2026-07-31,2,-100\n"
                 "2026-08-31,1,300\n2026-08-31,3,-100\n")  # fmt: skip
    book, day = nw.read_book(p)
    assert day == pd.Timestamp("2026-08-31") and book["permno"].tolist() == [1, 3]
    assert np.isclose(book.set_index("permno").loc[1, "weight"], 0.75)
    book, day = nw.read_book(p, "2026-08-15")
    assert day == pd.Timestamp("2026-07-31") and book["permno"].tolist() == [1, 2]
    assert np.isclose(book.set_index("permno").loc[1, "weight"], 0.5)
    assert nw.AXIS[book.attrs["basis"]] == "Percent of book gross"


# A weights file keeps the NAV axis.
def test_read_book_weights_axis(tmp_path):
    p = tmp_path / "book.csv"
    p.write_text("permno,weight\n1,0.02\n")
    assert nw.AXIS[nw.read_book(p, "2026-08-31")[0].attrs["basis"]] == "Percent of NAV"


# Dated CRSP links: tickers in force at the seal and 2015-2020 names.
def seal_links() -> pd.DataFrame:
    rows = [
        (1, "ticker", "ABC", "2012-01-01", None),
        (1, "name", "OLDCO INC", "2012-01-01", None),
        (2, "ticker", "REN", "2012-01-01", None),
        (2, "name", "FORMER NAME CORP", "2012-01-01", None),
        (3, "ticker", "GOOD", "2012-01-01", None),
        (3, "name", "GOOD WIDGETS INC", "2012-01-01", None),
    ]
    f = pd.DataFrame(rows, columns=["permno", "kind", "value", "valid_from", "valid_to"])
    return f.assign(
        valid_from=pd.to_datetime(f["valid_from"]), valid_to=pd.to_datetime(f["valid_to"])
    )


# Carbon Arc's free list: today's tickers and company names.
def carc_list() -> list[dict]:
    ents = [("ABC", "ticker"), ("REN", "ticker"), ("GOOD", "ticker"), ("NewCo Inc", "company"),
            ("Renamed Holdings", "company"), ("Good Widgets", "company")]  # fmt: skip
    return [{"carc_id": i, "carc_name": n, "entity_representation_name": r}
            for i, (n, r) in enumerate(ents)]  # fmt: skip


# A reused ticker and a renamed firm are refused; a named match stays.
def test_name_check_reused_ticker_and_renamed_firm():
    book = pd.DataFrame({"permno": [1, 2, 3, 4], "weight": [0.1, 0.1, -0.1, 0.1],
                         "ticker": [None, None, None, "abc"]})  # fmt: skip
    links = seal_links()
    filled = nw.fill_tickers(book, links)
    out, refused = nw.name_check(filled, links, carc_list(), {"ABC", "REN", "GOOD"})
    assert out["carc_match"].tolist() == [False, False, True, True]
    assert refused == 2
    rows = pd.DataFrame({"entity_name": ["ABC", "REN"], "relationship_filter": ["vendor"] * 2,
                         "affiliated_entity_name": ["GOOD", "GOOD"]})  # fmt: skip
    e, _ = nw.carbon_edges(rows, out)
    assert set(map(tuple, e[["a", "b"]].values)) == {(3, 4)}


# Missing tickers come from the pre-seal CRSP ticker, labelled.
def test_fill_tickers():
    book = pd.DataFrame({"permno": [1, 2, 3], "weight": [0.1, -0.1, 0.1],
                         "ticker": ["aaa", None, None]})  # fmt: skip
    links = pd.DataFrame({
        "permno": [2, 2], "kind": ["ticker", "ticker"], "value": ["OLD", "BBB"],
        "valid_from": pd.to_datetime(["2010-01-01", "2015-01-01"]),
        "valid_to": [pd.Timestamp("2014-12-31"), pd.NaT],
    })  # fmt: skip
    out = nw.fill_tickers(book, links)
    assert out["ticker"].tolist()[:2] == ["AAA", "BBB"]
    assert out["ticker_source"].tolist() == ["book", "crsp_pre_seal", "none"]


# Only vendor and partner rows between two book names become edges.
def test_carbon_edges():
    book = pd.DataFrame({"permno": [1, 2, 3], "ticker": ["AAA", "BBB", "CCC"]})
    rows = pd.DataFrame({
        "entity_name": ["AAA", "BBB", "AAA", "AAA", "ZZZ"],
        "relationship_filter": ["vendor", "partner", "other", "partner", "vendor"],
        "affiliated_entity_name": ["BBB", "AAA", "CCC", "BBB", "AAA"],
    })  # fmt: skip
    e, log = nw.carbon_edges(rows, book)
    assert set(map(tuple, e[["a", "b", "type"]].values)) == {(1, 2, "supplier"), (1, 2, "partner")}
    assert log["rows_kept_kinds"] == 4


# The churner turns over; the split does not count as trading.
def test_churn_and_split():
    rate = nw.churn(held_frame(), T)
    assert rate.loc[1] > 1.5
    assert np.isclose(rate.loc[2], 0.0)
    assert rate.drop(1).abs().max() < 1e-9


# A filer whose latest report is stale is not ranked at all.
def test_stale_filer_out():
    h = held_frame()
    old = h[h["filer_cik"] == 2].assign(filer_cik=99)
    old = old[old["period"] <= pd.Timestamp("2020-03-31")]
    rate = nw.churn(pd.concat([h, old]), T)
    assert 99 not in rate.index


# The top third by churn are short; their sole value is kept.
def test_short_owners():
    h = held_frame()
    rate = nw.churn(h, T)
    own = nw.short_owners(h, rate, T)
    assert 1 in set(own["filer_cik"])
    assert (own["value_sole"] > 0).all()


# Anton-Polk overlap: shared value over both caps, shared counts.
def test_overlap_numbers():
    own = pd.DataFrame({"filer_cik": [1, 1, 2, 2, 3], "permno": [10, 20, 10, 20, 30],
                        "value_sole": [1e6, 2e6, 3e6, 4e6, 5e6]})  # fmt: skip
    caps = pd.Series({10: 10.0, 20: 30.0, 30: 5.0})
    pairs = nw.overlap(own, caps, [10, 20, 30])
    row = pairs[(pairs["a"] == 10) & (pairs["b"] == 20)].iloc[0]
    assert row["shared"] == 2
    assert np.isclose(row["fcap"], (1e6 + 2e6 + 3e6 + 4e6) / 40e6)
    assert len(pairs) == 1


# The edge rule keeps pairs with two owners in the top share.
def test_owner_edges_rule():
    pairs = pd.DataFrame({"a": range(100), "b": range(1, 101), "fcap": np.linspace(0, 1, 100),
                          "shared": [2] * 99 + [1]})  # fmt: skip
    e = nw.owner_edges(pairs)
    assert len(e) == 1 and e["fcap"].iloc[0] == pairs["fcap"].iloc[98]
    assert (e["type"] == "shared_13f_owners").all()


# Two cliques joined by one edge split into two communities.
def test_louvain_two_cliques():
    a = np.zeros((8, 8))
    for block in (range(0, 4), range(4, 8)):
        for i in block:
            for j in block:
                if i != j:
                    a[i, j] = 1
    a[3, 4] = a[4, 3] = 1
    labels = nw.louvain(a)
    assert len(set(labels[:4])) == 1 and len(set(labels[4:])) == 1
    assert labels[0] != labels[7]
    assert nw.modularity(a, labels) > 0.3


# An empty graph leaves every node alone.
def test_louvain_empty():
    assert nw.louvain(np.zeros((3, 3))).tolist() == [0, 1, 2]


# Union-find components, labelled in node order.
def test_components():
    assert nw.components(5, [(0, 1), (3, 4)]).tolist() == [0, 0, 1, 2, 2]


# The whole map: clusters, net exposure and the hidden flag.
def test_build_clusters(tmp_path):
    book = pd.DataFrame({
        "permno": [1, 2, 3, 4, 5, 6],
        "weight": [0.05, 0.04, -0.01, -0.03, -0.02, 0.01],
        "ticker": ["A", "B", "C", "D", "E", "F"],
    })  # fmt: skip
    carbon = pd.DataFrame({"a": [1], "b": [2], "type": ["supplier"]})
    owner = pd.DataFrame({"a": [2, 1, 4], "b": [3, 3, 5], "fcap": [0.1, 0.2, 0.3],
                          "shared": [3, 2, 4], "type": "shared_13f_owners"})  # fmt: skip
    sectors = pd.Series({1: "Energy", 2: "Materials", 3: "Energy", 4: "Utilities", 5: "Utilities"})
    res = nw.build(book, carbon, owner, sectors)
    c = res["clusters"]
    first = c.iloc[0]
    assert first["names"] == 3 and np.isclose(first["net"], 0.08)
    assert bool(first["hidden"])
    assert not bool(c[c["names"] == 2]["hidden"].iloc[0])
    assert res["isolated"] == 1
    nw.chart(c, "Hidden clusters in a test book", "Synthetic data", tmp_path / "x.png")
    assert (tmp_path / "x.png").stat().st_size > 0
