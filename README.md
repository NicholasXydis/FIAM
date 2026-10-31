<div align="center">
<img src="site/docs/banner.jpg" alt="QUARCC Purple" width="100%">

### A market-neutral fund that stays level when AI moves the market

McGill-FIAM Asset Management Hackathon 2026 · Finals · [quarccpurple.ca](https://quarccpurple.ca)

**[Fact sheet](finals/QUARCC_Purple_Fact_Sheet.pdf) · [Deck (PowerPoint)](finals/QUARCC_Purple_Finals.pptx) · [Deck (PDF)](finals/QUARCC_Purple_Finals.pdf)**

</div>

## The fund

A $1 billion fund of US stocks that buys the strongest companies and shorts the weakest with the same money on both sides, so the market's swings cancel out. An E-LASSO model ranks every stock each month, an optimiser builds about 300 positions twice a month, and plain code enforces every rule on every day. AI agents check the book but never pick a stock or set a size.

## Results

January 2021 to August 2026, after all costs.

| | QUARCC Purple | T-bills + 4% | S&P 500 |
|---|---|---|---|
| $1bn became | $1.467bn | $1.509bn | $2.046bn |
| Return a year | 7.0% | 7.5% | 13.5% |
| Volatility | 3.96% | | 15.1% |
| Max drawdown | −2.99% | | −25.4% |
| Sharpe ratio | 0.91 | | 0.70 |
| Sortino ratio | 4.21 | | 1.51 |
| Ulcer index | 0.52% | | 8.10% |
| Beta to the S&P 500 | 0.012 | | |

The information ratio against T-bills + 4% is −0.11. The book was rebuilt 136 times with 0 rule breaches. Every figure, with its exact value, is in [finals/numbers.json](finals/numbers.json).

## Team

| Name | Role | Studies |
|---|---|---|
| Nicholas Xydis | AI & Research | Concordia, Computer Science |
| Yohannah Ilieva | Risk Management | Concordia, Mathematical & Computational Finance |
| Andrew Koumoudjian | Portfolio Construction | Concordia, Finance |
| Nokto Lapointe | Machine Learning | McGill, Honours Physics & Computer Science |
| Nicolas Romero | Data & Finance | Concordia, Finance, Mathematics & Statistics |

## Commands

Install once with `pip install uv`.

| To | Run |
|---|---|
| Check every rule and result with one file | `uv run MAIN.py` |
| Restore the data kit from the USB | `uv run fiam setup` |
| Prove every file matches the lock | `uv run fiam verify` |
| Rebuild the whole fund | `uv run fiam rerun` |
| Run the tests and checks | `uv run fiam check` |
| Rebuild the deck | `uv run tools/deck/build.py` |

The deck build needs Node and, once, `pnpm install` and `pnpm exec playwright-core install chromium` in `site/`. It writes the same bytes every time. On Windows, set `PYTHONUTF8=1` first. The Mac is the reference machine.

## What is where

| Folder | Holds |
|---|---|
| `finals/` | The fact sheet, the deck and the numbers they show |
| `fiam/` | All the code: the fund in `fiam/vfinal/` and the AI agents in `fiam/agents/` |
| `frozen/` | The lock and the locked results of the fund, and round one's book |
| `data/` | Small public series such as FRED and Kenneth French; licensed data stays on the USB kit |
| `site/` | The website and the film |
| `tools/` | The deck builder, the MAIN.py builder and the data tools |
| `tests/` | The tests |
