# SEC 13F holdings: forms, lines, units and CUSIP matches.

import zipfile

import pandas as pd

from fiam.vfinal import thirteen_f


# One quarter's zip with two reports, a notice and five lines.
def quarter(path):
    sub = pd.DataFrame(
        {
            "ACCESSION_NUMBER": ["h1", "h2", "n1"],
            "FILING_DATE": ["14-FEB-2019", "15-FEB-2019", "14-FEB-2019"],
            "SUBMISSIONTYPE": ["13F-HR", "13F-HR/A", "13F-NT"],
            "CIK": ["10", "11", "12"],
            "PERIODOFREPORT": ["31-DEC-2018"] * 3,
        }
    )
    cover = pd.DataFrame(
        {
            "ACCESSION_NUMBER": ["h1", "h2", "n1"],
            "ISAMENDMENT": ["N", "Y", "N"],
            "AMENDMENTTYPE": ["", "NEW HOLDINGS", ""],
            "REPORTTYPE": ["13F HOLDINGS REPORT", "13F HOLDINGS REPORT", "13F NOTICE"],
        }
    )
    info = pd.DataFrame(
        {
            "ACCESSION_NUMBER": ["h1", "h1", "h1", "h1", "h2", "n1"],
            "CUSIP": ["111111111", "111111111", "222222222", "333333333", "111111111", "1"],
            "VALUE": [100.0, 50.0, 30.0, 999.0, 10.0, 1.0],
            "SSHPRNAMT": [1000.0, 500.0, 300.0, 9.0, 100.0, 1.0],
            "SSHPRNAMTTYPE": ["SH", "SH", "SH", "PRN", "SH", "SH"],
            "PUTCALL": ["", "", "Put", "", "", ""],
            "INVESTMENTDISCRETION": ["SOLE", "DFND", "SOLE", "SOLE", "SOLE", "SOLE"],
        }
    )
    with zipfile.ZipFile(path, "w") as zf:
        for name, frame in (("SUBMISSION.tsv", sub), ("COVERPAGE.tsv", cover),
                            ("INFOTABLE.tsv", info)):  # fmt: skip
            zf.writestr(name, frame.to_csv(sep="\t", index=False))


# Notices, options and principal lines out; lines summed per CUSIP.
def test_read_zip_keeps_holdings_lines_only(tmp_path):
    quarter(tmp_path / "2019q1_form13f.zip")
    log = {}
    reports, lines = thirteen_f.read_zip(tmp_path / "2019q1_form13f.zip", set(), log)
    assert set(reports["ACCESSION_NUMBER"]) == {"h1", "h2"}
    assert log["notices_and_other_forms_left_out"] == 1
    assert log["option_lines_dropped"] == 1 and log["principal_lines_dropped"] == 1
    h1 = lines[lines["ACCESSION_NUMBER"] == "h1"].set_index("CUSIP")
    assert h1.loc["111111111", "VALUE"] == 150.0 and "222222222" not in h1.index
    # Shared-discretion shares are kept apart from sole ones.
    assert h1.loc["111111111", "SOLE"] == 1000.0 and h1.loc["111111111", "SSHPRNAMT"] == 1500.0
    # A filing already read from another zip is skipped, never doubled.
    again, _ = thirteen_f.read_zip(tmp_path / "2019q1_form13f.zip", {"h1"}, {})
    assert set(again["ACCESSION_NUMBER"]) == {"h2"}


# Units by each filing's own median value per share, else the switch.
def test_unit_class_per_filing():
    r = pd.DataFrame(
        {
            "value_per_share": [0.05, 40.0, 1.0, 40.0, 0.05],
            "share_lines": [50, 50, 50, 2, 2],
            "filing_date": pd.to_datetime(["2019-02-01"] * 3 + ["2019-02-01", "2023-02-01"]),
        }
    )
    got = thirteen_f.unit_class(r).tolist()
    assert got == ["thousands", "dollars", "unclear", "thousands", "dollars"]


# Zips sort by filing time: old quarters, then the 3-month windows.
def test_zip_order(tmp_path):
    names = ["01dec2024-28feb2025_form13f.zip", "2023q4_form13f.zip", "2013q2_form13f.zip"]
    paths = sorted((tmp_path / n for n in names), key=thirteen_f.zip_order)
    assert [p.name for p in paths] == [names[2], names[1], names[0]]


# CUSIPs map by the CRSP CUSIP in force; only US common stock stays.
def test_match_keeps_common_stock_by_dated_cusip(tmp_path):
    (tmp_path / "v4" / "clean").mkdir(parents=True)
    pd.DataFrame(
        {
            "permno": [1, 2, 3],
            "kind": ["cusip"] * 3,
            "value": ["111111111", "111111111", "444444444"],
            "valid_from": pd.to_datetime(["2010-01-01", "2019-06-01", "2010-01-01"]),
            "valid_to": pd.to_datetime(["2019-05-31", None, None]),
            "source": "crsp_monthly",
            "score": None,
        }
    ).to_parquet(tmp_path / "v4" / "links.parquet")
    pd.DataFrame(
        {
            "permno": [1, 3],
            "date": pd.to_datetime(["2018-12-31", "2018-12-31"]),
            "sharetype": ["NS", "NS"],
            "securitytype": ["EQTY", "FUND"],
        }
    ).to_parquet(tmp_path / "v4" / "clean" / "crsp_monthly.parquet")
    li = pd.DataFrame(
        {
            "accession": ["h1", "h1", "h1"],
            "cusip": ["111111111", "444444444", "999999999"],
            "period": pd.to_datetime(["2018-12-31"] * 3),
            "value_usd": [1.0, 2.0, 3.0],
            "shares": [1.0, 1.0, 1.0],
            "shares_sole": [1.0, 0.0, 1.0],
        }
    )
    log = {}
    got = thirteen_f.match(li, tmp_path, log)
    # 2018's holder of the CUSIP, not 2019's; the fund is dropped.
    assert got["permno"].tolist() == [1] and log["matched_lines_not_common_dropped"] == 1
    # Two lines of one stock in one report sum, sole shares apart.
    twice = pd.concat([li.iloc[[0]], li.iloc[[0]].assign(shares=4.0, shares_sole=0.0)])
    both = thirteen_f.match(twice, tmp_path, {}).iloc[0]
    assert both["shares"] == 5.0 and both["shares_sole"] == 1.0 and both["value_usd"] == 2.0
