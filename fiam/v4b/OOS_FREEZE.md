# 2021–2026 diagnostic freeze — 2026-10-23

This file records the one 2021–2026 evaluation. It is **not** a final-book
approval. E3 remains noncompliant on executed gross, name count and
liquidation capacity in 2017–2020 (D9), so the 2021+ run is labelled
diagnostic throughout. No 2021+ result was used to change a coefficient,
band, cost, or model choice.

## Frozen object

| Item | Frozen value |
|---|---|
| Strategy step | E3: greedy support, exposure bands, uncertainty term, trade costs, incumbent credit, borrow term, support request 250 |
| Forecast column | `Elasso_MaInf`, centred and calibrated by D7 |
| Forecast coefficients | Last rows at 2020-12-31 of `coefLasso`, `coefUniIntercept`, `coefUniSlope`, `coefGr`, `coefEncompass` |
| Forecast construction | S-LASSO MaInf = mean of all coefficients through 2020-12; C-LASSO = frozen 2020-12 univariate intercept/slope and `coefGr` selection; E-LASSO = frozen 2020-12 `MaInf` encompassing weight (0.59419) |
| Risk model | D8: factor half-life 84, EWMA-168 specific, 25% sector shrink, 5% floor; `cut=2026-08-31` |
| Costs | 5 bp commission, 27.8 bp SEC on sales, half-spread, 5-session square-root impact with `Y=1`, flat borrow schedule |
| Universe | `long_ok` / `short_ok` from the panel; no 2021+ eligibility rule added |
| Formations | eom 2020-12-31 through 2026-07-31 (68 monthly books) |
| Execution | Native NautilusTrader 1.230.0 orders, fills, positions and account state; 5-session working |
| Initial NAV | $1,000,000,000 |

The last coefficient row is used for **every** OOS month. The authors' model
is rolling; freezing is the only construction that does not fit on 2021+
returns. It answers a narrow question: what did the 2020-12 model earn after
2020? It is not the live rolling E-LASSO process, and its result must not be
reported as the performance of a monthly-refit model.

The forecast formula was validated exactly against the authors' R output for
target 2020-12 using coefficients through 2020-11: S, C and E matched to
machine precision (max difference 1.8e-15). `elasso/oos.py` is that frozen
application.

## Data

- 2015-01-02 through 2025-12-31: `data/fiam_v1/daily_market.parquet`
  (organisers' daily CRSP prices, total/price returns, volume, bid/ask).
- 2026-01-01 through 2026-08-31: `data/fiam_v1/daily_market_2026.parquet`,
  a **proxy** built from the monthly panel. The execution path is a
  split-adjusted **total-return index**: monthly `ret` is compounded exactly
  and `prc/adjfct` supplies only the starting level. The mini file's raw
  `daily_return` and raw `close` are not used for execution. `dolvol_126d`
  supplies ADV and `bidaskhl_21d` × the 2015–2020 size-group ratio supplies
  the half-spread. The D5 splice ratio and FINRA ADV verification were not
  applied; 2026 is a proxy label, not quote-verified data. See the amendment
  below for the first-run defect and the rebuild.
- Feature cross-sections: `chars_final_with_names.parquet`, GHZ winsorise /
  standardise / missing-to-zero within each eom, exactly as
  `elasso/build_input.py`; no post-2020 label enters a coefficient.
- ADV and spread for 2021–2025: daily quote/volume data; 2026: the proxy
  above.

## Forecast limitation found before the run

The frozen MaInf cross-section has a **negative** 2021–2026 rank IC against
the realised next-month total return (mean −0.033, t ≈ −2.47; 2022 −0.082,
2021 −0.047, 2023 +0.001, 2024 −0.026, 2025 −0.015, 2026-to-date −0.024).
The in-sample 2017–2020 IC on the same panel is +0.031. This is a frozen-model
result, not a claim that a rolling refit would also invert. It does mean the
2021+ book is being asked to earn a cost drag on a signal that was wrong in
several regimes. That is a finding about predictability, not a reason to
change the run after seeing it.

## Run

```
fiam/v4b/.venv/bin/python -m fiam.v4b.research.run_nautilus --oos --steps E3
```

Output: `fiam/v4b/out/nautilus_oos/` (`summary.json`, `yearly_performance.csv`,
`manifest.json`, daily holdings and NAV, breaches, policy exposures). Native
orders/fills/positions/accounts CSV and tearsheet export were disabled for
this run to bound memory; the ledger and holdings are still built from native
Nautilus fills and account state. The run is a single pass; no parameter was
changed after it started.

## Amendment 2026-10-24 — 2026 split adjustment and re-run

The first 2021–2026 run is preserved at
`out/engine/nautilus_oos_invalid2026.log` and `out/nautilus_oos_invalid2026/`.
It used the 2026 mini file's raw `daily_return`/`close`. Those values are not
split-adjusted; the run created spurious split jumps and overstated the 2026
loss. It is not a valid 2026 result and must not be cited as one.

The 2026 proxy was rebuilt as a split-adjusted total-return index from the
monthly panel `ret`; `prc/adjfct` is used only to set the starting level.
Every 2026 stock-month compounds to panel `ret` with maximum absolute error
2.0e-14. The 17266 July 2026 panel return is +0.927332 and is reproduced
exactly; the adjusted-price move for that row is internally inconsistent but
does not create an execution split jump because the synthetic path uses `ret`.
The boundary 2025-12-31/2026-01-02 maximum move is 13.8%, an ordinary daily
return, not a split.

The corrected run first reached 2026-07-31 but was killed during native report
rendering (`nautilus_oos_corrected_native_report_kill.log`); it produced no
ledger. The reported run is `nautilus_oos_corrected.log`, with native report
export disabled. The 2021–2025 monthly NAV path is exactly equal to the first
run (maximum absolute difference 0.0); only 2026 changes (Jan–Jul invalid −14.08%, corrected −8.72%).

## Hashes (SHA-256)

```
source_identity  5196f3b47233f57b46d9755af1ebadfca679fa22604a765dd5fb86b19de16980
optimize.py      c346504e149a1330b73522c48dd09edc0e3933475d014f38a9666458066e01cc
ladder.py        b0db9983263b82c144e20fdb3b79f0ed4acf23a058e2cc1df7464c8074ae3306
inputs.py        f37a06743a5697119c8d324b3e679bc9e086e9b5bc2193edf2c07230dcb12a9d
nautilus_data.py 3bf734abb1e619e7d6294ad21b62d79eb128c45c0edee1c1af2c9b237432df72
nautilus_backend.py 42ff61c459fe9ce04425867102791e10c362508b7ef4822568ec11416c58407d
nautilus_reports.py 3ab13a0932c5980d8e1b6f4ebd0e26c3fa2f10aae11d0b697f0c1135604a2ed6
oos_data.py      37c19e279f3ac5c59c7a63651d166b4c6f3c5f23d0fdbd6633c249358e6edc06
elasso/oos.py    595317ff6ad0ffdce1c906800012b7a2b0b846f42a51aa68b47c43cda216ad38
forecaster.py    90b4954fc6d46051b2c789d160bc57df2664d5e1efabbaebbaf901d0b65b5116
run_nautilus.py  be10228c89bbe22fcad9590bc910a86d13edd27f0b58de1eecb58746c97a9896
final_2026.json  ce483c7af52e7f2bb440463206b6bba089ce6c2e75b191ab9da45dad8b09ba4d
daily_market_2026.parquet df2f5b8d674e523b11b858394e974826b0aa3d9b01264e32f14d5d9fed19c642
forecastElasso_oos.parquet 36324eede0275c2417bdf417ecb1e836bb42086c42d9ccb1bbcb7c53e1fdcb89
coefLasso.parquet 4637df5a43ae3c2681d89b6908baf814c6adcfaabaf0589802a835cd1b4458c9
coefUniIntercept.parquet 62d60b9d389abd40bf2c7a565c8a32eb55216ce9d889c4b0204e06580b3a782b
coefUniSlope.parquet 8e72e5479936d6e8a99634d6f188742a03491cede3b8d7f3f4e90efa820187b0
coefGr.parquet   48108c7845d320230d232d54857a3d78dfbd4979b871623dde36c4039875b990
coefEncompass.parquet 4d6d65587123a4ace94c4bbcc88f3ecfaf30aac03ffc46f1fdb9b7f46440028b
```

Results and the non-promotion decision: `OOS_RESULTS.md`.

Repository HEAD: `b5bdf0d9e0eec6238bb81f04095bf4debf14d38d`. The v4b tree is
untracked in this checkout, so the file hashes above, not the commit, are the
provenance.
