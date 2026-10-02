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

# What each measure is, in words, so a reader or a model never has to guess a code.
NAMES = {
    "ivol_capm_21d": "idiosyncratic volatility over the last month",
    "be_me": "book value to market value",
    "qmj": "quality-minus-junk score",
    "at_gr1": "one-year growth in total assets",
    "niq_su": "standardized surprise in quarterly earnings",
    "ope_be": "operating profit to book equity",
    "chcsho_12m": "12-month change in shares outstanding",
    "o_score": "Ohlson bankruptcy-risk score",
    "ret_12_1": "return over the past 12 months, skipping the last",
    "gp_at": "gross profit to total assets",
    "noa_gr1a": "one-year growth in net operating assets",
    "eqnetis_at": "net equity issued, relative to total assets",
}


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
                # Each measure by its name, so the model never has to guess what a code means.
                signal_percentiles={NAMES[c]: v for c, v in ranks.get(name["permno"], {}).items()},
                signal_directions={
                    NAMES[c]: "higher is better" if s > 0 else "lower is better"
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
