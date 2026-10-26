# FIAM finals: research and implementation plan

**Prepared for Andrew Koumoudjian | 23 October 2026**

**Authority:** the attached *McGill-FIAM Asset Management Hackathon 2026 — Final Challenge Instructions* governs. The initial challenge supplies background and inherited requirements only where the final instructions do not supersede them. Event-day amendments remain outstanding. This document is a research-backed design, not a tested strategy or a claim of achievable returns.

## 1. The recommendation

Build **one pooled cross-sectional return forecaster, one dynamic factor risk model, and one deterministic optimizer that prices trading costs and estimation uncertainty**. Use monthly fundamental signals, a weekly opportunity to refresh positions, and daily risk monitoring with exception-driven trades. The execution clock must follow the final case's delayed close-to-close convention.

Start with a hierarchical ridge return model informed by economic signal families. Compare it with a small, regularized gradient-boosted tree model on the same chronological validation periods and through the same portfolio constructor. Deploy one winner, selected before the relevant test interval. Do not combine a collection of models simply because each has a different name. A pooled model shares statistical strength across stocks; it does not mean every stock has identical risk or every market state behaves identically.

The NBER paper's main contribution here is **how to trust and combine evidence**. Gârleanu–Pedersen supplies the more direct motivation for gradual, cost-aware rebalancing. Neither paper promises stable profits. Our proposed construction below is an engineering synthesis, not a replication of either paper's exact portfolio policy.

The investment hypothesis to test is that firms' operating quality, financing decisions and recent information contain incremental return information **within comparable sector and risk groups**, after familiar market/style exposures and implementation costs are removed. The 147 characteristics are the starting information set; an additional event feature earns its place only by improving this residual selection problem.

### What can actually be made predictable?

| Desired property | Implementable objective | Limitation |
|---|---|---|
| Constant beta | Target market beta zero, with an uncertainty-aware tolerance and daily monitoring | Estimated beta changes; future realized beta cannot be fixed by an optimizer |
| Constant returns | Seek positive expected active returns with diversified loss drivers | No risky equity model can guarantee constant positive realized returns |
| Stable risk | Limit forecast volatility, stress losses, concentration and liquidity use | Forecast error, gaps, halts and changing correlations remain |
| Meaningful positions | Economically nontrivial holdings with documented signal, hedge or diversification purpose | The 200-name floor can force weaker marginal holdings; measure that cost |
| Risk-adjusted performance | Choose the validated policy that improves net information ratio without losing neutrality or capacity | Minimizing variance alone can deliver a tiny book that never clears cash + 4% |
| Repeatability | Identical dated inputs, model versions and cached decisions yield identical orders | Determinism is a property of the process, not of market outcomes |

Do not target a straight equity line, fit weights to realized future returns, increase leverage to recover a recent loss, or impose an expected-return equality and call it a guarantee. Use the cash-plus-4% hurdle to evaluate the product, not as a daily obligation to take risk.

## 2. Translate the final mandate into executable rules

| Item | Governing final requirement | Implementation decision |
|---|---|---|
| Universe | U.S. public equities | Point-in-time eligibility and permanent identifiers |
| Capital | $1bn at OOS inception, compounding | Recompute dollars, participation and capacity against current NAV |
| OOS window | January 2021–August 2026 | Freeze a chronological evaluation ledger |
| Holdings | 200–500 across both legs | Start with 300 candidates, approximately 150 per leg; maintain 200+ economically active positions |
| Gross | At most 200% of NAV | Treat 200% as a ceiling, not a target |
| Net | Within −50% to +50% at all times | Aim for dollar neutrality; use a much tighter internal band |
| Position cap | 5% absolute NAV weight | Start with an internal 1% cap, additionally limited by liquidity |
| Shorts | Market cap at least $500m at formation | Dated capitalization check for every formation; do not confuse eligibility with a guaranteed locate |
| Frequency | Daily through monthly permitted | Monthly information refresh, weekly trade review, daily risk exceptions |
| Benchmark | Time-varying 3-month bill + 4% annual premium | Use the supplied series when available; implement the stated formulas independently for reconciliation |
| Neutrality | Realized beta scrutinized daily and monthly | Control forecast beta; report realized estimates with standard errors |
| Costs | Gross/net results and disclosed assumptions | Model trading, borrow and financing separately |
| Review | Arcana economic/factor analysis | Prepare attribution, exposures, sizing/selection and stress evidence |
| Submission | Holdings on every rebalance date; presentation with Arcana output | Confirm exact schema at onboarding; preserve richer internal audit files |

**Do not carry obsolete first-round or earlier project settings into the final.** There is no stated final-rule $300m short floor, 300% gross limit, mandatory 14% volatility target or 10% turnover cap. A price floor, ADV screen, turnover budget, 1% internal cap and beta tolerance are our proposed risk policies, not official requirements.

The final PDF has no standalone academic bibliography. Its references are principally platform/data links and the inherited first-round material. Section 12 below therefore covers every academic item in the initial bibliography, relevant papers cited by the NBER paper, and additional portfolio-construction literature. It does not pretend to be an exhaustive systematic review of every citation in every paper.

## 3. What the linked NBER paper contributes

**Jensen, Kelly and Pedersen, “Is There a Replication Crisis in Finance?” NBER w28432, February 2021.** The downloaded URL returned the original 54-page PDF, not the later Journal of Finance version. The paper studies 153 factors across 93 countries, groups related factors into 13 themes, and estimates their alphas jointly with a hierarchical Bayesian model. Its conclusions differ from skeptical replication studies partly because construction, benchmark and statistical assumptions differ. The 2021 version reports a global Bayesian replication rate of 84.9%; that is a significance result under its research design, not a probability that our portfolio will work.

The paper's factor construction uses characteristic terciles, non-microcap breakpoints and capped value weights. Its hierarchy pools related alpha estimates and shrinks them toward zero. Its CAPM benchmark is materially narrower than the finals' broader factor review. Its ex-post tangency analysis is not a deployable out-of-sample allocation rule. See printed pp. 17–22, 26–29 and 44–48; equations 21–25.

### Apply its logic in three separate places

1. **Signal organization.** Map the supplied characteristic list into economic families, then assess redundancy using training-only return correlations. A dozen variations of value are not a dozen independent opportunities. Retain different measurements when their incremental evidence survives, rather than deleting all but the historical winner.
2. **Forecast shrinkage.** Penalize unsupported coefficients and uncertain family effects. Learn the penalty from past-only validation or empirical Bayes. A model should require more evidence to justify an extreme forecast than a modest one.
3. **Portfolio uncertainty.** Carry uncertainty about expected returns into construction. Two stocks with the same point forecast need not get equal weights when one forecast is much less reliable or expensive to execute.

These are adaptations. Do not call a ridge regression or a risk optimizer an exact implementation of JKP's hierarchical factor-alpha model.

### A faithful research replication, separate from the tradable strategy

Reconstruct the available characteristic-sorted research portfolios on the supplied data, document missing characteristics relative to JKP's 153, use original economic signs where historically established, and report gross CAPM alphas and their joint uncertainty. Compare capped value, straight value and equal weighting. Then separately impose the final short floor, capacity, costs and broader factor controls. The difference between these results is the cost of turning a research anomaly into the mandated fund.

For a U.S.-only version, a simplified factor-alpha prior is

\[
\alpha\sim N(0,\Omega),\qquad \Omega=\tau_c^2MM^\top+\tau_w^2I,
\]

where rows of M identify factor families. With estimated alpha vector a and its sampling covariance V,

\[
\bar\alpha=\Omega(\Omega+V)^{-1}a,\qquad
P=\Omega-\Omega(\Omega+V)^{-1}\Omega.
\]

This general Gaussian updating notation corresponds to the paper's construction when V is its specified sampling covariance. Estimate V with dependence in mind; using independent standard errors throws away precisely the dependence the approach is meant to exploit. Regularize singular matrices and use linear solves. Estimate prior parameters only on the training interval. Empirical-Bayes plug-in uncertainty is conditional on estimated hyperparameters; it is not the full uncertainty of model selection.

**Critical distinction:** alpha uncertainty P is not the covariance of stock returns. A factor-alpha posterior cannot be inserted directly as a stock covariance matrix. To map family uncertainty into stock expected-return uncertainty, specify a stock exposure/loading map A and use A P A' plus justified stock-level uncertainty. Keep that approximation explicit.

### Avoid a new source of look-ahead

The paper appeared in February 2021, while the test starts in January 2021, and its published clusters were estimated on a much longer sample than our training interval. Use pre-2021 economic definitions and training-only clustering/estimation. Do not import its fitted clusters, winning themes, tangency weights or present-day factor database performance as if they were known at inception. The technique can inform today's research design; the simulated parameters must remain dated. Disclose the distinction between retrospective strategy design and historical information availability.

### Factor replication versus stock-selection alpha

A profitable market-neutral value/momentum combination may still be primarily a style portfolio. That is not equivalent to the idiosyncratic alpha the final case asks reviewers to inspect. Maintain two comparisons: a transparent factor-based baseline and the proposed within-group selection strategy. Report how much return survives market, sector and style attribution. Do not impose exact neutrality to all 147 signals: that can mechanically remove the information being forecast. Limit interpretable nuisance exposures and quantify the price paid for each limit.

## 4. The universal forecasting component

### Default: pooled hierarchical ridge

For stock i at formation t, predict a future excess return using the same fitted function across all eligible stocks:

\[
\widehat\mu_{i,t}^{(H)}=x_{i,t}^{\top}\theta,
\qquad
\min_\theta\ \sum_t\frac{1}{N_t}\sum_i
(y_{i,t}^{(H)}-x_{i,t}^{\top}\theta)^2
+\sum_g\lambda_g\|\theta_g\|_2^2.
\]

Date-balanced loss prevents dense recent cross-sections from dominating merely because they contain more rows. Strong family-level regularization shares evidence without pretending that hundreds of thousands of stock-months are independent time observations. Pool across stocks; avoid one separately fitted model per ticker. Include historical sector controls and missingness indicators where justified. Sector controls do not themselves guarantee a sector-neutral portfolio.

Use the next-month target supplied in the initial panel for the monthly baseline. Its `ret_exc_lead1m` is already forward aligned; do not shift it twice. For the actual delayed daily execution simulation, build an aligned future holding-period target from daily returns if available and compare the monthly target as a baseline. The forecast period must start after the allowed execution time, not at a month-end that the signal already observed.

The initial research target is approximately a 21-trading-day horizon. It is not a forecast of tomorrow's return. Monthly signals can be carried forward with age/staleness information and renewed only when new data arrives. Do not multiply the training sample by copying a monthly row onto 21 days and counting those targets as independent.

### Challenger: shallow gradient-boosted trees

Test a modest tree model on the same features, labels, universe, folds and optimizer. Trees are useful if conditional interactions add durable selection value; they are not justified merely because the panel is large. Keep the search budget small and recorded. Calibrate its forecast magnitudes on genuinely held-out predictions before using them as expected returns. Native tree dispersion is not automatically a calibrated posterior variance.

Promotion requires better **net portfolio economics**, acceptable prediction calibration, stable exposures and no dependence on a few illiquid names. Compare rank IC, net IR, drawdowns, turnover and factor-adjusted performance. A tiny improvement in prediction MSE alone does not settle the portfolio decision. If the existing team's forecast already passes these tests, retain it and improve construction first.

### Residual targeting: useful, but test it

An optional target subtracts realized future factor return contributions using exposures estimated before formation:

\[
y_{i,t}^{\mathrm{res}}=R_{i,t:t+H}^{e}-\widehat B_{i,t}^{\top}F_{t:t+H}.
\]

Future returns are legitimate training labels once their horizons have ended; they cannot enter input features. This can focus learning on stock selection, but noisy exposure estimates can corrupt the target. Compare against ordinary excess-return prediction with factor constraints at construction. Do not assume residual targets must win.

### Economic feature priorities

| Avenue | Financial hypothesis | Decision |
|---|---|---|
| Quality, profitability, accruals, investment and issuance | Prices incompletely reflect operating quality and financing behavior | Core structured information; test within sector/risk groups |
| Momentum and related price signals | Information is incorporated gradually | Core candidate; measure decay and reversal risk |
| Low risk and liquidity characteristics | Required returns and constraints vary across securities | Use carefully; avoid disguising a low-beta or illiquidity premium as unique alpha |
| Earnings expectation errors | Analyst optimism can differ from an independently estimated earnings outlook | Strong alternative if dated analyst estimates and actuals exist |
| Structured event surprises | New firm-specific disclosures change expected fundamentals | First optional extension after the base is complete |
| Filing text | Context in 10-K/10-Q/8-K disclosures may help forecast fundamentals | Secondary; corpus repair and model-memory controls are prerequisites |
| Option-derived predictors | Derivatives may contain incremental information about the underlying | Research branch only if historical option data is actually accessible and point-in-time |

## 5. One dynamic risk model

Use a parsimonious factor covariance model:

\[
\Sigma_{t,H}=B_tF_{t,H}B_t^\top+D_{t,H}.
\]

B contains market, a nonredundant sector representation and selected style exposures such as size, value, momentum, profitability and investment. Estimate exposures with shrinkage, update risk from past daily observations, shrink factor covariance and floor idiosyncratic variances. Use one coherent covariance forecast; a short-memory stress estimate can impose an additional risk constraint rather than silently replacing the model when performance is poor.

Start with regularized trailing regressions and exponentially weighted covariance. Compare a predeclared slower and faster estimator on pre-OOS forecast calibration. Candidate 252-day exposure windows and 20–60-day volatility half-lives are engineering starting points, not facts established by the cases. Monthly fundamentals do not have to be refreshed daily for daily price risk to be refreshed.

A 500-stock unregularized covariance matrix estimated from approximately 252 daily observations is an unstable input for inversion. A factor model with shrinkage is the practical default. New listings with insufficient history get shrunk sector priors and lower capacity/risk limits or remain ineligible under a declared rule.

### Beta control under estimation error

Target beta zero. If beta estimates have covariance U_beta, impose

\[
|\widehat\beta_t^\top w|+z\sqrt{w^\top U_{\beta,t}w}\leq\epsilon_\beta.
\]

This protects against an ellipsoidal set of beta errors. It is only as credible as that set; do not interpret it as a guarantee about next month's realized regression coefficient. If joint beta uncertainty cannot be estimated reliably, begin with explicit constraints against slow, fast and downside-beta scenarios, and label them sensitivity controls.

A nominal beta band of ±0.02 is a candidate internal policy. First test whether it is feasible with meaningful weights, liquidity limits and a reasonable uncertainty radius. Separate the nominal band from the larger uncertainty-aware bound. Report rolling realized beta with confidence intervals, including both daily and monthly regressions. An insignificant beta estimate with a wide confidence interval is weak evidence of neutrality.

### Stress and tails

At minimum, test a market fall with correlated short squeezes, a momentum reversal, sector dislocations, volatility/correlation increases, wider spreads, lower ADV, borrow recalls and delayed liquidations. Historical windows must be identified in advance of their use for trading calibration. Later events can be used for ex-post diagnostics, not retroactive policy tuning.

Use joint historical/block scenarios to preserve common shocks. Independent simulations for each stock destroy dependence and underestimate joint loss risk. A Student-t residual model can be a sensitivity exercise; fitting EVT tails or a complex GARCH system is not mandatory for a credible first version. HAR-CJ needs appropriate realized/jump inputs, which close-to-close daily returns alone do not provide.

## 6. The rebalancing controller

### Objective

Let w-minus be the actual drifted pretrade book, q=w−w-minus, mu the expected excess stock return vector over H days, Sigma the return covariance over that same horizon, and U_mu the covariance of expected-return estimation errors. A robust construction is

\[
\min_w\ \frac{\gamma}{2}w^\top\Sigma_{t,H}w
-\mu_{t,H}^\top w
+\rho\sqrt{w^\top U_{\mu,t,H}w}
+C_t(q;NAV_t)+H\sum_i b_{i,t}\max(-w_i,0)/252
+\eta\|w\|_2^2.
\]

Here C prices one rebalance in fractions of NAV, b is an annual borrow rate, and eta is a concentration regularizer. The norm term is a worst-case expected-return penalty under an ellipsoidal uncertainty set, not an extra realized-return covariance. If a quadratic uncertainty penalty is used instead, describe it as a different approximation. Align all horizons and units before tuning gamma or rho.

A convex transaction-cost model can include linear spread/commission and convex impact:

\[
C_t(q)=\sum_i s_{i,t}|q_i|+
\sum_i\kappa_i\sigma_{i,t}|q_i|\sqrt{NAV_t|q_i|/ADV_{i,t}}.
\]

The impact expression is a modeling assumption that must be calibrated or stress-tested, not a universal empirical law with known coefficients. A quadratic or piecewise-linear upper approximation provides a simpler solver path. Including norm uncertainty bounds makes this a conic optimization problem; it is not honestly described as a plain QP. The simpler quadratic-risk/linear-constraint version can be a QP.

### Constraints and support selection

Apply the final gross, net, short eligibility and position bounds to every final order and executed book. Add internal factor, participation and risk limits. For example,

\[
\|w\|_1\leq2,\quad |\mathbf1^\top w|\leq\epsilon_{net},\quad
|B_{style,t}^\top w|\leq d,\quad
w^\top\Sigma_{ann,t}w\leq\sigma_{max}^2.
\]

Position count and a minimum absolute position size are nonconvex if signs and support are unrestricted. Do not hide that fact. Use a deterministic two-stage method:

1. Rank candidates using forecast advantage, existing holdings, tradability and factor coverage. Select a support of about 300 names with preassigned long/short signs and entry/exit hysteresis. Build in enough sector and beta diversity to be feasible.
2. Solve weights on that support with signed linear minimum/maximum bounds. A proposed starting minimum is 0.10% of NAV per active stock, with a 1% internal maximum and tighter ADV-dependent caps. At inception these are $1m and $10m. These are policy proposals, not validated optimum sizes.
3. If infeasible, use a fixed deterministic support-repair procedure, swapping marginal candidates for feasible alternatives. Never round tiny optimizer weights into 200 pretend positions. If support repair fails, report infeasibility and apply the documented emergency hierarchy.

With 300 names at 0.10% minimum, gross cannot fall below 30%. With 200 names it cannot fall below 20%. This creates a real trade-off with emergency de-risking; an all-cash portfolio violates the stated count rule. Disclose it. The floor can also cost alpha when only a few opportunities are attractive; show the marginal economics rather than manufacturing conviction.

A holding is meaningful when it contributes expected net alpha, hedge value, or diversification and is large enough to affect the book. Report effective breadth,

\[
N_{eff}=\left(\sum_i(|w_i|/\|w\|_1)^2\right)^{-1},
\]

alongside nominal holdings, risk concentrations and common-factor contributions. This concentration measure does not establish the number of independent bets.

### Priority and infeasibility policy

Enforce legal/competition eligibility and hard exposure rules first. Then control beta, capacity and risk under stated internal policies; only then spend the available risk budget on expected net return. Do not lexicographically minimize beta variance all the way to a zero portfolio and subsequently wonder why returns disappear. Require compliance with a tolerance, then optimize utility within it.

Internal turnover targets may be exceeded to repair a hard breach, with attribution. A halt or unavailable borrow can make a compliant immediate trade impossible. Record the blocked order and actual breach; never fabricate a fill, silently relax a hard rule or rewrite the past book. Monitor daily drift and maintain buffers below gross/position caps because prices can move through a limit between executions. Daily data cannot prove intraday compliance.

### Rebalance logic

- Refresh fundamental information when it becomes available; retain the monthly forecast horizon.
- Review the core weekly. Calculate the marginal expected benefit of trading after risk improvement, spread, impact, borrow and uncertainty.
- Use no-trade regions/entry-exit buffers so small rank changes do not churn the book.
- Monitor daily for gross/net/beta drift, disqualifying shorts, corporate actions, stale prices and exceptional losses. Plan repairs on the allowed execution clock.
- Compare monthly, weekly and daily variants through identical signal and cost assumptions. Keep the simpler schedule unless additional net value is demonstrated.

A genuine multi-period model-predictive controller can optimize an H-step trade path with expected signal decay and participation constraints, execute its first step, and re-solve. That is a later extension. The proposed first version is a receding one-period controller with a holding-horizon forecast; do not label it an exact dynamic-programming solution.

## 7. Capacity, accounting and execution

At $1bn NAV and 200% gross, 300 equal absolute positions average about $6.67m. A $6.67m entry into a name with $20m ADV requires more than three days at 10% daily participation. At $2bn NAV that requirement doubles. This arithmetic alone can eliminate otherwise attractive stocks.

Separate position capacity from order capacity:

\[
NAV_t|q_i|\leq p\,ADV_{i,t},\qquad
NAV_t|w_i|/(p\,ADV_{i,t})\leq D_{max}.
\]

The first limits daily trading; the second bounds liquidation days at the chosen participation rate. Use lagged observed dollar volume, not monthly volume mislabeled as daily, and stress it downward. A 10% participation limit is a proposed baseline; test 5% and 20%. Apply constraints to executed transitions, not only intended target weights.

Initialize consistently. Either document an initial endowment portfolio and charge its formation costs under the organizer's accepted convention, or simulate a funded ramp before official measurement with declared initial holdings. Do not assume a free fully invested book and then claim every trade respected daily participation. Resolve how the 200-name floor applies to initial deployment and compulsory liquidations with organizers.

Maintain an explicit cash/collateral/financing ledger. A simplified fully collateralized accounting identity is

\[
R^{NAV}_{t+1}=r_{f,t+1}+\sum_i w_{i,t}r^e_{i,t+1}
-TC_{t+1}-Borrow_{t+1}-FundingSpread_{t+1},
\]

under a stated cash/short-proceeds remuneration convention. It is not a license to add risk-free interest twice or assume all restricted proceeds earn the same rate. Derive the implemented formula from signed holdings and actual modeled cash balances. Attribute long and short P&L in NAV units; a short stock's return enters with a negative weight. Charge fees on short notional, not gross or net exposure indiscriminately.

The final document explicitly permits disclosed current cost schedules but requires a conservative alternative. Include its example of 50bp annual borrow for large caps and 5% for other eligible shorts, with a declared large-cap definition. Add stress cases for higher impact, reduced participation and missing locates. Fees must not enter the predictive return model, although they belong in construction and economic ranking.

### Exact information clock

The final case says: information through trading day t forms the book at the close of t+1; the first earned return is close t+1 to close t+2. Implement trading-calendar dates, not calendar-day arithmetic. Adjust feature eligibility for its documented publication lag before applying the execution convention. Where the dataset's lag metadata and event-date definitions could double-count a delay, resolve the schema explicitly and use the conservative interpretation pending clarification.

The weekly Benzinga delivery is distinct from historical source availability. The case allows historical source-date eligibility, but also requires acknowledging live delivery constraints. Test weekly-delivery timing separately. CA0035 contains event metadata, not headline/body text.

Hold shares and cash through time. Drift weights with actual returns and NAV, including fees, before computing turnover. Never rebalance for free by resetting yesterday's weights. Missing data is not a zero return or permission to close at the last price. Handle corporate actions, delisting proceeds, bankruptcy stubs, halts and permanent identifier changes explicitly; distinguish unknown returns from observed zero.

## 8. Data priorities and agent use

| Data | Intended use | Admission gate |
|---|---|---|
| Supplied 147-characteristic panel | Base forecast | Verify column allowlist, lag conventions and target alignment |
| Daily returns from 2014 | Risk, trading simulation, evaluation | Join on PERMNO and observation date; no forward-date join |
| CA0065S price/volume history | Capacity and execution | Verify actual volume coverage, units, adjustments and dated availability |
| CA0032 SEC archive | Repair and extend filing channel | Historical CIK-security links, delisted coverage and acceptance timestamps |
| CA0035 event metadata | Counts, exclusivity, event novelty | No invented text; T+1 and weekly-delivery sensitivity |
| Analyst estimates and reported actuals | Earnings-bias branch | Historical consensus snapshots and release dates must exist |
| Other alternative datasets | At most one incremental hypothesis initially | History, metric-specific lag, reconstructible vintage, coverage bias |

The attached cases are instructions, not the underlying market datasets. No empirical model selection or performance assertion has been performed here. The Carbon Arc screening workbook, actual panel schemas and Arcana exports still need inspection.

The supplied 8-K corpus has a survivorship defect acknowledged in the final case. Treat it as contaminated until rebuilt or explicitly bounded. EDGAR's archival completeness does not automatically solve the historical CIK-to-security mapping. Test the case's delisted-company examples and compare covered/uncovered returns with sector/size controls; a difference is diagnostic evidence, not by itself proof of survivorship bias.

A historical lag cannot repair a revised historical value. Require reconstructible vintages, evidence that revisions cease before an imposed lag, or exclusion from the point-in-time strategy. Alternatives starting after January 2021 enter only after sufficient historical training exists; report their active subperiod separately.

### One useful agent, with a narrow role

Start with an **exception and pretrade explainer**. Feed it deterministic exposure, constraint, cost, scenario and attribution outputs. Let it describe the binding constraint and compare remedies already evaluated by code. Its arithmetic must reconcile to those outputs; it must not invent marginal costs or expected returns.

For a tested action-taking extension, restrict its proposals to a small approved menu, such as maintain the fixed-rule target, reduce a flagged exposure, or defer a discretionary trade. Code re-solves and validates. Run the same pipeline without the agent. Cache each output by input hash, model/version and prompt, and log the actual effect on holdings.

Do not claim an explanatory-only agent improved returns if it never changed a trade. Its value can instead be measured in error detection and faithful explanations. Historical prompts have no live retrieval. Use anonymized numerical diagnostics where possible, but do not claim blinding cures model memory. Declare release/cutoff dates, measure company re-identification on text, and show post-release performance only when that interval exists. A model released after August 2026 has no post-release interval inside this case. Keep the structured non-LLM baseline intact.

## 9. Validation and research controls

Use the final case's suggested first split: train 2015–2018, validate 2019–2020, test 2021. Then move forward on a predeclared annual schedule, using only past information. A concrete rolling design tests year Y with training through Y−3 and validation Y−2 through Y−1; after choosing settings, refit on eligible labeled observations through Y−1 if declared in advance. Purge observations whose target horizons cross a split boundary. All labels must have matured before a refit.

Earlier test years may become historical training/validation data for later simulated years under this fixed protocol. Do not revise the protocol because a later year disappointed. Cross-sectional normalizations are within date; historical transforms fit on training only. Maintain time blocks when estimating uncertainty—random stock-row splits are invalid.

**Researcher contamination matters.** The team has already examined 2021–2026 in prior work. Re-running it with clean code does not make it an untouched research holdout. Label it a historically walk-forward evaluation with prior researcher exposure. Freeze the revised policy now; reserve any genuinely unexamined data or run a future paper-trading test for stronger confirmation. Do not pretend an already viewed slice has become pristine because it was renamed holdout.

Log every tested family, feature, hyperparameter configuration and discarded experiment. Predeclare each economic hypothesis and admission rule. Bayesian shrinkage does not erase the selection bias from testing hundreds of variants and reporting only the winner. Use block-bootstrap intervals and a dependence-aware multiple-testing procedure where applicable; report uncertainty rather than a false sense of precision from only 68 monthly OOS observations.

### Compact experiment ladder

| Experiment | Change | Question |
|---|---|---|
| E0 | Existing compliant monthly signal, simple constrained weighting | What works before complexity? |
| E1 | Same forecast, factor/beta-aware construction | Is improved neutrality worth its cost? |
| E2 | Add shrinkage/uncertainty-aware sizing | Does estimation-error control improve stability? |
| E3 | Add liquidity/impact/borrow and hysteresis | Does the edge survive $1bn implementation? |
| E4 | Weekly review with daily risk exceptions | Does faster risk response justify turnover? |
| E5 | One eligible event or fundamentals feature | Is there incremental residual information? |
| E6 | Restricted agent versus fixed-rule action | Does agent discretion earn its place? |

Use pre-OOS validation for promotion. OOS variants are predeclared diagnostics, not a menu from which to choose the best retrospective headline. Test one major change at a time; avoid an untracked combinatorial sweep.

### Minimum acceptance checks

- No feature, vintage, identifier map or agent input is available after its simulated decision time.
- Positions first earn returns only after the prescribed delayed execution.
- Net/gross/count/cap/short eligibility hold on executed books; every drift or forced-trade exception is logged.
- No tiny-weight count padding; each selected stock passes minimum economic size and liquidity feasibility.
- NAV, dollar P&L, long/short attribution and all costs reconcile independently.
- No missing or delisting return is silently converted to a favorable exit.
- Ex-ante beta and realized daily/monthly beta are separately reported; uncertainty is visible.
- Capacity is checked against compounded NAV, including initial deployment.
- Forecast and realized risk calibration, factor attribution and adverse scenarios are reported.
- Net performance survives stated conservative assumptions; otherwise report the failure and retain the more defensible baseline.

Do not invent numerical performance gates after seeing OOS results. Freeze any required validation IR improvement, beta band, stress budget and drawdown tolerance before running the final comparison.

## 10. Reporting and attribution

Use the case's benchmark conventions exactly:

\[
b_m=TB3MS_m/1200+0.04/12,\qquad
b_d=TB3MS_d/25200+0.04/252.
\]

These are prescribed approximations, not a claim that the discount-basis bill quote is an exact investable total return. Use the supplied benchmark when issued. Daily compounding of the daily approximation will not exactly equal the separately prescribed monthly formula; show the reconciliation rather than silently changing either. Evaluation-period benchmark information must not become a forecast feature before it was observable.

For frequency K, active return is a=R−b and IR is sqrt(K) mean(a)/sd(a). Sharpe uses excess returns over cash, not over cash + 4%. Report daily and monthly statistics separately. Alpha/beta regressions use portfolio and S&P 500 **excess** returns; report robust standard errors and the window. CAGR comes from ending NAV, not annualized arithmetic mean.

Turnover at a rebalance is 0.5 sum(abs(w−w-minus)). Report per-rebalance and annualized turnover using the case conventions. For irregular exception trades, also report total turnover divided by elapsed years and explicitly define which dates count as rebalances. Measure holding period directly or label gross/annual turnover an approximation. Do not claim leverage cancels out of this calculation.

Deliver the complete final §9.1 table: ending endowment; cumulative return; annualized arithmetic return and CAGR; volatility; alpha and standard error; daily/monthly beta and standard errors; Sharpe; information ratio and tracking error; maximum drawdown; worst day/month; average/min/max holdings; gross and net ranges; turnover; holding period; average dollar position; median short market cap; annual trading and borrow costs; net-of-all-costs IR.

Required final exhibits include cumulative strategy/benchmark/S&P context, cumulative active performance with an explicit arithmetic-sum or relative-wealth definition, 252-day rolling beta, yearly gross/net returns, gross/net/count histories, top/bottom ten average holdings, ten best/worst contributors, short market-cap/volume distributions and long/short position size in days of ADV. Carry forward useful initial-case exhibits such as hit rate, long/short P&L, underwater chart and rolling monthly active performance. Label unavailable early rolling windows honestly.

Add Arcana-facing diagnostics: factor versus residual contribution; sizing versus selection using an identical-support equal-weight counterfactual; hit rate and win/loss ratio; signal decay at prespecified horizons; earnings-window versus ex-earnings P&L; concentration and stress. The sizing counterfactual is a defined comparison, not a unique causal attribution. If its risk differs, show a risk-matched version as well.

## 11. Implementation sequence and handoff

### Before the October 28–29 event

1. **Freeze rules and audit existing work.** Convert §2 into a versioned configuration. Reconcile the current strategy with $1bn, the $500m short floor and 200–500 holdings. Inventory what OOS research has already been seen.
2. **Fix the simulator before adding signals.** Establish the information clock, drifted holdings, cash/collateral, execution, delistings and costs. Compare daily aggregation with the prior monthly engine.
3. **Build the baseline and risk controller.** Keep the existing signal if sound; add regularized risk, meaningful support, capacity constraints and a deterministic solve. Generate a reason for each holding and rejected order.
4. **Run the predeclared validation ladder.** Select forecast complexity, rebalance schedule and risk controls from historical validation. Produce gross/net and factor attribution before touching another dataset.
5. **Prepare Arcana reconciliation.** Upload a small known book when access arrives; reconcile weights, signs, NAV conventions, timestamps and attribution. Confirm whether historical model vintages are available before using external risk data in simulated decisions.

### Two-day execution budget

| Time | Deliverable | Stop rule |
|---|---|---|
| Day 1, hours 0–2 | Event rules/schema diff and configuration lock | Resolve changed hard constraints before experiments |
| Hours 2–6 | Audited compliant baseline and cost ledger | No alternative data until NAV/timing reconcile |
| Hours 6–10 | Risk model, support selection and constrained optimizer | If robust conic version is unstable, use validated simpler construction |
| Hours 10–14 | Validation and frequency/cost comparison | Freeze the candidate; no new model families |
| Day 2, hours 0–4 | One optional data/agent ablation | Drop it if availability, incremental value or memory controls fail |
| Hours 4–8 | Full frozen evaluation, stress and Arcana reconciliation | Fix implementation errors; do not tune to OOS winners |
| Hours 8–12 | Reports, holdings exports and evidence pack | Every slide number comes from generated outputs |
| Remaining time | Ten-minute presentation rehearsal and contingency | No last-minute unvalidated feature |

### Module contracts

```text
data/asof       -> dated eligible observations, provenance, historical mappings
forecast        -> per-name expected H-period excess return and uncertainty metadata
risk            -> exposures, horizon covariance, beta uncertainty, scenarios
universe        -> support, signs, eligibility, liquidity and minimum/maximum weights
construction    -> target weights, binding limits, rejected trades, objective components
execution       -> delayed fills, actual holdings, cash, costs, blocked orders
accounting      -> NAV, returns, drifted weights, turnover, long/short attribution
reporting       -> required statistics, figures, holdings, Arcana reconciliation
agent           -> cached explanations or restricted proposals; never enforcement
```

Persist dated predictions, risk inputs, target/actual holdings, trade logs, NAV ledger, data versions, split manifests, experiment registry and cached agent decisions. Provide a `MAIN.py` entry point for the reproducible pipeline while confirming whether the first-round single-file/code submission requirement is still requested; the final specifies a different presentation/holdings process. Export both every-rebalance holdings and monthly snapshots, with permanent identifiers and period-supported ticker/company labels.

### Clarifications to resolve on access—not reasons to delay the baseline

Confirm price/volume and delisting fields; historical market-cap units; daily benchmark alignment; historical borrow/locate availability; exact Arcana upload schema and risk-model vintages; treatment of formation-time short eligibility after passive cap drift; initial deployment/count rules; and the final submission package. The final document explicitly anticipates further event-day configuration.

## 12. Focused literature review and source register

**Reading levels:** “full PDF retrieved” means the complete file was obtained and relevant sections inspected, not that every appendix was independently replicated. “Abstract/record” is a narrower review. Publication years and downloaded working-paper vintages can differ. Later research is guidance for today's design, never permission to import future fitted parameters into the backtest.

### A. Papers in the initial case's bibliography, inherited as reference

| Source and access | What it contributes | What we should do / not infer |
|---|---|---|
| [Jensen, Kelly & Pedersen, w28432 (2021)](https://www.nber.org/system/files/working_papers/w28432/w28432.pdf), full PDF retrieved; [published 2023 version](https://doi.org/10.1111/jofi.13249) separately identified | Hierarchical evidence pooling and replication methodology | Use training-only shrinkage and compare tradable versus research portfolios; do not transplant fitted weights |
| [Gu, Kelly & Xiu, *Empirical Asset Pricing via Machine Learning* (2020)](https://www.nber.org/papers/w25398), 2019-revised working PDF retrieved | Comparative prediction models, nonlinear interactions and chronological validation | Test a small tree challenger; their sample and gross portfolio results do not establish our capacity or expected IR |
| [Chapados et al., *Can AI Read the Minds of Corporate Executives?* (2023)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4493166), authors' abstract read, full paper not verified | Finance-objective text models for future earnings surprises using regular filings | A fundamentals-oriented text branch is more defensible than generic sentiment; do not equate 10-Q/10-K evidence with an 8-K replication or a generic frontier prompt |
| [Goyenko & Zhang, *The Joint Cross Section of Option and Stock Returns Predictability with Big Data and Machine Learning*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3747238), authors' abstract read; record revised 2022 | Option characteristics, notably illiquidity in their study, can inform stock-return prediction | Check dated option data and coverage before proposing the branch; trade equities only under this mandate |
| [Hoerl & Kennard (1970), ridge regression](https://doi.org/10.1080/00401706.1970.10488634), publication record verified | L2 regularization for correlated regressors | Strong, simple default; not a financial alpha theory |
| [Tibshirani (1996), lasso](https://doi.org/10.1111/j.2517-6161.1996.tb02080.x), publication record verified | L1 shrinkage and sparse coefficients | A useful benchmark, but coefficient sparsity does not enforce 200 meaningful portfolio positions |
| [Zou & Hastie (2005), elastic net](https://doi.org/10.1111/j.1467-9868.2005.00503.x), abstract/method discussion read | Combines shrinkage with selection and encourages correlated-variable grouping | A reasonable ridge challenger when redundant characteristics matter; selection stability must be measured |
| [van Binsbergen, Han & Lopez-Lira, *Man versus Machine Learning* (2023)](https://www.nber.org/papers/w27843), 2021-revised working PDF retrieved | Differences between analyst earnings forecasts and an ML benchmark relate to return predictability | Strong economic hypothesis for the short book if historical consensus is available; not a claim that generic ML always beats analysts |

The first-round bibliography also lists a September 2026 Wall Street Journal article and [FRED TB3MS](https://fred.stlouisfed.org/series/TB3MS). The article is context, not academic evidence, and its full text was not independently verified for this plan. The benchmark definition comes directly from the final case. No strategy claim here rests on that newspaper article.

### B. Selected papers cited by JKP: corroborating and skeptical evidence

| Source / review status | Relevant result or research question | Consequence for this project |
|---|---|---|
| [Hou, Xue & Zhang, *Replicating Anomalies* (2020)](https://www.nber.org/papers/w23394), working PDF retrieved and abstract read | Much weaker anomaly evidence under their construction and significance choices | Treat microcap restrictions, weighting and benchmark choice as substantive robustness tests; don't declare one paper has settled the dispute |
| [Harvey, Liu & Zhu (2016), *… and the Cross-Section of Expected Returns*](https://www.nber.org/papers/w20592), PDF retrieved and abstract read | Extensive factor searches require stronger evidence than isolated conventional t-tests | Record the complete search; a t-statistic around 2 is not a universal discovery threshold |
| [Chen & Zimmermann, *Open Source Cross-Sectional Asset Pricing*](https://www.federalreserve.gov/econres/feds/open-source-cross-sectional-asset-pricing.htm), primary abstract read | Close reproduction of published predictors is achievable | Use documented definitions to audit characteristics, while separating reproduction from future net profitability |
| [Kozak, Nagel & Santosh (2020), *Shrinking the Cross-Section*](https://www.nber.org/papers/w24070), full working PDF retrieved | Regularized high-dimensional SDF estimation can retain information across many correlated predictors | Supports shrinkage over aggressive winner selection; an SDF is not itself our stock-level portfolio policy |
| [Feng, Giglio & Xiu (2020), *Taming the Factor Zoo*](https://dachxiu.chicagobooth.edu/download/ZOO.pdf), full journal PDF retrieved, methodology inspected | Test incremental factor content while accounting for variable-selection mistakes | New features must add information beyond existing exposures; ordinary post-selection t-tests are unreliable |
| [Frazzini & Pedersen (2014), *Betting Against Beta*](https://www.nber.org/papers/w16601), working PDF retrieved and primary abstract reviewed | Funding/leverage constraints motivate differences across low/high-beta assets | Dollar neutrality does not imply beta neutrality; a BAB-like tilt is still a recognizable factor strategy |
| McLean & Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?*, JF 71, 5–32; discussed in JKP, not independently full-text reviewed | Post-publication deterioration and the interpretation of alpha decay | Haircut historical alpha and evaluate recent validation; do not budget the full published premium |
| Kelly, Pruitt & Su (2019), *Characteristics Are Covariances*, JFE 134, 501–524; bibliography/JKP discussion only | Characteristics can describe changing factor exposure as well as expected returns | IPCA is a coherent later challenger, but latent factors require external attribution and do not automatically give neutrality |
| Britten-Jones (1999), *The Sampling Error in Estimates of Mean-Variance Efficient Portfolio Weights*, JF 54, 655–671; bibliography/JKP use only | Statistical uncertainty in optimized portfolio weights | Do not use ex-post tangency allocations as a live rule |
| Shumway (1997), *The Delisting Bias in CRSP Data*, JF 52, 327–340; JKP implementation discussion read | Delisting treatment changes measured performance | Preserve terminal economics; JKP's particular −30% imputation is not a universal truth for our file |
| Newey & West (1987), *A Simple, Positive Semi-definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix*; JKP bibliography | Dependence-aware inference | Report appropriate robust alpha/beta uncertainty and block-based comparisons |

JKP also references Ward clustering, Bayesian inference/multiple comparisons, value/momentum, carry, liquidity pricing and broader replication-methodology papers. They support the conceptual background; they were not all independently reviewed here. Cross-asset carry and trend are not direct tradable additions to a U.S.-equity-only neutral mandate. Further reading should be driven by a concrete implementation question, not citation count.

### C. Additional papers needed to answer the rebalancing question

| Source / access | Contribution | Limitation and decision |
|---|---|---|
| [Gârleanu & Pedersen (2013), *Dynamic Trading with Predictable Returns and Transaction Costs*](https://www.nber.org/papers/w15205), full working PDF retrieved | Optimal adjustment depends on existing holdings, trading costs and signal persistence; slower signals justify different trading intensity | Use gradual adjustment and decay tests. Its assumptions and empirical application are not identical to constrained U.S. equities |
| [Ledoit & Wolf, *Honey, I Shrunk the Sample Covariance Matrix*](https://ledoit.net/honey_abstract.htm), authors' abstract read | Shrinkage reduces covariance estimation error that destabilizes portfolio optimization | Use regularized covariance; it does not guarantee correct crisis correlations |
| [Moreira & Muir (2017), *Volatility-Managed Portfolios*](https://www.nber.org/papers/w22208), full working PDF retrieved and abstract reviewed | Reducing risk in high-volatility periods can improve outcomes in their studied factors | Test risk scaling as a policy, not as a universal Sharpe enhancement; inverse variance and constant-volatility scaling are different |
| [Cederburg et al. (2020), *On the Performance of Volatility-Managed Portfolios*](https://doi.org/10.1016/j.jfineco.2020.04.015), [author institution abstract](https://experts.arizona.edu/en/publications/on-the-performance-of-volatility-managed-portfolios/) read | Broad real-time comparisons do not establish systematic outperformance of volatility-managed strategies | Keep a fixed-risk-policy counterfactual and judge net OOS stability; do not assume volatility timing supplies alpha |

## 13. Alternatives considered and why they are not the default

| Approach | When useful | Why not lead with it |
|---|---|---|
| Pure minimum variance | Risk benchmark or constrained risk reduction | Can satisfy risk goals while failing the cash-plus premium; zero book is a degenerate solution without meaningful holdings |
| Equal weight / inverse volatility | Transparent selection benchmark | Ignores cross-stock covariance, beta mismatch and costs unless constrained |
| Risk parity / hierarchical risk parity | Diversifying risk across sleeves | Allocates risk, not expected alpha; standard forms do not solve this long-short mandate |
| Black–Litterman | Combining views with a credible reference portfolio and view uncertainty | A zero-beta long-short book has no obvious market-cap equilibrium prior; Bayesian shrinkage is simpler here |
| IPCA / conditional factor models | Jointly interpreting characteristics, risk and return | Worth a controlled extension, not a prerequisite within two days |
| Online Kalman/state-space beta | Time-varying exposure estimation | Useful only if it beats shrinkage/EWMA without overreacting to noise |
| Regime switching / mixture of experts | Stable, causally identified differences across regimes | Sparse crisis observations and state-selection error create overfitting; never use smoothed future-informed states |
| CVaR / distributionally robust optimization | Explicit tail and ambiguity constraints | Useful extension with credible scenarios; a historical CVaR estimate does not guarantee loss bounds |
| Multiperiod stochastic optimization | Planning costly trades with alpha decay | More assumptions and engineering; add after the one-step controller is validated |
| Reinforcement learning | Long-horizon sequential policies with an independently validated simulator | Too easy to learn simulator errors and impossible-looking fills; weak fit for short daily history and hard feasibility |
| Transformers or universal time-series models | Specialized nonlinear sequence patterns | No evidence here that price-path generation solves cross-sectional alpha, neutrality or joint tail calibration |
| LLM decides final weights | Qualitative interpretation of unusual information | Hard constraints, repeatability and historical memory make unconstrained discretion unsuitable |
| Stop-loss or drawdown-only controller | Limiting additional risk after deterioration | Can sell after losses and miss rebounds; it cannot cap losses through gaps and must be tested against fixed rules |

## 14. Decision to implement

Implement the simplest compliant baseline first, then **hierarchical/regularized forecasting + a dynamic factor risk model + deterministic cost-aware construction with fixed support and meaningful weights**. Use the NBER paper to discipline signal evidence, not to justify buying every known anomaly. The central empirical question is whether within-group selection survives neutrality, costs and $1bn capacity. If it does not, no more elaborate optimizer can manufacture that missing edge.

Keep daily risk monitoring, but make daily trading earn its cost. Target zero beta and bounded risk; report variable realized returns honestly. Prefer an intelligible, repeatable book with credible net returns over an apparently smooth backtest that depends on hidden market exposure, stale prices or future information.

---

### Download provenance

- Requested PDF: `https://www.nber.org/system/files/working_papers/w28432/w28432.pdf`
- Retrieved: 23 October 2026.
- Version in bytes: February 2021 working paper; 54 PDF pages, 52 numbered content pages.
- SHA-256: `95807b0cc26262dad87be2f9b50d653d71f236b669e3d5c5d45f64b0729ce693`.
- Companion source archive contains this PDF, its complete extracted text, supporting PDFs retrieved during research and a manifest. Source files retain their authors' rights; they are supplied for this research task, not republished as our work.
