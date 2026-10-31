# The rules reader on both finals PDFs, then a code check of each rule.

from __future__ import annotations

import json
import os
import re
import sys
import time
from functools import cache
from pathlib import Path

from fiam import mandate as M
from fiam.agents import final_book as F
from fiam.agents import harness as H
from fiam.agents import rules_reader as R

# Drafts, quotes and call logs, gitignored; FIAM_RULES_WORK moves them.
WORK = Path(os.environ.get("FIAM_RULES_WORK", str(H.ROOT / "cache" / "agents" / "rules")))
OUT = F.PACK / "rules" / "rules_check.json"
# The locked finals mandate, read and never written.
LOCKED = H.ROOT / "frozen" / "vfinal" / "finals_2026.json"
HACK = "McGill-FIAM Asset Management Hackathon"
ORGANISERS = H.ROOT / "data" / "organisers"
PART2 = f"{HACK} Final Challenge 2026 - Part 2_FINAL.pdf"
# Both PDFs; Part 2 came by email, so FIAM_PART2_PDF may point at it.
PDFS = {
    "finals_instructions": ORGANISERS / f"{HACK} 2026 — Final Challenge Instructions.pdf",
    "finals_part2": Path(os.environ.get("FIAM_PART2_PDF", str(ORGANISERS / PART2))),
}
# Rules outside the reader's fields, quoted by hand, checked by code.
EXTRA = [
    ("finals_part2", "sectors_min", 5, "at least five of these eleven sectors", "sectors_min"),
    ("finals_part2", "sector_net", 0.20,
     "Net exposure to any single GICS sector must not exceed 20% of capital", "sector_net"),
    ("finals_part2", "vol", 0.12,
     "Annualised realised volatility of the portfolio must not exceed 12–14%", "vol"),
    ("finals_instructions", "short_floor_musd", 500.0,
     "Only names with market capitalisation ≥ US$500m, measured at the formation date",
     "short_floor_musd"),
]  # fmt: skip
WHAT = (
    "Gemma 4 26B rules reader on the Final Challenge Instructions PDF and Part 2. "
    "A rule is kept only if its quote is in the PDF word for word. Each is then "
    "compared in code with mandates/finals_2026.json and the fund's hard limits "
    "(fiam/vfinal/config.py HARD, checked every day by fiam/vfinal/checks.py)."
)
NET_WHY = (
    "The reader filed the -50% to +50% band as a fixed net. The fund fixes no "
    "net. Its net band is 0.5 (finals_2026.json net_band and HARD net), which "
    "the same quote also set as net_band, and that matched."
)
EXTRA_NOTE = (
    "Part 2 constraints 8 and 10 and the short floor have no field in the reader's "
    "schema. They are quoted here by hand, found in the PDF by code, and compared "
    "with the fund's hard limits by code. They are not counted in rules_read."
)
LOCKED_NOTE = (
    "mandates/finals_2026.json does not carry Part 2. Its sector_cap is null and it has no "
    "sector breadth or volatility field. The fund enforces Part 2's three limits in "
    "fiam/vfinal/config.py HARD (sectors_min 5, sector_net 0.20, vol 0.12)."
)


# Spaces, dashes and quotes folded so a quote finds its page.
def fold(text: str) -> str:
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("×", "x")
    return re.sub(r"\s+", "", text).lower()


# Each PDF page's text, in order, read once per file.
@cache
def pages(path: Path) -> tuple[str, ...]:
    from pypdf import PdfReader

    return tuple(p.extract_text() or "" for p in PdfReader(path).pages)


# The first page that holds a quote, 1-based, or None.
def page_of(quote: str, texts) -> int | None:
    q = fold(quote)
    found = [i + 1 for i, t in enumerate(texts) if q in fold(t)]
    return found[0] if found else None


# The fund's limit for each field the reader can fill, and its source.
def fund_limits(locked: dict, hard: dict) -> dict:
    # Each field's sources: the locked mandate first, then HARD.
    pairs = dict(
        gross=("gross", "gross"),
        net_band=("net_band", "net"),
        name_cap=("name_cap", "name_cap"),
        names_min=("names_min", "names_min"),
        names_max=("names_max", "names_max"),
        sector=("sector_cap", "sector_net"),
    )
    out = {
        field: [(f"finals_2026.json {a}", locked.get(a)), (f"HARD {b}", hard[b])]
        for field, (a, b) in pairs.items()
    }
    out["long_only"] = [("fund holds shorts", False)]
    out["countries"] = [("panel universe", ["USA"])]
    return out


# One reader value against the fund's limits: matched if any agrees.
def compare(field: str, value, limits: dict) -> dict:
    sources = limits.get(field)
    if not sources:
        return dict(status="no_fund_limit", fund=None)
    agree, held = [], {}
    for name, limit in sources:
        held[name] = limit
        if limit is None:
            continue
        if isinstance(limit, (int, float)) and not isinstance(limit, bool):
            same = isinstance(value, (int, float)) and abs(float(value) - float(limit)) < 1e-9
        else:
            same = value == limit
        if same:
            agree.append(name)
    return dict(status="matched" if agree else "mismatch", fund=held, agreeing=agree)


# Runs the reader on one PDF, logging every prompt and raw answer.
def read(name: str, path: Path, calls) -> dict:
    chat = H.Server.chat

    # Keeps the full prompt, schema and raw reply of each call.
    def logged_chat(self, messages, tools=None, schema=None, **kw):
        start = time.time()
        reply = chat(self, messages, tools=tools, schema=schema, **kw)
        row = dict(pdf=name, messages=messages, schema=schema, reply=reply)
        row |= dict(seconds=round(time.time() - start, 2), url=self.url)
        calls.write(json.dumps(row) + "\n")
        calls.flush()
        return reply

    H.Server.chat = logged_chat
    try:
        return R.main(str(path), name)
    finally:
        H.Server.chat = chat


# Asks the model to read both PDFs; drafts and quotes land in WORK.
def ask() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    templates, M.TEMPLATES = M.TEMPLATES, WORK
    try:
        with (WORK / "calls_rules_reader.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            for name, path in PDFS.items():
                read(name, path, fh)
    finally:
        M.TEMPLATES = templates


# Compares every rule read with the fund's limits, no model involved.
def check(work: Path = WORK, pdfs: dict = PDFS) -> dict:
    # Imported here: the engine's package turns blind mode on when loaded.
    from fiam.vfinal import config

    locked = json.loads(LOCKED.read_text(encoding="utf-8"))
    limits = fund_limits(locked, config.HARD)
    rows = []
    for name, path in pdfs.items():
        quotes = json.loads((work / f"{name}_draft_quotes.json").read_text(encoding="utf-8"))
        draft = json.loads((work / f"{name}_draft.json").read_text(encoding="utf-8"))
        texts = pages(path)
        for field, quote in quotes.items():
            value = draft.get(field)
            row = dict(pdf=path.name, field=field, value=value, quote=quote)
            row["page"] = page_of(quote, texts)
            row |= compare(field, value, limits)
            if field == "net":
                row["why"] = NET_WHY
            rows.append(row)
    found = {r["field"] for r in rows}
    missed = [f for f in limits if f not in found]
    extra = []
    for name, field, value, quote, key in EXTRA:
        page = page_of(quote, pages(pdfs[name]))
        fund = config.HARD[key]
        # The volatility rule is a 12 to 14% range; the fund keeps the low end.
        ok = page is not None and abs(fund - value) < 1e-9
        extra.append(
            dict(pdf=pdfs[name].name, field=field, pdf_value=value, quote=quote, page=page)
            | dict(fund=f"HARD {key} = {fund}", status="matched" if ok else "mismatch")
        )
    matched = [r for r in rows if r["status"] == "matched"]
    mismatches = [r for r in rows if r["status"] != "matched"]
    mismatches += [r for r in extra if r["status"] != "matched"]
    out = dict(what=WHAT, rules_read=len(rows), matched=len(matched), all_match=not mismatches)
    out |= dict(fields_read=sorted(found), reader_fields_not_returned=missed, rules=rows)
    out["beyond_reader_fields"] = dict(note=EXTRA_NOTE, rules=extra)
    out |= dict(mismatches=mismatches, locked_mandate_note=LOCKED_NOTE)
    # A misfiled net is a reader error when the band it holds matched.
    bands = {r["value"] for r in rows if r["field"] == "net_band" and r["status"] == "matched"}
    misfiled = [r for r in mismatches if r["field"] == "net" and r.get("value") in bands]
    out["reader_errors"] = len({r["field"] for r in mismatches})
    out["fund_limits_all_match"] = len(misfiled) == len(mismatches) and all(
        r["status"] == "matched" for r in extra
    )
    out |= lines(out["rules_read"], out["matched"], out["all_match"], out["fund_limits_all_match"])
    return out


# The fact-sheet line and the headline for the counts found.
def lines(n: int, m: int, all_match: bool, limits_match: bool) -> dict:
    if all_match:
        fact = f"{n} rules read, all match"
        head = f"The rules reader read {n} rules from both finals PDFs and all match"
    elif limits_match:
        fact = f"{n} rules read, every fund limit matches"
        head = (
            f"The rules reader read {n} rules from both finals PDFs and every fund limit "
            "matches, after one misfiled net band"
        )
    else:
        fact = f"{n} rules read, {m} match"
        head = f"The rules reader read {n} rules from both finals PDFs and {m} match"
    assert len(fact) <= 40 and len(head) <= 120
    return dict(fund_fact_line=fact, headline=head)


# Checks the saved drafts and writes rules_check.json.
def write(path: Path = OUT) -> dict:
    before = LOCKED.read_bytes()
    out = check()
    assert LOCKED.read_bytes() == before, "the locked mandate changed"
    out["locked_mandate_unchanged"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rules"}, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    # uv run python -m fiam.agents.rules_check ask | check
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step not in ("ask", "check"):
        sys.exit("usage: python -m fiam.agents.rules_check ask | check")
    if step == "ask":
        ask()
    write()
