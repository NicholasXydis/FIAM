# Rolling E-LASSO: the authors' monthly re-estimation carried through 2026 (D11).
#
# E-LASSO is a Fama-MacBeth method. The row dated t pairs month-t returns with
# characteristics known at eom t-1, so its coefficients use only returns
# realised by eom t, and the forecast for t+1 averages coefficients through t.
# Running the unchanged R code over 2015-2026 is therefore a real-time forecast
# at every formation, the authors' own out-of-sample design. elasso/oos.py
# froze the 2020-12 coefficients instead (D10); that froze the method itself.
#
# Labels, all fed through the same unchanged code (only the `ret` column
# differs, as in the authors' contract):
#   ret  - next-month excess return (D6 mean model);
#   up   - 1 if the return is in the month's top decile (right tail);
#   down - 1 if the return is in the month's bottom decile (left tail).
# The tail labels are the QUARCC-Black dual-head targets (Exp12 V6 C2,
# Exp15 L1: "bottom/top decile versus rest", score = long - short), estimated
# inside E-LASSO. The R code multiplies by 100, so tail forecasts are percent
# probabilities.

import subprocess
from pathlib import Path

import pandas as pd

from fiam.v4b.elasso.build_input import ghz
from fiam.v4b.elasso.forecaster import verify_code
from fiam.v4b.forecast import data

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "out" / "elasso" / "rolling"
CODE = ROOT / "external" / "elasso"
RSCRIPT = Path.home() / ".local/micromamba/envs/elasso/bin/Rscript"
CUT = pd.Timestamp("2026-08-31")
LABELS = ("ret", "up", "down")
TAIL = 0.10


# Month-t label for one variant; tails are cut within each target month.
# D13 tournament labels (fixed before any run): `resrank` = centred rank of the
# beta-adjusted return r - beta_60m * (me-weighted month mean); `up20`/`down20`
# = 20% tails of r; `resup`/`resdown` = 10% tails of the beta-adjusted return.
def label(ret: pd.Series, eom: pd.Series, kind: str, beta: pd.Series | None = None,
          me: pd.Series | None = None) -> pd.Series:
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


# The authors' input contract (build_input.main) with a later cut and a label choice.
# `keep` narrows the universe before standardising and labelling (walkforward
# --universe holdable): the model then learns only the names the book can hold.
def frame(kind: str = "ret", cut: pd.Timestamp = CUT, keep=None) -> pd.DataFrame:
    chars = data.characteristics()
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & p["ret_exc_lead1m"].notna() & (p["me"] > 0)].copy()
    if keep is not None:
        p = p[keep(p)].copy()
    ex = pd.read_parquet(data.PANEL, columns=["permno", "eom", "exchcd"], filters=[("eom", "<=", cut)])
    ex["eom"] = pd.to_datetime(ex["eom"]).astype("datetime64[ns]")
    p = p.merge(ex, on=["permno", "eom"], how="left")
    z = pd.DataFrame({c: ghz(p, c) for c in chars}, index=p.index)
    front = pd.DataFrame(
        {
            "date": (p["eom"] + pd.offsets.MonthEnd(1)).dt.date,
            "permno": p["permno"].astype("int64"),
            "exchcd": p["exchcd"].astype("float64"),
            "me": p["me"].astype("float64"),
            "ret": label(p["ret_exc_lead1m"].astype("float64"), p["eom"], kind,
                         beta=p["beta_60m"].astype("float64"), me=p["me"].astype("float64")),
        }
    )
    out = pd.concat([front, z], axis=1).sort_values(["date", "permno"], ignore_index=True)
    if pd.Timestamp(max(out["date"])) > cut:
        raise AssertionError("a target month after the cut")
    return out


# Builds the input and runs the unchanged authors' code for one label.
def run(kind: str, cut: pd.Timestamp = CUT) -> Path:
    verify_code()
    dest = BASE / kind
    (dest / "input").mkdir(parents=True, exist_ok=True)
    frame(kind, cut).to_parquet(dest / "input" / "data.parquet", index=False)
    with open(dest / "run.log", "w") as log:
        subprocess.run(
            [str(RSCRIPT), str(ROOT / "elasso" / "run_elasso.R"), str(dest / "input" / "data.parquet"),
             str(dest / "run"), str(CODE)],
            check=True, stdout=log, stderr=subprocess.STDOUT,
        )
    return dest / "run"


if __name__ == "__main__":
    import sys

    for k in sys.argv[1:] or LABELS:
        print(k, run(k))
