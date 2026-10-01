# Phase 3: construction v2 against the current book, once, on 2016-2026, by pre-registered rules.

from dataclasses import asdict, replace
from functools import partial

import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import paths
from fiam.exhibits import daily_risk as R

OUT = paths.EXHIBITS / "construction.json"
# Decisions from December 2015 to the record's last, so both windows are in one continuous book.
FIRST, LAST = "2015-12-31", P.LAST_FORECAST

# Each rule of v2 on its own, reported beside the bundle and never used to choose.
PARTS = ("adjusted_beta", "net_band", "short_rules", "liquidity_caps", "crash_protection")


# One design walked through every month: its monthly records and its holdings.
def run(design: P.Design) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = P.build_signal(P.screen(P.load_panel(), FIRST, LAST), design=design)
    records, holdings = [], []
    for step in P.walk(universe, optimize=partial(P.optimize_month, design=design)):
        record = P.month_record(*step)
        records.append(record)
        weights = step[1]
        frame = dict(Date=record["holding_month"], PERMNO=weights.index, WEIGHT=weights * 100)
        holdings.append(pd.DataFrame(frame))
    book = pd.DataFrame(records).set_index("holding_month")
    book["rf"] = B.benchmarks().set_index("month")["rf"].reindex(book.index)
    return book, pd.concat(holdings, ignore_index=True)


# IR, monthly beta on the CRSP market, worst drawdown, and the rules checked month by month.
def monthly(book: pd.DataFrame) -> dict:
    market = B.benchmarks().set_index("month")["mkt_rf_crsp"].reindex(book.index)
    fit = P.regress(book["net"], market)
    growth = (1 + book["rf"] + book["net"]).cumprod()
    return dict(
        months=int(len(book)),
        information_ratio=P.information_ratio(book["net"]),
        net_annual=float(book["net"].mean() * 12),
        cost_annual=float(book["cost"].mean() * 12),
        beta_monthly=float(fit.params.iloc[1]),
        beta_monthly_stderr=float(fit.bse.iloc[1]),
        max_drawdown=float((growth / growth.cummax() - 1).min()),
        names_min=int(book["n"].min()),
        names_max=int(book["n"].max()),
        gross_max=float(book["gross_exposure"].max()),
        net_max_abs=float(book["net_exposure"].abs().max()),
    )


# The daily beta on 2016-2025 and the largest gross on any day, from the book marked daily.
def daily(book: pd.DataFrame, holdings: pd.DataFrame) -> dict:
    marked = holdings[holdings["Date"] <= R.LAST]
    prices = R.daily_returns(marked["PERMNO"], "2016-01-01", R.LAST)
    path = R.paths_by_day(marked, book, prices)
    beta = R.daily_beta(path)
    return dict(
        beta_daily=beta["beta"],
        beta_daily_stderr=beta["stderr"],
        days=beta["days"],
        gross_max_any_day=float(path["gross"].max()),
        gross_max_2021_2025=float(path.loc["2021":, "gross"].max()),
    )


# The four pass rules of PREREGISTRATION.md, each true or false.
def verdict(current: dict, v2: dict) -> dict:
    rules = dict(
        ir_at_least_current=v2["information_ratio"] >= current["information_ratio"],
        beta_closer_to_zero=abs(v2["beta_monthly"]) < abs(current["beta_monthly"])
        and abs(v2["beta_daily"]) < abs(current["beta_daily"]),
        drawdown_no_deeper=v2["max_drawdown"] >= current["max_drawdown"],
        every_rule_every_month=100 <= v2["names_min"]
        and v2["names_max"] <= 500
        and v2["gross_max_any_day"] <= 2.0
        and v2["net_max_abs"] <= 0.5,
    )
    return dict(**rules, ships=all(rules.values()))


def main() -> None:
    books = {}
    for name, design in (("current", P.CURRENT), ("v2", P.V2)):
        book, holdings = run(design)
        books[name] = dict(**monthly(book), **daily(book, holdings))
        books[name]["by_window"] = {
            w: P.information_ratio(book.loc[a:b, "net"])
            for w, (a, b) in dict(
                y2016_2020=("2016-01-01", "2020-12-01"),
                y2021_2026=("2021-01-01", "2026-08-01"),
                y2023_2026=("2023-01-01", "2026-08-01"),
            ).items()
        }
        print(f"  {name}: {books[name]}")
    parts = {}
    for part in PARTS:
        switch = {part: P.V2.net_band if part == "net_band" else True}
        if part == "net_band":
            switch["adjusted_beta"] = True
        parts[part] = monthly(run(replace(P.CURRENT, **switch))[0])
        print(f"  {part} alone: IR {parts[part]['information_ratio']:+.2f}")
    out = dict(
        what="Construction v2 against the current construction on 2016-01 to 2026-08, both "
        "with the Phase 2 cost model, judged once by the rules PREREGISTRATION.md fixed. Each "
        "rule's separate effect is reported, never used to choose.",
        design=asdict(P.V2),
        market="CRSP value-weighted market for monthly beta; S&P 500 daily for daily beta",
        current=books["current"],
        v2=books["v2"],
        verdict=verdict(books["current"], books["v2"]),
        each_rule_alone=parts,
    )
    paths.write_json(OUT, out)
    print(f"  verdict: {out['verdict']}")


if __name__ == "__main__":
    main()
