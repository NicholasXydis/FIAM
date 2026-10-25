# The frozen book on 2016-2020, years not designed on. Writes the JSON.


import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import paths

OUT = paths.EXHIBITS

# Decisions from December 2015, so the first holding month is Jan 2016.
FIRST, LAST = "2015-12-31", "2020-11-30"


# The stats quoted for the real record, computed alike for any window.
def summarise(book: pd.DataFrame, market: pd.Series) -> dict:
    net = book["net"]
    growth = (1 + net).cumprod()
    fit = P.regress(net, market)
    by_year = {str(y): float((1 + g).prod() - 1) for y, g in net.groupby(net.index.year)}
    return dict(
        months=int(len(book)),
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(net.mean() * 12),
        information_ratio=P.information_ratio(net),
        sharpe_ratio=float(net.mean() / net.std() * np.sqrt(12)),
        beta_realized=float(fit.params.iloc[1]),
        beta_stderr=float(fit.bse.iloc[1]),
        max_drawdown_spread=float((growth / growth.cummax() - 1).min()),
        turnover=float(book["turnover"].mean()),
        positions=float(book["n"].mean()),
        net_by_year=by_year,
    )


# The same book on 2016-2020 beside the record, on the CRSP market.
def main() -> None:
    universe = P.build_signal(P.screen(P.load_panel(), FIRST, LAST))
    book = P.backtest(universe)
    # The limits the shipped book must clear, so the test is like for like.
    P.assert_limits(book)

    # FRED's S&P 500 starts Sep 2016, so both windows use the CRSP market.
    market = B.benchmarks().set_index("month")["mkt_rf_crsp"]
    shipped = paths.returns()

    path = OUT / "confirmation.json"
    out = dict(
        what="The shipped code and parameters, unchanged, on holding months 2016-01 to 2020-12.",
        why="Every signal and construction choice was made while looking at 2021-2026. This "
        "window was not examined while they were designed, so it is the nearest thing to a clean "
        "test. Since then the gross target and three rejected beta fixes were tried here, "
        "as config_log.csv records.",
        market="CRSP value-weighted market (Ken French), for both windows",
        confirmation_2016_2020=summarise(book, market),
        shipped_2021_2026=summarise(shipped, market),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    paths.write_json(path, out, rounded=False)

    for label in ("confirmation_2016_2020", "shipped_2021_2026"):
        s = out[label]
        print(
            f"{label}: IR {s['information_ratio']:+.2f}, net {s['net_annual']:+.1%}/yr, "
            f"beta {s['beta_realized']:+.2f} (se {s['beta_stderr']:.2f}), {s['months']} months"
        )


if __name__ == "__main__":
    main()
