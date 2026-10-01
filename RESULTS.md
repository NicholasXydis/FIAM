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

_From code `0a73b67299fdad06`._

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

| year | strategy | T-bill + 4% | S&P 500 (price) | active |
|---|---:|---:|---:|---:|
| 2021 | +35.1% | +4.1% | +26.9% | +30.9% |
| 2022 | +31.4% | +6.2% | -19.4% | +25.2% |
| 2023 | +15.8% | +9.5% | +24.2% | +6.3% |
| 2024 | -2.5% | +9.3% | +23.3% | -11.8% |
| 2025 | +5.2% | +8.4% | +16.4% | -3.1% |
| 2026 (Jan-Aug) | +12.8% | +5.2% | +12.3% | +7.6% |

<!--/AUTO:years-->

<!--AUTO:legs-->

| leg | contribution a year | per dollar in the leg | volatility | names | median size | median daily $ volume |
|---|---:|---:|---:|---:|---:|---:|
| long | +14.5% | +18.1% | 16.0% | 155 | $6.0bn | $64m |
| short | +3.4% | +4.3% | 20.2% | 142 | $1.9bn | $24m |

Short book by weight: 68% small-cap or below, 20% micro-cap, 23% in borrow tiers of 3% a year or more. In 2021-2025, 23% of it had more than 10% of its shares already sold short.

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
| Positions | 100-500 | 296 on average |
| Gross exposure | ≤ 200% | max 159.94% |
| Net exposure | −50% to +50%; ours exact before rounding | max abs 0.00% |
| Sector, 11 GICS + `XX` (ours) | 1% before whole-share rounding | max 1.04% after it |
| Single name (ours) | 1.5% before whole-share rounding | max 1.51% after it |
| Ex-ante beta | ±0.02 | mean +0.020 |
| Realized beta | build fails outside ±0.20 | -0.03 (se 0.09) |

<!--/AUTO:compliance-->

## Costs

Commissions and fees at Interactive Brokers' rates, half the bid-ask spread, a market-impact charge
that grows with trade size, borrow fees by how heavily a stock is shorted, and financing on cash.

<!--AUTO:costs-->

|  | % of NAV a year |
|---|---|
| Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA) | 0.27% |
| Half-spread (calibrated to CRSP quotes) | 0.87% |
| Market impact (square-root law) | 2.24% |
| Borrow (short-interest tiers) | 1.26% |
| Financing (benchmark less 0.5% on cash) | 0.50% |
| **Total** | 5.13% |
| Annual cost at which active return reaches zero | 13.9%, 2.71 times today's |

<!--/AUTO:costs-->

## Neutrality

<!--AUTO:drift-->

| period | beta | se | t |
|---|---:|---:|---:|
| 2021-2023 | +0.02 | 0.11 | +0.14 |
| 2024-2026 | -0.09 | 0.08 | -1.11 |
| full period | -0.03 | 0.09 | -0.31 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.67 |

19% of 57 rolling 12-month windows sit outside ±0.20, and 0% outside the range a zero-beta book with our residual risk would reach 95% of the time.

<!--/AUTO:drift-->

## Prediction accuracy (out-of-sample R²)

<!--AUTO:r2-->

| method | R², zero benchmark | R², cross-sectional |
|---|---:|---:|
| Template OLS | -0.32% | -0.26% |
| Template ridge | -0.06% | -0.02% |
| Template ElasticNet | -0.05% | -0.01% |
| ElasticNet, rank target | -0.01% | -0.01% |
| LightGBM | +0.08% | +0.05% |
| NN3, seed 42 | -0.15% | +0.01% |
| LambdaRank scorer | -0.07% | -0.07% |
| 12-signal composite | -0.01% | -0.01% |

<!--/AUTO:r2-->

## What we tried

<!--AUTO:tried-->

| what we tried | attempts | result | verdict |
|---|---|---|---|
| 28 candidate books, hedge and trader variants | 27 | composite 0.70, + hedge 0.72; rest -0.28 to 0.72 | hedge SHIPPED |
| yearly switching rule among the 28 | 1 | IR 0.34 or 0.67, flipped by the trader | dropped |
| neutralization: betas, volatility, sectors | 14 | sectors, beta, volatility kept; styles 0.75 | in part |
| construction: weights, carry-in, gross, vol target | 24 | 160% gross kept; vol targeting 0.15-0.34 | in part |
| optimizer: ridge, pool, turnover, short limits | 16 | ridge 30, pool 200 kept; penalty 0.49-0.54 | in part |
| more signals: added, reversal, seasonality | 33 | none helped; best addition 0.86, a coin flip | rejected |
| text signals: tone, filing intensity, items | 3 | no neutralized t above 2.1 | rejected |
| ML blends and targets: cost-aware, 3-6 month | 22 | best IR -0.15 | rejected |
| construction v2: beta, net band, short rules | 1 | IR -0.17 vs -0.00 on 2016-26 | rejected |
| construction v2, each rule alone | 5 | every rule alone lowers IR | control |
| factor-neutral book, five style limits | 1 | IR -0.89; alpha -4.2%, t -1.7 | rejected |
| ML on 147 characteristics: linear, trees, nets | 24 | IC t 2.5-4.1; all lose after costs | exhibit |
| stock picker, teachers, crowd, director | 16 | picker IC 0.068, t 3.55; beta error 0.55 vs 0.64 | hedge kept |
| trader: deep hedging and PPO | 3 | IR 0.70 to 0.41; not reproducible | removed |
| signal search: subsets, combinations, atlas | 1,139 | +1.78 where it looked, +0.33 unseen | control |
| discovery agent and random search | 95 | unseen IR -1.18 to -2.08; random -0.44 | control |
| robustness: shuffles, delays, 2016-20, lags | 241 | shuffles earn nothing; a day late costs nothing | control |

1,665 fits in all, 141 of them books we could have shipped. The book we ship was chosen by comparing these results; after counting every one, the deflated Sharpe gives a 46% chance its edge is real.

<!--/AUTO:tried-->

## The AI agents

All models run locally, with company names, tickers and dates hidden from them. No agent sets a
position. Prompts and tool definitions are in `prompts/agents/` and `submission/exhibits/agents/`.

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Triage** | Gemma 4 26B-A4B | 6,000 masked 8-Ks from 2015-18 labelled; FinBERT + LightGBM learns them at 87% against 80% for always routine, then labels every filing |
| **Analyst** | Qwen3.8-27B | 5,000 verdicts; named the company in 4% of 500 masked filings; its 2021-26 verdicts' IC -0.003, no sign of recall |
| **AI crowd** | Gemma 4 and Qwen3.8 | 265,590 picks from anonymous cards, 2016-20; the two models agree 0.51; they buy quality and 1-year momentum; 42% of our longs sit in their top tenth |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 0 citing a number no tool showed; run twice, 5 of 5 calls identical |
| **Explainer** | Qwen3.8-27B | 20 winners and losers explained from their facts alone |

<!--/AUTO:agents-->

The analyst's own verdicts never reach the book. A small model learned from its verdicts on filings
up to November 2020, and that model does the scoring. Its later verdicts are kept only to test
whether it remembered the future:

<!--AUTO:firewall-->

|  |  |
|---|---:|
| Verdicts that taught, up to November 2020 | 2,299 |
| Small model against the analyst, held-out rank correlation | 0.24 |
| Stock-months it scores for the stock picker | 187,004 |
| Probe: masked filings where the analyst named the company / year, of 500 | 4% / 9% |

|  | analyst's own verdicts | small model |
|---|---:|---:|
| IC, 2015-2020 | +0.033 (t 1.5) | +0.003 (t 0.1) |
| IC, 2021-2026 | -0.003 (t -0.1) | -0.021 (t -0.8) |

_Mean monthly rank correlation with next month's return, on the same answered stock-months, t across months. If the analyst beats the small model by far more in 2021-2026 than in 2015-2020, the gap is recall. In 2015-2020 the small model was fitted to these same verdicts._

<!--/AUTO:firewall-->

## Robustness

<!--AUTO:halves-->

| period | months | gross | cost | net | IR | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 17.9% | 5.1% | 12.8% | 0.74 | [-0.09, 1.61] |
| 2021-2022 | 24 | 34.4% | 5.3% | 29.1% | 1.63 | [1.05, 3.02] |
| **2023-2026** | 44 | 9.0% | 5.1% | 3.9% | -0.01 | [-1.12, 0.78] |
| 2022-2026 | 56 | 13.9% | 5.1% | 8.8% | 0.44 | [-0.60, 1.11] |
| CRSP years, 2021-2025 | 60 | 17.6% | 5.1% | 12.5% | 0.69 | [-0.25, 1.65] |

<!--/AUTO:halves-->

<!--AUTO:clean-->

|  | 2016-2020, a historical check | 2021-2026, the record |
|---|---|---|
| Information ratio | **-1.00** | +0.74 |
| Net return | -5.7% a year | +12.8% a year |
| Realized beta, CRSP market | **-0.25** (se 0.07) | -0.08 (se 0.09) |
| Worst spread drawdown | -35% | -13% |
| Turnover, one-way monthly | 46% | 46% |
| Net by year, compounded | 2016 +0%, 2017 -2%, 2018 +13%, 2019 -7%, 2020 -29% | 2021 +35%, 2022 +29%, 2023 +10%, 2024 -7%, 2025 +1%, 2026 +10% |

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
