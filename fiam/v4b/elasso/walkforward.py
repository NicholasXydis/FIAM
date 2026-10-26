# Walk-forward E-LASSO (user, 2026-10-26: "the weights of models have to be
# refit ... and for backtest latest refit model have to be used"; then "if
# better lets do a monthly re fit walk forward").
#
# Refit at each refit date r: the corrected port (gpu/elasso.py) runs on the
# resrank training rows dated <= r only (a row dated t carries month-t
# returns, so every label in the fit was realised by r). The fitted weights
# are frozen exactly as D10 froze 2020-12 (elasso/oos.py):
#   S-LASSO  mean of the monthly LASSO coefficient rows <= r (MaInf; Ma1 the
#            last row)
#   C-LASSO  univariate intercepts/slopes and the selected set at r
#   E-LASSO  encompassing weight at r
# The model refit at r forecasts the rows dated (r, next refit]: the
# formations at eom r .. next refit - 1 month, from each eom's characteristics.
# Forecast rows come from oos.features: no future label is required, so names
# that later delist stay in.
#
#   month - refit every month-end 2016-12..2026-07 (headline, D15)
#   year  - refit every year-end 2016..2025 (first trial; validation 21-day IC
#           0.013 against 0.027 monthly: the frozen model drifts within the year)
#
# Each refit's frozen weights are kept in weights.parquet (one row per refit
# and block); the yearly run also keeps each fit's full output (fit_<Y>/).
# The score is then volneut (elasso/volneut.tercile_rank) and its calibration
# scale and decay kappa are frozen by tail.calibrate on formations
# 2016-12..2020-11 only.
#
# Universe (user, 2026-10-26: "change training with only possible universe or
# holdable stocks?"; v4 trains on the screen it trades, fiam/ml/dataset.py):
#   all      - every long_ok name (price >= $5, ADV >= $2m), as before
#   holdable - also ADV >= HOLD_ADV and cap >= the $500m short floor, applied
#              before standardising and labelling, to training and forecast
#              rows alike. HOLD_ADV is the mandate's arithmetic, not a fit: an
#              average position ($1bn x 1.8 gross / 400 names = $4.5m) must
#              exit within days_to_exit_max (5) at participation (10%) of ADV.
#
# Usage: python -m fiam.v4b.elasso.walkforward [--every month|year] [--universe all|holdable] [--backend cpu|cuda]

import argparse
import json
import time

import numpy as np
import pandas as pd

from fiam.v4b.elasso import oos, rolling, tail
from fiam.v4b.elasso.volneut import tercile_rank
from fiam.v4b.gpu import elasso
from fiam.v4b.gpu.rolling import BASE

INPUT = BASE / "resrank" / "input" / "data.parquet"
ROOT = BASE.parent / "walkforward"
WINDOWS = {"Ma1": 1, "MaInf": np.inf}
LAST_ROW = pd.Timestamp("2026-08-31")
HOLD_ADV = 1e9 * 1.8 / 400 / (5 * 0.10)
HOLD_CAP = 500.0


def holdable(p: pd.DataFrame) -> pd.Series:
    cap = p[["me", "me_company"]].min(axis=1, skipna=False)
    return (p["dolvol_126d"] >= HOLD_ADV) & (cap >= HOLD_CAP)


def refits(every: str) -> list[pd.Timestamp]:
    if every == "year":
        return [pd.Timestamp(f"{y}-12-31") for y in range(2016, 2026)]
    return list(pd.date_range("2016-12-31", "2026-07-31", freq="ME"))


# The fitted weights frozen at r, one row per block (characteristics as columns).
def frozen_weights(out: dict, r: pd.Timestamp) -> pd.DataFrame:
    w = {k: oos._dated(v) for k, v in out.items()}
    chars = [c for c in w["coefLasso"].columns if c not in ("date", "intercept")]
    rows = {f"s_{n}": oos._avg(w["coefLasso"], r, size) for n, size in WINDOWS.items()}
    rows |= {"uni_int": oos._row_at(w["coefUniIntercept"], r), "uni_slope": oos._row_at(w["coefUniSlope"], r),
             "gr": oos._row_at(w["coefGr"], r)}
    f = pd.DataFrame({k: v.reindex(["intercept", *chars]) for k, v in rows.items()}).T
    enc = oos._row_at(w["coefEncompass"], r)
    f["enc"] = [float(enc[k.removeprefix("s_")]) if k.startswith("s_") else np.nan for k in f.index]
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
        s = b.loc[f"s_{name}", "intercept"] + z @ np.nan_to_num(b.loc[f"s_{name}", chars].to_numpy(float))
        e = float(b.loc[f"s_{name}", "enc"])
        f[name] = (1.0 - e) * s + e * c
    return f


def main(every: str = "month", backend: str = "cpu", universe: str = "all") -> dict:
    keep = holdable if universe == "holdable" else None
    out_dir = ROOT / (every if universe == "all" else f"{every}_{universe}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if keep is None:
        data = pd.read_parquet(INPUT)
    else:
        data = rolling.frame("resrank", keep=keep)
        data.to_parquet(out_dir / "input.parquet", index=False)
    dates = pd.to_datetime(data["date"])
    feats = oos.features(first_eom=pd.Timestamp("2016-11-30"), last_eom=oos.LAST_EOM, keep=keep)
    feats["date"] = pd.to_datetime(feats["date"]).astype("datetime64[ns]")
    rs = refits(every)
    blocks, weights, rep = [], [], {}
    for i, r in enumerate(rs):
        t0 = time.time()
        train = data[dates <= r]
        assert pd.to_datetime(train["date"]).max() <= r
        out = elasso.run(train, backend=backend)
        if every == "year":
            elasso.write(out, out_dir / f"fit_{r.year}")
        fw = frozen_weights(out, r)
        weights.append(fw)
        end = rs[i + 1] if i + 1 < len(rs) else LAST_ROW
        rows = feats[(feats["date"] > r) & (feats["date"] <= end)]
        blocks.append(apply(fw, rows).assign(refit=r))
        rep[str(r.date())] = {"train_months": int(train["date"].nunique()), "forecast_rows": int(len(rows)),
                              "selected_univariate": int((np.nan_to_num(fw.set_index("block").loc["gr"].drop(
                                  ["intercept", "enc", "refit"]).to_numpy(float)) != 0).sum()),
                              "encompass_MaInf": float(fw.set_index("block").loc["s_MaInf", "enc"]),
                              "seconds": round(time.time() - t0, 1)}
        print(r.date(), rep[str(r.date())], flush=True)
    pd.concat(weights, ignore_index=True).to_parquet(out_dir / "weights.parquet", index=False)
    raw = pd.concat(blocks, ignore_index=True)
    raw.to_parquet(out_dir / "forecastElasso_raw.parquet", index=False)
    run = out_dir / "volneut"
    run.mkdir(parents=True, exist_ok=True)
    tercile_rank(raw, ("MaInf", "Ma1")).to_parquet(run / "forecastElasso.parquet", index=False)
    cal = tail.calibrate(run)
    rep["calibration"] = {c: {"scale": cal[c]["calibration_y21"]["slope"], "kappa": cal[c]["frozen_kappa"],
                              "ic_21": cal[c]["ic_decay"]["curve"]["21"]} for c in tail.COLUMNS}
    (out_dir / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--every", default="month", choices=("month", "year"))
    a.add_argument("--backend", default="cpu")
    a.add_argument("--universe", default="all", choices=("all", "holdable"))
    x = a.parse_args()
    print(json.dumps(main(x.every, x.backend, x.universe)["calibration"], indent=1))
