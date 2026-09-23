# Builds the train/validate/test folds the rules prescribe, from the supplied panel.
# Reads data/chars_final_with_names.parquet, writes cached folds to cache/folds/.

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CHARS = Path("data/chars_final_with_names.parquet")
CHAR_LIST = Path("data/factor_char_list.csv")
CACHE = Path("cache/folds")

TARGET = "ret_exc_lead1m"

# Same screen as the book, so the ML comparison is against the universe we actually trade.
MIN_PRICE, MIN_ME = 5.0, 300.0

# Expanding training, 2-year rolling validation, annual refit, split by target month.
# Test blocks are calendar years. The panel starts in 2015, so the first one is short.
VAL_YEARS = 2
FIRST_TARGET = "2015-02-01"
FIRST_TEST_YEAR, LAST_TEST_YEAR = 2021, 2026

# The scored window ends with the August 2026 holding month, the same 68 months the book
# holds. Without this the last fold runs to September and the model tables count 69.
LAST_HOLDING_MONTH = "2026-08-01"
N_HOLDING_MONTHS = 68


# The 147 names we are allowed to use. Never "all numeric columns", because the panel's
# bookkeeping columns split 2026 perfectly and would leak.
def predictors() -> list[str]:
    with CHAR_LIST.open() as fh:
        return [row["variable"] for row in csv.DictReader(fh)]


# Loads the panel and attaches the holding month, which is what every split keys on.
def load() -> pd.DataFrame:
    cols = predictors() + ["permno", "eom", "prc", "me", TARGET]
    panel = pq.read_table(CHARS, columns=sorted(set(cols))).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    # eom is when we decide, the target lands the month after.
    # Carrying both is the one thing most likely to go wrong without anyone noticing.
    panel["holding_month"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    keep = (panel["prc"].abs() >= MIN_PRICE) & (panel["me"] >= MIN_ME)
    return panel[keep].copy()


# Ranks each predictor into [-1, 1] within its own month, as the rules' teaching script does.
# Gaps are filled with that month's median first.
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
        # Work backwards from the calendar test year so the test block is Jan to Dec, then
        # the two validation years, then everything before that is training.
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


# The models fit the rank of the target, not the return itself.
# Raw returns let a handful of 300% months own the loss, and ranks measured far better.
def rank_target(frame: pd.DataFrame) -> np.ndarray:
    r = frame.groupby("holding_month")[TARGET].rank(pct=True)
    return (r - 0.5).to_numpy()


# Drops rows with no target, for training and validation only.
# The test month is scored in full, because filtering it there is survivorship.
def labelled(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame[TARGET].notna()]


# What the cached folds depend on. Any change here has to invalidate them.
def fingerprint() -> str:
    import hashlib

    parts = [
        CHARS.stat().st_size,
        CHAR_LIST.read_bytes(),
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


# Builds the folds once and caches them, so the four model scripts all read the same splits.
def build(refresh: bool = False) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    marker = CACHE / "folds.parquet"
    stamp = CACHE / "fingerprint.txt"
    # Rebuild if the panel, predictors, screen or schedule change.
    # A stale cache after a date change is how wrong model numbers get shipped.
    current = fingerprint()
    if marker.exists() and not refresh and stamp.exists() and stamp.read_text() == current:
        return marker
    cols = predictors()
    df = rank_transform(load(), cols)
    df[["permno", "eom", "holding_month", TARGET] + cols].to_parquet(marker, index=False)
    stamp.write_text(current)
    return marker


# Stops a run whose predictions miss the months the book holds.
# A silent 69th month is how the model tables and the portfolio end up disagreeing.
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
    cols = predictors()
    print(f"panel {len(df):,} rows, {len(cols)} predictors")
    for f in folds(df):
        print(
            f"  test {f['test_year']}: "
            f"train {len(f['train']):>7,}  val {len(f['validate']):>6,}  test {len(f['test']):>6,}"
        )
