# Evaluation — Taildrop plan vs FINAL mandate (v4b synthesis)

> **Superseded on the forecaster (2026-10-23, D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md)).** This evaluation predates
> testing. Its forecaster verdicts (§4: ridge default / GBT challenger) were tested and
> retired (LESSONS 14–30). **The forecaster is E-LASSO.** Everything else stands as written.

**Overall grade: B as a research design, D as an executable specification. Verdict: KEEP WITH MAJOR FIXES.**
Do not rebuild the architecture. Do not run current repo code as a finals book.

**Single top finding:** the plan transcribes every hard mandate number correctly, but
no finals-compliant $1bn backtest exists and the machinery that would certify one
(validation gates, spread/capacity calibration, finals checker) is unspecified —
so as written the plan can produce a spectacular, untrustworthy headline IR.
The repo's presented book is IR 0.99 at $10m but **0.45 at $1bn**, breaks four
finals rules, uses `names_min=100`, `me>=300` on both legs, fixed $10m NAV, and
gross as an equality ([06_repo_evidence.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/06_repo_evidence.md)
§0, §7; [01_mandate_fidelity.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/01_mandate_fidelity.md) §§3–4;
spot-verified [08_critic.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/08_critic.md) §6).
Fix validation + costs + checker first; alpha second.

**Inputs evaluated:** plan
[FIAM_Final_Case_Research_and_Implementation_Plan.md](/home/drewclaw/Forkfiam/fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md)
(484 lines, §§1–14) against
[final_mandate.txt](/home/drewclaw/Forkfiam/fiam/v4b/inputs/final_mandate.txt)
(1,168 lines, extracted from "McGill-FIAM Asset Management Hackathon 2026 —
Final Challenge Instructions.pdf"). Evidence base: eval streams 01–09 read in
full (see [README.md](/home/drewclaw/Forkfiam/fiam/v4b/README.md) map). Where streams
conflict, [08_critic.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/08_critic.md) §2
adjudications and [09_gap_eventday_unknowables.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/09_gap_eventday_unknowables.md)
frozen defaults govern; both are applied below. Past repo work is evidence only.

**Severity:** CRITICAL = breach / wrong headline / disqualification risk ·
HIGH = large IR or judging cost · MEDIUM = material drag/credibility · LOW = polish.

---

## 1. Scored table (plan document, 0–5)

| Dimension | Score | One-line justification |
|---|---|---|
| Mandate fidelity | 4/5 | Every hard number correct in prose (§2, §10); not yet executable — constants/checkers missing (01 §§1, 4) |
| Forecasting | 3/5 | Ridge-over-trees ranking right; shrinkage identity, horizons, df accounting unspecified (02 F1–F3, F5/F6) |
| Risk | 3/5 | Factor `BFB'+D` right family; exposure estimator, `U_beta/U_mu`, ±0.02 robust band infeasible as written (03 F1–F3) |
| Construction | 3/5 | Two-stage + hard-first correct; sign circularity, triple regularisation, conic stack over-built (03 F5–F6; 08 M1–M2) |
| Costs / capacity | 2/5 | Architecture strong, calibration empty: no spread data exists, borrow swing 0.5–5.0% NAV/yr undefined (04 S4-07, S4-09) |
| Leakage / clock | 3/5 | Clock sentence exact; ≥9 holes in supplied files (filing dates, vintages, `dsf` dividends) unclosed (04 H1–H9) |
| Validation | 2/5 | Right vocabulary, **no frozen statistical gate** — at ~100 trials E[max Sharpe\|null] ≈ 1.06 (05 §§1.3–1.4; 08 E4 verified) |
| Reporting | 4/5 | §10 benchmark/Sharpe-vs-IR/CAGR exemplary; benchmark column + turnover hierarchy + Arcana reconciliation missing (05 §2) |
| Feasibility in 2 days | 2/5 | Sequence right; Arcana first upload, reporting pipeline, doubled agent run do not fit Day-2 hours (05 §5.1) |

Mean ≈ 2.9/5. The low scores are specification gaps, not direction errors:
with the §4 fixes below this is a buildable 4/5 plan (see
[REVISED_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/REVISED_PLAN.md)). No score rewards
any return claim — the plan correctly makes none (Plan L5, L289).

## 2. Per plan section — KEEP / FIX / DROP

### §1 Recommendation — KEEP with FIX · HIGH (scale) / LOW (wording)
Monthly information / weekly review / daily risk-only is the credited answer to
Mandate §4 (01 §1.9; 02 top line; 03 F9). "What can be made predictable" table
(L19–28) incl. L25 tiny-book warning: KEEP verbatim (08 §5).
**FIX (08 M1, missed by all streams):** with fixed 4% premium,
`IR(k)=(k·m−C(k)−0.04)/(k·s)` *increases* in scale `k` until convex costs bend it
down — §6's shrinkage stack tunes Sharpe, not IR, and can shrink positive alpha
to negative headline IR. Scale must be chosen on net IR(k), not Sharpe.
**FIX (01 §7, LOW):** present weekly-core as the E4-tested hypothesis, not a prior.
GP credited for "gradual rebalancing" (L13): FIX attribution per 03 F5.1 / 07 §3.5
— GP is quadratic costs + commodity futures; it does not justify L1/sqrt/conic/hysteresis.

### §2 Executable mandate translation — KEEP transcription, FIX executability · HIGH
No hard number mistranscribed: 200–500 combined, 5% cap, gross ≤200% *ceiling*,
net ±50%, shorts ≥$500m *at formation*, $1bn compounding, OOS Jan-2021–Aug-2026,
month-by-month benchmark, daily+monthly beta, turnover, §9.1/§9.4, Arcana, agents,
clock, Carbon Arc optional (01 §1 table, 16 rows). L49 disowning round-one
settings: KEEP (08 §5.4).
**FIX:** (a) §2 is prose, not a config — freeze `eps_net`, beta split, participation
`p` in a named `mandates/final_2026.json` before the ladder (01 §2.1).
(b) Drop forced ~150/leg; constrain combined count + neutrality, let legs float
(01 §2.2). (c) Internal 1% cap *binds at* the 200-name/200% floor (avg |w|=1.0%,
verified 08 E4) — cost it, replace with ADV-dependent cap as the rule (04 S4-05).
(d) Repo today: **no finals mandate file exists**; every `mandates/*.json` illegal
or wrong; checker still 100–500/polyfit beta, no 5%/short-floor/NAV checker (01 §§3–4 CRITICAL).

### §3 JKP contribution — KEEP method, FIX labelling · MEDIUM
Posterior maths `ᾱ=Ω(Ω+V)⁻¹a`, `Ω=τc²MM'+τw²I` and **"`P` is not `Σ`; use `APA'`"**
(L71–86) is the best page in the plan — KEEP verbatim (07 §3.1; 08 §5.2).
Look-ahead guard L90 (Feb-2021 paper vs Jan-2021 test; no imported clusters): KEEP.
Separate research replication vs tradable book (L69, L94): KEEP.
**FIX (08 E3, supersedes 02/07 glosses):** Plan L55 "global Bayesian 84.9%" is
*correct* (`w28432.txt:335-338`). Deck must show the 5-number bridge —
US OLS 84.9%, BY-adjusted 77.3% (frequentist, superseded in-paper), US Bayes 84.0%,
global Bayes 84.9%, US-conditioned-on-global 80.7% — all CAPM-alpha significance
rates, not tradable alphas. Neither "MT-adjusted 77.3%" alone (02) nor "global-EB
80.7%" as correction (07) is right. Budget alpha from HXZ-tradable numbers
(64–85% insignificant, `w23394`), method from JKP (07 §3.3).

### §4 Universal forecaster — KEEP ranking, FIX specification · CRITICAL (F3, F5/F6)
**[Superseded 2026-10-23: forecaster = E-LASSO, D6; ridge/GBT retired after testing, LESSONS 14–30.]**
Ridge default / shallow-GBT challenger / no NN / no daily alpha model: KEEP.
GKX `R²oos` (ENet 0.11%, GBRT 0.34%, NN3 0.40% monthly; OLS-920 −3.46%) supports
shrinkage (02 F2). Repo concurs: incumbent 12-signal EW `R²≈0`, 2016–20 IR −1.00,
chosen with 2021–26 visible — **DROP incumbent as default** (06 §1, HIGH);
LightGBM sole `+R²` (+0.08%) but best blend net IR −0.15 — challenger only (06 §2).
**FIX F1 HIGH:** "hierarchical ridge" conflates JKP alpha-pooling, KNS PC shrinkage
`d_j/(d_j+γ)` (η=2 prior), predictive ridge. Rename group-ridge; EB `λg=σ²/τg²`;
add KNS-PC factor benchmark. **FIX F3 CRITICAL:** no `T_eff`/df accounting —
`T_eff≈48–72`, not 250k rows; nested purged walk-forward + gap + df budget +
portfolio-level λ selection + 1-SE rule (02 F3; gap semantics per 08 C5).
**FIX F5/F6 CRITICAL:** no decay `κ`/half-life, no 21d→5d map. Correct share of
21d alpha in first 5d: h=15d **33.2%**, h=60d **26.1%** (08 E1 recomputed; 02's
26%/22% wrong, 22% impossible). Estimate IC decay; GP two knobs (aim size vs
trading speed) separate. **FIX F8 HIGH:** train on tradable universe, capped-VW
loss, leg-specific ICs — §4 EW full-universe contradicts §3/HXZ (02 F8).
**FIX F4 MEDIUM:** target order raw > sector-demeaned > residual (beta-noise,
double subtraction). **FIX (08 M3 HIGH):** pooled homogeneity untested — add
large/small slope gate; do not assert "universal". IPCA: DROP as forecaster
(= constrained Fama–MacBeth), diagnostic only (02 F2). Options branch: DROP for event.

### §5 Dynamic risk model — KEEP structure, FIX estimators · CRITICAL (F2/F3)
Factor `Σ=BFB'+D` over Ledoit–Wolf sample covariance: KEEP (attribution + K≪T;
use LW *inside* `F`, floor `D`) (03 F1.1). Repo design (`fiam/risk.py` + HAR vol,
frozen DM gate) reusable; monthly calibration underforecast pre-2021 (bias
1.38–1.41), daily realised beta −0.10 (t=−3.67) — rebuild daily (06 §4).
**FIX F1.2 HIGH:** "trailing regressions" for all exposures (L154) wrong +
unimplementable daily (~4M regressions). Use characteristic exposures + daily
cross-sectional WLS factor returns (repo `risk.py:22-60` pattern).
**FIX F1.3 MEDIUM:** EWMA factor HL 42/84d, specific 84/168d (not single 20–60d);
add horizon-scaling formula — `Σ_H ≠ H·Σ_1` under autocorrelation.
**DROP F2 CRITICAL:** dense `U_beta, U_mu` SOC terms unestimable (`U_beta=Σ_e/Sxx`
reintroduces N>T; `U_mu` has no input for ridge/GBM). Replace: scalar
`√(w'Σ_e w/Sxx)` reported, diagonal `u_i` shrinkage in objective.
**FIX F3 CRITICAL (numbers corrected 08 E2):** daily beta SE is 0.094–0.157
(not 03's 0.15–0.25); robust radius ≈0.034 at z=1.65, N_eff=150 — still >0.02, so
±0.02 *robust* band infeasible at 200% gross stands, correct reported bound
≈0.05–0.07. Hedge contemporaneous shrunk (Vasicek/Welch — one formula, not a
surname) beta = judges' OLS (Mandate §9.2); Dimson/downside diagnostics only.
Frozen repo race (Welch 0.518 < learned 0.567) is primary evidence (08 U2).
**FIX F4 MEDIUM:** stress needs loss budgets as constraints, pre-2021 calibration,
crowded-short overlay; parameterise or drop Student-t. Report daily beta as
headline compliance (SE≈0.01 binds; monthly SE 0.04–0.06 cannot separate 0 from
0.08 — 09 §6): judges' "materially ≠0" has no number; ±0.02 is internal only.

### §6 Rebalancing controller — KEEP shape, FIX to QP baseline · CRITICAL/HIGH
Honest nonconvexity (L211), "conic not QP" (L199), gross-floor disclosure (L217),
one-period not DP (L241), hard-first hierarchy (L227–231): KEEP verbatim (08 §5.6).
Two-stage support KEEP; MIP correctly rejected (NP-hard, no integer solver assumed).
Repo v1 `solve` has **no cost/variance term** (`book.py:306`), 46%/mo turnover,
IR 1.16→0.74; build on v2 convex plumbing, not v1 (06 §5 CRITICAL; 08 C3).
**FIX C3:** v1 optimiser = QP, quadratic impact `c_i q_i²`, `c_i=κσ_i NAV/ADV_i`;
ledger = sqrt-impact with execution days D (04 S4-08 formula below); shared `s_i`;
mismatch disclosed. **DROP** power-cone sqrt in optimiser, dense SOC, MPC (03 F9).
**FIX F5.2 HIGH:** `(γ,ρ,η,κ)` unidentifiable on 24 validation months — v1 keeps
`σ_max` + one cost scalar only. **FIX (08 M2 HIGH):** Stage-1 sign preassignment
circular — centre `μ` cross-sectionally, free-sign solve first, then fix signs;
resolve hedge-sleeve contradiction (L213 vs L219, 03 F6). **FIX F6:** greedy
risk/cost-adjusted selection with sector quotas, not raw rank.
**FIX F8 HIGH (tiered neutrality):** dollar + sector exact HARD, beta hard nominal,
**size hard band** (mechanical long-SMB from $500m short floor — unnamed in plan),
value/momentum/profitability *monitored* not zeroed (L94 beats uniform `|B'w|≤d`
L207); bands in vol units. **FIX F7:** slack-encoded solver ladder; short bound
at-formation hold-or-cover `w_i≥min(w⁻_i,0)` for drifted names (08 C2 — 04's forced
cover **rejected**). Daily = min-turnover repair only, never full re-solve (03 F5.5).
L1 band width is `|μ_i−γ(Σw)_i|≤s_i` (subgradient), not a global rank buffer (03 F5.1).

### §7 Capacity, accounting, clock — KEEP architecture/clock, FIX calibration · CRITICAL
Order-vs-position capacity split, no-free-book ramp, drifted ledger/accounting
identity, breach logging, hysteresis: KEEP — strongest part of §§6–8 (04 bottom
line). Clock L271 (t→close t+1→earn t+1→t+2): **KEEP verbatim** (08 §5.1).
Costs engine (`fiam/costs.py`, hand-tested) KEEP; fix scale (06 §6).
**FIX S4-04 CRITICAL (recomputed, 04 §1):** long leg binds, not shorts —
Dec-2020 median ADV all $9.5m vs short-eligible $31.1m; $6.67m position = 69.9%
1-day participation median long (7.0d @10%), only 19.3% of names ≤10% in 1 day.
Liquidity pre-filter **both** legs. Short-eligible pool 1,974–2,501/mo (median
2,091), not mandate prose 3,000–3,500 (S4-01 HIGH) — panel number governs (08).
**FIX S4-07 CRITICAL:** no spread data supplied — `bidask` is a 0/1 flag,
`dsf_mini` is `permno/date/prc/return` only. Bucketed half-spread + 0.5×/1×/2×
sensitivity; `κ/Y` unidentified — never quote FIM fractions to calibrate (08 U3).
**FIX S4-08 HIGH:** correct impact `|q|·Y·σ_daily·√(NAV|q|/(D·ADV))`; median long
~65bp/trade if 1-day; weekly 25% turnover @30bp = 3.9% NAV/yr (verified 08 E4).
**FIX S4-09 CRITICAL:** borrow 0.50%/2.75%/5.00% NAV/yr at 200% gross on undefined
"large cap" — swing exceeds the 4% premium. Mechanical dated rule + HTB/locate
stresses; pack has zero borrow literature (07 Rank 2). **FIX S4-06 HIGH:**
participation ×2.0 but sqrt drag ×√2 when NAV doubles; add NAV-contingent
breadth/gross rule. ADV frozen default: lagged `dolvol_126d` USD/day;
`dolvol` is monthly (21× error mode) (09 §4). Initial ramp: disclosed cash-ramp,
`w⁻=0` formation cost inside window (09 §5).

### §8 Data + agent — KEEP gates/PIT, FIX agent aim · HIGH
≤1 alt-data hypothesis + 4-question gate, 8-K "contaminated until rebuilt"
(L291), vintage principle (L293), PIT/memory controls (L301): KEEP (05 §§3–4; 08 §5.7).
Plan correctly beats Carbon Arc workbook on CA0035 no-text (05 §3.1).
**FIX (05 §3.2 HIGH):** workbook merge rules 2/4/5 missing — per-asset vintage
verdict, ban has-data-flag features (workbook-reported IC +0.021 t=6.1 is **not**
team evidence, 08 U4), cap sleeve to coverage. Analyst-estimates branch has no
provisioned asset — contingent only (05 §3.1; 07 §3.6: needs PIT I/B/E/S snapshots).
**FIX agent (08 C4: 05 beats 01 decisively):** explainer-only has Δholdings=0,
fails Mandate §5.3.4 counterfactual and §5.1 highest-value sizing role.
**DROP pure explainer as deliverable**; keep as audit log for a bounded-multiplier
(`m∈[0,1]`) sizing/triage agent + §5.2 triage agent. **FIX:** decoding contract,
full cache key incl. MCP responses, defined triggers + call budget (naïve 710k →
~3k exception calls); no raw 8-K text in action path (05 §4.3). Arcana MCP/vintages:
diagnostics only until PIT confirmed (09 §1; 01 §2.7).

### §9 Validation — KEEP skeleton, FIX gates · CRITICAL
Walk-forward + contamination disclosure L309 ("historically walk-forward with
prior researcher exposure"): KEEP verbatim in deck (08 §5.3). E0–E6 concept KEEP.
**FIX CRITICAL (05 §§1.2–1.4; 02 F7):** (i) purge-only insufficient — purge
overlapping 21d labels + justified pre-test gap (terminology per 08 C5;
severity HIGH not CRITICAL once purge correct); block ≥21d stated.
(ii) No statistical gate frozen: at T=68, IR 1.0 ⇒ t=2.38, IR 0.5 ⇒ t=1.19
(verified). Freeze paired-ΔIR block-bootstrap CI, IC HAC-t≥3 (HLZ), DSR in
*per-period* units (08 E4 trap warning). (iii) Effective trials undefined:
E[max ann. Sharpe|null] 0.58@N=7, **1.06@N=100**, 1.25@N=400 (recomputed 08 E4) —
IR≈1 is expected noise-max at realistic search. Effective-N registry + DSR;
PBO diagnostic only. (iv) Sequential ladder reuses 2019–20 (COVID) adaptively —
nested select/confirm years, count reuses in N (05 §1.5 HIGH). Repo context:
1,665 fits, DSR prob. 0.46, IR 2023–26 −0.01 (06 §0) — gates are not decoration.

### §10 Reporting — KEEP (exemplary), small FIXES · HIGH (attribution only)
Benchmark `b_m=TB3MS/1200+0.04/12`, `b_d=TB3MS/25200+0.04/252`, Sharpe over cash
vs IR over cash+4%, CAGR from ending NAV, daily≠monthly shown: KEEP (01 §2.4;
05 §2.1; 08 §5.5). §9.1 rows complete; §9.4 exhibits covered.
**FIX:** (a) benchmark column + one-slide constraint (Mandate §9 L867) (01 §2.6).
(b) Turnover (08 C1): §9.1 cell = prescribed avg×freq with declared rebalance set,
**co-headline** Σ/elapsed-years over *all* executed trade dates — neither 01's
footnote nor 05's inversion alone. Executed (not target) weights (04 S4-13).
(c) HAC lags stated; Dimson sensitivity if daily≈0/monthly≠0 (05 §2.4).
(d) **HIGH:** own-model attribution previews judges' Arcana/Barra split — add
own-vs-Arcana reconciliation + lens-2 exposure-emergence timeline (05 §2.6; 01 §2.7).
Supplied benchmark series is headline when issued; FRED recomputation is
reconciliation (file absent today, formula replicates hurdle ≈7.28%/yr, 09 §2).

### §11 Sequence + handoff — KEEP order, FIX hours · HIGH
Rules-first → simulator → baseline → ladder → Arcana; module contracts
`data/asof → … → agent never enforces` (L388–398); persistence list (L400);
clarifications list (L404): KEEP structure (05 §5.2; 01 build order).
**FIX (05 §5.1 HIGH):** hours fail as written — (i) Arcana first upload (identifier
map, weight basis, one-account bus factor) is ~half a day, move "small known book"
to D1 h2–6 on credential arrival; (ii) §9.1+8 exhibits+reconciliation in D2 h8–12
fits only if `reporting` emits every cell pre-event on dummy holdings (exit
criterion, no hand-typed numbers); (iii) agent ablation doubles the walk-forward —
run counterfactual on validation pre-freeze, chosen variant only in frozen OOS.
Add missing lines: Carbon Arc 20k-token pacing, per-position "why this trade?"
lookup, protected 2h rehearsal. E0 "audited compliant baseline" overstates
readiness — v4 recipe is in-progress/empty, `fiam/v4/kit.py` is USB tooling not
strategy code (06 §§0, 8). E0 = §4 ridge through new simulator; 12-signal is
diagnostic only. **FIX (08 M4 MEDIUM):** predeclare zero-alpha fallback book
(cheapest compliant neutral book) — mandate forbids empty book; plan has none.

### §12 Literature register — KEEP honesty, FIX scope · MEDIUM/HIGH
No misquotation found; cherry-picking is by omission/transfer (07 top line).
Reading-level labels (L408), MM/Cederburg pro/contra pairing (L449–450),
Shumway caveat, version discipline w/SHA (L480–484): KEEP as templates (07 §4; 02 §10).
Pack: 10 papers identified, 9/10 working-paper vintages, only FGX is journal PDF —
cite WP year + "published as" separately (07 §1.1 MEDIUM). Register coverage:
A 3/8 in pack, B 5/11, C 2/4; §§4–6 equations cite almost nothing (sqrt `κ` no
citation) (07 §2). **FIX HIGH:** GKX licenses *monthly* tree challenger only
(sample ends 2016, gross, reversal-heavy); GP licenses neither sqrt/L1/conic nor
weekly cadence (07 §§3.2, 3.5). HLZ t>3 must become BH-FDR + DSR + denominator,
not a per-feature gate (07 §3.4; 02 F7). KNS supports dense>sparse moral only
(PC rotation ≠ family ridge). BAB: KEEP as warning, DROP as alpha. FGX: optional
screen unless double-selection coded. Chapados/Goyenko-Zhang/Ledoit-Wolf/Cederburg/
McLean–Pontiff full texts not inspected — hypothesis/defaults only (07 §7).
**Missing literature ranked (07 §5):** 1 FIM/Khandani-Lo/Avramov daily-cost death ·
2 borrow (Cohen-Diether-Malloy; zero pack coverage) · 3 Kyle-Obizhaeva sqrt `Y` ·
4 PEAD/Lazy Prices · 5 McLean-Pontiff/Chen decay (≈42% WP — sensitivity only, 08 U5) ·
6 Davis-Norman/Boyd MPC (correct home for bands) · 7 daily-IC null. Snippet
magnitudes (STR 30–50bp/wk, Martineau RIP-PEAD) are hypotheses, never deck numbers (08 U1).

### §13 Alternatives table — KEEP with FIXES · MEDIUM
Rejections affirmed: pure min-variance as lead, RL, transformers, LLM weights,
stop-loss-only (L452–468). IPCA deferral KEEP but on statistical grounds
(constrained FM; unlabelled rotations) not only logistics (02 F2).
**FIX:** min-variance re-enters as fallback/null book (08 M4), not as strategy.
CVaR/DRO, MPC, Kalman beta: correctly deferred — keep deferred beyond event
unless E-ladder promotes with solve-time evidence (03 F9). Black–Litterman
rejection (no cap-equilibrium prior for zero-beta book): KEEP. Add explicit
DROP rows the eval confirms: daily alpha model, NN forecaster, options branch,
present-day listing filters (`provider_is_listed`/entity-map = survivorship, 04 S4-11).

### §14 Decision — KEEP thesis, FIX presentability · LOW
Core claim — within-group selection surviving neutrality, costs, $1bn capacity
is *the* question (= Arcana lens 1) — correct (01 §7). "Make daily trading earn
its cost" (L474) KEEP, stated as E4 hypothesis per §1 above. Add: if validation
says no edge, ship fallback book and honest negative (Mandate §§4–5 credit it);
no optimiser manufactures missing alpha (L472) — that sentence must survive.

---

## 3. Ranked issues

### Fatal if shipped as written (CRITICAL — close before any OOS run)
1. **No finals mandate config/checker; repo breaks finals rules** — `names_min=100`,
   `me>=300` both legs, $10m static NAV, gross equality, v3 IR 0.45@$1bn, README
   headline untraceable (01 §§3–4; 06 §§0, 7; 08 §6 verified).
2. **Validation can promote noise** — purge-only, no frozen gate, no effective-N/DSR;
   IR≈1 = noise-max @N=100 (05 §§1.2–1.4; 02 F3/F7).
3. **Horizon mismatch unquantified** — no `κ̂`, no 21d→5d map; E4 uninterpretable (02 F5/F6).
4. **`U_beta/U_mu` + ±0.02 robust beta infeasible/unestimable** (03 F2/F3, E2-corrected).
5. **Cost calibration empty at $1bn** — no spread source, borrow 0.5–5.0% swing,
   long leg 7d median @10% (04 S4-04, S4-07, S4-09). V1 objective omits binding term (06 §5).
6. **Leakage holes H1/H2** — 8-K provider dates (100% placeholder, 100% null SEC
   acceptance), 147 chars with no documented lag/vintage (04 H1–H2). Disqualification risk.

### Major (HIGH — close before trusting net IR)
7. IR-scale effect + sign circularity + pooled homogeneity (08 M1–M3).
8. Shrinkage identity (02 F1), microcap/trainable-universe gap (02 F8), HLZ→FDR/DSR (02 F7).
9. Exposure estimator + tiered neutrality incl. size band (03 F1.2, F8); GP mis-citation (03 F5.1).
10. Impact D/horizon conflation, compounding scalings, pool recount (04 S4-01, S4-06, S4-08).
11. Holes H3–H7: `ret_exc_lead1m` stub/target-month/allowlist, same-month `dolvol/me`,
    `dsf` past-OOS + price-only appearance, ticker joins, delisting numbers (04).
12. Ladder adaptivity (05 §1.5), turnover headline (05 §2.3/08 C1), Arcana lens risk (05 §2.6),
    merge rules 2/4/5 (05 §3.2), explainer agent (05 §4.1/08 C4), cache/triggers (05 §4.3), hours (05 §5.1).
13. Daily simulator + clock unbuilt; overlay unfunded (text t=2.1 rejected, analyst IC −0.003) (06 §3).
14. GKX/GP transfer overreach; borrow/impact literature absent (07 §§3–5).

### Minor (MEDIUM/LOW — fix in rewrite, not blockers)
15. JKP bridge labelling (08 E3 MEDIUM); decay-table/beta-SE report errors corrected (08 E1–E2).
16. Residual-target ordering, calibration slope, missingness ablation (02 F4, F10–F11).
17. Stress budgets, horizon scaling, slack ladder details (03 F4, F1.3, F7).
18. `me` field, ADV naming, S&P TR labelling, beta statistics — **now resolved** as
    frozen defaults (09 §§3–4, 6–7); cost ≤ few names/bp. GICS vintage (04 S4-12) unchecked.
19. Benchmark column, cost footnote, relative-wealth definition (05 §§2.2, 2.5, 2.7 LOW).
20. WP-vs-published years; abstract-only rows must not load-bear (07 §§1–2).

## 4. What the plan gets right (do not lose — 08 §5)
- Clock L271 verbatim; `P≠Σ` L86; contamination L309; §2 table + L49; §10
  conventions L347–353; honesty machinery (L199 conic, L217 gross floor, L231
  intraday, L241 not-DP, L408 reading levels, L90 look-ahead guard); 8-K L291.
- Architecture: one forecaster, monthly info/weekly review/daily risk-only,
  cost-aware construction, hard-rules-first, two-stage support, no padding.
- Order/position capacity split + no-free-book ramp; drifted ledger; breach logs.
- JKP as separate research exercise; factor-vs-selection comparison (L94).
- Drop list: daily alpha model, NN/transformer, options (event), LLM weights, MIP.
- Repo discipline worth reusing: costs engine + hand tests, v2 convex plumbing,
  HAR/DM vol gate, freeze tests, 1,665-experiment ledger (06 §8) — discipline
  proved even where strategies it judged failed.

## 5. Unresolved (preserved; not plan defects unless noted)
Event-day (09): Arcana identifier/columns/weight basis + PIT vintages (default:
diagnostics only); supplied benchmark TB3MS vintage + daily alignment; 200-floor
during ramp/liquidation + formation-cost window; judges' numeric beta line + their
S&P series. Data-gated: panel/147/`ret_exc_lead1m` construction + JKP lags (H2);
`dsf` dividend adjustment (H5, external record needed); CA0065S fields/units;
consensus-snapshot existence (gates van Binsbergen); GICS vintage; starter-script
internals; Gurobi availability (assumed absent). Empirical (frozen-protocol runs
only): `κ̂/Y`, IC-decay, `U_mu` sandwich, short alpha in ≥$500m pool, daily/weekly
net alpha, beta-SE on daily panel (Day-1 rerun). Literature unverified:
Martineau/Avramov primaries (403/snippet), Chapados/Goyenko-Zhang/Cederburg/
Ledoit-Wolf/McLean–Pontiff full texts, JKP JF-2023 vs w28432 diff. Carbon Arc
workbook was inspected by 05 (4 sheets) — per-asset vintages still open.
Full disposition + corrected build: [REVISED_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/REVISED_PLAN.md).

