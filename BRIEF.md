# The project in one page

**The idea.** Every month we score each US stock on twelve well-known measures: is it cheap, is it
profitable, is it careful with its money, is it rising. We buy the best and short the worst, about
<!--N:metrics.json:compliance.positions_average:.0f-->296<!--/N--> stocks, with as much money long as
short. The book is neutral to the market and to every sector, and every trade pays the costs a real
broker would charge.

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

## Where the AI comes in

- **It keeps the book neutral.** A small model learns how much each stock moves with the market,
  from daily prices, and the book is balanced on that. This is the one learned part of the book.
- **It cannot cheat by remembering.** Language models are trained on recent news, so one reading a
  2021 filing might already know what happened next. No such reading reaches our book: the AI agents
  judged older filings, and small models learned from those judgments. A test confirms it: the
  model recognised the company in only
  <!--N:exhibits/analyst.json:look_ahead_probe.company_named:.0%-->4%<!--/N--> of hidden filings.
- **It measures crowding.** We had two AI models play retail stock pickers. They mostly buy
  high-quality stocks, and
  <!--N:exhibits/pack.json:crowding.long.share_in_top_crowd_decile:.0%-->42%<!--/N--> of our longs are
  among their favourites, the crowding risk the brief warns about.
- **It predicts, but not enough to pay.** A machine-learning stock picker forecasts returns well,
  yet it trades so much that costs eat the gain. Trading it only in cheap-to-trade stocks is our
  next step.

## The honest reading

Much of the return comes from one investing style, quality and value. It paid well in 2021-22 and
lost money in 2020. We tried many variations before picking this book, and RESULTS.md lists every
one and what it did.

**Limits.** This is a backtest anyone can rerun, not a live record. Costs are modelled, not
observed.
