# Results

<!-- Tables between AUTO markers and numbers between N markers are written by fiam/report/docs.py. -->

<!--AUTO:made-->

Made by `uv run run.py --official --ml`, reusing 15 slow steps unchanged since the run that made them.

<!--/AUTO:made-->

Holding months January 2021 to August 2026, after every modelled cost unless a table says otherwise.
Anyone rerunning the code on the same data gets the same numbers.

## Headline

<!--AUTO:headline-->

|  |  |
|---|---|
| Gross return (annualized) | 13.7% |
| **Net return (annualized)** | **8.5%** |
| CAGR (total return) | 11.8% |
| Volatility | 11.4% |
| **Information ratio vs TB3MS + 4%** | **0.40** |
| Sharpe ratio | 0.75 |
| Max drawdown (total return) | -11.0% |
| Hit rate | 54.4% |
| **Alpha** | **9.0%** (se 5.1%, t = 1.78, HAC) |
| **Realized beta** | **-0.05** (se 0.09) |
| Correlation with market | -0.06 |
| Market series | S&P 500 price index (FRED SP500), excludes dividends |
| Positions | 278 |
| Turnover, one-way monthly | 46% |
| Costs as share of gross | 38% |
| Holding months | 68, 2021-01 to 2026-08 |

_From code `4ffd950c7dd38c8e`._

<!--/AUTO:headline-->

IR <!--N:metrics.json:performance.information_ratio:.2f-->0.40<!--/N--> against cash plus 4%. Beta is
the rules' regression on the S&P 500 price index with HAC errors; the build fails outside ±0.20.

## How the book is chosen

Twelve candidate books: the 12-signal composite with 0, 25 or 50% of the stock picker blended in,
each with and without the learned hedge and the trader. Each year a rule written in advance looks
only at the two years before: the composite ships unless another book beat its IR there by 0.25 with
beta inside ±0.15; then the twin with the other hedge ships if its beta sat nearer zero.

<!--AUTO:ship-->

| holding year | shipped book | composite IR, two years before | best other |
|---|---|---|---|
| 2021 | Composite + 50% scorer + hedge + trader | -2.06 | -0.71, Composite + 50% scorer + hedge |
| 2022 | Composite | -0.21 | +0.04, Composite + 50% scorer |
| 2023 | Composite + hedge | +1.76 | +1.77, Composite + trader |
| 2024 | Composite | +1.11 | +1.15, Composite + hedge |
| 2025 | Composite + hedge | -0.46 | -0.30, Composite + hedge |
| 2026 | Composite + hedge | -0.97 | -0.83, Composite + hedge |

| candidate, 2021-2026 | IR | net | cost | turnover | beta |
|---|---:|---:|---:|---:|---:|
| **Composite** | +0.70 | +12.5% | 5.0% | 44% | -0.05 |
| Composite + trader | +0.41 | +8.0% | 3.4% | 29% | -0.05 |
| **Composite + hedge** | +0.72 | +12.7% | 5.1% | 45% | -0.03 |
| Composite + hedge + trader | +0.63 | +11.0% | 4.7% | 42% | -0.04 |
| Composite + 25% scorer | +0.31 | +7.5% | 5.5% | 54% | -0.04 |
| Composite + 25% scorer + trader | +0.22 | +6.1% | 4.0% | 38% | -0.02 |
| Composite + 25% scorer + hedge | +0.41 | +8.9% | 5.5% | 54% | -0.04 |
| Composite + 25% scorer + hedge + trader | +0.31 | +6.8% | 3.1% | 27% | -0.03 |
| Composite + 50% scorer | -0.05 | +3.5% | 6.3% | 60% | +0.02 |
| Composite + 50% scorer + trader | -0.28 | +1.4% | 5.0% | 47% | +0.02 |
| Composite + 50% scorer + hedge | +0.01 | +4.2% | 6.2% | 61% | -0.03 |
| **Composite + 50% scorer + hedge + trader** | -0.09 | +3.1% | 4.9% | 47% | -0.04 |

<!--/AUTO:ship-->

**What the rule did.** For 2021 it left the composite. Over 2019-2020 the composite had lost 32.8%
in 2020 alone, and the half-stock-picker book had lost a third as much. The composite then had its
best year, +33.8% in 2021 against +12.2% for the book the rule chose. That one switch is most of the
gap between the composite kept every year (IR 0.70) and the book we ship (0.40). We ship the rule's
book because we wrote the rule first: a rule that judges two years of results follows what just
worked, and here it did so just before a reversal. Every other year it kept the composite, four times
with the learned hedge.

## Committee pack

<!--AUTO:committee-->

|  |  |
|---|---|
| Average monthly return, total | 0.98% |
| Annualized, arithmetic / geometric (CAGR) | 11.8% / 11.8% |
| Cumulative return, Jan 2021 to Aug 2026 | 87.9% |
| Best month | +10.2%, 2022-04 |
| Worst month | -9.2%, 2021-01 |
| Months beating the benchmark | 54% |
| Holdings, long / short | 144 / 134 |
| Gross exposure, average (range) | 153.46% (119.93% to 159.95%) |
| Net exposure, average (range) | 0.00% (0.00% to 0.00%) |
| Position weight, average / largest | 0.55% / 1.51% |
| Share of gross in the ten largest names | 9.4% |
| Turnover, one-way monthly, average (range) | 46% (28% to 94%) |

<!--/AUTO:committee-->

<!--AUTO:comparison-->

|  | strategy | T-bill + 4% | S&P 500 (price) |
|---|---:|---:|---:|
| Return a year, arithmetic | 11.8% | 7.3% | 13.8% |
| Return a year, geometric (CAGR) | 11.8% | 7.5% | 13.5% |
| Cumulative | 87.9% | 50.9% | 104.6% |
| Volatility | 11.3% | 0.6% | 15.1% |
| Sharpe ratio | 0.75 |  | 0.70 |
| Max drawdown | -11.0% | 0.0% | -24.8% |
| Best month | +10.2%, 2022-04 | +0.8%, 2023-10 | +10.4%, 2026-04 |
| Worst month | -9.2%, 2021-01 | +0.3%, 2021-04 | -9.3%, 2022-09 |

<!--/AUTO:comparison-->

<!--AUTO:years-->

| year | strategy | T-bill + 4% | S&P 500 (price) | active |
|---|---:|---:|---:|---:|
| 2021 | +9.9% | +4.1% | +26.9% | +5.8% |
| 2022 | +30.6% | +6.2% | -19.4% | +24.4% |
| 2023 | +15.8% | +9.5% | +24.2% | +6.4% |
| 2024 | -4.9% | +9.3% | +23.3% | -14.2% |
| 2025 | +5.3% | +8.4% | +16.4% | -3.1% |
| 2026 (Jan-Aug) | +12.8% | +5.2% | +12.3% | +7.6% |

<!--/AUTO:years-->

Each side before costs, its contribution to NAV and its return per dollar held:

<!--AUTO:legs-->

| leg | contribution a year | per dollar in the leg | volatility | names | median size | median daily $ volume |
|---|---:|---:|---:|---:|---:|---:|
| long | +11.8% | +16.0% | 15.7% | 144 | $6.8bn | $73m |
| short | +1.8% | +2.8% | 19.7% | 134 | $1.7bn | $23m |

Short book by weight: 71% small-cap or below, 22% micro-cap, 23% in borrow tiers of 3% a year or more. In 2021-2025, 22% of it had more than 10% of its shares already sold short.

<!--/AUTO:legs-->

<!--AUTO:top-->

|  | long | weight | short | weight |
|---|---|---|---|---|
| 1 | PRG, PROG HOLDINGS INC | 0.97% | NEXT, NextDecade Corp | -0.86% |
| 2 | MEDP, Medpace Holdings, Inc. | 0.89% | CWST, CASELLA WASTE SYSTEMS INC | -0.66% |
| 3 | ALGN, ALIGN TECHNOLOGY INC | 0.75% | KRUS, KURA SUSHI USA, INC. | -0.64% |
| 4 | DDS, DILLARD'S, INC. | 0.75% | VRDN, Viridian Therapeutics, Inc. | -0.61% |
| 5 | MTD, METTLER TOLEDO INTERNATIONAL INC | 0.71% | MSTR, Strategy Inc | -0.58% |
| 6 | LRCX, LAM RESEARCH CORP | 0.70% | CYTK, CYTOKINETICS INC | -0.57% |
| 7 | SIGA, S I G A TECHNOLOGIES INC | 0.69% | COGT, Cogent Biosciences, Inc. | -0.53% |
| 8 | DFIN, Donnelley Financial Solutions, Inc. | 0.66% | ABX, Abacus Global Management, Inc. | -0.51% |
| 9 | CCRN, CROSS COUNTRY HEALTHCARE INC | 0.65% | IONS, IONIS PHARMACEUTICALS INC | -0.51% |
| 10 | BLDR, BUILDERS FIRSTSOURCE INC | 0.63% | WOLF, WOLFSPEED INC NEW | -0.49% |

<!--/AUTO:top-->

## Neutrality, measured monthly and daily

The book is neutral by construction: dollar-neutral, neutral to its hedge beta and to each sector at
every rebalance. What it realized is measured here, not assumed. Twelve monthly returns pin a beta
only to about ±0.3, so the rolling chart shades where a zero-beta book would wander; daily returns
pin it far tighter, and show a small short tilt.

<!--AUTO:drift-->

| period | beta | se | t |
|---|---:|---:|---:|
| 2021-2023 | +0.00 | 0.11 | +0.00 |
| 2024-2026 | -0.12 | 0.08 | -1.56 |
| full period | -0.05 | 0.09 | -0.51 |
| 2021-2025, 1,255 days | -0.10 | 0.03 | -3.65 |

23% of 57 rolling 12-month windows sit outside ±0.20, and 0% outside the range a zero-beta book with our residual risk would reach 95% of the time.

<!--/AUTO:drift-->

Weights stay fixed within each month. Marked every trading day of 2021-2025 on CRSP daily prices,
at a <!--N:metrics.json:compliance.gross_exposure_max:.0%-->160%<!--/N--> gross target; the rules
measure the limits at each rebalance.

<!--AUTO:daily-->

|  |  |
|---|---|
| Trading days | 1,255, 2021-01 to 2025-12 |
| Gross at rebalance, largest | 160.0% |
| Gross within a month, largest | 199.8%, 2021-01 |
| Months above 200% on some day | 0 of 60 |
| Net within a month, largest absolute | 10.8% |
| Volatility, daily / monthly | 12.9% / 11.5% |
| Max drawdown, daily / monthly | -16.3% / -11.0% |
| One-day VaR 95% / 99%, CVaR 95% | -1.25% / -1.92%, -1.69% |
| Worst day | -3.19%, 2021-01-26 |
| Daily path compounded to months, against returns.csv | correlation 0.9998, largest gap 0.452% |

<!--/AUTO:daily-->

**Stress windows**, fixed in advance, on the daily path. The 2020 windows use the same code started
in December 2015, since the record starts in 2021.

<!--AUTO:stress-->

| window | strategy | S&P 500 | worst fall inside |
|---|---:|---:|---:|
| 2020 crash, Feb 19 to Mar 23 | +1.3% | -33.9% | -5.2% |
| 2020 rebound, Mar 24 to Jun 8 | -6.4% | +32.1% | -13.4% |
| 2022, rates up | +30.6% | -20.0% | -11.1% |
| 2023 AI rally, Jan to Jul | +9.0% | +20.0% | -5.6% |
| October 2024, the worst month | -7.7% | -0.1% | -9.7% |

Trading a day late, 60 months: IR +0.27 against +0.32 on time, +0.6% a year.

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
|---|---:|
| Commission and regulatory fees (IBKR Pro fixed, SEC, FINRA) | 0.27% |
| Half-spread (calibrated to CRSP quotes) | 0.87% |
| Market impact (square-root law) | 2.30% |
| Borrow (short-interest tiers) | 1.21% |
| Financing (benchmark less 0.5% on cash) | 0.50% |
| **Total** | 5.15% |
| Annual cost at which active return reaches zero | 9.7%, 1.88 times today's |

<!--/AUTO:costs-->

**If the costs are wrong, or the fund is bigger.** The same trades, charged again. Capacity keeps
the $10M weights, so it shows what costs do, not a book re-optimized for size.

<!--AUTO:implementation-->

|  | IR | net | cost | sold in a day at 20% of volume; 95th percentile |
|---|---:|---:|---:|---:|
| As modelled, $10M | +0.40 | +8.5% | 5.1% |  |
| Every cost doubled | -0.06 | +3.4% | 10.3% |  |
| Impact coefficient 0.5 | +0.50 | +9.7% | 4.0% |  |
| $10M of capital | +0.40 | +8.5% | 5.1% | 100%; 0.1 days |
| $100M of capital | -0.04 | +3.5% | 10.1% | 90%; 1.2 days |
| $500M of capital | -0.83 | -5.6% | 19.3% | 64%; 5.9 days |
| $1B of capital | -1.40 | -12.6% | 26.2% | 50%; 11.9 days |

<!--/AUTO:implementation-->

<!--AUTO:compliance-->

| rule | limit | measured |
|---|---|---|
| Positions | 100-500 | 278 on average |
| Gross exposure | ≤ 200% | max 159.95% |
| Net exposure | −50% to +50%; ours exact before rounding | max abs 0.00% |
| Sector, 11 GICS + `XX` (ours) | 1% before whole-share rounding | max 1.04% after it |
| Single name (ours) | 1.5% before whole-share rounding | max 1.51% after it |
| Ex-ante beta | ±0.02 | mean +0.019 |
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
| next quarter's earnings surprise | 0.52 |  |

<!--/AUTO:teachers-->

**The stock picker.** LightGBM ranks stocks by next month's return **less** their sector, beta and
style, so it must pick stocks, not styles. It reads the 147 characteristics, the 8-K counts, FinBERT's
reading of each filing, the triage and analyst agents as small models learned them from older
filings, the crowd score and the teachers. It trains on
the brief's folds, averages five seeds, and its scores are smoothed over three months so it trades
less.

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

**Trader.** Deep hedging: a policy trained by gradient through a simulator of the book chooses how
far to trade and at what gross. It learns every month from the months already paid for, starting
from last month's policy, one thread, deterministic. PPO, refit yearly, and the best fixed rate are
its yardsticks, on the half-scorer hedged book.

<!--AUTO:trader-->

| year | deep hedging, monthly | PPO, yearly | Gârleanu-Pedersen constant rate | trade all the way |
|---|---:|---:|---:|---:|
| 2019 | +1.5% | +1.7% | +4.2% | +5.5% |
| 2020 | -7.7% | -8.6% | -11.6% | -11.6% |
| 2021 | +12.4% | +15.3% | +19.6% | +16.4% |
| 2022 | +17.5% | +14.6% | +20.1% | +18.4% |
| 2023 | +2.5% | +7.3% | +6.6% | +3.9% |
| 2024 | -11.4% | -9.6% | -13.2% | -11.0% |
| 2025 | -4.8% | -4.8% | -6.3% | -4.8% |
| 2026 | +6.6% | +4.0% | +6.4% | +4.9% |

<!--/AUTO:trader-->

**The learning curve.** Each year's models train on every year before it, so they see more
data as time passes. The stock picker's IC and each teacher's accuracy, year by year:

<!--AUTO:learning-->

| year | years of training | stock picker IC | surprise teacher | beta teacher | crowding teacher | revisions teacher |
|---|---:|---:|---:|---:|---:|---:|
| 2019 | 4 | +0.046 | 0.51 | 0.43 | 0.70 | 0.55 |
| 2020 | 5 | -0.000 | 0.47 | 0.37 | 0.64 | 0.49 |
| 2021 | 6 | +0.138 | 0.52 | 0.37 | 0.57 | 0.53 |
| 2022 | 7 | +0.120 | 0.55 | 0.67 | 0.62 | 0.52 |
| 2023 | 8 | +0.014 | 0.61 | 0.44 | 0.62 | 0.56 |
| 2024 | 9 | +0.081 | 0.56 | 0.44 | 0.62 | 0.60 |
| 2025 | 10 | +0.006 | 0.51 | 0.52 | 0.64 | 0.55 |
| 2026 | 11 | +0.035 | 0.50 |  |  |  |

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
| LambdaRank scorer | -0.07% | -0.07% |
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

|  |  |
|---|---|
| Picks | 265,590 stock-months, models gemma, qwen |
| Agreement between the two models | 0.51 |
| What the crowd buys most | quality, 1-year momentum, profitability, last month |
| Against the crowd, IC 2016-2020 / 2021-2026 | -0.005 / -0.042 |
| Our longs / shorts, crowd percentile | 79 / 29 |

<!--/AUTO:crowd-->

**A firewall against recall.** The analyst's model was trained on text written after 2021, so its
reading of a 2021-2026 filing could be memory, not reading. Its verdicts up to November 2020 teach
a small model that sees only FinBERT's vectors and the stock's card, and that model, not the
analyst, scores every stock-month for the stock picker (amendment 12). The triage and crowd agents
already work this way, so no language model's reading of 2021-2026 reaches the book. The analyst's
own later verdicts are kept only to measure recall.

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

**The biggest winners and losers, explained.** The explainer reads each name's facts and nothing else, and says why the book held it.

<!--AUTO:explained-->

The explainer has not run on the winners and losers yet; it runs with --agents.

<!--/AUTO:explained-->

## Robustness

**Every way of choosing, walked forward.** Each year a rule sees only the months before it. Both
windows have now been seen, so new rules take their settings from published research, never from
these tables.

<!--AUTO:walk-->

|  | 2016-2020 | 2021-2022 | 2023-2026 | 2021-2026 |
|---|---|---|---|---|
| Shipped book |  | +0.99 (24) | -0.08 (44) | +0.40 (68) |
| Ship rule, walked forward | -1.23 (24, 2019-01 to 2020-12) | +1.11 (24) | -0.09 (44) | +0.43 (68) |
| Composite every year | -2.06 (24, 2019-01 to 2020-12) | +1.76 (24) | -0.11 (44) | +0.70 (68) |

IR by window, months in brackets, on the CRSP market. Picks start in 2019, the first year with two years of candidates behind it. Random picks of one candidate a year average IR -0.14; the rule beats 77% of them.

<!--/AUTO:walk-->

**A safer construction, tested once.** Five rules aimed at where losses came from: a better hedge
beta, a ±10% net band for true beta neutrality, no expensive-to-borrow shorts and smaller volatile
ones, smaller positions in thinly traded names, and momentum crash protection (Daniel and Moskowitz).
Both books pay the same costs, 2016-2026.

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

**Is it stock picking or style?** We held the book's size, value, profitability, investment and
momentum exposures near zero and judged it on all eleven years.

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

**2016-2020, a historical check.** We have seen these years too, so this is not a clean test:

<!--AUTO:clean-->

|  | 2016-2020, a historical check | 2021-2026, the record |
|---|---|---|
| Information ratio | **-1.00** | +0.40 |
| Net return | -5.7% a year | +8.5% a year |
| Realized beta, CRSP market | **-0.25** (se 0.07) | -0.09 (se 0.09) |
| Worst spread drawdown | -35% | -15% |
| Turnover, one-way monthly | 46% | 46% |
| Net by year, compounded | 2016 +0%, 2017 -2%, 2018 +13%, 2019 -7%, 2020 -29% | 2021 +10%, 2022 +28%, 2023 +10%, 2024 -10%, 2025 +1%, 2026 +10% |

<!--/AUTO:clean-->

**WRDS.** Delisted stocks leave on the decision date, takeover payouts are booked, and at most
<!--N:exhibits/wrds.json:report_dates.worst_early_share:.1%-->0.1%<!--/N--> of accounting updates came
before their report. 2021-2025 alone, the CRSP years, gives IR
<!--N:exhibits/pack.json:subperiod.crsp_era_2021_2025.information_ratio:.2f-->0.32<!--/N-->.

<!--AUTO:wrds-->

|  |  |
|---|---|
| Dated delistings and deletions applied | 8,346 securities |
| Rows already delisted at the decision, screened out | 598 |
| Held names already delisted | 0 |
| Held names taken over in their holding month | 67, 48 for cash; payouts +3.3 bp a year, closing cost 0.9 bp, already charged |
| Panel returns against CRSP, 2021-2025 | 83.9% within 1 bp, correlation 0.9995, 0.03% off by over 1% |
| Beta, S&P 500 with dividends, 2021-01 to 2025-12 | -0.02 (se 0.10) against -0.02 price-only; dividends 1.5% a year |
| Accounting updates with no new report behind them | worst signal 0.10%, rule 1%; a random month holds a release 33% of the time |
| Updates from a report dated on the decision day, held back a month | IR 0.68, net 12.3%; 1.2% of rows |
| Same code without WRDS, as a judge rebuilds it | IR 0.40, net 8.6%, beta -0.04 |
| IR on CRSP years only, 2021-2025 | 0.32 over 60 months |
| 2026, returns from Compustat | monthly spread 0.149 against 0.111-0.119; moves past ±50% 1.25% against 0.45%-0.75% |

<!--/AUTO:wrds-->

<!--AUTO:halves-->

| period | months | gross | cost | net | IR | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| **Full, 2021-2026** | 68 | 13.7% | 5.1% | 8.5% | 0.40 | [-0.37, 1.39] |
| 2021-2022 | 24 | 23.4% | 5.3% | 18.1% | 0.99 | [0.36, 2.57] |
| **2023-2026** | 44 | 8.4% | 5.1% | 3.3% | -0.08 | [-1.21, 0.78] |
| 2022-2026 | 56 | 13.3% | 5.2% | 8.1% | 0.38 | [-0.68, 1.12] |
| CRSP years, 2021-2025 | 60 | 12.8% | 5.1% | 7.6% | 0.32 | [-0.48, 1.40] |

<!--/AUTO:halves-->

<!--AUTO:factors-->

|  | loading | t |
|---|---:|---:|
| Market (CRSP) | +0.03 | +0.71 |
| Size | -0.33 | -2.43 |
| Value | +0.21 | +2.01 |
| Profitability | +0.40 | +3.41 |
| Investment | +0.05 | +0.34 |
| Momentum | -0.00 | -0.04 |
| **Alpha after all six** | **4.1%** | **+0.85** |
| Alpha after three | 4.3% | +0.94 |
| Alpha after the S&P 500 alone | 9.0% | +1.78 |

The six explain 37% of the variance, over 67 months.

<!--/AUTO:factors-->

**Style or stock selection, year by year.** At those loadings, each year's return splits into what
the six paid and what is left. Styles paid about half of 2021-22; the 2024 loss was stock-specific,
mostly squeezes on the short book, not style.

<!--AUTO:styles-->

| year | total | from the six styles | from stock selection |
|---|---:|---:|---:|
| 2021 | +10.4% | +14.9% | -4.5% |
| 2022 | +25.9% | +10.4% | +15.5% |
| 2023 | +10.0% | +0.4% | +9.6% |
| 2024 | -9.5% | +3.8% | -13.3% |
| 2025 | +1.4% | +0.1% | +1.3% |
| 2026 (7 months) | +13.0% | -1.1% | +14.1% |

Return over cash, monthly sums, at the full-period loadings on the market, size, value, profitability, investment and momentum (Ken French's factors, which end a month before our last). Stock selection is everything the six do not explain.

<!--/AUTO:styles-->

**The same loadings in each half.** Twelve months cannot pin six loadings, so the split is by
window, not by year.

<!--AUTO:factor_windows-->

| loading (t) | 2021-2022 | 2023-2026 |
|---|---:|---:|
| Market | -0.07 (-1.7) | -0.00 (-0.0) |
| Size | -0.56 (-2.3) | -0.07 (-0.5) |
| Value | +0.48 (+4.0) | -0.13 (-0.8) |
| Profitability | +0.73 (+5.4) | +0.25 (+2.1) |
| Investment | -0.28 (-1.4) | +0.21 (+0.7) |
| Momentum | +0.29 (+1.9) | -0.02 (-0.2) |
| Alpha a year | -3.3% (-1.0) | +5.9% (+0.8) |

<!--/AUTO:factor_windows-->

<!--AUTO:attribution-->

| signal | % a year of gross | t |
|---|---:|---:|
| `ope_be` | +2.2% | +0.97 |
| `ret_12_1` | +2.0% | +1.38 |
| `noa_gr1a` | +1.7% | +1.79 |
| `o_score` | +1.7% | +1.08 |
| `niq_su` | +1.2% | +1.76 |
| `eqnetis_at` | +1.1% | +0.61 |
| `be_me` | +0.6% | +1.84 |
| `chcsho_12m` | +0.6% | +0.38 |
| `at_gr1` | +0.4% | +0.30 |
| `qmj` | -0.4% | -0.18 |
| `ivol_capm_21d` | -0.9% | -0.95 |
| `gp_at` | -2.5% | -1.11 |
| explained by the twelve | +7.9% |  |
| residual | +5.8% |  |

<!--/AUTO:attribution-->

**Each signal by year**, % of NAV, before costs:

<!--AUTO:signal_years-->

| signal | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| `ope_be` | +4.5% | +8.1% | +2.3% | +2.9% | -1.3% | -3.9% |
| `ret_12_1` | +2.0% | +6.5% | -2.2% | +4.0% | +0.1% | +1.3% |
| `noa_gr1a` | +1.2% | +2.7% | +1.2% | +2.1% | +0.8% | +1.9% |
| `o_score` | +0.2% | +3.4% | +4.8% | -1.0% | +2.0% | +0.5% |
| `niq_su` | -0.1% | +3.1% | -0.1% | +2.9% | -0.9% | +1.7% |
| `eqnetis_at` | +8.6% | -3.4% | +1.0% | +1.5% | -4.6% | +3.4% |
| `be_me` | +2.2% | +0.6% | +0.2% | +0.4% | +0.2% | -0.0% |
| `chcsho_12m` | -1.8% | +3.9% | +4.7% | -6.3% | +0.3% | +2.8% |
| `at_gr1` | +1.2% | +6.2% | -3.0% | -1.5% | -0.7% | -0.1% |
| `qmj` | -2.1% | +0.2% | -5.5% | +3.8% | +0.4% | +0.9% |
| `ivol_capm_21d` | -1.4% | +1.4% | -2.1% | +1.2% | -2.2% | -1.8% |
| `gp_at` | +3.1% | -5.4% | +3.3% | -6.4% | -6.6% | -2.5% |

<!--/AUTO:signal_years-->

**The ten worst months**, traced to their source:

<!--AUTO:worst-->

| month | gross | long / short leg | worst sectors (GICS) | worst signals |
|---|---|---|---|---|
| 2021-01 | -8.5% | +4.4% / -12.9% | 45 -2.5%, 35 -2.2% | `qmj` -3.0%, `chcsho_12m` -2.7% |
| 2024-10 | -7.7% | -3.6% / -4.1% | 35 -3.8%, 45 -1.8% | `gp_at` -3.3%, `chcsho_12m` -2.5% |
| 2022-08 | -4.3% | -3.4% / -0.9% | 35 -3.0%, 20 -1.5% | `gp_at` -2.4%, `o_score` -1.4% |
| 2025-07 | -4.2% | +0.8% / -5.0% | 35 -4.6%, 10 -0.8% | `gp_at` -2.4%, `ret_12_1` -0.6% |
| 2023-12 | -3.3% | +9.6% / -12.9% | 35 -2.5%, 40 -1.1% | `gp_at` -2.1%, `ret_12_1` -1.7% |
| 2021-06 | -3.2% | +0.1% / -3.3% | 25 -1.6%, 15 -0.8% | `chcsho_12m` -1.6%, `ope_be` -1.1% |
| 2026-08 | -2.6% | +0.1% / -2.7% | 35 -2.5%, 20 -0.8% | `ope_be` -2.2%, `ret_12_1` -1.9% |
| 2023-05 | -2.4% | -1.0% / -1.4% | 25 -2.2%, 45 -0.9% | `ope_be` -2.1%, `at_gr1` -1.0% |
| 2024-07 | -2.2% | +5.2% / -7.5% | 50 -1.8%, 45 -0.4% | `gp_at` -2.2%, `o_score` -2.1% |
| 2025-02 | -1.5% | -6.4% / +5.0% | 40 -1.2%, 50 -0.5% | `gp_at` -1.5%, `eqnetis_at` -0.8% |

<!--/AUTO:worst-->

<!--AUTO:tails-->

|  |  |
|---|---:|
| 95% VaR, monthly | -4.58% |
| 95% CVaR, monthly | -6.97% |
| Skew | -0.22 |
| Excess kurtosis | +1.33 |
| Rolling 12-month windows with a negative IR | 37% of 57 |

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
| 2021 2025 crsp | CRSP, dated | 16,774 |
| 2021 2025 crsp | EDGAR, dated correction | 1 |
| 2026 public filings | 8-K on or before | 2,059 |
| 2026 public filings | EDGAR, dated name and current ticker | 57 |
| 2026 public filings | Compustat header, current | 9 |
| 2026 public filings | EDGAR, dated correction | 9 |
| 2026 public filings | unconfirmed: no public source agrees on both | 3 |

99.98% of 18,912 holding rows confirmed. Corrected from SEC's dated record: H20 AMERICA → H2O AMERICA from 2025-05-01, CONTANGO ORE INC → CONTANGO SILVER & GOLD INC from 2026-03-30.

<!--/AUTO:labels-->

## Multiple testing and limits

<!--AUTO:deflation-->

|  | Sharpe luck alone produces | deflated-Sharpe probability |
|---|---:|---:|
| **At 125 eligible attempts** | 1.10 | **0.22** |
| At 1,649, every fit we ever ran | 1.43 | 0.06 |
| Missing returns at −30%, longs / both sides |  | IR 0.39 / 0.41 |

<!--/AUTO:deflation-->

We saw 2021-2026 while designing the signals · costs are modelled · 2026 returns come from
Compustat · the S&P 500 series is price-only · point-in-time accounting is checked, not guaranteed.
