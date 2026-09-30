# The ship rule: builds every candidate book, trains the trader, and picks each year's book.

import json

import numpy as np
import pandas as pd
import torch

from fiam import book as P
from fiam import data, paths
from fiam.ml import scorer as SC
from fiam.ml import teachers as TE
from fiam.ml import trader as TR

OUT = paths.EXHIBITS / "ship.json"
# Every candidate's months: what the charts draw and the only record the director agent reads.
MONTHS = paths.EXHIBITS / "ship_candidates.csv"

# Decisions from December 2016, so the trader has two years of history before its first test.
FIRST_DECISION, FIRST_TRADER_YEAR, FIRST_SHIP_YEAR = (
    ("2021-12-31", 2024, 2024) if paths.SMOKE else ("2016-12-31", 2019, 2021)
)

# Written before any candidate was scored: the composite ships unless another beats it clearly.
HURDLE, MAX_BETA = 0.25, 0.15
# PPO is slow, so it is the trader's yardstick on one book: half scorer, learned hedge.
REFERENCE = P.candidate_name(0.5, True, False)


# The scorer's score, the teachers' beta and crowding, and the crowd score, where they exist.
def inputs() -> pd.DataFrame | None:
    frames = []
    if SC.CACHE.exists():
        frames.append(pd.read_parquet(SC.CACHE, columns=[*data.KEYS, "score"]))
    if TE.CACHE.exists():
        taught = pd.read_parquet(TE.CACHE)
        frames.append(taught.filter([*data.KEYS, "beta_hat", "crowding_hat"]))
    if SC.CROWD.exists():
        frames.append(pd.read_parquet(SC.CROWD))
    if not frames:
        return None
    out = frames[0]
    for extra in frames[1:]:
        out = out.merge(extra, on=data.KEYS, how="outer")
    return out.assign(eom=out["eom"].astype("datetime64[s]"))


# One candidate walked through every month, its records and the steps the trader learns from.
def run_book(universe, extra, name: str, trades: dict | None = None):
    steps = list(P.walk(P.candidate(universe, extra, name), trades=trades))
    records = pd.DataFrame([P.month_record(*s) for s in steps]).set_index("holding_month")
    return records, steps


# Each year's book: the composite, unless an alternative beat it on the two years before.
def choose(books: dict, year: int) -> tuple[str, dict]:
    first, last = f"{year - 2}-01-01", f"{year - 1}-12-01"
    scores = {name: P.judge(b["net"], first, last) for name, b in books.items()}
    base = scores["composite"]["information_ratio"]
    fit = {
        n: s
        for n, s in scores.items()
        if n != "composite"
        and s["information_ratio"] >= base + HURDLE
        and abs(s["beta"]) <= MAX_BETA
    }
    best = max(fit, key=lambda n: fit[n]["information_ratio"]) if fit else "composite"
    return best, scores


# Month by month, a policy trained on the months already paid for, warm from last month's.
def learn_trades(steps: list, nets: pd.Series, card: bool) -> tuple[dict, dict]:
    path = TR.arrays(steps)
    raw = TR.features(path, nets.reset_index(drop=True))
    tensors = {k: torch.as_tensor(v) for k, v in path.items() if k != "months"}
    years = np.array([(m + pd.offsets.MonthBegin(1)).year for m in path["months"]])
    trades, policy = {}, None
    for i in np.flatnonzero(years >= FIRST_TRADER_YEAR):
        if i < 2 * TR.EPISODE:
            continue
        # Features scaled by the paid months alone, so the decision month never informs them.
        z = torch.as_tensor((raw - raw[:i].mean(0)) / (raw[:i].std(0) + 1e-12))
        policy = TR.train_deep(tensors, z, np.arange(i), policy)
        with torch.no_grad():
            rate, gross = policy(z[i])
        trades[path["months"][i].strftime("%Y-%m-%d")] = [float(rate), float(gross)]
    return trades, scorecard(path, raw, tensors, years, trades) if card else {}


# Each test year replayed four ways: the monthly policy, PPO, the best fixed rate, no trader.
def scorecard(path: dict, raw, tensors: dict, years: np.ndarray, trades: dict) -> dict:
    card = {}
    for year in range(FIRST_TRADER_YEAR, int(years.max()) + 1):
        window, test = np.flatnonzero(years < year), np.flatnonzero(years == year)
        if len(window) < 2 * TR.EPISODE or not len(test):
            continue
        z = (raw - raw[window].mean(0)) / (raw[window].std(0) + 1e-12)
        fixed = TR.train_fixed(tensors, torch.as_tensor(z), window)
        ppo = TR.train_ppo(path, z, window)

        # PPO's action for month i, mapped to a rate and a gross.
        def ppo_act(i, ppo=ppo, z=z):
            a = ppo.predict(z[i], deterministic=True)[0]
            return TR.actions(*((np.clip(a, -1, 1) + 1) / 2))

        rules = dict(
            deep_hedging=lambda i: tuple(trades[path["months"][i].strftime("%Y-%m-%d")]),
            ppo=ppo_act,
            fixed_rate=lambda i, fixed=fixed: (fixed, TR.GROSS[1]),
            trade_all_the_way=lambda i: (1.0, TR.GROSS[1]),
        )
        card[str(year)] = {}
        for name, act in rules.items():
            nets = TR.replay(path, test, act)
            util = nets.mean() - TR.RISK_AVERSION / 2 * nets.var()
            card[str(year)][name] = dict(net_annual=nets.mean() * 12, utility=util)
        card[str(year)]["fixed_rate_chosen"] = fixed
    return card


# The year a decision's holding month falls in.
def holding_year(month: str) -> str:
    return str((pd.Timestamp(month) + pd.offsets.MonthBegin(1)).year)


# Every candidate and its trader, then each year's choice and the policy file.
def main() -> None:
    universe = P.build_signal(P.screen(P.load_panel(), FIRST_DECISION, P.LAST_FORECAST))
    extra = inputs()
    books, trades, card = {}, {}, {}
    # Each untraded book, then the trader learned on its path and the same book traded by it.
    for name, spec in P.CANDIDATES.items():
        if spec["trader"]:
            continue
        books[name], steps = run_book(universe, extra, name)
        traded = f"{name}+traded"
        trades[traded], scored = learn_trades(steps, books[name]["net"], name == REFERENCE)
        card = scored or card
        del steps
        books[traded], _ = run_book(universe, extra, traded, trades[traded])
        for n in (name, traded):
            print(f"  {n}: IR 2021-26 {P.information_ratio(books[n]['net'].loc['2021':]):+.2f}")

    by_year, verdicts = {}, {}
    for year in range(FIRST_SHIP_YEAR, 2027):
        by_year[str(year)], verdicts[str(year)] = choose(books, year)
    kept = {
        m: t
        for name, months in trades.items()
        for m, t in months.items()
        if by_year.get(holding_year(m)) == name
    }
    policy = dict(by_year=by_year, trades=dict(sorted(kept.items())))
    P.MODELS.mkdir(parents=True, exist_ok=True)
    policy_text = json.dumps(P.round_floats(policy), indent=2) + "\n"
    (P.MODELS / "policy.json").write_text(policy_text, encoding="utf-8", newline="\n")
    if extra is not None:
        recent = extra[extra["eom"] >= P.FIRST_FORECAST].sort_values(data.KEYS)
        recent.to_parquet(P.MODELS / "book_inputs.parquet", index=False)

    columns = ["gross", "cost", "net", "turnover", "n"]
    table = pd.concat([b[columns].assign(candidate=n) for n, b in books.items()])
    table.reset_index()[["candidate", "holding_month", *columns]].to_csv(
        MONTHS, index=False, float_format="%.8f", lineterminator="\n"
    )
    summary = dict(
        what="A 3 x 2 x 2 grid of candidate books from 2017: the composite blended with 0, 25 or "
        "50% scorer, each with and without the learned hedge and the trader, and each year's "
        "choice by a rule written before any candidate was scored.",
        rule=f"the composite ships unless another candidate's IR over the two prior years beats "
        f"it by {HURDLE} with beta inside +/-{MAX_BETA}",
        chosen=by_year,
        validation=verdicts,
        candidates_2021_2026={
            n: dict(
                **P.book_stats(b.loc["2021":]), beta=P.judge(b["net"], "2021", "2026-08")["beta"]
            )
            for n, b in books.items()
        },
        trader_book=REFERENCE,
        trader=card,
    )
    OUT.write_text(json.dumps(P.round_floats(summary), indent=2), encoding="utf-8", newline="\n")
    print(f"  chosen: {by_year}")


if __name__ == "__main__":
    main()
