# Port of glmnet's Gaussian LASSO path (alpha = 1, intercept, weights,
# standardize = FALSE, covariance updating), the routine E-LASSO calls through
# glmnet(x, y, weights, alpha = 1, standardize = FALSE [, lower.limits = 0]).
#
# It follows glmnet's `standard` + `elnet1` step for step so the iterates, not
# only the optimum, match: weights normalised to sum one; x and y centred by
# their weighted means; y scaled by its weighted sd; lambda_1 = "big" (all
# zero), lambda_2 = alf * max|g|, then geometric with alf = flmin^(1/(nlam-1));
# each lambda alternates active-set sweeps (in entry order, gradient updated
# on the active set, the rest caught up afterwards) and full sweeps until a
# full sweep moves no coefficient by more than thr in xv * delta^2; the path
# stops after mnlam lambdas once the deviance ratio gains less than
# fdev * rsq or exceeds devmax. glmnet.control defaults: fdev 1e-5, devmax
# 0.999, eps 1e-6, big 9.9e35, mnlam 5; glmnet defaults: nlambda 100,
# lambda.min.ratio 1e-4 if nobs > nvars else 0.01, thresh 1e-7.
#
# Backends: "cpu" (numba, months in parallel) and "cuda" (numba.cuda, one
# thread block per month; gpu/glmnet_cuda.py). Same arithmetic, same order.

from dataclasses import dataclass

import numpy as np
from numba import njit, prange

BIG = 9.9e35
FDEV, DEVMAX, EPS, MNLAM = 1e-5, 0.999, 1e-6, 5
NLAM, THRESH, MAXIT = 100, 1e-7, 100000


@dataclass
class Path:
    beta: np.ndarray  # [B, L, p] original-scale slopes (0 for unusable columns)
    a0: np.ndarray  # [B, L] intercepts
    lmu: np.ndarray  # [B] number of lambdas fitted


@njit(cache=True)
def _coord(ak, gk, xvk, ab, lower):
    u = gk + ak * xvk
    v = abs(u) - ab
    if v > 0.0:
        return max(lower, min(BIG, np.copysign(v, u) / xvk))
    return 0.0


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
            for l in range(nin):
                da[l] = a[ia[l]]
            while True:
                nlp += 1
                dlx = 0.0
                for l in range(nin):
                    k = ia[l]
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
            for l in range(nin):
                da[l] = a[ia[l]] - da[l]
            for j in range(p):
                if mm[j] != 0 or not ju[j]:
                    continue
                s = 0.0
                for l in range(nin):
                    s += da[l] * G[j, ia[l]]
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


def standardize(X, y, w):
    # glmnet `standard` with isd = 0, intr = 1. X [B, N, p], padding rows w = 0.
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


def lasso_path(X, y, w, usable, n, lower: float = -BIG, nlam: int = NLAM, thr: float = THRESH,
               backend: str = "cpu") -> Path:
    G, g, xv, xm, ym, ys = standardize(X, y, w)
    ju = usable & (xv > 0)
    nvars = usable.sum(1)
    flmin = np.where(n > nvars, 1e-4, 1e-2)
    if backend == "cuda":
        from fiam.v4b.gpu import glmnet_cuda

        ao, lmu = glmnet_cuda.paths(G, g, xv, ju, lower, flmin, nlam, thr, MAXIT)
    else:
        ao, lmu = _paths_cpu(G, g, xv, ju, lower, flmin, nlam, thr, MAXIT)
    if (lmu < 0).any():
        raise RuntimeError("glmnet port: maxit reached")
    beta = ao * ys[:, None, None]
    a0 = ym[:, None] - np.einsum("blp,bp->bl", beta, xm)
    return Path(beta=beta, a0=a0, lmu=lmu)


def aicc_select(path: Path, X, y, vw, nobs):
    # E-LASSO's estimateLasso: AICc over the fitted lambdas, first minimum.
    # vw = valueWeight (weights scaled to mean one), zero on padding rows.
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
