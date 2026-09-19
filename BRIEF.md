# What we're doing, in plain terms

## The competition

They give us eleven and a half years of data on about 6,500 US stocks — 147
numbers per stock per month (things like price-to-book, momentum, volatility) — plus 373,000 company
filings. We have to build a strategy that picks stocks, and hand in a slide deck showing it works.

## The strategy

We buy 150 stocks we think will go up and short 150 we think will go down, equal amounts on each side.
When the market rises, our longs gain and our shorts lose. When it falls, the opposite. **The market's
direction cancels out, and what's left is whether we picked better stocks than we shorted.**

That's called market neutral, and it's mandatory this year. We're not trying to beat the S&P 500. We're
trying to beat cash plus 4% a year, with a book that doesn't move with the market.

## How we pick the stocks

Three things, and a stock only gets a full-size position when they agree.

**1. Predict next month's return** from the 147 numbers. Three different models — a simple linear one,
a gradient-boosted tree, and a small neural network — then blend them.

**2. Predict earnings surprises.** Companies that beat expectations tend to keep rising for months after.
Everyone knows this; the hard part is knowing _when_ the next earnings report lands. Most teams will guess.
We don't have to — 120,000 of those filings are earnings announcements with real dates on them, so we know
exactly when each company reports. **That's our best original idea.**

**3. Read the filings.** Score them for tone, and run an AI model over the important ones to judge whether
each disclosure actually matters and which way. One hard rule: if a company changes auditor or admits its
old financials were wrong, we exit the position regardless of what the models say.

## What we're actually using

**For predicting returns**, three models. ElasticNet is regression with guardrails so it doesn't overfit,
and it's the competition's own baseline. LightGBM builds hundreds of small decision trees, each one fixing
the last one's mistakes. And a small neural network, which is what the paper the organisers cite found
worked best. A fourth tiny model then learns how much to trust each of the three. All of it runs on a
normal CPU in minutes.

**For reading filings**, three approaches and we keep whichever wins. A finance word list from 2011 as the
baseline. FinBERT-tone, an AI model trained on actual company filings rather than news headlines. And one
that turns each filing into numbers capturing its meaning, then hands those to LightGBM. It all runs once
on a free cloud GPU and gets cached, so we only pay the time cost once.

**The local AI:** Qwen3-14B from Alibaba rates about 9,000 filings — material or not, good or bad news,
how confident, plus a quoted sentence as evidence. Llama-3.1-8B from Meta does the same job as a second
opinion. Different companies, different training data, which is the whole point. Runs through `llama.cpp`
on the Vulkan backend, because the usual AI toolchain is painful on AMD cards and Vulkan sidesteps it.
Roughly six hours overnight, then cached forever. (Can use my 9070xt)

**Data we fetch:** the T-bill rate from the St. Louis Fed and S&P 500 returns from Ken French's data
library, both free and no signup. Daily prices for twenty stocks from Tiingo, free account. Everything
else was given to us.

**Python:** pyarrow, pandas, scikit-learn, lightgbm, statsmodels, matplotlib, shap, cvxpy, requests,
tiingo. Plus `llama.cpp`, which is a separate program.

## The AI part, and why we're doing it differently

This year's competition theme is AI agents. The organisers also warn about the obvious failure: if every
team asks ChatGPT what it likes, everyone ends up holding the same stocks and they all crash together.

**So we run our AI locally on a graphics card (I can use my 9070xt 16gb) instead of calling an API.** That gives us three things nobody using a cloud model can claim:

- It's free, so we can run it across 9,000 filings
- It's exactly reproducible — run it twice, get identical output, and we'll prove that in the deck
- Every number in the submission comes from models running on our own hardware, so a judge can rerun
  `MAIN.py` offline with no API key

Then we run the _same_ filings through a second, different AI model and measure how often the two agree.
High agreement means the signal is really in the documents. Low agreement means we were reading one
model's quirks. **Either answer is worth reporting, and no other team will have it.**

Two more AI jobs, both run in Claude Code rather than in the pipeline. One argues _against_ our twenty
biggest positions, hunting for the filing or the factor exposure that kills the case. The other re-runs
our own pipeline looking for mistakes before we submit. Neither touches a number — they produce
commentary and checks — so the numbers stay reproducible offline.

## Proving all this instead of claiming it

Three slides aimed straight at what the judges said they score.

**Originality.** Most teams will date the next earnings report by shifting three rows forward in a
spreadsheet, which is wrong, and the brief warns about exactly that. We'll show how often the shortcut
picks the wrong quarter, and what our results look like both ways.

**Technology choice.** The brief says it rewards the reasoning, not the tool. So we list what we rejected
and why — five models and methods we considered and dropped, each with a reason. Five rejections with
reasons says more about judgment than five models we ran.

**Execution.** We found a column in the data that quietly reveals which rows are from 2026. Feed it to the
model and results improve for no real reason. We'll run it once _with_ the column, report both numbers, and
say we removed it. A judge can't get that anywhere else, and it proves we were actually hunting for
problems rather than hoping there weren't any.

The appendix gets the rest, and all of it falls out of work we're doing anyway. How the strategy holds up
with each piece switched off. Year by year. At 150 stocks and at 500. At half our cost assumption and at
double. The trading cost at which our edge disappears entirely. How much money it could run before it
stops working. How it did in calm markets versus violent ones. How quickly the signal fades. And one
strategy we tried that didn't work.

## Not getting fooled by our own backtest

The easiest way to lose is to accidentally use information we wouldn't have had at the time (look forward bias). If our model sees next month's data, it looks brilliant and is worthless. We have 25 specific checks for this, and a script that stops the build rather than printing a warning.

Related: if you try fifty versions and report the best one, that number is partly luck. So we fix our
settings up front, count everything we try, and report the count. Choosing 300 stocks _before_ seeing
results is what makes the final number honest.

**The settings, decided now and not changed later:**

- **300 stocks, 150 on each side.** The rules allow anywhere from 100 to 500.
- **Nothing under $5 a share or under $300M in size.** Penny stocks and tiny companies cost a lot to
  trade, and you often can't borrow shares to short them at all. That still leaves about 2,400 to pick from.
- **Every trade costs us 0.10%** in fees and slippage. So the returns we report are after costs, not before.
- **Keep sector weights balanced** — roughly as much in tech as in energy as in healthcare, so we're
  betting on picking stocks rather than on tech beating energy. The data offers two ways to group sectors,
  183 or 49. We use 49: with 2,400 stocks split 183 ways, some groups have three stocks in them, and
  balancing across three stocks isn't balancing, it's forcing random trades.
- **Shrink our positions by a quarter when markets get choppy.** Written down now so nobody can say we
  invented the rule after seeing which version looked better.

## Who does what

|             |                                                                                               |
| ----------- | --------------------------------------------------------------------------------------------- |
| **CS**      | Builds the data pipeline and the portfolio construction. Will also help with ML.              |
| **ML1**     | The three prediction models, the earnings-surprise work, and all the performance statistics.  |
| **ML2**     | Everything to do with the filings and the AI models.                                          |
| **Finance** | Fixes the settings before we start, pulls the benchmark data, checks every number looks good. |
| **Deck**    | Verifies every company name and ticker, builds the slides, assembles the charts.              |

Finance and Deck don't write code. (Unless Wanted)

## What we hand in

A deck (8 slides plus up to 10 of appendix), a spreadsheet of what we held each month, a spreadsheet of
our returns, one Python file, five CVs, and a line saying it's public domain.

Every chart gets saved as an image when the pipeline runs, and those go
straight into PowerPoint. That's also how we all see where results stand.

## How it's judged

Mostly on **originality, our choice of technology, and whether the backtest was done properly** — the
organisers say this explicitly. Performance matters but isn't the main thing.

Which is why the plan spends so much effort on evidence: showing what our strategy is correlated with,
how much money it could actually handle, how it did in different market conditions, and what didn't work.
A deck where every number has support behind it beats a deck with a bigger number and no explanation.
