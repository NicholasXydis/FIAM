# Decile tables for every scoring model, which is how a signal earns its place here.
# Reads cache/preds/, writes submission/exhibits/decile_tables.csv.

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import pipeline as P

PREDS = Path("cache/preds")
OUT = Path("submission/exhibits")


# Average next-month excess return by decile of the score, annualized.
def deciles(frame: pd.DataFrame, score: str, n: int = 10) -> pd.Series:
    scored = frame.dropna(subset=[score, "actual"]).copy()
    # Rank inside each month, so a decile means the same thing in every cross-section.
    scored["bucket"] = scored.groupby("holding_month")[score].transform(
        lambda s: pd.qcut(s.rank(method="first"), n, labels=False, duplicates="drop")
    )
    monthly = scored.groupby(["holding_month", "bucket"])["actual"].mean()
    return monthly.groupby("bucket").mean() * 12


# The composite scored on the same universe, so the two tables are comparable.
def composite_frame() -> pd.DataFrame:
    df = P.build_signal(P.screen(P.load_panel()))
    return pd.DataFrame(
        dict(
            holding_month=(df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize(),
            composite=df["signal"].to_numpy(),
            actual=df["ret_exc_lead1m"].to_numpy(),
        )
    )


# Builds one decile row per model and writes them out as a single table.
def main() -> None:
    rows = {}
    comp = composite_frame()
    rows["composite"] = deciles(comp, "composite")
    for path in sorted(PREDS.glob("*.parquet")):
        frame = pd.read_parquet(path).rename(columns={"pred": path.stem})
        rows[path.stem] = deciles(frame, path.stem)

    table = pd.DataFrame(rows).T
    table.columns = [f"d{int(c) + 1}" for c in table.columns]
    table["top_minus_bottom"] = table.iloc[:, -1] - table.iloc[:, 0]
    # Rising through the tails is what a long-short book needs. A high middle is
    # worth nothing, because the middle never enters the book.
    table["top_beats_second"] = table["d10"] > table["d9"]
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "decile_tables.csv")
    print((table * 100).round(1).to_string())


if __name__ == "__main__":
    main()
