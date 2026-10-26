# Step 8 in stages: events, cards, answer, arms, decide (step 8 rules).

import contextlib
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from fiam.agents import harness
from fiam.v4 import daily_book, data, final, gates
from fiam.v4.construct import book, costs, exam, execution, risk, settings
from fiam.v4.desk import after, agents, arms, cards, decide, hook, triggers

OUT = gates.ROOT / "out" / "v4" / "desk"
STAGES = ("events", "cards", "answer", "cutoff", "arms", "decide")
# The stage each one needs first; answers come back through the cache.
NEEDS = {"cards": "events", "answer": "cards", "cutoff": "cards", "arms": "cards",
         "decide": "arms"}  # fmt: skip
# Arms replayed at once, each worker holding one context (about 7 GB).
WORKERS = 2
# The model, its pinned build and server, and the declared cutoff.
MODEL, BUILD, CUTOFF = "gemma", "b11132", "2025-01"
META = dict(model_sha=harness.MODELS[MODEL][2], build=BUILD, server_args=harness.LONG_PROMPTS,
            temperature=harness.TEMPERATURE, seed=harness.SEED, tokens=2048,
            cutoff=CUTOFF)  # fmt: skip
# The time-cutoff model (§10.5): same cards, same schema, reported only.
CUTOFF_META = META | dict(model_sha=harness.MODELS["pythia"][2], cutoff="2020-12")
# The memory gate's draws (step 8 rules).
MEMORY_CARDS, MEMORY_SEED, OTHERS_SEED, OTHERS = 200, 20261901, 20261902, 9
# The exam's commit, pinned in exam.py; None reads this commit's.
EXAM_AT = exam.EXAM_AT
# The exam's window (2017-2020), or the finals' once unsealed (--final).
FINAL = False
# Red-flag 8-K items on a card: those public in the 90 days to t.
FLAG_DAYS = pd.Timedelta(days=90)
# The earnings variance: announcement days in the year before t.
EARN_YEAR = pd.DateOffset(years=1)


# The exam's chosen design: its key, forecast column and held styles.
def chosen(head: str) -> tuple:
    designs = json.loads((book.OUT / f"exam_designs_{EXAM_AT or head[:12]}.json").read_text())
    k = int(designs["winner"])
    k = 1 if k == 3 else k
    z, _, neutral = exam.DESIGNS[k]
    return k, z, neutral


# A file of this stage at this commit; the finals' carry their prefix.
def path(stage: str, head: str, suffix: str = "json"):
    return OUT / f"{'final_' if FINAL else ''}{stage}_{head[:12]}.{suffix}"


# The window's last day and the first day its returns are read from.
def span() -> tuple:
    return (final.END, "2020-01-01") if FINAL else (exam.END, "2016-12-01")


# Arm A0's plans, days and positions: the exam's run, or the final one.
def a0_files(head: str, k: int) -> tuple:
    if FINAL:
        return tuple(final.path(f"{part}_{k}", head, ext)
                     for part, ext in (("plans", "pkl"), ("daily", "parquet"),
                                       ("positions", "parquet")))  # fmt: skip
    tag = f"{k}_{EXAM_AT or head[:12]}"
    return tuple(book.OUT / f"exam_{part}_{tag}.{ext}"
                 for part, ext in (("plans", "pkl"), ("daily", "parquet"),
                                   ("positions", "parquet")))  # fmt: skip


# The forecasts the window's book traded on.
def forecasts(head: str) -> pd.DataFrame:
    return pd.read_parquet(final.path("forecasts", head, "parquet")) if FINAL else book.forecasts()


# Arm A0 is the exam's (or the final) run of the design: its events.
def events(head: str) -> dict:
    k, _, _ = chosen(head)
    plans, days, held = a0_files(head, k)
    with plans.open("rb") as fh:
        blob = pickle.load(fh)
    daily = pd.read_parquet(days)
    pos = pd.read_parquet(held)
    OUT.mkdir(parents=True, exist_ok=True)
    with path("a0", head, "pkl").open("wb") as fh:
        pickle.dump(blob, fh)
    daily.to_parquet(path("a0_daily", head, "parquet"))
    pos.to_parquet(path("a0_positions", head, "parquet"))
    end, first = span()
    ids = sorted(forecasts(head)["permno"].unique())
    returns = risk.daily(ids, first, end)
    # 2026's days use the raw dsf: δ's day needs the month's end (M4).
    late = risk.late(ids, end)
    if len(late):
        returns = pd.concat([returns[returns.index <= data.CRSP_END], late])
    found = scan(daily, pos, blob["kept"], returns)
    keyed = {f"{d:%Y-%m-%d}|{p}": t for (d, p), t in found.items()}
    return {"design": k, "events": len(found), "found": keyed}


# Every close's triggers on the names A0 holds after that close.
def scan(daily: pd.DataFrame, pos: pd.DataFrame, kept: dict, returns: pd.DataFrame) -> dict:
    cal = data.table("earnings_calendar", ["projected"])
    sessions = data.calendar().index
    end = span()[0]
    iv = data.table("options_daily", ["iv_CATM"],
                    where={"date": (pd.Timestamp("2000-01-01"), end)})  # fmt: skip
    vol = iv.pivot_table(index="first_close", columns="permno", values="iv_CATM")
    jumps = triggers.Jumps(vol.where(vol > 0))
    # After the options data ends, 21-session realised vol stands in.
    realised = triggers.Jumps(returns.rolling(21).std()) if end > triggers.OPTIONS_END else None
    out, starts = {}, sorted(kept)
    for d in daily.index:
        live = [s for s in starts if s <= d]
        if not live:
            continue
        x, w = kept[live[-1]], weights(pos, daily, d)
        found: dict = {}
        for p, days in triggers.earnings(w.index, d, cal, sessions).items():
            found.setdefault(p, {})["earnings"] = days
        sigma = x["sigma_d"].reindex(w.index).fillna(x["sigma_d"].median())
        if d in returns.index:
            for p, size in triggers.losses(w, returns.loc[d], sigma).items():
                found.setdefault(p, {})["loss"] = size
        late = realised is not None and d > triggers.OPTIONS_END
        for p, size in (realised if late else jumps).at(d, w.index).items():
            found.setdefault(p, {})["vol_jump"] = size
        out |= {(d, p): t for p, t in found.items()}
    return out


# Monthly median squared 2-day excess move on last year's 2.02 8-Ks.
def earnings_var(returns: pd.DataFrame) -> pd.Series:
    ev = data.table("events", ["earnings_8k", "amendment"])
    ev = ev[ev["earnings_8k"].astype(bool) & ~ev["amendment"].astype(bool)]
    ev = ev.drop_duplicates(["permno", "first_close"])
    two = (1 + returns) * (1 + returns.shift(1)) - 1
    mkt = data.market_daily(returns.index)
    excess = two.sub((1 + mkt) * (1 + mkt.shift(1)) - 1, axis=0)
    ev = ev[ev["permno"].isin(excess.columns) & ev["first_close"].isin(excess.index)]
    rows = excess.index.get_indexer(ev["first_close"])
    cols = excess.columns.get_indexer(ev["permno"])
    moves = pd.Series(excess.to_numpy()[rows, cols] ** 2, index=ev["first_close"].to_numpy())
    moves = moves.dropna().sort_index()
    months = pd.date_range(returns.index[0], span()[0], freq="MS")
    out = {m: float(moves[(moves.index < m) & (moves.index >= m - EARN_YEAR)].median())
           for m in months}  # fmt: skip
    return pd.Series(out)


# A trigger's extra variance over the next month (step 8 rules, b).
def extra_var(trig: dict, spec: float, earn: float) -> float:
    v = earn if "earnings" in trig else 0.0
    if "vol_jump" in trig:
        v += spec * (np.exp(2 * trig["vol_jump"]) - 1)
    if "loss" in trig:
        v += spec * max((trig["loss"] / 3) ** 2 - 1, 0.0)
    return float(v)


# Whether a shrink to m of name p on day d passes the cost gate.
def passes(m: float, d, p, trig: dict, kept: dict, pos, daily, lam: float, earn) -> bool:
    _, x = frame_at(kept, d)
    w = weights(pos, daily, d).get(p, 0.0)
    if p not in x.index or w == 0.0:
        return False
    row, nav = x.loc[[p]], float(daily.loc[d, "nav"])
    v = extra_var(trig, float(x.loc[p, "spec"]), float(earn.get(d.to_period("M").start_time, 0)))
    # A shrink trades toward zero: a sale on a long, a purchase on a short.
    cost = lambda t: costs.share_of_nav(np.array([-np.sign(w) * t]), row, nav)  # noqa: E731
    return after.worth(w, m, v, lam, cost)


# The frame in force on a day: the latest formation's on or before it.
def frame_at(kept: dict, d):
    start = max(k for k in kept if k <= d)
    return start, kept[start]


# The book's weights at a close from A0's saved positions and NAV.
def weights(pos: pd.DataFrame, daily: pd.DataFrame, d) -> pd.Series:
    g = pos[pos["date"] == d].set_index("permno")["value"]
    w = g / float(daily.loc[d, "nav"])
    return w[w.abs() > 1e-9]


# The cost gate's inputs: lambda and each month's earnings variance.
def gate_inputs(head: str) -> tuple:
    lam = json.loads(settings.SETTINGS.read_bytes())["settings"]["risk_lambda"]
    path_ev = path("earn_var", head, "parquet")
    if not path_ev.exists():
        ids, end = sorted(forecasts(head)["permno"].unique()), span()[0]
        start = "2019-06-01" if FINAL else "2015-06-01"
        earnings_var(risk.daily(ids, start, end)).to_frame("v").to_parquet(path_ev)
    return lam, pd.read_parquet(path_ev)["v"]


# Each event that could act gets a masked card; the memory questions.
def build_cards(head: str) -> dict:
    found = json.loads(path("events", head).read_text())["found"]
    with path("a0", head, "pkl").open("rb") as fh:
        kept = pickle.load(fh)["kept"]
    daily = pd.read_parquet(path("a0_daily", head, "parquet"))
    pos = pd.read_parquet(path("a0_positions", head, "parquet"))
    lam, earn = gate_inputs(head)
    flags = data.table("events", ["red_flag", "item"])
    flags = flags[flags["red_flag"].astype(bool)]
    rows, gated_out = [], 0
    for event, trig in found.items():
        day, permno = event.split("|")
        d, p = pd.Timestamp(day), int(permno)
        # Asked only where some shrink could pass (the mildest passes most).
        could = [m for m in agents.SHRINKS if m < 1]
        if not any(passes(m, d, p, trig, kept, pos, daily, lam, earn) for m in could):
            gated_out += 1
            continue
        start, x = frame_at(kept, d)
        w = weights(pos, daily, d)
        stats = {"gross": daily.loc[d, "gross"], "net": daily.loc[d, "net"],
                 "beta": float((w * x["welch"].reindex(w.index).fillna(1.0)).sum())}  # fmt: skip
        mine = flags[(flags["permno"] == p) & (flags["first_close"] <= d)
                     & (flags["first_close"] > d - FLAG_DAYS)]  # fmt: skip
        c = cards.card(p, w, x["alpha"], x, trig, stats, mine["item"].tolist())
        rows.append({"day": day, "permno": p, "formed": f"{start:%Y-%m-%d}", "card": c})
    memory = questions(rows)
    with path("cards", head, "jsonl").open("w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    with path("memory", head, "jsonl").open("w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in memory)
    return {"cards": len(rows), "gated_before_asking": gated_out, "memory_questions": len(memory)}


# The memory gate: 200 cards by year, the company among 10, month of 12.
def questions(rows: list) -> list:
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    frame["year"] = frame["day"].str[:4]
    rng = np.random.default_rng(MEMORY_SEED)
    per = MEMORY_CARDS // frame["year"].nunique()
    picked = pd.concat([g.iloc[rng.permutation(len(g))[:per]] for _, g in frame.groupby("year")])
    others = np.random.default_rng(OTHERS_SEED)
    out = []
    for r in picked.to_dict("records"):
        eom = data.month_end_at(pd.Timestamp(r["day"]))
        names = data.table("panel", ["company_name", "gics"], purpose="label",
                           where={"eom": (eom, eom)}).set_index("permno")  # fmt: skip
        sector = str(names["gics"].get(r["permno"], ""))[:2]
        same = names["gics"].astype("string").str[:2] == sector
        pool = names[same].index.difference([r["permno"]])
        picks = list(others.choice(pool, size=min(OTHERS, len(pool)), replace=False))
        options = list(names.loc[[r["permno"], *picks], "company_name"].astype(str))
        options = [options[i] for i in others.permutation(len(options))]
        months = [f"{r['year']}-{m:02d}" for m in range(1, 13)]
        truth = {"company": str(names.loc[r["permno"], "company_name"]), "month": r["day"][:7]}
        out.append({"day": r["day"], "permno": r["permno"], "formed": r["formed"],
                    "card": r["card"], "truth": truth, "company": options,
                    "months": months})  # fmt: skip
    return out


# The memory gate's two questions on one card, each a closed choice.
def memory_messages(q: dict) -> list:
    ask = [("company", "Which of these companies does this card describe?", q["company"]),
           ("month", "In which month is this card dated?", q["months"])]  # fmt: skip
    return [([{"role": "user", "content": json.dumps({"card": q["card"], "question": text,
                                                         "options": opts}, sort_keys=True)}],
             {"type": "object", "required": ["choice"],
              "properties": {"choice": {"type": "string", "enum": opts}}}, kind)
            for kind, text, opts in ask]  # fmt: skip


# A chat model as the desk calls it: messages and a schema, a dict back.
class Model:
    # The running llama.cpp server and where it runs, for the log.
    def __init__(self, server):
        self.server, self.where = server, harness.REMOTE or harness.machine()

    # One answer in the schema's JSON.
    def chat(self, messages: list, schema: dict) -> dict:
        return harness.parse(self.server.chat(messages, schema=schema))


# One machine's part of the cards and memory questions, cached by key.
def answer(head: str, part: tuple = (1, 1)) -> dict:
    i, n = part
    rows = [json.loads(x) for x in path("cards", head, "jsonl").read_text().splitlines()]
    memory = [json.loads(x) for x in path("memory", head, "jsonl").read_text().splitlines()]
    rows, memory = rows[i - 1 :: n], memory[i - 1 :: n]
    with harness.answers(f"desk_v4_part{i}of{n}", key=lambda r: r["key"]) as (done, save):
        with harness.Server(MODEL, extra=harness.LONG_PROMPTS) as server:
            desk = agents.Desk(done, META, Model(server), save)
            for r in rows:
                desk.decide(r["card"], r["formed"])
            for q in memory:
                for messages, schema, _ in memory_messages(q):
                    desk.ask(messages, schema, q["formed"])
        return {"answers": len(done)}


# The time-cutoff model's first answer on one machine's part of cards.
def cutoff(head: str, part: tuple = (1, 1)) -> dict:
    i, n = part
    rows = [json.loads(x) for x in path("cards", head, "jsonl").read_text().splitlines()]
    with harness.answers(f"cutoff_v4_part{i}of{n}", key=lambda r: r["key"]) as (done, save):
        with harness.Server("pythia") as server:
            desk = agents.Desk(done, CUTOFF_META, Model(server), save)
            for r in rows[i - 1 :: n]:
                desk.ask(agents.sizing(r["card"]), agents.SIZING, r["formed"])
        return {"answers": len(done)}


# How often the cutoff model's shrink equals Gemma's, where both answer.
def agreement(rows: list, desk: agents.Desk) -> dict | None:
    files = sorted(harness.RUNS.glob("cutoff_v4*.jsonl"))
    lines = [x for f in files for x in f.read_text().splitlines()]
    if not lines:
        return None
    old = agents.Desk({r["key"]: r for r in map(json.loads, lines)}, CUTOFF_META)
    same = {"proposal": [], "final": []}
    for r in rows:
        theirs = old.ask(agents.sizing(r["card"]), agents.SIZING, r["formed"])
        _, said = desk.decide(r["card"], r["formed"])
        if theirs is None or not said:
            continue
        for k in same:
            same[k].append(theirs.get("shrink") == said[k].get("shrink"))
    return {
        "cards": len(same["final"]),
        "missing": len(old.missing),
        **{f"same_as_{k}": float(np.mean(v)) if v else None for k, v in same.items()},
    }


# All machines' answers replayed by key; a missing one stops the build.
def replay() -> agents.Desk:
    files = sorted(harness.RUNS.glob("desk_v4*.jsonl"))
    lines = [x for f in files for x in f.read_text().splitlines()]
    return agents.Desk({r["key"]: r for r in map(json.loads, lines)}, META)


# An arm's shrinks through the cost gate (step 8 rules, option b).
def gated(plan: dict, found: dict, kept: dict, pos, daily, lam: float, earn) -> dict:
    return {(d, p): m for (d, p), m in plan.items()
            if passes(m, d, p, found.get((d, p), {}), kept, pos, daily, lam, earn)}  # fmt: skip


# Each arm's shrinks through the gate, then replayed two at a time.
def run_arms(head: str, seeds=arms.PLACEBO_SEEDS) -> dict:
    with path("a0", head, "pkl").open("rb") as fh:
        kept = pickle.load(fh)["kept"]
    found = {(pd.Timestamp(e.split("|")[0]), int(e.split("|")[1])): t
             for e, t in json.loads(path("events", head).read_text())["found"].items()}  # fmt: skip
    daily = pd.read_parquet(path("a0_daily", head, "parquet"))
    pos = pd.read_parquet(path("a0_positions", head, "parquet"))
    desk = replay()
    rows = [json.loads(x) for x in path("cards", head, "jsonl").read_text().splitlines()]
    agent = {}
    for r in rows:
        shrink, _ = desk.decide(r["card"], r["formed"])
        agent[(pd.Timestamp(r["day"]), int(r["permno"]))] = shrink
    if desk.missing:
        raise SystemExit(f"{len(desk.missing)} answers missing: run the answer stage on Windows")
    lam, earn = gate_inputs(head)
    # A0 replayed with no shrinks must equal A0 day for day (a test).
    plans = {"A0_replay": {}, "A1": arms.shrinks(found, "A1"),
             "A2": arms.shrinks(found, "A2", agent)}  # fmt: skip
    plans |= {f"P1_{s}": arms.shrinks(found, "P1", agent, seed=s) for s in seeds}
    plans = {arm: gated(plan, found, kept, pos, daily, lam, earn) for arm, plan in plans.items()}
    names = list(plans)
    chunks = [names[i::WORKERS] for i in range(WORKERS)]
    with ProcessPoolExecutor(WORKERS) as pool:
        jobs = [pool.submit(replay_arms, head, {a: plans[a] for a in c}, FINAL)
                for c in chunks if c]  # fmt: skip
        out = {}
        for job in jobs:
            out |= job.result()
    return out


# The window's context and the switches its A0 ran with.
def context(head: str, z: str, neutral) -> tuple:
    if not FINAL:
        return book.Context(z=z, neutral=neutral), {}, False
    s = json.loads(settings.SETTINGS.read_bytes())
    ctx = final.Context(forecasts(head), float(s["alpha_scale"]), z, neutral)
    ran = json.loads(final.path("book", head).read_text())
    events = exam.overlay_events(final.FIRST, final.END) if ran["overlays"] else {}
    return ctx, {side: exam.by_day(events[side]) for side in ran["overlays"]}, ran["brake"]


# One worker: its window, its context once, then its arms.
def replay_arms(head: str, plans: dict, final_run: bool = False) -> dict:
    global FINAL
    FINAL = final_run
    with final.opened() if FINAL else contextlib.nullcontext():
        return replay_in(head, plans)


# The arms through the engine with A0's plans, costs and switches.
def replay_in(head: str, plans: dict) -> dict:
    k, z, neutral = chosen(head)
    with a0_files(head, k)[0].open("rb") as fh:
        blob = pickle.load(fh)
    made, hooks = blob["made"], blob["hooks"]
    ctx, overlays, brake = context(head, z, neutral)
    end = span()[0]
    ids = sorted(ctx.f["permno"].unique())
    T0 = data.eom_session([ctx.months[0]]).iloc[0]
    watch = execution.SqueezeWatch(ids, T0, end)
    trigger = execution.TriggerBeta(ctx.returns, ctx.late)
    holders = {e: pd.Series(dtype=float) for e in ctx.months}
    out = {}
    for arm, plan in plans.items():
        act = hook.Arm(made, plan, watch, trigger, overlays, brake)
        result = daily_book.run(holders, T0, end, costs=hooks.costs, borrow=hooks.borrow,
                                hook=act, permnos=ids, unsealed=FINAL, strict=False)  # fmt: skip
        days = result.daily[["nav", "ret", "rf", "cost", "borrow"]]
        days.to_parquet(path(f"arm_{arm}", head, "parquet"))
        # On the finals A1 and A2 keep every table: either may be the book.
        if FINAL and arm in ("A1", "A2"):
            for part in ("daily", "positions", "trades", "events", "ledger", "compliance"):
                getattr(result, part).to_parquet(path(f"book_{arm}_{part}", head, "parquet"))
        out[arm] = {"shrinks": len(plan), "breach_days": int(len(daily_book.breaches(result)))}
        data._CACHE.clear()
    return out


# The decision: each arm's IR, paired s.e., the memory gate, the arm.
def decision(head: str) -> dict:
    days = {"A0": pd.read_parquet(path("a0_daily", head, "parquet"))}
    prefix = "final_arm_" if FINAL else "arm_"
    for f in OUT.glob(f"{prefix}*_{head[:12]}.parquet"):
        days[f.stem.removeprefix(prefix).removesuffix(f"_{head[:12]}")] = pd.read_parquet(f)
    replayed = days.pop("A0_replay", None)
    same = replayed is not None and replayed["ret"].equals(days["A0"]["ret"])
    after = "2020-12" if FINAL else "2017-01"
    irs = {k: exam.scores(v, after)["ir"] for k, v in days.items()}
    active = {k: (v["ret"] - v["rf"] - exam.PREMIUM / 252).to_numpy() for k, v in days.items()}
    pairs = {f"{a}-{b}": {"diff": irs[a] - irs[b],
                          "se_daily": decide.paired_se(active[a], active[b])}
             for a, b in (("A2", "A1"), ("A2", "A0"), ("A1", "A0"))}  # fmt: skip
    desk = replay()
    memory = [json.loads(x) for x in path("memory", head, "jsonl").read_text().splitlines()]
    hits = {"company": 0, "month": 0}
    for q in memory:
        for messages, schema, kind in memory_messages(q):
            got = desk.ask(messages, schema, q["formed"]) or {}
            hits[kind] += got.get("choice") == q["truth"][kind]
    if desk.missing:
        raise SystemExit(f"{len(desk.missing)} memory answers missing: run them on Windows")
    gate = decide.memory_gate(len(memory), hits["company"], hits["month"])
    rows = [json.loads(x) for x in path("cards", head, "jsonl").read_text().splitlines()]
    placebo = [v for k, v in irs.items() if k.startswith("P1_")]
    return {"irs": {k: v for k, v in irs.items() if not k.startswith("P1_")}, "pairs": pairs,
            "placebo": {"n": len(placebo), "mean": float(np.mean(placebo)) if placebo else None,
                        "p05_p95": list(np.quantile(placebo, [0.05, 0.95])) if placebo else None},
            "memory_gate": gate, "a0_replay_identical": bool(same),
            "cutoff_agreement": agreement(rows, desk)} | headline(irs, gate)  # fmt: skip


# The exam window decides the arm; the finals report the frozen one.
def headline(irs: dict, gate: dict) -> dict:
    if not FINAL:
        return {"headline": decide.headline(irs, gate["passes"])}
    frozen = json.loads((gates.ROOT / "frozen" / "v4" / "config.json").read_text())
    return {"frozen_headline": frozen["headline"], "reported_only": True}


# python -m fiam.v4.desk.run events | cards | answer | arms | decide
if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage not in STAGES:
        raise SystemExit(f"name a stage: {' | '.join(STAGES)}")
    FINAL = "--final" in sys.argv
    head = gates.commit()
    # Step 8 runs on real data only once its rules are committed.
    if "## Step 8 rules" not in gates.PROTOCOL.read_text():
        raise SystemExit("commit the step 8 rules into the protocol first")
    # The answer and cutoff stages split the cards by machine: --part 1/2.
    part = sys.argv[sys.argv.index("--part") + 1] if "--part" in sys.argv else "1/1"
    i, n = (int(v) for v in part.split("/"))
    split = stage in ("answer", "cutoff")
    target = path(f"{stage}_part{i}of{n}" if split else stage, head)
    if target.exists():
        raise SystemExit(f"{target.name} exists: each stage runs once per commit")
    if stage == "arms" and not list(OUT.glob(path("answer_part*", head).name)):
        raise SystemExit("answer every part first at this commit")
    if stage in NEEDS and not path(NEEDS[stage], head).exists():
        raise SystemExit(f"run the {NEEDS[stage]} stage first at this commit")
    work = {"events": events, "cards": build_cards, "arms": run_arms, "decide": decision,
            "answer": lambda h: answer(h, (i, n)),
            "cutoff": lambda h: cutoff(h, (i, n))}  # fmt: skip
    # The finals' stages read 2021-2026, so only after the unseal.
    with final.opened() if FINAL else contextlib.nullcontext():
        out = {"stage": stage, "stamp": exam.stamp(head, settings.SETTINGS.read_bytes())}
        out |= work[stage](head) | {"window": "final" if FINAL else "exam"}
    OUT.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("stamp", "found")},
                     indent=1, default=str))  # fmt: skip
    sys.exit(0)
