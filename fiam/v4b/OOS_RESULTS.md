# 2021–2026 OOS diagnostic — corrected data and verdict

**Date:** 2026-10-24  
**Status:** diagnostic only. **The frozen 2020-12 E-LASSO candidate is rejected.** E3 remains noncompliant; this is not a final book, not a promotion, and not a basis for tuning on 2021+.

## 1. What changed

The first 2021–2026 run used raw 2026 `dsf_mini` `daily_return`/`close`. Those values are **not split-adjusted**; the run created spurious split jumps and overstated the 2026 loss. That run is preserved at `out/engine/nautilus_oos_invalid2026.log` and `out/nautilus_oos_invalid2026/` and is **not** a valid 2026 result.

The 2026 execution path is now a **split-adjusted total-return index** built from the monthly panel `ret`. `prc/adjfct` supplies only the starting level; the raw mini close/return does not drive execution. Every 2026 stock-month compounds to panel `ret` with maximum absolute error **2.0e-14**.

The 2021–2025 path is unchanged: every monthly NAV in the corrected run matches the first run exactly (max absolute difference **0.0**). Only 2026 changes.

## 1a. Remediation ledger — what was fixed, what cannot be fixed here

| Defect found | Action taken | Status |
|---|---|---|
| First 2026 run used raw, non-split-adjusted `dsf_mini` returns/closes; spurious split jumps | Rebuilt 2026 as a split-adjusted total-return index from panel `ret`; `prc/adjfct` only sets the starting level | **Fixed**; invalid run preserved |
| First corrected run was killed in native report rendering (~14 GB swap, no ledger) | Disabled native CSV/tearsheet export for OOS; ledger/holdings still built from native fills/account state | **Fixed**; reported run clean |
| FF5 loader skipped the header row and produced an empty factor set / intercept-only “alpha” | Include the header in the CSV parse; FF5 attribution now uses Mkt-RF, SMB, HML, RMW, CMA | **Fixed**; FF5 alpha −12.1%/yr |
| Headline return started at the 2021-01-04 NAV and omitted the first day | Anchor full-period return to the 1,000,000,000 starting NAV | **Fixed**; full net −35.83% |
| March 2021 attribution used stale 2021-02-26 weights | Recompute with actual prior-close daily weights | **Fixed**; long −0.96%, short −4.87% |
| `cvxportfolio` probe used the wrong simulator/result API | Use `market_data=...` and `result.w`; add asset gross/net fields | **Fixed**; probe runs |
| E3 executed names/gross/liquidation/beta/sector breaches | Audit and report every breach; do not hide them | **Open by design** — repairing construction changes the frozen book and is a new hypothesis |
| Negative OOS cross-section | No refit, sign flip, rescue config, or 2021+ tuning | **Rejected** — new pre-registered holdout required |
| 2026 has no actual FINRA ADV/quote verification; D5 splice not applied | Label as proxy; keep D5 deviation explicit | **Disclosed**, not silently fixed |
| E4 daily minimum-turnover/compliance repair | Not implemented; would be a new strategy hypothesis | **Open** — cannot be fitted on 2021+ |

## 2. Headline corrected result

| Year | Net | Gross | Benchmark (T-bill + 4%) | Active (pp) | Net IR | Max DD | Costs / NAV |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | −19.45% | −13.11% | +4.13% | −23.58 | −2.98 | −20.05% | 7.56% |
| 2022 | −11.27% | −3.16% | +6.20% | −17.47 | −2.59 | −11.59% | 8.73% |
| 2023 | +9.40% | +15.20% | +9.42% | −0.02 | +0.03 | −3.89% | 5.16% |
| 2024 | +0.31% | +5.61% | +9.38% | −9.07 | −1.45 | −7.09% | 5.15% |
| 2025 | −10.82% | −4.74% | +8.33% | −19.14 | −2.93 | −14.73% | 6.58% |
| 2026 Jan–Aug | −8.25% | −5.60% | +5.16% | −13.41 | −8.73 | −10.33% | 2.85% (partial) |
| **2021–2026** | **−35.83%** | **−7.94%** | **+50.76%** | **−14.93%/yr ann.** | **−2.28** | **−37.62%** | **6.39%/yr** |

The two positive calendar years were **2023 (+9.40%, active −0.02pp)** and **2024 (+0.31%, active −9.07pp)**. Neither delivered positive active return: 2023 only matched the benchmark (active −0.02pp), and 2024 lagged it by 9pp. Gross return was positive in both, but the cost drag consumed it; gross was negative in 2021, 2022, 2025 and 2026. The 2021–2025 cumulative net return is **−30.05%**; 2026 Jan–Aug adds **−8.25%**.

Costs are the largest mechanical drag: **6.39%/yr** on average, of which **4.85pp is impact**, 0.32pp spread, 0.08pp fees and 1.14pp borrow. Annualised turnover is **6.02×**. The first 2021 build alone paid about 0.75% of NAV in costs on day one.

## 3. The cross-section reversed immediately

Frozen MaInf rank IC against the next month's realised total return (the same series used in `OOS_FREEZE.md`):

| Signal | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 Jan–Jul | Full mean | t |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MaInf | −0.0467 | −0.0824 | +0.0006 | −0.0259 | −0.0151 | −0.0245 | −0.0328 | −2.47 |
| Ma1 | −0.0916 | −0.0759 | −0.0128 | −0.0690 | +0.0070 | +0.0010 | −0.0426 | −2.38 |
| Ma36 | −0.0631 | −0.1134 | −0.0159 | −0.0353 | −0.0214 | −0.0595 | −0.0510 | −3.46 |
| Ma60 | −0.0380 | −0.0925 | +0.0085 | −0.0348 | −0.0203 | −0.0332 | −0.0351 | −2.47 |

The first OOS month was already negative: **January 2021 MaInf IC = −0.0373**. February was +0.0309 (the book still lost 1.46% after costs), then **March 2021 IC = −0.2406**. January's NAV rose +0.45%, but the first trading day lost 0.75% after the initial build cost; a positive January NAV is not evidence that the cross-section worked.

March 2021, using actual prior-close weights and daily total returns:

- long leg: **−0.96%**
- short leg: **−4.87%**
- gross contribution: **−5.83%**
- costs: **0.83%**
- net: **−6.52%**

The short leg was the main loss, but the long leg lost too; this was a broad short squeeze, not one idiosyncratic name. The top five short losses each contributed only about 0.14–0.22%, so the damage was spread across the book.

### 3a. The loss is concentrated in the short book

The March pattern repeats over the full diagnostic. Summing prior-close weights times the next session's total return (approximate; marked weights drift intraday, so this is a sign/magnitude diagnostic, not an exact reconciliation):

| Year | Long-leg contribution | Short-leg contribution |
|---|---:|---:|
| 2021 | +7.07% | **−20.79%** |
| 2022 | −24.67% | +19.78% |
| 2023 | +30.63% | **−20.52%** |
| 2024 | +14.56% | **−13.02%** |
| 2025 | +11.43% | **−19.33%** |
| 2026 Jan–Aug | +7.62% | **−15.22%** |

The long leg was positive in five of six years (2022 the exception); the **short leg lost in five of six years**, with only 2022 adding. Borrow cost is only ~1.14%/yr, so this is not a financing problem: the stocks the model shorted rose. The short leg lost **−20.79%** in 2021, **−20.52%** in 2023 and **−19.33%** in 2025. The optimizer cannot repair that short selection by changing weights; it is a property of the frozen forecast and the short-side factor exposure.

The equal-weight forecast quintiles make the same point without the optimizer (gross, no costs, average monthly return):

| Year | Q0 lowest forecast (short tail) | Q4 highest forecast (long tail) | Q4 − Q0 |
|---|---:|---:|---:|
| 2021 | +1.06% | +0.18% | −0.88% |
| 2022 | −0.92% | −3.80% | −2.87% |
| 2023 | +0.87% | +1.56% | +0.70% |
| 2024 | +0.50% | +0.05% | −0.46% |
| 2025 | +0.71% | +0.22% | −0.48% |
| 2026 Jan–Aug | +2.07% | +1.74% | −0.34% |
| **Full mean** | **+0.63%/m** | **−0.11%/m** | **−0.75%/m** |

The long-short quintile spread is negative in **40 of 68 months**; its annualised t-statistic is only **−0.64**, so it is a weak but consistently wrong spread. The **Q0 short tail rose in five of six years**, while the Q4 long tail averaged **−0.11%/month** over the full sample. That is worse than a “no alpha” forecast: neither tail provided a reliable long-side edge, and the short tail rose more.

First-month nuance: the January 2021 rank IC was **−0.0373**, but the equal-weight Q4−Q0 spread was still **+5.44%** because both tails rose (Q0 +7.09%, Q4 +12.53%). The price spread did not collapse until March (Q0 +2.73%, Q4 −4.40%, Q4−Q0 **−7.13%**). The honest reading is that the rank IC reversed immediately, the price spread was mixed in January, and the book broke down unambiguously in March.

## 4. Risk and construction did not hold either

E3's executed book is noncompliant. The native summary reports:

- **Names:** average 552.9, maximum 611, versus the 500 hard ceiling; **1,402** name-breach days.
- **Gross:** average 1.954, maximum **2.479**, versus the 2.0 hard ceiling; **627** gross-breach days.
- **Liquidation capacity:** **71,371** name-days exceed the 5-day exit limit at 10% participation.
- **Short floor:** 31 breaches.
- **Policy:** 1,416 of 1,421 days violate at least one internal exposure condition; maximum absolute hedge beta **0.147** (band 0.02), maximum sector **4.68%** (band 1%).
- **Data gaps:** 73,250 unresolved-quote position-days and 11,682 unverified-gap position-days.
- **Total breach rows:** 73,431. `eligible_for_oos` is **false**.

The ex-ante beta is not neutral: mean **+0.053**, maximum **+0.147**; it exceeds the ±0.02 policy band on **1,307** days. Sector exposure exceeds 1% on 1,411 days. Missing exposures average 36 names/day. Realised daily S&P beta is **+0.0719** (t = 6.49), with alpha **−0.046%/day**.

This explains why 2023 could earn +9.40% while the signal IC was ~0: the book was carrying market/style exposure, not a neutral cross-section. Fama–French 5-factor monthly attribution (68 months) gives an alpha of **−12.1%/yr**, market beta −0.069, SMB +0.030, HML −0.131, RMW −0.223, CMA −0.074, and R² 0.27. The book is short quality/profitability and has a large unexplained negative alpha.

## 5. Corrected 2026 versus the invalid first run

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

The correction improves 2026 Jan–Jul by **+5.36pp**, but the strategy is still negative. The corrected and invalid monthly paths diverge because the 2026 returns change the subsequent weights, not merely the level.

Data checks:

- 2026 monthly compounding matches panel `ret` to **2.0e-14**.
- The 2025-12-31 → 2026-01-02 boundary maximum move is **13.8%**, an ordinary daily return, not a split jump.
- Permno 17266 July 2026 compounds to **+92.7332%**, exactly the panel `ret`; the row's adjusted-price move is internally inconsistent, but the execution path uses `ret` and does not create a split jump.
- `prc/adjfct` is split-adjusted price: AAPL August 2020 adjusted-price return +21.44% versus total return +21.66%; NVDA June 2021 +23.13% versus +23.16%.
- 2026 remains a **proxy**: no quote/volume verification, no FINRA ADV check, and the D5 splice ratio (**~1.0335**) is not applied. Using panel `dolvol_126d` directly makes 2026 ADV conservative by roughly 3.2%.

## 6. Regime overlay: post-hoc, not a rescue

The QUARCC-Black/Vireo gate is `trend_60(D−1) < 0 and breadth_20d(D−1) < 0.50`. It does **not** fire in December 2020–March 2021, so it cannot repair the first-month or March 2021 reversal. Applying it to the realised daily ledger (post-hoc, with no extra turnover cost):

| Overlay | 2021 | 2022 | 2021–2026 |
|---|---:|---:|---:|
| No gate | −19.45% | −11.27% | −35.83% |
| Daily `gate_short`, half gross | −15.04% | −6.73% | −31.23% |
| Daily `gate_short`, zero gross | −10.47% | −2.04% | −26.52% |
| Daily `gate_short or gate_risk`, half gross | −14.44% | −6.16% | −26.81% |
| Month-end `gate_short`, half gross | −17.67% | −7.91% | −31.52% |

Every variant remains deeply negative. The overlay is a **new risk-management hypothesis**, not part of the frozen E3 run; it must be pre-registered on a new holdout if it is to be used. It cannot fix a negative cross-section.

## 7. cvxportfolio probe

`cvxportfolio` was evaluated as a continuous-QP backend on a 40-name large-cap universe, 24 monthly periods (2021–2022), using the frozen MaInf cross-section as a 1%/month forecast, 5% name caps, dollar and market neutrality, 2× leverage, and its `TransactionCost`/`HoldingCost` classes.

- It solved the same class of problem and is fast (~0.02 s policy time/period).
- Average asset gross was **1.87**, asset net about **−0.01**, cash about **1.01**; long and short books averaged about 19 names each after the first period.
- Cumulative return was **−22.19%**, annualised **−13.56%**, volatility 10.38%, Sharpe **−1.23** on monthly mean/vol (the library’s excess-return print is −1.42).
- Its transaction-cost model charged only ~3bp/month (holding 0bp), far below the native impact model's 4.85%/yr; it does not include support/cardinality, sector/size bands, the exact SEC/borrow schedule, or the native five-session impact law.

Conclusion: `cvxportfolio` is a credible **future backend** for the continuous weights after support selection, or for an independent solver check. It is **not** a drop-in replacement for the frozen E3 construction and does not repair the signal. A naive swap would understate costs and silently relax mandate constraints.

## 7a. Cause map — outside v4b and other Forkfiam branches

The loss is not one bug. This table separates what the frozen E3 book proves from what other branches and tools can and cannot repair. The branch results use different selectors or constructions; none is a like-for-like E3 rescue or a licence to tune on 2021+.

| Candidate cause | E3 evidence | Outside / branch evidence | Verdict |
|---|---|---|---|
| Frozen signal | MaInf IC −0.0328 (t −2.47); Q4−Q0 −0.75%/month (t −0.64); negative in five of six years | QUARCC ML selector residual IC is stable at 0.019–0.069 every year 2019–26, but raw IC is unstable and direct top−bottom harvesting is only +0.18%/month (t +0.24); the QUARCC construction arm earns +1.90% CAGR, IR −0.498 | New forecast, new pre-registered holdout |
| Short side | Short leg lost in five of six years; Q0 short tail +0.63%/month versus Q4 −0.11%/month | The N=250 branch's raw short losses are largely the market hedge with net beta ≈0; E3's ex-ante/realised beta is not zero (+0.053/+0.072), so its long leg does not fully offset | Short-side risk control and better hedge; optimizer reweighting alone cannot fix it |
| Risk construction | Ex-ante beta +0.053 (max +0.147), sector max 4.68%; 1,416/1,421 policy-breach days | The N=250 beta audit has ex-ante beta 0.0000 every month but realised beta mean −0.011, sd 0.069, range −0.218…+0.203, corr −0.10; 26/60 months exceed 0.05 | Hard constraints plus realised-beta/sector monitoring; new hypothesis |
| Execution and capacity | 552.9 names average, gross 2.479 max, 71,371 liquidation name-days, 31 short-floor breaches | The N=250 branch uses a 250-name support with lot repair; Nautilus supplies native fills/positions | E4-style hard constraints; new hypothesis, not an OOS repair |
| Costs | 6.39%/yr; impact 4.85pp; turnover ≈6× | The cvxportfolio probe undercosts at ~3bp/month; the N=250 branch's different book costs ~0.9%/yr | Lower turnover/name count can help, but cannot turn a negative gross book positive |
| Regime | Gate is false Dec 2020–Mar 2021; even the best overlay is −31.23% | QUARCC-Black gate implementation; the branch factor regime explains why value/quality/low-investment paid in 2021–22 and faded after 2022 | Post-hoc overlay, not a rescue; new holdout only |
| Data / 2026 | 2026 is a labelled proxy; D5 ratio ~1.0335 not applied; no actual quote/ADV check | Actual FINRA/quote/borrow data and the D5 splice are available outside the proxy path | Fixes the 2026 label, not the 2021–25 signal |
| Universe and selection | 500 support, but executed names average 553 and breach the ceiling | The N=250 branch and QUARCC selector show selection/construction can change the outcome materially | A different selection is a new hypothesis, not a rescue for frozen E3 |

The most useful outside evidence is the **N=250 Forkfiam branch** (`feat/constructions-docs-drew`, 68-month report): 2021 **+9.64%**, 2022 **+11.23%**, 2023 +8.09%, 2024 +5.08%, 2025 +0.81%, 2026 YTD +6.37%; 68-month CAGR 7.23%, IR 0.781, max drawdown −3.87%. That is a genuinely better book, but it is **not the frozen E3 candidate**: it uses a different support/construction, and its own edge-decay diagnosis says 2021–22 was a value/quality/low-investment windfall, the design-window IC was ≈0, and the 4% hurdle has been missed since 2023. It shows that construction and selection matter; it does not show that E3 can be repaired by changing its optimizer.

The **branch beta audit** is the cleanest warning against trusting ex-ante neutrality: a portfolio can satisfy `|Σ w β̂| ≤ 0.02` exactly and still realise a monthly beta with sd 0.069 and essentially zero correlation with the forecast. E3's realised beta +0.072 is consistent with that failure mode. The fix is hard exposure control plus realised-risk monitoring, not another scalar penalty.

The **QUARCC selector** has stable residual IC, but the harvest is weak: the direct top−bottom decile is +0.18%/month (t +0.24), the rank-weighted factor-neutral book earns +0.86%/yr with IR −0.63, and the style-neutral version is −0.39%/yr with IR −1.40. The construction arm is also negative. A stable IC is not a book; this is a research lead for a new model, not a rescue.

`cvxportfolio` is a credible future QP backend and an independent solver check, but the probe lost money and its cost model is far lighter than the native impact model. NautilusTrader is the execution source of truth; no alternative execution engine can repair a negative signal. **None of these is a rescue for frozen E3.** The honest next test is a new pre-registered hypothesis with a different or refit forecast, hard support/count/gross/beta/sector constraints, short-side risk controls and a cost/capacity budget, evaluated on 2027+ or another untouched holdout.

## 8. Verdict and next step

**Reject the frozen 2020-12 E-LASSO candidate.** It failed on the first OOS cross-section (January IC −0.0373), failed catastrophically in March 2021 (IC −0.2406), had negative IC in every year except a statistically zero 2023, and neither positive year delivered positive active return. Costs, the persistent short-leg losses, beta drift, sector drift and capacity breaches make the executed book worse, but the forecast’s negative cross-section remains the root cause. No sign flip, rescue configuration, or 2021+ tuning is permitted.

E3 is **not a final book**: it breaches names, gross, liquidation capacity, short floor and internal beta/sector bands, and 2026 is still a labelled proxy. The next honest test is a **new pre-registered hypothesis on a new holdout** (for example 2027+), not another pass over 2021–2026. That hypothesis needs a stronger signal (monthly-refit E-LASSO or a genuinely different forecast), hard construction/execution constraints, and a cost/capacity budget that clears the mandate hurdle.

## 9. Artefacts

- `out/nautilus_oos/E3/summary.json`: native execution summary and compliance counters.
- `out/nautilus_oos/E3/yearly_performance.csv`: yearly net/gross/benchmark/costs.
- `out/nautilus_oos/E3/daily_nav.parquet`: daily ledger from native account state.
- `out/nautilus_oos/E3/daily_holdings.parquet`: daily marked holdings.
- `out/nautilus_oos/analysis.json`: IC, FF5, beta, March attribution, long/short and quintile attribution, regime overlay, 2026 comparison, top contributors.
- `out/nautilus_oos/manifest.json`: source identity and artifact hashes.
- `out/engine/nautilus_oos_invalid2026.log`: preserved invalid 2026 run.
- `out/engine/nautilus_oos_corrected_native_report_kill.log`: corrected-data run killed in native report rendering; no ledger.
- `OOS_FREEZE.md`: frozen object, amended data description and hashes.
- `out/nautilus_oos/PROVENANCE.json`: artifact and input hashes, labels, preserved runs.
- `out/nautilus_oos/data_audit.json`: 2026 compounding/boundary/adjfct checks.
- `out/nautilus_oos/regime_daily.parquet`, `regime_monthly.csv`: gate features.
- `research/oos_report.py`: reproducible analysis script.
- `research/cvxportfolio_probe.py`: the probe (research only).
