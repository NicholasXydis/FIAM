# Borrow a year by short-interest tier: the headline schedule (Final case §7
# allows a schedule calibrated today; the flat 0.5%/5% is reported beside it).
#
# Same schedule and data as v4 (fiam/costs.py, copied so v4b reads no code
# outside its folder): D'Avolio (2002) and Drechsler & Drechsler (2016) find
# most names on general collateral and fees rising with short interest;
# 0.30% up to 5% of shares short, 1% to 10%, 3% to 20%, 8% beyond; a name
# with no report pays the cheapest tier. Short interest is the WRDS research
# layer (outside the competition pack, disclosed), used a month late, as it is
# published. A borrow rate enters construction and costs only, never mu.
# Lesson 83: the flat 5% on every short below $10bn priced the shortable
# bottom decile out of the book.

from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

DIR = Path(__file__).resolve().parents[3] / "data" / "fiam_v1"
SHORT = DIR / "short_interest_monthly_research_only.parquet"
FEATURES = DIR / "features_monthly.parquet"
TIERS = ((0.05, 0.0030), (0.10, 0.0100), (0.20, 0.0300), (np.inf, 0.0800))


# Short interest over shares outstanding, dated by the month it is first known.
@cache
def short_ratio() -> pd.Series:
    s = pd.read_parquet(SHORT, columns=["permno", "eom", "short_interest_adjusted"])
    sh = pd.read_parquet(FEATURES, columns=["permno", "eom", "shares"])
    both = s.merge(sh, on=["permno", "eom"]).dropna()
    both["ratio"] = both["short_interest_adjusted"] / (both["shares"] * 1e6)
    both["eom"] = (pd.to_datetime(both["eom"]) + pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    return both.set_index(["eom", "permno"])["ratio"]


def tier(ratio: pd.Series) -> pd.Series:
    bounds, rates = zip(*TIERS)
    at = np.searchsorted(bounds, ratio.fillna(0.0).to_numpy(), side="right")
    return pd.Series(np.array(rates)[at], index=ratio.index)


# Annual borrow for each permno at formation eom.
def rates(eom, permnos: pd.Index) -> pd.Series:
    key = pd.MultiIndex.from_arrays([np.full(len(permnos), pd.Timestamp(eom)), permnos])
    return pd.Series(tier(pd.Series(short_ratio().reindex(key).to_numpy())).to_numpy(), index=permnos)
