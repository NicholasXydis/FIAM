# SYY-10, the headline composite (PLAN §7.1, the step 4 checklist).

import pandas as pd

from fiam.v4 import data, ranks, universe

# The ten Stambaugh-Yu-Yuan (2012) anomalies and signs; CHS is absent.
PARTS = {
    "o_score": -1, "chcsho_12m": -1, "eqnetis_at": -1, "oaccruals_at": -1, "noa_at": -1,
    "ret_12_1": 1, "gp_at": 1, "at_gr1": -1, "niq_at": 1, "ppeinv_gr1a": -1,
}  # fmt: skip
# A stock needs at least 5 of the 10 to carry the composite.
MIN_PARTS = 5


# The composite of one month's parts: mean of sign x rank, missing 0.
def combine(parts: pd.DataFrame) -> pd.DataFrame:
    signed = pd.DataFrame(
        {c: s * ranks.unit_rank(parts[c]) for c, s in PARTS.items()}, index=parts.index
    )
    out = pd.DataFrame(index=parts.index)
    out["present"] = signed.notna().sum(axis=1)
    out["raw"] = signed.fillna(0.0).sum(axis=1) / len(PARTS)
    out.loc[out["present"] < MIN_PARTS, "raw"] = float("nan")
    return out


# SYY-10 at one formation: ranked over the panel, then the universe.
def at(eom) -> pd.DataFrame:
    eom = pd.Timestamp(eom) + pd.offsets.MonthEnd(0)
    p = data.table("panel", list(PARTS), where={"eom": (eom, eom)}).set_index("permno")
    data.assert_public_by(p["first_close"], data.eom_session([eom]).iloc[0], "SYY-10 rows")
    out = combine(p[list(PARTS)])
    m = universe.members(eom).set_index("permno")
    inside = out.index.isin(m.index[m["new_long"]])
    out["in_universe"] = inside
    out["syy"] = float("nan")
    out.loc[inside, "syy"] = ranks.unit_rank(out.loc[inside, "raw"]).to_numpy()
    return out.reset_index().assign(eom=eom)


# SYY-10 for every month end in a span, one frame.
def history(start, end) -> pd.DataFrame:
    return pd.concat([at(e) for e in data.month_ends(start, end)], ignore_index=True)
