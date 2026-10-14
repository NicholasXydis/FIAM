# v2, amendment 1: the IC the cost-aware optimizer reads, and the book made of passing fixes

Written 2026-10-14, after the first v2 runs and before any run it covers. `v2.md` stands; this adds
a switch and a rule. Both are judged on data before 2021 only.

## Why
The `costs` member turns scores into monthly return forecasts with s_t = IC x median residual vol.
`v2.md` fixed IC as one pooled correlation over every stock-month, 2015-2020: 0.0071. The forecast
in Grinold (1994) and Grinold and Kahn (Active Portfolio Management, 1999) uses the cross-sectional
IC: the correlation within each month, averaged over months. Pooling across months mixes in
differences between months that no trade can capture, and here gives an IC about a third of the
cross-sectional one. With alpha understated, the optimizer sees costs as large next to it and
barely trades (turnover 10-12% a month against v1's 46%). The `costs` member failed its own test
on exactly this: its weights correlate only 0.28 with v1's (needs 0.7).

## Switch `grinold` (off by default)
- Identical to `costs` in every way except the IC: the mean over decision months 2015-01..2020-11 of
  the monthly Spearman correlation between the v1 signal and the sector- and beta-neutral next-month
  return (the same residual return `costs` uses). Fitted once, frozen in `frozen/v2_params.json` as
  `ic_monthly`.
- `grinold` and `costs` are never on together.

## Test (holding months 2016-01..2020-12, the `costs` test unchanged)
Pass if, at every capital level ($1M to $5B): annual cost below v1's, mean monthly turnover below
v1's, and the mean monthly correlation of its weights with v1's at least 0.7.

## v2a
v2 with `grinold` in place of `costs` (`grinold`, `persistence`, `beta`, `shorts`, `liquidity`).
Reported beside v2 and v1 at every capital level in both windows. No pass or fail.

## v2-pass
The fixes that passed their own pre-2021 test in `v2.md` or here, together. Today that is
`shorts`; `grinold` joins if it passes. Reported at every capital level in both windows, with the
stationary bootstrap of its monthly net difference from v1 and its deflated Sharpe.
Disclosed: this rule was written after the five members' 2021-2026 results had been seen. It uses
only their pre-2021 verdicts.

## Reported whatever happens
The `grinold` verdict and its three numbers; v2a and v2-pass beside v1 and v2: IR, cost, turnover,
realized beta, days to liquidate, in both windows and every capital level. Every run is a trial.
