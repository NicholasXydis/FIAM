# The event-triage agent: a local model labels the final book's 8-Ks.

import json
import re

import pandas as pd

from fiam import paths
from fiam.agents import final_book as F

# The final book's 8-Ks: three months to the book's date, named.
FINAL = F.PACK / "triage"
START = "2026-06-01"
MAIN_CHARS, EXHIBIT_CHARS = 6_000, 6_000
EVENTS = [
    "earnings_results",
    "guidance_or_outlook",
    "merger_or_acquisition",
    "asset_sale_or_spin_off",
    "financing_or_debt",
    "material_contract",
    "executive_or_director_change",
    "shareholder_vote",
    "dividend_or_buyback",
    "restructuring_or_impairment",
    "legal_or_regulatory",
    "accounting_or_auditor",
    "investor_presentation",
    "governance_or_bylaws",
    "other",
]
TONES = ["good", "bad", "neutral"]
MATERIALITY = {"low": 1, "medium": 2, "high": 3}
FINAL_SCHEMA = dict(
    type="object",
    properties=dict(
        event_type=dict(type="string", enum=EVENTS),
        tone=dict(type="string", enum=TONES),
        materiality=dict(type="string", enum=list(MATERIALITY)),
        summary=dict(type="string"),
    ),
    required=["event_type", "tone", "materiality", "summary"],
)
FINAL_SYSTEM = (
    "You triage company disclosures for an investment research desk. You read one Form 8-K "
    "current report: its item numbers, the main document from its first item heading, and the "
    "start of its press-release exhibit if it has one.\n\n"
    "Return four fields.\n"
    "- event_type: the main event, one of " + ", ".join(EVENTS) + ".\n"
    "- tone: good if the news should raise the company's value, bad if it should lower it, "
    "neutral if an investor would not act on it (a routine vote, a scheduled dividend, "
    "boilerplate).\n"
    "- materiality: high if it could move the stock several percent, medium if it matters but "
    "less, low if routine.\n"
    "- summary: one plain sentence of at most 30 words on what the filing says.\n\n"
    "Judge only from the text shown. Do not use what you may know about the company."
)
# The events each 8-K item usually reports, to check the labels' sense.
ITEM_EVENTS = {
    "1.01": {"material_contract", "merger_or_acquisition", "financing_or_debt"},
    "2.01": {"merger_or_acquisition", "asset_sale_or_spin_off"},
    "2.02": {"earnings_results", "guidance_or_outlook"},
    "2.03": {"financing_or_debt"},
    "2.05": {"restructuring_or_impairment"},
    "2.06": {"restructuring_or_impairment"},
    "4.01": {"accounting_or_auditor"},
    "4.02": {"accounting_or_auditor"},
    "5.02": {"executive_or_director_change"},
    "5.03": {"governance_or_bylaws"},
    "5.07": {"shareholder_vote"},
}
ITEM_HEAD = r"(?im)^\s*item\s*\d\.\d\d"


# The book's 8-Ks in the window, and how many came public too late.
def final_filings(held: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    f = pd.read_parquet(F.EDGAR / "filings.parquet")
    f = f[(f["form"] == "8-K") & f["cik"].isin(held["cik"].dropna().astype(int))]
    f = f[(f["filing_date"] >= START) & (f["filing_date"] <= F.AS_OF)].reset_index(drop=True)
    public = F.public_by(f["accepted"], f["filing_date"]).to_numpy()
    late = int((~public).sum())
    keep = ["permno", "ticker", "company_name", "w", "side", "cik"]
    f = f[public].merge(held[keep], on="cik", how="inner")
    return f.sort_values(["filing_date", "accession"], ignore_index=True), late


# One filing's prompt: items, main text from its first item, exhibit.
def final_prompt(row: dict) -> str:
    body = F.main_text(row["cik"], row["accession"], row["document"], FINAL / "sec_cache")
    first = re.search(ITEM_HEAD, body)
    body = body[first.start() if first else 0 :][:MAIN_CHARS]
    exhibit = F.exhibit_text(row["cik"], row["accession"], FINAL / "sec_cache")[:EXHIBIT_CHARS]
    parts = [f"Items: {row['items']}", f"Main document:\n{body}"]
    if exhibit:
        parts.append(f"Press-release exhibit (start):\n{exhibit}")
    return "\n\n".join(parts)


# An answer kept only if every field is present and in its list.
def format_check(answer: dict) -> str | None:
    if set(answer) != set(FINAL_SCHEMA["required"]):
        return f"fields {sorted(answer)}"
    if answer["event_type"] not in EVENTS:
        return f"event_type {answer['event_type']!r}"
    if answer["tone"] not in TONES:
        return f"tone {answer['tone']!r}"
    if answer["materiality"] not in MATERIALITY:
        return f"materiality {answer['materiality']!r}"
    summary = answer["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 400:
        return "summary empty or longer than 400 characters"
    return None


# Whether a label matches what the filing's items usually report.
def items_agree(items: str, event: str) -> bool | None:
    expected = set().union(*(ITEM_EVENTS.get(i, set()) for i in str(items).split(",")))
    return event in expected if expected else None


# Counts by side, good and bad shares, and the five weightiest events.
def final_summary(labels: pd.DataFrame, held: pd.DataFrame) -> dict:
    ok = labels[labels["check"].isna()]
    sides = {}
    for side, group in ok.groupby("side"):
        tones = group["tone"].value_counts()
        named = held[held["side"] == side]
        sides[side] = dict(
            names_in_book=int(len(named)),
            names_with_8k=int(group["permno"].nunique()),
            filings=int(len(group)),
            good=int(tones.get("good", 0)),
            bad=int(tones.get("bad", 0)),
            neutral=int(tones.get("neutral", 0)),
            share_good=round(float(tones.get("good", 0) / len(group)), 4),
            share_bad=round(float(tones.get("bad", 0) / len(group)), 4),
            share_neutral=round(float(tones.get("neutral", 0) / len(group)), 4),
            event_types={k: int(v) for k, v in group["event_type"].value_counts().items()},
            materiality={k: int(v) for k, v in group["materiality"].value_counts().items()},
        )
    # News for our side: good news on a long, bad news on a short.
    toned = ok[ok["tone"] != "neutral"]
    helps = ((toned["side"] == "long") & (toned["tone"] == "good")) | (
        (toned["side"] == "short") & (toned["tone"] == "bad")
    )
    # Importance: materiality first, then the position's size.
    ranked = ok.assign(
        rank_materiality=ok["materiality"].map(MATERIALITY), size=ok["w"].abs()
    ).sort_values(
        ["rank_materiality", "size", "filing_date", "accession"],
        ascending=[False, False, True, True],
    )
    top = []
    for r in ranked.head(5).itertuples():
        top.append(
            dict(
                ticker=r.ticker,
                company=r.company_name,
                side=r.side,
                weight=round(float(r.w), 6),
                filing_date=r.filing_date,
                accepted=r.accepted,
                accession=r.accession,
                items=r.items,
                event_type=r.event_type,
                tone=r.tone,
                materiality=r.materiality,
                summary=r.summary,
                for_our_side={"good": r.side == "long", "bad": r.side == "short"}.get(r.tone),
                url=f"{F.folder(r.cik, r.accession)}/{r.document}",
            )
        )
    agree = ok["items_agree"].dropna()
    return dict(
        by_side=sides,
        non_neutral_filings=int(len(toned)),
        share_for_our_side=round(float(helps.mean()), 4) if len(toned) else None,
        share_for_our_side_means="good news on a long or bad news on a short, of non-neutral",
        labels_matching_item_codes=dict(
            checked=int(len(agree)), share=round(float(agree.mean()), 4) if len(agree) else None
        ),
        top_five=top,
        top_five_rule="highest materiality first, then the largest absolute weight",
    )


# Labels every 8-K the book's names filed from June to the book's date.
def final() -> None:
    held = F.book()
    FINAL.mkdir(parents=True, exist_ok=True)
    filings, late = final_filings(held)
    print(f"  triage: {len(filings):,} 8-Ks to label, {late} accepted after {F.AS_OF}", flush=True)
    rows = filings.to_dict("records")
    prompts = F.fetch_all(final_prompt, rows)
    with F.Asker(FINAL / "calls.jsonl", FINAL_SYSTEM, FINAL_SCHEMA) as asker:
        answers = asker.ask_all(list(zip(filings["accession"], prompts)))
    checks = [a["error"] or format_check(a["parsed"]) for a in answers]
    parsed = [a["parsed"] if c is None else {} for a, c in zip(answers, checks)]
    labels = filings.assign(
        event_type=[p.get("event_type") for p in parsed],
        tone=[p.get("tone") for p in parsed],
        materiality=[p.get("materiality") for p in parsed],
        summary=[p.get("summary") for p in parsed],
        check=checks,
    )
    labels["items_agree"] = [
        items_agree(i, e) if e else None for i, e in zip(labels["items"], labels["event_type"])
    ]
    keep = ["filing_date", "accepted", "accession", "ticker", "company_name", "side", "w"]
    keep += ["items", "event_type", "tone", "materiality", "summary", "items_agree", "check"]
    labels[keep].to_csv(FINAL / "labels_final.csv", index=False)
    failures = sum(c is not None for c in checks)
    out = dict(
        what="A local model labelled every 8-K that the final book's companies filed from "
        f"{START} to {F.AS_OF}, using only filings accepted by the book's date. It reads text "
        "and sets no weight.",
        book=dict(
            date=F.AS_OF,
            names=int(len(held)),
            longs=int((held["side"] == "long").sum()),
            shorts=int((held["side"] == "short").sum()),
        ),
        filings=dict(
            in_window=int(len(filings) + late),
            accepted_after_book_date_left_out=late,
            labelled=int(len(filings)),
            passed_format_check=int(len(filings) - failures),
            failed=failures,
            failures=[
                dict(accession=a, reason=c)
                for a, c in zip(labels["accession"], checks)
                if c is not None
            ],
        ),
        accounting=asker.accounting(
            answers, sum(a["error"] is None and c is not None for a, c in zip(answers, checks))
        ),
        **final_summary(labels, held),
    )
    paths.write_json(FINAL / "triage_final.json", out, rounded=False)
    print(json.dumps({k: out[k] for k in ("filings", "by_side")}, indent=1, default=str))


if __name__ == "__main__":
    # uv run python -m fiam.agents.triage
    final()
