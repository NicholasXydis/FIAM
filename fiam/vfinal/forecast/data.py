# The panel reads E-LASSO needs; the organisers' files read only.

import numpy as np
import pandas as pd

from fiam.vfinal import config

# Columns the forecaster may read besides the 147 (never as inputs).
AUX = ["permno", "eom", "me", "me_company", "prc", "dolvol_126d", "gics", "ret_exc_lead1m"]
# Banned fields, asserted absent from every column list.
BANNED = {"adjfct"}


# The 147 characteristic names, in the organisers' order.
def characteristics() -> list[str]:
    c = pd.read_csv(config.CHARS)["variable"].tolist()
    assert not BANNED & set(c), "banned field in the characteristic list"
    return c


# Panel rows to the cut; a label ending after it is blanked.
def panel(cut: pd.Timestamp) -> pd.DataFrame:
    cols = list(dict.fromkeys(AUX + characteristics()))
    assert not BANNED & set(cols)
    p = pd.read_parquet(config.PANEL, columns=cols, filters=[("eom", "<=", cut.date())])
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    late = (p["eom"] + pd.offsets.MonthEnd(1)) > cut
    p.loc[late, "ret_exc_lead1m"] = np.nan
    return p.sort_values(["eom", "permno"], ignore_index=True)


# Exchange code per row, read by column name only.
def exchcd(first: pd.Timestamp | None, cut: pd.Timestamp) -> pd.DataFrame:
    f = [("eom", "<=", cut.date())]
    if first is not None:
        f.append(("eom", ">=", first.date()))
    ex = pd.read_parquet(config.PANEL, columns=["permno", "eom", "exchcd"], filters=f)
    ex["eom"] = pd.to_datetime(ex["eom"]).astype("datetime64[ns]")
    return ex


# Tradable flags per row: long-eligible, short-eligible (R3, R2).
def tradable(
    p: pd.DataFrame,
    adv_min_usd: float = 2e6,
    price_min: float = 5.0,
    short_floor_musd: float = 500.0,
) -> pd.DataFrame:
    cap = p[["me", "me_company"]].min(axis=1, skipna=False)
    long_ok = (p["prc"].abs() >= price_min) & (p["dolvol_126d"] >= adv_min_usd)
    return pd.DataFrame(
        {"long_ok": long_ok, "short_ok": long_ok & (cap >= short_floor_musd)}, index=p.index
    )
