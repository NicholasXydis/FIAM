# Risk dashboard and evidence tests for any book.

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from fiam import book as P
from fiam import layers

TRIALS_PAST = 1665
HURDLE = 0.04 / 12


# FF five factors and momentum by holding month, from the market layer.
def factors() -> pd.DataFrame | None:
    table = layers.load("market/factors_monthly")
    if table is None:
        return None
    table["month"] = pd.to_datetime(table["dateff"]).dt.to_period("M").dt.to_timestamp()
    return table.set_index("month")[["mktrf", "smb", "hml", "rmw", "cma", "umd"]]


# OLS of y on x, Newey-West at the given lag: (monthly alpha, its t).
def hac_alpha(y: pd.Series, x: pd.DataFrame, lags: int) -> tuple[float, float]:
    both = pd.concat([y.rename("_y"), x], axis=1, sort=True).dropna()
    fit = sm.OLS(both["_y"], sm.add_constant(both.drop(columns="_y"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags}
    )
    return float(fit.params.iloc[0]), float(fit.tvalues.iloc[0])


# Equal-weighted cosine t on alpha (Lazarus, Lewis, Stock, Watson 2018).
def ewc_alpha_t(y: pd.Series, x: pd.DataFrame) -> float:
    both = pd.concat([y.rename("_y"), x], axis=1, sort=True).dropna()
    exog = sm.add_constant(both.drop(columns="_y")).to_numpy()
    fit = sm.OLS(both["_y"].to_numpy(), exog).fit()
    n = len(both)
    b = max(int(0.4 * n ** (2 / 3)), 2)
    xtx = np.linalg.inv(exog.T @ exog)
    moments = exog * fit.resid[:, None]
    t_index = (np.arange(1, n + 1) - 0.5) / n
    projections = [
        np.sqrt(2 / n) * (np.cos(np.pi * j * t_index)[:, None] * moments).sum(axis=0)
        for j in range(1, b + 1)
    ]
    omega = sum(np.outer(p, p) for p in projections) / b
    cov = xtx @ omega @ xtx * n
    return float(fit.params[0] / np.sqrt(cov[0, 0]))


# Largest fall from any earlier high, the starting NAV counting as one.
def drawdown(net: pd.Series) -> float:
    growth = (1 + net).cumprod()
    peak = np.maximum(growth.cummax(), 1.0)
    return float((growth / peak - 1).min())


# Longest run of months below an earlier peak, starting NAV as a peak.
def underwater(net: pd.Series) -> int:
    growth = (1 + net).cumprod()
    below = growth < np.maximum(growth.cummax(), 1.0)
    runs = below.groupby((~below).cumsum()).sum()
    return int(runs.max()) if len(runs) else 0


# Daily VaR, CVaR: historical, Student-t, EVT above the 90th percentile.
def tail(daily: pd.Series, level: float) -> dict:
    loss = -daily.dropna().to_numpy()
    hist_var = float(np.quantile(loss, level))
    out = dict(historical=dict(var=hist_var, cvar=float(loss[loss >= hist_var].mean())))
    df, loc, scale = st.t.fit(loss)
    t_var = float(st.t.ppf(level, df, loc, scale))
    draws = st.t.rvs(df, loc, scale, size=200_000, random_state=42)
    out["student_t"] = dict(var=t_var, cvar=float(draws[draws >= t_var].mean()), df=float(df))
    u = float(np.quantile(loss, 0.90))
    excess = loss[loss > u] - u
    xi, _, beta = st.genpareto.fit(excess, floc=0)
    share = len(excess) / len(loss)
    evt_var = u + beta / xi * (((1 - level) / share) ** -xi - 1)
    evt_cvar = (evt_var + beta - xi * u) / (1 - xi) if xi < 1 else float("nan")
    out["evt"] = dict(var=float(evt_var), cvar=float(evt_cvar), xi=float(xi))
    return out


# A book's daily returns from monthly weights held through each month.
def daily_book(held: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    parts = []
    for eom, w in held.groupby("eom"):
        month = returns.loc[eom + pd.Timedelta(days=1) : eom + pd.offsets.MonthEnd(1)]
        weights = w.set_index("permno")["weight"].reindex(month.columns).fillna(0.0)
        parts.append(month.fillna(0.0) @ weights)
    return pd.concat(parts).sort_index() if parts else pd.Series(dtype=float)


# Daily gross of the untraded month-start book over NAV, cash included.
def daily_gross(held: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for eom, w in held.groupby("eom"):
        month = returns.loc[eom + pd.Timedelta(days=1) : eom + pd.offsets.MonthEnd(1)]
        if month.empty:
            continue
        weights = w.set_index("permno")["weight"].reindex(month.columns).fillna(0.0)
        value = (1 + month.fillna(0.0)).cumprod() * weights
        nav = 1 + (value - weights).sum(axis=1)
        start = float(weights.abs().sum())
        parts.append(pd.DataFrame(dict(gross=value.abs().sum(axis=1) / nav, start=start)))
    return pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=["gross", "start"])


# Daily beta with one lead and one lag of the market (Dimson 1979).
def dimson_beta(daily: pd.Series, market: pd.Series) -> float:
    frame = pd.DataFrame(dict(r=daily, m0=market, m1=market.shift(1), m_1=market.shift(-1)))
    frame = frame.dropna()
    fit = sm.OLS(frame["r"], sm.add_constant(frame[["m0", "m1", "m_1"]])).fit()
    return float(fit.params[["m0", "m1", "m_1"]].sum())


# Effective names per side and the top ten positions' share of gross.
def concentration(held: pd.DataFrame) -> dict:
    rows = []
    for _, w in held.groupby("eom"):
        weights = w["weight"]
        long, short = weights[weights > 0], -weights[weights < 0]
        rows.append(
            dict(
                effective_long=float(long.sum() ** 2 / (long**2).sum()) if len(long) else 0.0,
                effective_short=float(short.sum() ** 2 / (short**2).sum()) if len(short) else 0.0,
                top10=float(weights.abs().nlargest(10).sum() / weights.abs().sum()),
            )
        )
    return pd.DataFrame(rows).mean().to_dict()


# The monthly part of the dashboard for one book.
def dashboard(book: pd.DataFrame, market: pd.Series) -> dict:
    net = book["net"]
    downside = np.sqrt((np.minimum(net, 0) ** 2).mean()) * np.sqrt(12)
    fit = P.regress(net, market.reindex(net.index))
    f = factors()
    out = dict(
        information_ratio=P.information_ratio(net),
        sharpe=float(net.mean() / net.std() * np.sqrt(12)),
        sortino=float(net.mean() * 12 / downside) if downside else float("nan"),
        beta_monthly=float(fit.params.iloc[1]),
        max_drawdown=drawdown(net),
        hit_rate=float((net > 0).mean()),
        gross_exposure=float(book["gross_exposure"].mean()),
        net_exposure_max=float(book["net_exposure"].abs().max()),
    )
    if f is not None:
        for lags in (3, 6, 11):
            a, t = hac_alpha(net, f, lags)
            out |= {"alpha_annual": a * 12, f"alpha_t_hac{lags}": t}
        out["alpha_t_ewc"] = ewc_alpha_t(net, f)
    return out


# The daily part: Dimson beta, 95% and 99% VaR and CVaR, concentration.
def daily_risk(held: pd.DataFrame, returns: pd.DataFrame, market: pd.Series) -> dict:
    daily = daily_book(held, returns)
    out = dict(dimson_beta=dimson_beta(daily, market), days=len(daily))
    return out | dict(tail_95=tail(daily, 0.95), tail_99=tail(daily, 0.99)) | concentration(held)


# Politis-White (2004) automatic block length for stationary bootstrap.
def block_length(x: np.ndarray) -> float:
    n = len(x)
    x = x - x.mean()
    acf = np.array([x[: n - k] @ x[k:] / n for k in range(n // 2)])
    bound = 2 * np.sqrt(np.log10(n) / n)
    m_hat = next(
        (k for k in range(1, len(acf) - 5) if (np.abs(acf[k : k + 5] / acf[0]) < bound).all()), 1
    )
    m = min(2 * m_hat, len(acf) - 1)
    lags = np.arange(-m, m + 1)
    weights = np.where(np.abs(lags / m) <= 0.5, 1.0, 2 * (1 - np.abs(lags / m)))
    gamma = acf[np.abs(lags)]
    g = (weights * np.abs(lags) * gamma).sum()
    d = 2 * (weights * gamma).sum() ** 2
    return float(max((2 * g**2 / d) ** (1 / 3) * n ** (1 / 3), 1.0))


# Stationary bootstrap (Politis-Romano 1994) of a statistic, 90/95% CIs.
def bootstrap(frame: pd.DataFrame, statistic, reps: int = 10_000, seed: int = 42) -> dict:
    frame = frame.dropna()
    n, block = len(frame), block_length(frame.iloc[:, 0].to_numpy())
    rng = np.random.default_rng(seed)
    values = np.empty(reps)
    for r in range(reps):
        idx = np.empty(n, dtype=int)
        idx[0] = rng.integers(n)
        for i in range(1, n):
            idx[i] = rng.integers(n) if rng.random() < 1 / block else (idx[i - 1] + 1) % n
        values[r] = statistic(frame.iloc[idx])
    q = np.quantile(values, [0.025, 0.05, 0.95, 0.975])
    return dict(
        mean=float(statistic(frame)),
        ci90=[float(q[1]), float(q[2])],
        ci95=[float(q[0]), float(q[3])],
        block=block,
    )


# The stationary bootstrap of one series' mean, with its intervals.
def bootstrap_mean(x: pd.Series, reps: int = 10_000, seed: int = 42) -> dict:
    return bootstrap(x.to_frame(), lambda f: f.iloc[:, 0].mean(), reps, seed)


# Patton (2009): both under median (0.25), worst tenths together (0.10).
def patton(net: pd.Series, market: pd.Series) -> dict:
    both = pd.concat([net.rename("r"), market.rename("m")], axis=1).dropna()
    low = (both["r"] < both["r"].median()) & (both["m"] < both["m"].median())
    worst = both["m"] <= both["m"].quantile(0.10)
    joint = int((worst & (both["r"] <= both["r"].quantile(0.10))).sum())
    return dict(
        quadrant=float(low.mean()),
        quadrant_p=float(st.binomtest(int(low.sum()), len(both), 0.25).pvalue),
        tail=joint / int(worst.sum()),
        tail_p=float(st.binomtest(joint, int(worst.sum()), 0.10).pvalue),
    )


# Up and down capture, and the Henriksson-Merton timing coefficient.
def neutrality(net: pd.Series, market: pd.Series) -> dict:
    both = pd.concat([net.rename("r"), market.rename("m")], axis=1).dropna()
    up, down = both[both["m"] > 0], both[both["m"] < 0]
    x = sm.add_constant(pd.DataFrame(dict(m=both["m"], put=np.maximum(-both["m"], 0))))
    hm = sm.OLS(both["r"], x).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    rho, p_corr = st.pearsonr(both["r"], both["m"])
    return dict(
        up_capture=float(up["r"].mean() / up["m"].mean()),
        down_capture=float(down["r"].mean() / down["m"].mean()),
        correlation=float(rho),
        correlation_p=float(p_corr),
        henriksson_merton=float(hm.params["put"]),
        henriksson_merton_t=float(hm.tvalues["put"]),
    )
