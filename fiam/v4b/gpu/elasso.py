# Port of the authors' E-LASSO (external/elasso, programMainElasso.R and the six
# files it sources), every month solved at once on CPU (numba) or CUDA.
#
# Same input contract as run_elasso.R: columns date, permno, exchcd, me, ret,
# then the characteristics; ret is multiplied by 100 first, as the R code does.
# Same outputs as the R run directory (parquet): coefLasso, forecastSlasso,
# coefUniIntercept, coefUniSlope, coefGr, forecastClasso, coefEncompass,
# forecastElasso.
#
# One deliberate difference (D13): programForecastClasso.R does
# `tCoef = as.numeric(tCoef[-1]); tCoefGr[tIndex] = tCoef[-1]`, dropping the
# first slope a second time; R recycles the shorter vector, so characteristic i
# gets characteristic i+1's C-LASSO weight and the last gets the second's.
# Here each slope stays with its own characteristic. gpu/verify.py passes
# `gr_assign` to rebuild R's assignment only to prove the rest of the port
# against the existing R outputs.
#
# Usage: python -m fiam.v4b.gpu.elasso <input.parquet> <out_dir> [--backend cpu|cuda]

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.gpu import glmnet

FRONT = ["date", "permno", "exchcd", "me", "ret"]
MA = (1, 36, 60, 120, math.inf)
MA_NAMES = [f"Ma{int(s)}" if s != math.inf else "MaInf" for s in MA]


class Months:
    # Rows grouped by date in file order, padded to a common length.
    def __init__(self, data: pd.DataFrame, chars: list[str]):
        self.dates = pd.DatetimeIndex(pd.unique(data["date"]))
        d = data["date"].to_numpy()
        self.rows = [np.flatnonzero(d == x) for x in self.dates]
        self.n = np.array([len(g) for g in self.rows])
        T, N, p = len(self.rows), int(self.n.max()), len(chars)
        vals = data[chars].to_numpy(float)
        ret, me = data["ret"].to_numpy(float), data["me"].to_numpy(float)
        self.Z = np.zeros((T, N, p))
        self.y = np.zeros((T, N))
        self.me = np.zeros((T, N))
        self.na = np.zeros((T, p), dtype=bool)
        for t, g in enumerate(self.rows):
            z = vals[g]
            self.na[t] = np.isnan(z).any(0)
            self.Z[t, : len(g)] = np.nan_to_num(z)
            self.y[t, : len(g)] = ret[g]
            self.me[t, : len(g)] = me[g]
        self.mask = np.arange(N)[None, :] < self.n[:, None]
        # valueWeight: me / sum(me), rescaled to mean one over the month's rows.
        w = self.me / self.me.sum(1, keepdims=True)
        self.vw = np.where(self.mask, w / (w.sum(1, keepdims=True) / self.n[:, None]), 0.0)


def usable_pairs(na: np.ndarray) -> np.ndarray:
    # tIndex: no NA in month t and (for t < T) month t+1.
    ok = ~na
    return ok & np.concatenate([ok[1:], np.ones_like(ok[:1])], 0)


def wls_uni(Z, y, vw):
    # lm(ret ~ z_j, weights = vw) for every month and characteristic at once.
    sw = vw.sum(1, keepdims=True)
    zm = np.einsum("bn,bnp->bp", vw, Z) / sw
    ym = (vw * y).sum(1, keepdims=True) / sw
    zc = Z - zm[:, None, :]
    sxx = np.einsum("bn,bnp->bp", vw, zc * zc)
    sxy = np.einsum("bn,bnp->bp", vw * (y - ym), zc)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(sxx > 0, sxy / sxx, np.nan)
    return ym - slope * zm, slope


def window_mean(x: np.ndarray, t: int, size) -> np.ndarray:
    # computeAvg(x[1:t, ], size) with mean(..., na.rm = TRUE).
    lo = 0 if (size == math.inf or t + 1 < size) else t + 1 - int(size)
    blk = x[lo: t + 1]
    ok = ~np.isnan(blk)
    c = ok.sum(0)
    with np.errstate(invalid="ignore"):
        return np.where(c > 0, np.where(ok, blk, 0.0).sum(0) / np.maximum(c, 1), np.nan)


def run(data: pd.DataFrame, gr_assign=None, backend: str = "cpu") -> dict[str, pd.DataFrame]:
    data = data.reset_index(drop=True).copy()
    data["date"] = pd.to_datetime(data["date"])
    chars = [c for c in data.columns if c not in FRONT]
    data["ret"] = 100 * data["ret"]
    M = Months(data, chars)
    T, p = len(M.dates), len(chars)
    use = usable_pairs(M.na)
    front = data[FRONT]
    out = {}

    # Step 1 - S-LASSO: monthly LASSO (AICc), then averaged coefficients.
    path = glmnet.lasso_path(M.Z, M.y, M.vw, use, M.n, backend=backend)
    a0, beta = glmnet.aicc_select(path, M.Z, M.y, M.vw, M.n)
    coef = np.concatenate([a0[:, None], np.where(use, beta, np.nan)], 1)
    out["coefLasso"] = pd.DataFrame(coef, columns=["intercept", *chars]).assign(date=M.dates.date)[["date", "intercept", *chars]]
    fs = []
    for t in range(T - 1):
        idx = use[t]
        z = M.Z[t + 1, : M.n[t + 1]][:, idx]
        cols = {}
        for size, name in zip(MA, MA_NAMES):
            c = coef[t] if size == 1 else window_mean(coef, t, size)
            cols[name] = c[0] + z @ c[1:][idx]
        fs.append(front.iloc[M.rows[t + 1]].reset_index(drop=True).assign(**cols))
    slasso = pd.concat(fs, ignore_index=True)
    out["forecastSlasso"] = slasso

    # Step 2 - C-LASSO: univariate WLS, Ma1 univariate forecasts, nonnegative
    # LASSO (AICc) on the forecasts, mean of the selected forecasts.
    inter, slope = wls_uni(M.Z, M.y, M.vw)
    inter, slope = np.where(use, inter, np.nan), np.where(use, slope, np.nan)
    out["coefUniIntercept"] = pd.DataFrame(inter, columns=chars).assign(date=M.dates.date)[["date", *chars]]
    out["coefUniSlope"] = pd.DataFrame(slope, columns=chars).assign(date=M.dates.date)[["date", *chars]]
    U = inter[:-1, None, :] + slope[:-1, None, :] * M.Z[1:]  # forecastUni for months 1..T-1
    Tg = T - 1
    guse = usable_pairs(np.isnan(U[:, 0, :]))
    maskg = M.mask[1:]
    Ug = np.where(maskg[:, :, None], np.nan_to_num(U), 0.0)
    yg, vwg, ng = M.y[1:], M.vw[1:], M.n[1:]
    gpath = glmnet.lasso_path(Ug, yg, vwg, guse, ng, lower=0.0, backend=backend)
    _, gbeta = glmnet.aicc_select(gpath, Ug, yg, vwg, ng)
    coefgr = np.full((Tg, p), np.nan)
    for t in range(Tg):
        idx = np.flatnonzero(guse[t])
        s = gbeta[t, idx]  # slopes in tIndex order
        coefgr[t, idx] = s if gr_assign is None else gr_assign(s)
    out["coefGr"] = pd.DataFrame(coefgr, columns=chars).assign(date=M.dates[1:].date)[["date", *chars]]
    fc = []
    for t in range(Tg - 1):
        idx = np.flatnonzero(guse[t])
        sel = idx[coefgr[t, idx] != 0]
        n1 = ng[t + 1]
        f = np.zeros(n1) if len(sel) == 0 else U[t + 1, :n1][:, sel].mean(1)
        fc.append(front.iloc[M.rows[t + 2]].reset_index(drop=True).assign(forecast=f))
    classo = pd.concat(fc, ignore_index=True)
    out["forecastClasso"] = classo

    # Step 3 - E-LASSO: encompassing weight of C-LASSO over S-LASSO (MaInf).
    cdates = pd.DatetimeIndex(pd.unique(classo["date"]))
    s_by = dict(tuple(slasso.groupby("date", sort=False)))
    c_by = dict(tuple(classo.groupby("date", sort=False)))
    lam1 = np.zeros(len(cdates))
    for t, d in enumerate(cdates):
        A, Bc = s_by[d], c_by[d]
        w = A["me"].to_numpy() / A["me"].sum()
        eA = A["ret"].to_numpy() - A["MaInf"].to_numpy()
        dd = eA - (Bc["ret"].to_numpy() - Bc["forecast"].to_numpy())
        dm, am = (w * dd).sum(), (w * eA).sum()
        lam1[t] = min(max((w * (dd - dm) * (eA - am)).sum() / (w * (dd - dm) ** 2).sum(), 0.0), 1.0)
    enc = np.zeros((len(cdates), len(MA)))
    for t in range(len(cdates)):
        for i, size in enumerate(MA):
            lo = 0 if (size == math.inf or t + 1 < size) else t + 1 - int(size)
            enc[t, i] = lam1[t] if size == 1 else lam1[lo: t + 1].mean()
    out["coefEncompass"] = pd.DataFrame(enc, columns=MA_NAMES).assign(date=cdates.date)[["date", *MA_NAMES]]
    fe = []
    for t in range(len(cdates) - 1):
        A, Bc = s_by[cdates[t + 1]], c_by[cdates[t + 1]]
        cols = {name: (1 - enc[t, i]) * A["MaInf"].to_numpy() + enc[t, i] * Bc["forecast"].to_numpy()
                for i, name in enumerate(MA_NAMES)}
        fe.append(A[FRONT].reset_index(drop=True).assign(**cols))
    out["forecastElasso"] = pd.concat(fe, ignore_index=True)
    return out


def write(out: dict[str, pd.DataFrame], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for k, v in out.items():
        v.to_parquet(dest / f"{k}.parquet", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--backend", default="cpu", choices=["cpu", "cuda"])
    a = ap.parse_args()
    write(run(pd.read_parquet(a.input), backend=a.backend), a.out)
