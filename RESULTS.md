# Results

January 2021 to August 2026, after every modelled cost unless a table says otherwise. Every number
below is filled in from the run's own output files.

## Headline

<!--AUTO:headline-->

|  |  |
|---|---|
| Gross return (annualized) | 17.9% |
| **Net return (annualized)** | **12.8%** |
| CAGR (total return) | 16.5% |
| Volatility | 12.0% |
| **Information ratio vs TB3MS + 4%** | **0.74** |
| Information ratio before costs | 1.16 |
| Sharpe ratio | 1.07 |
| Max drawdown (total return) | -7.4% |
| Hit rate | 52.9% |
| **Alpha** | **13.1%** (se 5.6%, t = 2.35, HAC) |
| **Realized beta** | **-0.03** (se 0.09) |
| Correlation with market | -0.04 |
| Market series | S&P 500 price index (FRED SP500), excludes dividends |
| Positions | 296 |
| Turnover, one-way monthly | 46% |
| Costs as share of gross | 29% |
| Holding months | 68, 2021-01 to 2026-08 |

_From code `6d995c6c18e22b1d`._

<!--/AUTO:headline-->

## Returns, positions and exposure

<!--AUTO:committee-->

|  |  |
|---|---|
| Average monthly return, total | 1.34% |
| Annualized, arithmetic / geometric (CAGR) | 16.1% / 16.5% |
| Cumulative return, Jan 2021 to Aug 2026 | 138.1% |
| Best month | +10.8%, 2022-04 |
| Worst month | -6.5%, 2024-10 |
| Months beating the benchmark | 53% |
| Holdings, long / short | 155 / 142 |
| Gross exposure, average (range) | 159.92% (159.89% to 159.94%) |
| Net exposure, average (range) | 0.00% (0.00% to 0.00%) |
| Position weight, average / largest | 0.54% / 1.51% |
| Share of gross in the ten largest names | 9.4% |
| Turnover, one-way monthly, average (range) | 46% (29% to 80%) |

<!--/AUTO:committee-->

<!--AUTO:years-->

| year | strategy, total return | T-bill + 4% | S&P 500 (price) | strategy minus hurdle |
|---|---:|---:|---:|---:|
| 2021 | +35.1% | +4.1% | +26.9% | +30.9% |
| 2022 | +31.4% | +6.2% | -19.4% | +25.2% |
| 2023 | +15.8% | +9.5% | +24.2% | +6.3% |
| 2024 | -2.5% | +9.3% | +23.3% | -11.8% |
| 2025 | +5.2% | +8.4% | +16.4% | -3.1% |
| 2026 (Jan-Aug) | +12.8% | +5.2% | +12.3% | +7.6% |

<!--/AUTO:years-->

<!--AUTO:legs-->

| leg | return added a year | return per $1 in the leg | volatility | stocks | market cap, average | market cap, median | daily $ traded, average | daily $ traded, median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| long | +14.5% | +18.1% | 16.0% | 155 | $61.1bn | $6.0bn | $441m | $64m |
| short | +3.4% | +4.3% | 20.2% | 142 | $6.5bn | $1.9bn | $100m | $24m |

Shorts by weight: 68% small or micro caps (20% micro), and 23% cost 3% a year or more to borrow. In 2021-2025, the years with short-interest data, 23% were in stocks with over 10% of their shares already sold short.

<!--/AUTO:legs-->

<!--AUTO:top-->

|  | long | weight | short | weight |
|---|---|---|---|---|
| 1 | PRG, PROG HOLDINGS INC | 1.20% | NEXT, NextDecade Corp | -0.85% |
| 2 | DDS, DILLARD'S, INC. | 0.87% | CYTK, CYTOKINETICS INC | -0.69% |
| 3 | MEDP, Medpace Holdings, Inc. | 0.83% | KRUS, KURA SUSHI USA, INC. | -0.64% |
| 4 | SIGA, S I G A TECHNOLOGIES INC | 0.81% | CWST, CASELLA WASTE SYSTEMS INC | -0.59% |
| 5 | ALGN, ALIGN TECHNOLOGY INC | 0.79% | VRDN, Viridian Therapeutics, Inc. | -0.59% |
| 6 | MTD, METTLER TOLEDO INTERNATIONAL INC | 0.75% | BLNK, BLINK CHARGING CO | -0.58% |
| 7 | LRCX, LAM RESEARCH CORP | 0.74% | MSTR, Strategy Inc | -0.56% |
| 8 | DFIN, Donnelley Financial Solutions, Inc. | 0.72% | COGT, Cogent Biosciences, Inc. | -0.54% |
| 9 | CCRN, CROSS COUNTRY HEALTHCARE INC | 0.67% | IONS, IONIS PHARMACEUTICALS INC | -0.52% |
| 10 | BLDR, BUILDERS FIRSTSOURCE INC | 0.60% | ABX, Abacus Global Management, Inc. | -0.52% |

<!--/AUTO:top-->

<!--AUTO:compliance-->

| rule | limit | measured |
|---|---|---|
| Positions | 100 to 500 | 227 to 322, 296 on average |
| Gross exposure | up to 200% | largest 159.94% |
| Net exposure | −50% to +50% | largest 0.00% |
| Each sector (our own limit) | ±1% before rounding to whole shares | largest 1.04% after rounding |
| Each position (our own limit) | 1.5% before rounding to whole shares | largest 1.51% after rounding |
| Predicted beta (our own limit) | ±0.02 | average +0.020 |
| Realized beta (our own check) | run stops outside ±0.20 | -0.03 (standard error 0.09) |

<!--/AUTO:compliance-->

## Costs

Commissions and fees at Interactive Brokers' rates, half the bid-ask spread, a market-impact charge
that grows with trade size, borrow fees by how heavily a stock is shorted, and financing on cash.

<!--AUTO:costs-->

|  | % of NAV a year |
|---|---:|
| Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA) | 0.27% |
| Bid-ask spread (half, from real quotes) | 0.87% |
| Market impact (grows with trade size) | 2.24% |
| Borrow fees on shorts (by how heavily shorted) | 1.26% |
| Financing (cash earns the T-bill less 0.5%) | 0.50% |
| **Total** | 5.13% |
| Costs could rise to this before the edge over the hurdle disappears | 13.9% (2.7x) |

<!--/AUTO:costs-->

## Neutrality

<!--AUTO:drift-->

| period | beta | standard error | t-stat |
|---|---:|---:|---:|
| 2021-2023 | +0.02 | 0.11 | +0.14 |
| 2024-2026 | -0.09 | 0.08 | -1.11 |
| full period | -0.03 | 0.09 | -0.31 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.67 |

19% of the 57 rolling 12-month betas fall outside ±0.20, but none fall outside the range a truly zero-beta portfolio with our risk would show by chance (95%).

<!--/AUTO:drift-->

## Prediction accuracy (out-of-sample R²)

<!--AUTO:r2-->

| model | out-of-sample R², 2021-2026 |
|---|---:|
| Linear regression (template) | -0.32% |
| Ridge (template) | -0.06% |
| Elastic net (template) | -0.05% |
| Elastic net, on ranks | -0.01% |
| LightGBM | +0.08% |
| Neural network, 3 layers | -0.15% |
| Stock-picking model | -0.07% |
| Our 12-signal score | -0.01% |

<!--/AUTO:r2-->

## What we tried

<!--AUTO:tried-->

| what we tried | attempts | result | verdict |
|---|---|---|---|
| 28 candidate portfolios: signal sets, hedges, trading rules | 27 | When chosen: 12-signal score 0.70, with the predicted-beta hedge 0.72, others -0.28 to 0.72. Final run 0.74 | Shipped, with the hedge |
| A yearly rule to switch between candidates | 1 | IR 0.34 or 0.67, unstable between runs | Dropped |
| What to neutralize: betas, volatility, sectors | 14 | Sectors, beta and volatility kept. Style-neutral variant 0.75 | In part |
| Construction: weights, carrying positions over, gross exposure, volatility target | 24 | 160% gross kept. Volatility targeting 0.15 to 0.34 | In part |
| Optimizer: position penalty, candidate pool, turnover, short limits | 16 | Penalty 30 and a 200-stock pool kept. Turnover penalty 0.49 to 0.54 | In part |
| More signals: additions, reversal, seasonality | 33 | None helped. Best addition 0.86, no better than chance | Rejected |
| Text signals: tone, filing counts, 8-K items | 3 | None significant once neutralized (best t-stat 2.1) | Rejected |
| ML blends and targets: cost-aware, 3 to 6 months ahead | 22 | Best IR -0.15 | Rejected |
| Construction v2: beta, net exposure band, short rules | 1 | IR -0.17 against -0.00, 2016-2026 | Rejected |
| Construction v2, each rule alone | 5 | Every rule alone lowers IR | Check |
| Factor-neutral portfolio, five style limits | 1 | IR -0.89, alpha -4.2% (t-stat -1.7) | Rejected |
| ML on the 147 characteristics: linear, trees, neural nets | 24 | IC t-stat 2.5 to 4.1, all lose money after costs | Reported |
| Stock-picking model, helper models, AI crowd score | 16 | Picker IC 0.067 (t-stat 3.55). Beta error 0.55 against 0.64 | Beta model kept |
| Trading models: deep hedging and PPO | 3 | IR 0.70 to 0.41, not reproducible | Removed |
| Signal search: subsets and combinations | 1,139 | +1.78 where it searched, +0.33 on unseen years | Check |
| Signal-discovery agent and random search | 95 | Unseen IR -1.18 to -2.08, random -0.44 | Check |
| Robustness: shuffles, delays, 2016-20, lags | 241 | Shuffled scores earn nothing, a day's delay costs nothing | Check |

1,665 fits in all, 141 of them shippable portfolios. Adjusted for this many tries (deflated Sharpe ratio), the chance our edge is real is 46%.

<!--/AUTO:tried-->

## The AI agents

All models run locally, with company names, tickers and dates hidden from them. No agent sets a
position. Prompts and tool definitions are in `prompts/agents/` and `submission/exhibits/agents/`.

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Triage** | Gemma 4 26B-A4B | 6,000 8-Ks from 2015-18 labelled with names hidden. A small FinBERT-based model learns them, 87% correct against 80% for always guessing routine, then labels every filing |
| **Analyst** | Qwen3.8-27B | 5,000 verdicts. Named the company in 4% of 500 test filings. Its 2021-26 verdicts have no predictive power (IC -0.003) |
| **AI crowd** | Gemma 4 and Qwen3.8 | 265,590 picks from anonymous stock cards, 2016-20. The two models' picks correlate 0.51, and both favour quality and 1-year momentum. 42% of our longs are in their top tenth |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 0 citing a number no tool showed. Run twice, identical both times |
| **Explainer** | Qwen3.8-27B | 20 winners and losers explained from their facts alone |

<!--/AUTO:agents-->

The analyst's own verdicts never reach the book. A small model learned from its verdicts on filings
up to November 2020, and that model does the scoring. Its later verdicts are kept only to test
whether it remembered the future:

<!--AUTO:firewall-->

|  |  |
|---|---:|
| Analyst verdicts used for training, up to November 2020 | 2,299 |
| How well the small model copies the analyst, rank correlation on unseen data | 0.24 |
| Stock-months the small model scores | 187,004 |
| Test: share of 500 hidden filings where the analyst named the company / the year | 4% / 9% |

|  | analyst's own verdicts | small model |
|---|---:|---:|
| Predictive power (IC), 2015-2020 | +0.033 (t-stat 1.5) | +0.003 (t-stat 0.1) |
| Predictive power (IC), 2021-2026 | -0.003 (t-stat -0.1) | -0.021 (t-stat -0.8) |

IC: the average monthly rank correlation with next month's return. If the analyst remembered what happened, its 2021-2026 IC would far exceed the small model's. It does not.

<!--/AUTO:firewall-->

## Robustness

<!--AUTO:halves-->

| period | months | gross | costs | net | IR | IR, 95% range |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 17.9% | 5.1% | 12.8% | 0.74 | [-0.09, 1.61] |
| 2021-2022 | 24 | 34.4% | 5.3% | 29.1% | 1.63 | [1.05, 3.02] |
| **2023-2026** | 44 | 9.0% | 5.1% | 3.9% | -0.01 | [-1.12, 0.78] |
| 2022-2026 | 56 | 13.9% | 5.1% | 8.8% | 0.44 | [-0.60, 1.11] |
| 2021-2025, the years with daily prices | 60 | 17.6% | 5.1% | 12.5% | 0.69 | [-0.25, 1.65] |

<!--/AUTO:halves-->

<!--AUTO:clean-->

|  | 2016-2020, a historical check | 2021-2026, the record |
|---|---|---|
| Information ratio | **-1.00** | +0.74 |
| Net return | -5.7% a year | +12.8% a year |
| Beta to the whole US market (CRSP) | **-0.25** (standard error 0.07) | -0.08 (standard error 0.09) |
| Worst drawdown, net return | -35% | -13% |
| Turnover, one-way monthly | 46% | 46% |
| Net return by year, compounded | 2016 +0%, 2017 -2%, 2018 +13%, 2019 -7%, 2020 -29% | 2021 +35%, 2022 +29%, 2023 +10%, 2024 -7%, 2025 +1%, 2026 +10% |

<!--/AUTO:clean-->

<!--AUTO:deflation-->

|  | Sharpe luck alone produces | deflated-Sharpe probability |
|---|---:|---:|
| **At 141 eligible attempts** | 1.11 | **0.46** |
| At 1,665, every fit we ever ran | 1.43 | 0.19 |
| Missing returns at −30%, longs / both sides |  | IR 0.73 / 0.74 |

<!--/AUTO:deflation-->

## Data we used

| source | what we took | why |
|---|---|---|
| Organizer's panel and 8-K filings | 147 stock measures, returns, filing text | the core data |
| CRSP via WRDS | delistings and final returns; daily prices and bid-ask quotes | tradable universe, costs, daily risk, the learned beta |
| Compustat via WRDS | quarterly report dates, short interest | earnings timing, borrow costs |
| I/B/E/S via WRDS | analyst price-target revisions | a model input |
| FRED | 3-month T-bill (TB3MS), S&P 500 | the benchmark and beta |
| Kenneth French's library | Fama-French factors | style attribution |
| SEC EDGAR | company names by date | checking ticker labels |

Everything joins on CRSP PERMNO and month: Compustat files through gvkey and iid, I/B/E/S through
WRDS's dated I/B/E/S-CRSP link, never through a ticker or a name. The cleaning code is
`fiam/wrds.py` and `fiam/build_data.py`. WRDS data is licensed, so it is never committed or
submitted; a rebuild without it still runs and is marked provisional.
