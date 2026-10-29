# Protocols

Each file fixes a test before its first run: the question, the data and window, the method, the
deciding number and what is reported whatever happens. A change after a run is a new dated
protocol, and both are kept. Protocols of retired research books are kept in git history only.

| File | Covers |
|---|---|
| `stress.md` | Crises, named scenarios, reverse stress, liquidity, unwind |
| `honesty.md`, `honesty_amendment_1.md` | AI honesty tests, number verifier, rules reader, devil's advocate |
| `crowd.md`, `crowd_amendment_1.md` | The AI Crowd Lab; copycat test, capacity tax, herding and fear |

## Shared conventions
- Windows: pre-2021 = holding months 2016-01..2020-12; reported = 2021-01..2026-08; LLM outputs
  are clean on 2025-02..2026-08 (after Gemma's January 2025 cutoff).
- Correction (2026-10-22): this file once said 2021-2026 was never used to choose. That was wrong.
  From 64b6a3e (2026-09-20) to ea4176b (2026-10-01) it was the design window, and fifteen of the
  final research book's choices were made with it visible (among them `target10`, the 12-signal
  set, carry-in, `risk_rank`, the learned hedge, the zero-beta band, ridge 30, pool 200,
  `MIN_SIGNALS` 9). That book's record is partly in-sample and never called out-of-sample; v4
  decides on pre-2021 data only and runs 2021-2026 once.
- Data: every input dated at or before the decision month end (`eom`); short interest counted from
  8 trading days after settlement; after options (2025-08) and daily data (2025-12) end, the
  documented fallback applies and is labelled.
- Finance research cited as a reason is first public by 2021; other fields any date. Seeds are 42
  unless stated, and every random draw is fixed before the first run.
- Trials: every configuration run counts once in `out/research/trials.csv` (date, protocol, switch set,
  window, capital); capital levels of one configuration are one trial. The deflated Sharpe counts
  1,665 past fits, `research/exp`, Andrew's runs and every ledger row.
- Agents never set or change positions; any agent-derived number is an exhibit or a what-if.
- A result that cannot be computed takes its protocol's fallback, and the gap is reported, never
  silently dropped.
