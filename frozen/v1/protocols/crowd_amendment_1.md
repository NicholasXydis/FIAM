# AI Crowd Lab, amendment 1: what the crowds' saved answers can still tell us

Written 2026-10-14, after the crowds ran and before any of these measures was computed. `crowd.md`
stands. Every measure here reads saved answers only, is exploratory (19 months), has no pass or
fail, and never enters v1 or v2.

## Measures
1. **Copycat test.** For the copycat agents given v1's own strategy text: the share of their buys
   that v1 held long that month, and of their shorts that v1 held short, each divided by the base
   rate on the same cards (the share of card stocks v1 held on that side). The same ratios for the
   agents given the other two texts are the control. Intervals: bootstrap over months (10,000
   draws, seed 42). Also the mean monthly Spearman correlation of each group's net vote (buy minus
   short share) with v1's signal on the stocks shown.
2. **Copycat capacity tax.** If AI copycat money of $1B, $10B or $50B followed the v1-text copycats'
   consensus (net votes scaled to that gross), square-root impact on each name (the coefficient,
   volatility and volume of `costs.py`) moves the price against v1 wherever v1 trades the same way.
   Reported: the extra cost to v1 in basis points a month at $10M and $1B.
3. **What the crowd buys.** The crowd model's coefficients on the 147 characteristic ranks: the ten
   largest each way, named; and the mean monthly correlation of the crowd score with v1's signal.
4. **Herding and fear.** LSV herding per month for each crowd against the VIX at the decision month
   end; Spearman correlation over the 19 months. The April 2025 tariff shock (decisions 2025-03-31
   and 2025-04-30) is marked, not selected.
5. **Herding by recipe.** LSV and effective voters for the copycats given each of the three texts.
6. **Crowd picks before costs.** Gross and net information ratios of the crowd-alone books from
   `crowd.md` item 5, already run.
7. **Network.** Pairwise correlation of the 30 retail agents' pick indicators on shared stocks,
   grouped by average-linkage clustering into as many groups as the effective number of voters
   (rounded); reported as a picture with each group's persona and information-set mix.
8. **Animated replay.** A film of the crowds made only from saved answers and these results.

## Research desk additions (same rules as `honesty.md`)
- **September book explained:** Qwen explains the ten largest positions of the September v1 book
  from the stocks' own characteristics; every number must pass the verifier, or that name is
  dropped and counted.
- **Finals drill:** rules text -> rules reader -> mandate check -> v1's method and v2 under it,
  timed end to end. A human still approves the mandate before any real use.
