# Checks the brief's rules and recomputes the headline, with no data.

import json
import sys

import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import paths

COLUMNS = ["Date", "PERMNO", "TICKER", "COMPANY NAME", "WEIGHT"]
FIRST, LAST, MONTHS = "2021-01-01", "2026-08-01", 68


# The brief's Trading Criteria and Final Submission Package rules.
def rules(holdings: pd.DataFrame, returns: pd.DataFrame) -> list[tuple[str, bool, str]]:
    if holdings.empty:
        return [("holdings.csv has rows", False, "empty")]
    months = pd.DatetimeIndex(sorted(holdings["Date"].unique()))
    span = [pd.Timestamp(FIRST), pd.Timestamp(LAST)]
    by = holdings.groupby("Date")["WEIGHT"]
    count, gross, net = by.size(), by.apply(lambda w: w.abs().sum()) / 100, by.sum() / 100
    labels = holdings[["TICKER", "COMPANY NAME"]].isna().any(axis=1).sum()
    held = set(pd.to_datetime(returns["holding_month"]))
    return [
        ("columns", list(holdings.columns) == COLUMNS, ", ".join(holdings.columns)),
        (
            "months",
            len(months) == MONTHS and [months[0], months[-1]] == span and (months.day == 1).all(),
            f"{len(months)}, {months[0]:%Y-%m} to {months[-1]:%Y-%m}, first of each month",
        ),
        ("positions 100-500", count.between(100, 500).all(), f"{count.min()} to {count.max()}"),
        ("gross at most 200%", (gross <= 2 + 1e-6).all(), f"max {gross.max():.2%}"),
        ("net inside +/-50%", (net.abs() <= 0.5).all(), f"max |net| {net.abs().max():.2%}"),
        ("every row labelled", labels == 0, f"{labels} rows without ticker or name"),
        ("one row per stock-month", not holdings.duplicated(["Date", "PERMNO"]).any(), "unique"),
        ("returns cover the same months", held == set(months), f"{len(held)} months"),
    ]


# IR vs T-bill + 4%, Sharpe vs T-bill and S&P 500 beta, per the brief.
def headline(returns: pd.DataFrame) -> dict:
    # Cash rate from pinned FRED, not the file, so the check is independent.
    df = returns.drop(columns=["rf"], errors="ignore")
    df = df.assign(month=pd.to_datetime(df["holding_month"])).merge(
        B.benchmarks()[["month", "rf", "mkt_rf"]], on="month", how="left"
    )
    active = df["portfolio_total_return"] - (df["rf"] + 0.04 / 12)
    excess = df["portfolio_total_return"] - df["rf"]
    fit = df.dropna(subset=["mkt_rf"])
    beta = np.polyfit(fit["mkt_rf"], fit["portfolio_total_return"] - fit["rf"], 1)[0]
    return dict(
        information_ratio=float(active.mean() / active.std() * np.sqrt(12)),
        sharpe_ratio=float(excess.mean() / excess.std() * np.sqrt(12)),
        beta_realized=float(beta),
    )


# Checks the submitted files against every rule and prints each result.
def main() -> int:
    holdings_path = paths.SUBMISSION / "holdings.csv"
    returns_path = paths.SUBMISSION / "returns.csv"
    if not holdings_path.exists() or not returns_path.exists():
        print(f"Nothing to check: {holdings_path} and {returns_path} are not here.")
        return 1
    holdings = pd.read_csv(holdings_path, parse_dates=["Date"])
    returns = pd.read_csv(returns_path)

    results = rules(holdings, returns)
    reported_path = paths.SUBMISSION / "metrics.json"
    if reported_path.exists():
        reported = json.loads(reported_path.read_text(encoding="utf-8"))["performance"]
        for key, value in headline(returns).items():
            ok = abs(value - reported[key]) < 1e-3
            results.append((key, ok, f"recomputed {value:+.3f}, reported {reported[key]:+.3f}"))

    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<30} {detail}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed} of {len(results)} submission checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
