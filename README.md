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
2. **Forecast.** Each month three models (LightGBM, an elastic net and a small neural network) forecast only the part of each stock's return the market, its sector and known styles cannot explain. They refit every quarter on the past only.
3. **Build the book.** An optimiser turns forecasts into a book neutral to the market and sectors, after trading costs and borrow.
4. **Check every rule.** Plain code enforces every limit on every day. AI agents read the rules, explain positions and test risk, but never pick a stock or set a size.
5. **Lock it.** Hashes of the code, settings and results sit in `frozen/vfinal/`, so any later change shows.

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

## What is where

| Folder | Holds |
|---|---|
| `fiam/vfinal/` | The final fund |
| `fiam/` | The shared engine and the AI agents |
| `final/` | The results `MAIN.py` checks |
| `frozen/vfinal/` | The lock |
| `site/` | The website and the film |
| `docs/` | `PLAN.md` (rules and what is left) and `TEAM.md` (the whole project in plain English) |

## Made with

Python, LightGBM, PyTorch, scikit-learn, CVXPY and uv. Gemma, Qwen and Pythia run locally for the AI agents. TypeScript, React, three.js and GSAP for the website, and a film made in code and voiced by Kokoro.

<br>

Nicholas Xydis · Yohannah Ilieva · Andrew Koumoudjian · Nicolas Romero · Nokto Lapointe
