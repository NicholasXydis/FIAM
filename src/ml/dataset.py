# Builds the train/validate/test folds the rules prescribe. Caches them to cache/folds/.

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

CHARS = Path("data/chars_final_with_names.parquet")
CACHE = Path("cache/folds")

TARGET = "ret_exc_lead1m"

# Same screen as the book, so the ML comparison is against the universe we actually trade.
MIN_PRICE, MIN_ME = 5.0, 300.0

# Expanding train, 2-year validation, annual refit. Test blocks are calendar years.
VAL_YEARS = 2
FIRST_TARGET = "2015-02-01"
FIRST_TEST_YEAR, LAST_TEST_YEAR = 2021, 2026

# Ends at August 2026, the same 68 months the book holds. Otherwise the last fold is 69.
LAST_HOLDING_MONTH = "2026-08-01"
N_HOLDING_MONTHS = 68


# Loads the panel and attaches the holding month, which is what every split keys on.
def load() -> pd.DataFrame:
    cols = P.characteristics() + ["permno", "eom", "prc", "me", TARGET]
    panel = pq.read_table(CHARS, columns=sorted(set(cols))).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    # eom is when we decide, the target lands the month after. Carry both, always.
    panel["holding_month"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    keep = (panel["prc"].abs() >= MIN_PRICE) & (panel["me"] >= MIN_ME)
    return panel[keep].copy()


# Ranks each predictor into [-1, 1] within its month. Gaps filled with that month's median.
def rank_transform(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        g = out.groupby("eom")[col]
        out[col] = out[col].fillna(g.transform("median"))
        r = out.groupby("eom")[col].rank(method="dense") - 1
        mx = r.groupby(out["eom"]).transform("max")
        # A month where every value is missing ranks flat. Zero is the neutral score.
        out[col] = np.where(mx > 0, (r / mx.replace(0, np.nan)) * 2 - 1, 0.0)
    return out


# Yields one (train, validate, test) split per test year, expanding the training window.
def folds(df: pd.DataFrame):
    start = pd.Timestamp(FIRST_TARGET)
    m = df["holding_month"]
    for test_year in range(FIRST_TEST_YEAR, LAST_TEST_YEAR + 1):
        # Work back from the test year, so the block is Jan to Dec, then validation.
        test_start = pd.Timestamp(year=test_year, month=1, day=1)
        test_end = pd.Timestamp(year=test_year + 1, month=1, day=1)
        val_start = test_start - pd.DateOffset(years=VAL_YEARS)
        test_end = min(test_end, pd.Timestamp(LAST_HOLDING_MONTH) + pd.DateOffset(months=1))
        yield dict(
            test_year=test_year,
            train=df[(m >= start) & (m < val_start)],
            validate=df[(m >= val_start) & (m < test_start)],
            test=df[(m >= test_start) & (m < test_end)],
        )


# Models fit the rank, not the return. Raw returns let a few 300% months own the loss.
def rank_target(frame: pd.DataFrame) -> np.ndarray:
    r = frame.groupby("holding_month")[TARGET].rank(pct=True)
    return (r - 0.5).to_numpy()


# Drops rows with no target, train and validation only. Filtering the test month is bias.
def labelled(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame[TARGET].notna()]


# What the cached folds depend on. Any change here has to invalidate them.
def fingerprint() -> str:
    parts = [
        CHARS.stat().st_size,
        P.CHAR_LIST.read_bytes(),
        MIN_PRICE,
        MIN_ME,
        VAL_YEARS,
        FIRST_TARGET,
        FIRST_TEST_YEAR,
        LAST_TEST_YEAR,
        LAST_HOLDING_MONTH,
        TARGET,
    ]
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# Builds the folds once and caches them, so every model script reads the same splits.
def build(refresh: bool = False) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    marker = CACHE / "folds.parquet"
    stamp = CACHE / "fingerprint.txt"
    # Rebuild if the panel, predictors, screen or schedule change. Stale caches ship bugs.
    current = fingerprint()
    if marker.exists() and not refresh and stamp.exists() and stamp.read_text() == current:
        return marker
    cols = P.characteristics()
    df = rank_transform(load(), cols)
    df[["permno", "eom", "holding_month", TARGET] + cols].to_parquet(marker, index=False)
    stamp.write_text(current)
    return marker


# Stops a run whose predictions miss the book's months. A silent 69th breaks every table.
def assert_holding_months(preds: pd.DataFrame) -> None:
    months = preds["holding_month"].nunique()
    assert months == N_HOLDING_MONTHS, f"expected {N_HOLDING_MONTHS} holding months, got {months}"
    last = preds["holding_month"].max()
    assert last == pd.Timestamp(LAST_HOLDING_MONTH), f"last holding month is {last:%Y-%m}"


# Reads the cached table back, building it first if it is not there yet.
def load_folds(refresh: bool = False) -> pd.DataFrame:
    return pd.read_parquet(build(refresh=refresh))


if __name__ == "__main__":
    df = load_folds()
    cols = P.characteristics()
    print(f"panel {len(df):,} rows, {len(cols)} predictors")
    for f in folds(df):
        print(
            f"  test {f['test_year']}: "
            f"train {len(f['train']):>7,}  val {len(f['validate']):>6,}  test {len(f['test']):>6,}"
        )
