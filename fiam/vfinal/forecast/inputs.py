# E-LASSO's training and forecast rows from the organisers' panel.

import pandas as pd

from fiam.vfinal import config
from fiam.vfinal.forecast import data

CUT = pd.Timestamp(config.CUT)
TAIL = 0.10


# One characteristic, GHZ-style within each month.
def ghz(frame: pd.DataFrame, col: str) -> pd.Series:
    g = frame.groupby("eom")[col]
    lo, hi = g.transform(lambda s: s.quantile(0.01)), g.transform(lambda s: s.quantile(0.99))
    x = frame[col].clip(lo, hi)
    gx = x.groupby(frame["eom"])
    z = (x - gx.transform("mean")) / gx.transform("std")
    # A characteristic with no usable values this month stays NA.
    empty = gx.transform("count").fillna(0) < 2
    return z.fillna(0.0).where(~empty)


# Month-t label for one variant (resrank is the one used).
def label(ret: pd.Series, eom: pd.Series, kind: str, beta: pd.Series | None = None,
          me: pd.Series | None = None) -> pd.Series:  # fmt: skip
    if kind == "ret":
        return ret
    if kind in ("resrank", "resup", "resdown"):
        mkt = (ret * me).groupby(eom).transform("sum") / me.groupby(eom).transform("sum")
        b = beta.fillna(beta.groupby(eom).transform("median")).fillna(1.0)
        ret = ret - b * mkt
    q = ret.groupby(eom).rank(pct=True, method="average")
    tail = 0.2 if kind.endswith("20") else TAIL
    if kind == "resrank":
        return q - 0.5
    if kind in ("up", "up20", "resup"):
        return (q > 1 - tail).astype("float64")
    if kind in ("down", "down20", "resdown"):
        return (q <= tail).astype("float64")
    raise ValueError(kind)


# Training rows (rolling.frame): every label realised by the row's date.
def frame(kind: str = "resrank", cut: pd.Timestamp = CUT) -> pd.DataFrame:
    chars = data.characteristics()
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & p["ret_exc_lead1m"].notna() & (p["me"] > 0)].copy()
    ex = data.exchcd(None, cut)
    p = p.merge(ex, on=["permno", "eom"], how="left")
    z = pd.DataFrame({c: ghz(p, c) for c in chars}, index=p.index)
    front = pd.DataFrame(
        {
            "date": (p["eom"] + pd.offsets.MonthEnd(1)).dt.date,
            "permno": p["permno"].astype("int64"),
            "exchcd": p["exchcd"].astype("float64"),
            "me": p["me"].astype("float64"),
            "ret": label(
                p["ret_exc_lead1m"].astype("float64"),
                p["eom"],
                kind,
                beta=p["beta_60m"].astype("float64"),
                me=p["me"].astype("float64"),
            ),  # fmt: skip
        }
    )
    out = pd.concat([front, z], axis=1).sort_values(["date", "permno"], ignore_index=True)
    if pd.Timestamp(max(out["date"])) > cut:
        raise AssertionError("a target month after the cut")
    return out


# Forecast rows: characteristics at eom, no label needed.
def features(first_eom: pd.Timestamp, last_eom: pd.Timestamp,
             cut: pd.Timestamp = CUT) -> pd.DataFrame:  # fmt: skip
    chars = data.characteristics()
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & (p["me"] > 0)].copy()
    p = p[p["eom"].between(first_eom, last_eom)].copy()
    ex = data.exchcd(first_eom, last_eom)
    p = p.merge(ex, on=["permno", "eom"], how="left")
    z = pd.DataFrame({c: ghz(p, c) for c in chars}, index=p.index)
    z = z.fillna(0.0)
    front = pd.DataFrame(
        {
            "date": (p["eom"] + pd.offsets.MonthEnd(1)).dt.date,
            "permno": p["permno"].astype("int64"),
            "exchcd": p["exchcd"].astype("float64"),
            "me": p["me"].astype("float64"),
        }
    )
    return pd.concat([front, z], axis=1).sort_values(["date", "permno"], ignore_index=True)
