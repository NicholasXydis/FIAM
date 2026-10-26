# Group ridge with empirical-Bayes family penalties (R§3).
# Baseline only: the forecaster is E-LASSO (DECISIONS.md D6, v4b/elasso/).

from dataclasses import dataclass

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

# Families cut from training-only correlations; fixed before any fit.
FAMILIES = 12


# Characteristic families from training rows: average-linkage on 1-|rho|.
def families(x: np.ndarray, k: int = FAMILIES) -> np.ndarray:
    rho = np.corrcoef(x, rowvar=False)
    rho = np.nan_to_num(rho, nan=0.0)
    dist = 1 - np.abs(rho)
    np.fill_diagonal(dist, 0.0)
    tree = linkage(squareform(dist, checks=False), method="average")
    return fcluster(tree, k, criterion="maxclust") - 1


# Sufficient statistics of the month-weighted least-squares problem.
@dataclass
class Stats:
    xx: np.ndarray
    xy: np.ndarray
    yy: float
    months: int


# X'WX, X'Wy and y'Wy with weights that sum to one per month.
def stats(x: np.ndarray, y: np.ndarray, w: np.ndarray, months: int) -> Stats:
    xw = x * w[:, None]
    return Stats(xx=xw.T @ x, xy=xw.T @ y, yy=float((w * y) @ y), months=months)


# The fitted model: coefficients, penalties and their evidence.
@dataclass
class Fit:
    theta: np.ndarray
    lam: np.ndarray
    tau2: np.ndarray
    sigma2: float
    groups: np.ndarray
    df: float


# EM for tau_g^2 and sigma^2, each month one observation (T_eff, R§3).
def empirical_bayes(s: Stats, groups: np.ndarray, iters: int = 500, tol: float = 1e-10) -> Fit:
    g = groups.max() + 1
    size = np.bincount(groups, minlength=g)
    tau2 = np.full(g, 1e-4)
    sigma2 = s.yy / s.months
    for _ in range(iters):
        prec = s.xx / sigma2 + np.diag(1 / tau2[groups])
        cov = np.linalg.inv(prec)
        theta = cov @ s.xy / sigma2
        new_tau2 = np.maximum(
            np.bincount(groups, weights=theta**2 + np.diag(cov), minlength=g) / size, 1e-12
        )
        resid = s.yy - 2 * theta @ s.xy + theta @ s.xx @ theta
        new_sigma2 = max((resid + np.trace(s.xx @ cov)) / s.months, 1e-12)
        done = (
            np.max(np.abs(np.log(new_tau2 / tau2))) < tol and abs(np.log(new_sigma2 / sigma2)) < tol
        )
        tau2, sigma2 = new_tau2, new_sigma2
        if done:
            break
    lam = sigma2 / tau2[groups]
    return solve(s, lam, groups, tau2, sigma2)


# Coefficients for given penalties, with effective degrees of freedom.
def solve(s: Stats, lam: np.ndarray, groups, tau2=None, sigma2=float("nan")) -> Fit:
    a = s.xx + np.diag(lam)
    theta = np.linalg.solve(a, s.xy)
    df = float(np.trace(np.linalg.solve(a, s.xx)))
    tau2 = np.full(groups.max() + 1, np.nan) if tau2 is None else tau2
    return Fit(theta=theta, lam=lam, tau2=tau2, sigma2=sigma2, groups=groups, df=df)


# The same family shape with every penalty times m.
def scaled(s: Stats, base: Fit, m: float) -> Fit:
    return solve(s, base.lam * m, base.groups, base.tau2, base.sigma2)


# Deviation penalty over family-mean penalty; fixed before any fit.
DEVIATION_RATIO = 10.0


# Each feature's sign on its family's first principal component (no labels).
def orientations(x: np.ndarray, groups: np.ndarray) -> np.ndarray:
    signs = np.ones(x.shape[1])
    for g in np.unique(groups):
        cols = np.flatnonzero(groups == g)
        if len(cols) < 2:
            continue
        c = np.cov(x[:, cols], rowvar=False)
        vec = np.linalg.eigh(c)[1][:, -1]
        vec = vec if vec.sum() >= 0 else -vec
        signs[cols] = np.where(vec >= 0, 1.0, -1.0)
    return signs


# Family loading matrix S: x @ S is each family's oriented average.
def loadings(groups: np.ndarray, signs: np.ndarray) -> np.ndarray:
    g = groups.max() + 1
    s = np.zeros((len(groups), g))
    s[np.arange(len(groups)), groups] = signs
    return s / np.maximum(np.abs(s).sum(axis=0), 1)


# Hierarchical design: theta = S beta + delta, so features are [x S, x].
def hierarchical(x: np.ndarray, s: np.ndarray) -> np.ndarray:
    return np.hstack([x @ s, x])


# Penalties for [beta, delta, extras] on a common scale c.
def penalties(
    scale: float,
    families: int,
    features: int,
    extras: int = 0,
    ratio: float = DEVIATION_RATIO,
    extra: float = 1e-3,
) -> np.ndarray:
    return np.concatenate(
        [np.full(families, scale), np.full(features, scale * ratio), np.full(extras, scale * extra)]
    )
