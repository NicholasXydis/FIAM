# The source registry: clock, cleaning, bans and blind mode (PLAN §6.7).

import glob
import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4 import clock
from fiam.v4 import links as link_table
from fiam.v4 import text as filing_text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CLEAN = DATA / "v4" / "clean"
CARDS = DATA / "v4" / "cards"
EXTRACTS = DATA / "v4" / "extracts"
TEXT = DATA / "v4" / "text"
# Tables kept as a folder of parts, since one frame would be too big.
FOLDERS = {"crsp_daily", "sections"}
# Blind mode seals every row public after the end of 2020 (PLAN §1.3).
SEAL = pd.Timestamp("2020-12-31 23:59:59", tz=clock.EASTERN).tz_convert("UTC")
# CRSP's own days before 2014; the organisers' dsf days from 2014 on.
DSF_FROM = pd.Timestamp("2014-01-01")
# The SEC's 8-K item codes, never v1's labels (2.05 and 2.06 swapped).
ITEM_NAMES = {
    "1.01": "material agreement", "1.02": "agreement ended", "1.03": "bankruptcy",
    "1.04": "mine safety", "1.05": "cybersecurity incident", "2.01": "acquisition or sale done",
    "2.02": "results", "2.03": "new financial obligation", "2.04": "obligation accelerated",
    "2.05": "exit or disposal costs", "2.06": "material impairment", "3.01": "delisting notice",
    "3.02": "unregistered equity sale", "3.03": "holders' rights changed",
    "4.01": "auditor change", "4.02": "past financials unreliable", "5.01": "control change",
    "5.02": "director or officer change", "5.03": "charter, bylaws or fiscal year",
    "5.04": "plan trading suspended", "5.05": "code of ethics", "5.06": "shell status",
    "5.07": "shareholder vote", "5.08": "director nominations", "6.01": "ABS",
    "7.01": "Regulation FD", "8.01": "other events", "9.01": "exhibits",
}  # fmt: skip
# Red flags (§7.3): these items always; 5.02 only by the text rule.
RED_ITEMS = {"1.03", "2.06", "3.01", "4.01", "4.02"}
# Items beside which a 3.01 is mechanical (deal, control, reorganising).
MECHANICAL = {"2.01", "5.01", "3.03"}
# A Form 4 line filed this long after its trade is left out (M1).
INSIDER_LATE = pd.Timedelta(days=30)
# The insider data sets' kept columns; names and addresses never read.
INSIDER_FORMS = ("4", "4/A")
INSIDER_SUB = ["ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE", "ISSUERCIK"]
INSIDER_OWNER = ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"]
INSIDER_TRANS = [
    "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "SECURITY_TITLE", "TRANS_DATE", "TRANS_CODE",
    "EQUITY_SWAP_INVOLVED", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
    "SHRS_OWND_FOLWNG_TRANS", "DIRECT_INDIRECT_OWNERSHIP",
]  # fmt: skip
INSIDER_NAMES = {
    "ACCESSION_NUMBER": "accession", "NONDERIV_TRANS_SK": "trans_sk", "SECURITY_TITLE": "security",
    "TRANS_DATE": "trans_date", "TRANS_CODE": "trans_code", "EQUITY_SWAP_INVOLVED": "equity_swap",
    "TRANS_SHARES": "shares", "TRANS_PRICEPERSHARE": "price", "TRANS_ACQUIRED_DISP_CD": "acq_disp",
    "SHRS_OWND_FOLWNG_TRANS": "shares_after", "DIRECT_INDIRECT_OWNERSHIP": "direct",
    "FILING_DATE": "filing_date", "PERIOD_OF_REPORT": "period_of_report", "DOCUMENT_TYPE": "form",
    "ISSUERCIK": "issuer_cik", "RPTOWNERCIK": "owner_cik", "RPTOWNER_RELATIONSHIP": "relationship",
    "RPTOWNER_TITLE": "title",
}  # fmt: skip
# Form 4 titles that are common stock, and those that never are (L13).
COMMON_TITLE = r"(?i)common|ordinary|capital stock|class [a-z] shares"
NOT_COMMON = r"(?i)preferred|option|warrant|\bunits?\b|\bnotes?\b|debenture|\brights?\b"
# FINRA's files hold exchange-listed short interest from June 2021.
FINRA_FROM = pd.Timestamp("2021-06-01")


# A read that asks for a banned or restricted field.
class BannedField(Exception):
    pass


# A source that may not be read in the backtest at all.
class NotForBacktest(Exception):
    pass


# One registered source: where it is, its clock and what is banned.
@dataclass(frozen=True)
class Source:
    name: str
    raw: tuple[str, ...]
    key: tuple[str, ...]
    ids: str
    clock: str
    use: str = "backtest"
    banned: tuple[str, ...] = ()
    restricted: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    step: int = 3
    answers: dict = field(default_factory=dict)
    control: str = ""


# The PDF's four answers per source (p14-15), in plain words.
def four(start: str, lag: str, vintage: str, coverage: str) -> dict:
    return {"history_start": start, "lag": lag, "vintage": vintage, "coverage": coverage}


PANEL_IDS = ("permno", "gvkey", "iid", "eom", "id", "excntry", "exch_main", "common")
REGISTRY = {
    s.name: s
    for s in [
        Source(
            "panel",
            ("organisers/chars_final_with_names.parquet",),
            ("permno", "eom"),
            "permno",
            "eom",
            restricted={"ticker": {"label"}, "company_name": {"label"}},
            labels={"ret_exc_lead1m": 1},
            answers=four(
                "2015-01 (eom)",
                "known at eom, as the organisers define it; accounting release dates "
                "not verified by them (readme §5, §7)",
                "built from WRDS today, so restated Compustat values; SYY-10 inputs "
                "checked against SEC as-filed (§6.7)",
                "every common stock in their US universe; coverage independent of "
                "later exit (audit: 98.6% of CRSP common stock-months)",
            ),
        ),
        Source(
            "dsf",
            ("organisers/dsf_mini_from_2014.csv",),
            ("permno", "date"),
            "permno",
            "market",
            restricted={"prc": {"gap_ratio"}},
            answers=four(
                "2014-01-02",
                "that day's close",
                "price-only CRSP DlyRetx; prc split-adjusted to today (banned, B10)",
                "the panel's stocks; no delisting-return days (A13)",
            ),
        ),
        Source(
            "crsp_daily",
            ("v4/extracts/crsp_daily/*.parquet",),
            ("permno", "date"),
            "permno",
            "market",
            answers=four(
                "2000-01-03",
                "that day's close",
                "CRSP as of the 2025 annual update; the description in force each day",
                "all CRSP stocks; ends 2025-12",
            ),
        ),
        Source(
            "crsp_monthly",
            ("v4/extracts/crsp_monthly.parquet",),
            ("permno", "date"),
            "permno",
            "month_end",
            answers=four(
                "2000-01",
                "the month's last close",
                "as CRSP daily",
                "all CRSP stocks; ends 2025-12",
            ),
        ),
        Source(
            "crsp_delistings",
            ("v4/extracts/crsp_delistings.parquet",),
            ("permno",),
            "permno",
            "delisting",
            use="accounting",
            answers=four(
                "2000",
                "the delisting return is known after the next price (delnextdt)",
                "CRSP's own record",
                "every CRSP delisting; used only to true up stubs (§6.4)",
            ),
        ),
        Source(
            "crsp_distributions",
            ("v4/extracts/crsp_distributions.parquet",),
            ("permno", "disexdt", "disseqnbr"),
            "permno",
            "declared",
            use="accounting",
            answers=four(
                "2000",
                "the declaration date",
                "CRSP's own record",
                "every CRSP distribution; checks and split dates only",
            ),
        ),
        Source(
            "crsp_market_daily",
            ("v4/extracts/crsp_market_daily.parquet",),
            ("date",),
            "none",
            "market",
            answers=four(
                "2000-01-03",
                "that day's close",
                "CRSP index series",
                "the whole market; ends 2025-12",
            ),
        ),
        Source(
            "short_interest",
            (
                "v4/extracts/short_interest_legacy.parquet",
                "finra/short_interest.parquet",
                "v4/links.parquet",
            ),
            ("permno", "settlement"),
            "permno",
            "short_interest",
            banned=("shortintadj", "splitadjdate", "gvkey", "cik", "iid", "gvkey_iid"),
            answers=four(
                "2000-01 (exchange short interest only, A10)",
                "8 trading days after settlement",
                "exchange counts, never split-adjusted (M7); before 2021-06 WRDS holds "
                "today's corrected values (stated); a FINRA row corrected later takes the "
                "stock's last uncorrected value from up to 2 months before (1B)",
                "WRDS legacy file to 2021-05, FINRA's own files from 2021-06-15 (they "
                "agree on 99.96% of 2021-06..2024-12 pairs). Survivorship gap t 0.20; a "
                "missing report is neutral, the month's median, never a signal",
            ),
        ),
        Source(
            "edgar_filings",
            ("edgar/filings.parquet", "edgar/forms.parquet", "v4/links.parquet"),
            ("accession", "permno"),
            "permno",
            "edgar",
            # Today's EDGAR name on old rows tells how a firm ended (PDF p16).
            banned=("edgar_name",),
            answers=four(
                "2006-01 (forms) and 2012-01 (annual reports and 8-Ks)",
                "the acceptance second, read as the Eastern wall clock (A6)",
                "filings are never revised; amendments are new filings",
                "every panel firm with a CIK (6,256 of 6,561), dead firms included",
            ),
        ),
        Source(
            "events",
            ("v4/clean/edgar_filings.parquet",),
            ("accession", "permno", "item"),
            "permno",
            "edgar",
            answers=four(
                "2012-01 (8-Ks of every panel firm)",
                "the filing's acceptance second (A6)",
                "filings are never revised; items as the SEC codes them, 5.02 never a flag",
                "every panel firm with a CIK, dead firms included; red flags per §7.3",
            ),
            step=4,
            control=(
                "Coverage, any 8-K in the 12 months to t: 99.6% of trading months, 99.5% of "
                "leavers; same-month gap t -0.12, next-month t 0.04. A stock with no CIK link "
                "that month is left out of the red-flag gate, never given a 0."
            ),
        ),
        Source(
            "sections",
            ("v4/text/annual/part-*.parquet", "v4/clean/edgar_filings.parquet"),
            ("accession", "permno"),
            "permno",
            "edgar",
            step=4,
            answers=four(
                "2012-01 (annual reports of every panel firm)",
                "the filing's acceptance second (A6)",
                "filings are never revised; text as filed, boilerplate stripped (K5)",
                "every held 10-K, 10-K405 and 10-KT; a section under 500 characters is missing",
            ),
            control=(
                "Uncovered months are mostly new listings before their first 10-K (median 4 "
                "months in the panel against 30) and firms with no CIK; 99.5% of leavers "
                "resolve; same-month gap t -2.17, next-month t 0.30. A stock without both "
                "sections is left out of the Lazy Prices gate that month, signal and "
                "residualisation alike; the gate is also reported on stocks listed 15 months."
            ),
        ),
        Source(
            "footprint",
            ("v4/text/annual/part-*.parquet", "v4/clean/edgar_filings.parquet"),
            ("accession", "permno", "state"),
            "permno",
            "edgar",
            use="exhibit",
            step=4,
            answers=four(
                "2012-01 (annual reports)",
                "the filing's acceptance second (A6)",
                "as filed; never today's address (Carbon Arc tags are current)",
                "every held annual report with a US headquarters or a named property state",
            ),
            control=(
                "The same causes as sections (new listings, no CIK); 99.2% of leavers resolve; "
                "same-month gap t -2.53, next-month t -0.08. Exhibits and live flags only, "
                "each reported on covered firms and labelled."
            ),
        ),
        Source(
            "sec_insiders",
            ("edgar/insiders/*_form345.zip", "edgar/forms.parquet", "v4/links.parquet"),
            # One filer can hold several listed classes: a line per stock.
            ("accession", "trans_sk", "permno"),
            "permno",
            "edgar",
            answers=four(
                "2006q1, SEC's Forms 3, 4 and 5 data sets (Forms 4 and 4/A kept)",
                "the filing's acceptance second (A6), else the end of its filing day; "
                "never the trade date (PDF p16)",
                "as filed; a 4/A that changes a trade replaces it from its own date "
                "(superseded_at); repeats, code mismatches and lines over 30 days late out",
                "every Form 4 on a panel firm, dead firms included, linked by dated CIK",
            ),
            control=(
                "Coverage, a Form 4 in the 12 months to t: 99.1% of trading months, 98.7% of "
                "leavers; same-month gap t -2.12, next-month t 0.56. Of the 1,221 uncovered "
                "trading months, 401 have no CIK (banks filing with bank regulators), 353 sit "
                "on 12 stocks with no Form 4 ever and 379 in a stock's first 12 months. The "
                "signal is 0 with no trade, so coverage never picks the gate's stocks; a stock "
                "with no CIK link that month is missing, never 0."
            ),
        ),
        Source(
            "amazon_stores",
            ("amazon/product_month/*.parquet", "amazon/items/*.parquet"),
            ("store", "month"),
            "store",
            "end_of_day",
            use="exhibit",
            step=4,
            answers=four(
                "2000 (UCSD Amazon Reviews 2023, to 2023-09)",
                "the end of the month the reviews were posted (review timestamps, UTC)",
                "current vintage (PDF p16): a 2023 release that lacks reviews removed before "
                "2023, with stores from 2023 metadata; descriptive only, no snapshot field kept",
                "stores of every category; a store reaches a firm only by the ontology rule",
            ),
        ),
        Source(
            "restatements",
            ("v4/extracts/restatements.parquet", "v4/links.parquet"),
            ("restatement_notification_key", "permno"),
            "permno",
            "file_date",
            # Restated amounts may be revised later; dates only (L7).
            banned=(
                "initial_cum_net_income_usd",
                "restated_cum_net_income_usd",
                "change_cum_net_income_usd",
                "initial_cum_tot_sto_equ_usd",
                "restated_cum_tot_sto_equ_usd",
                "change_cum_tot_sto_equ_usd",
                "res_adverse",
                "res_improves",
                # A later 4.02 8-K's date and key (final audit M3).
                "date_of_8k_402",
                "form_fkey_of_8k_402",
                # Fraud, investigation and auditor fields may be updated later.
                "res_accounting",
                "res_accounting_res_cat_fke_lis",
                "res_accounting_res_cat_tit_lis",
                "res_fraud",
                "res_fraud_res_cat_fke_lis",
                "res_fraud_res_cat_tit_lis",
                "res_clerical_errors",
                "res_clerical_err_res_cat_fke_lis",
                "res_clerical_err_res_cat_tit_lis",
                "res_other",
                "res_other_res_cat_fke_lis",
                "res_other_res_cat_tit_lis",
                "res_auditor_letter",
                "res_sec_investigation",
                "res_board_approval",
                "res_regulatory_investigation",
                "file_date_auditor_name",
                "res_begin_auditor_name",
                "res_end_auditor_name",
                "general_type",
            ),
            answers=four(
                "2000",
                "the end of the filing day",
                "event and file dates only",
                "Audit Analytics restatements of SEC filers",
            ),
        ),
        Source(
            "vix",
            ("v4/extracts/vix_daily.parquet",),
            ("date",),
            "none",
            "end_of_day",
            answers=four(
                "2000-01-03",
                "the end of that day, so the next close (its close is 4:15 pm)",
                "CBOE series",
                "the index",
            ),
        ),
        Source(
            "french",
            ("benchmarks/ff5_daily.zip", "benchmarks/ff_momentum_daily.zip"),
            ("date",),
            "none",
            "monthly_release",
            answers=four(
                "1963-07 (five factors), 1926 (momentum)",
                "the end of the next month (French posts each month weeks later)",
                "current vintage; checked against an archived pre-2021 copy (B23)",
                "the US market",
            ),
        ),
        Source(
            "tb3ms",
            ("benchmarks/TB3MS_full.csv",),
            ("month",),
            "none",
            "benchmark",
            use="benchmark",
            answers=four(
                "1934-01",
                "the end of the first business day after the month; benchmark only",
                "FRED series",
                "n/a",
            ),
        ),
        Source(
            "sp500",
            ("benchmarks/SP500.csv",),
            ("date",),
            "none",
            "market",
            use="benchmark",
            step=4,
            answers=four(
                "2016-09-26 (FRED); CRSP sprtrn before, through 2025 (PLAN §6.1)",
                "the day's close; used for 2026 only, the PDF's beta table",
                "FRED series, price index without dividends",
                "n/a",
            ),
        ),
        Source(
            "earnings_calendar",
            ("v4/extracts/compustat_quarterly.parquet", "v4/links.parquet"),
            ("permno", "gvkey", "fyearq", "fqtr"),
            "permno",
            "projected",
            answers=four(
                "2000 (Compustat rdq)",
                "a projection is public once the quarter it copies was announced",
                "rdq as Compustat holds it today; dates before period end dropped (A7)",
                "firms with any rdq; none for the 27% of rows without one (B22)",
            ),
        ),
        Source(
            "exits",
            (
                "v4/extracts/crsp_delistings.parquet",
                "edgar/forms.parquet",
                "v4/extracts/compustat_annual.parquet",
            ),
            ("permno", "exit_date"),
            "permno",
            "exit",
            use="accounting",
            answers=four(
                "2000 (CRSP) and 2026 (SEC forms)",
                "CRSP: once the delisting return is known; "
                "2026: the first exit form on or after the last row",
                "CRSP's record, its delisting return booked at the exit date by CRSP's "
                "convention even when liquidation pays later (L1); SEC filings never change",
                "every CRSP delisting; every stock whose daily rows stop in 2026, or on "
                "2025-12-31 with no CRSP exit (2B)",
            ),
        ),
        Source(
            "links",
            ("v4/links.parquet",),
            ("permno", "kind", "value", "valid_from"),
            "permno",
            "links",
            use="links",
            answers=four("1900 (CIK) to 2026", "dated periods", "built here", "§6.7"),
        ),
    ]
}
# Sources converted in the step that first reads them (§6.7).
LATER = {
    "compustat_quarterly": 6,
    "compustat_annual": 6,
    "wrds_ratios": 6,
    "ibes": 9,
    "taq_daily": 7,
    "options_daily": 7,
    "sec_13f": 6,
    "sec_facts": 6,
    "noaa": 6,
    "fema": 6,
    "ca0065s": 3,
    "amazon": 6,
    "carbon_arc": 9,
}
# Fields banned before their source is registered (final audit 1, 15).
BANNED_LATER = {"noaa": ("DAMAGE_PROPERTY", "DAMAGE_CROPS", "damage_property", "damage_crops")}
# Sources the backtest may never read (PLAN §1.2).
NEVER = {
    "organisers_8k": "survivor-biased (A1); its permno-CIK pairs feed the links only",
    "fiam_v1_wrds": "v1-v3 copies, not point in time; use data/v4/extracts",
    "features_monthly_adjfct": "encodes future splits (A4)",
    "ibes": "today's vintage, history rewritten (B27); the live desk only",
    "carbon_arc": "current vintage (B29); live only, CA0065S volume excepted (B30)",
    "short_interest_lending": "stock-lending demand, not exchange short interest (A10)",
    "customer_links": "customer names failed their check (83 of 100, bar 85); removed 2026-10-24",
    "key_developments": "universe-level survivorship gap t -3.32; removed 2026-10-24",
}


# A file's SHA-256, read in chunks.
def sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


# Every raw file behind a source, globs expanded, in a stable order.
def raw_files(source: Source, data: Path = DATA) -> list[Path]:
    found = []
    for pattern in source.raw:
        found += sorted(Path(p) for p in glob.glob(str(data / pattern)))
    return found


# The one trading calendar: CRSP days before 2014, dsf days from 2014.
def trading_calendar(data: Path = DATA) -> pd.Series:
    market = pd.read_parquet(
        data / "v4" / "extracts" / "crsp_market_daily.parquet", columns=["dlycaldt"]
    )
    early_days = pd.to_datetime(market["dlycaldt"])
    dsf = pd.read_csv(data / "organisers" / "dsf_mini_from_2014.csv", usecols=["date"])
    late_days = pd.to_datetime(dsf["date"].drop_duplicates().astype(str), format="%Y%m%d")
    days = pd.concat([early_days[early_days < DSF_FROM], late_days[late_days >= DSF_FROM]])
    return clock.calendar(days)


# Adds available_at and first_close, both from one public instant.
def stamped(frame: pd.DataFrame, public, cal: pd.Series, market_day=None) -> pd.DataFrame:
    out = frame.copy()
    if market_day is not None:
        out["first_close"] = clock.market_session(market_day, cal).to_numpy()
        closes = cal.reindex(pd.DatetimeIndex(out["first_close"]))
        out["available_at"] = pd.Series(closes.array, index=out.index)
    else:
        when = pd.Series(pd.Series(public).array, index=out.index)
        out["available_at"] = clock.utc(when).to_numpy()
        out["first_close"] = clock.first_close(when, cal).to_numpy()
    return out


# The organisers' panel: ids, the 147, labels and the named extras.
def load_panel(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    chars = pd.read_csv(data / "organisers" / "factor_char_list.csv")["variable"].tolist()
    extras = ["me", "prc", "dolvol_126d", "ami_126d", "gics", "sic", "ff49", "ret"]
    extras += ["ret_exc_lead1m", "ticker", "company_name", "ticker_name_source"]
    p = pd.read_parquet(data / "organisers" / "chars_final_with_names.parquet")
    keep = [c for c in dict.fromkeys(list(PANEL_IDS) + extras + chars) if c in p.columns]
    log["chars_missing"] = sorted(set(chars) - set(p.columns))
    p = p[keep].copy()
    p["permno"] = p["permno"].astype("int64")
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    session = clock.eom_session(p["eom"], cal)
    return stamped(p, None, cal, market_day=session)


# The organisers' daily file; prc kept only for the gap ratio (B10).
def load_dsf(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    d = pd.read_csv(data / "organisers" / "dsf_mini_from_2014.csv")
    d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d").astype("datetime64[ns]")
    d = d.rename(columns={"daily_return": "ret"})
    d["prc_inf"] = ~np.isfinite(d["prc"]) & d["prc"].notna()
    d.loc[d["prc_inf"], "prc"] = np.nan
    d["ret_null"] = d["ret"].isna()
    log["prc_inf"], log["ret_null"] = int(d["prc_inf"].sum()), int(d["ret_null"].sum())
    log["abs_ret_over_50pct"] = int((d["ret"].abs() > 0.5).sum())
    return stamped(d, None, cal, market_day=d["date"])


# CRSP daily, file by file, raw prices and caps in USD millions.
def load_crsp_daily(path: Path, cal: pd.Series) -> pd.DataFrame:
    cols = ["PERMNO", "DlyCalDt", "DlyRet", "DlyRetx", "DlyPrc", "DlyVol", "DlyBid", "DlyAsk"]
    cols += ["DlyClose", "DlyCap", "ShrOut", "DlyDelFlg", "DlyRetMissFlg", "PrimaryExch"]
    cols += ["ShareType", "SecurityType", "SICCD"]
    d = pd.read_parquet(path, columns=cols)
    d = d.rename(columns=lambda c: c.lower().removeprefix("dly"))
    d = d.rename(columns={"caldt": "date", "cap": "cap_musd", "shrout": "shrout_k"})
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    d["date"] = pd.to_datetime(d["date"]).astype("datetime64[ns]")
    d["cap_musd"] = d["cap_musd"] / 1000
    return stamped(d, None, cal, market_day=d["date"])


# CRSP monthly at its month's last close; caps in USD millions.
def load_crsp_monthly(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    cols = ["PERMNO", "MthCalDt", "MthRet", "MthRetx", "MthPrc", "MthCap", "MthVol"]
    cols += ["MthPrcVol", "ShrOut", "MthDelFlg", "SICCD", "NAICS", "PrimaryExch"]
    cols += ["ShareType", "SecurityType", "PERMCO"]
    m = pd.read_parquet(data / "v4" / "extracts" / "crsp_monthly.parquet", columns=cols)
    m = m.rename(columns=lambda c: c.lower().removeprefix("mth"))
    m = m.rename(columns={"caldt": "date", "cap": "cap_musd", "shrout": "shrout_k"})
    m["permno"] = pd.to_numeric(m["permno"]).astype("int64")
    m["date"] = pd.to_datetime(m["date"]).astype("datetime64[ns]")
    m["cap_musd"] = m["cap_musd"] / 1000
    return stamped(m, None, cal, market_day=clock.eom_session(m["date"], cal))


# CRSP delistings, public once their return is known (accounting).
def load_delistings(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    d = pd.read_parquet(data / "v4" / "extracts" / "crsp_delistings.parquet").drop(
        columns=["ticker"]
    )
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    for col in ("delistingdt", "delnextdt", "delamtdt", "deldlydt"):
        d[col] = pd.to_datetime(d[col], errors="coerce").astype("datetime64[ns]")
    known = d["delnextdt"].fillna(d["delistingdt"])
    return stamped(d, clock.end_of_day(known), cal)


# CRSP distributions, public at their declaration (checks only).
def load_distributions(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    d = pd.read_parquet(data / "v4" / "extracts" / "crsp_distributions.parquet").drop(
        columns=["ticker"]
    )
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    for col in ("disexdt", "disdeclaredt", "disrecorddt", "dispaydt"):
        d[col] = pd.to_datetime(d[col], errors="coerce").astype("datetime64[ns]")
    known = d["disdeclaredt"].fillna(d["disexdt"])
    log["declared_missing"] = int(d["disdeclaredt"].isna().sum())
    return stamped(d, clock.end_of_day(known), cal)


# CRSP's market series at each day's close.
def load_market(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    m = pd.read_parquet(data / "v4" / "extracts" / "crsp_market_daily.parquet").rename(
        columns={"dlycaldt": "date"}
    )
    m["date"] = pd.to_datetime(m["date"]).astype("datetime64[ns]")
    return stamped(m, None, cal, market_day=m["date"])


# Exchange short interest on PERMNO: WRDS legacy, then FINRA (A10).
def load_short_interest(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    s = pd.read_parquet(data / "v4" / "extracts" / "short_interest_legacy.parquet")
    s = s.drop(columns=["shortintadj", "splitadjdate"]).rename(columns={"datadate": "settlement"})
    s["settlement"] = pd.to_datetime(s["settlement"]).astype("datetime64[ns]")
    s = s[s["settlement"] < FINRA_FROM]
    s["gvkey_iid"] = s["gvkey"].astype(str) + ":" + s["iid"].astype(str)
    owner = link_table.permno_at(lk, "gvkey_iid", s["gvkey_iid"], s["settlement"])
    s["permno"] = owner.to_numpy()
    log["legacy_unlinked"] = int(s["permno"].isna().sum())
    s = s.dropna(subset=["permno"]).astype({"permno": "int64"})
    wrds = pd.to_datetime(s["available_date"], errors="coerce")
    ours = clock.short_interest_available(s["settlement"], cal)
    log["ours_later_than_wrds_days"] = int((ours.dt.tz_localize(None).dt.normalize() > wrds).sum())
    s = s.drop(columns=["available_date"]).assign(source="wrds_legacy")
    # FINRA from its first exchange-listed date; revised rows left out.
    f = pd.read_parquet(data / "finra" / "short_interest.parquet")
    f = f[f["settlement"] >= FINRA_FROM].copy()
    f["settlement"] = pd.to_datetime(f["settlement"]).astype("datetime64[ns]")
    f["permno"] = link_table.permno_by_symbol(lk, f["symbol"], f["settlement"]).to_numpy()
    log["finra_unmapped"] = int(f["permno"].isna().sum())
    f = f.dropna(subset=["permno"]).astype({"permno": "int64"})
    # Two symbols on one stock and date cannot be told apart: both out.
    twice = f.duplicated(["permno", "settlement"], keep=False)
    log["finra_shared_left_out"] = int(twice.sum())
    f = f[~twice].rename(columns={"short": "shortint"})
    f = f[["settlement", "permno", "symbol", "shortint", "revision"]].assign(source="finra")
    both = pd.concat([s.assign(revision=""), f], ignore_index=True)
    both = both.sort_values(["permno", "settlement"], ignore_index=True)
    # A corrected FINRA row takes the last clean value in 2 months (1B).
    fixed = both["revision"].eq("R")
    prior = both["shortint"].where(~fixed).groupby(both["permno"]).ffill()
    when = both["settlement"].where(~fixed).groupby(both["permno"]).ffill()
    near = (both["settlement"] - when) <= pd.Timedelta(days=62)
    both.loc[fixed & near, "shortint"] = prior[fixed & near]
    both["carried_from"] = when.where(fixed & near)
    log["finra_corrected_rows_given_earlier_value"] = int((fixed & near).sum())
    log["finra_corrected_rows_left_missing"] = int((fixed & ~near).sum())
    both = both[~fixed | near].drop(columns=["revision"])
    ours = clock.short_interest_available(both["settlement"], cal)
    # WRDS's header ids served the link only (final audit M3).
    both = both.drop(columns=["gvkey", "cik", "iid", "gvkey_iid"], errors="ignore")
    return stamped(both, ours, cal)


# Filings and forms on the acceptance clock, per filing and PERMNO.
def load_edgar(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    f = pd.concat(
        [
            pd.read_parquet(data / "edgar" / "filings.parquet").assign(kind="filing"),
            pd.read_parquet(data / "edgar" / "forms.parquet"),
        ],
        ignore_index=True,
    ).drop_duplicates(["cik", "accession"])
    # Forms 4 tag owner companies too, so insiders read sec_insiders (L3).
    log["insider_forms_left_out"] = int(f["form"].isin(INSIDER_FORMS).sum())
    f = f[~f["form"].isin(INSIDER_FORMS)].copy()
    f["filing_date"] = pd.to_datetime(f["filing_date"]).astype("datetime64[ns]")
    # The download flag is not the red-flag rule, so it is named apart.
    f = f.drop(columns=["edgar_name"], errors="ignore").rename(
        columns={"red_flag": "downloaded_for_text"}
    )
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    # Each filer's copy of a joint filing meets its own stock, once.
    f = by_cik(f, lk, "filing_date", log).drop_duplicates(["accession", "permno"])
    public = clock.edgar_available(f["accepted"], f["filing_date"])
    return stamped(f, public, cal)


# 8-K events, one row per item and stock, on the filing's clock (§6.3).
def load_events(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    cols = ["accession", "permno", "form", "items", "filing_date", "available_at", "first_close"]
    f = pd.read_parquet(data / "v4" / "clean" / "edgar_filings.parquet", columns=cols)
    # An 8-K/A is kept apart and never counts again (protocol.md).
    f = f[f["form"].isin(["8-K", "8-K/A"]) & f["items"].notna()]
    rows = f.assign(item=f["items"].str.split(",")).explode("item").drop(columns=["items"])
    rows["item"] = rows["item"].str.strip()
    rows["amendment"] = rows["form"] == "8-K/A"
    # Only the SEC's own item codes flag, never 5.02 (leader 2026-10-24).
    red = rows["item"].isin(RED_ITEMS)
    # A 3.01 beside 2.01, 5.01 or 3.03 is mechanical, never a flag (M5).
    deal = rows["accession"].isin(rows.loc[rows["item"].isin(MECHANICAL), "accession"])
    mechanical = red & (rows["item"] == "3.01") & deal
    log["red_flag_rows_dropped_as_mechanical_301"] = int(mechanical.sum())
    red &= ~mechanical
    earnings = rows["accession"].isin(rows.loc[rows["item"] == "2.02", "accession"])
    rows["earnings_8k"] = earnings
    rows["red_flag"] = red & ~rows["amendment"] & ~earnings
    log["red_flag_rows_dropped_as_earnings_8k"] = int((red & ~rows["amendment"] & earnings).sum())
    rows["item_name"] = rows["item"].map(ITEM_NAMES)
    log["items_by_code"] = rows["item"].value_counts().head(30).to_dict()
    log["red_flag_rows"] = int(rows["red_flag"].sum())
    log["unknown_item_codes"] = int(rows["item_name"].isna().sum())
    return rows.drop_duplicates(["accession", "permno", "item"])


# Each annual-report text part joined to its stock and clock (§6.3).
def annual_parts(data: Path, columns: list[str]):
    keys = ["accession", "permno", "form", "filing_date", "available_at", "first_close"]
    f = pd.read_parquet(data / "v4" / "clean" / "edgar_filings.parquet", columns=keys)
    f = f[f["form"].isin(filing_text.ANNUAL)]
    for path in sorted((data / "v4" / "text" / "annual").glob("part-*.parquet")):
        part = pd.read_parquet(path, columns=["accession", "cik", *columns])
        yield part.merge(f, on="accession", how="inner")


# One report's state weights: named states equal, headquarters twice.
def footprint_weights(hq: str | None, named: str) -> dict[str, float]:
    states = list(dict.fromkeys(([hq] if hq else []) + [s for s in named.split(",") if s]))
    total = len(states) + (1 if hq else 0)
    return {s: (2 if s == hq else 1) / total for s in states}


# Footprint weights per report: named states equal, headquarters twice.
def load_footprint(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    a = pd.concat(annual_parts(data, ["hq_state", "hq_zip", "property_states"]), ignore_index=True)
    rows = []
    for r in a.itertuples():
        hq = r.hq_state if isinstance(r.hq_state, str) else None
        for s, weight in footprint_weights(hq, str(r.property_states or "")).items():
            rows.append((r.accession, r.permno, s, weight, hq, r.hq_zip, r.form, r.filing_date))
    cols = ["accession", "permno", "state", "weight", "hq_state", "hq_zip", "form", "filing_date"]
    out = pd.DataFrame(rows, columns=cols)
    clocks = a[["accession", "permno", "available_at", "first_close"]].drop_duplicates()
    out = out.merge(clocks, on=["accession", "permno"])
    log["reports"] = int(a[["accession", "permno"]].drop_duplicates().shape[0])
    log["reports_with_hq"] = int(a["hq_state"].notna().sum())
    log["reports_without_state"] = int(
        log["reports"] - out[["accession", "permno"]].drop_duplicates().shape[0]
    )
    return out


# Amazon store-month review counts and ratings, counted at month end.
def load_amazon_stores(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    sums = ["reviews", "rating_sum", "rating_sq"]
    frames = []
    for path in sorted((data / "amazon" / "product_month").glob("*.parquet")):
        items = pd.read_parquet(
            data / "amazon" / "items" / path.name, columns=["parent_asin", "store"]
        )
        m = pd.read_parquet(path, columns=["parent_asin", "month", *sums]).merge(
            items.drop_duplicates("parent_asin"), on="parent_asin"
        )
        m = m[m["store"].fillna("").str.strip() != ""]
        frames.append(m.groupby(["store", "month"], as_index=False)[sums].sum())
    f = pd.concat(frames).groupby(["store", "month"], as_index=False)[sums].sum()
    f["mean_rating"] = f["rating_sum"] / f["reviews"]
    log["stores"] = int(f["store"].nunique())
    log["categories"] = len(frames)
    ends = pd.to_datetime(f["month"]) + pd.offsets.MonthEnd(0)
    return stamped(f, clock.end_of_day(ends), cal)


# SEC Forms 4 and 4/A: open-market lines, timed by acceptance (§6.3).
def load_sec_insiders(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    forms = pd.read_parquet(
        data / "edgar" / "forms.parquet", columns=["accession", "form", "accepted"]
    )
    forms = forms[forms["form"].isin(INSIDER_FORMS)].drop_duplicates("accession")
    accepted = forms.set_index("accession")["accepted"]
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    ours = set(
        pd.to_numeric(lk.loc[lk["kind"] == "cik", "value"], errors="coerce")
        .dropna()
        .astype("int64")
    )
    parts, seen = [], {"form4_filings_all_issuers": 0, "lines_on_panel_firms": 0}
    for path in sorted((data / "edgar" / "insiders").glob("*_form345.zip")):
        with zipfile.ZipFile(path) as zf:
            sub = pd.read_csv(zf.open("SUBMISSION.tsv"), sep="\t", dtype=str, usecols=INSIDER_SUB)
            sub = sub[sub["DOCUMENT_TYPE"].isin(INSIDER_FORMS)]
            seen["form4_filings_all_issuers"] += len(sub)
            sub = sub[pd.to_numeric(sub["ISSUERCIK"], errors="coerce").isin(ours)]
            owners = pd.read_csv(
                zf.open("REPORTINGOWNER.tsv"), sep="\t", dtype=str, usecols=INSIDER_OWNER
            )
            trans = pd.read_csv(
                zf.open("NONDERIV_TRANS.tsv"), sep="\t", dtype=str, usecols=INSIDER_TRANS
            )
        trans = trans[trans["ACCESSION_NUMBER"].isin(sub["ACCESSION_NUMBER"])]
        seen["lines_on_panel_firms"] += len(trans)
        # Joint filings: the first officer or director stands for the line.
        owners = owners[owners["ACCESSION_NUMBER"].isin(sub["ACCESSION_NUMBER"])].copy()
        role = (
            owners["RPTOWNER_RELATIONSHIP"].fillna("").str.contains("Director|Officer", case=False)
        )
        owners = owners.assign(insider_role=role, order=range(len(owners)))
        first = owners.sort_values(
            ["ACCESSION_NUMBER", "insider_role", "order"], ascending=[True, False, True]
        ).drop_duplicates("ACCESSION_NUMBER")
        per = owners.groupby("ACCESSION_NUMBER")
        first = first.assign(
            n_owners=first["ACCESSION_NUMBER"].map(per.size()),
            any_officer_or_director=first["ACCESSION_NUMBER"].map(per["insider_role"].any()),
        ).drop(columns=["insider_role", "order"])
        parts.append(
            trans.merge(sub, on="ACCESSION_NUMBER").merge(first, on="ACCESSION_NUMBER", how="left")
        )
    t = pd.concat(parts, ignore_index=True).rename(columns=INSIDER_NAMES)
    log |= seen
    before = len(t)
    t = t.drop_duplicates(["accession", "trans_sk"])
    log["repeated_lines_dropped"] = before - len(t)
    # Typed dates outside 1990-2030 (a year "0008") are missing, counted.
    for col in ("filing_date", "trans_date", "period_of_report"):
        when = pd.to_datetime(t[col], format="%d-%b-%Y", errors="coerce")
        bad = when.notna() & ~when.dt.year.between(1990, 2030)
        log[f"{col}_out_of_range"] = int(bad.sum())
        t[col] = when.where(~bad).astype("datetime64[ns]")
    for col in ("shares", "price", "shares_after"):
        t[col] = pd.to_numeric(t[col], errors="coerce")
    # Common stock by its title, never a preferred share or a derivative.
    title = t["security"].fillna("")
    t["common_stock"] = title.str.contains(COMMON_TITLE) & ~title.str.contains(NOT_COMMON)
    t["cik"] = pd.to_numeric(t["issuer_cik"], errors="coerce").astype("int64")
    t = by_cik(t.drop(columns=["issuer_cik"]), lk, "filing_date", log)
    stamp_at = t["accession"].map(accepted)
    log["with_acceptance_time"] = round(float(stamp_at.notna().mean()), 4)
    t = stamped(t, clock.insider_available(stamp_at, t["filing_date"]), cal)
    return clean_insiders(t, log)


# Amendments, repeats, code mismatches and late lines (final audit M1).
def clean_insiders(t: pd.DataFrame, log: dict) -> pd.DataFrame:
    group = ["owner_cik", "permno", "trans_date", "trans_code"]
    sig = [*group, "shares", "price"]
    t = t.reset_index(drop=True)
    # A trade's signature as text, so missing values compare as equal.
    t["_sig"] = t[sig[0]].astype("string").fillna("NA")
    for col in sig[1:]:
        t["_sig"] = t["_sig"] + "|" + t[col].astype("string").fillna("NA")
    # A 4/A changing a trade replaces the earlier lines from its own time.
    dated = t["trans_date"].notna()
    amend = t.loc[(t["form"] == "4/A") & dated, [*group, "accession", "available_at"]]
    amend = amend.drop_duplicates([*group, "accession"])
    pairs = (
        t.loc[dated, [*group, "accession", "available_at"]]
        .reset_index()
        .merge(amend, on=group, suffixes=("", "_b"))
    )
    pairs = pairs[
        (pairs["accession_b"] != pairs["accession"])
        & (pairs["available_at_b"] > pairs["available_at"])
    ]
    a4 = t[t["form"] == "4/A"]
    in_b = set(zip(a4["accession"], a4["_sig"]))
    same = [k in in_b for k in zip(pairs["accession_b"], t.loc[pairs["index"], "_sig"])]
    pairs = pairs[~pd.Series(same, index=pairs.index, dtype=bool)]
    t["superseded_at"] = pairs.groupby("index")["available_at_b"].min().reindex(t.index)
    log["insider_lines_superseded_by_4a"] = int(t["superseded_at"].notna().sum())
    # A trade a later filing repeats keeps the first filing's lines only.
    t = t.sort_values("available_at")
    first = t.drop_duplicates("_sig").set_index("_sig")["accession"]
    again = t["accession"] != t["_sig"].map(first)
    log["insider_repeats_in_later_filings_dropped"] = int(again.sum())
    t = t[~again].drop(columns="_sig")
    # A purchase marked disposed, or a sale marked acquired, is dropped.
    bad = ((t["trans_code"] == "P") & (t["acq_disp"] == "D")) | (
        (t["trans_code"] == "S") & (t["acq_disp"] == "A")
    )
    log["insider_code_direction_mismatch_dropped"] = int(bad.sum())
    t = t[~bad]
    # A line filed over 30 days after its trade would read old news as new.
    late = (t["filing_date"] - t["trans_date"]) > INSIDER_LATE
    log["insider_late_lines_dropped"] = int(late.sum())
    return t[~late].sort_values(["permno", "available_at"]).reset_index(drop=True)


# Rows keyed by SEC id spread to every PERMNO that id held on the date.
def by_cik(frame: pd.DataFrame, lk: pd.DataFrame, date: str, log: dict) -> pd.DataFrame:
    ids = lk.loc[lk["kind"] == "cik", ["permno", "value", "valid_from", "valid_to"]]
    ids = link_table.nanos(ids).rename(columns={"value": "cik_key"})
    frame = frame.assign(cik_key=frame["cik"].astype("int64").astype(str), row=range(len(frame)))
    both = frame.merge(ids, on="cik_key", how="left")
    live = both["permno"].notna() & (both[date] >= both["valid_from"])
    live &= both["valid_to"].isna() | (both[date] <= both["valid_to"])
    out = both[live].drop(columns=["cik_key", "valid_from", "valid_to"])
    log["rows_without_permno"] = int(len(frame) - out["row"].nunique())
    return out.drop(columns=["row"]).astype({"permno": "int64"})


# Restatements from the end of their filing day, on PERMNO by SEC id.
def load_restatements(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    r = pd.read_parquet(data / "v4" / "extracts" / "restatements.parquet")
    banned = set(REGISTRY["restatements"].banned)
    keep = [c for c in r.columns if not c.startswith(("http_", "ftp_")) and c != "disclosure_text"]
    r = r[[c for c in keep if c not in banned]].copy()
    r["file_date"] = pd.to_datetime(r["file_date"], errors="coerce").astype("datetime64[ns]")
    r["cik"] = pd.to_numeric(r["company_fkey"], errors="coerce")
    r = r.dropna(subset=["cik", "file_date"])
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    r = by_cik(r, lk, "file_date", log)
    return stamped(r, clock.end_of_day(r["file_date"]), cal)


# VIX and its siblings at each close; two copied dates dropped (A16).
def load_vix(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    v = pd.read_parquet(data / "v4" / "extracts" / "vix_daily.parquet")
    v["date"] = pd.to_datetime(v["date"]).astype("datetime64[ns]")
    before = len(v)
    v = v.drop_duplicates("date", keep="first")
    log["duplicate_dates_dropped"] = before - len(v)
    # VIX settles at 4:15 pm, after the stock close, so the next close.
    return stamped(v, clock.end_of_day(v["date"]), cal)


# French's daily factors, percent to decimals, at each day's close.
def load_french(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    five = french_csv(data / "benchmarks" / "ff5_daily.zip")
    mom = french_csv(data / "benchmarks" / "ff_momentum_daily.zip")
    f = five.join(mom, how="outer").reset_index()
    f.columns = [c.strip().lower().replace("-", "") for c in f.columns]
    f = f.rename(columns={"mom": "umd"})
    log["from"], log["to"] = str(f["date"].min().date()), str(f["date"].max().date())
    # French posts each month's days weeks later: public at next month end.
    release = f["date"] + pd.offsets.MonthEnd(0) + pd.offsets.MonthEnd(1)
    log["days_before_the_calendar"] = int((f["date"] < cal.index[0]).sum())
    return stamped(f, clock.end_of_day(release), cal)


# One French CSV's daily table, percent turned to decimals.
def french_csv(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(","))
    body = []
    for line in lines[start:]:
        if line.strip() == "" and body:
            break
        body.append(line)
    t = pd.read_csv(io.StringIO("\n".join(body)))
    t = t.rename(columns={t.columns[0]: "date"})
    t["date"] = pd.to_datetime(t["date"].astype(str).str.strip(), format="%Y%m%d")
    t = t.set_index("date").astype(float) / 100
    return t


# FRED TB3MS by month; a benchmark, never a predictor.
def load_tb3ms(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    t = pd.read_csv(data / "benchmarks" / "TB3MS_full.csv")
    t = t.rename(columns={"observation_date": "month", "TB3MS": "tb3ms"})
    t["month"] = pd.to_datetime(t["month"]).astype("datetime64[ns]")
    t["tb3ms"] = pd.to_numeric(t["tb3ms"], errors="coerce") / 100
    # FRED posts a month's average the next business day.
    end = t["month"] + pd.offsets.MonthEnd(0) + pd.offsets.BDay(1)
    return stamped(t, clock.end_of_day(end), cal)


# FRED's S&P 500 level and daily return, each at its own close (M5).
def load_sp500(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    s = pd.read_csv(data / "benchmarks" / "SP500.csv")
    s = s.rename(columns={"observation_date": "date", "SP500": "sp500"})
    s["date"] = pd.to_datetime(s["date"]).astype("datetime64[ns]")
    s["sp500"] = pd.to_numeric(s["sp500"], errors="coerce")
    s = s.dropna().sort_values("date", ignore_index=True)
    s["ret"] = s["sp500"].pct_change()
    log["days"] = len(s)
    return stamped(s, None, cal, market_day=s["date"])


# Projected earnings dates per quarter, on PERMNO by gvkey (B22).
def load_earnings_calendar(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    cols = ["gvkey", "datadate", "fyearq", "fqtr", "rdq"]
    q = pd.read_parquet(data / "v4" / "extracts" / "compustat_quarterly.parquet", columns=cols)
    q["datadate"] = pd.to_datetime(q["datadate"])
    q["rdq"] = pd.to_datetime(q["rdq"], errors="coerce")
    early = q["rdq"] < q["datadate"]
    log["rdq_before_period_end_dropped"] = int(early.sum())
    q.loc[early, "rdq"] = pd.NaT
    q = q.dropna(subset=["fyearq", "fqtr"]).sort_values(["rdq", "datadate"], na_position="last")
    before = len(q)
    q = q.drop_duplicates(["gvkey", "fyearq", "fqtr"], keep="first")
    log["repeated_quarters_kept_earliest"] = before - len(q)
    projected = clock.project_earnings(q, key="gvkey", ahead=4)
    log["basis"] = projected["basis"].value_counts().to_dict()
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    gv = link_table.nanos(
        lk.loc[lk["kind"] == "gvkey", ["permno", "value", "valid_from", "valid_to"]]
    )
    both = projected.merge(gv.rename(columns={"value": "gvkey"}), on="gvkey")
    # The link on the day the projection is made, never the projected day.
    when = both["known_from"].astype("datetime64[ns]")
    live = (when >= both["valid_from"]) & (both["valid_to"].isna() | (when <= both["valid_to"]))
    both = both[live & both["projected"].notna()].drop(columns=["valid_from", "valid_to"])
    # The real release date is known only once it happens (H2): cut.
    both = both.drop(columns=["rdq"])
    both = both.drop_duplicates(["permno", "gvkey", "fyearq", "fqtr"]).astype({"permno": "int64"})
    log["permno_quarters"] = len(both)
    return stamped(both, clock.end_of_day(both["known_from"]), cal)


# The dated exits table, CRSP to 2025 and SEC-dated in 2026 (§6.4).
def load_exits(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    from fiam.v4 import exits

    table, report = exits.build(data)
    log.update(report)
    # An exit is public no earlier than its own exit date (final audit 7).
    exit_day = pd.to_datetime(table["exit_date"])
    known = pd.to_datetime(table["known"]).fillna(exit_day)
    known = known.where(known >= exit_day, exit_day)
    return stamped(table, clock.end_of_day(known), cal)


# The link table as registered; its periods are its clock.
def load_links(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    lk = pd.read_parquet(data / "v4" / "links.parquet")
    start = clock.end_of_day(lk["valid_from"].clip(lower=pd.Timestamp("1900-01-01")))
    return lk.assign(available_at=start.dt.tz_convert("UTC").to_numpy(), first_close=pd.NaT)


LOADERS = {
    "panel": load_panel,
    "dsf": load_dsf,
    "crsp_monthly": load_crsp_monthly,
    "crsp_delistings": load_delistings,
    "crsp_distributions": load_distributions,
    "crsp_market_daily": load_market,
    "short_interest": load_short_interest,
    "edgar_filings": load_edgar,
    "sec_insiders": load_sec_insiders,
    "events": load_events,
    "footprint": load_footprint,
    "amazon_stores": load_amazon_stores,
    "sp500": load_sp500,
    "restatements": load_restatements,
    "vix": load_vix,
    "french": load_french,
    "tb3ms": load_tb3ms,
    "earnings_calendar": load_earnings_calendar,
    "exits": load_exits,
    "links": load_links,
}


# Rows per year by first close or availability: counts only.
def by_year(frame: pd.DataFrame) -> dict:
    when = pd.to_datetime(frame["first_close"])
    stamp = pd.to_datetime(frame["available_at"], utc=True).dt.tz_localize(None)
    year = when.fillna(stamp).dt.year
    return {int(k): int(v) for k, v in year.value_counts().sort_index().items()}


# Fails unless every row is unique on its declared key.
def assert_unique(frame: pd.DataFrame, source: Source) -> int:
    dupes = int(frame.duplicated(list(source.key)).sum())
    if dupes:
        raise AssertionError(f"{source.name}: {dupes} rows repeat the key {source.key}")
    return dupes


# One source's card: raw hashes, counts, rules and its four answers.
def card(source: Source, files: list[Path], frame: pd.DataFrame, log: dict) -> dict:
    return {
        "source": source.name,
        "use": source.use,
        "raw": {str(p.relative_to(DATA)): sha256(p) for p in files},
        "rows_out": len(frame),
        "key": list(source.key),
        "ids": source.ids,
        "clock": source.clock,
        "banned_dropped": list(source.banned),
        "restricted": {k: sorted(v) for k, v in source.restricted.items()},
        "labels": source.labels,
        "rules": log,
        "rows_by_year": by_year(frame),
        "answers": source.answers,
        "survivorship_control": source.control,
    }


# Converts one source to data/v4/clean and writes its card.
def convert(name: str, data: Path = DATA, cal: pd.Series | None = None) -> dict:
    source = REGISTRY[name]
    cal = trading_calendar(data) if cal is None else cal
    files = raw_files(source, data)
    if not files:
        raise FileNotFoundError(f"{name}: no raw file under {source.raw}")
    log: dict = {}
    # The tables and cards go into the data tree read, never another one.
    clean, cards = data / "v4" / "clean", data / "v4" / "cards"
    clean.mkdir(parents=True, exist_ok=True)
    cards.mkdir(parents=True, exist_ok=True)
    if name == "crsp_daily":
        frames = []
        folder = clean / "crsp_daily"
        folder.mkdir(exist_ok=True)
        for n, path in enumerate(files):
            part = load_crsp_daily(path, cal)
            part.to_parquet(folder / f"part-{n:02d}.parquet", index=False)
            frames.append(part[["permno", "date", "first_close", "available_at"]])
        frame = pd.concat(frames, ignore_index=True)
    elif name == "sections":
        folder = clean / "sections"
        folder.mkdir(exist_ok=True)
        for old in folder.glob("part-*.parquet"):
            old.unlink()
        frames = []
        for n, part in enumerate(annual_parts(data, ["item1a", "item7"])):
            part.to_parquet(folder / f"part-{n:02d}.parquet", index=False, compression="zstd")
            found = part[["item1a", "item7"]].notna()
            frames.append(part[[*source.key, "first_close", "available_at"]].join(found))
        frame = pd.concat(frames, ignore_index=True)
        log["item1a_found"] = round(float(frame["item1a"].mean()), 4)
        log["item7_found"] = round(float(frame["item7"].mean()), 4)
    else:
        frame = LOADERS[name](data, cal, log)
        bad = [c for c in source.banned if c in frame.columns]
        if bad:
            raise AssertionError(f"{name}: banned columns survived {bad}")
        frame.to_parquet(clean / f"{name}.parquet", index=False)
    log["duplicate_keys"] = assert_unique(frame, source)
    log["rows_without_first_close"] = int(frame["first_close"].isna().sum())
    made = card(source, files, frame, log)
    (cards / f"{name}.json").write_text(json.dumps(made, indent=1, default=str))
    return made


# Blind mode lifts only by the hash-checked unseal (§13.3, step 10).
def unsealed() -> bool:
    return False


# Reads a clean table under blind mode, bans and limits (§1.2, §1.3).
def read(
    name: str, columns: list[str] | None = None, purpose: str | None = None, where=None
) -> pd.DataFrame:
    if name in NEVER:
        raise NotForBacktest(f"{name}: {NEVER[name]}")
    source = REGISTRY[name]
    # Exhibit-only sources never reach the backtest (approved 2026-10-23).
    if source.use == "exhibit" and purpose not in {"exhibit", "live"}:
        raise NotForBacktest(f"{name}: exhibits and live context only")
    asked = None if columns is None else set(columns)
    # A row filter is a use of its columns: the same bans apply.
    touched = (asked or set()) | set(where or {})
    for col in touched & set(source.banned):
        raise BannedField(f"{name}.{col} is banned (§1.2)")
    for col, allowed in source.restricted.items():
        if col in touched and purpose not in allowed:
            raise BannedField(f"{name}.{col} only for {sorted(allowed)} (§1.2)")
    path = CLEAN / name if name in FOLDERS else CLEAN / f"{name}.parquet"
    need = {"available_at", "first_close", "eom"} | set(source.key)
    if name in FOLDERS:
        frame = read_unsealed(path, None if asked is None else sorted(asked | need), where)
    elif asked is None and not where:
        frame = pd.read_parquet(path)
    else:
        frame = read_some(path, None if asked is None else sorted(asked | need), where)
    if asked is None:
        hidden = [c for c, ok in source.restricted.items() if purpose not in ok]
        frame = frame.drop(columns=[c for c in hidden if c in frame.columns])
    frame = sealed_out(frame, source, set(frame.columns) if asked is None else asked)
    if asked is None:
        return frame
    order = [*source.key, *columns, "first_close", "available_at"]
    return frame[[c for c in dict.fromkeys(order) if c in frame.columns]]


# A folder table's rows public by the seal, so sealed text never loads.
def read_unsealed(path: Path, want: list[str] | None, where=None) -> pd.DataFrame:
    import pyarrow as pa
    import pyarrow.dataset as ds

    table = ds.dataset(path)
    cols = None if want is None else [c for c in want if c in table.schema.names]
    seal = pa.scalar(SEAL.value, type=pa.timestamp("ns", tz="UTC"))
    expr = ds.field("available_at") <= seal
    rows = row_filter(table.schema, where)
    expr = expr if rows is None else expr & rows
    return table.to_table(columns=cols, filter=expr).to_pandas()


# Only the columns a table really has, so asking for eom never fails.
def read_some(path: Path, want: list[str] | None, where=None) -> pd.DataFrame:
    import pyarrow.dataset as ds

    table = ds.dataset(path)
    have = set(table.schema.names)
    cols = None if want is None else [c for c in want if c in have]
    return table.to_table(columns=cols, filter=row_filter(table.schema, where)).to_pandas()


# Rows kept by value: a set, or a closed (low, high) range, per column.
def row_filter(schema, where):
    import pyarrow as pa
    import pyarrow.dataset as ds

    if not where:
        return None
    expr = None
    for col, rule in where.items():
        kind = schema.field(col).type

        # A bound becomes a scalar of the column's own type before compare.
        def scalar(v):
            if pa.types.is_timestamp(kind):
                return pa.scalar(
                    pd.Timestamp(v).as_unit("ns").value, type=pa.timestamp("ns", tz=kind.tz)
                )
            return pa.scalar(v, type=kind)

        if isinstance(rule, tuple):
            low, high = rule
            parts = [ds.field(col) >= scalar(low)] if low is not None else []
            parts += [ds.field(col) <= scalar(high)] if high is not None else []
        else:
            parts = [ds.field(col).isin(pa.array(sorted(rule), type=kind))]
        for part in parts:
            expr = part if expr is None else expr & part
    return expr


# Drops every row public after the seal, and labels that reach past it.
def sealed_out(frame: pd.DataFrame, source: Source, asked: set) -> pd.DataFrame:
    public = pd.to_datetime(frame["available_at"], utc=True)
    keep = public <= SEAL
    for label, months in source.labels.items():
        if label in asked and "eom" in frame.columns:
            ends = pd.to_datetime(frame["eom"]) + pd.offsets.MonthEnd(months)
            keep &= ends <= SEAL.tz_convert(None)
    out = frame[keep.to_numpy()].copy()
    # A period ending after the seal reveals a later exit (M4): left open.
    if "valid_to" in out.columns:
        late = pd.to_datetime(out["valid_to"]) > SEAL.tz_convert(None)
        out.loc[late, "valid_to"] = pd.NaT
    return out


# Row counts per year of any registered table, sealed rows included.
def count(name: str) -> dict:
    path = CLEAN / name if name in FOLDERS else CLEAN / f"{name}.parquet"
    frame = pd.read_parquet(path, columns=["first_close", "available_at"])
    return by_year(frame)


# Converts the step 3 tables: uv run python -m fiam.v4.sources [names]
if __name__ == "__main__":
    names = sys.argv[1:] or ["crsp_daily", "sections", *LOADERS]
    calendar = trading_calendar()
    # A run of some tables updates their entries and keeps the rest.
    old = CARDS / "step3.json"
    report = json.loads(old.read_text()) if old.exists() else {}
    report["calendar"] = clock.cross_check(calendar.index)
    for name in names:
        made = convert(name, cal=calendar)
        report[name] = {"rows": made["rows_out"], "rules": made["rules"]}
        print(name, made["rows_out"], json.dumps(made["rules"], default=str), flush=True)
    (CARDS / "step3.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report["calendar"], default=str)[:2000])
