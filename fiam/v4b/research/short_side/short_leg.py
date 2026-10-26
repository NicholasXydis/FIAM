# Short-leg P&L under the opposite-direction (upside) interval rule.
#
# Profit is reported for the SHORT position: +x% means the shorted names fell
# x% relative to their benchmark. Shortable pool (cap >= $500m), one month hold.
#   res  : beta + GICS-sector residual (what a beta/sector-hedged book earns)
#   rel  : minus the pool's equal-weight mean (market-hedged, no sector hedge)
# Rules (fixed before running; validation decides, OOS is diagnostic):
#   plain_blend : bottom 10% of the 50/50 rank blend (mean + tail E-LASSO)
#   plain_mean  : bottom 10% of the mean E-LASSO
#   ub          : from the blend's bottom 30%, the third with the lowest upper
#                 bound UB = mu + 1.645 * s_up (95% one-sided interval)
#   mu_per_sup  : from the blend's bottom 30%, the third with the most negative
#                 mu / s_up (expected short profit per unit of upside risk)
#   no_jump     : bottom 10% of the blend minus the top tercile of p_up
# s_up = sqrt(sigma^2 + p_up * J^2): sigma = ivol_capm_252d * sqrt(21), p_up =
# predicted +20% relative-jump probability (risk/jumps.py, annual refits),
# J = 0.33 (mean relative return given an up-jump, LESSONS 63, validation).
# mu = real-time calibrated combined forecast (encompass.py), in return units.
# Weights: equal, and inverse s_up (each name gets the same upside risk).
import sys

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
from fiam.v4b.research.short_side.encompass import forecasts

J_UP = 0.33
Z = 1.645


def calibrated(f: pd.DataFrame) -> pd.Series:
    # Real-time MZ: month-e value-weighted slope of ret on enc, averaged over realised months.
    eoms = np.sort(f["eom"].unique())
    a, b, mu = [], [], pd.Series(np.nan, index=f.index)
    for k, e in enumerate(eoms):
        d = f[f["eom"] == e].dropna(subset=["enc"])
        if k >= 2 and len(a):
            mu.loc[d.index] = (np.mean(a) + np.mean(b) * d["enc"]) / 100.0
        if len(d) < 50:
            continue
        w = d["me"] / d["me"].sum()
        xm, ym = (w * d["enc"]).sum(), (w * d["ret"]).sum()
        s = (w * (d["enc"] - xm) * (d["ret"] - ym)).sum() / (w * (d["enc"] - xm) ** 2).sum()
        a.append(ym - s * xm)
        b.append(s)
    return mu


def frame(win: str) -> pd.DataFrame:
    f = forecasts()
    f["mu"] = calibrated(f)
    lo, hi = (pd.Timestamp(x) for x in rj.WINDOWS[win])
    cut = pd.Timestamp("2020-12-31") if win == "valid" else pd.Timestamp("2026-08-31")
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["short_ok"] & p["ret_exc_lead1m"].notna()][["permno", "eom", "gics", "beta_60m", "ivol_capm_252d", "ret_exc_lead1m"]]
    j = pd.read_parquet("fiam/v4b/out/risk/jumps/probabilities.parquet", columns=["permno", "eom", "p_y_up"])
    g = f[f["eom"].between(lo, hi)].merge(p, on=["permno", "eom"]).merge(j, on=["permno", "eom"], how="left")
    g["sector"] = g["gics"].astype(str).str[:2]
    g["y"] = g["ret_exc_lead1m"].astype(float)

    def resid(d):
        b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
        X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
        c, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        return pd.Series(d["y"].to_numpy() - X @ c, index=d.index)

    g["res"] = g.groupby("eom", group_keys=False).apply(resid, include_groups=False)
    g["rel"] = g["y"] - g.groupby("eom")["y"].transform("mean")
    gg = g.groupby("eom")
    g["blend"] = gg["A"].rank(pct=True) + gg["tail"].rank(pct=True)
    g["p_up"] = g["p_y_up"].fillna(gg["p_y_up"].transform("median"))
    sig = g["ivol_capm_252d"].fillna(gg["ivol_capm_252d"].transform("median")) * np.sqrt(21)
    g["s_up"] = np.sqrt(sig**2 + g["p_up"] * J_UP**2)
    g["ub"] = g["mu"] + Z * g["s_up"]
    g["mps"] = g["mu"] / g["s_up"]
    return g


def select(g: pd.DataFrame) -> dict[str, pd.Series]:
    gg = g.groupby("eom")
    q = lambda c: gg[c].rank(pct=True)
    b30 = q("blend") <= 0.30
    sel = {"plain_blend": q("blend") <= 0.10, "plain_mean": q("A") <= 0.10}
    for name, col in (("ub", "ub"), ("mu_per_sup", "mps")):
        r = g[b30].groupby("eom")[col].rank(pct=True)
        sel[name] = pd.Series(False, index=g.index)
        sel[name].loc[r.index] = r <= 1 / 3
    hi_up = q("p_up") > 2 / 3
    sel["no_jump"] = (q("blend") <= 0.10) & ~hi_up
    return sel


def report(win: str) -> None:
    g = frame(win)
    print(f"== {win}: SHORT-LEG PROFIT, %/month (t); + = shorts fell vs benchmark")
    print(f" {'rule':12s} {'wts':4s} {'names':>5s} {'res profit':>13s} {'rel profit':>13s} {'Sharpe/yr':>9s} {'hit':>5s} {'worst mo':>8s}  by year (res profit)")
    for name, s in select(g).items():
        d = g[s]
        for wname, w in (("eq", pd.Series(1.0, index=d.index)), ("1/su", 1.0 / d["s_up"])):
            w = w / w.groupby(d["eom"]).transform("sum")
            pr = -(w * d["res"]).groupby(d["eom"]).sum()
            pl = -(w * d["rel"]).groupby(d["eom"]).sum()
            t = lambda x: f"{x.mean()*100:+.2f} ({x.mean()/x.std()*np.sqrt(len(x)):+.1f})"
            yrs = {int(k): round(v * 100, 2) for k, v in pr.groupby(pr.index.year).mean().items()}
            print(f" {name:12s} {wname:4s} {int(d.groupby('eom').size().median()):5d} {t(pr):>13s} {t(pl):>13s} "
                  f"{pr.mean()/pr.std()*np.sqrt(12):9.2f} {(pr > 0).mean():5.2f} {pr.min()*100:+8.2f}  {yrs}")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["valid"]:
        report(w)
