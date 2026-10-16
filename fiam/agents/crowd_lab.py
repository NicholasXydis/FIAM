# The AI Crowd Lab: 30 retail investors and 30 copycat funds pick from anonymous cards, 2025-26.

import hashlib
import json
import os
import sys
import time
from operator import itemgetter
from pathlib import Path

import numpy as np
import pandas as pd

from fiam import book as P
from fiam import data
from fiam.agents import harness as H
from fiam.freeze import FROZEN

LABELS = FROZEN / "characteristic_labels.json"
SETS = FROZEN / "crowd_info_sets.json"
PROMPT = H.ROOT / "prompts" / "agents" / "crowd_lab.md"
COPYCAT = H.ROOT / "prompts" / "agents" / "crowd_lab_copycat.md"
JKP = Path("research/jkp/factor_details.csv")
# Decisions after Gemma's January 2025 cutoff: holding months 2025-02 to 2026-08.
FIRST, LAST = "2025-01-31", "2026-07-31"
STOCKS, PICKS, COLUMNS, N_SETS, SEED = 40, 8, 40, 5, 42
# 13 cards an agent-month timed at ~32 GPU hours (7.8 s a call); the protocol cuts evenly to fit 24.
CARDS = 9
PERSONAS = ("attention", "lottery", "momentum", "contrarian", "income", "familiar")


# Plain names for the 147 characteristics, from the JKP factor details, frozen for any machine.
def labels() -> dict:
    if LABELS.exists():
        return json.loads(LABELS.read_text(encoding="utf-8"))
    table = pd.read_csv(JKP, encoding="latin-1").dropna(subset=["abr_jkp"])
    names = table.drop_duplicates("abr_jkp").set_index("abr_jkp")["name_new"]
    names = names.str.replace("â€™", "'", regex=False).str.strip()
    out = {c: str(names.get(c, c)) for c in P.characteristics()}
    out["intrinsic_value"] = "Intrinsic value to price"
    FROZEN.mkdir(exist_ok=True)
    LABELS.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


# Five draws of 40 of the 147, seed 42, drawn once and frozen so every rerun shows the same.
def info_sets() -> list[list[str]]:
    if SETS.exists():
        return json.loads(SETS.read_text(encoding="utf-8"))
    rng = np.random.default_rng(SEED)
    chars = P.characteristics()
    sets = [sorted(rng.choice(chars, COLUMNS, replace=False).tolist()) for _ in range(N_SETS)]
    SETS.write_text(json.dumps(sets, indent=1) + "\n", encoding="utf-8")
    return sets


# v1's eligible stocks each month with every characteristic as a 0-100 percentile.
def universe() -> pd.DataFrame:
    chars = P.characteristics()
    frame = P.screen(P.load_panel(tuple(c for c in chars if c not in P.SIGNALS)), FIRST, LAST)
    for col in chars:
        frame[col] = (frame.groupby("eom")[col].rank(pct=True) * 100).round().fillna(50)
    frame[chars] = frame[chars].astype(int)
    return frame[[*data.KEYS, *chars]].reset_index(drop=True)


# The system prompt for one persona, with the shared instructions around it.
def persona_prompt(persona: str) -> str:
    text = PROMPT.read_text(encoding="utf-8")
    head, *sections = text.split("\n## ")
    found = {s.split("\n", 1)[0].strip(): s.split("\n", 1)[1].strip() for s in sections}
    return head.strip().format(persona=found[persona], picks=PICKS)


# This agent's cards this month: a fixed random draw of 40-stock cards, never the same twice.
def cards(month_rows: pd.DataFrame, agent: int, month: pd.Timestamp) -> list[pd.DataFrame]:
    rng = np.random.default_rng([SEED, agent, month.year, month.month])
    size = min(CARDS * STOCKS, len(month_rows))
    drawn = month_rows.iloc[rng.choice(len(month_rows), size, replace=False)]
    return [drawn.iloc[i : i + STOCKS] for i in range(0, size, STOCKS)]


# One card as compact CSV: codes and percentiles only, a quarter fewer tokens than a piped table.
def table(card: pd.DataFrame, columns: list[str], names: dict) -> tuple[str, list[str]]:
    codes = [f"S{i + 1:02d}" for i in range(len(card))]
    header = ",".join(["code", *(names[c].replace(",", " ") for c in columns)])
    rows = [
        ",".join([code, *map(str, values)]) for code, values in zip(codes, card[columns].values)
    ]
    return "\n".join([header, *rows]), codes


# The JSON shape every answer must take: exactly the asked number of codes from this card.
def schema(codes: list[str], short: bool = False) -> dict:
    items = dict(
        type="array", items=dict(type="string", enum=codes), minItems=PICKS, maxItems=PICKS
    )
    sides = dict(buy=items, short=items) if short else dict(buy=items)
    return dict(type="object", properties=sides, required=list(sides))


# The 30 retail investors: 6 personas x 5 information sets, card draws seeded by agent 0-29.
def retail_agents() -> list[dict]:
    sets = info_sets()
    out = []
    for agent in range(len(PERSONAS) * N_SETS):
        persona, info = PERSONAS[agent // N_SETS], agent % N_SETS
        tags = dict(persona=persona, info_set=info)
        out.append(dict(id=agent, seed=agent, system=persona_prompt(persona), columns=sets[info]))
        out[-1] |= dict(tags=tags, short=False)
    return out


# The 30 copycat funds: 10 per strategy text, each seeing the measures its text names plus a fill.
def copycat_agents() -> list[dict]:
    from fiam import mandate as M

    texts = [("v1", list(P.SIGNALS)), ("brief_2026", []), ("case_2025", [])]
    template = COPYCAT.read_text(encoding="utf-8")
    chars = P.characteristics()
    out = []
    for t, (name, named) in enumerate(texts):
        strategy = M.load(M.TEMPLATES / f"{name}.json").strategy_text
        system = template.format(strategy=strategy, picks=PICKS).strip()
        for j in range(10):
            agent = 10 * t + j
            rng = np.random.default_rng([SEED, 100 + agent])
            rest = [c for c in chars if c not in named]
            fill = rng.choice(rest, COLUMNS - len(named), replace=False).tolist()
            tags = dict(strategy=name)
            out.append(dict(id=agent, seed=100 + agent, system=system, columns=named + fill))
            out[-1] |= dict(tags=tags, short=True)
    return out


# One crowd, month by month so a stopped run leaves whole months; resumes from its own log.
def run_crowd(
    log: str, agents: list[dict], minutes: float | None = None, months: int | None = None
) -> None:
    frame, names = universe(), labels()
    stop = time.time() + minutes * 60 if minutes else None
    key = itemgetter("agent", "eom", "card")
    with H.Server("gemma", H.LONG_PROMPTS) as server, H.answers(log, key) as saved:
        done, save = saved
        H.stamp(server, log, (PROMPT, COPYCAT))
        for month in sorted(frame["eom"].unique())[-(months or 0) :]:
            rows = frame[frame["eom"] == month]
            for agent in agents:
                for number, card in enumerate(cards(rows, agent["seed"], month)):
                    if (agent["id"], f"{month:%Y-%m-%d}", number) in done:
                        continue
                    if stop and time.time() > stop:
                        print("stopped at the time budget; rerun resumes here", flush=True)
                        return
                    save(ask(server, agent, card, number, month, names))


# One agent's answer to one card, as the row the log keeps.
def ask(server, agent: dict, card: pd.DataFrame, number: int, month, names: dict) -> dict:
    text, codes = table(card, agent["columns"], names)
    messages = [dict(role="system", content=agent["system"]), dict(role="user", content=text)]
    answer = H.parse(server.chat(messages, schema=schema(codes, agent["short"])))
    by_code = dict(zip(codes, card["permno"].tolist()))
    row = dict(agent=agent["id"], **agent["tags"], eom=f"{month:%Y-%m-%d}")
    row |= dict(card=number, shown=card["permno"].tolist())
    row["picked"] = [int(by_code[c]) for c in codes if c in set(answer.get("buy", []))]
    if agent["short"]:
        shorted = set(answer.get("short", [])) - set(answer.get("buy", []))
        row["shorted"] = [int(by_code[c]) for c in codes if c in shorted]
    row["prompt_sha256"] = hashlib.sha256((agent["system"] + text).encode()).hexdigest()
    return row


# The always-on replay check (honesty.md): 2% of a crowd's saved answers, drawn with the seed,
# asked again live; agreement with the cached answer is reported apart from the replays.
def rerun(log: str, agents: list[dict], share: float = 0.02) -> None:
    frame, names = universe(), labels()
    saved = [json.loads(x) for x in (H.RUNS / f"{log}.jsonl").read_text("utf-8").splitlines()]
    rng = np.random.default_rng(SEED)
    chosen = sorted(rng.choice(len(saved), max(1, int(share * len(saved))), replace=False))
    by_id, key = {a["id"]: a for a in agents}, itemgetter("agent", "eom", "card")
    with H.Server("gemma", H.LONG_PROMPTS) as server, H.answers(f"{log}_rerun", key) as saved_:
        done, save = saved_
        for i in chosen:
            old = saved[i]
            if key(old) in done:
                continue
            agent, month = by_id[old["agent"]], pd.Timestamp(old["eom"])
            card = cards(frame[frame["eom"] == month], agent["seed"], month)[old["card"]]
            row = ask(server, agent, card, old["card"], month, names)
            same_prompt = row["prompt_sha256"] == old["prompt_sha256"]
            save(row | dict(cached=old["picked"], same_prompt=same_prompt))
    rows = [json.loads(x) for x in (H.RUNS / f"{log}_rerun.jsonl").read_text("utf-8").splitlines()]
    same = np.mean([set(r["picked"]) == set(r["cached"]) for r in rows])
    print(f"{log}: {len(rows)} live reruns, {same:.0%} identical to the cached answer")


# The two live crowds; the retail log keeps its name so a stopped run resumes.
def retail(minutes: float | None = None) -> None:
    run_crowd("crowdlab_retail", retail_agents(), minutes)


def copycat(minutes: float | None = None) -> None:
    run_crowd("crowdlab_copycat", copycat_agents(), minutes)


# Memorization check (crowd.md measure 3): 10% of saved cards asked again with every percentile
# moved at random by up to a card's own size of move (1 to 10 points); an agent that reads the card
# should change its picks more as the move grows.
def perturbed(log: str, agents: list[dict], share: float = 0.10) -> None:
    frame, names = universe(), labels()
    saved = [json.loads(x) for x in (H.RUNS / f"{log}.jsonl").read_text("utf-8").splitlines()]
    pick = np.random.default_rng(SEED + 1)
    chosen = sorted(pick.choice(len(saved), max(1, int(share * len(saved))), replace=False))
    by_id, key = {a["id"]: a for a in agents}, itemgetter("agent", "eom", "card")
    with H.Server("gemma", H.LONG_PROMPTS) as server, H.answers(f"{log}_perturbed", key) as io:
        done, save = io
        for i in chosen:
            old = saved[i]
            if key(old) in done:
                continue
            agent, month = by_id[old["agent"]], pd.Timestamp(old["eom"])
            card = cards(frame[frame["eom"] == month], agent["seed"], month)[old["card"]].copy()
            rng = np.random.default_rng([SEED, int(i)])
            size = int(rng.integers(1, 11))
            cols = agent["columns"]
            moves = rng.integers(-size, size + 1, size=(len(card), len(cols)))
            card[cols] = np.clip(card[cols].to_numpy() + moves, 0, 100)
            row = ask(server, agent, card, old["card"], month, names)
            save(row | dict(original=old["picked"], move=size))


# Every shown stock as a row: who saw it, when, and whether they picked it.
def picks(name: str = "crowdlab_retail") -> pd.DataFrame:
    log = H.RUNS / f"{name}.jsonl"
    rows = []
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        chosen, shorted = set(r["picked"]), set(r.get("shorted", []))
        tags = (r.get("persona"), r.get("info_set"), r.get("strategy"))
        for permno in r["shown"]:
            rows.append((r["agent"], *tags, r["eom"], permno, permno in chosen, permno in shorted))
    cols = ["agent", "persona", "info_set", "strategy", "eom", "permno", "picked", "shorted"]
    out = pd.DataFrame(rows, columns=cols)
    out["eom"] = pd.to_datetime(out["eom"])
    return out


if __name__ == "__main__":
    task, *rest = sys.argv[1:] or ["retail"]
    if task == "perturbed":
        perturbed("crowdlab_retail", retail_agents())
    elif task == "quick":
        # Finals day (crowd.md, level 1): a few retail agents on the newest months, in a budget.
        env, everyone = os.environ, retail_agents()
        n = int(env.get("FIAM_AGENTS", 6))
        agents = everyone[:: max(1, len(everyone) // n)][:n]
        months = int(env.get("FIAM_MONTHS", 1))
        run_crowd("crowdlab_quick", agents, float(env.get("FIAM_MINUTES", 20)), months)
    elif task == "rerun":
        crowd = rest[0] if rest else "retail"
        agents = retail_agents() if crowd == "retail" else copycat_agents()
        rerun(f"crowdlab_{crowd}", agents)
    else:
        {"retail": retail, "copycat": copycat}[task](float(rest[0]) if rest else None)
