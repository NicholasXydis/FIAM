<div align="center">
<img src="site/docs/banner.jpg" alt="QUARCC Purple" width="100%">

### A market-neutral fund that stays level when AI moves the market

McGill-FIAM Asset Management Hackathon 2026 · Finals

<a href="https://quarccpurple.ca"><img src="site/docs/site-btn.svg" alt="Visit quarccpurple.ca" width="560"></a>

</div>

## What it is

A $1 billion fund of US stocks that buys the strongest companies and shorts the weakest with the same money on both sides, so the market's swings cancel out.

## How it works

1. **Data on one clock.** Every fact is dated to the moment the public could first see it, and the fund trades on it one close later. Dead companies stay in, and later rewrites are replaced by the numbers first filed.
2. **Forecast.** Each month an E-LASSO model ranks every stock on the organisers' 147 characteristics plus three of our own (the SYY-10 mispricing score, an earnings surprise forecast and short interest). It refits every month on the past only, and a regime factor scales how much it is trusted.
3. **Build the book twice a month.** At each month end and again mid-month on refreshed prices, an optimiser with a full risk model turns the forecasts into about 300 longs and shorts, neutral to the market and sectors, after trading costs and borrow. Each change is worked over five sessions at no more than 10% of a stock's volume.
4. **Check every rule.** Plain code enforces every limit on every day. AI agents read the rules, explain positions and test risk, but never pick a stock or set a size.
5. **Lock it.** Hashes of the code, the inputs and every result sit in `frozen/vfinal/`, so any later change shows.

## Commands

Install once with `pip install uv`.

| To | Run |
|---|---|
| Check our results with one file | `uv run MAIN.py` |
| See every command | `uv run fiam help` |
| Restore the USB kit | `uv run fiam setup` |
| Prove every file matches the lock | `uv run fiam verify` |
| Rebuild the whole fund | `uv run fiam rerun` |
| Compare a rebuild with the locked run | `uv run fiam compare` |
| Run tests and checks | `uv run fiam check` |
| Build the website | `cd site && pnpm install && pnpm build` |

Without internet, clone from the stick with `git clone <USB>/fiam_finals/repo.bundle FIAM`.

## Four ways to check it

1. **`MAIN.py` alone** checks every rule on every day, recomputes the results and checks the code against the lock.
2. **`MAIN.py` with the organisers' files** in `data/organisers/` also replays our returns on their own prices.
3. **This repo plus the USB kit** proves every code, data and result file matches the lock.
4. **This repo plus the USB kit** rebuilds the whole fund and compares it with the locked run.

## How to reproduce

The Mac is the reference machine. Ways 1 and 2 both run `uv run MAIN.py`. Way 1 alone shows 22 of 22 checks, and way 2 with the organisers' data shows 30 of 30.

**On Windows**

1. Way 3 needs `uv sync --locked --python 3.14.6`, because the lock checks the exact Python version.
2. Set `PYTHONUTF8=1` first. In cmd, write `set "PYTHONUTF8=1"`.
3. Way 4's report stage calls `grep`, so put Git for Windows' `usr\bin` folder on `PATH`.

The Windows full rebuild matched the Mac to $5,050 on $1.467bn (0.0003%). It held the same names on the same side every day, and its IR and Sharpe were equal to 4 decimals. It is not byte identical, so the Mac is the reference.

## What is where

| Folder | Holds |
|---|---|
| `fiam/` | All the code: the final fund in `fiam/vfinal/`, the AI agents and their prompts in `fiam/agents/`, the round one book and the data tools |
| `frozen/` | Every fixed record: the lock, results and rules of the final fund in `frozen/vfinal/`, round one in `frozen/v1/`, the AI crowd files in `frozen/agents/` and the 61st Investor seals |
| `data/` | Small public series such as FRED and Kenneth French; licensed data stays on the USB kit |
| `site/` | The website and the film |
| `tests/` | The tests |
| `tools/` | MAIN.py and results builders, the comment check and the data download tools |

## Versions

Each version has a `version.json` in its `frozen/` folder with the fingerprints a test checks, so a closed version can never change unnoticed.

- **v1** is round one's submitted book, built by `fiam/book.py` on twelve signals with a fixed $10 million fund. Its holdings, returns, exhibits, rules and protocols are in `frozen/v1/`. Several of its choices were made while 2021 to 2026 was visible, so its record is partly in sample and never called out of sample.
- **vfinal** is the final fund, $1 billion compounding, with every finals rule enforced in code. Its code is `fiam/vfinal/` and its lock, protocol, rules and carried results are in `frozen/vfinal/`. Rows public after 2020 open only through the data gate.

## Made with

Python, numba, LightGBM, PyTorch, scikit-learn, CVXPY and uv. Gemma, Qwen and Pythia run locally for the AI agents. TypeScript, React, three.js and GSAP for the website, and a film made in code and voiced by Kokoro.

