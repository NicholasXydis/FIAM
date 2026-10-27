# Synthetic final-run tables for the exhibit tests and a dry render.

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# The run: the endowment close, then Jan 2021 to Aug 2026 sessions.
FIRST, LAST = "2020-12-31", "2026-08-31"
# The universe, the legs' name counts and their gross.
UNIVERSE, LONGS, SHORTS, LEG_GROSS = 700, 230, 200, 0.85
# Costs on traded dollars and borrow a year on short dollars.
COST, BORROW = 0.0004, 0.004
# The spill's cap: 10% of ADV a close, the rest the next session.
CAP = 0.10
NAV = 1e9


# The tables build() reads and its meta, from one seed.
def tables(seed: int = 7) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(FIRST, LAST)
    # New Year's Day is no session, so 2021-01-04 follows the endowment.
    days = days[~((days.month == 1) & (days.day == 1))]
    n, permnos = len(days), np.arange(10001, 10001 + UNIVERSE)
    rf = np.where(days.year < 2022, 0.0005, np.where(days.year < 2025, 0.045, 0.04)) / 252
    sp = rng.normal(0.0004, 0.011, n)
    beta = rng.uniform(0.6, 1.4, UNIVERSE)
    alpha = rng.normal(0.0, 0.0003, UNIVERSE)
    R = rf[:, None] + beta * (sp - rf)[:, None] + alpha + rng.normal(0, 0.018, (n, UNIVERSE))
    me = np.exp(rng.normal(np.log(9000), 0.9, UNIVERSE)).clip(650)
    adv = me * 1e6 * rng.uniform(0.004, 0.012, UNIVERSE)
    W = weights(rng, days, alpha, beta)
    nav, ret, cost, borrow = run(W, R, rf)
    adv_table = monthly(days, permnos, adv, rng).rename(columns={"me": "adv"})
    tables = {
        "daily": daily(days, nav, ret, rf, cost, borrow, W),
        "positions": positions(days, permnos, W, nav),
        "trades": trades(days, permnos, W, nav, adv_table),
        "ledger": ledger(days, permnos, W, nav, R, cost, borrow),
        "events": pd.DataFrame(
            {
                "date": days[[40, 300, 900]],
                "permno": permnos[:3],
                "kind": ["unfilled", "halt_day", "unfilled"],
                "value": [1.0, 1.0, 2.0],
            }
        ),  # fmt: skip
        "bench": pd.Series(sp, index=days),
        "caps": monthly(days, permnos, me, rng),
        "adv": adv_table,
        "ids": ids(permnos),
        "k1": pd.DataFrame(
            {
                "period": ["2017 to 2020", "2021 to 2026"],
                "ic": [0.031, 0.024],
                "breadth": [1900.0, 1750.0],
                "tc": [0.46, 0.44],
                "realised_ir": [0.52, 0.31],
            }
        ),  # fmt: skip
    }
    names = tables["daily"]["n_long"] + tables["daily"]["n_short"]
    tables["compliance"] = pd.DataFrame({"names": names, "companies": names - 2})
    rule_b = tables["daily"].copy()
    rule_b.loc[rule_b.index.year == 2026, "ret"] -= 0.00003
    tables["rule_b"] = rule_b
    notes = ["Synthetic tables for a dry render", "rule B sits beside rule A"]
    meta = {"window": ("2021-01-04", LAST), "arm": "A0", "notes_2026": notes}
    return tables, meta


# Monthly weights from the first session of each month, held between.
def weights(rng, days, alpha, beta) -> np.ndarray:
    W = np.zeros((len(days), len(alpha)))
    month = days.to_period("M")
    current = np.zeros(len(alpha))
    for i in range(1, len(days)):
        if month[i] != month[i - 1]:
            score = alpha + rng.normal(0, 0.0004, len(alpha))
            order = np.argsort(score)
            current = np.zeros(len(alpha))
            long, short = order[-LONGS:], order[:SHORTS]
            current[long] = LEG_GROSS * rng.dirichlet(np.full(LONGS, 8.0))
            current[short] = -LEG_GROSS * rng.dirichlet(np.full(SHORTS, 8.0)) * (
                beta[long].mean() / beta[short].mean())  # fmt: skip
        W[i] = current
    return W


# NAV and returns: cash earns the bill, costs on the trade day.
def run(W, R, rf) -> tuple:
    n = len(W)
    nav, ret = np.full(n, NAV), np.zeros(n)
    cost, borrow = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        prev = nav[i - 1]
        gain = (W[i - 1] * (R[i] - rf[i])).sum()
        cost[i] = COST * np.abs(W[i] - W[i - 1]).sum() * prev
        borrow[i] = BORROW / 252 * -W[i - 1][W[i - 1] < 0].sum() * prev
        ret[i] = rf[i] + gain - (cost[i] + borrow[i]) / prev
        nav[i] = prev * (1 + ret[i])
    return nav, ret, cost, borrow


# The engine's daily table, as daily_book.Result.daily holds it.
def daily(days, nav, ret, rf, cost, borrow, W) -> pd.DataFrame:
    moved = np.r_[0.0, 0.5 * np.abs(np.diff(W, axis=0)).sum(axis=1)]
    traded = moved > 0
    return pd.DataFrame(
        {"nav": nav, "ret": ret, "rf": rf, "cost": cost, "borrow": borrow, "traded": traded,
         "turnover": moved,
         "gross": np.abs(W).sum(axis=1), "net": W.sum(axis=1),
         "n_long": (W > 0).sum(axis=1), "n_short": (W < 0).sum(axis=1)},
        index=pd.DatetimeIndex(days, name="date"),
    )  # fmt: skip


# Closing positions in dollars, one row per held name and day.
def positions(days, permnos, W, nav) -> pd.DataFrame:
    i, j = np.nonzero(W)
    return pd.DataFrame({"date": days[i], "permno": permnos[j], "value": W[i, j] * nav[i]})


# Each formation's trades: 10% of ADV on the day, the rest the next.
def trades(days, permnos, W, nav, adv_table) -> pd.DataFrame:
    wide = adv_table.pivot(index="date", columns="permno", values="adv")[permnos]
    rows = []
    for i in np.nonzero(np.abs(np.diff(W, axis=0)).sum(axis=1) > 0)[0] + 1:
        formed = days[i] - pd.offsets.MonthEnd(1)
        # The ADV as of the formation, as the engine's spill reads it.
        adv = wide.loc[:formed].iloc[-1].to_numpy()
        move = (W[i] - W[i - 1]) * nav[i - 1]
        for j in np.nonzero(move)[0]:
            first = np.sign(move[j]) * min(abs(move[j]), CAP * adv[j])
            rows.append((days[i], formed, permnos[j], first))
            if abs(move[j]) > CAP * adv[j] and i + 1 < len(days):
                rows.append((days[i + 1], formed, permnos[j], move[j] - first))
    return pd.DataFrame(rows, columns=["date", "formed", "permno", "dollars"])


# The per-name ledger: price P&L, and costs split by traded size.
def ledger(days, permnos, W, nav, R, cost, borrow) -> pd.DataFrame:
    V = W * nav[:, None]
    price = np.zeros_like(V)
    price[1:] = V[:-1] * R[1:]
    move = np.abs(np.diff(W, axis=0, prepend=0.0))
    moved = move.sum(axis=1, keepdims=True)
    share = np.divide(move, moved, out=np.zeros_like(move), where=moved > 0)
    parts = [("price", price), ("cost", -share * cost[:, None])]
    shorts = np.where(np.r_[np.zeros((1, W.shape[1])), W[:-1]] < 0, -np.r_[[W[0]], W[:-1]], 0.0)
    total = shorts.sum(axis=1, keepdims=True)
    split = np.divide(shorts, total, out=np.zeros_like(shorts), where=total > 0)
    parts.append(("borrow", -split * borrow[:, None]))
    out = []
    for kind, M in parts:
        i, j = np.nonzero(M)
        out.append(pd.DataFrame({"date": days[i], "permno": permnos[j], "kind": kind,
                                 "dollars": M[i, j]}))  # fmt: skip
    return pd.concat(out, ignore_index=True)


# A month-end value per name, wandering about 5% around its level.
def monthly(days, permnos, level, rng) -> pd.DataFrame:
    ends = days[days.to_series().groupby(days.to_period("M")).transform("max") == days]
    noise = np.exp(rng.normal(0, 0.05, (len(ends), len(permnos))))
    frame = pd.DataFrame(noise * level, index=ends, columns=permnos)
    out = frame.stack().rename("me").reset_index()
    return out.rename(columns={"level_0": "date", "level_1": "permno"})


# Tickers and names, a few renamed in mid-2023 to test the as-of.
def ids(permnos) -> pd.DataFrame:
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    rows = []
    for k, p in enumerate(permnos):
        ticker = letters[k % 23] + letters[(k // 23) % 23] + letters[(k // 529) % 23]
        rows.append((p, "2020-12-31", f"{ticker} US Equity", f"SYNTHETIC HOLDINGS {k} INC"))
        if k % 50 == 0:
            rows.append((p, "2023-06-30", f"{ticker}X US Equity", f"RENAMED GROUP {k} CORP /DE/"))
    out = pd.DataFrame(rows, columns=["permno", "date", "ticker", "name"])
    return out.assign(date=pd.to_datetime(out["date"]))


# Renders one synthetic set: python -m fiam.vfinal.exhibits.synthetic
if __name__ == "__main__":
    from fiam.vfinal.exhibits.build import build

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "out/alt/exhibits_test")
    frames, meta = tables()
    for path in build(frames, target, meta):
        print(path)
