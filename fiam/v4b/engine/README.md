# Monthly controller and validation ladder

Read `../DECISIONS.md` first. E-LASSO MaInf remains primary; Ma1 can replace
it only through the net-performance and process gates. D7 calibration and
D8 risk settings are unchanged. No 2021+ returns are used here.

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -m fiam.v4b.engine.ladder --force
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest fiam/v4b/tests -q -p no:cacheprovider
```

`--force` rebuilds every target. Otherwise a target cache is usable only when
its metadata matches the mandate, step, engine/risk/forecaster source files,
forecast file and input identities. E0, E1, E2, the Ma1 trial and E3 are five
configurations; debugging reruns do not select additional settings on returns.

Targets are built at signal close inside the simulator, from actual executed
holdings and compounded NAV. Trades execute at the next close and earn only
subsequent returns. ADV, spreads and volatility are available before that
execution close. Missing short quotes leave the liability frozen with borrow
accruing. The 21-session forecasts, covariance and borrow costs are converted
to the same actual number of sessions to the next monthly review.

Stage 0 sees exposure limits before fixing signs. Greedy scores subtract
constraint shadows so a whole-sector forecast intercept cannot dominate
stock selection. Failed support may expand up to 500 names; the solver logs
that change, gross reductions and minimum-size relaxation. It never discards
solver dust to pretend a changed book still meets its constraints.

The report preserves hard breaches, daily beta/sector/size diagnostics,
accounting checks, independent monthly cohort reconciliation, paired-block
IR intervals, 2019 selection/2020 confirmation, gross-scale diagnostics,
half-ADV stress and 0.5/1/2 spread sensitivities. A failed predecessor cannot
be skipped. A noncompliant run cannot be promoted. If the fallback also fails
its process checks, `ship` is null. Failed gates are evidence, not thresholds
to tune away.

Evidence is saved in `../out/engine/`: `manifest.json`, `ladder.json`, target
weights and their solver logs, actual positions with signed dollar trades,
unfilled orders and synthetic long exits, daily NAV/cost ledgers, monthly
active returns, breach rows and policy exposure histories. Stress and spread
runs have their own ledgers and positions. Stock P&L is independently checked
by closed-form monthly compounding of actual trade cohorts; interest and cost
lines remain ledger inputs with separate hand-calculation tests.

This is the monthly E0–E3 stage. Weekly review/daily repairs (E4), alternative
data/agent experiments, full finals reporting and final OOS freeze are later
stages in REVISED_PLAN. `ready_for_freeze` and `ready_for_oos` remain false.
The risk report's 1.29–1.51 volatility-bias caveat is carried into ladder output.
