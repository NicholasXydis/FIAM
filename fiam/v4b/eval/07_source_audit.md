# Stream 7 — Source-pack & literature audit

**Scope:** Taildrop plan `fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md` (484 lines, cited as Plan §/L) vs FINAL mandate `fiam/v4b/inputs/final_mandate.txt` (1168 lines, cited as Mandate §/L). Source pack: `fiam/v4b/inputs/source_pack/sources/README.md` + `manifest.json` + 10 PDF/.txt pairs. Every paper below was identified from its .txt title/abstract head and spot-verified by grep of the full .txt. Past repo work treated as evidence only.

**Bottom line:** The pack is a coherent *monthly factor-zoo* canon. The finals are a *daily, $1bn, borrow-constrained* problem (Mandate §2 L52–68, §3.3 L163–198, §4 L214–253). The Plan cites the pack mostly accurately at abstract level and unusually honestly about adaptation gaps — but inherits the pack's blind spot: **zero daily-horizon, zero PEAD/8-K-drift, zero borrow-fee, and zero calibrated-impact evidence** for the very decisions (daily overlay, weekly trading, sqrt-impact optimizer) that will decide net IR. Two citations do real load-bearing work they cannot support (GKX → daily trees; Gârleanu–Pedersen → sqrt-impact conic controller). Fix those, add the missing implementation literature ranked in §5, and the register is keepable.

---

## 1. What is actually in the pack (identification)

`README.md:1-3` states only that w28432 was "requested" and others are "supporting primary-source papers", downloaded 23 Oct 2026, working-paper versions may differ from published. `manifest.json` lists 10 items with NBER/Chicago Booth URLs, SHA-256 and byte counts. Spot-check: recomputed SHA-256 for w28432.pdf (`95807b0c…e693`) and w25398.pdf (`cf4ebd0a…8c66`) match manifest exactly. All .txt are Poppler extractions.

| # | File | Paper (from .txt head) | Status of this copy |
|---|---|---|---|
| 1 | w28432 | Jensen, Kelly, Pedersen, *Is There a Replication Crisis in Finance?*, NBER Feb 2021 (153 factors, 93 countries, 13 themes) | Working paper; JF 2023 published version NOT in pack |
| 2 | w25398 | Gu, Kelly, Xiu, *Empirical Asset Pricing via ML*, Dec 2018 rev. Sep 2019 (~30k stocks 1957–2016, 94 chars) | Working paper; RFS 2020 version differs in vintage |
| 3 | w27843 | van Binsbergen, Han, Lopez-Lira, *Man vs ML: Term Structure of Earnings Expectations*, Sep 2020 rev. Aug 2021 | Working paper (later JFQA/RFS lineage; verify before citing as 2023) |
| 4 | w24070 | Kozak, Nagel, Santosh, *Shrinking the Cross Section*, Nov 2017 (PC-sparse SDF) | Working paper; JFE 2020 published |
| 5 | taming_factor_zoo | Feng, Giglio, Xiu, *Taming the Factor Zoo*, JF 75(3) Jun 2020 pp.1327+ (double-selection LASSO) | **Only peer-reviewed journal PDF in pack** |
| 6 | w23394 | Hou, Xue, Zhang, *Replicating Anomalies*, May 2017 (447 anomalies) | Working paper; RFS 2020 published |
| 7 | w20592 | Harvey, Liu, Zhu, *…and the Cross-Section of Expected Returns*, Oct 2014 (316 factors, t>3) | Working paper; RFS 2016 published |
| 8 | w16601 | Frazzini, Pedersen, *Betting Against Beta*, Dec 2010 | Working paper; JFE 2014 published |
| 9 | w15205 | Gârleanu, Pedersen, *Dynamic Trading with Predictable Returns and TC*, Aug 2009 | Working paper; JF 2013 published |
| 10 | w22208 | Moreira, Muir, *Volatility Managed Portfolios*, Apr 2016 rev. Jun 2016 | Working paper; JF 2017 published |

**Finding 1.1 [MEDIUM, fix]: 9/10 pack items are pre-publication vintages.** Plan §12 preamble L408 correctly warns "downloaded working-paper vintages can differ" and Plan §3 L55 correctly notes w28432 is "not the later JF version". But Plan §12 then dates several rows by *published* year (GKX 2020 L415, KNS 2020 L432, HXZ 2020 L429, BAB 2014 L434, GP 2013 L447, MM 2017 L449, vBHL 2023 L421) while the evidence inspected is the WP. Numbers, samples and even conclusions changed between WP and journal for at least JKP and GKX. *Correct practice:* cite WP year + "published as …" separately; never attribute a journal-year result to WP pages. Judges on Arcana (Mandate §11) will check this.

**Finding 1.2 [LOW, keep]: Provenance is good.** Manifest hashes + retrieval date + Plan L478–484 download provenance for w28432 exceed typical hackathon practice. Extend the same hash line to all 10 in the deck appendix; currently only w28432 gets it.

## 2. Plan §12 register cross-check (A / B / C)

Plan §12 L406–450 has three tiers. Coverage vs pack:

- **A (initial-case bibliography, L410–423): 8 items, only 3 in pack** (JKP, GKX, vBHL). The other five — Chapados et al. (SSRN abstract only L416), Goyenko–Zhang (abstract only L417), Hoerl–Kennard 1970 (record only L418), Tibshirani 1996 (record only L419), Zou–Hastie 2005 (abstract only L420) — have **no source-pack backing**. Plan is honest about this ("full paper not verified", "publication record verified"). Verdict: honest but thin — ridge/lasso/elastic-net are textbook methods needing no pack PDF, whereas Chapados (text→earnings) and Goyenko–Zhang (options→stocks) are *empirical* claims the Plan leans on in §4 L139–142 without inspected evidence. See §3.7.
- **B (cited by JKP, L425–441): 11 items, 5 in pack** (HXZ, HLZ, KNS, FGX, BAB). Six are explicitly not full-text reviewed (Chen–Zimmermann abstract L431; McLean–Pontiff L435, Kelly–Pruitt–Su L436, Britten-Jones L437, Shumway via JKP L438, Newey–West bibliography L439). Again honest labelling — a strength.
- **C (rebalancing, L443–450): 4 items, 2 in pack** (GP, MM). Ledoit–Wolf (abstract L448) and Cederburg et al. (abstract L450) are not in pack. Cederburg is the *only* skeptical counterweight to MM and it rests on an institutional abstract page — fragile for a load-bearing "don't vol-time" decision.

**Finding 2.1 [MEDIUM, fix]: Register honesty ≠ register sufficiency.** The Plan never pretends to have read what it hasn't (exemplary; keep). But Mandate §5.2/§8.3 judges will ask for denominators and primary sources. Any A/B/C row marked "abstract/record/bibliography only" must not support a modelling choice in §§4–6. Currently two do: Zou–Hastie grouping → §4 family ridge motivation, and Ledoit–Wolf → §5 covariance shrinkage default. Either retrieve full texts or downgrade those choices to "engineering default, literature pending".

**Finding 2.2 [LOW, keep]: No standalone bibliography in final PDF.** Plan L51 correctly states the final PDF has no academic bibliography and §12 therefore covers initial bibliography + JKP citations + rebalancing additions, explicitly "not an exhaustive systematic review". Accurate against Mandate text (references are platform/data links, §6/§11). Keep verbatim in deck to pre-empt "why didn't you cite X" — then answer X from §5 below.

Every in-Plan citation outside §12 was grepped: substantive mentions are JKP (§1 L13, §3 L55–94) and Gârleanu–Pedersen (§1 L13). All other papers appear *only* in §12 tables. That is itself a finding: **§§4–6 design equations cite almost nothing** — the ridge (§4 L102–108), factor covariance (§5 L148–150), robust beta (§5 L162–164), conic objective + sqrt impact (§6 L182–199) are presented as synthesis without per-equation provenance. Plan L13/L65/L199 disclaimers ("engineering synthesis, not replication") partially cover this, but a judge tracing "where does sqrt impact come from?" finds no citation at all. See §3.5.

## 3. Claim-by-claim verification (grep of full .txt)

Six attributed claims were verified against paper text; two more spot-checked. Line refs are .txt lines in `fiam/v4b/inputs/source_pack/sources/`.

### 3.1 JKP w28432 — "153 factors, 93 countries, 13 themes, 84.9%" (Plan §3 L55, §12 L414) — MOSTLY ACCURATE, one conflation [MEDIUM, fix]

Verified: abstract L57–59 (13 themes, 93 countries); L109 (153 factors/93 countries); tercile + capped value-weight construction L206, L251, L1203–1208; CAPM-alpha benchmark L242–245, L938; ex-post tangency of 13 theme portfolios L390–397 (10/13 significant); Shumway −30% delisting imputation L1271–1274 (Plan L438 correct, including "not a universal truth" caveat — keep).

Conflation: Plan L55 says "global Bayesian replication rate of 84.9%". The paper contains *several* near-84.9 numbers that are not the same object: US OLS CAPM-alpha replication 84.9% (L244–245, L1367), US empirical-Bayes 84.0% (L1386), global-sample final bar 84.9% (L336–337), global EB 80.7% (L1404–1405), BY multiple-testing-adjusted 77.3% (L270, L1377). Plan's gloss "significance result under its research design, not a probability our portfolio will work" (L55) is exactly right and should be kept — but the deck must state *which* 84.9 (global, Bayesian-model-based, Fig.1 last bar) and show the 56.9%→64.7%→84.9% bridge (L191–245) driven by terciles/capped-VW/CAPM choices. Otherwise judges will (correctly) accuse cherry-picking the largest number.

Deeper issue [HIGH for interpretation, Plan handles it — keep]: JKP alphas are vs **CAPM only**. Mandate §11 Arcana review uses 120+ risk models (Barra/Axioma/Wolfe, Mandate L1061–1067) and asks factor-vs-idiosyncratic decomposition (L1090–1094). A JKP-"replicable" factor can be 100% spanned by Barra styles and earn zero idiosyncratic credit. Plan §3 L57 ("CAPM benchmark materially narrower than finals' broader factor review") and L92–94 (factor replication ≠ stock-selection alpha) state this correctly. Mathematically correct alternative already in Plan L71–86: posterior `ᾱ = Ω(Ω+V)⁻¹a`, `P = Ω − Ω(Ω+V)⁻¹Ω` with `Ω = τc²MMᵀ + τw²I`, plus the crucial warning (L86) that alpha-uncertainty `P` is **not** return covariance `Σ` and needs a loading map `APA′`. This is the best page in the Plan. Keep; add one sentence: ridge (§4) equals this posterior mean **only** if `V ∝ I` and characteristics equal factor loadings — generally false, so "hierarchical ridge inspired by JKP" must never be shortened to "JKP model" (Plan L65 already says this; enforce in slides).

Look-ahead: Plan L90 correctly flags Feb-2021 paper vs Jan-2021 OOS start and forbids importing fitted clusters/tangency weights. Consistent with Mandate §7 (L671–673 disqualification rule) and §8.1. Keep. Note the JF 2023 version postdates even more of the OOS window — cite WP for method, never JF fitted values.

### 3.2 GKX w25398 — "trees/NN win, doubling performance" (Plan §12 L415, motivating §4 L116–120) — ACCURATE ABSTRACT, CHERRY-PICKED TRANSFER [HIGH, fix]

Verified: abstract L59–63 ("doubling performance… trees and neural networks… momentum, liquidity, volatility"); ~30,000 stocks 1957–2016, 94 characteristics L192–193, L1170–1177; train 1957–74 / validate 1975–86 / test 1987–2016 L1243–1244; monthly next-month decile sorts L2580. Plan L415 summary ("nonlinear interactions, chronological validation") is faithful, and its caveat ("sample and gross results do not establish capacity/IR") is present.

What Plan omits (cherry-pick by omission):
1. **Sample ends Dec 2016.** Finals OOS is Jan 2021–Aug 2026 (Mandate §3.1 L129) — entirely outside GKX. Post-2016 ML decay evidence (§5.5 below) is directly relevant and absent.
2. **Monthly, gross, microcap-inclusive deciles.** Headline Sharpe (e.g. NN4 1.69 value-weighted variant L2516; equal-weighted deciles higher) assumes frictionless monthly rebalancing across all CRSP names. Finals impose $1bn compounding, $500m short floor, 5% cap, 200–500 names (Mandate §3.1). GKX dominant signals — short-term reversal (`mom1m`), liquidity/turnover, volatility (L1806, L2090) — are precisely the highest-turnover, most capacity-constrained family (see §5.1). A tree that wins in GKX by loading reversal×size interactions may be *untradable* in finals.
3. **No daily evidence.** GKX monthly R² 0.33–0.40% (L240) says nothing about 1-day or 5-day horizons where Mandate §4 L241–243 warns cross-section is "dominated by microstructure noise".

*Mathematically correct use:* GKX licenses a *monthly* tree challenger on identical folds/optimizer with net-IR promotion (Plan L120 already requires this — keep and enforce). It does **not** license daily tree trading, nor expecting published Sharpe magnitudes. Add to §12 row: "OOS ends 2016; gross of costs; reversal-heavy — haircut per Avramov et al. / FIM before budgeting."

### 3.3 HXZ w23394 vs JKP — "don't declare settled" (Plan L429) — ACCURATE BUT UNDERWEIGHTED [MEDIUM, fix emphasis]

Verified HXZ abstract L44–49: 447 anomalies; 286 (64%) insignificant at 5% with NYSE breakpoints + VW; 380 (85%) at t≥3; q-factor leaves 115/161 alphas insignificant. Plan's one-liner is accurate.

Missing reconciliation the judges will demand: HXZ (447 vars, deciles, NYSE breakpoints, straight VW, q-factor/FF benchmarks) vs JKP (153 factors, terciles, non-microcap breakpoints, capped VW, CAPM) differ in *universe, breakpoints, weighting, benchmark, and inference* simultaneously — JKP L191–260 decomposes ~+4.3pp (sample), +4.0pp (terciles), +8.5pp (capped VW) etc. For finals tradability, **HXZ construction is closer to the mandate** (VW discipline ≈ capacity discipline; NYSE breakpoints ≈ $500m floor spirit) while JKP capped-tercile is closer to "research portfolio" (Plan L69's own distinction). Plan §3 replication design (compare capped/straight/equal weighting L69) will surface this — keep — but §12 should state the prior explicitly: *budget alpha from HXZ-like (tradable) numbers, use JKP for shrinkage method only.* Currently a reader could budget from JKP 84.9% optimism.

### 3.4 HLZ w20592 + FGX + KNS — multiple-testing / shrinkage trio (Plan L430, L432–433) — ACCURATE, MIS-SCOPED HURDLE [MEDIUM, fix]

Verified HLZ: t>3.0 hurdle, "most claimed findings likely false" L60–61; 313 papers / 316 factors L86, L184. Verified FGX: most new factors redundant, double-selection LASSO correcting oracle-property failure, .txt L15, L91, L158–212. Verified KNS: characteristics-sparse SDF rejected; sparsity in **PC space**, elastic-net-like prior shrinking low-variance PCs, L49–54, L110, L150, L452.

Plan summaries are each faithful. Two scope errors:
- HLZ t>3 is calibrated for *one new factor's time-series t* given ~316 published tries. Finals search is different: 147 chars × interactions × 77 Carbon Arc datasets × agent-proposed features (Mandate §5.2 L353–360 demands the denominator). Correct tool is FDR control (Benjamini–Hochberg/Yekutieli as in JKP/HLZ) or deflated Sharpe / block-bootstrap on *net* strategy returns, not a single t>3 gate per feature. Plan §9 L311 ("dependence-aware multiple-testing procedure") gestures correctly — name BH-FDR + report #tested/#kept per Mandate L356–360.
- KNS sparsity is after PC rotation; Plan §4 group ridge `Σg λg||θg||²` shrinks in *characteristic-family* space. These coincide only if families ≈ PC eigenspaces (false when families are correlated, e.g. 12 value variants). Citing KNS (L432) as support for family ridge is loose. Correct statement: KNS supports *dense shrinkage over sparse winner-picking* (keep that moral); the family-penalty form needs its own validation (§9 ladder E2), not KNS authority. Similarly FGX tests a *tradable factor's* marginal SDF loading — Plan's feature admission by net-IR improvement (L120, E5) is actually stronger for finals; present FGX-DS as optional statistical screen, not as implemented method unless coded.

### 3.5 Gârleanu–Pedersen w15205 — "gradual cost-aware rebalancing" (Plan §1 L13, §6, L447) — BIGGEST ADAPTATION GAP [HIGH, fix]

Verified: closed-form with **quadratic** costs `TC(Δx)=ΔxᵀΛΔx`, Assumption A `Λ=λΣ` (.txt L263–287); optimal policy trades partially toward an *aim portfolio* (weighted avg of current + expected future Markowitz portfolios), slower-decay signals get more aim weight (abstract L51–57; L99, L131–132, L367–381); empirics on **commodity futures** (L57, L149). No gross/net/count/cap/short-floor constraints; no L1 spread; no sqrt impact; no borrow.

Plan §6 objective (L182–199) is a different problem: `γ/2 wᵀΣw − μᵀw + ρ√(wᵀUμw) + C(q) + borrow + η||w||²` with `C(q)= Σ sᵢ|qᵢ| + Σ κᵢσᵢ|qᵢ|√(NAV|qᵢ|/ADVᵢ)` (i.e. cost ∝ |q|^{3/2}), solved as one-period conic program on a pre-selected 300-name support with hysteresis. **GP justifies none of: sqrt law, L1 term, robust norm term, support selection, weekly cadence.** Hysteresis/no-trade bands come from *proportional* costs (Davis–Norman), not GP quadratic costs (where optimal policy always trades a fraction, never a dead zone). Plan disclaimers (L13 "not replication", L199 "modeling assumption… not universal law", L241 "one-period controller, not exact DP") are honest and must stay — but §12 L447 ("Use gradual adjustment and decay tests") still lets GP bless the design.

*Mathematically correct GP alternative (state it, then deviate knowingly):* with signal decay `E[f_{t+k}|f_t]=Φᵏf_t` (Φ=diag(φg)), quadratic costs Λ=λΣ, risk aversion γ, the aim portfolio is `aim_t ∝ Σ_{k≥0} (… ) E_t[Markowitz_{t+k}]` with family weight increasing in φg/(1−… ) — i.e. estimate φg per family (half-life from IC decay, Mandate §11 alpha-decay diagnostic L1105–1107) and trade fraction `Λ⁻¹Axx` toward aim. Plan currently never estimates φg. Minimal fix: (a) estimate IC half-lives per family on validation; (b) implement GP partial-adjustment as E4 comparator vs Plan's conic+hysteresis; (c) cite Davis–Norman/Lobo/Boyd-MPC (§5.6) for bands/MPC, Kyle–Obizhaeva/FIM (§5.3) for sqrt κ calibration. Without (c), §6 κᵢ are free parameters judges can drive a truck through.

### 3.6 vBHL w27843, BAB w16601, MM w22208 — spot checks

**vBHL [MEDIUM, fix scope]:** Verified abstract L59–62 (upward bias rising in horizon; short legs contain over-optimistic firms; high-bias firms issue equity; linear models fail OOS); random forest primary method L100. Plan L421 accurate. But: (i) requires point-in-time I/B/E/S consensus + realized earnings at 1–2yr horizons — Plan §8 L286 admits this "must exist" (unverified in Carbon Arc list §6.6; CA0065C actuals ≠ consensus snapshots). Until snapshots verified, downgrade from "strong hypothesis for short book" to "contingent branch". (ii) "Linear earnings models do not work OOS" cuts against using Plan's ridge for any earnings-forecast target — if earnings branch pursued, benchmark must be nonlinear (RF) per vBHL, with ridge as straw man. Plan §4 residual targeting (L122–130) should note this.

**BAB [LOW as cited, HIGH if harvested — drop as alpha]:** Verified abstract (leverage-constrained investors bid up high-beta; BAB long levered low-beta/short high-beta; betas compress when funding tightens) .txt L52–56. Plan L434 uses BAB only for "dollar ≠ beta neutral" — correct and keep. Warning: BAB return *is* a levered beta spread; under Mandate gross≤200%, beta≈0 scrutiny (L194–198) and Arcana factor attribution, harvesting BAB reads as factor tilt, not idiosyncratic alpha, and crashes in funding squeezes (relevant to Plan §5 stress L172 short-squeeze scenario — link explicitly). Plan §4 table row "Low risk… avoid disguising low-beta premium as unique alpha" (L138) already says this; keep, cite BAB funding channel as mechanism.

**MM + Cederburg pairing [KEEP — model of non-cherry-picking]:** Verified MM: scale by inverse prior-month realized variance; market alpha 4.9% .txt L53, L77, L90. Plan L449–450 pairs MM with Cederburg et al. real-time failure and requires fixed-policy counterfactual. This pro/contra pairing is the register's best practice — replicate it for JKP/HXZ and GKX/Avramov. Substantive fix only: raw MM leverage `c/RV_{t-1}` frequently exceeds 200% gross cap and targets factor (not stock-book) vol; Plan §5 variance cap `wᵀΣann w ≤ σmax²` (L208) is *not* MM. Label §5 policy "vol-capped", cite MM/Cederburg as evidence *against* vol-timing alpha claims. Also retrieve Cederburg full text (JFE 2020) — abstract-only is too weak for the contra leg.

### 3.7 Non-pack A-items (Chapados, Goyenko–Zhang) [MEDIUM, fix or drop]

Plan §4 L139–142 prioritizes "earnings expectation errors" and "filing text" partly on these abstracts. Without full texts in pack, sample periods, horizons (Chapados: 10-K/Q → earnings surprise, not 8-K → daily returns), and cost/capacity treatment are unverified. Mandate §6.4–6.5 further constrains text: supplied 8-K corpus is survivorship-contaminated (L500–519), CA0035 has **no text at all** (L579, L584–588). Correct treatment: keep as *hypothesis sources*, require EDGAR-rebuilt (CA0032) point-in-time replication on validation before any return claim; do not cite SSRN abstract performance numbers in deck. Goyenko–Zhang options branch additionally needs historical point-in-time option data whose existence in Carbon Arc §6.6 list is not shown — keep Plan's "research branch only if accessible" (L142) verbatim.


## 4. Per-paper verdict table

| Paper (pack file) | Plan use (Plan §) | Faithful? | Verdict | Severity |
|---|---|---|---|---|
| JKP w28432 | §3 shrinkage method; §12 A | Yes, except 84.9% conflation (§3.1) | **KEEP** method; FIX number labelling; never import fitted clusters (Mandate §7) | MEDIUM |
| GKX w25398 | §4 tree challenger; §12 A | Abstract yes; transfer cherry-picked (ends 2016, monthly gross) | **FIX**: monthly-only license + net-IR gate; add decay haircut refs §5.5 | HIGH |
| vBHL w27843 | §4 short-book hypothesis; §12 A | Yes | **FIX**: contingent on I/B/E/S snapshots; RF not ridge for earnings | MEDIUM |
| HXZ w23394 | §12 B robustness | Yes, underweighted | **KEEP + PROMOTE**: budget alpha from HXZ-tradable, not JKP-research numbers | MEDIUM |
| HLZ w20592 | §9 search discipline; §12 B | Yes, hurdle mis-scoped | **FIX**: replace t>3 gate with BH-FDR/deflated Sharpe + denominator (Mandate §5.2) | MEDIUM |
| KNS w24070 | §4 shrinkage moral; §12 B | Moral yes; PC-vs-family rotation conflated | **FIX**: cite for dense> sparse only; validate family λg in E2 | MEDIUM |
| FGX JF2020 | §12 B incremental test | Yes | **KEEP as optional screen**; DROP implication it is implemented unless DS coded | LOW |
| BAB w16601 | §12 B beta warning | Yes (abstract level) | **KEEP as risk warning; DROP as alpha** (levered factor, funding crashes) | LOW/HIGH* |
| GP w15205 | §1/§6 rebalancing motive; §12 C | Principles yes; §6 maths is not GP | **FIX**: estimate φg half-lives; GP aim as comparator; cite Davis–Norman/Boyd for bands/MPC | HIGH |
| MM w22208 | §5/§12 C vol policy (+Cederburg contra) | Yes; best pro/contra pairing in Plan | **KEEP pairing; DROP raw 1/RV sizing** under 200% cap; retrieve Cederburg full text | MEDIUM |
| Chapados / Goyenko–Zhang (no PDF) | §4 text/options branches | Unverifiable (abstract) | **FIX**: hypothesis only; EDGAR/options PIT replication required | MEDIUM |
| Ledoit–Wolf / Cederburg (no PDF) | §5 covariance / vol contra | Unverifiable (abstract) | **FIX**: retrieve full texts or label engineering defaults | MEDIUM |

\* BAB severity LOW in current Plan use, HIGH if any low-beta tilt is presented as idiosyncratic alpha to Arcana.

**Cherry-picking summary:** No outright misquotation was found — every grepped number exists in its .txt. Cherry-picking is by *omission and transfer*: (1) GKX wins quoted without 2016 endpoint/gross/reversal caveats in §4 design flow; (2) JKP 84.9% quoted without its construction bridge; (3) GP gradualism quoted without quadratic-cost/commodity scope. Conversely MM/Cederburg and JKP/HXZ pairings show the Plan *can* present contra evidence — extend that pattern to GKX and GP.

## 5. Missing literature for the finals problem (ranked by decision impact)

Searches run (8): short-term reversal costs; PEAD costs; sqrt-law impact; ML decay post-2020; borrow fees; TC-aware optimisation/no-trade; 8-K text drift; Frazzini–Israel–Moskowitz capacity. Fetched in full: Chen–Lopez-Lira–Zimmermann arXiv HTML (https://arxiv.org/html/2212.10317v5). SSRN fetch returned 403 (recorded as unresolved for full-text numbers; abstract via search snippet only). Peer-reviewed (PR) vs working paper (WP) flagged.

### Rank 1 — Will daily/weekly trading survive costs at $1bn? (Mandate §4 L234–240, §3.3 L175–187; Plan §6–7, E3/E4) [CRITICAL gap]
- **Frazzini, Israel, Moskowitz, *Trading Costs of Asset Pricing Anomalies* (WP 2012/2018, ~$1tn live AQR trades).** Actual costs ~1/6–1/2 of academic estimates; value/momentum scalable, **short-term reversal most constrained**; break-even sizes with 50–100bp tracking-error allowance. *Decision:* calibrates whether Plan's weekly book + daily exceptions can beat monthly net; supplies κ magnitudes Plan §6 lacks. (Search: stern.nyu.edu/~afrazzin; SSRN 2294498.)
- **Khandani & Lo (2007/2011), Nagel (2012, PR RFS) liquidity-provision reversal.** Daily Lehmann reversal profits decay secularly as capital crowds in; returns are compensation for liquidity provision, concentrated in illiquid/small names — exactly those excluded/capped by $500m floor + ADV limits. *Decision:* prior that a daily reversal overlay (natural GKX-tree extension) is likely net-negative at $4–10m tickets (Mandate L148–149). Plan must show reversal exposure explicitly in attribution.
- **Avramov, Cheng, Metzker, *ML vs Economic Restrictions*, Management Science 2023 (PR).** ML profits concentrate in difficult-to-arbitrage (small/illiquid/high-cost) stocks and benign limit-to-arbitrage states; often fail economic restrictions net of costs. *Decision:* direct haircut to GKX transfer; mandate-eligible subsample reporting (≥$500m shorts, ADV-feasible) required before promoting trees (§3.2).

### Rank 2 — Is the $500m-eligible short actually borrowable, and what does borrow predict? (Mandate §3.3 L189–192, §7 borrow disclosure L787–803; Plan §7 L267) [CRITICAL gap]
- **Cohen, Diether, Malloy (2007, PR JF) *Supply and Demand Shifts in Shorting*; Boehmer, Jones, Zhang (2008, PR JF); Drechsler & Drechsler (2016 WP, *Shorting Premium*).** High/rising loan fees (>5% p.a. → <−2% next month in CDM) predict low returns but also signal recall/squeeze risk; fee distribution is extremely skewed (most ~30–50bp, tail >10%). *Decision:* Plan's flat 50bp/5% sensitivity (L267, mirroring Mandate L800) is a disclosure floor, not a sizing input. Correct: size shorts by fee-aware expected net alpha `μi − bi·H/252` with recall stress; exclude/shrink hard-to-borrow tail even if ≥$500m. Pack contains **zero** borrow papers — largest single-topic hole vs Mandate emphasis.

### Rank 3 — Square-root impact calibration for Plan §6 κi (Mandate §3.2 L154–156 "impact, not commission, is binding"; Plan L194–199) [HIGH gap]
- **Kyle & Obizhaeva (2016, WP/Econometrica lineage) market-microstructure invariance; Bouchaud et al. propagator/sqrt-law empirics.** Impact `≈ Y·σ·√(Q/ADV)` with Y≈0.3–1.0 depending on participation/venue; distinguishes temporary vs permanent. *Decision:* gives Plan's `κiσi|qi|√(NAV|qi|/ADVi)` an estimable Y range and stress band instead of free κi; also implies cost ∝ NAV^{1/2} — compounding NAV (Mandate L182–187) *raises* unit costs, so capacity must be re-tested at ending NAV, not inception. Plan L245 arithmetic hints this; literature makes it quantitative.

### Rank 4 — Days-scale event drift: PEAD & 8-K text (Mandate §4 event response L223–225, §6.4–6.5, §11 earnings split L1108–1111; Plan E5) [HIGH gap]
- **Bernard & Thomas (1989/90, PR) PEAD; Ng, Rusticus, Verdi (2008, PR JAR) + Chordia et al. liquidity/PEAD costs.** Drift persists ~60 days gross but concentrates in high-TC firms; net PEAD profits "significantly reduced" by costs/impact. *Decision:* event overlay horizon is days-to-weeks ( tradable under t+1→t+2 clock Mandate L701–703 ), but only in liquid subset; naive SUE deciles overstate net.
- **Cohen, Malloy, Nguyen (2020, PR JF) *Lazy Prices* (10-K/Q text changes); Loughran & McDonald (2011, PR JF) dictionaries.** Text *changes* (not levels/sentiment) predict returns/fundamentals; negative-word measures dominate. *Decision:* supports Plan's "fundamentals-oriented text" (L141) over generic sentiment, but horizon is months (periodic filings), not daily 8-K timing — keep 8-K for timing, 10-K/Q for content per Mandate L543–548. Pack has no filing-drift paper; Chapados abstract alone cannot set holding period.

### Rank 5 — Post-publication & post-2020 decay haircuts (Mandate OOS 2021–26; Plan §9 researcher contamination L309) [HIGH gap]
- **McLean & Pontiff (2016, PR JF)** — already in Plan L435 but *unread*. Post-publication decay ~58% (32pp statistical + publication effect in original). Retrieve full text; it is the quantitative prior for "do not budget full premium".
- **Chen, Lopez-Lira, Zimmermann, *Does Peer-Reviewed Research Help Predict Stock Returns?* (WP 2022, arXiv:2212.10317, fetched).** Post-sample decay ~42% overall (53–58% remains depending weighting); risk-based predictors decay extra ~29pp. *Decision:* apply 0.4–0.6× haircut to any pre-2021 backtest alpha when setting σmax/gross targets; report 2021–26 subperiod stability (Plan E-ladder) rather than full-sample IR alone. Also note **Jensen et al. JF 2023** published version vs w28432 — use WP for pre-2021 method integrity (§3.1).

### Rank 6 — TC-aware optimisation theory Plan §6 actually needs (Plan L241 MPC remark) [MEDIUM gap]
- **Davis & Norman (1990, PR) / Constantinides proportional-cost no-trade regions; Lobo, Fazel, Boyd (2007) portfolio optimisation with costs; Boyd et al. multi-period trading via convex optimisation (2017 monograph/WP).** *Decision:* correct citation home for hysteresis bands, L1 costs, and receding-horizon MPC with forecast decay + participation constraints. GP (quadratic) + these (proportional/convex MPC) together span Plan's hybrid; citing GP alone misattributes the band logic (§3.5).

### Rank 7 — Daily-horizon predictability null (Mandate §4 noise warning L241–243) [MEDIUM gap]
No pack paper estimates 1-day cross-sectional R²/IC decay. Before any daily signal work, establish the null on own validation data: IC(H) for H=1,5,21 days per family with t+1/t+2 clock, gross vs net of Rank-1 costs. Literature expectation (reversal/liquidity microstructure) is that fundamental families have ~zero 1-day IC — Plan's monthly-core/weekly-trade default (L9) is consistent, but currently asserted, not evidenced. One validation exhibit (IC decay = GP φg) simultaneously satisfies Mandate alpha-decay diagnostic, GP aim weights, and E4 promotion test. Highest value-per-hour empirical addition.

## 6. Required edits to Plan (checklist)

1. §3 L55: specify which 84.9%; add construction bridge; keep CAPM-vs-Arcana warning. [MEDIUM]
2. §4/§12 GKX row: add "OOS ends 2016, monthly gross, reversal-heavy; see Avramov/FIM haircuts". Gate trees on mandate-eligible net IR only. [HIGH]
3. §6: add φg estimation + GP-aim comparator; cite Davis–Norman/Boyd for bands/MPC and Kyle–Obizhaeva/FIM for κ calibration ranges; stress κ×2 at ending NAV. [HIGH]
4. §7: replace flat borrow sensitivity as *sizing* input with fee-distribution-aware sizing + recall stress; keep flat case as Mandate disclosure. Add borrow refs Rank 2. [HIGH]
5. §9: name BH-FDR/deflated-Sharpe procedure; commit denominator reporting per Mandate L356–360; apply McLean–Pontiff/Chen decay haircuts to target-setting (not to reported OOS returns). [MEDIUM]
6. §12: retrieve full texts for Cederburg, Ledoit–Wolf, McLean–Pontiff, Chen–Zimmermann *Open Source* (FEDS PR-adjacent) or downgrade dependent choices to defaults; split WP vs published years. [MEDIUM]
7. New validation exhibit: per-family IC decay H=1/5/21 gross/net — feeds GP φg, E4/E5 promotion, Arcana alpha-decay answer. [HIGH value]

## 7. Methods & unresolved gaps

Methods: read README/manifest in full; head-identified all 10 .txt; grep-verified 6+ claims with .txt line numbers above; read Plan (484 lines) and Mandate (1168 lines) in full; 8 web searches + 2 fetches (1 success, 1×403). Unresolved: (a) Chapados/Goyenko–Zhang/Cederburg/Ledoit–Wolf full texts not in pack and not fetched — verdicts rest on Plan's own "abstract only" labels; (b) JF-2023 JKP vs w28432 numeric diff not diffed (no JF PDF in pack); (c) Carbon Arc workbook/panel schemas not inspected (Plan L289 same limitation) so vBHL data availability remains conditional; (d) SSRN full-text numbers for reversal-cost paper unavailable (403) — Rank-1 magnitudes rely on search abstracts + FIM summaries, flagged WP status accordingly.
