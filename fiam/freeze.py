# Every number fiam.v2 learns from data up to 2020, saved in frozen/.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam import book as P
from fiam import costs as C
from fiam import data

# Small, so git holds it and MAIN.py carries it. Relative like cache/.
FROZEN = Path("frozen")
BETA = FROZEN / "beta_pre2021.parquet"


# The teacher's beta for each month, its own code rerun on cached folds.
def learned_beta() -> pd.DataFrame:
    from fiam.ml import teachers as T

    frame, cols = T.inputs()
    target = T.attach(frame, T.monthly_beta(), False)
    out = frame[data.KEYS].copy()
    out["beta_hat"] = T.walk_forward(frame, cols, target)
    return out.dropna(subset=["beta_hat"]).sort_values(data.KEYS, ignore_index=True)


# The rerun must match the shipped 2021+ betas, or it is another model.
def check_against_shipped(betas: pd.DataFrame) -> float:
    shipped = data.read(P.INPUTS, ["permno", "eom", "beta_hat"]).dropna()
    both = shipped.merge(betas, on=data.KEYS, suffixes=("_shipped", "_rerun"))
    if len(both) != len(shipped):
        raise SystemExit(f"rerun covers {len(both)} of {len(shipped)} shipped betas")
    return float((both["beta_hat_shipped"] - both["beta_hat_rerun"]).abs().max())


# Writes pre-2021 decisions only. The shipped file still covers 2021 on.
def freeze_beta() -> None:
    betas = learned_beta()
    gap = check_against_shipped(betas)
    if gap > 1e-9:
        raise SystemExit(f"rerun differs from the shipped betas by up to {gap:.2e}")
    early = betas[betas["eom"] < P.FIRST_FORECAST]
    FROZEN.mkdir(exist_ok=True)
    early.to_parquet(BETA, index=False)
    span = early["eom"].dt.strftime("%Y-%m")
    print(f"pre-2021 betas: {len(early):,} rows, {span.min()} to {span.max()}; 2021+ gap {gap:.0e}")


# Learned beta by month: frozen pre-2021, shipped after, else missing.
def learned(universe: pd.DataFrame) -> pd.Series:
    parts = [data.read(BETA)] if BETA.exists() else []
    parts.append(data.read(P.INPUTS, ["permno", "eom", "beta_hat"]))
    table = pd.concat(parts).drop_duplicates(data.KEYS, keep="last").set_index(data.KEYS)
    key = pd.MultiIndex.from_frame(universe[data.KEYS])
    return pd.Series(table["beta_hat"].reindex(key).to_numpy(), index=universe.index)


# Decisions held 2015-02 to 2020-12: every frozen number fits on these.
FIT = ("2015-01-31", "2020-11-30")


# The shipped cross-section in the fitting years, residual vol as scale.
def fit_universe() -> pd.DataFrame:
    return P.build_signal(P.screen(P.load_panel(("ivol_capm_252d",)), *FIT))


# Pooled rank correlation of the composite with next neutral return.
def information_coefficient(df: pd.DataFrame) -> float:
    both = pd.DataFrame(dict(score=df["signal"], residual=P.neutralize(df, df["ret_exc_lead1m"])))
    return float(both.dropna().corr(method="spearman").iloc[0, 1])


# How much of each signal's rank lasts a month, over the fitting years.
def autocorrelation(df: pd.DataFrame) -> dict:
    table = P.scores(df, P.SIGNALS).set_axis(list(P.SIGNALS), axis=1)
    table[data.KEYS] = df[data.KEYS].to_numpy()
    out = {}
    for col in P.SIGNALS:
        wide = table.pivot_table(index="permno", columns="eom", values=col)
        pairs = [wide.iloc[:, i].corr(wide.iloc[:, i + 1]) for i in range(wide.shape[1] - 1)]
        out[col] = float(np.nanmean(pairs))
    return out


# lambda in cost = lambda x trade^2, fitted to shipped-book trades.
def quadratic_cost(df: pd.DataFrame) -> float:
    from fiam import v2

    num = den = 0.0
    rf = P.benchmarks().set_index("month")["rf"]
    previous = None
    for month, weights, info, cross_section, parts, _ in P.walk(df):
        before = pd.Series(dtype=float) if previous is None else previous
        idx = weights.index.union(before.index).intersection(cross_section["permno"])
        pool = cross_section.set_index("permno").loc[idx].reset_index()
        trade = (
            weights.reindex(idx, fill_value=0.0) - before.reindex(idx, fill_value=0.0)
        ).to_numpy()
        linear, selling, impact, _ = v2.cost_terms(pool, C.DEFAULT.nav)
        cost = (
            linear * np.abs(trade) + selling * np.maximum(-trade, 0) + impact * np.abs(trade) ** 1.5
        )
        num += float((cost * trade**2).sum())
        den += float((trade**4).sum())
        cash = rf.get((month + pd.offsets.MonthBegin(1)).normalize(), 0.0)
        previous = P.drift(weights, info, parts, cash)
    return num / den


# Garleanu-Pedersen 1/(1 + phi a/gamma), mean one so only the mix moves.
def persistence(df: pd.DataFrame, ic: float) -> dict:
    phi = {col: 1.0 - rho for col, rho in autocorrelation(df).items()}
    vol = df["ivol_capm_252d"] * np.sqrt(21)
    gamma = P.LIMITS["ridge"] * float((ic * vol.groupby(df["eom"]).median()).mean())
    lam = quadratic_cost(df)
    ratio = (np.sqrt(1 + 4 * lam / gamma) - 1) / 2
    raw = {col: 1.0 / (1.0 + p * ratio) for col, p in phi.items()}
    mean = float(np.mean(list(raw.values())))
    weights = {col: w / mean for col, w in raw.items()}
    return dict(phi=phi, lambda_=lam, gamma=gamma, a_over_gamma=ratio, persistence_weights=weights)


# Fitting-year IC and persistence weights, written once for later runs.
def freeze_params() -> None:
    from fiam import v2

    df = fit_universe()
    ic = information_coefficient(df)
    fixed = v2.params() | dict(ic=ic, fitted_on=f"decisions {FIT[0]} to {FIT[1]}")
    fixed |= persistence(df, ic)
    FROZEN.mkdir(exist_ok=True)
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(
        f"IC {ic:.4f}; a/gamma {fixed['a_over_gamma']:.3f}; weights {fixed['persistence_weights']}"
    )


# IC as monthly Spearman of each signal against the neutral return.
def freeze_ic_monthly() -> None:
    from fiam import v2

    df = fit_universe()
    both = pd.DataFrame(
        dict(eom=df["eom"], s=df["signal"], r=P.neutralize(df, df["ret_exc_lead1m"]))
    ).dropna()
    monthly = both.groupby("eom")[["s", "r"]].apply(lambda g: g["s"].corr(g["r"], "spearman"))
    fixed = v2.params() | dict(ic_monthly=float(monthly.mean()), ic_monthly_months=len(monthly))
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(f"cross-sectional IC {monthly.mean():.4f} over {len(monthly)} months")


# Daily S&P 500 returns for the daily beta (FRED, from 2016-09-26).
def market_daily() -> pd.Series:
    from fiam import benchmarks as B

    close = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    return close.set_index("observation_date")["SP500"].pct_change().dropna()


# Welch (2019): 252 days, clip to [-2, 4] x market, 126-day half-life.
def welch(months: list) -> pd.DataFrame:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    returns = daily.pivot_table(index="date", columns="permno", values="total_return")
    market = market_daily().reindex(returns.index)
    returns, market = returns[market.notna()], market.dropna()
    decay = 0.5 ** (np.arange(251, -1, -1) / 126)
    rows = []
    for eom in months:
        window = returns.index[returns.index <= eom][-252:]
        # A month past the daily data has no window; the fallback covers it.
        if len(window) < 252 or (eom - window[-1]).days > 7:
            continue
        x = market.loc[window].to_numpy()
        y = returns.loc[window].to_numpy()
        lo, hi = np.minimum(-2 * x, 4 * x)[:, None], np.maximum(-2 * x, 4 * x)[:, None]
        y = np.clip(y, lo, hi)
        weight = np.where(np.isnan(y), 0.0, decay[:, None])
        total = weight.sum(axis=0)
        xm = (weight * x[:, None]).sum(axis=0) / total
        ym = np.nansum(weight * y, axis=0) / total
        dx = x[:, None] - xm
        cov = np.nansum(weight * dx * (y - ym), axis=0)
        var = (weight * dx**2).sum(axis=0)
        enough = ((weight > 0).sum(axis=0) >= 126) & (var > 0)
        beta = np.divide(cov, var, out=np.full_like(cov, np.nan), where=enough)
        rows.append(pd.DataFrame(dict(permno=returns.columns, eom=eom, beta=beta)))
    return pd.concat(rows).dropna(ignore_index=True)


# Each stock's realized daily beta in the month after each decision.
def realized(df: pd.DataFrame) -> pd.Series:
    from fiam.ml import teachers as T

    target = T.monthly_beta()
    holding = (df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    key = pd.MultiIndex.from_arrays([df["permno"], holding])
    return pd.Series(target.reindex(key).to_numpy(), index=df.index)


# The hedge beta: learned or Welch, whichever better fits next month.
def freeze_beta_fix() -> None:
    from fiam import v2

    fit = fit_universe()
    fit["learned"], fit["realized"] = learned(fit), realized(fit)
    sample = fit.dropna(subset=["learned", "realized"])
    b, a = np.polyfit(sample["learned"], sample["realized"], 1)
    every = P.build_signal(P.screen(P.load_panel(), FIT[0], P.LAST_FORECAST))
    welch_table = welch(sorted(every["eom"].unique()))
    every = every.merge(welch_table.rename(columns={"beta": "welch"}), on=data.KEYS, how="left")
    every["calibrated"] = a + b * learned(every)
    scored = every.merge(fit[[*data.KEYS, "realized", "learned"]], on=data.KEYS)
    scored = scored.dropna(subset=["realized", "learned", "welch", "calibrated"])
    scored["side"] = np.where(scored["signal"] >= 0, "long", "short")
    errors = {}
    for name in ("calibrated", "welch", "learned", "beta_60m"):
        cells = (
            (scored[name] - scored["realized"]).abs().groupby([scored["side"], scored["size_grp"]])
        )
        errors[name] = float(cells.mean().mean())
    choice = min(("calibrated", "welch"), key=errors.get)
    out = every[[*data.KEYS]].assign(beta=every[choice])
    FROZEN.mkdir(exist_ok=True)
    out.dropna().to_parquet(v2.BETAS, index=False)
    fixed = v2.params() | dict(
        beta_choice=choice,
        beta_errors=errors,
        beta_calibration=dict(intercept=float(a), slope=float(b), rows=int(len(sample))),
        beta_scored_rows=int(len(scored)),
    )
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(f"beta errors {errors}; chosen {choice}; calibration {a:+.3f} + {b:.3f} x learned")


# Risk lambda set on 2017 to match the shipped book's ridge penalty.
def freeze_risk_lambda() -> None:
    from fiam import v2

    held = data.read(v2.OUT / "v1@1e7" / "check" / "holdings.parquet")
    held = held[held["eom"].dt.year == 2017]
    df = v2.universe(("2017-01-31", "2017-12-31"), v2.Settings(frozenset({"risk"})), v2.params())
    ridge = v2.Settings().mandate.ridge
    model = penalty = 0.0
    for eom, book in held.groupby("eom"):
        pool = df[df["permno"].isin(book["permno"]) & (df["eom"] == eom)]
        w = book.set_index("permno")["weight"].reindex(pool["permno"]).fillna(0.0).to_numpy()
        loadings, spec = v2.risk_terms(pool)
        model += float(((loadings.T @ w) ** 2).sum() + spec @ w**2)
        penalty += float(pool["scale"].iloc[0] * 0.5 * ridge * (w**2).sum())
    fixed = v2.params() | dict(risk_lambda=penalty / model, risk_lambda_fitted_on="v1 books 2017")
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(f"risk lambda {penalty / model:.4f} from {held['eom'].nunique()} months of 2017")


# Cost budget and vol target from the `shorts` book at $10M, to 2020.
def freeze_v3() -> None:
    from fiam import v2

    folder = v2.OUT / "shorts@1e7" / "check"
    book = pd.read_csv(folder / "returns.csv", parse_dates=["holding_month"])
    trading = book[["cost_commission", "cost_spread", "cost_impact"]].sum(axis=1).iloc[1:]
    held = data.read(folder / "holdings.parquet")
    held = held[held["eom"] >= "2017-01-01"]
    df = v2.universe(v2.CHECK, v2.Settings(frozenset({"voltarget"})), v2.params())
    vols = []
    for eom, w in held.groupby("eom"):
        pool = df[(df["eom"] == eom) & df["permno"].isin(w["permno"])].reset_index(drop=True)
        weights = w.set_index("permno")["weight"].reindex(pool["permno"]).fillna(0.0)
        terms = v2.risk_terms(pool)
        if terms is not None:
            vols.append(v2.predicted_vol(weights.to_numpy(), terms))
    fixed = v2.params() | dict(
        cost_budget=float(trading.mean()),
        cost_budget_months=int(len(trading)),
        vol_target=float(np.median(vols)),
        vol_target_months=len(vols),
        v3_fitted_on="v2-pass at $10M: holding months 2016-02..2020-12, decisions 2017-01..2020-11",
    )
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(f"cost budget {trading.mean():.5f} a month; volatility target {np.median(vols):.4f}")


# Risk forecast error and gross cap from the `shorts` book at $10M.
def freeze_final() -> None:
    from fiam import stats, v2

    folder = v2.OUT / "shorts@1e7" / "check"
    book = pd.read_csv(folder / "returns.csv", parse_dates=["forecast_eom"])
    gross = book.set_index("forecast_eom")["gross"]
    held = data.read(folder / "holdings.parquet")
    df = v2.universe(v2.CHECK, v2.Settings(frozenset({"voltarget"})), v2.params())
    misses = []
    for eom, w in held[held["eom"] >= "2017-01-01"].groupby("eom"):
        pool = df[(df["eom"] == eom) & df["permno"].isin(w["permno"])].reset_index(drop=True)
        weights = w.set_index("permno")["weight"].reindex(pool["permno"]).fillna(0.0)
        terms = v2.risk_terms(pool)
        if terms is not None:
            misses.append((gross[eom] / v2.predicted_vol(weights.to_numpy(), terms)) ** 2)
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    daily = daily[daily["permno"].isin(held["permno"].unique())]
    returns = daily.pivot_table(index="date", columns="permno", values="total_return")
    path = stats.daily_gross(held, returns)
    drift = float((path["gross"] / path["start"]).max())
    fixed = v2.params() | dict(
        vol_bias=float(np.sqrt(np.mean(misses))),
        vol_bias_months=len(misses),
        gross_drift_max=drift,
        gross_ceiling=float(min(v2.GROSS_RANGE[1], 2.0 / drift)),
        final_fitted_on="v2-pass at $10M: decisions 2017-01..2020-11; 2016-2020 daily gross",
    )
    v2.PARAMS.write_text(json.dumps(fixed, indent=1) + "\n", encoding="utf-8")
    print(
        f"risk error {fixed['vol_bias']:.3f}; daily gross drift {drift:.3f}; ceiling "
        f"{fixed['gross_ceiling']:.3f}"
    )


if __name__ == "__main__":
    steps = dict(beta=freeze_beta, params=freeze_params, beta_fix=freeze_beta_fix)
    steps |= dict(risk_lambda=freeze_risk_lambda, ic_monthly=freeze_ic_monthly, v3=freeze_v3)
    steps |= dict(final=freeze_final)
    for name in sys.argv[1:] or list(steps):
        steps[name]()
