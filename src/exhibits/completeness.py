# The statistics the rules ask for that the headline table does not already carry.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

RETURNS = Path("submission/returns.csv")
HOLDINGS = Path("submission/holdings.csv")
CHARS = Path("data/chars_final_with_names.parquet")
OUT = Path("submission/exhibits")


# What a series of monthly returns actually earned over the period.
def compound(monthly: pd.Series) -> float:
    return float((1 + monthly.dropna()).prod() - 1)


# Strategy, benchmark and market by calendar year, which the rules ask for explicitly.
def by_year(df: pd.DataFrame) -> dict:
    market = P.benchmarks().set_index("month")["mkt_rf"]
    df = df.set_index("holding_month")
    out = {}
    for year, g in df.groupby(df.index.year):
        mkt = market.reindex(g.index)
        # Compounded, not summed. Twelve monthly returns added up is not a year.
        out[int(year)] = dict(
            months=int(len(g)),
            partial_year=bool(len(g) < 12),  # 2026 stops in August, so do not compare it flat
            strategy=compound(g["portfolio_total_return"]),
            benchmark=compound(g["rf"] + 0.04 / 12),
            market=compound(mkt + g["rf"]) if mkt.notna().any() else None,
            active=compound(g["portfolio_total_return"]) - compound(g["rf"] + 0.04 / 12),
        )
    return out


# Exposure and turnover ranges. The rules ask for averages and extremes, not just averages.
def ranges(df: pd.DataFrame) -> dict:
    return {
        name: dict(mean=float(df[col].mean()), min=float(df[col].min()), max=float(df[col].max()))
        for name, col in [
            ("gross_exposure", "gross_exposure"),
            ("net_exposure", "net_exposure"),
            ("turnover_one_way", "turnover"),
            ("positions", "n"),
        ]
    }


# What the long and short legs each contributed, since a market-neutral book is two books.
def legs() -> dict:
    panel = pq.read_table(
        CHARS, columns=["permno", "eom", "ret_exc_lead1m", "me", "dolvol_126d"]
    ).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    panel["holding_month"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()

    book = pd.read_csv(HOLDINGS, parse_dates=["Date"]).rename(columns={"Date": "holding_month"})
    book["w"] = book["WEIGHT"] / 100
    merged = book.merge(
        panel, left_on=["PERMNO", "holding_month"], right_on=["permno", "holding_month"], how="left"
    )
    merged["pnl"] = merged["w"] * merged["ret_exc_lead1m"].fillna(0.0)

    out = {}
    for side, mask in [("long", merged["w"] > 0), ("short", merged["w"] < 0)]:
        part = merged[mask]
        monthly = part.groupby("holding_month")["pnl"].sum()
        out[side] = dict(
            annual_contribution=float(monthly.mean() * 12),
            volatility=float(monthly.std() * np.sqrt(12)),
            names_per_month=float(part.groupby("holding_month").size().mean()),
            mean_market_cap_musd=float(part["me"].mean()),
            median_market_cap_musd=float(part["me"].median()),
            mean_dollar_volume=float(part["dolvol_126d"].mean()),
            median_dollar_volume=float(part["dolvol_126d"].median()),
        )

    # How much of the book sits in its ten largest positions.
    top10 = (
        book.assign(a=book["w"].abs())
        .groupby("holding_month")["a"]
        .nlargest(10)
        .groupby(level=0)
        .sum()
    )
    gross = book.groupby("holding_month")["w"].apply(lambda s: s.abs().sum())
    out["top10_share_of_gross"] = float((top10 / gross).mean())
    return out


# Collects every statistic the rules enumerate into one file for the deck.
def main() -> None:
    df = pd.read_csv(RETURNS, parse_dates=["holding_month"])
    monthly = df["portfolio_total_return"]
    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    per_month = book.groupby("Date")
    # The first five the rules list and the headline table does not carry.
    out = dict(
        average_monthly_return=float(monthly.mean()),
        cumulative_return_full_period=float((1 + monthly).prod() - 1),
        average_long_positions=float(per_month["WEIGHT"].apply(lambda s: (s > 0).sum()).mean()),
        average_short_positions=float(per_month["WEIGHT"].apply(lambda s: (s < 0).sum()).mean()),
        average_absolute_position_weight=float(book["WEIGHT"].abs().mean() / 100),
        by_year=by_year(df),
        ranges=ranges(df),
        legs=legs(),
        best_month=dict(
            month=str(df.loc[monthly.idxmax(), "holding_month"].date()), value=float(monthly.max())
        ),
        worst_month=dict(
            month=str(df.loc[monthly.idxmin(), "holding_month"].date()), value=float(monthly.min())
        ),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "completeness.json").write_text(json.dumps(out, indent=2))

    print("calendar year returns (strategy / benchmark / active)")
    for year, v in out["by_year"].items():
        flag = " (Jan-Aug only)" if v["partial_year"] else ""
        print(f"  {year}  {v['strategy']:>7.1%}  {v['benchmark']:>6.1%}  {v['active']:>7.1%}{flag}")
    legs_out = out["legs"]
    print(
        f"\nlong leg {legs_out['long']['annual_contribution']:+.1%}/yr, "
        f"short leg {legs_out['short']['annual_contribution']:+.1%}/yr, "
        f"top-10 share of gross {legs_out['top10_share_of_gross']:.1%}"
    )


if __name__ == "__main__":
    main()
