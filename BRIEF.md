# The project in plain terms

McGill-FIAM Hackathon 2026: eleven years of monthly data on 6,500 US stocks, 147 numbers each.

**What we built.** Each month we score every stock on twelve classical measures (volatility,
cheapness, profitability, asset growth, share issuance and more), remove the sector bet and the
market bet, and let an optimizer build about 316 positions, half long and half short, in whole
shares, with every cost charged. **No trained model and no AI touches a position.**

## What it returns

<!--AUTO:brief-->

|  |  |
|---|---|
| Net return | **16.1% a year** after every modelled fee |
| Information ratio | **0.83** |
| Alpha | 16.6% a year, t = 2.40 |
| Beta to the S&P 500 | -0.05, standard error 0.11 |
| Worst drawdown | -12.8% |
| Split in half | 2021-22 IR 1.87, 2023-26 IR +0.06 |
| CRSP years only | 2021-25 IR 0.76 |
| 2016-2020, never looked at | IR -0.82, beta -0.30 (se 0.09) |

<!--/AUTO:brief-->

**Read the last three rows.** The second half earned about nothing, the CRSP years alone earn less,
and the same code on 2016-2020, never looked at, lost money. The record is honest arithmetic, not
proof it works everywhere: a value, quality and defensive tilt that earns when that regime pays.

## What makes it different

1. **Our first book looked neutral and was not** (promised beta 0, real −0.52). Now the real beta
   fails the build.
2. **The machine-learning version predicts as well and loses money**, on trading costs.
3. **We could have shown a higher number and did not**: picking signals on the past picks badly.
4. **We checked the data against WRDS** and the book barely moved.
5. **We tried to make our result look fake and could not**, and a 28-check audit guards the build.

## The agents

Three local AI agents, run through Hermes, each judged on something it cannot fake:

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Signal discovery** | Qwen3.8-27B | real names: 8 backtests, best in sample 1.14, sealed IR **-2.08**; coded names: 0 backtests, sealed IR **-1.82**; random search, same budget, sealed IR -0.44 |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 quoting a number no tool showed; run twice, 5 of 5 calls identical |
| **Reproducibility** | Qwen3.8-27B | found **0 of 7** planted bugs; 10 false alarms on the clean copy |

<!--/AUTO:agents-->

## What we cannot claim

Research backtests, not a sealed out-of-sample record; costs modelled, not observed; 2026 returns
from Compustat, not CRSP. The only clean test is live: our September book is hashed, and October
2026 scores it.
