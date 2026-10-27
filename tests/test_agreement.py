# The Newey-West t that the survivorship test and the gates share.

import numpy as np
import pandas as pd

from fiam.vfinal import agreement

SERIES = [0.02, -0.01, 0.03, 0.01, 0.0, 0.04, -0.02, 0.01, 0.02, 0.03, -0.01, 0.05, 0.0, 0.02]


# Bartlett weights 1 - j/7 on autocovariances over n, no n/(n-1) factor.
def hand_nw_t(y: np.ndarray, lags: int = 6) -> float:
    n, e = len(y), y - y.mean()
    gamma = [(e[j:] * e[: n - j]).sum() / n for j in range(lags + 1)]
    long_run = gamma[0] + 2 * sum((1 - j / (lags + 1)) * gamma[j] for j in range(1, lags + 1))
    return float(y.mean() / np.sqrt(long_run / n))


# nw_t is exactly the hand formula the gates' simulated nulls assume.
def test_nw_t_matches_the_hand_formula():
    y = np.array(SERIES)
    assert abs(agreement.nw_t(pd.Series(y)) - hand_nw_t(y)) < 1e-10


# Missing months drop out first; under 12 months gives no t at all.
def test_nw_t_drops_missing_and_needs_twelve_months():
    y = pd.Series([*SERIES[:6], np.nan, *SERIES[6:]])
    assert abs(agreement.nw_t(y) - hand_nw_t(np.array(SERIES))) < 1e-10
    assert np.isnan(agreement.nw_t(pd.Series(SERIES[:11])))
