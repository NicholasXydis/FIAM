# The explainer: why the book held its biggest winners and losers, in words tied to the facts.

import json

from fiam import book as P
from fiam import paths
from fiam.agents import critic
from fiam.agents import harness as H

OUT = paths.EXHIBITS / "explainer.json"
SYSTEM = (
    "You explain to an investment committee why a quantitative portfolio held a position that "
    "became one of its largest winners or losers: which signals put it in the book, and what it "
    "contributed. Use only the facts given, cite the numbers you rely on, and never add anything "
    "you know about the company or what happened to it later. Two or three sentences."
)
SCHEMA = dict(type="object", properties=dict(why=dict(type="string")), required=["why"])


# Each of the twelve signals as a percentile within its month, at the name's last decision.
def signal_ranks(names: list[dict]) -> dict[int, dict]:
    universe = P.universe()
    ranks = {c: universe.groupby("eom")[c].rank(pct=True) for c in P.SIGNALS}
    table = universe[["permno", "eom"]].assign(**{c: (r * 100).round() for c, r in ranks.items()})
    out = {}
    for name in names:
        rows = table[table["permno"] == name["permno"]].sort_values("eom")
        if len(rows):
            out[name["permno"]] = {c: rows.iloc[-1][c] for c in P.SIGNALS}
    return out


# One answer per large position, from its facts alone.
def main() -> None:
    names = critic.positions(by="pnl")
    ranks = signal_ranks(names)
    out = []
    with H.Server("qwen") as server:
        for name in names[: 2 if paths.SMOKE else None]:
            facts = dict(
                name,
                signal_percentiles=ranks.get(name["permno"], {}),
                signal_directions={
                    c: "higher is better" if s > 0 else "lower is better"
                    for c, s in P.SIGNALS.items()
                },
            )
            messages = [
                dict(role="system", content=SYSTEM),
                dict(role="user", content=json.dumps(facts, default=str)),
            ]
            reply = server.chat(messages, schema=SCHEMA)
            why = H.parse(reply).get("why", "")
            out.append(
                dict(
                    ticker=name["ticker"],
                    company=name["company"],
                    side=name["side"],
                    why=why,
                    facts=facts,
                )
            )
    summary = dict(
        what="Why the book held its ten largest winners and ten largest losers by realized P&L, "
        "written by a local model from the facts shown beside each answer and nothing else. "
        "Retrospective, names visible.",
        model=server.name,
        positions=out,
    )
    paths.write_json(OUT, summary, rounded=False, default=str)
    print(f"{len(out)} positions explained")


if __name__ == "__main__":
    main()
