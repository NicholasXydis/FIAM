"""Yearly validation performance, calculated from saved daily NAV ledgers."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine import inputs
from fiam.v4b.engine.mandate import load

OUT = Path(__file__).resolve().parents[1] / "out" / "engine"
MODELS = ("E0", "E1", "E2", "E2_Ma1", "E3", "fallback")


def performance(ledger: pd.DataFrame, rf: pd.Series, premium=0.04) -> pd.DataFrame:
    previous = ledger.nav.shift(1)
    earned = ledger.iloc[1:]
    rows = []
    for year, block in earned.groupby(earned.index.year):
        bench = rf.reindex(block.index) + premium / 252
        active = block.ret - bench
        growth = np.r_[1.0, (1 + block.ret).cumprod().to_numpy()]
        net = float(growth[-1] - 1)
        benchmark = float((1 + bench).prod() - 1)
        costs = block[["spread", "impact", "fees", "borrow"]].div(
            previous.reindex(block.index), axis=0
        )
        rows.append(
            {
                "year": int(year),
                "sessions": len(block),
                "start_nav": float(previous.loc[block.index[0]]),
                "end_nav": float(block.nav.iloc[-1]),
                "net_return": net,
                "benchmark_return": benchmark,
                "active_return_pp": net - benchmark,
                "relative_wealth_active": (1 + net) / (1 + benchmark) - 1,
                "net_ir": float(active.mean() / active.std(ddof=1) * np.sqrt(252))
                if active.std() > 0
                else None,
                "max_drawdown": float((growth / np.maximum.accumulate(growth) - 1).min()),
                "cost_pct_nav": float(costs.sum().sum()),
                **{c + "_pct_nav": float(costs[c].sum()) for c in costs},
            }
        )
    return pd.DataFrame(rows)


def main():
    m = load()
    tables = []
    for name in MODELS:
        ledger = pd.read_parquet(OUT / f"ledger_{name}.parquet")
        if ledger.index.max() > pd.Timestamp(m.policy.blind_until):
            raise ValueError("yearly validation report refuses an unsealed ledger")
        table = performance(ledger, inputs.cash_rate(ledger.index), premium=m.hard.premium)
        table.insert(0, "model", name)
        breach_path = OUT / f"breaches_{name}.parquet"
        if breach_path.exists():
            breaches = pd.read_parquet(breach_path)
            counts = breaches.groupby(breaches.date.dt.year).size()
            table["breach_rows"] = table.year.map(counts).fillna(0).astype(int)
        tables.append(table)
    result = pd.concat(tables, ignore_index=True)
    result.to_csv(OUT / "yearly_performance.csv", index=False)
    (OUT / "yearly_performance.json").write_text(
        json.dumps(result.to_dict("records"), indent=2) + "\n"
    )
    print(
        result[
            [
                "model",
                "year",
                "net_return",
                "benchmark_return",
                "net_ir",
                "max_drawdown",
                "cost_pct_nav",
            ]
        ].to_string(index=False)
    )
    return result


if __name__ == "__main__":
    main()
