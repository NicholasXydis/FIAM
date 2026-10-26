> **Superseded for current state by [`HANDOFF_2026-10-26.md`](HANDOFF_2026-10-26.md).**

# Handoff — v4b E-LASSO 2021–2026 diagnostic

**Prepared:** 2026-10-25  
**Workspace:** `/home/drewclaw/Forkfiam`  
**Branch:** `feat/finals-v4-drew` at `b5bdf0d9e0eec6238bb81f04095bf4debf14d38d`  
**State:** audit complete; frozen candidate rejected; changes uncommitted.

> This is a diagnostic handoff, not a promotion. The frozen 2020-12 E-LASSO
> candidate is **rejected**. E3 is noncompliant and `eligible_for_oos=false`.
> Do not sign-flip, rescue, or tune anything on 2021–2026.

---

## 0. Read this first

If resuming, read in this order:

1. [`DECISIONS.md`](DECISIONS.md) — binding decisions, especially D6–D10.
2. This file — current state, session provenance, open directives.
3. [`OOS_RESULTS.md`](OOS_RESULTS.md) — corrected results, causes, verdict, §7a external audit.
4. [`OOS_FREEZE.md`](OOS_FREEZE.md) — frozen object, data amendment, hashes.
5. [`RISK_COST_AUDIT.md`](RISK_COST_AUDIT.md) — risk/cost implementation, corrected OOS costs/compliance.
6. [`RETURNS_AUDIT.md`](RETURNS_AUDIT.md) — return defects, corrected native addendum, external evidence.
7. [`CONTINUATION_STATUS.md`](CONTINUATION_STATUS.md) — checklist and next-work framing.
8. [`README.md`](README.md), [`REVISED_PLAN.md`](REVISED_PLAN.md) — project map and design.

The technical authority is the docs/artifacts, not a chat transcript. The two
local session logs below are provenance for how the work was directed.

---

## 1. Sessions reviewed (the two named in `CONTINUATION_STATUS.md`)

### 1.1 Claude session

| Field | Value |
|---|---|
| Session ID | `3fc28de7-893e-4d32-927a-1dc18676d593` |
| Path | `/home/drewclaw/.claude/projects/-home-drewclaw-Forkfiam/3fc28de7-893e-4d32-927a-1dc18676d593.jsonl` |
| Date | 2026-10-23 |
| Size | 1,532 JSONL lines |
| CWD / branch | `/home/drewclaw/Forkfiam`, `feat/finals-v4-drew` |

What the user asked for:

- Evaluate the latest Taildrop plan against the new final mandate and the
  relevant research, using past repo/QUARCC-Black work as **evidence only**,
  never as an assumed-optimal solution.
- Continue planning in `v4b/`; persist conclusions and lessons.
- Choose between MLP and GBT; enforce the short floor only on rebalance dates;
  approve no Arcana upload before the run; choose the ADV fallback.
- Test the unmodified authors' E-LASSO code on our data.
- Then: **“yes please replace with E-Lasso. and persist in ALL documents and
  files to persist that decision.”**

Key outcome: D6 was created; E-LASSO became the forecaster everywhere in
`v4b/` (docs, config, code, tests, memory), with MaInf primary and Ma1 the
single alternate. The final Claude response reported 21 tests passing at that
point. It also said the next step was the engine, then Ma1-vs-MaInf on net IR.

Important nuance from the same session: the user explicitly said not to rely
on outside repositories — “i told you we shouldnt care about outside
repositories, we are only working in v4b with OUR plan.” Later branch/external
work was therefore treated as an **audit of causes**, not as a replacement
plan or a rescue.

### 1.2 Muse session

| Field | Value |
|---|---|
| Session ID | `01a16aed-f8a1-78f3-8f99-773abeedb888` |
| Path | `/home/drewclaw/.local/share/muse/sessions/2026/10/23/01a16aed-f8a1-78f3-8f99-773abeedb888/session.jsonl` |
| Date | 2026-10-23 |
| Size | 8,606 JSONL lines |
| Name / model | `autumn-gemini` / `muse-wonder-full-1.0` |
| CWD | `/home/drewclaw/Forkfiam` |

What the user asked for, in three directives:

1. **Continue development exclusively in `v4b/`; read everything and the
   latest Claude session.** The prompt reiterates: E-LASSO is the forecaster
   everywhere; MaInf is primary; Ma1 is the one alternate, chosen only on net
   return after costs once the engine exists. The requested order was:
   finish the forecaster, then the risk model(s), and **only finally** build
   the optimizer.
2. **“go”** — proceed with implementation.
3. Later, the optimizer/backend directive:

   > “reference for optimizer : https://github.com/cvxgrp/cvxportfolio … then
   > move v4b to forkfiam/fiam/... AND remove all of claude status as
   > contributor in all of local commits and commit to github inside this
   > branch : https://github.com/niccc333/Forkfiam/tree/Risk-%26-AI-Agents-Improvements
   >
   > the optimizer must take the outputs of forecaster and outputs of risk as
   > inputs.”

How that directive stands now:

- `v4b` **is** under `fiam/v4b/`; the package path and commands use
  `fiam.v4b`.
- The optimizer **does** consume forecaster and risk outputs:
  `engine/optimize.py` takes `Formation.mu` (centred, calibrated, horizon
  converted) and the risk snapshot (`B`, `F`, `F1`, `d`, `beta`, etc.).
- The `cvxportfolio` reference was implemented as a **research probe**, not a
  replacement execution engine.
- The commit/attribution part is **not done**. There are no local commits for
  this audit; `fiam/v4b/` is entirely untracked. See §9.
- No raw session transcript was copied into the repository. The exact IDs and
  paths above are the session record; the transcripts remain local.

The two sessions are consistent: Claude established D6 (E-LASSO/MaInf), Muse
continued with the engine/risk/optimizer and gave the later repo/commit
directive. The 2021–2026 audit was performed after those sessions and is
recorded in the `v4b` files, not fully in either transcript.

These logs live outside the repository and may be pruned by their tools. If
they must survive long-term, copy them to a private archive; do not commit raw
chat transcripts without checking for credentials or sensitive content.

---

## 2. Bottom-line verdict

**Reject the frozen 2020-12 E-LASSO candidate.** The out-of-sample
cross-section was negative from the first month, the short leg lost in five
of six years, costs consumed any gross edge, and the executed book violated
the mandate’s construction/risk limits. The two positive calendar years did
not deliver positive active return.

**E3 is diagnostic only.** It is not a final book and cannot be promoted.
`eligible_for_oos=false`, `diagnostic_only=true`.

**No rescue is permitted.** No sign flip, no reweighting on 2021+, no
cost/band/model tuning on 2021+. A monthly-refit E-LASSO, a new signal, E4
daily repair, or a regime overlay is a **new hypothesis** and needs a **new
pre-registered holdout** (for example 2027+).

---

## 3. What was completed

### 3.1 Plan evaluation and design

- Evaluated the Taildrop plan against the final mandate and the research
  source pack. Recorded nine evidence streams and the synthesis in
  `EVALUATION.md`, `eval/01..09`, and `REVISED_PLAN.md`.
- Corrected the old repo’s non-finals assumptions: 100 names, $10m NAV, gross
  as equality, both-leg market-cap floor, no embargo/effective-trials gate,
  uncalibrated costs, leakage holes.
- Kept past repo/QUARCC-Black/Forkfiam work as evidence only, per the user’s
  instruction. The branch audit is explicitly separate from the frozen test.

### 3.2 Forecaster

- Kept the authors’ E-LASSO R code byte-for-byte in
  `external/elasso/` with `SHA256SUMS`.
- Built our input contract: 147 characteristics, month-`t−1` characteristics
  matched to month-`t` returns, winsorise/standardise/missing-to-zero,
  market-cap WLS weights, training label `ret_exc_lead1m`.
- **D6:** E-LASSO is the forecaster; `Elasso_MaInf` is primary; `Elasso_Ma1`
  is the one alternate. The MLP/GBT/ridge are baselines only.
- **D7:** engine-facing forecasts are centred and calibrated:
  `mu_tilde = scale * (mu - median_eom(mu))`, then horizon-decayed. Frozen
  MaInf scale 0.547, kappa 0.00524 (half-life 132 sessions); Ma1 scale 0.590,
  kappa 0.0697 (half-life 10 sessions).
- Frozen 2020-12 coefficients are applied to **every** 2021+ month. There is
  no OOS refit. The formula was checked against the authors’ R output on a
  target month to machine precision (max difference 1.8e-15).
- Pre-run finding that mattered: the frozen MaInf cross-section had a
  **negative** 2021–2026 rank IC before the OOS run. It was disclosed and the
  run was not changed after seeing it.

### 3.3 Risk model

- **D8 freeze:** assigned exposures, daily Barra-identified WLS factor
  returns, EWMA-84 factor covariance with Newey–West autocovariances and
  exact H-session scaling, correlation-stressed second covariance, and
  EWMA-168 specific variances with 25% sector-median shrink and a 5% floor.
- Hedge beta is the frozen 50/50 daily-Vasicek / panel-60m blend, refreshed
  weekly; the same market column is the hard beta band.
- Known bias, not fitted away: realised/predicted vol is 1.29–1.51; the
  ±0.02 nominal beta band is not statistically robust at the per-name level
  (median SE 0.021, p90 robust bound 0.052).
- No regime multiplier was silently added.

### 3.4 Monthly controller / engine

- Built the E0–E3 ladder, mandate checker, fallback, daily simulator, cost
  model, support/optimizer, and cohort reconciliation.
- Repaired the support cost (the old term was ~300–400× the fill model’s
  impact), cost units, incumbent impact credit, support cache key, trial
  gross, hard net band, and fill-matched sigma.
- State is actual executed holdings and compounded NAV, not an assumed $1bn
  target book. Missing shorts remain liabilities; costs use observable
  inputs; the checker records actual trades and drifted books.
- Added paired IR bootstrap, chronological diagnostics, stress/spread checks,
  and a float64 monthly cohort reconciliation (max gap 1.4e-15 after the fix).
- **D9 result:** E0–E3 each completed all 48 formations (2016-12..2020-11) at
  $1bn, but **no book is eligible**. E3 net IR −0.139, gross IR 0.583,
  annualised active mean −0.75%; it still had 2,041 executed rule/capacity
  breach rows. Fallback had 5,856. MaInf stayed primary; Ma1 was not promoted.

### 3.5 Native Nautilus OOS diagnostic

- Ran the frozen E3 through 2021-01-04..2026-08-31 using **native
  NautilusTrader 1.230.0 orders, fills, positions and account state**.
- Daily ledger and holdings are native-derived; native CSV/tearsheet export
  was disabled for this run to bound memory (the earlier attempt was killed
  during native report rendering at ~14 GB swap).
- One-shot design: no 2021+ result was used to change a coefficient, band,
  cost, or model choice after the run started.
- No Arcana upload occurred.

### 3.6 Data correction

- The first 2026 run used raw, non-split-adjusted `dsf_mini`
  `daily_return`/`close`; it produced spurious split jumps. It is preserved at
  `out/engine/nautilus_oos_invalid2026.log` and
  `out/nautilus_oos_invalid2026/` and **must not be cited**.
- Rebuilt the 2026 path as a split-adjusted total-return index from monthly
  panel `ret`; `prc/adjfct` only sets the starting level. Every 2026
  stock-month compounds to panel `ret` with max absolute error **2.0e-14**.
- 2021–2025 monthly NAV is unchanged by the correction (max absolute
  difference 0.0); only 2026 changes.
- Corrected 2026 Jan–Jul **−8.72%** (invalid raw run: −14.08%); Jan–Aug
  **−8.25%**.

### 3.7 Analysis and audit

- Headline, yearly returns, FF5, S&P beta, March 2021 attribution, long/short
  contributions, equal-weight forecast quintiles, regime overlay, IC table,
  2026 comparison, top contributors, data audit.
- External/branch cause map in `OOS_RESULTS.md` §7a.
- `cvxportfolio` real-data research probe.
- Documentation/provenance and tests.

### 3.8 Tests

- Current targeted suite: **85 passed**.
  ```bash
  fiam/v4b/.venv/bin/python -m pytest -q fiam/v4b/tests
  ```
- D9 also recorded 157 repository tests passing with 3 skipped before the
  later OOS/audit work. The current 85 is the relevant targeted v4b result.
- Analysis scripts compile; output JSON parses; manifest/provenance hashes
  were refreshed and verified at audit time.

---

## 4. Corrected results

### 4.1 Headline

| Metric | Value |
|---|---:|
| Period | 2021-01-04 .. 2026-08-31 |
| Initial NAV | $1,000,000,000 |
| Final NAV | $641,718,397 |
| Net return | **−35.83%** |
| Gross return | **−7.94%** |
| Benchmark (T-bill + 4%) | **+50.76%** |
| CAGR | −7.57% |
| Annualised active mean | −14.93% |
| Annualised active vol | 6.55% |
| Net IR | **−2.28** |
| Max drawdown | **−37.62%** |
| Costs | **6.39%/yr** |
| Turnover | **6.02×/yr** |

Cost composition: impact **4.85pp**, spread **0.32pp**, fees **0.08pp**,
borrow **1.14pp**. The first 2021 build paid about **0.75% of NAV** in costs
on day one.

The earlier draft headline of gross **−8.63%** and costs **6.26%/yr** is
superseded by the first-day NAV-anchor and first-day cost fixes. Use only
**−7.94% / 6.39%**.

### 4.2 Yearly

| Year | Net | Gross | Benchmark | Active (pp) | Net IR | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| 2021 | −19.45% | −13.11% | +4.13% | −23.58 | −2.98 | −20.05% |
| 2022 | −11.27% | −3.16% | +6.20% | −17.47 | −2.59 | −11.59% |
| 2023 | +9.40% | +15.20% | +9.42% | −0.02 | +0.03 | −3.89% |
| 2024 | +0.31% | +5.61% | +9.38% | −9.07 | −1.45 | −7.09% |
| 2025 | −10.82% | −4.74% | +8.33% | −19.14 | −2.93 | −14.73% |
| 2026 Jan–Aug | −8.25% | −5.60% | +5.16% | −13.41 | −8.73 | −10.33% |

2021–2025 cumulative net is **−30.05%**; 2026 Jan–Aug adds **−8.25%**.
2023 only matched the benchmark (active −0.02pp); 2024 lagged by 9.07pp.
Neither positive year delivered positive active return.

### 4.3 The cross-section reversed immediately

Frozen MaInf rank IC against the next month’s realised total return:

| Period | MaInf IC |
|---|---:|
| 2021 | −0.0467 |
| 2022 | −0.0824 |
| 2023 | +0.0006 |
| 2024 | −0.0259 |
| 2025 | −0.0151 |
| 2026 Jan–Jul | −0.0245 |
| Full | **−0.0328** (t −2.47) |

- **January 2021 IC = −0.0373** — already negative in the first OOS month.
- **March 2021 IC = −0.2406** — the acute break.
- Ma1, Ma36, Ma60 were also negative over the full window.
- January 2021 NAV rose +0.45%, but the first trading day lost ~0.75% after
  the initial build cost. A positive January NAV is not evidence the
  cross-section worked.

March 2021, using actual prior-close daily weights:

- long leg **−0.96%**
- short leg **−4.87%**
- gross **−5.83%**
- costs **0.83%**
- net **−6.52%**

The top five short losses each contributed only ~0.14–0.22%; the damage was
broad, not one name.

### 4.4 The short leg is the main realised drag

Prior-close-weight contributions (approximate; marked weights drift intraday):

| Year | Long leg | Short leg |
|---|---:|---:|
| 2021 | +7.07% | **−20.79%** |
| 2022 | −24.67% | +19.78% |
| 2023 | +30.63% | **−20.52%** |
| 2024 | +14.56% | **−13.02%** |
| 2025 | +11.43% | **−19.33%** |
| 2026 Jan–Aug | +7.62% | **−15.22%** |

The long leg was positive in five of six years; the short leg lost in five
of six. Borrow cost is only ~1.14%/yr, so this is not financing: the shorts
rose.

Equal-weight forecast quintiles (gross, no costs, average monthly return):

| Year | Q0 lowest forecast | Q4 highest forecast | Q4−Q0 |
|---|---:|---:|---:|
| 2021 | +1.06% | +0.18% | −0.88% |
| 2022 | −0.92% | −3.80% | −2.87% |
| 2023 | +0.87% | +1.56% | +0.70% |
| 2024 | +0.50% | +0.05% | −0.46% |
| 2025 | +0.71% | +0.22% | −0.48% |
| 2026 Jan–Aug | +2.07% | +1.74% | −0.34% |
| **Full mean** | **+0.63%/m** | **−0.11%/m** | **−0.75%/m** |

Q4−Q0 is negative in **40 of 68 months**; annualised t **−0.64**. This is a
weak but consistently wrong spread. The short tail rose in five of six years;
the long tail averaged −0.11%/month. This is worse than “no alpha.”

### 4.5 Risk, construction and costs

E3’s executed book is noncompliant:

- names: average **552.9**, max **611**, vs 500 hard ceiling; **1,402**
  name-breach days
- gross: average **1.954**, max **2.479**, vs 2.0; **627** gross-breach days
- liquidation capacity: **71,371** name-days above the 5-day/10%-ADV limit
- short floor: **31** breaches
- policy: **1,416 of 1,421** days violate at least one internal exposure band
- max absolute hedge beta **0.147** (band 0.02)
- max sector **4.68%** (band 1%)
- unresolved-quote position-days: **73,250**
- unverified-gap position-days: **11,682**
- total breach rows: **73,431**
- `eligible_for_oos`: **false**

Ex-ante beta mean **+0.053**; realised S&P beta **+0.0719** (t 6.49), alpha
−0.046%/day. FF5 monthly alpha **−12.1%/yr**, market beta −0.069, SMB +0.030,
HML −0.131, RMW −0.223, CMA −0.074, R² 0.27. The book is short
quality/profitability and carries a large unexplained negative alpha.

This explains 2023: +9.40% with IC ≈ 0 was market/style exposure, not
forecast alpha. Costs were 5.16% that year; 2024 gross +5.61% against 5.15%
costs.

### 4.6 2026 data correction

| Month | Invalid raw 2026 | Corrected split-adjusted |
|---|---:|---:|
| 2026-01 | −4.95% | −4.73% |
| 2026-02 | −6.42% | −5.76% |
| 2026-03 | +0.95% | +2.49% |
| 2026-04 | −1.08% | +0.06% |
| 2026-05 | −2.66% | −0.01% |
| 2026-06 | +0.31% | +0.98% |
| 2026-07 | −0.93% | −1.81% |
| **Jan–Jul** | **−14.08%** | **−8.72%** |
| 2026-08 | — | +0.51% |
| **Jan–Aug** | — | **−8.25%** |

Checks: 2026 monthly compounding matches panel `ret` to ≤2.0e-14; the
2025-12-31→2026-01-02 boundary maximum move is 13.8% (ordinary daily return,
not a split); permno 17266 July 2026 compounds to +92.7332% exactly; AAPL
August 2020 and NVDA June 2021 adjusted-price vs total-return checks passed.

**2026 remains a proxy.** No actual 2026 quote/volume verification, no FINRA
ADV check, and the D5 splice ratio (~1.0335) is **not applied**. Using
`dolvol_126d` directly makes 2026 ADV conservative by roughly 3.2%. Label
every 2026 number accordingly.

### 4.7 Regime overlay

QUARCC-Black/Vireo gate: `trend_60(D−1) < 0 and breadth_20d(D−1) < 0.50`.
It is **false in Dec 2020–Mar 2021**, so it cannot repair the first-month or
March 2021 reversal. Post-hoc, no extra turnover cost:

| Overlay | 2021 | 2022 | 2021–2026 |
|---|---:|---:|---:|
| No gate | −19.45% | −11.27% | −35.83% |
| Daily `gate_short`, half gross | −15.04% | −6.73% | −31.23% |
| Daily `gate_short`, zero gross | −10.47% | −2.04% | −26.52% |
| Daily `gate_short or gate_risk`, half gross | −14.44% | −6.16% | −26.81% |
| Month-end `gate_short`, half gross | −17.67% | −7.91% | −31.52% |

Every variant remains deeply negative. This is a new risk-management
hypothesis, not part of the frozen E3 run.

---

## 5. What was fixed

| Defect | Action | Status |
|---|---|---|
| 2026 raw `dsf_mini` daily return/close not split-adjusted; spurious split jumps | Rebuilt 2026 as split-adjusted total-return index from panel `ret`; `prc/adjfct` only sets starting level | **Fixed**; invalid run preserved |
| Corrected run killed in native report rendering (~14 GB swap, no ledger) | Disabled native CSV/tearsheet export for OOS; ledger/holdings still native | **Fixed**; reported run clean |
| FF5 loader skipped header row; empty factor set/intercept-only “alpha” | Include header in CSV parse; use Mkt-RF, SMB, HML, RMW, CMA | **Fixed**; FF5 alpha −12.1%/yr |
| Headline return started at 2021-01-04 NAV and omitted first day | Anchor full-period return to $1bn starting NAV | **Fixed**; full net −35.83% |
| March 2021 attribution used stale 2021-02-26 weights | Recompute with actual prior-close daily weights | **Fixed**; long −0.96%, short −4.87% |
| First-day cost denominator/accounting | Corrected first-day NAV/cost accounting | **Fixed**; gross −7.94%, costs 6.39%/yr |
| `cvxportfolio` probe wrong simulator/result API | Use `market_data=...`, `result.w`, asset gross/net fields | **Fixed**; probe runs |
| E3 names/gross/liquidation/beta/sector breaches | Audit and report every breach; do not hide them | **Open by design** — repair changes frozen book and is new hypothesis |
| Negative OOS cross-section | No refit, sign flip, rescue config, or 2021+ tuning | **Rejected** — new pre-registered holdout required |
| 2026 no actual FINRA ADV/quotes; D5 not applied | Label proxy; disclose D5 deviation | **Disclosed**, not silently fixed |
| E4 daily min-turnover/compliance repair | Not implemented | **Open** — new strategy hypothesis |

Also fixed earlier: optimizer support cost/units, incumbent impact credit,
support cache key, trial gross, hard net band, fill-matched sigma, float64
cohort reconciliation. See `RISK_COST_AUDIT.md` and `LESSONS.md`.

---

## 6. Open blockers and caveats

1. **E3 is noncompliant.** Names, gross, liquidation capacity, short floor and
   internal beta/sector bands all fail. No final book or promotion is possible.
2. **2026 is a labelled proxy.** No actual quotes/volume/borrow, no FINRA ADV
   verification, D5 ratio not applied.
3. **E4 is not implemented.** Daily minimum-turnover/compliance repair and
   execution sequencing remain a new hypothesis, not a 2021+ repair.
4. **Missing-return/exit assumptions remain material.** The native run is
   share-aware, but 73,250 unresolved-quote position-days and 11,682
   unverified-gap position-days remain. Synthetic long exits at a 30% recovery
   after five missing sessions are a frozen assumption, not verified evidence.
5. **Cost model is frozen, not calibrated.** `impact_y=1.0`, square-root
   exponent 1.5 and a flat borrow schedule are assumptions. FINRA TAF/CAT are
   not wired in; the omission is small but real.
6. **Risk model is miscalibrated.** Realised vol is 1.29–1.51× predicted.
   Nominal beta neutrality is not statistically robust per name.
7. **Validation is heavily reused.** 2017–2020 had many nominal configurations
   and repeated model-selection exposure; 2019/2020 is not a fresh holdout.
   The 2021+ run was one-shot and diagnostic, not a new validation set for
   choosing a rescue.
8. **Native CSV/tearsheet export is disabled.** Ledger/holdings are native;
   re-enable reports only for a smaller or report-only run.

---

## 7. External and branch evidence (not rescues)

| Candidate cause | E3 evidence | Outside/branch evidence | Verdict |
|---|---|---|---|
| Frozen signal | MaInf IC −0.0328 (t −2.47); Q4−Q0 −0.75%/m; negative 5/6 years | QUARCC ML selector residual IC 0.019–0.069 each year 2019–26, but raw IC unstable; direct top−bottom +0.18%/m (t 0.24); construction arm +1.90% CAGR, IR −0.498 | New forecast, new holdout |
| Short side | Short leg lost 5/6 years; Q0 +0.63%/m vs Q4 −0.11%/m | N=250 branch short losses largely market hedge with net beta ≈0; E3 beta not zero (+0.053 ex-ante/+0.072 realised) | Short-side risk control/hedge; optimizer reweighting alone cannot fix |
| Risk construction | Beta max 0.147, sector max 4.68%; 1,416/1,421 policy-breach days | N=250 beta audit: ex-ante beta 0.0000, realised mean −0.011, sd 0.069, range −0.218…+0.203, corr −0.10; 26/60 months with absolute beta above 0.05 | Hard constraints + realised-risk monitoring; new hypothesis |
| Execution/capacity | 552.9 avg names, gross 2.479 max, 71,371 liquidation name-days, 31 short-floor | N=250 branch uses 250-name support/lot repair; Nautilus native fills | E4-style hard constraints; new hypothesis |
| Costs | 6.39%/yr; impact 4.85pp; turnover ~6× | cvxportfolio probe ~3bp/month; N=250 branch ~0.9%/yr | Lower turnover/name count may help but cannot turn negative gross positive |
| Regime | Gate false Dec 2020–Mar 2021; best overlay −31.23% | QUARCC-Black gate implementation; factor regime explains value/quality/low-investment windfall | Post-hoc overlay; new holdout only |
| Data/2026 | Proxy; D5 ~1.0335 not applied; no actual quote/ADV | Actual FINRA/quote/borrow data and D5 exist outside proxy path | Fixes 2026 label, not 2021–25 signal |
| Universe/selection | 500 support but executed average 553 | N=250 branch and QUARCC selector show selection/construction matters materially | New hypothesis, not a rescue |

Key external facts:

- **N=250 Forkfiam branch** (`feat/constructions-docs-drew`, commit `c6d2ed7`):
  2021 +9.64%, 2022 +11.23%, 2023 +8.09%, 2024 +5.08%, 2025 +0.81%, 2026
  YTD +6.37%; 68-month CAGR 7.23%, IR 0.781, max DD −3.87%. It is a different
  book; its own edge-decay report calls 2021–22 a value/quality/low-investment
  windfall and says the 4% hurdle has been missed since 2023. **Not an E3
  rescue.**
- **Branch beta audit:** ex-ante beta 0.0000 every month but realised monthly
  beta mean −0.011, sd 0.069, range −0.218…+0.203, correlation with forecast
  −0.10; 26/60 months exceed |0.05|. Ex-ante neutrality does not guarantee
  realised neutrality.
- **QUARCC selector:** stable residual IC, weak harvest; factor-neutral book
  +0.86%/yr IR −0.63; style-neutral −0.39%/yr IR −1.40. A stable IC is not a
  book.
- **`cvxportfolio` probe:** 40 large caps, 24 monthly periods (2021–2022),
  cumulative −22.19%, annualised −13.56%, vol 10.38%, Sharpe −1.23 monthly
  mean/vol (library print −1.42), cost ~3bp/month. It solves the continuous QP
  but lacks support/cardinality, sector/size bands, exact SEC/borrow schedule
  and the native five-session impact law. Possible future backend or
  independent solver check, **not** a drop-in replacement for Nautilus native
  execution.
- **QUARCC-Black gate source:**
  `/home/drewclaw/quarcc-black-fiam/packages/strategies/vireo/backtest/vec_engine2.py`.
- **NautilusTrader remains the execution source of truth.**

The branch evidence docs live at
`docs/finals/research/2026-10-12-forecasting-risk-construction/milestone7/`
on `feat/constructions-docs-drew` (`c6d2ed7`), including
`n250-full-window-confirmation-2026-10-17.md`,
`edge-decay-diagnosis-2026-10-17.md`,
`beta-neutrality-structure-2026-10-17.md`, and
`ml-and-quarcc-book-arms-2026-10-17.md`.

---

## 8. Artifacts and reproduction

### 8.1 Primary artifacts

- `out/nautilus_oos/E3/summary.json` — native execution summary and compliance counters.
- `out/nautilus_oos/E3/yearly_performance.csv` — yearly net/gross/benchmark/costs.
- `out/nautilus_oos/E3/daily_nav.parquet` — daily native marked-equity ledger.
- `out/nautilus_oos/E3/daily_holdings.parquet` — daily marked holdings/weights.
- `out/nautilus_oos/E3/breaches.parquet` — executed-rule breaches.
- `out/nautilus_oos/E3/policy_exposures.parquet` — beta/size/sector checks.
- `out/nautilus_oos/analysis.json` — IC, FF5, beta, March, side/quintile, overlay, 2026 comparison, contributors.
- `out/nautilus_oos/manifest.json` — source identity and artifact hashes.
- `out/nautilus_oos/PROVENANCE.json` — hashes, labels, preserved runs, external evidence.
- `out/nautilus_oos/data_audit.json` — 2026 compounding/boundary/adjfct checks.
- `out/nautilus_oos/regime_daily.parquet`, `regime_monthly.csv` — gate features.
- `out/research/cvxportfolio_probe.json` — probe result.

Source identity:
`5196f3b47233f57b46d9755af1ebadfca679fa22604a765dd5fb86b19de16980`.

Key input hashes include:

- `daily_market_2026.parquet`
  `df2f5b8d674e523b11b858394e974826b0aa3d9b01264e32f14d5d9fed19c642`
- `forecastElasso_oos.parquet`
  `36324eede0275c2417bdf417ecb1e836bb42086c42d9ccb1bbcb7c53e1fdcb89`

### 8.2 Preserved failed runs

- Invalid raw 2026: `out/engine/nautilus_oos_invalid2026.log` and
  `out/nautilus_oos_invalid2026/`.
- Corrected-data run killed in native report rendering:
  `out/engine/nautilus_oos_corrected_native_report_kill.log` and
  `out/nautilus_oos/manifest_native_report_kill.json`.
- Pre-note manifest: `out/nautilus_oos/manifest_before_note_edits.json`.

### 8.3 Commands

```bash
# targeted tests
fiam/v4b/.venv/bin/python -m pytest -q fiam/v4b/tests

# native OOS diagnostic (expensive; one-shot)
fiam/v4b/.venv/bin/python -m fiam.v4b.research.run_nautilus --oos --steps E3

# analysis
fiam/v4b/.venv/bin/python fiam/v4b/research/oos_report.py

# cvxportfolio probe (research only; needs a cvxportfolio checkout on PYTHONPATH)
PYTHONPATH=/path/to/cvxportfolio \
  fiam/v4b/.venv/bin/python fiam/v4b/research/cvxportfolio_probe.py
```

Do not rerun the OOS path to “try” a new band, sign, model or cost. That is
tuning on the diagnostic window.

---

## 9. Repository state and pending directives

### 9.1 Current state

- HEAD: `b5bdf0d9e0eec6238bb81f04095bf4debf14d38d`
- `origin/Risk-&-AI-Agents-Improvements` points at the **same commit**.
- Current local branch: `feat/finals-v4-drew`, not a local branch named
  `Risk-&-AI-Agents-Improvements`.
- `fiam/v4b/` is **untracked**. The audit, reports, code, and outputs are not
  in any commit. `docs/finals/` and some root logs/tools are also untracked.
- No tracked files were modified by the audit; `git status --short` shows only
  untracked paths.
- Provenance therefore rests on the hashes in `OOS_FREEZE.md` and
  `PROVENANCE.json`, not on a commit.

### 9.2 Session directives still open

- **Commit to `Risk-&-AI-Agents-Improvements`.** Not done.
- **Remove all Claude status as contributor from local commits.** Not done;
  no local commits were created for this audit. This is a history/attribution
  operation, not a file edit. Do not rewrite history casually.
- **Move v4b to `fiam/v4b`.** Path is already there; it is untracked.
- **Optimizer consumes forecaster/risk.** Implemented in
  `engine/optimize.py` (`Formation.mu`, risk snapshot).
- **cvxportfolio reference.** Research probe implemented; not the execution
  engine.

### 9.3 Commit warning

`fiam/v4b` is ~3.1 GB on disk. Its `.gitignore` excludes `.venv`, `cache/`,
`out/**/*.parquet`, `out/**/*.RDS`, and `external/elasso_download/`; the root
`.gitignore` also ignores `*.parquet`, `cache/`, and `/out/`. A dry-run
`git add -n fiam/v4b` shows 231 candidate files, including source/docs and
some non-parquet out files, but **not** the main parquet ledgers.

Before committing:

1. Decide whether the handoff/audit should be committed at all, and to which
   branch.
2. Inspect `git status`, `git add -n`, and staged sizes.
3. Do not blindly `git add -A` or `git add fiam/v4b` without checking for
   `out` blobs, source-pack archives, and ignored data.
4. If the user wants the full ledger in git, use a deliberate artifact/LFS
   decision; otherwise commit code/docs/manifests and keep large outputs
   external with hashes.

No commit was made in this handoff step.

---

## 10. Next move

1. **Decide commit vs. handoff-only.** The work is currently untracked; if it
   is to be preserved in GitHub, review and commit deliberately to the
   requested branch. Do not rewrite contributor history without explicit
   confirmation.
2. **Freeze a new hypothesis before touching 2027+.** A monthly-refit E-LASSO,
   a genuinely different signal, E4 daily repair, or a regime overlay is a new
   hypothesis, not a continuation. Pre-register it and a new holdout (e.g.
   2027+); do not choose it on 2021–2026.
3. **Rebuild 2026 from actual quote/volume/borrow data**, apply D5 or document
   why not, and verify FINRA ADV before any future final run.
4. **Implement hard construction/execution constraints**: names, gross, beta,
   sector, size, liquidation capacity, short floor, daily minimum turnover;
   preserve actual fills and log every breach.
5. **Re-enable native reports only for a smaller/report-only run**; keep the
   OOS memory bound.
6. **Do not present E3 as final performance.** `eligible_for_oos=false`,
   `diagnostic_only=true`; 2021–2026 is one-shot diagnostic evidence.

---

## 11. Session quote appendix

Selected direct quotes, for provenance:

**Claude session**

> “i do not care about what have been made in the past. i want you to evaluate
> the latest plan i sent via taildrop (.md and the zip) against the new final
> mandate, your knowledge of the corresponding scientific math concepts and
> research you will conduct. you can use proof from past work in the repo but
> DO NOT consider it as optimal solution or implementation to our mandate”

> “yes please replace with E-Lasso. and persist in ALL documents and files to
> persist that decision.”

**Muse session**

> “continue devellopment in exclusively v4b directory. please read all of the
> following and the latest claude session to understand where we stand and what
> needs to be done : E-LASSO is now the forecaster everywhere in v4b/ … MaInf
> is the primary forecast. Ma1 is the one alternate, chosen only on net return
> after costs once the engine is built.”

> “what i think we should do is finish forecaster work, and then go to the risk
> model(s) as defined by the revised plan and ONLY fnally build the optimizer.”

> “reference for optimizer : https://github.com/cvxgrp/cvxportfolio … then move
> v4b to forkfiam/fiam/... AND remove all of claude status as contributor in
> all of local commits and commit to github inside this branch :
> https://github.com/niccc333/Forkfiam/tree/Risk-%26-AI-Agents-Improvements
>
> the optimizer must take the outputs of forecaster and outputs of risk as
> inputs.”

These quotes are from the local session logs listed in §1. They are included
so a future session can recover the exact directives without re-reading the
full transcripts.
