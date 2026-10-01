# Results

A market-neutral book of US stocks, January 2021 to August 2026: the 12-signal composite, hedged
on a beta our machine learning learned from daily prices. Information ratio against T-bill + 4%
<!--N:metrics.json:performance.information_ratio:.2f-->0.74<!--/N-->, net return
<!--N:metrics.json:performance.return_net_annual:.1%-->12.8%<!--/N--> a year after every modelled cost,
beta to the S&P 500 <!--N:metrics.json:performance.beta_realized:+.2f-->−0.03<!--/N-->. Every table and
number here is filled from the run's own files; the code that made them is named under the first
table.

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

_From code `c97aca22be53550c`._

<!--/AUTO:headline-->

## The committee pack

Every figure covers January 2021 to August 2026, net of every modelled cost unless it says gross.

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

## Costs and capacity

Interactive Brokers' fixed commission and regulatory fees, half the quoted spread calibrated to CRSP
closing quotes, square-root market impact, borrow by how shorted a stock is, and cash earning the
T-bill less 0.5%.

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

<!--AUTO:implementation-->

|  | IR | net | cost | sold in a day at 20% of volume; 95th percentile |
|---|---:|---:|---:|---:|
| As modelled, $10M | +0.74 | +12.8% | 5.1% |  |
| Every cost doubled | +0.30 | +7.6% | 10.3% |  |
| Impact coefficient 0.5 | +0.83 | +13.9% | 4.0% |  |
| $10M of capital | +0.74 | +12.8% | 5.1% | 100%; 0.1 days |
| $100M of capital | +0.33 | +7.9% | 10.0% | 91%; 1.1 days |
| $500M of capital | -0.41 | -0.9% | 18.9% | 65%; 5.6 days |
| $1B of capital | -0.96 | -7.7% | 25.6% | 51%; 11.2 days |

<!--/AUTO:implementation-->

## Neutrality and daily risk

The book is dollar neutral and held within ±0.02 of zero beta every month, on the learned beta.
Monthly weights are also marked every trading day.

<!--AUTO:drift-->

| period | beta | se | t |
|---|---:|---:|---:|
| 2021-2023 | +0.02 | 0.11 | +0.14 |
| 2024-2026 | -0.09 | 0.08 | -1.11 |
| full period | -0.03 | 0.09 | -0.31 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.67 |

19% of 57 rolling 12-month windows sit outside ±0.20, and 0% outside the range a zero-beta book with our residual risk would reach 95% of the time.

<!--/AUTO:drift-->

<!--AUTO:daily-->

|  |  |
|---|---|
| Trading days | 1,255, 2021-01 to 2025-12 |
| Gross at rebalance, largest | 159.9% |
| Gross within a month, largest | 195.9%, 2021-02 |
| Months above 200% on some day | 0 of 60 |
| Net within a month, largest absolute | 11.1% |
| Volatility, daily / monthly | 13.7% / 12.2% |
| Max drawdown, daily / monthly | -13.9% / -7.4% |
| One-day VaR 95% / 99%, CVaR 95% | -1.32% / -2.09%, -1.75% |
| Worst day | -3.28%, 2021-02-03 |
| Daily path compounded to months, against returns.csv | correlation 1.0000, largest gap 0.017% |

<!--/AUTO:daily-->

<!--AUTO:stress-->

| window | strategy | S&P 500 | worst fall inside |
|---|---:|---:|---:|
| 2020 crash, Feb 19 to Mar 23 | +1.3% | -33.9% | -5.2% |
| 2020 rebound, Mar 24 to Jun 8 | -6.4% | +32.1% | -13.4% |
| 2022, rates up | +31.4% | -20.0% | -12.0% |
| 2023 AI rally, Jan to Jul | +8.9% | +20.0% | -5.6% |
| October 2024, the worst month | -6.5% | -0.1% | -8.6% |

Trading a day late, 60 months: IR +0.68 against +0.69 on time, +0.3% a year.

<!--/AUTO:stress-->

## Where the return came from

<!--AUTO:factors-->

|  | loading | t |
|---|---:|---:|
| Market (CRSP) | +0.07 | +1.27 |
| Size | -0.28 | -2.58 |
| Value | +0.21 | +2.16 |
| Profitability | +0.49 | +3.34 |
| Investment | +0.14 | +1.17 |
| Momentum | +0.03 | +0.24 |
| **Alpha after all six** | **7.4%** | **+1.77** |
| Alpha after three | 7.9% | +1.76 |
| Alpha after the S&P 500 alone | 13.1% | +2.35 |

The six explain 44% of the variance, over 67 months.

<!--/AUTO:factors-->

<!--AUTO:styles-->

| year | total | from the six styles | from stock selection |
|---|---:|---:|---:|
| 2021 | +31.5% | +18.6% | +12.9% |
| 2022 | +26.7% | +13.4% | +13.3% |
| 2023 | +10.0% | -0.9% | +10.9% |
| 2024 | -7.1% | +4.1% | -11.2% |
| 2025 | +1.4% | -1.2% | +2.6% |
| 2026 (7 months) | +13.0% | +0.1% | +12.9% |

Return over cash, monthly sums, at the full-period loadings on the market, size, value, profitability, investment and momentum (Ken French's factors, which end a month before our last). Stock selection is everything the six do not explain.

<!--/AUTO:styles-->

<!--AUTO:attribution-->

| signal | % a year of gross | t |
|---|---:|---:|
| `ope_be` | +3.1% | +1.22 |
| `ret_12_1` | +2.4% | +1.50 |
| `noa_gr1a` | +2.1% | +2.02 |
| `eqnetis_at` | +1.9% | +0.95 |
| `o_score` | +1.7% | +1.04 |
| `be_me` | +1.3% | +1.83 |
| `niq_su` | +1.1% | +1.50 |
| `chcsho_12m` | +0.7% | +0.38 |
| `at_gr1` | +0.5% | +0.40 |
| `qmj` | -0.5% | -0.21 |
| `ivol_capm_21d` | -0.8% | -0.94 |
| `gp_at` | -2.5% | -1.01 |
| explained by the twelve | +10.9% |  |
| residual | +7.0% |  |

<!--/AUTO:attribution-->

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

## Machine learning

Every model trains on the brief's folds: expanding training, two years of validation, refit each
year, so each year is forecast only from the years before it. The beta teacher is the hedge we ship;
the stock picker, the crowd and the analyst are research we report.

<!--AUTO:teachers-->

| teacher predicts | rank correlation a year ahead | mean error |
|---|---|---|
| next month's daily beta | 0.45 | 0.55 against 0.64 for beta_60m |
| next month's short crowding | 0.64 |  |
| next month's analyst revisions | 0.54 |  |
| next quarter's earnings surprise | 0.52 |  |

<!--/AUTO:teachers-->

<!--AUTO:scorer-->

| year | IC |
|---|---:|
| 2021 | +0.138 |
| 2022 | +0.120 |
| 2023 | +0.014 |
| 2024 | +0.081 |
| 2025 | +0.006 |
| 2026 | +0.035 |
| **2021-2026** | **+0.067** (t = 3.55) |

<!--/AUTO:scorer-->

<!--AUTO:models-->

|  | IC t | gross | cost | net | turnover | **net IR** |
|---|---:|---:|---:|---:|---:|---:|
| **Our book** | 3.78 | 17.9% | 5.1% | **+12.8%** | 46% | **+0.74** |
| LightGBM | 3.60 | 7.2% | 10.1% | -2.9% | 101% | -0.65 |
| NN3, seed 42 | 3.91 | 6.1% | 7.3% | -1.2% | 80% | -0.51 |
| ElasticNet | 2.62 | 2.5% | 9.8% | -7.3% | 100% | -1.13 |

<!--/AUTO:models-->

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

## Agents

Local open models pinned by SHA-256, at temperature 0, with names, tickers and dates masked. No
agent sets a weight. Prompts and tool definitions are in `prompts/agents/` and
`submission/exhibits/agents/`.

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Triage** | Gemma 4 26B-A4B | 6,000 masked 8-Ks from 2015-18 labelled; FinBERT + LightGBM learns them at 87% against 80% for always routine, then labels every filing |
| **Analyst** | Qwen3.8-27B | 5,000 verdicts; named the company in 4% of 500 masked filings; its 2021-26 verdicts' IC -0.003, no sign of recall |
| **AI crowd** | Gemma 4 and Qwen3.8 | 265,590 picks from anonymous cards, 2016-20; the two models agree 0.51; they buy quality and 1-year momentum; 42% of our longs sit in their top tenth |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 citing a number no tool showed; run twice, 5 of 5 calls identical |

<!--/AUTO:agents-->

**A firewall against recall.** The analyst's model was trained on text written after 2021, so its
reading of a 2021-2026 filing could be memory. Its verdicts up to November 2020 teach a small model
that sees only FinBERT's vectors and the stock's card, and that model scores every month. The
analyst's own later verdicts are kept only to measure recall.

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

<!--AUTO:explained-->

The explainer has not run on the winners and losers yet; it runs with --agents.

<!--/AUTO:explained-->

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

<!--AUTO:placebo-->

| control | what changes | what happened |
|---|---|---|
| Permutation null | scores shuffled within sector and liquidity, 200 draws | gross +1.00% a year (sd 2.41%) against +17.9%; net IR -2.32 at 147% turnover |
| Inversion | every score times -1 | gross -17.9% against +17.9% |
| Stale scores | last month's ranking traded this month | net IR +0.43 against +0.84 over the same 67 months |

<!--/AUTO:placebo-->

<!--AUTO:deflation-->

|  | Sharpe luck alone produces | deflated-Sharpe probability |
|---|---:|---:|
| **At 141 eligible attempts** | 1.11 | **0.46** |
| At 1,665, every fit we ever ran | 1.43 | 0.19 |
| Missing returns at −30%, longs / both sides |  | IR 0.73 / 0.74 |

<!--/AUTO:deflation-->
