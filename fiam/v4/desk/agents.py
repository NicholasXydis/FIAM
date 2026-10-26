# The sizing agent and its devil's advocate (PLAN §10.3, step 8 rules).

import json

from fiam.v4.desk import cards

# The only shrinks the agent may give; anything else is no shrink.
SHRINKS = (1.0, 0.75, 0.5, 0.25)
# The longest reason kept, in characters.
REASON = 300
SIZING = {"type": "object", "required": ["shrink", "reason"],
          "properties": {"shrink": {"type": "number", "enum": list(SHRINKS)},
                         "reason": {"type": "string", "maxLength": REASON}}}  # fmt: skip
ADVOCATE = {"type": "object", "required": ["argument", "agree"],
            "properties": {"argument": {"type": "string", "maxLength": REASON},
                           "agree": {"type": "boolean"}}}  # fmt: skip
# The fixed prompt, from PDF p7 item 3; the card carries no identity.
PROMPT = ("You size one position of a market-neutral US equity fund. You may only keep it (1) "
          "or shrink it to 0.75, 0.5 or 0.25 of its weight. Shrink into an earnings print the "
          "signal has no edge on, where the position would take too long to exit, where its "
          "volatility has jumped, or where the crowd agrees too much. The card is all you know: "
          "no name, ticker, sector or date. Answer in JSON.")  # fmt: skip


# The three conversations: proposal, argument against it, final answer.
def sizing(card: dict) -> list:
    return [{"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(card, sort_keys=True)}]  # fmt: skip


# The advocate sees the card and the proposal, and argues against it.
def advocate(card: dict, proposal: dict) -> list:
    text = {"card": card, "proposal": proposal, "task": "Argue against this proposal."}
    return [{"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(text, sort_keys=True)}]  # fmt: skip


# The sizing agent's last word, with the argument in front of it.
def final(card: dict, proposal: dict, argument: dict) -> list:
    text = {"card": card, "your_proposal": proposal, "argument": argument}
    return [{"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(text, sort_keys=True)}]  # fmt: skip


# One cached desk: answers by key; a model answers what is missing.
class Desk:
    # A model with chat(messages, schema), or None to replay only.
    def __init__(self, store: dict, meta: dict, model=None, save=None):
        self.store, self.meta, self.model, self.save = store, meta, model, save
        self.missing: list = []

    # One answer by its PLAN §10.1 key, from the cache or the model.
    def ask(self, messages: list, schema: dict, formed) -> dict | None:
        m = self.meta
        k = cards.key(m["model_sha"], m["build"], m["server_args"], messages, schema,
                      m["temperature"], m["seed"], m["tokens"])  # fmt: skip
        if k in self.store:
            return self.store[k]["answer"]
        if self.model is None:
            self.missing.append(k)
            return None
        answer = self.model.chat(messages, schema)
        row = {"key": k, "answer": answer, "formed": str(formed), "cutoff": m["cutoff"],
               "messages": messages, "on": getattr(self.model, "where", "")}  # fmt: skip
        self.store[k] = row
        if self.save is not None:
            self.save(row)
        return answer

    # The final shrink for one card; code keeps it only if it is allowed.
    def decide(self, card: dict, formed) -> tuple:
        proposal = self.ask(sizing(card), SIZING, formed)
        if proposal is None:
            return None, {}
        argument = self.ask(advocate(card, proposal), ADVOCATE, formed)
        if argument is None:
            return None, {}
        last = self.ask(final(card, proposal, argument), SIZING, formed)
        if last is None:
            return None, {}
        shrink = last.get("shrink")
        shrink = float(shrink) if shrink in SHRINKS else 1.0
        return shrink, {"proposal": proposal, "argument": argument, "final": last}
