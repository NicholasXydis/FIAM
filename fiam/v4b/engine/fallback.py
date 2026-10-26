# The zero-alpha fallback book: cheapest compliant neutral book (R§5.5).

import numpy as np
import pandas as pd

from fiam.v4b.engine.checker import floor_cap
from fiam.v4b.engine.mandate import Final

# Panel columns the fallback reads; none is a return.
COLUMNS = ["me", "me_company", "prc", "gics", "dolvol_126d", "beta_60m"]
# Incumbents stay while inside this multiple of the target count by ADV.
KEEP = 1.5
# Vasicek-style pull of each beta toward 1, stated not fitted.
SHRINK = 1 / 3


# Names allowed this month: both-leg floor, price, size per ADV.
def eligible(month: pd.DataFrame, m: Final, nav: float) -> pd.DataFrame:
    p = m.policy
    size = p.fallback_gross / p.fallback_names * nav
    need = size / (p.participation * p.days_to_exit_max)
    ok = (
        (floor_cap(month) >= max(m.hard.short_floor_musd, p.long_floor_musd))
        & (month["prc"].abs() >= p.price_min)
        & (month["dolvol_126d"] >= need)
        & month["gics"].notna()
    )
    out = month[ok].copy()
    out["sector"] = out["gics"].astype(str).str[:2]
    beta = out["beta_60m"].fillna(out.groupby("sector")["beta_60m"].transform("median"))
    out["beta"] = (1 - SHRINK) * beta.fillna(1.0) + SHRINK
    out["cap"] = floor_cap(out)
    return out


# The most liquid names, keeping incumbents still near the top.
def pick(pool: pd.DataFrame, count: int, held: set) -> pd.DataFrame:
    rank = pool["dolvol_126d"].rank(ascending=False, method="first")
    keep = pool[pool["permno"].isin(held) & (rank <= KEEP * count)]
    rest = pool[~pool.index.isin(keep.index)].sort_values("dolvol_126d", ascending=False)
    return pd.concat([keep, rest.head(max(count - len(keep), 0))])


# Beta-adjacent pairs per sector; the bigger cap shorts (cheaper borrow).
def pair(chosen: pd.DataFrame, sides: dict) -> pd.Series:
    side = {}
    for _, s in chosen.sort_values(["sector", "beta"]).groupby("sector"):
        rows = s.to_dict("records")
        for a, b in zip(rows[0::2], rows[1::2]):
            short, long = (a, b) if a["cap"] >= b["cap"] else (b, a)
            # An incumbent keeps its side when the pair allows it.
            if sides.get(long["permno"]) == -1 or sides.get(short["permno"]) == 1:
                long, short = short, long
            side[long["permno"]], side[short["permno"]] = 1, -1
    return pd.Series(side, dtype=float)


# One target book per eom: equal weights, sector and beta paired.
def books(panel: pd.DataFrame, m: Final, nav: float) -> dict:
    p = m.policy
    out, sides = {}, {}
    for eom, month in panel.groupby("eom", sort=True):
        pool = eligible(month, m, nav)
        chosen = pick(pool, p.fallback_names, set(sides))
        side = pair(chosen, sides)
        if len(side) < m.hard.names_min:
            raise ValueError(f"{eom:%Y-%m}: only {len(side)} names pair up")
        sides = side.to_dict()
        out[eom] = side * (p.fallback_gross / len(side))
    return out


# The ex-ante beta of a book from the same shrunk betas.
def book_beta(weights: pd.Series, pool: pd.DataFrame) -> float:
    beta = pool.set_index("permno")["beta"].reindex(weights.index)
    return float(np.nansum(weights.to_numpy() * beta.to_numpy()))
