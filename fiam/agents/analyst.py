# Analyst agent: reads each top name's latest report against our side.

import json
import re

import pandas as pd

from fiam import paths
from fiam.agents import final_book as F
from fiam.vfinal import text as T

# The final book's ten largest longs and shorts, read in their filings.
FINAL = F.PACK / "analyst"
TOP = 10
MDNA_CHARS, RISK_CHARS = 30_000, 8_000
# Quarterly report headings: MD&A in Part I, risk factors in Part II.
QUARTERLY = {
    "mdna": (
        (r"item\s*2\b", r"management(?:.{0,2}s)?\s+discussion"),
        [
            (r"item\s*3\b", r"quantitative|qualitative"),
            (r"item\s*4\b", r"controls\s+and\s+procedures"),
        ],
    ),
    "risk": (
        (r"item\s*1\.?\s*a\b", r"risk\s+factors"),
        [
            (r"item\s*2\b", r"unregistered"),
            (r"item\s*3\b", r"defaults"),
            (r"item\s*4\b", r"mine\s+safety"),
            (r"item\s*5\b", r"other\s+information"),
            (r"item\s*6\b", r"exhibits"),
        ],
    ),
}
MDNA_TITLE = re.compile(r"(?im)^[^\n]{0,40}management(?:.{0,2}s)?\s+discussion\s+and\s+analysis")
FINAL_SCHEMA = dict(
    type="object",
    properties=dict(
        supports=dict(type="array", items=dict(type="string"), maxItems=3),
        challenges=dict(type="array", items=dict(type="string"), maxItems=3),
        balance=dict(type="string", enum=["supports", "challenges", "mixed"]),
        summary=dict(type="string"),
    ),
    required=["supports", "challenges", "balance", "summary"],
)
FINAL_SYSTEM = (
    "You are an equity analyst checking one position of a long-short fund against the "
    "company's latest quarterly or annual report. You are told the side the fund holds (long "
    "gains if the stock rises, short gains if it falls) and given excerpts of the report's "
    "Management's Discussion and Analysis and Risk Factors.\n\n"
    "Write a short thesis check from the excerpts only.\n"
    "- supports: up to three points from the filing that support the fund's side, one "
    "sentence each.\n"
    "- challenges: up to three points from the filing that challenge the fund's side, one "
    "sentence each.\n"
    "- balance: supports, challenges or mixed, for the fund's side on the filing as a whole.\n"
    "- summary: one sentence.\n\n"
    "Quote every number exactly as the excerpt prints it. Never compute, round or estimate a "
    "number of your own. Do not use what you may know from outside the excerpts. You do not "
    "decide position sizes."
)


# The longest span from a quarterly heading to the next item's heading.
def quarterly_section(text: str, which: str, minimum: int = 300) -> str | None:
    (item, title), stops = QUARTERLY[which]
    best = None
    for m in T.headings(text, item, title):
        ends = [h.start() for s, st in stops for h in T.headings(text, s, st, m.end(), True)[:1]]
        if not ends:
            continue
        span = text[m.start() : min(ends)]
        if best is None or len(span) > len(best):
            best = span
    return best if best is not None and len(best) >= minimum else None


# A report's MD&A and risk factors, each with how it is found.
def sections(text: str, form: str) -> dict:
    annual = form.startswith("10-K")
    mdna = T.section(text, "7") if annual else quarterly_section(text, "mdna")
    risk = T.section(text, "1a") if annual else quarterly_section(text, "risk", 100)
    how = dict(mdna="item heading" if mdna else None, risk="item heading" if risk else None)
    # A report laid out without item headings: from its MD&A title on.
    if mdna is None:
        found = [m for m in MDNA_TITLE.finditer(text) if m.start() > len(text) // 20]
        if found:
            mdna, how["mdna"] = text[found[0].start() :], "title, no item heading"
    return dict(
        mdna=T.strip_boilerplate(mdna)[:MDNA_CHARS] if mdna else "",
        risk=T.strip_boilerplate(risk)[:RISK_CHARS] if risk else "",
        found=how,
    )


# Each name's latest 10-Q or 10-K accepted by the book's date.
def latest_report(cik: int) -> dict | None:
    reports = F.periodic(cik)
    reports = reports[F.public_by(reports["acceptanceDateTime"], reports["filingDate"]).values]
    if reports.empty:
        return None
    last = reports.sort_values(["acceptanceDateTime", "accessionNumber"]).iloc[-1]
    return dict(
        form=last["form"],
        filing_date=last["filingDate"],
        accepted=last["acceptanceDateTime"],
        period=last["reportDate"],
        accession=last["accessionNumber"],
        document=last["primaryDocument"],
        url=f"{F.folder(cik, last['accessionNumber'])}/{last['primaryDocument']}",
    )


# One name's prompt: the side held, then the two excerpts.
def final_prompt(name: dict, report: dict, parts: dict) -> str:
    side = "LONG" if name["side"] == "long" else "SHORT"
    return (
        f"Company: {name['company_name']} ({name['ticker']})\nThe fund holds it: {side}\n"
        f"Report: Form {report['form']} for the period ended {report['period']}, filed "
        f"{report['filing_date']}\n\nManagement's Discussion and Analysis (excerpt):\n"
        f"{parts['mdna'] or '[not found in this report]'}\n\nRisk Factors (excerpt):\n"
        f"{parts['risk'] or '[not found in this report]'}"
    )


# An answer's shape checked, then every quoted number checked.
def checked(answer: dict, source: str) -> tuple[dict | None, str | None]:
    if set(answer) != set(FINAL_SCHEMA["required"]):
        return None, f"fields {sorted(answer)}"
    if answer["balance"] not in FINAL_SCHEMA["properties"]["balance"]["enum"]:
        return None, f"balance {answer['balance']!r}"
    lists = [answer["supports"], answer["challenges"]]
    if not all(isinstance(x, list) and all(isinstance(s, str) for s in x) for x in lists):
        return None, "points are not lists of text"
    if not isinstance(answer["summary"], str) or not answer["summary"].strip():
        return None, "summary empty"
    supports, dropped_s = F.number_check(answer["supports"], source)
    challenges, dropped_c = F.number_check(answer["challenges"], source)
    summary, dropped_m = F.number_check([answer["summary"]], source)
    return dict(
        supports=supports,
        challenges=challenges,
        balance=answer["balance"],
        summary=summary[0] if summary else None,
        dropped=[
            *(d | dict(part="supports") for d in dropped_s),
            *(d | dict(part="challenges") for d in dropped_c),
            *(d | dict(part="summary") for d in dropped_m),
        ],
    ), None


# The thesis checks as a page, each beside the filing it read.
def final_markdown(out: dict) -> str:
    lines = [
        "# Analyst thesis checks on the final book",
        "",
        f"Book date {out['book_date']}. The ten largest longs and ten largest shorts by weight. "
        "For each name a local model read the MD&A and Risk Factors of its latest 10-Q or 10-K "
        "accepted by the book's date and listed what supports or challenges the side we hold. "
        "Code kept a point only if every number in it is printed in the excerpt the model read, "
        "a percentage as a percentage. This shows each number is in the filing, not that it "
        "belongs to the fact the sentence gives it. "
        "No AI set or changed any weight.",
        "",
        f"Model {out['accounting']['model']} ({out['accounting']['model_file']}), temperature "
        f"{out['accounting']['temperature']}, seed {out['accounting']['seed']}.",
        "",
        "| Balance | Longs | Shorts |",
        "|---|---|---|",
    ]
    for kind in ("supports", "mixed", "challenges", "no answer"):
        lines.append(
            f"| {kind} | {out['balance_by_side']['long'].get(kind, 0)} "
            f"| {out['balance_by_side']['short'].get(kind, 0)} |"
        )
    for n in out["names"]:
        lines += ["", f"## {n['ticker']} {n['company']}", ""]
        lines.append(f"{n['side'].capitalize()}, weight {n['weight'] * 100:.2f}% of capital.")
        r = n.get("report")
        if not r:
            lines.append("No 10-Q or 10-K accepted by the book's date was found.")
            continue
        lines.append(
            f"Read Form {r['form']} for the period ended {r['period']}, filed {r['filing_date']} "
            f"([{r['accession']}]({r['url']})). Sections found by MD&A {n['found']['mdna']}, "
            f"risk factors {n['found']['risk']}."
        )
        if n.get("check"):
            lines.append(f"No usable answer ({n['check']}).")
            continue
        lines += ["", f"**Balance for our side** {n['balance']}", ""]
        if n["summary"]:
            lines += [n["summary"], ""]
        lines += ["Supports"] + [f"- {s}" for s in n["supports"]] + [""]
        lines += ["Challenges"] + [f"- {s}" for s in n["challenges"]]
        if n["dropped"]:
            lines += ["", f"Dropped by the number check ({len(n['dropped'])})"]
            lines += [
                f"- {d['text']} (not in the excerpt {d['unsupported_numbers']})"
                for d in n["dropped"]
            ]
    return "\n".join(lines) + "\n"


# Reads each top name's latest report and writes the thesis checks.
def final() -> None:
    held = F.book()
    FINAL.mkdir(parents=True, exist_ok=True)
    longs = held[held["side"] == "long"].nlargest(TOP, "w")
    shorts = held[held["side"] == "short"].nsmallest(TOP, "w")
    chosen = pd.concat([longs, shorts], ignore_index=True).to_dict("records")
    names, prompts = [], []
    for name in chosen:
        report = latest_report(int(name["cik"]))
        entry = dict(
            ticker=name["ticker"],
            company=name["company_name"],
            side=name["side"],
            weight=round(float(name["w"]), 6),
            report=report,
        )
        if report:
            text = F.main_text(
                name["cik"], report["accession"], report["document"], FINAL / "sec_cache"
            )
            parts = sections(text, report["form"])
            entry |= dict(
                found=parts["found"],
                excerpt_chars=dict(mdna=len(parts["mdna"]), risk=len(parts["risk"])),
            )
            prompts.append(
                (f"{name['ticker']}_{report['accession']}", final_prompt(name, report, parts))
            )
            entry["source"] = parts["mdna"] + "\n" + parts["risk"]
        names.append(entry)
    print(f"  analyst: {len(prompts)} of {len(names)} names have a report to read", flush=True)
    with F.Asker(FINAL / "calls.jsonl", FINAL_SYSTEM, FINAL_SCHEMA) as asker:
        answers = asker.ask_all(prompts)
    by_key = {k: a for (k, _), a in zip(prompts, answers)}
    for entry in names:
        source = entry.pop("source", None)
        if source is None:
            entry["check"] = "no report"
            continue
        answer = by_key[f"{entry['ticker']}_{entry['report']['accession']}"]
        result, problem = (
            (None, answer["error"]) if answer["error"] else checked(answer["parsed"], source)
        )
        entry["check"] = problem
        entry |= result or {}
    ok = [n for n in names if not n.get("check")]
    balance = {
        side: {
            k: sum(n.get("balance") == k for n in names if n["side"] == side)
            for k in ("supports", "mixed", "challenges")
        }
        | {"no answer": sum(bool(n.get("check")) for n in names if n["side"] == side)}
        for side in ("long", "short")
    }
    out = dict(
        what="A local model read the MD&A and Risk Factors of the latest 10-Q or 10-K, accepted "
        "by the book's date, for the final book's ten largest longs and ten largest shorts, and "
        "listed what supports or challenges the side held. It reads text and sets no weight.",
        book_date=F.AS_OF,
        excerpt_limits=dict(mdna_chars=MDNA_CHARS, risk_chars=RISK_CHARS),
        number_check="a point is kept only if every number in it is printed in the excerpt "
        "the model read, a percentage as a percentage; a point with any other number is "
        "dropped and listed. It shows a number is in the filing, not that it belongs to the "
        "fact the sentence gives it",
        names_read=len(prompts),
        answers_passed_checks=len(ok),
        points_kept=sum(len(n["supports"]) + len(n["challenges"]) for n in ok),
        points_dropped=sum(len(n["dropped"]) for n in ok),
        balance_by_side=balance,
        accounting=asker.accounting(answers, sum(a["error"] is None for a in answers) - len(ok)),
        names=names,
    )
    paths.write_json(FINAL / "analyst_final.json", out, rounded=False)
    (FINAL / "analyst_final.md").write_text(final_markdown(out), encoding="utf-8", newline="\n")
    print(json.dumps(dict(balance_by_side=balance, points_dropped=out["points_dropped"]), indent=1))


if __name__ == "__main__":
    # uv run python -m fiam.agents.analyst
    final()
