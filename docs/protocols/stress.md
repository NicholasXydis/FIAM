# Crash tests and liquidity

## Books and data
- Fixed books: the September 2026 v1 and v2 books (built from August 2026 data). Diagnostics only;
  nothing here changes a position.
- Daily data: `daily_market.parquet` (2015-2025) and the USB CRSP daily file (2000-2025, read-only)
  for earlier episodes; FF5 + UMD daily factors from `layers/market/factors_daily`.
- Source note (2026-10-22): CRSP daily and the factors now come from our read-only extracts in
  `data/v4/extracts/`, from the same WRDS files; a rerun matched 2026-10-15 to 4e-16, same method.

## 1. Seventeen crises (chosen from market events, not from our book's returns)
| # | Episode | Dates |
|---|---|---|
| 1 | Dot-com peak crash | 2000-03-10 to 2000-04-14 |
| 2 | September 11 | 2001-09-10 to 2001-09-21 |
| 3 | Accounting scandals | 2002-07-01 to 2002-07-23 |
| 4 | Quant unwind | 2007-07-24 to 2007-08-10 |
| 5 | Bear Stearns | 2008-03-03 to 2008-03-17 |
| 6 | Lehman and the crash | 2008-09-12 to 2008-10-27 |
| 7 | Junk rally, momentum crash | 2009-03-09 to 2009-05-29 |
| 8 | US downgrade | 2011-07-22 to 2011-08-19 |
| 9 | Taper tantrum | 2013-05-22 to 2013-06-24 |
| 10 | China devaluation | 2015-08-18 to 2015-08-25 |
| 11 | Oil and high-yield sell-off | 2016-01-04 to 2016-02-11 |
| 12 | Volatility spike | 2018-01-26 to 2018-02-08 |
| 13 | Late-2018 sell-off | 2018-10-03 to 2018-12-24 |
| 14 | Covid crash | 2020-02-19 to 2020-03-23 |
| 15 | Vaccine rotation | 2020-11-06 to 2020-11-13 |
| 16 | Rate shock | 2022-01-03 to 2022-06-16 |
| 17 | Yen carry unwind | 2024-07-31 to 2024-08-05 |

Method, in this order: (1) factor proxy: the book's FF5 + UMD loadings, estimated on its
hypothetical daily returns over the last 252 trading days of data, times each episode's
cumulative factor returns; (2) same-name replay: today's weights times each stock's actual
returns in the episode, coverage reported; a stock not trading then takes the median return of
its `ff49` industry and size group that day. Our panel starts 2015, so for earlier episodes the
peers are formed from the USB CRSP file's industry codes and market caps; if they cannot be formed,
only the factor proxy is reported for that episode and the gap is stated.

## 2. Named scenarios
- Oil crash: 2014-06-20 to 2016-02-11, and 2020-03-06 to 2020-04-21.
- Energy shock: 2022-02-24 to 2022-06-08.
- US-China trade war: 2018-03-22 to 2018-04-06, 2018-06-15 to 2018-07-06, 2019-05-03 to
  2019-06-03, 2019-08-01 to 2019-08-23.
Each is run as a replay (as above) and as a conditional factor shock: the two FF5 + UMD factors
that moved most in the episode are set to their episode moves, and the others to their conditional
expectation, E[f_o | f_s] = Sigma_os Sigma_ss^-1 f_s, with Sigma from daily factor returns 2000-2020.

## 3. Reverse stress
The most likely factor move that costs 10% of NAV in a month: f* = -L Sigma b / (b' Sigma b),
L = 0.10, b = the book's FF5 + UMD loadings, Sigma = monthly factor covariance 2000-2020. Reported
with the closest real month 2000-2025 by Mahalanobis distance.

## 4. Liquidity
- Days to liquidate per name: |w| x NAV / (0.10 x `dolvol_126d`). Reported by side: weighted
  mean, maximum, and number of names above 1 day, at each capital level ($1M to $5B).
- One-sided unwind: every name sold or bought back at 10% of its daily dollar volume until flat;
  each day's long dollars, short dollars, net exposure / NAV and book beta. Reported: the largest
  net exposure and beta reached, because liquid shorts clear before illiquid longs.
- 2008 short ban: shorts in GICS 40 (financials) frozen from 2008-09-19 to 2008-10-08 in the
  replay.
- Squeeze: replay of 2021-01-22 to 2021-02-02 for current shorts, and a hypothetical +50% one-day
  jump in the short book's names that are in the top 5% of short interest.
