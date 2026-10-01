# Everything we tried, by family, with its attempts: the deflated Sharpe counts them all.

import csv

from fiam import paths

OUT = paths.EXHIBITS

# Eligible means it could have shipped had it won. The deflated Sharpe in book.py reads both.
LEDGER = """
28 candidate books, hedge and trader variants | candidates | yes | 27 | composite 0.70, + hedge 0.72; rest -0.28 to 0.72 | hedge SHIPPED
yearly switching rule among the 28 | candidates | no | 1 | IR 0.34 or 0.67, flipped by the trader | dropped
neutralization: betas, volatility, sectors | neutralization | yes | 14 | sectors, beta, volatility kept; styles 0.75 | in part
construction: weights, carry-in, gross, vol target | construction | yes | 24 | 160% gross kept; vol targeting 0.15-0.34 | in part
optimizer: ridge, pool, turnover, short limits | optimizer | yes | 16 | ridge 30, pool 200 kept; penalty 0.49-0.54 | in part
more signals: added, reversal, seasonality | signals | yes | 33 | none helped; best addition 0.86, a coin flip | rejected
text signals: tone, filing intensity, items | text | yes | 3 | no neutralized t above 2.1 | rejected
ML blends and targets: cost-aware, 3-6 month | model | yes | 22 | best IR -0.15 | rejected
construction v2: beta, net band, short rules | construction | yes | 1 | IR -0.17 vs -0.00 on 2016-26 | rejected
construction v2, each rule alone | construction | no | 5 | every rule alone lowers IR | control
factor-neutral book, five style limits | construction | yes | 1 | IR -0.89; alpha -4.2%, t -1.7 | rejected
ML on 147 characteristics: linear, trees, nets | model | no | 24 | IC t 2.5-4.1; all lose after costs | exhibit
stock picker, teachers, crowd, director | model | no | 16 | picker IC 0.068, t 3.55; beta error 0.55 vs 0.64 | hedge kept
trader: deep hedging and PPO | model | no | 3 | IR 0.70 to 0.41; not reproducible | removed
signal search: subsets, combinations, atlas | control | no | 1139 | +1.78 where it looked, +0.33 unseen | control
discovery agent and random search | control | no | 95 | unseen IR -1.18 to -2.08; random -0.44 | control
robustness: shuffles, delays, 2016-20, lags | control | no | 241 | shuffles earn nothing; a day late costs nothing | control
"""

COLUMNS = ["experiment", "family", "eligible_for_deployment", "attempts", "result", "verdict"]


# The table above as rows, attempts as numbers.
def rows() -> list[list]:
    parsed = [[cell.strip() for cell in line.split("|")] for line in LEDGER.strip().splitlines()]
    return [[*row[:3], int(row[3]), *row[4:]] for row in parsed]


# The two counts the deflated Sharpe divides by: attempts that could have shipped, and every fit.
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
