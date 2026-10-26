# Risk and cost audit — 2026-10-23

Scope: the monthly controller (`engine/optimize.py`), the risk model
(`risk/`), and the cost lines shared by the optimizer, the simulator and the
native Nautilus run. This audit changes no frozen D6/D7/D8 choice. It records
what is correct, what was wrong, and what remains a disclosed limitation.

**Bottom line.** The risk model is causally assembled and dimensionally
consistent, but it is not calibrated: realised risk is 1.29–1.51× its
forecast. The optimizer's old support cost was not merely mis-scaled; at the
mandate's $1bn NAV and typical ADV it was roughly **300–400×** the fill
model's impact, which distorted which names entered the support and made the
incumbent credit dominate. The QP impact proxy was also wrong in the
cross-section (over-penalising small caps, under-penalising large caps), fees
were missing, and support was cached without the trial gross. Those are now
fixed. The remaining cost mismatch is the 2026 proxy and the flat borrow
schedule, both labelled below.

## 1. Risk implementation

### Correct

- **Timing.** `risk/exposures.py` uses characteristics dated eom;
  `risk/factors.py` uses exposures carried from the last eom before each
  session and factor returns through the session; `risk/beta.py` carries beta
  weekly from the prior week; `risk/covariance.py` uses returns strictly
  before the formation session; `risk/specific.py` uses residuals through eom.
  The tests `test_covariance_has_no_lookahead` and
  `test_weekly_carried_lags` exercise the two easiest leaks and pass.
- **Dimensions.** `model.snapshot` returns `B` (N×K), `F` (K×K, H-session),
  `F1` (K×K, one-session), `d` (N, daily) and `horizon` (H). `model.variance`
  computes `B'w F B'w + H Σ d_i w_i²`; `test_variance_and_marginal_match_dense`
  matches a dense `BFB' + H D` covariance to 1e-10.
- **Hedge beta.** The market column is the frozen 50/50 daily-Vasicek /
  panel-60m blend, and the hard beta band reads the same column. The S&P
  exhibit is reporting only.
- **Specific risk.** EWMA-168 on factor residuals, 25% sector-median shrink,
  5th-percentile floor, applied at each eom. The D8 race is pre-OOS and
  `test_frozen_half_life_matches_report` binds the shipped constant to the
  report.
- **Net constraint.** The net band was previously only a finite penalty on a
  slack; it is now also a hard constraint (`sum(w) <= hard.net_band` and the
  negative side). The soft target remains in the objective so the solver can
  still explain a policy tension, but it cannot cross the mandate limit.

### Miscalibrated (known, not fitted away)

- **Bias.** `out/risk/report.json` records realised/predicted vol of
  **1.348** on the E-LASSO decile book and **1.515** on the fallback book,
  against a stated ±0.20 band. The 15% annualised guardrail is therefore
  looser in realised terms than its label: a book at the guardrail has
  historically realised roughly 19–23% vol. The QP's risk aversion of 20 is
  effectively about 12–15.
- **Beta uncertainty.** Estimated beta SE on the decile book is 2.1% median
  and 3.1% at p90; the policy band is ±2%. The nominal band is feasible for
  the diversified book (portfolio SE falls with N), but it is not a
  statistically robust per-name band. D8 already documents this; no extra
  band was fitted.
- **No regime multiplier.** The bias is a vol-regime lag plus omitted-factor
  co-movement, not a horizon mistake (iid gives 1.22 on the same book). A
  regime multiplier would be a new risk-model decision and is not silently
  included.

### OOS risk model

The 2021–2026 diagnostic uses the same frozen factor half-life (84) and
specific estimator (EWMA-168), with `RiskModel(cut=2026-08-31)`. No
coefficient or variance model is refitted on 2021+ labels. The monthly
exposure cross-sections and factor WLS do use 2021+ returns as they become
known; that is causal estimation, not a forecast fit. The frozen half-life and
specific choice were selected only on 2017–2020.

## 2. Cost implementation

The fill law is the simulator's square-root law. A trade of portfolio weight
`q` is worked over `D = 5` sessions, so the total return cost is

```
impact(q) = Y * sigma * sqrt(NAV / (D * ADV)) * |q|^(3/2)
```

and the native `Costs.get_commission` charges `Y * sigma * dollars *
sqrt(dollars / ADV)` per fill. Five equal fills reproduce the expression
above. The optimizer now uses the same `sigma` as the fill model
(`Formation.sigma`, the lagged 63-session realised vol), not the risk model's
total vol.

### Fixed in this pass

| Defect | Old | Corrected |
|---|---|---|
| Support entry cost | `Y*sigma*(NAV/ADV)*w` (linear) | `impact(w)` with the square-root law |
| Support exit credit | same linearised formula | `impact(|w_pre|)` |
| QP impact | `Y*sigma*(NAV/ADV)*q²` | quadratic matched at the average target position to `impact(q)`; conservative above it |
| Fees | absent | 5 bp commission both sides, 2.78 bp SEC on sales |
| Spread when `trade_costs=False` | charged unconditionally | only charged when the step pays trade costs |
| Support cache | keyed by name count only | keyed by `(count, gross, min_size)`; support is rebuilt for each trial policy |
| Support gross | built at policy 1.8 even when the gross ladder tried 1.0 | built from the trial policy |
| Fill sigma | risk-model total vol | lagged realised sigma used by the fill engine |

At NAV $1bn, median 2021 ADV $8.3m and a 500-name target (q≈0.0036), the old
support entry term is about **400×** the correct impact; at a 250-name target
(q≈0.006) it is about **320×**. The direction is the important part: the old
support score made holding an existing name look almost free and made a new
name look impossibly expensive, independent of the name's actual liquidity.
The old QP was inconsistent across the cross-section: at the same NAV it
overcharged a $8m-ADV name by roughly 1.5× and undercharged a $40m-ADV name
by roughly 1.5×, relative to the five-day law, so it pushed the book toward
large caps for the wrong reason.

### Still disclosed, not fixed

- **2026 data proxy.** `data/fiam_v1/daily_market_2026.parquet` uses the
  organisers' actual CRSP daily file through 2025-12-31. For 2026-01-01 to
  2026-08-31 it uses the monthly panel: a split-adjusted total-return index
  built by compounding monthly `ret`, with `prc/adjfct` only as the starting
  level; `dolvol_126d` as average daily dollar volume; and `bidaskhl_21d` ×
  the 2015–2020 size-group half-spread/high-low ratio. The raw mini
  `daily_return`/`close` is not used. The D5 splice ratio was not applied;
  using `dolvol_126d` directly is conservative on ADV by about 3.2%.
  FINRA verification of the 2026 ADV proxy was not completed. Every 2026
  number in the OOS report is therefore a proxy label, not a quote-verified
  result.
- **Borrow.** The flat schedule (0.30%/1.00%/3.00%/8.00% by short-interest
  tier, with a 1% micro floor) is the same in the optimizer, simulator and
  Nautilus. It is not a securities-lending quote and has no recall risk.
- **Fees.** The native/simulator setup charges commission and SEC Section 31.
  It does not charge FINRA TAF or CAT per share. `fiam/costs.py` contains
  those constants, but they are not wired into `sim.Setup` or
  `nautilus_backend.Costs`. The omission is small (sub-bp on typical fills)
  but is a real understatement.
- **Impact calibration.** `impact_y = 1.0` and the square-root exponent 1.5
  are the frozen simulator assumptions, not a fitted 2021–2026 estimate. The
  cost sensitivity runs are the honest range; the point estimate is not a
  measured execution cost.
- **Borrow/interest timing.** Nautilus funding and the simulator both charge
  daily; the optimizer charges `horizon/252` of the annual borrow rate at the
  formation. The difference is second-order.

## 3. What the corrected costs imply

- The old E3 accounting had about 3.86%/yr of costs, of which 3.02% was
  impact. Native Nautilus E3 (same old target set, corrected execution) has
  spread 0.142%, impact 2.995%, fees 0.061%, borrow 0.682%/yr: about 3.88%/yr
  total, but distributed differently. The near-equal total masks the support
  distortion: the old optimizer chose a different, lower-turnover book for
  the wrong reason.
- In the first 2021 diagnostic months, the corrected optimizer's 500-name
  book paid about 0.6–0.8% of NAV in impact on a rebalance. At monthly
  cadence that is a 7–9%/yr drag before borrow and spread. A gross active
  return of +2–4%/yr cannot survive it; the strategy needs either a much
  stronger signal, a smaller book, slower trading, or higher participation
  capacity.
- Costs are not the only source of instability. The frozen MaInf forecast has
  a **negative** 2021–2026 rank IC (see the OOS report), so the cost drag is
  applied to a signal that is pointing the wrong way in several regimes. No
  cost fix can make that book predictable.

## 4. Files changed in this audit

- `engine/optimize.py`: three-argument cost functions, fees, support cache
  key, trial-gross support, conditional spread, hard net band,
  `Formation.sigma`, fill-matched sigma.
- `engine/inputs.py`: sigma uses returns clipped at ±50% so a vendor bad tick
  cannot become a 100%-daily-vol cost input.
- `engine/ladder.py`: parameterised `World` for cut/window/daily/forecast,
  `Formation.sigma`, panel cut in metrics/fallback.
- `engine/nautilus_data.py`: `from_world` honours the world's daily path/cut.
- `elasso/oos.py`: frozen 2020-12 coefficient application and OOS forecast
  build.
- `engine/oos_data.py`: 2026 proxy build.
- `research/run_nautilus.py`: OOS branch and diagnostic labels.
- `tests/test_optimize.py`: square-root-law and quadratic-proxy regressions.

The 2021–2026 run is a **diagnostic** evaluation of a frozen model. It is not
a final book: E3 still has executed gross/count/liquidation breaches in
2017–2020, and the 2021+ books are labelled with the same caveat.

## 5. Corrected 2021–2026 OOS costs and compliance (2026-10-24)

The corrected native run (`out/nautilus_oos/E3`) changes the cost picture
materially:

- Total costs **6.39%/yr**: impact **4.85pp**, spread **0.32pp**, fees
  **0.08pp**, borrow **1.14pp**. Annualised turnover **6.02×** (0.499 per
  rebalance). The first 2021 build paid about **0.75% of NAV** in costs on
  day one.
- Gross return **−7.94%** over 2021–2026 versus net **−35.83%**; the cost
  drag is the main mechanical difference. The gross result is itself negative,
  so cost reduction alone cannot rescue the frozen signal.
- The executed book is not compliant: average **552.9** names (max 611)
  against the 500 hard ceiling; average gross **1.954** (max **2.479**)
  against 2.0; **71,371** name-days above the 5-day/10%-ADV liquidation
  limit; 31 short-floor breaches; **1,416 of 1,421** days violate at least
  one internal exposure band. Maximum absolute hedge beta **0.147** (band
  0.02) and maximum sector **4.68%** (band 1%).
- The ex-ante beta mean is **+0.053**, not zero; realised S&P beta is
  **+0.0719** (t 6.49). The month-end target is not the executed risk.
- The 2026 correction improves Jan–Jul from **−14.08%** to **−8.72%**, but
  2026 Jan–Aug is still **−8.25%**.

Cost/risk conclusion: the optimizer's support-cost repair is still the right
implementation, but at the frozen 500-name/1.8× book the native five-session
impact law is a **~6%/yr** drag. A 500-name book at $1bn with this turnover
does not clear the mandate hurdle even before the negative forecast. Reducing
names/turnover or raising participation capacity is a new construction
hypothesis, not a free fix.

`cvxportfolio` was prototyped on a 40-name, 2021–2022 monthly book. It solved
the continuous market/dollar-neutral QP with 5% caps and 2× leverage, but its
default transaction-cost model charged only ~3bp/month (holding 0bp) and it
lacks support/cardinality, sector/size bands and the native five-session
impact law. It is a possible future backend, not a drop-in replacement.

