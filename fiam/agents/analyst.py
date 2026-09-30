# The analyst agent: reads a stock-month's material filings and its ranks, returns a conviction.

from operator import itemgetter

import numpy as np
import pandas as pd

from fiam import book as P
from fiam import data, paths
from fiam.agents import harness as H
from fiam.ml import crowd as C

PROMPT = H.ROOT / "prompts" / "agents" / "analyst.md"
OUT = paths.EXHIBITS / "analyst.json"
CONVICTIONS = paths.EXHIBITS / "agents" / "analyst.parquet"
# The pre-registered scope: material filings among the 400 best and worst composite scores.
TAILS, CALLS, SEED = 400, 20 if paths.SMOKE else 5_000, 42
PROBES = 5 if paths.SMOKE else 500
# The item codes the brief singles out as material events (amendment 6).
MATERIAL = ["item_101_contract", "item_102_contract_termination", "item_201_acquisition"]
MATERIAL += ["item_202_earnings", "item_205_impairment", "item_206_distress"]
MATERIAL += ["item_401_auditor_change", "item_402_nonreliance", "item_502_management_change"]
SCHEMA = dict(
    type="object",
    properties=dict(
        what_happened=dict(type="string"),
        expected=dict(type="boolean"),
        conviction=dict(type="integer", minimum=-2, maximum=2),
    ),
    required=["what_happened", "expected", "conviction"],
)
PROBE_SCHEMA = dict(
    type="object",
    properties=dict(company=dict(type="string"), year=dict(type="integer")),
    required=["company", "year"],
)


# Filings carrying at least one material item code, dated to the month they were filed in.
def material() -> pd.DataFrame:
    filings = data.filings(["document_id", "permno", "filing_date", *MATERIAL])
    filings = filings[filings[MATERIAL].sum(axis=1) > 0]
    return filings.assign(
        eom=(filings["filing_date"] + pd.offsets.MonthEnd(0)).astype("datetime64[s]")
    )


# The stock-months to read: a material filing, and a composite score in either tail of the month.
def chosen() -> pd.DataFrame:
    filings = material()
    # Every month from 2015, so the scorer can learn from the conviction and it can be judged early.
    screened = P.screen(P.load_panel(), "2015-01-31", P.LAST_FORECAST)
    universe = P.build_signal(screened)[["permno", "eom", "composite"]]
    rank = universe.groupby("eom")["composite"].rank(method="first")
    size = universe.groupby("eom")["composite"].transform("size")
    tails = universe[(rank <= TAILS) | (rank > size - TAILS)]
    keys = filings[data.KEYS].drop_duplicates().merge(tails[data.KEYS], on=data.KEYS)
    if len(keys) > CALLS:
        keys = keys.iloc[
            np.sort(np.random.default_rng(SEED).choice(len(keys), CALLS, replace=False))
        ]
    return keys.sort_values(data.KEYS, ignore_index=True)


# The twelve months of ranks as a small table, months counted back from t, never dated.
def history(cards: pd.DataFrame, permno: int, eom: pd.Timestamp) -> str:
    past = cards[(cards["permno"] == permno) & (cards["eom"] <= eom)].tail(12)
    lines = [" | ".join(["month", *C.CARD])]
    for back, (_, row) in zip(range(len(past) - 1, -1, -1), past.iterrows()):
        lines.append(" | ".join([f"t-{back}" if back else "t", *(str(row[c]) for c in C.CARD)]))
    return "\n".join(lines)


# One stock-month's prompt: its material filings, then its rank history.
def task(texts: pd.DataFrame, cards: pd.DataFrame, permno: int, eom: pd.Timestamp) -> str:
    mine = texts[(texts["permno"] == permno) & (texts["eom"] == eom)]["excerpt"].head(3)
    filings = "\n\n---\n\n".join(t[:2_500] for t in mine)
    return f"Filings this month:\n\n{filings}\n\nRanks:\n{history(cards, permno, eom)}"


# Can the model name the company or the year from a masked filing? The hit rate is reported.
def probe(server: H.Server, texts: pd.DataFrame) -> dict:
    names = data.filings(["document_id", "ticker", "company_name", "filing_date"])
    sample = texts.iloc[np.random.default_rng(SEED + 1).choice(len(texts), PROBES, replace=False)]
    sample = sample.merge(names, on="document_id")
    company = year = 0
    for row in sample.itertuples():
        ask = (
            "Which company filed this, and in which year? Guess if unsure.\n\n"
            + row.excerpt[:2_500]
        )
        reply = server.chat([dict(role="user", content=ask)], schema=PROBE_SCHEMA)
        guess = H.parse(reply)
        said = str(guess.get("company", "")).lower()
        company += bool(said) and (
            said in str(row.company_name).lower() or said == str(row.ticker).lower()
        )
        year += guess.get("year") == row.filing_date.year
    return dict(
        filings=int(len(sample)), company_named=company / len(sample), year_named=year / len(sample)
    )


def main() -> None:
    texts = data.research("filing_text", ["document_id", *data.KEYS, "excerpt"])
    if texts is None:
        raise SystemExit("No 8-K text layer: import the new fiam_v1.zip, then run this again.")
    keys = chosen()
    print(f"  analyst: {len(keys):,} stock-months to read", flush=True)
    texts = texts[texts["document_id"].isin(material()["document_id"])]
    cards = C.cards()
    system = PROMPT.read_text(encoding="utf-8")
    saved = H.answers("analyst", itemgetter("permno", "eom"))
    with H.Server("qwen") as server, saved as (done, save):
        for permno, eom in zip(keys["permno"], keys["eom"]):
            key = (int(permno), f"{eom:%Y-%m-%d}")
            if key in done:
                continue
            messages = [
                dict(role="system", content=system),
                dict(role="user", content=task(texts, cards, permno, eom)),
            ]
            answer = H.parse(server.chat(messages, schema=SCHEMA))
            row = dict(permno=key[0], eom=key[1], model=server.name, **answer)
            save(row)
        leak = probe(server, texts)
    out = pd.DataFrame(done.values())
    out["eom"] = pd.to_datetime(out["eom"]).astype("datetime64[s]")
    # A cut-off answer has no conviction; it stays missing, never guessed.
    out = out.reindex(columns=[*out.columns.difference(["conviction"]), "conviction"])
    out = out.rename(columns={"conviction": "analyst_conviction"})
    out[[*data.KEYS, "analyst_conviction"]].to_parquet(CONVICTIONS, index=False)
    summary = dict(
        what="A local model read masked 8-Ks and twelve months of ranks for stock-months with a "
        "material filing in either tail of the composite; its conviction feeds the scorer.",
        model=server.name,
        stock_months=int(len(out)),
        conviction_counts=out["analyst_conviction"].value_counts().sort_index().to_dict(),
        look_ahead_probe=leak,
    )
    paths.write_json(OUT, summary, default=str)
    print(f"{len(out):,} stock-months read; probe {leak}")


if __name__ == "__main__":
    main()
