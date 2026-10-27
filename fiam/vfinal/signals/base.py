# What every gated signal shares: formation days and the CIK link.

import pandas as pd

from fiam.vfinal import data, links


# Each formation month end and T, its last session.
def formations(eoms) -> pd.DataFrame:
    eoms = pd.DatetimeIndex(eoms)
    return pd.DataFrame({"eom": eoms, "T": data.eom_session(eoms).to_numpy()})


# Stocks with an SEC filer on T: without one a filing signal is none.
def has_cik(permnos, T) -> pd.Series:
    ids = sorted(set(int(p) for p in permnos))
    lk = data.table("links", None)
    got = links.value_at(lk, "cik", ids, [pd.Timestamp(T)] * len(ids))
    return pd.Series(got.notna().to_numpy(), index=ids)


# The trading universe's stocks at one formation.
def universe_at(eom) -> list[int]:
    from fiam.vfinal import universe

    m = universe.members(eom)
    return sorted(m.loc[m["new_long"], "permno"].astype(int))
