# Results

<!-- Tables between AUTO markers and numbers between N markers are written by fiam/report/docs.py. -->

<!--AUTO:made-->

Made by `uv run run.py --official`; models trained by `uv run run.py --official --ml`.

<!--/AUTO:made-->

Holding months January 2021 to August 2026, after every modelled cost unless a table says otherwise.
Anyone rerunning the code on the same data gets the same numbers.

## Headline

<!--AUTO:headline-->

|  |  |
|---|---|
| Gross return (annualized) | 17.6% |
| **Net return (annualized)** | **13.6%** |
| CAGR (total return) | 17.5% |
| Volatility | 12.2% |
| **Information ratio vs TB3MS + 4%** | **0.79** |
| Sharpe ratio | 1.12 |
| Max drawdown (total return) | -10.5% |
| Hit rate | 55.9% |
| **Alpha** | **14.1%** (se 5.7%, t = 2.46, HAC) |
| **Realized beta** | **-0.05** (se 0.09) |
| Correlation with market | -0.06 |
| Market series | S&P 500 price index (FRED SP500), excludes dividends |
| Positions | 276 |
| Turnover, one-way monthly | 44% |
| Costs as share of gross | 22% |
| Holding months | 68, 2021-01 to 2026-08 |

_From code `ec55b6dc9e51c240`._

<!--/AUTO:headline-->

IR <!--N:metrics.json:performance.information_ratio:.2f-->0.79<!--/N--> against cash plus 4%. Beta is
the rules' regression on the S&P 500 price index with HAC errors; the build fails outside ±0.20.

## How the book is chosen

A 3 × 2 × 2 grid of candidate books: the composite of the 12 signals with 0, 25 or 50% of a
learning-to-rank scorer blended in, each with and without a hedge on the learned beta and a trader
that decides how far to trade. A rule written before any candidate was scored picks each year's book from the two years
before it: the composite ships unless another candidate beats its IR there by 0.25 with beta inside
±0.15. Every candidate counts in the multiple-testing ledger, and `figures/candidates.png` draws
them all.

<!--AUTO:ship-->

| holding year | shipped book | composite IR, two years before | best other |
|---|---|---|---|
| 2021 | Composite | -1.93 | -1.05, Composite + 50% scorer + hedge |
| 2022 | Composite | -0.15 | -0.14, Composite + 25% scorer + hedge |
| 2023 | Composite | +1.83 | +1.83, Composite + trader |
| 2024 | Composite | +1.20 | +1.24, Composite + hedge |
| 2025 | Composite | -0.35 | -0.18, Composite + hedge |
| 2026 | Composite | -0.81 | -0.66, Composite + hedge |

| candidate, 2021-2026 | IR | net | cost | turnover | beta |
|---|---:|---:|---:|---:|---:|
| **Composite** | +0.80 | +13.7% | 3.9% | 44% | -0.05 |
| Composite + trader | +0.79 | +12.8% | 3.4% | 39% | -0.06 |
| Composite + hedge | +0.82 | +13.8% | 3.9% | 45% | -0.03 |
| Composite + hedge + trader | +0.78 | +12.5% | 3.5% | 40% | -0.04 |
| Composite + 25% scorer | +0.52 | +9.9% | 4.8% | 64% | -0.02 |
| Composite + 25% scorer + trader | +0.49 | +8.4% | 4.0% | 53% | -0.02 |
| Composite + 25% scorer + hedge | +0.65 | +11.4% | 4.8% | 65% | -0.03 |
| Composite + 25% scorer + hedge + trader | +0.62 | +9.5% | 3.6% | 48% | -0.03 |
| Composite + 50% scorer | +0.13 | +5.5% | 5.5% | 78% | +0.04 |
| Composite + 50% scorer + trader | +0.11 | +5.1% | 4.5% | 62% | +0.03 |
| Composite + 50% scorer + hedge | +0.21 | +6.6% | 5.7% | 81% | +0.01 |
| Composite + 50% scorer + hedge + trader | +0.13 | +5.3% | 4.5% | 64% | +0.01 |

<!--/AUTO:ship-->

## Committee pack

<!--AUTO:committee-->

|  |  |
|---|---|
| Average monthly return, total | 1.41% |
| Annualized, arithmetic / geometric (CAGR) | 16.9% / 17.5% |
| Cumulative return, Jan 2021 to Aug 2026 | 149.2% |
| Best month | +10.3%, 2022-04 |
| Worst month | -7.6%, 2024-10 |
| Months beating the benchmark | 56% |
| Holdings, long / short | 144 / 132 |
| Gross exposure, average (range) | 159.93% (159.87% to 159.96%) |
| Net exposure, average (range) | 0.00% (0.00% to 0.00%) |
| Position weight, average / largest | 0.58% / 1.51% |
| Share of gross in the ten largest names | 9.4% |
| Turnover, one-way monthly, average (range) | 44% (28% to 80%) |

<!--/AUTO:committee-->

<!--AUTO:comparison-->

|  | strategy | T-bill + 4% | S&P 500 (price) |
|---|---:|---:|---:|
| Return a year, arithmetic | 16.9% | 7.3% | 13.8% |
| Return a year, geometric (CAGR) | 17.5% | 7.5% | 13.5% |
| Cumulative | 149.2% | 50.9% | 104.6% |
| Volatility | 12.0% | 0.6% | 15.1% |
| Sharpe ratio | 1.12 |  | 0.70 |
| Max drawdown | -10.5% | 0.0% | -24.8% |
| Best month | +10.3%, 2022-04 | +0.8%, 2023-10 | +10.4%, 2026-04 |
| Worst month | -7.6%, 2024-10 | +0.3%, 2021-04 | -9.3%, 2022-09 |

<!--/AUTO:comparison-->

<!--AUTO:years-->

| year | strategy | T-bill + 4% | S&P 500 (price) | active |
|---|---:|---:|---:|---:|
| 2021 | +38.7% | +4.1% | +26.9% | +34.5% |
| 2022 | +32.6% | +6.2% | -19.4% | +26.4% |
| 2023 | +15.6% | +9.5% | +24.2% | +6.2% |
| 2024 | -4.1% | +9.3% | +23.3% | -13.4% |
| 2025 | +5.3% | +8.4% | +16.4% | -3.1% |
| 2026 (Jan-Aug) | +16.1% | +5.2% | +12.3% | +10.9% |

<!--/AUTO:years-->

Each side before costs, its contribution to NAV and its return per dollar held:

<!--AUTO:legs-->

| leg | contribution a year | per dollar in the leg | volatility | names | median size | median daily $ volume |
|---|---:|---:|---:|---:|---:|---:|
| long | +14.1% | +17.7% | 15.8% | 144 | $6.1bn | $65m |
| short | +3.4% | +4.3% | 20.3% | 132 | $1.8bn | $24m |

Short book by weight: 68% small-cap or below, 20% micro-cap, 48% charged as hard to borrow. In 2021-2025, 23% of it had more than 10% of its shares already sold short.

<!--/AUTO:legs-->

<!--AUTO:top-->

|  | long | weight | short | weight |
|---|---|---|---|---|
| 1 | PRG, PROG HOLDINGS INC | 1.22% | NEXT, NextDecade Corp | -0.86% |
| 2 | DDS, DILLARD'S, INC. | 0.94% | CYTK, CYTOKINETICS INC | -0.72% |
| 3 | MEDP, Medpace Holdings, Inc. | 0.85% | KRUS, KURA SUSHI USA, INC. | -0.65% |
| 4 | SIGA, S I G A TECHNOLOGIES INC | 0.85% | VRDN, Viridian Therapeutics, Inc. | -0.62% |
| 5 | ALGN, ALIGN TECHNOLOGY INC | 0.82% | CWST, CASELLA WASTE SYSTEMS INC | -0.62% |
| 6 | DFIN, Donnelley Financial Solutions, Inc. | 0.81% | MSTR, Strategy Inc | -0.61% |
| 7 | MTD, METTLER TOLEDO INTERNATIONAL INC | 0.77% | COGT, Cogent Biosciences, Inc. | -0.58% |
| 8 | LRCX, LAM RESEARCH CORP | 0.70% | BLNK, BLINK CHARGING CO | -0.58% |
| 9 | CCRN, CROSS COUNTRY HEALTHCARE INC | 0.67% | IONS, IONIS PHARMACEUTICALS INC | -0.52% |
| 10 | BLDR, BUILDERS FIRSTSOURCE INC | 0.64% | ABX, Abacus Global Management, Inc. | -0.50% |

<!--/AUTO:top-->

## Neutrality, measured monthly and daily

The book is neutral by construction: dollar-neutral, neutral to its hedge beta and to each sector at
every rebalance. What it realized is measured here, not assumed. Twelve monthly returns pin a beta
only to about ±0.3, so the rolling chart shades where a zero-beta book would wander; daily returns
pin it far tighter, and show a small short tilt.

<!--AUTO:drift-->

| period | beta | se | t |
|---|---:|---:|---:|
| 2021-2023 | +0.02 | 0.11 | +0.19 |
| 2024-2026 | -0.16 | 0.09 | -1.87 |
| full period | -0.05 | 0.09 | -0.51 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.52 |

30% of 57 rolling 12-month windows sit outside ±0.20, and 0% outside the range a zero-beta book with our residual risk would reach 95% of the time.

<!--/AUTO:drift-->

Weights stay fixed within each month. Marked every trading day of 2021-2025 on CRSP daily prices,
at a <!--N:metrics.json:compliance.gross_exposure_max:.0%-->160%<!--/N--> gross target; the rules
measure the limits at each rebalance.

<!--AUTO:daily-->

|  |  |
|---|---|
| Trading days | 1,255, 2021-01 to 2025-12 |
| Gross at rebalance, largest | 160.0% |
| Gross within a month, largest | 193.6%, 2021-02 |
| Months above 200% on some day | 0 of 60 |
| Net within a month, largest absolute | 10.8% |
| Volatility, daily / monthly | 13.6% / 12.5% |
| Max drawdown, daily / monthly | -16.3% / -10.5% |
| One-day VaR 95% / 99%, CVaR 95% | -1.30% / -1.98%, -1.73% |
| Worst day | -3.09%, 2021-02-03 |
| Daily path compounded to months, against returns.csv | correlation 1.0000, largest gap 0.013% |

<!--/AUTO:daily-->

## Costs and compliance

Commission 5 bp and impact 8 bp per side, half of `bidaskhl_21d` × 0.20 as spread, borrow 50 bp a
year plus 250 bp for hard-to-borrow shorts: micro-caps, the least liquid twentieth, and the tenth
the crowding teacher expects to be most shorted. All assumed, not observed.

<!--AUTO:costs-->

|  | % of NAV a year |
|---|---|
| Commission, exchange, regulatory | 0.53% |
| Market impact | 0.85% |
| Borrow, general collateral | 0.40% |
| Borrow, hard-to-borrow surcharge | 0.97% |
| Half-spread (scaled Corwin-Schultz) | 1.16% |
| **Total** | 3.91% |
| Annual cost at which active return reaches zero | 13.6%, 3.47 times today's |

<!--/AUTO:costs-->

<!--AUTO:compliance-->

| rule | limit | measured |
|---|---|---|
| Positions | 100-500 | 276 on average |
| Gross exposure | ≤ 200% | max 159.96% |
| Net exposure | −50% to +50%; ours exact before rounding | max abs 0.00% |
| Sector, 11 GICS + `XX` | 1% target | max 1.04% |
| Single name | 1.5% target | max 1.51% |
| Ex-ante beta | ±0.02 | mean +0.020 |
| Realized beta | build fails outside ±0.20 | -0.05 (se 0.09) |

<!--/AUTO:compliance-->

## Machine learning

Every learned part below is a candidate or a control: it reaches the book only when the ship rule
picks it.

**Teachers.** The daily prices, short interest and analyst data stop in 2025, so they cannot feed a
2026 decision. Each teaches a LightGBM model to predict what it would show next month from the
characteristics and 8-K counts, which reach August 2026; each year's model sees only earlier years.

<!--AUTO:teachers-->

| teacher predicts | rank correlation a year ahead | mean error |
|---|---|---|
| next month's daily beta | 0.45 | 0.55 against 0.64 for beta_60m |
| next month's short crowding | 0.64 |  |
| next month's analyst revisions | 0.54 |  |

<!--/AUTO:teachers-->

**Scorer.** LightGBM LambdaRank learns each month's ranking of what a neutral book can earn, next
month's return less its sector's mean and its market bet, one model per tail, averaged over five
seeds, on the rules' folds. Its inputs are the 147 characteristics, the 8-K counts, the three
teachers and the crowd score.

<!--AUTO:scorer-->

| year | IC |
|---|---:|
| 2021 | +0.097 |
| 2022 | +0.096 |
| 2023 | +0.015 |
| 2024 | +0.073 |
| 2025 | +0.021 |
| 2026 | +0.029 |
| **2021-2026** | **+0.057** (t = 3.51) |

<!--/AUTO:scorer-->

**Trader.** Deep hedging: a policy trained by gradient through a simulator of the book chooses how
far to trade and at what gross. It learns every month from the months already paid for, starting
from last month's policy, one thread, deterministic. PPO, refit yearly, and the best fixed rate are
its yardsticks, on the half-scorer hedged book.

<!--AUTO:trader-->

| year | deep hedging, monthly | PPO, yearly | best fixed rate | trade all the way |
|---|---:|---:|---:|---:|
| 2019 | +1.2% | +1.0% | +2.1% | +3.3% |
| 2020 | -15.6% | -14.9% | -20.3% | -20.3% |
| 2021 | +14.6% | +17.3% | +21.4% | +21.4% |
| 2022 | +8.0% | +10.3% | +15.4% | +10.2% |
| 2023 | +5.4% | +6.2% | +7.9% | +7.3% |
| 2024 | -5.5% | -5.2% | -10.9% | -7.0% |
| 2025 | -0.9% | -2.0% | -0.7% | -2.1% |
| 2026 | +11.8% | +9.3% | +10.5% | +12.0% |

<!--/AUTO:trader-->

**The comparison.** ElasticNet, LightGBM and NN3 on all 147 characteristics through the same book.
They predict; costs sink them.

<!--AUTO:models-->

|  | IC t | gross | cost | net | turnover | **net IR** |
|---|---:|---:|---:|---:|---:|---:|
| **12-signal composite** | 3.78 | 17.6% | 3.9% | **+13.7%** | 44% | **+0.80** |
| LightGBM | 3.60 | 7.2% | 6.7% | +0.6% | 101% | -0.32 |
| NN3, seed 42 | 3.91 | 6.1% | 5.2% | +0.9% | 80% | -0.30 |
| ElasticNet | 2.62 | 2.5% | 6.3% | -3.8% | 100% | -0.78 |

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
| LambdaRank scorer | -29.93% | -34.11% |
| 12-signal composite | -0.01% | -0.01% |

<!--/AUTO:r2-->

## Agents

Local models from two vendors, pinned by SHA-256, at temperature 0, run by one command on Windows,
macOS, Linux or Lightning AI. No agent sets a weight: the crowd score reaches the book only through
the scorer, and only when the ship rule picks a scorer book. Prompts, tool definitions and every
transcript are in `prompts/agents/` and `submission/exhibits/agents/`.

**Bet against the AI crowd.** The brief warns that AI agents crowd into the same names. Our models
played AI assistants picking stocks for retail clients from anonymous cards, no names and no dates,
every month of 2016-2020. A small model learns what they buy, so every month to 2026 gets a crowd
score with no LLM at run time.

<!--AUTO:crowd-->

The crowd agent has not run yet; it runs with --agents.

<!--/AUTO:crowd-->

**Agents as researchers, scored like any model.** The research director sees every candidate's
months up to each December and chooses next year's book, one run a year; its picks are scored
against the rule and against random picks, and never trade. The discovery agent searches for
signals on 2015-2020 and is sealed on 2021-2026 beside a random search with the same budget. The
auditor hunts bugs we planted, the devil's advocate argues against the book, and the explainer says
why the book held its largest names.

<!--AUTO:agents-->

| agent | model | what happened |
|---|---|---|
| **Signal discovery** | Qwen3.8-27B | real names: 8 backtests, best in sample 1.14, sealed IR **-2.08**; coded names: 0 backtests, sealed IR **-1.82**; random search, same budget, sealed IR -0.44 |
| **Devil's advocate** | Gemma 4 26B-A4B | 5 critiques, 1 quoting a number no tool showed; run twice, 5 of 5 calls identical |
| **Reproducibility** | Qwen3.8-27B | found **0 of 7** planted bugs; 10 false alarms on the clean copy |

_From the earlier harness (Hermes Agent); the next `--all` run replaces them._

<!--/AUTO:agents-->

## Robustness

**2016-2020, the years the signals were not designed on:**

<!--AUTO:clean-->

|  | 2016-2020, not designed on | 2021-2026, the record |
|---|---|---|
| Information ratio | **-0.83** | +0.79 |
| Net return | -4.0% a year | +13.6% a year |
| Realized beta, CRSP market | **-0.25** (se 0.07) | -0.10 (se 0.09) |
| Worst spread drawdown | -33% | -15% |
| Turnover, one-way monthly | 46% | 44% |
| Net by year, compounded | 2016 +2%, 2017 0%, 2018 +15%, 2019 -6%, 2020 -27% | 2021 +39%, 2022 +30%, 2023 +10%, 2024 -9%, 2025 +1%, 2026 +13% |

<!--/AUTO:clean-->

**WRDS.** Delisted stocks leave on the decision date, takeover payouts are booked, and at most
<!--N:exhibits/wrds.json:report_dates.worst_early_share:.1%-->0.1%<!--/N--> of accounting updates came
before their report. 2021-2025 alone, the CRSP years, gives IR
<!--N:exhibits/pack.json:subperiod.crsp_era_2021_2025.information_ratio:.2f-->0.71<!--/N-->.

<!--AUTO:wrds-->

|  |  |
|---|---|
| Dated delistings and deletions applied | 8,346 securities |
| Rows already delisted at the decision, screened out | 598 |
| Held names already delisted | 0 |
| Held names taken over in their holding month | 50, 35 for cash; payouts -0.1 bp a year, closing cost 0.9 bp, already charged |
| Panel returns against CRSP, 2021-2025 | 83.9% within 1 bp, correlation 0.9995, 0.03% off by over 1% |
| Beta, S&P 500 with dividends, 2021-01 to 2025-12 | -0.02 (se 0.10) against -0.01 price-only; dividends 1.5% a year |
| Accounting updates with no new report behind them | worst signal 0.10%, rule 1%; a random month holds a release 33% of the time |
| Updates from a report dated on the decision day, held back a month | IR 0.82, net 14.0%; 1.2% of rows |
| Same code without WRDS, as a judge rebuilds it | IR 0.79, net 13.6%, beta -0.05 |
| IR on CRSP years only, 2021-2025 | 0.71 over 60 months |
| 2026, returns from Compustat | monthly spread 0.149 against 0.111-0.119; moves past ±50% 1.25% against 0.45%-0.75% |

<!--/AUTO:wrds-->

<!--AUTO:halves-->

| period | months | gross | cost | net | IR | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 17.6% | 3.9% | 13.6% | 0.79 | [-0.14, 1.68] |
| 2021-2022 | 24 | 34.9% | 4.1% | 30.8% | 1.81 | [1.18, 3.15] |
| **2023-2026** | 44 | 8.1% | 3.8% | 4.3% | 0.03 | [-1.17, 0.87] |
| 2022-2026 | 56 | 13.1% | 3.8% | 9.2% | 0.47 | [-0.64, 1.18] |
| CRSP years, 2021-2025 | 60 | 16.7% | 3.9% | 12.9% | 0.71 | [-0.29, 1.70] |

<!--/AUTO:halves-->

<!--AUTO:factors-->

|  | loading | t |
|---|---:|---:|
| Market (CRSP) | +0.05 | +1.03 |
| Size | -0.31 | -2.88 |
| Value | +0.21 | +2.09 |
| Profitability | +0.51 | +3.73 |
| Investment | +0.13 | +1.13 |
| Momentum | +0.00 | +0.02 |
| **Alpha after all six** | **8.3%** | **+1.85** |
| Alpha after three | 8.5% | +1.80 |
| Alpha after the S&P 500 alone | 14.1% | +2.46 |

The six explain 47% of the variance, over 67 months.

<!--/AUTO:factors-->

<!--AUTO:attribution-->

| signal | % a year of gross | t |
|---|---:|---:|
| `ope_be` | +3.1% | +1.23 |
| `ret_12_1` | +2.2% | +1.44 |
| `noa_gr1a` | +2.1% | +2.02 |
| `eqnetis_at` | +1.9% | +0.94 |
| `o_score` | +1.8% | +1.07 |
| `be_me` | +1.3% | +1.91 |
| `niq_su` | +1.1% | +1.52 |
| `chcsho_12m` | +0.6% | +0.36 |
| `at_gr1` | +0.6% | +0.42 |
| `qmj` | -0.4% | -0.17 |
| `ivol_capm_21d` | -0.7% | -0.82 |
| `gp_at` | -2.4% | -0.99 |
| explained by the twelve | +11.2% |  |
| residual | +6.4% |  |

<!--/AUTO:attribution-->

<!--AUTO:tails-->

|  |  |
|---|---:|
| 95% VaR, monthly | -4.61% |
| 95% CVaR, monthly | -5.83% |
| Skew | +0.34 |
| Excess kurtosis | +0.30 |
| Rolling 12-month windows with a negative IR | 35% of 57 |

<!--/AUTO:tails-->

<!--AUTO:placebo-->

| control | what changes | what happened |
|---|---|---|
| Permutation null | scores shuffled within sector and liquidity, 200 draws | gross +0.33% a year (sd 2.51%) against +17.6%; net IR -2.04 at 146% turnover |
| Inversion | every score times -1 | gross -17.6% against +17.6% |
| Stale scores | last month's ranking traded this month | net IR +0.45 against +0.94 over the same 67 months |

<!--/AUTO:placebo-->

**Selection is worse than not choosing.** Across 792 five-signal subsets, early and late IR
correlate at <!--N:exhibits/ml_metrics.json:subset_sweep.early_late_correlation:.2f-->−0.36<!--/N-->;
a budgeted search scored
<!--N:exhibits/selection.json:search_control.chosen_ir_in_search:+.2f-->+1.78<!--/N--> where it looked
and <!--N:exhibits/selection.json:search_control.chosen_ir_in_sealed:+.2f-->+0.33<!--/N--> after.

<!--AUTO:labels-->

| period | confirmed by | rows |
|---|---|---|
| 2021 2025 crsp | CRSP, dated | 16,819 |
| 2026 public filings | 8-K on or before | 1,896 |
| 2026 public filings | EDGAR, dated name and current ticker | 68 |
| 2026 public filings | EDGAR, dated correction | 10 |
| 2026 public filings | unconfirmed: no public source agrees on both | 3 |
| 2026 public filings | Compustat header, current | 3 |

99.98% of 18,799 holding rows confirmed. Corrected from SEC's dated record: H20 AMERICA → H2O AMERICA from 2025-05-01, CONTANGO ORE INC → CONTANGO SILVER & GOLD INC from 2026-03-30.

<!--/AUTO:labels-->

## Multiple testing and limits

<!--AUTO:deflation-->

|  | Sharpe luck alone produces | deflated-Sharpe probability |
|---|---:|---:|
| **At 123 eligible attempts** | 1.09 | **0.52** |
| At 1,641, every fit we ever ran | 1.43 | 0.23 |
| Missing returns at −30%, longs / both sides |  | IR 0.79 / 0.80 |

<!--/AUTO:deflation-->

We saw 2021-2026 while designing the signals · costs are modelled · 2026 returns come from
Compustat · the S&P 500 series is price-only · point-in-time accounting is checked, not guaranteed.
