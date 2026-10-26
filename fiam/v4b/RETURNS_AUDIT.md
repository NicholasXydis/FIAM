# Returns/strategy audit — 2026-10-23

Status: findings identified, not fixed in this audit. No strategy code or
reported returns were changed. Earlier E0–E3 completion means the pipeline
ran; it does not mean execution semantics or strategy validity are proven.
Accounting reconciliation alone cannot establish either.

## Newly reproduced implementation problems

1. **Dollar residuals do not follow price drift during liquidation.**
   `engine/sim.py:118–125` fixes an order in dollars and subtracts dollar fills,
   while the position is independently marked with daily returns. Reproduction:
   own $20, target zero, allow $10/day. First sale leaves $10. Price doubles;
   second sale is still only $10. Order is zero but $10 of stock remains.
   This can create unintended exposures and change subsequent P&L. Historical
   E3 impact has not yet been isolated. Use share/quantity-aware orders or
   target-aware residual recomputation, with explicit full-close semantics.

2. **Expired unfilled orders disappear from the audit trail.**
   `engine/sim.py:127–128` clears the order before logging it. A $90 request
   with five $10 fills records zero unfilled at expiry despite a $40
   cancellation. Preserve expired/cancelled residuals and reasons separately.

3. **The S&P beta exhibit drops valid sessions.**
   `engine/ladder.py:362` computes pct_change before aligning the price index
   to trading sessions. Holiday placeholders cause the next valid return to
   disappear: 970 observations instead of 1,007. Align first, then compute
   returns. Read-only recalculation changes E3 beta from -0.02332 (t=-2.313)
   to -0.02521 (t=-2.524). This affects the exhibit, not NAV/strategy IR.

## Material return assumptions and strategy weaknesses

4. **Missing observations are treated as synthetic long exits.** After five
   missing sessions, the simulator writes down a long 30% and converts its
   remaining value to cash without a quote. E3 has 21 synthetic exits across
   20 dates, with $42.84m of stub losses. Missing data is not itself evidence
   of delisting or a realizable 70% recovery. The frozen assumption needs
   event/source verification and the predeclared recovery sensitivities.

5. **Targets are not executed compliance.** E3 max gross is 2.2694 versus
   2.0 allowed; max absolute carried hedge beta 0.09175 versus policy 0.02;
   max sector exposure 0.02386 versus policy 0.01. Breach rows: 22 gross,
   105 count, 1 short floor and 1,913 liquidation capacity. Cost deductions,
   market drift, overlapping fills and incomplete exits require actual
   constraint repair/execution sequencing; tightening only targets is insufficient.

6. **Costs consume the measured edge.** Gross active IR 0.5827 becomes net
   -0.1389. Annual costs in return/NAV units total about 3.86%, including
   3.02% impact and 0.64% borrow. Spread sensitivity alone is not adequate;
   impact calibration/execution assumptions and borrow assumptions matter.
   E3 annual active mean is -0.753%, despite positive cumulative NAV growth.

7. **Risk and forecast magnitudes are uncertain.** D8 reference books have
   volatility bias 1.29–1.51; these are not calibrated E3 risk forecasts.
   D7 MaInf centred calibration is weakly identified (90% interval includes
   zero). The optimistic interpretation of return forecasts is not established.

8. **Validation is heavily reused and regime-dependent.** The 2017–2020
   window has 82 nominal recorded configurations and repeated debugging/model
   selection exposure. 2019 underperforms the benchmark by 13.11 percentage
   points; 2020 outperforms by 11.65. The 2019/2020 split is not a fresh holdout.
   Attribution and stability analysis are needed before claiming durable alpha.

Priority: fix execution/order audit semantics and return-source/exit treatment;
then repair actual compliance and rerun the frozen pipeline. Reassess cost
sensitivity and attribution before selecting a forecaster or opening OOS.
Keep D6–D8 unchanged while diagnosing these issues.

---

# Addendum 2026-10-24 — corrected native 2021–2026 diagnostic

**Status:** the frozen 2020-12 E-LASSO candidate is rejected. The 2021–2026
run is diagnostic only, not a final book. See `OOS_RESULTS.md`.

## Execution supersedes the legacy simulator for this run

The 2021–2026 diagnostic uses native NautilusTrader **share/quantity orders**,
native fills, positions and account state. The old `engine/sim.py` dollar-
residual/expiry problems (items 1–2 above) are therefore not the execution
mechanism for this run; the native tests cover share-aware liquidation and
retained expired residuals. Items 4–7 remain material: missing/unverified
quotes, synthetic long exits, target-vs-executed compliance, cost magnitude,
risk calibration and validation reuse. The native book still reports 73,250
unresolved-quote position-days and 11,682 unverified-gap position-days, and
E3 remains noncompliant.

## Corrected headline

| Year | Net | Gross | Benchmark | Active | Net IR | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| 2021 | −19.45% | −13.11% | +4.13% | −23.58pp | −2.98 | −20.05% |
| 2022 | −11.27% | −3.16% | +6.20% | −17.47pp | −2.59 | −11.59% |
| 2023 | +9.40% | +15.20% | +9.42% | −0.02pp | +0.03 | −3.89% |
| 2024 | +0.31% | +5.61% | +9.38% | −9.07pp | −1.45 | −7.09% |
| 2025 | −10.82% | −4.74% | +8.33% | −19.14pp | −2.93 | −14.73% |
| 2026 Jan–Aug | −8.25% | −5.60% | +5.16% | −13.41pp | −8.73 | −10.33% |
| 2021–2026 | **−35.83%** | **−7.94%** | **+50.76%** | **−14.93%/yr** | **−2.28** | **−37.62%** |

Costs are **6.39%/yr** (impact 4.85pp, spread 0.32pp, fees 0.08pp, borrow
1.14pp) at 6.02× annual turnover. The 2023 positive year was not alpha: active
return was −0.02pp; 2024 was +0.31% but active return was −9.07pp. FF5 monthly alpha is **−12.1%/yr**; realised S&P beta is
**+0.0719** (t 6.49), not neutral.

## Why 2021+ was unstable

1. **The rank IC reversed from the first OOS month.** MaInf rank IC was
   **−0.0373 in January 2021** and **−0.2406 in March 2021**; the equal-weight
   quintile spread was still mixed in January but collapsed in March. Annual means:
   2021 −0.0467, 2022 −0.0824, 2023 +0.0006, 2024 −0.0259, 2025 −0.0151,
   2026 Jan–Jul −0.0245; full −0.0328 (t −2.47). Ma1, Ma36 and Ma60 were also
   negative. No construction knob fixes a negative signal.
2. **The executed book was not neutral or compliant.** Average 552.9 names
   (max 611) vs 500; average gross 1.954 (max 2.479) vs 2.0; 71,371 name-days
   above the 5-day liquidation limit; 31 short-floor breaches; 1,416/1,421
   policy-breach days; max |hedge beta| 0.147 vs 0.02; max sector 4.68% vs 1%.
   The ex-ante beta mean was +0.053, not zero. The book carried market/style
   exposure, so 2023's +9.40% was beta, not forecast alpha.
3. **Costs consumed any gross edge.** Gross was +15.2% in 2023 and +5.6% in
   2024, but costs were 5.2% and 5.1%; gross was negative in 2021, 2022, 2025
   and 2026. At 6.4%/yr, a 500-name 1.8× book needs a much stronger signal.
4. **The March 2021 squeeze was broad.** Using actual prior-close weights:
   long −0.96%, short −4.87%, gross −5.83%, costs 0.83%, net −6.52%. The top
   short losses were only 0.14–0.22% each; the damage was spread across the
   short leg, not one name.
5. **The short leg is the main realised drag.** Prior-close-weight
   contributions show the long leg positive in five of six years, while the
   short leg lost in five of six years (−20.79% in 2021, −20.52% in 2023,
   −19.33% in 2025). Equal-weight forecast quintiles give Q0 (short tail)
   +0.63%/month versus Q4 (long tail) −0.11%/month; Q4−Q0 is −0.75%/month
   (t −0.64, 40/68 negative months). Borrow cost (~1.14%/yr) is not the cause;
   the shorted stocks rose. This is both a forecast and a short-side factor
   problem, not something an optimizer can repair by reweighting.
6. **The regime gate cannot rescue the first quarter.** `trend_60 < 0 and
   breadth < 0.50` was false in Dec 2020–Mar 2021. A post-hoc daily half-gross
   overlay improves 2021 from −19.45% to −15.04% and 2022 from −11.27% to
   −6.73%, but full 2021–2026 remains −31.23% (and −26.81% for the wider
   either-gate variant). It is a new risk hypothesis, not a fix.

## Data correction

The first 2026 path used raw `dsf_mini` daily returns/closes, which are not
split-adjusted. The corrected 2026 path is a split-adjusted total-return index
from panel `ret`; the first run is preserved as invalid. Jan–Jul 2026 improves
from −14.08% to −8.72%; Jan–Aug is −8.25%. 2026 remains a proxy (no FINRA ADV
verification, no D5 splice, no actual quotes).

## Optimizer

`cvxportfolio` solved a 40-name, 2021–2022 monthly market/dollar-neutral
probe (−22.19% cumulative, −13.56%/yr, Sharpe −1.23) but its default cost model
charged only ~3bp/month and lacks the support/cardinality, sector/size and
five-session impact machinery. It is a possible continuous-QP backend, not a
rescue.

## External / branch evidence

`OOS_RESULTS.md` §7a records the cross-branch audit. The N=250 branch book is
positive in 2021 (+9.64%) and 2022 (+11.23%) but fades to +5.08% in 2024 and
+0.81% in 2025; its own edge-decay report calls 2021–22 a factor windfall. Its
beta audit shows ex-ante beta 0.0000 with realised beta sd 0.069 and
ex-ante/realised correlation −0.10. The QUARCC selector has stable residual IC
but no harvestable book edge in the branch arms. None of these is a rescue for
the frozen E3 candidate; they are evidence for a new, pre-registered hypothesis.

## Decision

Reject the frozen candidate. Do not sign-flip, rescue, or tune on 2021+. E3 is
not a final book. Any next hypothesis (monthly-refit E-LASSO, new signal, E4
daily repair, regime overlay) needs a **new pre-registered holdout** and a
construction/execution plan that can actually satisfy names, gross, beta,
sector and liquidation limits.
