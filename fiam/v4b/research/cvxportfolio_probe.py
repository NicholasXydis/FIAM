"""Minimal real-data cvxportfolio probe (research only, not the frozen book).

Uses 40 large-cap names, monthly panel total returns, the frozen E-LASSO
MaInf cross-section as a 1%/month forecast, and cvxportfolio's
SinglePeriodOptimization with dollar/market neutrality, leverage, name caps,
transaction costs and short borrow.  The point is to check that the suggested
backend solves the same class of problem on our data, not to replace the E3
support/band construction or to produce a strategy result.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "fiam/v4b/out/research"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    cols = ["permno", "eom", "ret", "prc", "adjfct", "dolvol_126d", "me"]
    p = pd.read_parquet(ROOT / "data/finals_2026/chars_final_with_names.parquet",
                        columns=cols, filters=[("eom", ">=", pd.Timestamp("2020-01-31")),
                                               ("eom", "<=", pd.Timestamp("2022-12-31"))])
    p["eom"] = pd.to_datetime(p.eom)
    p["adj_prc"] = p["prc"] / p["adjfct"].replace(0, np.nan)
    # 40 names with a complete 2020-2022 history and the largest 2020-12 cap.
    wide = p.pivot(index="eom", columns="permno", values="ret")
    good = wide.columns[wide.notna().all()]
    cap = p[(p.eom == pd.Timestamp("2020-12-31")) & p.permno.isin(good)].set_index("permno")["me"]
    names = list(cap.nlargest(40).index)
    p = p[p.permno.isin(names)]
    rets = p.pivot(index="eom", columns="permno", values="ret")[names]
    prices = p.pivot(index="eom", columns="permno", values="adj_prc")[names]
    vols = p.pivot(index="eom", columns="permno", values="dolvol_126d")[names] * 21.0
    # Monthly cash return, last column.
    t = pd.read_csv(ROOT / "data/benchmarks/TB3MS.csv", parse_dates=["observation_date"])
    m = t.set_index(t.observation_date.dt.to_period("M"))["TB3MS"]
    rets["cash"] = pd.Series(rets.index.to_period("M").map(m).to_numpy() / 1200.0, index=rets.index)
    rets = rets.dropna(subset=names)
    prices = prices.reindex(rets.index)
    vols = vols.reindex(rets.index).ffill().fillna(1e6)
    prices = prices.ffill().bfill()
    # Index must be timezone-aware only if cash is added; cash already last.
    rets.index = pd.DatetimeIndex(rets.index).tz_localize("UTC")
    prices.index = rets.index
    vols.index = rets.index

    f = pd.read_parquet(ROOT / "fiam/v4b/out/elasso/run_oos/forecastElasso_oos.parquet",
                        columns=["date", "permno", "MaInf"])
    f["date"] = pd.to_datetime(f.date).dt.tz_localize("UTC")
    f = f[f.permno.isin(names)]
    rhat = f.pivot(index="date", columns="permno", values="MaInf").reindex(index=rets.index, columns=names)
    rhat = rhat.ffill().fillna(0.0)
    rhat = rhat.sub(rhat.mean(axis=1), axis=0).div(rhat.std(axis=1).replace(0, np.nan), axis=0)
    rhat = rhat.fillna(0.0) * 0.01  # 1%/month at one cross-sectional sigma

    import cvxportfolio as cvx
    md = cvx.UserProvidedMarketData(returns=rets, volumes=vols, prices=prices,
                                    cash_key="cash", min_history=pd.Timedelta("365d"))
    costs = [cvx.TransactionCost(a=0.00025, b=1.0), cvx.HoldingCost(short_fees=0.05)]
    policy = cvx.SinglePeriodOptimization(
        cvx.ReturnsForecast(r_hat=rhat)
        - 0.5 * cvx.FullCovariance()
        - 0.5 * cvx.TransactionCost(a=0.00025, b=1.0)
        - 0.5 * cvx.HoldingCost(short_fees=0.05),
        constraints=[cvx.DollarNeutral(), cvx.MarketNeutral(), cvx.LeverageLimit(2.0),
                     cvx.MaxWeights(0.05), cvx.MinWeights(-0.05)],
        solver="CLARABEL",
        fallback_solver="SCS",
    )
    sim = cvx.MarketSimulator(market_data=md, costs=costs)
    result = sim.backtest(policy, start_time="2021-01-31", end_time="2022-12-31")
    result.w.to_parquet(OUT / "cvxportfolio_weights.parquet")
    result.returns.to_frame("net_return").to_parquet(OUT / "cvxportfolio_returns.parquet")
    stats = {
        "universe": int(len(names)),
        "start": str(rets.index[0].date()),
        "end": str(rets.index[-1].date()),
        "mean_monthly": float(result.returns.mean()),
        "vol_monthly": float(result.returns.std()),
        "sharpe_monthly_ann": float(result.returns.mean() / result.returns.std() * np.sqrt(12)),
        "cumulative": float((1 + result.returns).prod() - 1),
        "avg_total_gross_including_cash": float(result.w.abs().sum(axis=1).mean()),
        "avg_asset_gross": float(result.w[[c for c in result.w.columns if c != "cash"]].abs().sum(axis=1).mean()),
        "avg_asset_net": float(result.w[[c for c in result.w.columns if c != "cash"]].sum(axis=1).mean()),
        "avg_cash_weight": float(result.w["cash"].mean()),
        "annualized_volatility": float(result.annualized_volatility),
        "annualized_average_return": float(result.annualized_average_return),
    }
    (OUT / "cvxportfolio_probe.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))
    print(result)


if __name__ == "__main__":
    main()
