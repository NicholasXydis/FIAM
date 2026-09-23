# Splits the cost model into parts and asks how much worse it can get before we lose.

import json
from pathlib import Path

import numpy as np
import pandas as pd

RETURNS = Path("submission/returns.csv")
OUT = Path("submission/exhibits")

HURDLE = 0.04 / 12

# Same schedule as the book, repeated so this exhibit states what it is testing.
COMMISSION_BPS, IMPACT_BPS, GC_BPS, HTB_BPS = 5.0, 8.0, 50.0, 250.0


# The cost lines a desk would recognise. Spread is the remainder, since we scaled it.
def components(df: pd.DataFrame) -> dict:
    traded = df["turnover"] * 2  # turnover is quoted one way, costs are charged both ways
    commission = traded * COMMISSION_BPS / 1e4
    impact = traded * IMPACT_BPS / 1e4
    borrow_gc = pd.Series(GC_BPS / 1e4 / 12, index=df.index)
    borrow_htb = df["htb_share"] * HTB_BPS / 1e4 / 12
    spread = df["cost"] - (commission + impact + borrow_gc + borrow_htb)
    return {
        "commission": float(commission.mean() * 12),
        "impact": float(impact.mean() * 12),
        "borrow_general_collateral": float(borrow_gc.mean() * 12),
        "borrow_hard_to_borrow": float(borrow_htb.mean() * 12),
        "spread": float(spread.mean() * 12),
        "total": float(df["cost"].mean() * 12),
    }


# How far costs can rise before active return hits zero. A level, not a multiple.
def break_even(df: pd.DataFrame) -> dict:
    gross, cost = df["gross"].mean() * 12, df["cost"].mean() * 12
    # Run past break-even so the chart crosses zero instead of stopping short.
    break_even_multiple = (gross - 0.04) / cost
    ladder = {}
    for multiple in (1.0, 1.5, 2.0, 2.5, 3.0, break_even_multiple, break_even_multiple * 1.15):
        active = df["gross"] - df["cost"] * multiple - HURDLE
        ladder[f"x{multiple:.2f}"] = dict(
            annual_cost=float(cost * multiple),
            active_annual=float(active.mean() * 12),
            information_ratio=float(active.mean() / active.std() * np.sqrt(12)),
        )
    return dict(
        current_annual_cost=float(cost),
        break_even_annual_cost=float(gross - 0.04),
        break_even_multiple=float(break_even_multiple),
        ladder=ladder,
    )


# Writes the cost breakdown and the break-even ladder.
def main() -> None:
    df = pd.read_csv(RETURNS, parse_dates=["holding_month"])
    out = dict(components=components(df), break_even=break_even(df))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_ladder.json").write_text(json.dumps(out, indent=2))

    print("annualized cost by component")
    for name, value in out["components"].items():
        print(f"  {name:<28} {value:>6.2%}")
    b = out["break_even"]
    print(
        f"\ncosts would have to rise from {b['current_annual_cost']:.1%} to "
        f"{b['break_even_annual_cost']:.1%} a year "
        f"({b['break_even_multiple']:.2f}x) before active return reaches zero"
    )


if __name__ == "__main__":
    main()
