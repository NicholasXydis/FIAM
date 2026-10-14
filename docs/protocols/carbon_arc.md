# Carbon Arc spending data

## Question
If the finals provide Carbon Arc consumer-spending data, does it tell us something the market has
not priced: does recent spending growth predict the next sales surprise?

## Before the data arrives (fixed now)
- Layer template `fiam/layers/carbon_arc.py`: keys (company name or ticker, period), columns,
  `known_at` = the date the data would have been available (the period end plus Carbon Arc's stated
  publication lag; if none is stated, 30 days), role feature, licence noted.
- Name matcher: normalise names (case, punctuation, legal suffixes), block by country, top 3
  candidates by `difflib` similarity, an LLM yes/no only for scores between 0.80 and 0.95; matches
  below 0.80 are dropped. A human checks 50 random matches; precision is reported.
- Dry run on a fake file shaped like typical spend data (company, month, spend) to time the path.

## Test
- Signal: spending growth over the latest 3 months vs a year before, minus the company's last
  reported year-over-year sales growth (Compustat), known by the decision month end.
- Target: the next quarterly sales surprise after the decision (`saleq_su` at the next report).
- Measure: monthly cross-sectional Spearman IC over every month available, Newey-West t (lag 3).
- Pass: mean IC > 0 with t > 2. If it passes, a "carbon" switch adds it to v2 as one extra signal at
  one-thirteenth weight, reported beside v2; if it fails, it is reported and not used.
- Also: the crowd test in `crowd.md` item 9 (does spending data change how AI investors herd?).
