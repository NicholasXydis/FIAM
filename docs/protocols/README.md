# Protocols

Each file fixes a test before its first run: the question, the data and window, the method, the
deciding number and what is reported whatever happens. A change after a run is a new dated
protocol, and both are kept.

| File | Covers |
|---|---|
| `v2.md`, `v2_amendment_1.md` | The five v2 improvements and other switches; `grinold`, v2a and v2-pass |
| `v2_amendment_2.md` | v3: size, low volatility, risk target, drawdown brake |
| `v2_amendment_3.md` | Final v3: zero beta, 10% risk, daily gross ceiling, risk-sized names, adaptive signals |
| `risk.md` | Volatility model, risk model, dashboard, volatility budget, warning signs |
| `evidence.md` | Deflated Sharpe, bootstrap, HAC, break-even IC, neutrality, regimes |
| `final_exhibits.md` | Is final v3's edge real, live projection, risk table, exposures, agents, dendrogram |
| `capacity.md` | Optimal and break-even fund size, cost stress |
| `stress.md` | Crises, named scenarios, reverse stress, liquidity, unwind |
| `honesty.md`, `honesty_amendment_1.md` | AI honesty tests, number verifier, rules reader, devil's advocate |
| `crowd.md`, `crowd_amendment_1.md` | The AI Crowd Lab; copycat test, capacity tax, herding and fear |
| `finals.md` | Turnover cap, net band, rules rehearsals, the pack for any book, which book |
| `finals_global.md`, `finals_global_amendment_1.md` | The `global` switch, country caps, minimum cap, excluded sectors |
| `nautilus.md`, `carbon_arc.md` | Accounting replay tolerances; Carbon Arc spending data |

## Shared conventions
- Windows: pre-2021 = holding months 2016-01..2020-12; reported = 2021-01..2026-08; LLM outputs
  are clean on 2025-02..2026-08 (after Gemma's January 2025 cutoff).
- Correction (2026-10-22): this file once said 2021-2026 was never used to choose. That was wrong.
  From 64b6a3e (2026-09-20) to ea4176b (2026-10-01) it was the design window, and fifteen of final
  v3's choices were made with it visible (among them `target10`, the 12-signal set, carry-in,
  `risk_rank`, the learned hedge, the zero-beta band, ridge 30, pool 200, `MIN_SIGNALS` 9). Final
  v3's record is partly in-sample and never called out-of-sample; v4 decides on pre-2021 data
  only and runs 2021-2026 once.
- Data: every input dated at or before the decision month end (`eom`); short interest counted from
  8 trading days after settlement; after options (2025-08) and daily data (2025-12) end, the
  documented fallback applies and is labelled.
- Finance research cited as a reason is first public by 2021; other fields any date. Seeds are 42
  unless stated, and every random draw is fixed before the first run.
- Trials: every configuration run counts once in `out/v2/trials.csv` (date, protocol, switch set,
  window, capital); capital levels of one configuration are one trial. The deflated Sharpe counts
  1,665 past fits, `research/exp`, Andrew's runs and every ledger row.
- Agents never set or change positions; any agent-derived number is an exhibit or a what-if.
- A result that cannot be computed takes its protocol's fallback, and the gap is reported, never
  silently dropped.
