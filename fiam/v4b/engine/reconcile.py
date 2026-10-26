"""Independent monthly cohort compounding of actual fills, R§8 E0.

Stock P&L is computed in closed form from starting holdings and each actual
trade's subsequent return path, not from the simulator's daily P&L column.
Cash interest and cost lines remain the ledger inputs; their arithmetic has
separate hand-calculation tests. This does not validate source return vintages.
"""

import numpy as np
import pandas as pd


def monthly_reference(ledger, positions, returns):
    names = pd.Index(sorted(positions.permno.unique()))
    dates = ledger.index[1:]
    r = returns.reindex(index=dates, columns=names).fillna(0.0)
    holdings = (
        positions.pivot(index="date", columns="permno", values="w")
        .reindex(index=dates, columns=names)
        .fillna(0.0)
        .mul(ledger.nav.reindex(dates), axis=0)
    )
    previous = holdings.shift(1).fillna(0.0)
    r = r.mask((previous < 0) & (r <= -1.0), 0.0)
    trades = (
        positions.assign(q=positions.trade_dollars + positions.synthetic_exit_dollars)
        .pivot(index="date", columns="permno", values="q")
        .reindex(index=dates, columns=names)
        .fillna(0.0)
    )
    rows = []
    for month, block in r.groupby(r.index.to_period("M")):
        days = block.index
        growth = 1.0 + block.to_numpy(dtype=np.float64)
        # A close trade earns only the returns strictly AFTER its fill day.
        after = np.ones_like(growth)
        if len(growth) > 1:
            after[:-1] = np.cumprod(growth[:0:-1], axis=0)[::-1]
        start = previous.loc[days[0]].to_numpy()
        stock_pnl = float(start @ (growth.prod(axis=0) - 1))
        stock_pnl += float((trades.loc[days].to_numpy() * (after - 1)).sum())
        lines = ledger.loc[days]
        cash_pnl = float(
            (
                lines.interest
                + lines.stub
                - lines[["spread", "impact", "fees", "borrow"]].sum(axis=1)
            ).sum()
        )
        start_nav = float(ledger.nav.loc[ledger.index[ledger.index.get_loc(days[0]) - 1]])
        expected = (stock_pnl + cash_pnl) / start_nav
        actual = float((1 + lines.ret).prod() - 1)
        rows.append(
            {
                "month": str(month),
                "reference_return": expected,
                "simulator_return": actual,
                "gap": actual - expected,
            }
        )
    gap = max((abs(row["gap"]) for row in rows), default=float("inf"))
    return {"months": len(rows), "max_return_gap": gap, "passed": gap < 1e-9, "rows": rows}
