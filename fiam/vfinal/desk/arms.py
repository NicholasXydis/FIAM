# The four arms: no desk, set map, agent, random placebo.

import numpy as np
import pandas as pd

# Arm A1's set map; several triggers multiply, never below 0.25.
FIXED = {"earnings": 0.75, "vol_jump": 0.5, "loss": 0.5}
FLOOR = 0.25
# Arm P1's seeds.
PLACEBO_SEEDS = range(20261800, 20261900)


# Arm A1: the product of the triggers' multipliers, floored at 0.25.
def fixed(triggers: dict) -> float:
    m = float(np.prod([FIXED[k] for k in triggers if k in FIXED])) if triggers else 1.0
    return max(m, FLOOR)


# Arm P1: A2's multipliers shuffled over the same trigger events.
def placebo(events: list, agent: dict, seed: int) -> dict:
    values = np.array([agent.get(e, 1.0) for e in events], dtype=float)
    shuffled = np.random.default_rng(seed).permutation(values)
    return {e: float(v) for e, v in zip(events, shuffled) if v < 1.0}


# An arm's shrinks by trigger event, (day, permno) -> multiplier.
def shrinks(events: dict, arm: str, agent: dict | None = None, seed: int | None = None) -> dict:
    if arm == "A0":
        return {}
    if arm == "A1":
        out = {e: fixed(t) for e, t in events.items()}
        return {e: m for e, m in out.items() if m < 1.0}
    if arm == "A2":
        return {e: m for e, m in (agent or {}).items() if m < 1.0}
    if arm == "P1":
        return placebo(sorted(events), agent or {}, seed)
    raise ValueError(f"unknown arm {arm}")


# One arm's shrinks of one close, as the hook will apply them.
def today(plan: dict, d) -> dict:
    d = pd.Timestamp(d)
    return {p: m for (day, p), m in plan.items() if pd.Timestamp(day) == d}
