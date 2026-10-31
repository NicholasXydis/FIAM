# Position explanations

Written by the team's explainer agent (fiam/agents/explainer.py, Gemma 4 26B, temperature 0, seed 42) from the facts table under each answer. Every number in an answer was checked against its facts table by the explainer's number check (fiam/agents/explainer.py `supported`). Retrospective, names visible. No AI set or changed any weight.

P&L is daily dollar positions (previous close) times daily stock returns from out/vfinal/cache/market_ret.parquet, 2021-01-04 to 2026-08-31, before costs and borrow. The engine's own ledger figure is shown beside it as a cross-check. Forecast z is the el_plus E-LASSO MaInf score, z-scored across all stocks that month and multiplied by rho. A driver's number is its contribution to that z (coefficient times the stock's demeaned characteristic, divided by the month's forecast spread).

## Top-10 long in the 2026-08-31 book

### 1. IBKR Interactive Brokers Group Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by low Market Beta, a low Kaplan-Zingales index, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the positive forecast, which pointed the same way as the trade. The position earned $44.92 million as the stock returned 553.7% while held, and it had a weight of 4.019% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $44.92m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $44.92m (long days $44.92m, short days $0.0m) |
| P&L by year | 2021 $0.37m, 2022 $0.25m, 2023 $1.1m, 2024 $11.03m, 2025 $12.88m, 2026 $19.28m |
| Engine ledger price P&L (cross-check) | $44.57m |
| Dividends, trading cost, borrow | $0.35m, $-0.1m, $0.0m |
| Average weight while held | 1.222% |
| Largest absolute weight | 4.071% |
| Weight on 2026-08-31 | 4.019% |
| Stock return while held | 553.7% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.86, percentile 98 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Beta (stock z -0.68, model rewards lower, +0.40)<br>Kaplan-Zingales index (stock z -7.42, model rewards lower, +0.39)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.76, model rewards lower, +0.31)<br>Free cash flow-to-price (stock z 4.57, model rewards higher, +0.31)<br>Book leverage (stock z 6.93, model rewards lower, -0.55)<br>Change in current operating liabilities (stock z 3.2, model rewards lower, -0.42)<br>Liquidity of market assets (stock z 3.04, model rewards lower, -0.41)<br>Change in net financial assets (stock z 0.94, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z 1.34, percentile 94, agrees with trade True |
| Drivers at 2026-07-31 | Operating cash flow-to-market (stock z 2.55, model rewards higher, +0.35)<br>Free cash flow-to-price (stock z 2.77, model rewards higher, +0.31)<br>Capital turnover (stock z -1.06, model rewards lower, +0.20)<br>Kaplan-Zingales index (stock z -7.26, model rewards lower, +0.20)<br>Operating leverage (stock z -1.09, model rewards higher, -0.23)<br>Market Beta (stock z 0.42, model rewards lower, -0.14)<br>Long-term reversal (stock z 2.89, model rewards lower, -0.13)<br>Operating profits-to-book assets (stock z -0.5, model rewards higher, -0.10) |

### 2. EXPD Expeditors International Wa Inc (LONG)

> The portfolio entered a long position on 2023-07-03 because the forecast was high, driven by high Operating leverage, high Operating profits-to-book assets, and high Mispricing factor: Performance. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $25.06 million as the stock returned 60.6% while held, and it had a weight of 3.895% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2023-07-03 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $25.06m |
| All spells | 1 spells, 794 trading days, first 2023-07-03, last 2026-08-31 |
| Total P&L 2021-2026 | $25.06m (long days $25.06m, short days $0.0m) |
| P&L by year | 2023 $2.14m, 2024 $-3.85m, 2025 $13.78m, 2026 $12.99m |
| Engine ledger price P&L (cross-check) | $23.98m |
| Dividends, trading cost, borrow | $1.08m, $-0.1m, $0.0m |
| Average weight while held | 2.625% |
| Largest absolute weight | 3.989% |
| Weight on 2026-08-31 | 3.895% |
| Stock return while held | 60.6% |
| Entry decision | 2023-06-30 (month-end), drivers from the 2023-06-30 refit |
| Forecast at entry | z 3.52, percentile 100 of 2165, rho 1.5, agrees with trade True |
| Drivers at entry | Operating leverage (stock z 3.21, model rewards higher, +1.12)<br>Operating profits-to-book assets (stock z 1.6, model rewards higher, +0.74)<br>Mispricing factor: Performance (stock z 1.5, model rewards higher, +0.39)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.89, model rewards lower, +0.32)<br>Capital turnover (stock z 2.47, model rewards lower, -0.81)<br>Cash-based operating profits-to-book assets (stock z 2.44, model rewards lower, -0.50)<br>Return volatility (stock z -0.98, model rewards higher, -0.28)<br>Equity net payout (stock z 1.04, model rewards lower, -0.23) |
| Forecast at 2026-07-31 refit | z 0.66, percentile 69, agrees with trade True |
| Drivers at 2026-07-31 | Operating leverage (stock z 2.75, model rewards higher, +0.57)<br>Operating profits-to-book assets (stock z 1.01, model rewards higher, +0.19)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.83, model rewards lower, +0.17)<br>Mispricing factor: Performance (stock z 1.55, model rewards higher, +0.12)<br>Capital turnover (stock z 2.76, model rewards lower, -0.53)<br>Return volatility (stock z -0.86, model rewards higher, -0.12)<br>Operating profits-to-lagged book assets (stock z 0.71, model rewards lower, -0.09)<br>SYY-10 mispricing score (stock z 1.97, model rewards lower, -0.08) |

### 3. COST Costco Wholesale Corp New (LONG)

> The long position was entered on 2021-12-01 because the forecast was high, driven by high Operating leverage, high Market Equity, and low Market Beta. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $32.07 million while the stock returned 86.8%, and it had a weight of 3.825% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-12-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $32.07m |
| All spells | 1 spells, 1191 trading days, first 2021-12-01, last 2026-08-31 |
| Total P&L 2021-2026 | $32.07m (long days $32.07m, short days $0.0m) |
| P&L by year | 2021 $0.24m, 2022 $-2.12m, 2023 $12.49m, 2024 $17.47m, 2025 $-1.73m, 2026 $5.72m |
| Engine ledger price P&L (cross-check) | $30.22m |
| Dividends, trading cost, borrow | $1.86m, $-0.08m, $0.0m |
| Average weight while held | 2.792% |
| Largest absolute weight | 4.294% |
| Weight on 2026-08-31 | 3.825% |
| Stock return while held | 86.8% |
| Entry decision | 2021-11-30 (month-end), drivers from the 2021-11-30 refit |
| Forecast at entry | z 3.07, percentile 100 of 2554, rho 1.32, agrees with trade True |
| Drivers at entry | Operating leverage (stock z 4.2, model rewards higher, +1.04)<br>Market Equity (stock z 6.36, model rewards higher, +0.66)<br>Market Beta (stock z -1.09, model rewards lower, +0.58)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -1.04, model rewards lower, +0.37)<br>Capital turnover (stock z 3.98, model rewards lower, -0.86)<br>Dollar trading volume (stock z 3.39, model rewards lower, -0.32)<br>Return volatility (stock z -0.98, model rewards higher, -0.20)<br>Maximum daily return (stock z -0.65, model rewards higher, -0.11) |
| Forecast at 2026-07-31 refit | z 0.58, percentile 66, agrees with trade True |
| Drivers at 2026-07-31 | Operating leverage (stock z 4.24, model rewards higher, +0.89)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.96, model rewards lower, +0.19)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -1.0, model rewards lower, +0.17)<br>Capital turnover (stock z 3.96, model rewards lower, -0.75)<br>Dollar trading volume (stock z 4.16, model rewards lower, -0.28)<br>Return volatility (stock z -0.88, model rewards higher, -0.13)<br>Idiosyncratic volatility from the q-factor model (stock z -0.92, model rewards higher, -0.10) |

### 4. MET Metlife Inc (LONG)

> The long position was entered on 2021-01-04 because the forecast was high, driven by low Idiosyncratic volatility from the Fama-French 3-factor model, high Ebitda-to-market enterprise value, and low Asset tangibility. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $21.79 million while the stock returned 140.7%, and it held a weight of 3.781% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $21.79m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $21.79m (long days $21.79m, short days $0.0m) |
| P&L by year | 2021 $2.17m, 2022 $2.85m, 2023 $-0.65m, 2024 $7.38m, 2025 $0.09m, 2026 $9.95m |
| Engine ledger price P&L (cross-check) | $18.37m |
| Dividends, trading cost, borrow | $3.42m, $-0.09m, $0.0m |
| Average weight while held | 2.046% |
| Largest absolute weight | 3.994% |
| Weight on 2026-08-31 | 3.781% |
| Stock return while held | 140.7% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.0, percentile 83 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.87, model rewards lower, +0.41)<br>Ebitda-to-market enterprise value (stock z 3.38, model rewards higher, +0.40)<br>Asset tangibility (stock z -1.7, model rewards lower, +0.31)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.74, model rewards lower, +0.30)<br>Equity duration (stock z -2.54, model rewards higher, -0.57)<br>Operating profits-to-book assets (stock z -0.48, model rewards higher, -0.19)<br>Return volatility (stock z -0.74, model rewards higher, -0.16)<br>Liquidity of market assets (stock z 1.11, model rewards lower, -0.15) |
| Forecast at 2026-07-31 refit | z 1.47, percentile 96, agrees with trade True |
| Drivers at 2026-07-31 | Idiosyncratic volatility from the CAPM (21 days) (stock z -0.99, model rewards lower, +0.20)<br>Operating cash flow-to-market (stock z 1.4, model rewards higher, +0.19)<br>Free cash flow-to-price (stock z 1.68, model rewards higher, +0.19)<br>Capital turnover (stock z -0.97, model rewards lower, +0.18)<br>Operating leverage (stock z -0.96, model rewards higher, -0.20)<br>Return volatility (stock z -1.0, model rewards higher, -0.15)<br>Operating profits-to-book assets (stock z -0.74, model rewards higher, -0.14)<br>Idiosyncratic volatility from the q-factor model (stock z -1.04, model rewards higher, -0.11) |

### 5. PRU Prudential Financial Inc (LONG)

> The long position was entered on 2021-01-04 because the forecast was high, driven by low Percent operating accruals, low Idiosyncratic volatility from the Fama-French 3-factor model, and high Ebitda-to-market enterprise value. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $17.71 million while the stock returned 95.9%, and it had a weight of 3.679% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $17.71m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $17.71m (long days $17.71m, short days $0.0m) |
| P&L by year | 2021 $6.91m, 2022 $-0.8m, 2023 $2.14m, 2024 $5.55m, 2025 $2.07m, 2026 $1.84m |
| Engine ledger price P&L (cross-check) | $10.49m |
| Dividends, trading cost, borrow | $7.22m, $-0.15m, $0.0m |
| Average weight while held | 2.592% |
| Largest absolute weight | 3.951% |
| Weight on 2026-08-31 | 3.679% |
| Stock return while held | 95.9% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 0.83, percentile 78 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Percent operating accruals (stock z -7.47, model rewards lower, +0.78)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.94, model rewards lower, +0.44)<br>Ebitda-to-market enterprise value (stock z 3.38, model rewards higher, +0.40)<br>Free cash flow-to-price (stock z 4.05, model rewards higher, +0.27)<br>Equity duration (stock z -2.34, model rewards higher, -0.52)<br>Percent total accruals (stock z -7.03, model rewards higher, -0.33)<br>Residual momentum t-12 to t-1 (stock z 1.62, model rewards lower, -0.26)<br>Market Beta (stock z 0.44, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z 2.01, percentile 99, agrees with trade True |
| Drivers at 2026-07-31 | Ebitda-to-market enterprise value (stock z 2.18, model rewards higher, +0.54)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -1.01, model rewards lower, +0.20)<br>Capital turnover (stock z -1.01, model rewards lower, +0.19)<br>Operating cash flow-to-market (stock z 1.25, model rewards higher, +0.17)<br>Operating leverage (stock z -1.0, model rewards higher, -0.21)<br>Return volatility (stock z -1.01, model rewards higher, -0.15)<br>Operating profits-to-book assets (stock z -0.74, model rewards higher, -0.14)<br>Idiosyncratic volatility from the q-factor model (stock z -1.14, model rewards higher, -0.12) |

### 6. LRCX Lam Resh Corp (LONG)

> The long position was entered on 2024-05-16 because the forecast was high, driven by high Operating profits-to-book assets, high Mispricing factor: Performance, and high Market Equity. The strategy believed in the forecast at entry, though by the latest month-end refit the forecast did not point the same way as the trade. The position earned $35.09 million while the stock returned 225.2%, and it held a weight of 3.582% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2024-05-16 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $35.09m |
| All spells | 1 spells, 574 trading days, first 2024-05-16, last 2026-08-31 |
| Total P&L 2021-2026 | $35.09m (long days $35.09m, short days $0.0m) |
| P&L by year | 2024 $-1.52m, 2025 $18.22m, 2026 $18.38m |
| Engine ledger price P&L (cross-check) | $34.85m |
| Dividends, trading cost, borrow | $0.23m, $-0.07m, $0.0m |
| Average weight while held | 1.535% |
| Largest absolute weight | 4.533% |
| Weight on 2026-08-31 | 3.582% |
| Stock return while held | 225.2% |
| Entry decision | 2024-05-15 (mid-month review), drivers from the 2024-04-30 refit |
| Forecast at entry | z 1.9, percentile 95 of 2109, rho 1.5, agrees with trade True, mid-month z 2.2 |
| Drivers at entry | Operating profits-to-book assets (stock z 1.94, model rewards higher, +0.72)<br>Mispricing factor: Performance (stock z 1.78, model rewards higher, +0.44)<br>Market Equity (stock z 2.3, model rewards higher, +0.35)<br>Years 2-5 lagged returns, nonannual (stock z 0.89, model rewards higher, +0.22)<br>Dollar trading volume (stock z 3.0, model rewards lower, -0.43)<br>Operating profits-to-lagged book assets (stock z 1.57, model rewards lower, -0.33)<br>Cash-based operating profits-to-book assets (stock z 1.75, model rewards lower, -0.27)<br>Market Beta (stock z 0.45, model rewards lower, -0.25) |
| Forecast at 2026-07-31 refit | z -0.03, percentile 36, agrees with trade False |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 2.77, model rewards higher, +0.53)<br>Market Equity (stock z 5.89, model rewards higher, +0.39)<br>Price momentum t-12 to t-1 (stock z 3.15, model rewards higher, +0.28)<br>Return volatility (stock z 1.87, model rewards higher, +0.27)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Market Beta (stock z 1.12, model rewards lower, -0.38)<br>Operating profits-to-lagged book assets (stock z 2.28, model rewards lower, -0.29)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 1.3, model rewards lower, -0.26) |

### 7. AVGO Broadcom Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by high Market Equity, high Operating profits-to-book assets, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the positive forecast at entry, though by the 2026-07-31 refit the forecast did not point the same way as the position held. The position earned $92.44 million while the stock returned 867.9%, and it had a weight of 2.772% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $92.44m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $92.44m (long days $92.44m, short days $0.0m) |
| P&L by year | 2021 $10.26m, 2022 $-4.29m, 2023 $23.41m, 2024 $33.73m, 2025 $25.05m, 2026 $4.28m |
| Engine ledger price P&L (cross-check) | $89.18m |
| Dividends, trading cost, borrow | $3.26m, $-0.12m, $0.0m |
| Average weight while held | 2.844% |
| Largest absolute weight | 4.553% |
| Weight on 2026-08-31 | 2.772% |
| Stock return while held | 867.9% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.28, percentile 91 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Equity (stock z 4.83, model rewards higher, +0.52)<br>Operating profits-to-book assets (stock z 1.06, model rewards higher, +0.42)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.94, model rewards lower, +0.38)<br>Asset tangibility (stock z -1.67, model rewards lower, +0.31)<br>Cash-based operating profits-to-book assets (stock z 1.16, model rewards lower, -0.33)<br>Liquidity of book assets (stock z -0.88, model rewards higher, -0.32)<br>Dollar trading volume (stock z 2.7, model rewards lower, -0.24)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.16, model rewards lower, -0.14) |
| Forecast at 2026-07-31 refit | z -0.3, percentile 28, agrees with trade False |
| Drivers at 2026-07-31 | Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Operating profits-to-book assets (stock z 1.49, model rewards higher, +0.29)<br>Years 2-5 lagged returns, nonannual (stock z 2.16, model rewards higher, +0.18)<br>Mispricing factor: Performance (stock z 1.44, model rewards higher, +0.12)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Long-term reversal (stock z 4.86, model rewards lower, -0.23)<br>Operating leverage (stock z -0.79, model rewards higher, -0.17)<br>Operating profits-to-lagged book assets (stock z 1.2, model rewards lower, -0.16) |

### 8. ABNB Airbnb Inc (LONG)

> The long position was entered on 2022-11-01 because the forecast was high, driven by high Liquidity of book assets, low Equity net payout, and high Share turnover. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $12.66 million while the stock returned 68.0%, and it had a weight of 2.583% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2022-11-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $12.66m |
| All spells | 2 spells, 1100 trading days, first 2021-11-01, last 2026-08-31 |
| Total P&L 2021-2026 | $13.39m (long days $12.66m, short days $0.73m) |
| P&L by year | 2021 $0.2m, 2022 $0.17m, 2023 $2.84m, 2024 $-1.45m, 2025 $1.45m, 2026 $10.18m |
| Engine ledger price P&L (cross-check) | $13.39m |
| Dividends, trading cost, borrow | $0.0m, $-0.05m, $-0.0m |
| Average weight while held | 1.226% |
| Largest absolute weight | 2.698% |
| Weight on 2026-08-31 | 2.583% |
| Stock return while held | 9.0% |
| Entry decision | 2022-10-31 (month-end), drivers from the 2022-10-31 refit |
| Forecast at entry | z 0.21, percentile 53 of 2187, rho 1.32, agrees with trade True |
| Drivers at entry | Liquidity of book assets (stock z 0.92, model rewards higher, +0.33)<br>Equity net payout (stock z -0.77, model rewards lower, +0.20)<br>Share turnover (stock z 0.78, model rewards higher, +0.18)<br>Quality minus Junk: Profitability (stock z 1.28, model rewards higher, +0.16)<br>Dollar trading volume (stock z 3.31, model rewards lower, -0.43)<br>Change in operating cash flow to assets (stock z 4.1, model rewards lower, -0.20)<br>Number of zero trades with turnover as tiebreaker (6 months) (stock z -1.2, model rewards higher, -0.17)<br>Cash-based operating profits-to-book assets (stock z 0.66, model rewards lower, -0.13) |
| Forecast at 2026-07-31 refit | z 0.49, percentile 61, agrees with trade True |
| Drivers at 2026-07-31 | Idiosyncratic volatility from the CAPM (252 days) (stock z -0.76, model rewards lower, +0.13)<br>Operating profits-to-book assets (stock z 0.64, model rewards higher, +0.12)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.52, model rewards lower, +0.11)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.68, model rewards lower, +0.09)<br>Idiosyncratic volatility from the q-factor model (stock z -0.88, model rewards higher, -0.10)<br>Operating leverage (stock z -0.45, model rewards higher, -0.09)<br>Return volatility (stock z -0.57, model rewards higher, -0.08)<br>SYY-10 mispricing score (stock z 1.7, model rewards lower, -0.07) |

### 9. ABBV Abbvie Inc (LONG)

> The portfolio entered a long position in ABBV because the forecast was high, driven by high Market Equity, high Change in net operating assets, and low Change in net financial assets. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $22.41 million as the stock returned 195.9% while held, and it had a weight of 2.564% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $22.41m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $22.41m (long days $22.41m, short days $0.0m) |
| P&L by year | 2021 $4.43m, 2022 $4.8m, 2023 $-0.38m, 2024 $2.3m, 2025 $6.7m, 2026 $4.55m |
| Engine ledger price P&L (cross-check) | $18.99m |
| Dividends, trading cost, borrow | $3.42m, $-0.04m, $0.0m |
| Average weight while held | 1.665% |
| Largest absolute weight | 2.854% |
| Weight on 2026-08-31 | 2.564% |
| Stock return while held | 195.9% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.94, percentile 99 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Equity (stock z 5.16, model rewards higher, +0.55)<br>Change in net operating assets (stock z 4.72, model rewards higher, +0.46)<br>Change in net financial assets (stock z -1.64, model rewards lower, +0.45)<br>Market Beta (stock z -0.77, model rewards lower, +0.45)<br>Change in net noncurrent operating assets (stock z 3.63, model rewards lower, -0.31)<br>Operating profits-to-lagged book assets (stock z 1.95, model rewards lower, -0.31)<br>Dollar trading volume (stock z 3.08, model rewards lower, -0.27)<br>Change in financial liabilities (stock z 2.05, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z 1.1, percentile 89, agrees with trade True |
| Drivers at 2026-07-31 | Market Beta (stock z -1.34, model rewards lower, +0.45)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Operating profits-to-book assets (stock z 1.75, model rewards higher, +0.34)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.79, model rewards lower, +0.16)<br>Dollar trading volume (stock z 2.97, model rewards lower, -0.20)<br>Operating profits-to-lagged book assets (stock z 1.22, model rewards lower, -0.16)<br>Operating leverage (stock z -0.67, model rewards higher, -0.14)<br>Return volatility (stock z -0.76, model rewards higher, -0.11) |

### 10. PM Philip Morris International Inc (LONG)

> The long position was entered on 2021-01-04 because the forecast was high, driven by high Operating profits-to-book assets, low Market Beta, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the forecast, which pointed the same way as the trade. The position earned $20.54 million while the stock returned 193.1%, and it had a weight of 2.352% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $20.54m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $20.54m (long days $20.54m, short days $0.0m) |
| P&L by year | 2021 $0.27m, 2022 $0.46m, 2023 $0.12m, 2024 $3.46m, 2025 $11.03m, 2026 $5.2m |
| Engine ledger price P&L (cross-check) | $17.88m |
| Dividends, trading cost, borrow | $2.65m, $-0.04m, $0.0m |
| Average weight while held | 1.077% |
| Largest absolute weight | 2.608% |
| Weight on 2026-08-31 | 2.352% |
| Stock return while held | 193.1% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.65, percentile 97 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Operating profits-to-book assets (stock z 1.84, model rewards higher, +0.74)<br>Market Beta (stock z -0.95, model rewards lower, +0.56)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -1.02, model rewards lower, +0.42)<br>Market Equity (stock z 3.39, model rewards higher, +0.36)<br>Cash-based operating profits-to-book assets (stock z 1.44, model rewards lower, -0.42)<br>Years 2-5 lagged returns, nonannual (stock z -0.79, model rewards higher, -0.33)<br>SYY-10 mispricing score (stock z 1.57, model rewards lower, -0.23)<br>Operating profits-to-lagged book assets (stock z 1.19, model rewards lower, -0.19) |
| Forecast at 2026-07-31 refit | z 0.86, percentile 79, agrees with trade True |
| Drivers at 2026-07-31 | Market Beta (stock z -1.21, model rewards lower, +0.41)<br>Market Equity (stock z 4.72, model rewards higher, +0.31)<br>Operating profits-to-book assets (stock z 1.25, model rewards higher, +0.24)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.73, model rewards lower, +0.12)<br>Operating profits-to-lagged book assets (stock z 0.87, model rewards lower, -0.11)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.87, model rewards lower, -0.11)<br>Dollar trading volume (stock z 1.53, model rewards lower, -0.10)<br>Operating leverage (stock z -0.48, model rewards higher, -0.10) |

## Top-10 short in the 2026-08-31 book

### 1. SNPS Synopsys Inc (SHORT)

> The portfolio entered a short position on 2026-02-18 because the forecast was low, driven by high Dollar trading volume, low Operating leverage, and high Asset Growth. The forecast pointed the same way as the trade. The position earned $0.07 million while the stock returned -0.6%, and it had a weight of -1.155% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2026-02-18 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $0.07m |
| All spells | 1 spells, 135 trading days, first 2026-02-18, last 2026-08-31 |
| Total P&L 2021-2026 | $0.07m (long days $0.0m, short days $0.07m) |
| P&L by year | 2026 $0.07m |
| Engine ledger price P&L (cross-check) | $0.07m |
| Dividends, trading cost, borrow | $0.0m, $-0.02m, $-0.02m |
| Average weight while held | -0.759% |
| Largest absolute weight | 1.224% |
| Weight on 2026-08-31 | -1.155% |
| Stock return while held | -0.6% |
| Entry decision | 2026-02-17 (mid-month review), drivers from the 2026-01-31 refit |
| Forecast at entry | z -0.56, percentile 18 of 2227, rho 0.8, agrees with trade True, mid-month z -0.61 |
| Drivers at entry | Change in long-term net operating assets (stock z 5.41, model rewards higher, +0.37)<br>Capital turnover (stock z -0.77, model rewards lower, +0.33)<br>Change in net financial assets (stock z -1.93, model rewards lower, +0.20)<br>Market Equity (stock z 1.3, model rewards higher, +0.19)<br>Dollar trading volume (stock z 2.47, model rewards lower, -0.45)<br>Operating leverage (stock z -0.91, model rewards higher, -0.42)<br>Asset Growth (stock z 4.95, model rewards lower, -0.36)<br>Operating profits-to-lagged book assets (stock z 1.22, model rewards lower, -0.30) |
| Forecast at 2026-07-31 refit | z -0.67, percentile 20, agrees with trade True |
| Drivers at 2026-07-31 | Change in long-term net operating assets (stock z 4.96, model rewards higher, +0.18)<br>Capital turnover (stock z -0.74, model rewards lower, +0.14)<br>Asset tangibility (stock z -1.91, model rewards lower, +0.08)<br>Frazzini-Pedersen market beta (stock z 1.76, model rewards higher, +0.08)<br>Operating leverage (stock z -0.89, model rewards higher, -0.18)<br>Change in net noncurrent operating assets (stock z 4.07, model rewards lower, -0.18)<br>Liquidity of book assets (stock z -0.68, model rewards higher, -0.11)<br>Dollar trading volume (stock z 1.56, model rewards lower, -0.10) |

### 2. SPGI S & P Global Inc (SHORT)

> The portfolio entered a short position on 2022-06-01 because high Asset Growth, high Dollar trading volume, and high Change in common equity lowered the forecast. The forecast did not point the same way as the trade, but the optimiser held the position for the book's limits or risk. The position lost $5.47 million while the stock returned 35.2%, and it had a weight of -1.108% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2022-06-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-5.47m |
| All spells | 1 spells, 1066 trading days, first 2022-06-01, last 2026-08-31 |
| Total P&L 2021-2026 | $-5.47m (long days $0.0m, short days $-5.47m) |
| P&L by year | 2022 $-0.7m, 2023 $-3.93m, 2024 $-1.91m, 2025 $-1.24m, 2026 $2.32m |
| Engine ledger price P&L (cross-check) | $-5.09m |
| Dividends, trading cost, borrow | $-0.37m, $-0.03m, $-0.16m |
| Average weight while held | -0.967% |
| Largest absolute weight | 1.217% |
| Weight on 2026-08-31 | -1.108% |
| Stock return while held | 35.2% |
| Entry decision | 2022-05-31 (month-end), drivers from the 2022-05-31 refit |
| Forecast at entry | z 0.42, percentile 58 of 2315, rho 1.34, agrees with trade False |
| Drivers at entry | Change in net operating assets (stock z 6.13, model rewards higher, +0.37)<br>Change in long-term net operating assets (stock z 5.15, model rewards higher, +0.34)<br>Market Equity (stock z 3.13, model rewards higher, +0.33)<br>Equity net payout (stock z -1.4, model rewards lower, +0.31)<br>Asset Growth (stock z 5.65, model rewards lower, -0.46)<br>Dollar trading volume (stock z 2.86, model rewards lower, -0.36)<br>Change in common equity (stock z 3.81, model rewards lower, -0.27)<br>Operating profits-to-lagged book equity (stock z 4.16, model rewards lower, -0.24) |
| Forecast at 2026-07-31 refit | z 0.01, percentile 38, agrees with trade False |
| Drivers at 2026-07-31 | Capital turnover (stock z -0.71, model rewards lower, +0.14)<br>Market Equity (stock z 1.71, model rewards higher, +0.11)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.65, model rewards lower, +0.11)<br>short interest relative to shares (stock z -1.02, model rewards lower, +0.09)<br>Operating leverage (stock z -0.91, model rewards higher, -0.19)<br>Liquidity of book assets (stock z -0.83, model rewards higher, -0.13)<br>Dollar trading volume (stock z 1.84, model rewards lower, -0.12)<br>Price momentum t-12 to t-1 (stock z -0.71, model rewards higher, -0.06) |

### 3. MCO Moodys Corp (SHORT)

> The portfolio entered a short position on 2022-05-31 because the forecast was low, driven primarily by low Standardized Revenue surprise, low Liquidity of book assets, and low Maximum daily return. The forecast pointed the same way as the trade at entry, though by the latest month-end refit the forecast did not point the same way as the position held. The position lost $4.72 million while the stock returned 84.1%, and it had a weight of -1.103% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2022-06-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-4.72m |
| All spells | 2 spells, 1080 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-4.74m (long days $-0.03m, short days $-4.72m) |
| P&L by year | 2021 $-0.03m, 2022 $-0.04m, 2023 $-1.84m, 2024 $-1.44m, 2025 $-1.48m, 2026 $0.07m |
| Engine ledger price P&L (cross-check) | $-4.52m |
| Dividends, trading cost, borrow | $-0.23m, $-0.02m, $-0.11m |
| Average weight while held | -0.63% |
| Largest absolute weight | 1.168% |
| Weight on 2026-08-31 | -1.103% |
| Stock return while held | 68.0% |
| Entry decision | 2022-05-31 (month-end), drivers from the 2022-05-31 refit |
| Forecast at entry | z -0.11, percentile 42 of 2315, rho 1.34, agrees with trade True |
| Drivers at entry | Idiosyncratic volatility from the CAPM (252 days) (stock z -1.14, model rewards lower, +0.30)<br>Operating profits-to-book assets (stock z 0.73, model rewards higher, +0.24)<br>Quality minus Junk: Profitability (stock z 1.16, model rewards higher, +0.14)<br>Asset tangibility (stock z -1.17, model rewards lower, +0.13)<br>Standardized Revenue surprise (stock z -2.66, model rewards higher, -0.28)<br>Liquidity of book assets (stock z -0.64, model rewards higher, -0.19)<br>Maximum daily return (stock z -0.93, model rewards higher, -0.17)<br>Operating leverage (stock z -0.73, model rewards higher, -0.14) |
| Forecast at 2026-07-31 refit | z 0.02, percentile 38, agrees with trade False |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 1.42, model rewards higher, +0.27)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.75, model rewards lower, +0.13)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.48, model rewards lower, +0.10)<br>short interest relative to shares (stock z -1.0, model rewards lower, +0.09)<br>Operating leverage (stock z -0.65, model rewards higher, -0.14)<br>Operating profits-to-lagged book assets (stock z 0.92, model rewards lower, -0.12)<br>Market Beta (stock z 0.3, model rewards lower, -0.10)<br>Liquidity of book assets (stock z -0.61, model rewards higher, -0.10) |

### 4. MSI Motorola Solutions Inc (SHORT)

> The portfolio entered a short position on 2021-09-16 because the forecast was driven by low Market Beta, high Operating profits-to-book assets, and high Cash-based operating profits-to-book assets. The forecast did not point the same way as the trade, but the optimiser held the position for the book's limits or risk. The position lost $10.08 million while the stock returned 110.7%, and it had a weight of -1.098% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-09-16 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-10.08m |
| All spells | 1 spells, 1244 trading days, first 2021-09-16, last 2026-08-31 |
| Total P&L 2021-2026 | $-10.08m (long days $0.0m, short days $-10.08m) |
| P&L by year | 2021 $-0.35m, 2022 $-0.14m, 2023 $-2.34m, 2024 $-5.77m, 2025 $2.31m, 2026 $-3.78m |
| Engine ledger price P&L (cross-check) | $-9.57m |
| Dividends, trading cost, borrow | $-0.5m, $-0.03m, $-0.16m |
| Average weight while held | -0.845% |
| Largest absolute weight | 1.213% |
| Weight on 2026-08-31 | -1.098% |
| Stock return while held | 110.7% |
| Entry decision | 2021-09-15 (mid-month review), drivers from the 2021-08-31 refit |
| Forecast at entry | z 1.55, percentile 87 of 2596, rho 1.5, agrees with trade False, mid-month z 1.24 |
| Drivers at entry | Market Beta (stock z -0.89, model rewards lower, +0.55)<br>Operating profits-to-book assets (stock z 1.26, model rewards higher, +0.45)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.95, model rewards lower, +0.31)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.78, model rewards lower, +0.29)<br>Cash-based operating profits-to-book assets (stock z 1.09, model rewards lower, -0.28)<br>Return volatility (stock z -1.0, model rewards higher, -0.24)<br>Firm age (stock z 2.28, model rewards lower, -0.22)<br>Residual momentum t-12 to t-1 (stock z 0.88, model rewards lower, -0.13) |
| Forecast at 2026-07-31 refit | z 0.03, percentile 39, agrees with trade False |
| Drivers at 2026-07-31 | Idiosyncratic volatility from the CAPM (21 days) (stock z -0.97, model rewards lower, +0.20)<br>Operating profits-to-book assets (stock z 0.97, model rewards higher, +0.19)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.84, model rewards lower, +0.14)<br>Market Beta (stock z -0.4, model rewards lower, +0.14)<br>Return volatility (stock z -0.98, model rewards higher, -0.14)<br>Operating profits-to-lagged book assets (stock z 1.09, model rewards lower, -0.14)<br>Idiosyncratic volatility from the q-factor model (stock z -1.04, model rewards higher, -0.11)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.53, model rewards lower, -0.09) |

### 5. PANW Palo Alto Networks Inc (SHORT)

> The portfolio entered a short position on 2024-06-18 because high Dollar trading volume, high Change in long-term investments, and low Operating leverage lowered the forecast. The forecast did not point the same way as the trade, but the optimiser held the position for the book's limits or risk. The position lost $8.73 million while the stock returned 141.1%, and it had a weight of -1.085% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2024-06-18 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-8.73m |
| All spells | 2 spells, 973 trading days, first 2021-12-01, last 2026-08-31 |
| Total P&L 2021-2026 | $-9.19m (long days $0.0m, short days $-9.19m) |
| P&L by year | 2021 $-0.09m, 2022 $0.32m, 2023 $-0.68m, 2024 $-0.39m, 2025 $-0.59m, 2026 $-7.75m |
| Engine ledger price P&L (cross-check) | $-9.19m |
| Dividends, trading cost, borrow | $0.0m, $-0.02m, $-0.1m |
| Average weight while held | -0.358% |
| Largest absolute weight | 1.089% |
| Weight on 2026-08-31 | -1.085% |
| Stock return while held | 194.7% |
| Entry decision | 2024-06-17 (mid-month review), drivers from the 2024-05-31 refit |
| Forecast at entry | z 0.62, percentile 63 of 2129, rho 1.5, agrees with trade False, mid-month z 0.51 |
| Drivers at entry | Change in noncurrent operating liabilities (stock z 4.43, model rewards higher, +0.36)<br>Mispricing factor: Performance (stock z 1.27, model rewards higher, +0.30)<br>Market Equity (stock z 1.78, model rewards higher, +0.25)<br>Years 2-5 lagged returns, nonannual (stock z 1.09, model rewards higher, +0.24)<br>Dollar trading volume (stock z 5.33, model rewards lower, -0.65)<br>Change in long-term investments (stock z 4.51, model rewards lower, -0.27)<br>Operating leverage (stock z -0.49, model rewards higher, -0.19)<br>Long-term reversal (stock z 1.56, model rewards lower, -0.15) |
| Forecast at 2026-07-31 refit | z -0.4, percentile 26, agrees with trade True |
| Drivers at 2026-07-31 | Market Equity (stock z 4.26, model rewards higher, +0.28)<br>Change in long-term net operating assets (stock z 4.96, model rewards higher, +0.18)<br>Standardized Revenue surprise (stock z 4.29, model rewards higher, +0.14)<br>Capital turnover (stock z -0.63, model rewards lower, +0.12)<br>Dollar trading volume (stock z 3.93, model rewards lower, -0.26)<br>Operating leverage (stock z -0.78, model rewards higher, -0.16)<br>Change in net noncurrent operating assets (stock z 3.47, model rewards lower, -0.16)<br>Change in common equity (stock z 2.52, model rewards lower, -0.10) |

### 6. MU Micron Technology Inc (SHORT)

> The portfolio entered a short position on 2021-01-04 because the forecast was low, driven primarily by high Long-term reversal, high Dollar trading volume, and high Cash-based operating profits-to-book assets. The strategy believed in the short forecast, which pointed the same way as the trade. The position lost $46.41 million while the stock returned 1227.1%, and it held a weight of -1.083% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-01-04 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-46.41m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-46.41m (long days $0.0m, short days $-46.41m) |
| P&L by year | 2021 $-2.06m, 2022 $5.6m, 2023 $-7.31m, 2024 $-1.44m, 2025 $-20.27m, 2026 $-20.93m |
| Engine ledger price P&L (cross-check) | $-46.12m |
| Dividends, trading cost, borrow | $-0.29m, $-0.08m, $-0.19m |
| Average weight while held | -0.902% |
| Largest absolute weight | 1.564% |
| Weight on 2026-08-31 | -1.083% |
| Stock return while held | 1227.1% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z -0.17, percentile 37 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Years 2-5 lagged returns, nonannual (stock z 1.4, model rewards higher, +0.58)<br>Operating profits-to-book assets (stock z 1.0, model rewards higher, +0.40)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.69, model rewards lower, +0.28)<br>Mispricing factor: Performance (stock z 1.09, model rewards higher, +0.22)<br>Long-term reversal (stock z 1.87, model rewards lower, -0.52)<br>Dollar trading volume (stock z 4.31, model rewards lower, -0.38)<br>Cash-based operating profits-to-book assets (stock z 1.01, model rewards lower, -0.29)<br>Asset tangibility (stock z 1.38, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z -0.83, percentile 17, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 3.35, model rewards higher, +0.64)<br>Price momentum t-12 to t-1 (stock z 5.04, model rewards higher, +0.45)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Return volatility (stock z 2.37, model rewards higher, +0.34)<br>Market Beta (stock z 1.64, model rewards lower, -0.55)<br>Operating profits-to-lagged book assets (stock z 3.66, model rewards lower, -0.47)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 2.01, model rewards lower, -0.41)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40) |

### 7. MMC Marsh & Mclennan Cos Inc (SHORT)

> The position was entered as a short on 2022-06-01, driven by low Return volatility, low Liquidity of book assets, and high Residual momentum t-12 to t-1. The forecast did not point the same way as the trade, but the optimiser held it for the book's limits or risk. The position lost $1.35 million while the stock returned 27.8%, and it had a weight of -1.082% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2022-06-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-1.35m |
| All spells | 2 spells, 1183 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-1.12m (long days $0.22m, short days $-1.35m) |
| P&L by year | 2021 $0.22m, 2022 $-0.18m, 2023 $-0.98m, 2024 $-0.83m, 2025 $1.32m, 2026 $-0.68m |
| Engine ledger price P&L (cross-check) | $-0.73m |
| Dividends, trading cost, borrow | $-0.39m, $-0.02m, $-0.11m |
| Average weight while held | -0.572% |
| Largest absolute weight | 1.187% |
| Weight on 2026-08-31 | -1.082% |
| Stock return while held | 55.2% |
| Entry decision | 2022-05-31 (month-end), drivers from the 2022-05-31 refit |
| Forecast at entry | z 0.62, percentile 64 of 2315, rho 1.34, agrees with trade False |
| Drivers at entry | Idiosyncratic volatility from the CAPM (252 days) (stock z -1.23, model rewards lower, +0.32)<br>Market Beta (stock z -0.58, model rewards lower, +0.26)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -1.01, model rewards lower, +0.21)<br>Market Equity (stock z 1.94, model rewards higher, +0.20)<br>Return volatility (stock z -0.93, model rewards higher, -0.21)<br>Liquidity of book assets (stock z -0.7, model rewards higher, -0.20)<br>Residual momentum t-12 to t-1 (stock z 1.51, model rewards lower, -0.17)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.56, model rewards lower, -0.16) |
| Forecast at 2026-07-31 refit | z 0.44, percentile 58, agrees with trade False |
| Drivers at 2026-07-31 | Market Beta (stock z -0.86, model rewards lower, +0.29)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.8, model rewards lower, +0.14)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.62, model rewards lower, +0.13)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.7, model rewards lower, +0.10)<br>Operating leverage (stock z -0.52, model rewards higher, -0.11)<br>Idiosyncratic volatility from the q-factor model (stock z -0.81, model rewards higher, -0.09)<br>Liquidity of book assets (stock z -0.51, model rewards higher, -0.08)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.42, model rewards lower, -0.08) |

### 8. MSFT Microsoft Corp (SHORT)

> The portfolio entered a short position on 2026-02-02 because high Dollar trading volume, high Operating profits-to-lagged book assets, and low Operating leverage lowered the forecast. The forecast did not point the same way as the trade, but the optimiser held the position for the book's limits or risk. The position lost $4.65 million while the stock returned 19.8%, and it had a weight of -1.081% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2026-02-02 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-4.65m |
| All spells | 8 spells, 937 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-6.99m (long days $-0.61m, short days $-6.38m) |
| P&L by year | 2021 $2.53m, 2022 $-2.11m, 2023 $-1.33m, 2024 $-1.33m, 2025 $-0.1m, 2026 $-4.65m |
| Engine ledger price P&L (cross-check) | $-7.05m |
| Dividends, trading cost, borrow | $0.06m, $-0.03m, $-0.03m |
| Average weight while held | 0.086% |
| Largest absolute weight | 1.5% |
| Weight on 2026-08-31 | -1.081% |
| Stock return while held | 120.7% |
| Entry decision | 2026-01-30 (month-end), drivers from the 2026-01-31 refit |
| Forecast at entry | z 0.07, percentile 43 of 2227, rho 0.8, agrees with trade False |
| Drivers at entry | Market Equity (stock z 6.56, model rewards higher, +0.96)<br>Operating profits-to-book assets (stock z 1.61, model rewards higher, +0.56)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.89, model rewards lower, +0.30)<br>Mispricing factor: Performance (stock z 1.71, model rewards higher, +0.25)<br>Dollar trading volume (stock z 6.12, model rewards lower, -1.11)<br>Operating profits-to-lagged book assets (stock z 1.7, model rewards lower, -0.41)<br>Operating leverage (stock z -0.77, model rewards higher, -0.36)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.56, model rewards lower, -0.19) |
| Forecast at 2026-07-31 refit | z -0.0, percentile 38, agrees with trade False |
| Drivers at 2026-07-31 | Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Operating profits-to-book assets (stock z 1.5, model rewards higher, +0.29)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.67, model rewards lower, +0.12)<br>short interest relative to shares (stock z -1.11, model rewards lower, +0.09)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Operating profits-to-lagged book assets (stock z 1.45, model rewards lower, -0.19)<br>Operating leverage (stock z -0.8, model rewards higher, -0.17)<br>Intrinsic value to price (stock z 6.59, model rewards lower, -0.09) |

### 9. NVDA Nvidia Corp (SHORT)

> The position was entered as a short on 2024-08-16 because the forecast was low, driven by high Dollar trading volume, high Operating profits-to-lagged book assets, and high Long-term reversal. The forecast pointed the same way as the trade. The position lost $10.86 million while the stock returned 77.3%, and it had a weight of -1.068% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2024-08-16 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-10.86m |
| All spells | 2 spells, 1107 trading days, first 2022-04-01, last 2026-08-31 |
| Total P&L 2021-2026 | $70.8m (long days $81.68m, short days $-10.88m) |
| P&L by year | 2022 $-3.95m, 2023 $42.36m, 2024 $41.79m, 2025 $-6.34m, 2026 $-3.05m |
| Engine ledger price P&L (cross-check) | $70.77m |
| Dividends, trading cost, borrow | $0.03m, $-0.1m, $-0.09m |
| Average weight while held | 0.93% |
| Largest absolute weight | 4.499% |
| Weight on 2026-08-31 | -1.068% |
| Stock return while held | 727.9% |
| Entry decision | 2024-08-15 (mid-month review), drivers from the 2024-07-31 refit |
| Forecast at entry | z -1.81, percentile 11 of 2150, rho 1.5, agrees with trade True, mid-month z -2.63 |
| Drivers at entry | Operating profits-to-book assets (stock z 2.97, model rewards higher, +0.84)<br>Market Equity (stock z 6.75, model rewards higher, +0.82)<br>Liquidity of book assets (stock z 1.96, model rewards higher, +0.61)<br>Years 2-5 lagged returns, nonannual (stock z 2.64, model rewards higher, +0.58)<br>Dollar trading volume (stock z 6.24, model rewards lower, -0.77)<br>Operating profits-to-lagged book assets (stock z 3.32, model rewards lower, -0.64)<br>Long-term reversal (stock z 5.41, model rewards lower, -0.63)<br>Sales Growth (1 year) (stock z 5.97, model rewards lower, -0.56) |
| Forecast at 2026-07-31 refit | z -1.16, percentile 13, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 3.43, model rewards higher, +0.66)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Cash-based operating profits-to-lagged book assets (stock z 4.6, model rewards higher, +0.36)<br>Years 2-5 lagged returns, nonannual (stock z 2.84, model rewards higher, +0.24)<br>Market Beta (stock z 1.67, model rewards lower, -0.56)<br>Operating profits-to-lagged book assets (stock z 3.66, model rewards lower, -0.47)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Long-term reversal (stock z 4.86, model rewards lower, -0.23) |

### 10. DE Deere & Co (SHORT)

> The portfolio entered a short position on 2021-09-01, driven by high Firm age, high Dollar trading volume, and high Long-term reversal. The forecast did not point the same way as the trade, but the optimiser held it for the book's limits or risk. The position lost $7.63 million while the stock returned 84.7%, and it had a weight of -1.065% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-09-01 to 2026-08-31 (the spell held on 2026-08-31) |
| Spell P&L | $-7.63m |
| All spells | 1 spells, 1254 trading days, first 2021-09-01, last 2026-08-31 |
| Total P&L 2021-2026 | $-7.63m (long days $0.0m, short days $-7.63m) |
| P&L by year | 2021 $0.12m, 2022 $-0.64m, 2023 $0.19m, 2024 $-0.88m, 2025 $-1.45m, 2026 $-4.97m |
| Engine ledger price P&L (cross-check) | $-7.15m |
| Dividends, trading cost, borrow | $-0.48m, $-0.02m, $-0.13m |
| Average weight while held | -0.642% |
| Largest absolute weight | 1.231% |
| Weight on 2026-08-31 | -1.065% |
| Stock return while held | 84.7% |
| Entry decision | 2021-08-31 (month-end), drivers from the 2021-08-31 refit |
| Forecast at entry | z 0.16, percentile 49 of 2596, rho 1.5, agrees with trade False |
| Drivers at entry | Market Equity (stock z 2.88, model rewards higher, +0.33)<br>Market Beta (stock z -0.45, model rewards lower, +0.28)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.75, model rewards lower, +0.24)<br>Operating profits-to-book assets (stock z 0.45, model rewards higher, +0.16)<br>Firm age (stock z 2.87, model rewards lower, -0.27)<br>Dollar trading volume (stock z 2.35, model rewards lower, -0.21)<br>Long-term reversal (stock z 0.73, model rewards lower, -0.15)<br>Return volatility (stock z -0.52, model rewards higher, -0.13) |
| Forecast at 2026-07-31 refit | z 0.22, percentile 47, agrees with trade False |
| Drivers at 2026-07-31 | Market Equity (stock z 2.37, model rewards higher, +0.16)<br>Market Beta (stock z -0.32, model rewards lower, +0.11)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.63, model rewards lower, +0.11)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.53, model rewards lower, +0.11)<br>Operating leverage (stock z -0.51, model rewards higher, -0.11)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.74, model rewards lower, -0.10)<br>Dollar trading volume (stock z 1.36, model rewards lower, -0.09)<br>Return volatility (stock z -0.58, model rewards higher, -0.08) |

## Top-10 positive contributor 2021-2026

### 1. AVGO Broadcom Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by high Market Equity, high Operating profits-to-book assets, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the positive forecast at entry, though by the 2026-07-31 refit the forecast did not point the same way as the position held. The position earned $92.44 million while the stock returned 867.9%, and it had a weight of 2.772% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $92.44m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $92.44m (long days $92.44m, short days $0.0m) |
| P&L by year | 2021 $10.26m, 2022 $-4.29m, 2023 $23.41m, 2024 $33.73m, 2025 $25.05m, 2026 $4.28m |
| Engine ledger price P&L (cross-check) | $89.18m |
| Dividends, trading cost, borrow | $3.26m, $-0.12m, $0.0m |
| Average weight while held | 2.844% |
| Largest absolute weight | 4.553% |
| Weight on 2026-08-31 | 2.772% |
| Stock return while held | 867.9% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.28, percentile 91 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Equity (stock z 4.83, model rewards higher, +0.52)<br>Operating profits-to-book assets (stock z 1.06, model rewards higher, +0.42)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.94, model rewards lower, +0.38)<br>Asset tangibility (stock z -1.67, model rewards lower, +0.31)<br>Cash-based operating profits-to-book assets (stock z 1.16, model rewards lower, -0.33)<br>Liquidity of book assets (stock z -0.88, model rewards higher, -0.32)<br>Dollar trading volume (stock z 2.7, model rewards lower, -0.24)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.16, model rewards lower, -0.14) |
| Forecast at 2026-07-31 refit | z -0.3, percentile 28, agrees with trade False |
| Drivers at 2026-07-31 | Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Operating profits-to-book assets (stock z 1.49, model rewards higher, +0.29)<br>Years 2-5 lagged returns, nonannual (stock z 2.16, model rewards higher, +0.18)<br>Mispricing factor: Performance (stock z 1.44, model rewards higher, +0.12)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Long-term reversal (stock z 4.86, model rewards lower, -0.23)<br>Operating leverage (stock z -0.79, model rewards higher, -0.17)<br>Operating profits-to-lagged book assets (stock z 1.2, model rewards lower, -0.16) |

### 2. NVDA Nvidia Corp (LONG)

> The portfolio entered a LONG position on 2022-04-01 because the forecast was high, driven by high Market Equity, high Operating profits-to-book assets, and high Price momentum t-12 to t-1. The strategy believed in the positive forecast, which pointed the same way as the trade. This position earned $81.68 million while the stock returned 367.0%, and the position's weight on 2026-08-31 was -1.068%.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2022-04-01 to 2024-08-15 (the largest spell by dollars) |
| Spell P&L | $81.68m |
| All spells | 2 spells, 1107 trading days, first 2022-04-01, last 2026-08-31 |
| Total P&L 2021-2026 | $70.8m (long days $81.68m, short days $-10.88m) |
| P&L by year | 2022 $-3.95m, 2023 $42.36m, 2024 $41.79m, 2025 $-6.34m, 2026 $-3.05m |
| Engine ledger price P&L (cross-check) | $70.77m |
| Dividends, trading cost, borrow | $0.03m, $-0.1m, $-0.09m |
| Average weight while held | 0.93% |
| Largest absolute weight | 4.499% |
| Weight on 2026-08-31 | -1.068% |
| Stock return while held | 727.9% |
| Entry decision | 2022-03-31 (month-end), drivers from the 2022-03-31 refit |
| Forecast at entry | z 1.16, percentile 93 of 2425, rho 0.94, agrees with trade True |
| Drivers at entry | Market Equity (stock z 6.56, model rewards higher, +0.86)<br>Operating profits-to-book assets (stock z 2.18, model rewards higher, +0.79)<br>Price momentum t-12 to t-1 (stock z 2.16, model rewards higher, +0.49)<br>Years 2-5 lagged returns, nonannual (stock z 1.51, model rewards higher, +0.40)<br>Dollar trading volume (stock z 6.2, model rewards lower, -0.85)<br>Operating profits-to-lagged book assets (stock z 2.38, model rewards lower, -0.33)<br>Cash-based operating profits-to-book assets (stock z 1.5, model rewards lower, -0.33)<br>Long-term reversal (stock z 1.42, model rewards lower, -0.23) |
| Forecast at 2026-07-31 refit | z -1.16, percentile 13, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 3.43, model rewards higher, +0.66)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Cash-based operating profits-to-lagged book assets (stock z 4.6, model rewards higher, +0.36)<br>Years 2-5 lagged returns, nonannual (stock z 2.84, model rewards higher, +0.24)<br>Market Beta (stock z 1.67, model rewards lower, -0.56)<br>Operating profits-to-lagged book assets (stock z 3.66, model rewards lower, -0.47)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Long-term reversal (stock z 4.86, model rewards lower, -0.23) |

### 3. IBKR Interactive Brokers Group Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by low Market Beta, a low Kaplan-Zingales index, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the positive forecast, which pointed the same way as the trade. The position earned $44.92 million as the stock returned 553.7% while held, and it had a weight of 4.019% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $44.92m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $44.92m (long days $44.92m, short days $0.0m) |
| P&L by year | 2021 $0.37m, 2022 $0.25m, 2023 $1.1m, 2024 $11.03m, 2025 $12.88m, 2026 $19.28m |
| Engine ledger price P&L (cross-check) | $44.57m |
| Dividends, trading cost, borrow | $0.35m, $-0.1m, $0.0m |
| Average weight while held | 1.222% |
| Largest absolute weight | 4.071% |
| Weight on 2026-08-31 | 4.019% |
| Stock return while held | 553.7% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.86, percentile 98 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Beta (stock z -0.68, model rewards lower, +0.40)<br>Kaplan-Zingales index (stock z -7.42, model rewards lower, +0.39)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.76, model rewards lower, +0.31)<br>Free cash flow-to-price (stock z 4.57, model rewards higher, +0.31)<br>Book leverage (stock z 6.93, model rewards lower, -0.55)<br>Change in current operating liabilities (stock z 3.2, model rewards lower, -0.42)<br>Liquidity of market assets (stock z 3.04, model rewards lower, -0.41)<br>Change in net financial assets (stock z 0.94, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z 1.34, percentile 94, agrees with trade True |
| Drivers at 2026-07-31 | Operating cash flow-to-market (stock z 2.55, model rewards higher, +0.35)<br>Free cash flow-to-price (stock z 2.77, model rewards higher, +0.31)<br>Capital turnover (stock z -1.06, model rewards lower, +0.20)<br>Kaplan-Zingales index (stock z -7.26, model rewards lower, +0.20)<br>Operating leverage (stock z -1.09, model rewards higher, -0.23)<br>Market Beta (stock z 0.42, model rewards lower, -0.14)<br>Long-term reversal (stock z 2.89, model rewards lower, -0.13)<br>Operating profits-to-book assets (stock z -0.5, model rewards higher, -0.10) |

### 4. AAPL Apple Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by high Market Equity, high Operating profits-to-book assets, and low Idiosyncratic volatility from the CAPM (252 days). The strategy believed in the positive forecast, which pointed the same way as the trade. The position earned $41.09 million while the stock returned 151.5%, and it held a weight of 1.972% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $41.09m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $41.09m (long days $41.09m, short days $0.0m) |
| P&L by year | 2021 $9.19m, 2022 $-11.22m, 2023 $18.0m, 2024 $14.38m, 2025 $4.03m, 2026 $6.71m |
| Engine ledger price P&L (cross-check) | $40.06m |
| Dividends, trading cost, borrow | $1.03m, $-0.06m, $0.0m |
| Average weight while held | 3.217% |
| Largest absolute weight | 4.226% |
| Weight on 2026-08-31 | 1.972% |
| Stock return while held | 151.5% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.11, percentile 86 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Equity (stock z 6.57, model rewards higher, +0.70)<br>Operating profits-to-book assets (stock z 1.61, model rewards higher, +0.65)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.97, model rewards lower, +0.40)<br>Years 2-5 lagged returns, nonannual (stock z 0.96, model rewards higher, +0.40)<br>Dollar trading volume (stock z 6.03, model rewards lower, -0.53)<br>Cash-based operating profits-to-book assets (stock z 1.33, model rewards lower, -0.38)<br>Long-term reversal (stock z 1.12, model rewards lower, -0.31)<br>SYY-10 mispricing score (stock z 2.07, model rewards lower, -0.30) |
| Forecast at 2026-07-31 refit | z 0.17, percentile 44, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 3.39, model rewards higher, +0.65)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Cash-based operating profits-to-lagged book assets (stock z 2.25, model rewards higher, +0.18)<br>Mispricing factor: Performance (stock z 1.98, model rewards higher, +0.16)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Operating profits-to-lagged book assets (stock z 2.94, model rewards lower, -0.38)<br>Capital turnover (stock z 1.03, model rewards lower, -0.20)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z 1.8, model rewards lower, -0.10) |

### 5. LRCX Lam Resh Corp (LONG)

> The long position was entered on 2024-05-16 because the forecast was high, driven by high Operating profits-to-book assets, high Mispricing factor: Performance, and high Market Equity. The strategy believed in the forecast at entry, though by the latest month-end refit the forecast did not point the same way as the trade. The position earned $35.09 million while the stock returned 225.2%, and it held a weight of 3.582% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2024-05-16 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $35.09m |
| All spells | 1 spells, 574 trading days, first 2024-05-16, last 2026-08-31 |
| Total P&L 2021-2026 | $35.09m (long days $35.09m, short days $0.0m) |
| P&L by year | 2024 $-1.52m, 2025 $18.22m, 2026 $18.38m |
| Engine ledger price P&L (cross-check) | $34.85m |
| Dividends, trading cost, borrow | $0.23m, $-0.07m, $0.0m |
| Average weight while held | 1.535% |
| Largest absolute weight | 4.533% |
| Weight on 2026-08-31 | 3.582% |
| Stock return while held | 225.2% |
| Entry decision | 2024-05-15 (mid-month review), drivers from the 2024-04-30 refit |
| Forecast at entry | z 1.9, percentile 95 of 2109, rho 1.5, agrees with trade True, mid-month z 2.2 |
| Drivers at entry | Operating profits-to-book assets (stock z 1.94, model rewards higher, +0.72)<br>Mispricing factor: Performance (stock z 1.78, model rewards higher, +0.44)<br>Market Equity (stock z 2.3, model rewards higher, +0.35)<br>Years 2-5 lagged returns, nonannual (stock z 0.89, model rewards higher, +0.22)<br>Dollar trading volume (stock z 3.0, model rewards lower, -0.43)<br>Operating profits-to-lagged book assets (stock z 1.57, model rewards lower, -0.33)<br>Cash-based operating profits-to-book assets (stock z 1.75, model rewards lower, -0.27)<br>Market Beta (stock z 0.45, model rewards lower, -0.25) |
| Forecast at 2026-07-31 refit | z -0.03, percentile 36, agrees with trade False |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 2.77, model rewards higher, +0.53)<br>Market Equity (stock z 5.89, model rewards higher, +0.39)<br>Price momentum t-12 to t-1 (stock z 3.15, model rewards higher, +0.28)<br>Return volatility (stock z 1.87, model rewards higher, +0.27)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Market Beta (stock z 1.12, model rewards lower, -0.38)<br>Operating profits-to-lagged book assets (stock z 2.28, model rewards lower, -0.29)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 1.3, model rewards lower, -0.26) |

### 6. DELL Dell Technologies Inc (LONG)

> The portfolio entered a long position on 2022-06-16 because the forecast was high, driven by high Operating cash flow-to-market, low Market Beta, and high Ebitda-to-market enterprise value. The forecast pointed the same way as the trade at entry, though by the latest month-end refit the forecast did not point the same way as the position held. The position earned $33.84 million while the stock returned 976.0%, and it had a weight of 1.643% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2022-06-16 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $33.84m |
| All spells | 2 spells, 1165 trading days, first 2021-04-01, last 2026-08-31 |
| Total P&L 2021-2026 | $33.9m (long days $33.9m, short days $0.0m) |
| P&L by year | 2021 $0.06m, 2022 $-0.16m, 2023 $3.8m, 2024 $5.4m, 2025 $2.81m, 2026 $21.98m |
| Engine ledger price P&L (cross-check) | $33.41m |
| Dividends, trading cost, borrow | $0.5m, $-0.05m, $0.0m |
| Average weight while held | 0.627% |
| Largest absolute weight | 2.085% |
| Weight on 2026-08-31 | 1.643% |
| Stock return while held | 1046.2% |
| Entry decision | 2022-06-15 (mid-month review), drivers from the 2022-05-31 refit |
| Forecast at entry | z 2.59, percentile 99 of 2315, rho 1.34, agrees with trade True, mid-month z 2.81 |
| Drivers at entry | Operating cash flow-to-market (stock z 3.76, model rewards higher, +0.58)<br>Market Beta (stock z -0.99, model rewards lower, +0.44)<br>Ebitda-to-market enterprise value (stock z 1.03, model rewards higher, +0.23)<br>Free cash flow-to-price (stock z 2.49, model rewards higher, +0.23)<br>Equity net payout (stock z 1.3, model rewards lower, -0.29)<br>Highest 5 days of return scaled by volatility (stock z 2.64, model rewards lower, -0.27)<br>Liquidity of book assets (stock z -0.67, model rewards higher, -0.19)<br>R&D-to-market (stock z 1.98, model rewards lower, -0.18) |
| Forecast at 2026-07-31 refit | z -0.1, percentile 34, agrees with trade False |
| Drivers at 2026-07-31 | Return volatility (stock z 1.41, model rewards higher, +0.20)<br>Price momentum t-9 to t-1 (stock z 2.37, model rewards higher, +0.17)<br>Operating leverage (stock z 0.79, model rewards higher, +0.16)<br>Price momentum t-12 to t-1 (stock z 1.84, model rewards higher, +0.16)<br>Dollar trading volume (stock z 4.57, model rewards lower, -0.30)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 1.46, model rewards lower, -0.30)<br>Price momentum t-6 to t-1 (stock z 4.74, model rewards lower, -0.25)<br>Capital turnover (stock z 1.06, model rewards lower, -0.20) |

### 7. COST Costco Wholesale Corp New (LONG)

> The long position was entered on 2021-12-01 because the forecast was high, driven by high Operating leverage, high Market Equity, and low Market Beta. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $32.07 million while the stock returned 86.8%, and it had a weight of 3.825% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-12-01 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $32.07m |
| All spells | 1 spells, 1191 trading days, first 2021-12-01, last 2026-08-31 |
| Total P&L 2021-2026 | $32.07m (long days $32.07m, short days $0.0m) |
| P&L by year | 2021 $0.24m, 2022 $-2.12m, 2023 $12.49m, 2024 $17.47m, 2025 $-1.73m, 2026 $5.72m |
| Engine ledger price P&L (cross-check) | $30.22m |
| Dividends, trading cost, borrow | $1.86m, $-0.08m, $0.0m |
| Average weight while held | 2.792% |
| Largest absolute weight | 4.294% |
| Weight on 2026-08-31 | 3.825% |
| Stock return while held | 86.8% |
| Entry decision | 2021-11-30 (month-end), drivers from the 2021-11-30 refit |
| Forecast at entry | z 3.07, percentile 100 of 2554, rho 1.32, agrees with trade True |
| Drivers at entry | Operating leverage (stock z 4.2, model rewards higher, +1.04)<br>Market Equity (stock z 6.36, model rewards higher, +0.66)<br>Market Beta (stock z -1.09, model rewards lower, +0.58)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -1.04, model rewards lower, +0.37)<br>Capital turnover (stock z 3.98, model rewards lower, -0.86)<br>Dollar trading volume (stock z 3.39, model rewards lower, -0.32)<br>Return volatility (stock z -0.98, model rewards higher, -0.20)<br>Maximum daily return (stock z -0.65, model rewards higher, -0.11) |
| Forecast at 2026-07-31 refit | z 0.58, percentile 66, agrees with trade True |
| Drivers at 2026-07-31 | Operating leverage (stock z 4.24, model rewards higher, +0.89)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.96, model rewards lower, +0.19)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -1.0, model rewards lower, +0.17)<br>Capital turnover (stock z 3.96, model rewards lower, -0.75)<br>Dollar trading volume (stock z 4.16, model rewards lower, -0.28)<br>Return volatility (stock z -0.88, model rewards higher, -0.13)<br>Idiosyncratic volatility from the q-factor model (stock z -0.92, model rewards higher, -0.10) |

### 8. FTNT Fortinet Inc (LONG)

> The portfolio entered a long position on 2021-01-04 because the forecast was high, driven by high Operating profits-to-book assets, high Years 2-5 lagged returns, nonannual, and low Residual momentum t-12 to t-1. The strategy's forecast pointed the same way as the trade. The position earned $28.92 million as the stock returned 487.2%, and it held a weight of 2.173% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $28.92m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $28.92m (long days $28.92m, short days $0.0m) |
| P&L by year | 2021 $1.91m, 2022 $-2.68m, 2023 $2.08m, 2024 $11.38m, 2025 $-2.88m, 2026 $19.1m |
| Engine ledger price P&L (cross-check) | $28.92m |
| Dividends, trading cost, borrow | $0.0m, $-0.05m, $0.0m |
| Average weight while held | 1.125% |
| Largest absolute weight | 2.255% |
| Weight on 2026-08-31 | 2.173% |
| Stock return while held | 487.2% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.28, percentile 91 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Operating profits-to-book assets (stock z 1.17, model rewards higher, +0.47)<br>Years 2-5 lagged returns, nonannual (stock z 1.06, model rewards higher, +0.44)<br>Residual momentum t-12 to t-1 (stock z -2.26, model rewards lower, +0.37)<br>Mispricing factor: Performance (stock z 1.56, model rewards higher, +0.31)<br>Long-term reversal (stock z 1.53, model rewards lower, -0.42)<br>Cash-based operating profits-to-book assets (stock z 1.41, model rewards lower, -0.41)<br>SYY-10 mispricing score (stock z 2.07, model rewards lower, -0.30)<br>Change in current operating liabilities (stock z 1.25, model rewards lower, -0.16) |
| Forecast at 2026-07-31 refit | z 0.23, percentile 48, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 1.61, model rewards higher, +0.31)<br>Mispricing factor: Performance (stock z 1.98, model rewards higher, +0.16)<br>Market Equity (stock z 1.67, model rewards higher, +0.11)<br>Cash-based operating profits-to-lagged book assets (stock z 1.15, model rewards higher, +0.09)<br>Operating profits-to-lagged book assets (stock z 1.18, model rewards lower, -0.15)<br>SYY-10 mispricing score (stock z 2.02, model rewards lower, -0.09)<br>Price momentum t-6 to t-1 (stock z 1.55, model rewards lower, -0.08)<br>Dollar trading volume (stock z 1.1, model rewards lower, -0.07) |

### 9. EXPD Expeditors International Wa Inc (LONG)

> The portfolio entered a long position on 2023-07-03 because the forecast was high, driven by high Operating leverage, high Operating profits-to-book assets, and high Mispricing factor: Performance. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $25.06 million as the stock returned 60.6% while held, and it had a weight of 3.895% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2023-07-03 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $25.06m |
| All spells | 1 spells, 794 trading days, first 2023-07-03, last 2026-08-31 |
| Total P&L 2021-2026 | $25.06m (long days $25.06m, short days $0.0m) |
| P&L by year | 2023 $2.14m, 2024 $-3.85m, 2025 $13.78m, 2026 $12.99m |
| Engine ledger price P&L (cross-check) | $23.98m |
| Dividends, trading cost, borrow | $1.08m, $-0.1m, $0.0m |
| Average weight while held | 2.625% |
| Largest absolute weight | 3.989% |
| Weight on 2026-08-31 | 3.895% |
| Stock return while held | 60.6% |
| Entry decision | 2023-06-30 (month-end), drivers from the 2023-06-30 refit |
| Forecast at entry | z 3.52, percentile 100 of 2165, rho 1.5, agrees with trade True |
| Drivers at entry | Operating leverage (stock z 3.21, model rewards higher, +1.12)<br>Operating profits-to-book assets (stock z 1.6, model rewards higher, +0.74)<br>Mispricing factor: Performance (stock z 1.5, model rewards higher, +0.39)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.89, model rewards lower, +0.32)<br>Capital turnover (stock z 2.47, model rewards lower, -0.81)<br>Cash-based operating profits-to-book assets (stock z 2.44, model rewards lower, -0.50)<br>Return volatility (stock z -0.98, model rewards higher, -0.28)<br>Equity net payout (stock z 1.04, model rewards lower, -0.23) |
| Forecast at 2026-07-31 refit | z 0.66, percentile 69, agrees with trade True |
| Drivers at 2026-07-31 | Operating leverage (stock z 2.75, model rewards higher, +0.57)<br>Operating profits-to-book assets (stock z 1.01, model rewards higher, +0.19)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.83, model rewards lower, +0.17)<br>Mispricing factor: Performance (stock z 1.55, model rewards higher, +0.12)<br>Capital turnover (stock z 2.76, model rewards lower, -0.53)<br>Return volatility (stock z -0.86, model rewards higher, -0.12)<br>Operating profits-to-lagged book assets (stock z 0.71, model rewards lower, -0.09)<br>SYY-10 mispricing score (stock z 1.97, model rewards lower, -0.08) |

### 10. ABBV Abbvie Inc (LONG)

> The portfolio entered a long position in ABBV because the forecast was high, driven by high Market Equity, high Change in net operating assets, and low Change in net financial assets. The strategy believed in the forecast, which pointed the same way as the trade. The position earned $22.41 million as the stock returned 195.9% while held, and it had a weight of 2.564% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | LONG 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $22.41m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $22.41m (long days $22.41m, short days $0.0m) |
| P&L by year | 2021 $4.43m, 2022 $4.8m, 2023 $-0.38m, 2024 $2.3m, 2025 $6.7m, 2026 $4.55m |
| Engine ledger price P&L (cross-check) | $18.99m |
| Dividends, trading cost, borrow | $3.42m, $-0.04m, $0.0m |
| Average weight while held | 1.665% |
| Largest absolute weight | 2.854% |
| Weight on 2026-08-31 | 2.564% |
| Stock return while held | 195.9% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z 1.94, percentile 99 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Market Equity (stock z 5.16, model rewards higher, +0.55)<br>Change in net operating assets (stock z 4.72, model rewards higher, +0.46)<br>Change in net financial assets (stock z -1.64, model rewards lower, +0.45)<br>Market Beta (stock z -0.77, model rewards lower, +0.45)<br>Change in net noncurrent operating assets (stock z 3.63, model rewards lower, -0.31)<br>Operating profits-to-lagged book assets (stock z 1.95, model rewards lower, -0.31)<br>Dollar trading volume (stock z 3.08, model rewards lower, -0.27)<br>Change in financial liabilities (stock z 2.05, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z 1.1, percentile 89, agrees with trade True |
| Drivers at 2026-07-31 | Market Beta (stock z -1.34, model rewards lower, +0.45)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Operating profits-to-book assets (stock z 1.75, model rewards higher, +0.34)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.79, model rewards lower, +0.16)<br>Dollar trading volume (stock z 2.97, model rewards lower, -0.20)<br>Operating profits-to-lagged book assets (stock z 1.22, model rewards lower, -0.16)<br>Operating leverage (stock z -0.67, model rewards higher, -0.14)<br>Return volatility (stock z -0.76, model rewards higher, -0.11) |

## Top-10 negative contributor 2021-2026

### 1. MU Micron Technology Inc (SHORT)

> The portfolio entered a short position on 2021-01-04 because the forecast was low, driven primarily by high Long-term reversal, high Dollar trading volume, and high Cash-based operating profits-to-book assets. The strategy believed in the short forecast, which pointed the same way as the trade. The position lost $46.41 million while the stock returned 1227.1%, and it held a weight of -1.083% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-46.41m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-46.41m (long days $0.0m, short days $-46.41m) |
| P&L by year | 2021 $-2.06m, 2022 $5.6m, 2023 $-7.31m, 2024 $-1.44m, 2025 $-20.27m, 2026 $-20.93m |
| Engine ledger price P&L (cross-check) | $-46.12m |
| Dividends, trading cost, borrow | $-0.29m, $-0.08m, $-0.19m |
| Average weight while held | -0.902% |
| Largest absolute weight | 1.564% |
| Weight on 2026-08-31 | -1.083% |
| Stock return while held | 1227.1% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z -0.17, percentile 37 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Years 2-5 lagged returns, nonannual (stock z 1.4, model rewards higher, +0.58)<br>Operating profits-to-book assets (stock z 1.0, model rewards higher, +0.40)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.69, model rewards lower, +0.28)<br>Mispricing factor: Performance (stock z 1.09, model rewards higher, +0.22)<br>Long-term reversal (stock z 1.87, model rewards lower, -0.52)<br>Dollar trading volume (stock z 4.31, model rewards lower, -0.38)<br>Cash-based operating profits-to-book assets (stock z 1.01, model rewards lower, -0.29)<br>Asset tangibility (stock z 1.38, model rewards lower, -0.26) |
| Forecast at 2026-07-31 refit | z -0.83, percentile 17, agrees with trade True |
| Drivers at 2026-07-31 | Operating profits-to-book assets (stock z 3.35, model rewards higher, +0.64)<br>Price momentum t-12 to t-1 (stock z 5.04, model rewards higher, +0.45)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Return volatility (stock z 2.37, model rewards higher, +0.34)<br>Market Beta (stock z 1.64, model rewards lower, -0.55)<br>Operating profits-to-lagged book assets (stock z 3.66, model rewards lower, -0.47)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 2.01, model rewards lower, -0.41)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40) |

### 2. INTC Intel Corp (SHORT)

> The portfolio entered a short position on 2021-09-16 because high Dollar trading volume, high Cash-based operating profits-to-book assets, and low Return volatility lowered the forecast. The forecast did not point the same way as the trade, but the optimiser held the position for the book's limits or risk. The position lost $25.35 million while the stock returned 77.3%, and it had a weight of -0.826% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-09-16 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-25.35m |
| All spells | 1 spells, 1244 trading days, first 2021-09-16, last 2026-08-31 |
| Total P&L 2021-2026 | $-25.35m (long days $0.0m, short days $-25.35m) |
| P&L by year | 2021 $0.11m, 2022 $1.67m, 2023 $-9.01m, 2024 $10.04m, 2025 $-11.06m, 2026 $-17.1m |
| Engine ledger price P&L (cross-check) | $-24.79m |
| Dividends, trading cost, borrow | $-0.56m, $-0.08m, $-0.16m |
| Average weight while held | -0.811% |
| Largest absolute weight | 1.479% |
| Weight on 2026-08-31 | -0.826% |
| Stock return while held | 77.3% |
| Entry decision | 2021-09-15 (mid-month review), drivers from the 2021-08-31 refit |
| Forecast at entry | z 1.45, percentile 85 of 2596, rho 1.5, agrees with trade False, mid-month z 1.16 |
| Drivers at entry | Market Beta (stock z -1.09, model rewards lower, +0.68)<br>Market Equity (stock z 5.73, model rewards higher, +0.66)<br>Operating profits-to-book assets (stock z 1.76, model rewards higher, +0.63)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.9, model rewards lower, +0.33)<br>Dollar trading volume (stock z 5.91, model rewards lower, -0.53)<br>Cash-based operating profits-to-book assets (stock z 1.68, model rewards lower, -0.43)<br>Return volatility (stock z -1.01, model rewards higher, -0.24)<br>Intrinsic value to price (stock z 6.35, model rewards lower, -0.14) |
| Forecast at 2026-07-31 refit | z -0.13, percentile 33, agrees with trade True |
| Drivers at 2026-07-31 | Price momentum t-12 to t-1 (stock z 5.04, model rewards higher, +0.45)<br>Market Equity (stock z 6.73, model rewards higher, +0.44)<br>Price momentum t-9 to t-1 (stock z 3.73, model rewards higher, +0.26)<br>Return volatility (stock z 1.34, model rewards higher, +0.19)<br>Market Beta (stock z 1.62, model rewards lower, -0.54)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Price momentum t-6 to t-1 (stock z 3.98, model rewards lower, -0.21)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 0.8, model rewards lower, -0.16) |

### 3. PLTR Palantir Technologies Inc (SHORT)

> The portfolio entered a SHORT position on 2021-06-01 because the forecast was low, driven by low Operating profits-to-book assets, high Change in net financial assets, and high Dollar trading volume. The forecast pointed the same way as the trade. The position lost $21.21 million while the stock returned 576.5%, and the weight on 2026-08-31 was 0.0%.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-06-01 to 2025-08-19 (the largest spell by dollars) |
| Spell P&L | $-21.21m |
| All spells | 2 spells, 1290 trading days, first 2021-06-01, last 2026-07-21 |
| Total P&L 2021-2026 | $-23.3m (long days $-2.08m, short days $-21.21m) |
| P&L by year | 2021 $2.56m, 2022 $6.04m, 2023 $-4.57m, 2024 $-12.04m, 2025 $-12.98m, 2026 $-2.31m |
| Engine ledger price P&L (cross-check) | $-23.3m |
| Dividends, trading cost, borrow | $0.0m, $-0.07m, $-0.16m |
| Average weight while held | -0.409% |
| Largest absolute weight | 1.596% |
| Weight on 2026-08-31 | 0.0% |
| Stock return while held | 440.2% |
| Entry decision | 2021-05-28 (month-end), drivers from the 2021-05-31 refit |
| Forecast at entry | z -1.63, percentile 12 of 2566, rho 1.28, agrees with trade True |
| Drivers at entry | Change in financial liabilities (stock z -4.57, model rewards lower, +0.53)<br>Share turnover (stock z 0.98, model rewards higher, +0.20)<br>Operating profits-to-lagged book assets (stock z -1.52, model rewards lower, +0.19)<br>Return volatility (stock z 0.87, model rewards higher, +0.18)<br>Operating profits-to-book assets (stock z -2.28, model rewards higher, -0.73)<br>Change in net financial assets (stock z 3.74, model rewards lower, -0.71)<br>Dollar trading volume (stock z 5.95, model rewards lower, -0.40)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z 1.22, model rewards lower, -0.36) |

### 4. CEG Constellation Energy Corp (SHORT)

> The portfolio entered a short position on 2022-08-16 because the forecast was low, driven by high Idiosyncratic volatility from the Fama-French 3-factor model, high Idiosyncratic volatility from the q-factor model, and high Idiosyncratic skewness from the Fama-French 3-factor model. The strategy believed the forecast, which pointed the same way as the trade. The position lost $19.17 million while the stock returned 246.5%, and it had a weight of -0.891% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2022-08-16 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-19.17m |
| All spells | 1 spells, 1014 trading days, first 2022-08-16, last 2026-08-31 |
| Total P&L 2021-2026 | $-19.17m (long days $0.0m, short days $-19.17m) |
| P&L by year | 2022 $0.07m, 2023 $-3.27m, 2024 $-11.68m, 2025 $-7.14m, 2026 $2.85m |
| Engine ledger price P&L (cross-check) | $-18.89m |
| Dividends, trading cost, borrow | $-0.27m, $-0.07m, $-0.14m |
| Average weight while held | -0.855% |
| Largest absolute weight | 1.409% |
| Weight on 2026-08-31 | -0.891% |
| Stock return while held | 246.5% |
| Entry decision | 2022-08-15 (mid-month review), drivers from the 2022-07-31 refit |
| Forecast at entry | z -0.59, percentile 30 of 2263, rho 1.5, agrees with trade True, mid-month z -1.19 |
| Drivers at entry | Maximum daily return (stock z 2.44, model rewards higher, +0.55)<br>Return volatility (stock z 0.94, model rewards higher, +0.26)<br>Idiosyncratic skewness from the CAPM (stock z 2.52, model rewards higher, +0.15)<br>Idiosyncratic skewness from the q-factor model (stock z 1.87, model rewards higher, +0.08)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z 1.7, model rewards lower, -0.39)<br>Idiosyncratic volatility from the q-factor model (stock z 1.5, model rewards lower, -0.20)<br>Idiosyncratic skewness from the Fama-French 3-factor model (stock z 2.55, model rewards lower, -0.18)<br>Total skewness (stock z 3.07, model rewards lower, -0.14) |
| Forecast at 2026-07-31 refit | z -0.12, percentile 33, agrees with trade True |
| Drivers at 2026-07-31 | Standardized Revenue surprise (stock z 2.9, model rewards higher, +0.10)<br>Capital turnover (stock z -0.48, model rewards lower, +0.09)<br>Change in long-term net operating assets (stock z 2.48, model rewards higher, +0.09)<br>Market Equity (stock z 1.25, model rewards higher, +0.08)<br>Operating leverage (stock z -0.69, model rewards higher, -0.14)<br>Dollar trading volume (stock z 1.69, model rewards lower, -0.11)<br>Change in net noncurrent operating assets (stock z 1.86, model rewards lower, -0.08)<br>Price momentum t-9 to t-1 (stock z -1.01, model rewards higher, -0.07) |

### 5. WDC Western Digital Corp (SHORT)

> The portfolio entered a short position on 2021-09-01 because the forecast was low, driven primarily by high Market Beta, low Years 2-5 lagged returns, nonannual, and low Number of zero trades with turnover as tiebreaker (6 months). The strategy believed in the negative forecast, which pointed the same way as the trade. The position lost $16.23 million while the stock returned 885.7%, and it had a weight of -0.32% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-09-01 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-16.23m |
| All spells | 2 spells, 1268 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-16.22m (long days $0.0m, short days $-16.22m) |
| P&L by year | 2021 $-0.17m, 2022 $1.3m, 2023 $-2.45m, 2024 $-1.77m, 2025 $-8.57m, 2026 $-4.55m |
| Engine ledger price P&L (cross-check) | $-14.21m |
| Dividends, trading cost, borrow | $-2.01m, $-0.03m, $-0.22m |
| Average weight while held | -0.418% |
| Largest absolute weight | 1.119% |
| Weight on 2026-08-31 | -0.32% |
| Stock return while held | 867.8% |
| Entry decision | 2021-08-31 (month-end), drivers from the 2021-08-31 refit |
| Forecast at entry | z -0.63, percentile 29 of 2596, rho 1.5, agrees with trade True |
| Drivers at entry | Operating profits-to-book assets (stock z 0.7, model rewards higher, +0.25)<br>Mispricing factor: Performance (stock z 0.99, model rewards higher, +0.16)<br>Number of zero trades with turnover as tiebreaker (1 month) (stock z -1.25, model rewards lower, +0.14)<br>Long-term reversal (stock z -0.48, model rewards lower, +0.10)<br>Market Beta (stock z 0.31, model rewards lower, -0.20)<br>Years 2-5 lagged returns, nonannual (stock z -0.53, model rewards higher, -0.18)<br>Number of zero trades with turnover as tiebreaker (6 months) (stock z -0.91, model rewards higher, -0.15)<br>Liquidity of book assets (stock z -0.39, model rewards higher, -0.14) |
| Forecast at 2026-07-31 refit | z -0.84, percentile 17, agrees with trade True |
| Drivers at 2026-07-31 | Price momentum t-12 to t-1 (stock z 5.04, model rewards higher, +0.45)<br>Operating profits-to-book assets (stock z 1.82, model rewards higher, +0.35)<br>Return volatility (stock z 2.24, model rewards higher, +0.32)<br>Price momentum t-9 to t-1 (stock z 4.56, model rewards higher, +0.32)<br>Market Beta (stock z 1.58, model rewards lower, -0.53)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 2.09, model rewards lower, -0.42)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Highest 5 days of return (stock z 2.33, model rewards lower, -0.23) |

### 6. C Citigroup Inc (SHORT)

> The portfolio entered a short position on 2023-03-01 because the forecast was low, driven primarily by high Dollar trading volume, low Return volatility, and low Operating profits-to-book assets. The strategy believed in the short forecast at entry, though the forecast eventually pointed in the opposite direction of the position. This position lost $14.97 million while the stock returned 182.2%, and it held a weight of -0.806% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2023-03-01 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-14.97m |
| All spells | 3 spells, 1203 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-15.26m (long days $-0.4m, short days $-14.86m) |
| P&L by year | 2021 $0.2m, 2022 $-0.49m, 2023 $-1.59m, 2024 $-4.45m, 2025 $-7.07m, 2026 $-1.86m |
| Engine ledger price P&L (cross-check) | $-14.27m |
| Dividends, trading cost, borrow | $-0.99m, $-0.03m, $-0.12m |
| Average weight while held | -0.615% |
| Largest absolute weight | 1.189% |
| Weight on 2026-08-31 | -0.806% |
| Stock return while held | 140.1% |
| Entry decision | 2023-02-28 (month-end), drivers from the 2023-02-28 refit |
| Forecast at entry | z -0.86, percentile 24 of 2166, rho 1.5, agrees with trade True |
| Drivers at entry | Assets-to-market (stock z 4.77, model rewards higher, +0.53)<br>Market Equity (stock z 2.29, model rewards higher, +0.44)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.87, model rewards lower, +0.34)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.93, model rewards lower, +0.32)<br>Dollar trading volume (stock z 3.84, model rewards lower, -0.81)<br>Return volatility (stock z -0.96, model rewards higher, -0.36)<br>Operating profits-to-book assets (stock z -0.74, model rewards higher, -0.35)<br>Equity duration (stock z -2.01, model rewards higher, -0.34) |
| Forecast at 2026-07-31 refit | z 1.3, percentile 94, agrees with trade False |
| Drivers at 2026-07-31 | Ebitda-to-market enterprise value (stock z 1.29, model rewards higher, +0.32)<br>Market Equity (stock z 3.52, model rewards higher, +0.23)<br>Capital turnover (stock z -1.04, model rewards lower, +0.20)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.82, model rewards lower, +0.17)<br>Operating leverage (stock z -1.07, model rewards higher, -0.22)<br>Dollar trading volume (stock z 3.18, model rewards lower, -0.21)<br>Operating cash flow-to-market (stock z -1.07, model rewards higher, -0.15)<br>Operating profits-to-book assets (stock z -0.6, model rewards higher, -0.11) |

### 7. MRVL Marvell Technology Inc (SHORT)

> The portfolio entered a short position on 2024-06-18 based on a forecast z of -0.91, driven by high Market Beta, low Liquidity of book assets, and high Dollar trading volume. The strategy believed in the short forecast, which pointed the same way as the trade. The position lost $15.21 million while the stock returned 190.8%, and it held a weight of -0.981% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2024-06-18 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-15.21m |
| All spells | 1 spells, 552 trading days, first 2024-06-18, last 2026-08-31 |
| Total P&L 2021-2026 | $-15.21m (long days $0.0m, short days $-15.21m) |
| P&L by year | 2024 $-0.62m, 2025 $-0.19m, 2026 $-14.4m |
| Engine ledger price P&L (cross-check) | $-15.2m |
| Dividends, trading cost, borrow | $-0.01m, $-0.04m, $-0.04m |
| Average weight while held | -0.438% |
| Largest absolute weight | 1.695% |
| Weight on 2026-08-31 | -0.981% |
| Stock return while held | 190.8% |
| Entry decision | 2024-06-17 (mid-month review), drivers from the 2024-05-31 refit |
| Forecast at entry | z -0.91, percentile 21 of 2129, rho 1.5, agrees with trade True, mid-month z -1.03 |
| Drivers at entry | Capital turnover (stock z -0.77, model rewards lower, +0.28)<br>Earnings variability (stock z 4.73, model rewards higher, +0.26)<br>Asset tangibility (stock z -1.76, model rewards lower, +0.17)<br>Market Equity (stock z 0.96, model rewards higher, +0.14)<br>Market Beta (stock z 1.11, model rewards lower, -0.55)<br>Liquidity of book assets (stock z -1.37, model rewards higher, -0.42)<br>Dollar trading volume (stock z 2.92, model rewards lower, -0.36)<br>Operating leverage (stock z -0.77, model rewards higher, -0.30) |
| Forecast at 2026-07-31 refit | z -1.09, percentile 14, agrees with trade True |
| Drivers at 2026-07-31 | Return volatility (stock z 1.71, model rewards higher, +0.25)<br>Price momentum t-9 to t-1 (stock z 3.21, model rewards higher, +0.22)<br>Price momentum t-12 to t-1 (stock z 2.26, model rewards higher, +0.20)<br>Market Equity (stock z 2.44, model rewards higher, +0.16)<br>Market Beta (stock z 1.78, model rewards lower, -0.60)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z 1.36, model rewards lower, -0.28)<br>Price momentum t-6 to t-1 (stock z 4.74, model rewards lower, -0.25) |

### 8. GE General Electric Co (SHORT)

> The portfolio entered a short position on 2023-08-16 based on a forecast z of -0.34, driven by high Dollar trading volume, high Equity net payout, and high Firm age. The strategy's forecast pointed the same way as the trade at entry. The position lost $14.8 million while the stock returned 276.5%, and it had a weight of -0.241% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2023-08-16 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-14.8m |
| All spells | 2 spells, 1164 trading days, first 2021-11-01, last 2026-08-31 |
| Total P&L 2021-2026 | $-14.83m (long days $-0.02m, short days $-14.8m) |
| P&L by year | 2021 $-0.27m, 2022 $-0.77m, 2023 $-0.66m, 2024 $-6.67m, 2025 $-5.92m, 2026 $-0.54m |
| Engine ledger price P&L (cross-check) | $-12.65m |
| Dividends, trading cost, borrow | $-2.18m, $-0.03m, $-0.08m |
| Average weight while held | -0.318% |
| Largest absolute weight | 1.168% |
| Weight on 2026-08-31 | -0.241% |
| Stock return while held | 387.0% |
| Entry decision | 2023-08-15 (mid-month review), drivers from the 2023-07-31 refit |
| Forecast at entry | z -0.34, percentile 34 of 2174, rho 1.5, agrees with trade True, mid-month z -0.63 |
| Drivers at entry | Market Equity (stock z 2.82, model rewards higher, +0.52)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.8, model rewards lower, +0.30)<br>Price momentum t-9 to t-1 (stock z 1.77, model rewards higher, +0.30)<br>Capital turnover (stock z -0.74, model rewards lower, +0.24)<br>Dollar trading volume (stock z 2.51, model rewards lower, -0.46)<br>Equity net payout (stock z 1.98, model rewards lower, -0.43)<br>Firm age (stock z 3.04, model rewards lower, -0.25)<br>Residual momentum t-12 to t-1 (stock z 2.43, model rewards lower, -0.23) |
| Forecast at 2026-07-31 refit | z -0.0, percentile 38, agrees with trade False |
| Drivers at 2026-07-31 | Market Equity (stock z 6.02, model rewards higher, +0.40)<br>Idiosyncratic volatility from the CAPM (21 days) (stock z -0.75, model rewards lower, +0.15)<br>Years 2-5 lagged returns, nonannual (stock z 1.48, model rewards higher, +0.12)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.71, model rewards lower, +0.12)<br>Dollar trading volume (stock z 3.27, model rewards lower, -0.22)<br>Market Beta (stock z 0.43, model rewards lower, -0.14)<br>Long-term reversal (stock z 2.87, model rewards lower, -0.13)<br>Operating leverage (stock z -0.56, model rewards higher, -0.12) |

### 9. STT State Street Corp (SHORT)

> The portfolio entered a short position on 2021-01-04 based on a forecast z of -0.77, driven by low Equity duration, high Payout yield, and high Market Beta. The strategy's forecast pointed the same way as the trade at entry. The position lost $14.03 million while the stock returned 208.7%, and it held a weight of -1.06% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-01-04 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-14.03m |
| All spells | 1 spells, 1421 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-14.03m (long days $0.0m, short days $-14.03m) |
| P&L by year | 2021 $-0.42m, 2022 $0.11m, 2023 $-0.23m, 2024 $-2.13m, 2025 $-5.15m, 2026 $-6.21m |
| Engine ledger price P&L (cross-check) | $-13.32m |
| Dividends, trading cost, borrow | $-0.71m, $-0.03m, $-0.11m |
| Average weight while held | -0.463% |
| Largest absolute weight | 1.173% |
| Weight on 2026-08-31 | -1.06% |
| Stock return while held | 208.7% |
| Entry decision | 2020-12-31 (month-end), drivers from the 2020-12-31 refit |
| Forecast at entry | z -0.77, percentile 20 of 2256, rho 1.15, agrees with trade True |
| Drivers at entry | Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.61, model rewards lower, +0.28)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.67, model rewards lower, +0.28)<br>Cash-based operating profits-to-book assets (stock z -0.84, model rewards lower, +0.24)<br>Capital turnover (stock z -1.03, model rewards lower, +0.20)<br>Equity duration (stock z -1.27, model rewards higher, -0.28)<br>Payout yield (stock z 2.99, model rewards lower, -0.21)<br>Market Beta (stock z 0.29, model rewards lower, -0.17)<br>Mispricing factor: Performance (stock z -0.76, model rewards higher, -0.15) |
| Forecast at 2026-07-31 refit | z 0.54, percentile 64, agrees with trade False |
| Drivers at 2026-07-31 | Idiosyncratic volatility from the CAPM (21 days) (stock z -1.13, model rewards lower, +0.23)<br>Capital turnover (stock z -1.05, model rewards lower, +0.20)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.99, model rewards lower, +0.17)<br>Idiosyncratic volatility from the Fama-French 3-factor model (stock z -0.97, model rewards lower, +0.13)<br>Operating leverage (stock z -1.08, model rewards higher, -0.22)<br>Market Beta (stock z 0.47, model rewards lower, -0.16)<br>Operating profits-to-book assets (stock z -0.63, model rewards higher, -0.12)<br>Return volatility (stock z -0.78, model rewards higher, -0.11) |

### 10. ORCL Oracle Corp (SHORT)

> The portfolio entered a short position on 2021-08-02 because high Dollar trading volume, high Highest 5 days of return scaled by volatility, and high Intrinsic value to price lowered the forecast. The forecast did not point the same way as the trade, but the optimiser held it for the book's limits or risk. The position lost $14.01 million while the stock returned 80.4%, and it had a weight of -0.683% on 2026-08-31.

Numbers checked against facts: yes

| Fact | Value |
|---|---|
| Spell in view | SHORT 2021-08-02 to 2026-08-31 (the largest spell by dollars) |
| Spell P&L | $-14.01m |
| All spells | 2 spells, 1290 trading days, first 2021-01-04, last 2026-08-31 |
| Total P&L 2021-2026 | $-14.02m (long days $-0.02m, short days $-14.01m) |
| P&L by year | 2021 $0.21m, 2022 $0.11m, 2023 $-3.46m, 2024 $-7.01m, 2025 $-4.91m, 2026 $1.04m |
| Engine ledger price P&L (cross-check) | $-13.42m |
| Dividends, trading cost, borrow | $-0.6m, $-0.04m, $-0.17m |
| Average weight while held | -0.846% |
| Largest absolute weight | 1.379% |
| Weight on 2026-08-31 | -0.683% |
| Stock return while held | 73.0% |
| Entry decision | 2021-07-30 (month-end), drivers from the 2021-07-31 refit |
| Forecast at entry | z 0.9, percentile 96 of 2590, rho 0.66, agrees with trade False |
| Drivers at entry | Market Equity (stock z 6.35, model rewards higher, +0.49)<br>Market Beta (stock z -0.89, model rewards lower, +0.48)<br>Operating profits-to-book assets (stock z 0.83, model rewards higher, +0.24)<br>Idiosyncratic volatility from the CAPM (252 days) (stock z -0.84, model rewards lower, +0.22)<br>Dollar trading volume (stock z 3.89, model rewards lower, -0.26)<br>Highest 5 days of return scaled by volatility (stock z 2.08, model rewards lower, -0.19)<br>Intrinsic value to price (stock z 6.26, model rewards lower, -0.18)<br>Short-term reversal (stock z 1.46, model rewards lower, -0.15) |
| Forecast at 2026-07-31 refit | z -0.45, percentile 24, agrees with trade True |
| Drivers at 2026-07-31 | Market Equity (stock z 6.03, model rewards higher, +0.40)<br>Capital turnover (stock z -0.63, model rewards lower, +0.12)<br>Years 2-5 lagged returns, nonannual (stock z 1.12, model rewards higher, +0.09)<br>Change in net financial assets (stock z -1.57, model rewards lower, +0.09)<br>Dollar trading volume (stock z 6.09, model rewards lower, -0.40)<br>Market Beta (stock z 0.93, model rewards lower, -0.31)<br>Operating leverage (stock z -0.88, model rewards higher, -0.18)<br>Operating profits-to-lagged book assets (stock z 0.76, model rewards lower, -0.10) |
