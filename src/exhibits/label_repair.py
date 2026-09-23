# Fills blank tickers using only labels dated on or before the month we held the stock.
#
# A fallback, not a source of record. An older label is wrong if the name changed since.

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

HOLDINGS = Path("submission/holdings.csv")
CHARS = Path("data/chars_final_with_names.parquet")


# Every labelled (stock, month) in the panel, which is what we search backwards through.
def labels() -> pd.DataFrame:
    cols = ["permno", "eom", "ticker", "company_name"]
    panel = pq.read_table(CHARS, columns=cols).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"]).astype("datetime64[ns]")
    return panel[panel["ticker"].notna()].sort_values("eom")


# Fills every blank label it safely can, and refuses to write if a row went missing.
def main() -> int:
    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    missing = book["TICKER"].isna()
    if not missing.any():
        print("every holding already has a label")
        return 0

    # Only labels from the decision month or earlier. Searching forward is look-ahead.
    book["eom"] = (book["Date"] - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    filled = pd.merge_asof(
        book.sort_values("eom"),
        labels(),
        on="eom",
        left_by="PERMNO",
        right_by="permno",
        direction="backward",
    )
    filled["TICKER"] = filled["TICKER"].fillna(filled["ticker"])
    filled["COMPANY_NAME"] = filled["COMPANY_NAME"].fillna(filled["company_name"])

    still_missing = int(filled["TICKER"].isna().sum())
    repaired = int(missing.sum()) - still_missing
    print(f"repaired {repaired} of {int(missing.sum())} unlabelled rows, {still_missing} left")

    # Only rewrite if no row was lost. A silent drop beats the blank labels we started with.
    if len(filled) != len(book):
        print("row count changed, refusing to write")
        return 1
    out = filled.sort_values(["Date", "PERMNO"])[
        ["Date", "PERMNO", "TICKER", "COMPANY_NAME", "WEIGHT"]
    ]
    out.to_csv(HOLDINGS, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
