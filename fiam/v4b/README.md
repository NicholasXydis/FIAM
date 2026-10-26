# v4b — Taildrop plan evaluated against the FINAL mandate

**Headline:** plan grade **B as design / D as executable spec — KEEP WITH MAJOR
FIXES; do not run current repo code as a finals book** (repo book IR 0.99@$10m →
0.45@$1bn, breaks four finals rules). Start with
[EVALUATION.md](/home/drewclaw/Forkfiam/fiam/v4b/EVALUATION.md) §1 scores + §3 ranked
issues, build from [REVISED_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/REVISED_PLAN.md).

**Monthly engine status (D9):** E0–E3 completed; no book passes executed compliance.
Yearly results: `out/engine/yearly_performance.csv`. The corrected 2021–2026
diagnostic is complete; the frozen candidate is **rejected** and E3 is not a
final book. See [OOS_RESULTS.md](/home/drewclaw/Forkfiam/fiam/v4b/OOS_RESULTS.md).

**Binding decisions:** [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md). **Forecaster = E-LASSO** (D6, 2026-10-23), MaInf
primary, run from the authors' unchanged R code in `external/elasso/` via `elasso/`.
Lessons and evidence: [LESSONS.md](/home/drewclaw/Forkfiam/fiam/v4b/LESSONS.md).

## Contents map

| Path | What it is | Use it for |
|---|---|---|
| [EVALUATION.md](/home/drewclaw/Forkfiam/fiam/v4b/EVALUATION.md) | Synthesis verdict: per plan §1–14 KEEP/FIX/DROP + severity, fatal/major/minor ranking, 0–5 scores, do-not-lose list | Judging the Taildrop plan; deck Q&A defence |
| [REVISED_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/REVISED_PLAN.md) | Corrected Oct 28–29 build: specs+math, frozen gates, hour budget, drops, organiser questions. **[Evidence]/[Judgement]** marked | Implementation. Supersedes plan text where EVALUATION says FIX/DROP |
| [eval/01_mandate_fidelity.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/01_mandate_fidelity.md) | Hard-number audit, repo mandate/checker gaps, folder vs Mandate §11 | Finals config + checker build order |
| [eval/02_forecasting.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/02_forecasting.md) | Ridge/GBT/IPCA, T_eff/df/nested CV, decay κ, HLZ/DSR, tradable universe, daily-vs-monthly magnitudes, JKP claim audit | Forecaster + validation machinery (decay shares corrected in 08 E1) |
| [eval/03_risk_construction.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/03_risk_construction.md) | Factor risk, U_beta/U_mu, beta band, stress, QP-vs-conic, support, tiered neutrality | Risk + controller (beta SE corrected in 08 E2) |
| [eval/04_capacity_leakage.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/04_capacity_leakage.md) | Recomputed pool/ADV/participation, spread/borrow, clock holes H1–H9, survivorship | Costs/capacity + leakage assertions (forced-cover rule rejected in 08 C2) |
| [eval/05_validation_reporting.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/05_validation_reporting.md) | Purge/gates/DSR arithmetic, §9 reporting, Carbon Arc workbook (4 sheets), Arcana, agent, 2-day hours | Gates, reporting pipeline, agent design |
| [eval/06_repo_evidence.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/06_repo_evidence.md) | What repo proves/disproves/is silent on; headline reconciliation; reuse-vs-rebuild | Baseline honesty; what code to keep |
| [eval/07_source_audit.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/07_source_audit.md) | 10-paper pack ID + per-paper verdicts, transfer audit, missing lit ranked 1–7 | Citations; what *not* to claim from GKX/GP/JKP |
| [eval/08_critic.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/08_critic.md) | Adversarial cross-check: M1–M4 missed flaws, C1–C6 adjudications, E1–E4 recomputations, spot-check log | **Tie-breaker** where 01–07 conflict; corrected numbers |
| [eval/09_gap_eventday_unknowables.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/09_gap_eventday_unknowables.md) | 7 "unknowables" adjudicated: 4 resolved as frozen defaults, 3 genuinely event-day | Config defaults + Day-1 organiser questions |
| [inputs/](/home/drewclaw/Forkfiam/fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md) | Taildrop plan + mandate + source pack (see Provenance) | Source of truth inputs — do not edit |
| [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md) | Binding decision log (D6: E-LASSO; D7: calibration/decay; D8: risk freeze; D9/D10: no eligible book, rejection) | What is decided, by whom, where enforced |
| [HANDOFF.md](/home/drewclaw/Forkfiam/fiam/v4b/HANDOFF.md) | Current handoff: verdict, completed work, corrected results, session provenance, artifacts, repo state and next steps | Resume work; includes the Claude/Muse session IDs and exact paths |
| [LESSONS.md](/home/drewclaw/Forkfiam/fiam/v4b/LESSONS.md) | Append-only conclusions with numbers and sources | Why each decision was made |
| `elasso/` + `external/elasso/` | E-LASSO: our I/O (`build_input.py`, `run_elasso.R`, `forecaster.py`, `judge.py`, `decay.py`, `freeze.py`, `lag_check.py`) + the authors' code with checksums | **The forecaster** (frozen D7: centred, calibrated) |
| `risk/` | Factor risk (R§4): assigned exposures, daily WLS factor returns, EWMA/NW covariance, EWMA-168 specifics, hedge beta (frozen D8) | **The risk model**; evidence `out/risk/report.json` |
| `forecast/` | Data/labels/harness; retired baselines (ridge, MLP, GBT, initial-plan test) | Evaluation harness and comparisons |
| `engine/`, `config/` | Monthly E0–E3 controller, executed-book checker, simulator, cohort reconciliation and fallback; frozen E-LASSO inputs | See `engine/README.md`; validation in `out/engine/ladder.json` |
| `CONTINUATION_STATUS.md` | Current continuation checklist and remaining work | Read after DECISIONS.md when resuming |
| [CONTINUATION_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/CONTINUATION_PLAN.md) | Next steps on top of REVISED_PLAN: outside evidence that changes it (X1–X9), hurdle/noise maths, amendments A1–A15, decisions, Oct 24–29 order of work | Why REVISED_PLAN changed; all amendments are already merged into REVISED_PLAN |
| `research/` | `pre2021_noise.py/.out` (IC noise, idio vol, pool; labels ≤2020-12 only), `hurdle_by_size.py/.out` (hurdle IR vs N, selection noise) | Sources for every new number in CONTINUATION_PLAN |

Conflict precedence: **08 adjudications > 09 defaults > 01–07 originals >
Taildrop plan**. EVALUATION/REVISED_PLAN already apply that order.

## Provenance of inputs (Taildrop delivery, 23 Oct 2026)

- **Plan:** `inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md`
  (484 lines, §§1–14 + download provenance). Prepared for Andrew Koumoudjian;
  self-described research-backed design, explicitly *not* a tested strategy.
- **Mandate:** `inputs/final_mandate.txt` (1,168 lines), extracted text of
  `data/finals_2026/McGill-FIAM Asset Management Hackathon 2026 — Final Challenge Instructions.pdf`.
  The PDF governs; the .txt is the citable working copy (eval cites `final_mandate.txt:L…`).
- **Source pack:** `inputs/FIAM_Research_Source_Pack.zip` →
  `inputs/source_pack/sources/` (`manifest.json` + `README.md` + 10 PDF/.txt
  pairs: w28432 JKP, w25398 GKX, w27843 vBHL, w24070 KNS, taming_factor_zoo FGX
  (only journal PDF), w23394 HXZ, w20592 HLZ, w16601 BAB, w15205 GP, w22208 MM).
  Downloaded 23 Oct 2026; SHA-256 spot-checked (07 §1). 9/10 are working-paper
  vintages — cite WP year + "published as" separately.
- **Finals data (outside v4b, evidence in eval):** `data/finals_2026/` —
  `chars_final_with_names.parquet`, `8k_20150101_20260831_identified.parquet`,
  `dsf_mini_from_2014.csv`, `factor_char_list.csv`,
  `MCGILL_2026_CarbonArc_Data_Screen.xlsx`, `readme.md`, `ARCANA/`,
  starter scripts (`penalized_linear_hackathon.py`, `portfolio_analysis_hackathon.py`
  — internals still unopened, Day-1 check). No supplied benchmark file present.
- **Repo (evidence only, never assumed optimal):** `fiam/`, `mandates/`,
  `versions/`, `frozen/`, `tests/`, `RESULTS.md`/`README.md` as cited per eval file.

## How to use

1. **Deciding:** read EVALUATION §§1–3 (10 min). Fatal list = pre-OOS blockers.
2. **Building pre-event:** follow REVISED_PLAN §§2–5 then §10 pre-event exits.
   Freeze config + gates *before* the ladder. No hand-typed numbers anywhere.
3. **At the event:** REVISED_PLAN §10 table + §11 four organiser questions.
   Arcana = diagnostics only until PIT vintages confirmed.
4. **Writing the deck:** copy verbatim — clock (plan L271), `P≠Σ` (L86),
   contamination (L309), benchmark conventions (L347–353); use EVALUATION §4
   do-not-lose list; JKP as the 5-number CAPM bridge (08 E3); label snippet
   literature hypothesis-only; report failed gates, never replace thresholds.
5. **Auditing a claim:** every number should meet one of two bars (08 §3) —
   recomputed-by-projection (04 template) or machine-readable artefact
   (`frozen/*.json`, `tests/`; 06 template). Otherwise it's a hypothesis.

Unresolved items are consolidated in EVALUATION §5 and REVISED_PLAN §11 —
they block specific claims (daily returns before `dsf` dividend check, etc.),
not the build order.
