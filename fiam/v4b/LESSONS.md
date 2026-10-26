# Lessons and conclusions (append-only, newest last)

Every number below comes from a file under `fiam/v4b/out/` or `fiam/v4b/research/`, named in its line.
Nothing here used a label that ends after 2020-12-31.

## 2026-10-23 — Planning

1. **The hurdle sets the bar.** A fully neutral book beats T-bill + 4% only if residual
   rank IC after construction losses is about 0.031–0.039 (`research/hurdle_by_size.out`).
   SYY-style composite: +0.010 on 2015–2020, −0.005 on 2019–20 (`research/pre2021_noise.out`).
2. **Neutral books are calm.** Idiosyncratic TE is about 2–3% at N 200–500 and gross 1.77
   (ω ≈ 25.9%/yr), so an 8–12% vol target needs style tilts.
3. **Yearly swings are mostly noise.** Monthly IC sd ≈ 0.10 → yearly IC s.e. ≈ 0.029. At
   IC 0.02 a losing year has 24% probability. Only independent signals and removing style
   bets reduce it.
4. **Selection luck ≈ the hurdle.** Best-of-96 settings on 24 months adds +0.044 to +0.062 IC
   from luck alone. Hence ≤12 configs, 1-SE rules, paired block-bootstrap gates.

## 2026-10-23 — Forecaster fold 1 (train targets 2015-02..2018-12, validate 2019-01..2020-12)

Source: `out/forecast/fold1/report.json`, `diagnostics.json`, `registry.csv`.

| Validation 2019–20 | Rank IC (t) | Top−bottom 10%, 21d (t) | 2019 | 2020 |
|---|---|---|---|---|
| 50/50 blend ridge+MLP | 0.023 (0.81) | −0.53% (−0.42) | +1.80% | −2.93% |
| MLP alone | 0.036 (2.43) | +0.66% (1.12) | +1.77% | −0.61% |
| Ridge (EB, month-level) | 0.005 (0.13) | −1.85% (−1.05) | +1.31% | −4.78% |
| GBT alone | 0.040 (1.77) | — | — | — |

Conclusions:
5. **Month-level EB collapses the linear model.** With 46 effective months it shrinks 147
   slopes to df ≈ 0.3. What remains is a fixed covariance-weighted composite, and it lost
   money in 2019–20. That verdict comes from training data, not validation returns.
6. **IC and return spread can disagree in sign.** The blend had IC +0.023 but decile spread
   −0.53%. Never promote on IC alone; always report the return-terms spread with it.
7. **The edge lives where we cannot trade.** Blend IC: full universe 0.055 (diagnostic),
   tradable 0.023, short-eligible 0.012.
8. **One year can decide a 24-month validation.** 2020 is negative for every model.
   Validation s.e. on IC is 0.015–0.03.
9. **No measurable short-horizon alpha.** Per-day slope by age (1–63 days) is within ±2 s.e.
   of zero, first days negative. Monthly cadence; the weekly test (E4) fails by rule.
10. **Don't calibrate magnitudes by regression on 24 months.** The slope of return per unit
    z was negative (−0.0028) despite positive IC. Use Grinold IC·ω·z with a stated IC.
11. **MLP vs GBT by rule.** GBT − MLP paired IC gain was +0.0016 ± 0.0049 (< 1 SE), so the
    MLP stays.
12. **Process.**
    - sklearn `early_stopping` uses a shuffled split; it stays off (B14-type leak).
    - LightGBM runs `deterministic`.
    - The loader blanks every label ending after 2020-12-31 and asserts it.

Resolved in lesson 14: ridge half dropped. Fold-1 labels were price-only (see 13); later runs add dividends.

## 2026-10-23 — Data check H5 (`out/audit/dsf_vs_panel.json`)

13. **The organisers' daily returns are price-only.** 86% of stock-months match panel
    total `ret` to 1e-4. Payers (yield > 2%) have median gap 0 but mean gap 0.37%/month,
    about their 0.39% monthly yield. So the dividend is missing on ex-dates. Labels now
    add each month's gap back across its sessions (`data.with_dividends`).

## 2026-10-23 — The initial plan's forecaster, tested as written

Nested expanding walk-forward. Each test year 2017–2020 picks λ on the year before by
1-SE (heavier), then refits on all earlier data. That gives 48 held-out months, all
judged on the same realised 21d total-return label in the tradable universe.
2019–20 had already been seen in fold 1 (disclosed: "chronological ≠ untouched").
Sources: `out/forecast/initial_plan/report.json`, `checks.json`, `registry.csv`
(12 configs, 63 trials counting the λ path).

| Config | IC (t) | Spread 10%, 21d (t) | Within-sector spread (t) | Factor α 21d (t) |
|---|---|---|---|---|
| R1 plain ridge | 0.016 (0.71) | −0.74% (−0.72) | −0.50% (−0.59) | 0.49% (0.89) |
| R2 hierarchical ridge (plan default) | 0.018 (0.84) | −0.60% (−0.61) | −0.40% (−0.49) | 0.56% (1.10) |
| R3 + sector controls | 0.033 (2.14) | +0.31% (0.30) | −0.59% (−1.52) | 0.14% (0.19) |
| R7 residual target | 0.025 (1.10) | −0.71% (−0.66) | −0.47% (−0.57) | 0.92% (1.87) |
| G1 GBT depth 3 | 0.029 (1.85) | +0.51% (0.79) | +0.25% (0.56) | 1.27% (2.02) |
| G2 GBT residual | 0.027 (1.75) | −0.02% (−0.03) | +0.02% (0.03) | 1.36% (2.52) |
| M1 MLP | 0.023 (1.81) | +0.34% (0.64) | +0.24% (0.69) | 1.07% (2.26) |

14. **The default ridge fails the plan's own promotion test.**
    - Validation chose the heaviest penalty in every year (df ≈ 0). Inner-year IC was
      flat across five orders of λ and swung −0.045 to +0.06 between years.
    - The forecast is a static large-cap (size +0.49), low-beta (−0.32) tilt.
    - Calibration slope is wrong-signed (−335). Within-sector spread is negative.
15. **The hierarchy shares nothing measurable.** R2 − R1 = +0.002 ± 0.002 IC.
16. **Sector controls only buy sector bets.** That is unusable in a sector-neutral book.
17. **Missingness indicators, √ADV loss weights and the sector-demeaned target don't
    help** (all within 1 SE, mostly negative).
18. **The daily-aligned label costs nothing.** `y21` and monthly `ret_exc_lead1m` give
    identical IC (Δ 0.0000), so the earnable-timing label stays primary.
19. **"Do not assume residual targets must win": they don't.** They raise factor α
    but not the within-sector spread a neutral book earns.
20. **The challenger beats the default.**
    - GBT vs R2: spread +1.11% ± 0.64% (1.7 SE). MLP vs R2: +0.94% ± 0.74%.
    - GBT vs MLP is a near-tie: IC +0.006 ± 0.005, spread +0.17% ± 0.31%. The MLP was
      chosen once on 2019–20 and stays; the GBT is reported beside it.
21. **Nonlinear models trade more.** Rank autocorrelation is 0.67–0.70 vs 0.86 for ridge,
    and top-decile churn about 0.50 vs 0.40. Net economics need the engine.
22. **Every model loses in two places.** The first held-out month (Jan 2017 target) is
    −1.8% to −6.8%, and 2020 is negative for all (−1.0% to −5.1%).
23. **The MLP is still below the hurdle.** Held-out IC is 0.023 tradable and 0.019 within
    sector, against 0.031–0.039 needed. The fallback book stays the likely headline.

Plan changes made (REVISED_PLAN §3; MLP later superseded by E-LASSO, lesson 35): forecaster = MLP alone (ridge and the 50/50 blend
dropped), no sector controls, no missingness indicators, raw-excess `y21` with
dividends, Grinold magnitudes. Still to run on the MLP: the +1m vintage lag (H2).

## 2026-10-23 — E-LASSO (Han, He, Rapach, Zhou), run unchanged

Code: Rapach's `elasso_06-16-2024.zip` (Drive), kept byte for byte in `external/elasso/`
(`SHA256SUMS` checked before the run). Spec: Internet Appendix A1.2–A1.4
(`external/fm_appendix/`). Run in R 4.4.3 / glmnet 5.0 via `elasso/run_elasso.R`.

We changed only I/O, building the authors' data contract from the 2018 WP's data section:
- characteristics winsorised at 1/99% and standardised within month, NA → 0 ("FillCsm");
- the month-t return is matched to characteristics at t−1, with WLS weight `me` at t−1;
- our 147 characteristics, tradable universe, `ret_exc_lead1m` (decimal → the code's percent);
- target months 2015-02..2020-12, nothing after.

**Why not `y21`:** the 21-day label ends one session into the next month, so month-t
coefficients would see a day the book can't. The monthly label keeps the clock clean.

Authors' own evaluation (unchanged script, 2015-03..2020-12, value-weighted):
R²_CSOS −0.03% (MaInf). Mincer-Zarnowitz slope 1.22 (t 2.35 against 0, 0.43 against 1),
so the magnitudes are calibrated. Encompassing θ (weight on C-LASSO) 0.59.

Our harness, same 48 held-out months as initial_plan (`out/elasso/report.json`):

| Forecast | IC (t) | Short-eligible IC | Spread 10% (t) | Within-sector (t) | Factor α (t) | Rank autocorr / top-decile churn |
|---|---|---|---|---|---|---|
| E-LASSO MaInf | 0.031 (2.38) | 0.034 | +0.86% (1.59) | +0.42% (1.03) | 0.66% (1.14) | 0.56 / 0.60 |
| E-LASSO Ma1 | 0.041 (2.65) | 0.042 | +1.62% (2.45) | +1.13% (2.11) | 1.22% (1.80) | 0.31 / 0.70 |
| S-LASSO MaInf | 0.023 (1.85) | 0.023 | +0.33% (0.63) | +0.05% (0.13) | 0.62% (1.76) | 0.71 / 0.48 |
| C-LASSO | 0.019 (1.00) | 0.023 | +1.07% (1.36) | +0.67% (1.10) | 0.43% (0.48) | 0.10 / 0.81 |
| MLP (reference) | 0.023 (1.81) | 0.015 | +0.34% (0.64) | +0.24% (0.69) | 1.07% (2.26) | 0.67 / 0.53 |

24. **E-LASSO is the strongest forecaster tested, and its edge sits where we can trade.**
    - Short-eligible IC is ≥ tradable IC (MLP: 0.015 vs 0.023).
    - The liquid-half IC beats the illiquid half (MaInf 0.040 vs 0.023), the reverse of the MLP.
25. **It survives 2020.** MaInf +0.80%, Ma1 +2.07%, while every other model lost. The source
    is C-LASSO's month-by-month re-estimation (C-LASSO alone: +4.9% in 2020).
26. **It wins but is not yet decisive.**
    - Paired vs MLP: MaInf +0.53% ± 0.51% spread (1.0 SE), IC +0.007 ± 0.013.
    - Ma1: +1.28% ± 0.72% (1.8 SE).
27. **Ma1 is mostly last-month payoff persistence.** Rank autocorrelation 0.31 and top-decile
    churn 0.70 mean very high turnover. Its gross edge must survive $1bn costs before it
    counts.
28. **Some of the edge is style.** MaInf tilts momentum +0.25, value −0.19, profitability
    +0.15. Factor α t is 1.14, below the raw spread t of 1.59. Expect a sector/size/beta-neutral
    book to keep only part of it.
29. **Smoothing windows are degenerate here.** With 70 months of history, Ma36/60/120 ≈ MaInf.
    The method's long-window smoothing cannot be tested on this panel.
30. **Trials.** 11 more forecast columns judged (5 E, 5 S, 1 C). The cumulative registry is
    now 74 trials on 2017–2020, and 2019–20 has been seen three times.

Decision: see lesson 35.

## 2026-10-23 — Refit frequency and daily data (`out/elasso/decay.json`)

31. **E-LASSO already refits monthly.** It is a Fama-MacBeth method: a new cross-sectional
    regression every month. Ma1 uses last month's payoffs and MaInf averages every month so
    far. That recency is why it adapted in 2020. Only the MLP/GBT/ridge were refit yearly
    (R§3 rule). A monthly refit adds about 2% more data per fit; low prior, cheap test.
32. **There is no front-loaded alpha to harvest daily.** E-LASSO per-day payoff by age:
    days 1–5 are within ±1 SE of zero, the clearest edge is days 5–10 (~+4–5 bp/day, ~1.8 SE),
    and it then fades.
    - MaInf keeps earning in months 2–3 (+0.7 bp/day); only about 50% of its 63-day alpha
      arrives in month 1. So hold longer with bands; don't trade faster.
    - Ma1 delivers about 75% of its alpha in month 1 and nothing after day 42.
33. **Daily data should not be used as more observations.** Characteristics change
    monthly, so daily regressions on them re-cut the same information. 21× the rows ≠ 21×
    the evidence, as the initial plan warns.
34. **Where daily data can add value:**
    - risk, beta, ADV and execution, as already planned;
    - a pre-registered mid-month payoff refresh: E-LASSO on rolling 21-trading-day payoffs,
      re-run weekly. One trial, judged net of costs in the engine; low prior given lesson 32;
    - new daily-only characteristics, gated like any new signal family.

## 2026-10-23 — Decision

35. **The forecaster is E-LASSO** (user: "yes please replace with E-Lasso"; D6 in [DECISIONS.md](/home/drewclaw/Forkfiam/fiam/v4b/DECISIONS.md)).
    - MaInf is primary. Ma1 is the one alternate, chosen only on net IR at $1bn in the
      engine.
    - The MLP, GBT, group-ridge and 50/50 blend are retired to comparison baselines.
    - It runs from the authors' unchanged code (`external/elasso/`, checksums) through
      `elasso/`, trained on `ret_exc_lead1m` and evaluated on `y21`.
    - Recorded in REVISED_PLAN, CONTINUATION_PLAN, EVALUATION (banner), README,
      `config/final_2026.json` (`policy.forecaster*`), `engine/mandate.py` and
      `elasso/forecaster.py`.

## 2026-10-23 — Forecaster freeze (`out/elasso/frozen.json`, `lag1.json`)

Estimated once on the 48 held-out months (eom 2016-12..2020-11) by
`elasso/freeze.py`; block bootstrap over months (block 3, 2000 draws).

36. **Raw E-LASSO levels are market timing, and the timing is wrong.**
    - Monthly forecast medians swing -4.3%..+8.4% while within-month sd is
      ~0.4-0.5%. In target Dec 2020 every stock is forecast +7%..+11.6%.
    - Levels MZ slope on the monthly label: MaInf -0.11, Ma1 +0.56. The
      authors' 1.22 (full window, their statistic) does not survive as a
      held-out levels slope. Only centred dispersion is earnable (D7).
37. **Centred calibration halves the forecasts.**
    - MaInf on `y21`: 0.547, s.e. 0.366, 90% CI -0.016..1.180 (covers both 0
      and 1: weak). On the monthly label: 0.641 (0.108..1.236).
    - Ma1 on `y21`: 0.590, s.e. 0.184, 90% CI 0.264..0.877 (excludes 1).
    - Point estimates frozen in config; the optimiser must not read raw
      magnitudes or it overtrades by roughly 2x against costs.
38. **Decay confirms lesson 32 by the IC route: MaInf builds, Ma1 fades.**
    - MaInf mean IC by horizon: 1d -0.009, 5d +0.001, 10d +0.024, 21d +0.031,
      42d +0.037, 63d +0.046. The exponential IC fit degenerates to a
      constant (no decay to fit). Cumulative-alpha kappa 0.0052/session
      (half-life 132 sessions), 90% CI ~0..0.055: weakly identified, frozen
      at the point estimate.
    - Ma1: IC peaks at 21d (0.041) then eases (63d 0.033); kappa 0.070
      (half-life 10 sessions), 90% CI 0.004..0.165. Ma1 staleness bites
      within one holding month; MaInf staleness barely does.
39. **H2 vintage lag: the primary is unharmed, the alternate is not.**
    Unchanged authors' code, characteristics one month staler throughout
    (`elasso/lag_check.py`). MaInf IC 0.031 -> 0.038, paired +0.0070 ± 0.0066,
    spread +0.91% ± 0.41%. Ma1 IC 0.041 -> 0.020, paired -0.0211 ± 0.0162.
    Vintage risk is therefore bounded for the shipped column. The lagged
    variant is NOT adopted: picking it on this window would be the selection
    the registry exists to prevent. Registry now 75 trials.
40. **Burn-in is not validation.** Before eom 2016-12 the MaInf average spans
    <21 regressions; Ma1/MaInf monthly rank correlation is -0.27 (2015-09)
    and -0.16 (2016-04). Engine validation formations start 2016-12.

## 2026-10-23 — Risk model (`out/risk/report.json`, `fiam/v4b/risk/`)

48 formations (eom 2016-12..2020-11), frozen fallback and E-LASSO decile books.

41. **The factor model fits levels but lags regimes.** Daily WLS market factor
    correlates 0.97 with the liquid universe's mean excess return; crash-day
    uncentred R2 57-76%, median day 20%. Factor vols (annualised): market
    18.8%, styles 2.0-5.9%. But market-factor bias std(z) is 1.40 overall -
    0.74 in calm 2017, 2.17 in 2018, 1.53 in 2020. EWMA-84 cannot see a vol
    spike before it starts; no backward-looking estimator can.
42. **Book vol is understated by 30-50%, worst where specific risk dominates.**
    Decile book bias 1.29 (factor share 80%); fallback bias 1.51 rising by
    year 1.12 -> 1.93 (specific share 88%). Specific variance at the median
    name is overpredicted (realised/predicted 0.63) yet the fallback book
    still understates: residuals co-move in stress (omitted factor), which
    a diagonal D cannot represent. Horizon scaling is exonerated (iid
    21xF1 bias 1.22 vs autocovariance form 1.29). No multiplier fitted (D8).
43. **HAR loses on residuals.** The repo HAR design retargeted at factor
    residuals: QLIKE 0.795 vs EWMA-168 0.583, Diebold-Mariano t +4.3 (favouring
    EWMA), 91,678 stock-months 2017-2020. EWMA-84 is close (0.599). The repo
    result (HAR beats LightGBM for total vol) does not transfer to D.
44. **Beta uncertainty matches the eval arithmetic.** Decile-book hedge-beta
    SE median 0.021, p90 robust bound 0.052; fallback SE 0.007. Constrain
    nominal beta to ±0.02, report ~0.05 robust. Vasicek shrinkage cuts raw
    beta dispersion (sd 0.49 -> 0.45 in the probe cross-section) and the
    weekly grid never uses same-week returns.

## 2026-10-23 — Monthly controller continuation (E0–E3)

45. **Fix signs with the exposure limits visible.** Global forecast tails
    omitted opposite-side hedge names within sectors. An unbanded stage-0
    solve plus raw-alpha support scores stranded the financial sector long;
    February 2017's sector slack reached 0.56. Stage 0 now sees the limits,
    spans the liquid universe, and passes its constraint shadows into greedy
    scores. A generic sector-level-alpha regression reproduces the failure.
46. **Expand support before reducing gross.** The former loop reduced gross
    on the first selected support before trying more names. In February 2017,
    300 requested names settled at 150% while wider support could fund 180%.
    A synthetic 0.5%-capacity fixture reproduces this error. At each gross, the solver tries the normal and relaxed minimum on each
    support, including enlargement, before reducing gross; every attempt is
    recorded. The realised count can exceed the hurdle's
    requested N; it is always reported rather than described as N independent bets.
47. **Support costs and forecasts need the same units.** Multiplying a
    spread by a position weight before subtracting it from expected return
    understated entry cost. E3 uses per-dollar entry cost (spread plus the
    QP impact proxy), waives entry for a same-side incumbent and credits its
    avoided exit including impact. The 50%-spread synthetic case now rejects
    names whose forecast cannot pay their entry cost. No cost scalar was fit.
48. **Actual fills and NAV are state.** The controller now forms the next
    target from executed holdings and compounded NAV inside the simulator,
    not the previous target drifted at an assumed $1bn. Forecast decay,
    covariance and borrow use the same sessions-to-next-review horizon.
    Missing shorts remain frozen with borrow; spreads lag execution; actual
    sales, not denominator-induced weight changes, trigger D3's short-add check.
49. **Report process failures before model selection.** Count, leverage,
    capacity, short-floor and policy exposure violations are preserved in
    executed-book files. Promotion cannot skip a failed predecessor or pass
    on return evidence while compliance fails. Paired bootstrap intervals
    recompute IR; return-difference intervals remain additional evidence.
    The 2019-selection/2020-confirmation cut does not undo repeated use of
    2017–2020, which remains disclosed validation reuse.

50. **Construction with costs helps; compliance still blocks shipping.** E3
    net IR -0.139 versus E2 -1.849; the paired
    improvement interval is positive, and 2020 confirms the direction.
    Yet E3 has 2,041 executed rule/capacity breach rows. The fallback has
    5,856; neither is eligible. The next work is actual repair,
    not relaxing gates or unsealing OOS (D9). Yearly results are in
    `out/engine/yearly_performance.csv`, for all six books.
51. **Independent reconciliation needs float64 arithmetic.** The simulator
    promoted float32 source returns to double, while the monthly reference
    initially compounded in float32: max baseline gap 5.95e-8. A focused test
    reproduces it. Casting before compounding cuts the gap to 1.38e-15.
    This corrected reporting only, not trading results. All six references
    now pass; the original generator and refreshed report identities are
    preserved separately in `out/engine/manifest.json`.

## 2026-10-25 — Rolling E-LASSO and the left/right-tail score (D11; `out/elasso/rolling/judge_valid.json`, `judge_oos.json`)

The authors' unchanged code, re-estimated every month through 2026-08 for
three labels (`ret`, `up` = top-decile indicator, `down` = bottom-decile
indicator). Tail score = MaInf(up) − MaInf(down). Decile returns are
equal-weight relative to the month's mean; "≥$500m" is the shortable pool.

52. **The rolling run reproduces the original pre-2021 forecasts** (140,443
    rows, max |Δ| 1.2e-13 MaInf, 1.0e-12 Ma1). Extending the window changes
    nothing before 2021, as a real-time method must.
53. **Validation (48 formations, 2016-12..2020-11) was split:**
    | Score | IC (t) | Spread (t) | D9 (t) | D0 ≥$500m (t) | Spread ≥$500m (t) |
    |---|---|---|---|---|---|
    | mean MaInf | 0.031 (2.09) | +0.94% (1.40) | +0.63% (1.94) | −0.42% (−0.99) | +1.21% (2.15) |
    | tail MaInf | 0.036 (3.51) | +0.72% (1.72) | +0.50% (2.97) | +0.03% (0.09) | +0.53% (1.45) |
    The tail score ranked better and more steadily; the mean model had the
    better shortable bottom decile. By the D11 rule (≥$500m spread and both
    legs right-signed) **mean MaInf stayed primary**.
54. **The separate tail heads learn extremeness, as QUARCC-Black found.**
    `up` alone has validation IC −0.015 and OOS −0.082; `down` alone has a
    positive IC but a wrong-signed spread. Only their difference is directional.
55. **2021–2026 (68 formations), opened once for both candidates:**
    | Score | IC (t) | Spread (t) | D9 (t) | D0 (t) | D0 ≥$500m (t) | Spread ≥$500m (t) |
    |---|---|---|---|---|---|---|
    | frozen mean MaInf (D10) | −0.033 (−2.47) | — | — | — | — | — |
    | rolling mean MaInf | +0.004 (0.23) | +0.34% (0.44) | −0.26% (−0.54) | −0.60% (−1.31) | −0.48% (−1.12) | +0.61% (0.81) |
    | rolling tail MaInf | **+0.047 (4.32)** | **+1.75% (3.11)** | +0.54% (1.94) | −1.21% (−2.27) | −0.50% (−1.00) | +0.98% (1.87) |
    Tail-score IC is positive in every calendar year 2021–2026 (0.020–0.101).
    Rolling re-estimation alone repairs the frozen inversion but leaves the
    mean model near zero; the mean model's long decile is wrong-signed.
    The shortable short tail is the weakest part of both (t ≈ −1); 2024–2025
    shortable D0 is wrong-signed for the tail score.
56. **Protocol.** The pre-registered rule picked the mean model, which did
    worse after 2020. Promoting the tail score now is a choice informed by
    2021+ and must be disclosed as such (registry +2 trials, D11).

## 2026-10-25 — Why the tail score is weak on shorts (`elasso/short_diagnosis.py`, `out/elasso/rolling/short_diagnosis.json`)

Shortable pool (me ≥ $500m), tail score MaInf, returns relative to the pool's
equal-weight mean; validation = formations 2016-12..2020-11, OOS = 2020-12..2026-07.
Diagnostic only; nothing was selected. The tail score became primary on
2026-10-25 (user: "1. yes"), disclosed as a post-2021 choice (D11, lesson 56).

57. **The forecaster ranks shorts correctly; the payoff is right-skewed.**
    | Short decile D0 | Validation | OOS |
    |---|---|---|
    | name-month median | −0.89% | −1.94% |
    | mean | −0.00% | −0.59% |
    | mean excluding the top 5% | −2.26% | −3.57% |
    | mean of the top 5% | +42.9% | +55.9% |
    | skew | 1.98 | 2.01 |
    The typical short loses, as forecast. A few jumps (one name-month in
    twenty, averaging +43–56%) cancel the leg. The long decile has no such
    gap (median ≈ 0, mean +0.5%).
58. **D0 is a lottery/distress bucket.** Versus the middle decile: daily ivol
    3.1–4.1% vs 1.6–1.9%, beta 1.3–1.5 vs 1.1, max daily return 6.8–8.7% vs
    3.1–3.8%, idiosyncratic skew +0.33 vs ≈0, last-month winners (+5.6–6.6%),
    higher O-score, lower gross profitability, lower characteristic coverage,
    median cap $1.5bn vs $3.9–4.8bn. Healthcare (GICS 35) is 37–44% of D0,
    +20–27pp over its pool share. The tail heads are extremeness detectors:
    D0 names rank high on *both* p_down (0.92) and p_up (0.78–0.83);
    cross-sectional corr(up, down) is 0.85–0.89 (QUARCC Exp14: 0.987).
    Linear E-LASSO, fitted with me weights, extrapolates furthest on these
    smaller, extreme-characteristic names.
59. **The jump risk sits in the high-volatility shorts.** Within D0, the
    top ivol tercile has the most negative median (−1.0% / −3.5%) but the
    worst mean relative to it (+0.51% / −0.11%). The low-ivol tercile is
    negative in both windows (−0.19%, t −0.66 / −0.29%, t −0.97). The same
    pattern holds for max daily return. D0 also co-moves with the market
    (corr 0.47 / 0.32 vs 0.16 / 0.13 for D9): +1.1% / +0.7% in strong-market
    months, −1.0% / −1.7% in weak ones. A hard beta band hedges that part.
60. **What does not explain it (both windows):** sector alone (within-sector
    ranking: D0 +0.11% val / −0.45% OOS, mixed); dividing the score by ivol
    (spread falls in both); the E-LASSO p_up as an "opposite-direction" filter
    (validation favours low-p_up shorts, OOS the reverse); size buckets
    (best bucket flips between windows). Healthcare shorts were the drag in
    validation (+0.57% vs −0.26%), not in OOS (−0.61% vs −0.56%).
61. **Consequence for risk.** The short leg needs a measure of each name's
    *upside* tail (an opposite-direction interval), sized against the
    forecast: a mean-variance QP and a symmetric σ treat a +50% jump on a
    short like any 3σ move. The E-LASSO tail heads cannot supply it (lesson
    60); it must come from the name's own return distribution (ivol, max
    return, skew), calibrated on pre-2021 residuals.

## 2026-10-25 — Jump probabilities as a risk metric (`risk/jumps.py`, `out/risk/jumps/evaluation.json`)

Shortable pool. Label: next-month return relative to the pool mean ≥ +20%
(up-jump) or ≤ −20% (down-jump). Daily jumps: |market-adjusted return| >
4 × lagged bipower vol, from the organisers' dsf_mini, kept only where a
stock-month compounds to panel `ret` within 2% (drops the 2026 unadjusted
splits causally). Logistic model on 15 pre-specified features, refit each
January on an expanding window of realised labels.

62. **Monthly jumps are predictable in size, not direction.** AUC up/down:
    validation (2017–2020) 0.776 / 0.779, OOS 0.771 / 0.796; Brier skill
    3.1% / 2.6% and 3.9% / 5.2%. The top predicted decile realises 12–15%
    jump months against 0.3% in the bottom one. Volatility carries almost
    all of it (ivol-only AUC 0.76–0.79); the full model adds ≈ +0.01 AUC.
    Past daily-jump counts add nothing beyond ivol. Up and down
    probabilities load on the same features (ivol, max daily return,
    turnover, deal 8-Ks, healthcare): the model sees *how big* a move will
    be, not which way. Middle deciles are under-predicted ≈1.5× in both
    windows; recalibrate on training data before use.
63. **A jump costs about a third of the position.** Mean relative return
    given an up-jump +32% / +34%; given a down-jump −28% / −29%
    (validation / OOS).
64. **Shorts: the jump-prone third is noise; the rest is the edge.**
    Bottom 20% of the tail score, by tercile of predicted up-jump probability:
    | Tercile (p_up) | Valid mean (t) | Valid median | OOS mean (t) | OOS median | Monthly sd val / OOS |
    |---|---|---|---|---|---|
    | low (1–2%) | −0.32% (−1.45) | −0.49% | −0.19% (−0.73) | −0.26% | 1.5% / 2.1% |
    | mid (3–5%) | −0.19% (−0.56) | −0.64% | −0.73% (−2.32) | −1.31% | 2.3% / 2.6% |
    | high (10–12%) | +0.33% (+0.53) | −1.29% | −0.26% (−0.34) | −3.17% | 4.2% / 6.3% |
    The high tercile has the most negative median and 2–3× the volatility,
    but its mean is a coin flip because 11–14% of its name-months jump
    about +33%. Low/mid terciles are negative in both windows.
65. **Longs are the mirror image: jump-prone longs carry the alpha.** Top
    20%, by predicted down-jump tercile: high tercile +1.10% (t 3.18)
    validation, +0.42% (t 0.82) OOS; the low tercile ≈ 0. The same names
    have high up-jump odds, which pay a long. So the risk metric must be
    direction-aware: an up-jump budget binds hard on shorts; longs keep
    variance control and a looser down-jump budget. QUARCC Risk/1 charges
    every position its *downside* ES regardless of sign, which is wrong
    for shorts.
66. **Unsettled delisted names were the hidden breach engine.** The
    Nautilus backend froze unquoted positions forever. In the 2017–2020 E3
    book these grew to 0.18 gross, +0.05 net and 35 names by late 2020
    (mean 0.089 gross, 16 names); the target part sat at gross 1.81, net
    +0.003. They carried most of the executed net/beta drift and every
    liquidation-days breach (no ADV). For ≥$500m names the panel's month
    return after the last daily quote averages −0.06% (93% within ±2%),
    so settling at the last mark is the delisting value (D12).
67. **The tail score is a small number in return units.** Centred MZ slope
    0.051 on a score with monthly cross-sectional sd ≈ 2.75pp gives an
    expected-return sd ≈ 0.14%/month (mean model: 0.55 × its own
    dispersion). Costs must therefore be modelled tightly; a 30bp round
    trip eats two months of a 1-sd name's alpha.


## 2026-10-26 — Why the short leg has no edge, competition pack only (`research/short_side/`)

Shortable pool (cap ≥ $500m), returns are beta + GICS-sector residuals, labels
end ≤ 2020-12 unless marked OOS. Diagnostics; the only choice proposed is the
blend in lesson 73 (not yet adopted).

68. **The E-LASSO plumbing matches the paper and the authors' code.** The row
    dated d carries month-d excess return with eom d-1 characteristics and
    eom d-1 market equity (max |Δ| 0); ghz transform reproduces to 9e-15;
    all 292,838 forecasts align with their labels; the authors' zip on the
    Drive link is byte-identical to `external/elasso_download/elasso.zip`.
    Four characteristics are dropped by the code in one month (all-NA).
69. **The one deviation is history.** HHRZ use data from 1980:01 and start
    forecasting in 1990:01 "to accommodate the 120-month moving averages".
    The pack starts 2015-01: 3 months behind the first forecast, 23 behind
    the first validation formation, 70 behind the last. Split-half
    reliability of the forecast ranking (odd vs even months): tail label
    −0.8 / −0.07 / 0.29 at 23 / 46 / 70 months; ret label −1.7 / 0.02 / 0.88.
    The 2021+ forecasts sit on 71–139 months, which is part of why the tail
    score looks better there.
70. **Noise is not what kills the shorts.** Richer labels (residual rank,
    normal scores, 20–30% tails) raise reliability to 0.95+ by 70 months but
    every one leaves the shortable bottom decile at +0.1–0.2%/month in the
    proxy. The tail score's D0 holds 19.7% of next month's losers and 17.2%
    of its winners: it finds names that will move, not their direction. D0
    is flat in every ivol quintile (−0.05 to −0.11%).
71. **Nothing in the pack predicts large-cap losers in 2015–2020 on its own.**
    No single characteristic has a stable residual short end (best |t| ≈ 2,
    all from 2018–2020 and against the textbook signs: high asset growth,
    issuance and low B/M rose). Classic short signals are |t| ≤ 1.2 (SUE,
    momentum, ivol, MAX, O-score, mispricing). Earnings-announcement drift
    from 8-K item 2.02 plus daily returns: worst quintile +0.02%/month,
    nothing inside the tail score's short third. The tail score's D0 tilts
    to ivol/MAX/turnover/low profitability, which did not pay there.
72. **The mean model is the only pre-2021 short leg:** D0 −0.38% (t −1.9),
    D0–1 −0.31% (t −2.4), concentrated in 2017–2019. The tail score has the
    steadier long leg (D8–9 t 3.2 vs 2.3).
73. **A fixed 50/50 rank blend of the two runs is right-signed on both legs
    in both windows.** Validation D0 −0.34% (t −2.0), D9 +0.36% (t +2.3),
    spread +0.70% (t +3.1); 2021–26 (already opened for both inputs, so not
    clean OOS) D0 −0.44% (t −1.5), D0–1 −0.46% (t −2.3), D9 +0.45% (t +1.8),
    spread +0.89% (t +2.1). On validation alone the mean model is still
    better (spread +0.94%); the blend trades some of that for the tail
    score's steadier long leg. Short D0 is still wrong-signed in 2020
    (+0.13%) and 2024 (+0.38%).
74. **The authors' encompassing step picks the 50/50 weight by itself.**
    Putting the tail score in return units (real-time value-weighted FM slope,
    MaInf) and running programForecastElasso.R's encompassing regression
    against the mean E-LASSO gives a real-time weight on the tail forecast of
    0.55–0.59 every year 2016–2019 and 0.50 in 2020, from pre-2021 data only
    (`research/short_side/encompass.py`). Combined in return units the
    forecast is a little weaker than the rank 50/50 (validation D0 −0.27%,
    t −1.3; spread +0.71%, t +2.9) because the mean forecast's larger
    dispersion dominates; in ranks the two get equal say, which is what the
    weight says they deserve.
75. **Shorts are profitable against their benchmark; the book loses them.**
    Short-leg profit (+ = shorted names fell), shortable pool, one-month hold
    (`research/short_side/short_leg.py`): bottom 10% of the 50/50 blend earns
    +0.34%/month (t +2.0) after beta + sector in validation and +0.44%
    (t +1.5) in 2021–26; inverse-upside-risk weights +0.29% (t +1.9) /
    +0.41% (t +1.7), worst month −2.85% / −5.29%. The earlier tables printed
    the shorted names' return (negative = profit). The old 2017–2020 E3 book
    delivered only +0.7%/yr of short alpha against ≈ +4%/yr in the decile:
    construction and costs, not the signal, lost it. Raw short-leg P&L is
    negative in any rising market because the leg carries the beta hedge.
76. **The upside-interval selection rule caps the tail but gives up the OOS
    edge.** Shorting the third of the blend's bottom 30% with the lowest
    95% upper bound (mu + 1.645·s_up, s_up = √(σ² + p_up·0.33²)): validation
    +0.25% (t +1.8) residual, +0.62% (t +2.6) market-relative, worst month
    −1.36% (plain −2.49%); 2021–26 +0.06% / +0.13%, worst month −3.58%
    (plain −6.12%). It selects low-volatility names, where the forecast has
    little to say. Using the interval for sizing (weights 1/s_up) keeps the
    edge in both windows; using it to select does not.

## 2026-10-26 — E-LASSO port and the C-LASSO defect (D13; `gpu/`)

77. **A faithful port has to follow glmnet's iterates, not just its optimum.**
    glmnet stops each lambda when a full sweep moves no coefficient by more
    than thresh (1e-7) in xv·Δ²; that leaves coefficients ~1e-4 from the
    exact LASSO solution. Replicating `standard` + `elnet1` step for step
    (big first lambda, active-set sweeps in entry order with lazy gradient
    catch-up, fdev/devmax stopping after 5 lambdas) matches R to ≈1e-11;
    an exact solver would not. Coordinate descent in interpreted torch took
    180 s for 8 months; compiled (numba), 14 s for all 139.
78. **The authors' C-LASSO assigns each selection to the wrong
    characteristic.** `tCoef[-1]` is applied twice in programForecastClasso.R;
    R recycles, so characteristic i takes characteristic i+1's weight. The
    defect is inside the published code and was in every R forecast through
    D12.
79. **The defect was flattering the mean model's short leg.** Corrected
    mean E-LASSO, validation shortable short-leg profit +0.19%/month
    (t +0.8) against +0.38% (t +1.9) with the defect; tail score +0.11%
    (t +0.5). The pre-2021 "mean model shorts" of lesson 72 were partly the
    mis-assigned C-LASSO selection, i.e. luck.
80. **D13 tournament (rule fixed first, `research/short_side/tournament.py`,
    `out/elasso/gpu/tournament.json`): `resrank` wins** — the only candidate
    with both legs at t ≥ 1 in validation: short +0.27% (t +1.7), long
    +0.30% (t +1.8), spread +0.57% (t +2.2), IC t +3.0. Not gated: mean
    (short t 0.8), tail (0.5), blend (0.8), tail20 (0.1), restail (0.7).
    2021–26 diagnostic for resrank: short +0.39% (t +1.3), long +0.14%
    (t +0.6), spread +0.53% (t +1.2), IC t +4.2; the blend and tail have the
    better 2021–26 long leg, which the rule does not let us use.
    Training on the rank of the beta-adjusted return removes the market
    and the right-skew outliers from the label, which is what lets the
    LASSO find direction among large caps.
81. **The CUDA backend reproduces the port; GPU only from here.**
    `gpu/glmnet_cuda.py` runs glmnet's control flow on thread 0 of one
    block per month and the gradient update across threads. It matched the
    CPU kernel exactly in the numba simulator and to ≤2e-11 on a Modal L4
    over all 139 `ret` months (6.1 s against 16.7 s on the container CPU);
    the `resrank` run trained on Modal matches the local run to 1e-12.
    The user does not want CPU reference runs any more ("getting the values
    for cpu will take ages"), so later runs go to CUDA without a CPU twin.
    numba-cuda needs numpy < 2.4 (pinned to 2.3.5 in the Modal image).

## 2026-10-26 — Why the book's short leg is worse than its long leg (`research/short_side/book_attribution.py`, `cap_buckets.py`, `borrow_net.py`)

Validation books with the forecast each was built from: E3_mean
(`out/nautilus/E3`) and E3_tail (`out/nautilus_d12/E3`). One-month hold,
beta + sector residuals, + = profit for that leg.

82. **The optimizer turns the short leg into a mega-cap hedge.** Long gross
    sits at the forecast's extreme (D8–9: 61% / 83% of long gross), short
    gross does not (D0–1: 39% / 40%; D3 and beyond: 43% / 38%). 97% / 90%
    of short gross is in names ≥ $10bn, against 79% / 47% of long gross.
    Decile → book: short +0.38% → +0.17% (mean), +0.06% → +0.06% (tail);
    long +0.56% → +0.52%, +0.38% → +0.32%.
83. **The cause is the flat 5% borrow on every short below $10bn.** 87–93%
    of each score's short decile is below $10bn, where the config charges
    5%/yr (0.42%/month), more than the decile's whole edge. Net of that
    borrow the shortable D0 loses in validation for every score (mean
    −0.18%, tail −0.28%, resrank −0.12%/month), so the optimizer correctly
    avoids it and fills the floor with ≥ $10bn names, whose D0 slice is
    7–13% of D0 with no reliable edge. The long leg pays no borrow. The
    case (§7) allows a schedule calibrated today and asks for the flat
    0.5%/5% only as the alternative reported alongside. Net of
    short-interest tiers (0.3/1/3/8%, `fiam/costs.py`) resrank D0 is +0.14%
    (t +0.9); at a 0.3% general-collateral rate +0.24% (t +1.6). Short
    deciles are crowded names: average tier borrow 1.5–1.8% vs 0.3% GC.
84. **Ex-jump, the short leg is as good as the long leg.** Residual jumps
    (|res| ≥ 20%) cost the book's shorts −0.08% / −0.16%/month and paid its
    longs +0.30% / +0.22% (t 2.5–2.9). Without them, short +0.25% / +0.22%
    vs long +0.22% / +0.10%. The forecast's extremes are high-volatility
    names (lesson 58), and right skew makes that a gift to longs and a tax
    on shorts. Sizing shorts by the upside interval (lesson 76) targets
    exactly this part.

## 2026-10-26 — The structural short-leg problem: the forecast's bottom is a volatility sort (`research/short_side/asymmetry.py`, `vol_loading.py`, `vol_fix.py`)

Shortable pool, beta + sector residuals, + = profit for that leg.

85. **The forecast ranks the downside as well as the upside, or better.**
    Rank IC inside the bottom half vs inside the top half: resrank +0.017
    (t 2.5) vs +0.011 (t 1.3) in validation, +0.045 (t 5.3) vs −0.005 in
    2021–26; mean and tail the same way. Characteristic arms are symmetric:
    over 147 characteristics the low arm (Q3 − Q1) averages +0.18%/month
    against +0.16% for the high arm; a linear model's assumption holds.
86. **What breaks the short leg is who sits at the bottom.** Every score
    loads negatively on idiosyncratic vol (rank corr resrank −0.45 / −0.57,
    tail −0.30, mean −0.23): D0 ivol 55–75% a year, D9 28–31%. D0's
    realised residual sd is 15–20%/month against 9–10% in D9, and its
    median −0.69% (−1.67% in 2021–26) against a mean of −0.27% (−0.39%):
    the right tail of high-vol names takes 60–75% of the short decile's
    typical win. The same skew pays the long leg (D9 median −0.04%, mean
    +0.30%). Within ivol terciles the asymmetry the user saw appears: in
    the high-vol third the model calls winners (+1.03%, t 2.6) and not
    losers (+0.16%, t 0.5); the short edge sits in the mid-vol third
    (+0.44%, t 1.9; 2021–26 +0.47%, t 2.1). Up-jumps are predictable in
    size, not direction (lesson 62), so in high-vol names the downside is
    noise by construction of equity payoffs (losses bounded, gains not).
87. **Pre-registered structural fix (`vol_fix.py`): `volneut` wins**, deciles
    taken within ivol terciles. Validation short +0.22% (t 1.7), long +0.38%
    (t 2.1), spread +0.60% (t 2.4) against base +0.27 / +0.30 / +0.57
    (t 2.2); short-decile ivol 40% instead of 55%, worst month −1.5%.
    2021–26 diagnostic: short +0.22% (t 1.2), long +0.19% (t 0.9), spread
    +0.41% (t 1.3). `exhivol` (no shorts in the top-vol third) passes the
    gate but loses on spread (+0.46%, t 1.8). Registry +2 trials. The gain
    is small: vol-matching removes the jump noise from the short leg but
    the short decile's mean stays near +0.2–0.3%/month, because the edge
    the model has on shorts is in the median, and a short pays the mean.

## 2026-10-26 — Risk-model accuracy at the portfolio level (`risk/enhanced.py`, `risk/beta_cal.py`, `risk/accuracy.py`, `out/risk/accuracy.json`)

48 formations 2016-12..2020-11; six books: resrank volneut decile book, its
long and short legs alone, the fallback, the executed E3 books (mean, tail).
z = realised 21-session excess / predicted vol, bias = sd(z) (target 1,
band ±0.20); beta error = realised 21-session OLS book beta − predicted.

88. **Volatility regime adjustment and residual PCA factors both pass, on
    all six books** (rule fixed first). Bias base → vra+pca: volneut 1.21 →
    1.15, long leg 1.52 → 1.41, short leg 1.39 → 1.36, fallback 1.51 →
    1.39, E3_mean 1.26 → 1.14, E3_tail 1.17 → 1.05. The hedged optimizer
    books are now inside the ±0.20 band; leg books and the specific-heavy
    fallback are not (2018 legs 2.0–2.3, the February and Q4 market
    spikes; fallback 2019–20 1.6–1.7). λ_F averages 0.88 in 2017 and 1.56
    in 2020 (max 3.1). A sector factor with numerically zero returns
    (`s_60`, |f| < 1e-12 on 421 days) must count as missing, or λ explodes.
89. **Predicted beta is biased on vol-tilted books.** On the volneut book
    realised beta exceeds predicted by +0.149 (RMSE 0.22): low predicted
    betas realise higher (long leg +0.067), high ones lower (short leg
    +0.082). Realised = 0.39 + 0.68 × predicted on average (cross-section,
    71 months): the Vasicek + 60m blend shrinks a third too little. The
    executed E3 books have ≈ 0 mean error (RMSE 0.10–0.13) because they are
    large-cap and beta-matched on both legs.
90. **The expanding-window beta calibration fixes it but fails the rule as
    written.** Errors volneut +0.149 → +0.044, long +0.067 → +0.002, short
    +0.082 → +0.042, RMSE never worse by more than 0.0014; but the three
    books already at ≈ 0 error moved by ≤ 0.003 the wrong way, so it is
    better on 3 of 6, not 4. Not adopted (off by default in
    EnhancedRiskModel); the rule's flaw is noted, the choice is the user's.

## 2026-10-26 — Optimizer review and the E5 objective (`engine/optimize.py`, `engine/ladder.py` E5)

91. **What the E3 objective did against the user's spec** (max return, min
    vol, min beta, subject to the rules): gross was forced equal to 1.8, so
    the short side had to be filled whatever its alpha; beta had only a
    ±0.02 band with nothing pulling it to zero inside (the market factor's
    variance prices (β'w)² at ≈ 0.03); variance was symmetric with no jump
    term. With the volneut forecast and short-interest borrow, E3's short
    gross already moves into the forecast's bottom 30% (0.98–0.99 of short
    gross on 2018-01 and 2020-02, against 0.39 in D0–1 before, lesson 82).
92. **E5** = max μ'w − costs − borrow − λ_β(β'w)², min vol through the
    enhanced risk model plus direction-aware jump variance (shorts
    p_up·0.32², longs p_dn·0.28²), predicted vol ≤ 6%/yr, gross ≤ 1.8, all
    hard rules. Three traps on the way: (a) the stage-0 support finder must
    keep E3's risk price, or the small E5 γ concentrates support into a
    lopsided set (147 longs / 96 shorts) that cannot meet the sector and
    net bands; (b) under a gross ceiling the first clean support is not the
    best: support sizes are compared on the objective; (c) from cash, the
    one-month cost charge and the liquidity caps hold the first build to
    gross 1.0–1.1 (no costs: 1.28); predicted vol 1.9–3.0%, beta 0.000.
    γ in {0.5, 2, 5} changes nothing: the vol cap does not bind at this
    forecast's strength; costs, caps and bands do.

93. **E5 validation book (2017–2020, Modal, `out/nautilus_e5/E5`).** Short leg after
    beta +4.0%/yr (t 1.5; +5.7% per unit gross) against +0.7% (t 0.2) in E3_mean and
    −0.5% in E3_tail: the volneut + short-interest borrow + E5 fix moved the short
    leg from noise to the same order as the long leg. Long leg after beta +2.1%/yr
    (t 0.9) against E3_mean's +7.7% (t 3.3), but E3_mean's long was 2020-heavy
    (+20% that year; ≈+3.5%/yr in 2017–19, close to E5's ≈+3.2%). Book: 5.0%/yr net,
    vol 4.7%, daily beta +0.02, max DD −6.5%, 7.7% before costs; impact (2.1%/yr) is
    the largest cost. Neither leg is significant on its own over 4 years, and the
    short alpha is uneven (2017 −5.9%, 2019 −2.3%, 2020 +16%). Compliance: the 490-
    name target plus names still being liquidated put the count above 500 on 202
    days (rebalance days hold ≈630 names); the formation target needs headroom under
    the 500 cap. Peak memory 63 GB: books of this size must run on Modal, never on
    the 15 GB box.

94. **Walk-forward + union fix, 2017–2020 (`out/nautilus_e5_wf2/E5`, D15).** Monthly
    refits on data <= r reproduce the monthly-run signal (IC21 0.027); yearly refits
    halve it (0.013), as the frozen model drifts within the year. The name count
    broke 500 only in the days after each rebalance: entries and exits trade over
    the same days and a 440-name target swapped 150–200 names. Trimming entries so
    held ∪ target <= 490 removed every name breach (156 days -> 0) at almost no
    cost. Book: 4.8%/yr net, vol 4.4%, daily beta +0.02, max DD −5.8%. Short leg
    after beta +4.6%/yr (t 1.7), long leg +1.1% (t 0.5): the short leg now carries
    the book; the long leg's 2020 (−7.5%) is its weak spot. Peak memory 39 GB.

95. **Single 2021–2026 run of E5 (walk-forward, D15; `out/nautilus_e5_oos/E5`).**
    0.6%/yr net against TB3MS+4%, net IR −1.47, vol 4.5%, daily beta +0.02, max DD
    −10.3%. Both legs after beta ≈ 0: long −0.6%/yr (t −0.2), short +0.5% (t +0.2).
    Costs 2.6%/yr (impact 2.0%) exceed the 3.4% made before costs, most of which is
    cash interest. Only 2026 (+12.4%, proxy total-return data) beat the benchmark.
    Forecast level (diagnostic, residual = r − beta60·mkt): volneut IC fell from
    +0.063 (t 3.5) on validation to +0.017 (t 1.3); the raw resrank score held more
    (+0.047, t 2.6). Out of sample the top decile is negative (−0.24%/m) and the
    edge is in the bottom decile (+0.93%/m equal-weighted, t 1.6), which the
    cap-limited value-weighted short book does not capture. Any change made from
    these numbers is a post-2021 choice and must be disclosed as such.

96. **Why the 2021–2026 book earned nothing while the forecast kept its edge
    (`research/oos_causes.py`, `out/oos_causes.json`; diagnostic).** The raw
    walk-forward resrank IC was +0.051 (t 5.1) out of sample, higher than validation
    (+0.027). The loss is in the book, not the forecast:
    (a) The edge lives in volatile names, in both periods. IC by ivol tercile, OOS:
        low +0.005 (t 0.4), mid +0.009, high +0.029 (t 3.8); validation: +0.019,
        +0.004, +0.030 (t 4.2). The residual return per unit of score rises with
        residual sd (OOS 0.09 -> 0.23 -> 0.71 %/month; sd 6.4 -> 9.5 -> 17.8%).
    (b) The optimizer is fed a rank (volneut x one scale): the same expected return
        for a 6%-sd and an 18%-sd name. Minimizing risk under that input puts the
        book in calm names: target ivol percentile 0.30 long / 0.23 short against
        0.44 / 0.49 for the score's own deciles, cap percentile 0.77. That is the
        tercile with no edge. Grinold-Kahn: alpha = IC x sigma x score.
    (c) Beta: the score loads −0.5 (volneut) / −0.63 (raw) on beta_60m. Holding a
        dollar- and beta-balanced book pulls both legs toward the middle (target
        score percentile 0.88 / 0.13 against 0.95 / 0.05 in the deciles).
    (d) volneut halves the OOS IC (0.051 -> 0.022): most of the raw OOS IC sits
        between ivol terciles.
    (e) Target book before costs, OOS: long +0.23%/m (t 1.1), short −0.18%/m (t −0.8)
        against +0.41 / +0.38 (t 1.6 each) on validation; costs 2.6%/yr then take the
        rest. Fixes informed by this are post-2021 choices and must be disclosed;
        (a) is visible on validation too, so a vol-scaled alpha can be judged there.

97. **Beta-matched selection wins the pre-registered variant race (2017–2020,
    `elasso/variants.py`; rule in its header, set before any book ran).** Ranking
    the score within beta_60m quintiles makes longs and shorts opposite in score but
    equal in beta, so equal dollars cancel the market and the hedge stops dragging
    both legs to the middle. E5 books: betamatch net +6.6%/yr, beta −0.002, long
    alpha +3.7% (t 1.5), short +5.0% (t 1.6), gross 1.72, costs 3.5%, max DD −9.3%;
    baseline +4.8%; volscale +4.4% (gross 0.85: the scaled alpha did not pay its
    costs in the book); betavol +2.9% (costs 4.3%). Vol scaling helps a decile sort
    but not the optimised book. Registry +3. The 2021–2026 run of betamatch is a
    second, disclosed look at that window (the first was lesson 95).

98. **Training on the holdable universe (v4's rule: train on the screen you trade;
    `walkforward --universe holdable`, `research/holdable_compare.py`).** Screen =
    ADV >= $9m (mandate arithmetic: $4.5m average position out in 5 days at 10%) and
    cap >= $500m, ~1,450–1,780 names a month. Validation, holdable pool: spread
    +0.67%/m (t 2.4) against +0.52 (t 2.0), short leg +0.36 (t 2.0) against +0.22 →
    adopted by the pre-registered rule. 2021–2026 (disclosed diagnostic): IC +0.036
    (t 3.7), yet the extreme deciles earn nothing (D9 +0.01, D0 short +0.10): the curve
    peaks in deciles 4–7 and turns at both ends, for both training universes. Terciles
    hold up better (long +0.12 t 1.0, short +0.24 t 1.6, before costs). An optimizer that
    concentrates in the extremes buys exactly the part that reverted out of sample.

99. **The D17 clean race: holdable training helps the forecast but not the book;
    the winner loses on 2021–2026 (2026-10-26).** On 2017–2020 the four E5 books all
    pass |beta| <= 0.05 with both legs' alpha > 0: all-name betamatch +6.5%/yr,
    holdable volneut +6.2, holdable betamatch +6.0, holdable raw +4.4 (gross 0.66: a
    calibration slope whose interval spans 0 sizes the book down). The winner's single
    2021–2026 run: −1.7%/yr, long alpha −3.6% (t −1.3), short +0.6% (t 0.2), +1.7%/yr
    before 3.3%/yr costs. The book runs at 5% vol against v4's 12%, so even a positive
    edge would have needed twice the risk to reach v4's 12.8%; here the edge itself is
    gone in the names the book holds (lesson 98: extreme deciles reverted).

100. **Earn the window: E6 fails its short-window gates, and the beta model is the
    structural defect (D19, 2026-10-26).** Before any full-window run, each hypothesis
    got a pre-registered test on Jan–Feb 2017 (2 formations, ~37 sessions), with ex-ante
    power. Nothing survived.
    - The signal gate removed raw/raw_s6 (calibration t 0.5, −0.1).
    - The optimiser is sound: every first-rung solve was optimal with all hard rules
      met, apart from one gross step-down.
    - The beta model is not sound. Across 2,003 names, realised beta rose 1.76 per unit of
      predicted beta (CI 1.43–2.11), and every "neutral" book carried +0.16 to +0.23
      realised beta.
    - Leg vol was overpredicted ~1.6×.
    - Step 2 lowered realised vol against the HHRZ reference (3.3–3.7% vs 3.9–4.2%), but
      2 months could not show it with the power required. With betamatch scores the
      decile reference is already near beta-neutral, so step 2 has little to do.
    - Lesson: a beta-neutral construction is only as good as the beta forecast's
      dispersion. Test that first, cheaply, on short windows, before any book race
      (the branch book's ex-ante 0 / realised sd 0.069 was the same warning).

101. **No trailing beta survives a sell-off, and our calibration map overcompresses
    (D20 step A, 2026-10-26).** Six beta forecasts (engine calibrated/uncalibrated,
    v4's Welch and Dimson, beta_60m, Welch+Dimson) were tested on the first two months of
    2017–2020.
    - Calm windows (2017, 2019): the uncalibrated engine beta and Welch+Dimson hit slope
      ≈ 1. The calibration map (on since D14, although it failed its own accuracy rule)
      pushed the slope to 1.4–1.8.
    - Sell-off windows (Feb 2018, Feb 2020): every forecast's slope fell to 0.1–0.6.
    - Neutral books can still carry beta at net 0 and predicted beta 0. The W17 E6 books
      did (+0.16..+0.23), because the beta error lined up with the long/short selection.
      That points to style exposure, not to the beta's level or scale.
