# One line per AI agent: what it found, its number, date and file.

from __future__ import annotations

from pathlib import Path

from fiam.agents import desk as D

OUT = D.PACK / "agents_found.json"
FINDING_CHARS, FACT_LINE_CHARS = 110, 76
AGENTS = (
    "Rules reader",
    "Triage",
    "Analyst",
    "Explainer",
    "Memo writer",
    "Devil's advocate",
    "Risk desk",
    "AI crowd",
)


# The rules reader's match count.
def rules(r: dict) -> tuple[str, str]:
    read, matched = r["rules_read"], r["matched"]
    return (
        f"Read {read} rules in the finals PDFs and {matched} match the fund's limits, "
        f"{read - matched} misfile the net band",
        f"{matched} of {read}",
    )


# The triage agent's share of news that favoured our side.
def triage(t: dict) -> tuple[str, str]:
    share = round(t["share_for_our_side"] * 100)
    return (
        f"Labelled {t['filings']['labelled']} 8-Ks from the book's names and {share}% of "
        "the non-neutral news favoured our side",
        f"{t['filings']['labelled']} 8-Ks",
    )


# The analyst's supports and challenges across both sides.
def analyst(a: dict) -> tuple[str, str]:
    bal = a["balance_by_side"]
    sup = sum(b["supports"] for b in bal.values())
    cha = sum(b["challenges"] for b in bal.values())
    mixed = sum(b["mixed"] for b in bal.values())
    return (
        f"Read the latest report of {a['names_read']} top names, {sup} support our side, "
        f"{mixed} are mixed and {cha} challenge it",
        f"{sup} of {a['names_read']}",
    )


# The explainer's positions and how many answers traced every number.
def explainer(e: dict) -> tuple[str, str]:
    p = e["positions"]
    answers = len({x["call_key"] for x in p})
    clean = len({x["call_key"] for x in p if not x["unsupported_numbers"]})
    return (
        f"Explained {len(p)} top positions in {answers} answers and {clean} of {answers} "
        "traced every number",
        f"{len(p)} positions",
    )


# The memo writer's headline: the letter's value against the hurdle.
def memo(m: dict) -> tuple[str, str]:
    f = m["facts"]
    ir = f["information_ratio_after_costs"]
    return (
        f"The August letter reports ${f['ending_value_billion']:.3f}bn against the "
        f"${f['hurdle_ending_value_billion']:.3f}bn hurdle and an IR of {ir:.2f}",
        f"IR {ir:.2f}",
    )


# The devil's advocate's attacks and how many still stand.
def devil(c: dict) -> tuple[str, str]:
    n, v = len(c["attacks"]), c["verdicts"]
    stand = v.get("stands", 0) + v.get("partly stands", 0)
    return (
        f"Made {n} attacks on the final book and the data shows {stand} stand in whole or in part",
        f"{stand} of {n}",
    )


# The risk desk's flags by level and whether a finals limit broke.
def risk(r: dict) -> tuple[str, str]:
    lv = r["levels"]
    flagged = len(r["flags"])
    return (
        f"Raised {flagged} flags on the final book, {lv['alert']} alert and {lv['watch']} "
        "watch, with no finals limit broken"
        if lv["alert"] == 0
        else f"Raised {flagged} flags on the final book, {lv['alert']} alert and "
        f"{lv['watch']} watch",
        f"{lv['watch']} watch",
    )


# The AI crowd's view of the book on its date.
def crowd(c: dict) -> tuple[str, str]:
    r = c["round"]
    return (
        f"On the final book our longs sit at the AI crowd's {D.nth(r['long_pct'])} percentile "
        f"and shorts at the {D.nth(r['short_pct'])}, crowd beta {r['beta']}",
        f"crowd beta {r['beta']}",
    )


SOURCES = {
    "Rules reader": (D.RULES, rules),
    "Triage": (D.TRIAGE, triage),
    "Analyst": (D.ANALYST, analyst),
    "Explainer": (D.EXPLAINER, explainer),
    "Memo writer": (D.DESK / "letter.json", memo),
    "Devil's advocate": (D.DESK / "critic_final.json", devil),
    "Risk desk": (D.DESK / "risk_note.json", risk),
    "AI crowd": (D.CROWD_LIVE, crowd),
}


# One agent's entry, or pending while its file is missing or partial.
def entry(path: Path, read) -> dict | str:
    data = D.load(path)
    if data is None:
        return "pending"
    try:
        finding, key = read(data)
    except KeyError, TypeError:
        return "pending"
    if not D.screen_ok(finding, FINDING_CHARS):
        raise ValueError(f"finding breaks the on-screen rules: {finding}")
    return dict(finding=finding, key_number=key, date=D.stamp(path), source=D.rel(path))


# The desk's fact line, checked against the on-screen rules.
def fact_line() -> str:
    line = f"{len(AGENTS)} AI agents read and check the fund and none sets a trade"
    if not D.screen_ok(line, FACT_LINE_CHARS):
        raise ValueError(f"fact line breaks the on-screen rules: {line}")
    return line


# The map of all eight agents and the desk's fact line.
def build() -> dict:
    agents = {name: entry(*SOURCES[name]) for name in AGENTS}
    line = fact_line()
    return dict(
        what="What each of the fund's AI agents found, one line each, built by code from the "
        "agent's own output file. pending means that file was not ready.",
        agents_count=len(AGENTS),
        agents=agents,
        pending=[k for k, v in agents.items() if v == "pending"],
        fund_fact_line=line,
    )


# Writes agents_found.json and says which agents are still pending.
def run() -> dict:
    out = build()
    D.write_json(OUT, out)
    print(
        f"agents found: {len(AGENTS) - len(out['pending'])} ready, pending {out['pending']}",
        flush=True,
    )
    return out
