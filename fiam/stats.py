# The past trial count and the drawdown measure the books share.

import numpy as np
import pandas as pd

TRIALS_PAST = 1665


# Largest fall from any prior high, the starting NAV counting as one.
def drawdown(net: pd.Series) -> float:
    growth = (1 + net).cumprod()
    peak = np.maximum(growth.cummax(), 1.0)
    return float((growth / peak - 1).min())
