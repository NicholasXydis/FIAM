<div align="center">
<img src="site/docs/banner.jpg" alt="QUARCC Purple" width="100%">

### A market-neutral fund that stays level when AI moves the market

McGill-FIAM Asset Management Hackathon 2026 · Finals

<br>

<a href="https://quarccpurple.ca"><img src="site/docs/site-btn.svg" alt="Visit quarccpurple.ca" width="560"></a>

</div>

## About

QUARCC Purple is a market-neutral fund of US stocks. It buys the strongest companies and shorts
the weakest with the same money on both sides, so the market's swings cancel out. AI agents on our
own machines check the work, and code enforces every rule after any agent.

This repository holds two books.

| Book | What it is | Where it lives |
|---|---|---|
| v1 | The book we submitted in round one | `fiam/book.py` and `submission/` |
| vfinal | The final fund we present at the finals | `fiam/vfinal/` and `versions/vfinal/` |

## v1, the round-one record

v1 ranks about 3,500 US stocks each month on twelve published signals, such as value, quality and
momentum, and holds about 300 of them long and short with a fixed $10 million fund. Its record runs
from January 2021 to August 2026 after every modelled cost.

| Measure | v1 |
|---|---|
| Return a year after costs | 12.8% |
| Information ratio | 0.74 |
| Sharpe ratio | 1.07 |
| Beta to the S&P 500 | −0.03 |
| Worst drawdown | −7.4% |

Several of v1's choices were made while 2021 to 2026 was visible, so this record is partly in
sample and is never called out of sample.

## vfinal, the final fund

vfinal runs a $1 billion fund that compounds, and code enforces every finals rule. Its settings and
protocol live in `versions/vfinal/`. The lock in `frozen/vfinal/` hashes its code, its settings and
its headline outputs, so any later change shows. Rows public after 2020 stay closed unless the
data gate holds, and the tests always run blind.

## Commands

```bash
pip install uv
uv run fiam help      # every command of the final fund
uv run fiam check     # tests, ruff, the comment scan and doctor
uv run fiam rerun     # every headline stage at this commit, then the pick
uv run fiam verify    # the lock, then the headline outputs it records
uv run run.py         # the submitted v1 book against the brief
```

## The USB kit and MAIN.py

The finals kit on the USB carries the data, models and results a git repository cannot hold.
`uv run fiam export` writes it and `uv run fiam setup` restores it on another machine, copying only
missing files and checking each one against its hash. `uv run fiam doctor` says what is missing and
how to fix it.

MAIN.py is the brief's one file. Run `uv run MAIN.py` in an empty folder and it writes the project's
code beside itself, then checks the submitted v1 book against every rule in seconds. With the
organizer's data beside it, it rebuilds the v1 book.

## Made with

| Part | Built with |
|---|---|
| Research | Python, PyTorch, scikit-learn, LightGBM, pandas, NumPy, SciPy, CVXPY, uv |
| AI agents | Gemma, Qwen and Pythia, run on our own machines |
| Website | TypeScript, React 19, Vite, Tailwind CSS, three.js, WebGL, GSAP |
| Film | Made in code with three.js, voiced by Kokoro, an AI voice that runs locally |
| Hosting | Cloudflare Workers and R2, GitHub Actions |

## What is where

| Folder | What it holds |
|---|---|
| `fiam/` | The v1 book with its costs, models and agents, and `fiam/vfinal/` for the final fund |
| `submission/` | The official v1 results |
| `versions/` | Each book's recipe and the fingerprints a test checks |
| `frozen/` | Small frozen inputs and the final fund's lock |
| `site/` | The website and the film |
| `docs/` | The plan and every protocol written before its test ran |

<br>

Nicholas Xydis · Yohannah Ilieva · Andrew Koumoudjian · Nicolas Romero · Nokto Lapointe
