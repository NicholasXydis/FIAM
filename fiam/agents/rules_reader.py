# Rules reader: rules PDF in, draft mandate out, every quote checked.

import json
import os
import sys
import time
from dataclasses import fields
from pathlib import Path

from fiam import mandate as M
from fiam.agents import harness as H

SYSTEM = (
    "You read a portfolio competition's rules and fill in a mandate. For every field you fill, "
    "give the exact sentence from the rules that sets it, copied word for word. Use null for "
    "a field the rules do not set. Never guess. Fields, every percentage written as a fraction: "
    "gross = long plus short as a share of capital (130/30 leverage is 1.6); net = long minus "
    "short when the rules fix it (130/30 is 1.0); net_band = the widest net exposure allowed "
    "either way when the rules give a range instead (-50% to +50% is 0.5); name_cap = the most "
    "in any one stock (5% is 0.05); sector = the most net weight in one sector; beta = the "
    "largest allowed absolute market beta; names_min and names_max = how many stocks; "
    "country_cap = the most in any one country; turnover = the most one-way turnover allowed "
    "in a month (30% is 0.3); long_only = true only if short selling is not allowed; countries "
    "= the countries allowed, if listed."
)
NUMBERS = (
    "gross",
    "net",
    "net_band",
    "name_cap",
    "sector",
    "beta",
    "names_min",
    "names_max",
    "country_cap",
    "turnover",
)
FLAGS = ("long_only",)
LISTS = ("countries",)


# The answer's shape: each field a value and the quote behind it.
def schema() -> dict:
    value = {n: dict(type=["number", "null"]) for n in NUMBERS} | {
        f: dict(type=["boolean", "null"]) for f in FLAGS
    }
    quote = {f"{n}_quote": dict(type=["string", "null"]) for n in (*NUMBERS, *FLAGS, *LISTS)}
    props = value | quote | dict(countries=dict(type=["array", "null"], items=dict(type="string")))
    return dict(type="object", properties=props, required=list(props))


# Long rules in pieces the model reads whole, cut at paragraph breaks.
def chunks(text: str, size: int = 12_000) -> list[str]:
    out, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) > size and current:
            out.append(current)
            current = ""
        current += para + "\n\n"
    return [*out, current] if current else out


# A rule stays only if its quote is in the rules verbatim, spaces aside.
def verified(answer: dict, text: str) -> dict:
    flat = " ".join(text.split())
    out = {}
    for name in (*NUMBERS, *FLAGS, *LISTS):
        value, quote = answer.get(name), answer.get(f"{name}_quote")
        if value is None or value == [] or not quote:
            continue
        if " ".join(quote.split()) in flat:
            out[name] = dict(value=value, quote=quote)
    return out


# The rules' mandate, our neutral-book limits off if net long or short.
def drafted(found: dict, name: str) -> dict:
    known = {f.name for f in fields(M.Mandate)}
    draft = {"name": name} | {k: v["value"] for k, v in found.items() if k in known}
    if abs(draft.get("net") or 0.0) > 0.1:
        draft = {"name": name, "sector": None, "beta": None, "risk": None} | draft
    # The panel's spelling of the United States, however the rules write it.
    usa = {"us", "u.s.", "usa", "u.s.a.", "united states", "united states of america"}
    if draft.get("countries"):
        draft["countries"] = [("USA" if c.lower() in usa else c) for c in draft["countries"]]
    return draft


# The rules as text: a PDF's pages in order, or the file itself.
def text_of(source: str) -> str:
    path = Path(source)
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8")
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    (M.TEMPLATES / f"{path.stem}_rules.txt").write_text(text, encoding="utf-8")
    return text


# Reads each chunk and drafts its verified rules for a human to approve.
def main(source: str, name: str) -> dict:
    text = text_of(source)
    found = {}
    with H.Server("gemma", H.LONG_PROMPTS) as server:
        for piece in chunks(text):
            messages = [dict(role="system", content=SYSTEM), dict(role="user", content=piece)]
            answer = H.parse(server.chat(messages, schema=schema()))
            for key, rule in verified(answer, text).items():
                found.setdefault(key, rule)
    draft = drafted(found, name)
    target = M.TEMPLATES / f"{name}_draft.json"
    target.write_text(json.dumps(draft, indent=1) + "\n", encoding="utf-8")
    quotes = {k: v["quote"] for k, v in found.items()}
    (M.TEMPLATES / f"{name}_draft_quotes.json").write_text(
        json.dumps(quotes, indent=1) + "\n", encoding="utf-8"
    )
    problems = M.check(M.load(target))
    report = dict(draft=draft, problems=problems, approve="a human must approve before use")
    # Accepted when each numeric limit of the hand-made reference matches.
    reference = M.TEMPLATES / f"{name}.json"
    if reference.exists():
        truth = json.loads(reference.read_text(encoding="utf-8"))
        limits = [k for k in NUMBERS if truth.get(k) is not None]
        same = [k for k in limits if draft.get(k) is not None and abs(draft[k] - truth[k]) < 1e-9]
        report["reference"] = dict(limits=len(limits), found_and_equal=len(same))
        report["reference"]["missed_or_different"] = sorted(set(limits) - set(same))
    print(json.dumps(report, indent=1))
    return report


# Finals drill (finals.md): rules, draft mandate, v1 and v2, all timed.
def drill(source: str) -> None:
    from fiam import v2

    start, name = time.time(), Path(source).stem
    report = main(source, name)
    books = v2.finals(M.TEMPLATES / f"{name}_draft.json")
    minutes = (time.time() - start) / 60
    path = v2.OUT / "drill.json"
    record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    record = {k: v for k, v in record.items() if isinstance(v, dict)}
    record[name] = dict(
        source=Path(source).name,
        mandate=f"{name}_draft.json",
        minutes=minutes,
        reference=report.get("reference"),
        books={
            k: dict(run=v["run"], breaches=v["months_breaching"], empty=v["months_empty"])
            for k, v in books.items()
        },
        finished=time.strftime("%Y-%m-%d %H:%M"),
    )
    path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"drill: {minutes:.1f} minutes from the rules text to both books")


if __name__ == "__main__":
    if sys.argv[1:2] == ["drill"]:
        drill(sys.argv[2] if len(sys.argv) > 2 else os.environ["FIAM_RULES"])
    else:
        main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).stem)
