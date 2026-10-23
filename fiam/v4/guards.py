# Fit guards: no shuffled folds, no label reaching a forecast (B14).

import pandas as pd


# A fit's folds must keep time order; shuffled splitters are refused.
def refuse_shuffle(splitter) -> None:
    if getattr(splitter, "shuffle", False):
        raise ValueError(f"{type(splitter).__name__} shuffles; folds must keep time order (B14)")


# Every training label must end before the fit's first forecast month.
def assert_time_split(label_ends, first_forecast) -> None:
    ends = pd.to_datetime(pd.Series(label_ends)).dt.to_period("M")
    start = pd.Timestamp(first_forecast).to_period("M")
    late = ends >= start
    if late.any():
        raise AssertionError(f"{int(late.sum())} training labels end on or after {start} (B14)")
