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

## Amendments

Each change is dated, made before the test it touches ran, and kept here rather than edited in.

1. **2026-09-30, before any Phase 2 code ran.** IBKR's US stock commission page lists three
   regulatory fees charged on top of the fixed commission. The FINRA Trading Activity Fee takes its
   highest rate in 2021-2026, the rule the SEC fee already follows: $0.000195 a share sold, at most
   $9.79 a trade, in force since January 2026 (the $0.000166 above was the 2024-2025 rate). The FINRA
   Consolidated Audit Trail fee, $0.000003 a share on every buy and sale, is added; it was missing.
   Together they move costs by well under 0.01% a year.

2. **2026-09-30, after Phase 2 and before any Phase 3 code ran.** Phase 2 showed market impact is
   now the largest cost (2.2% a year of 5.1%). Construction v2 adds liquidity-scaled caps: each
   name's cap, long or short, is 1.5% × the lesser of 1 and m ÷ kᵢ, where kᵢ = `rvol_21d` ÷
   √`dolvol_126d` is its impact per dollar under the Phase 2 square-root law and m is that month's
   median k. No position then carries more expected impact per dollar than the median name. A short
   takes the smaller of this cap and its volatility cap. The pass rules are unchanged. Nothing about
   which names or signals lost money in Phase 2 enters any rule.

3. **2026-09-30, before any Phase 4 code ran.** Every 8-K opens with a cover page of about 1,250
   characters (registrant, address, file numbers, checkboxes), about half of FinBERT's 512 tokens.
   FinBERT and every agent read each filing from its first "Item N.NN" heading instead, or from the
   start when it has none (12% of filings). The embedding is the mean of FinBERT's last layer over
   the filing's tokens, a detail the plan left open. Tickers are masked as whole words of two or
   more letters, so a one-letter ticker cannot erase ordinary words. The masked excerpt, 3,000
   characters from that heading, becomes a layer of the data bundle, built once from the
   organizer's file.

4. **2026-09-30, a new test, before its code ran: the factor-neutral book.** The book's six-factor
   alpha is 7% a year with t = 1.56; its good and bad years follow the value factor (HML -31% in
   2020, +32% in 2022). The brief calls neutralizing size, value and momentum an optional
   refinement. On top of the current construction (v2 was rejected), the book's exposure to five
   Fama-French characteristics is held within ±0.02, the limit its volatility complex already has:
   size `market_equity`, value `be_me`, profitability `ope_be`, investment `at_gr1`, momentum
   `ret_12_1`, each ranked within its month as the composite ranks. It ships only if all four hold
   on 2016-01 to 2026-08, with the Phase 2 costs on both books: IR higher than the current book's;
   monthly beta closer to zero; worst drawdown shallower; 100-500 names, gross at most 200% and net
   within ±50% every month, and no day above 200% gross in 2021-2025, the record's daily data.
   Judged on all eleven years, not the window that flatters us. It counts as one more attempt.
5. **2026-09-30, before the analyst agent ran.** Qwen3.8-27B takes about 5-10 seconds a call, so
   20,000 calls would take 30-55 hours. The analyst reads at most 5,000 stock-months, drawn from the
   same eligible set with the same seed. The reason is compute time; no result has been seen.
6. **2026-09-30, before the analyst agent ran.** So every agent can run in one unattended night on
   the Windows GPU, the analyst chooses stock-months by the filings' own item codes rather than by
   the triage model, which needs FinBERT vectors built on another machine. A filing is material if
   it carries item 1.01, 1.02, 2.01, 2.02, 2.05, 2.06, 4.01, 4.02 or 5.02, the events the brief
   singles out; routine items 7.01, 8.01 and 9.01 alone do not count. Everything else in
   amendment 5 stands. The reason is scheduling; no result has been seen.
7. **2026-09-30, before the scorer ran with any Phase 4 input.** The factor-neutral test showed the
   book's return is style. So the scorer becomes a stock picker: it learns next month's return less
   its sector's mean and its exposure to beta and the five characteristics of amendment 4, each
   month by least squares, instead of beta alone. Everything else about it is unchanged, and it
   still reaches the book only through the candidate grid and the ship rule.
8. **2026-09-30, before the trader or the live book ran.** The trader's constant-rate yardstick is
   named for what it is: Gârleanu and Pedersen's (2013) optimal policy trades a constant fraction of
   the way to its aim each month; ours takes that fraction from 25%, 50%, 75% or 100% on earlier
   years only. Separately, each month from October 2026 the book for the coming month is built from
   the latest data and committed before that month begins, then scored once its returns are known.
   Until the organizer's panel updates, it is built from August 2026 characteristics.
9. **2026-09-30.** The live book of amendment 8 is dropped: the submission is due before October's
   returns exist, so it could not be scored in time. The rest of amendment 8 stands.
10. **2026-09-30, before the stock picker ran with any Phase 4 input.** Its forecasts churn the book
    (80-100% a month), which trading costs punish. Its scores now enter the book as an average of
    each stock's current and past scores, weighted with a three-month half-life, past months only:
    Gârleanu and Pedersen (2013) show a trader facing costs should aim at an average of current and
    expected future targets. A stock with no score this month gets none. The grid and the ship rule
    are unchanged.
11. **2026-09-30, before the ship rule ran again.** The hedge follows neutrality, which the brief
    checks first. Each year, once the ship rule has chosen a book, it takes that book's twin with
    the other hedge (the 60-month beta or the teacher's learned beta) if the twin's monthly beta
    over the same two prior years was closer to zero. Disclosed: we had already seen that the
    learned hedge kept 2021-2026 beta closer to zero.
12. **2026-09-30, before the stock picker ran with the analyst's verdicts.** Two look-ahead guards
    from our own audit. (a) The analyst's model was trained on text written after 2021, so its
    verdicts on 2021-2026 filings could be recall rather than reading. No language-model output
    from the evaluation years now reaches the book. A small model learns the analyst's verdicts
    dated up to November 2020, before the first decision of the evaluation, from what the analyst
    read: the FinBERT vectors of that month's material filings (FinBERT's training text predates
    2020) and the stock's card percentiles. It then scores every stock-month with a material
    filing, as the triage and crowd agents already work. The analyst's own 2021-2026 verdicts are
    kept for one exhibit: their correlation with next month's return beside the small model's on
    the same stock-months, a direct measure of recall. Verdicts before 2021 may themselves recall
    later events; the small model sees no names, so it can carry general patterns of text, not
    what happened to a company. (b) The earnings-surprise teacher's label is known up to five
    months after its decision. A training label first known on or after the test year's first
    day is dropped, as the brief requires for labels realized in the test period. Nothing else
    changes, and neither change's effect has been seen.
