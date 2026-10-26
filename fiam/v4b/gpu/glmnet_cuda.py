# CUDA version of glmnet.elnet1: one thread block per problem (month). Thread 0
# runs glmnet's scalar control flow (coordinate update, entry order, rsq,
# convergence); every thread then applies the gradient update for its own
# column. The gradient is updated on every column at each step (no lazy
# catch-up after active sweeps); the result differs from the CPU kernel only by
# rounding. p must not exceed TPB.

import math

import numpy as np
from numba import cuda, float64, int64

from fiam.v4b.gpu.glmnet import BIG, DEVMAX, EPS, FDEV, MNLAM

TPB = 256


@cuda.jit(device=True)
def _coord(ak, gk, xvk, ab, lower):
    u = gk + ak * xvk
    v = abs(u) - ab
    if v > 0.0:
        return max(lower, min(BIG, math.copysign(v, u) / xvk))
    return 0.0


@cuda.jit
def _kernel(G, g0, xv0, ju0, lower, alf, nlam, thr, ao, lmu):
    b = cuda.blockIdx.x
    tid = cuda.threadIdx.x
    p = g0.shape[1]
    a = cuda.shared.array(TPB, float64)
    g = cuda.shared.array(TPB, float64)
    xv = cuda.shared.array(TPB, float64)
    ju = cuda.shared.array(TPB, int64)
    mm = cuda.shared.array(TPB, int64)
    ia = cuda.shared.array(TPB, int64)
    sc = cuda.shared.array(8, float64)  # 0 delta, 1 dlx, 2 rsq, 3 alm, 4 rsq0
    si = cuda.shared.array(8, int64)  # 1 nin, 2 iz, 3 stop, 6 jz
    if tid < p:
        a[tid] = 0.0
        g[tid] = g0[b, tid]
        xv[tid] = xv0[b, tid]
        ju[tid] = ju0[b, tid]
        mm[tid] = 0
        ia[tid] = 0
    if tid == 0:
        si[1] = 0
        si[2] = 0
        si[3] = 0
        sc[2] = 0.0
    cuda.syncthreads()
    for m in range(nlam):
        if tid == 0:
            if m == 0:
                sc[3] = BIG
            elif m == 1:
                mx = 0.0
                for j in range(p):
                    if ju[j] != 0:
                        mx = max(mx, abs(g[j]))
                sc[3] = alf[b] * mx
            else:
                sc[3] = sc[3] * alf[b]
            sc[4] = sc[2]
            si[6] = 1
        cuda.syncthreads()
        ab = sc[3]
        while True:
            full = not (si[2] == 1 and si[6] == 1)
            cuda.syncthreads()
            if full:
                if tid == 0:
                    sc[1] = 0.0
                cuda.syncthreads()
                for k in range(p):
                    if tid == 0:
                        sc[0] = 0.0
                        if ju[k] != 0:
                            ak = a[k]
                            an = _coord(ak, g[k], xv[k], ab, lower)
                            if an != ak:
                                a[k] = an
                                if mm[k] == 0:
                                    si[1] += 1
                                    mm[k] = si[1]
                                    ia[si[1] - 1] = k
                                d = an - ak
                                sc[2] += d * (2.0 * g[k] - d * xv[k])
                                sc[1] = max(sc[1], xv[k] * d * d)
                                sc[0] = d
                    cuda.syncthreads()
                    d = sc[0]
                    if d != 0.0 and tid < p:
                        g[tid] -= G[b, k, tid] * d
                    cuda.syncthreads()
                conv = sc[1] < thr
                cuda.syncthreads()
                if conv:
                    break
            if tid == 0:
                si[2] = 1
            cuda.syncthreads()
            while True:
                if tid == 0:
                    sc[1] = 0.0
                cuda.syncthreads()
                nin = si[1]
                for l in range(nin):
                    k = ia[l]
                    if tid == 0:
                        sc[0] = 0.0
                        ak = a[k]
                        an = _coord(ak, g[k], xv[k], ab, lower)
                        if an != ak:
                            a[k] = an
                            d = an - ak
                            sc[2] += d * (2.0 * g[k] - d * xv[k])
                            sc[1] = max(sc[1], xv[k] * d * d)
                            sc[0] = d
                    cuda.syncthreads()
                    d = sc[0]
                    if d != 0.0 and tid < p:
                        g[tid] -= G[b, k, tid] * d
                    cuda.syncthreads()
                conv = sc[1] < thr
                cuda.syncthreads()
                if conv:
                    break
            if tid == 0:
                si[6] = 0
            cuda.syncthreads()
        if tid < p:
            ao[b, m, tid] = a[tid]
        if tid == 0:
            lmu[b] = m + 1
            if m + 1 >= MNLAM:
                if sc[2] - sc[4] < FDEV * sc[2] or sc[2] > DEVMAX:
                    si[3] = 1
        cuda.syncthreads()
        if si[3] == 1:
            break


def paths(G, g, xv, ju, lower, flmin, nlam, thr, maxit):
    B, p = g.shape
    if p > TPB:
        raise ValueError(f"p={p} exceeds {TPB} threads per block")
    alf = np.maximum(flmin, EPS) ** (1.0 / (nlam - 1))
    ao = cuda.to_device(np.zeros((B, nlam, p)))
    lmu = cuda.to_device(np.zeros(B, np.int64))
    _kernel[B, TPB](cuda.to_device(np.ascontiguousarray(G)), cuda.to_device(g), cuda.to_device(xv),
                    cuda.to_device(ju.astype(np.int64)), float(lower), cuda.to_device(alf), nlam, thr, ao, lmu)
    return ao.copy_to_host(), lmu.copy_to_host()
