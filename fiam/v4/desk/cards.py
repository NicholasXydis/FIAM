# The desk's masked card: numbers only, no name, ticker, sector or date.

import hashlib
import json

import pandas as pd

# Exposures shown as percentiles in the universe (step 8 rules).
SHOWN = ("size", "value", "momentum", "quality", "welch", "liquidity", "crowding")


# A value's percentile in its column, rounded to 2 decimals.
def pct(col: pd.Series, name) -> float:
    return round(float(col.rank(pct=True).get(name, 0.5)), 2)


# One held name's card from the formation frame and today's triggers.
def card(name, w: pd.Series, alpha: pd.Series, x: pd.DataFrame, trig: dict, book: dict,
         items=()) -> dict:  # fmt: skip
    side = 1 if w[name] > 0 else -1
    same = w[w * side > 0].abs()
    out = {"side": "long" if side > 0 else "short",
           "weight_pct_in_side": pct(same, name),
           "alpha_pct_in_side": pct((alpha * side).reindex(same.index), name),
           "confidence_tercile": int(x["confidence_tercile"].get(name, 2))
           if "confidence_tercile" in x else 2}  # fmt: skip
    out |= {f"{k}_pct": pct(x[k], name) for k in SHOWN if k in x}
    out["triggers"] = {k: v for k, v in trig.items() if v is not None}
    out["red_flag_items_90d"] = sorted(set(str(i) for i in items))
    out["book"] = {k: round(float(v), 2) for k, v in book.items()}
    return out


# PLAN §10.1's cache key: model, build, server, messages, schema, draws.
def key(model_sha: str, build: str, server_args, messages, schema, temperature, seed, tokens):
    parts = [model_sha, build, json.dumps(list(server_args)),
             json.dumps(messages, sort_keys=True), json.dumps(schema, sort_keys=True),
             str(temperature), str(seed), str(tokens)]  # fmt: skip
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
