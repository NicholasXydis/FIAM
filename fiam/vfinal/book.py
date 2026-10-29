# One book on 2021-2026 through fiam.vfinal's daily book and ledger.

import json
import time

import pandas as pd

from fiam.vfinal import config, daily_book
from fiam.vfinal.construct import formation
from fiam.vfinal.execution import costs, hook

# The daily book's frames each run writes.
PARTS = ("daily", "positions", "trades", "events", "compliance", "ledger")


# A file written whole, so a stopped job never leaves half of one.
def write(path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".tmp")
    part.write_text(json.dumps(body, indent=1, default=str))
    part.replace(path)


# Every name the book may trade: $3bn and up at some formation.
def universe(world) -> set:
    exp = world.m["exp"]
    pool = exp[exp["eom"].isin(world.eoms) & exp["long_ok"] & (exp["me"] >= 3000)]
    return set(pool["permno"].astype(int))


# A scaled book's core targets, from its core book's own folder.
def core_targets(name: str) -> dict:
    t = pd.read_parquet(config.folder(name) / "targets.parquet")
    return {pd.Timestamp(T): g.set_index("permno")["core"] for T, g in t.groupby("T")}


# One book end to end: formations, the daily book, its frames.
def run(name: str, end=config.END) -> dict:
    r = config.RUNS[name]
    out = config.folder(name)
    out.mkdir(parents=True, exist_ok=True)
    (out / "LABEL.txt").write_text(config.LABEL)
    t0 = time.time()
    ov = r.overlay
    world = formation.World(r.policy, solves=not ov.scaled)
    core = core_targets(ov.core) if ov.scaled else None
    law = costs.Law(world.frames, world)
    h = hook.Hook(world, r, law, core)
    names = universe(world) | ({int(p) for c in core.values() for p in c.index} if core else set())
    start = world.signal[world.eoms[0]]
    result = daily_book.run({}, start, end, unsealed=True, strict=False, costs=law.costs,
                            borrow=law.borrow, hook=h, permnos=sorted(names))  # fmt: skip
    for part in PARTS:
        getattr(result, part).to_parquet(out / f"{part}.parquet")
    h.target_frame().to_parquet(out / "targets.parquet", index=False)
    write(out / "formations.json", {"run": r.as_dict(), "formations": h.logs})
    minutes = (time.time() - t0) / 60
    write(config.LOGS / f"timing_{name}.json", {"run": name, "minutes": minutes})
    return {"run": name, "minutes": minutes}


# A finished book's frames from its folder.
def tables(name: str) -> dict:
    return {p: pd.read_parquet(config.folder(name) / f"{p}.parquet") for p in PARTS}
