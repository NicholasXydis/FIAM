# The research desk: a devil's advocate checked by code, and a PM memo that fails closed.

import json
import re
import sys
from pathlib import Path

import pandas as pd

from fiam import paths, v2
from fiam.agents import critic
from fiam.agents import harness as H

OUT = v2.OUT / "desk.json"
MEMO = v2.OUT / "pm_memo.md"
# Final v3's desk (final_exhibits.md): the same agents on the book we present, written apart.
FINAL_OUT, FINAL_MEMO = v2.OUT / "desk_final.json", v2.OUT / "pm_memo_final.md"


# Where each test's number comes from: v1's submission, or final v3's pack and runs.
def sources(book: str) -> dict:
    stress = json.loads((v2.OUT / "stress.json").read_text(encoding="utf-8"))
    crowd = json.loads((v2.OUT / "crowd_lab.json").read_text(encoding="utf-8"))
    if book == "v1":
        return dict(
            metrics=json.loads(paths.METRICS.read_text(encoding="utf-8")),
            daily_beta=critic.load("daily_risk.json").get("beta_to_sp500_daily", {}).get("beta"),
            stress=stress["v1"],
            crowd=crowd.get("v1@1e7 record", {}),
            check_ir=critic.load("confirmation.json")
            .get("confirmation_2016_2020", {})
            .get("information_ratio"),
        )
    name = v2.Settings(v2.final_three()).name
    evidence = json.loads((v2.OUT / "evidence.json").read_text(encoding="utf-8"))
    pack = Path("out") / "finals" / name / "submission" / "metrics.json"
    check = json.loads((v2.OUT / name / "check" / "stats.json").read_text(encoding="utf-8"))
    return dict(
        metrics=json.loads(pack.read_text(encoding="utf-8")),
        daily_beta=evidence.get("final_daily", {}).get("dimson_beta"),
        stress=stress["final v3"],
        crowd=crowd.get(f"{name} record", {}),
        check_ir=check["information_ratio"],
    )


# The registry: each test reads one number our code already wrote, and says when it is a problem.
def tests(book: str = "v1") -> dict:
    src = sources(book)
    metrics = src["metrics"]
    perf, costs, comp = metrics["performance"], metrics["costs"], metrics["compliance"]
    rob = metrics["robustness"]
    stress = src["stress"]
    rows = {
        "alpha_below_hurdle": (
            "Alpha t-statistic is below the t > 3 hurdle",
            perf["alpha_tstat"],
            "<",
            3.0,
        ),
        "daily_beta_short": (
            "Daily beta to the S&P 500 is negative",
            src["daily_beta"] or 0.0,
            "<",
            0.0,
        ),
        "monthly_beta_drift": (
            "Monthly realized beta is outside +/-0.10",
            abs(perf["beta_realized"]),
            ">",
            0.10,
        ),
        "costs_heavy": (
            "Costs take over a quarter of gross return",
            costs["cost_share_of_gross"],
            ">",
            0.25,
        ),
        "turnover_high": (
            "One-way monthly turnover is above 40%",
            costs["turnover_monthly_one_way"],
            ">",
            0.40,
        ),
        "borrow_crowded": (
            "Over 20% of the short book is hard to borrow",
            costs["hard_to_borrow_share_of_short_book"],
            ">",
            0.20,
        ),
        "luck_possible": (
            "Probability the edge is real after every trial is below 50%",
            rob["deflated_sharpe_probability_all"],
            "<",
            0.5,
        ),
        "weak_2016_2020": (
            "The same book lost against its hurdle in 2016-2020",
            src["check_ir"] or 0.0,
            "<",
            0.0,
        ),
        "one_style": (
            "One style (profitability) loads above 0.5",
            stress["loadings"]["rmw"],
            ">",
            0.5,
        ),
        "junk_rally_risk": (
            "The likeliest 10% loss comes from profitability falling",
            stress["reverse_stress"]["move"]["rmw"],
            "<",
            0.0,
        ),
        "short_illiquid": (
            "At $1B the short side takes over 5 days to cover on average",
            stress["liquidity"]["1e+09"]["short"]["weighted_mean"],
            ">",
            5.0,
        ),
        "crowded_with_ai": (
            "Returns load positively on the AI crowd's favourites",
            src["crowd"].get("crowding_beta", {}).get("beta", 0.0),
            ">",
            0.0,
        ),
        "sector_tilt": (
            "Some sector tilt exceeds 1% after rounding",
            comp["sector_tilt_max"],
            ">",
            0.01,
        ),
        "deep_drawdown": (
            "Worst drawdown is deeper than -7%",
            perf["max_drawdown_total"],
            "<",
            -0.07,
        ),
        "concentrated": (
            "The largest position exceeds 1.5%",
            comp["position_weight_max"],
            ">",
            0.015,
        ),
    }
    return {
        k: dict(text=t, value=float(v), problem=(v < x) if op == "<" else (v > x))
        for k, (t, v, op, x) in rows.items()
    }


# The critic picks the problems it expects from the descriptions alone; code then checks each.
def advocate(server: H.Server, registry: dict) -> dict:
    listing = "\n".join(f"{k}: {v['text']}" for k, v in registry.items())
    system = (
        "You are the devil's advocate on an investment committee reviewing a market-neutral US "
        "equity book. From the list of checks below, pick the five you expect to show a problem, "
        "each with a one-sentence reason. Pick by test id only."
    )
    ids = list(registry)
    item = dict(
        type="object",
        properties=dict(test=dict(type="string", enum=ids), reason=dict(type="string")),
        required=["test", "reason"],
    )
    schema = dict(
        type="object",
        properties=dict(critiques=dict(type="array", items=item, minItems=5, maxItems=5)),
        required=["critiques"],
    )
    reply = server.chat(
        [dict(role="system", content=system), dict(role="user", content=listing)], schema=schema
    )
    picks = H.parse(reply).get("critiques", [])
    # A test named twice counts once.
    first = {p["test"]: p for p in reversed(picks) if p.get("test") in registry}
    checked = [
        p | dict(confirmed=bool(registry[p["test"]]["problem"]), value=registry[p["test"]]["value"])
        for p in picks
        if first.get(p.get("test")) is p
    ]
    # Most checks flag something, so a random pick would confirm this many by chance.
    chance = sum(v["problem"] for v in registry.values()) / len(registry) * len(checked)
    confirmed = sum(c["confirmed"] for c in checked)
    return dict(critiques=checked, confirmed=confirmed, asked=len(checked), chance=chance)


# The September memo from facts our code computed; any number not among them stops it being written.
def memo(server: H.Server, facts: dict, path: Path = MEMO) -> dict:
    sheet = "\n".join(f"{k}: {v}" for k, v in facts.items())
    system = (
        "Write a one-page memo to a portfolio manager about next month's market-neutral book, "
        "using only the facts given. Cover what the book holds, its risks and what to watch. Use "
        "no number that is not in the facts."
    )
    text = (
        server.chat([dict(role="system", content=system), dict(role="user", content=sheet)]).get(
            "content"
        )
        or ""
    )

    # A range such as 2016-2020 is two numbers, not 2016 and minus 2020.
    def plain(s: str) -> str:
        return re.sub(r"(?<=\d)\s?[-–]\s?(?=\d)", " to ", s)

    seen = critic.numbers(plain(sheet))
    # List numbering is layout, not a claim, so it is left out of the check.
    claims = plain(re.sub(r"(?m)^\s*\d+[.)]\s", "", text))
    unsupported = [n for n in critic.numbers(claims) if not critic.supported(n, seen)]
    # Fails closed: no memo, and no older memo left behind to be mistaken for this one.
    path.unlink(missing_ok=True)
    if not unsupported:
        path.write_text(text + "\n", encoding="utf-8")
    return dict(written=not unsupported, unsupported_numbers=unsupported[:10])


# The September v1 book's ten largest named positions, each explained from its own signal ranks
# (crowd_amendment_1.md); a name whose text uses a number not in its facts is dropped and counted.
def september(server: H.Server, held: Path | None = None) -> dict:
    from fiam import book as P
    from fiam import data
    from fiam.exhibits import september as S
    from fiam.freeze import FROZEN

    labels = json.loads((FROZEN / "characteristic_labels.json").read_text(encoding="utf-8"))
    book = pd.read_csv(held or S.V1).dropna(subset=["company_name"])
    book = book.loc[book["weight"].abs().sort_values(ascending=False).index].head(10)
    panel = data.features(list(P.SIGNALS))
    month = panel[panel["eom"] == S.DECISION].set_index("permno")[list(P.SIGNALS)]
    ranks = month.rank(pct=True).mul(100).round()
    system = (
        "In two sentences, tell a portfolio manager why a market-neutral quant book holds this "
        "stock on the side given, using only the facts: percentile ranks among US stocks this "
        "month, each marked with which direction the book prefers. Use no other number."
    )
    out, dropped = [], 0
    for _, row in book.iterrows():
        side = "long" if row["weight"] > 0 else "short"
        facts = "\n".join(
            f"{labels.get(c, c)} ({'higher' if s > 0 else 'lower'} is better): "
            f"{ranks.loc[row['permno'], c]:.0f}"
            for c, s in P.SIGNALS.items()
            if row["permno"] in ranks.index and pd.notna(ranks.loc[row["permno"], c])
        )
        ask = f"{row['company_name']} ({row['ticker']}), {side}.\nFacts:\n{facts}"
        messages = [dict(role="system", content=system), dict(role="user", content=ask)]
        text = server.chat(messages).get("content") or ""
        seen = critic.numbers(facts)
        if all(critic.supported(n, seen) for n in critic.numbers(text)):
            out.append(dict(ticker=row["ticker"], side=side, why=text.strip()))
        else:
            dropped += 1
    return dict(explained=out, dropped=dropped)


# What final v3 was betting on, told from its yearly style exposures; a number not in the table
# stops the account being kept (final_exhibits.md).
def factor_story(server: H.Server, by_year: dict) -> dict:
    table = "\n".join(
        f"{year}: " + ", ".join(f"{style} {value:+.2f}" for style, value in row.items())
        for year, row in by_year.items()
    )
    system = (
        "In four sentences, tell a portfolio manager what a market-neutral US equity book was "
        "betting on and how that changed, from its average exposure per unit of gross to five "
        "styles each year (positive means long the style). Use no number that is not in the table."
    )
    messages = [dict(role="system", content=system), dict(role="user", content=table)]
    text = (server.chat(messages).get("content") or "").strip()
    seen = critic.numbers(table)
    unsupported = [n for n in critic.numbers(text) if not critic.supported(n, seen)]
    return dict(story=text if not unsupported else "", unsupported_numbers=unsupported[:10])


# Every agent on final v3's book, written beside v1's desk.
def final(part: str = "all") -> None:
    from fiam.exhibits import september as S

    registry = tests("final")
    out = FINAL_OUT
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    report["book"] = v2.Settings(v2.final_three()).name
    if part in ("all", "advocate"):
        with H.Server("gemma") as server:
            report["advocate"] = advocate(server, registry)
    if part in ("all", "memo", "september", "story"):
        facts = {
            f"{v['text']} ({'true' if v['problem'] else 'false'}; value)": round(v["value"], 4)
            for v in registry.values()
        }
        exhibits = json.loads((v2.OUT / "final_exhibits" / "report.json").read_text())
        with H.Server("qwen") as server:
            if part in ("all", "memo"):
                report["memo"] = memo(server, facts, FINAL_MEMO)
            if part in ("all", "september"):
                report["september"] = september(server, S.FINAL)
            if part in ("all", "story"):
                report["factor_story"] = factor_story(
                    server, exhibits["exposures"]["styles_by_year"]
                )
    report["registry"] = registry
    out.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "registry"}, indent=1, default=float))


def main(part: str = "all") -> None:
    registry = tests()
    report = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if part in ("all", "advocate"):
        with H.Server("gemma") as server:
            report["advocate"] = advocate(server, registry)
    if part in ("all", "memo"):
        # Each fact as the check it measures and its value, so the writer knows what it means.
        facts = {
            f"{v['text']} ({'true' if v['problem'] else 'false'}; value)": round(v["value"], 4)
            for v in registry.values()
        }
        with H.Server("qwen") as server:
            report["memo"] = memo(server, facts)
    if part == "september":
        with H.Server("qwen") as server:
            report["september"] = september(server)
    report["registry"] = registry
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "registry"}, indent=1, default=float))


# uv run python -m fiam.agents.desk [all | advocate | memo | september] [final]
if __name__ == "__main__":
    final(sys.argv[1]) if sys.argv[2:3] == ["final"] else main(*sys.argv[1:2])
