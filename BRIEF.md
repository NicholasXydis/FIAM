# The project in plain terms

**What it is.** A market-neutral book of US stocks. Each month we rank every stock on twelve
well-known measures (cheap, profitable, careful with money, rising), buy the best and short the
worst: about <!--N:metrics.json:compliance.positions_average:.0f-->272<!--/N--> names, as much long
as short, neutral to the market and to every sector, with every trading cost charged.

**What the AI adds.** FinBERT reads every 8-K filing. Local AI agents triage filings, act as analysts
and play the "AI crowd". A stock picker learns from all of it. A rule we wrote before seeing any
result decides each year whether the learned books replace the simple one.
<!--AUTO:shipped-->

It shipped Composite + 50% scorer + hedge + trader in 2021; Composite + hedge in 2023; Composite + hedge in 2025; Screen-then-rank in 2026, and the composite in the other years.

<!--/AUTO:shipped-->

## Results

<!--AUTO:brief-->

|  |  |
|---|---|
| Net return | **7.8% a year** after every modelled fee |
| Information ratio | **0.34** |
| Alpha | 8.4% a year, t = 1.68 |
| Beta to the S&P 500, monthly | -0.06, standard error 0.09 |
| Beta, daily returns 2021-25 | -0.10, t = -3.7: a short market tilt |
| Worst drawdown | -11.0% |
| Split in half | 2021-22 IR 0.99, 2023-26 IR -0.20 |
| CRSP years only | 2021-25 IR 0.32 |
| 2016-2020, a historical check | IR -1.00, beta -0.25 (se 0.07) |

<!--/AUTO:brief-->

**The honest reading.** Two things shape this record. First, style: about half of 2021-22 came
from quality and value, and the same tilt lost heavily in 2020, almost all of 2016-2020's loss.
Second, our own rule: twice, after the composite's worst stretches, it moved to the book that had
lost less (the stock picker for 2021, screen-then-rank for 2026), just before the composite
rebounded. The composite kept every year scores IR 0.70; the rule's book, which we ship because we
wrote the rule first, scores 0.34. The 2024 loss was stock-specific, mostly squeezes on our shorts, not style.

## What is new here

1. **Costs like a real fund.** Interactive Brokers' prices, spreads from real quotes, market impact
   that grows with trade size, borrow fees by how shorted a stock is.
2. **Rules written before the test.** Every upgrade was written down first and judged once. Two of
   ours failed and were dropped, and we ship our rule's choice even though it cost us.
3. **Old data helps new decisions.** Small models learn what data that ends in 2025 would say, so it
   still informs 2026.
4. **AI that cannot remember the answer.** No language model's reading of a 2021-2026 filing
   reaches the book: the agents judge older filings, and small models learn those judgments and
   do the scoring. Names and dates are hidden; the analyst named the company in 4% of 500 masked
   filings, and its own 2021-2026 verdicts predict nothing (IC -0.003), so it was not remembering.
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
