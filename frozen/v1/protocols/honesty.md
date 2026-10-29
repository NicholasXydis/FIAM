# AI honesty tests and research-desk checks

## Question
Do our language models read the filings they are given, or recall what they know about the
company? Reported as "tests found no evidence of ..." or the measured effect, never "we prove".

## Sample (fixed before the first run)
- 250 8-Ks with item 2.02 (earnings) filed in 2024 (before Gemma's January 2025 cutoff) and 250
  filed 2025-02..2025-12 (after; daily returns end 2025-12), drawn with seed 42 from
  `filings.parquet`, stratified by size group.
- Task: from the filing text, predict the sign of the 2-day abnormal return: stock total return
  minus the S&P 500 over the first trading day on or after the filing date and the next.
- Model under test: Gemma (it decides). ChronoGPT is the null. Qwen is reported for information
  only: its cutoff is unknown, so it has no clean window.
- Conditions, each filing: masked (names, tickers, addresses removed); named (company shown);
  numbers changed (headline results moved against their direction: a beat becomes a miss); dates
  shifted (every date moved by one year); masked repeated with a new seed.

## Measures
1. Accuracy against the realized sign, by condition and side of the cutoff.
2. Flip rate when numbers change: a model that reads should flip its call.
3. Memorization difference-in-differences: (named - masked accuracy) before the cutoff minus
   (named - masked) after. ChronoGPT (trained to 2020-12-31) runs the same tests as the null.
4. Re-identification: from a masked filing, pick the company among 5 candidates from the same
   industry and size group; chance is 20%.
5. Effective cutoff probe per model: accuracy by filing month across the sample.
6. Minimum detectable effect at 80% power for 250 per side, stated before results: about 12.5
   percentage points for an accuracy gap. Smaller true effects may go undetected; we say so.

## Always-on checks
- Number verifier (code): every number in an agent's answer must appear in its input or a tool
  result; failures are counted and shown.
- 2% of replayed decisions are rerun live; agreement with the cached answer is reported.
- One SHA-256 over all transcripts is published in the report.

## Research desk acceptance
- Rules reader: on the 2025 final-case PDF (read from Andrew's branch, kept outside git), every
  extracted limit carries a verbatim quote and all numeric limits in a hand-made reference are
  found; a human approves before any run uses it.
- Devil's advocate: each critique names a test from the registry of about 15 code tests and an
  expected sign; reported as "k of n confirmed".
- PM memo: built from a template that refuses to render if any number fails the verifier.
