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

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CLEAN = DATA / "v4" / "clean"
CARDS = DATA / "v4" / "cards"
EXTRACTS = DATA / "v4" / "extracts"
# Blind mode seals every row public after the end of 2020 (PLAN §1.3).
SEAL = pd.Timestamp("2020-12-31 23:59:59", tz=clock.EASTERN).tz_convert("UTC")
# CRSP's own days before 2014; the organisers' dsf days from 2014 on.
DSF_FROM = pd.Timestamp("2014-01-01")
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
            ("v4/extracts/short_interest_legacy.parquet", "finra/short_interest.parquet"),
            ("permno", "settlement"),
            "permno",
            "short_interest",
            banned=("shortintadj", "splitadjdate"),
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
            ("edgar/filings.parquet", "edgar/forms.parquet"),
            ("accession", "permno"),
            "permno",
            "edgar",
            answers=four(
                "2006-01 (forms) and 2012-01 (annual reports and 8-Ks)",
                "the acceptance second, read as the Eastern wall clock (A6)",
                "filings are never revised; amendments are new filings",
                "every panel firm with a CIK (6,256 of 6,561), dead firms included",
            ),
        ),
        Source(
            "sec_insiders",
            ("edgar/insiders/*_form345.zip", "edgar/forms.parquet"),
            # One filer can hold several listed classes: a line per stock.
            ("accession", "trans_sk", "permno"),
            "permno",
            "edgar",
            answers=four(
                "2006q1, SEC's Forms 3, 4 and 5 data sets (Forms 4 and 4/A kept)",
                "the filing's acceptance second (A6), else the end of its filing day; "
                "never the trade date (PDF p16)",
                "as filed; a 4/A is its own row from its own date",
                "every Form 4 on a panel firm, dead firms included, linked by dated CIK",
            ),
        ),
        Source(
            "key_developments",
            ("v4/extracts/events.parquet",),
            ("keydevid", "permno"),
            "permno",
            "entered",
            use="exhibit",
            banned=("ticker", "ticker_startdate", "ticker_enddate", "speffectivedate", "sptodate"),
            answers=four(
                "2004 (entered dates; earlier rows entered years late, A9)",
                "the instant the event was entered (entereddateutc)",
                "entries stay; revision stamps banned",
                "our gvkeys; results announcements only, no advance dates",
            ),
        ),
        Source(
            "restatements",
            ("v4/extracts/restatements.parquet",),
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
            "earnings_calendar",
            ("v4/extracts/compustat_quarterly.parquet",),
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
                "CRSP: once the delisting return is known; 2026: the last form used",
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
    "compustat_quarterly": 4,
    "compustat_annual": 4,
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
# Sources the backtest may never read (PLAN §1.2).
NEVER = {
    "organisers_8k": "survivor-biased (A1); its permno-CIK pairs feed the links only",
    "fiam_v1_wrds": "v1-v3 copies, not point in time; use data/v4/extracts",
    "features_monthly_adjfct": "encodes future splits (A4)",
    "ibes": "today's vintage, history rewritten (B27); the live desk only",
    "carbon_arc": "current vintage (B29); live only, CA0065S volume excepted (B30)",
    "short_interest_lending": "stock-lending demand, not exchange short interest (A10)",
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
    market = pd.read_parquet(EXTRACTS / "crsp_market_daily.parquet", columns=["dlycaldt"])
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
    m = pd.read_parquet(EXTRACTS / "crsp_monthly.parquet", columns=cols)
    m = m.rename(columns=lambda c: c.lower().removeprefix("mth"))
    m = m.rename(columns={"caldt": "date", "cap": "cap_musd", "shrout": "shrout_k"})
    m["permno"] = pd.to_numeric(m["permno"]).astype("int64")
    m["date"] = pd.to_datetime(m["date"]).astype("datetime64[ns]")
    m["cap_musd"] = m["cap_musd"] / 1000
    return stamped(m, None, cal, market_day=clock.eom_session(m["date"], cal))


# CRSP delistings, public once their return is known (accounting).
def load_delistings(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    d = pd.read_parquet(EXTRACTS / "crsp_delistings.parquet").drop(columns=["ticker"])
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    for col in ("delistingdt", "delnextdt", "delamtdt", "deldlydt"):
        d[col] = pd.to_datetime(d[col], errors="coerce").astype("datetime64[ns]")
    known = d["delnextdt"].fillna(d["delistingdt"])
    return stamped(d, clock.end_of_day(known), cal)


# CRSP distributions, public at their declaration (checks only).
def load_distributions(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    d = pd.read_parquet(EXTRACTS / "crsp_distributions.parquet").drop(columns=["ticker"])
    d["permno"] = pd.to_numeric(d["permno"]).astype("int64")
    for col in ("disexdt", "disdeclaredt", "disrecorddt", "dispaydt"):
        d[col] = pd.to_datetime(d[col], errors="coerce").astype("datetime64[ns]")
    known = d["disdeclaredt"].fillna(d["disexdt"])
    log["declared_missing"] = int(d["disdeclaredt"].isna().sum())
    return stamped(d, clock.end_of_day(known), cal)


# CRSP's market series at each day's close.
def load_market(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    m = pd.read_parquet(EXTRACTS / "crsp_market_daily.parquet").rename(columns={"dlycaldt": "date"})
    m["date"] = pd.to_datetime(m["date"]).astype("datetime64[ns]")
    return stamped(m, None, cal, market_day=m["date"])


# Exchange short interest on PERMNO: WRDS legacy, then FINRA (A10).
def load_short_interest(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    s = pd.read_parquet(EXTRACTS / "short_interest_legacy.parquet")
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
    # A row FINRA later corrected takes the stock's last uncorrected value
    # from up to 2 months before, published then (approved 2026-10-23, 1B).
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
    return stamped(both, ours, cal)


# Filings and forms on the acceptance clock, per filing and PERMNO.
def load_edgar(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    f = pd.concat(
        [
            pd.read_parquet(data / "edgar" / "filings.parquet").assign(kind="filing"),
            pd.read_parquet(data / "edgar" / "forms.parquet"),
        ],
        ignore_index=True,
    ).drop_duplicates("accession")
    f["filing_date"] = pd.to_datetime(f["filing_date"]).astype("datetime64[ns]")
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    f = by_cik(f, lk, "filing_date", log)
    public = clock.edgar_available(f["accepted"], f["filing_date"])
    return stamped(f, public, cal)


# SEC Forms 4 and 4/A: open-market lines, timed by acceptance (§6.3).
def load_sec_insiders(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    forms = pd.read_parquet(
        data / "edgar" / "forms.parquet", columns=["accession", "form", "accepted"]
    )
    forms = forms[forms["form"].isin(INSIDER_FORMS)].drop_duplicates("accession")
    accepted = forms.set_index("accession")["accepted"]
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
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
        # Joint filings: the first owner stands for the line, the count kept.
        owners = owners[owners["ACCESSION_NUMBER"].isin(sub["ACCESSION_NUMBER"])]
        first = owners.drop_duplicates("ACCESSION_NUMBER")
        first = first.assign(
            n_owners=first["ACCESSION_NUMBER"].map(owners["ACCESSION_NUMBER"].value_counts())
        )
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
    t["cik"] = pd.to_numeric(t["issuer_cik"], errors="coerce").astype("int64")
    t = by_cik(t.drop(columns=["issuer_cik"]), lk, "filing_date", log)
    stamp_at = t["accession"].map(accepted)
    log["with_acceptance_time"] = round(float(stamp_at.notna().mean()), 4)
    return stamped(t, clock.insider_available(stamp_at, t["filing_date"]), cal)


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


# Key developments from their entry instant; one copy per event (A9).
def load_key_developments(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    e = pd.read_parquet(EXTRACTS / "events.parquet")
    e = e.drop(
        columns=["ticker", "ticker_startdate", "ticker_enddate", "speffectivedate", "sptodate"]
    )
    before = len(e)
    e = e.drop_duplicates(["keydevid", "gvkey"])
    log["copies_dropped"] = before - len(e)
    e["entered"] = pd.to_datetime(e["entereddateutc"], errors="coerce", utc=True)
    e = e.dropna(subset=["entered"])
    e = e[e["entered"] >= pd.Timestamp("2004-01-01", tz="UTC")]
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    gv = link_table.nanos(
        lk.loc[lk["kind"] == "gvkey", ["permno", "value", "valid_from", "valid_to"]]
    )
    e["day"] = e["entered"].dt.tz_localize(None).astype("datetime64[ns]")
    both = e.assign(row=range(len(e))).merge(gv.rename(columns={"value": "gvkey"}), on="gvkey")
    live = (both["day"] >= both["valid_from"]) & (
        both["valid_to"].isna() | (both["day"] <= both["valid_to"])
    )
    both = both[live]
    log["events_without_permno"] = int(len(e) - both["row"].nunique())
    both = both.drop(columns=["row", "day", "valid_from", "valid_to"]).astype({"permno": "int64"})
    return stamped(both, both["entered"], cal)


# Restatements from the end of their filing day, on PERMNO by SEC id.
def load_restatements(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    r = pd.read_parquet(EXTRACTS / "restatements.parquet")
    banned = set(REGISTRY["restatements"].banned)
    keep = [c for c in r.columns if not c.startswith(("http_", "ftp_")) and c != "disclosure_text"]
    r = r[[c for c in keep if c not in banned]].copy()
    r["file_date"] = pd.to_datetime(r["file_date"], errors="coerce").astype("datetime64[ns]")
    r["cik"] = pd.to_numeric(r["company_fkey"], errors="coerce")
    r = r.dropna(subset=["cik", "file_date"])
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    r = by_cik(r, lk, "file_date", log)
    return stamped(r, clock.end_of_day(r["file_date"]), cal)


# VIX and its siblings at each close; two copied dates dropped (A16).
def load_vix(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    v = pd.read_parquet(EXTRACTS / "vix_daily.parquet")
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
    return t.assign(available_at=clock.end_of_day(end).dt.tz_convert("UTC"), first_close=pd.NaT)


# Projected earnings dates per quarter, on PERMNO by gvkey (B22).
def load_earnings_calendar(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    cols = ["gvkey", "datadate", "fyearq", "fqtr", "rdq"]
    q = pd.read_parquet(EXTRACTS / "compustat_quarterly.parquet", columns=cols)
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
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    gv = link_table.nanos(
        lk.loc[lk["kind"] == "gvkey", ["permno", "value", "valid_from", "valid_to"]]
    )
    both = projected.merge(gv.rename(columns={"value": "gvkey"}), on="gvkey")
    # The link on the day the projection is made, never the projected day.
    when = both["known_from"].astype("datetime64[ns]")
    live = (when >= both["valid_from"]) & (both["valid_to"].isna() | (when <= both["valid_to"]))
    both = both[live & both["projected"].notna()].drop(columns=["valid_from", "valid_to"])
    # The real release date is known only once it happens (H2), so it is cut.
    both = both.drop(columns=["rdq"])
    both = both.drop_duplicates(["permno", "gvkey", "fyearq", "fqtr"]).astype({"permno": "int64"})
    log["permno_quarters"] = len(both)
    return stamped(both, clock.end_of_day(both["known_from"]), cal)


# The dated exits table, CRSP to 2025 and SEC-dated in 2026 (§6.4).
def load_exits(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    from fiam.v4 import exits

    table, report = exits.build(data)
    log.update(report)
    known = table["known"].fillna(table["exit_date"])
    return stamped(table, clock.end_of_day(known), cal)


# The link table as registered; its periods are its clock.
def load_links(data: Path, cal: pd.Series, log: dict) -> pd.DataFrame:
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
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
    "key_developments": load_key_developments,
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
    }


# Converts one source to data/v4/clean and writes its card.
def convert(name: str, data: Path = DATA, cal: pd.Series | None = None) -> dict:
    source = REGISTRY[name]
    cal = trading_calendar(data) if cal is None else cal
    files = raw_files(source, data)
    if not files:
        raise FileNotFoundError(f"{name}: no raw file under {source.raw}")
    log: dict = {}
    CLEAN.mkdir(parents=True, exist_ok=True)
    CARDS.mkdir(parents=True, exist_ok=True)
    if name == "crsp_daily":
        frames = []
        folder = CLEAN / "crsp_daily"
        folder.mkdir(exist_ok=True)
        for n, path in enumerate(files):
            part = load_crsp_daily(path, cal)
            part.to_parquet(folder / f"part-{n:02d}.parquet", index=False)
            frames.append(part[["permno", "date", "first_close", "available_at"]])
        frame = pd.concat(frames, ignore_index=True)
    else:
        frame = LOADERS[name](data, cal, log)
        bad = [c for c in source.banned if c in frame.columns]
        if bad:
            raise AssertionError(f"{name}: banned columns survived {bad}")
        frame.to_parquet(CLEAN / f"{name}.parquet", index=False)
    log["duplicate_keys"] = assert_unique(frame, source)
    log["rows_without_first_close"] = int(frame["first_close"].isna().sum())
    made = card(source, files, frame, log)
    (CARDS / f"{name}.json").write_text(json.dumps(made, indent=1, default=str))
    return made


# Reads a clean table under blind mode, bans and limits (§1.2, §1.3).
def read(name: str, columns: list[str] | None = None, purpose: str | None = None) -> pd.DataFrame:
    if name in NEVER:
        raise NotForBacktest(f"{name}: {NEVER[name]}")
    source = REGISTRY[name]
    # Exhibit-only sources never reach the backtest (approved 2026-10-23).
    if source.use == "exhibit" and purpose not in {"exhibit", "live"}:
        raise NotForBacktest(f"{name}: exhibits and live context only")
    asked = None if columns is None else set(columns)
    for col in (asked or set()) & set(source.banned):
        raise BannedField(f"{name}.{col} is banned (§1.2)")
    for col, allowed in source.restricted.items():
        if asked is not None and col in asked and purpose not in allowed:
            raise BannedField(f"{name}.{col} only for {sorted(allowed)} (§1.2)")
    path = CLEAN / name if name == "crsp_daily" else CLEAN / f"{name}.parquet"
    need = {"available_at", "first_close", "eom"} | set(source.key)
    frame = pd.read_parquet(path) if asked is None else read_some(path, sorted(asked | need))
    if asked is None:
        hidden = [c for c, ok in source.restricted.items() if purpose not in ok]
        frame = frame.drop(columns=[c for c in hidden if c in frame.columns])
    frame = sealed_out(frame, source, set(frame.columns) if asked is None else asked)
    if asked is None:
        return frame
    order = [*source.key, *columns, "first_close", "available_at"]
    return frame[[c for c in dict.fromkeys(order) if c in frame.columns]]


# Only the columns a table really has, so asking for eom never fails.
def read_some(path: Path, want: list[str]) -> pd.DataFrame:
    import pyarrow.dataset as ds

    have = set(ds.dataset(path).schema.names)
    return pd.read_parquet(path, columns=[c for c in want if c in have])


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
    path = CLEAN / name if name == "crsp_daily" else CLEAN / f"{name}.parquet"
    frame = pd.read_parquet(path, columns=["first_close", "available_at"])
    return by_year(frame)


# Converts the step 3 tables: uv run python -m fiam.v4.sources [names]
if __name__ == "__main__":
    names = sys.argv[1:] or ["crsp_daily", *LOADERS]
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
