# Stream 2 — Forecasting Science Evaluation
## Taildrop plan §§3–4 (and §§9, 12–13 where they govern forecasting) vs. FINAL mandate

**Workspace:** `/home/drewclaw/Forkfiam` · **Plan:** `fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md` (484 lines, read in full) · **Mandate:** `fiam/v4b/inputs/final_mandate.txt` (read §§1–9; forecasting-relevant §§3, 4, 5.2, 7, 8.1, 11 in full) · **Source pack:** `fiam/v4b/inputs/source_pack/sources/manifest.json` + `.txt` bodies opened (see §0). Past repo work treated as evidence only.

**Verdict key:** KEEP = correct as written · FIX = right direction, materially incomplete/wrong in detail · DROP = remove or demote to research-only. **Severity:** CRITICAL = will mislead OOS IR / breach mandate if implemented as written · HIGH = likely large OOS degradation · MEDIUM = meaningful drag or judge exposure · LOW = polish.

**Top line:** The plan's *architecture* — one pooled forecaster, monthly information, weekly review, daily risk-only, cost-aware construction — is the correct answer to Mandate §4. Its *forecasting science* is under-specified at exactly the points that decide whether the backtest is honest: (1) "hierarchical ridge" conflates three different shrinkage objects (JKP factor-alpha pooling, KNS SDF/PC shrinkage, stock-level predictive ridge) without the math that distinguishes them; (2) no effective-sample-size / effective-df accounting, so the 2015–2020 training window is treated as far larger than it is; (3) the horizon-mismatch problem is named but never quantified — no decay parameter, no Garleanu–Pedersen trading-rate implication, no multi-horizon target; (4) multiple-testing control stops at "log everything" with no numeric hurdle (no HLZ t>3, no deflated Sharpe, no FDR). None of these requires a different strategy. All four require fixes before any OOS number can be trusted.

---

## 0. Sources actually opened (evidence base)

| Manifest file | Identity (verified from `.txt` title pages) | Use in this stream |
|---|---|---|
| `w28432.txt` | Jensen–Kelly–Pedersen, *Is There a Replication Crisis in Finance?* NBER w28432 (Feb 2021) | §3 audit: 153 factors / 93 countries / 13 themes / 84.9% |
| `w25398.txt` | Gu–Kelly–Xiu, *Empirical Asset Pricing via Machine Learning* NBER w25398 (rev. Sep 2019) | Ridge vs ENet vs trees/NN; R² magnitudes; split design |
| `w24070.txt` | Kozak–Nagel–Santosh, *Shrinking the Cross Section* NBER w24070 (Nov 2017) | SDF shrinkage, PC-sparsity, η=2 prior, dual penalty |
| `w20592.txt` | Harvey–Liu–Zhu, *…and the Cross-Section of Expected Returns* NBER w20592 (Oct 2014) | Multiple-testing hurdle t>3.0 |
| `w23394.txt` | Hou–Xue–Zhang, *Replicating Anomalies* NBER w23394 (May 2017) | Microcap/breakpoint fragility; 64–85% insignificant |
| `taming_factor_zoo.txt` | Feng–Giglio–Xiu, *Taming the Factor Zoo*, J. Finance LXXV(3), Jun 2020 | Double-selection LASSO; post-selection inference |
| `w15205.txt` | Garleanu–Pedersen, *Dynamic Trading with Predictable Returns and Transaction Costs* NBER w15205 (Aug 2009) | Aim portfolio, alpha decay, partial adjustment |
| `w27843.txt` | van Binsbergen–Han–Lopez-Lira, *Man vs. Machine Learning* NBER w27843 (rev. Aug 2021) | Earnings-bias feature audit |
| `w16601.txt`, `w22208.txt` | Frazzini–Pedersen BAB; Moreira–Muir vol-managed | Risk-layer context only (Stream 3 owns) |

Web verification (6 searches; 1 full fetch succeeded, 1 blocked — see §10): GKX criticisms/microcaps, short-term reversal net magnitudes, IPCA vs Fama–MacBeth, deflated Sharpe (Bailey & López de Prado 2014), PEAD magnitudes/decline, purged CV/embargo. URLs fetched are listed in §10; search-result snippets are labelled as such and never cited as primary evidence where the source-pack body was available.

---

## 1. Mandate constraints that bind the forecaster (what "correct" means)

1. **Forecast returns or fundamentals, strictly OOS** — Mandate §3 (`final_mandate.txt:101-103`): "to forecast returns or firms' fundamentals and to construct a portfolio from those forecasts. Report performance strictly out of sample." OOS window 01/2021–08/2026 (`:129`), i.e. **68 monthly observations** — the plan correctly flags this (`plan:311`).
2. **Daily is permitted, not required; daily alpha must earn its costs** — Mandate §4 (`:214-253`). Decisive lines: "Daily cross-sectional return dispersion is dominated by microstructure and liquidity, not by fundamentals. A model trained to predict tomorrow's return is largely being trained to predict noise. Think about whether your signal has a daily horizon at all" (`:241-243`); "A defensible answer is a weekly or monthly core book with a daily overlay for events" (`:249-251`); "'We tested daily rebalancing, it did not survive costs, and here is the evidence' is a strong finding" (`:251-252`). Turnover at 10%/day ⇒ >2,500% p.a. one-way (`:234-235`).
3. **Delayed-execution clock** — Mandate §7 (`:700-703`): information through day *t* forms the book at close *t+1*; first earned return is close *t+1* → close *t+2*. Any feature using day-*t* return has already "spent" that return (`:704-708`). The plan adopts this correctly (`plan:271`).
4. **Leakage catalogue for forecasting** — Mandate §7: full-sample feature selection on 147 characteristics 2015–2026 (`:687-690`), full-sample standardisation/winsorisation (`:724-726`), hyperparameters tuned on test (`:727-730`) are all disqualifying-grade leaks. §8.1 walk-forward default: train 2015–2018 / validate 2019–2020 / first OOS 2021, then roll (`:824-826`).
5. **Multiple-testing denominator is mandatory** — Mandate §5.2 (`:353-360`): "state how many hypotheses you tested, in total, not how many you kept; hold out a slice…; require an economic rationale written down before the test." A team showing "four features and no denominator… we will ask for the denominator."
6. **Alpha decay is a required exhibit** — Mandate §11 (`:1105-1107`): "How quickly the edge in your signal dissipates after formation… if your alpha decays over three days, a monthly book is leaving most of it on the table; if it decays over two months, daily trading is paying costs for nothing." The plan lists "signal decay at prespecified horizons" (`plan:361`) but gives no estimator (see Finding F6).
7. **Short leg ≥ $500m at formation; 200–500 names; $1bn compounding** (`:114-125`). Any forecaster whose edge lives in microcap shorts is forecasting an untradable object (see Finding F8).

**Implication:** the forecaster is judged on *net, factor-adjusted, capacity-feasible* OOS IR with an honest denominator — not on gross rank IC or pooled R². Every finding below is scored against that standard.

---

## 2. Finding F1 — "Pooled hierarchical ridge" conflates three distinct shrinkage problems [FIX · HIGH]

**Plan:** §3 `plan:59-65` (three applications of JKP logic) + §4 `plan:98-110`:

$$\widehat\mu_{i,t}^{(H)}=x_{i,t}^{\top}\theta,\qquad \min_\theta \sum_t\frac{1}{N_t}\sum_i (y_{i,t}^{(H)}-x_{i,t}^{\top}\theta)^2+\sum_g\lambda_g\|\theta_g\|_2^2 .$$

The plan is admirably explicit that this is an *adaptation*, not JKP: "Do not call a ridge regression or a risk optimizer an exact implementation of JKP's hierarchical factor-alpha model" (`plan:65`), and "$P$ is not the covariance of stock returns… use $APA'$" (`plan:86`). That caution is **KEEP**. The problem is that the three objects being adapted have *different* statistically correct penalties, and the plan's single family-wise $\lambda_g$ matches none of them exactly:

| Object | What is shrunk | Correct penalty structure | Plan's $\sum_g\lambda_g\|\theta_g\|^2$ matches? |
|---|---|---|---|
| **(a) JKP factor-alpha pooling** (`w28432.txt:665-668`, "common component + idiosyncratic") | Factor *alphas* $\alpha$ toward theme means and zero: $\alpha\sim N(0,\Omega)$, $\Omega=\tau_c^2MM^\top+\tau_w^2I$ (`plan:73-75`) | Posterior $\bar\alpha=\Omega(\Omega+V)^{-1}a$ requires full sampling covariance $V$ incl. cross-factor dependence (`plan:84` correct) | No — predictive ridge on stock returns does not estimate $\Omega$ or $V$ |
| **(b) KNS SDF shrinkage** (`w24070.txt` eqs. 18–26) | SDF loadings $b=\Sigma^{-1}\mu$; prior $\mu\sim N(0,\frac{\kappa^2}{\tau}\Sigma^{\eta})$ with $\eta=2$ | $\hat b=(\Sigma+\gamma I)^{-1}\bar\mu$; PC-wise shrinkage $d_j/(d_j+\gamma)$ — *eigenvalue-dependent*, heaviest on low-variance PCs (`w24070.txt`, §3.1.1) | No — flat per-family $\lambda_g$ shrinks high- and low-variance directions equally within a family |
| **(c) Stock-level predictive ridge** (GKX $\rho=1$ special case of elastic net, `w25398.txt:557-563`) | Predictive coefficients $\theta$ for $E[r_{i,t+1}\mid x_{i,t}]$ | Penalty chosen to maximise *OOS predictive* loss under time dependence (see F3) | Partially — but only if $\lambda_g$ selection respects time-series dependence, which the plan does not specify |

**Why this matters mathematically.** KNS prove (not assume) that $\eta\le 1$ priors are economically implausible: with $\eta=0$ the prior Sharpe of low-eigenvalue PCs explodes (near-arbitrage); with $\eta=1$ (Pástor–Stambaugh) all PCs get equal prior Sharpe; bounded $E[b^\top b]=\frac{\kappa^2}{\tau}\sum_i d_i^{\eta-2}$ requires $\eta\ge 2$ (eq. 21). Their estimator therefore shrinks *directions*, not *variables*. A family-wise ridge on raw characteristics does the opposite: two nearly-collinear value proxies in the same family span one high-variance PC and one near-zero-variance PC (their difference); flat $\lambda_g$ leaves the near-arbitrage difference direction under-shrunk — precisely the direction that overfits. JKP's hierarchy has the same flavour: shrinkage $\kappa$ depends on $T$ and $\tau$ jointly ("The more data we have (higher $T$), the less shrinkage… the stronger the prior of zero alpha (lower $\tau$), the heavier the shrinkage", `w28432.txt:508-509`), and global shrinkage tightens with cross-market correlation (`:629-632`). Neither is a per-family constant.

**Correct alternative (implementable in two days):**
1. Keep the pooled predictive ridge as the *baseline* — it is the right default (see F2) — but rename it honestly: "group-ridge predictive regression," not "hierarchical" in the JKP sense. Reserve "JKP replication" for the separate research exercise in `plan:67-84`, which is correctly specified.
2. Add the KNS-faithful challenger the plan omits: form characteristic-sorted factor returns $F_t=Z_{t-1}'R_t$ (KNS eq. 4), orthogonalise to market, PCA-rotate, and estimate $\hat b=(\Sigma+\gamma I)^{-1}\bar\mu$ with $\gamma$ by time-series CV. This is a *pricing* (max-Sharpe) object, not a stock forecaster — compare it as a factor-timing/combination benchmark, exactly as `plan:432` hints ("an SDF is not itself our stock-level portfolio policy" — correct, **KEEP** that sentence).
3. If family pooling is wanted, implement it as empirical Bayes on $\theta$: $\theta_g\sim N(0,\tau_g^2 I)$ with $\tau_g^2$ by marginal likelihood on training folds only, giving $\lambda_g=\hat\sigma^2/\hat\tau_g^2$. Report $\hat\tau_g$ per family — judges can then see *which* families the data actually support. A grid over independent $\lambda_g$ per family with ~10 families is a 10-dimensional hyperparameter search on ~24 validation months (see F3/F7) and will overfit the validation set itself.

**Severity HIGH, not CRITICAL:** the plan's honesty caveats (`plan:65,86`) prevent the worst error (inserting $P$ as $\Sigma$). But as written, an implementer will tune $\{\lambda_g\}$ by pooled CV and believe they have "done JKP/KNS shrinkage." They have not.

---

## 3. Finding F2 — Ridge vs. the alternatives: the ranking is right, the evidence cited is incomplete [FIX · MEDIUM]

**Plan:** Default ridge (`plan:98-114`), challenger shallow GBM (`plan:116-120`), alternatives table §13 (`plan:452-469`), lit table §12A–B (`plan:414-436`).

### 3.1 What GKX actually found (source-pack verification)

From `w25398.txt` Table 1 and text (monthly stock-level OOS $R^2$, 1987–2016, 94 characteristics → 920 with interactions/macro, `:1222`; splits 1957–74 / 1975–86 / 1987–2016, `:1243-1247`):

- OLS-920: $R^2_{oos}=-3.46\%$ ("predictability vanishes immediately", `:220-224`) — unregularised high-dimensional regression is catastrophic. **Supports plan's shrinkage default.**
- Elastic net: $0.11\%$; PCR $0.26\%$; PLS $0.27\%$; OLS-3 (size/BM/momentum only) $0.16\%$.
- Random forest $0.33\%$, GBRT $0.34\%$, NN3 $0.40\%$ — trees/NN "unambiguously improve" (`:239-240`), gains traced to *interactions*, not univariate nonlinearity (`:242-245`); shallow beats deep (`:246-249`).
- Long–short decile Sharpe: NN 1.35 value-weighted / 2.45 equal-weighted vs. linear 0.61 / 0.83 (`:277-280`) — **gross, pre-cost, pre-capacity, 30-year OOS**.

The plan's use of GKX (`plan:415`: "Test a small tree challenger; their sample and gross portfolio results do not establish our capacity or expected IR") is exactly right — **KEEP**. Two gaps:

**(a) Elastic net is demoted on insufficient evidence.** Plan §12A calls elastic net "a reasonable ridge challenger… selection stability must be measured" (`plan:420`) but §4 never schedules it — only ridge vs. GBM. Yet GKX's own horse race has ENet ($0.11\%$) *below* PCR/PLS and OLS-3 at stock level, while KNS's dual-penalty (L1+L2, "similar to the elastic net", `w24070.txt:150-152`) finds the SDF is **not** characteristics-sparse: "restricting the SDF to just a few characteristics-based factors does not adequately capture the cross-section" (`:170-171`), whereas a *PC-sparse* SDF does (`:174-181`). The correct inference — which the plan should state — is: **dense shrinkage (ridge/PCR) dominates sparse selection (lasso) for this problem; elastic net's L1 component buys interpretability, not OOS accuracy, and its selection is unstable under the collinearity that defines the 147-characteristic panel.** Verdict: keep ridge as default, keep ENet as a *diagnostic* (which variables survive?), do not promote on ENet sparsity alone. The plan's lasso note ("coefficient sparsity does not enforce 200 meaningful portfolio positions", `plan:419`) is sharp and correct — **KEEP**.

**(b) IPCA dismissal is too quick for a two-day event, but the reasoning should be statistical, not logistical.** Plan §13: IPCA "worth a controlled extension, not a prerequisite within two days" (`plan:460`); §12B: "latent factors require external attribution and do not automatically give neutrality" (`plan:436`). Both true. But the *decisive* argument is missing: IPCA (Kelly–Pruitt–Su 2019) estimates loadings $\beta_{i,t}=\Gamma' z_{i,t}$ and latent factors jointly by alternating least squares; with $K=L$ it *equals* Fama–MacBeth, with $K<L$ it is a reduced-rank constraint on Fama–MacBeth (verified via web search §10, result 3: "when $K<L$, IPCA's $f_{t+1}$ estimate is a constrained Fama-MacBeth regression coefficient"). IPCA answers "are characteristics covariances (risk) or characteristics (mispricing)?" — a *pricing* question. The mandate asks for a *tradable forecast* under neutrality/capacity constraints. IPCA's latent factors are unlabelled rotations; enforcing beta/sector neutrality on them requires a second attribution step the plan correctly fears. **Verdict: DROP IPCA as forecaster; KEEP as optional attribution diagnostic** (does the ridge forecast load on 3–5 latent factors or is it diffuse?). State the Fama–MacBeth equivalence so judges see this was a considered statistical choice, not time pressure.

**(c) Characteristic-sorted factor premia vs. stock-level prediction — the plan wants both but never reconciles them.** §3 research replication builds tercile portfolios (`plan:69`); §4 forecasts stock returns. These estimate different objects: factor premia $E[F]$ (time-series means, $T\approx 72$ pre-2021 monthly obs.) vs. conditional stock means $E[r_i\mid x_i]$ (pooled panel). With $T=72$, the standard error on a factor premium with 3%/month vol is $3/\sqrt{72}\approx 0.35\%$/month — larger than most premia being estimated. Stock-level pooling does not repeal this: cross-sectional $N$ reduces *idiosyncratic* noise, not the common time-series noise in premia (see F3). **Fix:** present the factor replication as a *prior-elicitation* device (which families have non-trivial premia at all?) feeding $\hat\tau_g$ in F1, not as a parallel return forecast. The plan's factor-vs-selection comparison (`plan:94`: "Report how much return survives market, sector and style attribution") is the right judge-facing exhibit — **KEEP**, and pre-specify that the tradable claim is the *residual*, not the factor combination.

### 3.2 Trees/NN: challenger design is sound; add two guardrails

Plan `plan:118-120` (same folds/optimizer, calibrated magnitudes, promotion on net IR not MSE) — **KEEP in full**. Add:
- **Interaction budget:** GKX gains come from interactions among a *small* set of dominant predictors (momentum, liquidity, volatility families). With 147 characteristics and ~72 training months, an unconstrained GBM will find interactions that are validation-set artefacts. Cap depth ≤3, min-child large, monotonicity where economics dictates sign, and report SHAP/interaction stability across folds. Unstable interactions = no promotion, regardless of pooled IC.
- **No NN in the two-day window.** GKX NN3 ($0.40\%$) vs GBRT ($0.34\%$) gap is small, bought with far larger tuning surface (architecture, dropout, early stopping — all validation-consuming). The plan does not propose an NN — correct. Say so explicitly in §13 (currently NNs appear only via "Transformers", `plan:466`, which is a different — and correctly rejected — idea).

---

## 4. Finding F3 — Effective sample size, effective df, and CV under dependence are unspecified [FIX · CRITICAL]

**Plan:** Date-balanced loss (`plan:110`: "prevents dense recent cross-sections from dominating"), "hundreds of thousands of stock-months are [not] independent time observations" (`plan:110`), walk-forward with purge (`plan:305`), "random stock-row splits are invalid" (`plan:307`), block bootstrap (`plan:311`). All directionally correct — and none quantified. This is the single most important forecasting gap, because every hyperparameter ($\lambda_g$, tree depth, feature admission) will be chosen against a validation criterion whose noise the plan never sizes.

### 4.1 The arithmetic the plan must show

Pre-OOS training per Mandate §8.1 / plan §9: 2015–2018 train (48 months) + 2019–2020 validate (24 months); expanding thereafter. With $N_t\approx 3{,}000$–$4{,}000$ stocks/month, pooled rows $\approx 250$k. But for estimating a *common* $\theta$, the binding dimension is $T$, not $NT$: stock returns share factor shocks, so cross-sectional averaging diversifies idiosyncratic variance ($\sim\sigma_e^2/N$) but not factor-realisation variance. Effective time-series sample for premia-like parameters is $T_{\text{eff}}\approx 48$–$72$, further reduced by (i) overlapping $H$-day labels if daily targets are built (overlap factor $\approx H$; 21-day overlapping labels on daily formations give $T_{\text{eff}}\approx T_{\text{daily}}/21$), and (ii) characteristic persistence (slow-moving accounting variables change quarterly at best).

Ridge effective degrees of freedom: $\text{df}(\lambda)=\sum_j \frac{d_j^2}{d_j^2+\lambda}$ over singular values $d_j$ of the (date-balanced) design. With $p=147$ (+ sector dummies + missingness indicators, `plan:110`), an implementer must report $\text{df}(\hat\lambda)$ *and* the ratio $\text{df}/T_{\text{eff}}$. If $\text{df}\approx 30$ against $T_{\text{eff}}\approx 60$, the model is far less "pooled-safe" than 250k rows suggest. GKX had 60 years ($T=720$) and still got $R^2_{oos}=-3.46\%$ unregularised; this project has one-tenth the time span. **The plan must pre-commit a df budget** (e.g. $\text{df}\le T_{\text{train}}/5$) as a sanity gate alongside validation loss.

### 4.2 CV choice: "chronological validation" is necessary, not sufficient

The plan says "same chronological validation periods" (`plan:11`) and purge boundary-crossing labels (`plan:305`) — **KEEP**. Missing:

1. **No random K-fold anywhere in the pipeline** — including inside `sklearn` defaults for ridge/GBM tuning, feature scaling, or early stopping. GKX state it plainly: "we do not use cross-validation in order to maintain the temporal ordering" (`w25398.txt:1261`), using a single expanding train/validation split with annual refits. For this project the analogue is *nested* walk-forward: inner folds (expanding, purged) choose $\lambda$; outer fold (next year) is never touched by tuning. López de Prado's purged K-fold + embargo (web search §10, result 6) formalises the same idea for overlapping labels: purge training rows whose label windows overlap the test window, embargo $\approx$1% of $T$ after each test block. Plan's "purge observations whose target horizons cross a split boundary" (`plan:305`) is the purge half; add the embargo half (features with lookbacks — e.g. 12-month momentum — leak across the boundary in the other direction).
2. **Tuning objective must match the tradable object.** Pooled MSE weights every stock-month equally (date-balanced); the portfolio holds 200–500 names with capacity constraints. A $\lambda$ minimising pooled MSE can maximise weight on microcap predictability the fund cannot harvest (see F8). Tune (or at least *select* among near-optimal $\lambda$) on validation *net portfolio* IR through the actual constructor — the plan requires this for ridge-vs-GBM promotion (`plan:120`) but not for $\lambda$ itself. Extend it.
3. **One-standard-error rule under dependence.** With 24 validation months, the SE of a validation IC difference is large. Prefer the most-regularised $\lambda$ within 1 block-bootstrap SE of the optimum. Without this, $\hat\lambda$ chases validation noise — a second-order overfit that walk-forward alone does not cure.
4. **Refit hygiene.** Plan `plan:305` ("after choosing settings, refit on eligible labeled observations through $Y-1$ if declared in advance… All labels must have matured before a refit") — **KEEP verbatim**. Add: hyperparameters frozen at validation choice; refitting $\lambda$ on train+validation pooled without a fresh inner split silently reintroduces selection bias.

**Severity CRITICAL:** an implementer following the plan literally can still run shuffled 5-fold CV inside the ridge solver, report a beautiful validation $R^2$, and fail Mandate §7 (`:727-730`, hyperparameters tuned on test / leakage) without any single line of code looking wrong. The fix is specification, not research: nested purged walk-forward, embargo, df budget, portfolio-level selection, 1-SE rule. Budget half a day; it protects everything else.

---

## 5. Finding F4 — Residual (orthogonalised) targets: correctly hedged, but the error-in-variables cost is understated [FIX · MEDIUM]

**Plan:** §4 `plan:122-130`: $y^{res}_{i,t}=R^{e}_{i,t:t+H}-\widehat B_{i,t}^{\top}F_{t:t+H}$, "noisy exposure estimates can corrupt the target… Do not assume residual targets must win." **KEEP the hedge.** The plan understates *how* the corruption works and omits the cleaner alternative:

- **Generated-regressor / attenuation mechanics.** $\widehat B_{i,t}$ is estimated (e.g. 252-day trailing regression, cf. `plan:154`). Then $y^{res}= \underbrace{(B_{i,t}-\widehat B_{i,t})^{\top}F}_{\text{label noise }\propto\text{ factor vol}} + e_i$. In high-vol months $\|F\|$ is large, so label noise is heteroskedastic and *correlated across stocks sharing estimation error* (same lookback window). Ridge trained on $y^{res}$ partially learns to predict beta-estimation error, not alpha. Worse, if $\widehat B$ uses characteristics correlated with $x_{i,t}$ (size, value loadings vs. size/value features), residualisation *removes* part of the signal being forecast — the plan notes the dual risk for neutrality (`plan:94`: "Do not impose exact neutrality to all 147 signals: that can mechanically remove the information being forecast") but does not connect it to the target choice. Connect it: residual target + factor-constrained construction = double subtraction.
- **What the literature supports.** KNS orthogonalise *factors* to market before SDF estimation (`w24070.txt`, §2.1: "we orthogonalize the characteristics-based factors with respect to the market factor") — a factor-level operation with $T$-observation precision, not a stock-level label operation with $N\times K$ noisy betas. FGX's lesson cuts the other way for *testing*: naive orthogonalisation-then-test invalidates inference (omitted-variable bias from selection mistakes, `taming_factor_zoo.txt:13-15, 91-99`); double-selection exists precisely because single-pass residualisation lies. For *prediction* the stakes are lower than for inference, but the plan should not present residual targets as a neutral 50/50 experiment.
- **Correct alternative (test in this order):** (1) raw excess-return target + factor constraints at construction (plan's own comparator — make it the default); (2) *cross-sectionally demeaned / sector-demeaned* target (removes factor *means* without stock-level beta noise; matches the "within comparable sector and risk groups" hypothesis, `plan:15`); (3) full residual target only if (2) shows factor-timing contamination in validation attribution. Report all three on identical folds; promote on net IR. Also: $F_{t:t+H}$ in training labels is legitimate post-horizon (plan `plan:130` correct) but the *deployed* forecast must add back nothing — ensure the optimizer does not interpret a residual forecast as a total-return forecast when sizing against $\Sigma_{t,H}$ (units mismatch; cf. `plan:190` horizon-alignment warning).

**Severity MEDIUM:** the plan already refuses to assume victory; the fix is ordering + the sector-demeaned middle option + explicit double-subtraction warning.

---

## 6. Finding F5 + F6 — Horizon mismatch is named but never mathematised [FIX · CRITICAL]

**Plan:** Monthly target `ret_exc_lead1m`, "~21-trading-day horizon… not a forecast of tomorrow's return" (`plan:112-114`); "Monthly signals can be carried forward with age/staleness information" (`plan:114`); weekly review + no-trade regions (`plan:235-239`); Garleanu–Pedersen cited for "gradual, cost-aware rebalancing" (`plan:13`) and decay tests (`plan:447`). **KEEP the schedule** (monthly info / weekly review / daily risk-only is the right answer to Mandate §4). But the plan contains **no decay parameter, no half-life estimator, and no mapping from a 21-day forecast to a 5-day holding decision.** As written, the weekly controller re-trades on a forecast whose remaining alpha it has not computed. That is the instability the mandate warns about: a monthly-trained signal *re-ranked* weekly/daily churns on rank noise while its true alpha decays slowly.

### 6.1 The math the plan must include

Let the signal imply instantaneous expected return decaying exponentially after formation: $\mu_i(s)=\mu_i(0)\,e^{-\kappa s}$ (GP's mean-reverting predictor; `w15205.txt:82-85, 131-133`: "predictors with slower mean reversion (alpha decay) get more weight… trade more aggressively on persistent signals"). Cumulative alpha over holding horizon $H$: $A_i(H)=\mu_i(0)\frac{1-e^{-\kappa H}}{\kappa}$. A model trained on $H_{tr}=21$d estimates $A_i(21)$, *not* $\mu_i(0)$. Recovering the tradeable remainder at age $a$ days with $H_{hold}$ days to next review:

$$\widehat A_i(a,H_{hold}) = \widehat A_i(21)\cdot \frac{e^{-\kappa a}(1-e^{-\kappa H_{hold}})}{1-e^{-21\kappa}}.$$

Half-life $h=\ln 2/\kappa$. Consequences the plan should tabulate for judges:

| True half-life $h$ | $\kappa$ (/day) | Share of 21d alpha in first 5d | Share remaining at day 10 | Weekly re-trade verdict |
|---|---|---|---|---|
| 3 days (event/PEAD-fast, STR) | 0.231 | 69% | 10% | Monthly book forfeits most alpha; daily/event overlay justified *if* net of costs |
| 15 days | 0.046 | 26% | 63% | Weekly review captures decay efficiently; daily adds little |
| 60 days (slow fundamentals) | 0.012 | 22%* | 89% | Weekly ≈ monthly gross; weekly wins only on risk control, loses on costs |

*For $h=60$d the 21d window itself truncates the alpha; training horizon should lengthen, not trading frequency rise.

**Garleanu–Pedersen implication (cite it properly or drop the citation).** GP Props. 2–3 (`w15205.txt:367-419`): optimal $x_t=(1-\theta)x_{t-1}+\theta\,\bar x_t$ where aim $\bar x_t$ is an exponentially-weighted average of current and *expected future* Markowitz portfolios ("aim in front of the target"), with trading rate $\theta$ decreasing in costs and aim-weights increasing in signal persistence. The plan's one-period controller (`plan:241` honestly labelled "not an exact dynamic-programming solution" — **KEEP**) corresponds to $\theta=1$ toward a myopic target each week. With proportional + impact costs (`plan:192-199`) that over-trades fast-decaying components and under-weights slow ones relative to GP. **Minimal fix without full MPC:** decompose the forecast into slow/fast sleeves by estimated $\kappa$ (or by feature-family half-life) and set GP's two distinct knobs separately: (i) *aim size* — persistent signals get larger aim weights because their alpha amortises the entry cost over many periods; fast signals get smaller aims; (ii) *trading speed* — fast sleeves, if traded at all, must be entered promptly with a hard expiry (alpha gone in days), while slow sleeves are approached gradually (e.g. close $\approx$1/3 of the gap to aim per week, $\theta\approx0.3$). Conflating (i) and (ii) into a single "trade aggressively on X" rule is the common implementation error; the plan should state both knobs explicitly. Hysteresis bands (`plan:213,237`) approximate the no-trade region under proportional costs — **KEEP**, but calibrate band width to $s_i$ (spread) per name, not a global rank buffer.

### 6.2 Estimation protocol (pre-register it)

1. **IC decay curve:** on validation only, compute rank IC of formation-date forecast against non-overlapping forward returns at horizons 1, 2, 3, 5, 10, 21, 42, 63 days (all respecting the $t\to t{+}1$ execution lag, Mandate §7). Fit $\text{IC}(h)=\text{IC}_0 e^{-\kappa h}$ (+ constant for slow premia) by nonlinear LS with block-bootstrap CI on $\hat\kappa$. This *is* the Mandate §11 alpha-decay exhibit (`:1105-1107`).
2. **Multi-horizon targets:** train *separate* heads (or separate ridge fits) for $H\in\{5,21\}$ on identical features. If $\hat\mu^{(5)}/\hat\mu^{(21)}$ ratios are unstable across folds, the daily/weekly trade has no forecast — only the monthly one does. Do **not** rescale $\hat\mu^{(21)}/21$ into a "daily alpha" (assumes $\kappa=0$ within month; false for any event/momentum component).
3. **Staleness as feature, not fudge:** "age/staleness information" (`plan:114`) must enter as forecast *decay* $e^{-\hat\kappa a}$ multiplying $\hat\mu$, with $\hat\kappa$ from step 1 — not as an extra regressor the ridge can use to memorise calendar effects. And never copy monthly rows to daily frequency for training (plan `plan:114` prohibits counting them independent — **KEEP**; strengthen to prohibit the construction entirely for the daily head: daily heads need daily-formed labels with overlap-aware weights, López de Prado uniqueness weighting $\propto 1/\text{concurrency}$).

**Severity CRITICAL:** without $\hat\kappa$, the weekly-vs-monthly comparison (E4, `plan:321`) cannot distinguish "weekly adds alpha" from "weekly re-trades the same alpha at 4× cost." Judges are instructed to ask exactly this (Mandate §4 `:237`, §11 `:1105-1107`).

---

## 7. Finding F7 — Multiple testing: denominator logged, but no hurdle, no deflation [FIX · HIGH]

**Plan:** §9 `plan:309-311` (researcher contamination disclosed; log every variant; "Bayesian shrinkage does not erase selection bias"; block bootstrap; "dependence-aware multiple-testing procedure where applicable"); E0–E6 ladder (`plan:313-325`); §12B HLZ row (`plan:430`: "a t-statistic around 2 is not a universal discovery threshold"). The *attitude* is exemplary and matches Mandate §5.2 (`:353-360`) — **KEEP** the contamination disclosure (`plan:309`: "Label it a historically walk-forward evaluation with prior researcher exposure") verbatim; it is the strongest paragraph in §§3–4's neighbourhood. What is missing is every number.

### 7.1 What the source pack requires

- **HLZ hurdle.** Harvey–Liu–Zhu: given the history of factor searches, "a t-ratio greater than 3.0" is the appropriate hurdle for a *new* factor claim (`w20592.txt:54-60`), via Bonferroni / Holm (FWER) or Benjamini–Hochberg–Yekutieli (FDR) adjustments. Plan `plan:430` gestures at this without adopting it. **Adopt it explicitly:** any *new* feature family (event, alt-data, text) must clear $|t|>3$ on validation (Newey–West / block-bootstrap $t$, not pooled-row $t$) *or* survive BHY at FDR 5% across the full tested set. Incumbent 147 characteristics are not "new discoveries" — but any *selection* among them (families kept/dropped on validation performance) re-enters multiple-testing territory. FGX double-selection (`taming_factor_zoo.txt:91-99,158-165`) is the correct inferential technology for "does feature $g$ add beyond the other 146?"; at minimum cite it as the reason post-selection $t$-stats from a single LASSO/GBM importance ranking will not be reported as evidence (Mandate §7 `:687-690` already bans full-sample importance screening — plan should ban validation-importance $t$-stats too).
- **Deflated Sharpe Ratio (Bailey & López de Prado 2014) — absent from the plan entirely.** With $M$ trials (E-ladder variants × hyperparameter configs × feature families — easily $M=50$–$500$ once agent-proposed features enter, cf. Mandate §5.2 "four hundred candidate features"), the expected maximum Sharpe under the null grows as $O(\sqrt{\ln M})$: $\widehat{SR}_0 \approx \sqrt{V[\widehat{SR}]}\left[(1-\gamma)\Phi^{-1}(1-1/M)+\gamma\Phi^{-1}(1-1/(Me))\right]$, and $\text{DSR}=\Phi\!\left(\frac{(\widehat{SR}-\widehat{SR}_0)\sqrt{T-1}}{\sqrt{1-\hat\gamma_3\widehat{SR}+\frac{\hat\gamma_4-1}{4}\widehat{SR}^2}}\right)$ (formula verified via web search §10, result 4). Worked warning for the deck: with $T=68$ OOS months and $M=100$ effectively-independent trials, $\widehat{SR}_0$ (monthly input, annualised output) is roughly 0.8–1.0 — i.e. a headline annualised Sharpe below ~1.0 *cannot* reject "best of 100 noise strategies" at conventional levels, before non-normality haircuts. The plan's "report uncertainty rather than false precision from only 68 monthly OOS observations" (`plan:311`) must become: report (i) $M$ (raw and effective/independent-trials estimate via return-correlation clustering), (ii) DSR, (iii) block-bootstrap CI for IR. Harvey–Liu haircut heuristic (divide backtested Sharpe by $\ge$2; web result 4) as a cross-check, labelled heuristic.
- **JKP does not exempt the project.** JKP's Bayesian MT treatment still deflates: replication falls 84.9% → 77.3% after MT accounting (`w28432.txt:270-272`), and their shrinkage *raises* the bar for individual factors while borrowing strength across related ones (`:303-310`). Citing JKP's 84.9% as comfort without the 77.3% MT-adjusted figure (plan `plan:55` reports only 84.9%, though correctly caveated as "not a probability that our portfolio will work" — **KEEP caveat, ADD the MT-adjusted number**) misleads by omission. HXZ's mirror result — 64–85% of 447 anomalies insignificant under NYSE breakpoints + value weights (`w23394.txt:408`) — must sit next to it. The honest prior for any single new feature is "probably noise," which is exactly why shrinkage (F1) + hurdle (this section) are complements, not substitutes. Plan `plan:311` says this in words; give it teeth in numbers.

### 7.2 Pre-registration mechanics (one page, freeze before OOS)

Experiment registry fields: hypothesis + economic rationale (dated, pre-test per Mandate §5.2), feature definition hash, folds, hyperparameter grid size, validation metric, admission rule, outcome (including nulls). E0–E6 (`plan:313-325`) is a good ladder — **KEEP**, with two amendments: (a) each rung pre-declares a *minimum economic* promotion bar (e.g. Δ net IR ≥ 0.15 with block-bootstrap 90% CI excluding 0) so "tiny MSE improvement" cannot promote (plan `plan:120` already requires this qualitatively for GBM — generalise it); (b) OOS is evaluated *once* per frozen candidate; the plan's "OOS variants are predeclared diagnostics, not a menu" (`plan:325`) — **KEEP verbatim** — plus a hard rule that any post-OOS change restarts the contamination disclosure.

**Severity HIGH:** judges will ask "how many things did you try?" (Mandate §5.2). "We logged everything" without DSR/hurdle arithmetic earns partial credit at best; with it, even a modest IR becomes credible.

---

## 8. Finding F8 — Microcap / breakpoint fragility is acknowledged for the replication but not enforced in the forecaster [FIX · HIGH]

**Plan:** JKP construction noted (`plan:57`: terciles, non-microcap breakpoints, capped VW); HXZ row (`plan:429`: "Treat microcap restrictions, weighting and benchmark choice as substantive robustness tests"); short floor implemented (`plan:41`). All good — for §3's research replication. §4's forecaster, however, trains on the *full* eligible panel with date-balanced (i.e. essentially equal-weighted across stocks within date) loss. HXZ's central finding is that this is where fake alpha lives: microcaps are ~3% of market cap but ~60% of stock count (`w23394.txt:155-159`); equal-weighted / full-universe-breakpoint constructions "overweight microcaps" (`:163-165`) and most anomalies collapse under NYSE breakpoints + VW (`:43-45, 408`). JKP vs. HXZ replication gap (84.9% vs. ~35% OLS) is *substantially* construction: terciles vs. deciles, non-microcap breakpoints, capped VW (+8.5pp from weighting alone, `w28432.txt:206-211, 251-253`).

**Consequence for §4:** a pooled ridge minimising equal-weighted MSE will load on microcap predictability (where $R^2$ is highest and noise-fitting easiest — cf. GKX Bottom-1000 vs Top-1000 splits, `w25398.txt` Table 1) and the optimiser will then be unable to express it: longs capped by ADV/participation (`plan:245-254`), shorts banned below $500m. Validation IC will overstate tradable IC by construction.

**Correct alternative:**
1. **Train/validate on the tradable universe, report the gap.** Primary loss: universe = names passing *lagged* liquidity screen (ADV, price) with shorts additionally ≥$500m; weight by capped value or $\sqrt{\text{ADV}}$ (report both; JKP capped-VW is the principled compromise between EW noise-chasing and VW mega-cap domination). Diagnostic: full-universe EW fit. The difference is the "untradable alpha" exhibit — judges love it, and Mandate §3.3 (`:170-192`, books "that could not have been traded at any institutional scale") demands it.
2. **Asymmetric evaluation:** long-leg IC on long-eligible names, short-leg IC on short-eligible (≥$500m) names only. A single pooled IC hides the binding constraint (Mandate §3.2 `:156-160`: 250-name short book ≈ 7–8% of everything shortable).
3. **Breakpoint hygiene in features:** cross-sectional ranks/z-scores computed within tradable universe per date (also satisfies Mandate §7 `:724-726` no-full-sample-standardisation). Winsorise at *expanding-window* quantiles, never full-sample.

**Severity HIGH:** without (1)–(2), E0→E3 ladder (`plan:317-320`) will show a mysterious alpha collapse at the capacity rung that was actually present from the first fit.

---

## 9. What is actually predictable at daily vs. monthly horizon (magnitudes for the deck)

The plan's feature table (`plan:132-142`) lists hypotheses without horizons or magnitudes. Judges (Mandate §4) will probe exactly this. The table below states the consensus the plan should anchor to; all magnitudes are *gross* unless stated, US equities, and must be haircut for post-publication decay (McLean–Pontiff, `plan:435` — **KEEP** that row's instruction) and for the $1bn/$500m constraints.

| Horizon | Phenomenon | Gross magnitude (literature) | Net / modern status | Role in this mandate |
|---|---|---|---|---|
| **Daily (1–5d)** | Short-term reversal (STR): buy 1-week losers, sell winners | ~0.5–1.5%/week EW in classic samples; HXZ find Jegadeesh STR does **not** survive NYSE-breakpoint/VW replication (`w23394.txt:95`) | Lehmann/Jegadeesh profits largely bid-ask bounce + microcaps. Best modern implementations (large-cap only, turnover-aware "smart" construction): **30–50 bp/week net** (Avramov–Chordia–Goyal-style; SSRN 1963131 abstract via web search §10 result 2 — snippet-level, fetch blocked 403, treat as indicative). Naive daily reversal at $1bn: negative net. | **Not a core signal.** At most a *cost-aware execution overlay* (provide liquidity, delay trades into reversal) within large caps. Daily $R^2$ from characteristics ≈ 0; daily rank IC of monthly features ≈ IC$_{21}$/$\sqrt{21}$ at best, swamped by microstructure variance (Mandate §4 `:241-243` is correct). |
| **Daily–weekly (event)** | Post-earnings-announcement drift (PEAD) | Bernard–Thomas: high–low SUE spread ≈ **4.2% over 60 trading days** (1974–85); ~8–9%/quarter hedge returns (web fetch §10: Wikipedia PEAD, fetched in full). LSEG modern sample: extreme-surprise drift +126 bp / −214 bp over 30d (asymmetric, short leg stronger). | **Severely attenuated:** Martineau (2022) "RIP PEAD" — ≈0 for large caps by ~2006 post-decimalisation/Reg NMS (via web search snippet; primary paper not fetched — flag as such in deck). Residual PEAD concentrates in small/illiquid/low-coverage names — largely **unshortable/unscalable here**. Announcement-window (days 0–2) reaction is now ~complete for ≥$500m names. | Event overlay only with honest subperiod reporting. Earnings-*surprise* features (SUE, EAR) belong in the monthly model as slow drift + the van Binsbergen bias channel (below), not as a daily PEAD trade. Any daily event backtest must use $t{+}1$ entry (Mandate §6.5 `:593-596`) — same-day entry fabricates most of modern "PEAD." |
| **Monthly (21d)** | Cross-sectional characteristic premia (value, momentum 12-1, profitability/quality, investment, accruals) via pooled ML | GKX monthly stock-level $R^2_{oos}$: linear ~0.11–0.27%, trees/NN 0.33–0.40% (`w25398.txt` Table 1). Implies monthly rank IC ≈ 0.05–0.08 for good models. Decile-spread Sharpe gross 0.6–1.35 VW (GKX, 1987–2016) — **pre-cost, pre-2021, includes microcap contribution in EW versions**. | Realistic 2021–26 planning assumption: gross long–short 4–8%/yr at 8–12% vol before costs for a diversified characteristic book; net IR vs cash+4% is the open empirical question (plan correctly refuses to promise, `plan:5,13`). Factor-adjusted *residual* alpha will be 1/3–1/2 of raw spread. | **The core.** Plan §§4–6 correctly built around it. Budget expectations from residual, capacity-feasible numbers — never from GKX headline Sharpes (`plan:415` already warns this — **KEEP**). |
| **Monthly–quarterly** | Analyst-bias / earnings-expectation errors (van Binsbergen et al.) | ML-benchmark minus analyst forecast predicts returns cross-sectionally; short leg of many anomalies = high-optimism firms (`w27843.txt:56-61,123`). | Requires point-in-time I/B/E/S-style consensus snapshots. Plan gates it correctly ("if dated analyst estimates and actuals exist", `plan:139`; admission gate `plan:286`) — **KEEP**. Do not proxy with revised/current-vintage estimates (Mandate §7 `:709-715`). | Highest-value *optional* branch (E5) *if* data audit passes; otherwise DROP without regret. |
| **Monthly** | Momentum | 12-1 momentum among the most robust premia (survives HXZ/JKP both); crashes in sharp reversals (2009-type). Half-life ~1–2 months for the *signal*, formation over 12 months. | Crowded; borrow-sensitive on short (loser) leg. Needs vol-scaling / crash guard tested pre-OOS only (cf. Moreira–Muir vs Cederburg dispute, `plan:449-450` — plan's "test, don't assume" is correct). | Core candidate (`plan:137` — **KEEP** with decay + reversal-risk measurement as written). |
| **Any** | Tomorrow's return from slow characteristics | $R^2\approx 0.00$–$0.02\%$ daily; signal-to-noise $\propto\sqrt{H}$ only if alpha accrues linearly, which event/momentum components violate. | Training a daily target on monthly features fits microstructure noise (Mandate §4). Plan prohibits this (`plan:114`) — **KEEP**. | **DROP** any "daily alpha model" framing. Daily = risk + event-expiry + execution timing only. |

**One-line summary for the deck:** *At $1bn with a $500m short floor, credibly predictable US-equity alpha lives at the monthly horizon (IC ~0.05, $R^2$ ~0.2–0.4%/month); daily predictability is either microstructure rent that costs consume (STR) or event drift that modern markets have largely arbitraged in tradable names (PEAD). The daily clock therefore buys risk control and event expiry, not a second alpha engine.* This is consistent with — and slightly more pessimistic than — plan §1. Pessimism here is a feature: Mandate §4 explicitly credits "daily did not survive costs, here is the evidence."

---

## 10. JKP / factor-zoo claim audit (plan §3 + §12 vs. source-pack bodies)

| Plan claim | Verdict | Evidence |
|---|---|---|
| "153 factors across 93 countries… 13 themes… global Bayesian replication rate of 84.9%" (`plan:55`) | **KEEP + FIX** (add MT-adjusted 77.3%) | Verified: `w28432.txt:57,109,127,337`. Decomposition vs HXZ baseline 56.9% (`:191`): construction + weighting explain most of gap (`:194-222`). MT-adjusted 77.3% at `:249,270` — plan omits; add. |
| "terciles, non-microcap breakpoints and capped value weights" (`plan:57`) | **KEEP** | `w28432.txt:206,251-253,1202-1208`. Note asymmetry: breakpoints from non-microcaps, microcaps still *assigned* to terciles (`:1218`) — replication must copy this, not exclude microcaps outright. |
| "CAPM benchmark materially narrower than finals' broader factor review" (`plan:57`) | **KEEP** | Correct and judge-relevant: JKP alphas are vs. CAPM (+ global variants); Arcana review (Mandate §11) will attribute vs. richer models. Research replication must show both. |
| "ex-post tangency analysis is not a deployable OOS rule" (`plan:57`) | **KEEP** | Correct; cf. Britten-Jones sampling-error warning (`plan:437`). 10/13 themes in tangency (`w28432.txt:391`) is in-sample. |
| Hierarchical prior $\Omega=\tau_c^2MM^\top+\tau_w^2I$, posterior $\bar\alpha=\Omega(\Omega+V)^{-1}a$ (`plan:71-84`) | **KEEP** as research-replication spec | Faithful Gaussian restatement ("corresponds… when $V$ is its specified sampling covariance", `plan:84` — honest). Implementation note: $V$ must be HAC (Newey–West, `plan:439`) with cross-factor blocks; diagonal $V$ invalidates the exercise. |
| "paper appeared Feb 2021, test starts Jan 2021… Do not import fitted clusters/weights" (`plan:90`) | **KEEP** — exemplary | Correct look-ahead hygiene. Extend identically to GKX variable-importance rankings (estimated through 2016+, published 2020) and Chen–Zimmermann characteristic definitions fitted on full history: technique transfers, fitted objects do not. |
| GKX row: "nonlinear interactions and chronological validation" (`plan:415`) | **KEEP** | Verified `w25398.txt:60-62,239-249,1261`. Add magnitudes (Table 1 $R^2$ above) so the team calibrates expectations. |
| KNS row: "retain information across many correlated predictors… SDF is not our portfolio policy" (`plan:432`) | **KEEP** | Verified `w24070.txt:46-55,164-181`. Add the PC-sparsity half (sparse in PCs, dense in characteristics) — it is KNS's headline and directly motivates PCR-style shrinkage in F1. |
| FGX row: "ordinary post-selection t-tests are unreliable" (`plan:433`) | **KEEP** | Verified `taming_factor_zoo.txt:13-15,91-99`. Consequence (add): GBM importance + $t$-stat slide is prohibited evidence; use double-selection or pure OOS portfolio tests. |
| HLZ row (`plan:430`) | **FIX** — adopt $t>3.0$ numerically | See F7. `w20592.txt:54-60`. |
| HXZ row (`plan:429`) | **FIX** — move from "robustness test" to forecaster design constraint | See F8. `w23394.txt:43-45,155-176,408`. |
| van Binsbergen row (`plan:421`) | **KEEP** | Verified `w27843.txt:56-61`. Gate on snapshot availability as plan does. |
| GP row (`plan:447`): "slower signals justify different trading intensity" | **FIX** — state aim/trading-rate formulas | See F5/F6. `w15205.txt:51-56,367-419`. |
| McLean–Pontiff "not independently full-text reviewed" (`plan:435`); Chapados/Goyenko abstract-only (`plan:416-417`) | **KEEP** disclosure practice | Honest reading levels (`plan:408`) — judges should be shown this register; it pre-empts citation-padding challenges. No forecasting claim in §§3–4 rests solely on an unread paper. **No fabricated citation found** in §§3–4/12: every load-bearing claim traces to an opened `.txt` body above. |

**Net assessment of §§3/12 scholarship:** unusually careful — version discipline (w28432 Feb 2021 vs. JoF 2023, `plan:55,414,480-484` with SHA-256), explicit non-claims, skeptical counterparts (HXZ, Cederburg) included. The failures are of *omission* (77.3%, PC-sparsity, magnitudes, DSR), not fabrication.

---

## 11. Smaller forecasting findings

- **F9 · Sector controls ≠ sector neutrality** [KEEP]. Plan `plan:110` states this explicitly. Add implementation check: ridge with sector dummies still produces sector-tilted *portfolios* if signal strength varies by sector; neutrality is a construction constraint (`plan:203-209`), validated by attribution — which Stream 3 owns.
- **F10 · Missingness indicators** [FIX · LOW]. `plan:110` allows them "where justified." Missingness in Compustat-style panels is informative (small/young/distressed firms) *and* regime-dependent (coverage expansions look like alpha). Require: missingness indicator + within-date median imputation fitted on training folds only; ablation reported. GBM native missing-handling must match ridge's explicit handling or the horse race is confounded.
- **F11 · Forecast calibration for the optimiser** [FIX · MEDIUM]. Plan requires GBM calibration (`plan:118`) but not ridge calibration. Ridge $\hat\mu$ is shrunk by construction — its cross-sectional *dispersion* understates true alpha dispersion by factor $\approx\text{df}$-dependent shrinkage. Feeding shrunk $\hat\mu$ into $\min \frac{\gamma}{2}w^\top\Sigma w-\mu^\top w+\dots$ (`plan:183-188`) with $\gamma$ tuned on the same shrunk scale is coherent *only* if $\gamma,\rho$ are tuned jointly on portfolio outcomes (F3.2). Add a validation calibration regression $y = a + b\hat\mu + \varepsilon$ per fold: report $b$ (should be ≈1 after rescaling); rescale forecasts by $b$ before construction so $\mu$ units are honest expected returns. Rank-only use (support selection, `plan:213`) is immune; magnitude use (sizing) is not.
- **F12 · One model vs. ensemble** [KEEP]. "Deploy one winner… Do not combine a collection of models simply because each has a different name" (`plan:11`). Correct for a two-day event: forecast-combination weights are another estimation layer on 24 validation months. Exception worth one pre-registered test: *equal-weight rank average* of ridge + GBM (no estimated weights) — combination gains in GKX-style settings often exceed selection gains because model errors diversify. If tested, it counts toward $M$ in F7.
- **F13 · Feature priorities table** (`plan:132-142`) [FIX · LOW]. Add horizon + expected decay + short-leg borrow sensitivity columns (from §9 above). "Low risk" row's warning (don't disguise BAB as alpha, `plan:138`) — **KEEP**; enforce via beta-attribution exhibit. Option-derived predictors (`plan:142`): correctly research-only — **DROP** for the event unless point-in-time options data is *already in hand* on Day 1 (no dataset in Mandate §6.6 catalogue supplies it).
- **F14 · Daily-head features from daily returns** [FIX · MEDIUM]. Plan builds risk from daily returns (`plan:154`) but never says whether *forecast features* (e.g. 5d reversal, 21d vol) enter the monthly model. If they do, Mandate §7 spent-return rule (`:704-708`) + $t{+}1$ clock applies with full force, and monthly-panel alignment (`ret_exc_lead1m`, `plan:112`) must be re-derived on the daily clock — the plan flags this (`plan:112`: "build an aligned future holding-period target from daily returns… compare") but sequences it as optional. Make the alignment audit (feature timestamp < formation ≤ execution < first earned return, asserted per join cf. Mandate §8.1 `:829-832`) a *gate* before E4, not a comparison after it.

---

## 12. Verdict summary (Stream 2 scope: plan §§3–4, §§9/12–13 forecasting parts)

| # | Item (plan locus) | Verdict | Severity |
|---|---|---|---|
| F1 | "Hierarchical ridge" shrinkage identity (§§3–4) | FIX (rename; add KNS-PC challenger; EB $\lambda_g$) | HIGH |
| F2 | Ridge default / GBM challenger / IPCA deferral (§4, §13) | KEEP ranking; FIX evidence (ENet role, IPCA rationale, factor-vs-stock reconciliation) | MEDIUM |
| F3 | Effective $T$, df budget, nested purged CV + embargo (§9) | FIX (specify fully) | **CRITICAL** |
| F4 | Residual targets (§4) | FIX (reorder: raw → sector-demeaned → residual) | MEDIUM |
| F5/F6 | Horizon mismatch / decay / GP trading rule (§§4, 6) | FIX (estimate $\hat\kappa$; multi-horizon heads; two-knob GP) | **CRITICAL** |
| F7 | Multiple testing (§9) | FIX (HLZ $t>3$ / BHY; DSR with $M$; promotion bars) | HIGH |
| F8 | Tradable-universe training (§4 vs §3) | FIX (capped-VW loss; asymmetric leg ICs) | HIGH |
| — | JKP replication as separate research exercise (§3) | KEEP | — |
| — | Look-ahead hygiene: dated params, no imported clusters (§3) | KEEP | — |
| — | Contamination disclosure; E-ladder concept (§9) | KEEP (+ F7 amendments) | — |
| — | Drop list affirmed: daily alpha model, NN/transformer forecaster, options branch (event), LLM weights (§13) | KEEP as DROP | — |

**Bottom line for the owner:** Do not rebuild the forecasting architecture. Freeze it, and spend the available hours on the two CRITICAL specifications (F3 validation machinery, F5/F6 decay machinery) plus the F7 numeric hurdles. A ridge forecaster with honest $T_{\text{eff}}$, purged nested tuning, estimated half-life, and a deflated-Sharpe denominator will survive judge scrutiny even if its IR is modest. The same forecaster without them will not survive scrutiny even if its IR looks spectacular — and under Mandate §§4/7/11, spectacular-without-machinery reads as leakage.

---

## 13. Web sources (searches performed; fetches recorded honestly)

Searches (6): (1) GKX R²/criticisms/microcaps; (2) short-term reversal magnitudes/costs; (3) IPCA vs Fama–MacBeth; (4) deflated Sharpe formula; (5) PEAD magnitudes/decline; (6) purged CV/embargo.

- **Fetched successfully:** `https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement_drift` (HTTP 200, full text processed) — Bernard–Thomas 8–9%/quarter hedge magnitude; used only for classic-sample scale, cross-checked against search-result LSEG/event-study summaries.
- **Fetch attempted, blocked:** `https://papers.ssrn.com/abstract=1963131` (HTTP 403) — STR net 30–50 bp/week claim therefore cited as *search-snippet/abstract-level, indicative*, never as verified body text. Primary STR scepticism in §9 rests on opened `w23394.txt:95` instead.
- **Search-result-level only (labelled as such wherever used):** DSR formula corroborated across multiple result snippets (Bailey & López de Prado 2014 — canonical reference; formula in F7 is standard); IPCA–Fama–MacBeth equivalence (multiple concordant snippets); purged-CV/embargo definitions (López de Prado, *Advances in Financial Machine Learning* — canonical); Martineau (2022) PEAD-decline (single secondary summary — flagged unverified in §9; deck must verify or drop the citation).
- **Contradicting evidence found and incorporated:** GKX gains are interaction-driven and shrink dramatically outside long samples / with costs (search 1: "complexity wedge" — attainable performance ≪ infeasible-true-model performance); PEAD ≈0 in modern large caps (search 5) contradicting naive daily-event optimism; STR largely compensation for liquidity provision, not characteristic alpha (search 2). All three push *toward* the plan's conservative architecture and *against* any daily-alpha extension.

## 14. Unresolved gaps (require data/event access; cannot be closed from documents alone)

1. Actual 147-characteristic definitions, lags, and `ret_exc_lead1m` construction in the supplied panel — F8/F14 audits need the schema (`plan:289` concurs: "actual panel schemas… still need inspection").
2. Whether point-in-time analyst consensus snapshots exist (gates E5 / van Binsbergen branch).
3. Daily-file (`dsf_mini_from_2014.csv`) fields: delisting returns, adjustment methodology, PERMNO continuity — gates daily-head labels and F14.
4. Empirical $\hat\kappa$ / IC-decay curve and tradable-vs-full-universe IC gap — estimable only on data; §6.2/§8 give the pre-registered estimators.
5. Martineau (2022) primary text and Avramov et al. STR net-return tables — verify before citing magnitudes in the deck (see §13).

*End of Stream 2 report.*



