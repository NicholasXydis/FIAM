# The project in plain terms

**What it is.** A market-neutral book of US stocks. Each month we rank every stock on twelve
published measures of value, quality, investment and momentum, buy the best and short the worst:
about <!--N:metrics.json:compliance.positions_average:.0f-->296<!--/N--> names, as much long as short,
neutral to every sector and hedged to zero beta with a beta our machine learning learned from daily
prices. Every trade pays broker-level costs.

<!--AUTO:brief-->

|  |  |
|---|---|
| Net return | **12.8% a year** after every modelled fee |
| Information ratio | **0.74** |
| Information ratio before costs | 1.16 |
| Alpha | 13.1% a year, t = 2.35 |
| Beta, daily returns 2021-25 | -0.10, t = -3.7: a short market tilt |
| Beta to the S&P 500, monthly | -0.03, standard error 0.09 |
| Worst drawdown | -7.4% |
| Split in half | 2021-22 IR 1.63, 2023-26 IR -0.01 |
| CRSP years only | 2021-25 IR 0.69 |
| 2016-2020, a historical check | IR -1.00, beta -0.25 (se 0.07) |

<!--/AUTO:brief-->

## What the AI does

- **The hedge.** A small model learns each stock's next-month beta from daily returns, and the book
  is neutral to it. It is the one learned part of the book we ship.
- **A firewall against recall.** No language model's reading of a 2021-2026 filing reaches the book:
  the agents judged older filings, and small models learned their judgments. The analyst named the
  company in <!--N:exhibits/analyst.json:look_ahead_probe.company_named:.0%-->4%<!--/N--> of masked
  filings, and its 2021-2026 verdicts predict nothing (IC
  <!--N:exhibits/analyst_learned.json:recall_test.2021-2026.analyst.rank_correlation:+.3f-->−0.003<!--/N-->).
- **The AI crowd.** Two AI models, playing retail stock pickers on anonymous cards, mostly buy
  quality. <!--N:exhibits/pack.json:crowding.long.share_in_top_crowd_decile:.0%-->42%<!--/N--> of our
  longs sit in their favourite tenth: the crowding the brief warns about, measured.
- **The stock picker.** A machine-learning ranker predicts next month's returns (IC
  <!--N:exhibits/scorer.json:ic_2021_2026.ic_mean:.3f-->0.067<!--/N-->, t
  <!--N:exhibits/scorer.json:ic_2021_2026.ic_t:.2f-->3.55<!--/N-->) but trades too much to beat the
  composite after costs. Keeping it to cheap-to-trade names is our next step.

## The honest reading

Style carries much of the return: the same quality-and-value tilt that paid in 2021-22 returned
<!--N:exhibits/confirmation.json:confirmation_2016_2020.net_by_year.2020:.0%-->−29%<!--/N--> in 2020.
We tried <!--N:metrics.json:robustness.attempts_all:,-->1,665<!--/N--> fits before choosing this book,
and after counting them the chance its edge is real is
<!--N:metrics.json:robustness.deflated_sharpe_probability_eligible:.0%-->46%<!--/N-->. RESULTS.md
lists what we tried and what each idea did.

**Limits.** A backtest anyone can rerun, not a live record. Costs are modelled, not observed. 2026
returns come from Compustat, not CRSP.
