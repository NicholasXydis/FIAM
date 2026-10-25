# Running the book for real: cost sensitivities, capacity and liquidity.


import numpy as np
import pandas as pd

from fiam import book as P
from fiam import costs as C
from fiam import paths

OUT = paths.EXHIBITS / "implementation.json"

# Capital a committee asks about; weights stay, only trading costs move.
CAPITAL = (10e6, 100e6, 500e6, 1e9)
# The share of a day's dollar volume a position may take when sold.
PARTICIPATION = 0.20


# The shipped book rerun under one cost model: its IR and yearly cost.
def rerun(model: C.Model) -> dict:
    book = P.backtest(P.shipped(P.universe()), model=model)
    return dict(
        information_ratio=P.information_ratio(book["net"]),
        net_annual=float(book["net"].mean() * 12),
        cost_annual=float(book["cost"].mean() * 12),
    )


# Days to sell each position at the participation cap, size-weighted.
def liquidity(holdings: pd.DataFrame, nav: float) -> dict:
    universe = P.universe()[["permno", "eom", "dolvol_126d"]]
    held = holdings.assign(eom=holdings["Date"] - pd.offsets.MonthEnd(1)).astype(
        {"eom": "datetime64[s]"}
    )
    held = held.merge(universe, left_on=["PERMNO", "eom"], right_on=["permno", "eom"], how="left")
    size = held["WEIGHT"].abs() / 100
    days = size * nav / (PARTICIPATION * held["dolvol_126d"])
    return dict(
        share_of_book_out_in_one_day=float(size[days <= 1].sum() / size.sum()),
        days_p95=float(np.nanpercentile(days, 95)),
        days_max=float(np.nanmax(days)),
    )


# Charges the shipped trades under other cost models and capital levels.
def main() -> None:
    holdings = paths.holdings()
    sensitivities = dict(
        as_modelled=rerun(C.DEFAULT),
        every_cost_doubled=rerun(C.Model(multiple=2.0)),
        impact_coefficient_half=rerun(C.Model(impact_y=0.5)),
    )
    capacity = {f"{nav / 1e6:.0f}m": rerun(C.Model(nav=nav)) for nav in CAPITAL}
    out = dict(
        what="The shipped book's trades, charged under other cost models and capital levels. "
        "Weights stay as shipped, so capacity shows what costs do, not a re-optimized book.",
        participation=PARTICIPATION,
        sensitivities=sensitivities,
        capacity=capacity,
        liquidity={f"{nav / 1e6:.0f}m": liquidity(holdings, nav) for nav in CAPITAL},
    )
    paths.write_json(OUT, out)
    for name, s in {**sensitivities, **capacity}.items():
        print(f"  {name}: IR {s['information_ratio']:+.2f}, costs {s['cost_annual']:.1%} a year")


if __name__ == "__main__":
    main()
