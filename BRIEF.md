# The project in plain terms

McGill-FIAM Asset Management Hackathon 2026. Eleven years of monthly data on 6,500 US stocks,
147 numbers each, plus 373,000 filings.

## What we built

Every month we score each stock on twelve classical measures, things like volatility,
cheapness, profitability, asset growth and share issuance, then average all twelve.

Then we strip two things out. The **sector bet**, so we are not accidentally long tech and
short energy. And the **market bet**, because "buy calm stocks, short wild ones" is secretly a
bet that the market falls.

An optimizer turns the scores into positions under hard limits: zero net exposure, 200% gross,
beta near zero, no sector above 1% of the book, no position above 1.5%. About 316 stocks, half
long and half short, rounded to whole shares. **No trained model touches any of it.**

## What it returns

| | |
|---|---|
| Net return | **16.3% a year** after every modelled fee |
| Information ratio | **0.85** |
| Sharpe ratio | 1.12 |
| Alpha | 18.2% a year, t = 2.57 |
| Beta | -0.11, standard error 0.11, so statistically zero |
| Worst drawdown | -12.5% |
| Split in half | 2021-22 IR 1.87, 2023-26 IR +0.08. We show both |

Costs eat 19% of gross: commission, spread, borrow fees, an extra charge on the 21% that are
hard to borrow, and market impact. **No borrow rate here is observed data**, every one is a
stress assumption. They would have to reach 16.2% a year, 4.2 times what we assume, before we
stopped beating the benchmark.

## The five things that make us different

All five are the same finding: **things that look better are not.**

**1. Our first book looked neutral and was not.** Reported beta -0.002, real beta **-0.52**. It
made +17.7% in a month the market fell 9.4%. We had neutralised the obvious measure of market
sensitivity, but the book was still tilted away from volatile stocks, and volatile stocks *are*
market sensitivity. Fixing it moved beta to -0.10 and lifted IR 0.47 to 0.73. A later fix to
how the optimizer treats positions it already holds took it to 0.85.

**2. We built the machine-learning version and it lost.**

| | prediction skill | what is scored |
|---|---|---|
| **Our factor score** | t = 3.77 | **IR +0.85** |
| Penalised linear | t = 2.55 | IR -0.52 |
| Gradient-boosted tree | t = 3.60 | IR -0.37 |
| Neural network | **t = 3.89** (best) | IR -0.24 |

The neural network ranks stocks better than we do. **It loses on the trading bill, not on the
neutrality rules.** We measured every stage: taking out the sector, market and volatility bets
actually *helps* all three models. What sinks them is turnover. They re-rank the market every
month, trading at 99-121% against our 50%, on a third of our gross return, so costs eat 84-178%
of everything they earn.

We then tried to fix that by slowing them down. The best of 15 attempts reached IR -0.15,
still far below ours. The neural network's number also moves with its random seed: five seeds
give -1.38 to -0.24, and the one above is the **best** of them.

**3. We could have shown a higher number and did not.** Across all 792 five-signal combinations
the IR ranged 0.45 to 1.26, purely on which five you pick, and past IR correlates **-0.36** with
future IR. So we use all twelve and there is nothing to cherry-pick.

**4. We reproduced the failure the rules warn about, with no model at all.** A **deterministic
random search**, not an LLM: 200 signal combinations, three years to look at, then a period it
had never seen. Its pick scored **+1.78** where it could look and **+0.33** afterwards, ranking
54 of 200. A second script audits our own work: seventeen look-ahead checks that fail the build,
which have caught three real regressions, one of them twice.

**5. We tried to make our own result look fake, and could not.** We ran the identical pipeline
200 times on shuffled scores. Those runs earned **+0.36% a year** before costs against our
20.2%, so the machinery does not manufacture returns. Inverting every score loses **-20.2%**,
the mirror of what we make, which is what a real signal must do. Trading last month's ranking
keeps 81% of the gross but only half the risk-adjusted return, so the signal is slow-moving.
That last one is a real caveat and we say so rather than leave it to be found.

**None of these is an LLM agent and we do not call them one.** They are controls that stand in
for an agent, with no model in the loop. Nothing they produce is an input to the book.

## What did not work, and what we cannot claim

Momentum is statistically dead in this period. Filing sentiment looked real until we removed
the sector and market bets, then vanished. Predicting fundamentals instead of returns, which
the rules suggest, beat nothing. Volatility targeting and turnover control both made it worse.

These are research backtests, not a sealed out-of-sample record, because we made design choices
while able to see the 2021-2026 results. The deflated-Sharpe probability, which asks how likely
a result is to be real given how many things you tried, is **0.58** counting the 85 attempts
that could have become the book and **0.25** counting all 1,328 fits we ever ran. Encouraging
under one count, inconclusive under the other. We report both, and the ledger adds up to both.

**Still waiting on WRDS.** The rules ask for beta against the S&P 500. We use Ken French's broad
market series and label it honestly, because the free S&P data has no dividends. WRDS through
McGill fixes that and adds daily data. Requested, not granted, and nothing else waits on it.

## Running it

    python run.py    # builds the portfolio, updates RESULTS.md, draws the charts

The pipeline stops if any competition limit breaks, so a clean run means the book is compliant.
`MAIN.py`, the single file the rules want, is assembled from `src/` at the end.

## How it is judged

Mostly on originality, choice of technology, and whether the backtest was done properly. They
check the book is really neutral before anything else. The panel is 40+, almost all finance, so
it has to survive ninety seconds:

> _We run a sector- and beta-neutral book of 316 US stocks, ranked on twelve classical factors
> with the market bet stripped out. We also built the machine-learning version. It predicted
> better and still lost money, and we can show you the exact stage where: not neutralization,
> which helps it, but costs. It re-ranks the market every month and trades at twice our
> turnover on a third of our gross return. Our first pipeline also looked neutral and had a
> real beta of -0.52. We found it, fixed it, and show you both numbers._
