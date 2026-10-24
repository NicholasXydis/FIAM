# The B23 vintage check's age shares and lag L on small inputs.

import pandas as pd

from fiam.v4 import vintage


# Values change only when young: the share by minimum age and L follow.
def test_by_age_and_smallest_age():
    days = pd.date_range("2020-01-01", periods=10)
    both = pd.DataFrame(
        {"X_old": [1.0] * 10, "X_new": [1.0] * 7 + [1.5] * 3, "age": list(range(9, -1, -1))},
        index=days,
    )
    shares = vintage.by_age(both, ["X"])
    assert shares.loc[3, "X"] == 1.0 and shares.loc[0, "X"] == 0.7
    assert vintage.smallest_age(shares["X"] >= 0.99) == 3


# A bar that fails at old ages too gives no lag, so the control is off.
def test_no_lag_when_old_values_fail():
    holds = pd.Series([True, True, False, True], index=[0, 1, 2, 3])
    assert vintage.smallest_age(holds) == 3
    assert vintage.smallest_age(pd.Series([False, False], index=[0, 1])) is None


# Storm counts compare by county and month, missing counted as zero.
def test_compare_counts_missing_as_zero():
    idx = pd.MultiIndex.from_tuples(
        [(1, 1, pd.Period("2019-01", "M")), (1, 2, pd.Period("2019-02", "M"))]
    )
    old = pd.Series([2, 1], index=idx)
    new = pd.Series([2], index=idx[:1])
    out = vintage.compare(old, new, "20200115000000", lambda a, b: a.fillna(0) == b.fillna(0))
    assert out["ok"].tolist() == [True, False]
    assert out["age"].tolist() == [12, 11]
