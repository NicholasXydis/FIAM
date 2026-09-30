# Results

<!-- Tables between AUTO markers and numbers between N markers are written by fiam/report/docs.py. -->

<!--AUTO:made-->

Made by `uv run run.py --official --ml`.

<!--/AUTO:made-->

Holding months January 2021 to August 2026, after every modelled cost unless a table says otherwise.
Anyone rerunning the code on the same data gets the same numbers.

## Headline

<!--AUTO:headline-->

|  |  |
|---|---|
| Gross return (annualized) | 17.6% |
| **Net return (annualized)** | **12.5%** |
| CAGR (total return) | 16.1% |
| Volatility | 12.2% |
| **Information ratio vs TB3MS + 4%** | **0.69** |
| Sharpe ratio | 1.02 |
| Max drawdown (total return) | -11.0% |
| Hit rate | 54.4% |
| **Alpha** | **12.9%** (se 5.8%, t = 2.23, HAC) |
| **Realized beta** | **-0.04** (se 0.09) |
| Correlation with market | -0.06 |
| Market series | S&P 500 price index (FRED SP500), excludes dividends |
| Positions | 276 |
| Turnover, one-way monthly | 44% |
| Costs as share of gross | 29% |
| Holding months | 68, 2021-01 to 2026-08 |

_From code `4945ecd22bced975`._

<!--/AUTO:headline-->

IR <!--N:metrics.json:performance.information_ratio:.2f-->0.69<!--/N--> against cash plus 4%. Beta is
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
| 2021 | Composite | -2.06 | -1.26, Composite + 50% scorer + hedge |
| 2022 | Composite | -0.21 | -0.11, Composite + trader |
| 2023 | Composite | +1.76 | +1.77, Composite + trader |
| 2024 | Composite | +1.11 | +1.15, Composite + hedge |
| 2025 | Composite | -0.46 | -0.30, Composite + hedge |
| 2026 | Composite | -0.97 | -0.83, Composite + hedge |

| candidate, 2021-2026 | IR | net | cost | turnover | beta |
|---|---:|---:|---:|---:|---:|
| **Composite** | +0.70 | +12.5% | 5.0% | 44% | -0.05 |
| Composite + trader | +0.41 | +8.0% | 3.4% | 29% | -0.05 |
| Composite + hedge | +0.72 | +12.7% | 5.1% | 45% | -0.03 |
| Composite + hedge + trader | +0.63 | +11.0% | 4.7% | 42% | -0.04 |
| Composite + 25% scorer | +0.41 | +8.6% | 6.1% | 64% | -0.02 |
| Composite + 25% scorer + trader | +0.36 | +7.1% | 4.5% | 49% | -0.01 |
| Composite + 25% scorer + hedge | +0.54 | +10.2% | 6.1% | 65% | -0.02 |
| Composite + 25% scorer + hedge + trader | +0.37 | +6.9% | 3.3% | 34% | +0.01 |
| Composite + 50% scorer | -0.03 | +3.6% | 7.4% | 78% | +0.04 |
| Composite + 50% scorer + trader | -0.04 | +3.6% | 6.0% | 65% | +0.02 |
| Composite + 50% scorer + hedge | +0.07 | +4.8% | 7.5% | 81% | +0.02 |
| Composite + 50% scorer + hedge + trader | +0.06 | +4.6% | 5.7% | 63% | +0.01 |

<!--/AUTO:ship-->

## Committee pack

<!--AUTO:committee-->

|  |  |
|---|---|
| Average monthly return, total | 1.31% |
| Annualized, arithmetic / geometric (CAGR) | 15.7% / 16.1% |
| Cumulative return, Jan 2021 to Aug 2026 | 133.3% |
| Best month | +10.2%, 2022-04 |
| Worst month | -7.7%, 2024-10 |
| Months beating the benchmark | 54% |
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
| Return a year, arithmetic | 15.7% | 7.3% | 13.8% |
| Return a year, geometric (CAGR) | 16.1% | 7.5% | 13.5% |
| Cumulative | 133.3% | 50.9% | 104.6% |
| Volatility | 12.1% | 0.6% | 15.1% |
| Sharpe ratio | 1.02 |  | 0.70 |
| Max drawdown | -11.0% | 0.0% | -24.8% |
| Best month | +10.2%, 2022-04 | +0.8%, 2023-10 | +10.4%, 2026-04 |
| Worst month | -7.7%, 2024-10 | +0.3%, 2021-04 | -9.3%, 2022-09 |

<!--/AUTO:comparison-->

<!--AUTO:years-->

| year | strategy | T-bill + 4% | S&P 500 (price) | active |
|---|---:|---:|---:|---:|
| 2021 | +37.6% | +4.1% | +26.9% | +33.5% |
| 2022 | +31.1% | +6.2% | -19.4% | +24.9% |
| 2023 | +14.5% | +9.5% | +24.2% | +5.1% |
| 2024 | -5.2% | +9.3% | +23.3% | -14.5% |
| 2025 | +3.5% | +8.4% | +16.4% | -4.9% |
| 2026 (Jan-Aug) | +15.1% | +5.2% | +12.3% | +9.9% |

<!--/AUTO:years-->

Each side before costs, its contribution to NAV and its return per dollar held:

<!--AUTO:legs-->

| leg | contribution a year | per dollar in the leg | volatility | names | median size | median daily $ volume |
|---|---:|---:|---:|---:|---:|---:|
| long | +14.1% | +17.7% | 15.8% | 144 | $6.1bn | $65m |
| short | +3.4% | +4.3% | 20.3% | 132 | $1.8bn | $24m |

Short book by weight: 68% small-cap or below, 20% micro-cap, 24% in borrow tiers of 3% a year or more. In 2021-2025, 23% of it had more than 10% of its shares already sold short.

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
| 2021-2023 | +0.02 | 0.11 | +0.21 |
| 2024-2026 | -0.16 | 0.09 | -1.86 |
| full period | -0.04 | 0.09 | -0.49 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.51 |

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
| Gross within a month, largest | 193.9%, 2021-02 |
| Months above 200% on some day | 0 of 60 |
| Net within a month, largest absolute | 10.8% |
| Volatility, daily / monthly | 13.7% / 12.5% |
| Max drawdown, daily / monthly | -18.1% / -11.0% |
| One-day VaR 95% / 99%, CVaR 95% | -1.31% / -1.98%, -1.74% |
| Worst day | -3.09%, 2021-02-03 |
| Daily path compounded to months, against returns.csv | correlation 1.0000, largest gap 0.013% |

<!--/AUTO:daily-->

**Stress windows**, fixed in advance, on the daily path. The 2020 windows use the same code started
in December 2015, since the record starts in 2021.

<!--AUTO:stress-->

| window | strategy | S&P 500 | worst fall inside |
|---|---:|---:|---:|
| 2020 crash, Feb 19 to Mar 23 | +1.3% | -33.9% | -5.2% |
| 2020 rebound, Mar 24 to Jun 8 | -6.4% | +32.1% | -13.4% |
| 2022, rates up | +31.1% | -20.0% | -11.0% |
| 2023 AI rally, Jan to Jul | +8.0% | +20.0% | -6.0% |
| October 2024, the worst month | -7.7% | -0.1% | -9.7% |

Trading a day late, 60 months: IR +0.63 against +0.62 on time, +0.0% a year.

<!--/AUTO:stress-->

## Costs and compliance

Every rule was fixed in `PREREGISTRATION.md` before it ran, and lives in `fiam/costs.py`:

- **Commission:** IBKR Pro fixed, $0.005 a share, at least $1 and at most 1% of the trade, on the
  book's real whole shares at $10M.
- **Regulatory fees:** the SEC Section 31 fee on sales at its 2021-2026 high ($27.80 a million),
  FINRA's Trading Activity Fee ($0.000195 a share sold, at most $9.79) and its audit-trail fee
  ($0.000003 a share).
- **Spread:** half the closing quoted spread, calibrated to CRSP bid and ask quotes on 2015-2020
  only.
- **Impact:** the square-root law: daily volatility × √(trade ÷ daily dollar volume), coefficient 1.
- **Borrow:** by short interest over shares outstanding: 0.3% a year under 5%, 1% to 10%, 3% to
  20%, 8% above; micro-caps at least 1%. Short interest is used a month late, as it is published.
- **Financing:** cash and short proceeds earn the benchmark less 0.5%, as IBKR pays.

Spread, impact and borrow are models, not observed fills.

<!--AUTO:costs-->

|  | % of NAV a year |
|---|---|
| Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA) | 0.26% |
| Half-spread (calibrated to CRSP quotes) | 0.84% |
| Market impact (square-root law) | 2.22% |
| Borrow (short-interest tiers) | 1.27% |
| Financing (benchmark less 0.5% on cash) | 0.50% |
| **Total** | 5.09% |
| Annual cost at which active return reaches zero | 13.6%, 2.66 times today's |

<!--/AUTO:costs-->

**If the costs are wrong, or the fund is bigger.** The same trades, charged again. Capacity keeps
the $10M weights, so it shows what costs do, not a book re-optimized for size.

<!--AUTO:implementation-->

|  | IR | net | cost | sold in a day at 20% of volume; 95th percentile |
|---|---:|---:|---:|---:|
| As modelled, $10M | +0.69 | +12.5% | 5.1% |  |
| Every cost doubled | +0.27 | +7.4% | 10.2% |  |
| Impact coefficient 0.5 | +0.78 | +13.6% | 4.0% |  |
| $10M of capital | +0.69 | +12.5% | 5.1% | 100%; 0.1 days |
| $100M of capital | +0.30 | +7.7% | 9.9% | 90%; 1.2 days |
| $500M of capital | -0.41 | -1.1% | 18.7% | 64%; 6.0 days |
| $1B of capital | -0.93 | -7.8% | 25.4% | 50%; 12.0 days |

<!--/AUTO:implementation-->

<!--AUTO:compliance-->

| rule | limit | measured |
|---|---|---|
| Positions | 100-500 | 276 on average |
| Gross exposure | ≤ 200% | max 159.96% |
| Net exposure | −50% to +50%; ours exact before rounding | max abs 0.00% |
| Sector, 11 GICS + `XX` | 1% target | max 1.04% |
| Single name | 1.5% target | max 1.51% |
| Ex-ante beta | ±0.02 | mean +0.020 |
| Realized beta | build fails outside ±0.20 | -0.04 (se 0.09) |

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

| year | deep hedging, monthly | PPO, yearly | Gârleanu-Pedersen constant rate | trade all the way |
|---|---:|---:|---:|---:|
| 2019 | +0.4% | +0.5% | +1.2% | +1.7% |
| 2020 | -17.0% | -14.2% | -21.6% | -23.2% |
| 2021 | +14.2% | +17.3% | +21.2% | +20.0% |
| 2022 | +8.4% | +9.8% | +15.1% | +8.0% |
| 2023 | +4.8% | +6.0% | +7.9% | +6.1% |
| 2024 | -6.6% | -5.8% | -10.8% | -8.7% |
| 2025 | -1.7% | -2.9% | -0.6% | -3.2% |
| 2026 | +12.4% | +8.2% | +10.5% | +11.6% |

<!--/AUTO:trader-->

**The learning curve.** Each year's models train on every year before it, so they see more
data as time passes. The stock picker's IC and each teacher's accuracy, year by year:

<!--AUTO:learning-->

The stock picker has not run yet.

<!--/AUTO:learning-->

**The comparison.** ElasticNet, LightGBM and NN3 on all 147 characteristics through the same book.
They predict; costs sink them.

<!--AUTO:models-->

|  | IC t | gross | cost | net | turnover | **net IR** |
|---|---:|---:|---:|---:|---:|---:|
| **12-signal composite** | 3.78 | 17.6% | 5.0% | **+12.5%** | 44% | **+0.70** |
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

**Every way of choosing, walked forward.** Each year a rule sees only the months before it. Both
windows have now been seen, so new rules take their settings from published research, never from
these tables.

<!--AUTO:walk-->

|  | 2016-2020 | 2021-2022 | 2023-2026 | 2021-2026 |
|---|---:|---:|---:|---:|
| Shipped book |  | +1.74 (24) | -0.11 (44) | +0.69 (68) |
| Ship rule, walked forward | -2.06 (24) | +1.76 (24) | -0.11 (44) | +0.70 (68) |
| Composite every year | -2.06 (24) | +1.76 (24) | -0.11 (44) | +0.70 (68) |

IR by window, months in brackets, on the CRSP market. Picks start in 2019, the first year with two years of candidates behind it. Random picks of one candidate a year average IR -0.19; the rule beats 90% of them.

<!--/AUTO:walk-->

**Construction v2, tested once as pre-registered.** Five rules aimed at the losses Phase 2 traced:
a lag-corrected hedge beta, a ±10% net band for true beta neutrality, no special-borrow shorts
with volatility-scaled short caps, liquidity-scaled caps, and Daniel-Moskowitz crash protection.
Both books carry the Phase 2 costs over 2016-2026.

<!--AUTO:construction-->

|  | current | v2 |
|---|---:|---:|
| IR, 2016-2026 | -0.00 | -0.17 |
| IR, 2016-2020 | -1.00 | -1.28 |
| IR, 2021-2026 | +0.70 | +0.68 |
| Net a year / costs a year | +4.0% / 5.1% | +2.3% / 3.7% |
| Beta, monthly (se) | -0.18 (0.06) | -0.15 (0.07) |
| Beta, daily 2016-2025 (se) | -0.018 (0.018) | -0.039 (0.013) |
| Worst drawdown | -38.2% | -33.8% |
| Largest gross on any day | 202.6% | 200.5% |

IR at least the current book's: **failed**; beta closer to zero, monthly and daily: **failed**; worst drawdown no deeper: passed; every rule, every month and day: **failed**. **Not shipped: the current construction stays.** Each rule alone, IR on 2016-2026: adjusted beta -0.02, net band -0.10, short rules -0.09, liquidity caps -0.07, crash protection -0.01.

<!--/AUTO:construction-->

**Is it stock picking or style?** Amendment 4 held the book's size, value, profitability,
investment and momentum exposures near zero and judged it on all eleven years.

<!--AUTO:neutral-->

|  | current | factor-neutral |
|---|---|---|
| IR, 2016-2026 | -0.00 | -0.89 |
| IR, 2016-2020 | -1.00 | -1.46 |
| IR, 2021-2022 | +1.76 | +0.00 |
| IR, 2023-2026 | -0.11 | -0.85 |
| Beta, monthly / daily | -0.18 / -0.018 | -0.07 / -0.001 |
| Worst drawdown | -38.2% | -32.2% |
| Loadings: size, value, profitability, investment, momentum | -0.30, +0.21, +0.49, +0.19, +0.07 | -0.17, +0.04, +0.31, +0.03, -0.05 |
| **Six-factor alpha a year (t)** | +2.9% (+1.05) | -4.2% (-1.69) |

**Not shipped: the current construction stays.**

<!--/AUTO:neutral-->

**2016-2020, the years the signals were not designed on:**

<!--AUTO:clean-->

|  | 2016-2020, not designed on | 2021-2026, the record |
|---|---|---|
| Information ratio | **-1.00** | +0.69 |
| Net return | -5.7% a year | +12.5% a year |
| Realized beta, CRSP market | **-0.25** (se 0.07) | -0.10 (se 0.09) |
| Worst spread drawdown | -35% | -17% |
| Turnover, one-way monthly | 46% | 44% |
| Net by year, compounded | 2016 +0%, 2017 -2%, 2018 +13%, 2019 -7%, 2020 -29% | 2021 +38%, 2022 +28%, 2023 +9%, 2024 -10%, 2025 -1%, 2026 +12% |

<!--/AUTO:clean-->

**WRDS.** Delisted stocks leave on the decision date, takeover payouts are booked, and at most
<!--N:exhibits/wrds.json:report_dates.worst_early_share:.1%-->0.1%<!--/N--> of accounting updates came
before their report. 2021-2025 alone, the CRSP years, gives IR
<!--N:exhibits/pack.json:subperiod.crsp_era_2021_2025.information_ratio:.2f-->0.62<!--/N-->.

<!--AUTO:wrds-->

|  |  |
|---|---|
| Dated delistings and deletions applied | 8,346 securities |
| Rows already delisted at the decision, screened out | 598 |
| Held names already delisted | 0 |
| Held names taken over in their holding month | 50, 35 for cash; payouts -0.1 bp a year, closing cost 0.5 bp, already charged |
| Panel returns against CRSP, 2021-2025 | 83.9% within 1 bp, correlation 0.9995, 0.03% off by over 1% |
| Beta, S&P 500 with dividends, 2021-01 to 2025-12 | -0.02 (se 0.10) against -0.01 price-only; dividends 1.5% a year |
| Accounting updates with no new report behind them | worst signal 0.10%, rule 1%; a random month holds a release 33% of the time |
| Updates from a report dated on the decision day, held back a month | IR 0.68, net 12.3%; 1.2% of rows |
| Same code without WRDS, as a judge rebuilds it | IR 0.69, net 12.5%, beta -0.04 |
| IR on CRSP years only, 2021-2025 | 0.62 over 60 months |
| 2026, returns from Compustat | monthly spread 0.149 against 0.111-0.119; moves past ±50% 1.25% against 0.45%-0.75% |

<!--/AUTO:wrds-->

<!--AUTO:halves-->

| period | months | gross | cost | net | IR | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 17.6% | 5.1% | 12.5% | 0.69 | [-0.24, 1.60] |
| 2021-2022 | 24 | 34.9% | 5.1% | 29.9% | 1.74 | [1.10, 3.09] |
| **2023-2026** | 44 | 8.1% | 5.1% | 3.0% | -0.11 | [-1.33, 0.71] |
| 2022-2026 | 56 | 13.1% | 5.1% | 8.0% | 0.36 | [-0.76, 1.06] |
| CRSP years, 2021-2025 | 60 | 16.7% | 5.0% | 11.7% | 0.62 | [-0.41, 1.62] |

<!--/AUTO:halves-->

<!--AUTO:factors-->

|  | loading | t |
|---|---:|---:|
| Market (CRSP) | +0.05 | +1.09 |
| Size | -0.31 | -2.96 |
| Value | +0.21 | +2.12 |
| Profitability | +0.52 | +3.75 |
| Investment | +0.13 | +1.14 |
| Momentum | +0.00 | +0.03 |
| **Alpha after all six** | **7.0%** | **+1.56** |
| Alpha after three | 7.3% | +1.52 |
| Alpha after the S&P 500 alone | 12.9% | +2.23 |

The six explain 48% of the variance, over 67 months.

<!--/AUTO:factors-->

**The same loadings in each half.** Twelve months cannot pin six loadings, so the split is by
window, not by year.

<!--AUTO:factor_windows-->

| loading (t) | 2021-2022 | 2023-2026 |
|---|---:|---:|
| Market | -0.04 (-0.8) | -0.01 (-0.2) |
| Size | -0.35 (-2.0) | -0.11 (-0.7) |
| Value | +0.43 (+4.0) | -0.12 (-0.8) |
| Profitability | +0.92 (+7.9) | +0.30 (+2.8) |
| Investment | -0.12 (-0.7) | +0.23 (+0.9) |
| Momentum | +0.21 (+1.8) | -0.02 (-0.3) |
| Alpha a year | +4.7% (+1.9) | +5.7% (+0.7) |

<!--/AUTO:factor_windows-->

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

**Each signal by year**, % of NAV, before costs:

<!--AUTO:signal_years-->

| signal | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| `ope_be` | +9.5% | +8.1% | +2.2% | +3.0% | -1.3% | -3.9% |
| `ret_12_1` | +3.3% | +6.4% | -2.3% | +3.9% | -0.0% | +0.9% |
| `noa_gr1a` | +3.2% | +2.7% | +1.1% | +2.1% | +0.7% | +1.9% |
| `eqnetis_at` | +12.8% | -3.4% | +1.0% | +1.5% | -4.7% | +3.4% |
| `o_score` | +0.4% | +3.3% | +4.9% | -1.0% | +1.9% | +0.6% |
| `be_me` | +6.1% | +0.6% | +0.1% | +0.4% | +0.1% | +0.4% |
| `niq_su` | -0.3% | +3.0% | -0.1% | +2.9% | -0.9% | +1.7% |
| `chcsho_12m` | -1.9% | +3.9% | +4.7% | -6.3% | +0.3% | +2.8% |
| `at_gr1` | +2.1% | +6.3% | -2.9% | -1.5% | -0.7% | -0.0% |
| `qmj` | -1.8% | +0.2% | -5.5% | +3.9% | +0.3% | +0.8% |
| `ivol_capm_21d` | -0.9% | +1.3% | -1.7% | +1.2% | -2.2% | -1.6% |
| `gp_at` | +3.6% | -5.4% | +3.5% | -6.4% | -6.5% | -2.5% |

<!--/AUTO:signal_years-->

**The ten worst months**, traced to their source:

<!--AUTO:worst-->

| month | gross | long / short leg | worst sectors (GICS) | worst signals |
|---|---|---|---|---|
| 2024-10 | -7.7% | -3.6% / -4.1% | 35 -3.8%, 45 -1.8% | `gp_at` -3.3%, `chcsho_12m` -2.5% |
| 2021-01 | -4.4% | +6.1% / -10.5% | 35 -2.8%, 20 -1.7% | `chcsho_12m` -3.2%, `qmj` -3.1% |
| 2022-08 | -4.3% | -3.4% / -0.9% | 35 -3.0%, 20 -1.5% | `gp_at` -2.4%, `o_score` -1.4% |
| 2025-07 | -4.2% | +0.8% / -4.9% | 35 -4.6%, 10 -0.7% | `gp_at` -2.4%, `ret_12_1` -0.6% |
| 2023-12 | -3.6% | +9.2% / -12.8% | 35 -2.3%, 45 -1.3% | `gp_at` -2.1%, `ret_12_1` -1.8% |
| 2023-05 | -2.6% | -1.1% / -1.5% | 25 -2.2%, 45 -0.8% | `ope_be` -2.2%, `at_gr1` -1.0% |
| 2024-07 | -2.2% | +5.2% / -7.5% | 50 -1.8%, 45 -0.4% | `gp_at` -2.2%, `o_score` -2.1% |
| 2026-08 | -2.0% | +0.3% / -2.3% | 35 -2.1%, 20 -0.9% | `ope_be` -2.3%, `ret_12_1` -1.5% |
| 2025-06 | -1.8% | +3.2% / -5.0% | 45 -1.1%, 35 -1.0% | `gp_at` -3.3%, `chcsho_12m` -1.2% |
| 2021-06 | -1.8% | +3.3% / -5.1% | 25 -1.8%, 15 -1.1% | `chcsho_12m` -2.2%, `ope_be` -2.1% |

<!--/AUTO:worst-->

<!--AUTO:tails-->

|  |  |
|---|---:|
| 95% VaR, monthly | -4.70% |
| 95% CVaR, monthly | -5.93% |
| Skew | +0.35 |
| Excess kurtosis | +0.29 |
| Rolling 12-month windows with a negative IR | 42% of 57 |

<!--/AUTO:tails-->

<!--AUTO:placebo-->

| control | what changes | what happened |
|---|---|---|
| Permutation null | scores shuffled within sector and liquidity, 200 draws | gross +0.33% a year (sd 2.51%) against +17.6%; net IR -2.38 at 146% turnover |
| Inversion | every score times -1 | gross -17.6% against +17.6% |
| Stale scores | last month's ranking traded this month | net IR +0.35 against +0.79 over the same 67 months |

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
| **At 123 eligible attempts** | 1.09 | **0.43** |
| At 1,642, every fit we ever ran | 1.43 | 0.16 |
| Missing returns at −30%, longs / both sides |  | IR 0.69 / 0.70 |

<!--/AUTO:deflation-->

We saw 2021-2026 while designing the signals · costs are modelled · 2026 returns come from
Compustat · the S&P 500 series is price-only · point-in-time accounting is checked, not guaranteed.
