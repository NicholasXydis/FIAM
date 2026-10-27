# The fund beside the market.

import numpy as np
import pandas as pd

from fiam.vfinal import daily_book
from fiam.vfinal.report import table_9_1

# The blend holds this share in the market, the rest in the fund.
MARKET_SHARE = 0.8
COLUMNS = ["measure", "fund", "sp500_price", "market_total", "blend"]


# Monthly measures of one path against the bill and the whole market.
def measures(r: pd.Series, rf: pd.Series, market: pd.Series) -> list[float]:
    excess, market_excess = r - rf, market - rf
    cagr = float((1 + r).prod() ** (12 / len(r)) - 1)
    beta = float(np.cov(excess, market_excess, ddof=1)[0, 1] / market_excess.var(ddof=1))
    return [cagr * 100, float(r.std(ddof=1) * np.sqrt(12) * 100),
            table_9_1.annual_ratio(excess), table_9_1.drawdown(r) * 100,
            float(r.min() * 100), float(r.corr(market)), beta]  # fmt: skip


# Fund, S&P 500 price index, market with dividends and the 80/20 blend.
def table(daily: pd.DataFrame, sp500: pd.Series, market: pd.Series) -> pd.DataFrame:
    # The first row is the endowment close; no statistic counts it.
    d = daily.iloc[1:].loc[: table_9_1.END]
    sp, mkt = sp500.reindex(d.index), market.reindex(d.index)
    if sp.isna().any() or mkt.isna().any():
        raise ValueError("a market series misses a day of the run")
    m = daily_book.monthly(d)
    sp_m, mkt_m = table_9_1.compound(sp), table_9_1.compound(mkt)
    # The blend is rebalanced to 80/20 at each month end.
    blend = MARKET_SHARE * mkt_m + (1 - MARKET_SHARE) * m["ret"]
    paths = [m["ret"], sp_m, mkt_m, blend]
    cols = [measures(p, m["rf"], mkt_m) for p in paths]
    names = ["Annual return, compounded (%)", "Annual volatility (%)", "Sharpe ratio",
             "Max drawdown, month ends (%)", "Worst month (%)",
             "Correlation with the market", "Beta to the market"]  # fmt: skip
    rows = [[n, *(c[i] for c in cols)] for i, n in enumerate(names)]
    return pd.DataFrame(rows, columns=COLUMNS)
