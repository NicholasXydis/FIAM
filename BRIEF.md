# The project in plain terms

McGill-FIAM Hackathon 2026: eleven years of monthly data on 6,500 US stocks, 147 numbers each.

**What we built.** Each month we score every stock on twelve classical measures, remove the sector
and market bets, and let an optimizer build about
<!--N:metrics.json:compliance.positions_average:.0f-->276<!--/N--> positions, half long, half short,
in whole shares, every cost charged, at a gross that never passed 200% on any trading day we could
measure. Machine learning adds a learned ranking, a learned hedge and a learned trader as candidates;
a rule written before any of them was scored decides each year which book ships.
<!--AUTO:shipped-->

It shipped the composite in all 6 years: no learned book beat it clearly.

<!--/AUTO:shipped-->

## What it returns

<!--AUTO:brief-->

|  |  |
|---|---|
| Net return | **13.6% a year** after every modelled fee |
| Information ratio | **0.79** |
| Alpha | 14.1% a year, t = 2.46 |
| Beta to the S&P 500, monthly | -0.05, standard error 0.09 |
| Beta, daily returns 2021-25 | -0.10, t = -3.5: a short market tilt |
| Worst drawdown | -10.5% |
| Split in half | 2021-22 IR 1.81, 2023-26 IR +0.03 |
| CRSP years only | 2021-25 IR 0.71 |
| 2016-2020, not designed on | IR -0.83, beta -0.25 (se 0.07) |

<!--/AUTO:brief-->

**Read the last rows.** The second half earned far less, and the same code lost money on
2016-2020, which the signals were never designed on. It is a value, quality and defensive tilt that
earns when that style pays.

## What makes it different

1. **Learning has to earn its place.** A learned ranking, hedge and trader are candidates, never
   defaults; the rule above decides, and every attempt counts in the multiple-testing ledger.
2. **Data that stops in 2025 still helps in 2026**, through teachers: models that learn what the
   daily prices, short interest and analyst data would say, from inputs that reach 2026. One of them
   decides which shorts pay hard-to-borrow rates in the book we ship.
3. **We measure the AI crowd instead of joining it.** Our local models play AI assistants picking
   stocks from anonymous cards; a small model learns where they buy, and we measure what betting
   against them is worth.
4. **Machine learning predicts as well and loses money on trading costs**, so a trader retrained
   every month on the months already paid for is tested as a candidate.
5. **Agents do research, not trading.** A research-director agent picks each year's book from
   earlier months only, and is scored against our rule and against chance.
6. **Neutral by construction, and measured.** Our first book looked neutral and was not (promised
   beta 0, real −0.52); now a real beta outside ±0.20 fails the build, and daily returns still show
   the small short tilt in the table above.
7. **The same code and data give the same numbers on any machine**, and an audit guards the
   build.

## The agents

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Signal discovery** | Qwen3.8-27B | real names: 8 backtests, best in sample 1.14, sealed IR **-2.08**; coded names: 0 backtests, sealed IR **-1.82**; random search, same budget, sealed IR -0.44 |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 quoting a number no tool showed; run twice, 5 of 5 calls identical |
| **Reproducibility** | Qwen3.8-27B | found **0 of 7** planted bugs; 10 false alarms on the clean copy |

_From the earlier harness (Hermes Agent); the next `--all` run replaces them._

<!--/AUTO:agents-->

## What we cannot claim

Research backtests that anyone can rerun to the same numbers, not a live record. Costs are
modelled, not observed. 2026 returns come from Compustat, not CRSP.
