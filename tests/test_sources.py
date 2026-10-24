# The registry's bans, blind mode and leak traps (§1.2, §1.3, B14, B19).

import pandas as pd
import pytest

from fiam.v4 import clock, guards, sources

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
    ],
)
def test_never_sources_are_refused(clean, name):
    with pytest.raises(sources.NotForBacktest):
        sources.read(name)


# A planted one-month-ahead feature is caught by the join check (B19).
def test_planted_future_feature_is_caught(clean):
    cal = clean
    eom = pd.Series(pd.to_datetime(["2020-11-30", "2020-12-31"]))
    formation = clock.formation(clock.eom_session(eom, cal), cal)
    honest = clock.eom_session(eom, cal)
    clock.assert_known_before(honest, formation, "honest")
    planted = clock.eom_session(eom + pd.offsets.MonthEnd(1), cal)
    with pytest.raises(AssertionError, match="not public before formation"):
        clock.assert_known_before(planted, formation, "planted")


# Shuffled folds and labels overlapping a fit are refused (B14).
def test_no_shuffle_and_no_overlapping_labels():
    from sklearn.model_selection import KFold, TimeSeriesSplit

    guards.refuse_shuffle(TimeSeriesSplit(n_splits=3))
    with pytest.raises(ValueError, match="shuffles"):
        guards.refuse_shuffle(KFold(n_splits=3, shuffle=True))
    guards.assert_time_split(["2018-11-30", "2018-12-31"], "2019-01-31")
    with pytest.raises(AssertionError, match="B14"):
        guards.assert_time_split(["2018-12-31", "2019-01-31"], "2019-01-31")


# On a machine with the data, no banned field survives in a clean table.
@pytest.mark.skipif(not (sources.DATA / "v4" / "clean").exists(), reason="no data folder")
def test_real_clean_tables_hold_no_banned_field():
    import pyarrow.dataset as ds

    for name, source in sources.REGISTRY.items():
        path = sources.DATA / "v4" / "clean" / (name if name == "crsp_daily" else f"{name}.parquet")
        if path.exists():
            assert not set(source.banned) & set(ds.dataset(path).schema.names), name


# Short interest is one exchange series that switches once (A10).
def test_real_short_interest_is_one_exchange_series():
    path = sources.DATA / "v4" / "clean" / "short_interest.parquet"
    if not path.exists():
        pytest.skip("no clean short interest on this machine")
    s = pd.read_parquet(path, columns=["settlement", "source", "permno"])
    assert set(s["source"]) == {"wrds_legacy", "finra"}
    assert s.loc[s["source"] == "wrds_legacy", "settlement"].max() < sources.FINRA_FROM
    assert s.loc[s["source"] == "finra", "settlement"].min() >= sources.FINRA_FROM
    assert not s.duplicated(["permno", "settlement"]).any()


# Fields banned everywhere (§1.2) appear in no clean table (L4).
def test_real_clean_tables_hold_no_globally_banned_field():
    import pyarrow.dataset as ds

    always = {"adjfct", "shortintadj", "splitadjdate", "dldte", "dlrsn"}
    always |= {"lastmodifieddate", "mostimportantdateutc", "speffectivedate"}
    for name in sources.REGISTRY:
        path = sources.DATA / "v4" / "clean" / (name if name == "crsp_daily" else f"{name}.parquet")
        if path.exists():
            assert not always & set(ds.dataset(path).schema.names), name


# Blind reads of the link table show no period ending after the seal (M4).
def test_real_links_hide_ends_after_the_seal():
    path = sources.DATA / "v4" / "clean" / "links.parquet"
    if not path.exists():
        pytest.skip("no clean links on this machine")
    got = sources.read("links", ["valid_to"])
    assert not (pd.to_datetime(got["valid_to"]) > pd.Timestamp("2020-12-31 23:59:59")).any()


# Only declared labels carry next month's return (M4, B19), on 2019.
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
