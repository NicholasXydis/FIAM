# Capacity: how much money each book can run

Written 2026-10-14, before any run it covers. Exhibits only; nothing here changes a position.

## Question
At what fund size does each book stop paying, where does it earn the most dollars, and do the
answers survive different trading-cost assumptions? (Berk and Green 2004; Pastor, Stambaugh and
Taylor 2015: skill meets decreasing returns to scale.)

## Measures (v1, v2, v2a, v2-pass; capital grid $1M, $10M, $100M, $500M, $1B, $5B)
1. Dollar profit a year = mean monthly net return over the T-bill x 12 x capital, per window.
   Reported: the curve and the grid point where it peaks (no extrapolation off the grid).
2. Break-even size = where the information ratio against T-bill + 4% crosses zero, interpolated
   linearly in log capital between the two grid points around the crossing; "above $5B" or "below
   $1M" when it does not cross on the grid.
3. Each book minus v1 at $1B and $5B: stationary bootstrap of the monthly net difference, as in
   `evidence.md` item 2 (10,000 draws, seed 42, Politis-White block length).

## Cost stress (v1 and v2, every capital level, holding months 2021-01..2026-08)
- Half impact: the square-root impact coefficient at 0.5 instead of 1.0 (the sensitivity
  `costs.py` names).
- TAQ spreads: each stock's modelled half spread scaled by its size group's median ratio of half the
  TAQ effective spread to our modelled half spread, ratios measured on holding months
  2016-01..2020-12 only.
- Both set at run time in a separate process; `costs.py` is never edited. Each run is a trial.
- Reported: break-even size and annual cost at $1B under each assumption. No pass or fail.
