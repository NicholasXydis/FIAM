# Step 5's test: v3's stored 2016-2020 holdings through the daily book.

import json
import sys
from pathlib import Path

import pandas as pd

from fiam.v4 import daily_book, data

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "out" / "v2" / "brake+shorts+size+target10+voltarget+zerobeta@1e9" / "check"
OUT = ROOT / "out" / "v4" / "engine"
# The pass rule fixed before the run (PLAN §18 step 5).
MEAN_ABS_DIFF, MIN_CORR = 0.0005, 0.98
START, END = "2015-12-31", "2020-12-31"


# v3's month-end weights as formation-date targets.
def targets() -> dict:
    held = pd.read_parquet(V3 / "holdings.parquet")
    held["eom"] = pd.to_datetime(held["eom"]).astype("datetime64[ns]")
    return {eom: g.set_index("permno")["weight"] for eom, g in held.groupby("eom")}


# v3's own monthly excess return before costs, by holding month.
def v3_months() -> pd.Series:
    r = pd.read_csv(V3 / "returns.csv", parse_dates=["holding_month"])
    return r.set_index(r["holding_month"].dt.to_period("M"))["gross"].rename("v3")


# One replay at a lag, compared month by month with v3's record.
def compare(lag: int) -> tuple[dict, pd.DataFrame, daily_book.Result]:
    result = daily_book.run(targets(), START, END, lag=lag, nav=1e9, same_day=lag == 0)
    v4 = daily_book.monthly(result.daily)["excess"].rename("v4")
    both = pd.concat([v3_months(), v4], axis=1, join="inner").dropna()
    both["diff"] = both["v4"] - both["v3"]
    kinds = result.events["kind"].value_counts().to_dict()
    # The per-name ledger and the bill rebuild the NAV path to the cent.
    gained = result.ledger["dollars"].sum() + result.daily["interest"].sum()
    gap = gained - (result.daily["nav"].iloc[-1] - 1e9)
    summary = dict(
        lag=lag,
        months=len(both),
        mean_diff=float(both["diff"].mean()),
        mean_abs_diff=float(both["diff"].abs().mean()),
        max_abs_diff=float(both["diff"].abs().max()),
        worst_month=str(both["diff"].abs().idxmax()),
        corr=float(both["v3"].corr(both["v4"])),
        v3_mean=float(both["v3"].mean()),
        v4_mean=float(both["v4"].mean()),
        events={k: int(v) for k, v in sorted(kinds.items())},
        trades=int(len(result.trades)),
        ledger_minus_nav_dollars=float(gap),
        breach_days=int(len(daily_book.breaches(result))),
    )
    # Only the same-day replay is judged; t+1 is reported beside it.
    summary["judged"] = lag == 0
    summary["within_bar"] = bool(
        summary["mean_abs_diff"] < MEAN_ABS_DIFF and summary["corr"] > MIN_CORR
    )
    return summary, both, result


# Each held day's move past 50% beside the panel's month return (§6.4).
def big_moves(result: daily_book.Result) -> pd.DataFrame:
    moves = result.events[result.events["kind"] == "big_move"].copy()
    moves["eom"] = moves["date"] + pd.offsets.MonthEnd(0)
    panel = data.panel(moves["permno"], moves["eom"].min(), moves["eom"].max(), ("ret",))
    return moves.merge(
        panel.rename(columns={"ret": "panel_month_ret"}), on=["permno", "eom"], how="left"
    )


# δ against a CRSP total-return book, both ex-day rules, price only.
def dividend_check() -> dict:
    report = {}
    for name, lag in (("same_day", 0), ("t_plus_1", 1)):
        books = {}
        for label, basis, ex in (
            ("delta", "delta", "crsp"),
            ("delta_2026_rule", "delta", "dsf"),
            ("delta_month_end", "delta", "month_end"),
            ("crsp", "crsp", "crsp"),
            ("price_only", "none", "crsp"),
        ):
            result = daily_book.run(
                targets(),
                START,
                END,
                lag=lag,
                nav=1e9,
                dividends=basis,
                ex_days=ex,
                same_day=lag == 0,
            )
            books[label] = result.daily
        months = {k: daily_book.monthly(v)["excess"] for k, v in books.items()}
        years = len(months["delta"]) / 12
        row = {}
        # Each δ book against the CRSP book, month by month.
        for label in ("delta", "delta_2026_rule", "delta_month_end"):
            gap = months[label] - months["crsp"]
            row[label] = dict(
                mean_minus_crsp=float(gap.mean()),
                mean_abs_minus_crsp=float(gap.abs().mean()),
                max_abs_minus_crsp=float(gap.abs().max()),
                worst_month=str(gap.abs().idxmax()),
                dividends_per_year=float(books[label]["dividends"].sum() / 1e9 / years),
            )
        row["crsp_dividends_per_year"] = float(books["crsp"]["dividends"].sum() / 1e9 / years)
        row["total_minus_price_only_per_year"] = float(
            (months["delta"] - months["price_only"]).mean() * 12
        )
        report[name] = row
    return report


# Each 2026 ex-day rule run on 2016-2020 against CRSP's exact days.
def rule_2026_check() -> dict:
    report = {}
    for name, lag in (("same_day", 0), ("t_plus_1", 1)):
        runs = {
            rule: daily_book.monthly(
                daily_book.run(
                    targets(), START, END, lag=lag, nav=1e9, ex_days=rule, same_day=lag == 0
                ).daily
            )["excess"]
            for rule in ("crsp", "dsf", "bound", "month_end")
        }
        row = {}
        # A is the headline, B the robustness line, C the first wording.
        for rule, label in (
            ("dsf", "A_sharpest_fall"),
            ("bound", "B_least_good"),
            ("month_end", "C_month_end"),
        ):
            gap = runs[rule] - runs["crsp"]
            row[label] = dict(
                mean=float(gap.mean()),
                mean_abs=float(gap.abs().mean()),
                worst=float(gap.abs().max()),
                worst_month=str(gap.abs().idxmax()),
                total=float(gap.sum()),
                months_above=int((gap > 1e-7).sum()),
                months_below=int((gap < -1e-7).sum()),
            )
        report[name] = row
    return report


# Both replays written to out/v4/engine; the same-day one is the test.
def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(
        rule=f"mean |v4 - v3| < {MEAN_ABS_DIFF:.2%} a month and correlation > {MIN_CORR}",
        source=str(V3.relative_to(ROOT)),
    )
    for name, lag in (("same_day", 0), ("t_plus_1", 1)):
        summary, both, result = compare(lag)
        report[name] = summary
        both.to_csv(OUT / f"replay_v3_{name}.csv", index_label="month")
        events = result.events.assign(date=result.events["date"].dt.date)
        events[events["kind"] != "halt_day"].to_csv(
            OUT / f"replay_v3_{name}_events.csv", index=False
        )
        big_moves(result).to_csv(OUT / f"replay_v3_{name}_big_moves.csv", index=False)
        for label, frame in daily_book.logs(result).items():
            frame.to_csv(OUT / f"replay_v3_{name}_{label}.csv", index=False)
    report["dividends"] = dividend_check()
    report["rule_2026"] = rule_2026_check()
    report["passes"] = report["same_day"]["within_bar"]
    (OUT / "replay_v3.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    sys.exit(0 if main()["passes"] else 1)
