# The assembled risk model: Sigma = B F B' + D in factor form (R§4).
#
# Dense N x N covariances are never formed. A snapshot at formation eom t
# carries exposures B (market column = hedge beta, so B'w's first entry is
# the book's beta), the H-session factor covariance F, specific variances
# d (daily), and the market Sxx behind beta's standard error. Everything in
# the snapshot was knowable at the eom close: factor returns before the
# formation session, exposures dated eom, betas ending on/before eom.

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk import covariance, exposures, factors, specific

FACTOR_HL = 84  # selected by validate.py from {42, 84}; see out/risk/report.json


# Everything build() estimates once, blind to the cutoff.
class RiskModel:
    def __init__(self, cut: pd.Timestamp = data.BLIND, factor_hl: int = FACTOR_HL):
        self.cut, self.factor_hl = cut, factor_hl
        self.exp = exposures.monthly(cut)
        self.factors, self.resid = factors.cached(cut)
        excess, mkt = beta_mod.excess_wide(cut=cut)
        self.market = mkt
        rolled = beta_mod.rolling_beta(excess, mkt["mkt_rf"])
        self.betas = beta_mod.hedge_betas(self.exp, rolled)
        self.spec_race = specific.race(self.resid, sorted(self.exp["eom"].unique()))
        self.spec = self._specific_table()

    # Winner variances at every eom, shrunk and floored, by (eom, permno).
    def _specific_table(self) -> pd.DataFrame:
        eoms = sorted(self.exp["eom"].unique())
        winner = self.spec_race["winner"]
        if winner == "har_var":
            table = specific.har_forecast(
                specific.har_features(self.resid, eoms), specific.realised_next(self.resid, eoms)
            ).rename(columns={"har_var": "spec_var"})
            # Early eoms without a HAR fit fall back to EWMA-84 (stated).
            ew = specific.ewma_at(self.resid, eoms, 84).rename(columns={"ewma84": "spec_var"})
            table = table.merge(ew, on=["eom", "permno"], how="outer", suffixes=("", "_ew"))
            table["spec_var"] = table["spec_var"].fillna(table["spec_var_ew"])
            table = table[["eom", "permno", "spec_var"]]
        else:
            hl = int(winner.removeprefix("ewma"))
            table = specific.ewma_at(self.resid, eoms, hl).rename(columns={winner: "spec_var"})
        sectors = self.exp[["eom", "permno", "sector"]]
        table = table.reset_index(drop=True)
        table["spec_var"] = specific.shrink_floor(table, "spec_var", sectors).to_numpy()
        return table.set_index(["eom", "permno"])["spec_var"]

    # Market Sxx over the beta window ending at eom (for beta's SE).
    def _sxx(self, eom: pd.Timestamp) -> float:
        m = self.market["mkt_rf"]
        window = m[m.index <= pd.Timestamp(eom)].tail(beta_mod.WINDOW)
        return float(((window - window.mean()) ** 2).sum())

    # Snapshot pieces at one formation eom (liquid names only).
    def snapshot(self, eom, horizon: int = 21) -> dict:
        eom = pd.Timestamp(eom)
        month = self.exp[self.exp["eom"] == eom]
        x, _ = exposures.design(month)
        all_sectors = [f"s_{s}" for s in sorted(self.exp["sector"].dropna().unique())]
        x = x.reindex(columns=[*all_sectors, *exposures.STYLES], fill_value=0.0)
        b = self.betas[self.betas["eom"] == eom].set_index("permno")["beta_hedge"]
        names = x.index.intersection(b.index)
        B = x.loc[names].copy()
        B.insert(0, "mkt", b.loc[names].to_numpy())
        sessions = self.factors.index
        s0 = sessions[sessions > eom][0] if (sessions > eom).any() else sessions[-1]
        F = covariance.factor_cov_horizon(self.factors, s0, self.factor_hl, horizon)
        F1 = covariance.factor_cov(self.factors, s0, self.factor_hl)
        F_daily = covariance.factor_cov_daily(self.factors, s0, self.factor_hl)
        d = self.spec.loc[eom].reindex(names)
        med = d.median()
        return {
            "eom": eom,
            "s0": s0,
            "horizon": horizon,
            "B": B,
            "F": F,
            "F1": F1,
            "F_daily": F_daily,
            "d": d.fillna(med),
            "beta": b.loc[names],
            "sxx": self._sxx(eom),
            "month": month.set_index("permno").loc[names],
        }


# Aligned (B'w, w, d) arrays for a weight vector on snapshot names.
def _aligned(snap: dict, w: pd.Series):
    B = snap["B"]
    ww = w.reindex(B.index).fillna(0.0).to_numpy(dtype=float)
    return B.to_numpy(dtype=float).T @ ww, ww, snap["d"].to_numpy(dtype=float)


# Factor exposures B'w (first entry is the book's hedge beta).
def factor_exposures(snap: dict, w: pd.Series) -> pd.Series:
    bw, _, _ = _aligned(snap, w)
    return pd.Series(bw, index=snap["B"].columns)


# Book beta and its estimation standard error sqrt(w'Sigma_e w / Sxx).
# Sigma_e uses daily (1-session) covariances; the market part is removed.
def beta_of(snap: dict, w: pd.Series) -> tuple[float, float]:
    beta = float(snap["beta"].reindex(w.index).fillna(0.0).to_numpy() @ w.to_numpy())
    bw, ww, d = _aligned(snap, w)
    F1 = snap["F1"].reindex(index=snap["B"].columns, columns=snap["B"].columns).to_numpy()
    total = float(bw @ F1 @ bw + (ww**2 * d).sum())
    market_var = float(F1[0, 0])
    nonmarket = max(total - beta**2 * market_var, float((ww**2 * d).sum()))
    return beta, float(np.sqrt(nonmarket / snap["sxx"])) if snap["sxx"] > 0 else float("nan")


# H-session variance, its factor share, and annualised vol.
def variance(snap: dict, w: pd.Series, stressed: bool = False) -> tuple[float, float]:
    bw, ww, d = _aligned(snap, w)
    F = snap["F"]
    if stressed:
        F = covariance.stressed(F)
    Fm = F.reindex(index=snap["B"].columns, columns=snap["B"].columns).to_numpy()
    factor_var = float(bw @ Fm @ bw)
    spec_var = float((ww**2 * d).sum() * snap["horizon"])
    total = factor_var + spec_var
    return total, (factor_var / total if total > 0 else float("nan"))


def daily_variance(snap: dict, w: pd.Series) -> float:
    """One-session variance from contemporaneous factors and specific risk."""
    bw, ww, d = _aligned(snap, w)
    factors = snap["F_daily"].reindex(index=snap["B"].columns, columns=snap["B"].columns).to_numpy()
    return float(bw @ factors @ bw + (ww**2 * d).sum())


def daily_vol(snap: dict, w: pd.Series) -> float:
    return float(np.sqrt(daily_variance(snap, w)))


# Annualised vol over the snapshot horizon (252 sessions a year).
def vol(snap: dict, w: pd.Series, stressed: bool = False) -> float:
    total, _ = variance(snap, w, stressed)
    return float(np.sqrt(total * 252 / snap["horizon"]))


# Marginal variance contributions d(w'Sigma w)/dw in factor form (for QP use).
def marginal(snap: dict, w: pd.Series) -> pd.Series:
    B = snap["B"]
    bw, ww, d = _aligned(snap, w)
    Fm = snap["F"].reindex(index=B.columns, columns=B.columns).to_numpy()
    grad = 2 * (B.to_numpy(dtype=float) @ (Fm @ bw) + ww * d * snap["horizon"])
    return pd.Series(grad, index=B.index)
