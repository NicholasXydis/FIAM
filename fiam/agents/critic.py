# The devil's-advocate agent on a second vendor's model, to critic.json.

from __future__ import annotations

import json
import re
import sys
from functools import cached_property

import numpy as np
import pandas as pd

from fiam import data, paths
from fiam.agents import harness as H

ROOT = H.ROOT
EXHIBITS = ROOT / paths.EXHIBITS
PROMPT = ROOT / "fiam" / "agents" / "prompts" / "critic.md"

# Ten each side. Fewer misses the book's character, more goes unread.
TOP_N = 10

TASK = (
    "Attack this market-neutral book. Find the positions, exposures and assumptions a sceptical "
    "investment committee would challenge first, and whether the book we chose to ship deserved "
    "it over the others we tried."
)

# What must match for two runs to count as the same run.
SAME_INPUTS = (
    "model_sha256",
    "system_sha256",
    "task_sha256",
    "tools_sha256",
    "seed",
    "temperature",
)


# An exhibit the pipeline wrote, or nothing if that step has not run.
def load(name: str) -> dict:
    path = EXHIBITS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# Top ten longs and shorts by mean weight, or by="pnl" winners, losers.
def positions(by: str = "weight") -> list[dict]:
    book = paths.holdings()
    book["w"] = book["WEIGHT"] / 100
    months = book["Date"].nunique()
    # Grouped on PERMNO alone, or a ticker change splits one security.
    held = book.groupby("PERMNO", as_index=False).agg(
        weight_while_held=("w", "mean"), months_held=("w", "size"), as_of=("Date", "max")
    )
    latest = book.sort_values("Date").groupby("PERMNO").last()[["TICKER", "COMPANY NAME"]]
    held = held.merge(latest.rename(columns={"COMPANY NAME": "company"}), on="PERMNO", how="left")
    held["mean_weight"] = held["weight_while_held"] * held["months_held"] / months

    panel = data.panel(["ret_exc_lead1m", "me", "dolvol_126d", "size_grp"])
    panel["eom"] = panel["eom"].astype("datetime64[ns]")
    # Realized P&L of each name, so the critic knows what it is attacking.
    panel["Date"] = (panel["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    pnl = book.merge(panel, left_on=["PERMNO", "Date"], right_on=["permno", "Date"], how="left")
    pnl = (pnl["w"] * pnl["ret_exc_lead1m"].fillna(0.0)).groupby(pnl["PERMNO"]).sum()
    held["pnl"] = held["PERMNO"].map(pnl).fillna(0.0)
    key = "pnl" if by == "pnl" else "mean_weight"
    names = pd.concat([held.nlargest(TOP_N, key), held.nsmallest(TOP_N, key)])
    # Traits as of the last decision month. Later rows add unknown facts.
    names["eom"] = (names["as_of"] - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    facts = pd.merge_asof(
        names.sort_values("eom"),
        panel[panel["permno"].isin(names["PERMNO"])].sort_values("eom"),
        on="eom",
        left_by="PERMNO",
        right_by="permno",
        direction="backward",
    ).set_index("PERMNO")
    items = filing_items(dict(zip(names["PERMNO"], names["eom"])))

    out = []
    for row in names.itertuples():
        # A list lookup returns a frame, so a repeated name still gives one row.
        c = facts.loc[[row.PERMNO]].iloc[0]
        out.append(
            dict(
                permno=int(row.PERMNO),
                ticker=row.TICKER,
                company=row.company,
                side="LONG" if row.mean_weight > 0 else "SHORT",
                mean_weight_all_months_pct=round(row.mean_weight * 100, 3),
                weight_while_held_pct=round(row.weight_while_held * 100, 3),
                months_held=int(row.months_held),
                realized_pnl_pct=round(float(pnl.get(row.PERMNO, 0.0)) * 100, 3),
                market_cap_musd=round(float(c.get("me", np.nan)), 1),
                dollar_volume=round(float(c.get("dolvol_126d", np.nan)), 1),
                size_group=str(c.get("size_grp", "")),
                filing_item_codes=items.get(int(row.PERMNO), []),
            )
        )
    return out


# Item codes filed by each name's decision month, none filed later.
def filing_items(cutoff: dict) -> dict[int, list[str]]:
    table = data.filings(["permno", "filing_date", "items"])
    table = table[table["permno"].isin(cutoff)]
    table = table[pd.to_datetime(table["filing_date"]) <= table["permno"].map(cutoff)]
    return {
        int(p): sorted({i for items in g["items"] if items is not None for i in items})
        for p, g in table.groupby("permno")
    }


# The facts the critic may use, all from exhibits already written.
class Evidence:
    # Starts with nothing shown, so every number quoted can be traced.
    def __init__(self):
        self.seen: list[str] = []

    # Built on first use, so the tools cost nothing until one is called.
    @cached_property
    def pack(self) -> list[dict]:
        return positions()

    # Every result is kept, so final claims are checked against the shown.
    def show(self, result: object) -> object:
        self.seen.append(json.dumps(result, default=str))
        return result

    # The ten largest longs and shorts, by ticker and name.
    def list_positions(self) -> list:
        keep = ("ticker", "company", "side", "mean_weight_all_months_pct", "months_held")
        return self.show([{k: p[k] for k in keep} for p in self.pack])

    # Unknown tickers are reported back, never guessed.
    def position(self, ticker: str) -> dict:
        match = [p for p in self.pack if p["ticker"].upper() == ticker.upper()]
        return self.show(match[0] if match else {"error": f"{ticker} is not one of the twenty"})

    # A risk committee's first asks: factor loadings, borrow, clean test.
    def book_risk(self) -> dict:
        metrics = paths.read_json(paths.METRICS)
        pack = load("pack.json")
        return self.show(
            dict(
                five_factor_momentum=pack.get("risk", {}).get("five_factor_momentum"),
                # Each year's return split into six-factor pay and stock selection.
                style_or_selection_by_year=pack.get("risk", {}).get("style_by_year"),
                hard_to_borrow_share_of_short_book=metrics["costs"][
                    "hard_to_borrow_share_of_short_book"
                ],
                # Where our longs and shorts sit among what AI crowd agents would buy.
                crowd_percentile_of_our_book=pack.get("crowding"),
                realized_beta=metrics["performance"]["beta_realized"],
                frozen_book_on_2016_2020=load("confirmation.json").get("confirmation_2016_2020"),
            )
        )

    # Each variant with its result, the final book and the recall test.
    def what_we_tried(self) -> dict:
        from fiam.exhibits import config_log

        tried = [dict(experiment=r[0], result=r[4], verdict=r[5]) for r in config_log.rows()]
        return self.show(
            dict(
                shipped_information_ratio=paths.read_json(paths.METRICS)["performance"][
                    "information_ratio"
                ],
                tried=tried,
                analyst_recall_test=load("analyst_learned.json").get("recall_test"),
            )
        )

    # Which signals earned the return, to test "the alpha is one factor".
    def signal_attribution(self) -> dict:
        full = load("pack.json").get("attribution", {}).get("full", {})
        return self.show({k: v.get("contribution_annual") for k, v in full.items()})


# Numbers in text, thousands commas dropped so "19,169,939" is one.
def numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+\.?\d*", re.sub(r"(?<=\d),(?=\d{3})", "", text))


# A claim's number is supported if a tool showed it, at its precision.
def supported(claim: str, seen: list[str]) -> bool:
    shown = [float(x) for x in numbers(" ".join(seen))]
    for token in numbers(claim):
        value = float(token)
        decimals = len(token.split(".")[1]) if "." in token else 0
        # Claims often quote a share as a percent, so allow a factor of 100.
        candidates = [round(v, decimals) for v in shown] + [round(v * 100, decimals) for v in shown]
        if value not in candidates and abs(value) > 1:
            return False
    return True


# Five read-only tools and the answer. No panel or weight is reachable.
def tools(evidence: Evidence) -> list[H.Tool]:
    empty = dict(type="object", properties={})
    critique = dict(
        type="object",
        properties=dict(
            target=dict(type="string", description="a ticker, 'book', or 'the choice'"),
            claim=dict(type="string", description="the objection, quoting only numbers you saw"),
            severity=dict(type="string", enum=["low", "medium", "high"]),
        ),
        required=["target", "claim", "severity"],
    )
    ticker = dict(type="object", properties=dict(ticker=dict(type="string")), required=["ticker"])
    answer = dict(
        type="object",
        properties=dict(critiques=dict(type="array", items=critique, minItems=1)),
        required=["critiques"],
    )
    return [
        H.Tool(
            "list_positions", "The ten largest longs and shorts.", empty, evidence.list_positions
        ),
        H.Tool(
            "position",
            "Everything known about one position: realized P&L, size, liquidity, 8-K items.",
            ticker,
            evidence.position,
        ),
        H.Tool(
            "book_risk",
            "Factor loadings, style or selection by year, borrow, crowding, the 2016-2020 test.",
            empty,
            evidence.book_risk,
        ),
        H.Tool(
            "what_we_tried",
            "Every variant we tested with its result and verdict, and the analyst recall test.",
            empty,
            evidence.what_we_tried,
        ),
        H.Tool(
            "signal_attribution",
            "Each signal's contribution to gross return, % a year.",
            empty,
            evidence.signal_attribution,
        ),
        H.Tool(
            "final_answer",
            "Your critiques. Quote only numbers a tool returned.",
            answer,
            lambda critiques: dict(accepted=True, count=len(critiques)),
        ),
    ]


# One critic run. The tag names the transcript, so repeats never clash.
def critique(server: H.Server, tag: str = "") -> dict:
    system = PROMPT.read_text(encoding="utf-8")
    budget = 6 if paths.SMOKE else 30
    run = H.Run("critic", "gemma", system, TASK, budget, tag=tag)
    return H.run_agent(server, run, tools(Evidence()))


# The same inputs again, call by call. Same is repeatable, not right.
def repeat() -> None:
    first = H.TRANSCRIPTS / "critic.jsonl"
    with H.Server("gemma") as server:
        result = critique(server, tag="repeat")
    header = [
        json.loads(p.read_text(encoding="utf-8").splitlines()[0])["header"]
        for p in (first, result["transcript"])
    ]
    out = load("critic.json")
    out["repeatability"] = dict(
        what="The same run twice with identical inputs, compared call by call.",
        identical_inputs=all(header[0][k] == header[1][k] for k in SAME_INPUTS),
        comparison=H.repeatable(first, result["transcript"]),
        runtime=header[1]["server"],
    )
    paths.write_json(EXHIBITS / "critic.json", out, rounded=False)
    print(json.dumps(out["repeatability"], indent=2))


# One critic run, its critiques checked against what the tools showed.
def main() -> None:
    with H.Server("gemma") as server:
        result = critique(server)
    critiques = (result["answer"] or {}).get("critiques", [])
    checked = [
        dict(c, numbers_supported=supported(c.get("claim", ""), result["seen"])) for c in critiques
    ]
    out = dict(
        what="Devil's advocate on a second vendor's model. Retrospective, names visible, so "
        "never a forecast. Every quoted number is checked against what the tools showed.",
        status=result["status"],
        steps=result["steps"],
        plan_revisions=len(result["plans"]),
        critiques=checked,
        unsupported=sum(1 for c in checked if not c["numbers_supported"]),
        transcript=result["transcript"].relative_to(ROOT).as_posix(),
    )
    paths.write_json(EXHIBITS / "critic.json", out, rounded=False)
    print(f"{len(checked)} critiques, {out['unsupported']} with numbers no tool showed")


if __name__ == "__main__":
    repeat() if "--repeat" in sys.argv else main()
