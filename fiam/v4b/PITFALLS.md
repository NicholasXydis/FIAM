# Pitfalls to not repeat — checked against E6 (2026-10-26)

Sources read: this folder (HANDOFF_2026-10-26, DECISIONS D1–D18, LESSONS, REVISED_PLAN,
CONTINUATION_PLAN, RETURNS_AUDIT, RISK_COST_AUDIT), the docs branch
`origin/feat/constructions-docs-drew` (`docs/CONSTRUCTION.md`, `ACCEPTANCE.md`,
`BACKTESTING.md`, research `Final conclusions.md`), v4 (`RESULTS.md`, verdict r13,
STANDING-ORDERS, EXTERNAL-REVIEW), QUARCC black (Exp14 audit, Exp15/15b/16 ledgers) and the
ctanny notebooks. Papers are linked where cited.

Each row: the mistake, where it happened, and how E6 handles it today.

## A. The signal binds; construction does not create alpha

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| A1 | Treating a better optimiser as a fix for a weak or negative signal | v4b E3 2021+: MaInf IC −0.033 (t −2.5) from Jan 2021 (RETURNS_AUDIT); v4 r13 verdict; QUARCC Exp15 "economic edge did not track ranking" | D18 item 5 says step 2 cannot create alpha. E6 is judged only on 2017–2020 against the D17 winner |
| A2 | Concentrating in the extreme deciles | Lesson 98: on 2021–26 D9/D0 earned nothing; deciles 4–7 carried the IC | **Open risk.** HHRZ deciles are exactly the extremes. Hysteresis (D8/D1 holders stay) widens the book a little. If the screen passes, the 2021–26 look will show whether extremes revert again |
| A3 | IC gains that don't move the book | QUARCC Exp16: attention +0.020 IC, book −0.0001; v4: ML IC t 2.5–4.1, all lost money after costs | The screen scores books net of per-name costs, never IC |
| A4 | Hurdle: a neutral book needs residual IC ≈ 0.031–0.039 to beat T-bill + 4% | CONTINUATION_PLAN §2.1 | Report the IC alongside each E6 book |

## B. Selection on viewed data (D16)

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| B1 | Picking the max of many settings: best of 96 adds +0.04–0.06 IC from luck | CONTINUATION_PLAN §2.3; v4 "+1.78 where searched, +0.33 unseen" | 8 variants, rule written before any return (D18). Registry +8 +1 |
| B2 | Choosing anything on 2021–26 | v3 60/40 sleeve (ban list X9) | 6-month smoothing came from an in-sample 2021–26 screen. **Disclosed in D18 item 3**, and it is only 2 of the 8 variants |
| B3 | Reusing 2017–2020 so often it stops being a holdout | RETURNS_AUDIT #8: 82 configurations | Count E6 in the registry. 2019 vs 2020 swings are noise unless they fall outside ±0.029 IC/yr (CONTINUATION §2.2) |
| B4 | Rescuing a failure by sign-flip, overlay or tuning on OOS | RETURNS_AUDIT decision; regime overlay | If E6 fails D18, stop and ask the user (D18 item 4) |

## C. Beta neutrality and the short leg

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| C1 | Ex-ante beta 0 but realised beta drifts (**E6 W: +0.16..+0.23; predicted betas compressed, slope 1.76**) | Branch N=250 book: ex-ante 0.000, realised sd 0.069, corr −0.10; E3 max hedge beta 0.147 | Report **realised daily beta** in the Nautilus run, not the forecast. D18 gate is |daily beta| ≤ 0.05 |
| C2 | A full dollar-neutral short book turns weak short ranking into exposure | QUARCC Exp15 §11; v4b E3 short leg lost 5 of 6 years | E6 holds net within the hard ±0.5 band (Amendment 1a), so beta is hedged with dollars as in BAB ([Frazzini–Pedersen](https://conference.nber.org/confer/2010/BEf10/Frazzini.pdf)). Watch the [Novy-Marx–Velikov critique](https://mysimon.rochester.edu/novy-marx/research/BABAB.pdf): leveraged low-beta longs bring size and cost loads |
| C3 | Judging shorts on raw P&L | CONTINUATION X5 | Legs are judged on alpha vs the cap-weighted holdable pool, after beta |
| C4 | Global tails leave sectors one-sided; the optimiser then breaks sector bands | Lesson 45; E6 smoke (sector slack 8–11%) | Fixed: within-sector deciles (Amendment 1b), with a test that every sector is two-sided |
| C5 | Weighted penalties reversing the priority (beta first) | docs `CONSTRUCTION.md` §1: lexicographic | E6 has both a hard beta band (accepted only if the slack ≤ 1e-6) and λβ. The band is the priority, so this is fine |
| C6 | A fixed name set can't add hedge names | docs `ACCEPTANCE.md` "expansion" | **Known E6 limit.** Raw scores give up gross (1.0–1.5) to neutralise beta. Logged as `ladder_gross` |

## D. Costs and execution

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| D1 | Flat cost rates | v4 standing orders | Per-name model: half-spread, sqrt impact over 5 days, fees, borrow |
| D2 | Turnover eats the edge: E3 3.9%/yr costs turned IR +0.58 gross into −0.14 net; ML strategies lose ~57% to costs ([Azevedo–Hoegner–Velikov](https://quantpedia.com/the-expected-returns-of-machine-learning-strategies/)); the average anomaly nets ~8 bp/month ([Chen–Velikov](https://www.federalreserve.gov/econres/feds/zeroing-in-on-the-expected-returns-of-anomalies.htm)) | RETURNS_AUDIT #6 | Hysteresis is the best mitigator ([Novy-Marx–Velikov 2016](https://www.nber.org/papers/w20721)); E6 has it. Report the cost per year and turnover per variant |
| D3 | Targets that are not executed compliance (gross 2.27, names 611, beta 0.147) | E3 RETURNS_AUDIT #5 and the 2021+ book | Union room 490, names room 440, gross ≤ 1.8. Only the Nautilus run proves compliance; check breach counts there |
| D4 | A fixed $10m NAV in impact | docs `Final conclusions.md` §4 | Nautilus runs $1bn compounding |
| D5 | Missing returns set to 0, or synthetic exits | RETURNS_AUDIT #4; docs §4 | The screen fills missing `ret_exc_lead1m` with 0 (as stage2 did). **Disclosed**; the Nautilus run handles exits |
| D6 | Paying costs to scale a weak signal | Lesson 97: volscale gross 0.85 did not pay | E6 floor is scale-invariant (ρ·μ'w_ref), so no slope calibration sizes the book |

## E. Risk numbers

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| E1 | Predicted vol understates realised by 1.3–1.5× | D8 vol bias 1.29–1.51; ctanny: a normal model understates CVaR 1.4–1.6× | Report predicted vs realised vol. The 12% cap never binds at 3–4% predicted vol |
| E2 | Running at 5% vol cannot reach 12.8%/yr even with a good edge | Lesson 99 | **Structural.** E6 predicted vol is 3–4%. A beta-neutral book at this IC can't match v4's return without leverage the mandate forbids. Say so in the deck |
| E3 | No static comparator | ctanny | The D17 E5 holdings through the same simulator are the yardstick |

## F. Process

| # | Pitfall | Where it happened | E6 status |
|---|---|---|---|
| F1 | Paid remote runs dying on spend limits | QUARCC 15b/16 | Modal CPU, small smoke first |
| F2 | Code drifting from the decision text (E6 copied net 1e-6) | E6 Amendment 1a | Amended before any return was seen |
| F3 | Mislabelled fields | docs (`niq_su`) | n/a for E6 |
| F5 | Racing full-window books before each component earns it | E6 screen launched first, sealed under D19 | D19 gates: G0–G5 on 1–2 months, with ex-ante power; an underpowered gate fails |
| F4 | Optimiser solutions "repaired cosmetically" | docs `CONSTRUCTION.md` §2 | Report failed formations (`failed`) and the ρ/gross ladder rungs used; don't hide them |

Construction papers behind E6: HHRZ spread portfolios
([RoF 2024](https://ideas.repec.org/a/oup/revfin/v28y2024i6p1807-1831..html)); the
implementable frontier ([Jensen–Kelly–Malamud–Pedersen](https://papers.ssrn.com/abstract=4187217));
characteristics and trading costs ([DeMiguel et al. 2020](https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2180-2222..html));
the transfer coefficient ([Clarke–de Silva–Thorley 2002](https://ideas.repec.org/a/taf/ufajxx/v58y2002i5p48-66.html)),
which explains why step 2 reweighting lowers alpha per unit of exposure, and why ρ < 1 costs return.
