# Results

<!-- Every table between AUTO markers is written by src/docs.py and overwritten on each run. The
     prose is by hand; src/docs.py fails the run if a number it repeats has gone stale. -->

Made by `uv run run.py --official`. January 2021 to August 2026, after all modelled costs unless a
table says otherwise.

## Headline

<!--AUTO:headline-->

|  |  |
|---|---|
| Gross return (annualized) | 20.2% |
| **Net return (annualized)** | **16.1%** |
| CAGR (total return) | 20.0% |
| Volatility | 14.5% |
| **Information ratio vs TB3MS + 4%** | **0.83** |
| Sharpe ratio | 1.11 |
| Max drawdown (total return) | -12.8% |
| Hit rate | 57.4% |
| **Alpha** | **16.6%** (se 6.9%, t = 2.40, HAC) |
| **Realized beta** | **-0.05** (se 0.11) |
| Correlation with market | -0.05 |
| Market series | S&P 500 price index (FRED SP500), excludes dividends |
| Positions | 316 |
| Turnover, one-way monthly | 53% |
| Costs as share of gross | 20% |
| Holding months | 68, 2021-01 to 2026-08 |

_Generated 2026-09-27T16:58:59+00:00 from commit `b7e1612`._

<!--/AUTO:headline-->

IR 0.83 against cash plus 4%. Beta is the regression the rules ask for, against the S&P 500 price
index (FRED `SP500`) with HAC errors. The build fails if it leaves ±0.20. Adding dividends from
WRDS barely moves it.

## Committee pack

<!--AUTO:committee-->

|  |  |
|---|---|
| Average monthly return, total | 1.62% |
| Annualized, arithmetic / geometric (CAGR) | 19.4% / 20.0% |
| Cumulative return, Jan 2021 to Aug 2026 | 181.4% |
| Best month | +12.1%, 2022-04 |
| Worst month | -9.2%, 2024-10 |
| Months beating the benchmark | 57% |
| Holdings, long / short | 164 / 152 |
| Gross exposure, average (range) | 199.90% (199.84% to 199.94%) |
| Net exposure, average (range) | -0.02% (-0.09% to 0.00%) |
| Position weight, average / largest | 0.63% / 1.64% |
| Share of gross in the ten largest names | 7.5% |
| Turnover, one-way monthly, average (range) | 53% (36% to 100%) |

<!--/AUTO:committee-->

<!--AUTO:years-->

| year | strategy | T-bill + 4% | S&P 500 (price) | active |
|---|---:|---:|---:|---:|
| 2021 | +49.1% | +4.1% | +26.9% | +45.0% |
| 2022 | +37.8% | +6.2% | -19.4% | +31.6% |
| 2023 | +17.9% | +9.5% | +24.2% | +8.4% |
| 2024 | -5.5% | +9.3% | +23.3% | -14.8% |
| 2025 | +4.1% | +8.4% | +16.4% | -4.3% |
| 2026 (Jan-Aug) | +18.1% | +5.2% | +12.3% | +12.9% |

<!--/AUTO:years-->

Each side's contribution to NAV, before costs:

<!--AUTO:legs-->

| leg | return a year | volatility | names | median size | median daily $ volume |
|---|---:|---:|---:|---:|---:|
| long | +16.9% | 19.6% | 164 | $6.2bn | $65m |
| short | +3.3% | 24.7% | 152 | $1.9bn | $24m |

Short positions flagged small-cap or hard to borrow: 21% of the short book.

<!--/AUTO:legs-->

The ten largest positions on each side by average weight. Every name is checked against a dated
source:

<!--AUTO:top-->

|  | long | weight | short | weight |
|---|---|---|---|---|
| 1 | PRG, PROG HOLDINGS INC | 1.32% | NEXT, NextDecade Corp | -0.89% |
| 2 | DDS, DILLARD'S, INC. | 1.00% | CYTK, CYTOKINETICS INC | -0.81% |
| 3 | ALGN, ALIGN TECHNOLOGY INC | 0.96% | KRUS, KURA SUSHI USA, INC. | -0.73% |
| 4 | DFIN, Donnelley Financial Solutions, Inc. | 0.95% | VRDN, Viridian Therapeutics, Inc. | -0.73% |
| 5 | MEDP, Medpace Holdings, Inc. | 0.94% | CWST, CASELLA WASTE SYSTEMS INC | -0.70% |
| 6 | SIGA, S I G A TECHNOLOGIES INC | 0.93% | MSTR, Strategy Inc | -0.69% |
| 7 | MTD, METTLER TOLEDO INTERNATIONAL INC | 0.85% | COGT, Cogent Biosciences, Inc. | -0.66% |
| 8 | LRCX, LAM RESEARCH CORP | 0.79% | IONS, IONIS PHARMACEUTICALS INC | -0.60% |
| 9 | CCRN, CROSS COUNTRY HEALTHCARE INC | 0.73% | BLNK, BLINK CHARGING CO | -0.60% |
| 10 | AMAT, APPLIED MATERIALS INC | 0.70% | FIVN, FIVE 9 INC | -0.59% |

<!--/AUTO:top-->

## The clean test failed

The same frozen book on 2016-2020, five years we never looked at while designing it:

<!--AUTO:clean-->

|  | 2016-2020, never looked at | 2021-2026, the record |
|---|---|---|
| Information ratio | **-0.82** | +0.83 |
| Net return | -5.4% a year | +16.1% a year |
| Realized beta, CRSP market | **-0.30** (se 0.09) | -0.11 (se 0.11) |
| Worst spread drawdown | -38% | -18% |
| Turnover, one-way monthly | 56% | 53% |
| Net by year, compounded | 2016 +1%, 2017 -2%, 2018 +16%, 2019 -7%, 2020 -31% | 2021 +49%, 2022 +35%, 2023 +12%, 2024 -10%, 2025 0%, 2026 +15% |

<!--/AUTO:clean-->

**IR −0.82 and beta −0.30.** The book is a value, quality and defensive tilt. It earns when that
style pays, and the 2020 rally in low-quality stocks broke it. So 2021-2026 is honest arithmetic,
**not proof that the design works in general**.

## What WRDS changed

We used late CRSP and Compustat exports to check and correct the book, never as a signal. Delisted
stocks are removed on the decision date, takeover payouts are booked, the S&P 500 is the market,
and turnover is measured from the drifted book. We also fixed a T-bill file that started in 2020,
which had cut every 2016-2020 regression to 12 months.

<!--AUTO:corrections-->

|  | before | now |
|---|---|---|
| Information ratio | 0.85 | 0.83 |
| Net return | 16.3% | 16.1% |
| Costs a year | 3.9% | 4.1% |
| Turnover, one-way monthly | 50% | 53% |
| Realized beta | -0.11 (se 0.11), CRSP market, 67 months | -0.05 (se 0.11), S&P 500, 68 months |
| Alpha | 18.2% (t 2.57) | 16.6% (t 2.40) |
| Max drawdown | -12.5% | -12.8% |
| Deflated-Sharpe probability, 92 / 1,586 | 0.57 / 0.23 at 1,575 | 0.56 / 0.22 |
| Weight with no return, long / short | 0.074% / 0.363% | 0.016% / 0.044% |
| 2016-2020 beta, CRSP market | -0.36 (se 0.04), 12 months by mistake | -0.30 (se 0.09), 60 months |

<!--/AUTO:corrections-->

<!--AUTO:wrds-->

|  |  |
|---|---|
| Dated delistings and deletions applied | 8,346 securities |
| Rows already delisted at the decision, screened out | 598 |
| Held names already delisted | 0 |
| Held names taken over in their holding month | 60, 42 for cash; payouts +0.7 bp a year, closing cost 1.2 bp, already charged |
| Panel returns against CRSP, 2021-2025 | 83.9% within 1 bp, correlation 0.9995, 0.03% off by over 1% |
| Beta, S&P 500 with dividends, 2021-01 to 2025-12 | -0.02 (se 0.12) against -0.01 price-only; dividends 1.5% a year |
| Accounting updates with no new report behind them | worst signal 0.10%, rule 1%; a random month holds a release 33% of the time |
| Updates from a report dated on the decision day, held back a month | IR 0.82, net 15.9%; 1.2% of rows |
| Same code without WRDS, as a judge rebuilds it | IR 0.83, net 16.1%, beta -0.05 |
| IR on CRSP years only, 2021-2025 | 0.76 over 60 months |
| 2026, returns from Compustat | monthly spread 0.149 against 0.111-0.119; moves past ±50% 1.25% against 0.45%-0.75% |

<!--/AUTO:wrds-->

Accounting data is point-in-time: for every signal, at most 0.1% of updates had no report behind
them. Holding back reports dated on the decision day gives IR 0.82. **2021-2025 alone gives IR
0.76.** 2026 comes from Compustat and is visibly noisier, so it is the part we trust least.

## Neutrality

Our first book had a predicted beta of −0.002 and a real beta of −0.52: flat on `beta_60m`, but
tilted away from volatile stocks. Limiting the volatility signals fixed it. The full-period beta
still hides a drift:

<!--AUTO:drift-->

| period | beta | se | t |
|---|---:|---:|---:|
| 2021-2023 | +0.04 | 0.13 | +0.34 |
| 2024-2026 | -0.21 | 0.09 | -2.24 |
| full period | -0.05 | 0.11 | -0.43 |

37% of 57 rolling 12-month windows sit outside ±0.20.

<!--/AUTO:drift-->

## Costs and compliance

Commission 5 bp and impact 8 bp per side. The half-spread is `bidaskhl_21d` × 0.20, because that
estimator's level is scaled. Borrow is 50 bp a year, plus 250 bp for hard-to-borrow shorts. Borrow
costs and the hard-to-borrow flag are assumptions, not observed data.

<!--AUTO:costs-->

|  | % of NAV a year |
|---|---|
| Commission, exchange, regulatory | 0.64% |
| Market impact | 1.03% |
| Borrow, general collateral | 0.50% |
| Borrow, hard-to-borrow surcharge | 0.53% |
| Half-spread (scaled Corwin-Schultz) | 1.38% |
| **Total** | 4.08% |
| Annual cost at which active return reaches zero | 16.2%, 3.97 times today's |

<!--/AUTO:costs-->

<!--AUTO:compliance-->

| rule | limit | measured |
|---|---|---|
| Positions | 100-500 | 316 on average |
| Gross exposure | ≤ 200% | max 199.94% |
| Net exposure | −50% to +50%; ours exact before rounding | max abs 0.09% |
| Sector, 11 GICS + `XX` | 1% target | max 1.11% |
| Single name | 1.5% target | max 1.64% |
| Ex-ante beta | ±0.02 | mean +0.020 |
| Realized beta | build fails outside ±0.20 | -0.05 (se 0.11) |

<!--/AUTO:compliance-->

## The machine-learning comparison

ElasticNet, LightGBM and NN3 on all 147 characteristics, with calendar-year folds as the rules ask,
each run through the same optimizer and costs as the book:

<!--AUTO:models-->

|  | IC t | gross | cost | net | turnover | **net IR** |
|---|---:|---:|---:|---:|---:|---:|
| **12-signal composite** | 3.78 | 20.2% | 4.1% | **+16.1%** | 53% | **+0.83** |
| LightGBM | 3.60 | 7.7% | 8.1% | -0.4% | 123% | -0.35 |
| NN3, seed 42 | 3.91 | 7.2% | 6.4% | +0.8% | 98% | -0.26 |
| ElasticNet | 2.55 | 3.8% | 6.1% | -2.3% | 94% | -0.50 |

<!--/AUTO:models-->

<!--AUTO:stages-->

|  | equal-weight | optimizer | + neutrality | + whole shares | **+ costs** |
|---|---:|---:|---:|---:|---:|
| **12-signal composite** | +0.71 | +0.70 | +1.12 | +1.12 | +0.83 |
| LightGBM | -0.23 | -0.08 | +0.29 | +0.29 | -0.35 |
| NN3 | -0.02 | +0.24 | +0.26 | +0.25 | -0.26 |
| ElasticNet | -0.31 | -0.18 | -0.02 | -0.02 | -0.50 |

<!--/AUTO:stages-->

**Neutralizing helps them; costs sink them.** NN3 depends on its seed: five seeds give IR −1.26 to
−0.26, mean −0.81, and seed 42 is the best. Blending toward last month's scores, longer horizons,
monotone constraints and an ensemble all stayed negative (figures in `config_log.csv`).

<!--AUTO:r2-->

| method | R², zero benchmark | R², cross-sectional |
|---|---:|---:|
| Template OLS | -0.32% | -0.26% |
| Template ridge | -0.06% | -0.02% |
| Template ElasticNet | -0.05% | -0.01% |
| ElasticNet, rank target | -0.10% | -0.11% |
| LightGBM | +0.08% | +0.05% |
| NN3, seed 42 | -0.15% | +0.01% |
| 12-signal composite | -0.01% | -0.01% |

NN3 across five seeds: -0.16% to +0.07%, zero benchmark.

<!--/AUTO:r2-->

## The record in pieces

<!--AUTO:halves-->

| period | months | gross | cost | net | IR | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 20.2% | 4.1% | 16.1% | 0.83 | [-0.09, 1.75] |
| 2021-2022 | 24 | 41.2% | 4.2% | 37.0% | 1.87 | [1.16, 3.31] |
| **2023-2026** | 44 | 8.7% | 4.0% | 4.7% | 0.06 | [-1.15, 0.94] |
| 2022-2026 | 56 | 14.6% | 4.0% | 10.5% | 0.50 | [-0.59, 1.20] |
| CRSP years, 2021-2025 | 60 | 19.3% | 4.1% | 15.3% | 0.76 | [-0.25, 1.77] |

<!--/AUTO:halves-->

The 95% interval includes zero, and most of the return came early: 2023-2026 is IR +0.06.

## Where the return comes from

<!--AUTO:factors-->

|  | loading | t |
|---|---:|---:|
| Market (CRSP) | +0.07 | +1.41 |
| Size | -0.37 | -3.10 |
| Value | +0.25 | +2.19 |
| Profitability | +0.63 | +3.86 |
| Investment | +0.17 | +1.29 |
| Momentum | +0.01 | +0.09 |
| **Alpha after all six** | **9.5%** | **+1.82** |
| Alpha after three | 9.9% | +1.75 |
| Alpha after the S&P 500 alone | 16.6% | +2.40 |

The six explain 49% of the variance, over 67 months.

<!--/AUTO:factors-->

<!--AUTO:attribution-->

| signal | % a year of gross | t |
|---|---:|---:|
| `ope_be` | +3.8% | +1.22 |
| `ret_12_1` | +2.6% | +1.46 |
| `noa_gr1a` | +2.5% | +2.02 |
| `eqnetis_at` | +2.3% | +0.94 |
| `o_score` | +2.2% | +1.08 |
| `be_me` | +1.5% | +1.85 |
| `niq_su` | +1.3% | +1.55 |
| `chcsho_12m` | +0.8% | +0.36 |
| `at_gr1` | +0.7% | +0.43 |
| `qmj` | -0.5% | -0.17 |
| `ivol_capm_21d` | -0.8% | -0.81 |
| `gp_at` | -2.9% | -0.99 |
| explained by the twelve | +13.5% |  |
| residual | +6.6% |  |

<!--/AUTO:attribution-->

<!--AUTO:tails-->

|  |  |
|---|---:|
| 95% VaR, monthly | -5.12% |
| 95% CVaR, monthly | -6.64% |
| Skew | +0.37 |
| Excess kurtosis | +0.26 |
| Rolling 12-month windows with a negative IR | 40% of 57 |

<!--/AUTO:tails-->

The panel's earnings update in the month they are released 90% of the time. Using them three
months late gives IR 0.41, six months late 0.33.

## Trying to make the result disappear

<!--AUTO:placebo-->

| control | what changes | what happened |
|---|---|---|
| Permutation null | scores shuffled within sector and liquidity, 200 draws | gross +0.38% a year (sd 2.82%) against +20.2%; net IR -2.06 at 180% turnover |
| Inversion | every score times -1 | gross -20.2% against +20.2% |
| Stale scores | last month's ranking traded this month | net IR +0.46 against +0.93 over the same 67 months |

<!--/AUTO:placebo-->

## Selection is worse than not choosing

Across all 792 five-signal subsets, IR in the early years and IR in the later years correlate at
−0.36. A budgeted search scored +1.78 on the years it searched and +0.33 afterwards. Across all 147
characteristics, t-statistics before and after 2021 correlate at −0.41, and only 38% keep their
sign. That is why the twelve signals are signed by theory and never picked on results.

## The earnings module

Designed and judged on 2016-2020, under a rule written down first:

<!--AUTO:earnings-->

| variant | 2016-20 IR | 2016-20 beta | tails | 2021-26 IR |
|---|---:|---:|---:|---:|
| Frozen book | -0.82 | -0.30 | monotone | +0.83 |
| Announcement premium (Frazzini-Lamont 2007) | -0.76 | -0.27 | not monotone | +0.72 |
| Earnings plus revenue surprise (Jegadeesh-Livnat 2006) | -0.73 | -0.32 | not monotone | +0.80 |
| Fresh surprise only | -0.82 | -0.31 | monotone | +0.80 |

Rule: +0.10 IR on 2016-2020, beta inside ±0.15, monotone tails. Shipped: **no**.

<!--/AUTO:earnings-->

## Agents

Local models from two vendors, run through Hermes, pinned by SHA-256, at temperature 0. Each agent
gets only its own read-only tools, and every call is logged. **No model output ever sets a
weight.** Transcripts and tool definitions are in `submission/exhibits/agents/`.

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Signal discovery** | Qwen3.8-27B | real names: 8 backtests, best in sample 1.14, sealed IR **-2.08**; coded names: 0 backtests, sealed IR **-1.82**; random search, same budget, sealed IR -0.44 |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 quoting a number no tool showed; run twice, 5 of 5 calls identical |
| **Reproducibility** | Qwen3.8-27B | found **0 of 7** planted bugs; 10 false alarms on the clean copy |

<!--/AUTO:agents-->

## Labels

<!--AUTO:labels-->

| period | confirmed by | rows |
|---|---|---|
| 2021 2025 crsp | CRSP, dated | 19,226 |
| 2021 2025 crsp | EDGAR, dated correction | 8 |
| 2026 public filings | 8-K on or before | 2,177 |
| 2026 public filings | EDGAR, dated name and current ticker | 77 |
| 2026 public filings | EDGAR, dated correction | 12 |
| 2026 public filings | unconfirmed: no public source agrees on both | 3 |
| 2026 public filings | Compustat header, current | 3 |

99.99% of 21,506 holding rows confirmed. Corrected from SEC's dated record: H20 AMERICA → H2O AMERICA from 2025-05-01, CONTANGO ORE INC → CONTANGO SILVER & GOLD INC from 2026-03-30.

<!--/AUTO:labels-->

## The live forecast

<!--AUTO:live-->

|  |  |
|---|---|
| Sealed book | 299 names, SHA-256 `bb58c4d406a1edb2`, first hashed 2026-09-23T13:55:30+00:00 |
| Holding month | 2026-09; the clean test is October 2026, same book |
| Today's code, same month | 298 names, `eb60a983495d15ec`; the sealed file is never rewritten |

<!--/AUTO:live-->

September is mechanical, because the book was hashed on the 23rd. October is the clean test,
scored so far at the finals. The rule, set in advance: report whatever it shows.

## Multiple testing

<!--AUTO:deflation-->

|  | Sharpe luck alone produces | deflated-Sharpe probability |
|---|---:|---:|
| **At 92 eligible attempts** | 1.05 | **0.56** |
| At 1,586, every fit we ever ran | 1.42 | 0.22 |
| Missing returns at −30%, longs / both sides |  | IR 0.83 / 0.84 |

<!--/AUTO:deflation-->

The deflated-Sharpe probability is a probability, not a Sharpe ratio. Attempt counts come from
`config_log.csv`. **These are research backtests, not a sealed out-of-sample record.**

## Limits

We saw 2021-2026 while designing · costs are modelled · 2026 returns come from Compustat · the S&P
500 series is price-only · point-in-time accounting is checked, not guaranteed.
