# Risk: volatility model, risk model, dashboard, budget, warning signs

## 1. Volatility forecast (`fiam/vol.py`)
- Target: each stock's realized volatility in the holding month = standard deviation of daily
  `total_return` (`daily_market.parquet`) x sqrt(21); months with fewer than 15 trading days dropped.
- Model: LightGBM on `teachers.inputs` (the 147 ranked + 8-K counts), trained year by year with
  `teachers.walk_forward` (each test year sees only earlier holding months). Settings fixed as in
  `teachers.py`; no tuning on a test year. Daily data starts 2015, so test years are 2017 onward.
- Benchmark: HAR (Corsi 2009) in logs, adapted to a monthly target: log RV next month on log RV
  over the last 5, 21 and 63 trading days, fitted on the same walk-forward years.
- Score: QLIKE = mean(RV^2/F^2 - log(RV^2/F^2) - 1). Pass: LightGBM's QLIKE below HAR's in at least
  3 of 4 years 2017-2020 and a Diebold-Mariano t below -2 on the 48 monthly cross-sectional mean
  loss differences, 2017-2020 (Newey-West lag 3). If it fails, HAR is used everywhere `vol.py` is
  named, and that is reported.
- After the freeze the model only predicts. New universes use the saved model; missing inputs fall
  back to `rvol_21d` x sqrt(21).

## 2. Risk model (`fiam/risk.py`)
- Factors: 11 GICS sectors (first two digits of `gics`) and five styles, each the month's rank z of
  log `me` (size), `be_me` (value), `ret_12_1` (momentum), `ivol_capm_252d` (low volatility),
  `ope_be` (quality).
- Factor returns: each month, cross-sectional regression of next-month excess returns on the
  exposures, weights sqrt(`me`). Covariance: exponentially weighted, half-life 36 months, fixed,
  built at each decision only from factor returns already realized. The panel starts 2015-01, so
  the model is used from 2017-01 (24 months of factor returns); never before.
- Specific variance: square of the `vol.py` forecast (or HAR if section 1 fails).
- Checks on v1's and v2's monthly books, 2017-2020 and the reported window: bias statistic (std of
  realized/predicted return), pass band 1 +/- sqrt(2/T); 95% and 99% VaR from the predicted
  volatility under a normal, exceptions tested with Kupiec and Christoffersen at 5%.
- Volatility budget (`vol_budget`, off by default): sqrt(12 x w' Sigma w) <= budget, as a convex
  constraint in v2. Used only when a mandate sets it.

## 3. Risk dashboard (`fiam/stats.py`)
Computed the same way for v1, v2 and any switch, both windows, monthly unless stated:
- IR vs T-bill + 4%; Sharpe; Sortino (downside deviation below 0); alpha (FF5 + UMD, HAC t).
- Beta: monthly to the S&P 500 (as in v1's reports) and daily (Dimson, 1 lead and 1 lag).
- Max drawdown from the starting NAV; hit rate (share of positive months).
- VaR and CVaR at 95% and 99% on daily book returns, three ways: historical, Student-t fitted by
  maximum likelihood, and EVT (generalized Pareto above the 90th percentile of losses).
- Gross and net exposure; effective names (1/sum w^2, by side); top-10 share.
- Days to liquidate at 10% of `dolvol_126d`; AI crowding beta (from `crowd.md`).

## 4. Risk warning signs (exhibit only; never applied to v1 or v2)
Signals that would make a manager cut gross by half until cleared. Their history 2016-2026 is
shown; IR is never a trigger.
1. Rolling 126-day daily beta outside +/-0.20 with |t| > 2.
2. Average borrow fee on the short book above twice its 2016-2020 median.
3. Largest days to liquidate above 5 at the book's NAV.
Reported: dates each would have fired and what the book did in the next three months.
