# v4 protocol

Every rule here is fixed before the check or run it governs. A change after a check is an amendment that shows both results (PLAN §13.4). This file is hashed at the freeze. The data section is written in step 3; the signals, models, construction and AI sections are written in step 4, before any run that reads returns.

## Data section (step 3, written 2026-10-23, before its checks ran)

### The calendar
- One calendar: CRSP's sessions 2000-2013 and the organisers' dsf sessions 2014 to 2026-09-28, each closing at 16:00 Eastern, or 13:00 on XNYS early-close days (`exchange-calendars` 4.13.2).
- Cross-check (2026-10-23): 6,724 days, none extra and none missing against XNYS, 58 early closes all present.

### Volume spike flag (PLAN §6.5, B24, B30)
- A stock-day is flagged when its volume exceeds 5 times the mean of the same stock's volume over the 126 sessions before it (that day excluded), with at least 63 such sessions; otherwise no flag.
- Split-safe volume:
  - CRSP (through 2025) and CA0065S: dollar volume, price times shares traded.
  - FINRA, which gives shares only: the mean uses only window days after the stock's most recent split before that day, again at least 63 of them. Split dates are CRSP distributions with a share factor (`disfacshr` > 0) through 2025. In 2026 they are the ends of FINRA short-interest periods whose `stockSplitFlag` is set; the split day inside such a period is unknown, so the whole period counts as before it.
- Test stock-days: 2015-01..2020-12, stocks whose panel `me` was at least $600m at the last `eom` before that day (lever A3).
- Pass: precision, the share of a source's flags that CRSP also flags, at least 0.8; recall, the share of CRSP's flags the source also flags, at least 0.8; and at least 95% of universe names covered on every 2026 trading day (counts only, §1.3).
- Order, never chosen by returns: CA0065S if bought and it passes, else FINRA if it passes, else the 2026 volume screens are off.

### FINRA short interest (PLAN §6.5)
- Symbols map to PERMNO by the CRSP ticker valid on the settlement date (`data/v4/links.parquet`). A class symbol ("BRK.B") maps by ticker plus CRSP share class; unmatched symbols are counted.
- 2026 coverage: the share of universe names with a FINRA short position on each 2026 settlement date. At least 95% on every date, else the stated fallback.
- WRDS agreement on 2021-06..2025-12 (counts only, §1.3): the share of matched (PERMNO, settlement) pairs whose FINRA short position equals WRDS `shortint` within 1% or 100 shares. Reported, not a gate.

### Cross-source agreement (PLAN §6.7; an exhibit)
| Pair | Measure | Pass |
|---|---|---|
| Panel `ret` vs CRSP `MthRet` | absolute difference | at most 1e-6 on at least 99% of matched stock-months, 2015-2020 |
| dsf compounded vs CRSP `MthRetx` | absolute difference | at most 1e-4 on at least 99%, 2015-2020 |
| Panel `me` vs CRSP cap | ratio | within 0.5% on at least 99%, 2015-2020 |
| Panel exits vs CRSP delistings | a panel stock that leaves in 2015-2020 has a CRSP delisting or later CRSP rows | at least 99% |
| Compustat `cik` vs EDGAR filer | same filer | reported |
| I/B/E/S, OptionMetrics, TAQ links | share of panel stock-months at each score | reported |
| CA0065S closes vs CRSP prices (if bought) | absolute relative difference | at most 0.5% on at least 99% of 2015-2020 sample days |
| 13F CUSIP to PERMNO | share of 13F value matched | reported |
| SEC insider issuer CIK to PERMNO | share of Forms 4 matched | reported |

"Reported" rows have no bar; they are shown as measured.

### French factor vintage (B23)
- Archive: the Internet Archive's newest copy, dated before 2021-01-01, of French's daily five-factor and momentum zips, fetched with a receipt by `tools/data/french.py archive`.
- Bar: on the overlap up to the archive's last day, at least 99% of daily values of UMD, and of each of the five factors, equal to today's copy or one rounding step apart, compared on the files' own two-decimal percent values (so float error cannot fail a match), measured by age. L is the shortest age after which the bar holds.
- Use: if L is 21 sessions or less, the crash control reads UMD only up to L sessions before each date. If L is longer, any factor fails, or no archived copy exists, the crash control stays off.

### CA0065S, if it becomes orderable (approved 2026-10-23, PLAN §6.5)
Not orderable on 2026-10-23. Should it become orderable before the freeze, these rules apply as approved:

- CA0065S (Fiscal AI daily open, close and volume; "CBOE-listed only", 1,500-2,000 firms; lag T+1; added to Carbon Arc 2026-04-23, so its whole history is today's copy). Pull: universe tickers 2025-07..2026-09 (one source for the 6-month window), a fixed-seed sample of 300 universe names 2015-2020 and the six named failures (§6.8); priced free first, bought only by the leader (§12.2). Rules, fixed before the check:
  - dollar volume (close x volume) and ratios inside the window only, never price or share levels; split days checked against CRSP; the $5 floor stays on the panel's traded price
  - tickers to PERMNO by dated ticker (§6.7), share classes normalised (BRK.B vs BRK-B), match rate counted
  - (ticker, date) deduped; non-XNYS days dropped; zero or negative values flagged; no gap filling; unit jumps checked against CRSP
  - whether volume is consolidated or CBOE-only is measured; the ratio flag works either way if the share is steady
  - a name missing in 2026 gets the price and short-interest screens only, never a "missing" flag (merge rule 4)
  - 2021+ rows stored sealed: counts, coverage and the 2025-07..12 flag agreement with CRSP as counts only (§1.3); the 2026 returns vs dsf only after the unseal
  - never in a forecast, gate or desk card; rows in the leakage register, the passport and the 2026 sub-period (§13.5, §13.6)
