# The ledger behind the deflated Sharpe. Attempts count runs, not rows. Writes config_log.csv.

import csv

from fiam import paths

OUT = paths.EXHIBITS

# Eligible means it could have shipped had it won. The deflated Sharpe in book.py reads both.
LEDGER = """
beta_60m only                            | neutralization | yes |    1 | realized beta -0.52                             | rejected
beta_60m + volatility complex            | neutralization | yes |    1 | realized beta -0.10                             | SHIPPED
sector GICS-2                            | neutralization | yes |    1 | max tilt 1.1%                                   | SHIPPED
sector ff49                              | neutralization | yes |    1 | 7.3% of groups under 5 names                    | rejected
also neutral on size and value           | neutralization | yes |    1 | IR 0.85 to 0.75, DD -24%                        | rejected
equal-weight 12 signals                  | construction   | yes |    1 | IR 0.85                                         | SHIPPED
carry-in rule                            | construction   | yes |    1 | IR 0.73 to 0.85                                 | SHIPPED, post-hoc
conviction scaling                       | construction   | yes |    1 | signal t 3.10 to 3.10                           | rejected
signal-agreement gate                    | construction   | yes |    1 | signal t 3.07                                   | rejected
within-sector ranking                    | construction   | yes |    1 | signal t 2.94                                   | rejected
median instead of mean                   | construction   | yes |    1 | signal t 2.84                                   | rejected
winsorised z +/-2                        | construction   | yes |    1 | signal t 3.10                                   | rejected
divided by dispersion                    | construction   | yes |    1 | IR 0.93                                         | not adopted
8 theme blocks                           | construction   | yes |    1 | IR 0.97                                         | not adopted
vol-matched legs                         | construction   | yes |    1 | IR 0.79 but net +0.83                           | rejected, breaks mandate
inverse-vol weighting                    | construction   | yes |    1 | IR 0.55                                         | rejected
vol target 10/8/6%                       | construction   | yes |    3 | IR 0.34/0.26/0.15                               | rejected
ridge 15/20/30/45/60                     | optimizer      | yes |    5 | IR 0.81/0.84/0.85/0.78/0.76                     | 30 SHIPPED
pool 100/150/200/300/400                 | optimizer      | yes |    5 | IR 0.75/0.82/0.85/0.85/0.85                     | 200 SHIPPED
turnover penalty 0.25-2.0                | optimizer      | yes |    4 | IR 0.49-0.54, turnover 50% to 6-16%             | rejected
shorts restricted to >$1bn               | optimizer      | yes |    1 | IR 0.52 to 0.41                                 | rejected
12 more theory-signed signals            | signals        | yes |   12 | IR 0.48                                         | rejected
single best added signal                 | signals        | yes |   12 | IR 0.86, 6 of 12 helped                         | rejected, coin flip
broad theme composite, 41 chars          | signals        | yes |    1 | IR 0.28, DD -45%                                | rejected
factor-agreement filter                  | signals        | yes |    3 | IR 0.49/0.34/0.32                               | rejected
1m and 3m reversal                       | signals        | yes |    2 | neutralized t -0.33 / -1.12                     | rejected
lottery demand, illiquidity              | signals        | yes |    2 | neutralized t -0.46 / -0.12                     | rejected
seasonality                              | signals        | yes |    1 | neutralized t 1.22                              | rejected
Loughran-McDonald tone                   | text           | yes |    1 | t -2.41 raw, 0.44 neutralized                   | rejected
8-K filing intensity                     | text           | yes |    1 | t 2.05 neutralized, decile table fails          | rejected
8-K signed item codes                    | text           | yes |    1 | t -0.20 raw, +0.06 neutralized, 25% coverage    | rejected
ElasticNet on 147 chars                  | model          | no  |    1 | IC t 2.55, IR -0.52                             | exhibit
LightGBM on 147 chars                    | model          | no  |    1 | IC t 3.60, IR -0.37                             | exhibit
NN3 on 147 chars                         | model          | no  |    1 | IC t 3.89, IR -0.24                             | exhibit
Ridge a=100/1000                         | model          | no  |    2 | IC t 3.73 / 3.65                                | exhibit
PLS 5/15 components                      | model          | no  |    2 | IC t 4.05 / 3.70                                | exhibit
RandomForest depth 6                     | model          | no  |    1 | IC t 3.25                                       | exhibit
ExtraTrees depth 6                       | model          | no  |    1 | IC t 3.85                                       | exhibit
LightGBM on residual target              | model          | no  |    1 | IC t 3.43                                       | exhibit
composite + ML blends                    | model          | no  |    1 | t 2.05 falls to 0.52                            | exhibit
MSE target instead of rank               | model          | no  |    1 | IC 0.0142 vs 0.0610                             | exhibit
page-23 fundamental forecast             | model          | no  |    1 | t 3.53 vs 3.66 for the level                    | exhibit
fundamental changes not levels           | model          | no  |    1 | t 1.72 vs 3.87                                  | exhibit
792 five-signal subsets                  | control        | no  |  792 | IR 0.45-1.26, early-late corr -0.36             | control
200-combination search                   | control        | no  |  200 | +1.78 where it looked, +0.33 sealed, 54 of 200  | control
cost sensitivity 1x-4.8x                 | control        | no  |    5 | break-even at 16.2%                             | control
drawdown override policy                 | control        | no  |    1 | documented, not applied                         | control
NN3 five-seed sweep                      | control        | no  |    5 | IR -1.38 to -0.24, mean -0.80                   | control
constraint survival, 5 stages x 4 models | control        | no  |   20 | neutralization helps all, costs sink three      | control
permutation null, 200 draws              | control        | no  |  200 | shipped above all 200, null net IR -2.06        | control
inversion of the composite               | control        | no  |    1 | gross -20.2% a year                             | control
stale scores, one month lag              | control        | no  |    1 | net IR 0.47                                     | control
cost-aware blend, 3 models x 5 weights   | model          | yes |   15 | best IR -0.15 (NN3, blend 0.7) vs +0.85         | rejected
signal decay by model                    | control        | no  |    4 | one month on: 83-97% of IC retained             | control
3m and 6m forward targets                | model          | yes |    2 | IC 0.0126 / 0.0179, IR -1.31 / -0.67            | rejected
monotone constraints on 12 signs         | model          | yes |    1 | IC 0.0549, IR -0.37                             | rejected
purged folds, 6-month embargo            | control        | no  |    1 | IC 0.0561 to 0.0426, IR -0.88                   | control
ensemble of the three models             | model          | yes |    1 | best IC 0.0611, IR -0.31                        | rejected
template OLS / ridge / ElasticNet        | model          | no  |    3 | OOS R2 all below zero                           | exhibit
frozen book on 2016-2020                 | control        | no  |    1 | IR -0.82, beta -0.30 (60 months)                | control
factor atlas, 147 characteristics        | control        | no  |  147 | t corr -0.41                                    | control
earnings module, 3 declared variants     | model          | yes |    3 | none passed the 2016-20 rule                    | rejected by rule
accounting lagged 3 and 6 months         | control        | no  |    2 | IR 0.42 / 0.33                                  | control
stock-split event study                  | control        | no  |    1 | 230 forward, 70 reverse                         | control
release-day reports held back a month    | control        | no  |    1 | IR 0.82                                         | control
discovery agent, old harness, real names | control        | no  |   23 | sealed IR -1.18                                 | control
discovery agent, old harness, coded      | control        | no  |   31 | sealed IR -1.41                                 | control
discovery agent, Hermes, real names      | control        | no  |    9 | sealed IR -2.08                                 | control
discovery agent, Hermes, coded names     | control        | no  |    1 | sealed IR -1.82, picked on lookups alone        | control
random search beside the agent           | control        | no  |   31 | sealed IR -0.44                                 | control
gross 200/190/180/170/160%, on 2016-20   | construction   | yes |    5 | above 200% at month end: 35/12/8/2/1 of 60      | 190, then 160
two more ex-ante betas, three ways       | neutralization | yes |    3 | 2016-20 beta -0.30 to -0.34, none better        | rejected
ex-ante beta aimed at trailing beta      | neutralization | yes |    3 | 2016-20 beta -0.29                              | rejected
market sleeve sized by trailing beta     | neutralization | yes |    3 | 2016-20 beta -0.21, fails the 0.15 rule         | rejected
ElasticNet penalty: non-empty, rank IC   | model          | no  |    2 | squared error kept 2 vars, validation IC -0.007 | exhibit
gross fixed at target, deeper pool      | optimizer      | yes |    1 | shipped IR unchanged; every model book 127+     | SHIPPED
zero-beta book, 5,000 bootstrap draws    | control        | no  |    1 | 49% of 12-month windows outside +/-0.20         | control
gross 160-200%, daily peaks 2021-25      | construction   | yes |    5 | IR 0.83-0.85 flat; at 160% no day above 200%    | 160 SHIPPED
teachers: beta, crowding, revisions     | model          | no  |    3 | learned beta error 0.55 vs 0.64; see teachers   | input
LambdaRank scorer, residual target      | model          | no  |    5 | see scorer.json                                 | input
candidates: 3 blends x hedge x trader   | construction   | yes |   11 | see ship.json                                   | by ship rule
trader: monthly deep hedging, PPO, fixed| model          | no  |    3 | see ship.json, trader                           | deep in book
ship rule, +0.25 IR over 2 prior years  | control        | no  |    1 | see ship.json                                   | control
crowd agent, 2 models x 60 months       | control        | no  |    2 | see crowd.json                                  | control
crowding teacher's top tenth as HTB     | costs          | no  |    1 | costs can only rise                             | SHIPPED
research director agent, one run a year | control        | no  |    6 | see director.json                               | control
cost model v2: IBKR, CRSP quotes, tiers   | costs          | no  |    1 | pre-registered measurement, every book          | SHIPPED
construction v2, one pre-registered test | construction   | yes |    1 | IR -0.17 vs -0.00 on 2016-26, 3 of 4 rules fail | rejected by rule
construction v2, each rule alone         | construction   | no  |    5 | every rule alone lowers IR                      | control
factor-neutral book, five FF limits      | construction   | yes |    1 | IR -0.89 vs -0.00 on 2016-26; alpha -4.2%, t -1.7 | rejected by rule
screen-then-rank, amendment 13           | construction   | yes |    4 | IR 0.23-0.38; most defensive in 2024            | chosen for 2026
scorer in liquid names, amendment 13     | construction   | yes |    8 | IR 0.27-0.49; 50% blend 0.01 to 0.47 with hedge | not chosen
distress veto on longs, amendment 13     | construction   | yes |    4 | IR 0.54-0.72, the composite's own record         | not chosen
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
