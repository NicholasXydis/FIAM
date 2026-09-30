# The project in plain terms

**What it is.** A market-neutral book of US stocks. Each month we rank every stock on twelve
well-known measures (cheap, profitable, careful with money, rising), buy the best and short the
worst: about <!--N:metrics.json:compliance.positions_average:.0f-->276<!--/N--> names, as much long
as short, neutral to the market and to every sector, with every trading cost charged.

**What the AI adds.** FinBERT reads every 8-K filing. Local AI agents triage filings, act as analysts
and play the "AI crowd". A stock picker learns from all of it. A rule we wrote before seeing any
result decides each year whether the learned books replace the simple one.
<!--AUTO:shipped-->

It shipped the composite in all 6 years: no learned book beat it clearly.

<!--/AUTO:shipped-->

## Results

<!--AUTO:brief-->

|  |  |
|---|---|
| Net return | **12.5% a year** after every modelled fee |
| Information ratio | **0.69** |
| Alpha | 12.9% a year, t = 2.23 |
| Beta to the S&P 500, monthly | -0.04, standard error 0.09 |
| Beta, daily returns 2021-25 | -0.10, t = -3.5: a short market tilt |
| Worst drawdown | -11.0% |
| Split in half | 2021-22 IR 1.74, 2023-26 IR -0.11 |
| CRSP years only | 2021-25 IR 0.62 |
| 2016-2020, a historical check | IR -1.00, beta -0.25 (se 0.07) |

<!--/AUTO:brief-->

**The honest reading.** Most of the return comes from one style, quality and value. It paid in
2021-22, was flat in 2023-26 while the AI rally favoured expensive growth, and lost money in
2016-2020, value's worst stretch in decades. We show this rather than hide it.

## What is new here

1. **Costs like a real fund.** Interactive Brokers' prices, spreads from real quotes, market impact
   that grows with trade size, borrow fees by how shorted a stock is.
2. **Rules written before the test.** Every upgrade was written down first and judged once. Two of
   ours failed and were dropped.
3. **Old data helps new decisions.** Small models learn what data that ends in 2025 would say, so it
   still informs 2026.
4. **AI you can check.** Names and dates are hidden from the models, and a probe measures whether
   they recognise the company anyway.
5. **The same numbers on any machine**, checked by an audit on every run.

## The agents

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Signal discovery** | Qwen3.8-27B | real names: 8 backtests, best in sample 1.14, sealed IR **-2.08**; coded names: 0 backtests, sealed IR **-1.82**; random search, same budget, sealed IR -0.44 |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 quoting a number no tool showed; run twice, 5 of 5 calls identical |
| **Reproducibility** | Qwen3.8-27B | found **0 of 7** planted bugs; 10 false alarms on the clean copy |

_From the earlier harness (Hermes Agent); the next `--all` run replaces them._

<!--/AUTO:agents-->

## Limits

A backtest anyone can rerun, not a live record. Costs are modelled, not observed. 2026 returns come
from Compustat, not CRSP. We saw both 2016-2020 and 2021-2026 while building, so neither is a
perfectly clean test.
