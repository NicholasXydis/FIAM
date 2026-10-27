# The registry's bans, blind mode and point-in-time traps.

from pathlib import Path

import pandas as pd
import pytest

from fiam.vfinal import clock, guards, sources

SEALED_DAY = pd.Timestamp("2021-01-04")


# A tiny clean folder: a panel and a daily file either side of the seal.
@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CLEAN", tmp_path)
    cal = clock.calendar(clock.xnys_sessions("2020-11-01", "2021-03-31"))
    eoms = pd.to_datetime(["2020-11-30", "2020-12-31", "2021-01-31"])
    panel = pd.DataFrame(
        {
            "permno": [1, 1, 1],
            "eom": eoms,
            "be_me": [0.5, 0.6, 0.7],
            "ret_exc_lead1m": [0.01, 0.02, 0.03],
            "ticker": ["ABC"] * 3,
        }
    )
    sources.stamped(panel, None, cal, clock.eom_session(panel["eom"], cal)).to_parquet(
        tmp_path / "panel.parquet"
    )
    days = pd.to_datetime(["2020-12-30", "2020-12-31", "2021-01-04"])
    dsf = pd.DataFrame({"permno": [1, 1, 1], "date": days, "prc": [10.0] * 3, "ret": [0.0] * 3})
    sources.stamped(dsf, None, cal, days).to_parquet(tmp_path / "dsf.parquet")
    return cal


# Blind mode drops every row public after 2020, whatever the purpose.
def test_blind_mode_drops_rows_after_the_seal(clean):
    for purpose in (None, "label", "gap_ratio"):
        rows = sources.read("dsf", ["ret"], purpose=purpose)
        assert pd.to_datetime(rows["date"]).max() == pd.Timestamp("2020-12-31")
    assert sources.read("dsf")["date"].max() < SEALED_DAY


# The Dec 2020 row is readable, but its January 2021 label is not.
def test_label_reaching_2021_drops_its_row_only_when_asked(clean):
    features = sources.read("panel", ["be_me"])
    assert features["eom"].max() == pd.Timestamp("2020-12-31")
    labelled = sources.read("panel", ["be_me", "ret_exc_lead1m"])
    assert labelled["eom"].max() == pd.Timestamp("2020-11-30")


# Restricted fields need their one purpose; banned ones never read.
def test_bans_and_restrictions_refuse_reads(clean):
    with pytest.raises(sources.BannedField):
        sources.read("dsf", ["prc"])
    assert "prc" in sources.read("dsf", ["prc"], purpose="gap_ratio").columns
    assert "prc" not in sources.read("dsf").columns
    with pytest.raises(sources.BannedField):
        sources.read("panel", ["ticker"])
    with pytest.raises(sources.BannedField):
        sources.read("short_interest", ["shortintadj"])
    with pytest.raises(sources.NotForBacktest):
        sources.read("key_developments", ["keydevid"])


# Sources the backtest may never touch are refused by name.
@pytest.mark.parametrize(
    "name",
    [
        "organisers_8k",
        "fiam_v1_wrds",
        "features_monthly_adjfct",
        "ibes",
        "carbon_arc",
        "short_interest_lending",
        "customer_links",
        "key_developments",
    ],
)
def test_never_sources_are_refused(clean, name):
    with pytest.raises(sources.NotForBacktest):
        sources.read(name)


# A planted one-month-ahead feature is caught by the join check.
def test_planted_future_feature_is_caught(clean):
    cal = clean
    eom = pd.Series(pd.to_datetime(["2020-11-30", "2020-12-31"]))
    formation = clock.formation(clock.eom_session(eom, cal), cal)
    honest = clock.eom_session(eom, cal)
    clock.assert_known_before(honest, formation, "honest")
    planted = clock.eom_session(eom + pd.offsets.MonthEnd(1), cal)
    with pytest.raises(AssertionError, match="not public before formation"):
        clock.assert_known_before(planted, formation, "planted")


# Shuffled folds and labels overlapping a fit are refused.
def test_no_shuffle_and_no_overlapping_labels():
    from sklearn.model_selection import KFold, TimeSeriesSplit

    guards.refuse_shuffle(TimeSeriesSplit(n_splits=3))
    with pytest.raises(ValueError, match="shuffles"):
        guards.refuse_shuffle(KFold(n_splits=3, shuffle=True))
    guards.assert_time_split(["2018-11-30", "2018-12-31"], "2019-01-31")
    with pytest.raises(AssertionError, match="training labels end"):
        guards.assert_time_split(["2018-12-31", "2019-01-31"], "2019-01-31")


# On a machine with the data, no banned field survives in a clean table.
@pytest.mark.skipif(not (sources.DATA / "v4" / "clean").exists(), reason="no data folder")
def test_real_clean_tables_hold_no_banned_field():
    import pyarrow.dataset as ds

    for name, source in sources.REGISTRY.items():
        path = (
            sources.DATA / "v4" / "clean" / (name if name in sources.FOLDERS else f"{name}.parquet")
        )
        if path.exists():
            assert not set(source.banned) & set(ds.dataset(path).schema.names), name


# Short interest is one exchange series that switches once.
def test_real_short_interest_is_one_exchange_series():
    path = sources.DATA / "v4" / "clean" / "short_interest.parquet"
    if not path.exists():
        pytest.skip("no clean short interest on this machine")
    s = pd.read_parquet(path, columns=["settlement", "source", "permno"])
    assert set(s["source"]) == {"wrds_legacy", "finra"}
    assert s.loc[s["source"] == "wrds_legacy", "settlement"].max() < sources.FINRA_FROM
    assert s.loc[s["source"] == "finra", "settlement"].min() >= sources.FINRA_FROM
    assert not s.duplicated(["permno", "settlement"]).any()


# Fields banned everywhere appear in no clean table.
def test_real_clean_tables_hold_no_globally_banned_field():
    import pyarrow.dataset as ds

    always = {"adjfct", "shortintadj", "splitadjdate", "dldte", "dlrsn"}
    always |= {"lastmodifieddate", "mostimportantdateutc", "speffectivedate"}
    for name in sources.REGISTRY:
        path = (
            sources.DATA / "v4" / "clean" / (name if name in sources.FOLDERS else f"{name}.parquet")
        )
        if path.exists():
            assert not always & set(ds.dataset(path).schema.names), name


# Blind reads of the links show no period ending after the seal.
def test_real_links_hide_ends_after_the_seal():
    path = sources.DATA / "v4" / "clean" / "links.parquet"
    if not path.exists():
        pytest.skip("no clean links on this machine")
    got = sources.read("links", ["valid_to"])
    assert not (pd.to_datetime(got["valid_to"]) > pd.Timestamp("2020-12-31 23:59:59")).any()


# Only declared labels carry next month's return, on 2019.
def test_real_panel_has_no_hidden_next_month_return():
    path = sources.DATA / "v4" / "clean" / "panel.parquet"
    if not path.exists():
        pytest.skip("no clean panel on this machine")
    p = pd.read_parquet(path, filters=[("eom", ">=", pd.Timestamp("2019-01-31"))])
    p = p[p["eom"] <= "2019-12-31"]
    label = p["ret_exc_lead1m"]
    labels = set(sources.REGISTRY["panel"].labels)
    numeric = p.select_dtypes("number").drop(columns=[*labels, "permno"], errors="ignore")
    numeric = numeric.loc[:, numeric.std() > 0]
    close = [c for c in numeric if abs(numeric[c].corr(label)) > 0.9]
    assert close == [], close


# Footprint weights: named states equal, the headquarters counted twice.
def test_footprint_weights():
    assert sources.footprint_weights("TX", "TX,OH") == {"TX": 2 / 3, "OH": 1 / 3}
    assert sources.footprint_weights(None, "CA,NY") == {"CA": 0.5, "NY": 0.5}
    assert sources.footprint_weights("IL", "") == {"IL": 1.0}
    assert sources.footprint_weights(None, "") == {}


# No row public after the seal comes back from any text or map table.
@pytest.mark.skipif(not (sources.DATA / "v4" / "clean" / "sections").exists(), reason="no data")
def test_real_step4_tables_hide_rows_after_the_seal():
    for name, cols, purpose in [
        ("events", ["item"], None),
        ("sections", ["form"], None),
        ("footprint", ["state"], "exhibit"),
        ("amazon_stores", ["reviews"], "exhibit"),
    ]:
        got = sources.read(name, columns=cols, purpose=purpose)
        assert (pd.to_datetime(got["available_at"], utc=True) <= sources.SEAL).all(), name


# Red flags: listed items only; never 5.02, 8-K/A, 2.02 or a deal's 3.01
def test_load_events_red_flag_rules(tmp_path):
    clean, text_dir = tmp_path / "v4" / "clean", tmp_path / "v4" / "text"
    clean.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    stamp = pd.Timestamp("2018-01-02 15:00", tz="UTC")
    pd.DataFrame(
        {
            "accession": ["a1", "a2", "a3", "a4", "a5", "a6", "a7"],
            "permno": [1, 2, 3, 4, 5, 6, 7],
            "form": ["8-K", "8-K", "8-K", "8-K/A", "8-K", "8-K", "8-K"],
            "items": ["2.06", "5.02", "5.02", "4.02", "2.06,2.02", "3.01", "2.01,3.01,1.03"],
            "filing_date": pd.Timestamp("2018-01-02"),
            "available_at": stamp,
            "first_close": pd.Timestamp("2018-01-02"),
        }
    ).to_parquet(clean / "edgar_filings.parquet")
    got = sources.load_events(tmp_path, None, {})
    flags = got.set_index(["accession", "item"])["red_flag"]
    # Only the SEC's item codes flag: a 5.02 departure never does.
    assert flags[("a1", "2.06")] and not flags[("a2", "5.02")]
    assert not flags[("a3", "5.02")] and not flags[("a4", "4.02")]
    assert not flags[("a5", "2.06")] and not flags[("a5", "2.02")]
    # A deficiency 3.01 flags; one beside a completed deal does not.
    assert flags[("a6", "3.01")] and not flags[("a7", "3.01")] and flags[("a7", "1.03")]


# Insider lines: a changed 4/A replaces, repeats, mismatches, late out.
def test_clean_insiders_rules():
    at = pd.Timestamp("2018-01-05 15:00", tz="UTC")
    day = pd.Timestamp("2018-01-03")
    base = {"owner_cik": 9, "permno": 1, "trans_date": day, "trans_code": "P", "price": 10.0}
    rows = [
        base | {"accession": "f1", "form": "4", "shares": 100.0, "acq_disp": "A"},
        base | {"accession": "f2", "form": "4", "shares": 100.0, "acq_disp": "A"},
        base | {"accession": "f3", "form": "4/A", "shares": 150.0, "acq_disp": "A"},
        base | {"accession": "f4", "form": "4", "shares": 5.0, "acq_disp": "D"},
        base | {"accession": "f5", "form": "4", "shares": 7.0, "acq_disp": "A", "price": 9.0},
    ]
    t = pd.DataFrame(rows)
    t["available_at"] = [at, at + pd.Timedelta(days=1), at + pd.Timedelta(days=2), at, at]
    t["filing_date"] = [day + pd.Timedelta(days=2)] * 4 + [day + pd.Timedelta(days=40)]
    log = {}
    got = sources.clean_insiders(t, log).set_index("accession")
    # f2 repeats f1; f3 changes the trade, so f1 holds until f3's time.
    assert "f2" not in got.index and got.loc["f1", "superseded_at"] == t.loc[2, "available_at"]
    assert pd.isna(got.loc["f3", "superseded_at"])
    # f4 is a purchase marked disposed; f5 came 37 days after its trade.
    assert "f4" not in got.index and "f5" not in got.index
    assert log["insider_repeats_in_later_filings_dropped"] == 1
    # Lines missing a price stay apart from other lines missing one.
    gaps = t.iloc[[0, 4]].assign(price=float("nan"), accession=["g1", "g2"])
    gaps = gaps.assign(filing_date=day + pd.Timedelta(days=2), acq_disp="A")
    assert len(sources.clean_insiders(gaps, {})) == 2
    # Two identical lines inside one filing are two trades: both stay.
    twin = pd.concat([t.iloc[[0]], t.iloc[[0]]], ignore_index=True)
    assert len(sources.clean_insiders(twin, {})) == 2


# The raw text tables hold 2021+ rows, so only their builders read them.
def test_raw_text_tables_are_read_only_by_their_builders():
    allowed = {"text.py", "sources.py", "hand_checks.py", "kit.py"}
    root = Path(sources.__file__).resolve().parents[2]
    for path in [*(root / "fiam").rglob("*.py"), *(root / "tools").rglob("*.py")]:
        if path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        assert '"text" / "annual"' not in source and "five02.parquet" not in source, path


# Only the registry, builders and count tools open data files.
def test_only_allowed_modules_open_data_files():
    allowed = {"sources.py", "links.py", "exits.py", "agreement.py", "fallbacks.py"}
    allowed |= {"hand_checks.py", "kit.py", "text.py", "vintage.py", "fema.py"}
    # The table builders read the extracts and CRSP's types to clean them.
    allowed |= {"compustat.py", "thirteen_f.py"}
    # The final run, the headline and the what-ifs read their own outputs.
    allowed |= {"final.py", "headline.py", "whatif.py"}
    root = Path(sources.__file__).resolve().parent
    opens = ("read_parquet", "read_csv", '"clean"', '"extracts"', "fiam_v1", "pq.read_table")
    for path in sorted(root.glob("*.py")):
        if path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        assert not any(word in source for word in opens), f"{path.name} reads data around read()"


# A source registered later must ban the fields banned for it already.
def test_registered_sources_keep_their_early_bans():
    for name, fields in sources.BANNED_LATER.items():
        if name in sources.REGISTRY:
            assert set(fields) <= set(sources.REGISTRY[name].banned), name


# SEC and Compustat tables: bans refuse reads, sealed labels never load.
def test_step6_bans_and_sealed_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CLEAN", tmp_path)
    for name, col, why in (("sec_facts", "frame", None), ("compustat_quarterly", "dldte", "twin")):
        with pytest.raises(sources.BannedField):
            sources.read(name, [col], purpose=why)
    for name in ("compustat_quarterly", "compustat_annual"):
        assert {"dldte", "dlrsn", "cik", "ipodate"} <= set(sources.REGISTRY[name].banned)
    cal = clock.calendar(clock.xnys_sessions("2020-11-01", "2021-02-26"))
    lab = pd.DataFrame(
        {
            "permno": [1, 2],
            "eom": pd.to_datetime(["2020-10-31", "2020-11-30"]),
            "horizon": [1, 1],
            "label": [0.1, 0.2],
            "available": pd.to_datetime(["2020-12-01", "2021-01-04"]),
        }
    )
    sources.stamped(lab, None, cal, market_day=lab["available"]).to_parquet(
        tmp_path / "labels.parquet"
    )
    got = sources.read("labels", ["label"], purpose="label")
    assert got["permno"].tolist() == [1]
    # Labels and restated Compustat refuse any other purpose.
    with pytest.raises(sources.NotForBacktest):
        sources.read("labels", ["label"])
    for name in ("compustat_quarterly", "compustat_annual"):
        with pytest.raises(sources.NotForBacktest):
            sources.read(name, ["datadate"], purpose="model")
    assert {"ajexq", "ajex"} <= set(sources.COMPUSTAT_BANNED)


# The SUE and 13F holdings stay sealed like every registered table.
def test_step6_sue_and_holdings_are_sealed(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CLEAN", tmp_path)
    cal = clock.calendar(clock.xnys_sessions("2020-11-01", "2021-02-26"))
    filed = pd.to_datetime(["2020-12-30", "2021-01-05"])
    sue = pd.DataFrame({"permno": [1, 1], "end": pd.to_datetime(["2020-09-30", "2020-12-31"]),
                        "sue": [1.0, 2.0], "filed": filed})  # fmt: skip
    sources.stamped(sue, clock.end_of_day(filed), cal).to_parquet(tmp_path / "sue.parquet")
    held = pd.DataFrame({"accession": ["a", "b"], "permno": [1, 1], "value_usd": [1.0, 2.0]})
    sources.stamped(held, clock.end_of_day(filed), cal).to_parquet(tmp_path / "sec_13f.parquet")
    assert sources.read("sue", ["sue"], purpose="label")["sue"].tolist() == [1.0]
    assert sources.read("sec_13f", ["value_usd"])["accession"].tolist() == ["a"]
