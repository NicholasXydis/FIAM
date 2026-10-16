# Finals global, amendment 1: who may enter, and today's slide

Written 2026-10-15, before any run it covers. `finals_global.md` stands. Both rules are off unless a
mandate sets them, so every book so far is unchanged.

## Two rules a finals mandate may set
- `min_market_cap`: the smallest market value a stock may have to enter, in $ millions as the panel
  gives it (`me`), checked each month before any signal is built.
- `exclude_sectors`: GICS sectors left out, by two-digit code or name (10 or "Energy"). An unknown
  sector stops the run with its name.
- Neither is ever chosen by results: they are written into the mandate from the day's rules, quoted,
  and approved by a person, as `finals.md` sets out.

## Exchange rates to date
The same Federal Reserve H.10 daily rates, pinned from FRED from 2014 to the day they were fetched
in `data/benchmarks/fx_daily_*.csv` (source and hash in `sources.json`), are used before the
WRDS copy, which stops in February 2025. A currency or month with no rate still stops the build.

## Today's slide
The finals deck adds one slide for the latest finals run on real data: final v3's information ratio,
beta, names and months breaching a rule, and the same for v1's method and v2, with the largest
country when the data has countries. Each run records its data folder, window and mandate; a run on
the fake two-country rehearsal is never shown.
