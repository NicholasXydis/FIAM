# The engine's tail forecaster (D11 amendment, D12): rolling E-LASSO up - down.
#
# Score = MaInf(up head) - MaInf(down head) from elasso/rolling.py, the
# QUARCC-Black dual-head score estimated inside the authors' unchanged code.
# Ma1 is carried the same way as the alternate. Units are percent probability
# points; forecaster.expected_returns divides by 100 like any E-LASSO column.
#
# The score is not a return, so it gets the same centred Mincer-Zarnowitz
# calibration and alpha-decay fit as D7 (elasso/freeze.py), estimated on the
# validation formations 2016-12..2020-11 only. Nothing after 2020-11 enters
# the frozen numbers; the decision to use the tail score at all was taken
# after seeing 2021+ (disclosed in D11/D12).

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.elasso import freeze, judge
from fiam.v4b.elasso.rolling import BASE
from fiam.v4b.forecast import initial_plan, run

OUT = BASE / "tail"
COLUMNS = ("Elasso_MaInf", "Elasso_Ma1")


# Writes the combined tail file in the authors' forecastElasso layout.
def build() -> Path:
    up = pd.read_parquet(BASE / "up" / "run" / "forecastElasso.parquet")
    dn = pd.read_parquet(BASE / "down" / "run" / "forecastElasso.parquet")
    key = ["date", "permno"]
    f = up[key + ["me", "MaInf", "Ma1"]].merge(
        dn[key + ["MaInf", "Ma1"]], on=key, suffixes=("_up", "_dn"), validate="one_to_one"
    )
    for w in ("MaInf", "Ma1"):
        f[w] = f[f"{w}_up"] - f[f"{w}_dn"]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "forecastElasso.parquet"
    f[key + ["me", "MaInf", "Ma1"]].to_parquet(path, index=False)
    return path


# freeze.frame with the tail forecasts (or another run's, `out`) in place of the frozen-run ones.
def frame(out: Path = OUT, columns: tuple = COLUMNS) -> pd.DataFrame:
    u, *_ = initial_plan.prepare()
    fc = pd.read_parquet(out / "forecastElasso.parquet")
    fc["eom"] = (pd.to_datetime(fc["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    fc = fc.rename(columns={c.split("_", 1)[1]: c for c in columns})
    fc = fc[fc["eom"].between(pd.Timestamp(judge.WINDOW[0]), pd.Timestamp(judge.WINDOW[1]))]
    keep = ["eom", "permno", "ret_exc_lead1m", *[f"y{h}" for h in run.HORIZONS]]
    f = fc[["eom", "permno", *columns]].merge(u[keep], on=["eom", "permno"], how="inner")
    for c in columns:
        f[c] = f[c] / 100.0
    f["y2"] = freeze._y2(f)
    return f


# Frozen calibration and decay for the tail columns, or for any run in the
# same layout (`out`; elasso/volneut.py), validation window only.
def calibrate(out_dir: Path = OUT, columns: tuple = COLUMNS) -> dict:
    f = frame(out_dir, columns)
    months = np.array(sorted(f["eom"].unique()))
    if pd.Timestamp(months[-1]) > pd.Timestamp("2020-11-30"):
        raise AssertionError("tail calibration must not see 2020-12 or later formations")
    draws = freeze._month_draws(months)
    out = {
        "window_eom": [str(pd.Timestamp(months[0]).date()), str(pd.Timestamp(months[-1]).date())],
        "months": int(len(months)),
        "rows": int(len(f)),
        "bootstrap": {"draws": freeze.DRAWS, "block_months": freeze.BLOCK, "seed": freeze.SEED},
    }
    for c in columns:
        out[c] = {
            "calibration_y21": freeze.calibration(f, c, "y21", draws),
            "calibration_monthly": freeze.calibration(f, c, "ret_exc_lead1m", draws),
            "ic_decay": freeze.decay(f, c, draws, freeze.ic_curve, freeze._fit_ic),
            "alpha_decay": freeze.decay(f, c, draws, freeze.alpha_curve, freeze._fit_alpha),
            "score_sd": float(f.groupby("eom")[c].std().mean()),
        }
        a = out[c]["alpha_decay"]
        identified = a.get("kappa") is not None and a.get("kappa_lo90", 0) > 0
        out[c]["frozen_kappa"] = a["kappa"] if identified else 0.0
        out[c]["kappa_identified"] = bool(identified)
    (out_dir / "frozen.json").write_text(json.dumps(out, indent=2, default=run._plain) + "\n")
    return out


if __name__ == "__main__":
    if "build" in sys.argv[1:] or not (OUT / "forecastElasso.parquet").exists():
        print(build())
    r = calibrate()
    for c in COLUMNS:
        x = r[c]
        for lab in ("calibration_y21", "calibration_monthly"):
            v = x[lab]
            print(f"{c} {lab}: {v['slope']:.3f} se {v['se']:.3f} [{v['lo90']:.3f}, {v['hi90']:.3f}]")
        a = x["alpha_decay"]
        print(f"{c} alpha curve {({k: round(v, 3) for k, v in a['curve'].items()})}")
        print(f"{c} kappa {a.get('kappa')} [{a.get('kappa_lo90')}, {a.get('kappa_hi90')}] "
              f"-> {x['frozen_kappa']}; score sd {x['score_sd']:.4f}")
