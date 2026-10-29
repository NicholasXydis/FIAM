# Opens the finals window past the cutoff, with the pinned SUE choice.

import json
from contextlib import contextmanager

import pandas as pd

from fiam.vfinal import clock, data, gates, sources
from fiam.vfinal.forecast import dataset, grid

# The finals' last formation and the window's last day.
LAST, END = pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-31")
# Yearly refits each January keep the 2019-2020 choices as they are.
YEARS, SUE_YEARS = range(2021, 2027), range(2016, 2027)
# The SUE model's cell, chosen on 2019-2020 data and pinned in a file.
CHOICES = gates.ROOT / "frozen" / "vfinal" / "pinned" / "validate_9f47207c568b.json"


# Opens the windows to the finals' end once the gate is open; restores.
@contextmanager
def opened():
    if not sources.unsealed():
        raise SystemExit("sealed: rows public after 2020 stay closed, see uv run fiam verify")
    keep = (clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST, grid.SUE_YEARS, grid.RETURN_YEARS)
    clock.LAST_LABEL_DAY = gates.LAST_DAY = END
    dataset.LAST, grid.SUE_YEARS, grid.RETURN_YEARS = LAST, SUE_YEARS, YEARS
    data._CACHE.clear()
    try:
        yield
    finally:
        clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST = keep[:3]
        grid.SUE_YEARS, grid.RETURN_YEARS = keep[3:]
        data._CACHE.clear()


# The models' choices, read from the pinned file, never chosen again.
def choices() -> dict:
    v = json.loads(CHOICES.read_text())["validate"]
    sue = {s: {"passes": r["passes"], "chosen": r["chosen"]} for s, r in v["sue_model"].items()}
    return {"chosen": v["chosen"], "members": v["members"] | {"sue": sue}}
