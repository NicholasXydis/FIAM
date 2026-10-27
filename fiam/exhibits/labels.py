# Checks each held label on a dated source. Writes labels.csv and .json.

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

from fiam import book as P
from fiam import data, paths

SOURCES = P.CACHE / "label_sources.parquet"
EDGAR = P.CACHE / "edgar"
OUT = paths.EXHIBITS

# Endings that differ by source without changing who the company is.
SUFFIXES = "|".join(
    ["INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "PLC", "LP", "LLC", "paths.HOLDINGS"]
    + ["HLDGS", "HLDG", "GROUP", "THE", "NV", "SA", "AG", "NEW", "DE"]
)

# CRSP's last month. Until then CRSP decides; after, public filings do.
CRSP_END = pd.Timestamp("2025-12-31")


# Upper case, no punctuation, suffix or spaces, so "S I G A" is "SIGA".
def normalise(name) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(name).upper())
    return re.sub(r"\s+", "", re.sub(rf"\b({SUFFIXES})\b", " ", text))


# Class dots and Compustat's inactive suffix vary; only letters count.
def symbol(ticker) -> str:
    return re.sub(r"[^A-Z]", "", re.sub(r"\.\d+$", "", str(ticker).upper()))


# Same name, or ours cut at 32 characters: same start, letters in order.
def same_name(ours, theirs) -> bool:
    a, b = normalise(ours), normalise(theirs)
    rest = iter(b)
    return a == b or (a[:4] == b[:4] and all(letter in rest for letter in a))


# Holding rows by decision month, flagging borrowed and on-show labels.
def holdings() -> pd.DataFrame:
    book = paths.holdings()
    book["eom"] = (book["Date"] - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    borrowed = pd.read_parquet(SOURCES).assign(Date=lambda d: pd.to_datetime(d["Date"]))
    book = book.merge(borrowed, on=["Date", "PERMNO"], how="left")
    book["borrowed"] = book["label_month"].notna()

    # Names the charts and tables show: top ten a side by weight and by P&L.
    earned = P.universe()[["permno", "eom", "ret_exc_lead1m"]]
    earned = earned.assign(eom=earned["eom"].astype("datetime64[ns]"))
    pnl = book.merge(earned, left_on=["PERMNO", "eom"], right_on=["permno", "eom"], how="left")
    pnl = (pnl["WEIGHT"] * pnl["ret_exc_lead1m"].fillna(0.0)).groupby(pnl["PERMNO"]).sum()
    weight = book.groupby("PERMNO")["WEIGHT"].sum()
    shown = {*weight.nlargest(10).index, *weight.nsmallest(10).index}
    shown |= {*pnl.nlargest(10).index, *pnl.nsmallest(10).index}
    book["shown"] = book["PERMNO"].isin(shown)
    return book


# CRSP's ticker and issuer at decision month-end, or none without WRDS.
def crsp(book: pd.DataFrame) -> pd.DataFrame:
    names = data.wrds("crsp_monthly", ["PERMNO", "YYYYMM", "Ticker", "IssuerNm", "SecInfoStartDt"])
    if names is None:
        return pd.DataFrame(index=book.index, columns=["crsp_ticker", "crsp_name"])
    names["start"] = pd.to_datetime(names["SecInfoStartDt"]).astype("datetime64[ns]")
    # A name change inside a month gives two records; the later is in force.
    names = names.sort_values("start").drop_duplicates(["PERMNO", "YYYYMM"], keep="last")
    key = book["eom"].dt.year * 100 + book["eom"].dt.month
    found = pd.DataFrame(dict(PERMNO=book["PERMNO"], YYYYMM=key)).merge(
        names, on=["PERMNO", "YYYYMM"], how="left"
    )
    found.index = book.index
    return found.rename(columns={"Ticker": "crsp_ticker", "IssuerNm": "crsp_name"})[
        ["crsp_ticker", "crsp_name"]
    ]


# The latest 8-K on or before the decision month, never a later one.
def filings(book: pd.DataFrame) -> pd.DataFrame:
    table = data.filings(["permno", "filing_date", "document_id", "ticker", "company_name", "cik"])
    table["eom"] = pd.to_datetime(table["filing_date"]).astype("datetime64[ns]")
    matched = pd.merge_asof(
        book[["PERMNO", "eom"]].reset_index().sort_values("eom"),
        table.sort_values("eom").drop(columns="permno").assign(PERMNO=table["permno"]),
        on="eom",
        by="PERMNO",
        direction="backward",
    ).set_index("index")
    renamed = dict(ticker="filing_ticker", company_name="filing_company", filing_date="filed")
    return matched.rename(columns=renamed)[[*renamed.values(), "cik", "document_id"]]


# SEC's filer record: the name in force on a date, and its tickers.
def edgar(cik, eom: pd.Timestamp) -> tuple[str | None, list[str]]:
    path = None if pd.isna(cik) else EDGAR / f"CIK{int(cik):010d}.json"
    if path is None or not path.exists():
        return None, []
    record = json.loads(path.read_text(encoding="utf-8"))
    for former in record.get("formerNames", []):
        if pd.Timestamp(former["from"][:10]) <= eom <= pd.Timestamp(former["to"][:10]):
            return former["name"], record.get("tickers", [])
    return record["name"], record.get("tickers", [])


# Compustat's header by gvkey. Current, undated, so the weakest source.
def compustat(book: pd.DataFrame) -> pd.DataFrame:
    header = data.wrds("compustat_quarterly", ["gvkey", "datadate", "tic", "conm", "cik"])
    if header is None:
        return pd.DataFrame(index=book.index, columns=["comp_ticker", "comp_name", "comp_cik"])
    header = header.sort_values("datadate").drop_duplicates("gvkey", keep="last")
    # The panel's gvkey in the decision month itself, never an undated one.
    keys = data.features(["gvkey"]).dropna()
    keys["eom"] = keys["eom"].astype("datetime64[ns]")
    dated = book[["PERMNO", "eom"]].merge(
        keys, left_on=["PERMNO", "eom"], right_on=["permno", "eom"], how="left"
    )
    gvkey = dated["gvkey"].astype("Int64").astype("string").str.zfill(6)
    found = header.set_index("gvkey").reindex(gvkey)[["tic", "conm", "cik"]]
    found.index = book.index
    return found.rename(columns={"tic": "comp_ticker", "conm": "comp_name", "cik": "comp_cik"})


# The first source agreeing on ticker and name, best-dated first.
def verdict(row) -> str:
    ticker, name = symbol(row["TICKER"]), row["COMPANY NAME"]
    # An SEC-dated name correction counts, even where CRSP has the typo.
    if (row.get("PERMNO"), name) in {(fix[0], fix[3]) for fix in P.LABEL_FIXES}:
        return "EDGAR, dated correction"
    if row["eom"] <= CRSP_END:
        if pd.isna(row["crsp_ticker"]):
            return "unconfirmed: no CRSP record that month"
        # CRSP keeps the class letter apart, so BF plus B is our BFB.
        root = symbol(row["crsp_ticker"])
        agree = ticker == root or (len(ticker) == len(root) + 1 and ticker.startswith(root))
        named = same_name(name, row["crsp_name"])
        if agree and named:
            return "CRSP, dated"
        return "differs from CRSP on " + (
            "both" if not agree and not named else "ticker" if not agree else "name"
        )
    candidates = [
        ("8-K on or before", [row["filing_ticker"]], row["filing_company"]),
        ("EDGAR, dated name and current ticker", row["edgar_tickers"], row["edgar_name"]),
        ("Compustat header, current", [row["comp_ticker"]], row["comp_name"]),
    ]
    for source, tickers, issuer in candidates:
        if pd.notna(issuer) and ticker in map(symbol, tickers) and same_name(name, issuer):
            return source
    return "unconfirmed: no public source agrees on both"


# One EDGAR record per filer, fetched once with a contact, then cached.
def fetch(ciks: set) -> None:
    contact = (
        os.environ.get("SEC_CONTACT")
        or dict(
            line.split("=", 1)
            for line in Path(".env").read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        .get("SEC_CONTACT", "")
        .strip()
    )
    if not contact:
        raise SystemExit("set SEC_CONTACT in .env to an email SEC can reach")
    EDGAR.mkdir(parents=True, exist_ok=True)
    for cik in sorted(ciks):
        path = EDGAR / f"CIK{int(cik):010d}.json"
        if path.exists():
            continue
        url = f"https://data.sec.gov/submissions/{path.name}"
        request = urllib.request.Request(url, headers={"User-Agent": f"FIAM research {contact}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
        # SEC allows ten requests a second; this stays well under.
        time.sleep(0.2)
    print(f"  EDGAR: {len(ciks)} filers cached in {EDGAR}")


# Confirms every holding label and writes labels.csv and labels.json.
def main() -> None:
    book = holdings()
    book = book.join(crsp(book)).join(filings(book)).join(compustat(book))
    late = book["eom"] > CRSP_END
    # A name with no 8-K still has a Compustat filer number to ask EDGAR.
    book["cik"] = pd.to_numeric(book["cik"].fillna(book.pop("comp_cik")), errors="coerce")
    if "--fetch" in sys.argv:
        fetch(set(book.loc[late, "cik"].dropna().astype(int)))
    found = [
        edgar(c, e) if after else (None, []) for c, e, after in zip(book["cik"], book["eom"], late)
    ]
    book["edgar_name"] = [name for name, _ in found]
    book["edgar_tickers"] = [tickers for _, tickers in found]
    book["source"] = book.apply(verdict, axis=1)
    book["confirmed"] = ~book["source"].str.startswith(("unconfirmed", "differs"))

    # Written out: every unconfirmed row, borrowed label and name on show.
    listed = book[~book["confirmed"] | book["borrowed"] | book["shown"]].copy()
    listed["edgar_tickers"] = listed["edgar_tickers"].str.join(" ")
    listed["why_listed"] = (
        listed["borrowed"].map({True: "borrowed ", False: ""})
        + listed["shown"].map({True: "shown ", False: ""})
        + (~listed["confirmed"]).map({True: "unconfirmed", False: ""})
    ).str.strip()
    # Public evidence only. No CRSP or Compustat value is committed.
    keep = ["Date", "PERMNO", "TICKER", "COMPANY NAME", "why_listed", "source", "label_month"]
    keep += ["filing_ticker", "filing_company", "filed", "cik", "edgar_name", "edgar_tickers"]
    OUT.mkdir(parents=True, exist_ok=True)
    listed[keep].sort_values(["Date", "PERMNO"]).to_csv(
        OUT / "labels.csv", index=False, lineterminator="\n"
    )

    period = late.map({False: "2021_2025_crsp", True: "2026_public_filings"})
    summary = dict(
        what="Every holding's ticker and name checked against CRSP's dated record through 2025, "
        "then the latest prior 8-K, EDGAR's dated issuer name and Compustat. Nothing is guessed: "
        "a label no source confirms is listed in labels.csv and left as the panel had it.",
        holding_rows=int(len(book)),
        confirmed_share=float(book["confirmed"].mean()),
        by_period={p: g.value_counts().to_dict() for p, g in book["source"].groupby(period)},
        borrowed=book.loc[book["borrowed"], "source"].value_counts().to_dict(),
        shown=book.loc[book["shown"]]
        .drop_duplicates("PERMNO", keep="last")["source"]
        .value_counts()
        .to_dict(),
        corrected=[
            dict(permno=permno, was=wrong, now=right, from_decisions_on_or_after=since)
            for permno, wrong, since, right in P.LABEL_FIXES
        ],
        edgar_filers_cached=len(list(EDGAR.glob("*.json"))) if EDGAR.exists() else 0,
    )
    paths.write_json(OUT / "labels.json", summary)
    print(json.dumps(summary["by_period"], indent=2))


if __name__ == "__main__":
    main()
