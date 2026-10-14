# Finals: rules we may be handed, the pack for any book, and which book we present

Written 2026-10-14, before the finals and before any run it covers. Nothing here changes v1: every
new rule is off by default, and v2 with every switch off still matches v1 weight for weight.

## Rules the mandate can now hold
- `net_band`: the widest net exposure the rules allow either way (this year's brief: -50% to
  +50%). The book still targets its own net (0 for v1); the band is checked before any run.
- `turnover`: the most one-way turnover a month, as a share of NAV, measured as v1 measures it
  (half the summed weight changes against last month's drifted book). The first month's build is
  exempt. Under a budget a held name may stay where it is rather than force a trade, and a month
  no solver can fit keeps last month's book. A month above the cap after whole shares is a breach
  and is reported.
- The rules reader looks for both, quoted word for word like every other limit.

## Rehearsals (each against a hand-made reference, reported whatever it finds)
- Last year's finals text (`case_2025.txt` vs `mandates/case_2025.json`) and this year's rules
  (`rules_2026.txt`, excerpts of the 2026 brief, vs `mandates/rules_2026.json`): every limit the
  reference sets found and equal, the minutes from text to both books, and breaches.

## The committee pack for any book
`fiam/exhibits/finals_book.py` writes a run's holdings (ticker and company name, from the panel
as of each decision month), monthly returns and statistics in the submission's shape, then runs
the same pack and charts as the v1 book. No new statistic is defined here.

## Which book we present at the finals
- With no new rules and no stated fund size: v1, the book we submitted.
- With a stated fund size: v1's method below the capacity crossover in `capacity.json` (the
  smallest grid size where v2's information ratio is above v1's, interpolated in log capital), v2
  at or above it.
- With new rules: the same choice, both run under the approved mandate. Never chosen by comparing
  the two books' results under the new rules.
