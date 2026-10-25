# Step 4 hand checks: seeded 2015-2020 draws and their worksheets.

import gzip
import json
import re
import sys
from pathlib import Path

import pandas as pd

from fiam.v4 import text

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "v4" / "text" / "hand_checks"
# The draws protocol.md fixes: seed, the fresh seed and sizes.
SEED, FRESH = 20261023, 20261024
FROM, TO = pd.Timestamp("2015-01-01"), pd.Timestamp("2020-12-31")
SEAL = pd.Timestamp("2020-12-31")
SIZES = {"sections": 100, "footprint": 50, "five02": 200, "customers": 100, "properties": 50}
KIND = {"sections": "annual", "footprint": "annual", "five02": "502", "customers": "annual"}
KIND["properties"] = "annual"
# Draws made before every earlier draw was excluded (final audit 14).
FIRST_RULE = {"properties_20261026", "properties_20261027"}
# The property-state check's seed and its fresh seed (protocol.md).
PROPERTY_SEEDS = (20261026, 20261027)
# The leader's human check (protocol.md decision 9): seed and groups.
LEADER_SEED = 20261028
LEADER_GROUPS = (("Item 1A", 10), ("Item 7", 10), ("Headquarters", 5), ("Property states", 5))


# Held filings of one kind with their filing date, in accession order.
def population(kind: str) -> pd.DataFrame:
    rows = pd.DataFrame(text.held(kind), columns=["cik", "accession"])
    f = pd.read_parquet(text.EDGAR / "filings.parquet", columns=["accession", "filing_date"])
    f["filing_date"] = pd.to_datetime(f["filing_date"])
    rows = rows.merge(f.drop_duplicates("accession"), on="accession", how="left")
    return rows.sort_values("accession", ignore_index=True)


# One check's sample: filings drawn from 2015-2020 by the fixed seed.
def draw(check: str, seed: int = SEED) -> pd.DataFrame:
    rows = population(KIND[check])
    rows = rows[rows["filing_date"].between(FROM, TO)]
    # A check added later never reuses a filing any earlier draw picked.
    if check == "properties":
        key = f"{check}_{seed}"
        # The two property draws made first excluded other kinds only.
        early = reserved(but=check) if key in FIRST_RULE else drawn_before(key)
        rows = rows[~rows["accession"].isin(early)]
    return rows.sample(SIZES[check], random_state=seed).reset_index(drop=True)


# The draws saved before their worksheets, as protocol.md requires.
def saved_draws() -> dict[str, list[str]]:
    path = OUT / "draws.json"
    return json.loads(path.read_text()) if path.exists() else {}


# Filings every draw saved before this one picked, in their saved order.
def drawn_before(key: str) -> set[str]:
    saved = saved_draws()
    names = list(saved)
    earlier = names[: names.index(key)] if key in names else names
    return {item.split("#")[0] for name in earlier for item in saved[name]}


# Every filing a formal draw picked, from the saved draws when present.
def reserved(but: str = "") -> set[str]:
    saved = {k: v for k, v in saved_draws().items() if not (but and k.startswith(but))}
    if saved:
        return {item.split("#")[0] for ids in saved.values() for item in ids}
    out: set[str] = set()
    for check in ("sections", "footprint", "five02"):
        for seed in (SEED, FRESH):
            out |= set(draw(check, seed)["accession"])
    return out


# Dev filings: pre-2021, never drawn; customers 2012-2014 (protocol.md).
def dev_rows(kind: str, n: int, seed: int = 1, customers: bool = False) -> list[tuple[int, str]]:
    rows = population(kind)
    rows = rows[rows["filing_date"] <= SEAL]
    if customers:
        rows = rows[rows["filing_date"] < FROM]
    rows = rows[~rows["accession"].isin(reserved())]
    pick = rows.sample(min(n, len(rows)), random_state=seed)
    # Every development draw is logged, so none can hide (audit 12).
    OUT.mkdir(parents=True, exist_ok=True)
    entry = {"kind": kind, "n": n, "seed": seed, "customers": customers, "rows": len(pick)}
    entry["ids"] = pick["accession"].tolist()
    with (OUT / "dev_log.jsonl").open("a") as fh:
        fh.write(json.dumps(entry | {"when": pd.Timestamp.now(tz="UTC").isoformat()}) + "\n")
    return list(zip(pick["cik"].astype(int), pick["accession"]))


# Every filing seen before the leader's draw: draws, pilot, development.
def seen_before() -> set[str]:
    seen = reserved()
    for name in ("pilot_ids.json", "dev_ids.json"):
        ids = json.loads((OUT / name).read_text())["ids"]
        seen |= {i[0] if isinstance(i, list) else i for i in ids}
    for line in (OUT / "dev_log.jsonl").read_text().splitlines():
        seen |= set(json.loads(line).get("ids", []))
    return seen


# The leader's 30 reports from 2015-2020, none seen before, by seed.
def leader_draw(seed: int = LEADER_SEED) -> pd.DataFrame:
    rows = population("annual")
    rows = rows[rows["filing_date"].between(FROM, TO) & ~rows["accession"].isin(seen_before())]
    pick = rows.sample(sum(n for _, n in LEADER_GROUPS), random_state=seed)
    groups = [name for name, n in LEADER_GROUPS for _ in range(n)]
    return pick.reset_index(drop=True).assign(check=groups)


# The leader's sheet: each drawn row's link and what the code found.
def leader_rows(pick: pd.DataFrame) -> tuple[list[dict], dict]:
    rows, rule = [], {}
    for n, r in enumerate(pick.itertuples(), 1):
        path = text.EDGAR / "docs" / str(r.cik) / f"{r.accession}.gz"
        raw = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        doc = text.html_text(raw)
        plain = r.accession.replace("-", "")
        link = f"https://www.sec.gov/Archives/edgar/data/{r.cik}/{plain}/{r.accession}-index.htm"
        row = {"n": n, "check": r.check, "filing": r.accession, "filed": str(r.filing_date.date())}
        if r.check in ("Item 1A", "Item 7"):
            span = text.section(doc, "1a" if r.check == "Item 1A" else "7")
            found = None if span is None else {"starts": span[:160], "ends": span[-160:]}
        elif r.check == "Headquarters":
            found = text.headquarters(doc, raw[:400000])[0]
        else:
            found = text.property_states(doc)
        rows.append(row | {"link": link, "code_found": found})
        rule[r.accession] = found
    return rows, rule


# The sheet as Markdown, one numbered row per filing to mark.
def leader_markdown(rows: list[dict]) -> str:
    out = ["# Human check (seed 20261028)", ""]
    out += ["Open each link, find the part named, and mark the row right or wrong.", ""]
    for r in rows:
        out += [f"## {r['n']}. {r['check']}, filed {r['filed']}", f"[{r['filing']}]({r['link']})"]
        got = r["code_found"]
        if isinstance(got, dict):
            out += ["", f"Starts: {got['starts']!r}", "", f"Ends: {got['ends']!r}"]
        else:
            out += ["", f"Code found: {got if got else 'nothing'}"]
        out += [""]
    return "\n".join(out)


# A saved main document as plain text.
def document(cik: int, accession: str) -> str:
    path = text.EDGAR / "docs" / str(cik) / f"{accession}.gz"
    return text.html_text(gzip.decompress(path.read_bytes()).decode("utf-8", "replace"))


# Text around a position, for the checker to read.
def around(doc: str, at: int, before: int, after: int) -> str:
    return doc[max(0, at - before) : at + after]


# A section's extracted start and end in context, or every heading try.
def section_sheet(doc: str, which: str) -> dict:
    span = text.section(doc, which)
    item = text.HEADINGS[which][0][0]
    tries = [around(doc, m.start(), 60, 160) for m in re.finditer(item, doc, re.I)][:10]
    if span is None:
        return {"extracted": None, "item_mentions": tries}
    start = doc.find(span)
    end = start + len(span)
    return {
        "extracted": {"chars": len(span), "start": around(doc, start, 200, 300)},
        "end_before": doc[max(start, end - 300) : end],
        "end_after": doc[end : end + 300],
        "item_mentions": tries,
    }


# Sections worksheet: both sections of each drawn annual report.
def sections_rows(seed: int = SEED) -> list[dict]:
    rows = []
    for r in draw("sections", seed).itertuples():
        doc = document(r.cik, r.accession)
        sheet = {"1a": section_sheet(doc, "1a"), "7": section_sheet(doc, "7")}
        rows.append({"id": r.accession, "filing_date": str(r.filing_date.date())} | sheet)
    return rows


# Footprint worksheet, blind: the cover around the address label only.
def footprint_rows(seed: int = SEED) -> list[dict]:
    rows, answers = [], {}
    for r in draw("footprint", seed).itertuples():
        path = text.EDGAR / "docs" / str(r.cik) / f"{r.accession}.gz"
        raw = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        doc = text.html_text(raw)
        mark = text.LABEL.search(doc[:200000])
        name = re.search(r"exact\s+name\s+of\s+(?:the\s+)?registrant", doc[:200000], re.I)
        at = mark.start() if mark else (name.end() if name else 0)
        rows.append({"id": r.accession, "cover": around(doc, at, 900, 500)})
        answers[r.accession] = text.headquarters(doc, raw[:400000])[0]
    return rows, answers


# 5.02 worksheet, blind: the 8-K's text after its cover page.
def five02_rows(seed: int = SEED) -> list[dict]:
    rows, answers = [], {}
    for r in draw("five02", seed).itertuples():
        doc = document(r.cik, r.accession)
        first = re.search(r"item\s*5\.02", doc, re.I)
        at = first.start() if first else 0
        body = doc[at : at + 40000]
        rows.append({"id": r.accession, "text": body, "truncated": len(doc) - at > 40000})
        answers[r.accession] = text.departure_502(doc)
    return rows, answers


# Named 2015-2020 mentions drawn by seed, none from an earlier draw.
def customer_draw(seed: int = SEED) -> pd.DataFrame:
    pop = population("annual")
    pop = pop[pop["filing_date"].between(FROM, TO)]
    parts = pd.read_parquet(text.OUT / "annual", columns=["accession", "customers"])
    a = parts.merge(pop, on="accession").sort_values("accession")
    if seed != SEED:
        first = json.loads((OUT / f"customers_{SEED}_sheet.json").read_text())
        a = a[~a["accession"].isin({row["id"].split("#")[0] for row in first})]
    m = pd.DataFrame(
        [
            (r.accession, r.cik, r.filing_date, i, name, share, floor)
            for r in a.itertuples()
            for i, (name, share, kind, floor) in enumerate(json.loads(r.customers))
            if kind == "named"
        ],
        columns=["accession", "cik", "filing_date", "order", "customer", "share", "floor"],
    )
    return m.sample(SIZES["customers"], random_state=seed).reset_index(drop=True)


# Customers worksheet: each mention in context, with its matched stock.
def customers_rows(seed: int = SEED) -> list[dict]:
    pick = customer_draw(seed)
    e = pd.read_parquet(ROOT / "data" / "v4" / "clean" / "edgar_filings.parquet")
    filer = e[["accession", "permno"]].drop_duplicates("accession")
    pick = pick.merge(filer, on="accession", how="left")
    lk = pd.read_parquet(ROOT / "data" / "v4" / "links.parquet")
    names = lk[lk["kind"] == "name"]
    got = text.match_customers(pick.fillna({"permno": -1}), names)
    rows = []
    for r in got.itertuples():
        doc = text.flat(document(r.cik, r.accession))
        # The mention is the name, then its share with a percent sign.
        share = re.escape(f"{r.share:g}") + r"\s*%"
        hit = re.search(re.escape(r.customer) + r".{0,250}?" + share, doc)
        at = hit.start() if hit else doc.find(r.customer)
        crsp = names[names["permno"] == r.customer_permno]["value"].tolist()
        rows.append(
            {
                "id": f"{r.accession}#{r.order}",
                "customer": r.customer,
                "share": r.share,
                "share_is_floor": bool(r.floor),
                "context": around(doc, at, 400, 400) if at >= 0 else None,
                "matched_permno": None if pd.isna(r.customer_permno) else int(r.customer_permno),
                "matched_crsp_names": crsp,
                "match": r.match,
            }
        )
    return rows


# Property states, blind: Item 2 as cut, the rule's states kept apart.
def properties_rows(seed: int) -> tuple[list[dict], dict]:
    rows, answers = [], {}
    for r in draw("properties", seed).itertuples():
        doc = document(r.cik, r.accession)
        body = text.section(doc, "2", minimum=1)
        cut = None if body is None else body[:8000]
        rows.append({"id": r.accession, "item2": cut, "truncated": cut != body})
        answers[r.accession] = text.property_states(doc)
    return rows, answers


# Right when the rule adds no state and misses at most one of Item 2's.
def property_right(rule: list[str], read: list[str]) -> bool:
    return not set(rule) - set(read) and len(set(read) - set(rule)) <= 1


# Saves each draw's filings first: python -m fiam.v4.hand_checks draws
if __name__ == "__main__" and sys.argv[1:2] == ["draws"]:
    OUT.mkdir(parents=True, exist_ok=True)
    made = {}
    for check in ("sections", "footprint", "five02"):
        for seed in (SEED, FRESH):
            got = draw(check, seed)
            made[f"{check}_{seed}"] = got["accession"].tolist()
    (OUT / "draws.json").write_text(json.dumps(made, indent=1))
    print({k: len(v) for k, v in made.items()})


# Writes the worksheets: python -m fiam.v4.hand_checks sheets [seed]
if __name__ == "__main__" and sys.argv[1:2] == ["sheets"]:
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else SEED
    OUT.mkdir(parents=True, exist_ok=True)
    rule = {}
    for check, make in (("footprint", footprint_rows), ("five02", five02_rows)):
        rows, rule[check] = make(seed)
        (OUT / f"{check}_{seed}_sheet.json").write_text(json.dumps(rows, indent=1))
    (OUT / f"rule_answers_{seed}.json").write_text(json.dumps(rule, indent=1, default=str))
    for check, make in (("sections", sections_rows), ("customers", customers_rows)):
        (OUT / f"{check}_{seed}_sheet.json").write_text(json.dumps(make(seed), indent=1))
    print(sorted(p.name for p in OUT.iterdir()))


# The leader's draw, saved first, then the sheet: hand_checks leader
if __name__ == "__main__" and sys.argv[1:2] == ["leader"]:
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else LEADER_SEED
    saved, pick = saved_draws(), leader_draw(seed)
    saved[f"leader_{seed}"] = pick["accession"].tolist()
    (OUT / "draws.json").write_text(json.dumps(saved, indent=1))
    rows, rule = leader_rows(pick)
    (OUT / f"leader_{seed}_sheet.json").write_text(json.dumps(rows, indent=1))
    (OUT / f"leader_{seed}_sheet.md").write_text(leader_markdown(rows))
    (OUT / f"rule_answers_leader_{seed}.json").write_text(json.dumps(rule, indent=1))
    print(len(rows), "rows;", sum(r["code_found"] in (None, [], "") for r in rows), "found nothing")


# The protocol's bars, scored from the checker's verdicts and the rule.
def score(seed: int = SEED) -> dict:
    files = {c: OUT / f"{c}_{seed}_verdicts.json" for c in SIZES}
    verdict = {c: json.loads(f.read_text()) for c, f in files.items() if f.exists()}
    rule = json.loads((OUT / f"rule_answers_{seed}.json").read_text())
    out = {"seed": seed, "checked": sorted(verdict)}
    # A check with no verdicts for this seed was not rerun (it had passed).
    verdict = {c: verdict.get(c, []) for c in SIZES}
    for part in ("1a", "7"):
        rows = [v for v in verdict["sections"] if v["section"] == part]
        right = sum(bool(v["correct"]) for v in rows)
        out[f"item{part}"] = {"checked": len(rows), "correct": right, "pass": right >= 90}
    agree = 0
    for v in verdict["five02"]:
        got = rule["five02"][v["id"]]
        mine = bool(got["ceo_cfo_leaving"] or got["director_disagreement"])
        agree += mine == bool(v["ceo_cfo_leaving"] or v["director_disagreement"])
    n = len(verdict["five02"])
    out["five02"] = {"checked": n, "agree": agree, "pass": agree >= 0.9 * n}
    right = sum(
        (rule["footprint"][v["id"]] or "none") == (v["state"] or "none")
        for v in verdict["footprint"]
    )
    n = len(verdict["footprint"])
    out["footprint"] = {"checked": n, "hq_right": right, "pass": right >= 0.95 * n}
    rows = verdict["customers"]
    names = sum(bool(v["name_right"]) for v in rows)
    matched = [v for v in rows if v.get("permno_right") is not None]
    permnos = sum(bool(v["permno_right"]) for v in matched)
    out["customers"] = {
        "checked": len(rows),
        "name_right": names,
        "matched": len(matched),
        "permno_right": permnos,
        "pass": names >= 0.85 * len(rows) and permnos >= 0.9 * max(1, len(matched)),
    }
    # A part with nothing checked has no pass or fail for this seed.
    for part, got in out.items():
        if isinstance(got, dict) and got["checked"] == 0:
            out[part] = {"checked": 0, "pass": None}
    (OUT / f"results_{seed}.json").write_text(json.dumps(out, indent=1))
    return out


# Scores one seed against the bars: python -m fiam.v4.hand_checks score
if __name__ == "__main__" and sys.argv[1:2] == ["score"]:
    print(json.dumps(score(int(sys.argv[2]) if len(sys.argv) > 2 else SEED), indent=1))


# The property check's draw and sheet: hand_checks properties <seed>
if __name__ == "__main__" and sys.argv[1:2] == ["properties"]:
    seed = int(sys.argv[2])
    saved = saved_draws()
    rows, rule = properties_rows(seed)
    saved[f"properties_{seed}"] = [r["id"] for r in rows]
    (OUT / "draws.json").write_text(json.dumps(saved, indent=1))
    (OUT / f"properties_{seed}_sheet.json").write_text(json.dumps(rows, indent=1))
    (OUT / f"rule_answers_properties_{seed}.json").write_text(json.dumps(rule, indent=1))
    print(len(rows), "drawn,", sum(r["item2"] is None for r in rows), "without an Item 2")


# Scores the property check: hand_checks properties-score seed
if __name__ == "__main__" and sys.argv[1:2] == ["properties-score"]:
    seed = int(sys.argv[2])
    rule = json.loads((OUT / f"rule_answers_properties_{seed}.json").read_text())
    read = json.loads((OUT / f"properties_{seed}_verdicts.json").read_text())
    right = sum(property_right(rule[v["id"]], v["states"]) for v in read)
    out = {"seed": seed, "checked": len(read), "right": right, "pass": right >= 0.9 * len(read)}
    (OUT / f"results_properties_{seed}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


# Words as lower-case letters and digits, for a tolerant match.
def plain(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))


# The blind readers against the code, by the protocol's decision 9.
def leader_score(seed: int = LEADER_SEED) -> dict:
    sheet = json.loads((OUT / f"leader_{seed}_sheet.json").read_text())
    read = {v["n"]: v for v in json.loads((OUT / f"leader_{seed}_verdicts.json").read_text())}
    pop = population("annual").set_index("accession")
    rows = []
    for r in sheet:
        v, acc = read[r["n"]], r["filing"]
        if r["check"] in ("Item 1A", "Item 7"):
            doc = document(int(pop.loc[acc, "cik"]), acc)
            span = text.section(doc, "1a" if r["check"] == "Item 1A" else "7")
            # The reader's first and last words sit at the cut's two ends.
            first = " ".join(plain(v.get("start_words", "")).split()[:6])
            last = " ".join(plain(v.get("end_words", "")).split()[-6:])
            if v.get("absent") or span is None:
                right = bool(v.get("absent")) and span is None
            else:
                right = first in plain(span[:400]) and last in plain(span[-400:])
        elif r["check"] == "Headquarters":
            right = (r["code_found"] or None) == (v.get("state") or None)
        else:
            right = property_right(r["code_found"] or [], v.get("states") or [])
        rows.append({"n": r["n"], "check": r["check"], "right": bool(right)})
    out = {"seed": seed, "reader": "three blind AI readers (decision 9)", "rows": rows}
    kinds = {"Item 1A": ("Item 1A",), "Item 7": ("Item 7",)}
    kinds["Footprint"] = ("Headquarters", "Property states")
    for name, checks in kinds.items():
        wrong = [x["n"] for x in rows if x["check"] in checks and not x["right"]]
        n = sum(x["check"] in checks for x in rows)
        out[name] = {"checked": n, "wrong": wrong, "pass": len(wrong) < 2}
    (OUT / f"results_leader_{seed}.json").write_text(json.dumps(out, indent=1))
    return out


# Scores the blind readers on the leader draw: hand_checks leader-score
if __name__ == "__main__" and sys.argv[1:2] == ["leader-score"]:
    print(
        json.dumps(leader_score(int(sys.argv[2]) if len(sys.argv) > 2 else LEADER_SEED), indent=1)
    )


# Receipts of every check file and the protocol: hand_checks receipts
if __name__ == "__main__" and sys.argv[1:2] == ["receipts"]:
    import hashlib

    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "receipts.json")
    files.append(ROOT / "versions" / "v4" / "protocol.md")
    book = {
        str(p.relative_to(ROOT)): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
            "modified_utc": pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").isoformat(),
        }
        for p in files
    }
    (OUT / "receipts.json").write_text(json.dumps(book, indent=1))
    print(len(book), "receipts written")
