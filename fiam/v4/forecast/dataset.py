# The models' monthly table: inputs, labels and SUE targets (step 6).

import numpy as np
import pandas as pd

from fiam.v4 import data, gates, ranks, sources, universe
from fiam.v4 import inputs as engine_inputs
from fiam.v4.signals import syy

# Formations with inputs: 2015-01 to 2020-12 (the last has no label).
FIRST, LAST = pd.Timestamp("2015-01-31"), pd.Timestamp("2020-12-31")
# The two training sets of lever D1, by their label sample's name.
STOCKS = ("universe", "panel")
# Inputs beyond the organisers' 147 (no flag, no cost, PLAN §1.2).
EXTRA = ("syy", "sue_forecast")


# Inputs may only be the 147, SYY-10 and the SUE forecast (allow-list).
def check_inputs(names: list[str], chars: list[str]) -> list[str]:
    allowed = set(chars) | set(EXTRA)
    for name in names:
        if name not in allowed:
            raise sources.NotForBacktest(f"{name} is not an allowed model input (§1.2)")
    return list(names)


# Every formation's panel rows, universe flag, SYY-10 and sector.
def inputs(chars: list[str]) -> pd.DataFrame:
    cols = list(dict.fromkeys([*chars, "me", "gics"]))
    p = data.table("panel", cols, where={"eom": (FIRST, LAST)})
    out = []
    for eom, g in p.groupby("eom"):
        T = data.eom_session([eom]).iloc[0]
        data.assert_public_by(g["first_close"], T, "model inputs")
        g = g.set_index("permno")
        m = universe.members(eom).set_index("permno")
        frame = g[[*chars, "me"]].copy()
        frame["syy_raw"] = syy.combine(g[list(syy.PARTS)])["raw"]
        # GICS-2, else the SIC-2 then "XX", as the labels' regression uses.
        frame["sector"] = engine_inputs.sector(g.index, eom).reindex(g.index).to_numpy()
        frame["in_universe"] = frame.index.isin(m.index[m["new_long"]])
        out.append(frame.reset_index().assign(eom=eom, T=T))
    return pd.concat(out, ignore_index=True)


# Both horizons' labels: ranked residuals, raw residuals and clocks.
def targets() -> pd.DataFrame:
    cols = ["resid_rank_universe", "resid_rank_panel", "resid_universe", "available"]
    # A residual uses its month's labels: public at month_available.
    cols.append("month_available")
    lab = sources.read("labels", cols, purpose="label")
    wide = lab.set_index(["permno", "eom", "horizon"])[cols].unstack("horizon")
    wide.columns = [f"{c}_h{h}" for c, h in wide.columns]
    return wide.reset_index()


# Each formation's next as-filed SUE within 4 months, with its clock.
def sue_targets(eoms) -> pd.DataFrame:
    sue = sources.read("sue", ["sue", "announced", "end", "filed"], purpose="label")
    out = []
    for eom in eoms:
        T = data.eom_session([eom]).iloc[0]
        if T + gates.FOUR_MONTHS > gates.LAST_DAY:
            continue
        nxt = sue[(sue["announced"] > T) & (sue["announced"] <= T + gates.FOUR_MONTHS)]
        nxt = nxt.sort_values(["announced", "end"], kind="stable").drop_duplicates("permno")
        out.append(pd.DataFrame({"permno": nxt["permno"].to_numpy(), "eom": eom,
                                 "sue_target": nxt["sue"].to_numpy(),
                                 "sue_public": nxt["first_close"].to_numpy()}))  # fmt: skip
    return pd.concat(out, ignore_index=True)


# The whole table: one row per panel stock and formation.
def build(chars: list[str]) -> pd.DataFrame:
    x = inputs(chars)
    x = x.merge(targets(), on=["permno", "eom"], how="left")
    x = x.merge(sue_targets(sorted(x["eom"].unique())), on=["permno", "eom"], how="left")
    return x


# A month's inputs ranked within a training set, missing as 0.
def ranked(frame: pd.DataFrame, cols: list[str], stocks: str) -> pd.DataFrame:
    rows = frame if stocks == "panel" else frame[frame["in_universe"]]
    out = []
    for _, g in rows.groupby("eom"):
        r = pd.DataFrame({c: ranks.unit_rank(g[c]) for c in cols}, index=g.index)
        out.append(r.fillna(0.0))
    return pd.concat(out).reindex(rows.index)


# Rows usable for a fit whose first forecast formation closes at T.
def public_by(frame: pd.DataFrame, clock: str, T) -> np.ndarray:
    seen = pd.to_datetime(frame[clock])
    if getattr(seen.dt, "tz", None) is not None:
        seen = seen.dt.tz_convert(None)
    return (seen <= pd.Timestamp(T)).to_numpy()


# The label columns for a horizon and a training set.
def label_column(horizon: int, stocks: str) -> str:
    return f"resid_rank_{stocks}_h{horizon}"
