# Bundle on tiny synthetic files: label apart, builder misses no filing.

import importlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest


# A two-name bundle in a temporary folder, with data.py pointed at it.
@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("FIAM_DATA_DIR", str(tmp_path))
    data = importlib.reload(importlib.import_module("fiam.data"))
    keys = pd.DataFrame(dict(permno=[1, 2], eom=pd.to_datetime(["2015-01-31", "2026-08-31"])))
    keys.assign(prc=[10.0, 20.0]).to_parquet(data.FEATURES)
    keys.assign(next_month_excess_return=[0.01, None]).to_parquet(data.LABELS)
    keys.assign(document_id=["a", "b"]).to_parquet(data.FILINGS)
    data.MANIFEST.write_text(json.dumps(dict(organizer_characteristics=["prc"])))
    yield data
    monkeypatch.delenv("FIAM_DATA_DIR")
    importlib.reload(data)


# Features never hold next month's return; the panel joins it on keys.
def test_features_never_carry_the_label_and_panel_joins_it(bundle, monkeypatch):
    # The bundle reader with blind mode off, so every year reads.
    monkeypatch.delenv("FIAM_BLIND", raising=False)
    assert "ret_exc_lead1m" not in bundle.features(["prc"])
    panel = bundle.panel(["prc", "ret_exc_lead1m"])
    assert panel["ret_exc_lead1m"].tolist()[0] == pytest.approx(0.01)
    assert panel["ret_exc_lead1m"].isna().tolist() == [False, True]
    with pytest.raises(AssertionError):
        bundle.features(["ret_exc_lead1m"])


# A bundle whose features hold the label fails validation.
def test_validation_rejects_a_label_in_the_features(bundle):
    frame = pd.read_parquet(bundle.FEATURES).assign(ret_exc_lead1m=[0.01, 0.02])
    frame.to_parquet(bundle.FEATURES)
    with pytest.raises(AssertionError, match="label"):
        bundle.validate()


# Without the WRDS folder every WRDS read returns None.
def test_no_wrds_means_none(bundle):
    assert bundle.wrds("exits") is None and bundle.research("daily_market") is None


# A filing on 2 January 2015 counts, and item 12.02 is not item 2.02.
def test_builder_keeps_january_2015_and_matches_items_exactly(tmp_path):
    build = importlib.import_module("fiam.build_data")
    filings = pd.DataFrame(
        dict(
            document_id=["a", "b", "c"],
            permno=[1, 1, 2],
            gvkey="001",
            iid="01",
            cik="1",
            ticker="X",
            company_name="X INC",
            filing_date=pd.to_datetime(["2015-01-02", "2015-01-20", "2015-03-05"]),
            form_type="8-K",
            is_amendment=False,
            items=[["2.02", "9.01"], ["12.02"], None],
            word_count=[10, 20, 30],
            text=["A loss and a decline", "growth", ""],
            **{column: None for column in [*build.NAMES, *build.TICKERS]},
        )
    )
    filings.to_parquet(tmp_path / build.FILINGS)
    table, texts = build.filing_table(tmp_path)
    assert texts["excerpt"].tolist() == ["A loss and a decline", "growth", ""]
    assert table["item_202_earnings"].tolist() == [1, 0, 0]
    assert table["text_negative"].tolist() == [2, 0, 0]
    events = build.monthly_events(table).set_index(["permno", "eom"])
    january = events.loc[(1, pd.Timestamp("2015-01-31"))]
    assert january["filing_count"] == 2 and january["filing_days_before_eom"] == 11


# No filing in a month counts zero; days-before stays blank, not zero.
def test_months_without_a_filing_count_zero(tmp_path):
    build = importlib.import_module("fiam.build_data")
    features = pd.DataFrame(dict(permno=[1, 2], eom=pd.to_datetime(["2015-01-31"] * 2)))
    events = pd.DataFrame(
        dict(
            permno=[1],
            eom=pd.to_datetime(["2015-01-31"]),
            filing_count=[1],
            filing_days_before_eom=[3],
        )
    )
    joined = build.join_events(features, events).set_index("permno")
    assert joined.loc[2, "filing_count"] == 0
    assert pd.isna(joined.loc[2, "filing_days_before_eom"])


# A bundle zip unpacks; one with an entry escaping it writes nothing.
def test_import_refuses_a_zip_that_escapes_the_bundle(tmp_path):
    spec = importlib.util.spec_from_file_location("run", Path(__file__).parents[1] / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    good, bad = tmp_path / "good.zip", tmp_path / "bad.zip"
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr(f"{run.BUNDLE.name}/ok.txt", "ok")
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr(f"{run.BUNDLE.name}/ok.txt", "ok")
        zf.writestr("../escaped.txt", "no")
    target = tmp_path / "data"
    target.mkdir()
    run.unzip(good, target)
    assert (target / run.BUNDLE.name / "ok.txt").read_text() == "ok"
    with pytest.raises(SystemExit):
        run.unzip(bad, tmp_path / "other")
    assert not (tmp_path / "escaped.txt").exists() and not (tmp_path / "other").exists()


# Excerpt opens at the first item; names, tickers, CIK, dates masked.
def test_filing_excerpt_is_masked():
    build = importlib.import_module("fiam.build_data")
    row = dict(company_name="PFIZER INC", ticker="PFE", cik="0000078003", provider_ticker="PFE")
    text = (
        "COVER PAGE PFIZER INC 0000078003 Item 8.01 Other Events. On October 5, 2015, Pfizer Inc. "
        "(NYSE: PFE) completed its offers, as filed July 2014 and on 10/05/2015. CIK 78003."
    )
    out = build.excerpt(text, row)
    assert out.startswith("Item 8.01")
    for leak in ("Pfizer", "PFIZER", "PFE", "2015", "2014", "October", "July", "78003"):
        assert leak not in out, leak
    assert "Securities Act of 1933" == build.excerpt("Item 1.01 Securities Act of 1933", {})[10:]


# Under FIAM_BLIND=1 the bundle reader drops 2021+ rows and labels.
def test_blind_mode_seals_the_v1_reader(bundle, monkeypatch):
    monkeypatch.setenv("FIAM_BLIND", "1")
    keys = pd.DataFrame(
        dict(permno=[1, 1, 1], eom=pd.to_datetime(["2020-11-30", "2020-12-31", "2021-01-31"]))
    )
    keys.assign(prc=[10.0, 11.0, 12.0]).to_parquet(bundle.FEATURES)
    keys.assign(next_month_excess_return=[0.01, 0.02, 0.03]).to_parquet(bundle.LABELS)
    assert bundle.features(["prc"])["eom"].max() == pd.Timestamp("2020-12-31")
    labelled = bundle.panel(["prc", "ret_exc_lead1m"])
    assert labelled["eom"].tolist() == [pd.Timestamp("2020-11-30")]
    monkeypatch.delenv("FIAM_BLIND")
    assert len(bundle.panel(["prc", "ret_exc_lead1m"])) == 3
