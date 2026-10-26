# Decisions (binding; newest first)

Each decision states what was decided, by whom, the evidence, and where it is enforced.
A later decision may supersede an earlier one; both stay listed. Every plan, config and
code file that touches a decision points here.

## D26 — As-of selector for specific risk (2026-10-26)

**Scope:** implement and synthetic-test a mechanism that can repair D25. No
market-data experiment, promotion, or change to the existing risk-model default.
The current user asked to make the strategy profitable; avoiding look-ahead is
necessary to distinguish a genuine improvement from a historical artifact.

**Rule, fixed before tests:** inputs are per-formation/per-name QLIKE losses for
EWMA-84 and EWMA-168 plus each observation's explicit label-completion timestamp.
At a decision timestamp, discard labels completed later, average each candidate's
loss across the same complete names within each formation, and give each completed
formation equal weight. Use at most the latest 60 complete formations. Require
at least 12 paired formations; otherwise return fixed EWMA-84. Select the lower
mean loss; ties go to EWMA-84. Missing formation date, completion timestamp,
or paired loss is excluded. Return the selected name, the completed-formation
count and the latest label timestamp used. Do not manufacture late or missing
labels. The selector is not yet adopted as a strategy: it must be integrated and
registered separately before use on real data, including multiplicity and all
earlier window disclosures. D22/D23's no-market-re-gating stop remains in force.

**Synthetic outcome:** `risk.specific.choose_ewma_asof` passes the two tests in
`tests/test_specific_asof.py` on Modal, including invariance to changes in
unfinished labels and the insufficient-history fallback. The model's existing
global-selection default is unchanged; this does not prove a new book's alpha.

## D25 — Disclose look-ahead in validation-period risk-model selection (2026-10-26)

**Finding from code inspection; no new market return was read.** `risk/model.py`
constructs `self.spec_race = specific.race(self.resid, all_eoms)` and uses the
single winner for all formations. `risk/specific.py` scores realized-next-month
variance for formation years 2017–2020. Consequently the risk method used at
a 2017 formation was selected using later 2017–2020 outcomes. The factor half-life
84 was also selected on the 2016-12..2020-11 validation window
(`risk/validate.py`, `out/risk/report.json`). This is **model-selection look-ahead**
in the 2017–2020 experiments, even though the individual rolling estimates use
past data. D21's assertion that its risk inputs are selected from data available
before each formation is incomplete. The effect on returns or gate conclusions
has not been measured.

For the later 2021–2026 diagnostic, 2017–2020 precedes the period, but that
diagnostic has separate, already disclosed contamination and data limitations.
Do not silently rewrite earlier experiments. A future evaluation needs risk
hyperparameters fixed without the test window, or an expanding selection using
only **completed** labels before every formation, with known-truth as-of tests
and an explicit record of repeated choices. D22/D23's synthetic interval
stop still applies; no new market outcome was opened by this audit.

## D24 — Correct the short-floor formation check (2026-10-26)

**Finding before repair:** the mandate §3.1 and `engine/checker.py` define the
$500m short floor as **each shorted company's market capitalization**, not the
total dollars shorted. D19 and D21 gate code incorrectly label a $500m aggregate
short-notional check `short_floor`. The selection pipeline already uses dated
`short_ok`, but the gate does not independently verify each short's capitalisation.
`RESEARCH_ROADMAP_2026-10-26.md` repeated the incorrect aggregate-floor claim.

**Repair:** synthetic tests first, then check `min(me, me_company) >= $500m` for
each selected short at formation, with missing values or missing names failing.
Keep the previously registered aggregate ≥$500m short-notional check as a
separately named **research constraint** for D19/D21 reproducibility; do not call
it a finals mandate. Existing decisions and results remain as recorded. No market
re-gating or earlier strategy result is changed by the mechanical repair.

**Synthetic outcome:** `tests/test_formation_short_floor.py` checks each short's
capitalization, missing data and the distinction from short-book notional. The
full v4b Modal suite passed 119 tests after this and D22–D26, with 54 existing
Pandas/Nautilus deprecation warnings.

## D22 — Audit daily-versus-horizon risk and the G2 interval (2026-10-26)

**Authorization:** Andrew asked to evaluate the additional work and make the strategy
profitable, retaining the existing short-window discipline. This authorizes a targeted
diagnostic and does not make an unsuccessful strategy profitable by definition.

**Observed before any new result:** D19/D21 G2 standardizes daily returns using
`model.vol(snap, w) / sqrt(252)`. That equals the square root of **holding-period**
variance divided by its horizon, not necessarily the variance of a daily return.
`risk/covariance.py` includes lagged factor covariance in `F`; moreover, `F1` is a
Newey–West-adjusted estimate rather than raw one-day variance. Daily tests need the
zero-lag covariance. D21's failed gates are preserved and not retroactively passed.

**Prerecorded diagnostics, all synthetic first:**
1. Add a point-in-time zero-lag factor covariance and daily portfolio variance using
   the same exposures, specific risk, VRA and PCA conventions. Verify analytically
   on known covariance fixtures, including factor autocorrelation and date cutoffs.
   Keep the risk optimizer's original horizon model and existing D21 gate unchanged.
2. Test the D21 chi-square 90% volatility-ratio interval's empirical coverage on
   10,000 independent synthetic 160-session paths, fixed seed 20261026, for Gaussian
   and variance-normalized Student-t(5) innovations. Pass only if coverage lies in
   [0.875, 0.925] for both. This is a test of the gate, not a strategy promotion.
   No financial outcomes or new window are needed. A miss invalidates that interval
   under that simulated data-generating process; it does not reverse D21 outcomes.
3. If either known-truth test fails, stop before any market-data re-gating; report
   the failure. No long-window or OOS run is authorized by this diagnostic.

**Profitability remains separate:** D21 does not test expected-return alpha, costs,
or executed mandate compliance. No claim about exceeding v4 can be made until a
pre-registered separate-leg alpha test and the execution audit pass.

**Outcome (synthetic only, `out/g2_known_truth.json`):** the 10,000-path coverage
check passed for Gaussian returns (0.8993, Monte Carlo SE 0.0030) and failed for
Student-t(5) (0.6975, SE 0.0046). As preregistered, no market-data re-gating was
run. `tests/test_spot_risk.py` verifies the separate zero-lag daily-risk calculation;
the original G2 and all earlier results remain unchanged. The t(5) case demonstrates
undercoverage in that synthetic setting, not the exact coverage of the real data.

## D23 — Synthetic candidates for a dependable volatility interval (2026-10-26)

**Scope:** repair the test identified by D22. Synthetic data only. This does not
authorize market re-gating, full-window returns, or changes to any past result.
Written before calculating these candidates' results.

**Fixed simulation:** 10,000 independent 160-session paths per distribution,
seed 20261027, Gaussian and variance-normalized Student-t(5). The three intervals
are (a) chi-square (control), (b) percentile bootstrap on sample standard deviation,
(c) basic bootstrap on log standard deviation. Bootstrap: 500 iid resamples per
path, seed 20261028, processed in batches. Each interval is 90%. An interval is
eligible only if coverage of the true standard deviation is in [0.875, 0.925] in
both distributions, and the 90% interval is wholly inside [2/3, 3/2] on at least
80% of true-unit-vol paths. In order, consider (b), then (c). Report every result;
if neither is eligible, stop. These iid simulations do not establish validity under
serial dependence or regime changes; those need separate known-truth tests before
any use with real data.

**Outcome (synthetic only, `out/g2_robust_known_truth.json`):** no interval passed.
Gaussian coverage: chi-square 0.9048, percentile 0.8843, basic-log 0.8882.
Student-t(5) coverage: 0.6920, 0.8293 and 0.8439, respectively. The latter two
miss the preregistered 0.875 minimum. Unit-vol power was ≥0.965 for all. No
interval is adopted; no market-data re-gating is authorized by this study.

## D21 — Beta repair hypothesis H-β, after known-truth gate tests; plan of record = STATUS_ASSESSMENT + RESEARCH_ROADMAP (2026-10-26)

**Decision (user, 2026-10-26, answering D20 step A).** "1. ok": the uncalibrated engine
beta. "2. yes realized beta": gate the book's realised beta, not stock-level slopes.
"3. yes": v4-style neutrality under several betas, plus style neutrality. "BUT ABOVE ALL,
you must really understand what I've determined in the plans as well as EVERY REFERENCE":
`STATUS_ASSESSMENT_2026-10-26.md` and `RESEARCH_ROADMAP_2026-10-26.md` are the plan of
record with D16–D20. Their order binds: audit and known-truth tests first, then the
registered beta hypothesis on the directions actually traded, then the E6 and decile
gates. Written before any phase ran.

**Phase 0 — trust the measurement (roadmap §1, §2.1, §2.5). No market returns read.**
- **0a Known-truth fixture** (`tests/test_gate_truth.py`, synthetic). A market with calm
  (0.6%/day) and stressed (2.0%/day) windows. 2,000 stocks with known betas
  (dispersion 0.4), 10 industry residual factors, t(5) residuals, 2% missing days.
  Four windows of 40 sessions, pooled. Dollar-neutral 400-name books. Checks:
  - HB size: true |β| = 0.10 passes ≤ 5%.
  - HB power: true β = 0 passes ≥ 80%.
  - Bootstrap 90% coverage in [0.85, 0.95].
  - Zero-filled missing returns move book beta by < 0.01.
  - Stock-level slope recovery with known slope 1 (coverage reported).
  A failed check fixes the test, never the data, and 0a is re-run before Phase 1.
- **0b Point-in-time.** Every E6 input is traced to its estimation window
  (`out/pit_audit.md`). Known: the forecaster scale and kappa come from `frozen.json`
  fitted on 2016-12..2020-11, the whole validation window, and are used inside 2017
  formations. E6 must therefore be invariant to any positive rescaling of μ, tested on
  the fixture: same weights within 1e-6. If it is not, this is a look-ahead and Phase 1
  waits for the user.
- **0c Execution audit** (roadmap §1.3) is required before any G5 or promotion, not
  before Phase 1.

**Phase 1 — H-β on W17–W20 (D20 windows), data before each formation only.**
- **Beta in force:** B1 = engine hedge beta, `beta_calibration` off.
- **Construction (E6 and H-ref):**
  - B1 band 0.02, hard (slack ≤ 1e-6).
  - Added bands |Σw·B5| ≤ 0.05 and |Σw·B4| ≤ 0.05 (Welch+Dimson and `beta_60m`, as v4's
    optimizer holds several betas). Tier-1 slack.
  - Value, momentum, profitability and investment bands tightened from 1.0 to 0.25 of
    the risk-unit width, the size band's width. Tier-2 slack.
  - Sectors unchanged at 1%.
- **Gate HB (replaces G3a and G3b):** realised book beta (daily OLS on the S&P 500) over the
  four windows' pooled sessions. Its 90% 5-day-block bootstrap interval must lie inside
  [−0.10, 0.10]. Per-window values are reported, with the sell-off windows W18 and W20
  shown separately.
- **Paired directions (roadmap §2.3), reported, not a gate:** on the same frozen weights,
  for the long leg, short leg, book and the adverse direction (top-minus-bottom
  predicted-beta quintile of the candidates):
  - realised minus predicted beta under B1 and under B0;
  - signed and absolute error, squared hedge loss, intervals, effective dates.
- **Variance (roadmap §2.4), reported, not a gate:** realised/predicted vol for the book
  and both legs under four models (factor model, diagonal, single index, Ledoit–Wolf
  single-index shrinkage on 252 prior sessions), calm (W17, W19) vs stressed (W18, W20).
- **Variants:** E6 × {betamatch, betamatch_s6} × {vw, ew}, and H-ref (D20 step C, legs
  scaled to B1 beta 0) × the same 4. Registry +8.
- **E6 gates:**
  - G1 at every formation of every window (D19 definition).
  - G2 pooled (D19 band).
  - HB.
  - G4 pooled, with D19's power rule.
  - G5 after 0c.
- **H-ref gates:** G1 (hard rules only, reported not repaired), G2 pooled, HB, G5 after 0c.
- No survivor: stop and report, with no new candidates without the user.
- Survivors: D19's "After the gates" applies.
- Separate-leg alpha tests (roadmap §3) are registered separately when the user decides.

**Amendment 1 (2026-10-26, after the first 0a run, synthetic data only).**
- **0a result.** HB with the 5-day circular block bootstrap has power 1.000, coverage
  0.853 / 0.848 and size 0.095 at |β| = 0.10. **Fails** (size > 5%).
- **0a passed.** Zero-fill bias −0.0000 / −0.0020. Stock-slope recovery 1.002 (sd 0.006).
- **0b passed.** E6 weights are unchanged (< 1e-6) when μ is scaled by 3.7, vw and ew.
  The full-window scale and kappa therefore cannot change an E6 book.
- **Fix rule, written before trying any alternative.** The HB interval method is the
  first of these that passes every 0a check:
  - (1) a bootstrap that resamples 5-day blocks within each window, preserving the
    calm/stress mix;
  - (2) the OLS slope with HC3 standard errors and a t(n−2) interval;
  - (3) a wild bootstrap with Rademacher signs on 5-day blocks of residuals.
- **Monte Carlo noise.** The size check becomes ≤ 0.05 + 2 Monte Carlo standard errors
  (REPS = 1,000; ≤ 0.064). An exactly calibrated test would otherwise fail half the time.
  This loosens a threshold after a result. It is disclosed: the first method's 0.095
  fails either way.
- **If none passes:** stop and report.

**Amendment 1 outcome (synthetic only, `out/phase0a_modal2.log`): none passes; stopped.**
- strat: size 0.103, coverage 0.853 / 0.838.
- **hc3: size 0.070, coverage 0.897 / 0.891.**
- wild: size 0.104, coverage 0.851 / 0.835.
- All three: power 1.000, zero-fill bias +0.0001 / −0.0020.

HC3's intervals are calibrated. Its excess size matches the zero-fill bias at |β| = 0.10:
a −0.002 shift is about 0.17 SE, which takes a 5% tail to about 6.6%. The bootstraps
undercover by about 5 points. Consequence for D19–D20: their block-bootstrap intervals were
too narrow. The D20 step A failures sit far outside the band (W18/W20 slopes ≤ 0.58;
W17 B0 1.76 [1.43, 2.11]), so they stand. The stock-level slope interval itself was not
coverage-tested. Phase 1 waits for the user.

**Amendment 2 (user, 2026-10-26: "Ok bro do it"; written before the re-run).**
- **Interval:** HB uses HC3 + t(n−2).
- **Missing returns:** explicit (roadmap §1.2), no zero-fill. A day's leg return is the
  observed names' P&L scaled by leg weight / observed leg weight. D19's G2 series and the
  Phase 1 diagnostics use the same rule. Each day's unobserved weight share is reported.
- **Order:** 0a re-runs with exactly the Amendment 1 checks (size ≤ 0.064, coverage
  [0.85, 0.95], bias < 0.01, power ≥ 0.80). If it passes, Phase 1 runs as registered.
  If it fails, stop.
- **Phase 1 implementation:**
  - B4 and B5 enter as tier-1 slack bands at 0.05 (`policy.beta_bands_extra`).
  - Style bands at 0.25 (`policy.style_band_share`).
  - Configs `variant_e6_<score>_hb.json`: `beta_calibration` off, `beta_source` engine.
  - G5 waits for 0c (execution audit), as registered.

**Amendment 2 outcome.**
- **0a re-run passed (HC3 with per-leg missing returns):** power 1.000, size 0.056,
  coverage 0.897 / 0.883, bias 0.0000.
- **Phase 1 (`out/hbeta_gates/hbeta_gates.json`, `out/hbeta_modal.log`): no survivor
  before G5; stopped.**

| Variant | G1 | HB pooled beta (90% CI) | G2 book / long / short, CI upper | G4 E6 vs ref vol |
|---|---|---|---|---|
| E6 betamatch vw | fail (W17 Jan gross 1.5) | −0.019 (−0.066, +0.029) ✓ | 1.21 / 1.47 / **1.506** | 3.9% vs 4.8%, p 0.001 ✓ |
| E6 betamatch ew | ✓ | +0.008 (−0.028, +0.043) ✓ | 1.19 / **1.502** / **1.505** | 3.6% vs 4.3% ✓ |
| E6 betamatch_s6 vw | ✓ | +0.002 (−0.036, +0.040) ✓ | 1.29 / **1.507** / 1.49 | 4.0% vs 5.7% ✓ |
| E6 betamatch_s6 ew | ✓ | +0.024 (−0.009, +0.056) ✓ | 1.29 / **1.552** / 1.50 | 3.9% vs 4.8% ✓ |
| H-ref betamatch vw | fail (sector one-sided) | +0.060 (+0.024, +0.096) ✓ | 1.15 / **1.60** / 1.41 | — |
| H-ref betamatch ew | ✓ | +0.076 (+0.041, **+0.110**) ✗ | 1.11 / **1.54** / 1.38 | — |
| H-ref betamatch_s6 vw | ✓ | +0.060 (+0.022, +0.099) ✓ | 1.19 / **1.60** / 1.41 | — |
| H-ref betamatch_s6 ew | ✓ | +0.069 (+0.035, **+0.103**) ✗ | 1.18 / **1.53** / 1.39 | — |

- **What H-β fixed.** Every E6 book's pooled realised beta is within ±0.07, including the
  Feb 2018 and Feb 2020 sell-offs. The W17 window alone still shows +0.13..+0.19 with
  wide CIs. Step 2 cuts realised vol 15–30% against the paper reference, powered
  (expected t −4.9 to −8.6).
- **What fails.** Leg risk. The factor model's leg vol ratio is 0.71–0.75 in calm windows
  (overpredicts) and 1.74–1.90 in sell-offs (underpredicts). Ledoit–Wolf (0.79–0.83 /
  1.72–1.82) and single index (1.15–1.37 / 1.78–1.90) do no better; diagonal is 4.4–8.3.
  The miss is the market-variance level in regime changes, not the cross-section. Book
  risk passes everywhere (calm 0.95–1.10, stressed 1.06–1.29). The E6 failures are
  narrow (CI upper 1.502–1.552 vs 1.50) but count, per the rule.
- **Beta directions.** Realised leg betas are ≈ 0.86 against predicted ≈ 1.0 (B1) or 1.05
  (B0). B1 has lower leg MAE and squared hedge loss than B0 in every E6 variant.
- **Adverse top-minus-bottom quintile.** Realised +0.32 against B1 +0.63 and B0 +0.41.
  B1 matches in calm windows (W17 0.71–0.89 vs 0.67; W19 0.52–0.60 vs 0.55). Betas
  compress in sell-offs (W18 0.15–0.40, W20 0.32–0.33) and B0's shrinkage happens to fit
  them better.

Registry +8. No new candidates without the user.

## D20 — Fix the beta forecast first, then regate E6 and the plain decile sort on four short windows (2026-10-26)

**Decision (user, 2026-10-26, answering the D19 outcome).** "1. yes, you could take from
v4 latest commits on github": fix beta first. "2. yes": more gate windows for E6.
"3. yes": the plain decile sort is a hypothesis of its own. Written before any of it ran.

**Windows.** W17, W18, W19, W20: the first two months of each year 2017–2020. Formations
are Dec 31 and Jan 31, held to the end of February, as D19's W. W17 is already seen (D19).
W20 contains the start of the Feb 2020 sell-off. These are disclosed looks at 2017–2020.

**Step A — beta gate (G3a on all four windows).** Candidates, all known at formation:
- B0: engine hedge beta, calibrated (today's `snap["beta"]`).
- B1: engine hedge beta, uncalibrated (Vasicek 252d, 50/50 with `beta_60m`).
- B2: Welch slope-winsorised beta, 252 sessions, half-life 126 (v4 `fiam/v4/betas.py`,
  commit 67e39da).
- B3: Dimson beta, 126 sessions, one lag and one lead (v4).
- B4: panel `beta_60m`.
- B5: the mean of B2 and B3.

B2/B3 are estimated on CRSP total excess returns against the Fama–French market excess, as
the engine does. Realised beta is daily OLS on the S&P 500 over the window, the D19
measure. Test per candidate and window: across the first formation's candidates, the 95%
5-day-block-bootstrap interval of the realised-on-predicted slope lies inside [0.5, 1.5].
A candidate passes only if all four windows pass. Pick: the passer with the smallest mean
|slope − 1|. No passer: stop and report, with no further candidates without the user.
Registry +6.

**Step B — regate E6 with the picked beta.** It replaces `snap["beta"]` and the market
column of B, and the calibration map is not applied on top. Variants: betamatch and
betamatch_s6 × vw/ew (G0 passers). G1 must pass in every formation of every window. G2,
G3b and G4 pool the four windows' sessions (~150), with D19's margins and power rule. G5:
Nautilus smoke on W17. Registry +4.

**Step C — the plain decile sort (H-ref).** The HHRZ reference book alone: strict D9 long,
D0 short, vw or ew, gross 1.8. The legs are rescaled so that the picked beta's book beta
is 0 at the same gross (no optimiser). Gates: G1 (hard rules; it may fail names or name
cap, which is reported, not repaired), G2 and G3b pooled, G5 on W17. Registry +4.

**After.** Only a variant passing every gate in B or C earns the full 2017–2020 window:
the sealed D18 screen for E6, a new run for H-ref. 2021+ follows only per D18.

**Step A outcome (2026-10-26, `out/beta_gates/beta_gates.json` on the volume,
`out/beta_gates_modal.log`): no candidate passes all four windows; stopped per the rule.**
Realised-on-predicted slope (95% CI inside [0.5, 1.5] = pass):

| | W17 | W18 | W19 | W20 | mean abs(slope − 1) |
|---|---:|---:|---:|---:|---:|
| B0 engine, calibrated | 1.76 | 0.43 | 1.38 | 0.58 | 0.53 |
| B1 engine, uncalibrated | **1.11** | 0.28 | **0.89** | 0.40 | 0.38 |
| B2 Welch | 1.61 | 0.32 | 1.21 | 0.52 | 0.50 |
| B3 Dimson | 0.54 | 0.08 | **0.68** | 0.18 | 0.63 |
| B4 beta_60m | **0.77** | 0.17 | 0.48 | 0.26 | 0.58 |
| B5 Welch+Dimson | **1.00** | 0.16 | **0.96** | 0.32 | 0.39 |

Bold = passed that window. In the calm windows (W17, W19), B1 and B5 are calibrated, and
the calibration map (b ≈ 0.63–0.69) overcompresses B0 (1.76, 1.38). In the two sell-off
windows (Feb 2018, Feb 2020) every candidate fails: realised betas compress (slopes
0.08–0.58, mean realised 0.88–0.96 against predicted 1.1–1.4), which no trailing estimator
foresees. Rank correlation is 0.2–0.7 everywhere. The W17 E6 books were dollar-neutral at
both formations (net 0.000; weights read from the sealed targets, no returns), so their
+0.16..+0.23 realised beta is not a slope effect, which would cancel at net 0 and
predicted beta 0. It is name-level beta error lined up with the long/short selection.
Registry +6. Steps B and C wait for the user.

## D19 — Earn the window: short-window gates before any full-window or OOS run (2026-10-26)

**Decision (user, 2026-10-26: "If the tests are not statistically significant for each
hypothesis you can forget running for the whole window or even less oos. You must earn
it. Tests must be done in a short window like one or two months so that the models and
optimizers we're designing are structurally sound and not some Frankenstein").** Written
before any gate ran. Applies to E6 now and to every later construction.

**State when written.** The D18 screen ran its 8 books over 2016-12..2020-11 on Modal
before this instruction. It was stopped before its summary: per-variant targets and logs
sit on the volume (`out/twostep_screen/`), no return or cost was computed or read. Seen:
the per-formation lines (names, gross, predicted vol, ρ) and at least 12 formations that found no
E6 solve (all raw/raw_s6). Those targets stay sealed unless a variant passes every gate.

**Window W.** The first two D18 formations (2016-12-31, 2017-01-31). Each book is held,
drifting daily, from the session after its signal day to the next signal day; the second
to 2017-02-28 (~37 sessions). Market = S&P 500 (`data/benchmarks/SP500.csv`, as Nautilus).
This is a disclosed look at Jan–Feb 2017 of the validation window.

**Gates.** A variant (score, weighting) runs on the full window only if it passes all of them.
- **G0 signal (existing evidence, no new look).** The score's frozen walk-forward
  calibration slope (Elasso_MaInf, 48 months 2016-12..2020-11, 3-month block bootstrap) has
  lo90 > 0 (one-sided p < 0.05). raw: slope t = 0.53, lo90 −0.081, **fails**. raw_s6:
  t = −0.06, **fails**. betamatch: t = 3.44, lo90 +0.0063, passes. betamatch_s6: t = 2.61,
  lo90 +0.0043, passes. raw and raw_s6 leave E6.
- **G1 structure (mechanical, both formations).** First rung solves (ρ = 0.9, gross 1.8)
  with status `optimal`, not `optimal_inaccurate`; beta slack ≤ 1e-6; μ'w ≥ 0.9 μ'w_ref;
  200 ≤ names ≤ 500; max |w| ≤ 0.05; gross ≤ 2.0; |net| ≤ 0.5; short gross ≥ 0.5
  ($500m at $1bn); both sides in every sector; the union fits.
- **G2 risk forecast is calibrated.** For the book, the long leg and the short leg:
  s = sd of daily returns divided by the predicted daily vol (`risk.model.vol`/√252,
  that formation's). The 90% chi-square interval for s lies inside [2/3, 3/2].
- **G3 beta forecast works.** (a) Across the first formation's candidates, the slope of
  realised W beta on predicted beta: its 95% day-block-bootstrap interval (5-day blocks,
  1,000 draws, seed 42) lies inside [0.5, 1.5]. (b) The book's realised beta on W: 90%
  bootstrap interval inside [−0.2, 0.2].
- **G4 step 2 earns its place.** Daily realised variance of E6 is lower than (i) the HHRZ
  reference book (strict D9/D0, same weighting and gross) and (ii) that reference hedged
  with the S&P 500 at its predicted beta. One-sided Pitman–Morgan p < 0.05 for each.
- **G5 execution.** Nautilus E6 smoke over W (`--months 2`): zero hard-rule breaches on
  executed holdings (names, name cap, gross, net, short floor).

**Power.** Each statistical gate reports its ex-ante interval half-width on W from the
risk model's predicted vols. A gate whose half-width is wider than its margin cannot pass:
it is reported as underpowered and counts as a fail. W is not lengthened or moved without
the user.

**After the gates.** No survivor: stop and report. Survivors only: the sealed D18 summary
is computed among them, then the D18 Nautilus rule, then (per D18) one disclosed 2021–2026
run. Registry +4 (2 scores × 2 weightings on W).

**Outcome (2026-10-26, `out/e6_gates/gates.json` on the volume, `out/e6_gates_modal.log`):
no survivor. E6 does not run on the full window; the D18 screen stays sealed.**
- G0: raw and raw_s6 out (above).
- G1: passes, except betamatch/vw at 2017-01-31 (needed the gross rung 1.5; 286 names).
- G2: book calibrated (s 0.95–1.05, powered). Legs fail: s 0.56–0.67, so leg vol is
  overpredicted ~1.6× in calm Jan–Feb 2017; the book passes only because leg errors cancel.
- G3a: **fails, common to every variant.** Realised-on-predicted beta slope 1.76 (95% CI
  1.43–2.11, 2,003 names). Predicted betas are far too compressed.
- G3b: fails. Book realised beta +0.16 to +0.23 (90% CIs about ±0.13; three of four
  exclude 0) against a predicted ≈ 0.
- G4: E6 realised vol was lower than the HHRZ reference in all four (3.3–3.7% vs 3.9–4.2%;
  betamatch/ew p = 0.017 raw, 0.008 hedged). But the gate was underpowered ex ante
  (expected t ≈ −1.5 vs −1.69 needed), so it fails by rule. The betamatch reference is
  already near beta-neutral (predicted −0.06 to +0.02), which leaves step 2 little to remove.

## D18 — Two-step construction E6: select by expected return, then reweight for risk at a return floor; rule fixed before any E6 number (2026-10-26)

**Decision (user, 2026-10-26: "first a screen to maximize returns and select positions
AND THEN another step that minimize vol and forecasted beta (using the same forecasted
market and returns) by tweaking weights but somehow while maximizing returns"; "the
paper I gave you concerning e-lasso was a good starting point").** Written before any
E6 book, screen or formation was computed.

1. **Step 1, selection (return only)** = HHRZ 2018 §2.5 spread portfolio
   (`external/fm_appendix/HHRZ_2018_wp.txt` lines 1076–1085), inside the engine's
   eligible pool (candidates with a position cap >= the minimum size; shorts need
   min(me, me_company) >= $500m). Long = top decile, short = bottom decile. `vw`:
   breakpoints from NYSE names (`crsp_nyse`), reference weights by `me`; `ew`: names
   below the NYSE 20th percentile of `me` dropped, breakpoints from all remaining
   names, equal reference weights. Hysteresis: a held name stays while it is in the
   top (long) / bottom (short) two deciles. New entries are trimmed (least extreme
   first) so held ∪ target <= 490 (D15's union room). Signs are fixed by the decile.
2. **Step 2, weights (risk, return held).** On the fixed set with fixed signs, minimise
   (γ/2) w'Σw + λ_β(β'w)² + trading costs + borrow (+ E5's uncertainty and
   direction-aware jump variance), subject to μ'w >= ρ μ'w_ref, side'w = G, every
   engine band (sector, beta, size, styles with their slacks; net <= 0.5 hard;
   policy position cap 1%, minimum size 0.1%). w_ref = the step-1 decile weights (top
   and bottom decile only), G/2 a side, clipped to the caps. Σ, β, μ, costs = the
   engine's: enhanced risk model with beta calibration, the forecaster run's centred
   μ (the floor is invariant to μ's scale, so no calibration slope enters step 2), the
   per-name spread/impact/fee/borrow model. Fixed by judgement: ρ = 0.9 (if the floor is
   infeasible, ρ steps 0.75, 0.5, 0 and the step is logged), γ = `risk_aversion` (20,
   E3's risk price), λ_β = 10, G = 1.8, then G scaled down if predicted vol > 12%
   (v4's level; the gross cap is expected to bind first).
3. **Variants (fast screen, `research/twostep_screen.py`, formations 2016-12..2020-11
   only).** Score ∈ {`raw` (the paper's: walk-forward E-LASSO MaInf, all-name training,
   `walkforward/month`), `betamatch` (the D17 winner's input)} × smoothing ∈ {1, 6}
   months (mean of the month-centred score over the last k formations, past only) ×
   weighting ∈ {`vw`, `ew`} = 8. Disclosed: 6-month smoothing was the best setting of
   the in-sample 2021–2026 screen (`stage2_el`, D17), so it is a post-2021-informed
   candidate. Targets from the engine's formation inputs; returns and per-name costs by
   `stage2.simulate`. **Screen pick:** highest net Sharpe among variants with |beta| <=
   0.05 and both legs' after-beta alpha > 0, else highest net Sharpe.
4. **Book rule.** The pick runs as the Nautilus E6 book on Modal, 2017–2020. E6 is
   adopted over the D17 winner (all-name betamatch E5, +6.5%/yr net) iff its net annual
   return is higher with |daily beta| <= 0.05 and both legs' after-beta alpha > 0
   (`research/legs_report.py`). If adopted, E6 gets one 2021–2026 run, disclosed under
   D16. If not, nothing runs on 2021–2026 without the user.
5. **What it can and cannot do (stated before running).** Step 2 lowers vol and beta at
   a given expected return; it cannot create alpha the selected names lack. On
   2021–2026 the extreme deciles reverted (lesson 98), and the paper's sort buys the
   extremes, so a good 2017–2020 result does not imply 2021–2026.

**Registry.** +8 (screen variants) +1 (the E6 book).

**Amendment 1 (2026-10-26, after a 2-formation feasibility smoke on Modal, before any
return was computed: the smoke's summary step crashed before scoring).** (a) The code had
copied the engine's dollar-neutral tolerance (|net| <= 1e-6) into E6, against item 2's
"net <= 0.5 hard": every `raw` solve was optimal but rejected, because the raw score loads
−0.6 on beta (lesson 96c) and a beta-neutral raw book must be net long. E6 now holds net
by the hard ±0.5 band (the penalty still pulls it to 0 where free) and beta by its band.
(b) The global decile sort left whole sectors one-sided (betamatch: 8–11% net in a
sector, against the 1% band), lesson 45's failure again; lesson 16: sector bets are
unusable in a neutral book. Deciles are now formed **within each sector** with that
sector's NYSE breakpoints (`ew`: its non-micro names), the industry-neutral version of
the HHRZ sort. A sector with < 10 reference names uses all its names. Nothing else
changes; the variants, rule and registry stand.

**Enforced in** `engine/optimize.py` (`two_step_book`, `solve_qp(floor=...)`),
`engine/ladder.py` (step E6), `elasso/variants.py` (smoothed inputs),
`research/twostep_screen.py`, `config/variant_e6_*.json`.

## D17 — Clean build on the holdable-trained forecaster; book race fixed before any book ran (2026-10-26)

**Decision (user, 2026-10-26: "clean, then tune to bat 12.8").** Two stages, kept apart:

1. **Clean (this decision).** Forecaster = the holdable-trained monthly walk-forward
   (`walkforward/month_holdable`, adopted by the `research/holdable_compare.py` rule,
   lesson 98). Three book inputs from it, built and calibrated on formations
   2016-12..2020-11 only by `elasso/variants.py --base month_holdable`: `raw` (the
   walk-forward score), `volneut` (ranked within ivol terciles), `betamatch` (ranked
   within beta_60m quintiles). Each runs the E5 book on 2017–2020
   (`config/variant_h_<name>.json`). The previous race winner (betamatch on the
   all-name training, net 6.6%/yr) races with them. **Rule:** the winner is the
   highest net annual return among books with |daily beta| <= 0.05 and both legs'
   after-beta alpha > 0 (`research/legs_report.py`), else the highest net return. The
   winner alone gets one 2021–2026 run, disclosed under D16. Registry +3.
2. **Tuning to beat v4's 12.8%/yr (later, separate).** Any choice made on 2021–2026
   returns makes that window in-sample. Its result is reported as in-sample, beside the
   clean result, never in place of it. v4's 12.8% is also an in-sample number: its 12
   signals and limits were chosen with 2021–2026 visible (`fiam/book.py`), and its
   composite has IC +0.001 on 2017–2020 in the holdable pool.

**Race result (2017–2020, `out/race_d17.json`).** All four books qualify (|beta| <= 0.05,
both legs' alpha > 0). Net %/yr: all-name betamatch +6.5 (winner), holdable volneut
+6.2, holdable betamatch +6.0, holdable raw +4.4 (gross only 0.66: the raw score's
calibration slope interval spans 0). Holdable training wins on the forecast tests
(lesson 98) but not in the book, so the winner is `config/variant_betamatch.json`; its
one 2021–2026 run is `out/nautilus_d17_oos` (the stopped run of lesson 97 was the same
config, seen to 2022-08; disclosed under D16).

**Clean 2021–2026 result (single run, `out/nautilus_d17_oos`).** $1bn → $906m: −1.7%/yr,
vol 5.0%, beta +0.012, max DD −17.6%, net IR −1.78 against TB3MS+4%. Long leg alpha
−3.6%/yr (t −1.3), short leg +0.6% (t 0.2); return before costs +1.7%/yr, costs
3.3%/yr (impact 2.5). By year: −5.9, −11.0, +4.3, +0.0, −4.7, +8.9 (2026 to Aug). Avg
382 names, gross 1.79, no gross breaches; 7,495 liquidation-capacity rows. The
2017–2020 edge did not carry into 2021–2026 for this forecaster. This is the clean
result and is reported as such beside any stage-2 number.

**Stage 2 screen (IN-SAMPLE, `research/stage2.py`, `out/elasso/walkforward/stage2.json`;
registry +30).** Fast monthly simulator, 2021–2026, both pools, top/bottom 100/150/200
names, blends of E-LASSO and v4's 12-signal composite. v4's composite alone: +9.5 to
+10.8%/yr excess of cash (≈ v4's 12.8% total with cash), short alpha +15–18% (t 2.7–2.8),
long +2% (t 0.9). Every step toward E-LASSO lowers it, monotonically, in both pools
(E-LASSO alone −2.2 to +0.6%). Realised beta is −0.2 to −0.5 although the gross split
is beta-0 ex ante on beta_60m (the screen is a diagnostic, not a book). On 2021–2026
the return is in v4's signals, not in E-LASSO.

**Stage 2, E-LASSO kept (user chose "Keep E-LASSO, tune construction"; IN-SAMPLE,
`research/stage2_el.py`, registry +72).** Costs revised to the engine's per-name
model (user: "revise cost too"): half-spread from v4's quoted/high-low ratios,
sqrt impact Y = 1 over 5 days, fees, borrow. Grid: pool x transform x smoothing
(1/3/6 months) x names (150/250) x rolling beta hedge. Best: holdable pool, raw score,
6-month smoothing, 250 a side, rolling hedge: +2.0%/yr over cash (≈ +5% total), beta
+0.01, long alpha −2.1% (t −0.7), short +7.9% (t 1.8), turnover 7.4x, costs 3.8%/yr.
Under the same costs v4's composite makes +7–8%/yr over cash in this screen: E-LASSO's
rank changes month to month (autocorrelation 0.77 vs 0.93) cost more than its short-leg
alpha earns, and its long leg has none on 2021–2026. No construction setting brings
E-LASSO near 12.8%, even fitted in-sample.

## D16 — The 2021–2026 window stays presentable: no tuning on it (2026-10-26)

**Decision (user, 2026-10-26: "no i want to keep 2021-now window prresentable").**
Nothing is chosen, tuned or adjusted on 2021–2026 returns from here on; changes are
judged on 2017–2020 only, then 2021–2026 is run as a single disclosed look.

**Disclosed looks at 2021–2026 so far (all must be listed with any 2021–2026 result):**
D11/D12 (rolling and tail forecasts), the E5 single run (lesson 95), the cause analysis
(lessons 96–98: forecast diagnostics, beta-matched and holdable decile checks), the
stopped beta-matched book (lessons 97, NAV seen to 2022-08), and `research/tune_oos.py`
(144 configs on 2021–2024, two on 2025–2026; nothing adopted). Registry +144 for the
grid.

## D15 — Walk-forward E-LASSO, beta calibration on, 440-name formation ceiling (2026-10-26)

**Decisions (user, 2026-10-26).**
1. **Walk-forward forecaster** ("the weights of models have to be refit in every year
   and for backtest latest refit model have to be used"; then "if better lets do a
   monthly re fit walk forward"). `elasso/walkforward.py`: at each month-end r
   (2016-12..2026-07) the corrected port is refit on training rows dated <= r only;
   the frozen weights (S-LASSO MaInf mean, C-LASSO univariate coefficients and
   selection, encompassing weight) forecast the next formation from that eom's
   characteristics. Forecast rows need no future label (`oos.features`), so names
   that later delist stay in. All 116 refits' weights: `out/elasso/walkforward/
   month/weights.parquet`. Score = volneut of it; scale and kappa frozen by
   `tail.calibrate` on formations 2016-12..2020-11 (scale 0.0077, IC21 0.027).
   The yearly refit was tried first (`--every year`, fits kept in `walkforward/year`):
   validation IC21 0.013 and a calibration slope whose 90% interval spans 0. The
   frozen model drifts within a year (rank corr with the monthly model 1.00 in
   January, ~0.8 later), so monthly was adopted. Registry +1 (the yearly trial).
   Tests: `tests/test_walkforward.py` (a refit does not move when anything after r
   changes; a forecast does not read its own month's return).
2. **Beta calibration on** ("I think it's a good thing to keep beta low so keep"):
   `policy.beta_calibration = true`, overriding the D14 rule result (3 of 6 books).
3. **Name ceiling** (user "Yes" to ~440): `optimize.NAMES_HEADROOM = 60`, and under
   the gross cap a book whose union with held names fits always beats one that does
   not (the 2017-2020 E5 run had picked non-fitting books: ~630 names on rebalance
   days, 202 breach days).

**Enforced in** `config/final_2026.json`, `engine/mandate.py`, `engine/optimize.py`,
`elasso/walkforward.py`, tests `test_walkforward.py`, `test_forecaster.py`.

## D14 — Short leg rebuilt: volneut forecast, short-interest borrow, enhanced risk model, E5 objective (2026-10-26)

**Decisions.**
1. **Borrow** (user: "Same borrow fee modelling as the papers suggest and like we did
   in v4 and Quarcc black"): short-interest tiers 0.30/1/3/8% (D'Avolio 2002,
   Drechsler & Drechsler 2016; v4 `fiam/costs.py`), `engine/borrow.py`,
   `policy.borrow_schedule = "short_interest"`. Short interest is the WRDS research
   layer, outside the competition pack (disclosed). The flat 0.5%/5% stays selectable
   (`"flat"`) and is reported beside it (case §7). Evidence: lessons 82–83.
2. **Forecast = volneut** (pre-registered rule, `research/short_side/vol_fix.py`):
   resrank E-LASSO ranked within ivol terciles. Evidence: lessons 85–87. Scales and
   kappas frozen by `elasso/tail.calibrate` on 2016-12..2020-11
   (`out/elasso/gpu/volneut/run/frozen.json`). Registry +2 trials (volneut, exhivol).
3. **Risk model = enhanced** (user: "our risk models MUST be very accurate"):
   volatility regime adjustment + 5 residual PCA factors, both adopted by the rule in
   `risk/accuracy.py` on all six books (lesson 88). The beta calibration
   (`risk/beta_cal.py`) fixes the vol-tilted book's beta bias (+0.149 → +0.044) but
   failed the rule as written (3 of 6 books) and is off pending the user (lesson 90).
4. **E5 objective** (user: "it must minimize volatility, minimize beta and maximize
   return subject to wtv"): max μ'w − costs − borrow − λ_β(β'w)² with direction-aware
   jump variance in the risk term, predicted vol ≤ `vol_target` (6%), gross ≤ 1.8;
   stage-0 support keeps E3 settings; support size chosen on the objective
   (lessons 91–92). λ_β = 10, vol target 6%, γ = 2, jump sizes 0.32/0.28 are stated
   judgements set without looking at returns. E3/E4 stay in the ladder unchanged.

**Registry.** +7 return-judged trials on top of the D12 count: the D13 label
tournament (resrank, tail20, restail, blend; `research/short_side/tournament.py`),
the vol fix (volneut, exhivol; `vol_fix.py`) and the E5 book on 2017–2020. The risk
variants (vra, pca, vra+pca, betacal) were judged on predicted-vs-realised vol and
beta, never on returns, and are listed in `risk/accuracy.py` but not counted.

**Validation run.** The E5 2017–2020 Nautilus book runs on Modal
(`gpu/modal_book.py`, 8 CPU / 64 GB; the local 15 GB box was reaped mid-run).
Inputs sit in the user's private volume `fiam-v4b` under `/repo`; the image
carries v4b code only and the run refuses to start if any parquet is baked in.

**Enforced in** `config/final_2026.json` (policy), `engine/mandate.py` (checks),
`engine/optimize.py`, `engine/ladder.py`, `engine/borrow.py`, `risk/enhanced.py`,
tests `test_optimize.py` (E5 cases).

## D13 — E-LASSO ported to compiled Python; authors' C-LASSO assignment defect corrected (2026-10-26)

**Decision (user, 2026-10-26: "port e-lasso to cuda enabled python libraires";
"just correct the bug right now instead of porting it over").**

1. **The forecaster runs from `gpu/elasso.py`** (glmnet's `standard` + `elnet1`
   covariance path in `gpu/glmnet.py`, numba on CPU, numba.cuda on GPU; one
   problem per month, all months at once). Proof (`gpu/verify.py`,
   `out/gpu/verify_{ret,up,down}.json`): against the authors' R runs on all
   139 months, max |Δ| coefLasso 2.4e-11, forecastSlasso 9.6e-11,
   forecastClasso 3.2e-14, coefEncompass 9.2e-14, forecastElasso 3.0e-12; no
   unmatched rows, no NA mismatches. C-LASSO weights (coefGr) have the same
   support in every month; their magnitudes differ by 1–3% in a few
   ill-conditioned months (weights 30–150), which no forecast uses. 14 s per
   label on 4 CPU cores against ≈12 min in R.
2. **Defect corrected.** `programForecastClasso.R` assigns
   `tCoefGr[tIndex] = tCoef[-1]` after `tCoef = as.numeric(tCoef[-1])`: the
   first slope is dropped twice and R recycles the shorter vector, so each
   characteristic's C-LASSO selection is its neighbour's. The port keeps each
   slope with its own characteristic. The R files stay byte for byte in
   `external/elasso/`; the R-compatible assignment exists only in
   `gpu/verify.py` to prove the rest of the port. Every forecast after D13 is
   from the corrected code; earlier R forecasts (D10–D12) carry the defect.
3. **Disclosure.** The correction changes 2021–2026 forecasts already
   examined under D11; it is a code fix, not a selection, and enters the
   registry as such.

**Enforced in:** `gpu/elasso.py`, `gpu/glmnet.py`, `gpu/verify.py`.

## D12 — Engine build: tail forecaster, dated fees, stale settlement, jump budgets (2026-10-25)

**Decision (user, 2026-10-25: "1. yes" [tail primary]; "idc about turnover as long
as we optimize with number of transacrion by taking into account feees"; "adopting
more Value at risk style risk metrics like the oppostive-direction incertainty
interval"; "yes, go").**

1. **Forecaster = rolling tail score.** `policy.forecaster_run =
   out/elasso/rolling/tail`: `Elasso_MaInf` there is MaInf(up) − MaInf(down)
   (`elasso/tail.py`); Ma1 likewise as alternate. The D11 pre-registered rule
   kept the mean model on validation; the user chose the tail score after the
   2021+ judge (rolling tail OOS IC +0.047, t 4.32). **Disclosed as a post-2021
   choice**; registry +1 trial. Calibration is D7's method on 2016-12..2020-11
   only: centred MZ slope on y21 = 0.0511 (se 0.045), alpha kappa 0.0237 per
   session (90% CI excludes 0 barely); Ma1 slope 0.0066 (no signal).
   `out/elasso/rolling/tail/frozen.json`, copied into config.
2. **Fees = dated schedule.** `engine/fees.py` (IBKR Pro fixed $0.005/share,
   $1 min, 1% max; SEC 27.80e-6 on sales; FINRA TAF $0.000195/share capped
   $9.79; CAT $0.000003/share; schedule dated 2026-09-30, copied from
   `fiam/costs.py` with sources). The optimizer charges the convex per-dollar
   part in the objective and in support entry/exit costs; the backend charges
   each order exactly on actual (raw-close) shares. No turnover cap: trades
   happen when forecast gain beats spread + impact + fees + borrow. Flat
   borrow 0.5%/5% stays (Final case §7 alternative) and is reported.
3. **Stale quotes settle at the last mark.** A position unquoted for
   `stub_days` (5) sessions is closed at its last mark with half-spread and
   fees, both sides. The previous backend froze them forever: by 2020 they
   were 0.18 gross / +0.05 net / 35 names, the bulk of the gross, net, beta,
   names and liquidation breaches (LESSONS 66).
4. **Jump budgets (E4).** Direction-aware, scale-free, from out-of-sample
   jump probabilities (`risk/jumps.py`, annual expanding refits):
   short cap × min(1, mean p_up / p_up_i); short-book weighted p_up ≤
   `jump_short_ratio` (1.0) × pool mean; long-book weighted p_dn ≤
   `jump_long_ratio` (1.5) × pool mean. Ratios fixed by judgement from
   LESSONS 64–65 before any engine run; E4 is judged against E3 on
   2017–2020 only.
5. **Name headroom.** Support grows 250 → 300 → 350 → 490; a book is
   preferred only if its union with held names is ≤ 490, so execution
   overlap cannot cross 500.

**Enforced in:** `config/final_2026.json`, `elasso/tail.py`,
`elasso/forecaster.py`, `engine/fees.py`, `engine/optimize.py`,
`engine/nautilus_backend.py`, `engine/ladder.py` (E4),
`research/run_nautilus.py`.

## D11 — Rolling E-LASSO and left/right-tail E-LASSO; primary rule pre-registered (2026-10-25)

**Decision (user, 2026-10-25: "1. yes you may"; "2. same as in quarcc black (left
and right tail inside of e-lasso)").**

1. **The forecast process is the authors' rolling E-LASSO.** `elasso/oos.py`
   applied the 2020-12 coefficients to all 68 later months. E-LASSO is a
   Fama-MacBeth method: the row dated t pairs month-t returns with
   characteristics at eom t-1, and the forecast for t+1 averages coefficients
   through t. Re-estimating every month uses only returns realised by each
   formation, so it is the authors' real-time design, not an in-sample replay.
   Freezing it removed the monthly re-estimation credited for 2020 (LESSONS 25,
   31) and left C-LASSO on one month's selection for five and a half years. The
   D10 run stands as the record of that frozen variant. `elasso/rolling.py`
   runs the unchanged R code over 2015-02..2026-08 (cut 2026-08-31).
2. **Tail conditioning = QUARCC-Black dual head, inside E-LASSO.** Two more
   runs of the unchanged code with `ret` replaced by `up` = 1{return in the
   month's top decile} and `down` = 1{bottom decile} (Exp12 V6 C2 targets;
   Exp15 L1 `score = long - short`). Tail score = `Elasso_MaInf(up) -
   Elasso_MaInf(down)`. QUARCC found separate tail heads learn extremeness
   (corr(p_down, p_up) 0.987, Exp14 audit §1); the difference is the
   directional part, so the heads alone are diagnostics.
3. **Primary rule, fixed before any 2021+ number was computed.** On the
   validation formations (eom 2016-12..2020-11) only, the tail score replaces
   `mean_MaInf` as primary iff (a) its top-minus-bottom decile spread inside
   the ≥$500m pool is at least the mean model's, and (b) both legs are
   right-signed there: long D9 above and short D0 (≥$500m) below the month's
   mean. Otherwise `mean_MaInf` stays. Ma1 columns are diagnostics (D6: Ma1
   only on net IR in the engine).
4. **Disclosure.** 2021–2026 was already opened by the frozen run (D10). The
   rolling runs are a second look and enter the registry as two trials (rolling
   mean, tail score). No coefficient, label, window or threshold is chosen on
   2021+.

**Enforced in:** `elasso/rolling.py`, `elasso/rolling_judge.py`
(`out/elasso/rolling/judge_valid.json` before `judge_oos.json`).

## D10 — Frozen E-LASSO candidate rejected; 2021–2026 is diagnostic only (2026-10-24)

**Decision.** Do not promote the frozen 2020-12 E-LASSO candidate, do not
sign-flip it, and do not tune any model/band/cost on 2021+ returns. The
corrected 2021–2026 run is a one-shot diagnostic, not a final book.

**Evidence.** `OOS_RESULTS.md`; corrected native E3: net −35.83%, benchmark
+50.76%, net IR −2.28, costs 6.39%/yr. MaInf OOS rank IC −0.0328 (t −2.47);
2021 −0.0467, 2022 −0.0824, 2023 +0.0006, 2024 −0.0259, 2025 −0.0151,
2026 Jan–Jul −0.0245. The first OOS month was already negative (January 2021
IC −0.0373) and March 2021 was −0.2406. The prior-close-weight short leg lost in five of six years (−20.8% 2021, −20.5% 2023, −19.3% 2025); equal-weight Q0 short tail averaged +0.63%/month versus Q4 long tail −0.11%/month, so the loss was not merely an optimizer artefact. The two positive years, 2023 (+9.40%, active −0.02pp) and 2024 (+0.31%, active −9.07pp), delivered no positive active return; FF5 alpha is −12.1%/yr. E3 is noncompliant: max gross
2.479, 552.9 average names, 71,371 liquidation-days, 1,416/1,421 policy-breach
days, so `eligible_for_oos=false`.

**Data correction.** The first 2026 run used raw, non-split-adjusted
`dsf_mini` returns/closes. The corrected 2026 path is a split-adjusted
total-return index from panel `ret`; 2021–2025 is unchanged, 2026 Jan–Jul
improves from −14.08% to −8.72%, and Jan–Aug is −8.25%. The invalid run is
preserved and must not be cited.

**Next test.** A new hypothesis (monthly-refit E-LASSO, new signal, E4 daily
repair, or a regime overlay) needs a new pre-registered holdout, for example
2027+. Construction must satisfy names, gross, beta, sector and liquidation
limits before it is called a book.

## D9 — Monthly controller completed; no eligible book (2026-10-23)

**Result.** E0, E1, E2, the Ma1 trial and E3 each completed all 48
formations (2016-12..2020-11) at $1bn starting NAV with actual fills and
compounding. E3 net IR is -0.139, gross IR 0.583;
annualised active mean -0.75%. Construction with costs
improves IR over E2 by 1.710, but
**does not pass the process gate**. Executed E3 has 22 gross, 105 count,
1 short-floor and 1,913 liquidation-capacity breach rows, plus daily policy
exposure violations. The fallback also fails capacity/policy checks.
`ship` is null; final freeze and OOS remain blocked.

**Forecast and risk decisions unchanged.** D6–D8 still govern. Ma1 is not
promoted: the engine has no compliant comparison supporting replacement.
MaInf remains primary; this is not evidence that Ma1 can never win after
execution repairs. The risk model's 1.29–1.51 bias caveat remains attached.

**Implementation.** Stage 0 sees exposure bands; support scores subtract
constraint shadows; support expands before gross is reduced. E3 entry/exit
costs use return-per-dollar units and include impact. Target formation reads
executed holdings and NAV, with one horizon to the next monthly review.
Missing shorts remain liabilities, costs use observable inputs, and the
checker records actual trades and drifted books. IR confidence intervals
recompute IR on paired 21-session blocks; 2019 selects, 2020 confirms, and a
failed predecessor cannot be skipped. Reused validation is not a fresh holdout.

**Evidence.** `out/engine/ladder.json`, `manifest.json`,
`yearly_performance.csv`, `ledger_*.parquet`, `positions_*.parquet`,
`breaches_*.parquet`, `policy_*.parquet`, and target solver logs.
The manifest retains the construction identity and the reporting-only
float64 reconciliation correction; no targets or fills changed in that
refresh. All six daily books reconcile to monthly trade cohorts within
1.4e-15 return units. Tests: 71 v4b, 157 repository passing (3 skipped).

**Next.** E4: actual daily constraint repair and execution sequencing,
followed by the same net-performance/process gates. Do not loosen the
bands or call these diagnostic returns compliant finals performance.

## D8 — Risk model freeze (2026-10-23)

**Decision.** The risk model is `fiam/v4b/risk/` as specified in REVISED_PLAN §4:
assigned exposures (sectors exact, five style rank-z, market column = hedge
beta), daily Barra-identified WLS factor returns on the liquid universe,
EWMA factor covariance with Newey-West autocovariances and exact
H-session horizon scaling, correlation-stressed second covariance, and
specific variances shrunk 25% to sector medians with a 5th-percentile floor.
Hedge beta = 50% Vasicek-shrunk 252-session OLS (FF daily market) + 50%
panel 60-month beta, weekly refresh. Two predeclared selections, frozen
from `fiam/v4b/out/risk/report.json` (48 formations, eom 2016-12..2020-11):

| Choice | Frozen | Evidence |
|---|---|---|
| Factor EWMA half-life | 84 sessions | Pooled \|bias-1\| 0.80 vs 0.86 for 42 |
| Specific estimator | EWMA-168 on residuals | QLIKE 0.583 vs HAR 0.795; DM t +4.3 against HAR |

**HAR deviation, stated.** R§4 names the repo HAR winner for specifics. That
winner forecasts *total* vol; retargeted at residuals (the same design and
DM gate) it loses decisively, so EWMA-168 ships. Total-vol HAR inside D
would double-count factor variance and is not used.

**Known bias, not fitted away.** Predicted vol understates realised vol:
bias std(realised/predicted) = 1.29 (E-LASSO decile book, 80% factor share)
and 1.51 (fallback book, 88% specific share), band ±0.20. Diagnosis
(LESSONS 41-44): vol-regime lag plus residual co-movement in stress
(omitted-factor risk), not horizon arithmetic (iid scaling gives 1.22).
No vol-regime multiplier is fitted at this stage; it and any extra factor
are E-ladder upgrades judged on net IR. Ex-ante TE from this model must be
reported with the bias beside it.

**Beta arithmetic on data.** Nominal |beta| ≤ 0.02 stays the hard policy
band. Estimation SE on the decile book: median 0.021, robust bound
(1.65×SE) p90 = 0.052 - the ±0.02 *robust* band is infeasible, as eval 03
predicted (expected 0.05-0.07). The fallback book's SE is 0.007.

**Enforced in:** `fiam/v4b/risk/` (`exposures.py`, `beta.py`, `factors.py`,
`covariance.py`, `specific.py`, `model.py`, `validate.py`);
`model.FACTOR_HL = 84`; `tests/test_risk.py`; report at
`out/risk/report.json`. Registry: 77 trials (75 + 2 selections above).

## D7 — Forecaster freeze: centring, calibration, decay (2026-10-23)

**Decision.** The engine reads E-LASSO only as **centred, calibrated** expected
returns: `mu_tilde = scale * (mu - median_eom(mu))`, converted to the holding
horizon with the frozen decay rate (see `elasso/forecaster.py`:
`centred_returns`, `horizon_returns`). Raw `expected_returns` stays for
evaluation and audit only. Frozen numbers, estimated once by
`elasso/freeze.py` on the 48 held-out months (formation eom 2016-12..2020-11)
and copied into config (`out/elasso/frozen.json` is the evidence):

| Column | Scale (centred MZ slope on `y21`) | kappa /session | Half-life |
|---|---|---|---|
| MaInf (primary) | 0.547 (90% CI -0.016..1.180: weak) | 0.00524 | 132 sessions |
| Ma1 (alternate) | 0.590 (90% CI 0.264..0.877) | 0.0697 | 10 sessions |

**Why centred.** Raw forecasts are mostly a market-level intercept: monthly
medians swing -4%..+8% against ~0.5% cross-sectional dispersion, and the
levels Mincer-Zarnowitz slope for MaInf is -0.11 on the same window. A
dollar-neutral book earns only the dispersion. This corrects D6's wording
("after dividing by 100, scaled by the calibration slope"), which omitted
the centring R§3 already required. D6's cited slope of 1.22 is the authors'
full-window statistic, not our held-out centred slope.

**Burn-in.** Formations before eom 2016-12 average fewer than 21 monthly
regressions and are unstable (Ma1/MaInf rank correlation flips sign in
2015-09 and 2016-04). They may warm up holdings, never count as validation.

**H2 vintage lag (diagnostic, not adopted).** Rerunning the unchanged authors'
code with characteristics one month staler (`out/elasso/lag1.json`): MaInf
paired IC +0.0070 ± 0.0066 (unharmed), Ma1 -0.0211 ± 0.0162 (halved). The
shipped forecaster stays unlagged per D6; adopting the lag on this evidence
would be validation selection. The deck reports the lagged run as the
conservative vintage case. Registry: 75 trials (74 + this diagnostic).

**Enforced in:** `config/final_2026.json` → `policy.forecaster_scale`,
`forecaster_alternate_scale`, `forecaster_kappa`,
`forecaster_alternate_kappa`; `engine/mandate.py` range checks;
`elasso/forecaster.py` (only centred/horizon functions are engine-facing);
`tests/test_forecaster.py` (config must equal `frozen.json`).

## D6 — The forecaster is E-LASSO (2026-10-23, user: "yes please replace with E-Lasso")

**Decision.** The strategy's return forecaster is **E-LASSO** (Han, He, Rapach, Zhou,
*Cross-Sectional Expected Returns: New Fama-MacBeth Regressions in the Era of Machine
Learning*, Review of Finance 28(6), 2024). The primary forecast is the
**MaInf** column. **Ma1** is the one alternate variant; it is chosen over MaInf only on
**net IR at $1bn in the engine**, never on gross spread or IC. Choosing between them is
one registry trial.

**What it replaces.** The MLP (D2) is retired as the forecaster. The group/hierarchical
ridge, the 50/50 blend, the GBT and the 2-layer MLP stay only as reported comparison
baselines in `out/forecast/`.

**How it runs (do not denature).**
- The authors' R code (`elasso_06-16-2024.zip`) is kept byte for byte in
  `external/elasso/` and verified against `SHA256SUMS` before every run. It runs in R 4.4.3
  with glmnet 5.0 through `elasso/run_elasso.R`. Only inputs and outputs are ours.
- The input contract (`elasso/build_input.py`) follows the authors' data section
  (`external/fm_appendix/HHRZ_2018_wp.txt` §2.1):
  - each characteristic is winsorised at 1/99% within month, standardised to mean 0 and
    sd 1, and missing values set to 0;
  - the month-t return is matched to characteristics at t−1;
  - the WLS weight is `me` at t−1.
- Inputs used: our 147 characteristics, the tradable universe and `ret_exc_lead1m`.
- **Training label = `ret_exc_lead1m`, not `y21`.** `y21` ends one session into the next
  month, so month-t coefficients would see a day the book cannot trade. Evaluation still
  uses the earnable `y21`.
- **Cadence:** E-LASSO re-estimates every month by construction (Fama-MacBeth). The book
  is formed at the first session after each eom. Do not retrain on daily rows (lesson 33).
- **Magnitudes:** E-LASSO forecasts are in percent per month and are calibrated: the
  authors' Mincer-Zarnowitz slope is 1.22, s.e. ≈ 0.5. They feed the optimiser as
  expected returns after dividing by 100, scaled by the held-out calibration slope frozen
  before the run. No Grinold IC mapping is needed.
- **Holding:** MaInf earns into months 2–3 (lesson 32), so the controller uses no-trade
  bands and longer holding, not faster trading.

**Evidence** (`out/elasso/report.json`, `decay.json`; LESSONS 24–34). On the same 48
held-out months (2017–2020) as every other model:
- MaInf IC 0.031 (t 2.38) and short-eligible IC 0.034; MLP 0.023 and 0.015.
- Spread +0.86%/month; within-sector +0.42%.
- The only model positive in 2020 (+0.80%).
- Liquid-half IC 0.040 vs 0.023 in the illiquid half.
- Paired vs MLP: +0.53% ± 0.51% spread (1.0 SE).

**Known costs.**
- Style tilts (momentum +0.25, value −0.19) mean a neutral book keeps only part of the
  spread; factor α t is 1.14.
- Ma1 churns 70% of its top decile monthly.
- The smoothing windows are degenerate on 70 months.
- Registry: 74 trials on 2017–2020, and 2019–20 was seen three times. The deck carries
  the deflated-Sharpe haircut.

**Enforced in:**
- `config/final_2026.json` → `policy.forecaster` = `elasso`,
  `policy.forecaster_column` = `Elasso_MaInf`, `policy.forecaster_alternate` = `Elasso_Ma1`;
- `engine/mandate.py` checks those keys;
- `elasso/forecaster.py` is the only interface the engine reads forecasts from;
- REVISED_PLAN §§0, 1, 3, 8, 10, 11; CONTINUATION_PLAN A3/§4/§5; LESSONS 35; README.

## D5 — 2026 ADV fallback (2026-10-23, assistant on "idk")
CRSP daily dollar volume through 2025-12. From 2026: `dolvol_126d` lagged one month ×
a splice ratio frozen on 2015–2020. FINRA replaces it only if its agreement check passes
before the config freeze. REVISED_PLAN §2, §7.

## D4 — No Arcana upload before the single 2021–26 run (2026-10-23, user: "yes")
REVISED_PLAN §2 (Arcana bullet).

## D3 — Short floor checked on rebalance dates (2026-10-23, user: "only on rebalance")
At each rebalance every short needs `min(me, me_company) ≥ $500m`. Between rebalances
drift is held, and only trades that add to a short are re-checked. REVISED_PLAN §5,
`engine/checker.py`.

## D2 — MLP over GBT by the 1-SE rule (2026-10-23) — **superseded by D6**
User: "mlp or gbt whichever is better". The rule picked the MLP (fold 1: GBT − MLP IC
+0.0016 ± 0.0049).

## D1 — Ridge and the 50/50 blend dropped (2026-10-23)
The initial plan's hierarchical ridge, tested as written, fails its own promotion test:
df ≈ 0 and within-sector spread −0.40%. LESSONS 14–23.
