# Research roadmap: what must be established for FIAM v4b

**Date:** 2026-10-26. **Status:** research and proposed experiments, not an
adopted decision or a performance claim. D16–D20 remain binding. No sealed
D18 full-window results were read to write this document.

## Executive assessment

No published paper or existing backtest establishes that a strategy can meet
all the requested constraints and beat 12.8%/year in this dataset. The
necessary route is to demonstrate (1) a real, tradable and cost-adjusted
forecast in **both** legs; (2) calibrated risk and beta in executable portfolio
directions; (3) a feasible, cost-aware implementation; and (4) sufficiently
independent confirmation. Each is necessary. None alone guarantees the final
return. If one fails, report the failure and the constraint or objective that
cannot currently be justified; do not manufacture a winner.

The immediate bottleneck is not another full-window race. D19 found no E6
survivor on its registered two-formation test. Raw scores failed the signal
gate. The betamatch variants failed risk, beta and/or power gates. The observed
beta errors are important evidence, but a two-month noisy beta regression is
not by itself proof of a permanent defect or its root cause. The window was
already inspected; it is now diagnostic data for any repair. D20 records
Andrew's subsequent authorization to compare six beta candidates across four
short windows and, subject to those results, regate E6 and a plain decile sort.

The earlier E5 2021–26 diagnostic is −1.7%/year, with long alpha −3.6% and
short alpha +0.6%, and the window has been repeatedly viewed. The earlier
in-sample construction grid's best E-LASSO result was about +2%/year over
cash and a negative long alpha. Consequently, demonstrating a positive long
edge after risk adjustment and trading costs is as important as fixing the
beta model. The $1bn book's ≈3.3%/year modeled costs are an economic hurdle,
not a detail. See `STATUS_ASSESSMENT_2026-10-26.md` and D17–D19.

## Evidence base and what it means here

| Source | What it establishes | Project implication, which still needs a test |
|---|---|---|
| [Han–He–Rapach–Zhou](https://academic.oup.com/rof/article/28/6/1807/7737488) | E-LASSO combines regularization, characteristic selection and forecast combination; the paper evaluates cross-sectional forecasts and sorted portfolios. | Retain the user's E-LASSO base. Reproduce the paper baseline on the actual eligible universe and compare each additional constraint. The paper is not evidence that this portfolio wins after this mandate's costs. |
| [Gu–Kelly–Xiu](https://www.nber.org/papers/w25398) | Flexible models can improve cross-sectional prediction in their historical setting. | Better forecast fit or rank IC is a hypothesis generator, not a substitute for separate leg and executable net results. Do not replace E-LASSO without the user's decision. |
| [Novy-Marx–Velikov](https://www.nber.org/papers/w20721) | A buy/hold spread reduced transaction costs in their anomaly tests; high turnover frequently erased significance. | Preserve and test hysteresis, but measure lost forecast strength and total costs together. The paper's turnover result is not a universal threshold for this book. |
| [Jensen–Kelly–Malamud–Pedersen](https://www.aqr.com/Insights/Research/Working-Paper/Machine-Learning-and-the-Implementable-Efficient-Frontier) | Comparing portfolios on a net-of-cost risk frontier can reverse a gross-return ranking. | Compare the E6 book and its reference at the same NAV, universe, costs, risk and constraints, and report the cost of a beta constraint and a return floor. |
| [Ledoit–Wolf](https://www.econ.uzh.ch/dam/jcr:ffffffff-935a-b0d6-ffff-ffff9961f70f/jef.pdf) | High-dimensional sample covariance is unstable; shrinkage improved out-of-sample variance in their study. | Test the enhanced model against simple diagonal, market-factor and shrunk covariance baselines on the actual candidate books. Do not assume the complex model or a raw 252-day covariance is better. |
| [Drobetz et al.](https://doi.org/10.1017/s0022109024000036) | Betas change and forecasting methods can be compared using realized hedge errors; their ML models improved on baselines in their sample. | Run a controlled beta-forecast comparison. More complex beta models are candidates only after the simple and point-in-time baselines and paired uncertainty checks. |
| [Harvey–Liu–Zhu](https://www.nber.org/papers/w20592) and [Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | Repeated strategy selection increases false discoveries and historical selection bias. | Preserve every trial, account for selection, and reserve a genuinely untouched confirmation period. Their suggested thresholds are not automatic proof for this specific test. |

Research used 12 focused searches (82 requested result slots across the initial
five and seven targeted searches) and fetched the primary sources above; search
hits overlap and are not 96 unique papers. This is a focused literature review,
not an exhaustive survey. Project observations and external findings are kept
distinct.

## 1. Protect inference and audit the data before repair

**Must establish:** all forecasts, calibration parameters, holdings, risk
snapshots, market returns and execution assumptions were available by their
formation or decision times, and unobserved returns were not presented as known.

1. Trace the forecast and risk timestamp for both D19 formations, including
   calibration, smoothing, beta calibration, NYSE breakpoints and eligibility.
   D19 G0 deliberately uses frozen evidence from 2016-12..2020-11; that is
   evidence over four years, not a two-month signal-significance result. Audit
   whether parameters used **inside** the 2017 formations were estimated using
   completed information available at those times. A full-period fitted scale
   must not be portrayed as a point-in-time 2017 input. Positive scale leaves
   the *floor inequality* unchanged, but costs and risk calibrated in absolute
   return units still need a consistent economic interpretation.
2. Reconcile the market index, dividend treatment, stock total returns,
   identifier and exit mapping, factor times, and the 2026 proxy; trace all
   gaps and compare zero-fill against explicit missingness and bounded
   scenarios. D19 reports roughly 0.7–2% affected weight per formation.
   Its G3a uses only names with complete W returns; quantify selection bias.
   Audit the separate 2,626 unverified-gap position-days in the E5 report.
3. Reconcile target-versus-executed holdings, fees and borrow to the daily NAV
   and monthly summaries. Audit the short-floor, participation, liquidation and
   policy exceptions individually; distinguish legal mandate rules from policy
   and capacity alerts. The required $500m short-eligible market-cap condition
   and aggregate $500m short exposure floor are separate checks.
4. Freeze source/version hashes and retain negative attempts. Commit no private
   WRDS/OptionMetrics data, individual holdings, forecasts or sealed screen
   outputs. Preserve accessible aggregate evidence and the private artifact
   manifest.

**Exit:** mechanical timing and accounting tests pass, unresolved gaps are
reported with sensitivity, and every data limitation has a named owner and
status. These checks do not grant permission to view a protected return window.

## 2. Diagnose beta and risk with controlled short-window hypotheses

**Must establish:** the forecast works for the exposure directions actually
traded, not just average individual-stock error. Pre-register each new
hypothesis and window under D19. Andrew has authorized D20's four two-month
windows; January–February 2017 is already viewed. D20 governs their use and
does not authorize any other window or a full run before its gates pass.

The D19 realized-on-predicted slope 1.76, bootstrap interval [1.43, 2.11], and
realized book beta +0.16 to +0.23 fail the specified gates. That is evidence
of mismatch in W. The stock-level regression uses 37-ish daily observations
per realized beta, complete cases and common shocks. The observed slope need
not isolate the true latent beta dispersion: returns, non-synchronous trading,
short-window label noise and model timing can all matter. D19's daily normal
chi-square volatility interval and Pitman–Morgan test also have assumptions;
the logged G4 ex-ante expected-t check is a heuristic, not a complete power
curve. Independently test coverage and size with simulation before calling
these diagnostics definitive.

Pre-registered tests, using only data completed before each formation:

1. **Integrity fixture:** synthetic market plus stocks with known constant and
   changing betas; impose realistic gaps, common residual factors and drift.
   Verify signed portfolio beta, stock-slope recovery, interval coverage and
   false-positive rates. Compare complete-case and missing-data policies.
2. **Point-in-time baseline comparison:** current calibrated beta against
   market regression with prespecified windows, standard shrinkage and a
   simple expanding calibration. No data-dependent sign flips or regression on
   W used to 'fix' W. Include non-synchronous returns as an explicit diagnostic.
3. **Paired portfolio directions:** same frozen eligible cohort and weights,
   test long, short, hedged book and adverse/high-beta directions. Report
   signed and absolute beta errors, squared hedge loss, intervals, number of
   independent dates, and sensitivity to market index and gaps. A stock MAE
   improvement is insufficient if the actual book's hedge gets worse.
4. **Variance:** compare current factor model to diagonal, market-factor and
   shrunk covariance nulls, with frozen formation weights. Assess realized/
   predicted ratios and robust intervals separately for both legs and the book
   across calm and stressed periods. Do not add PCA or beta uncertainty merely
   because it is more complex; require paired out-of-sample calibration gains.
5. **Power:** simulate the prespecified null and alternatives using only prior
   data; state the smallest detectable effect, actual test size and power,
   serial dependence and multiplicity. A gate is `underpowered` rather than
   a positive finding when its fixed rule cannot be met. Under D19 this is a
   fail for promotion, not proof that the effect is zero.

**Exit:** a candidate passes every applicable preset short-window test with
honest missingness, and no interval or window is quietly changed afterward.
This does not yet demonstrate alpha.

## 3. Establish tradable, separate-leg E-LASSO alpha

**Must establish:** an economically meaningful signal survives the actual
universe, beta adjustment and costs on each side. The empirical observation
that post-2020 extreme deciles reverted means another optimizer is not enough.

1. Run an attribution waterfall on eligible names: paper raw deciles →
   shortable/liquid/price-eligible set → sector sort → beta matching →
   200–500-name and per-name caps → fixed-set risk weights → actual execution.
   At each step report forecast distribution, long and short excess and
   beta-adjusted alpha, equal and value weighting, IC, uncertainty, turnover,
   costs, concentration and the fraction of names excluded. Keep signs and
   units consistent. Compare long and short with a risk- and sector-matched
   eligible reference; a profitable short alpha means positive after-beta
   performance, not necessarily positive raw short P&L.
2. On *newly prespecified, short, permitted windows*, test hypotheses motivated
   by existing evidence: whether the long leg's E-LASSO ranking is positive
   within the holdable pool; whether the extreme-decile curve is monotone;
   whether the short edge remains after borrow and impact; and whether a fixed
   past-only holding buffer reduces cost more than it sacrifices alpha. Test
   the book, long and short separately. Estimate statistical power before
   running; dependence across stocks means 2,000 names in two months are not
   2,000 independent time periods.
3. Treat six-month smoothing as **post-2021-informed**, not a fresh discovery.
   Do not use the 2021–26 in-sample grid to promote a candidate or relabel it
   OOS. If raw tail forecasts lack repeatable long alpha, say so and return to
   the user for a change of research scope; a construction-only adjustment
   cannot ensure an alpha that is absent. v4 signals or an E-LASSO short filter
   are alternatives the user previously did not choose.

**Exit:** separate-leg, after-beta signal hypotheses pass their fixed rules,
with the number of attempted variants and uncertainty reported. This is still
not proof of meeting the 12.8% total-return target.

## 4. Make the two-step book implementable

**Must establish:** the frozen selected names support the rules, the return
floor and the intended risk tradeoff in actual executed shares.

1. Keep the user-selected order: return-only selection first; fixed names and
   signs second; risk, beta and turnover minimization subject to a reported
   forecast-return floor. Compare VW and EW paper references at identical gross,
   NAV, dates, costs, universe and market conventions. Sector deciles and
   hysteresis are departures from a pure global paper sort and must be labeled.
2. Audit feasibility before solving: side capacity, concentration, 200–500
   active names, sector coverage, eligible shorts, net, gross, and union with
   incumbents. Independently recompute floor and slacks on final weights after
   rounding, dropping dust, and any scaling. Record `optimal_inaccurate`,
   fallbacks, failed solves, sector/style slack, gross reductions and costs;
   the D19 gate demands first-rung `optimal`, ρ=0.9 and gross 1.8.
3. The fixed support can exclude a necessary high-beta hedge; the docs-branch
   acceptance contract calls for an adversarial omitted-hedge test. A larger
   or adaptive support, or market overlay, would change the fixed-selection
   mandate. Quantify the tradeoff as a diagnostic and obtain a user decision
   before adopting any expanded-hedge policy. Do not silently loosen the rules.
4. Validate full compounding at $1bn, realistic per-name spreads, five-day
   impact, dated fees, short-interest borrow, exits and partial fills. Show
   turnover, cost lines, participation and capacity, name/gross/net/short-floor
   breaches and risk drift. Stress spread/impact/borrow and the 2026 proxy;
   compare assumptions consistently with v4. A simulated zero-cost ETF hedge
   is not an executable stock-only solution.

**Exit:** the two-month executed G5 smoke has zero specified hard-rule breaches
after G0–G4 pass. The short smoke proves neither long-run performance nor
financial significance.

## 5. Honest promotion and target comparison

Once a candidate earns the full window under D19, apply the preregistered D18
selection and run its 2017–2020 Nautilus book. D18 promotion requires net annual
return greater than the D17 E5 winner's +6.5%, |daily beta| ≤0.05 and positive
after-beta alpha in both legs. This rule is a necessary internal gate, not proof
that each leg is statistically strong or that 12.8% is achievable. Add the
user's stated significance requirement without changing the gate after seeing
results: report confidence intervals, power and multiplicity, and do not call
an insignificant leg strong.

If a candidate qualifies, D18 allows one disclosed historical 2021–2026 run;
the period remains previously viewed. A genuinely independent claim requires
new, untouched future outcomes or another prospectively frozen sample that
has not influenced research and is authorized by the user. Do not describe an
already-viewed window as pristine. Any new trial and its window must be entered
in the ledger before outcomes are examined.

Compare the 12.8% v4 figure and candidate on the same *total* annual-return
definition, dates, NAV, costs, share accounting and benchmark. Present the
TB3MS+4% hurdle and over-cash returns separately. Explain that v4's 12.8% is
itself a previously selected in-sample benchmark. Stress the portfolio's
achievable gross, risk and net alpha; a 12% target volatility is not achievable
merely by asking for it when the gross and other rules bind.

## Priority and stop rules

1. **Now:** finish the timing, missingness, gate-power and execution audit;
   write and validate short-window mechanical/known-truth tests. D20's beta
   gate is authorized; no full return screen or 2021–26 look is authorized yet.
2. **Next, under D20:** validate the six beta candidates, then regate E6 and
   the plain decile book only as D20 permits. Separately register any new
   tradable long- and short-signal test. A failed or underpowered gate stops
   promotion.
3. **Then:** fix only demonstrated mechanisms, repeat the registered gate as
   allowed, and run the executed smoke. The fixed-support hedge limitation is
   presented to Andrew if an expansion would be needed.
4. **Only after all gates:** D18's longer validation and, if it qualifies, the
   one disclosed 2021–26 evaluation. Independent future confirmation remains
   separate.

These are requirements to establish whether the goal is attainable, not a
promise of 12.8% or statistically significant positive legs. If no candidate
passes, the correct result is the demonstrated failure, its limitations and a
decision on which constraint or goal the user wants to revisit.
