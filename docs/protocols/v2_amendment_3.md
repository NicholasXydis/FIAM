# v2, amendment 3: the final v3

Written 2026-10-15, after the 2021-2026 results of v3 (amendment 2) had been seen, and before any
run it covers. `v2.md` and amendments 1 and 2 stand. v1, v2, v2-pass and v3 stay unchanged and
reported. Every new switch is off by default, so v2 with every switch off still matches v1.

## Why
v3's 2021-2026 diagnosis (disclosed because it shaped this file): returns front-loaded (2021-2022
+33.5% and +18.1%, 2024 -3.3%, 29 months below its peak); the short leg lost money every year from
2023, as it did in 2019 (-21%) and 2020 (-26%); the hedge beta sat at the +0.02 edge of its band in
every month (mean +0.0199, v1 too) and realized beta was +0.07; the risk target held gross near
100% after 2020 (7.2% volatility), because predicted risk rose above the 2017-2020 target. Two
ideas come from Andrew's branch `feat/constructions-docs-drew`: beta first, then everything else
(his 12-month 2021 development run moved realized beta from +0.040 to 0.000), and a risk forecast
rescaled by its own recent error (his Risk/4 settings, half-life 12 months).

## Rule fixes (conventions or the brief's own rules; no test)
1. **`zerobeta`: beta held at zero.** The hedge-beta band narrows from +/-0.02 to +/-0.005, so the
   book no longer sits at the band's edge (the brief: a book that "sits at the edge of the band
   month after month" reads as directional).
2. **`target10`: 10% annual volatility, realized.** With `voltarget`, gross = 160% x (0.10 /
   sqrt(12)) / (b_t x predicted), where predicted is the risk model's monthly volatility of the
   book the rules choose at 160% (as amendment 2) and b_t corrects its bias: b_t^2 is the
   exponentially weighted mean, half-life 12 months, of (realized gross return / predicted
   volatility)^2 over the book's own past months, started from v2-pass's $10M books, decisions
   2017-01..2020-11 (frozen as `vol_bias`). Only months already ended enter b_t.
3. **Gross ceiling that holds every day.** The ceiling is min(180%, 200% / r), where r is the
   largest ratio of any day's gross to the month-start gross in v2-pass's $10M books, holding
   months 2016-01..2020-12, from daily returns (frozen as `gross_ceiling`). The brief's 200% limit
   holds "throughout"; the 2021-2025 daily gross of final v3 is reported, and 2026 months (no daily
   data) rest on the ceiling.

## Tested fixes (2016-2020 decides; each run alone on base = v3 + `zerobeta` + `target10`)
4. **`riskcap`: smaller positions in volatile stocks** (volatility scaling, a sizing the brief
   names). Each name's cap becomes 1.5% x min(1, m / s_i), at least 0.5%, where s_i is the name's
   specific volatility (`vol.forecast`) and m its month's median. Pass at $10M: the short leg's
   worst month and its total over months when the market rose more than 3% both less negative
   than base's, and IR no more than 0.10 below base's.
5. **`adaptive`: signals that are failing count half** (factor momentum: Gupta and Kelly 2019;
   Ehsani and Linnainmaa 2019). Each month each of the twelve signals' long-short return over the
   last 12 realized holding months (`book.spread`, at least 6 months, else full weight) is summed;
   a negative sum halves its weight in the composite. Pass at $10M: the longest run below a previous
   peak shorter than base's and IR above base's.

## Final v3
Final v3 = v3 (`shorts`, `size`, `voltarget`, `brake`) + `zerobeta` + `target10` + every tested fix
that passes. It replaces v3 as the book we present at the finals, with v1 (the submitted book), v2,
v2-pass and v3 as benchmarks. It runs under any finals mandate (`v2.finals`). Never chosen by
comparing 2021-2026 results.

## Reported whatever happens
- Final v3, base and each tested fix at every capital level, both windows: the `v2.md` and
  amendment 2 measures, plus the longest run below a peak, rolling 12-month returns, and the share
  of variance factors explain.
- The risk dial: final v3 at 6%, 8%, 10% and 12% targets at every capital level. 10% was fixed
  here; the others are reported, never chosen.
- On final v3's September 2026 book: the 17 crises, the named scenarios, the 2021 squeeze, the 2008
  short ban, reverse stress and liquidity (`stress.md`); AI-crowd overlap, crowding beta and the AI
  sell-off cost (`crowd.md`); the NautilusTrader whole-share replay (`nautilus.md`).
- Daily gross, volatility, VaR and drawdown for 2021-2025; deflated Sharpe at both trial counts,
  every run here a trial; v1, v2, v2-pass and v3 beside it.
