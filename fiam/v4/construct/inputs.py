# Each formation's construction inputs: exposures, betas, liquidity.

import numpy as np
import pandas as pd

from fiam.v4 import data, ranks, universe
from fiam.v4 import inputs as engine_inputs
from fiam.v4.signals import short_interest

# Styles the optimiser holds at 0 (size, value) or caps (the rest).
STYLES = {"size": "me", "value": "be_me", "momentum": "ret_12_1", "quality": "gp_at",
          "investment": "at_gr1", "high_ivol": "ivol_capm_252d",
          "liquidity": "turnover_126d"}  # fmt: skip
NEUTRAL = ("size", "value")
CAPPED = ("momentum", "quality", "investment", "high_ivol", "mid_cap", "liquidity")
# A held short is covered below $550m (protocol "Step 7 rules").
SHORT_HOLD_MUSD = 550.0
# Borrow tiers a year by short interest over shares (checklist).
TIERS = ((0.20, 0.08), (0.10, 0.03), (0.05, 0.01), (0.0, 0.003))


# Root-cap weighted z-scores of every style, clipped at 3, missing 0.
def styles(frame: pd.DataFrame) -> pd.DataFrame:
    w = np.sqrt(frame["me"].clip(lower=1.0))
    out = pd.DataFrame(index=frame.index)
    for name, col in STYLES.items():
        raw = np.log(frame[col].clip(lower=1e-6)) if name == "size" else frame[col]
        out[name] = ranks.zscore(raw, w).fillna(0.0)
    # Mid cap: the cube of size, orthogonal to size, re-standardised.
    cube = out["size"] ** 3
    x = np.column_stack([np.ones(len(cube)), out["size"]])
    coef, *_ = np.linalg.lstsq(x * np.sqrt(w.to_numpy())[:, None],
                               cube.to_numpy() * np.sqrt(w.to_numpy()), rcond=None)  # fmt: skip
    out["mid_cap"] = ranks.zscore(cube - x @ coef, w).fillna(0.0)
    return out


# The borrow tier a year for a short ratio; unknown is the cheapest.
def borrow_tier(ratio: pd.Series) -> pd.Series:
    out = pd.Series(TIERS[-1][1], index=ratio.index)
    for bound, rate in reversed(TIERS[:-1]):
        out[ratio >= bound] = rate
    return out


# One formation: who may trade, with exposures, betas and liquidity.
def formation(eom, held_long=(), held_short=()) -> pd.DataFrame:
    eom = pd.Timestamp(eom) + pd.offsets.MonthEnd(0)
    m = universe.members(eom, held_long, held_short).set_index("permno")
    m["keep_short"] &= m["me"] >= SHORT_HOLD_MUSD
    m = m[m["new_long"] | m["keep_long"] | m["keep_short"]]
    T = m["session"].iloc[0]
    cols = ["be_me", "ret_12_1", "gp_at", "at_gr1", "ivol_capm_252d", "turnover_126d", "beta_60m",
            "dolvol_126d", "bidaskhl_21d"]  # fmt: skip
    p = data.table("panel", cols, where={"eom": (eom, eom)}).set_index("permno")
    data.assert_public_by(p["first_close"], T, "construction panel rows")
    x = m[["me", "prc", "new_long", "new_short", "keep_long", "keep_short"]].join(p[cols])
    x = x.join(styles(x))
    x["sector"] = engine_inputs.sector(x.index, eom).reindex(x.index)
    si = short_interest.build([eom]).set_index("permno")["value"]
    x["short_ratio"] = si.reindex(x.index)
    x["borrow"] = borrow_tier(x["short_ratio"].fillna(0.0))
    return x.assign(eom=eom, T=T)
