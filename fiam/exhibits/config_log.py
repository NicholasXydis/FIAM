# Every experiment family and its attempts, all fed to deflated Sharpe.

import csv

from fiam import paths

OUT = paths.EXHIBITS

# Eligible means it could have shipped had it won. book.py reads both.
LEDGER = """
28 candidate portfolios: signal sets, hedges, trading rules | candidates | yes | 27 | When chosen: 12-signal score 0.70, with the predicted-beta hedge 0.72, others -0.28 to 0.72. Final run 0.74 | Shipped, with the hedge
A yearly rule to switch between candidates | candidates | no | 1 | IR 0.34 or 0.67, unstable between runs | Dropped
What to neutralize: betas, volatility, sectors | neutralization | yes | 14 | Sectors, beta and volatility kept. Style-neutral variant 0.75 | In part
Construction: weights, carrying positions over, gross exposure, volatility target | construction | yes | 24 | 160% gross kept. Volatility targeting 0.15 to 0.34 | In part
Optimizer: position penalty, candidate pool, turnover, short limits | optimizer | yes | 16 | Penalty 30 and a 200-stock pool kept. Turnover penalty 0.49 to 0.54 | In part
More signals: additions, reversal, seasonality | signals | yes | 33 | None helped. Best addition 0.86, no better than chance | Rejected
Text signals: tone, filing counts, 8-K items | text | yes | 3 | None significant once neutralized (best t-stat 2.1) | Rejected
ML blends and targets: cost-aware, 3 to 6 months ahead | model | yes | 22 | Best IR -0.15 | Rejected
Construction v2: beta, net exposure band, short rules | construction | yes | 1 | IR -0.17 against -0.00, 2016-2026 | Rejected
Construction v2, each rule alone | construction | no | 5 | Every rule alone lowers IR | Check
Factor-neutral portfolio, five style limits | construction | yes | 1 | IR -0.89, alpha -4.2% (t-stat -1.7) | Rejected
ML on the 147 characteristics: linear, trees, neural nets | model | no | 24 | IC t-stat 2.5 to 4.1, all lose money after costs | Reported
Stock-picking model, helper models, AI crowd score | model | no | 16 | Picker IC 0.067 (t-stat 3.55). Beta error 0.55 against 0.64 | Beta model kept
Trading models: deep hedging and PPO | model | no | 3 | IR 0.70 to 0.41, not reproducible | Removed
Signal search: subsets and combinations | control | no | 1139 | +1.78 where it searched, +0.33 on unseen years | Check
Signal-discovery agent and random search | control | no | 95 | Unseen IR -1.18 to -2.08, random -0.44 | Check
Robustness: shuffles, delays, 2016-20, lags | control | no | 241 | Shuffled scores earn nothing, a day's delay costs nothing | Check
"""

COLUMNS = ["experiment", "family", "eligible_for_deployment", "attempts", "result", "verdict"]


# The table above as rows, attempts as numbers.
def rows() -> list[list]:
    parsed = [[cell.strip() for cell in line.split("|")] for line in LEDGER.strip().splitlines()]
    return [[*row[:3], int(row[3]), *row[4:]] for row in parsed]


# The deflated Sharpe's two counts: shippable attempts and every fit.
def attempts() -> tuple[int, int]:
    table = rows()
    return sum(r[3] for r in table if r[2] == "yes"), sum(r[3] for r in table)


# Writes the ledger and prints the two attempt counts.
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "config_log.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows([COLUMNS, *rows()])
    eligible, everything = attempts()
    print(f"{len(rows())} families, {eligible} eligible attempts, {everything} in all")


if __name__ == "__main__":
    main()
