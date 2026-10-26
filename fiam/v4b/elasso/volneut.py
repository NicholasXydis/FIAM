# The volneut forecast (lesson 87): the resrank E-LASSO score ranked within
# its month's ivol tercile, so neither leg is a volatility sort (lesson 86).
# Written in the engine's forecast format (forecastElasso.parquet, percent
# units) so elasso/forecaster.py reads it unchanged:
#   MaInf / Ma1 = 100 * (within-tercile percentile rank - 0.5)
# Terciles of ivol_capm_252d at eom over every name with a forecast; a name
# without ivol takes the month's median. Calibration and decay are frozen by
# the same routine as the tail score (elasso/tail.calibrate: centred MZ slope
# on y21 and the alpha-decay kappa, formations 2016-12..2020-11 only).
# elasso/annual.py applies the same ranking to the annual walk-forward run.
# Usage: python -m fiam.v4b.elasso.volneut

import pandas as pd

from fiam.v4b.elasso import tail
from fiam.v4b.forecast import data
from fiam.v4b.gpu.rolling import BASE

SRC = BASE / "resrank" / "run" / "forecastElasso.parquet"
DEST = BASE / "volneut" / "run"
COLS = ("MaInf", "Ma1")


# Rows dated t (eom t-1 characteristics) -> within-tercile ranks of `cols`.
def tercile_rank(f: pd.DataFrame, cols=COLS) -> pd.DataFrame:
    f = f[["date", "permno", *cols]].copy()
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    iv = data.panel(cut=pd.Timestamp("2026-08-31"))[["permno", "eom", "ivol_capm_252d"]]
    f = f.merge(iv, on=["permno", "eom"], how="left")
    v = f["ivol_capm_252d"].fillna(f.groupby("eom")["ivol_capm_252d"].transform("median"))
    f["ivt"] = v.groupby(f["eom"]).transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
    for c in cols:
        f[c] = 100.0 * (f.groupby(["eom", "ivt"])[c].rank(pct=True) - 0.5)
    return f[["date", "permno", *cols]]


def build() -> pd.DataFrame:
    return tercile_rank(pd.read_parquet(SRC, columns=["date", "permno", *COLS]))


if __name__ == "__main__":
    f = build()
    DEST.mkdir(parents=True, exist_ok=True)
    f.to_parquet(DEST / "forecastElasso.parquet", index=False)
    cal = tail.calibrate(DEST)
    for c in tail.COLUMNS:
        print(c, cal[c]["calibration_y21"], "kappa", cal[c]["frozen_kappa"], cal[c]["kappa_identified"])
