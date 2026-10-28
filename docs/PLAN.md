# PLAN: QUARCC Purple, McGill-FIAM 2026 finals

The rules and what is left to do, written so an AI agent can execute it exactly. `docs/TEAM.md` explains the whole project in plain English. Event: Wed-Thu 2026-10-28/29. Repo `/Users/nicholas/Code/Forkfiam`.

## 0. How to read and edit this file
- Read §1 (rules), then §2 (state), then work through §3 in order. §4 is the honesty record.
- Finished work leaves §3 (git keeps the history). Section numbers cited inside §1 (§6 to §16) point to the full plan before this rewrite, in git at `ba39bed:docs/PLAN.md`.
- After every step or decision, update this file and TEAM.md together. A decision changes only with the leader's approval.
- Every number shown to judges comes from an output file, named where the number is used. Code comments explain the code only.

## 1. Rules

### 1.1 Ground rules
- Never `git commit`, `git push` or stage. The leader commits whole files in GitHub Desktop. Propose titles only, `feat: ...`, no scope, no body. Pushing, merging, making the repo public and every Cloudflare step are [LEADER].
- Never modify: `/Applications/@Apps/Stock Data/` (raw WRDS archive, read-only, the only full copy since 2026-10-23, hashes in `data/v4/stock_data_sha256.json`), `deck/A_backup/`, `data/organisers/` or any copy of the organisers' files, `~/Downloads/OneDrive_1_2026-10-21/`.
- Never commit data rows (organisers', WRDS, Carbon Arc, EDGAR, Amazon) or `.env`. Never print a secret; never ask for or store a password. `data/*`, `.env`, `/research/` and the local rules file are gitignored. Tracked today: `data/benchmarks/*` (public series), `data/edgar_cache.zip`, and round-one outputs under `submission/`, including two WRDS-derived permno-month tables (`models/borrow.parquet`, `models/book_inputs.parquet`); `data/benchmarks/SP500.csv` and those two tables leave before the repo goes public, from a history-purged copy (§16).
- `.env` holds only `SEC_CONTACT` and `API_AUTH_TOKEN` (`.env.example` lists just these). Overrides, rarely needed: `FIAM_DATA_DIR` (another bundle; `--world` sets it), `FIAM_STOCK_DATA` (archive not at the default path).
- The finals PDF governs. A round-one rule applies only where the finals text is silent. Quote the exact words when citing a rule.
- Knowledge rule: finance research that shapes a choice is first public before 2021-01-01 (ML, statistics and engineering methods any date); no choice is decided from 2021-2026 results; what may be done with each period before the freeze is in §1.3. [2026-10-27, leader] After the unseal the leader revised the strategy (§2 REVISED STRATEGY); those changes were chosen after the 2021-2026 result was seen and are recorded as such.
- No coding-time estimates; work in §3's order. Report results exactly; a failing test is reported with its output.
- House style: one comment line of at most 72 characters above every function and block, saying what and why; ruff (E, F, I, W, 100 columns) and ruff format; type hints, `pathlib`, small pure functions, no hidden globals; every rule parameter named once.
- On-screen copy (site, film, deck, TEAM.md): no em or en dashes, colons, semicolons or Oxford commas; honest numbers only. Ask before any visible site or film change; visible changes are limited to §16.
- AI never sets a weight. Deterministic code enforces every rule after any agent (PDF p9).
- On a new machine run `uv run fiam doctor` first.
- Carbon Arc: every buy is priced first, approved and run by the leader; the assistant's tools never spend credits.
- Plan files: `docs/PLAN.md` (these rules and what is left) and `docs/TEAM.md` (the whole project in plain English) are tracked in git and carried in the kit; the local rules file stays local (gitignored). No other plan files. Whether the two plan files stay in the repo when it goes public is the leader's call. Public doc: `README.md`.

### 1.2 Banned inputs (the registry refuses each; a trap test each: data bans in step 3, the last two rows in step 6)
| Banned | Why | Use instead |
|---|---|---|
| The organisers' 8-K file and anything derived from it (counts, items, text) | Survivor-biased (A1, PDF p12) | EDGAR. Exceptions: its permno-CIK pairs as one input to the dated link table (B12), and the A1 comparison exhibit (coverage counts, never a signal) |
| `adjfct` (in `features_monthly`, not in the 147); Compustat `ajexq` and `ajex` (2026-10-25) | Encode future splits (A4) | Nothing; CRSP's dated `disfacshr` where a split must be undone |
| dsf `prc` as a filter, cap or feature | Split-adjusted to today: NVDA $0.50 in June 2015 vs $20.11 traded (B10) | Traded price: panel `prc` or CRSP `MthPrc`. Exception: `daily_book` reads it for the §6.4 gap ratio only (a ratio of adjusted prices is split-consistent), and step 5's integrity test counts sub-penny rows (counts only) |
| Any I/B/E/S field in a forecast, gate, rule or desk card | Levels on today's split basis, rounded (A3); the history was rewritten (Ljungqvist-Malloy-Marston, JF 2009) and we hold no older copy (B27) | Nothing (analyst revisions dropped 2026-10-23). Exception: the last consensus shown live, with its date, on the preview desk (B20) |
| Compustat `dldte`, `dlrsn` outside the dated exits table | Later deletion (A7, B11) | The exits table (§6.4) |
| Header fields: Compustat `gsector`/`gind`/`sic`, CRSP `HdrCUSIP`, current names and tickers as signals | Today's values (organisers' `readme.md` §7) | Panel monthly GICS (2015 on), CRSP monthly `SICCD`/`NAICS`, dated tickers and CUSIPs |
| `shortintadj` | Adjusted to a later split (independent audit M7) | `shortint` |
| `data/fiam_v1/wrds/*` (the retired research books only) | Not point-in-time; `compustat_quarterly` runs to 2026-09-22 with `dlrsn` | `data/v4/extracts/` |
| Key developments [REMOVED from every use 2026-10-24; the bans stay] `lastmodifieddate`, `mostimportantdateutc`, `speffectivedate`, ticker columns | Revision stamps, copies per ticker (A9) | `entereddateutc`, joined on gvkey |
| Amazon snapshot fields `average_rating`, `rating_number`, `price` | Current snapshot | Review timestamps |
| NOAA damage fields | Revised later (A17) | Event dates and counts |
| Any Carbon Arc series in the backtest (a forecast, gate, rule or backtested desk card), Benzinga (CA0035) included | Current vintage, weekly labels, drifting coverage, today's entity map (PDF p10-16; B29) | EDGAR, WRDS and the organisers' data. Exceptions: CA0065S dollar volume in the 2026 squeeze screens (§6.5, B30); live use only on the final book (Appendix B), such as the X-ray from owned data (§12.4 FINAL SET; the preview desk was cut 2026-10-26) |
| Any "has data" flag as a feature | A survival proxy (merge rule 4) | Nothing |
| Any cost or fee parameter in the forecast | PDF p17 | The construction layer only |

### 1.3 What may be done with each period before the freeze
| Period | Allowed | Never |
|---|---|---|
| Up to 2020-12 | Compute, view, test and choose: ML settings on 2019-2020, construction and AI choices on 2017-2020 (§8.0), the crash-control and squeeze tests on longer pre-2021 history (§8.4, §8.6) | Choosing with later data |
| 2021-01 to 2026-08 | Count rows, dates, coverage, schemas, hashes. Compute features in batch and store them sealed | Returns, signal-return links, performance, viewing sealed values, human hand checks, risk-desk agent cards, any exhibit with returns |
| 2026-09 on | As 2021-2026 | Anything else; the September book is scored once after the freeze |

- Blind mode is always on: every registered table refuses rows with `available_at` after 2020-12-31, and any label or outcome window (returns, 3-month labels, next-quarter SUE or sales, event windows) that ends, by availability, after 2020-12-31 is refused and its row dropped, never truncated (so `eom` 2020-12-31's January 2021 label is refused), except through the count and coverage functions; step 3 tests it. The v1 reader `fiam.data.panel` obeys it when v4 calls it; a test shows no v4 switch (signals, desk, overlay, crash control) can read a sealed row. The registry enforces it from step 3; `fiam.v4.data` inherits it in step 5. Only `finals --unseal`, after the hash check, lifts it (§13.3).
- AI calls on 2021+ inputs made before the freeze (the AI crowd's 2026-08-31 month, decided 2026-10-22) are stored sealed and read only after the unseal; the AI-crowd exhibit was cut on 2026-10-26 (§12.4 FINAL SET), so those answers stay sealed and unused.
- Hand checks of text (§7.3) and agent cards before the freeze use 2015-2020 filings only. The first step 4 pilot (2026-10-23) drew from every year and printed layout from a few 2021-2026 reports (about 20 customer strings, three cover openings, three Item 1A heading snippets, one report's item headings; no return, price or performance), disclosed in protocol.md; every development draw is pre-2021 since (`hand_checks.dev_rows`, ids logged); an independent check found every rule still in use format-only and every accuracy figure blind on 2015-2020 (`out/audit/pilot_reach.md`).
- Data-integrity checks may inspect 2021+ values without returns: glitches, nulls and units (§6.4), and agreement counts such as WRDS vs FINRA short interest on 2021-2025 and CA0065S vs CRSP volume flags on 2025-07..12 (§6.5); never linked to returns or performance. Step 5's integrity test reads 2021+ dsf `prc` and panel `me` and `prc` straight from the clean files and asserts only that no sub-penny row or resumed 5+ session gap touches a $500m and $5 stock; the exits diff compares 2021+ rows by key, date and category, never `delret`.
- Arcana before the unseal: no v4 book is uploaded. Its overview says mock portfolios "update in real-time" with "historical backfill" and its Excel add-in takes any start and end date, so we assume an uploaded book is tracked forward to today, which would show even the Dec 2020 book's 2021-2026 result. The intro video (transcribed 2026-10-23, `data/arcana/`) never says a book stops at its last date, and a pasted "new book" is analysed over trailing windows to today (year to date, one year), so the conditional drill stays off and no v4 book enters Arcana before the unseal. The pre-freeze lens checks run in our own code (PDF p24: "You do not need Arcana to ask these questions of your own work"). The leader learns the platform on Arcana's sample book only; until the freeze (step 10), when every rule is written and `protocol.md` is hashed, the leader also skips Arcana's factor-return, factor-stress and single-stock performance pages, which show 2021-2026 results; no MCP use (§10.1); no v4 choice comes from anything seen there, since every remaining choice is a written rule on pre-2021 data. Never 2021+ holdings, the rehearsal books (relabelled onto 2021-2026 dates), 2021+ factor dashboards for our books or any performance view of our books.


## 2. State (2026-10-27, late evening)

### 2.1 The fund: vfinal
- **What it is:** the one final fund, quarterly refits and loose limits, $1bn, market neutral, 2021-01 to 2026-08, after every modelled cost.
- **Headline:**
  - $1bn to $1.054bn, against cash plus 4% at $1.509bn;
  - CAGR 0.93%, vol 7.45%, Sharpe -0.28;
  - IR vs bill + 4% -0.82 (s.e. 0.43), -0.54 before costs;
  - beta -0.093 monthly and -0.034 daily;
  - max drawdown -10.3%, worst month -5.6%;
  - 0 breach days, 274 names on average, gross 165%;
  - one-way turnover 157% a year;
  - trading cost 1.72% and borrow 0.50% of NAV a year;
  - flat-borrow sensitivity IR -1.01.
  
  Files: `out/vfinal/final/revised_quarterly_loose/table_9_1_eab2349a0ce1.csv` and `report_eab2349a0ce1.json`.
- **Code:** `fiam/vfinal`, run as `uv run fiam <verb>` (check, rerun, stage, whatif, lock, verify, audit, export, setup, doctor; `uv run fiam help`). v1 modules stay only because vfinal imports `fiam.book`, `fiam.data`, `fiam.stats` and `fiam.exhibits.*`. v2 and v3 are deleted; their research outputs are in `out/research/`.
- **The lock:**
  - `frozen/vfinal/opened.json`, `vfinal.sha256` (96 files) and `outputs.json`;
  - the locked run is commit eab2349 (`*_eab2349a0ce1*` files), content-identical to the original run at 81eba1f;
  - after editing any locked file, run `uv run fiam lock eab2349a0ce1`; `outputs.json` must stay unchanged, then `uv run fiam verify` must print "verifies" and "headline outputs match";
  - relocked 2026-10-27 after the sweep (only `fiam/vfinal/evidence.py` changed).
- **In-sample what-ifs:** `out/vfinal/final/whatif/<variant>/`, summarised by `uv run fiam whatif summary 81eba1fad3ac`. Each is labelled "chosen with 2021-2026 visible, not the strategy". Results in §4.

### 2.2 Everything around it
- **Site and film:** `site/` (`pnpm check`, `pnpm build`). Data comes from `uv run tools/build_site.py`, which picks the newest pick with its crises file and is byte-identical on rebuild. Films are `deck/QUARCC_Purple_FIAM_trailer{,_vertical,_sideways}.mp4`, with web copies in `out/media/`. Pre-vfinal copies are in `~/FIAM_backup_2026-10-27_site_film/`. The leader checks devices on their own.
- **Deck:** built in the session scratch (`deck_build_v5.py`, 16 main slides and 6 appendix). It must move into the repo before the session ends (§3 step 9).
- **Arcana:**
  - ours is "QUARCC Purple vFinal", id 34377266; quote Historical mode only, ending 2026-08-31;
  - "QUARCC Purple vFinalv2", id 34387571, is Andrew's D69 (5% name cap broken on 317 days), to be renamed;
  - the analysis lives in the session scratch `deck/arcana/REPORT.md`;
  - Backtest mode holds the latest book back in time (hindsight), so it is never quoted.
- **Machines:**
  - the Mac is the reference (bit-exact reruns);
  - the PC (`nick@100.66.128.94`, Tailscale) is not bit-exact when it retrains, so it is reported with its measured gap and never decides;
  - commits reach the PC by git bundle;
  - PC state 2026-10-27: never sleeps on AC, sshd and Tailscale services automatic, Tailscale tied to the NicksPC login (not unattended), no auto-login, 390 GB free on F:.
- **USB:** `FIAM_FINALS`, kit in `fiam_finals/` (never delete the folder). Full kit 89.9 GB; lean kit without the AI model files (`--skip weights-gemma,weights`) is about 57 GB; 158.6 GB free.

## 3. What is left, in order

### Tonight
1. **[DONE 2026-10-28 00:20] vfinal-only MAIN.py** (19.4 MB, 244 files).
   - Way 1 alone: 22 of 22 checks (every rule, the headline recomputed exactly, 90 of 90 code files match the lock).
   - Way 2 with the organisers' files: 30 of 30 (their checksums; our stock P&L replayed on their returns to the cent on 1,349 of 1,349 fully priced days; the $224k gap sits on 2 null-return name-days the engine prices from the price ratio).
   - `uv run fiam compare`, `repo.bundle` in the export, results carried in `final/` (6.2 MB, rebuilt byte-identical by `tools/final_results.py`).
   - Relocked (98 files, outputs unchanged, verify passes); 672 tests pass.
2. **[LEADER] Commit:** "feat: make MAIN.py check the final fund and add fiam compare". [DONE] a6fe867 (sweep and docs).
3. **[DONE] PC settings:** Run unattended on, Windows Update paused to 2026-11-11, never sleeps on AC. The reboot test is optional (only the live AI demo needs the PC).
4. **[me] Lean kit:** `uv run fiam export --skip weights-gemma,weights` after the final commit, with no job writing. Then restore into an empty folder on the Mac, check every SHA-256, and run `fiam doctor`.
5. **[me] Mac tests:** ways 1, 2 and 3 from the fresh restore; way 4 overnight, then `fiam compare` (expected identical).
6. **[me] PC tests:** the leader moves the stick; sync to the final commit by bundle; restore to F:; ways 1, 2 and 3; way 4 overnight, then `fiam compare` (expected close, not identical; report the gap).
7. **[me] Deck v5** (agent building), 16 main and 6 appendix:
   - the leader's slides (1 to 5 and 16) dark, others white;
   - timing: leader 0:45 + 1:45 + 0:45, others 1:30;
   - the PDF checked page by page as pictures;
   - reserved panels: slide 8 (Carbon Arc) and slide 16 (fixes tested).
8. **[awaiting leader] Optimizer and Arcana trial.** Plan in the session; results are in-sample and labelled so.

### Morning
9. **Report everything:**
   - [me] every result exactly as it comes out; Tailscale check after the night;
   - [LEADER] hotspot test, manual check of the 4 ways, deck notes;
   - [me] deck fixes, then the PowerPoint (animated builds, with the film, AI crowd and MCP clips embedded) and the web version;
   - [me] move the deck builder into the repo (`tools/deck/`) and its outputs into `deck/`.

### Last
10. **Carbon Arc** (four pieces, the leader approves each batch; never in the fund), **study guide**, **Arcana** (rename vFinalv2, delete "Portfolio 14", the MCP clip), then:
    - one small commit;
    - re-export of only the changed parts;
    - delete agent worktrees and scratch;
    - **deploy the site**.

## 4. Honesty record (keep)
- **The first final run** at 512e4bd (frozen before any 2021+ result, 2026-10-27 01:14 to 03:40):
  - $0.803bn, CAGR -3.80%, Sharpe -0.88, IR vs bill + 4% -1.39 (s.e. 0.44);
  - the AI desk did not help (no AI -1.39, fixed rule -1.43, AI -1.42; 100 random desks around no AI), so the fund runs without it.
- **vfinal is one revision chosen after that result was seen** (leader, 2026-10-27 10:30):
  - the SUE table rebuilt to 2026-08;
  - the hurdle exactly as PDF p20;
  - trade to the optimum each month;
  - short interest as a model input;
  - refits from 2017;
  - the cadence and limits picked blind on 2017-2020.
  
  The deck does not mention it; the leader discloses it in person. No slide claims the fund was fixed before 2021.
- **SUE note** (cut-the-future test, 2026-10-27):
  - The SUE table rebuilt as it stood at three cuts differs on a few rows public by then: 2021 cut 13 values, 2023 cut 0, 2025 cut 29, from later Compustat `rdq` matches.
  - With each cut's table the forecast's z rank correlation is 0.967 (2023-06) and 0.963 (2025-06).
  - The 2017-2020 books and the 2021 SUE model are untouched.
  - Recorded, not fixed.
- **What-ifs** (in-sample, never a headline), CAGR / IR net / max drawdown against the headline's 0.93% / -0.82 / -10.3%:

  | What-if | CAGR | IR net | Max drawdown |
  |---|---|---|---|
  | Style caps lifted | 2.00% | -0.71 | -9.4% |
  | 220 names | 1.06% | -0.78 | -12.6% |
  | Yearly refits | -0.13% | -0.87 | -11.9% |
  | No cost budget | 0.15% | -0.90 | -11.0% |
  | Sectors wide | 0.03% | -0.92 | -11.5% |
  | Speed 0.5 | -0.31% | -0.91 | -14.2% |
  | Speed 0.2 | -2.22% | -1.28 | -18.8% |
  | 480 names | -0.19% | -1.09 | -10.7% |
  | Half risk aversion | -0.45% | -1.00 | -14.7% |
  | Cost budget halved | -0.54% | -1.09 | -13.5% |
  | Stocks of $3bn and up | 0.13% | -1.00 | -9.8% |
  | Volatility reliability (Andrew's A2, winner of his pre-set rule on 2017-2020 at IR 0.068) | 0.82% | -0.85 | -10.5% |

  Alpha times volatility (A1) failed that rule at -0.85 on 2017-2020 and was stopped unread.
- **Andrew's D69** (`origin/feat/v4b`) breaks the PDF p4 5% name cap on 317 days (363 position-days, max 5.69%), so it cannot be the fund.
- **Arcana on vfinal** (before costs and cash interest):
  - stock picks +11.54% (residual IR 0.46) against factor tilts -10.46%;
  - positions older than a year hold 59% of gross for almost no edge;
  - five days around earnings lost $104.9M.
