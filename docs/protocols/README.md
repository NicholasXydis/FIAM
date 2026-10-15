# Protocols

Each file here fixes a test before its first run: the question, the data and window, the exact
method, the number that decides it, and what is reported whatever happens. A protocol is committed
before any run it covers; a change after that is a new protocol with its own date, and both are kept.

| File | Covers | PLAN.md step |
|---|---|---|
| `v2.md` | The five v2 improvements and the other switches | S2 |
| `risk.md` | Volatility model, risk model, risk dashboard, volatility budget, warning signs | S3 |
| `evidence.md` | Deflated Sharpe, bootstrap, HAC, break-even IC, neutrality, regimes | S3 |
| `honesty.md` | AI honesty tests, number verifier, rules reader, devil's advocate | S5, S7 |
| `crowd.md` | AI Crowd Lab: crowds, herding, crowd model, without/with/against, crowd risk | S6 |
| `stress.md` | Crises, named scenarios, reverse stress, liquidity, unwind | S8 |
| `nautilus.md` | Accounting replay tolerances | S9 |
| `carbon_arc.md` | Carbon Arc spending data | S10 |
| `honesty_amendment_1.md` | Honesty sample and the "results reversed" condition | S5 |
| `v2_amendment_1.md` | The `grinold` switch, v2a and v2-pass | S2 |
| `capacity.md` | Optimal fund size, break-even size, cost stress | S3 |
| `crowd_amendment_1.md` | Copycat test, capacity tax, what the crowd buys, herding and fear | S6, S7 |
| `finals.md` | Turnover cap and net band, rules rehearsals, the pack for any book, which book | S7 |
| `v2_amendment_2.md` | v3, the final book: size, low-volatility, risk target, drawdown brake | S2 |
| `v2_amendment_3.md` | Final v3: beta at zero, 10% risk, daily gross ceiling, risk-sized names, adaptive signals | S2 |
| `final_exhibits.md` | Is final v3's edge real (four benchmarks), live projection, risk table, exposures, agents, dendrogram | S3, S7 |

## Shared conventions

- Windows: **pre-2021** = holding months 2016-01..2020-12, used for every choice; **reported** =
  2021-01..2026-08, shown once, never used to choose. The clean window for LLM outputs is holding
  months 2025-02..2026-08 (after Gemma's January 2025 cutoff).
- Data: every input dated at or before the decision month end (`eom`); short interest counted from
  8 trading days after settlement; options data ends 2025-08 and daily data ends 2025-12, after
  which the documented fallback applies and is labelled.
- Finance papers cited as reasons are first public by 2021; other fields any date.
- Seeds: 42 unless stated. Every random draw is fixed before the first run.
- Trials: every backtest configuration run counts once in the trial ledger
  (`out/v2/trials.csv`: date, protocol, switch set, window, capital). Capital levels of one
  configuration are one trial. The deflated Sharpe uses 1,665 past fits + `research/exp` +
  Andrew's runs + every ledger row.
- Agents never set or change positions. Any agent-derived number is an exhibit or a what-if.
- If a result cannot be computed (missing data, a model that will not load), the protocol's
  fallback applies and the gap is reported; nothing is silently dropped.
