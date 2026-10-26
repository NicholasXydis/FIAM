# Stream 6 — Repo evidence: what past work proves, disproves, or is silent on

**Scope.** Taildrop plan `fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md`
(cited as Plan §) judged against the final mandate `fiam/v4b/inputs/final_mandate.txt`
(cited as Mandate §), using only inspected repo files. Past work is treated as
evidence, never as optimality. Verdicts are **keep / fix / drop** for the *plan
choice* in light of the evidence; severity is the cost of getting it wrong at
$1bn under finals rules.

**Files inspected in full or in relevant part:** `README.md`, `RESULTS.md`,
`versions/README.md`, `versions/v1..v4/recipe.json`, `frozen/*.json`,
`tests/test_versions.py`, `tests/test_mechanics.py`, `tests/test_models.py`,
`fiam/book.py` (headers, `SIGNALS`/`LIMITS`/`NAV`, `solve`/`optimize_month`),
`fiam/costs.py`, `fiam/risk.py`, `fiam/vol.py`, `fiam/v2.py` (switches,
`cost_terms`/`trading_cost`/`rules`/`solve`, `short_ban`, `risk_terms`),
`fiam/v4/kit.py`, `fiam/mandate.py`, `fiam/checks/verify.py`, `run.py` header,
`out_r13_full.log` (monthly JSON lines + terminal summary).

## 0. Headline reconciliation — read this first

Three different "finals" headlines coexist and only one is traceable:

| Claim | Source | What it actually is |
|---|---|---|
| 16.0%/yr, IR 0.99, Sharpe 1.49, beta +0.06, scales to $5bn | `README.md:33,53-64` | **Untraceable.** No run artifact in the repo reproduces it. |
| Net 12.8%, IR 0.74 (1.16 pre-cost), Sharpe 1.07, beta −0.03, 296 names, 46%/mo turnover | `RESULTS.md:13-28` (code hash `6d995c6c18e22b1d`) | v1 book at $10m fixed NAV, monthly, first-round rules. |
| IR 0.99 at $10m but **0.45 at $1bn**, Sharpe −1.25 on 2016-20, 15 choices made with 2021-26 visible, breaks 4 finals rules | `versions/README.md:19-21` | v3 = the book the site/deck present. |

**Verdict: fix (Critical).** The README number is the v3 $10m number relabelled
as a finals book. At finals scale the same family is IR 0.45
(`versions/README.md:20`). The v4 finals book does not yet exist:
`versions/v4/recipe.json` is `"status": "in progress"`, `"fingerprints": {}`,
command `"(built from step 5)"`, protocol `"(written before any run, step 4)"`.
Plan §11 step 1 ("reconcile the current strategy with $1bn, the $500m short
floor and 200–500 holdings; inventory what OOS research has already been
seen") is therefore not optional housekeeping — it is the gating task.
Any plan language that treats an existing compliant baseline as available
(Plan §9 E0, §11 Day-1 hours 2–6 "audited compliant baseline") overstates
readiness. Correct alternative: strike the README headline from all finals
material; cite only `RESULTS.md` (v1, $10m, contaminated design) and the
v3-at-$1bn IR 0.45 as the honest starting points, both labelled as
researcher-contaminated per Plan §9.

Two further honesty numbers bound everything below (`RESULTS.md:185,234-251,259-260`):
1,665 fits / 141 shippable portfolios; deflated-Sharpe probability the edge is
real = **0.46** (0.19 at all 1,665 fits); IR 2023-26 = **−0.01**; same book on
2016-20 = **IR −1.00**, net −5.7%/yr, beta −0.25. Past results therefore
*disprove* stability of the shipped signal, whatever the 2021-26 headline says.

## 1. Ridge default (Plan §4) vs the shipped 12-signal equal-weight score

**Plan choice.** Pooled hierarchical ridge on the 147 characteristics,
family penalties $\sum_g\lambda_g\|\theta_g\|_2^2$, date-balanced loss
(Plan §4, lines 98-114). Mandate §3 requires ML/LLM/agentic forecasting
"strictly out of sample"; Mandate §7(1) bans full-sample feature selection;
§8.1 requires stated walk-forward splits.

**What past results PROVE.**
- The shipped book is *not* a ridge forecaster. It is an equal-weight mean of
  12 theory-signed rank-z signals (`fiam/book.py:38-51` `SIGNALS`,
  `build_signal`/`scores`), requiring ≥9 present (`MIN_SIGNALS=9`,
  `fiam/book.py:32`). The only "ridge" in v1 is the *optimizer* penalty
  $a^\top w-\tfrac12\cdot30\|w\|_2^2$ (`fiam/book.py:54,306`) — a
  concentration regularizer, not a return model. Conflating the two in a deck
  would be an error; Plan §4's ridge is a new build.
- Penalized-linear return models on this panel have *no* measured OOS
  predictive power: Ridge (template) OOS $R^2=-0.06\%$, elastic net
  $-0.05\%$, our 12-signal score $-0.01\%$ (`RESULTS.md:150-157`). "ML on the
  147: IC t 2.5–4.1, all lose money after costs" (`RESULTS.md:178`).
- The 12-signal set, `MIN_SIGNALS`, and all `LIMITS` were "chosen/set with
  2021-26 visible" (`fiam/book.py:31,37,53`). Under Mandate §7(1)/(8) and
  Plan §9's researcher-contamination paragraph, the 2021-26 record cannot
  certify this signal set. v2's frozen weights do improve discipline
  (`frozen/v2_params.json`: fitted 2015-01 to 2020-11, IC 0.0071/0.0062) but
  the *signal identities* remain the contaminated twelve.

**What they DISPROVE.** That equal-weighting 12 hand-picked characteristics
is a validated null to beat. Its OOS $R^2$ is zero and its 2016-20 IR is
−1.00 (`RESULTS.md:246`). Keeping it because it exists would violate the
brief of this stream and Plan §4's own promotion logic.

**What they say NOTHING about.** Whether a *family-penalized, date-balanced*
ridge beats equal weights. No run in `RESULTS.md` implements Plan §4's exact
loss (per-date $1/N_t$ weighting, per-family $\lambda_g$). The template
ridge $R^2$ is a pooled, presumably row-weighted fit — a different estimator.

**Verdict: keep the plan choice, drop the incumbent as default (High).**
Mathematically correct implementation detail the plan gets right and the
repo gets wrong: date-balancing. Row-pooled OLS/ridge minimizes
$\sum_t\sum_i(\cdot)^2$, so dense recent cross-sections dominate; Plan §4's
$\sum_t N_t^{-1}\sum_i$ is the correct loss if each *date* is one observation
of the premium. The repo's rank-z averaging is implicitly date-balanced but
imposes $\theta\in\{\pm1/12\}$ with no shrinkage estimation — strictly more
rigid than ridge and untestable as a $\lambda$ choice. E0 (Plan §9) must
therefore be redefined: E0 = Plan §4 ridge through the finals simulator,
with the 12-signal score retained only as a *diagnostic* comparator, not as
the compliant baseline.

## 2. GBT challenger (Plan §4) vs LightGBM evidence

**Plan choice.** One shallow GBT on identical features/labels/folds/optimizer;
promote only on net portfolio economics, calibrated magnitudes (Plan §4,
lines 116-121). Mandate §7(8): no hyperparameter tuning on the test period.

**PROVE.** LightGBM is the *only* model class with positive OOS $R^2$
($+0.08\%$ vs NN $-0.15\%$, `RESULTS.md:154-155`), and the stock-picker has
real rank information (IC 0.067, t=3.55, `RESULTS.md:179`). Walk-forward
LightGBM plumbing exists and is tested: `fiam/ml/teachers.walk_forward`
drops labels known inside the test year (`tests/test_models.py`
`test_teacher_drops_labels_known_in_the_test_year`).

**DISPROVE.** That predictive rank information survives construction and
costs: "ML blends and targets: best IR −0.15 — Rejected"
(`RESULTS.md:174`); deep-hedging/PPO "IR 0.70 to 0.41, not reproducible —
Removed" (`RESULTS.md:180`). For *volatility* forecasting LightGBM formally
failed its pre-registered gate: QLIKE wins 3/4 years but Diebold-Mariano
t = +1.31 (wrong sign for the $t<-2$ requirement), so HAR was used
(`frozen/vol_check.json`: `"passed": false, "used": "har"`;
`fiam/vol.py:104-107`). This is the repo's best piece of model-selection
discipline and directly supports Plan §4's "MSE alone does not settle it."

**SILENT.** Whether a *shallow, heavily regularized* GBT with a small
recorded search budget (Plan §4) beats ridge through the *finals*
constructor. Past GBT runs used the v1 monthly $10m constructor, microcap
shorts, and 100-name-era books — none transfer (see §7 below).

**Verdict: keep as challenger only (Medium).** The evidence justifies
exactly Plan §4's posture — one challenger, predeclared budget, net-IR
promotion — and forbids anything stronger. Two fixes: (a) Plan §4 must
state the GBT's forecast-to-$\mu$ calibration explicitly (isotonic/linear
on held-out predictions); the repo's failure mode was feeding rank scores
into a score-maximizing optimizer (`fiam/book.py:284-306` uses `signal`
directly as $a$), which silently assumes score ∝ expected return with
unit scale. (b) The vol-model gate (`fiam/vol.py:106`: `wins>=3 and t<-2`)
should be reused verbatim as the template for the GBT gate — it is the one
promotion rule in the repo that was written before its result.

## 3. Monthly core + weekly review + daily event overlay (Plan §1, §6)

**Plan choice.** Monthly information refresh, weekly trade review, daily
risk exceptions; delayed close-to-close clock (Plan §1, §6 lines 233-241,
§7 lines 269-275). Mandate §4 permits but does not require daily trading
and explicitly credits "we tested daily, it did not survive costs";
Mandate §7(1) fixes the clock: information through $t$ forms the book at
close $t{+}1$, first earned return close $t{+}1\to t{+}2$.

**PROVE.** Nothing about weekly or daily alpha. Every backtested book in
the repo is monthly: `FIRST_FORECAST/LAST_FORECAST` month-ends,
`N_HOLDING_MONTHS=68` (`fiam/book.py:28-29`), `walk`/`backtest` step by
holding month, turnover quoted one-way monthly 46% (`RESULTS.md:26`).
`out_r13_full.log` is daily *marking* of a monthly book ("monthly economic
book; native daily total-return marks", 68 monthly formations) at $10m —
it proves the daily NAV/beta accounting path runs, not that daily trading
pays. Its position counts (438–500) and largest positions (~3.2–3.7%)
also belong to a different, non-finals constructor and must not be cited
as finals evidence.

**DISPROVE.** The monthly book's robustness to timing is actually
*reassuring* for a slow core: "a day's delay costs nothing"
(`RESULTS.md:183`). That cuts *against* needing daily execution for the
core signal — consistent with Plan §4's "~21-day horizon, not a forecast
of tomorrow."

**SILENT (the important part).** (i) Event-overlay alpha: text signals
were all rejected once neutralized (best t=2.1, `RESULTS.md:173`); the
analyst agent's 2021-26 IC is −0.003 and its student model's −0.021
(`RESULTS.md:199,222`). There is currently *no* validated fast signal to
put in the overlay. (ii) Weekly-vs-monthly net value: never run.
(iii) The finals $t{+}1/t{+}2$ clock: the repo earns `ret_exc_lead1m`
from the formation month-end; no code path implements the mandated
two-close delay on daily data.

**Verdict: fix (High).** Keep the *architecture* (it matches Mandate §4's
endorsed "monthly/weekly core + daily overlay"), but the plan must label
the overlay as **unfunded research, default OFF**, promoted only via
Plan §9 E5 on pre-2021 validation. Mathematically, weekly review of a
21-day-horizon forecast is only justified if signal decay is measured:
with Gârleanu–Pedersen decay $\mu_{t+k}=\rho^k\mu_t$, trading weekly
rather than monthly earns at most the decayed remainder while multiplying
spread/impact events ~4×; at the repo's measured 46% monthly one-way
turnover, naive weekly re-optimization implies ~2,400% annualized —
exactly Mandate §4's transfer-to-market-makers regime. The simulator
(Plan §11 step 2) must be built before any frequency claim; `fiam/book.py`
cannot answer frequency questions at all because its label, drift, and
cost functions are hard-wired monthly (`drift`, `trading_cost`,
`month_record`).

## 4. Risk model (Plan §5) vs `fiam/risk.py` + `fiam/vol.py`

**Plan choice.** $\Sigma=BF B^\top+D$, shrunk exposures, EW factor
covariance, floored idiosyncratic variances, robust beta constraint
$|\hat\beta^\top w|+z\sqrt{w^\top U_\beta w}\le\epsilon_\beta$
(Plan §5). Mandate §3.3: judges estimate realized beta daily *and*
monthly; "materially different from zero" = directional strategy.

**PROVE.** A working monthly factor risk model exists: sectors + 5 styles
(size/value/momentum/low-vol/quality, `fiam/risk.py:14-15`), sqrt($me$)-
weighted cross-sectional factor returns (`fiam/risk.py:37-49`), EW
covariance with 36-month half-life using only realized factor returns
(`fiam/risk.py:53-60`), specific risk from HAR (`fiam/risk.py:64-70`,
`fiam/vol.py`). Its full-record calibration is respectable: v2@\$10m bias
1.004, VaR95 1 exception vs 3.4 expected (`frozen/risk_check.json`).
v2 already consumes it in-constructor via eigen-loadings
(`fiam/v2.py:291-314` `risk_terms`/`variance`).

**DISPROVE / LIMITS.**
- Pre-2021 check-sample calibration is poor: bias 1.38–1.41 (realized vol
  ~40% above forecast), VaR99 Kupiec p=0.013 (v1 check) — the model
  *underforecast* risk exactly in the validation window Plan §9 would
  use for promotion (`frozen/risk_check.json` "check" blocks).
- It is monthly. Plan §5 needs daily-refreshed price risk (252d
  exposures, 20–60d vol half-lives); `fiam/risk.py:16` (`HALF_LIFE=36`
  *months*, `MIN_MONTHS=24`) cannot be re-labelled daily. No $U_\beta$
  exists anywhere; beta control today is a point-estimate band
  ($|\beta^\top w|\le0.02$, `fiam/book.py:300`) on a learned beta whose
  own frozen horse-race it *lost*: Welch 0.518 < calibrated 0.536 <
  learned 0.567 < beta_60m 0.620 (`frozen/v2_params.json`
  `beta_errors`). The README's "beta held at zero by a LightGBM model"
  (`README.md:71-72`) advertises the third-best estimator.
- Realized neutrality is weaker than the headline: full-period monthly
  beta −0.03 (se 0.09) but **daily beta −0.10 (se 0.03, t=−3.67)** and
  2016-20 beta −0.25 (`RESULTS.md:135-140,248`). Under Mandate §3.3's
  daily-beta scrutiny the v1 book would be flagged. Plan §5's warning
  ("insignificant with wide CI is weak evidence") applies to our own
  monthly number.
- Construction v2's extra neutrality *hurt*: factor-neutral variant
  IR −0.89; every v2 construction rule alone lowers IR
  (`RESULTS.md:175-177`). Evidence for Plan §3/§5's "price each limit,
  don't neutralize everything."

**Verdict: fix — reuse the design, rebuild at daily frequency (High).**
Correct alternatives: (a) keep $BF B^\top+D$ but re-estimate $F$ from
daily factor returns with Ledoit–Wolf/EW shrinkage and horizon-scale
$\Sigma_{t,H}$ (Plan §5); the monthly $F$ in
`frozen/risk_factor_returns.parquet` is not reusable as a daily input.
(b) Default hedge beta = Welch (frozen winner), learned beta demoted to
challenger. (c) Until $U_\beta$ is estimable, implement Plan §5's
fallback (slow/fast/downside beta scenarios) — the panel already carries
`beta_60m`, `beta_dimson_21d`, `betadown_252d`, `betabab_1260d`
(`fiam/book.py:97-99`), so this is cheap. (d) Vol-targeting/brake must
not be inherited from v3: vol-target variants scored IR 0.15–0.34 and
v3 breaks 4 finals rules (`RESULTS.md:170`, `versions/README.md:21`);
Plan §12-13's fixed-policy counterfactual is the right treatment.

## 5. Turnover penalty / cost-aware objective (Plan §6) vs v1/v2 constructors

**Plan choice.** Minimize $\tfrac\gamma2 w^\top\Sigma w-\mu^\top w
+\rho\sqrt{w^\top U_\mu w}+C(q)+$ borrow $+\eta\|w\|^2$ with
$C(q)=\sum s_i|q_i|+\sum\kappa_i\sigma_i|q_i|\sqrt{NAV|q_i|/ADV_i}$
(Plan §6). Correctly identified as conic, not a plain QP (Plan §6:199).

**PROVE.** The repo contains *both* endpoints and their measured costs:
- v1 has **no** turnover penalty, no cost term, no variance term — just
  $a^\top w-15\|w\|^2$ s.t. gross=1.6 exactly, dollar/beta/risk/sector
  bands, sign-fixed 1.5% caps (`fiam/book.py:292-313`). Result: 46%
  one-way monthly turnover, costs 5.13%/yr = 29% of gross, IR 1.16→0.74
  (`RESULTS.md:17,26-27,124`). Costs are charged *ex post*
  (`trading_cost`), never optimized.
- v2 implements the convex precursor of Plan §6: per-name linear +
  sale-fee + $|q|^{1.5}$ impact + borrow
  (`fiam/v2.py:317-340` `cost_terms`/`trading_cost`/`convex_cost`),
  optional turnover budget and cost budget constraints
  (`fiam/v2.py:360-419`), dual/shadow-price recording
  (`fiam/v2.py:455-460`). Measured effect of turnover control in the
  old search: "Turnover penalty 0.49 to 0.54" vs shipped 0.70-0.74
  (`RESULTS.md:167,171`) — i.e. at $10m/monthly it *cost* IR.

**DISPROVE (at finals scale, by arithmetic).** That $10m result does
not transfer, and citing it against Plan §6 would be an error. Impact
in both cost models scales as $\sigma\sqrt{Q/ADV}\cdot Q$ dollars,
i.e. $NAV^{3/2}|q|^{3/2}$; moving $10^7\to10^9$ multiplies the impact
*rate* per dollar traded by $\sqrt{100}=10$ at fixed weights. The repo
confirms the consequence empirically: v3 IR 0.99 @ $10m → 0.45 @ $1bn
(`versions/README.md:20`). At $1bn the no-penalty v1 objective is
mathematically misspecified — it optimizes gross alpha while the
binding term is the one it omits.

**SILENT.** Values of $\gamma,\rho,\eta,\kappa$; whether the ellipsoidal
$\rho\sqrt{w^\top U_\mu w}$ term beats v2's quadratic risk penalty
(`risk_lambda=0.521`, fitted on "v1 books 2017",
`frozen/v2_params.json` — a thin, partly in-sample calibration that
must be refit pre-2021 under the finals universe).

**Verdict: keep Plan §6, build on v2's convex cost code (Critical if
omitted).** Reuse `fiam/v2.py` `cost_terms/trading_cost/rules/solve`
(including CLARABEL→SCS fallback and 1e-3 feasibility acceptance,
`fiam/v2.py:440-453`) as the starting constructor; discard `fiam/book.py`
`solve` for finals (fixed gross equality, $10m share-rounding, no costs).
Two mathematical corrections to carry into implementation:
(1) turnover for reporting must be $\tfrac12\sum|w-w^-|$ on *drifted*
$w^-$ (Mandate §9.3; Plan §10) — `fiam/book.py:361` halves correctly
but v1's $w^-$ is monthly-drifted at fixed $10m NAV, so daily/weekly
turnover needs a new drift path. (2) Holding period $\ne$
1/turnover at 200% gross (Mandate §9.3); report
$\overline{\text{gross}}/\text{annual turnover}$ labelled as an
approximation or measure directly (Plan §10 agrees).

## 6. Cost model (Plan §6-7) vs `fiam/costs.py`

**Plan choice.** Separate trading/borrow/financing; disclosed current
schedule + conservative flat alternative (50bp large-cap / 5% other
borrow, Mandate §7); participation limits $NAV|q_i|\le p\,ADV_i$ and
liquidation-days caps (Plan §7).

**PROVE — this is the repo's strongest reusable asset.**
`fiam/costs.py` models IBKR Pro fixed commission with min/1%-cap, SEC
31, FINRA TAF (per-trade cap) and CAT fees (lines 15-22), half-spreads
calibrated to CRSP closing quotes 2015-20 only (lines 30-31, 49-65;
test-pinned in `tests/test_mechanics.py`
`test_spread_calibration_stops_in_2020`), square-root impact
$Y\sigma\sqrt{Q/ADV}$ with $Y=1$ (line 24, 154), short-interest-tiered
borrow 0.30%/1%/3%/8% with 1% micro floor (lines 26-27, 109-136),
financing at benchmark −0.50% (line 29). Hand-checked to the cent in
`tests/test_mechanics.py:68-113`. Measured v1 decomposition: impact
2.24% > borrow 1.26% > spread 0.87% > financing 0.50% > commission
0.27% (`RESULTS.md:119-124`) — already impact-dominated at $10m,
which is why $1bn breaks it.

**DISPROVE / GAPS vs finals + Plan §7.**
- `Model.nav` defaults to $10m and is *fixed* (`fiam/costs.py:40`);
  `fiam/book.py:35` `NAV=10_000_000` drives whole-share rounding.
  No compounding-NAV path exists in v1 (Mandate §3.1/§3.3 requires it;
  capacity tightens as the fund grows).
- `dolvol_126d` (126-day dollar volume) is used as the ADV denominator
  (`fiam/costs.py:154`, `fiam/v2.py:325`). Plan §7:254 explicitly warns
  against "monthly volume mislabeled as daily"; a 126d smoothed ADV
  understates impact in falling-liquidity states and cannot support
  a daily participation constraint. Needs lagged daily ADV (CA0065S /
  finals daily file) with downward stress.
- No participation cap, no liquidation-days cap, no locate-failure or
  recall modelling in v1; v2's only capacity device is
  `cap=min(cap, 0.4*dolvol/capital)` (`fiam/v2.py:369`) — a *position*
  cap equal to 40% of 126d dollar volume, far looser than Plan §7's
  $p=10\%$ *daily-order* cap and silent on multi-day execution.
- Missing borrow data defaults to the cheapest tier
  (`fiam/costs.py:111` `fillna(0.0)` → 0.30%): optimistic for exactly
  the hard-to-borrow names the finals floor targets. Must be replaced
  by the Mandate §7 conservative schedule as the *default*, with the
  fitted tiers as sensitivity — the reverse of the current setup.
- `out_r13_full.log` confirms cost accounting runs daily-marked, but
  its terminal summary self-reports "short locate/permission evidence
  unavailable; reference prices are not live execution fills; dated
  delisting payout unavailable" — i.e. the cost numbers are model
  charges, not execution evidence. Do not cite r13 costs as fills.

**Verdict: keep the engine, fix scale/ADV/borrow-default/caps (High).**
Mathematically correct borrow accounting (already right in code, keep):
charge on short notional only, $b_i\max(-w_i,0)/12$ monthly
(`fiam/costs.py:160`), matching Plan §6's $H\sum b_i\max(-w_i,0)/252$
at daily frequency. Break-even honesty check to retain: v1 edge dies
at 2.7× modelled costs (`RESULTS.md:125`); README's "4.1×" and "$5bn"
(`README.md:63-64`) have no supporting artifact — drop.

## 7. First-round artefacts invalid under finals rules

Each item: finals rule → repo violation → required rebuild.

1. **Microcap / sub-$500m shorts.** Mandate §2/§3.1: shorts need
   mktcap ≥ $500m *at formation*. Repo: universe screen is `me>=300`
   ($m) for *both* legs (`fiam/book.py:114`); shorts are 68% small/micro
   (20% micro), median short mktcap $1.9bn but average $6.5bn with a
   long micro tail (`RESULTS.md:73-75`). v2's `short_ban`
   (`fiam/v2.py:122-135`) bans micro/nano + borrow≥3% + options/event
   flags for *new* shorts only — closer, but it is a size-group ban,
   not a dated $500m formation test, and held names are grandfathered
   (`fiam/v2.py:375-377`). **Severity Critical** — hard-rule breach;
   short alpha must be re-measured inside the eligible pool (Plan §2).
   Note Plan §2:49 correctly warns there is no finals $300m floor —
   the repo's $300m screen must not be carried over as if official.
2. **100-name floor.** Mandate §3.1: 200–500 combined. Repo still
   encodes round one: `Mandate.names_min=100` (`fiam/mandate.py:31`),
   verifier rule `"positions 100-500"` (`fiam/checks/verify.py:33`),
   test expects 99 names to fail only that rule
   (`tests/test_mechanics.py:272`), compliance table "100 to 500"
   (`RESULTS.md:100`). v1 averaged 296 names so it would usually pass
   by luck, but nothing *enforces* 200, and Plan §6's support/min-weight
   machinery (300-name support, 0.10% min, $N_{eff}$ reporting) does
   not exist — v1 drops $|w|\le10^{-5}$ (`fiam/book.py:313`), the
   "tiny-weight padding" Plan §6/§9 ban. r13's books show why this
   matters: nominal ~500 names but $N_{eff}\approx$134–168 and dozens
   of <1bp positions. **Severity Critical.**
3. **Monthly-only engine, wrong clock.** Mandate §7(1) $t\to$close
   $t{+}1\to$ earn $t{+}1\to t{+}2$; repo forms at month-end and earns
   `ret_exc_lead1m` immediately. No daily decision path, no
   drifted-daily-weights turnover, no daily benchmark
   ($b_d=TB3MS/25200+0.04/252$, Mandate §9.2). **Severity High.**
4. **Fixed $10m, no $1bn capacity.** Mandate §3.3 compounding $1bn.
   Repo: fixed NAV everywhere above; whole-share rounding material
   only at $10m (`fiam/book.py:34` admits it "only matters for
   rounding"); no initial-deployment ramp (first month buys the whole
   book in one step, `tests/test_mechanics.py:94-98`); no
   days-of-ADV exhibits (Mandate §9.4). v3's own $1bn rerun (IR 0.45)
   is the proof this is binding, not cosmetic. **Severity Critical.**
5. **Position cap.** Finals 5% (Mandate §3.1). Repo internal cap 1.5%
   (`fiam/book.py:54`) is *stricter*, so compliant, but Plan §2/§6's
   proposed 1% internal cap + ADV caps must replace the flat 1.5%
   at $1bn (1.5% = $15m = 75% of a $20m-ADV name's day). **Fix, Medium.**
6. **Gross as equality.** v1 forces gross=1.6 exactly
   (`fiam/book.py:295`); Mandate §3.1/Plan §2 treat 200% as a ceiling.
   Forced gross + 200-name floor + min-weight can be jointly
   infeasible in illiquid months; Plan §6's $\|w\|_1\le2$ + repair
   hierarchy is the correct form. **Fix, Medium.**
7. **Contaminated design + seen holdout.** Signals/limits chosen with
   2021-26 visible (§1 above); 1,665 fits searched incl. a 1,139-combo
   search scoring +1.78 in-sample / +0.33 unseen and agent search
   −1.18 to −2.08 unseen (`RESULTS.md:181-182`). Under Mandate §5.2/
   §7(8) and Plan §9, 2021-26 is a *labelled walk-forward evaluation
   with prior exposure*, never a holdout. Any reuse of frozen
   September books (`frozen/september_*.csv`) as finals evidence is
   invalid. **Severity Critical for credibility.**
8. **Missing-return = cash.** `drift`/`month_record` book missing
   returns at cash/zero and record them (`fiam/book.py:394`;
   `tests/test_mechanics.py:168-184`). Mandate §7(6) + Plan §7 require
   explicit delisting/stub handling; zero-booking flatters shorts in
   collapsing names. The −30% Shumway stress exists
   (`fiam/book.py:63`, `RESULTS.md:261`: IR 0.73/0.74 — reassuring at
   monthly $10m) but daily stubs are unhandled. **Fix, High.**

## 8. Reusable vs must-rebuild

**Reuse (with stated fixes) — because tested, not because present:**
- `fiam/costs.py` fee/spread/impact/borrow engine + its hand-checked
  tests; change NAV to compounding, ADV to lagged daily, borrow
  default to Mandate §7 conservative schedule.
- `fiam/v2.py` convex cost-aware constructor skeleton (`cost_terms`,
  `trading_cost`, `rules`, `solve`, dual recording, feasibility gate)
  as the base for Plan §6; add $U_\mu$ term, support selection,
  participation caps, dated $500m short test.
- `fiam/risk.py` factor-model *design* + `fiam/vol.py` HAR + QLIKE/DM
  gate; re-estimate daily, refit all frozen numbers pre-2021 on the
  finals universe (`frozen/v2_params.json`, `risk_check.json`,
  `vol_check.json` are $10m/monthly/microcap-contaminated as numbers).
- Walk-forward discipline code: `teachers.walk_forward`, analyst
  firewall (`tests/test_models.py`), spread-calibration cutoff,
  `settle`/exits logic (`fiam/book.py:127-145`) extended to daily stubs.
- Version/freeze machinery: `versions/*/recipe.json` fingerprints
  enforced by `tests/test_versions.py` — exemplary; apply to v4.
- Mechanics tests as *templates* (drift, costs, whole shares, rule
  breaches) — rewrite expectations to finals rules (200–500, 5%,
  $500m shorts, daily clock).

**Must rebuild (do not patch):**
- Finals simulator: daily information clock ($t{+}1/t{+}2$), drifted
  holdings/cash ledger at compounding NAV, multi-day participation-
  limited execution incl. initial ramp, delisting stubs. Nothing in
  `fiam/book.py` `walk/backtest` does this.
- Forecaster: Plan §4 ridge (+ GBT challenger) with pre-2021-fitted
  families. The 12-signal composite, crowd emulator
  (`frozen/crowd_emulator.json`: 2025-26 $R^2$ −0.29/−0.14 — broken
  out of period), and analyst text channel (IC≈0) contribute no
  validated alpha; keep only as reported negatives (Mandate §4/§5
  credit honest negatives).
- Support selection + min/max-weight two-stage solver (Plan §6);
  verifier + mandate defaults (200 floor, daily beta, §9.1 table,
  §9.4 exhibits incl. days-of-ADV and short-mktcap distributions).
- `fiam/v4/kit.py` is **not** a strategy module — it is the USB
  export/setup/doctor kit (header line 1). There is no v4 forecasting
  or construction code to reuse; `versions/v4/recipe.json` "in
  progress" is accurate. Plan §11's module contracts
  (`data/asof … agent`) are greenfield.

## 9. Summary verdicts

| Plan choice | Verdict | Severity | One-line reason |
|---|---|---|---|
| Hierarchical ridge default (§4) | keep; drop 12-signal incumbent | High | Incumbent OOS $R^2\approx0$, contaminated, 2016-20 IR −1.00 |
| Shallow GBT challenger (§4) | keep, challenger only | Medium | Only +$R^2$ class, but −0.15 best net IR historically |
| Monthly core + weekly + daily overlay (§1/§6) | fix: overlay default OFF | High | No validated fast signal; no daily engine; delay costs nothing |
| Dynamic factor risk model (§5) | fix: rebuild daily, Welch beta | High | Monthly model underforecast pre-2021; daily beta −0.10*** |
| Cost/turnover-aware objective (§6) | keep; build on v2 convex code | Critical | v1 objective omits the binding term at $1bn (0.99→0.45) |
| Cost model (§7) | keep engine; fix NAV/ADV/borrow/caps | High | Best asset in repo, but $10m/126d-ADV/optimistic-default |

**Unresolved gaps (no repo evidence either way):** daily/weekly net
alpha of any signal; $U_\mu$/$U_\beta$ estimability; $\kappa$ calibration
at $1bn; short alpha inside the ≥$500m pool; Carbon Arc / CA0035
incremental value (workbook and schemas uninspected, Plan §8:289);
Arcana upload schema and risk-model vintages (Plan §11 clarifications).
Each must be settled on pre-2021 validation (Plan §9 E1–E6) — the repo
proves the *discipline* for doing so exists (vol gate, freeze tests,
1,665-experiment ledger) even where it disproves the *strategies* that
discipline was applied to.
