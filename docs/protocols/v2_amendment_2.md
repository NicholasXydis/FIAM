# v2, amendment 2: v3, the final book, built from v2-pass for every fund size

Written 2026-10-15, after the 2016-2026 results of v1, v2, v2a and v2-pass had been seen, and
before any run it covers. `v2.md` and amendment 1 stand; v1, v2 and v2-pass stay unchanged as
benchmarks. Every new switch is off by default, so v2 with every switch off still matches v1.

## Why
v2-pass (v1 plus the short rule) is our best book at $10M, but its trading cost grows with fund
size until it loses money above about $700M. v2 trades cheaply at any size but earns less. v3 keeps
v2-pass's signals and solve and adds four parts, each a standard risk rule published before 2021,
each judged alone on 2016-2020 by the mechanism it targets, never by information ratio (IR) alone.
Numbers below are fitted on holding months before 2021 and frozen in `frozen/v2_params.json`.

## What shaped the choice (2016-2020 only, disclosed)
Overlays on the saved 2016-2020 books of v1 and v2-pass at $10M, approximations only:
- Correcting the hedge with the book's trailing 126-day daily (Dimson) beta moved the monthly beta
  further from zero (v1 -0.25 to -0.28; v2-pass -0.21 to -0.22). Daily and monthly betas disagree
  (v1 in 2017: daily -0.15, monthly +0.56). Dropped from the plan.
- The book's exposure to the risk model's low-volatility style (month rank of `ivol_capm_252d`;
  -0.25 per unit of gross for v2-pass) carried most of its monthly beta: removing that style's
  return moved v2-pass's beta from -0.21 to -0.08 and its volatility from 8.2% to 6.8% a year. The
  size style did not (beta -0.20, volatility up), so it is not capped.
- Scaling exposure by the risk model's predicted volatility steadied yearly volatility and cut
  v2-pass's 2016-2020 maximum drawdown from -31.7% to -25.3%.

## The four parts
1. **`size`: trading speed set by fund size** (Garleanu and Pedersen 2013; Grinold and Kahn 1999
   on transaction-cost budgets).
   - Cost budget: each month's cost of trading from the drifted book, in `convex_cost`'s terms
     without borrow (half spread and commission on each trade, sale fees on sells, square-root
     impact at the run's capital), is at most the mean monthly trading cost (commission + spread +
     impact) v2-pass paid at $10M over holding months 2016-02..2020-12, the first build excluded:
     0.165% of NAV (`cost_budget`). The first month's build is exempt. The same budget buys fewer
     trades at a bigger size, so a big fund trades slowly and keeps the trades with the most score
     per dollar of cost.
   - Liquidity cap: no position above 0.4 x `dolvol_126d` / NAV (two days at 20% of average daily
     dollar volume), as `liquidity` in `v2.md`, clipped after the solve. `liquidity` failed only
     its 2.0-day tolerance after whole shares (2.1 days at $1B); here days to liquidate are
     reported, not judged.
   - A held name may stay or shrink when its score changes sign; it never grows against it.
   - A month no book can fit is solved again at twice the budget, then without it; such months are
     counted and reported.
   - Test: at $500M, $1B and $5B, annual cost below v2-pass's and annual net return above it; at
     $10M, IR no more than 0.10 below v2-pass's.
2. **`lowvol`: no unintended low-volatility bet** (Grinold and Kahn 1999 on unintended factor
   bets; Ang, Hodrick, Xing and Zhang 2006; Frazzini and Pedersen 2014 on low-risk stocks' betas).
   v1 holds its 21-day volatility complex (`risk_rank`) within +/-0.02; this adds the month's rank z
   of `ivol_capm_252d` within the same +/-0.02. Test at $10M: realized monthly beta closer to zero
   than v2-pass's, and annual volatility of monthly net return lower.
3. **`voltarget`: steady risk** (Moreira and Muir 2017; Barroso and Santa-Clara 2015). Each month
   the risk model (`risk.py`, from 2017-01) predicts the volatility of the book the rules choose at
   160% gross (the same solve without `size` and `brake`). Gross is set to 160% x target /
   predicted, kept within 100% and 180% (180% leaves room for drift under the 200% limit, as v1's
   160% did). Target = the median predicted monthly volatility of v2-pass's $10M books, decisions
   2017-01..2020-11 (`vol_target`). 2016 decisions keep 160%. Under `size`, a gross the budget
   cannot reach falls back to halfway, then to last month's gross. Test at $10M, holding months
   2017-02..2020-12: the standard deviation of the four yearly realized volatilities below
   v2-pass's; maximum drawdown smaller; Sharpe no more than 0.10 lower.
4. **`brake`: drawdown control** (Grossman and Zhou 1993; Kaminski and Lo 2014: stop-loss rules
   add value when returns are serially correlated; v2-pass's 2016-2020 lag-1 autocorrelation is
   +0.15). The book's cumulative net return is tracked as each month is earned. At 5% or more
   below its peak, gross is cut to 100% until half the fall from the peak to the lowest point since
   is recovered; a new low within the same fall engages it again; a new peak resets it. Test at
   $10M: maximum drawdown smaller than v2-pass's and Sharpe not lower.

## v3
v3 = `shorts` + every part that passes. Each part is also run alone on v2-pass. Every run covers
all six capital levels and both windows: 2016-2020 decides, 2021-01..2026-08 is shown once.
The risk model uses monthly data only, so `voltarget` runs to the last decision; for 2026
decisions specific risk uses `rvol_21d` x sqrt(21) (`risk.md`'s fallback), as daily data ends
2025-12.

## The book we present at the finals
If `size` passes, v3 is our final book at every fund size, with v1 (the submitted book) and v2 as
benchmarks and v2-pass beside them. If `size` fails, `finals.md`'s rule stands. Never chosen by
comparing 2021-2026 results.

## Reported whatever happens
For v3, each part alone, v2-pass, v2 and v1, at every capital level and both windows: IR, Sharpe,
net return, cost, turnover, realized monthly beta with its standard error, volatility, maximum
drawdown, gross range, positions, days to liquidate, months over budget. Also: v3 minus v1 and v3
minus v2-pass (stationary bootstrap, 2021-2026, every capital level); the deflated Sharpe at the
full and effective trial counts, every run here a trial; capacity (`capacity.md`) with v3 added;
the `stress.md` crises on v3's September 2026 book. Failures are reported next to passes.
