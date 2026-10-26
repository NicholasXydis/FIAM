# Book-construction variants of the walk-forward volneut score (lesson 96;
# user, 2026-10-26: "Whichever works best either 1,2,3"). Rule fixed before
# any book was run: each variant's E5 book runs on 2017-2020; the winner is
# the highest net annual return among books with |daily beta| <= 0.05 and
# both legs' after-beta alpha > 0 (legs_report), else the highest net return;
# baseline = the current E5 book (out/nautilus_e5_wf2). The winner alone gets
# one disclosed 2021-2026 run. Registry +3.
#
#   betamatch - volneut re-ranked within beta_60m quintiles at eom: longs and
#               shorts are opposite in score but matched in beta, so equal
#               dollars cancel the market (lesson 96 (c))
#   volscale  - volneut x ivol_capm_252d / the month's median ivol: expected
#               return scales with residual vol (Grinold-Kahn alpha = IC x
#               sigma x score; lesson 96 (a), visible on 2017-2020 too)
#   betavol   - betamatch, then volscale
# Inputs are point-in-time panel values at each eom. Calibration scale and
# kappa are re-frozen per variant by tail.calibrate (formations 2016-12..
# 2020-11), since the score's units change.
# --base month_holdable builds the same variants (plus `raw`, the walk-forward
# score untransformed) from the holdable-trained run (lesson 98) for the clean
# book race of D17.
# --e6 builds the D18 screen inputs on the all-name run: `raw` (the paper's
# score as is) and `raw_s6` / `betamatch_s6`, each the mean of the month-centred
# score over the last 6 formations the name had (past only, D18 item 3).
# Usage: python -m fiam.v4b.elasso.variants [--base month|month_holdable] [--e6]

import argparse
import json

import pandas as pd

from fiam.v4b.elasso import tail
from fiam.v4b.forecast import data

from fiam.v4b.elasso.walkforward import ROOT

SRC = ROOT / "month" / "volneut" / "forecastElasso.parquet"
COLS = ("MaInf", "Ma1")
NAMES = ("betamatch", "volscale", "betavol")


def build(name: str, base: str = "month") -> pd.DataFrame:
    if name == "raw":
        return pd.read_parquet(ROOT / base / "forecastElasso_raw.parquet", columns=["date", "permno", *COLS])
    if name == "volneut":
        return pd.read_parquet(ROOT / base / "volneut" / "forecastElasso.parquet", columns=["date", "permno", *COLS])
    f = pd.read_parquet(ROOT / base / "volneut" / "forecastElasso.parquet")
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    p = data.panel(cut=pd.Timestamp("2026-08-31"))[["permno", "eom", "beta_60m", "ivol_capm_252d"]]
    f = f.merge(p, on=["permno", "eom"], how="left")
    g = f.groupby("eom")
    if name in ("betamatch", "betavol"):
        b = f["beta_60m"].fillna(g["beta_60m"].transform("median"))
        f["bq"] = b.groupby(f["eom"]).transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
        for c in COLS:
            f[c] = 100.0 * (f.groupby(["eom", "bq"])[c].rank(pct=True) - 0.5)
    if name in ("volscale", "betavol"):
        iv = f["ivol_capm_252d"].fillna(g["ivol_capm_252d"].transform("median"))
        rel = iv / iv.groupby(f["eom"]).transform("median")
        for c in COLS:
            f[c] = f[c] * rel
    return f[["date", "permno", *COLS]]


# Mean of the month-centred score over the last k formations (this one included).
def smoothed(name: str, k: int, base: str = "month") -> pd.DataFrame:
    f = build(name, base)
    f["eom"] = pd.to_datetime(f["date"])
    for c in COLS:
        f[c] = f[c] - f.groupby("eom")[c].transform("median")
        wide = f.pivot_table(index="eom", columns="permno", values=c, aggfunc="last").sort_index()
        mean = wide.rolling(k, min_periods=1).mean().where(wide.notna())
        f[c] = mean.stack().rename(c).reindex(pd.MultiIndex.from_frame(f[["eom", "permno"]])).to_numpy()
    return f[["date", "permno", *COLS]]


def main(base: str = "month", names=NAMES) -> dict:
    rep = {}
    for name in names:
        out = ROOT / base / name
        out.mkdir(parents=True, exist_ok=True)
        if "_s" in name:
            src, k = name.rsplit("_s", 1)
            smoothed(src, int(k), base).to_parquet(out / "forecastElasso.parquet", index=False)
        elif name != "volneut":  # volneut/ is written (and calibrated) by walkforward.py
            build(name, base).to_parquet(out / "forecastElasso.parquet", index=False)
        cal = tail.calibrate(out)
        rep[name] = {c: {"scale": cal[c]["calibration_y21"]["slope"], "lo90": cal[c]["calibration_y21"]["lo90"],
                         "kappa": cal[c]["frozen_kappa"], "ic21": cal[c]["ic_decay"]["curve"]["21"]}
                     for c in tail.COLUMNS}
        print(name, json.dumps(rep[name]), flush=True)
    return rep


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--base", default="month")
    a.add_argument("--e6", action="store_true")
    args = a.parse_args()
    if args.e6:
        main("month", ("raw", "raw_s6", "betamatch_s6"))
    else:
        main(args.base, ("raw", "volneut", "betamatch") if args.base != "month" else NAMES)
