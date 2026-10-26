# Stream 1 — Mandate fidelity: Taildrop plan vs FINAL mandate

**Sources opened in full:** [final_mandate.txt](/home/drewclaw/Forkfiam/fiam/v4b/inputs/final_mandate.txt) (1168 lines, extracted from the Final Challenge Instructions PDF), [FIAM_Final_Case_Research_and_Implementation_Plan.md](/home/drewclaw/Forkfiam/fiam/v4b/inputs/FIAM_Final_Case_Research_and_Implementation_Plan.md) (484 lines; §§1, 2, 11, 14 read closely, rest skimmed for cross-references), all `mandates/*.json`, [fiam/mandate.py](/home/drewclaw/Forkfiam/fiam/mandate.py), all `versions/*/recipe.json`, [fiam/book.py](/home/drewclaw/Forkfiam/fiam/book.py), [fiam/v2.py](/home/drewclaw/Forkfiam/fiam/v2.py) (mandate-relevant parts), [fiam/benchmarks.py](/home/drewclaw/Forkfiam/fiam/benchmarks.py), [fiam/costs.py](/home/drewclaw/Forkfiam/fiam/costs.py), all of `fiam/checks/` (`verify.py`, `reproducibility.py`, `compare.py`, `provenance.py`, `wrds_checks.py`), and `ls` of `data/finals_2026/`. Past repo work is treated as evidence only.

**Severity scale:** CRITICAL = breach/disqualification or wrong headline if shipped as-is; HIGH = mandate requirement unmet or untestable; MEDIUM = over/under-constraint or deck risk; LOW = completeness/wording.

**Top line:** The plan's *prose* translation of the mandate (§2, §10, §11) is unusually faithful — every hard number is transcribed correctly and inherited round-one settings are explicitly disowned (plan L49). The fidelity failures are almost all in the *repo machinery the plan will inherit*: no finals mandate file exists, the compliance checker still enforces round-one numbers, the $500m short floor has no side-specific implementation or checker, and capital is hard-coded at $10m, not $1bn compounding. Plan §11 step 1 ("convert §2 into a versioned configuration") is therefore load-bearing, not bookkeeping. Verdict on the plan document itself: **keep with fixes**; verdict on running current repo code under it: **do not — CRITICAL gaps below.**

---

## 1. Every hard number, checked

| # | Mandate (final_mandate.txt) | Plan | Verdict | Repo evidence |
|---|---|---|---|---|
| 1.1 | **200–500 names, long+short combined** — §2 table L70, §3.1 L114, rationale §3.2 L136–160 | §2 L37 correct; §6 L211–217 two-stage support (~300, min 0.10% NAV, no padding) | **KEEP** plan; **FIX repo CRITICAL** | See §3 below: every repo artefact still says 100 |
| 1.2 | **Single position ≤5% of capital** — §2 L73, §3.1 L123; "backstop… expect to be asked to justify" near it, §3.2 L149–152 | §2 L40: 5% rule + internal 1% start, labelled policy L49 | **KEEP** (1% is defensible over-constraint, see §2.2) | No checker exists (§4) |
| 1.3 | **Gross ≤200%** ("up to", leverage ≤2×) — §3.1 L116 | §2 L38 "ceiling, not a target"; §6 L206 `‖w‖₁≤2` | **KEEP** plan; **FIX repo HIGH** (equality, not ceiling) | `book.py:54,295`; `v2.py` solve |
| 1.4 | **Net −50%…+50% at all times; dollar neutrality natural centre** — §3.1 L118 | §2 L39 aim dollar-neutral, tighter internal band | **KEEP** | `rules_2026.json` net_band 0.5 ✓; others illegal (§3) |
| 1.5 | **Shorts only if mktcap ≥$500m at formation; longs unrestricted** — §2 L57–60, §3.1 L120–121 | §2 L41 wording exact, "eligibility ≠ locate" | **KEEP wording; FIX implementation CRITICAL** | Universe-wide screen, wrong threshold (§3) |
| 1.6 | **$1bn at OOS start, compounding, no flows** — §3.1 L111–112, §3.3 L165–187 | §2 L35, §7 L245–265: recompute vs current NAV | **KEEP** plan; **FIX repo CRITICAL** ($10m hard-coded) | `book.py:35`, `costs.py:40` |
| 1.7 | **OOS 01/2021–08/2026, strictly OOS** — §3 L103, §3.1 L129 | §2 L36 "freeze chronological ledger"; §9 walk-forward + contamination disclosure L309 | **KEEP** | 68-month checkers ✓ monthly only (§4) |
| 1.8 | **Benchmark 3m T-bill +4%/yr, month by month; supplied series; IR is headline** — §3.1 L127, §3.4 L210–211, §9.2 L941–945 | §10 L347–353 formulas exact, Sharpe-vs-IR distinction correct | **KEEP** (exemplary); **FIX repo MEDIUM** | FRED-pinned, not supplied series (§2.4) |
| 1.9 | **Any frequency daily→monthly; you choose and justify** — §3.1 L125, §4 L249–253 | §1 L9, §2 L42, §6 L239, §9 E4: monthly info / weekly review / daily exceptions, compared at identical costs | **KEEP** — exactly the credited answer shape | No daily simulator yet (plan §11 step 2) |
| 1.10 | **Realised beta judged by organisers at daily AND monthly; materially ≠0 = directional** — §3.3 L194–198, §9.1 L886–888, §9.2 L947–951 | §2 L44, §5 L160–168, §10 L353: forecast control + both realised with SEs | **KEEP**; note no numeric tolerance exists (§5) | Monthly-only gated check (§4) |
| 1.11 | **Turnover mandatory, prescribed formula** — §2 L86–87, §9.3 L956–967 | §10 L355 formula correct incl. leverage warning | **KEEP with one FIX** (prescribed annualisation must headline, §2.5) | Drift-aware recompute exists; no finals gate |
| 1.12 | **Standardised §9.1 table (one slide) + §9.4 exhibits (8)** — L871–924, L976–988 | §10 L357–359 lists full table + exhibits + inherited extras | **KEEP, minor FIX** (benchmark column, §2.6) | `pack.py` is round-one format |
| 1.13 | **Arcana economic/factor review, 7 judge lenses; holdings every rebalance date** — §11 L1049–1151 (task brief calls this "sec 11") | §2 L46–47, §10 L361, §11 step 5 | **KEEP, one gap** (MCP path ignored, §2.7) | No Arcana code/schema yet — expected |
| 1.14 | **Agentic scope extended to construction + position-level risk; 6 design requirements** — §5 L254–396, §5.3 L369–389 | §8 L295–301 narrow explainer + restricted menu + counterfactual + cache | **KEEP core; FIX scope statement** (§2.8) | Agents exist; no finals counterfactual yet |
| 1.15 | **Forward bias = disqualification; daily clock t→close t+1→earn t+1→t+2** — §7 L671–730 (plan/task "sec 7"); agent PIT §8.2 L840–851 | §7 L271 clock exact; §8 L301, §9 controls strong | **KEEP**; §2 table omits it as a row (§2.9) | Monthly leakage checks only (§4) |
| 1.16 | **Carbon Arc optional: "opportunity, not obligation"** — §1 note L94–98, §6 L397–666 | §8 L287 "at most one incremental hypothesis initially" + 4-question gate | **KEEP** | `carbon_arc.py` switch gated on pre-registered test ✓ |

No hard number is mistranscribed in the plan. That includes the easy-to-miss ones: 200% as ceiling, "at formation", "month by month", combined (not per-leg) name count, and the 50bp/5% conservative borrow alternative (plan §7 L267 = mandate §7 L799–801).

## 2. Where the plan mistranslates, omits, or over-constrains

### 2.1 [HIGH] §2 is a translation table, not yet an executable ruleset
Plan §2 (L32–47) maps each requirement to an "implementation decision" in prose ("dated capitalization check", "much tighter internal band" — numberless). Three internal policies that determine compliance are never given frozen values anywhere: the net band `ε_net` (§6 L206), the beta tolerance split (nominal ±0.02 "candidate", §5 L168), and participation `p` (10% "proposed baseline", §7 L254). Plan §9 L340 rightly forbids inventing gates after seeing OOS — but that means these must be frozen *before* the validation ladder, in the versioned config of §11 step 1. **Fix:** the config file is a deliverable with a name (e.g. `mandates/final_2026.json` + policy annex), not a step description. Mathematically correct forms are already in the plan (§§5–7); they just need constants and checkers (§4).

### 2.2 [MEDIUM] Over-constraints that must be presented as costs, not compliance
All are labelled policy at plan L49 — good — but three interact with hard rules and need feasibility evidence in validation, not assertion:
- **Internal 1% cap** (§2 L40, §6 L214) vs 5% rule: at 200 names/200% gross, average |w|=1.0% — the internal cap *binds at the floor* and forces near-equal weights. Feasible, but it converts the mandate's backstop into the binding constraint; cost it explicitly (E1/E2 ladder can).
- **"Approximately 150 per leg"** (§2 L37): the mandate constrains only the combined 200–500. Forced symmetry is stricter and, with the short pool restricted to ~3,000–3,500 names ≥$500m (§3.2 L157–160), can force weak shorts. **Correct alternative:** constrain combined count + dollar/beta neutrality; let leg counts float, report them.
- **0.10% minimum size** (§6 L214) ⇒ gross floor 30% at 300 names (plan discloses, L217 ✓). Combined with "all-cash violates the count rule", emergency de-risking can breach either the count or the minimum. The plan's infeasibility hierarchy (§6 L227–231) handles this correctly in principle — **keep**, but the hierarchy order (hard rules before minimum-size policy) must be explicit so the *policy* yields first, never the mandate.

### 2.3 [MEDIUM] Short-floor drift: daily "disqualifying shorts" over-reads "at formation"
Plan §6 L238 monitors daily for "disqualifying shorts" and plans repairs. The mandate tests capitalisation *at the formation date* (§3.1 L120–121) only. Forced exit when a held short drifts below $500m is an over-constraint that manufactures turnover in exactly the falling names a short book profits from. Plan §11 L404 already lists "treatment after passive cap drift" as a clarification — **keep the question, fix the default**: test at initiation and at any *increase*; passive drift alone triggers no trade (log it). Correct encoding as an optimizer bound, per formation date t: `w_i ≥ −cap_i · 1{me_{i,t} ≥ 500}` for new/increased shorts, `w_i ≥ min(w⁻_i, 0)` (hold-or-cover only) otherwise — cf. the existing hold-or-shrink pattern for banned shorts at [fiam/v2.py:375-377](/home/drewclaw/Forkfiam/fiam/v2.py:375).

### 2.4 [MEDIUM] Benchmark: supplied series vs repo FRED series; daily/monthly non-reconciliation
Plan §10 L347–351 is mathematically exact: `b_m = TB3MS_m/1200 + 0.04/12`, `b_d = TB3MS_d/25200 + 0.04/252`, IR `=√K·mean(a)/sd(a)`, Sharpe over cash (not cash+4%), CAGR from ending NAV. **Keep.** Two implementation traps the plan names only in passing: (a) mandate §9.2 L943–944 promises an identical supplied benchmark series — headline IR must use *it*, while [fiam/benchmarks.py:93](/home/drewclaw/Forkfiam/fiam/benchmarks.py:93) (`rf = tb3ms/100/12`) and [fiam/checks/verify.py:49](/home/drewclaw/Forkfiam/fiam/checks/verify.py:49) recompute from pinned FRED; keep the recomputation as reconciliation (plan §2 L43 ✓), not as headline. (b) [fiam/book.py:440-442](/home/drewclaw/Forkfiam/fiam/book.py:440) `information_ratio` subtracts only 0.04/12, valid solely because its `net` is already excess over cash at zero net exposure — false once NAV compounding, financing spread and non-zero net enter at daily frequency. **Fix:** one benchmark module implementing §9.2 literally, used by both book and checker.

### 2.5 [LOW] Turnover annualisation: prescribed figure must headline
Mandate §9.3 L961–963: annualised = average per-rebalance × rebalances/yr (252/52/12); holding period measured directly or `avg gross / annualised turnover` labelled approximation (L963–967). Plan §10 L355 adds "total turnover ÷ elapsed years" for irregular exception trades. Sensible diagnostic, but with weekly-plus-exceptions the *prescribed* multiplier is undefined — the deck must state which dates count as rebalances (plan says this ✓) and put the §9.3-conformant number in the §9.1 table, the alternative in a footnote. Otherwise cross-team comparability — the point of §9 — is lost.

### 2.6 [LOW] §9.1 benchmark column and one-slide constraint
Mandate §9 L867–868: the table is submitted "on one slide, for the strategy **and for the benchmark where applicable**" (ending value, cumulative/annualised return, volatility, Sharpe, drawdown, worst month/day have benchmark values; rows marked n/a at L884–924 do not). Plan §10 L357 enumerates strategy metrics without explicitly carrying the benchmark column. **Fix:** generate both columns from the supplied benchmark series compounded on $1bn; ending endowment for the benchmark is the allocator comparison §3.3 L172–173 asks for.

### 2.7 [MEDIUM] Arcana: plan prepares for the lens but ignores the offered tool
Against the seven judge lenses (§11 L1090–1114) plan §10 L361 covers factor-vs-residual ✓, sizing-vs-selection (identical-support equal-weight counterfactual, correctly caveated as non-causal) ✓, hit rate/win-loss ✓, signal decay ✓, earnings-window split ✓, stress ✓. Lens 2 — *when* an unintended exposure emerged and what drove it (L1095–1097) — needs dated exposure attribution, which the plan's daily monitoring can produce but never lists as an exhibit. **Fix:** add exposure-emergence timeline. Separately, mandate §11 L1072–1085 presents the Arcana MCP connector as "the shortest path" to a §5.1 agent; plan §8 builds the agent on home-grown deterministic outputs instead. That is defensible on point-in-time grounds (Arcana model vintages are unknown — plan §11 L371 asks exactly this ✓) but the plan never states the trade-off. **Fix:** one paragraph: Arcana for *ex-post* review/reconciliation; in-simulation decisions only from vintaged inputs unless Arcana confirms historical model vintages. Using present-day Arcana exposures inside a 2021 decision would be a §7 leak.

### 2.8 [MEDIUM] Agentic scope: second frontier silently dropped
Mandate §5 wants effort in two places: downstream risk layer (§5.1) and upstream Carbon Arc exploration (§5.2, incl. the three multiple-testing defences at L356–360: denominator, untouched holdout, rationale-before-test). Plan §8 implements only the first, narrowly. "One done well beats six gestured at" (L275–276) licenses this, and plan §9 L311 adopts the denominator discipline for all research ✓ — but the deck (§10 item 3/5, L1009–1016) will be asked what the agent did on data discovery. **Fix:** state the scope choice + denominator log as the §5.2 answer, or add the dataset-triage agent (cheapest of the four, L324–328) as documentation-only. Also omitted operationally: Carbon Arc's 20k tokens/day cap (§5.2 L319–320) belongs in the event-day budget. Plan §8 otherwise satisfies §5.3: code enforces (L299 "code re-solves and validates"), logging/caching by input hash ✓, exception triggers ✓, counterfactual (E6) ✓, and the honest "explainer never changed a trade ⇒ no return claim" (L301) ✓. **Keep.**

### 2.9 [LOW] Omissions from §2 as a standalone checklist
Covered elsewhere in the plan but absent from the §2 table a checker would be built from: disqualification rule and daily clock (§7); model-memory four expectations — release-date split, re-identification rate, smaller-model preference, ≥1 non-LLM signal (§7 L761–775; plan §8 L301 covers most); deck's 8 minimum contents and 10-minute format (§10 L1003–1022); Python/commenting (§12 L1158); cost-disclosure trio incl. "fees never enter the forecast" (§7 L797–803; plan §7 L267 ✓). **Fix:** extend §2 or add a compliance annex so §4's checker matrix has one source.

## 3. Repo `mandates/*.json` and code defaults vs the finals mandate (CRITICAL if reused)

There is **no finals mandate file**. `mandates/` holds round-one/hypothetical variants, every one illegal or wrong for the finals on at least one hard number:

| File | Finals violations |
|---|---|
| `rules_2026.json` (closest) | `names_min:100` (finals 200); no `name_cap` ⇒ inherits 1.5% (compliant but unstated); no short floor field set; gross 2.0 ✓, net_band 0.5 ✓ |
| `brief_2026.json` | `names_min:100`; gross 1.6 (compliant ceiling-wise, but see equality issue); no short floor |
| `case_2025.json` | `net:1.0` (150/50 — breaches ±50% band as a *target* neutrality claim and "market neutral"); `name_cap:0.10` **breaches 5%**; `names 100–300`; countries USA+CAN (finals: US only, §2 L50) |
| `130_30.json` | `net:1.0`; names 100–300 |
| `neutral_global.json` | names_min 100; CAN included |
| `long_only_2024.json` | long-only, names 50–100 — different product |
| `v1.json` | strategy text only; everything defaults (below) |

Code defaults compound this. [fiam/mandate.py:31](/home/drewclaw/Forkfiam/fiam/mandate.py:31) `names_min=100`; gross/name defaults inherit [fiam/book.py:54](/home/drewclaw/Forkfiam/fiam/book.py:54) `LIMITS gross=1.6, name=0.015` ("set with 2021-26 visible" — the file's own honest comment, and itself a §7-hyperparameter disclosure issue for any finals reuse). Gross is imposed as an **equality** (`side @ w == LIMITS["gross"]`, [fiam/book.py:295](/home/drewclaw/Forkfiam/fiam/book.py:295); same pattern in v2 solve), so plan §2's "ceiling, not target" requires a solver change to `side @ w ≤ 2` with the objective, not the constraint, deciding leverage — otherwise de-risking and the 0.10% minimum interact exactly as plan §6 L217 warns, silently.

**Short floor — the single largest repo/plan gap.** The only market-cap gate is universe-wide: [fiam/book.py:114](/home/drewclaw/Forkfiam/fiam/book.py:114) `me ≥ 300` for *both* legs, and mandate-level [fiam/v2.py:206-209](/home/drewclaw/Forkfiam/fiam/v2.py:206) `admitted()` filters the whole universe by `min_market_cap`. Setting it to 500 would (a) wrongly bar <$500m **longs**, which the finals explicitly leave unrestricted, and (b) still not encode "at formation" for held shorts. Leaving 300 in place permits $300–500m shorts — a direct breach. `short_ban` ([fiam/v2.py:122-134](/home/drewclaw/Forkfiam/fiam/v2.py:122): micro/nano or borrow ≥3% or options/event flags) is a different, stricter-in-places rule and no substitute. **Correct alternative:** side-specific bound in §2.3 above, using dated `me` at formation; keep any $300m long screen only as disclosed policy. Plan L49 correctly states no $300m final rule exists — but the code still carries one.

**Capital.** [fiam/book.py:35](/home/drewclaw/Forkfiam/fiam/book.py:35) `NAV=10_000_000`, [fiam/costs.py:40](/home/drewclaw/Forkfiam/fiam/costs.py:40) `Model.nav=10m`: whole-share rounding, per-share commission min/max, and square-root impact `√(value/ADV)` ([fiam/costs.py:154](/home/drewclaw/Forkfiam/fiam/costs.py:154)) are all calibrated 100× below the mandate and static rather than compounding. `fiam/exhibits/implementation.py:14` does sweep capital to 1e9, so the machinery to parameterise exists. Plan §7's capacity arithmetic (L245: 300 names ⇒ ~$6.67m avg; >3 days at 10% of $20m ADV) is correct and matches mandate §3.3 L175–180.

**Versions.** `versions/v1–v3/recipe.json` are closed round-one artefacts (v3 switches include `target10`/`voltarget` — the very 10%-vol targeting plan L49 disowns for finals; harmless as history, toxic if the v3 book is presented as finals-compliant). `versions/v4/recipe.json` is an empty "in progress" shell pointing at `fiam/v4/`, which currently contains only the USB/kit tooling (`kit.py`) — no finals strategy code. Consistent with plan §11 being prospective.

## 4. Is plan §2 testable today? Rule → checker matrix

Read: `fiam/checks/verify.py` (submission rules + headline recompute), `reproducibility.py` (22 leakage/reconciliation checks), `wrds_checks.py` (CRSP/Compustat audits), `compare.py`/`provenance.py` (run comparison/hashes — no mandate content), `fiam/mandate.py:check()` (internal consistency of a mandate *file* only — never inspects holdings).

| Plan §2 rule | Existing checker | Finals-ready? |
|---|---|---|
| US-only universe, PIT IDs | reproducibility: labels-backward-only, exits applied; wrds report-dates | Partial — monthly, no daily/CIK test |
| $1bn compounding NAV, capacity vs current NAV | **None** (costs reconcile monthly at fixed $10m) | **No — build** |
| OOS 2021-01…2026-08 | verify L13/L28–31 (68 first-of-months); reproducibility 68-month checks | Monthly ✓; daily/weekly holdings dates ✗ |
| 200–500 combined | verify L33 checks **100–500**; [fiam/book.py:460](/home/drewclaw/Forkfiam/fiam/book.py:460) asserts 100–500 | **Wrong constant — one-line fix each, plus mandate default** |
| Gross ≤200% | verify L34 at formation weights only; `exhibits/daily_risk.py` counts days >200% but does not gate | Formation ✓; "at all times"/drift path ✗ (mandate §3.1; daily data cannot prove intraday — plan §6 L231 honest ✓) |
| Net ±50% | verify L35 formation only; book asserts \|net\|<0.5% internal | Formation ✓; drift path ✗ |
| 5% single-name cap | **None anywhere** (verify has no max-\|w\| rule) | **No — build (trivial)** |
| Short floor ≥$500m at formation | **None** (§9.4 short-cap distribution exhibit also unbuilt for finals) | **No — build (needs dated `me` join)** |
| Frequency justified | N/A — evidence, not assertion: E4 comparison + alpha-decay exhibit | Plan covers; no code yet |
| Benchmark month-by-month, supplied series | verify headline recomputes IR/Sharpe/beta from FRED (monthly, `polyfit` beta **without SE**, L52) | Partial; daily beta + SEs + supplied series ✗ |
| Realised beta daily+monthly w/ SE | monthly: reproducibility L277–281 + wrds total-return variant w/ SE; daily: exhibits only, ungated | **Promote daily to a gate; add HAC SEs both** (book `regress()` L489 already HAC — reuse) |
| Gross/net-of-cost + conservative alternative | reproducibility costs-reconcile L285–289 (5 lines sum) ✓ monthly | Partial; 50bp/5% flat-borrow rerun ✗; daily ✗ |
| Turnover (drifted `w⁻`) | reproducibility L293–311 recomputes from holdings with drift ✓ — best existing template | Monthly ✓; generalise to arbitrary rebalance dates |
| Arcana lenses | None (attribution exhibits are round-one) | Build factor/residual + sizing/selection per plan §10 |
| Holdings every rebalance date (date, id, weight) | verify expects round-one `Date,PERMNO,TICKER,COMPANY NAME,WEIGHT` monthly (L12) | Schema unknown until event (§5); exporter must be schema-parameterised (plan §11 L400 ✓) |
| Forward-bias: feature dates ≤ formation | reproducibility: no-provenance-features, target-not-reshifted, within-month ranks, fold ordering, carry-in timing — strong monthly suite | Daily t+1/t+2 clock, vintage reconstruction, CA0035 date-only rule: **all unbuilt** |
| Agent §5.3 (code enforces, logs, cache, counterfactual) | provenance records agent model+hash per transcript (L94–102) | Partial; decision-log-vs-holdings effect check ✗ |

**Verdict [HIGH]:** plan §2 is *complete as a translation* (modulo §2.9) but *not yet executable*: roughly half its rows have no finals checker, and the two checkers that do exist for count/gross/net encode round-one constants or formation-only snapshots. The plan's own §9 "minimum acceptance checks" (L329–338) is the right spec for the missing suite — notably executed-book (not target-book) compliance with logged drift exceptions. Build order by breach risk: (1) finals mandate JSON + count/cap/short-floor holdings checks; (2) NAV-compounding ledger reconciliation; (3) daily clock assertion per join (mandate §8.1 L829–832 asks for exactly this, five lines per join); (4) daily+monthly beta gate.

## 5. Still unknowable until event-day clarifications

The mandate itself defers these ("further constraints and the final data configuration will be given at the start of the two-day event", L25–26, L1167). Plan §11 L402–404 lists most; complete set, with what to ask:

1. **Arcana holdings schema + risk-model vintages** (§11 L1150–1151: "format matters — specification will come"). Plan asks ✓ (L404). Includes: identifier expected (PERMNO? ticker? FIGI?), weight convention (% NAV vs fraction, signed?), and whether 20y of model history is point-in-time vintaged or current-model backcast (decides §2.7).
2. **Supplied benchmark series file** (§9.2 L943) — not in the folder (§6 below). Daily TB3MS alignment (monthly series carried to days?) is plan L404 ✓.
3. **Market-cap definition for the $500m floor**: security `me` vs company `me_company` (both in panel, USD millions per readme), measured at which close relative to the t→t+1→t+2 clock, and passive-drift treatment (plan L404 ✓; §2.3 default proposed).
4. **Daily price/volume/ADV source**: `dsf_mini_from_2014.csv` is returns only; levels via CA0065S or Arcana (§11 L1034–1036) — units, adjustment basis, and dated availability unconfirmed (plan §8 L283 gate ✓). Delisting/stub convention in dsf ("simply has no further data", L1033–1034) needs an explicit terminal-return rule (mandate §7 item 6; plan §7 L275 ✓).
5. **Borrow/locate reality**: no historical locate file is promised; only the disclosed-schedule + flat-alternative rule (§7 L787–803). Whether any finals borrow data arrives with Carbon Arc/Arcana is unknown.
6. **Initial deployment**: does the 200-name floor (and gross/capacity) bind during ramp from cash, and is formation cost inside OOS measurement? Plan §7 L256 raises ✓ — genuinely ambiguous in the mandate.
7. **Numeric beta tolerance**: mandate says "materially different from zero" (§3.3 L197) with no threshold, and S&P 500 series unspecified price vs total return (§9.2 says "S&P 500 excess return"; repo headline uses price-only FRED SP500, [fiam/benchmarks.py:80-85](/home/drewclaw/Forkfiam/fiam/benchmarks.py:80), while `wrds_checks` shows the dividend gap matters). Plan's ±0.02 + uncertainty SOC (§5 L163) is a sound internal policy — `|β̂ᵀw| + z√(wᵀU_β w) ≤ ε_β` is the correct robust form — but must never be sold as the compliance line.
8. **"At all times" granularity** for gross/net: close-to-close daily data cannot prove intraday compliance (plan §6 L231 ✓). Assume judged on submitted holdings + daily reconstruction; keep buffers.
9. **Submission package beyond deck+holdings** (§11 L1146–1151 lists only those two; plan §11 L400 `MAIN.py` is a round-one habit — confirm, don't assume). Also Carbon Arc onboarding/token budget in practice, and any event-day *tightening* (the reserve power at L25 cuts both ways: config must be re-diffed hour 0–2, plan §11 ✓).
10. **CA0086-style late-start data and revised Carbon Arc vintages**: entry rules are stated (§6.6 L620–623; §7 item 3 three acceptable treatments) — knowable as rules, unknowable per-asset until the workbook/catalogue is inspected (plan §8 L289 concedes not yet done).

## 6. Mandate §11 folder listing vs actual `data/finals_2026/` (ls, 23 Oct 2026)

§11 (L1028–1046) promises: core panel (147 chars + 8-K corpus), `dsf_mini_from_2014.csv`, Carbon Arc onboarding separately, `MCGILL_2026_CarbonArc_Data_Screen.xlsx`. Actual folder:

| Item | §11 status | Present? |
|---|---|---|
| `chars_final_with_names.parquet` (413MB) | Core panel ✓ | Yes |
| `8k_20150101_20260831_identified.parquet` (358MB) | 8-K corpus ✓ (survivorship defect disclosed §6.4/§11 L1038–1041; plan §8 L291 treats as contaminated ✓) | Yes |
| `factor_char_list.csv` | Implied by panel (147 list) | Yes |
| `dsf_mini_from_2014.csv` (518MB) | Named exactly L1032 ✓ | Yes |
| `MCGILL_2026_CarbonArc_Data_Screen.xlsx` | Named L1045 ✓ | Yes |
| Final Instructions PDF itself | Container document | Yes |
| Supplied benchmark series (§9.2 L943) | **Promised "with the data"** | **Absent** — unknowable #2 |
| Carbon Arc credentials/catalogue | "Sent separately" L1043 | Absent (expected) |
| Arcana instructions/schema | "During the event" L1053 | Absent (expected) |
| `readme.md` (27KB dataset guide) | Not listed in §11 | Present — useful; its timing warnings (filing timestamps are date/midnight placeholders; `ret_exc_lead1m` is future) align with §7 |
| `penalized_linear_hackathon.py`, `portfolio_analysis_hackathon.py` | Not listed in §11 | Present — organiser starter code, round-one vintage assumed; audit before reuse, do not treat as finals-calibrated |
| `ARCANA/Arcana Overview.pdf` + recording (.mp4) | Not listed in §11 | Present — pre-reading; does not substitute for event-day schema |

**Verdict:** folder matches §11 on every named data file; the one promised-but-absent artefact is the benchmark series. Two unlisted starter scripts are a (minor) trap if their embedded round-one constants are trusted. Note §11's merge instruction (L1033: on `permno` and *observation* date, "do not merge on forward date") — plan §8 L282 repeats it correctly ✓.

## 7. Sections 1, 14 (recommendation/decision) — fidelity notes

- §1's "what can actually be made predictable" table (L19–28) is mandate-honest: no constant-return or fixed-beta promise, hurdle as evaluation not obligation. Aligns with §3.4 (hurdle is a time series, ~4% in 2021 vs ~7.7% now) — worth quoting in the deck because it pre-empts the "why didn't you clear cash+4% every year" question. **Keep.**
- §1 L9 "delayed close-to-close convention" + §14 L474 "make daily trading earn its cost": the frequency stance is stated as architecture before E4 evidence exists. Mandate §4 credits the *tested* conclusion, not the prior. **Fix (wording, LOW):** present weekly-core as the hypothesis E4 adjudicates; if daily wins net of costs in validation, the plan must be willing to switch — §6 L239 already commits to "keep the simpler schedule unless additional net value is demonstrated" ✓, so this is presentational consistency between §1 and §6.
- §14's core claim — within-group selection surviving neutrality, costs and $1bn capacity is *the* empirical question — is precisely Arcana lens 1. No fidelity issue.

## 8. Consolidated action list

| Priority | Action | Where |
|---|---|---|
| CRITICAL | Create `mandates/final_2026.json` (200–500, gross≤2.0 ceiling, net target 0/band 0.5, name_cap 0.05 hard + 0.01 policy, US-only); retire/quarantine round-one JSONs for finals runs; fix `names_min` default path | `mandates/`, `fiam/mandate.py:31` |
| CRITICAL | Side-specific $500m-at-formation short bound (§2.3 form); remove/relabel universe-wide `me≥300` as policy-only for longs | `fiam/book.py:114`, `fiam/v2.py:206-209,360-377` |
| CRITICAL | Parameterise NAV: $1bn initial, compounding ledger through costs/rounding/impact | `fiam/book.py:35`, `fiam/costs.py:40` |
| CRITICAL | Finals holdings checker: count 200–500, max\|w\|≤5%, short-floor at formation, gross/net on *executed drifted* books | new/`fiam/checks/verify.py:33-35` |
| HIGH | Gross as inequality in solver; freeze ε_net, ε_β, participation in versioned config before ladder | `fiam/book.py:295`, plan §11 step 1 |
| HIGH | Daily t+1/t+2 clock assertions per join; daily+monthly HAC beta gate with SEs | `fiam/checks/reproducibility.py` (extend) |
| HIGH | Benchmark module per §9.2 (supplied series primary, FRED reconciliation); fix `information_ratio` shortcut | `fiam/benchmarks.py`, `fiam/book.py:440` |
| MEDIUM | §2.2 feasibility costing (1% cap at 200-name floor; drop forced 150/leg); §2.3 drift default; §2.7 exposure-emergence exhibit + Arcana-vintage stance; §2.8 scope statement | Plan §§2, 6, 8, 10 |
| LOW | §9.1 benchmark column; prescribed turnover annualisation headlines; §2.9 annex rows; §1/§6 wording consistency | Plan §§1, 2, 10 |

**Unresolved evidence:** Carbon Arc workbook/catalogue contents, Arcana overview/schema, dsf_mini schema/units, and starter scripts' internals were listed/readme-sampled but not opened in this stream (data/agent streams own them); event-day items in §5 are unknowable by construction. No performance claim in the plan was tested — the plan itself makes none (§8 L289), which is the correct posture.

