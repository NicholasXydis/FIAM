# Pre-registration: Phases 2-4

Written and committed before any of these tests ran. Every setting comes from a published source or
from data before 2021, never from the results. We have already seen both 2016-2020 and 2021-2026, so
no window is clean; that is why the settings are fixed here. Each test adds its rows to
`fiam/exhibits/config_log.py`, and the deflated Sharpe keeps counting every attempt.

## Phase 2: measurement (adopted for every book, not chosen by results)

**Costs, IBKR-style, on the book's whole shares at $10M NAV.**

| line | rule | source |
|---|---|---|
| Commission | $0.005 a share, at least $1.00 and at most 1% of the trade | IBKR Pro fixed US stock rate, saved with its date |
| Fees on sales | SEC Section 31 fee at the highest rate in force during 2021-2026, plus FINRA TAF at $0.000166 a share, at most $8.30 a trade | SEC and FINRA notices, saved with their dates |
| Spread | half the closing quoted spread, predicted from `bidaskhl_21d` by the median ratio within each `size_grp`, fitted on 2015-2020 CRSP closing bid and ask only | CRSP daily quotes |
| Impact | Y × daily volatility × √(trade ÷ average daily dollar volume), Y = 1, from `rvol_21d` and `dolvol_126d` | square-root law (Tóth et al. 2011; Almgren et al. 2005); Y = 0.5 as a sensitivity |
| Borrow | a year, by short interest ÷ shares outstanding: under 5% 0.30%; 5-10% 1.00%; 10-20% 3.00%; 20% or more 8.00%; micro-caps at least 1.00% | D'Avolio (2002); Drechsler & Drechsler (2016) |
| Financing | cash and short proceeds earn TB3MS less 0.50% | IBKR's published credit-interest spread, saved with its date |

Short interest is used one month late, as it is published after the month ends. For 2026, when the
data stop, a name takes the ratio found at its crowding-teacher percentile in the last month with data.

**Reported, never chosen on:** each cost line; IR with every cost doubled and with Y = 0.5; IR at $10M,
$100M, $500M and $1B; days to exit the book at 20% of daily volume; the daily path through March 2020,
2022, January-July 2023 and October 2024; a one-day execution delay; factor loadings by year; each
signal's return by year; the ten worst months by leg, sector and signal.

## Phase 3: construction v2 (one bundle, one test)

1. **Hedge beta:** 0.67 × the mean of `beta_60m` and `beta_dimson_21d`, plus 0.33, so stale small-cap
   prices stop understating beta (Dimson 1979; Blume 1971 adjustment). Either input alone if one is
   missing.
2. **Beta neutrality:** net exposure may move within ±10% (the rules allow ±50%); the beta limit stays
   ±0.02 on the new hedge beta.
3. **Short book:** no short where short interest is 20% of shares or more; each short's cap is 1.5%
   × the lesser of 1 and the month's median `rvol_21d` over its own. Longs are unchanged.
4. **Crash protection:** when the market's return over the past 24 months is negative at the
   decision, `ret_12_1` leaves the composite until it turns positive (Daniel & Moskowitz 2016, their
   24-month bear-market indicator). The rule was prompted by the 2020 rebound loss; its setting is
   the paper's, not ours.

Everything else is as shipped: 160% gross, 100-500 names, sector ±1%, name cap 1.5%, ridge 30.

**It ships only if all four hold** on 2016-01 to 2026-08, with the Phase 2 costs on both books:
IR at least the current book's; absolute monthly beta and absolute daily beta (2016-2025) both
smaller; worst drawdown no deeper; every rule holds every month. Otherwise the current construction
stays and the result is reported. Each part's separate effect is reported, never used to choose.

**Considered and dropped:** a net-of-cost optimizer (turnover penalties of 0.25-2.0 already cut IR
to about 0.5 in the ledger); gross set from expected drift (worth about +0.03 IR, with a real chance
of a day above 200%).

## Phase 4: new sources of return

**Timing:** filings dated on or before a month's last day feed that month's decision (the brief's
monthly convention).

**Masking:** company names, tickers, CIKs and every date or year are replaced with placeholders
before any model reads a filing.

1. **Embeddings.** FinBERT (Araci 2019, trained on text before 2020, so it cannot know 2021-2026) is
   the primary encoder, on the first 512 tokens. Qwen3-Embedding is reported beside it. Each
   stock-month takes the mean embedding of its filings; 32 principal components are fitted on each
   fold's training years only.
2. **Event triage.** Gemma 4 26B-A4B labels 6,000 masked filings from 2015-2018, sampled at random
   with a fixed seed, as routine, material good news, material bad news or distress. A LightGBM
   classifier on the FinBERT embeddings learns those labels and scores every filing; each
   stock-month counts filings per label.
3. **Analyst agent.** Qwen3.8-27B reads the masked filings and 12 months of characteristic
   percentiles for stock-months with a material or distress filing, among the 400 best and 400 worst
   composite scores, at most 20,000 calls. It answers what happened, whether it was expected, and a
   conviction from -2 to +2. Look-ahead probe: 500 masked filings, asked for the company and year;
   the hit rate is reported.
4. **Earnings surprise.** The target is `niq_su` at the first month-end at least one month after the
   next report date (`rdq` in Compustat quarterly), if that report falls within four months;
   otherwise missing. Ranked within month and learned year by year like the teachers, from the
   characteristics, the 8-K counts and the text components.

**How they enter the book:** the text components, the triage counts, the analyst conviction and
the earnings-surprise forecast become scorer inputs. The candidate grid and the ship rule are
unchanged: they reach the book only if a scorer book beats the composite by 0.25 IR over the two
years before, with beta inside ±0.15. The folds are the rules': expanding training, two years of
validation, annual refit. OOS R² is reported for every new model.
