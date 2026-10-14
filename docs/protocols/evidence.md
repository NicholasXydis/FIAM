# Evidence: is the edge real, and what does v2 change?

All tests run on monthly net excess returns over the T-bill (and over T-bill + 4% where stated),
for v1 and v2, pre-2021 and reported windows. Nothing here chooses a model; it only reports.

1. **Deflated Sharpe ratio** (Bailey and Lopez de Prado 2014) at the full trial count (1,665 past
   fits + `research/exp` + Andrew's runs + every ledger row) and at the effective count (trials
   grouped where their monthly returns correlate above 0.9; trials without a saved return series
   count as distinct). Reported as the probability the edge is real.
2. **v2 minus v1:** stationary bootstrap (Politis and Romano 1994) of the monthly difference,
   10,000 draws, seed 42, block length by Politis and White (2004) computed on the series itself.
   Reported: mean difference with 90% and 95% intervals, for net return, cost and beta.
3. **Alpha t-statistic** on FF5 + UMD with Newey-West lags 3, 6 and 11 and the equal-weighted
   cosine estimator (Lazarus, Lewis, Stock and Watson 2018). Compared with the t > 3 hurdle
   (Harvey, Liu and Zhu 2016).
4. **Break-even IC:** pooled 2016-2026 regression of monthly gross return on that month's residual
   IC and the market return, gross = a + b x IC + c x mkt; IC* = (cost + hurdle - a)/b, for v1 and
   v2. Reported with the realized IC beside it; v2 lowers the bar if its IC* is lower.
5. **Neutrality:** Patton (2009) tests (correlation, quadrant and tail dependence with the market),
   up and down capture, Henriksson and Merton (1981) timing regression, daily Dimson beta.
6. **Weak periods:** 2016-2020 split into beta drag (realized beta x market) and the rest, with a
   bootstrap interval; 2023-2026 losses split by signal theme.
7. **Regimes:** months classed by month-end VIX against its 2000-2020 75th percentile and by the
   market's sign; cells with fewer than 12 months are hidden.
8. **Costs:** cost waterfall v1 -> v2 by component; our modelled half spread against TAQ effective
   spreads (`trading/spreads_monthly`) by size group, 2016-2024.
9. **Canaries on every new module:** a planted look-ahead feature must be caught by the audit;
   shuffled labels must give IC near zero (|t| < 2); a firm-identity feature must not add IC.
