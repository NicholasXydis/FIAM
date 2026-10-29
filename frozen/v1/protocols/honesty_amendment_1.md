# Honesty tests, amendment 1 (written 2026-10-14, before any honesty run)

## Why
`honesty.md` draws 250 item-2.02 8-Ks per side at random. A check of the text layer, made before any
honesty run, shows that only 11% of those excerpts contain a number (a percentage or a dollar
figure) and 3% contain a direction word (increased, fell, grew, declined); the rest point to an
attached press release. A model cannot read results that are not there, so a random draw would
mostly test nothing. This amendment replaces the sample and the "numbers changed" condition; every
other part of `honesty.md` stands. Both files are kept.

## Sample (replaces "Sample")
- Eligible: 8-Ks with item 2.02 whose excerpt (the masked 3,000-character text in `filing_text`)
  contains at least one percentage or dollar figure and at least one direction word.
- 250 filed in 2024 and 250 filed 2025-02-01..2025-12-29, drawn with seed 42, stratified by size
  group. If a side has fewer than 250 eligible filings, all of them are used and the count is
  reported.

## Conditions (each filing)
- Masked: the excerpt as stored ([COMPANY] and [DATE] already masked).
- Named: [COMPANY] replaced by the company's name from `filings.parquet`.
- Results reversed (replaces "numbers changed"): every direction word swapped for its opposite
  (increase/decrease, increased/decreased, rose/fell, grew/declined, higher/lower, up/down,
  gain/loss, improved/worsened, beat/missed) and every signed percentage negated.
- Dates shifted: every [DATE] filled with the filing date moved one year later.
- Repeat: the masked excerpt asked again at temperature 0.7, seed 43 (all others at temperature 0).

## Measures (unchanged except)
- Flip rate is measured on "results reversed" against "repeat", so a model that reads should flip
  far more often under reversal than under resampling alone.
