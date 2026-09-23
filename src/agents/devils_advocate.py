# Builds the evidence pack the devil's-advocate prompt attacks. Writes submission/exhibits/.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

HOLDINGS = Path("submission/holdings.csv")
FILINGS = Path("data/8k_20150101_20260831_identified.parquet")
OUT = Path("submission/exhibits")

# A line break inside a built-up block.
BR = chr(10)

# Ten each side. Fewer misses the book's character, more is a reading list nobody works through.
TOP_N = 10

# What the prompt needs to mount each of its four attacks, in the order it makes them.
FACTS = ["me", "be_me", "ret_12_1", "qmj", "ivol_capm_21d", "dolvol_126d", "zero_trades_126d"]


# Averaged over every month, not only months held, or one-month bets would outrank.
def core_positions() -> pd.DataFrame:
    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    book["w"] = book["WEIGHT"] / 100
    months = book["Date"].nunique()
    # Group on PERMNO alone, or a ticker change splits one security into two.
    held = book.groupby("PERMNO", as_index=False).agg(
        weight_while_held=("w", "mean"), months_held=("w", "size"), as_of=("Date", "max")
    )
    # Then attach the label the security carried in its most recent held month.
    latest = book.sort_values("Date").groupby("PERMNO").last()[["TICKER", "COMPANY_NAME"]]
    held = held.merge(latest, on="PERMNO", how="left")
    # Months not held count as zero, so permanent positions outrank one-offs.
    held["mean_weight"] = held["weight_while_held"] * held["months_held"] / months
    longs = held.nlargest(TOP_N, "mean_weight")
    shorts = held.nsmallest(TOP_N, "mean_weight")
    return pd.concat([longs, shorts], ignore_index=True)


# How much each name actually made or lost us, so the prompt can be told what it is attacking.
def realized_pnl(names: pd.DataFrame) -> pd.Series:
    panel = pq.read_table(P.CHARS, columns=["permno", "eom", "ret_exc_lead1m"]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    panel["Date"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()

    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    book["w"] = book["WEIGHT"] / 100
    merged = book.merge(panel, left_on=["PERMNO", "Date"], right_on=["permno", "Date"], how="left")
    merged["pnl"] = merged["w"] * merged["ret_exc_lead1m"].fillna(0.0)
    # A name can flip sides and appear twice, so look up by permno, never reindex.
    return merged.groupby("PERMNO")["pnl"].sum()


# Characteristics as of the decision month. The latest row would add facts nobody had.
def characteristics(names: pd.DataFrame) -> pd.DataFrame:
    panel = pq.read_table(P.CHARS, columns=["permno", "eom", "size_grp", *FACTS]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"]).astype("datetime64[ns]")
    panel = panel[panel["permno"].isin(names["PERMNO"])].sort_values("eom")

    wanted = names[["PERMNO", "as_of"]].copy()
    # The decision month is the month end before the holding month.
    wanted["eom"] = (wanted["as_of"] - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    wanted = wanted.sort_values("eom")
    asof = pd.merge_asof(
        wanted, panel, on="eom", left_by="PERMNO", right_by="permno", direction="backward"
    )
    return asof.set_index("PERMNO")


# Item codes filed on or before the decision month. Later ones nobody had at the time.
def filing_items(names: pd.DataFrame) -> dict[int, list[str]]:
    table = pq.read_table(FILINGS, columns=["permno", "filing_date", "items"]).to_pandas()
    table["filing_date"] = pd.to_datetime(table["filing_date"])
    cutoff = dict(zip(names["PERMNO"], names["as_of"] - pd.offsets.MonthEnd(1)))
    table = table[table["permno"].isin(cutoff)]
    out: dict[int, list[str]] = {}
    for permno, group in table.groupby("permno"):
        visible = group[group["filing_date"] <= cutoff[permno]]
        codes = sorted({i for items in visible["items"] if items is not None for i in items})
        out[int(permno)] = codes
    return out


# Writes one block per name, formatted for the prompt in prompts/devils_advocate.md.
def main() -> None:
    months = pd.read_csv(HOLDINGS)["Date"].nunique()
    names = core_positions()
    pnl = realized_pnl(names)
    chars = characteristics(names)
    items = filing_items(names)

    blocks, records = [], []
    for row in names.itertuples():
        # A name that flipped sides appears twice, so take the first match rather than a frame.
        if row.PERMNO in chars.index:
            c = chars.loc[row.PERMNO]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[0]
        else:
            c = pd.Series(dtype=float)
        side = "LONG" if row.mean_weight > 0 else "SHORT"
        record = dict(
            permno=int(row.PERMNO),
            ticker=row.TICKER,
            company=row.COMPANY_NAME,
            side=side,
            mean_weight_all_months_pct=round(row.mean_weight * 100, 3),
            weight_while_held_pct=round(row.weight_while_held * 100, 3),
            months_held=int(row.months_held),
            realized_pnl_pct=round(float(pnl.get(row.PERMNO, 0.0)) * 100, 3),
            market_cap_musd=None if c.empty else round(float(c.get("me", np.nan)), 1),
            dollar_volume=None if c.empty else round(float(c.get("dolvol_126d", np.nan)), 1),
            size_group=None if c.empty else str(c.get("size_grp", "")),
            filing_item_codes=items.get(int(row.PERMNO), []),
        )
        records.append(record)
        blocks.append(
            f"{side} {row.TICKER} ({row.COMPANY_NAME})"
            + BR
            + f"  weight {record['mean_weight_all_months_pct']:+.3f}% of NAV over all months,"
            + f" {record['weight_while_held_pct']:+.3f}% while held"
            + f" ({record['months_held']} of {months} months)"
            + BR
            + f"  realised P&L {record['realized_pnl_pct']:+.3f}% of NAV"
            + BR
            + f"  market cap {record['market_cap_musd']} musd,"
            + f" dollar volume {record['dollar_volume']},"
            + f" size group {record['size_group']}"
            + BR
            + f"  8-K items filed: {', '.join(record['filing_item_codes']) or 'none'}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "devils_advocate_positions.json").write_text(json.dumps(records, indent=2))
    (OUT / "devils_advocate_positions.txt").write_text("\n\n".join(blocks), encoding="utf-8")
    borrowable = sum(1 for r in records if r["side"] == "SHORT" and r["size_group"] != "micro")
    print(f"built {len(records)} position blocks, {TOP_N} long and {TOP_N} short")
    print(f"  {borrowable} of {TOP_N} shorts are outside the micro-cap bucket")
    print("  paste each block into prompts/devils_advocate.md, one exchange per name")


if __name__ == "__main__":
    main()
