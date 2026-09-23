# Splits risk and return into what the known factors explain and what is left over.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

RETURNS = Path("submission/returns.csv")
OUT = Path("submission/exhibits")

HURDLE = 0.04 / 12

# Newey-West lag. Monthly returns are autocorrelated, so plain errors overstate.
HAC_LAGS = 6


# The Fama-French factors, which are what "explained by known risk" means in practice.
def factors() -> pd.DataFrame:
    import zipfile

    with zipfile.ZipFile(P.BENCH / "ff_factors.zip") as archive:
        raw = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    rows = [r.split(",") for r in raw if r.strip()[:6].isdigit() and len(r.split(",")) == 5]
    ff = pd.DataFrame(rows, columns=["ym", "mkt_rf", "smb", "hml", "rf"])
    ff["month"] = pd.to_datetime(ff["ym"].str.strip(), format="%Y%m")
    for col in ("mkt_rf", "smb", "hml", "rf"):
        ff[col] = ff[col].astype(float) / 100
    return ff.set_index("month")[["mkt_rf", "smb", "hml"]]


# Regress on the factors. The intercept is what none of them explain, and what we earn.
def attribution(excess: pd.Series, f: pd.DataFrame) -> dict:
    both = pd.concat([excess.rename("r"), f], axis=1, sort=True).dropna()
    fit = sm.OLS(both["r"], sm.add_constant(both[["mkt_rf", "smb", "hml"]])).fit(
        cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS}
    )
    # Each factor's squared-beta share. They do not sum, the factors are correlated.
    individual = {
        name: float((fit.params[name] ** 2) * both[name].var() / both["r"].var())
        for name in ("mkt_rf", "smb", "hml")
    }
    # The only defensible split. What the fitted values explain, and what is left over.
    fitted_share = float(np.var(fit.fittedvalues, ddof=1) / both["r"].var())
    return dict(
        alpha_annual=float(fit.params["const"] * 12),
        alpha_t=float(fit.tvalues["const"]),
        betas={k: float(fit.params[k]) for k in ("mkt_rf", "smb", "hml")},
        t_stats={k: float(fit.tvalues[k]) for k in ("mkt_rf", "smb", "hml")},
        r_squared=float(fit.rsquared),
        individual_variance_contribution=individual,
        unallocated_after_individual_contributions=float(1 - sum(individual.values())),
        explained_by_all_three=fitted_share,
        residual_share=float(1 - fitted_share),
        months=int(len(both)),
    )


# Book-level return before and after costs. The leg split lives in completeness.py.
def book_risk(df: pd.DataFrame) -> dict:
    out = {}
    for leg in ("gross", "net"):
        series = df[leg]
        out[leg] = dict(
            annual=float(series.mean() * 12),
            volatility=float(series.std() * np.sqrt(12)),
            worst_month=float(series.min()),
            best_month=float(series.max()),
        )
    return out


# Tail risk, which monthly volatility hides. A committee asks for these by name.
def tails(active: pd.Series) -> dict:
    sorted_returns = active.sort_values()
    cutoff = int(np.ceil(len(active) * 0.05))
    return dict(
        var_95_monthly=float(np.percentile(active, 5)),
        cvar_95_monthly=float(sorted_returns.iloc[:cutoff].mean()),
        skew=float(active.skew()),
        excess_kurtosis=float(active.kurtosis()),
        worst_three_months=[float(x) for x in sorted_returns.iloc[:3]],
    )


# Rolling 12-month IR and how often it is under water. The spread beats the average.
def consistency(active: pd.Series) -> dict:
    rolling = active.rolling(12)
    ratio = (rolling.mean() / rolling.std() * np.sqrt(12)).dropna()
    return dict(
        windows=int(len(ratio)),
        share_negative=float((ratio < 0).mean()),
        median=float(ratio.median()),
        worst=float(ratio.min()),
        best=float(ratio.max()),
    )


# Runs every decomposition and writes them as one artifact.
def main() -> None:
    df = pd.read_csv(RETURNS, parse_dates=["holding_month"]).set_index("holding_month")
    excess = df["portfolio_total_return"] - df["rf"]
    active = df["net"] - HURDLE

    out = dict(
        attribution=attribution(excess, factors()),
        book=book_risk(df),
        tails=tails(active),
        consistency=consistency(active),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "risk_decomposition.json").write_text(json.dumps(out, indent=2))

    a = out["attribution"]
    print(f"three-factor attribution over {a['months']} months")
    print(f"  alpha           {a['alpha_annual']:+.1%} a year, t = {a['alpha_t']:.2f}")
    for name in ("mkt_rf", "smb", "hml"):
        print(f"  {name:<15} beta {a['betas'][name]:+.3f}  (t {a['t_stats'][name]:+.2f})")
    print(f"  r-squared       {a['r_squared']:.3f}")
    print(f"  residual        {a['residual_share']:.1%} of variance, from the regression")
    print(
        f"  unallocated     {a['unallocated_after_individual_contributions']:.1%} "
        f"after individual contributions, the gap is the factors' covariance"
    )
    t = out["tails"]
    print(f"  95% VaR {t['var_95_monthly']:.2%} a month, CVaR {t['cvar_95_monthly']:.2%}")
    c = out["consistency"]
    print(f"  {c['share_negative']:.0%} of rolling 12-month windows have a negative IR")


if __name__ == "__main__":
    main()
