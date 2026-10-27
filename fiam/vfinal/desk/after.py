# Code after the desk: the cost gate and enforce_constraints (PDF p9).

import pandas as pd

# A shrink that cannot be placed stays as cash; a weight is never added.
SIDES = (1, -1)


# A shrink only where the risk it saves beats its round-trip cost.
def worth(w: float, shrink: float, var: float, risk_lambda: float, cost) -> bool:
    saving = risk_lambda * (1 - shrink**2) * w**2 * var
    return saving > 2 * cost(abs(1 - shrink) * abs(w))


# Shrinks applied, freed gross to the same side's others within caps.
def enforce(w: pd.Series, shrinks: dict, caps: pd.Series) -> tuple:
    out = w.copy()
    # A name gone from the book since its trigger is skipped, logged.
    gone = {n: s for n, s in shrinks.items() if n not in w.index}
    shrinks = {n: s for n, s in shrinks.items() if n in w.index}
    for name, s in shrinks.items():
        out[name] = out[name] * s
    unplaced = {}
    for side in SIDES:
        mine = out.index[out * side > 0]
        freed = float((w[mine].abs() - out[mine].abs()).sum())
        others = mine.difference(pd.Index(list(shrinks)))
        # Pro rata to the others' weights, never past a cap; a few passes.
        for _ in range(5):
            room = (caps.reindex(others).fillna(0.0) - out[others].abs()).clip(lower=0.0)
            open_ = others[room > 1e-12]
            if freed <= 1e-12 or len(open_) == 0:
                break
            share = out[open_].abs() / float(out[open_].abs().sum())
            add = (share * freed).clip(upper=room[open_])
            out[open_] = out[open_] + side * add
            freed -= float(add.sum())
        unplaced[side] = max(freed, 0.0)
    return out, unplaced | ({"gone": gone} if gone else {})
