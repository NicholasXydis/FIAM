# glmnet's Gaussian LASSO path, step for step, in numba.

from dataclasses import dataclass

import numpy as np
from numba import njit, prange

BIG = 9.9e35
FDEV, DEVMAX, EPS, MNLAM = 1e-5, 0.999, 1e-6, 5
NLAM, THRESH, MAXIT = 100, 1e-7, 100000


# One path per month: slopes, intercepts and lambdas fitted.
@dataclass
class Path:
    beta: np.ndarray  # [B, L, p] original-scale slopes (0 for unusable columns)
    a0: np.ndarray  # [B, L] intercepts
    lmu: np.ndarray  # [B] number of lambdas fitted


# One coordinate's soft-thresholded update, inside its bounds.
@njit(cache=True)
def _coord(ak, gk, xvk, ab, lower):
    u = gk + ak * xvk
    v = abs(u) - ab
    if v > 0.0:
        return max(lower, min(BIG, np.copysign(v, u) / xvk))
    return 0.0


# glmnet's elnet1: the whole lambda path for one month.
@njit(cache=True)
def elnet1(G, g0, xv, ju, lower, flmin, nlam, thr, maxit):
    p = g0.shape[0]
    g = g0.copy()
    a = np.zeros(p)
    mm = np.zeros(p, np.int64)
    ia = np.zeros(p, np.int64)
    da = np.zeros(p)
    ao = np.zeros((nlam, p))
    nin = 0
    rsq = 0.0
    iz = 0
    nlp = 0
    lmu = 0
    alf = max(flmin, EPS) ** (1.0 / (nlam - 1))
    alm = 0.0
    for m in range(nlam):
        if m == 0:
            alm = BIG
        elif m == 1:
            alm = 0.0
            for j in range(p):
                if ju[j]:
                    alm = max(alm, abs(g[j]))
            alm = alf * alm / max(1.0, 1e-3)
        else:
            alm = alm * alf
        ab = alm
        rsq0 = rsq
        jz = 1
        while True:
            if not (iz == 1 and jz == 1):
                nlp += 1
                dlx = 0.0
                for k in range(p):
                    if not ju[k]:
                        continue
                    ak = a[k]
                    a[k] = _coord(ak, g[k], xv[k], ab, lower)
                    if a[k] == ak:
                        continue
                    if mm[k] == 0:
                        nin += 1
                        mm[k] = nin
                        ia[nin - 1] = k
                    d = a[k] - ak
                    rsq += d * (2.0 * g[k] - d * xv[k])
                    dlx = max(xv[k] * d * d, dlx)
                    for j in range(p):
                        if ju[j]:
                            g[j] -= G[j, k] * d
                if dlx < thr:
                    break
                if nlp > maxit:
                    return ao, -1
            iz = 1
            for li in range(nin):
                da[li] = a[ia[li]]
            while True:
                nlp += 1
                dlx = 0.0
                for li in range(nin):
                    k = ia[li]
                    ak = a[k]
                    a[k] = _coord(ak, g[k], xv[k], ab, lower)
                    if a[k] == ak:
                        continue
                    d = a[k] - ak
                    rsq += d * (2.0 * g[k] - d * xv[k])
                    dlx = max(xv[k] * d * d, dlx)
                    for jj in range(nin):
                        j = ia[jj]
                        g[j] -= G[j, k] * d
                if dlx < thr:
                    break
                if nlp > maxit:
                    return ao, -1
            for li in range(nin):
                da[li] = a[ia[li]] - da[li]
            for j in range(p):
                if mm[j] != 0 or not ju[j]:
                    continue
                s = 0.0
                for li in range(nin):
                    s += da[li] * G[j, ia[li]]
                g[j] -= s
            jz = 0
        for j in range(p):
            ao[m, j] = a[j]
        lmu = m + 1
        if m + 1 < MNLAM:
            continue
        if rsq - rsq0 < FDEV * rsq:
            break
        if rsq > DEVMAX:
            break
    return ao, lmu


# Every month's path at once, months spread over the threads.
@njit(parallel=True, cache=True)
def _paths_cpu(G, g, xv, ju, lower, flmin, nlam, thr, maxit):
    B, p = g.shape
    ao = np.zeros((B, nlam, p))
    lmu = np.zeros(B, np.int64)
    for b in prange(B):
        o, n = elnet1(G[b], g[b], xv[b], ju[b], lower, flmin[b], nlam, thr, maxit)
        ao[b] = o
        lmu[b] = n
    return ao, lmu


# glmnet `standard` with isd = 0, intr = 1; padding rows have w = 0.
def standardize(X, y, w):
    w = w / w.sum(1, keepdims=True)
    xm = np.einsum("bn,bnp->bp", w, X)
    ym = (w * y).sum(1)
    B, _, p = X.shape
    G = np.empty((B, p, p))
    g = np.empty((B, p))
    ys = np.empty(B)
    for b in range(B):
        v = np.sqrt(w[b])[:, None]
        xc = v * (X[b] - xm[b])
        yc = v[:, 0] * (y[b] - ym[b])
        ys[b] = np.sqrt(yc @ yc)
        yc = yc / ys[b]
        G[b] = xc.T @ xc
        g[b] = xc.T @ yc
    xv = np.ascontiguousarray(np.diagonal(G, axis1=1, axis2=2))
    return G, g, xv, xm, ym, ys


# The LASSO path of every month, back on the original scale.
def lasso_path(X, y, w, usable, n, lower: float = -BIG, nlam: int = NLAM,
               thr: float = THRESH) -> Path:  # fmt: skip
    G, g, xv, xm, ym, ys = standardize(X, y, w)
    ju = usable & (xv > 0)
    nvars = usable.sum(1)
    flmin = np.where(n > nvars, 1e-4, 1e-2)
    ao, lmu = _paths_cpu(G, g, xv, ju, lower, flmin, nlam, thr, MAXIT)
    if (lmu < 0).any():
        raise RuntimeError("glmnet port: maxit reached")
    beta = ao * ys[:, None, None]
    a0 = ym[:, None] - np.einsum("blp,bp->bl", beta, xm)
    return Path(beta=beta, a0=a0, lmu=lmu)


# estimateLasso: AICc over the fitted lambdas, first minimum.
def aicc_select(path: Path, X, y, vw, nobs):
    B, L, p = path.beta.shape
    a0 = np.empty(B)
    beta = np.empty((B, p))
    for b in range(B):
        n = int(nobs[b])
        lm = int(path.lmu[b])
        bb = path.beta[b, :lm]
        resid = y[b, :n, None] - (path.a0[b, None, :lm] + X[b, :n] @ bb.T)
        mse = (vw[b, :n, None] * resid * resid).mean(0)
        df = (bb != 0).sum(1).astype(float)
        df = np.where(bb.sum(1) == 0, 0.0, df)
        aicc = n * np.log(mse) + 2 * df * n / (n - df)
        k = int(np.argmin(aicc))
        a0[b], beta[b] = path.a0[b, k], bb[k]
    return a0, beta
