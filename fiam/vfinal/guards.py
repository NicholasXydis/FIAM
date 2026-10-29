# Fit guards: no shuffled folds, no label reaching a forecast.

import pandas as pd


# A fit's folds must keep time order; shuffled splitters are refused.
def refuse_shuffle(splitter) -> None:
    if getattr(splitter, "shuffle", False):
        raise ValueError(f"{type(splitter).__name__} shuffles; folds must keep time order")


# Every training label must end before the fit's first forecast month.
def assert_time_split(label_ends, first_forecast) -> None:
    ends = pd.to_datetime(pd.Series(label_ends)).dt.to_period("M")
    start = pd.Timestamp(first_forecast).to_period("M")
    late = ends >= start
    if late.any():
        raise AssertionError(f"{int(late.sum())} training labels end on or after {start}")


# A fit used at formation day T holds only labels ended by T (purge).
def assert_label_window(label_ends, formation_day) -> None:
    ends = pd.to_datetime(pd.Series(label_ends))
    late = ends > pd.Timestamp(formation_day)
    if late.any():
        raise AssertionError(f"{int(late.sum())} labels end after {formation_day} (purge)")
