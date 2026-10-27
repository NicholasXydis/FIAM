# Capacity exhibits: break-even size, gaps to the shipped book, stress.

import json
import sys

import numpy as np
import pandas as pd

from fiam import costs as C
from fiam import layers, stats, v2
from fiam import mandate as M
from fiam.exhibits import evidence as E

OUT = v2.OUT / "capacity.json"
TAGS = {c: f"{c:.0e}".replace("+0", "") for c in v2.CAPITALS}
STRESS = ("impact_half", "taq_spreads")


# Each book's run-name prefix; later books join once verdicts exist.
def books() -> dict:
    out = {"v1": "v1", "v2": "v2", "v2a": "v2a"}
    if (v2.OUT / "evidence.json").exists():
        out["v2-pass"] = v2.Settings(v2.passing()).name.split("@")[0]
        final = v2.final()
        if final is not None:
            out["v3"] = v2.Settings(final).name.split("@")[0]
        chosen = v2.final_three()
        if chosen is not None:
            out["final v3"] = v2.Settings(chosen).name.split("@")[0]
            # The chosen book at three risk targets, shown beside it, never picked.
            for vol in (6, 8, 12):
                out[f"final v3 at {vol}%"] = f"risk{vol}_" + out["final v3"]
    return out


# A book by capital: IR, yearly net, cost and dollars over the T-bill.
def curve(prefix: str, window: str) -> list[dict]:
    rows = []
    for cap, tag in TAGS.items():
        run = E.load(f"{prefix}@{tag}", window)
        if run:
            s = run[2]
            rows.append(
                dict(
                    capital=cap,
                    information_ratio=s["information_ratio"],
                    net_annual=s["net_annual"],
                    cost_annual=s["cost_annual"],
                    dollars=s["net_annual"] * cap,
                )
            )
    return rows


# Where IR over T-bill + 4% crosses zero, in log capital, or a bound.
def break_even(rows: list[dict]) -> float | str:
    for a, b in zip(rows, rows[1:]):
        if a["information_ratio"] > 0 >= b["information_ratio"]:
            share = a["information_ratio"] / (a["information_ratio"] - b["information_ratio"])
            x = np.log10(a["capital"]) + share * (np.log10(b["capital"]) - np.log10(a["capital"]))
            return float(10**x)
    if rows and rows[0]["information_ratio"] <= 0:
        return "below $1M"
    return "above $5B"


# Book minus the shipped book at $1B and $5B, net 2021-2026, bootstrap.
def gaps(prefix: str) -> dict:
    out = {}
    for cap in (1e9, 5e9):
        a, b = E.load(f"v1@{TAGS[cap]}", "record"), E.load(f"{prefix}@{TAGS[cap]}", "record")
        if a and b:
            diff = (b[0]["net"] - a[0]["net"]).dropna()
            out[TAGS[cap]] = stats.bootstrap_mean(diff)
    return out


# Median TAQ effective half spread over our model's, by size, 2016-2020.
def taq_ratios() -> dict:
    taq = layers.load("trading/spreads_monthly")
    taq = taq.assign(eom=pd.to_datetime(taq["eom"]), permno=taq["permno"].astype(int))
    df = E.frame("check", frozenset())
    ours = df[["permno", "eom", "size_grp"]].assign(ours=C.half_spread(df).to_numpy())
    both = ours.merge(taq, on=["permno", "eom"])
    both["ratio"] = both["EffectiveSpread_Percent_DW_median"] / 2 / both["ours"]
    both = both.replace([np.inf, -np.inf], np.nan).dropna(subset=["ratio"])
    return {str(k): float(v) for k, v in both.groupby("size_grp")["ratio"].median().items()}


# One stress scenario in this process: shipped and switched, 2021-2026.
def stress(scenario: str) -> None:
    if scenario == "impact_half":
        C.IMPACT_Y = 0.5
    else:
        ratios, plain = taq_ratios(), C.half_spread
        C.half_spread = lambda q: plain(q) * q["size_grp"].map(ratios).fillna(1.0).to_numpy()
        (v2.OUT / f"{scenario}_ratios.json").write_text(json.dumps(ratios, indent=1) + "\n")
    rules, fixed = M.Mandate(name=scenario), v2.params()
    for on in (frozenset(), v2.V2):
        for cap in v2.CAPITALS:
            s = v2.run(v2.Settings(on, cap, rules), v2.RECORD, fixed)
            print(f"{scenario} {'v2' if on else 'v1'} {TAGS[cap]} IR {s['information_ratio']:+.2f}")


# Writes the capacity report, or runs one stress scenario when asked.
def main(args: list[str]) -> None:
    if args[:1] == ["stress"]:
        stress(args[1])
        return
    report = dict(protocol="docs/protocols/capacity.md", books={})
    for name, prefix in books().items():
        entry = {w: curve(prefix, w) for w in ("check", "record")}
        rec = entry["record"]
        entry["break_even"] = break_even(rec)
        entry["peak"] = max(rec, key=lambda r: r["dollars"])["capital"] if rec else None
        entry["minus_v1"] = gaps(prefix) if name != "v1" else {}
        report["books"][name] = entry
    report["stress"] = {}
    for scenario in STRESS:
        for book, prefix in (("v1", f"{scenario}_v1"), ("v2", f"{scenario}_v2")):
            rows = curve(prefix, "record")
            if rows:
                at_1b = next((r["cost_annual"] for r in rows if r["capital"] == 1e9), None)
                report["stress"][f"{scenario} {book}"] = dict(
                    break_even=break_even(rows), cost_at_1bn=at_1b, rows=rows
                )
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    for name, e in report["books"].items():
        print(name, "break-even", e["break_even"], "peak", e["peak"])


if __name__ == "__main__":
    main(sys.argv[1:])
