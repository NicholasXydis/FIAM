# Continuation plan — what to do next on top of REVISED_PLAN

**Status:** planning only. **Forecaster = E-LASSO (D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md)).** **Amendments A1–A15 are merged into
[REVISED_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/REVISED_PLAN.md) (2026-10-23), which is the plan
of record; its §10 calendar mirrors §4 here.** This file keeps the evidence (X1–X9), the
maths (§2) and the decisions (§5) behind those edits.
Section numbers like "R§3" point into REVISED_PLAN. Outside material (quarcc-black-fiam,
older Forkfiam work, the teammate's upstream `docs/PLAN.md`) appears **only where it changes
a decision**. Every new number here comes from
[research/pre2021_noise.out](/home/drewclaw/Forkfiam/fiam/v4b/research/pre2021_noise.out) or
[research/hurdle_by_size.out](/home/drewclaw/Forkfiam/fiam/v4b/research/hurdle_by_size.out).
Both use labels that end by 2020-12 only. **[Evidence]** and **[Judgement]** are marked as in R.

## 0. Bottom line

1. **The calendar in R§10 is wrong.** The organisers wrote that the two days in Montreal
   "are not build time". Teams must arrive with models built, the pipeline running and
   results reproducible. Everything in R§10's D1/D2 table moves to Oct 24–27. Event days
   only rerun the frozen strategy under any new constraints (§4).
2. **The mandate's hurdle sets one bar, and it is high.** A fully neutral book beats
   T-bill + 4% only if its residual rank IC, after construction losses, is about
   **0.031–0.039** (§2.1). SYY-style composites scored **+0.010** on 2015–2020 and
   **−0.005** on 2019–20. Plan for a negative headline IR and make it the prepared, credited
   story, not a surprise.
3. **Selection noise is as large as the signal.** With 24 validation months, picking the
   best of 96 settings by IC adds **+0.044 to +0.062** IC from luck alone (§2.3). That is
   more than the hurdle IC. R§3's "near-optimal set + 1-SE rule" is the right instinct. It
   must become the only selection rule, with a hard cap on the number of settings tried.
4. **Year-to-year swings are mostly expected noise, plus style.** At IC 0.02 a losing year
   has a **24%** chance (§2.2). Two things lower it: more independent signals, and taking
   out style bets. Better tuning does not.
5. **Two outside lessons change the build.** Simple models won every frozen tournament
   (quarcc-black Exp16). Paid GPU runs died four times on spend limits. So: one cheap
   forecaster family, CPU only, nothing rented on the critical path.

## 1. Outside evidence that changes R (and nothing else)

| # | Fact | Source | Changes |
|---|---|---|---|
| X1 | Organisers' email, 2026-10-23: event days "are not build time"; final instructions bring "a set of constraints to tune against" | upstream `docs/PLAN.md` §2 | R§10 schedule → §4 below. Event day = rerun under new limits, both numbers shown |
| X2 | WRDS is allowed (round-one rule, finals silent). The team holds read-only CRSP daily (volume, bid/ask), TAQ and Compustat extracts through 2025-12 | upstream `docs/PLAN.md` §3.1, §6.6 | R§7 "no spread data" holds only for the organisers' files. Calibrate the half-spread on CRSP/TAQ for 2015–2020. Build ADV from CRSP daily volume through 2025. R's bucket table becomes the **2026 fallback**, labelled. The 0.5×/1×/2× spread sensitivity stays |
| X3 | The point-in-time clock, dated PERMNO links, exits table and blind mode already exist and are tested (`fiam/v4/clock.py`, `links.py`, `exits.py`, `sources.py`; 160 tests) | upstream branch `b5bdf0d` | R§6 assertions are built on these, not rewritten. Pull the branch before step 1 of §4 |
| X4 | Frozen forecaster tournament, 2018 discovery: B0-MLP IC 0.032, linear 0.026, **LightGBM −0.038**. Cross-stock attention gained +0.020 IC yet changed the fixed-solver book return by **−0.0001**. No paper architecture was admitted | quarcc `experiments/16/TRIAL_LEDGER.md` | R§3: no model-family search. Fixed **equal-weight blend of group-ridge + one shallow nonlinear model**, settings fixed ahead of time. Promotion only on book-level net change (R§8 already says so; this is the evidence) |
| X5 | The economic part of the edge did not track how well models imitated the oracle or how well they ranked; the short leg was the steady drag | quarcc `experiments/15/README.md`; audit `AUDIT.md` §4–5 | Keep the R§3 leg-specific ICs. Judge shorts against a risk-matched short-eligible reference, not on raw short P&L |
| X6 | Audit P1 bugs: genuine −100% returns dropped as NaN; fit months that cannot hold data, given the warm-up; HAC returning t = ∞ from one observation; pandas renaming `_field` in `itertuples` | quarcc audit `AUDIT.md` §7 | Add four checker tests (§3, A9) |
| X7 | Four paid GPU runs stopped on spend limits or a disabled workspace; a CPU fallback ran for hours with no progress | quarcc `15b/TRIAL_LEDGER.md`, `16/TRIAL_LEDGER.md` | Nothing on the critical path needs a GPU or a paid remote job. Target ≤5 min per $1bn book on CPU |
| X8 | Older Forkfiam book: style-neutral variant IR **−0.89**. IR 1.63 in 2021–22 vs −0.01 in 2023–26. 2016–20 IR −1.00. ML on the 147 had IC t 2.5–4.1 but **lost money after costs**. Signal search: +1.78 where searched, +0.33 on unseen years | `RESULTS.md` (tried, halves, clean tables) | The old edge was style timing. Expect R's residual book to be much weaker. Costs and turnover are the main lever we control (§2.1) |
| X9 | A 60/40 "residual sleeve" blend was chosen on 2021-01..2026-08 results | `docs/finals/research/.../v3-qbase-sleeve-2026-10-17.md` | Add it to the ban list with v3's 15 choices. The idea may not come back in v4 in any form |

Not carried over on purpose: Carbon Arc piece lists, the site and film, USB kit work,
history-twin rebuilds and the six-signal family in upstream `docs/PLAN.md`. They add scope,
not decisions. The one exception is R§8 E5, which already allows ≤1 event sleeve.

## 2. New maths that should drive the remaining choices

### 2.1 The hurdle condition [Evidence: research/hurdle_by_size.out; Judgement: TC, costs, TE inflation]

Take an equal-weight approximation: N names, gross G, N/2 per side from a pool P. Grinold's
alpha per name is `α_i = IC·ω·z_i`. Annual book alpha is `G·TC·IC·ω·√12·E|z|(p)`, with
`p = N/(2P)` and `E|z| = φ(Φ⁻¹(1−p))/p`. Tracking error is `TE ≈ G·ω/√N × inflation`.

`IR = √N · (G·TC·IC·ω·√12·E|z| − 0.04 − c) / (G·ω·infl)`

- **The sign does not depend on TE or N.** It depends on whether the book's alpha clears
  4% + costs. N only scales the size of the result, whether it is good or bad.
- Inputs: pool P = 1,862 (2015–20 median, `me≥600`, price ≥$5); ω = 25.9%/yr (median
  `ivol_capm_252d` ×√252); G = 1.77. Judgement inputs: TC = 0.6, c = 2%/yr, realised TE =
  1.5× the idiosyncratic estimate.

| N | idio TE | realised TE | IR @ IC .02 | .03 | .04 | .06 | IC needed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 200 | 3.2% | 4.9% | −0.44 | −0.04 | +0.36 | +1.16 | 0.031 |
| 275 | 2.8% | 4.1% | −0.58 | −0.14 | +0.29 | +1.16 | 0.033 |
| 450 | 2.2% | 3.2% | −0.87 | −0.38 | +0.11 | +1.08 | 0.038 |
| 500 | 2.1% | 3.1% | −0.95 | −0.45 | +0.05 | +1.04 | 0.039 |

What follows:
- **A neutral book carries 2–3% idiosyncratic TE, not 5–8%.** R§5's σ_max ∈ [8%, 12%]
  range cannot be reached without style tilts, which Arcana lens 1 penalises, or
  concentration below the 200-name floor. Replace it with an **ex-ante TE that is reported,
  not targeted** (A1).
- **At ICs we can realistically reach (≤0.035), fewer names hurt less.** Below about 0.06
  the concentrated end wins. The ~275 vs 450 choice comes from this formula with validation
  IC and the measured cost curve plugged in. Bigger positions raise impact per dollar by
  about √(450/275) ≈ 1.28 (R§7 sqrt law), so feed that into c(N). It is mechanics, not a
  search (A2).
- **The cost lever is worth as much as the IC lever.** Each 1% of NAV/yr in cost moves the
  IC needed by about 0.006 at N = 275. Halving turnover cost is worth as much as a new
  signal.
- Deck: one slide with this identity, the IC we measured, the IC needed, and the gap. If
  the gap is negative, it says so plainly. Mandate §§4–5 credit an honest negative result.

### 2.2 Why alpha jumps around from year to year [Evidence: pre2021_noise.out]

Monthly rank IC sd ≈ **0.10** for every signal checked (`syy` 0.102, `gp_at` 0.105,
`o_score` 0.085, `ret_12_1` 0.155). The standard error of a yearly IC mean is therefore
0.10/√12 = **0.029**. That is larger than any mean IC in the panel (`gp_at` +0.021,
`syy` +0.010).
- P(losing year) = Φ(−IC/0.029): **24%** at IC 0.02, **8%** at 0.04. Over 68 OOS months,
  about 1–2 negative years are expected even if the edge is real. The pre-2021 record shows
  exactly this: `syy` by year +0.027, −0.035, +0.043, +0.036, +0.006, −0.017.
- Better fitting does not shrink this. Two things do: **independent signals**, since
  composite sd scales as `σ√((1+(K−1)ρ)/K)` with ρ the correlation of IC series; and
  **taking out style bets**, which caused the 2021–22 vs 2023–26 split (X8).
- Rule (A6): report IC and net IR by year with this ±band drawn. A year inside the band is
  noise. Only a year outside it starts the R§8 kill or decay review.

### 2.3 How much luck is in each choice [Evidence: hurdle_by_size.out]

SE of a 24-month mean IC ≈ 0.020. The expected best of K null settings ≈ `SE·√(2 ln K)`.

| Choice point | K | Expected luck in the winner |
|---|---:|---:|
| 96 independent settings | 96 | +0.062 IC |
| 96 correlated settings (effective K ≈ 10) | 10 | +0.044 IC |
| hurdle IC (§2.1) | — | 0.031–0.039 |

So any "pick the max" rule over R§3's λ grid, R§4's half-lives and R§5's knobs can make up
the whole hurdle from noise. R§8's paired block-bootstrap promotion gate is the defence.
§3 turns it into hard caps.

## 3. Amendments to REVISED_PLAN (freeze in `mandates/final_2026.json` + policy annex before any ladder run)

| ID | R§ | Change | Why |
|---|---|---|---|
| A1 | §5 | Drop the σ_max ∈ [8%,12%] start range. Scale = max gross under the HARD rules (§2.1 shows IR rises with gross). Report ex-ante TE and implied γ; use `IR(k)` only to check whether a lower scale is needed for costs | §2.1; 08 M1 |
| A2 | §5 support | Choose N ∈ {≈250, ≈300, ≈450} by plugging the frozen-validation IC and the measured c(N) into §2.1's formula. Not by comparing backtest IRs | §2.1; avoids a three-way IR horse race |
| A3 | §3 | **Superseded 2026-10-23 by D6: the forecaster is E-LASSO** (MaInf primary, Ma1 alternate chosen only on net IR in the engine; authors' R code unchanged, `elasso/`). The original A3 (50/50 ridge + MLP/GBT blend) was tested and retired: LESSONS 14–30. | LESSONS 24–30; DECISIONS D6 |
| A4 | §3, §8 | Hard cap: **≤12 registered configurations** before freeze, across all of λ, half-life, support, p and bands. Each choice uses the most regularised setting within 1 block-bootstrap SE. Every extra setting needs a written reason and counts toward DSR N | §2.3 |
| A5 | §8 | Add an economic gate before any E-step promotion: the step must raise validation **net** IC × TC toward the §2.1 IC needed. A step that raises gross IC but lowers TC or raises cost does not pass | X4, X8 |
| A6 | §8 report | Yearly IC and IR exhibit with the ±0.029/√(years) noise band. Kill or decay reviews trigger only outside the band | §2.2 |
| A7 | §7 | Spread: CRSP/TAQ effective half-spread by size and price bucket, fitted 2015–2020. ADV: CRSP daily volume through 2025, then `dolvol_126d` lagged as the 2026 fallback, labelled. Keep 0.5×/1×/2× | X2 |
| A8 | §2 | Ban list in config: v3's 15 OOS-visible choices, the 60/40 residual sleeve, and any setting first seen in `out_r11..r13` logs (2021+ replays) | X9; Mandate §7.8 |
| A9 | §2 checker | Four tests: (a) a synthetic −100% return stays in P&L; (b) the first fit month is no earlier than the warm-up allows; (c) no t-stat or CI is produced from fewer than 12 independent periods (it prints "n/a"); (d) no `_`-prefixed fields go through `itertuples` | X6 |
| A10 | §1, §10 | CPU only; ≤5 min per $1bn book; no Modal or rented GPU on the critical path; agent answers cached locally before freeze | X7 |
| A11 | §6 | Build the clock assertions on the upstream `fiam/v4/clock.py` / `links.py` / `exits.py` (tested); keep R's field rules as extra assertions | X3 |
| A12 | §11 deck | Add the §2.1 hurdle slide and the §2.2 band slide to the honesty pack | §2 |
| A13 | §5 short bound | The $500m floor is checked on **rebalance dates**, since each rebalance is a formation. At a rebalance every short held must have `min(me, me_company) ≥ $500m`; names below are covered in that rebalance's trades. Between rebalances drift is held, never force-covered, but any daily repair that opens or increases a short re-checks the floor. Replaces R's hold-or-cover for names below the floor at rebalances | Mandate §3.1 "measured at the formation date"; decision §5.2 |
| A14 | §2, §11 | No v4 book (backtest, rehearsal or candidate) is uploaded to Arcana before the single 2021–26 run. Before that, the lens checks run in our own code. Arcana's optimiser, hedge ideas and conviction sizing never set a weight | Decision §5.3 |
| A15 | §7 ADV | ADV = CRSP daily dollar volume, trailing 126 days and lagged one day, through 2025-12. From 2026-01 it is `dolvol_126d` lagged one month, times a fixed splice ratio (median CRSP-ADV / `dolvol_126d` on 2015–2020, frozen pre-2021). The 2026 sub-period is labelled. Checker unit test: `dolvol` is monthly, not daily | X2; R§7 21× error mode; decision §5.4 |

R stays as written in all other respects. Notably, R§5.5's fallback book is now *likely*
to be needed, not a remote contingency. Build it first, not last.

## 4. Order of work, Oct 24 → Oct 29 (replaces R§10's hour table)

Each line is an exit check. When a line slips, use the cut column. Never loosen a gate.

| By | Must be true | Cut if late |
|---|---|---|
| **Sat Oct 24** | Config + ban list + checker green on a dummy book (R§2, A8, A9). Daily $1bn simulator on the t+1/t+2 clock reconciles daily ↔ monthly on a 2017 baseline. R§5.5 fallback book runs end to end | Nothing; this is the floor |
| **Sun Oct 25 midday** | Costs calibrated (A7). E-LASSO run on the finals panel through 2020-12 (D6). Decay done (LESSONS 32). Hurdle exhibit filled with measured IC, TC, c (§2.1) | Carry MaInf only; Ma1 waits |
| **Sun Oct 25 night** | Risk model + QP controller (R§§4–5). E0–E3 on validation with ≤12 configs (A4). N chosen by A2. Agent exception cards for 2017–2020 queued to run overnight (R§9) | Drop E4 weekly (stay monthly + daily repair). Drop E5 entirely |
| **Mon Oct 26** | E6 agent vs `m≡1` on validation. Reporting emits every §9.1 cell + 8 §9.4 exhibits from files on the candidate. **Freeze + single 2021-01..2026-08 run, evening** | If E6 has not run, ship `m≡1` and report "agent not evaluated" |
| **Tue Oct 27** | Arcana upload + own-vs-Arcana reconciliation. Deck built from output files only. Rule-change rerun drill (three mock constraint sets). Q&A drill on positions | Rehearsal stays; Carbon Arc demo goes |
| **Wed–Thu Oct 28–29** | Re-diff the event instructions → edit config → rerun the frozen strategy → show both numbers. No new signals, models or settings | — |

## 5. Decisions (taken 2026-10-23, freeze in config)

1. **Forecaster: E-LASSO** (D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md), user 2026-10-23: "yes please replace with E-Lasso"). It supersedes the earlier MLP-vs-GBT rule (D2), which picked the MLP before
   E-LASSO was tested.
2. **Short floor:** checked only on rebalance dates; between rebalances drift is held → A13.
3. **Arcana:** no v4 book uploaded before the single 2021–26 run → A14.
4. **2026 ADV fallback:** not settled by the team, so decided on these grounds: `dolvol_126d`
   is already in the organisers' panel through 2026-08, needs no new source and has no
   vintage risk, while FINRA volume is still downloading and has its own split problems.
   Spliced to CRSP with a frozen pre-2021 ratio → A15. Revisit only if FINRA passes its
   upstream agreement check before Saturday's freeze of the config.
