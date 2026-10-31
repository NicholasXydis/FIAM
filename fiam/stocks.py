# The stock panel, the tradable screen and the twelve signals.

from __future__ import annotations

from functools import cache

import pandas as pd

from fiam import data
from fiam.benchmarks import benchmarks

# Decide at month end, hold the next, so July 2026 is the last decision.
FIRST_FORECAST, LAST_FORECAST = "2020-12-31", "2026-07-31"

# Twelve measures, each signed by theory.
SIGNALS = {
    "ivol_capm_21d": -1,
    "be_me": +1,
    "qmj": +1,
    "at_gr1": -1,
    "niq_su": +1,
    "ope_be": +1,
    "chcsho_12m": -1,
    "o_score": -1,
    "ret_12_1": +1,
    "gp_at": +1,
    "noa_gr1a": -1,
    "eqnetis_at": -1,
}


# Loads the stock data and works out each company's sector.
def load_panel(extra: tuple[str, ...] = ()) -> pd.DataFrame:
    # Only the columns we use. Loading all 198 wastes about 2GB of memory.
    cols = (
        list(SIGNALS)
        + list(extra)
        + [
            "permno",
            "eom",
            "prc",
            "me",
            "ret_exc_lead1m",
            "gics",
            "beta_60m",
            "dolvol_126d",
            "size_grp",
            "bidaskhl_21d",
            "rvol_21d",
            "betadown_252d",
            "betabab_1260d",
            "beta_dimson_21d",
            "market_equity",
            "ticker",
            "company_name",
        ]
    )
    panel = data.panel(cols)
    # Two GICS digits give 11 sectors. No sector is its own group, kept.
    panel["sector"] = panel["gics"].astype("string").str[:2].fillna("XX")
    return panel


# Narrows the list to stocks we would actually be willing to trade.
def screen(
    panel: pd.DataFrame, first: str = FIRST_FORECAST, last: str = LAST_FORECAST, wrds: bool = True
):
    # Price and size only, never a return, so failed firms stay in.
    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)
    window = panel["eom"].between(first, last)
    # wrds=False is the panel anyone rebuilds from organizer data alone.
    return settle(panel[keep & window].copy()) if wrds else panel[keep & window].copy()


# Dated delistings and final-month payouts from WRDS, or None without.
@cache
def exits() -> pd.DataFrame | None:
    return data.wrds("exits")


# Drops names delisted by decision date, books next-month exit payouts.
def settle(df: pd.DataFrame) -> pd.DataFrame:
    table = exits()
    if table is None:
        return df
    # Only an exit dated by the decision is known then, so no later one.
    dead = df["permno"].map(table["exit_date"]) <= df["eom"]
    df = df[~dead].copy()
    df.attrs["dead_at_decision"] = int(dead.sum())
    holding = (df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    final = (
        df["permno"]
        .map(table["final_return"])
        .where(df["permno"].map(table["final_month"]) == holding)
    )
    rf = holding.map(benchmarks().set_index("month")["rf"])
    df["ret_exc_lead1m"] = df["ret_exc_lead1m"].fillna(final - rf)
    return df


# The 147 characteristics the rules name, the only source of predictors.
def characteristics() -> list[str]:
    return data.characteristics()
