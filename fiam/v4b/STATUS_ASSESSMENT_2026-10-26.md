# FIAM v4b — objectives and advancement, 2026-10-26

This preserves the assessment provided to Andrew, with one material correction:
a subsequent D19 short-window run was recorded after the original assessment.
It reports **no E6 survivor**. D20 subsequently records Andrew's authorization
for additional short windows, beta candidates and a plain-decile hypothesis.
E6 has not earned a full-window return screen or an out-of-sample run. The
stopped D18 screen remains sealed under D19–D20.

## Goal and status

The goal is an E-LASSO-based, beta-neutral strategy with predictable risk,
strong out-of-sample results in both legs, and a return above v4's 12.8%/year.
**This goal has not been achieved.** E5 achieved low aggregate historical beta,
but its 2021–August 2026 diagnostic lost money and did not establish a strong
edge in either leg. E6 implements the proposed two-step construction but did
not pass the short-window gates.

| Requirement | Advancement | Evidence and remaining work |
|---|---|---|
| E-LASSO base and monthly walk-forward refits | Implemented | Corrected E-LASSO port and monthly forecasts exist; original code defect and verification recorded in D13–D15. |
| Select by expected return first | Implemented prototype | E6 chooses forecast deciles within sectors, with VW and EW-ex-micro variants and holding hysteresis. D18 amends the original global sort. |
| Reweight the fixed set for risk and beta with a return floor | Implemented prototype; gates failed | Starts at 90% of the reference forecast return. Feasibility fallbacks may reduce the floor to 75%, 50%, then zero and may reduce gross. |
| Per-name costs | Implemented in engine; screen approximate | Engine models spread, impact, fees and tiered borrow; screen uses approximations. E6 has no executed full-book cost report. |
| Low beta and predictable risk | E5 aggregate beta low; E6 not validated | E6 G3 beta and leg risk calibration failed on W. A low forecast beta does not establish realized neutrality. |
| Strong performance in both legs | Not achieved | E5's validation leg alphas were positive but individually weak; historical long alpha negative and short alpha near zero. E6 lacks a permitted full-window result. |
| Beat 12.8%/year | Not achieved | E5 validation +6.5%/year; historical diagnostic −1.7%/year. The best E-LASSO construction grid was an in-sample screen, not a promotion. |
| Finals compliance on executed holdings | Partial for E5; E6 G5 not run | E5 has no reported gross breach but has short-floor, participation, liquidation-capacity and policy exceptions. E6 needs an executed-holdings check after preceding gates. |
| One/two-month tests before longer windows | D19 run; no survivors | Raw scores fail G0; betamatch versions fail one or more G1–G4 checks. G5 was not run. Do not read sealed D18 screen returns. |
| Follow-up beta and decile gates | D20 preregistered; scripts in progress | Six beta candidates across four two-month windows; E6 and the plain decile reference proceed only under D20's rules. W17 is already viewed. No results are claimed here. |
| 2017–2020 then 2021–2026 | Not earned for E6 | D19 requires all gates to pass before evaluating eligible sealed screen variants; D18 prescribes the full-book and subsequent historical-window decision. |

## Completed E5 benchmark — not E6

| Measure | Validation, 2017–2020 | Historical diagnostic, 2021–Aug 2026 |
|---|---:|---:|
| Net annual return | +6.5% | −1.7% |
| Annual volatility | 5.4% | 5.0% |
| Daily market beta | −0.002 | +0.012 |
| Long-leg alpha after market beta | +3.7%/year (t 1.5) | −3.6%/year (t −1.3) |
| Short-leg alpha after market beta | +5.0%/year (t 1.6) | +0.6%/year (t 0.2) |
| Costs | 3.5%/year | 3.3%/year |

The historical run ended around $906m from $1bn and had a −17.6% maximum
drawdown. Annual cost lines were approximately 0.34% spread, 2.50% impact,
0.16% fees and 0.31% borrow. Its saved summary records 9 short-floor breaches,
41 participation breaches, 7,495 liquidation-capacity rows, 1,409 policy-breach
days and 2,626 unverified-gap position-days; these are different units.
2026 uses a proxy. The saved summary flags the result diagnostic-only and not
eligible for OOS. D16 enumerates previous views of 2021–2026: it is not a
pristine holdout.

Sources: `evidence/race_d17.json`, `evidence/d17_oos/{summary,legs}.json`,
`RISK_COST_AUDIT.md`, `HANDOFF_2026-10-26.md`, `DECISIONS.md` D16–D20,
and `LESSONS.md` 93–100. Raw output files remain local/private; aggregate
evidence is copied into `evidence/` for the repository.

## D19 short-window outcome

On December 2016 and January 2017 formations through February 2017:

- G0 uses existing 48-month evidence, rather than a new two-month signal test:
  raw and raw_s6 fail; betamatch and betamatch_s6 pass.
- G1 passes except betamatch/VW's second formation, which required reducing gross
  to 1.5. The other variants pass both formation checks.
- G2 passes for the aggregate book but fails for both legs: realized/predicted
  vol ratios are roughly 0.56–0.67. This short calm window does not, on its own,
  establish a general full-sample calibration defect.
- G3a realized-on-predicted beta slope is 1.76, 95% block-bootstrap interval
  [1.43, 2.11], outside the prespecified [0.5, 1.5] interval. G3b realized book
  beta is roughly +0.16 to +0.23 and its interval fails the ±0.2 rule.
- G4 does not pass the prespecified power requirement; one variant's nominal
  variance test was significant but did not satisfy that requirement.
- G5 was not executed because no variant passed G0–G4. The Modal log also
  records an unconsumed async-map warning; do not treat G5 as executed.

The gate code fills missing daily returns with zero and reports affected
weight, about 0.7–2.0% by formation. Statistical tests rely on short-sample
assumptions; the cross-sectional beta regression uses noisy realized beta
labels. These are limitations for interpretation, not grounds to override a
failed registered gate. The target screen remains sealed and no longer window
is authorized by these results.

## Independent verification of prototype

`PYTHONPATH=. /home/drewclaw/.venvs/v4b-gpu/bin/python -m pytest
fiam/v4b/tests/test_twostep.py -q -p no:cacheprovider` returned **10 passed**
on this workspace. These are synthetic mechanics checks; they do not prove
financial performance, risk calibration or executed compliance. The docs-branch
acceptance test for an omitted essential hedge candidate remains unresolved:
fixed E6 selection cannot add that candidate.
