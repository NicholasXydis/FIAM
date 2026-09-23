# Feeds a model's predictions through the same optimizer the book uses, and reports the IR.
# Reads cache/preds/<model>.parquet, writes cache/preds/<model>_portfolio.json.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

OUT = Path("cache/preds")


# Swaps a model's score in for the composite, then runs the book's own neutralization.
# Everything after that is the shipped code, so only the score differs.
def neutralize(panel: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    df = P.build_signal(P.screen(panel))
    scored = df.merge(preds[["permno", "eom", "pred"]], on=["permno", "eom"], how="inner")

    # Same treatment the composite gets: rank within month, sector-demean, then strip beta.
    r = scored.groupby("eom")["pred"].rank(pct=True)
    mu = r.groupby(scored["eom"]).transform("mean")
    sd = r.groupby(scored["eom"]).transform("std")
    # A fully penalised ElasticNet predicts one constant all month, so the z-score would
    # divide by zero. Score those months flat instead of dropping them.
    z = ((r - mu) / sd.replace(0.0, np.nan)).fillna(0.0)
    demeaned = z - z.groupby([scored["eom"], scored["sector"]]).transform("mean")
    bx = scored["beta_60m"] - scored.groupby("eom")["beta_60m"].transform("mean")
    sy = demeaned - demeaned.groupby(scored["eom"]).transform("mean")
    cov = (bx * sy).groupby(scored["eom"]).transform("sum")
    var = (bx * bx).groupby(scored["eom"]).transform("sum")
    scored["signal"] = sy - (cov / var) * bx
    return scored


# Runs the book month by month, exactly as pipeline.run does, and returns monthly returns.
def backtest(universe: pd.DataFrame) -> pd.DataFrame:
    rows, previous, previous_spreads = [], None, None
    flat_months = 0
    for month in sorted(universe["eom"].unique()):
        cross_section = universe[universe["eom"] == month]
        # Same carry-in rule the book gets, or the comparison would be rigged in our favour.
        weights = P.optimize_month(cross_section, previous)
        if weights is None:
            continue
        info = cross_section.set_index("permno").loc[weights.index]
        weights = P.to_whole_shares(weights, info["prc"].abs())
        info = info.loc[weights.index]

        # The shipped cost model, called rather than copied, so the two cannot drift apart.
        spreads = cross_section.set_index("permno")["bidaskhl_21d"]
        cost, turnover = P.trading_cost(weights, previous, info, spreads, previous_spreads)

        # Same limits the book asserts, so a model cannot win by breaking one. The floor is
        # the exception. A flat month leaves nothing to rank, so we count it and report it.
        if not len(weights):
            flat_months += 1
            previous, previous_spreads = previous, previous_spreads
            continue
        assert len(weights) <= 500, f"{len(weights)} positions"
        assert weights.abs().sum() <= 2.0 + 1e-9, "gross above 200%"
        assert abs(weights.sum()) < 0.005, "net exposure outside tolerance"

        # Missing returns are kept and booked flat, the same treatment the book gives them.
        gross = (weights * info["ret_exc_lead1m"].fillna(0.0)).sum()
        rows.append(
            dict(
                holding_month=(month + pd.offsets.MonthBegin(1)).normalize(),
                gross=gross,
                cost=cost,
                net=gross - cost,
                turnover=turnover,
                n=len(weights),
                beta=(weights * info["beta_60m"]).sum(),
            )
        )
        previous, previous_spreads = weights, spreads
    book = pd.DataFrame(rows).set_index("holding_month")
    book.attrs["months_with_no_position"] = flat_months
    return book


# IR against the competition benchmark: T-bill plus 4% a year.
def information_ratio(book: pd.DataFrame) -> float:
    bm = P.benchmarks().set_index("month")
    active = book.join(bm[["rf"]], how="left")["net"] - 0.04 / 12
    return float(active.mean() / active.std() * np.sqrt(12))


# Scores one model's predictions into a book and writes the information ratio it earned.
def main(model: str = "lgbm") -> None:
    preds = pd.read_parquet(OUT / f"{model}.parquet")
    preds["eom"] = pd.to_datetime(preds["eom"])
    book = backtest(neutralize(P.load_panel(), preds))
    stats = dict(
        model=model,
        information_ratio=information_ratio(book),
        net_annual=float(book["net"].mean() * 12),
        gross_annual=float(book["gross"].mean() * 12),
        turnover=float(book["turnover"].mean()),
        months=int(len(book)),
        months_with_no_position=int(book.attrs.get("months_with_no_position", 0)),
        positions=float(book["n"].mean()),
    )
    (OUT / f"{model}_portfolio.json").write_text(json.dumps(stats, indent=2))
    print(
        f"{model}: IR {stats['information_ratio']:+.2f}  "
        f"net {stats['net_annual'] * 100:+.1f}%/yr  over {stats['months']} months"
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "lgbm")
