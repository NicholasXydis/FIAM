# The event-triage agent: a local model labels masked 2015-2018 8-Ks.

from operator import itemgetter

import numpy as np
import pandas as pd

from fiam import data, paths
from fiam.agents import harness as H
from fiam.ml.triage import KINDS

PROMPT = H.ROOT / "prompts" / "agents" / "triage.md"
LABELS = paths.EXHIBITS / "agents" / "triage_labels.parquet"
# The sample: 6,000 filings from 2015-2018, drawn once with this seed.
SAMPLE, LAST, SEED = 40 if paths.SMOKE else 6_000, "2018-12-31", 42

SCHEMA = dict(
    type="object", properties=dict(label=dict(type="string", enum=KINDS)), required=["label"]
)


# The filings to label, the same ones on every machine.
def sample() -> pd.DataFrame:
    texts = data.research("filing_text", ["document_id", "eom", "excerpt"])
    texts = texts[texts["eom"] <= LAST].sort_values("document_id", ignore_index=True)
    at = np.random.default_rng(SEED).choice(len(texts), SAMPLE, replace=False)
    return texts.iloc[np.sort(at)].reset_index(drop=True)


# Labels each filing once, saving as it goes so a stop can resume.
def main() -> None:
    if data.research("filing_text", ["document_id"]) is None:
        raise SystemExit("No 8-K text layer: import the new fiam_v1.zip, then run this again.")
    chosen = sample()
    print(f"  triage: {len(chosen):,} filings to label", flush=True)
    system = PROMPT.read_text(encoding="utf-8")
    saved = H.answers("triage", itemgetter("document_id"))
    with H.Server("gemma") as server, saved as (done, save):
        for document, excerpt in zip(chosen["document_id"], chosen["excerpt"]):
            if document in done:
                continue
            messages = [dict(role="system", content=system), dict(role="user", content=excerpt)]
            reply = server.chat(messages, schema=SCHEMA)
            label = H.parse(reply).get("label", "unreadable")
            row = dict(document_id=document, label=label, model=server.name)
            save(row)
    out = pd.DataFrame([done[d] for d in chosen["document_id"]])
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(LABELS, index=False)
    print(f"{len(out):,} filings labelled: {out['label'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
