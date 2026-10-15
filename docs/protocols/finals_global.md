# Finals: the `global` switch and the day-of options

Written 2026-10-15, before any run it covers. `finals.md` and every v2 amendment stand. Every option
here is off by default: with all of them off, v1, v2, v2-pass, v3 and final v3 are unchanged weight
for weight, and a test proves it.

## Why
Last year's finals asked for a global book (at least two countries, at most 75% of the book in one,
150/50, 100 to 300 names) on data handed out that day, run on Lightning AI (Linux). Our code reads
one US panel. This adds what a global book needs without changing how any book is built.

## 1. A global data bundle (`fiam/world.py`)
- Input: the finals panel as the organizer gives it (CSV or parquet, one row per stock-month) and a
  column map (`data/world/columns.json`) naming its id, month, country, next month's excess return,
  and any column whose name differs from ours. Written by hand on the day, never fitted.
- Output: a bundle in our layout (`features_monthly`, `labels_monthly`, an empty `filings`,
  `manifest`) under `data/world/`, read through `FIAM_DATA_DIR` as every step already reads data.
- Ids: a US stock keeps its PERMNO when the panel gives one. Every other stock gets 100,000,000 plus
  its position in the sorted list of the panel's own ids, so no id meets a PERMNO.
- Returns: USD as given. If the panel says a return is in another currency, it is converted with
  the Federal Reserve rates (`layers/market/fx_daily`) at each month end; a currency with no rate
  stops the build with its name. Nothing is guessed.
- Missing columns are left missing: no ticker or name, sector "XX" without GICS, and a stock needs
  9 of the 12 signals, as in v1.

## 2. The `global` switch
- Countries: only the mandate's countries enter. Each country's gross exposure is at most
  `country_cap` times the book's gross, inside the optimizer beside the sector rule.
- Hedge beta: the learned beta where it exists, else the stock's 60-month beta, as v1 already does.
- Costs: v1's formulas on the panel's own columns (spread, dollar volume, volatility); borrow at the
  general rate where there is no short interest.
- Beta is reported against the S&P 500, as now, and against the panel's own value-weighted market.

## 3. Day-of options
- `--window FIRST LAST`: the decision months of a finals run when the data covers other dates.
- `hurdle` in a mandate: the yearly spread over the T-bill (default 4%, the brief's).
- Rules handed out as a PDF: its text goes to the rules reader exactly as `finals.md` sets out.

## 4. Which book
Final v3 (`v2_amendment_3.md`) under the approved mandate; a mandate whose net is not zero drops the
risk target and brake, as `v2.finals` already does. v1's method and v2 run beside it. Never chosen by
comparing results under the new rules or data.

## 5. Rehearsal (mechanics only, never evidence)
A fake two-country bundle from our US panel: a stock is "CAN" when the last digit of its PERMNO is
0, 1 or 2, else "USA". Under a 150/50 mandate with both countries, a 75% cap and 100 to 300 names,
over 2021-01..2026-08 at $10M. Passes when no month breaches a rule or is empty and both countries
hold weight every month. Timed from the raw file to the committee pack, on Windows and on Linux.
Its returns are labelled "fake countries" and never reported as performance.

## Reported whatever happens
Each month's weight by country, names, gross, net, both betas and breaches; the information ratio
against the hurdle; anything that could not be computed and why. Every run on finals data is a
trial in the ledger under this protocol.
