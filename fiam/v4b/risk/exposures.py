# Factor exposures B_t: assigned, never regressed (R§4, eval 03 F1.2).
#
# Sectors are exact dummies from the dated panel GICS. Styles are the same
# within-month rank z-scores the residual target uses (forecast/targets.py),
# so B'w reads as the book's average standardised characteristic. The market
# column (shrunk time-series beta) lives in beta.py. Exposures are monthly:
# the row at eom t is public after that close and is carried over the daily
# sessions that follow it, never backward.

import pandas as pd

from fiam.v4b.forecast import data, targets

# Style name -> panel column (targets.EXPOSURES without its beta entry).
STYLES = {k: v for k, v in targets.EXPOSURES.items() if k != "beta"}
PANEL_COLS = ["me", "me_company", "prc", "dolvol_126d", "gics", "beta_60m", *STYLES.values()]


# Monthly exposures for every panel row to the blind cutoff.
def monthly(cut: pd.Timestamp = data.BLIND) -> pd.DataFrame:
    p = pd.read_parquet(
        data.PANEL, columns=["permno", "eom", *PANEL_COLS], filters=[("eom", "<=", cut)]
    )
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    p = p.join(data.tradable(p))
    p["sector"] = targets.sector(p)
    for name, col in STYLES.items():
        p[name] = targets.zrank(p, col)
    keep = [
        "eom",
        "permno",
        "sector",
        *STYLES,
        "me",
        "me_company",
        "dolvol_126d",
        "beta_60m",
        "long_ok",
        "short_ok",
    ]
    return p[keep].sort_values(["eom", "permno"], ignore_index=True)


# The exposure row in force on a session: last eom strictly before it.
def carried(exp: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict:
    eoms = pd.DatetimeIndex(sorted(exp["eom"].unique()))
    pos = eoms.searchsorted(pd.DatetimeIndex(sessions), side="left") - 1
    return {day: (eoms[i] if i >= 0 else None) for day, i in zip(sessions, pos)}


# Design block for one month: sector dummies + styles, liquid rows only,
# indexed by permno. Empty sectors drop out (their column would be zero).
def design(month: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    m = month[month["long_ok"] & month["sector"].notna()].copy()
    dummies = pd.get_dummies(m["sector"], prefix="s", dtype=float)
    dummies.index = m.index
    x = pd.concat([dummies, m[list(STYLES)]], axis=1)
    x.index = m["permno"].to_numpy()
    x.index.name = "permno"
    sectors = [c for c in x.columns if c.startswith("s_")]
    return x, sectors
