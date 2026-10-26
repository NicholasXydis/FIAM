# E-LASSO input: the authors' data contract built from the organisers' panel.
#
# Contract (programMainElasso.R + Han-He-Rapach-Zhou data section, GHZ style):
#   columns date, permno, exchcd, me, ret, then characteristics;
#   a row dated t holds the month-t return and characteristics known at t-1;
#   me is market value at the end of t-1 (the WLS weight);
#   each characteristic winsorised at 1/99%, standardised within month, NA -> 0.
# Our choices on the input side only: tradable universe, excess return,
# target months 2015-02..2020-12 (blind: no label ends after 2020-12-31).

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data

BASE = Path(__file__).resolve().parents[1] / "out" / "elasso"
OUT = BASE / "input"


# One characteristic, GHZ-style within each month: clip, standardise, fill 0.
def ghz(frame: pd.DataFrame, col: str) -> pd.Series:
    g = frame.groupby("eom")[col]
    lo, hi = g.transform(lambda s: s.quantile(0.01)), g.transform(lambda s: s.quantile(0.99))
    x = frame[col].clip(lo, hi)
    gx = x.groupby(frame["eom"])
    z = (x - gx.transform("mean")) / gx.transform("std")
    # A characteristic with no usable values this month stays NA (code drops it).
    empty = gx.transform("count").fillna(0) < 2
    return z.fillna(0.0).where(~empty)


# Standardised characteristics lagged one month per stock (H2 vintage case).
# Standardise first (within the characteristics' own month), then lag, so the
# stale cross-section keeps its own scaling; a missing prior month is neutral.
def lagged(z: pd.DataFrame, p: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    key = pd.Series(range(len(p)), index=pd.MultiIndex.from_frame(p[["permno", "eom"]]))
    prev = pd.MultiIndex.from_arrays([p["permno"], p["eom"] - pd.offsets.MonthEnd(1)])
    pos = key.reindex(prev).to_numpy()
    values = np.zeros(z.shape, dtype=float)
    ok = ~pd.isna(pos)
    values[ok] = z.to_numpy()[pos[ok].astype(int)]
    return pd.DataFrame(values, index=z.index, columns=z.columns), ok


# Builds the data frame and writes it as parquet for the R side.
# lag=True is the H2 conservative case: month-t returns meet t-2 characteristics.
def main(lag: bool = False) -> pd.DataFrame:
    chars = data.characteristics()
    p = data.panel()
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & p["ret_exc_lead1m"].notna() & (p["me"] > 0)].copy()
    ex = pd.read_parquet(
        data.PANEL, columns=["permno", "eom", "exchcd"], filters=[("eom", "<=", data.BLIND)]
    )
    ex["eom"] = pd.to_datetime(ex["eom"]).astype("datetime64[ns]")
    p = p.merge(ex, on=["permno", "eom"], how="left")
    z = pd.DataFrame({c: ghz(p, c) for c in chars}, index=p.index)
    if lag:
        z, ok = lagged(z, p)
        # A month with almost no stale data (the first) has no usable
        # cross-section; the authors' code cannot fit it. Drop such months.
        share = pd.Series(ok, index=p.index).groupby(p["eom"]).transform("mean")
        keep = (share >= 0.5).to_numpy()
        p, z = p[keep].copy(), z[keep]
    front = pd.DataFrame(
        {
            "date": (p["eom"] + pd.offsets.MonthEnd(1)).dt.date,
            "permno": p["permno"].astype("int64"),
            "exchcd": p["exchcd"].astype("float64"),
            "me": p["me"].astype("float64"),
            "ret": p["ret_exc_lead1m"].astype("float64"),
        }
    )
    out = pd.concat([front, z], axis=1).sort_values(["date", "permno"], ignore_index=True)
    if pd.Timestamp(max(out["date"])) > data.BLIND:
        raise AssertionError("a target month after the blind cutoff")
    dest = BASE / ("input_lag1" if lag else "input")
    dest.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest / "data.parquet", index=False)
    return out


if __name__ == "__main__":
    import sys

    d = main(lag="--lag1" in sys.argv)
    print(d.shape, d["date"].min(), d["date"].max(), d.groupby("date").size().median())
