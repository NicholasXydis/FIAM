# Revised plan v4b — build Oct 24–27, rerun only Oct 28–29

**Status:** corrected build plan. Supersedes conflicting text in the Taildrop
plan ([FIAM_Final_Case_Research_and_Implementation_Plan.md](/home/drewclaw/Forkfiam/fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md))
where [EVALUATION.md](/home/drewclaw/Forkfiam/fiam/v4b/EVALUATION.md) records FIX/DROP.
Governing authority remains
[final_mandate.txt](/home/drewclaw/Forkfiam/fiam/v4b/inputs/final_mandate.txt).
This is a design, not a tested strategy. No return is promised.
**Merged 2026-10-23:** amendments A1–A15 from [CONTINUATION_PLAN.md](/home/drewclaw/Forkfiam/fiam/v4b/CONTINUATION_PLAN.md) (its evidence X1–X9 and the
pre-2021 maths in `research/`) are written into the sections below and govern
over any older wording. The organisers wrote that the event days "are not build
time": everything is built before Oct 28; the event days only rerun the frozen
strategy under any new constraints.
**Forecaster decision (2026-10-23, D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md)): E-LASSO** (Han–He–Rapach–Zhou), MaInf
primary, Ma1 alternate chosen only on net IR in the engine. It replaces every earlier
forecaster wording (group-ridge, 50/50 blend, MLP), which survives below only as tested
comparison baselines.

**Conventions:** rules marked **[Evidence]** trace to eval inspection (file cited);
**[Judgement]** marks reversible choices evidence does not settle — freeze them in
config before the ladder anyway. Anything unmarked "judgement" that lacks evidence
was deliberately *excluded* (see §11 drops).

**Implementation status, 2026-10-23 (D9):** monthly E0–E3 is complete as a
diagnostic. No candidate passes executed compliance; daily repair and final
reporting remain prerequisites to OOS. See `CONTINUATION_STATUS.md` and
`out/engine/ladder.json`; the gates below remain unchanged.

## 0. One-paragraph build order
Finals config + holdings checker + $1bn compounding daily simulator (t+1/t+2
clock) first — nothing is judgeable without them ([08_critic.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/08_critic.md)
rewrite order (1)–(2)). Then frozen validation gates, the E-LASSO forecaster (D6) on
the tradable universe, characteristic-exposure factor risk, QP controller tuned
for net IR scale, liquidity-first costs. Agent and alt-data last, each behind a
pre-registered kill gate. If validation says no edge, ship the fallback book (§5.5).
Build the §5.5 fallback book on day one: the hurdle condition (§5) says a neutral
book needs residual IC ≈0.031–0.039 after construction losses, and our pre-2021
SYY-style composite shows +0.010, so the fallback is the likely headline.

## 1. Architecture
```
monthly information -> weekly core solve (QP) -> daily monitor (repair only)
data/asof -> forecast -> risk -> universe/support -> construction(QP)
          -> execution(simulator) -> accounting(NAV ledger) -> reporting
agent: bounded multipliers on exception-flagged trades; never enforces
```
**[Evidence]** Monthly info / weekly review / daily risk-only is the credited
shape (Mandate §4; 01 §1.9; 02 §9; 03 F9). Daily buys risk control + event expiry,
*not* a second alpha engine: daily characteristic R²≈0, STR mostly microstructure/
microcap (HXZ `w23394:95`), modern large-cap PEAD ≈0 at snippet grade — daily
alpha model, NN, options branch are **dropped** (02 §9; magnitudes snippet-only
per [08_critic.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/08_critic.md) U1, never budgeted).
One forecaster: **E-LASSO** (§3, D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md)), run from the authors' unchanged R code;
never a model-family search. Ridge, blend, MLP and GBT are tested baselines only
(LESSONS 14–30).

**Reuse vs rebuild [Evidence: 06 §8]:** reuse `fiam/costs.py` engine + hand tests,
`fiam/v2.py` convex plumbing (solver fallback, dual logging), `fiam/risk.py`
*design* + `fiam/vol.py` HAR/DM gate, walk-forward/firewall tests, freeze machinery.
Reuse the upstream point-in-time layer `fiam/v4/clock.py`, `links.py`, `exits.py`,
`sources.py` (tested) for §6 (X3). Rebuild: daily simulator, E-LASSO runner (`elasso/`, authors' code unchanged),
support solver, verifier + §9 reporting. CPU only, ≤5 min per $1bn book, no
rented GPU on the critical path (X7: four paid runs died on spend limits). `fiam/v4/kit.py` is USB tooling, not strategy code. Discard `book.py`
`solve` for finals (gross equality, $10m rounding, no costs — `book.py:295,306`).
Strike README IR 0.99/16% from finals material; honest starts are v1 $10m
contaminated and v3 IR 0.45 @$1bn (06 §0).

## 2. Finals config — freeze before any ladder (pre-event deliverable)
Create versioned `mandates/final_2026.json` + policy annex; quarantine round-one
JSONs for finals runs (01 §8 CRITICAL). Hard rules (Mandate §3.1):
`names 200–500 combined · |w_i|≤5% · ||w||1≤2.0 (ceiling, inequality) ·
net target 0, mandate band ±50% · US only · shorts min(me, me_company)≥$500m
at formation · NAV0=$1bn compounding, no flows · OOS 2021-01–2026-08`.

Frozen defaults resolving former "unknowables" ([09_gap_eventday_unknowables.md](/home/drewclaw/Forkfiam/fiam/v4b/eval/09_gap_eventday_unknowables.md)):
- **Cap field:** security `me` (USD m, readme L146); safest `min(me,me_company)≥500`
  — 1 discordant name Jan-21 (PERMNO 18050), cost immaterial. Never `market_equity`
  characteristic as compliance field (04 S4-02). Daily formations:
  `me_{i,d}=prc_{i,d}×shares_{i,last prior month}`, rechecked at execution for
  new/increased shorts (04 S4-03 as corrected by 08 C2).
- **ADV:** CRSP daily dollar volume (WRDS allowed, X2), trailing 126d, lagged one
  day, through 2025-12. From 2026-01: `dolvol_126d` lagged one month × a splice
  ratio frozen on 2015–2020 (median CRSP-ADV / `dolvol_126d`); 2026 labelled as
  its own sub-period. `dolvol` is *monthly* USD (`=|prc|·tvol`, ratio 1.000) —
  using it as daily overstates capacity 21×; unit-test it (04 §1; 09 §4). FINRA
  or CA0065S replace the 2026 leg only if they pass agreement checks before the
  config freeze.
- **Beta series:** prefer S&P 500 total-return excess; else FRED SP500 labelled
  "price, excl. dividends" + footnote (β unchanged; α shift ≈β·ȳ_div ≤3bp at
  band; cumulative context gap ~8%, 09 §7). `r_f` from TB3MS basis, /12, /252.
- **Benchmark:** supplied series headline when issued; formula
  `b_m=TB3MS/1200+0.04/12`, `b_d=TB3MS/25200+0.04/252` as reconciliation (Plan §10
  KEEP). Never a forecast feature before observable.
- **Arcana:** no v4 book (backtest, rehearsal or candidate) uploaded before the
  single 2021–26 run — a mock book may be tracked forward to today. Before it,
  the lens checks run in our own code. Afterwards diagnostics only; Arcana's
  optimiser, hedge ideas and conviction sizing never set a weight. Dated
  PERMNO→CUSIP/ticker crosswalk pre-built.
- **Ramp:** disclosed cash-ramp, participation-capped partial fills, formation
  turnover with `w⁻=0` + costs inside measured window; 200-floor binds every
  *target* book, executed converges; report ramp days + §9.1 min-count (09 §5).
- **[Judgement] internal policies** (label policy, cost each): `eps_net≈0` at
  formation; beta nominal ±0.02 (internal, §4); participation p=10% (test 5/20%);
  `D_max` 3–5d; position cap `min(1%, p·ADV·D_max/NAV)` (04 S4-05 — flat 1% alone
  is infeasible-size); min size 0.10% with hierarchy: policy yields before mandate.

Holdings checker (new; build order 01 §4): count 200–500, max|w|≤5%, short-floor
at formation (dated `me` join), gross/net on *executed drifted* books, NAV-ledger
reconciliation, per-join `max(feature_date+lag)≤formation_date` assertions
(Mandate §8.1), daily+monthly HAC beta gate. Fix `names_min` default path
(`fiam/mandate.py:31`, `verify.py:33` still 100 — CRITICAL until changed). Plus four tests from the
quarcc audit (X6): a synthetic −100% return stays in P&L; the first fit month
respects the warm-up; no t-stat/CI from <12 independent periods (prints n/a); no
`_`-prefixed fields through `itertuples`. **Ban list in config:** v3's 15
OOS-visible choices, the 60/40 residual sleeve (chosen on 2021–26, X9), and any
setting first seen in the `out_r11..r13` 2021+ replays.

## 3. Forecasting spec
**Target/horizon [Evidence 02 F5/F6; D6]:** E-LASSO is *estimated* on the monthly
`ret_exc_lead1m` (a month-t regression may use only returns realised by eom t; `y21`
would leak one session). Every forecast is *evaluated* on the earnable daily-aligned
H=21d excess total return (`y21`, dividends added back, H5). Separate H=5 head only
as E4 diagnostic. Never rescale `μ̂²¹/21` to "daily alpha"; never copy monthly
rows to daily training.

Decay (pre-register; Mandate §11 exhibit): on validation only, rank IC vs
non-overlapping forwards H∈{1,2,3,5,10,21,42,63}d (all t+1-lagged), fit
`IC(H)=IC0·e^{−κH}` (+slow constant), block-bootstrap CI on `κ̂`, half-life
`h=ln2/κ`. Remaining alpha at age a: `Â(a,H_hold)=Â(21)·e^{−κa}(1−e^{−κH_hold})/(1−e^{−21κ})`.
Corrected 5d shares of 21d alpha: h=3d 69.0%, 15d **33.2%**, 60d **26.1%** (08 E1).
Staleness enters as `e^{−κ̂a}·μ̂` multiplier, not a regressor. GP two knobs stated
separately: aim *size* ↑ persistence; trading *speed* — fast sleeves prompt+expiry
or not traded, slow approached gradually (02 §6.1; GP quadratic-cost scope per 07 §3.5).

**Model (decided, D6): E-LASSO.** Each month: (1) S-LASSO, a value-weighted LASSO of
returns on standardised characteristics, λ by AICc, coefficients averaged over past
months (MaInf); (2) C-LASSO, univariate WLS forecasts combined by a non-negative LASSO
and averaged over the selected ones; (3) E-LASSO, the forecast-encompassing weight θ ∈
[0,1] between them, averaged over time (Internet Appendix A1.2–A1.4). Inputs follow the
authors' GHZ contract: within-month winsorise 1/99%, standardise, NA → 0, weight `me` at
t−1. The forecast is calibrated: Mincer-Zarnowitz slope 1.22 (s.e. ≈ 0.5), so it enters
the optimiser as an expected return, after the frozen held-out calibration scale.
Re-estimated every month; the book holds with bands because MaInf alpha persists into
months 2–3 (LESSONS 32).
**Tested and retired as forecasters (kept as baselines):** pooled **group-ridge** (rename; not "JKP hierarchical") —
`min Σ_t (1/N_t)Σ_i (y−x'θ)² + Σ_g λg||θg||²`, `λg=σ̂²/τ̂g²` empirical-Bayes per
family on training folds only; report `τ̂g` (02 F1). Ridge>ENet>sparse on evidence
(GKX/ KNS dense-in-chars, sparse-in-PCs); ENet diagnostic only; lasso sparsity ≠
positions. The 2-layer MLP (fixed defaults, 5-seed average, rank labels) was the
interim forecaster under D2 and is **superseded by E-LASSO (D6)**. **[Evidence, amended 2026-10-23,
`out/forecast/initial_plan/`, LESSONS §3]:** the group/hierarchical ridge was tested as the
initial plan wrote it (date-balanced, family-regularised, nested walk-forward
2017–2020, 48 held-out months). Validation picked maximal shrinkage every year
(df ≈ 0; inner IC flat across five orders of λ), and the result is a static
large-cap/low-beta tilt with within-sector spread −0.40%/21d. The hierarchy adds
nothing (+0.002 ± 0.002 IC). The 50/50 blend is therefore **dropped**; the ridge stays
as a reported diagnostic. MLP was chosen once on 2019–20 by the 1-SE rule. On 48
months GBT depth≤3 is a near-tie (IC +0.006 ± 0.005, spread +0.17% ± 0.31%) and is
reported beside it, never swapped in post hoc. Magnitudes: rank scores, mapped by
Grinold `α = IC·ω·z` with a stated IC, never by a regression slope (slopes on 24–48
months were unstable or wrong-signed). KNS-PC `b̂=(Σ+γI)⁻¹μ̄` on `F=Z'R` reported as a pricing diagnostic only.
No deep nets/attention (quarcc Exp12–16: none admitted). IPCA diagnostic only.
JKP replication stays a *separate* research exercise (Plan L71–86, `P≠Σ`, HAC `V`,
no imported clusters L90) feeding family priors `τg` — tradable claim is the
factor-attributed *residual* (02 F2c).

**Universe/loss [Evidence 02 F8, 04]:** train/validate primary on tradable
universe (lagged ADV/price screen; shorts additionally ≥$500m), capped-VW or
√ADV loss weights (report both); full-universe EW as "untradable alpha" diagnostic.
Leg-specific ICs (long-eligible vs short-eligible). Baselines use within-date
ranks/z on the tradable universe; E-LASSO uses its own GHZ contract (D6). No
full-sample statistics anywhere. **Centre forecasts:**
`μ̃_i=μ̂_i−median_j(μ̂_j)` per formation before any sign logic (08 M2).
**Heterogeneity gate (08 M3):** large/small split `θ` correlation + sign agreement
on validation; interaction ridge only within df budget + net-IR promotion.
Targets order: raw excess (default) > sector-demeaned > full residual (02 F4).
**Tested:** the residual target did not win on within-sector spread (GBT 0.02% vs
0.25%). Monthly `ret_exc_lead1m` and the daily-aligned `y21` give identical ICs, so
`y21` (earnable timing) stays primary. `y21` adds dividends back (H5: dsf is
price-only, `out/audit/dsf_vs_panel.json`).
Missingness: within-month median impute (rank 0), **no indicators** (tested: −0.005
IC, and they risk acting as has-data flags).
**Sector controls in the forecast: dropped.** They raised raw IC (0.033) only through
sector bets: within-sector IC 0.011, spread −0.59%. A sector-neutral book cannot
harvest them. The forecast is judged within sector. Feature allowlist = 147 names only; ban `adjfct/ret*/me_lag1/
source_crsp`, all provenance flags, any has-data presence feature (04 H3/H6; 05 §3.2).

**Validation machinery (02 F3 CRITICAL):** E-LASSO has no tuned hyperparameter: λ is set
by AICc inside each monthly regression, and its smoothing windows are the authors'. So
nothing is selected on validation except Ma1 vs MaInf, on net IR (one trial). The rules
below govern the baselines and any future challenger. nested expanding walk-forward
(train 15–18/val 19–20/test 21, then train≤Y−3, val Y−2..Y−1, test Y; refit thru
Y−1 only if predeclared, λ frozen). Purge labels crossing boundaries (key splits
on *target month*); pre-test gap only where a named trailing feature needs it
(08 C5 — do not blanket-embargo 21d without naming the channel). No shuffled
K-fold anywhere incl. solver defaults. Report `df(λ)=Σ d_j²/(d_j²+λ)`, `T_eff`
(≈48–72 pre-OOS; overlapping daily labels ÷H), gate **[Judgement]** `df≤T_train/5`.
Select λ (near-optimal set) on validation *net portfolio* IR; 1-SE rule (most
regularised within 1 block-bootstrap SE). Block bootstrap block ≥21d, stated.
**Hard cap: ≤12 registered configurations before freeze**, across λ, half-lives,
support, p and bands; each extra needs a written reason and enters DSR N.
**[Evidence: research/hurdle_by_size.out]** SE of a 24-month mean IC ≈0.020, so
best-of-96 adds +0.044 (correlated) to +0.062 (independent) IC of luck — more
than the hurdle IC itself.

## 4. Risk model spec
`Σ_{t,H}=B_t F_{t,H} B_t' + D_{t,H}`, K≈16 (market + sectors + size/value/momentum/
profitability/investment). **[Evidence 03 F1]** Exposures assigned, not regressed:
sector dummies exact; styles = within-date standardised characteristics (monthly
carry); market beta column = shrunk time-series beta (below), weekly refresh.
Factor returns: one daily cross-sectional WLS/day on liquid universe (weights
`√me` or `1/σ̂_e`), Barra identification (no intercept; cap-weighted sector
returns sum 0). `F`: EWMA of factor returns, HL **[Judgement]** {42,84}d chosen by
pre-OOS bias statistic `std(r_p/σ̂_p)` (repo `risk.py:74-105` test ported daily),
Newey–West pre-adjustment, shrunk to diagonal `δ≈0.1–0.3` predeclared.
Specific: HAR forecast (repo frozen winner; LightGBM failed DM gate — do not
revive without new gate), EWMA HL {84,168}d, cross-sectional shrink + floor at
~5th percentile. **Frozen 2026-10-23 (D8): EWMA-168 on residuals — HAR retargeted
at residuals lost the QLIKE/DM race (LESSONS 43); factor HL 84; bias 1.29-1.51
documented, no vol multiplier fitted.** Horizon: estimate `F` on non-overlapping 5d returns for weekly
controller, scale `×H/5`; state iid assumption; full form
`Σ_H=HΣ_1+Σ_{j<H}(H−j)(Γ_j+Γ_j')` in factor space if autocovariances kept (03 F1.3).
Stress overlay as second constraint `max{w'Σ_base w, w'Σ_fast w}≤σ_max²`, report
which binds (03 F1.4) + correlation-stressed `F^stress` (corrs 50% to ±1, vols×1.5).

**Beta (judged object = contemporaneous OLS, Mandate §9.2):** hedge beta =
Vasicek/Welch shrink of winsorised 252d daily OLS toward sector mean, blended
**[Judgement]** 50/50 with 60m monthly (print the formula/weights, 08). Repo
frozen race favours Welch over learned beta (06 §4) — learned is challenger only.
Dimson (±1), downside, BAB betas: diagnostics (panel fields exist). Constraint:
nominal `|β̂'w|≤0.02` HARD (feasible pattern). Uncertainty **reported**:
`√(w'Σ_e w/Sxx)` from factor model (never form dense `U_β`); expected robust
bound ≈0.05–0.07 (08 E2) — if it must bind, gross/`N_eff` gives, stated with
arithmetic. Sat Oct 24 check: rerun SE on daily panel (literature σ used so far).
Compliance evidence: daily beta headline (SE 0.008–0.013, T=1421), monthly with
HAC CI (SE 0.040–0.064 — "insignificant ≠ neutral", Plan L168), 252d rolling exhibit.

**Stress (03 F4):** joint block scenarios only; loss budgets as linear constraints
`w'r⁽ˢ⁾≥−L_s` (**[Judgement]** L=3% NAV factor shocks); calibrate pre-2021
(2008 momentum crash, 2020-Mar), OOS episodes diagnostics-only; crowded-short
overlay (cap shorts by borrow tier; stress top-decile crowded +30% idio + forced
cover at stressed ADV). Drop unparameterised Student-t (or df 4–6, specific only).

## 5. Controller spec (objective + constraints in math)
Weekly core solve; daily = minimum-turnover projection onto violated constraint
only. One horizon H everywhere (days to next review for holding costs; decay
converts 21d forecast to H — 03 F5.4). `w⁻` = drifted pre-trade book, `q=w−w⁻`.

**v1 objective (QP) [08 C3]:**
```
min_w  (γ/2)·w'Σ_{t,H}w − μ̃_{t,H}'w + Σ_i s_i|q_i| + Σ_i c_i·q_i²
       + (H_hold/252)·Σ_i b_i·max(−w_i,0) + Σ_i u_i·w_i²   (+ ordered slacks, below)
  c_i = κ·σ_{i,daily}·NAV_t/ADV_{i,lag}      (quadratic impact in optimiser)
  u_i ∝ σ̂²_{e,i} / (signal age, coverage)     (diagonal uncertainty; replaces SOC)
```
Dropped from v1: `ρ√(w'U_μw)` SOC, `η||w||²` (D does the work; 1% cap handles
concentration), power-cone sqrt (03 F2/F5). Free knobs in v1: `σ_max` (via
constraint, implied γ reported) + **one** cost scalar. Every extra knob = E-upgrade.
No-trade logic from subgradient: don't trade i iff
`|μ̃_i−γ(Σw)_i−shadows|≤s_i` — hysteresis bands calibrated to name `s_i` (03 F5.1).
Cite Davis–Norman/Boyd for bands, GP only for persistence/holdings-dependence morals.

**Scale for IR, not Sharpe (08 M1):** on validation, plot net
`IR(k)=(k·m−C(k)−0.04)/(k·s)` for frozen direction, full convex costs+borrow;
default scale = the largest gross the HARD rules allow (IR rises with gross under
the fixed premium); `IR(k)` only checks whether costs justify less. Ex-ante TE is
**reported, not targeted**: a neutral book carries ≈2–3% idiosyncratic TE
(ω≈25.9%/yr, N 200–500, G 1.77), so the former σ_max∈[8%,12%] range is
unreachable without style tilts and is dropped. If `max_k E[a]≤0` on validation → §5.5.
**Hurdle condition [Evidence: research/hurdle_by_size.out; Judgement TC 0.6, c 2%,
realised TE 1.5× idio]:** `IR = √N·(G·TC·IC·ω·√12·E|z|(p) − 0.04 − c)/(G·ω·infl)`,
`p=N/(2P)`, `E|z|=φ(Φ⁻¹(1−p))/p`, pool P≈1,862. The sign depends only on whether
book alpha clears 4%+c; IC needed 0.031 (N=200) … 0.039 (N=500). Each 1% NAV/yr
of cost moves the IC needed by ≈0.006 — cost cuts are worth as much as signals.

**Constraints.** HARD (no slack): `||w||1≤2 · |net|≤0.50 · |w_i|≤5% ·
short bound · order caps NAV|q_i|≤p·ADV_i · liquidation NAV|w_i|/(p·ADV_i)≤D_max`.
POLICY (ordered slacks `M1≫M2≫`alpha, slack log = pre-trade explanation):
`1'w=0` formation · sector `|S'w|≤1% NAV/sector` **[Judgement]** · `|β̂'w|≤0.02` ·
size band `|(B'w)_size|≤d_size` · `w'Σ_ann w≤σ_max²` (+stress max) · turnover guide.
Bands in vol units `d_k=0.25·σ_target/σ_{F,k}` (state orthogonality caveat or bound
`√((B'w)'F(B'w))` directly, 08 E2). Alpha-styles (value/mom/prof/invest): monitored,
wide bands only — zeroing them zeroes the thesis (Plan L94). Solver ladder:
enlarge support → resolve with slacks → min-gross compliant book + breach-day log
(03 F7). Never fabricate fills; turnover may break guide to repair HARD breach.

**Short bound (checked on rebalance dates; each rebalance is a formation):** at a
rebalance every held short needs `min(me,me_co)≥500`; names below are covered in
that rebalance's trades. Between rebalances drift is held and logged, never
force-covered; a daily repair that opens or increases short `i` requires
`w_i≥−cap_i·1{min(me,me_co)≥500}`, else `w_i≥min(w⁻_i,0)`. Borrow bans
(repo `short_ban` pattern) sit *inside* this bound as policy.

**Support (N from the hurdle condition, two-stage; MIP dropped):** N∈{≈250,
≈300, ≈450} picked by plugging frozen validation IC and measured c(N) (impact per
$ ∝√position) into the §5 hurdle formula — mechanics, not a backtest race; below
IC≈0.06 the concentrated end wins. Stage 0 free-sign solve on enlarged
support (no min-size) → read signs/shadows (08 M2). Stage 1 greedy add by
`(μ̃_i−borrow_i−entry cost_i)/σ̂_{e,i}`, sector quotas, incumbents credited saved
exit cost; leg counts float (combined 200–500 only). **Hedge decision [Judgement]:**
sign-fixed book + capped sign-free hedge sleeve ≤10% gross with μ̃≈0 required —
or sign-fixed everywhere and delete "hedge value" claims; pick one in config (03 F6).
Stage 2 QP with signed [0.10%, min(1%, ADV-cap)] bounds. Gross floor 30%@300
disclosed (Plan L217); emergency order: min-size relaxes before count.
Report `N_eff=(Σ(|w_i|/||w||1)²)⁻¹` + factor-risk share (≠ independent bets).

**5.5 Fallback book (08 M4, predeclare):** cheapest compliant neutral book —
most-liquid longs, cheapest-borrow large-cap shorts, min turnover, gross minimising
expected NAV drag. Also the identical-support null for forecast-value attribution.
Attribute weekly drift-restoration flows (long-leg reversal / short-leg momentum
mechanics) before crediting weekly trading with "risk control".

## 6. Information clock rules (each = code assertion, not prose)
Master rule **verbatim**: information through day t forms book at **close t+1**;
first earned return **close t+1→t+2**; trading-calendar arithmetic; publication
lag applied *before* execution convention (Plan L271). Field rules (04 H1–H9):
- **8-K:** `filing_date` = unverified provider date, midnight placeholder, SEC
  fields 100% null → treat as after-close t; headline + extra +1d conservative
  case (form t+2). Ban: `content_report_date`, timestamp hour, `period_end`,
  prep clocks, `title_ai/sector/industry/metadata_json`. Aggregate ≤5 filings/
  PERMNO-day pre-join. EDGAR rebuild via acceptance time + dated CIK→PERMNO map.
- **147 chars:** no documented lag/vintage (readme L296, L332) — declare as
  unrepaired vintage risk in deck; impose JKP-style lags (annual +6m, quarterly
  +4m) *if verified against codebook*, else +1m conservative case with IR delta
  shown (H2). Clock keys on `date`, not `eom` label.
- **Labels/splits:** key on target month; purge label windows crossing splits;
  daily-aligned label is the result, monthly never headline (H3).
- **Aggregates:** ADV/`me`/`size_grp` for month t from t−1 (or trailing verified
  daily); never same-month `dolvol` (H4). Characteristics carried with age feature.
- **`dsf`:** truncate ≤20260831 at load (file runs to 20260928); reconcile vs
  monthly `ret` before *any* daily return is presented — IBM test suggests
  price-only (H5 **unresolved** until external distribution record); if price-only,
  add dividend adjustment or bound short-book dividend drag. As-of joins
  `feature_date≤t`, sorted, direction asserted.
- **Identifiers:** PERMNO-native; CA0035 ticker joins need dated ticker map +
  delisted-coverage test; header labels banned from prompts/features; text splits
  grouped by `text_sha256`/CIK×time (H6). Drop present-day listing filters (S4-11).
- **Delisting [freeze numbers pre-OOS]:** longs imputed delisting return with
  sensitivity (0%/−30%/−55% performance-related, sourced); shorts cover at last
  traded price only if traded that day, else frozen + borrow continues to stated
  date; never book uncollectible −100% windfall; report count/weight/yr (H7).
- **2026 break:** Compustat winsorised returns + inferred identifiers — disclose,
  flag sub-period for any CUSIP/ticker/CIK join (H8). Verify `gics/sic/ff49`
  within-PERMNO variation by Sat Oct 24 (S4-12, two-column groupby).
- **CA0035:** full chain event→feature→formation→first-earned per family in deck;
  decay curve gates admission; weekly-delivery case separate (H9).
- Model memory: no live retrieval, release/cutoff in config, re-id rate reported,
  numeric-only agent inputs, non-LLM baseline intact (Plan L301 KEEP).

## 7. Cost / capacity model
**Liquidity first [Evidence 04]:** hard pre-filter both legs
`position ≤ p·ADV_lag·D_max` *before* ranking; report IC destroyed by filter +
joint (forecast-rank × ADV) distribution — it gates 200/300/500 choice.
Capacity vs compounded NAV, stressed ADV **[Judgement]** ×0.5. NAV-contingent
rule: N_t (toward 500) or gross adjusts so median days-to-trade ≤D_max (S4-06);
remember participation ×2 vs sqrt-drag ×√2 at NAV×2. Dated eligible counts per
formation reported (pool median 2,091, S4-01) — sampling share vs panel pool.

**Ledger costs (single source for deck magnitudes; optimiser §5 approximates it):**
```
spread:  s_i = half-spread (state it; full-spread error = clean 2×)
         bucketed by lagged price×ADV fitted to CRSP/TAQ 2015–2020; bidaskhl_21d x-check only
impact:  |q_i| · Y · σ_{i,daily} · sqrt(NAV|q_i| / (D·ADV_i))     [D = execution days]
borrow:  (days/252) · b_i · drifted short market value, daily accrual
fees:    repo costs.py commission/SEC/FINRA/CAT schedule, current + disclosed vintage
```
**[Evidence]** The organisers' files carry no quoted spread (S4-07), but WRDS is
allowed and the team holds CRSP daily bid/ask + TAQ through 2025-12 (X2): fit
half-spread by size×price bucket to 2015–2020 TAQ effective spreads; the
organisers-only bucket table is the labelled 2026 fallback. 0.5×/1×/2× IR
sensitivity mandatory. Single global `Y` (vol/sector buckets at
most); per-name `κ_i` unidentified = leakage if fitted on test. Reuse repo fee/
tier machinery but invert defaults: missing borrow = conservative schedule, not
cheapest tier (`costs.py:111` fix, 06 §6); `NAV` compounding, not $10m fixed.
**Borrow rule [freeze]:** mechanical dated "large cap" (e.g. **[Judgement]**
security `me≥$10bn` at formation — pick one, publish short-book mix by year);
headline sensitivity = mandate 50bp large / 5% other (drag at 200% gross =
0.50/2.75/5.00% NAV/yr — show all three). Stresses: top-decile conviction shorts
at 10–25%, locate-failure rate → 0 + replacement cost, recall covers. Fees never
enter forecast (Mandate §7; audit liquidity chars aren't a fitted fee curve).
**Accounting:** `R_NAV = r_f + Σ w⁻_i r^e_i − TC − Borrow − FundingSpread` on
start-of-period drifted weights; TC charged at execution close t+1 before
t+1→t+2 accrual; share/cash state (not weight jumps) so ramp cash drag + partial
fills are real; split long-debit financing vs short-rebate haircut (zero allowed
with reason) (04 S4-10). Turnover on executed daily share changes; exceptions count.

## 8. Experiment ladder with hard acceptance thresholds (freeze pre-OOS)
Registry counts *configurations* (λ grid, depth, support, p, bands…), collapsed to
effective-N by return-correlation clustering (05 §1.4). Nested select/confirm
(select 2019 → confirm 2020 or reverse; never both jobs both years); reuse count
enters N; per-step ΔIR split 2019 vs 2020 (COVID-only win = crisis claim).
**Global gates (all pre-OOS validation unless stated):**
- Promotion: Δ(net IR) > 0 **and** paired block-bootstrap (≥21d) 90% CI excludes 0;
  **[Judgement]** economic floor ΔIR≥0.15 for added-complexity steps (02 §7.2).
- New feature family: IC HAC-t (lag≥H) ≥3 **or** BHY-FDR 5% over full tested set;
  no post-selection t-stats as evidence (FGX lesson). GBM: + interaction stability.
- Final report: DSR with registry N in *per-period* SR units + skew/kurtosis,
  SR0 table (0.58@7…1.06@100…1.25@400, T=68), block-bootstrap IR CI, honest
  language if gates fail ("positive point estimate, unresolved at T=68").
  PBO/CSCV diagnostic only. **Failed gate is reported, never replaced post-OOS.**
- Economic gate: a step must raise validation net IC×TC toward the hurdle IC
  (§5); a gross-IC gain that lowers TC or raises cost fails (X4, X8).
- Yearly noise band: IC and net IR by year drawn with ±0.029 (yearly IC SE at
  monthly sd 0.10, `research/pre2021_noise.out`). At IC 0.02 a losing year has
  24% probability; kill/decay reviews fire only outside the band.
- Process gates (Plan L329–338 KEEP): timing assertions, executed-book compliance
  w/ logged exceptions, NAV/cost reconciliation, no padding, no silent delisting
  exit, capacity at compounded NAV, risk calibration reported.
| Step | Change vs prior | Promote iff (in addition to global gates) |
|---|---|---|
| E0 | E-LASSO MaInf (D6) → simple constrained QP, monthly, new simulator (12-signal = diagnostic) | Simulator reconciles to monthly engine; checker green. No IR gate (null baseline) |
| E1 | + factor/beta/size-aware construction (§§4–5) | Beta/sector/size bands hold; shadow-price cost of each limit reported |
| E2 | + diagonal uncertainty + frozen E-LASSO calibration scale; Ma1 vs MaInf on net IR (one trial) | Tradable-vs-full IC gap shown; heterogeneity gate (§3) reported either way |
| E3 | + liquidity filter, ledger costs, hysteresis, IR(k) scale | Net IR @ $1bn *and* stressed NAV/ADV; realised turnover + bp/trade reported |
| E4 | Weekly review + daily repair (vs monthly, identical costs) | `κ̂` estimated; weekly wins on net IR, not re-traded alpha (decay-adjusted) |
| E5 | ≤1 event/alt-data sleeve (§9 gates) | Vintage verdict + coverage cap + covered/uncovered test; subperiod sleeve if late-start |
| E6 | Agent multipliers vs `m≡1` (§9) | Counterfactual on validation; per-exception-type attribution; stability rate |
OOS evaluated once per frozen candidate; OOS variants are predeclared diagnostics,
not a menu (Plan L325 KEEP). Deck carries contamination sentence verbatim (L309).
E5 data gates: workbook rules 1–6 incl. vintage verdict, has-data ban, sleeve≤coverage,
delisted roster (Sears/Bon-Ton/Pier 1/GNC/Ascena/JCP) on every adopted asset (05 §3.2).
Analyst branch only if PIT consensus snapshots verified on onboarding day — else drop.

## 9. Agent spec (two roles, one model; 08 C4)
(a) **Exploration/triage** (pre-event, no trade impact): 4-question screen over
starter assets, denominator-logged; output is a deck artefact.
(b) **Exception sizing/triage** (risk layer): input = anonymised numeric diagnostics
only (no raw 8-K text in action path); output per flagged name = multiplier
`m∈[0,1]` or defer flag; code applies to target trade, re-solves, validates HARD
rules ("agent proposes, code enforces"). Explainer = this agent's audit log;
success metric = breaches caught / false alarms on validation + `m` vs `m≡1` ΔIR.
Triggers **[Judgement, freeze]**: constraint within x% of bound, |loss−model|>kσ,
earnings ≤3d, days-to-exit>D_max → budget ~290×10≈3k calls (not 710k). Decoding
contract: temp 0 (residual non-determinism disclosed), provider snapshot ID,
system-prompt hash; stability = k-sample action-agreement on validation sample.
Cache key = hash(rendered prompt incl. rounded numerics + tool/MCP responses +
formatter code version). Numeric checker rejects non-reconciling agent arithmetic.
Carbon Arc 20k tokens/day paced. Report counterfactual by exception type.

## 10. Module contracts + calendar
Contracts (Plan L388–398 KEEP + additions): `data/asof` also emits per-join
assertion results; `reporting` owns registry N + DSR + both turnover forms
(§9.1 cell prescribed avg×freq w/ declared dates, co-headline Σ/years — 08 C1) +
benchmark column (relative-wealth cumulative active, footnoted) + own-vs-Arcana
reconciliation + lens-2 emergence timeline. Persist: dated predictions, risk
inputs, target/actual holdings, trade/blocked logs, NAV ledger, versions, split
manifests, registry, cached agent decisions, per-position reason lookup.
**Exit criteria (must hold before the Mon Oct 26 freeze):** config+checker green on a
dummy book; simulator reconciles daily↔monthly on baseline; `reporting` emits
every §9.1 cell + 8 §9.4 exhibits from files on dummy holdings; crosswalk built.
| By | Must be true | Cut if late |
|---|---|---|
| **Sat Oct 24** | §2 config + ban list + checker green on a dummy book; daily $1bn simulator (t+1/t+2) reconciles daily↔monthly on a 2017 baseline; §5.5 fallback book end to end | Nothing; this is the floor |
| **Sun Oct 25 midday** | §7 costs calibrated; E-LASSO run on the finals panel through 2020-12 (authors' code, checksums verified, §3); decay `κ̂` (done, LESSONS 32); hurdle numbers filled with measured IC, TC, c | Carry MaInf only; Ma1 waits |
| **Sun Oct 25 night** | Risk + QP (§§4–5); E0–E3 on validation within the ≤12-config cap; N by the hurdle rule; agent exception cards for 2017–2020 queued overnight | Drop E4 (stay monthly + daily repair); drop E5 |
| **Mon Oct 26** | E6 agent vs `m≡1` on validation; `reporting` emits every §9.1 cell + 8 §9.4 exhibits from files; **freeze + single 2021-01..2026-08 run, evening** | No E6 ⇒ ship `m≡1`, report "agent not evaluated" |
| **Tue Oct 27** | Arcana upload + own-vs-Arcana reconciliation; deck from output files only; rule-change rerun drill (3 mock constraint sets); per-position Q&A drill | Carbon Arc demo goes before rehearsal does |
| **Oct 28–29** | Re-diff event instructions → edit config → rerun frozen strategy → show both numbers. No new signals, models or settings | — |

## 11. Drops, open clarifications, unresolved
**Dropped (do not revive at event):** dense `U_μ/U_β` SOC · power-cone optimiser ·
MIP · MPC/DP · daily alpha model · NN/transformer · options branch · IPCA-as-
forecaster · pure explainer agent · forced-cover on cap drift · present-day
listing filters · raw 8-K text in action path · README 0.99 headline · v1 `solve`.
**Ask organisers verbatim (at the event opening, 09):** 1) Arcana identifier/columns/weight
basis + PIT vintages? 2) Supplied benchmark file: TB3MS vintage + daily carry?
3) Does 200-floor bind *executed* holdings in ramp/liquidation; formation cost
inside measured window? 4) Judges' S&P series (price/TR) — beta line itself is
discretion, prepare daily-t defence. Plus: submission package beyond deck+holdings;
borrow/locate data if any; CA0065S volume units; consensus-asset existence.
**Unresolved until data runs (frozen protocol only):** `κ̂/Y`, IC-decay curve,
tradable-vs-full IC gap, short alpha in ≥$500m pool, daily/weekly net alpha,
147 lags/vintages (H2 rerun on E-LASSO done 2026-10-23: MaInf unharmed, Ma1 halved; D7, LESSONS 39), Carbon Arc
per-asset vintages. H5 resolved: dsf is price-only and labels add dividends back.
**Deck honesty pack:** contamination L309 · `P≠Σ` · gross-floor + conic→QP note ·
intraday-unprovable · failed gates reported · JKP 5-number bridge (US OLS 84.9 /
BY 77.3 / US Bayes 84.0 / global Bayes 84.9 / US|global 80.7, CAPM rates) ·
WP-vs-published years · snippet literature labelled hypothesis-only ·
hurdle slide (IC needed vs measured, §5) · yearly noise-band slide (§8).
If gates fail: fallback book + honest negative outscores a replaced threshold.

