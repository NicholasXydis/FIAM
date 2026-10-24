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
- Amendment (approved by the leader 2026-10-23, after the agreement count above and before any short interest result was computed; no 2021+ returns seen):
  - The WRDS `short_interest` file is "Securities Finance short-interest / total-demand quantity" (stock lending; Stock Data README). FINRA agreed with it on 1.13% of 426,799 pairs, and with `short_interest_legacy`, the exchange series, on 99.96% of 338,475 pairs (2021-06..2024-12).
  - v4 uses exchange short interest only: the legacy file's `shortint` (never `shortintadj`) for settlements before 2021-06-01, FINRA's files from 2021-06-15, both public 8 sessions after settlement. The lending file is never read (registry `NEVER`).
  - FINRA rows with the revision flag are left out, as their first value is not in today's files (0.66% of rows). Two FINRA symbols on one PERMNO and date are both left out.
  - The mapping as built: the CRSP trading symbol, then the ticker, valid on the settlement date, letters and digits only (BRK.B = BRKB); a symbol two stocks share on a date stays unmapped and is counted.
  - The 95% coverage bar applies to every FINRA date from 2021-06 (98.06% minimum over 128 dates, counts only).

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
- Operational reading, written 2026-10-23 before the check ran: a value's age is the number of sessions from its date to the archive capture; for each age a, the bar is checked on all overlap values at least a sessions old; L is the smallest a at which it holds for all six series. Older pre-2021 captures are fetched too and reported beside, never deciding.
- Use: if L is 21 sessions or less, the crash control reads UMD only up to L sessions before each date. If L is longer, any factor fails, or no archived copy exists, the crash control stays off.

### NOAA vintage (B23; written 2026-10-23 before the check ran)
- Archive: for each storm data year 2000-2020, the Internet Archive's newest capture before 2021 of `StormEvents_details-ftp_v1.0_d<year>_c<date>.csv.gz` (host www1.ncdc.noaa.gov); for state temperature and precipitation (`climdiv-tmpcst`, `climdiv-pcpnst`, host ftp.ncdc.noaa.gov or www1.ncdc.noaa.gov), the newest capture before 2021. Each copy is checked against the archive's digest and saved with a receipt (`tools/data/noaa.py archive`); older captures are reported beside, never deciding.
- Storms: county-month event counts (`CZ_TYPE` C; `STATE_FIPS`, `CZ_FIPS`, `BEGIN_YEARMONTH`), the archived file against today's, every county-month with an event in either; unchanged if equal. Age: months from the event month to the capture month.
- Climate: state-month values of both series; unchanged if within 0.1 as printed.
- L: for each age a in months, the bar (at least 99% of storm county-months unchanged and at least 99% of each climate series within 0.1) is checked on all values at least a months old; L is the smallest a at which it holds. L of 12 months or less: the storm and weather exhibits and desk flags count from L, never earlier than §6.3 (storms at event month + 4). L over 12 months or no archived copy: both exhibits are labelled current vintage and their desk flags are live only.
- The weather window starts after NCEI's switch to nClimDiv: "March 13, 2014: NCDC is transitioning from its traditional divisional dataset to the nClimDiv" (`data/noaa/climdiv/div-dataset-transition-readme.txt`), so from 2014-04. Amended 2026-10-23 by the leader before any exhibit result, on the older copies' evidence: copies from 2014-10 to 2015-12 match today only 91.7-92.5% (temperature) and 96.5-97.2% (rainfall) within 0.1, copies from 2016-03 on 99.8%, so NOAA rewrote its climate history in early 2016; the weather exhibit therefore starts 2016-03, when every value and every past normal it uses was published as it stands today.

### FEMA and the Federal Register check (B1; written 2026-10-23 before the check ran)
- Data: OpenFEMA `DisasterDeclarationsSummaries` (v2) and `FemaWebDeclarationAreas` (v1), full CSV downloads with receipts (URL, SHA-256, rows, the dataset's `lastRefresh`), by `tools/data/fema.py`.
- Scope: major disasters (declaration type DR). A county's FEMA date is its earliest `designatedDate` in `FemaWebDeclarationAreas` for that disaster in an Individual or Public Assistance program (codes IA, IH, IFG, HA, DH, DUA, CC and PA with its categories). Hazard Mitigation (HM, usually statewide on the declaration day), Direct Federal Assistance, Other and SBA designations do not count. Corrected 2026-10-23 before the check ran: the first wording, "any program", would have dated every county from the statewide HM designation.
- Check 1: no county designated before its disaster's `declarationDate`; any that are get the declaration date.
- Check 2: 100 county designations drawn with seed 20261023 from DR county designations dated 1994-01-01..2020-12-31. For each, the Federal Register documents of FEMA naming "FEMA-<disaster number>-DR", oldest first; the notice date is the publication date of the first one whose text names the county (its name without the type suffix, as a whole word, any case) or has a sentence naming all counties or areas of the state for Individual or Public Assistance (the statewide Hazard Mitigation sentence does not count). Gap = notice date minus FEMA's date.
- Rule: if more than 5% of matched designations have a gap over 30 days, every FEMA date is replaced by its notice date where one exists and the rest count from event month + 4 months. If more than 20 of the 100 cannot be matched, the check is inconclusive and FEMA is not the fast clock (NOAA's event month + 4 months applies). Otherwise FEMA counts from the end of its date, county by county (§6.3).

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

### Amendments after the step 3 audits (approved by the leader 2026-10-23; no 2021+ return seen)
Each follows the independent step 3 audit (`out/audit/independent_audit_step3.md`, every finding reproduced before it was fixed) or a decision the leader took on counts and dates only.

- **FINRA corrected rows (decision 1B; supersedes "left out" above).** Leaving them out left 7.71% coverage on 2021-06-15, and the WRDS legacy file matches FINRA's corrected values on 99.96% of overlapping pairs, so pre-2021-06 history is today's corrected vintage (stated). From 2021-06-15 a row FINRA flags as corrected takes the same stock's last uncorrected value from up to 62 days earlier, which was public then; with none, the row is missing (neutral). Coverage is measured on the clean table the backtest reads, at least 95% on every FINRA date.
- **Stocks the organisers' daily file drops while still trading (decision 2B).** Through 2025 a held stock whose dsf rows stop while CRSP daily still has rows (13 of $500m or more in 2015-2020, such as Mylan, Cboe and STERIS) is marked on CRSP's daily return until the next formation, where it is sold at CRSP's close; never stubbed. Stocks whose dsf rows stop on 2025-12-31 with no CRSP exit join the 2026 rule. In that rule an 8-K item 1.03 makes the exit a failure even beside an item 2.01. A 2026 stop with no SEC exit form (Cadence Bank, a bank filing with bank regulators, acquired in 2026) is closed at its last dsf price, never stubbed, and listed by name with the stub result beside.
- **Clocks (decision 3).** VIX counts from the end of its day, so the next close (it settles at 4:15 pm). French's daily factors count from the end of the month after their month (French posts each month weeks later); the B23 lag L applies on top only if longer. TB3MS counts from the end of the first business day after its month (benchmark only).
- **Links before 2015 (decision 4A+).** After WRDS ratios, in this order and only for months ratios leaves empty: the stock's own 2015 panel gvkey and iid carried back from the gvkey's first Compustat date; Compustat's header CUSIP (`data/v4/extracts/compustat_ids.parquet`, linking only, never a signal) matched to CRSP's CUSIP of that month; then, for a stock whose every known link names one gvkey, that gvkey while it has Compustat data. Bar, fixed before each check: 99% agreement with an independent key. First attempt: the CUSIP match without dates agreed 98.12% with the organisers' 2015-2020 links and failed (mergers leave the successor's CUSIP in the header); second and final attempt, disclosed: the dated match, 99.85% against the organisers' links and 99.83% against WRDS ratios; the carry-back 99.83% and the fill 100% against WRDS ratios. Coverage of large stocks 2000-2014 rises from 80-86% to 95-98.5%; 240 of the 333 stocks still unlinked have no Compustat data at all. iid 01 only when CRSP shows one common stock for the company (M2).
- **SEC links (H4, L6).** Undated CIK links start at the filer's first filing in our index; the CIK map reads the v4 Compustat extract (the v1 bundle's copy is banned, §1.2; 20 stocks, none in the universe, lose a CIK seen only in 2026 rows). Succession forms (8-K12B, 8-K12G3, 8-A12B) are in the forms index, so every dated decision switch is reproducible; the switch is the filing that registers the listed common shares (QVC's earlier 8-A12B filings registered notes).
- **Earnings calendar (H2).** The real release date is not in the table (it is known only once it happens), and a projection maps to a stock by the link valid on the day the projection is made.
- **Blind mode (M4).** A link period ending after the seal reads as open before the unseal. Trap tests: no clean table holds a globally banned field; no panel column besides the declared label tracks next month's return (2019 rows).
- **Survivorship test (M3).** The six named firms are matched by name on any row; the earnings calendar's coverage is a projected release ahead at month end; an ex-ante gap (coverage at m, return at m+1) is reported beside the PDF's same-period test, never replacing it.
- **Smaller fixes.** Restated dollar amounts and their direction flags are banned in the restatements table (L7); Compustat's deletion date joins an exit only within 90 days of it (L8).
