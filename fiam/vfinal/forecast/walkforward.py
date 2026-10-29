# The walk-forward freeze and apply of one refit's weights.

import numpy as np
import pandas as pd

from fiam.vfinal import config

WINDOWS = {"Ma1": 1, "MaInf": np.inf}
LAST_ROW = pd.Timestamp(config.CUT)


# Date column as datetime64[ns].
def _dated(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).astype("datetime64[ns]")
    return out


# Last row dated on or before the cut.
def _row_at(frame: pd.DataFrame, cut: pd.Timestamp) -> pd.Series:
    rows = frame[frame["date"] <= cut]
    if rows.empty:
        raise ValueError(f"no coefficient row on or before {cut}")
    return rows.sort_values("date").iloc[-1]


# Mean of the rows dated on or before the cut over a window.
def _avg(frame: pd.DataFrame, cut: pd.Timestamp, window: float) -> pd.Series:
    rows = frame[frame["date"] <= cut].sort_values("date")
    if window == np.inf:
        use = rows
    else:
        use = rows.tail(int(window))
    return use.drop(columns="date").mean()


# Monthly refit dates, 2016-12 to 2026-07.
def refits() -> list[pd.Timestamp]:
    return list(pd.date_range("2016-12-31", config.LAST_EOM, freq="ME"))


# The fitted weights frozen at r, one row per block.
def frozen_weights(out: dict, r: pd.Timestamp) -> pd.DataFrame:
    w = {k: _dated(v) for k, v in out.items()}
    chars = [c for c in w["coefLasso"].columns if c not in ("date", "intercept")]
    rows = {f"s_{n}": _avg(w["coefLasso"], r, size) for n, size in WINDOWS.items()}
    rows |= {"uni_int": _row_at(w["coefUniIntercept"], r),
             "uni_slope": _row_at(w["coefUniSlope"], r),
             "gr": _row_at(w["coefGr"], r)}  # fmt: skip
    f = pd.DataFrame({k: v.reindex(["intercept", *chars]) for k, v in rows.items()}).T
    enc = _row_at(w["coefEncompass"], r)
    f["enc"] = [float(enc[k.removeprefix("s_")]) if k.startswith("s_") else np.nan
                for k in f.index]  # fmt: skip
    return f.rename_axis("block").reset_index().assign(refit=r)


# The frozen model applied to one block of characteristic rows.
def apply(fw: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    b = fw.set_index("block")
    chars = [c for c in b.columns if c not in ("intercept", "enc", "refit")]
    z = rows[chars].fillna(0.0).to_numpy(float)
    sel = np.nan_to_num(b.loc["gr", chars].to_numpy(float)) != 0.0
    uni = b.loc["uni_int", chars].to_numpy(float) + z * b.loc["uni_slope", chars].to_numpy(float)
    c = np.nan_to_num(uni[:, sel]).mean(1) if sel.any() else np.zeros(len(rows))
    f = rows[["date", "permno", "exchcd", "me"]].copy()
    for name in WINDOWS:
        coef = np.nan_to_num(b.loc[f"s_{name}", chars].to_numpy(float))
        s = b.loc[f"s_{name}", "intercept"] + z @ coef
        e = float(b.loc[f"s_{name}", "enc"])
        f[name] = (1.0 - e) * s + e * c
    return f
