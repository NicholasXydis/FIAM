# Proves gpu/elasso.py against the authors' R outputs of a rolling run.
#
# The R run carries the C-LASSO assignment defect (D13), so the comparison
# rebuilds R's assignment here (and only here) via `r_assign`. Everything
# else is the production code path.
# Usage: python -m fiam.v4b.gpu.verify <kind> [--months N]
#   kind: ret | up | down (out/elasso/rolling/<kind>); --months N runs the first
#   N dates only and compares the months that do not depend on later data.

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.gpu import elasso

BASE = Path(__file__).resolve().parents[1] / "out" / "elasso" / "rolling"


def r_assign(s: np.ndarray) -> np.ndarray:
    # R: tCoefGr[tIndex] = tCoef[-1] with tCoef already intercept-free.
    v = s[1:]
    return v[np.arange(len(s)) % len(v)]


def _dates(x) -> pd.Series:
    return pd.to_datetime(pd.Series(x)).dt.normalize()


def compare(ours: pd.DataFrame, r: pd.DataFrame, key: list[str], cols: list[str], keep_dates=None) -> dict:
    a, b = ours.copy(), r.copy()
    for d in (a, b):
        d["date"] = _dates(d["date"]).to_numpy()
    if keep_dates is not None:
        a, b = a[a["date"].isin(keep_dates)], b[b["date"].isin(keep_dates)]
    m = a.merge(b, on=key, suffixes=("", "_r"), how="outer", indicator=True)
    res = {"rows_ours": int(len(a)), "rows_r": int(len(b)), "unmatched": int((m["_merge"] != "both").sum())}
    m = m[m["_merge"] == "both"]
    worst, scale = 0.0, 0.0
    for c in cols:
        x, y = m[c].to_numpy(float), m[c + "_r"].to_numpy(float)
        both_nan = np.isnan(x) & np.isnan(y)
        res.setdefault("nan_mismatch", 0)
        res["nan_mismatch"] += int((np.isnan(x) ^ np.isnan(y)).sum())
        d = np.abs(x - y)[~both_nan & ~np.isnan(x) & ~np.isnan(y)]
        if len(d):
            worst = max(worst, float(d.max()))
            scale = max(scale, float(np.nanmax(np.abs(y))))
    res["max_abs_diff"] = worst
    res["max_abs_value"] = scale
    return res


def main(kind: str, months: int | None, backend: str = "cpu") -> dict:
    data = pd.read_parquet(BASE / kind / "input" / "data.parquet")
    data["date"] = pd.to_datetime(data["date"])
    dates = pd.DatetimeIndex(pd.unique(data["date"]))
    if months:
        data = data[data["date"].isin(dates[:months])]
    t0 = time.time()
    out = elasso.run(data, gr_assign=r_assign, backend=backend)
    secs = time.time() - t0
    run = BASE / kind / "run"
    chars = [c for c in data.columns if c not in elasso.FRONT]
    used = pd.DatetimeIndex(pd.unique(data["date"]))
    # With a truncated input the last month uses the t == T rule; compare the rest.
    keep = used[:-1] if months else used
    rep = {"kind": kind, "months": len(used), "seconds": round(secs, 1), "backend": backend}
    rep["coefLasso"] = compare(out["coefLasso"], pd.read_parquet(run / "coefLasso.parquet"), ["date"], ["intercept", *chars], keep)
    rep["forecastSlasso"] = compare(out["forecastSlasso"], pd.read_parquet(run / "forecastSlasso.parquet"), ["date", "permno"], elasso.MA_NAMES, keep)
    rep["coefGr"] = compare(out["coefGr"], pd.read_parquet(run / "coefGr.parquet"), ["date"], chars, keep[1:-1] if months else keep)
    rep["forecastClasso"] = compare(out["forecastClasso"], pd.read_parquet(run / "forecastClasso.parquet"), ["date", "permno"], ["forecast"], keep)
    rep["coefEncompass"] = compare(out["coefEncompass"], pd.read_parquet(run / "coefEncompass.parquet"), ["date"], elasso.MA_NAMES, keep[:-1] if months else keep)
    rep["forecastElasso"] = compare(out["forecastElasso"], pd.read_parquet(run / "forecastElasso.parquet"), ["date", "permno"], elasso.MA_NAMES, keep)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kind")
    ap.add_argument("--months", type=int)
    ap.add_argument("--backend", default="cpu", choices=["cpu", "cuda"])
    a = ap.parse_args()
    print(json.dumps(main(a.kind, a.months, a.backend), indent=1))
