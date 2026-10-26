# Accuracy upgrades on top of risk/model.py, so the optimizer cannot buy vol
# or beta it does not see (user, 2026-10-26: "our risk models MUST be very
# accurate"). Lesson 42: book vol was understated 30-50%, worst in 2018/2020
# and where specific risk dominates, because EWMA lags regimes and residuals
# co-move in stress, which a diagonal D cannot represent. Two standard fixes,
# fixed parameters, nothing searched:
#
#   vra  - volatility regime adjustment (Barra USE4, Menchero et al. 2011):
#          lambda^2_t = EWMA_42 of the cross-sectional mean of z^2, where z
#          is each day's return over its own ex-ante vol. Factor z use the
#          model's factor EWMA (hl FACTOR_HL); specific z use the residual
#          EWMA (hl of the specific-race winner). F is scaled by lambda_F^2,
#          D and the residual factors by lambda_S^2, both read the day
#          before the formation session.
#   pca  - K statistical factors of the factor-model residuals (Connor &
#          Korajczyk 1988 APT; USE4 "blind factors"): EWMA (hl 84) residual
#          covariance over the 252 sessions before formation, top K = 5
#          components, eigenvalues less the mean of the rest (noise floor).
#          They enter B as extra columns with unit-variance factors, and D
#          keeps the share of each name's residual variance they leave.
#   beta_cal - predicted-to-realised hedge-beta map, expanding window on
#          earlier months only (risk/beta_cal.py).
#
# Torch on the GPU when present (CUDA on Modal), else CPU; float64 throughout.

import numpy as np
import pandas as pd
import torch

from fiam.v4b.risk import model, specific

DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")
VRA_HL = 42
PCA_K, PCA_WINDOW, PCA_HL = 5, 252, 84


def _t(x) -> torch.Tensor:
    return torch.as_tensor(np.array(x, dtype=float), dtype=torch.float64, device=DEV)


# Ex-ante EWMA variance at each day from rows strictly before it; NaN until
# min_periods observations. x [T, N] with NaN for missing.
def ewma_var_before(x: torch.Tensor, hl: int, min_periods: int = 21) -> torch.Tensor:
    a = 1 - 0.5 ** (1 / hl)
    T, N = x.shape
    s = torch.zeros(N, dtype=x.dtype, device=x.device)
    wsum = torch.zeros_like(s)
    n = torch.zeros_like(s)
    out = torch.full((T, N), float("nan"), dtype=x.dtype, device=x.device)
    for t in range(T):
        ok = n >= min_periods
        out[t, ok] = s[ok] / wsum[ok]
        v = x[t]
        m = ~torch.isnan(v)
        s = torch.where(m, (1 - a) * s + a * torch.nan_to_num(v) ** 2, s)
        wsum = torch.where(m, (1 - a) * wsum + a, wsum)
        n = n + m
    return out


# lambda^2 known at the close of each day (applies to forecasts made after it).
# A zero (|x| < 1e-12) is a return that was not estimated (a sector factor
# before the sector has names) and counts as missing.
def vra_path(x: pd.DataFrame, hl: int, vra_hl: int = VRA_HL) -> pd.Series:
    xt = _t(x.mask(x.abs() < 1e-12).to_numpy())
    var = ewma_var_before(xt, hl)
    z2 = xt**2 / var
    ok = ~torch.isnan(z2)
    cs = torch.where(ok, z2, torch.zeros_like(z2)).sum(1) / ok.sum(1).clamp(min=1)
    has = ok.sum(1) > 0
    a = 1 - 0.5 ** (1 / vra_hl)
    lam, w, out = 0.0, 0.0, np.full(len(x), np.nan)
    c, h = cs.cpu().numpy(), has.cpu().numpy()
    for t in range(len(x)):
        if h[t]:
            lam, w = (1 - a) * lam + a * c[t], (1 - a) * w + a
        if w > 0:
            out[t] = lam / w
    return pd.Series(out, index=x.index)


# Top-K residual components on `names` from the PCA_WINDOW sessions before s0.
def residual_factors(resid: pd.DataFrame, s0, names: pd.Index, k: int = PCA_K):
    block = resid[resid.index < pd.Timestamp(s0)].tail(PCA_WINDOW).reindex(columns=names)
    x = _t(block.to_numpy())
    x = torch.nan_to_num(x)
    T = x.shape[0]
    age = torch.arange(T - 1, -1, -1, dtype=torch.float64, device=DEV)
    w = 0.5 ** (age / PCA_HL)
    w = w / w.sum()
    xs = x * torch.sqrt(w)[:, None]
    _, sv, vt = torch.linalg.svd(xs, full_matrices=False)
    ev = sv**2  # eigenvalues of the weighted residual covariance (daily)
    noise = ev[k:].mean() if len(ev) > k else torch.tensor(0.0, dtype=torch.float64, device=DEV)
    lam = (ev[:k] - noise).clamp(min=0)
    V = vt[:k].T  # [N, k] unit loadings
    load = V * torch.sqrt(lam)[None, :]  # exposures on unit-variance factors
    tot = (xs**2).sum(0)  # each name's weighted residual variance
    share = torch.where(tot > 0, (load**2).sum(1) / tot, torch.zeros_like(tot)).clamp(0, 0.9)
    cols = [f"pca{j + 1}" for j in range(k)]
    return (pd.DataFrame(load.cpu().numpy(), index=names, columns=cols),
            pd.Series(share.cpu().numpy(), index=names))


class EnhancedRiskModel(model.RiskModel):
    def __init__(self, *args, vra: bool = True, pca: int = PCA_K, beta_cal: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.vra, self.pca, self.beta_cal = vra, pca, beta_cal
        from fiam.v4b.risk import beta_cal as bc

        self.beta_maps = bc.monthly_maps(self)
        if vra:
            self.lam_f = vra_path(self.factors, self.factor_hl)
            winner = self.spec_race["winner"]
            spec_hl = int(winner.removeprefix("ewma")) if winner.startswith("ewma") else 84
            self.lam_s = vra_path(self.resid, spec_hl)

    def _lam(self, path: pd.Series, s0) -> float:
        before = path[path.index < pd.Timestamp(s0)].dropna()
        return float(before.iloc[-1]) if len(before) else 1.0

    def snapshot(self, eom, horizon: int = 21) -> dict:
        snap = super().snapshot(eom, horizon)
        if snap["F"] is None or snap["F1"] is None:
            return snap
        lf = self._lam(self.lam_f, snap["s0"]) if self.vra else 1.0
        ls = self._lam(self.lam_s, snap["s0"]) if self.vra else 1.0
        F, F1, F_daily, d, B = (snap["F"] * lf, snap["F1"] * lf,
                                snap["F_daily"] * lf, snap["d"] * ls, snap["B"].copy())
        beta, ab = snap["beta"], None
        if self.beta_cal:
            from fiam.v4b.risk import beta_cal as bc

            ab = bc.map_at(self.beta_maps, snap["s0"])
            if ab is not None:
                beta = ab[0] + ab[1] * beta
                B["mkt"] = beta.reindex(B.index).to_numpy()
        if self.pca:
            load, share = residual_factors(self.resid, snap["s0"], B.index, self.pca)
            d = d * (1 - share.reindex(d.index).fillna(0.0))
            B = pd.concat([B, load], axis=1)
            cols = list(B.columns)
            eye = pd.DataFrame(np.eye(self.pca), index=load.columns, columns=load.columns)
            F = _block(F, eye * horizon * ls, cols)
            F1 = _block(F1, eye * ls, cols)
            F_daily = _block(F_daily, eye * ls, cols)
        return snap | {"B": B, "F": F, "F1": F1, "F_daily": F_daily, "d": d, "beta": beta,
                       "beta_map": ab, "lam_f": lf, "lam_s": ls}


def _block(a: pd.DataFrame, b: pd.DataFrame, cols: list) -> pd.DataFrame:
    out = pd.DataFrame(0.0, index=cols, columns=cols)
    out.loc[a.index, a.columns] = a.to_numpy()
    out.loc[b.index, b.columns] = b.to_numpy()
    return out
