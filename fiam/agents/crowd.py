# Crowd agent: local models pick for retail clients from masked cards.

from operator import itemgetter

import numpy as np
import pandas as pd

from fiam import paths
from fiam.agents import harness as H
from fiam.ml import crowd as C

PROMPT = H.ROOT / "fiam" / "agents" / "prompts" / "crowd.md"
# Decisions Dec 2015 to Nov 2020: the 60 holding months of 2016-2020.
FIRST, LAST = "2015-12-31", "2020-11-30"
BATCH, PICKS, SEED = 40, 8, 42
MODELS = ("gemma", "qwen")


# A batch as the agent sees it: codes, percentiles, the month's filings.
def table(batch: pd.DataFrame, codes: list[str]) -> str:
    header = ["code", *C.CARD, "filings this month"]
    lines = [" | ".join(header)]
    for code, (_, row) in zip(codes, batch.iterrows()):
        events = "; ".join(label for label in C.EVENTS if row[label]) or "none"
        lines.append(" | ".join([code, *(str(row[c]) for c in C.CARD), events]))
    return "\n".join(lines)


# Each month's stocks shuffled by a set seed, so reruns ask the same.
def batches(frame: pd.DataFrame, month: pd.Timestamp) -> list[pd.DataFrame]:
    part = frame[frame["eom"] == month]
    order = np.random.default_rng([SEED, month.year, month.month]).permutation(len(part))
    part = part.iloc[order]
    return [part.iloc[i : i + BATCH] for i in range(0, len(part), BATCH)]


# One model through every month and batch, saving each answer to resume.
def pick(model: str, frame: pd.DataFrame, months: list) -> list[dict]:
    system = PROMPT.read_text(encoding="utf-8")
    saved = H.answers(f"crowd_{model}", itemgetter("eom", "batch"))
    with H.Server(model) as server, saved as (done, save):
        for month in months:
            for number, batch in enumerate(batches(frame, month)):
                key = (month.strftime("%Y-%m-%d"), number)
                if key in done:
                    continue
                codes = [f"S{i + 1:02d}" for i in range(len(batch))]
                want = min(PICKS, len(batch))
                schema = dict(
                    type="object",
                    properties=dict(
                        buy=dict(
                            type="array",
                            items=dict(type="string", enum=codes),
                            minItems=want,
                            maxItems=want,
                        )
                    ),
                    required=["buy"],
                )
                task = f"Pick the {want} stocks you would buy.\n\n{table(batch, codes)}"
                messages = [dict(role="system", content=system), dict(role="user", content=task)]
                reply = server.chat(messages, schema=schema)
                chosen = set(H.parse(reply).get("buy", []))
                row = dict(
                    eom=key[0],
                    batch=number,
                    model=server.name,
                    permnos=[int(p) for p in batch["permno"]],
                    picked=[int(c in chosen) for c in codes],
                )
                save(row)
    return list(done.values())


# Every model through every month, then one table of the crowd's picks.
def main() -> None:
    frame = C.cards(FIRST, LAST)
    months = sorted(frame["eom"].unique())
    if paths.SMOKE:
        months, frame = months[:1], frame[frame["eom"] == months[0]].head(2 * BATCH)
    rows = []
    for model in MODELS:
        for r in pick(model, frame, months):
            rows += [
                dict(permno=p, eom=r["eom"], model=r["model"], picked=k)
                for p, k in zip(r["permnos"], r["picked"])
            ]
    out = pd.DataFrame(rows).assign(eom=lambda d: pd.to_datetime(d["eom"]))
    out = out.sort_values(["eom", "permno", "model"]).drop_duplicates(["eom", "permno", "model"])
    C.PICKS.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(C.PICKS, index=False)
    print(f"{len(out):,} stock-months judged by {out['model'].nunique()} model(s)")


if __name__ == "__main__":
    main()
