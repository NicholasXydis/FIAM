# Nautilus backtest and subsequent risk/cost audit

User-authorized order: migrate/fix backtest and reports first; then audit risk
and optimizer costs. Source development remains exclusively in fiam/v4b.
D6/D7 forecast settings stay fixed; no 2021+ returns or Arcana upload.

Design: NautilusTrader 1.230.0 owns quantity orders, fills, positions, account
state and native reports. The old dollar-residual simulator is retained only
as a superseded diagnostic. Submit participation-capped share orders using
prices/ADV available at the execution clock; expiry/cancellation retains
quantities and reasons. Missing observations never fabricate a sale. Use
split-adjusted price paths reconstructed from price_return; dividend cash
comes from total_return minus price_return, so dividends are not reinvested
into phantom shares. Preserve assumptions and data-gap exposure explicitly.
Execution at close t+1, first earned return t+2. Costs remain our documented
spread/impact/fee/borrow assumptions, charged from actual Nautilus fills.
No claim that installing Nautilus validates historical liquidity assumptions.

Files: engine/nautilus_backend.py (engine and strategy),
engine/nautilus_data.py (blind price/dividend/execution inputs),
engine/nautilus_reports.py (native reports, daily NAV, yearly summaries),
research/run_nautilus.py (validation runner), tests/test_nautilus.py.
Later: focused risk and optimizer tests/repairs plus RISK_COST_AUDIT.md.

Checklist:
- [x] Discover pinned version and read official docs/installed API.
- [x] Install isolated optional environment; base project remains unchanged.
- [ ] Reproduce quantity/partial-exit/expiry/missing-data and beta issues in tests.
- [ ] Build native quantity/account execution; verify hand-calculated cases.
- [ ] Generate native orders/fills/positions/accounts/tearsheet plus mandate metrics.
- [ ] Run pre-2021 validation with actual holdings/NAV feedback, replace stale results.
- [ ] Audit factor identification, timing, beta refresh, covariance horizons,
      specific-risk freeze and missing-data handling; test substantive defects.
- [ ] Trace spread/impact/borrow/fees and order caps through support and final QP.
- [ ] Verify final suite, audit source provenance, document limitations and results.

Review focus: same-day lookahead; market fills that bypass liquidity limits;
expired residuals; dividends/splits; stale quotes masquerading as liquidity;
margin/equity versus cash; horizon-1 covariance; optimizer exits outside support.

Additional explicit user request (same task): after the migration and risk/cost
audit are done, freeze the corrected setup and run January 2021–August 2026
once, then attribute return instability. No OOS tuning to force smooth returns.
Daily-data coverage and 2026 input limitations must be disclosed. A single
frozen strategy can be evaluated without claiming it is deployment-ready.
