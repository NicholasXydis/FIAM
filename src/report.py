# Copies the numbers from the results file into the table in RESULTS.md.
# Run it after the pipeline, so the write-up always shows what the code actually produced.

import json
from pathlib import Path

METRICS = Path("submission/metrics.json")
TARGET = Path("RESULTS.md")
START, END = "<!--AUTO:headline-->", "<!--/AUTO:headline-->"


# Builds the results table that goes into RESULTS.md.
def table(m: dict) -> str:
    perf, cost, comp, run = m["performance"], m["costs"], m["compliance"], m["run"]
    # A label and a number per row. We round hard on purpose, because our headline figures are
    # only accurate to about a tenth and more digits would pretend otherwise.
    rows = [
        ("Gross return (annualized)", f"{perf['return_gross_annual']:.1%}"),
        ("**Net return (annualized)**", f"**{perf['return_net_annual']:.1%}**"),
        ("CAGR (total return)", f"{perf['return_total_cagr']:.1%}"),
        ("Volatility", f"{perf['volatility_annual']:.1%}"),
        ("**Information ratio vs TB3MS + 4%**", f"**{perf['information_ratio']:.2f}**"),
        ("Sharpe ratio", f"{perf['sharpe_ratio']:.2f}"),
        ("Max drawdown (total return)", f"{perf['max_drawdown_total']:.1%}"),
        ("Hit rate", f"{perf['hit_rate_positive_active_months']:.1%}"),
        ("**Annualized alpha**",
         f"**{perf['alpha_annual']:.1%}** (t = {perf['alpha_tstat']:.2f}, HAC)"),
        ("**Realized beta**",
         f"**{perf['beta_realized']:.2f}** (se {perf['beta_stderr']:.2f})"),
        ("Correlation with market", f"{perf['correlation_with_market']:.2f}"),
        ("Positions", f"{comp['positions_average']:.0f}"),
        ("Max single-sector tilt", f"{comp['sector_tilt_max']:.2%}"),
        ("Max single position", f"{comp['position_weight_max']:.2%}"),
        ("Turnover, one-way monthly", f"{cost['turnover_monthly_one_way']:.0%}"),
        ("Costs as share of gross", f"{cost['cost_share_of_gross']:.0%}"),
        ("Holding months", f"{run['holding_months']}, {run['window']}"),
    ]
    # The date and code version at the bottom are how you spot an old table. If they are older
    # than your last pipeline run, these numbers came from a different one.
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    stamp = f"_Generated {run['generated_utc']} from commit `{run['git_commit']}`._"
    return f"| | |\n|---|---:|\n{body}\n\n{stamp}"


# Replaces the old table with a fresh one and leaves the rest of the file untouched.
def main() -> None:
    m = json.loads(METRICS.read_text())
    text = TARGET.read_text(encoding="utf-8")
    # Only the part between the two markers gets replaced. Everything else is written by hand
    # and has to survive untouched.
    a, b = text.index(START) + len(START), text.index(END)
    TARGET.write_text(text[:a] + "\n\n" + table(m) + "\n\n" + text[b:], encoding="utf-8")
    perf = m["performance"]
    print(f"RESULTS.md synced: IR {perf['information_ratio']:.2f}, "
          f"net {perf['return_net_annual']:.1%}")


if __name__ == "__main__":
    main()
