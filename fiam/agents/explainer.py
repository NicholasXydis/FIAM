# Why the book held its best and worst names, in words tied to facts.

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from fiam.agents import explainer_facts as E
from fiam.agents import final_book as F
from fiam.agents import harness as H

# The explainer's instructions and the one field each answer must fill.
SYSTEM = (
    "You explain to an investment committee why a quantitative portfolio held a position that "
    "became one of its largest winners or losers: which signals put it in the book, and what it "
    "contributed. Use only the facts given, cite the numbers you rely on, and never add anything "
    "you know about the company or what happened to it later. Two or three sentences."
)
SCHEMA = dict(type="object", properties=dict(why=dict(type="string")), required=["why"])

# Work files and call logs, gitignored; FIAM_EXPLAINER_WORK moves them.
WORK = Path(os.environ.get("FIAM_EXPLAINER_WORK", str(H.ROOT / "cache" / "agents" / "explainer")))
FACTS = WORK / "facts.json"
RAW = WORK / "explainer_raw.json"
LOG = WORK / "calls.jsonl"
# The committed record the render step writes.
OUT_JSON = F.PACK / "explanations.json"
OUT_MD = F.PACK / "explanations.md"
# Most calls one run may make, counted from the log across restarts.
CAP = 60
PROMPT_VERSION = 2
HOW_BUILT = (
    "Ranking: an E-LASSO model refit monthly on 150 stock characteristics gives each stock a "
    "forecast score, times a regime dial rho. Construction: a factor risk model and optimiser "
    "set the weights, with market beta 0, each sector's net within plus or minus 1%, longs at "
    "most 3.9% and shorts at most 1%, rebalanced at month end plus a mid-month review. A "
    "position whose forecast points against it is held because the optimiser needed it for "
    "these limits or for risk, not for its forecast. No AI sets or changes any weight."
)
TASK = (
    "Write 2 or 3 plain-English sentences for this position, for an investment committee. "
    "Sentence 1: when the trade went on, on which side, and why: the forecast at entry and the "
    "two or three strongest drivers, each named in words with whether the stock was high or "
    "low on it. Sentence 2: what the strategy believed, and if the forecast did not point the "
    "same way as the trade, say so plainly and that the optimiser held it for the book's "
    "limits or risk. Sentence 3: what it earned in dollars and how the stock moved while "
    "held, and its weight on 2026-08-31 if still held. Use only the facts in the READABLE "
    "block and the JSON below, quote numbers exactly as written there, write money like "
    "$44.92 million, never quote field names, never put numbers in quotation marks. Answer "
    "in JSON with the key why."
)
UNITS = (
    "pnl in millions of US dollars from daily positions times daily returns; weights in % "
    "of fund value; forecast_z is the stock's forecast score in standard deviations across "
    "all stocks scored that month, times rho; contribution_to_forecast_z is how much one "
    "characteristic moved that score; stock_value_z is the stock's characteristic in "
    "standard deviations from that month's average"
)
# The four lists, in the order the record shows them.
ORDER = [
    "top-10 long in the 2026-08-31 book",
    "top-10 short in the 2026-08-31 book",
    "top-10 positive contributor 2021-2026",
    "top-10 negative contributor 2021-2026",
]


# Numbers in text, thousands commas dropped so "19,169,939" is one.
def numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+\.?\d*", re.sub(r"(?<=\d),(?=\d{3})", "", text))


# A claim's numbers are supported if the facts show them, at precision.
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


# Numbers in text that the shown facts do not contain at that precision.
def unsupported(text: str, shown: str) -> list[str]:
    return [token for token in numbers(text) if not supported(token, [shown])]


# 1st, 2nd, 43rd: an ordinal for a percentile.
def nth(n: int) -> str:
    end = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{end}"


# Money as earned or lost, never a minus sign before a dollar.
def money(x: float) -> str:
    return f"{'earned' if x >= 0 else 'lost'} ${abs(x)} million"


# One driver as a phrase: high or low on it, and which way it pushed.
def phrase(d: dict) -> str:
    level = "high" if d["stock_value_z"] > 0 else "low"
    push = "raised" if d["contribution_to_forecast_z"] > 0 else "lowered"
    return (
        f"{level} {d['characteristic']} ({nth(d['stock_percentile'])} percentile), which "
        f"{push} the forecast by {abs(d['contribution_to_forecast_z'])}"
    )


# The facts as short lines a reader can quote without decoding.
def readable(f: dict) -> str:
    s = f["spell_in_view"]
    ent = f.get("entry_formation", {})
    m = ent.get("model", {})
    lines = [
        f"{f['ticker']} ({f['company']}), listed as: {'; '.join(f['listed_because'])}.",
        f"Spell in view: {s['side']} from {s['entered']} to {s['exited']}, which "
        f"{money(s['pnl_musd'])} before costs and borrow, at an average weight of "
        f"{s['avg_weight_pct']}%, while the stock returned {s['stock_return_pct']}%.",
        f"All holdings 2021-2026: {f['holding_spells']} spell(s), first {f['first_entered']}, "
        f"last {f['last_held']}, in total {money(f['pnl_musd'])}, average weight while held "
        f"{f['avg_weight_while_held_pct']}%, stock return while held "
        f"{f['stock_return_while_held_pct']}%.",
    ]
    if f["still_held_on_2026_08_31"]:
        lines.append(f"Weight on 2026-08-31: {f['weight_on_2026_08_31_pct']}%.")
    if m.get("available"):
        agree = ent.get("forecast_points_same_way_as_trade")
        lines.append(
            f"Entry decision {ent['decision_date']} ({ent['kind']}): forecast z "
            f"{m['forecast_z']}, {nth(m['forecast_percentile'])} percentile of "
            f"{m['stocks_scored']} stocks; the forecast "
            f"{'pointed the same way as' if agree else 'did NOT point the same way as'} the "
            "trade."
        )
        if ent.get("mid_month_forecast_z") is not None:
            lines.append(
                f"At that mid-month review its refreshed score was z "
                f"{ent['mid_month_forecast_z']}; the z and drivers above and below are from "
                f"the {m['formation_month_end']} month-end refit."
            )
        # The drivers on the trade's side come first, three of them.
        long = s["side"] == "LONG"
        ups = [phrase(d) for d in m.get("top_drivers_up", [])[: 3 if long else 2]]
        downs = [phrase(d) for d in m.get("top_drivers_down", [])[: 2 if long else 3]]
        up = "Drivers that raised the forecast: " + "; ".join(ups) + "."
        down = "Drivers that lowered the forecast: " + "; ".join(downs) + "."
        lines += [up, down] if long else [down, up]
    lf = f.get("latest_formation", {})
    if lf.get("available"):
        agree = lf.get("forecast_points_same_way_as_trade")
        lines.append(
            f"Latest month-end refit 2026-07-31: forecast z {lf['forecast_z']}, "
            f"{nth(lf['forecast_percentile'])} percentile; the forecast "
            f"{'points the same way as' if agree else 'does NOT point the same way as'} the "
            "position held on 2026-08-31."
        )
    return "\n".join(lines)


# What the explainer sees: one name's facts minus bookkeeping fields.
def explainer_facts(rows: list[dict]) -> dict:
    f = dict(rows[0])
    f["listed_because"] = [r["listed_because"] + f" (#{r['rank_in_list']})" for r in rows]
    for k in ("rank_in_list", "rank_basis", "permno"):
        f.pop(k, None)
    f["how_the_book_is_built"] = HOW_BUILT
    f["units"] = UNITS
    return f


# The answer key for one name's spell, shared by ask and render.
def key_of(row: dict) -> str:
    s = row["spell_in_view"]
    return f"{row['permno']}_{s['entered']}_{s['side']}"


# Calls made so far, from the log, so the cap holds across restarts.
def calls_made(log: Path = LOG) -> int:
    return len(log.read_text().splitlines()) if log.exists() else 0


# One logged completion, retried with growing waits while busy.
def chat(url: str, kind: str, key: str, messages: list, info: dict) -> dict:
    if calls_made() >= CAP:
        raise SystemExit(f"call cap {CAP} reached")
    body = dict(model="gemma", messages=messages, temperature=H.TEMPERATURE, seed=H.SEED)
    body["max_tokens"] = 2048
    body["response_format"] = dict(
        type="json_schema", json_schema=dict(name="answer", schema=SCHEMA)
    )
    start = datetime.now(UTC)
    t0 = time.time()
    error, raw, tries = None, None, 0
    for tries in range(1, 9):
        req = urllib.request.Request(
            f"{url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=1200) as r:
                raw = json.loads(r.read())
            error = None
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            error = repr(e)
            time.sleep(min(30 * tries, 180))
    message = raw["choices"][0]["message"] if raw else {}
    row = dict(kind=kind, key=key, prompt_version=PROMPT_VERSION, started_utc=start.isoformat())
    row |= dict(seconds=round(time.time() - t0, 1), attempts=tries, error=error, server=info)
    row |= dict(request=body, inputs=dict(facts_key=key), response=raw)
    row["output"] = H.parse(message) if message else {}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


# One answer per name and spell, retried once on an unsupported number.
def ask() -> None:
    facts = json.loads(FACTS.read_text())
    groups: dict = {}
    for row in facts["names"]:
        groups.setdefault(key_of(row), []).append(row)
    done = json.loads(RAW.read_text()) if RAW.exists() else {}
    with H.Server("gemma") as server:
        info = dict(url=server.url, props=server.props() or {})
        for key, rows in groups.items():
            if key in done:
                continue
            f = explainer_facts(rows)
            shown = json.dumps(f, default=str)
            check = readable(f) + " " + shown
            prompt = TASK + "\n\nREADABLE\n" + readable(f) + "\n\nJSON\n" + shown
            messages = [dict(role="system", content=SYSTEM), dict(role="user", content=prompt)]
            why = chat(server.url, "explainer", key, messages, info)["output"].get("why", "")
            bad = unsupported(why, check)
            first = dict(why=why, unsupported=bad)
            # One retry that names the numbers the facts do not hold.
            if bad or not why:
                listed = ", ".join(bad) or "none, but the answer was empty"
                fix = (
                    f"These numbers are not in the facts: {listed}. Rewrite the 2 or 3 "
                    "sentences using only numbers in the facts, exactly as written."
                )
                messages += [
                    dict(role="assistant", content=json.dumps(dict(why=why))),
                    dict(role="user", content=fix),
                ]
                rec = chat(server.url, "explainer_retry", key, messages, info)
                why = rec["output"].get("why", "")
                bad = unsupported(why, check)
            done[key] = dict(key=key, ticker=f["ticker"], company=f["company"])
            done[key] |= dict(lists=f["listed_because"], side=rows[0]["spell_in_view"]["side"])
            done[key] |= dict(why=why, numbers_supported=not bad, unsupported_numbers=bad)
            done[key] |= dict(first_attempt=first, facts=f)
            RAW.write_text(json.dumps(done, indent=1, default=str))
            print(f"{f['ticker']}: {len(bad)} unsupported; {why[:90]}", flush=True)
    print("calls logged:", calls_made())


# Drivers as short readable lines with their numbers.
def drivers(m: dict) -> str:
    if not m or not m.get("available"):
        return "not available"
    parts = []
    for d in m.get("top_drivers_up", []) + m.get("top_drivers_down", []):
        parts.append(
            f"{d['characteristic']} (stock z {d['stock_value_z']}, model rewards "
            f"{d['model_rewards']}, {d['contribution_to_forecast_z']:+.2f})"
        )
    return "<br>".join(parts)


# One name's facts as a two-column table.
def table(f: dict) -> list[str]:
    s = f["spell_in_view"]
    ent = f.get("entry_formation", {})
    m = ent.get("model", {})
    mid = f", mid-month z {ent['mid_month_forecast_z']}" if "mid_month_forecast_z" in ent else ""
    rows = [
        ("Spell in view", f"{s['side']} {s['entered']} to {s['exited']} ({s['which']})"),
        ("Spell P&L", f"${s['pnl_musd']}m"),
        (
            "All spells",
            f"{f['holding_spells']} spells, {f['trading_days_held']} trading days, "
            f"first {f['first_entered']}, last {f['last_held']}",
        ),
        (
            "Total P&L 2021-2026",
            f"${f['pnl_musd']}m (long days ${f['pnl_long_days_musd']}m, "
            f"short days ${f['pnl_short_days_musd']}m)",
        ),
        ("P&L by year", ", ".join(f"{y} ${v}m" for y, v in f["pnl_by_year_musd"].items())),
        ("Engine ledger price P&L (cross-check)", f"${f['engine_ledger_price_pnl_musd']}m"),
        (
            "Dividends, trading cost, borrow",
            f"${f['dividends_musd']}m, ${f['trading_cost_musd']}m, ${f['borrow_cost_musd']}m",
        ),
        ("Average weight while held", f"{f['avg_weight_while_held_pct']}%"),
        ("Largest absolute weight", f"{f['max_abs_weight_pct']}%"),
        ("Weight on 2026-08-31", f"{f['weight_on_2026_08_31_pct']}%"),
        ("Stock return while held", f"{f['stock_return_while_held_pct']}%"),
        (
            "Entry decision",
            f"{ent.get('decision_date')} ({ent.get('kind')}), drivers from the "
            f"{m.get('formation_month_end')} refit",
        ),
        (
            "Forecast at entry",
            f"z {m.get('forecast_z')}, percentile {m.get('forecast_percentile')}"
            f" of {m.get('stocks_scored')}, rho {m.get('regime_dial_rho')}, agrees with trade "
            f"{ent.get('forecast_points_same_way_as_trade')}{mid}",
        ),
        ("Drivers at entry", drivers(m)),
    ]
    if "latest_formation" in f:
        lf = f["latest_formation"]
        rows += [
            (
                "Forecast at 2026-07-31 refit",
                f"z {lf.get('forecast_z')}, percentile {lf.get('forecast_percentile')}, "
                f"agrees with trade {lf.get('forecast_points_same_way_as_trade')}",
            ),
            ("Drivers at 2026-07-31", drivers(lf)),
        ]
    return ["| Fact | Value |", "|---|---|", *(f"| {k} | {v} |" for k, v in rows)]


# Every list's entries, each answer beside the facts it came from.
def entries(facts: dict, raw: dict) -> list[dict]:
    out = []
    for f in facts["names"]:
        key = key_of(f)
        a = raw.get(key, {})
        out.append(
            dict(list=f["listed_because"], rank=f["rank_in_list"], rank_basis=f["rank_basis"])
            | dict(ticker=f["ticker"], company=f["company"], side=f["side"])
            | dict(explanation=a.get("why", ""))
            | dict(numbers_checked_against_facts=a.get("numbers_supported"))
            | dict(unsupported_numbers=a.get("unsupported_numbers"))
            | dict(first_attempt=a.get("first_attempt"), call_key=key, facts=f)
        )
    return out


# The record as markdown: the method, then every answer and its table.
def markdown(items: list[dict]) -> str:
    md = [
        "# Position explanations",
        "",
        "Written by the team's explainer agent (fiam/agents/explainer.py, Gemma 4 26B, "
        "temperature 0, seed 42) from the facts table under each answer. Every number in an "
        "answer was checked against its facts table by the explainer's number check "
        "(fiam/agents/explainer.py `supported`). Retrospective, names visible. No AI set or "
        "changed any weight.",
        "",
        "P&L is daily dollar positions (previous close) times daily stock returns from "
        "out/vfinal/cache/market_ret.parquet, 2021-01-04 to 2026-08-31, before costs and "
        "borrow. The engine's own ledger figure is shown beside it as a cross-check. Forecast "
        "z is the el_plus E-LASSO MaInf score, z-scored across all stocks that month and "
        "multiplied by rho. A driver's number is its contribution to that z (coefficient "
        "times the stock's demeaned characteristic, divided by the month's forecast spread).",
        "",
    ]
    for lst in ORDER:
        md += [f"## {lst[0].upper() + lst[1:]}", ""]
        for e in [x for x in items if x["list"] == lst]:
            ok = "yes"
            if not e["numbers_checked_against_facts"]:
                ok = f"NO, unsupported {e['unsupported_numbers']}"
            md += [
                f"### {e['rank']}. {e['ticker']} {e['company'].title()} ({e['side']})",
                "",
                f"> {e['explanation']}",
                "",
                f"Numbers checked against facts: {ok}",
                "",
                *table(e["facts"]),
                "",
            ]
    return "\n".join(md)


# Writes explanations.json and .md from facts.json and the answers.
def render(out_json: Path = OUT_JSON, out_md: Path = OUT_MD) -> list[dict]:
    items = entries(json.loads(FACTS.read_text()), json.loads(RAW.read_text()))
    meta = dict(
        what="Why the fund holds or held each name, written by the team's explainer agent "
        "(Gemma 4 26B on the team PC) from the facts table beside each answer and nothing else. "
        "Retrospective, names visible. No AI set or changed any weight.",
        fund="QUARCC Purple (run bw_fresh_lag)",
        log="calls.jsonl",
    )
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(dict(meta=meta, positions=items), indent=1, default=str))
    out_md.write_text(markdown(items))
    bad = [e["ticker"] for e in items if not e["numbers_checked_against_facts"]]
    print(len(items), "entries; unsupported:", bad)
    return items


# Builds facts.json from the fund's outputs, no model involved.
def facts() -> None:
    out = E.write(FACTS)
    print(len(out["names"]), "names written to", FACTS)


if __name__ == "__main__":
    # uv run python -m fiam.agents.explainer facts | ask | render
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    steps = dict(facts=facts, ask=ask, render=render)
    if step not in steps:
        sys.exit("usage: python -m fiam.agents.explainer facts | ask | render")
    steps[step]()
