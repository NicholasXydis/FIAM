# Continuation status — 2026-10-23

Read `DECISIONS.md` first, then `HANDOFF.md`. Development stays exclusively in
`fiam/v4b/`. Latest Claude `3fc28de7-893e-4d32-927a-1dc18676d593` and Muse
`01a16aed-f8a1-78f3-8f99-773abeedb888` were recovered and read; their
provenance and directives are recorded in `HANDOFF.md` §1 and §11.

Completed:

- [x] D7 forecaster and D8 risk freezes verified; neither changed.
- [x] Optimizer support/sign/scale repairs, cost units and incumbent impact credit.
- [x] Actual executed holdings and compounded NAV drive each formation.
- [x] Simulator clock/cost/short-liability and checker regressions.
- [x] Source identities and cache provenance; all six 48-formation books saved.
- [x] Paired IR bootstrap, chronological diagnostics, stress and spread checks.
- [x] Independent monthly cohort reconciliation, corrected to float64; all pass.
- [x] Yearly results for 2017–2020 and all six books in out/engine/yearly_performance.csv.
- [x] Fresh review findings addressed; 71 v4b tests, 157 repository tests pass; 3 skip.

Result: no eligible book (D9). E3 net IR -0.139, but 2,041 executed rule/capacity
breach rows; fallback has 5,856. MaInf remains primary; Ma1 was not promoted.
As of 2026-10-23, no 2021+ returns had been unsealed and no Arcana upload had occurred. The corrected 2021–2026 diagnostic was subsequently run as a one-shot and is recorded in `OOS_RESULTS.md`; it is not a promotion.

Next work, per REVISED_PLAN:

1. E4 daily minimum-turnover constraint repair and execution sequencing:
   gross drift, count during overlapping partial fills, liquidation capacity,
   rebalance short floor and beta/sector/size bands. Preserve actual fills.
2. Repeat the frozen performance and process gates; carry validation reuse.
3. Full finals reporting, optional agent/event gates, then a concrete final
   freeze before the single OOS run. Current ready_for_freeze/ready_for_oos are false.

Evidence: out/engine/ladder.json, manifest.json, validation_final.log and
report_refresh.log. The refresh corrected monthly-reference precision only;
it changed neither targets/fills nor the Ma1 selection/hurdle N.

Subsequent audit: read RETURNS_AUDIT.md before continuing. Newly reproduced
issues in dollar residuals, expiry logging and beta calendar alignment remain
unfixed. Address execution semantics and missing-return exits before relying
on E3 returns or adding daily repair. Accounting reconciliation still passes,
but it does not validate these economic assumptions.

---

# Update 2026-10-24 — corrected 2021–2026 diagnostic complete

Completed:

- [x] Rebuilt the 2026 execution path as a split-adjusted total-return index
  from panel `ret`; raw 2026 `dsf_mini` daily returns/closes no longer drive
  Nautilus. Monthly compounding matches panel `ret` to ≤2.0e-14.
- [x] Preserved the invalid first 2026 run and the corrected-data run that was
  killed during native report rendering.
- [x] Completed the corrected native E3 2021–2026 diagnostic through
  2026-08-31 with native fills/positions/account state.
- [x] Wrote `OOS_RESULTS.md`, updated `OOS_FREEZE.md`, `RISK_COST_AUDIT.md`,
  `RETURNS_AUDIT.md`, output `README.md`/`PROVENANCE.json`.
- [x] Ran the cvxportfolio probe as a research backend check (not a strategy
  replacement).
- [x] `85 passed` in `fiam/v4b/tests`.

Result: the frozen 2020-12 E-LASSO candidate is **rejected**. Headline:
2021 −19.45%, 2022 −11.27%, 2023 +9.40% (active −0.02pp), 2024 +0.31%,
2025 −10.82%, 2026 Jan–Aug −8.25%, full −35.83%; net IR −2.28; costs
6.39%/yr; MaInf OOS IC −0.0328 (t −2.47), with January 2021 IC −0.0373 and
March 2021 IC −0.2406. E3 is noncompliant (max gross 2.479, 552.9 average
names, 71,371 liquidation-days, 1,416/1,421 policy-breach days), so
`eligible_for_oos=false`.

Blocked / not done:

- No final book and no promotion. 2021–2026 is diagnostic; the frozen
  candidate cannot be rescued by sign-flipping, reweighting, or tuning.
- 2026 is still a labelled proxy (no FINRA ADV verification, no D5 splice,
  no actual 2026 quotes).
- E4 daily minimum-turnover/compliance repair is not implemented.
- A true next OOS requires a new pre-registered holdout (for example 2027+);
  monthly-refit E-LASSO is a new hypothesis, not a continuation of this
  frozen test.
- Native CSV/tearsheet export disabled for the OOS run to bound memory; ledger
  and holdings are native. Re-enable only for a smaller/report-only run.

Next:

1. If continuing, freeze a new hypothesis with hard names/gross/beta/sector/
   liquidation constraints and a cost budget that clears the mandate hurdle.
2. Rebuild 2026 from actual quote/volume data and apply the D5 splice or
   document why not.
3. Re-run a new pre-registered holdout. Do not use 2021–2026 to choose the
   next model, bands or turnover.
