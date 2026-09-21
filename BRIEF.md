# The project in plain terms

McGill-FIAM Asset Management Hackathon 2026. Eleven years of monthly data on 6,500 US stocks,
147 numbers each, plus 373,000 filings.

## What we built

Every month we score each stock on twelve classical measures, things like volatility,
cheapness, profitability, asset growth and share issuance, then average all twelve.

Then we strip two things out of that score. The **sector bet**, so we are not accidentally long
tech and short energy. And the **market bet**, because "buy calm stocks, short wild ones" is
secretly a bet that the market falls.

An optimizer turns the scores into positions under hard limits: zero net exposure, 200% gross,
beta near zero, no sector above 1% of the book, no position above 1.5%. About 253 stocks, half
long and half short, rounded to whole shares. No trained model touches any of it. It is
arithmetic a judge can check by hand.

## What it returns

Straight from the code, full detail in `RESULTS.md`.

|                   |                                                                 |
| ----------------- | --------------------------------------------------------------- |
| Net return        | **14.3% a year** after every modelled fee                       |
| Information ratio | **0.73**, the headline number                                   |
| Sharpe ratio      | 1.01                                                            |
| Alpha             | 16.1% a year, t = 2.28                                          |
| Beta              | −0.10, standard error 0.10, so statistically zero               |
| Worst drawdown    | −14.1%                                                          |
| By year           | 2021 +49%, 2022 +36%, 2023 +12%, 2024 −5%, 2025 flat, 2026 +18% |

Costs eat 25% of the gross return: commission, spread, borrow fees on the shorts, an extra
charge on the 21% that are hard to borrow, and market impact. No borrow rate here is observed
data, every one is a stress assumption, and we say so.

## The three things that make us different

All three are the same finding: **things that look better are not.**

**1. Our first book looked neutral and was not.** Reported beta −0.002, real beta −0.52. It made
+17.7% in a month the market fell 9.4%. We had neutralised the obvious measure of market
sensitivity, but the book was still tilted away from volatile stocks, and volatile stocks _are_
market sensitivity. Fixing it moved beta to −0.10 and improved everything else: IR 0.47 to 0.73,
drawdown −35% to −14%.

**2. We built the machine-learning version and it lost.**

|                       | prediction skill    | what is scored |
| --------------------- | ------------------- | -------------- |
| **Our factor score**  | t = 3.10            | **IR +0.73**   |
| Gradient-boosted tree | t = 2.99            | IR −1.80       |
| Neural network        | **t = 4.47** (best) | IR −1.75       |

They predict better and lose money, because they rank the middle of the pack well and we only
trade the extremes. We ship the simple model and keep them as evidence.

**3. We could have shown a higher number and did not.** Across all 792 five-signal combinations
the IR ranged 0.03 to 0.96, purely on which five you pick, and past IR correlates −0.48 with
future IR. So we use all twelve and there is nothing to cherry-pick.

## What did not work, and what we cannot claim

Momentum is statistically dead in this period. Filing sentiment looked real until we removed the
sector and market bets, then vanished. Predicting fundamentals instead of returns, which the
rules suggest, beat nothing. Volatility targeting and turnover control both made things worse.

These are research backtests, not a sealed out-of-sample record, because we made design choices
while able to see the 2021-2026 results. The deflated Sharpe, which asks whether a result
survives how many things you tried, is 0.52 on the choices that fed the book and 0.20 counting
everything we ever ran. Encouraging under one count, inconclusive under the other. We report both.

**Still waiting on WRDS.** The rules ask for beta against the S&P 500. We use Ken French's broad
market series and label it honestly, because the free S&P data has no dividends in it. WRDS
access through McGill fixes that and adds daily data for better risk numbers. Requested, not
granted, and nothing else is waiting on it.

## Running it

    python run.py    # builds the portfolio, updates RESULTS.md, draws the charts

The pipeline stops if any competition limit breaks, so a clean run means the book is compliant.
`MAIN.py`, the single file the rules want, is assembled from `src/` at the end.

## How it is judged

Mostly on originality, choice of technology, and whether the backtest was done properly, and
they check the book is really neutral before anything else. The panel is people aged 40+, almost
all finance, so it has to survive being pitched in ninety seconds:

> _We run a sector- and beta-neutral book of 253 US stocks, ranked on twelve classical factors
> with the market bet stripped out. We also built the machine-learning version. It predicted
> better and lost money, because its skill is in the middle of the distribution and a long-short
> book only trades the tails. Our first pipeline also looked neutral and had a real beta of
> −0.52. We found it, fixed it, and show you both numbers._
