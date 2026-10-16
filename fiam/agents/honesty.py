# Honesty tests: does the model read the filing, or recall the company? (docs/protocols/honesty*.md)

import hashlib
import json
import re
import sys
import time
from operator import itemgetter

import numpy as np
import pandas as pd

from fiam import data
from fiam.agents import harness as H

PER_SIDE, SEED = 250, 42
BEFORE = ("2024-01-01", "2024-12-31")
AFTER = ("2025-02-01", "2025-12-29")
NUMBER = re.compile(r"\d+(?:\.\d+)?\s?%|\$\s?\d")
DIRECTION = re.compile(r"\b(?:increas|decreas|rose|fell|grew|declin)", re.I)
OPPOSITES = {
    "increase": "decrease",
    "increased": "decreased",
    "increases": "decreases",
    "rose": "fell",
    "grew": "declined",
    "higher": "lower",
    "up": "down",
    "gain": "loss",
    "gains": "losses",
    "improved": "worsened",
    "beat": "missed",
}
OPPOSITES |= {v: k for k, v in list(OPPOSITES.items())}
SYSTEM = (
    "You are an equity analyst. Read this earnings filing excerpt and say whether the company's "
    "stock will beat the market over the next two trading days. Answer up or down."
)
SCHEMA = dict(
    type="object", properties=dict(call=dict(type="string", enum=["up", "down"])), required=["call"]
)
PICK = "Which company filed this? Choose one of the names given."


# Earnings 8-Ks whose excerpt has a number and a direction word, 250 each side of the cutoff.
def sample() -> pd.DataFrame:
    filings = data.filings(
        ["document_id", "permno", "filing_date", "company_name", "item_202_earnings"]
    )
    texts = data.research("filing_text", ["document_id", "excerpt"])
    df = filings[filings["item_202_earnings"] > 0].merge(texts, on="document_id")
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df = df[df["excerpt"].str.contains(NUMBER) & df["excerpt"].str.contains(DIRECTION)]
    size = data.features(["size_grp"]).rename(columns={"eom": "month_end"})
    df["month_end"] = df["filing_date"] + pd.offsets.MonthEnd(0)
    df = df.merge(
        size, left_on=["permno", "month_end"], right_on=["permno", "month_end"], how="left"
    )
    rng = np.random.default_rng(SEED)
    out = []
    for side, (first, last) in (("before", BEFORE), ("after", AFTER)):
        part = df[df["filing_date"].between(first, last)].copy()
        part["group"] = part["size_grp"].fillna("unknown")
        if len(part) <= PER_SIDE:
            out.append(part.assign(side=side))
            continue
        share = part["group"].value_counts(normalize=True)
        taken = []
        for group, frac in share.items():
            pool = part[part["group"] == group]
            take = min(len(pool), int(frac * PER_SIDE))
            taken.append(pool.iloc[rng.choice(len(pool), take, replace=False)])
        chosen = pd.concat(taken)
        # Rounding down leaves a few places; they are filled from the rest at random.
        rest = part.drop(chosen.index)
        extra = rest.iloc[rng.choice(len(rest), PER_SIDE - len(chosen), replace=False)]
        out.append(pd.concat([chosen, extra]).assign(side=side))
    return pd.concat(out, ignore_index=True).sort_values("document_id", ignore_index=True)


# The protocol's four texts for one filing; the fifth condition repeats the masked one.
def conditions(row: pd.Series) -> dict:
    masked = row["excerpt"]
    later = (row["filing_date"] + pd.DateOffset(years=1)).strftime("%B %d, %Y")

    def flip(match: re.Match) -> str:
        word = match.group(0)
        swap = OPPOSITES[word.lower()]
        return swap.capitalize() if word[0].isupper() else swap

    words = re.compile(r"\b(" + "|".join(sorted(OPPOSITES, key=len, reverse=True)) + r")\b", re.I)
    reversed_ = words.sub(flip, masked)
    reversed_ = re.sub(
        r"(?<![\d.])(-?)(\d+(?:\.\d+)?)\s?%",
        lambda m: f"{'' if m.group(1) else '-'}{m.group(2)}%",
        reversed_,
    )
    return dict(
        masked=masked,
        named=masked.replace("[COMPANY]", str(row["company_name"])),
        reversed=reversed_,
        dated=masked.replace("[DATE]", later),
    )


# Five candidate names: the filer and four others of its size, drawn with the seed.
def candidates(row: pd.Series, names: pd.DataFrame) -> list[str]:
    stream = int(hashlib.sha256(str(row["document_id"]).encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng([SEED, stream])
    rest = names[
        (names["permno"] != row["permno"]) & (names["company_name"] != row["company_name"])
    ]
    others = rest[rest["size_grp"] == row["size_grp"]]
    # A filer with no size group, or too few peers in it, draws from everyone else.
    others = others if len(others) >= 4 else rest
    picked = others.iloc[rng.choice(len(others), 4, replace=False)]
    choice = [str(row["company_name"]), *picked["company_name"].astype(str)]
    rng.shuffle(choice)
    return choice


# Every call, saved as it comes; the abnormal-return check is done later by fiam.exhibits.honesty.
def main(minutes: float | None = None) -> None:
    chosen = sample()
    names = chosen.drop_duplicates("permno")[["permno", "company_name", "size_grp"]]
    key = itemgetter("document_id", "condition")
    stop = time.time() + minutes * 60 if minutes else None
    with H.Server("gemma", H.LONG_PROMPTS) as server, H.answers("honesty", key) as saved:
        done, save = saved
        H.stamp(server, "honesty")
        for _, row in chosen.iterrows():
            texts = conditions(row)
            asks = [(c, t, 0.0) for c, t in texts.items()] + [("repeat", texts["masked"], 0.7)]
            for condition, text, temperature in asks:
                if (row["document_id"], condition) in done:
                    continue
                if stop and time.time() > stop:
                    return
                messages = [dict(role="system", content=SYSTEM), dict(role="user", content=text)]
                reply = server.chat(messages, schema=SCHEMA, temperature=temperature, seed=43)
                save(
                    dict(
                        document_id=row["document_id"],
                        side=row["side"],
                        condition=condition,
                        call=H.parse(reply).get("call"),
                    )
                )
            if (row["document_id"], "identify") not in done:
                options = candidates(row, names)
                schema = dict(
                    type="object",
                    properties=dict(company=dict(type="string", enum=options)),
                    required=["company"],
                )
                text = f"{PICK}\nNames: {'; '.join(options)}\n\n{texts['masked']}"
                reply = server.chat([dict(role="user", content=text)], schema=schema)
                answer = H.parse(reply).get("company")
                save(
                    dict(
                        document_id=row["document_id"],
                        side=row["side"],
                        condition="identify",
                        call=answer,
                        correct=answer == str(row["company_name"]),
                    )
                )
    print(json.dumps(dict(filings=len(chosen), sides=chosen["side"].value_counts().to_dict())))


if __name__ == "__main__":
    main(float(sys.argv[1]) if sys.argv[1:] else None)
