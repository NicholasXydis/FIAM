# Stream 3 — Risk + construction: Taildrop plan §§5–6 vs FINAL mandate

**Sources opened in full:** [FIAM_Final_Case_Research_and_Implementation_Plan.md](/home/drewclaw/Forkfiam/fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md) §§5–6 (`plan:144-241`, read in full; §§1–4, 7, 12–13 for cross-refs), [final_mandate.txt](/home/drewclaw/Forkfiam/fiam/v4b/inputs/final_mandate.txt) §§3–5, 7, 9, 11. Repo evidence opened: [fiam/risk.py](/home/drewclaw/Forkfiam/fiam/risk.py) (monthly factor model), [fiam/vol.py](/home/drewclaw/Forkfiam/fiam/vol.py) (HAR vs LightGBM specific vol), [fiam/book.py](/home/drewclaw/Forkfiam/fiam/book.py:54) `LIMITS` + `solve():276-312` (shipped monthly QP), [fiam/costs.py](/home/drewclaw/Forkfiam/fiam/costs.py:140-163) (accounting cost model), [fiam/ml/teachers.py](/home/drewclaw/Forkfiam/fiam/ml/teachers.py) monthly-beta teacher. Source-pack papers used: Gârleanu–Pedersen w15205, Frazzini–Pedersen w16601, Moreira–Muir w22208 (via plan §12C). Web searches (4): Ledoit–Wolf nonlinear shrinkage vs factor models under N>T; Gârleanu–Pedersen aim portfolio vs proportional-cost no-trade region; Vasicek/Dimson beta estimation accuracy; cardinality-constrained MIQP feasibility. Past repo work is evidence only.

**Severity:** CRITICAL = infeasible, unimplementable in 2 days, or judged non-neutral if shipped as written · HIGH = large alpha/feasibility cost or judge exposure · MEDIUM = material drag · LOW = polish. **Verdicts:** KEEP / FIX / DROP applied to the plan element.

**Top line:** Plan §§5–6 choose the right family — parsimonious factor covariance, beta band with uncertainty, one-period cost-aware controller, two-stage support, hard-rules-first hierarchy — and are unusually honest about nonconvexity (`plan:211`), SOCP-vs-QP (`plan:199`) and the gross-floor trap (`plan:217`). Those choices are **KEEP**. The failures are calibration and estimability, not direction: (1) the uncertainty objects $U_\beta$ and $U_\mu$ are written as full $N\times N$ matrices that cannot be estimated on 252 daily observations, and the candidate $\pm0.02$ uncertainty-aware beta band is arithmetically infeasible at 200% gross; (2) "regularised trailing regressions" for all exposures (`plan:154`) is the wrong estimator for sector/style loadings and unimplementable rolled daily — the repo already contains the correct characteristic-exposure architecture; (3) the objective mixes three regularisers ($\gamma\Sigma$, $\rho\sqrt{w^\top U_\mu w}$, $\eta\|w\|^2$) plus a power-cone impact term, citing Gârleanu–Pedersen (quadratic costs ⇒ partial adjustment, *no* no-trade region) for an L1 no-trade logic that comes from a different cost model; (4) neutrality is over-imposed in formula (`|B'_{style}w|\le d`, `plan:207`) relative to the plan's own correct §3 principle, while the one mechanical tilt the mandate creates — long-small/short-large from the $500m short floor — is never named. Every fix below is a simplification toward a QP that can be built and walk-forwarded in the event window.

---

## 0. What the mandate actually judges (the target §§5–6 must hit)

| # | Mandate requirement | Consequence for risk/construction |
|---|---|---|
| M1 | Gross ≤200%, net ±50% "at all times; dollar neutrality is the natural centre", 200–500 combined names, ≤5%/name, shorts ≥$500m at formation — §3.1 (`final_mandate.txt:114-125`) | Hard set is small and linear (except count). Everything else is policy and must yield first (see F7). |
| M2 | "Neutrality has more than one definition… dollar, beta, or sector and factor… long high-beta / short low-beta is a levered long in disguise. **We will estimate your realised beta ourselves, at both daily and monthly frequency**" — §3.3 (`:194-198`); beta = OLS slope of excess returns on S&P 500 excess, both frequencies with SEs — §9.2 (`:947-951`); 252-day rolling beta exhibit — §9.4 (`:980`) | The hedged object must be the judges' estimator: contemporaneous univariate OLS beta. Any other beta (Dimson, downside, multi-factor market loading) is a diagnostic, not the constraint (F3). |
| M3 | $1bn compounding; ~$4m/name at 500, ~$10m at 200; participation 10–20% ADV is the professional norm — §3.3 (`:175-187`); position-size-in-days-of-ADV exhibit split by leg — §9.4 (`:988`) | Capacity binds inside construction, at current NAV, separately for orders vs holdings. Plan §7 gets this right; §6 must import it as bounds, not commentary (F6). |
| M4 | Daily permitted not mandated; turnover is "the binding constraint"; costs before/after mandatory — §4 (`:232-253`); turnover $=\tfrac12\sum_i|w_{i,\tau}-w_{i,\tau-}|$ on drifted weights — §9.3 (`:956-967`) | The controller's cost terms must reconcile to the accounting costs in §9 reporting. Two different impact models (optimizer vs ledger) will be caught (F5). |
| M5 | Arcana review: factor-vs-idiosyncratic split (lens 1), unintended-exposure emergence (lens 2), sizing-vs-selection (lens 3), 50+ stress scenarios (lens 7) — §11 (`:1090-1114`) | Judges decompose with Barra/Axioma-class models (`:1062-1065`). An internal 16-factor model will disagree; the defence is pre-computed attribution on the same lenses, not a bigger internal model (F1, F4). |
| M6 | Agent may propose, **code enforces** every hard constraint; counterfactual vs fixed rule mandatory — §5.3 (`:369-382`) | Constraint enforcement and infeasibility handling must be deterministic code paths with logs (`plan:231` correct). No LLM in the repair loop (F7). |

---

## F1. Single dynamic risk model: factor structure KEEP; exposure estimator and horizon scaling FIX [HIGH]

**Plan §5** (`plan:146-156`): $\Sigma_{t,H}=B_tF_{t,H}B_t^\top+D_{t,H}$; $B$ = market + nonredundant sectors + size/value/momentum/profitability/investment; "Estimate exposures with shrinkage… Start with regularized trailing regressions and exponentially weighted covariance… Candidate 252-day exposure windows and 20–60-day volatility half-lives"; "A 500-stock unregularized covariance matrix estimated from approximately 252 daily observations is an unstable input for inversion. A factor model with shrinkage is the practical default."

### F1.1 Factor vs shrinkage covariance — the plan picks correctly, for a stronger reason than it states [KEEP]

With support $N=300$–$500$ (universe ~3,000+) and $T=252$ daily obs, the sample covariance is singular ($N>T$) and its eigenvalues spread per Marčenko–Pastur even when $N<T$; inversion for mean-variance weights amplifies the smallest eigenvalues — exactly the noise directions. Two regularised families compete:

| Attribute | Factor $BFB^\top+D$ (plan) | Ledoit–Wolf shrinkage of sample cov |
|---|---|---|
| Parameters at N=400, K=16 | $K(K{+}1)/2+N \approx 536$ | $N(N{+}1)/2 \approx 80{,}200$, shrunk |
| Needs $T$ vs | $T \gg K$ (factor cov only) | Works at $N>T$ (target is PD) |
| Gives exposures/attribution | Yes — sector, beta, style (M5) | No — judges' lenses unanswerable |
| Failure mode | Omitted factor (subjectivity) | Shrinks true structure toward target |

Linear Ledoit–Wolf (2004) shrinks toward scaled identity/constant-correlation with one intensity — too blunt when sector blocks are real. Nonlinear shrinkage (Ledoit–Wolf 2012/2020) keeps sample eigenvectors and shrinks each eigenvalue (optimally the *inverse* eigenvalues for portfolio use) via the Marčenko–Pastur/Stieltjes machinery; it dominates linear shrinkage for minimum-variance portfolios at $N/T$ near 1 in their horse races. But it still yields an uninterpretable dense $\hat\Sigma$: no beta vector, no sector exposure, no Arcana-lens answer, and $\hat\Sigma$ must be re-estimated on the *support* each rebalance (eigenvectors change as names enter/leave). **Verdict: factor model as the single coherent model — KEEP.** Correct use of Ledoit–Wolf here is *inside* it: shrink the $K\times K$ factor covariance $F$ toward its diagonal (or apply nonlinear shrinkage to $F$, where $K\approx16\ll T$ makes even the sample $F$ well-conditioned), and shrink specific variances cross-sectionally toward sector medians. Plan `plan:152` ("shrink factor covariance and floor idiosyncratic variances") says this — **KEEP**, and name the targets: $F \leftarrow (1-\delta)\hat F^{EWMA}+\delta\,\mathrm{diag}(\hat F)$ with $\delta\approx0.1$–$0.3$ chosen pre-OOS; $D$ floored at e.g. the 5th cross-sectional percentile to stop the optimizer loading on a spuriously "riskless" name — the classic error-maximisation channel the floor exists to block.

### F1.2 "Regularized trailing regressions" for all of B is the wrong estimator [FIX · HIGH]

Barra-style models — and the repo's own [fiam/risk.py](/home/drewclaw/Forkfiam/fiam/risk.py:22-33) — do **not** estimate sector/style exposures by time-series regression. They *assign* them: sector = dummy (exact, zero estimation error), styles = cross-sectionally standardised characteristics (`risk.py:14-15` maps size→`market_equity`, value→`be_me`, momentum→`ret_12_1`, low-vol→`ivol_capm_252d`, quality→`ope_be`, each rank-z'd within month), then estimate *factor returns* by cross-sectional WLS each period (`risk.py:37-49`, $\sqrt{me}$ weights) and $F$ as the (EWMA) covariance of those factor returns (`risk.py:53-60`, half-life 36 *months* — monthly vintage). Only the market beta is a time-series object, and in Barra it too is a shrunk blend.

Trailing multivariate regressions per stock ($r_i$ on market + sector + 5 style factor returns, 252 obs) invert this: K≈16 correlated regressors per name, betas that swing with the window, style loadings that no longer equal the characteristics the forecaster used — breaking the plan's own "limit interpretable nuisance exposures" accounting (`plan:94`) because $B^\top w$ stops meaning "average standardised size of the book". Rolled daily over ~3,000 names × ~1,400 OOS days it is also ~4M regressions — **unimplementable as a daily refresh in the event budget**; weekly/monthly refresh of characteristic exposures is one groupby.

**Mathematically correct alternative (adopt repo architecture, extend frequency):**

1. Exposures $B_t$: sector dummies exact; styles = within-date standardised characteristics carried from the monthly panel (staleness is fine — characteristics are slow; `plan:154` already notes monthly fundamentals need not refresh for daily price risk); market beta column = shrunk time-series beta (F3), updated weekly.
2. Factor returns $f_t$: daily cross-sectional WLS of stock returns on $B_t$ over the liquid universe (weights $\propto 1/\hat\sigma_{e,i}$ or $\sqrt{me}$ as in `risk.py:45`), with one identification constraint (market factor + sector dummies are collinear with an intercept: drop the intercept and impose cap-weighted $\sum_s \overline{me}_s f_{s,t}=0$ on sector factor returns, Barra-style, so sector returns are deviations from the market factor). One regression per day, not per stock.
3. $F_{t}$: EWMA covariance of $f_t$ (F1.3) + diagonal shrinkage; $D_t$: EWMA of squared residuals $e_{i,t}^2$ per name with cross-sectional shrinkage + floor. Specific-risk forecasting already has a validated repo answer — HAR beat LightGBM and was frozen (`vol.py:107`, `risk.py:117` "specific: fiam.vol (HAR: LGBM failed)") — reuse the HAR specific-vol forecast, rescaled, rather than inventing a second specific-risk model in §5.

### F1.3 EWMA half-lives 20–60d: defensible range, missing effective-sample and horizon arithmetic [FIX · MEDIUM]

EWMA weight $\lambda=2^{-1/HL}$ per day; effective sample $T_{eff}\approx(1+\lambda)/(1-\lambda)\approx 2.9\times HL/\ln2$… precisely $T_{eff}=(\sum w)^2/\sum w^2$: HL=20d ⇒ $T_{eff}\approx58$; HL=60d ⇒ $\approx173$. Against $K=16$ factors both are estimable ($T_{eff}/K\approx4$–$11$); against a *specific variance* per name, HL=20d gives relative SE $\approx\sqrt{2/T_{eff}}\approx19\%$ on variance (≈9% on vol) before fat-tail inflation — noisy enough that the optimizer will chase it. RiskMetrics $\lambda=0.94$ (HL≈11d) is a one-day VaR choice, wrong for a 21-day holding horizon. Barra USE4-class models use HL ≈ 80–120d for factor cov with volatility-regime adjustment. **Fix:** predeclare HL$_{factor}\in\{42,84\}$d and HL$_{spec}\in\{84,168\}$d (specific slower than factor — opposite of the plan's single 20–60d band), select by pre-OOS bias statistic $\mathrm{std}(r_{p,t}/\hat\sigma_{p,t})$ on frozen validation books — the repo already implements exactly this test with Kupiec/Christoffersen VaR backtests ([fiam/risk.py:74-105](/home/drewclaw/Forkfiam/fiam/risk.py:74)); port it to daily. Newey–West/autocorrelation adjustment on $f_t$ before EWMA (factor returns, esp. momentum/liquidity factors, are autocorrelated; raw EWMA understates multi-day factor variance).

**Horizon scaling — unspecified in the plan, load-bearing in §6.** $\Sigma_{t,H}$ at $H=21$d is not $\Sigma_{t,1d}\times21$ unless returns are iid. Correct first-order: $\Sigma_{H}=H\,\Sigma_1+\sum_{j=1}^{H-1}(H-j)(\Gamma_j+\Gamma_j^\top)$ with $\Gamma_j$ the lag-$j$ autocovariance — in factor space this is cheap ($K\times K$). At minimum: estimate $F$ from *non-overlapping 5-day* factor returns for the weekly controller and scale $\times(H/5)$, and state the iid assumption where used. Mixing a daily $F$ with a 21-day $\mu$ and tuning $\gamma$ to fit (`plan:190` warns "align all horizons" but gives no formula) makes $\gamma$ absorb a factor-21 error and every $\gamma$ comparison across frequencies meaningless.

### F1.4 "One coherent covariance" + stress overlay [KEEP with relabel]

`plan:152` ("a short-memory stress estimate can impose an additional risk constraint rather than silently replacing the model") is the right governance — but then there are two covariances and the binding one is $\max$ of the two risk numbers. Label it a robust constraint $\max\{w^\top\Sigma^{base}w,\;w^\top\Sigma^{fast}w\}\le\sigma_{max}^2$ (second-order-cone representable as two constraints) and report which binds. Silent-switching procyclicality (de-risk after vol spikes, re-risk after calm) is what Moreira–Muir vs Cederburg dispute (`plan:449-450` handles honestly) — a constraint that only binds in stress is the defensible middle.

---

## F2. The N>T problem is solved for Σ but reintroduced for U_β and U_μ [FIX · CRITICAL]

Plan §5 solves $N>T$ for returns via factors, then §5–§6 pose two new $N\times N$ objects: beta-error covariance $U_{\beta,t}$ in $|\hat\beta^\top w|+z\sqrt{w^\top U_\beta w}\le\epsilon_\beta$ (`plan:163`) and forecast-error covariance $U_{\mu,t,H}$ in $\rho\sqrt{w^\top U_\mu w}$ (`plan:185`). Neither estimator is specified. Both are harder than $\Sigma$ itself:

**$U_\beta$.** For univariate market regressions on a common sample, $\hat\beta_i-\beta_i=\sum_t \tilde r_{m,t}e_{i,t}/S_{xx}$ with $S_{xx}=\sum_t\tilde r_{m,t}^2$, so exactly
$$U_\beta=\mathrm{Cov}(\hat\beta)=\frac{\Sigma_e}{S_{xx}},$$
where $\Sigma_e$ is the $N\times N$ residual covariance — the very matrix the factor model exists to avoid estimating densely. The factor structure rescues it: $\Sigma_e\approx B_{-m}F_{-m}B_{-m}^\top+D$ (residuals still carry sector/style factors), hence $w^\top U_\beta w=(w^\top\Sigma_e w)/S_{xx}$ = (book's non-market variance)/$S_{xx}$, computable from objects already in §5. A diagonal $U_\beta$ (independent beta errors) *understates* uncertainty whenever the book has net sector/style exposure — precisely when beta error matters. **Correct alternative:** implement the scalar $\sqrt{w^\top U_\beta w}=\sqrt{w^\top\hat\Sigma_e w/S_{xx}}$ from the factor model; never form $U_\beta$. The plan's fallback (`plan:166`: slow/fast/downside beta scenario constraints) is more robust than a fabricated $U_\beta$ — promote it to the default, keep the SOC as the labelled refinement.

**$U_\mu$.** For the §4 ridge, $\hat\mu=X\hat\theta$ gives $U_\mu=X\,\mathrm{Cov}(\hat\theta)\,X^\top$, rank ≤ $p\approx147$, with $\mathrm{Cov}(\hat\theta)$ requiring a dependence-aware (block/HAC) sandwich — estimable but a research project, and undefined for the GBM challenger (`plan:118` concedes tree dispersion "is not automatically a calibrated posterior variance"). §3's $P$ is factor-alpha posterior covariance, explicitly *not* $U_\mu$ without the $APA^\top$ map (`plan:86`). So as written §6's headline robustness term has no input. **Correct 2-day alternative:** diagonal uncertainty — shrink each $\hat\mu_i$ toward its sector mean by its validation calibration and penalise $\sum_i u_i w_i^2$ with $u_i\propto\hat\sigma^2_{e,i}/(\text{signal age, coverage})$ (a QP term, folds into $\eta\|w\|^2$ with name-specific $\eta_i$), or the quadratic form $w^\top U_\mu w$ with low-rank $U_\mu=X\Lambda^{-1}X^\top\hat\sigma^2$ from the ridge design — which is just extra risk aversion along characteristic directions and should be reported as such, not as an ellipsoidal worst case. Keeping $\rho\sqrt{w^\top U_\mu w}$ with an invented $U_\mu$ is worse than dropping it: an SOC constraint with wrong geometry binds in wrong directions. **Verdict: DROP the SOC term from v1; keep diagonal forecast-quality shrinkage. Revisit only with a computed ridge sandwich covariance.**

---

## F3. Beta control: right constraint shape, infeasible candidate band, wrong beta unless specified [FIX · CRITICAL]

**Plan §5** (`plan:158-168`): target zero; robust band above; "A nominal beta band of ±0.02 is a candidate internal policy. First test whether it is feasible… Separate the nominal band from the larger uncertainty-aware bound. Report rolling realized beta with confidence intervals, including both daily and monthly regressions."

### F3.1 The ±0.02 uncertainty-aware band fails its own feasibility test at 200% gross

Daily 252-day OLS beta SE for a typical name: $\mathrm{se}(\hat\beta_i)=\sigma_{e,i}/\sqrt{S_{xx}}\approx(1.5\text{–}2.5\%\,/\text{day})/\sqrt{252\times(1\%)^2}\approx0.15\text{–}0.25$. For a diversified book, $\sqrt{w^\top U_\beta w}\approx\sqrt{\sum_i w_i^2\mathrm{se}_i^2}$ (diagonal approx — a *lower* bound per F2). At 200% gross over $N_{eff}\approx150$ effective names (`plan:222`), $\sum w_i^2\approx\|w\|_1^2/N_{eff}=4/150\approx0.027$, so the uncertainty radius $\approx0.2\times\sqrt{0.027}\approx0.033$, and $z\cdot(\cdot)$ at $z=1.65$ ≈ **0.054 > 0.02** — infeasible before any alpha, liquidity or sector constraint, and worse with correlated errors. The shipped monthly book can hold `|β̂ᵀw| ≤ 0.02` ([fiam/book.py:54,300](/home/drewclaw/Forkfiam/fiam/book.py:300), `beta_60m` point estimates, gross 1.6) precisely because it constrains only the point estimate. **Fix:** nominal $|{\hat\beta}^\top w|\le0.02$ as the hard constraint (proven feasible pattern), uncertainty-aware bound as a *reported* quantity with $\epsilon_\beta^{rob}\approx0.08$–$0.10$ or as a soft penalty; if the robust form must bind, gross or $N_{eff}$ must give — state that trade-off with the arithmetic above in the deck. Never present ±0.02-robust as achievable without the feasibility run `plan:168` demands.

### F3.2 Which beta? Vasicek KEEP, Dimson as diagnostic only, hedge the judges' estimator [FIX · HIGH]

- **Vasicek (1973) shrinkage** $\hat\beta_i^{V}=\frac{\hat\beta_i/\mathrm{se}_i^2+\bar\beta/\tau^2}{1/\mathrm{se}_i^2+1/\tau^2}$, $\bar\beta$ = cross-sectional (or sector) mean, $\tau^2$ = cross-sectional beta variance. Best-practice evidence (Welch 2022 "simply better betas"; Levi–Welch; Lof 2026 assessment): 1-year daily OLS + Vasicek shrinkage is the hard-to-beat beta forecaster; shrinkage "remains highly advisable" in every horse race; winsorisation + EWMA weighting also help. The repo currently hedges raw `beta_60m` (60 *monthly* obs — slow, `book.py:210,253`) or a LightGBM beta teacher trained to mimic within-month daily betas (`teachers.py:monthly_beta()`, clipped to [−1,4]) — neither is Vasicek-shrunk daily beta. **Fix:** hedge beta = Vasicek blend of 252d daily OLS (winsorised returns) toward sector mean, blended 50/50 with 60m monthly beta for stability (Frazzini–Pedersen BAB uses 5y monthly + 1y daily with Dimson + Vasicek toward 1, w16601 — a defensible template to cite). Shrinkage also directly reduces $U_\beta$ above.
- **Dimson (1979)** $\hat\beta^{D}=\sum_{k=-K}^{K}\hat\beta^{(k)}$ (leads/lags of market) corrects nonsynchronous-trading attenuation. Relevant here asymmetrically: shorts are ≥$500m (liquid, Dimson ≈ OLS), longs are unrestricted (illiquid longs: contemporaneous OLS understates true beta). But — decisive — judges compute realised beta as *contemporaneous* OLS slope (M2). Hedging Dimson beta to zero leaves contemporaneous beta *negative* on an illiquid-long book (you over-hedge the measured object). Evidence also warns multi-lag Dimson adds variance and can underperform shrunk OLS out-of-sample for liquid US names (Hoberg–et-al-style horse races: "The Dimson correction is better avoided" for 1y daily). **Correct treatment:** constrain contemporaneous shrunk beta (what is judged); *report* Dimson (±1 lag is enough at this liquidity; ±5 is variance without bias benefit) and downside beta as sensitivity exhibits — exactly `plan:166`'s scenario idea, with the hierarchy made explicit. The panel already carries `beta_dimson_21d`, `betadown_252d`, `betabab_1260d` (`book.py:95-97`) — diagnostics are free.
- **Realised-beta judging reality check.** Ex-ante $\hat\beta^\top w=0$ does not deliver realised 0: betas vary, weights drift, and monthly realised beta over 68 obs carries SE ≈ $\sigma_{e,p}/(\sqrt{68}\,\sigma_m)$ ≈ 0.06–0.10 for a 6–8%-vol book — a realised monthly beta of 0.12 can be statistically indistinguishable from 0 yet read as "materially different" (`final_mandate.txt:197`) by a judge eyeballing the point estimate. Defence is presentational and must be built now: report daily beta (1,400+ obs, SE ~0.02–0.03 — the precise one) as headline compliance evidence, monthly with HAC CI (`book.py:489` `regress()` already HAC), plus the 252d rolling exhibit (§9.4). `plan:168` ("insignificant beta with wide CI is weak evidence") cuts both ways — say so.

---

## F4. Stress and tails: good scenario list, no budget, no constraint mapping [FIX · MEDIUM]

**Plan §5** (`plan:170-174`): market fall + correlated short squeezes, momentum reversal, sector dislocations, vol/corr increases, wider spreads, lower ADV, borrow recalls, delayed liquidations; joint historical/block scenarios; Student-t sensitivity; EVT/complex GARCH not mandatory; "HAR-CJ needs… realised/jump inputs, which close-to-close daily returns alone do not provide."

- Scenario *list* and joint-block requirement: **KEEP** — independent per-stock simulation understating joint loss is correctly prohibited. HAR-CJ remark: correct (needs intraday RV/bipower variation; `fiam/vol.py` HAR on daily closes is HAR in name only — 5/21/63d realised vols, still useful, just don't claim jump separation).
- Missing: (i) a *loss budget* per scenario ($w^\top r^{(s)}\ge -L_s$, e.g. $L$=3% NAV for factor shocks) imposed as linear constraints in §6 — without it stress is a reporting exhibit that cannot change the book, and Arcana lens 7 (M5) will show breaches the team never constrained; (ii) calibration discipline — scenarios fit on 2021–26 OOS windows (e.g. Jan-2021 squeeze) then used to "control" that same window is in-sample policy tuning; `plan:172` says identify windows in advance — enforce: pre-2021 episodes (2008 momentum crash, 2020-Mar) for calibration, OOS episodes diagnostics-only; (iii) short-squeeze modelling — a factor shock cannot generate it; squeeze = idiosyncratic + borrow recall + ADV collapse jointly on high-short-interest names. Implement as name-level overlays: cap short weight by short-interest/borrow tier (repo `costs.py:26` tiers exist), stress = top-decile crowded shorts +30% idiosyncratic with forced cover at stressed ADV. Student-t residuals (iv): state df (4–6 for daily equity residuals) and use only to scale *specific* tail, or drop — an unparameterised "t sensitivity" is unfalsifiable.
- Tail dependence the Gaussian factor model misses even with scenarios: correlations →1 in crashes makes $BFB^\top$ with calm-period $F$ understate crash beta (long high-β/short low-β book's crash beta > calm beta — exactly the disguised-long failure M2). Add one *correlation-stressed* $F^{stress}$ (factor correlations shrunk 50% toward ±1 by sign, vols ×1.5) as the F1.4 second constraint. Cheap, honest, no copula/EVT needed. **Verdict: KEEP framework, FIX by adding budgets + pre-2021 calibration + one crowded-short overlay; DROP unspecified Student-t or parameterise it.**

---

## F5. Controller objective: over-regularised, cost-model confused, GP mis-cited [FIX · CRITICAL]

**Plan §6** (`plan:180-199`):
$$\min_w\ \tfrac{\gamma}{2}w^\top\Sigma_{t,H}w-\mu_{t,H}^\top w+\rho\sqrt{w^\top U_\mu w}+C_t(q)+H\sum_i b_i\max(-w_i,0)/252+\eta\|w\|_2^2,\quad q=w-w^-$$
$$C_t(q)=\sum_i s_i|q_i|+\sum_i\kappa_i\sigma_i|q_i|\sqrt{NAV|q_i|/ADV_i}.$$
Plan correctly notes this is conic, "not honestly described as a plain QP" (`plan:199`), offers quadratic/piecewise-linear impact as simpler path, and labels the controller receding one-period, not dynamic programming (`plan:241`). All **KEEP**. Five problems remain:

### F5.1 Gârleanu–Pedersen ≠ L1 no-trade region — pick the cost model, then the policy shape [HIGH]

| Cost structure | Optimal policy | Small-trade behaviour |
|---|---|---|
| Quadratic $\tfrac12 q^\top\Lambda q$, $\Lambda=\lambda\Sigma$ (**GP 2013**, w15205) | Partial adjustment to *aim* $\bar x_t$ = discounted avg of current + expected future Markowitz portfolios; trading rate $\theta\in(0,1)$ | Always trade a little; **no no-trade region** |
| Proportional $s\|q\|_1$ (Davis–Norman; GP-framework extensions) | Parallelogram no-trade region; trade minimally to its boundary | Strictly no trade inside region |
| Plan's $s\|q\|_1+\kappa\|q\|^{3/2}$ (one-period) | No-trade region from L1 kink (below) + smooth braking from 3/2-power | No trade iff marginal benefit ≤ spread |

The plan invokes GP for "gradual, cost-aware rebalancing" (`plan:13`) and simultaneously wants L1 no-trade regions/hysteresis (`plan:237`). These are different theorems. The one-period L1 logic is self-contained and correct — from the subgradient condition at $q_i=0$, name $i$ is not traded iff
$$\bigl|\,\mu_i-\gamma(\Sigma w)_i-\eta\text{-terms}-(\text{borrow/constraint shadows})_i\,\bigr|\ \le\ s_i,$$
i.e. band width = name-level half-spread $s_i$ (plus impact derivative where differentiable), **not** a global rank buffer. State it this way, calibrate hysteresis bands to $s_i$ distribution, and cite GP only for the two qualitative lessons that survive: (a) trading intensity falls in cost and rises in signal persistence (aim-weight vs trading-speed are separate knobs — a one-period model has only the first), (b) existing holdings enter the optimum ($w^-$ dependence). Claiming GP aim-portfolio optimality for a myopic L1 controller will not survive a judge who has read GP. Repo status quo for scale: shipped `solve()` has *no* cost or turnover term at all — $\max a^\top w-\tfrac12\cdot30\|w\|^2$ ([fiam/book.py:306](/home/drewclaw/Forkfiam/fiam/book.py:306)) with turnover reduced only by re-adding held names to the pool (`book.py:278-281`). The plan's controller is a genuine advance; it does not need a borrowed optimality claim.

### F5.2 Triple regularisation is unidentifiable on 24 validation months [HIGH]

$\gamma$ (risk aversion), $\rho$ (forecast-uncertainty SOC), $\eta$ ($\|w\|^2$ concentration) all shrink/diffuse weights; with $F$ near-diagonal-dominant styles, $\tfrac{\gamma}{2}w^\top D w$ already *is* a name-weighted $\|w\|^2$. Tuning $(\gamma,\rho,\eta,\kappa)$ on 2019–20 validation is a 4-D search against ~24 monthly (or ~500 correlated daily) observations — validation overfitting by construction. **Correct v1:** drop $\rho$-SOC (F2), set $\eta=0$ (let $D$ do the work; keep explicit 1% cap for concentration), tune only $\gamma$ (via target ex-ante vol $\sigma_{max}$ — see F8.3, one interpretable knob) + one cost scalar multiplier. Every extra knob must earn promotion on net IR per the E-ladder discipline (§9), not arrive in the baseline.

### F5.3 Impact term: keep square-root in accounting, quadratic in optimizer [FIX · MEDIUM]

$\kappa_i\sigma_i NAV^{1/2}ADV_i^{-1/2}|q_i|^{3/2}$ is convex (power 3/2) but needs a power cone per name; CVXPY/Clarabel can in principle, 300 names × ~290 weekly solves × ladder variants cannot in practice within build/debug time, and $\kappa_i$ is uncalibrated ("not a universal empirical law", `plan:199` — correct). The repo's ledger already charges square-root impact ex post with $Y=1.0$ (sensitivity 0.5) ([fiam/costs.py:23-24,154](/home/drewclaw/Forkfiam/fiam/costs.py:154)) at $10m NAV — rescaling to $1bn compounding is mandatory regardless. **Correct split:** optimizer uses quadratic impact $\sum_i c_i q_i^2$ with $c_i=\kappa\sigma_i NAV/ADV_i$ (linear temporary impact in participation; QP, GP-shaped partial adjustment on this component); ledger keeps sqrt-impact. Disclose the approximation direction: quadratic *overstates* large-trade cost vs sqrt, *understates* small-trade — conservative exactly where capacity binds. Optimizer-ledger mismatch (M4) is then bounded and stated, not hidden. Also: $s_i$ must be the same calibrated half-spread object in both places (repo: `costs.py:88-91` size-group calibrated — reuse, recalibrate units at $1bn).

### F5.4 Borrow and horizon bookkeeping [FIX · LOW]

$H\sum b_i\max(-w_i,0)/252$ is dimensionally right for an $H$-day hold. Re-solved weekly with $H=21$, each solve charges 21 days of borrow for a book held 5 — consistent only if interpreted as *steady-state* holding cost rate, in which case write it as $(H_{hold}/252)$ with $H_{hold}$ = days to next review and keep $\mu,\Sigma$ on that same horizon via F1.3 decay scaling. Mixed horizons (21d $\mu$, 5d holding cost) distort the short leg's hurdle by 4×. One horizon $H$ everywhere in the objective; signal decay converts the 21d forecast to it.

### F5.5 Solve-time feasibility [KEEP the QP fallback as the baseline]

QP with 300 vars, ~20 linear constraints, L1 via auxiliary vars: Clarabel milliseconds–seconds; full weekly walk-forward 2021–26 (~290 solves) plus validation ladder is an overnight-free computation. SOCP + power cones: 10–100× slower with far worse failure modes (cone infeasibility certificates mid-backtest). Plan §11 already budgets "if robust conic version is unstable, use validated simpler construction" — invert the order: **QP is the baseline (E1–E3); conic terms are E-upgrades that must beat it.** Daily *exception* trades must never full-resolve the book: project the drifted book onto the violated constraint only (minimum-turnover repair QP), else "daily risk monitoring" becomes daily alpha re-trading with 252× turnover annualisation (M4).

---

## F6. Support selection 200–500: two-stage heuristic KEEP; MIP correctly rejected; three design fixes [FIX · HIGH]

**Plan §6** (`plan:211-225`): count + minimum size are nonconvex, "Do not hide that fact"; Stage 1 rank by forecast advantage/holdings/tradability/factor coverage → ~300 names, preassigned signs, hysteresis; Stage 2 QP on support with [0.10%, 1%] signed bounds + ADV caps; deterministic support repair; never pad with tiny weights; $N_{eff}=(\sum(|w_i|/\|w\|_1)^2)^{-1}$ reported.

**MIP verdict: plan is right not to attempt it.** Cardinality-constrained QP is NP-hard ($\binom{3000}{300}$ supports); exact MIQP is routine only to ~200–300 *universe* names with a commercial solver (Gurobi licence not guaranteed in the event environment; Clarabel/ECOS have no integers; open-source MIP (HiGHS/SCIP) on MI**Q**P with dense factor $\Sigma$ will not certify in backtest-loop time). Any team claiming "optimal 300 from 3,000" is claiming a time-limited heuristic with extra steps. Two-stage select-then-weight is the industry-standard answer (cf. GRASP+QP hybrids) and matches the repo's proven pattern — `optimize_month()` takes top/bottom `pool=200`/side by signal, doubling depth until feasible ([fiam/book.py:264-272](/home/drewclaw/Forkfiam/fiam/book.py:264)). **KEEP.**

Fixes:

1. **Selection criterion must be risk- and cost-adjusted, not raw rank.** Top-|$\hat\mu$| selection picks correlated clusters (one sector's momentum names) and Stage 2 then pays the neutrality constraints to undo Stage 1. Greedy marginal-utility selection: iteratively add the name maximising $(\hat\mu_i - \text{borrow}_i - \text{entry cost}_i)/\hat\sigma_{e,i}$ subject to per-sector quotas and sign balance, with held names credited their saved exit cost (hysteresis in *economic* units: incumbent kept unless challenger's advantage exceeds round-trip cost — the F5.1 band logic applied to support). Sector quotas in Stage 1 are what make the F8 sector-neutrality constraint cheap in Stage 2.
2. **Preassigned signs forbid pure hedges — contradicting `plan:219`.** A name held *against* its forecast sign purely for beta/sector offset is sometimes the cheapest neutrality (repo does the same sign-fixing for explainability, `book.py:285-286` — a deliberate, defensible choice). Choose explicitly: either sign-fixing everywhere (then delete "hedge value" as a holding justification and budget neutrality cost accordingly) or a capped hedge sleeve (≤10% gross, sign-free, forecast must be ≈0 so it is a hedge not a counter-signal bet). Silence on this is an infeasibility source: sign-fixed + sector-neutral + beta-neutral can have empty interior in a month where one sector's signals are one-signed.
3. **Minimum 0.10% × 300 = 30% gross floor** (`plan:217` discloses honestly — KEEP disclosure): interacts with vol-target de-risking (cannot go below 30% gross without breaking count *or* minimum). Hierarchy must state minimum-size relaxes before count (policy before mandate — F7). Also at the 1% internal cap, reaching 200% gross needs ≥200 names *at cap* — with ~300 names average |w|≈0.67% ≈ $6.7m at inception; the cap binds the best ideas at 1.5× average, flattening sizing-vs-selection (Arcana lens 3 will show near-equal weights — pre-empt by reporting the identical-support equal-weight counterfactual, `plan:361`). Consider cap = min(1%, ADV-based cap) but allow 1.5% for top-decile ADV names if validation shows sizing adds IR; don't decide by taste.

$N_{eff}$ reporting: **KEEP**, with `plan:225`'s caveat (concentration ≠ independent bets — correlated factor bets make true breadth lower; report factor-risk share of variance alongside).

---

## F7. Constraint priority and infeasibility: correct principle, needs slack mechanics [FIX · MEDIUM]

**Plan §6** (`plan:227-231`): legal/competition eligibility and hard exposure rules first; then beta/capacity/risk policy; then expected return; "Do not lexicographically minimize beta variance all the way to a zero portfolio… Require compliance with a tolerance, then optimize utility within it"; turnover limits may be exceeded to repair hard breaches; blocked orders and actual breaches recorded, never fabricated fills; buffers below caps for drift; "Daily data cannot prove intraday compliance."

Principle: **KEEP in full** — this is the correct lexicography and matches Mandate §5.3 code-enforces (M6). Two mechanical gaps:

1. **Solver-level encoding.** A hard-constrained QP that is infeasible returns a certificate, not a book — mid-backtest that is a crash, not a policy. Encode the hierarchy with slacks: hard set (gross ≤2, |net|≤0.5 mandate band, 5% cap, short-floor bounds, ADV order caps) stays hard; internal policies (ε_net small, β band, sector/style bands, σ_max, turnover guide) get slack variables with ordered exact penalties ($M_1\gg M_2\gg$ alpha scale), so the solver always returns the least-violating feasible book *and* names which policy yielded and by how much — that slack log *is* the §5.1 pre-trade explanation input. Support repair (`plan:215`) then becomes: enlarge support (repo depth-doubling pattern) → re-solve with slacks → if hard set itself infeasible on full eligible universe (possible only via halts/borrow + count floor), fall to minimum-gross compliant book and log a breach day. Specify this ladder deterministically now; "deterministic support-repair procedure" unspecified is a Day-1 debugging sink.
2. **Drift compliance semantics.** Submitted holdings prove formation-date compliance; mandate says gross/net hold "at all times" (§3.1) but judges reconstruct from holdings + daily returns, where drifted gross can wander (200% gross book, +10% long-leg month ⇒ net +~5%, gross falls — net band ±50% is hard to breach passively; 5% name cap breach needs a +400% winner at 1% internal cap — internal caps *are* the drift buffer, say so quantitatively). Count can breach by delisting (500→499 fine; exactly-200 book losing a name intraday unfixable) — hold a count buffer (target 300 as planned, repair threshold 220) and disclose. `plan:231`'s honesty on intraday proof: KEEP verbatim in deck.

Short-floor encoding detail (cross-ref Stream 1 §2.3): "at formation" ⇒ bound applies to initiation/increase; passive drift below $500m must not force-cover. In bound form: new/increased short requires `me_{i,t} ≥ 500`; else `w_i ≥ min(w⁻_i,0)` (hold-or-cover). Plan §6's daily monitoring for "disqualifying shorts" (`plan:238`) must implement *this*, not an exit trigger, or it manufactures turnover in falling names.

---

## F8. Neutrality: which combination is identifiable and cheap [FIX · HIGH]

**Plan:** dollar aim + ε_net (`plan:39,206`), beta-zero target (`plan:160`), $|B_{style,t}^\top w|\le d$ (`plan:207`), §3 principle "Do not impose exact neutrality to all 147 signals… Limit interpretable nuisance exposures and quantify the price paid for each limit" (`plan:94`), signal-level sector+beta neutralisation inherited from repo practice ([fiam/book.py:175-179](/home/drewclaw/Forkfiam/fiam/book.py:175) `neutralize()` demeans score by sector then residualises on hedge beta *before* optimization, then `solve()` *also* constrains beta, sectors, and a volatility-complex `risk_rank` — double neutralisation worth auditing).

| Neutrality | Exposure known? | Constraints | Alpha cost | Verdict |
|---|---|---|---|---|
| Dollar $1^\top w=0$ | Exact | 1 linear | ~Zero (mandate centre) | **HARD equality** (ε_net=0 at formation; drift tolerance separate). Repo: `book.py:293`. |
| Sector $S^\top w=0$ (11 GICS) | Exact (dummies) | 10 independent given dollar ($\sum_s (S^\top w)_s=1^\top w$) | Low if Stage-1 quotas (F6); kills sector-timing the mandate doesn't reward | **HARD small tolerance** (e.g. ≤1% NAV/sector, repo uses 0.01, `book.py:54`). Cheapest true neutrality — zero estimation error. |
| Market beta $\hat\beta^\top w=0$ | Estimated (SE~0.2/name) | 1 linear (+F3 robustness reporting) | Moderate; high if signal is low-vol/beta-correlated (BAB warning, w16601) | **HARD nominal band ±0.02** on Vasicek beta (F3). This is the judged one (M2). |
| Size (log-me exposure) | Characteristic, near-exact | 1 linear band | **Mechanical tilt**: longs unrestricted (small), shorts ≥$500m (large) ⇒ unconstrained book is structurally long-SMB; Arcana lens 1 will call alpha "small-cap tilt" | **HARD band** centred 0 with width from factor vol (below). Plan never names this — add it; it is the highest-value style constraint in this mandate. |
| Value / momentum / profitability / investment | Characteristics | Bands | **These may BE the alpha** (§4 families); zeroing them zeroes the thesis (`plan:94`) | **MONITOR + wide bands only** (e.g. ±0.5 SD of feasible range), report as intended exposures with factor-attribution share. §6's uniform $|B'_{style}w|\le d$ contradicts §3 — tier it. |
| Volatility-complex (repo `risk_rank`: ivol+rvol+downside-β+BAB-β, `book.py:218-220,302`) | Mixed estimates | 1 linear | Repo's stated main finding: leaning from jumpy stocks = hidden short-market bet | KEEP as one bounded composite *or* replace by beta+size bands — don't stack all: collinear constraints eat feasibility without adding identification. Test E1 with/without. |

**Band units — the missing math in `plan:207`.** $d$ must be set in *risk* units, not raw exposure: factor $k$ contributes vol $\approx|(B^\top w)_k|\cdot\sigma_{F,k}$; a defensible default bounds each unintended factor's standalone vol contribution to ≤25% of target book vol: $d_k=0.25\,\sigma_{target}/\sigma_{F,k}$ (annualised consistently). Raw $d$ (e.g. 0.1 for every style) is meaningless across factors whose vols differ 5×.

**Identifiability note (F1.2 dependency):** with characteristic exposures, $B^\top w$ is *exactly* the book's weighted-average standardised characteristic — neutrality statements are verifiable by judges from holdings alone. With regression betas as exposures they are not. Another reason the F1.2 fix is load-bearing.

**Double neutralisation audit:** if the *signal* is already sector-demeaned and beta-residualised (repo `neutralize()`), portfolio-level equality constraints on the same exposures are nearly free (weights ∝ signal inherit neutrality approximately) — good — but with caps/costs/truncation they still bind at the margin; keep both layers, report constraint shadow prices to show the second layer's true cost rather than assuming either suffices.

### F8.3 Risk limit vs risk aversion — one knob, tied to the hurdle

$w^\top\Sigma_{ann}w\le\sigma_{max}^2$ (`plan:208`) + $\gamma$ in the objective are duals; keep the constraint form with $\sigma_{max}$ set from product logic: to clear cash+4% with IR≈0.5 needs active vol ≈8%; a market-neutral book at 200% gross with diversified specifics typically forecasts 6–12% — set $\sigma_{max}\in[8\%,12\%]$ pre-OOS and let implied $\gamma$ float (report it). Pure min-variance degeneracy (zero book) is already excluded by count+minimum (F6) — plan §13's rejection of pure min-var: **KEEP**. Vol-target *scaling* of gross to hit σ each week (Moreira–Muir style) is a separate policy needing its own counterfactual (`plan:449-450` correct) — not in v1.

---

## F9. Unimplementable-at-daily-frequency register (2-day budget)

| Item (plan) | Status | Reason |
|---|---|---|
| Daily refreshed trailing-regression exposures $B_t$ (`plan:154` read literally) | **UNIMPLEMENTABLE → F1.2 characteristic exposures** | ~4M regressions walk-forward; unstable loadings |
| Dense $U_\beta$, $U_\mu$ + SOC terms (`plan:163,185`) | **DROP v1 → F2 scalar/diagonal forms** | No estimator exists in plan; $N>T$ reintroduced |
| Power-cone sqrt-impact inside optimizer (`plan:196`) | **DROP → quadratic in optimizer, sqrt in ledger (F5.3)** | Solve time × backtest loops; uncalibrated κ |
| Exact MIP cardinality (considered & rejected by plan) | Correctly rejected | NP-hard; no integer solver guaranteed |
| Multi-period MPC / dynamic programming (`plan:241`) | Correctly deferred | Needs alpha-decay process + nested solves |
| EVT tails, multivariate GARCH, HAR-CJ (`plan:174`) | Correctly not required | No intraday inputs in dsf_mini (returns only, §11) |
| Daily alpha re-optimization on monthly signal | **DROP framing** | No daily forecast exists; daily = min-turnover risk repair only (F5.5). Weekly core review + monthly information (`plan:235-239`) is the implementable cadence — **KEEP** |
| Daily cross-sectional factor returns on ~3,000 names | Implementable with care | One WLS/day; needs daily returns × monthly exposures join on permno/date with no forward merge (§11 warning) + delisting handling — budget the data engineering, it's the critical path |
| Arcana/Barra replication internally | **DROP** | 120+ models (§11); reconcile ex-post instead (M5) |

Repo readiness summary: monthly analogues of the risk model (`risk.py`), specific vol (`vol.py` HAR frozen), QP with dollar/beta/sector constraints (`book.py solve()`), and cost ledger (`costs.py`) all exist and are coherent. The finals gap is *frequency + scale*: daily factor-return estimation, $1bn compounding NAV in every cost/capacity formula (currently $10m hard-coded — Stream 1 CRITICAL), turnover/cost terms inside `solve()`, Vasicek daily beta, and finals hard bounds (200-name floor, 5% cap, $500m short bound). Plan §§5–6 describe that target well; with F1–F8 simplifications it is a 2-day build. Without them it is a conic-programming research project.

---

## Consolidated verdicts

| # | Plan element | Verdict | Severity if unfixed |
|---|---|---|---|
| F1.1 | Factor $BFB^\top+D$ over sample/shrinkage covariance | KEEP (+LW inside $F$, floor $D$) | — |
| F1.2 | Trailing-regression exposures | FIX → characteristic exposures + daily X-sectional factor returns | HIGH |
| F1.3 | EWMA 20–60d, 252d windows | FIX → factor 42/84d, specific 84/168d, bias-stat selection, horizon scaling formula | MEDIUM |
| F2 | $U_\beta$/$U_\mu$ SOC robustness | DROP dense forms → scalar $\sqrt{w^\top\Sigma_e w/S_{xx}}$, diagonal $u_i$ | CRITICAL (unestimable) |
| F3 | β band ±0.02 robust; beta definition | FIX → nominal ±0.02 hard on Vasicek contemporaneous β; robust ≈0.08–0.10 reported; Dimson diagnostic | CRITICAL (infeasible / wrong object) |
| F4 | Stress list, joint blocks | KEEP + FIX loss budgets as constraints, pre-2021 calibration, crowded-short overlay | MEDIUM |
| F5.1 | GP citation for L1 controller | FIX attribution; band width $=s_i$ from subgradient | HIGH (credibility) |
| F5.2 | $(\gamma,\rho,\eta,\kappa)$ all free | FIX → σ_max + 1 cost scalar in v1 | HIGH (validation overfit) |
| F5.3 | Sqrt-impact in optimizer | FIX → quadratic optimizer / sqrt ledger, shared $s_i$ | MEDIUM |
| F5.5/F9 | Daily full re-solves | FIX → weekly solve, daily min-turnover repair only | HIGH (turnover) |
| F6 | Two-stage support, no MIP, no padding | KEEP + FIX greedy risk-adjusted selection, hedge-sign decision | HIGH (feasibility) |
| F7 | Hard-first hierarchy, breach honesty | KEEP + FIX slack-encoded solver ladder, at-formation short bound | MEDIUM |
| F8 | Uniform style neutrality $|B'w|\le d$ | FIX → tiered: dollar+sector+β+size hard, alpha-styles monitored; bands in vol units | HIGH (alpha destruction / missed SMB tilt) |

**Unresolved evidence:** dsf_mini schema/ADV availability (returns-only per §11 — ADV must come from CA0065S/Arcana, units unverified in this stream); whether Gurobi/commercial MIP exists in event environment (assumed no); Arcana factor definitions for reconciliation; actual beta-SE/feasibility numbers require the daily panel (F3.1 arithmetic uses literature-typical σ_e, σ_m — rerun on data Day 1); no plan performance claim was or could be tested here.



