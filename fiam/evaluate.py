# The research harness: any book or rule scored window by window, choices walked forward in time.


import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import paths
from fiam.exhibits.confirmation import summarise

OUT = paths.EXHIBITS / "evaluation.json"
MONTHS = paths.EXHIBITS / "ship_candidates.csv"

# The windows every result is reported on, by holding month. Both were seen, so neither is clean.
WINDOWS = {
    "2016-2020": ("2016-01-01", "2020-12-01"),
    "2021-2022": ("2021-01-01", "2022-12-01"),
    "2023-2026": ("2023-01-01", "2026-08-01"),
    "2021-2026": ("2021-01-01", "2026-08-01"),
}
DRAWS, SEED = 10_000, 42


# The CRSP market for every window, since FRED's S&P 500 starts in September 2016.
def market() -> pd.Series:
    return B.benchmarks().set_index("month")["mkt_rf_crsp"]


# One book's statistics in each window it covers for at least a year.
def by_window(book: pd.DataFrame) -> dict:
    out = {}
    for name, (first, last) in WINDOWS.items():
        part = book.loc[first:last]
        if len(part) >= 12:
            span = f"{part.index.min():%Y-%m} to {part.index.max():%Y-%m}"
            out[name] = dict(**summarise(part, market()), span=span)
    return out


# Every candidate's monthly record, one frame per candidate keyed on holding month.
def candidates() -> dict[str, pd.DataFrame]:
    table = pd.read_csv(MONTHS, parse_dates=["holding_month"])
    return {
        n: g.set_index("holding_month").drop(columns="candidate")
        for n, g in table.groupby("candidate")
    }


# Each year's pick by a rule that sees only months before that year, and the picks' months joined.
def nested(books: dict[str, pd.DataFrame], rule, years) -> tuple[dict, pd.DataFrame]:
    picks = {}
    for year in years:
        history = {n: b[b.index < f"{year}-01-01"] for n, b in books.items()}
        picks[str(year)] = rule(history, year)
    joined = pd.concat([books[name].loc[year] for year, name in picks.items()])
    return picks, joined


# The ship rule as written, and the default it has to beat.
def ship_rule(history: dict, year: int) -> str:
    return P.choose(history, year)[0]


# The composite every year, whatever the history says.
def always_composite(history: dict, year: int) -> str:
    return "composite"


# Where a set of picks falls among random picks of one candidate a year, over the same years.
def chance(books: dict[str, pd.DataFrame], picks: dict) -> dict:
    rng, names = np.random.default_rng(SEED), sorted(books)
    draws = [
        P.information_ratio(
            pd.concat([books[names[rng.integers(len(names))]].loc[y, "net"] for y in picks])
        )
        for _ in range(DRAWS)
    ]
    ir = P.information_ratio(pd.concat([books[n].loc[y, "net"] for y, n in picks.items()]))
    return dict(
        information_ratio=ir,
        random_mean=float(np.mean(draws)),
        share_of_random_beaten=float(np.mean(np.array(draws) < ir)),
    )


def main() -> None:
    books = candidates()
    first = int(min(b.index.min().year for b in books.values())) + 2
    years = range(first, 2027)
    tracks = {}
    for name, rule in (("ship_rule", ship_rule), ("always_composite", always_composite)):
        picks, joined = nested(books, rule, years)
        tracks[name] = dict(
            picks=picks, windows=by_window(joined), against_chance=chance(books, picks)
        )
    out = dict(
        what="Each candidate and each way of choosing between them, by window. A rule picks every "
        "year from the months before it; random picks over the same years are the control.",
        market="CRSP value-weighted market, for every window",
        first_pick=first,
        tracks=tracks,
        shipped=by_window(paths.returns()),
        candidates={n: by_window(b) for n, b in books.items()},
    )
    paths.write_json(OUT, out)
    for name, track in tracks.items():
        irs = {w: round(s["information_ratio"], 2) for w, s in track["windows"].items()}
        beaten = track["against_chance"]["share_of_random_beaten"]
        print(f"  {name}: IR {irs}, above {beaten:.0%} of random picks")


if __name__ == "__main__":
    main()
