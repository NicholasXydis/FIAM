# The risk model's pieces in numpy: betas, covariances, variances.

import numpy as np
import pandas as pd

# beta.py: 252-session OLS, 200 pairs, 50/50 with the panel's beta_60m.
WINDOW, MIN_OBS, BLEND_DAILY = 252, 200, 0.5
# covariance.py: diagonal shrink 0.2, 5 Bartlett lags, 126 days first.
DELTA, NW_LAGS, MIN_DAYS = 0.2, 5, 126
# specific.py: HAR windows, EWMA half-lives, 25% shrink, 5% floor.
HAR_WINDOWS, EWMA_HALF_LIVES, SHRINK, FLOOR_Q = (5, 21, 63), (84, 168), 0.25, 0.05
# enhanced.py: vol regime half-life 42, 5 residual factors over 252.
VRA_HL, PCA_K, PCA_WINDOW, PCA_HL = 42, 5, 252, 84
# beta_candidates.py: Welch 252 sessions half-life 126, Dimson 126.
WELCH_DAYS, WELCH_HALF, DIMSON_DAYS = 252, 126, 126


# Rolling 252-session OLS beta and its standard error per stock.
def rolling_beta(excess: pd.DataFrame, mkt_rf: pd.Series) -> dict:
    m = mkt_rf.reindex(excess.index).to_numpy(dtype=float)
    present = excess.notna()
    x = excess.to_numpy(dtype=float)
    roll = dict(window=WINDOW, min_periods=MIN_OBS)
    mm = pd.DataFrame(np.where(present, m[:, None], np.nan), index=excess.index,
                      columns=excess.columns)  # fmt: skip
    n = present.rolling(**roll).sum().to_numpy(dtype=float)
    sm, sx = mm.rolling(**roll).sum().to_numpy(), excess.rolling(**roll).sum().to_numpy()
    smm = (mm**2).rolling(**roll).sum().to_numpy()
    syy_s = (excess**2).rolling(**roll).sum().to_numpy()
    smx = pd.DataFrame(np.where(present, x * m[:, None], np.nan), index=excess.index,
                       columns=excess.columns).rolling(**roll).sum().to_numpy()  # fmt: skip
    sxx = smm - sm**2 / n
    sxy = smx - sm * sx / n
    beta = np.where(sxx > 0, sxy / np.where(sxx > 0, sxx, np.nan), np.nan)
    rss = np.maximum((syy_s - sx**2 / n) - beta * sxy, 0.0)
    se = np.sqrt(rss / np.maximum(n - 2, 1) / np.where(sxx > 0, sxx, np.nan))
    frame = lambda a: pd.DataFrame(a, index=excess.index, columns=excess.columns)  # noqa: E731
    return {"beta": frame(beta), "se": frame(se), "sxx": frame(sxx)}


# Vasicek shrink toward the sector mean, precision weighted.
def vasicek(beta: pd.Series, se: pd.Series, sector: pd.Series) -> pd.Series:
    f = pd.DataFrame({"b": beta, "se": se, "s": sector}).dropna(subset=["b"])
    prior_var = f.groupby("s")["b"].transform("var").clip(lower=0.01)
    prior_mean = f.groupby("s")["b"].transform("mean")
    own = 1.0 / f["se"].fillna(f["se"].median()).clip(lower=0.02) ** 2
    out = (f["b"] * own + prior_mean / prior_var) / (own + 1.0 / prior_var)
    return out.reindex(beta.index)


# One cross-section's hedge beta: Vasicek, then half the 60-month beta.
def hedge(rolled: dict, pos: int, month: pd.DataFrame) -> pd.Series:
    names = month.index.intersection(rolled["beta"].columns)
    b = rolled["beta"].iloc[pos].reindex(names)
    se = rolled["se"].iloc[pos].reindex(names)
    bv = vasicek(b, se, month.loc[names, "sector"])
    b60 = month.loc[names, "beta_60m"]
    return (BLEND_DAILY * bv + (1 - BLEND_DAILY) * b60).fillna(bv).fillna(b60)


# Hedge betas at every month end, from sessions on or before it.
def hedge_betas(exp: pd.DataFrame, rolled: dict) -> pd.DataFrame:
    days, rows = rolled["beta"].index, []
    for eom, month in exp.groupby("eom"):
        pos = days.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 0:
            continue
        h = hedge(rolled, pos, month.set_index("permno"))
        rows.append(pd.DataFrame({"eom": eom, "permno": h.index, "beta_hedge": h.to_numpy()}))
    out = pd.concat(rows, ignore_index=True)
    # Names with neither leg take their sector-month mean, then 1.0.
    joined = exp[["eom", "permno", "sector"]].merge(out, on=["eom", "permno"], how="left")
    fill = joined.groupby(["eom", "sector"])["beta_hedge"].transform("mean")
    joined["beta_hedge"] = joined["beta_hedge"].fillna(fill).fillna(1.0)
    return joined.drop(columns="sector")


# The daily hedge-beta grid: weekly anchors, data before the anchor.
def hedge_beta_daily(exp: pd.DataFrame, rolled: dict) -> pd.DataFrame:
    days = rolled["beta"].index
    week = pd.Series(days, index=days).groupby(days.to_period("W")).transform("min")
    eoms = pd.DatetimeIndex(sorted(exp["eom"].unique()))
    by_month = {e: g.set_index("permno") for e, g in exp.groupby("eom")}
    out = {}
    for anchor in sorted(set(week)):
        pos = days.get_loc(anchor) - 1
        epos = eoms.searchsorted(pd.Timestamp(anchor), side="left") - 1
        if pos < 0 or epos < 0:
            continue
        out[anchor] = hedge(rolled, pos, by_month[eoms[epos]])
    return pd.DataFrame(out).T.reindex(days).ffill()


# EWMA autocovariances G0..G_maxlag from factor rows before a date.
def autocovariances(factors: pd.DataFrame, date, half_life: int, maxlag: int):
    hist = factors[factors.index < pd.Timestamp(date)].dropna()
    if len(hist) < MIN_DAYS + maxlag:
        return None
    x = hist.to_numpy(dtype=float)
    w = 0.5 ** (np.arange(len(x) - 1, -1, -1) / half_life)
    w = w / w.sum()
    xc = x - w @ x
    out = [(xc * w[:, None]).T @ xc]
    for j in range(1, maxlag + 1):
        wj = w[j:] / w[j:].sum()
        out.append((xc[j:] * wj[:, None]).T @ xc[:-j])
    return out


# Symmetrise, floor eigenvalues, shrink toward the diagonal.
def regularise(cov: np.ndarray, delta: float = DELTA) -> np.ndarray:
    cov = 0.5 * (cov + cov.T)
    vals, vecs = np.linalg.eigh(cov)
    floor = max(float(vals.max()), 0.0) * 1e-8
    cov = (vecs * np.clip(vals, floor, None)) @ vecs.T
    return (1 - delta) * cov + delta * np.diag(np.diag(cov))


# One-session factor covariance: plain, or with Newey-West lags.
def factor_cov(factors: pd.DataFrame, date, half_life: int, newey: bool = True):
    g = autocovariances(factors, date, half_life, NW_LAGS if newey else 0)
    if g is None:
        return None
    cov = g[0]
    if newey:
        cov = cov + sum((1 - j / (NW_LAGS + 1)) * (g[j] + g[j].T) for j in range(1, NW_LAGS + 1))
    return pd.DataFrame(regularise(cov), index=factors.columns, columns=factors.columns)


# H-session factor covariance from the same autocovariances.
def factor_cov_horizon(factors: pd.DataFrame, date, half_life: int, horizon: int):
    if horizon == 1:
        return factor_cov(factors, date, half_life)
    g = autocovariances(factors, date, half_life, horizon - 1)
    if g is None:
        return None
    cov = horizon * g[0] + sum((horizon - j) * (g[j] + g[j].T) for j in range(1, horizon))
    return pd.DataFrame(regularise(cov), index=factors.columns, columns=factors.columns)


# Correlations halfway to +-1 and vols x1.5 (covariance.stressed).
def stressed(cov: pd.DataFrame) -> pd.DataFrame:
    v = np.sqrt(np.diag(cov.to_numpy()))
    corr = cov.to_numpy() / np.outer(v, v)
    out = corr + 0.5 * (np.sign(corr) - corr)
    np.fill_diagonal(out, 1.0)
    out = out * np.outer(1.5 * v, 1.5 * v)
    return pd.DataFrame(regularise(out, delta=0.0), index=cov.index, columns=cov.columns)


# Log RMS residual vol over trailing windows at each month end.
def har_features(resid: pd.DataFrame, eoms) -> pd.DataFrame:
    sq = resid**2
    means = {n: sq.rolling(n, min_periods=max(n // 2, 2)).mean() for n in HAR_WINDOWS}
    rows = []
    for eom in eoms:
        pos = resid.index.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < max(HAR_WINDOWS):
            continue
        part = pd.DataFrame({f"har_{n}": np.log(np.sqrt(means[n].iloc[pos])) for n in HAR_WINDOWS})
        part = part.replace([np.inf, -np.inf], np.nan).assign(eom=pd.Timestamp(eom))
        rows.append(part.reset_index(names="permno"))
    return pd.concat(rows, ignore_index=True)


# Realised daily residual variance over (eom, next eom].
def realised_next(resid: pd.DataFrame, eoms) -> pd.DataFrame:
    ordered, rows = sorted(pd.Timestamp(e) for e in eoms), []
    for a, b in zip(ordered[:-1], ordered[1:]):
        block = resid[(resid.index > a) & (resid.index <= b)]
        if len(block) < 10:
            continue
        var = (block**2).mean()
        rows.append(pd.DataFrame({"eom": a, "permno": var.index, "realised_var": var.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


# EWMA of squared residuals sampled at each month end.
def ewma_at(resid: pd.DataFrame, eoms, half_life: int) -> pd.DataFrame:
    ew = (resid**2).ewm(alpha=1 - 0.5 ** (1 / half_life), min_periods=21, ignore_na=True).mean()
    rows = []
    for eom in eoms:
        pos = resid.index.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 0:
            continue
        s = ew.iloc[pos]
        rows.append(pd.DataFrame({"eom": pd.Timestamp(eom), "permno": s.index,
                                  f"ewma{half_life}": s.to_numpy()}))  # fmt: skip
    return pd.concat(rows, ignore_index=True)


# Downside and upside EWMA specific variances at each month end.
def directional_at(resid: pd.DataFrame, eoms, half_life: int = 84) -> pd.DataFrame:
    a = 1 - 0.5 ** (1 / half_life)
    down = (resid.clip(upper=0.0) ** 2).ewm(alpha=a, min_periods=21, ignore_na=True).mean()
    up = (resid.clip(lower=0.0) ** 2).ewm(alpha=a, min_periods=21, ignore_na=True).mean()
    rows = []
    for eom in eoms:
        pos = resid.index.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 0:
            continue
        rows.append(pd.DataFrame({"eom": pd.Timestamp(eom), "permno": resid.columns,
                                  "down_var": down.iloc[pos].to_numpy(),
                                  "up_var": up.iloc[pos].to_numpy()}))  # fmt: skip
    return pd.concat(rows, ignore_index=True)


# QLIKE loss on variances (lower is better).
def qlike(realised: pd.Series, forecast: pd.Series) -> pd.Series:
    ratio = realised / forecast
    return ratio - np.log(ratio) - 1


# Diebold-Mariano t on monthly mean loss differences.
def diebold_mariano(diff: pd.Series, lags: int = 3) -> float:
    d = diff.dropna().to_numpy(dtype=float)
    c = d - d.mean()
    var = float(c @ c) / len(d)
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * float(c[lag:] @ c[:-lag]) / len(d)
    return float(d.mean() / np.sqrt(var / len(d)))


# Walk-forward HAR variances: each year fit on prior years only.
def har_forecast(feats: pd.DataFrame, realised: pd.DataFrame) -> pd.DataFrame:
    f = feats.merge(realised, on=["eom", "permno"], how="left")
    names = [f"har_{n}" for n in HAR_WINDOWS]
    f["har_var"] = np.nan
    f["log_var"] = np.log(f["realised_var"].clip(lower=1e-10)) / 2
    for year in sorted(f["eom"].dt.year.unique()):
        train = (f["eom"].dt.year < year) & f[names + ["log_var"]].notna().all(axis=1)
        test = (f["eom"].dt.year == year) & f[names].notna().all(axis=1)
        if train.sum() < 5000 or not test.any():
            continue
        x = np.column_stack([np.ones(int(train.sum())), f.loc[train, names].to_numpy()])
        coef, *_ = np.linalg.lstsq(x, f.loc[train, "log_var"].to_numpy(), rcond=None)
        xt = np.column_stack([np.ones(int(test.sum())), f.loc[test, names].to_numpy()])
        f.loc[test, "har_var"] = np.exp(xt @ coef) ** 2
    return f[["eom", "permno", "har_var"]]


# The QLIKE race on 2017-2020 formations: HAR against each EWMA.
def race(resid: pd.DataFrame, eoms, years) -> dict:
    realised = realised_next(resid, eoms)
    table = har_forecast(har_features(resid, eoms), realised)
    table = table.merge(realised, on=["eom", "permno"])
    for hl in EWMA_HALF_LIVES:
        table = table.merge(ewma_at(resid, eoms, hl), on=["eom", "permno"], how="left")
    cols = ["har_var", *[f"ewma{h}" for h in EWMA_HALF_LIVES]]
    scored = table[table["eom"].dt.year.isin(years)].dropna(subset=["realised_var", *cols])
    losses = {c: qlike(scored["realised_var"], scored[c].clip(lower=1e-10)) for c in cols}
    out = {"rows": int(len(scored)), "qlike": {c: float(v.mean()) for c, v in losses.items()}}
    out["dm_har_vs"] = {f"ewma{h}": diebold_mariano((losses["har_var"] - losses[f"ewma{h}"])
                                                    .groupby(scored["eom"]).mean())
                        for h in EWMA_HALF_LIVES}  # fmt: skip
    best = min((f"ewma{h}" for h in EWMA_HALF_LIVES), key=lambda c: out["qlike"][c])
    har_wins = out["qlike"]["har_var"] < out["qlike"][best] and out["dm_har_vs"][best] < -2
    out["winner"] = "har_var" if har_wins else best
    return out


# Shrink toward the sector median and floor at the 5th percentile.
def shrink_floor(table: pd.DataFrame, col: str, sectors: pd.DataFrame) -> pd.Series:
    f = table.merge(sectors, on=["eom", "permno"], how="left")
    med = f.groupby(["eom", "sector"])[col].transform("median")
    shrunk = ((1 - SHRINK) * f[col] + SHRINK * med).fillna(med)
    floor = shrunk.groupby(f["eom"]).transform(lambda s: s.quantile(FLOOR_Q))
    return pd.Series(np.maximum(shrunk.to_numpy(), floor.to_numpy()), index=table.index)


# Ex-ante EWMA variance at each day from rows strictly before it.
def ewma_var_before(x: np.ndarray, hl: int, min_periods: int = 21) -> np.ndarray:
    a = 1 - 0.5 ** (1 / hl)
    s, wsum, n = np.zeros(x.shape[1]), np.zeros(x.shape[1]), np.zeros(x.shape[1])
    out = np.full(x.shape, np.nan)
    for t in range(len(x)):
        ok = n >= min_periods
        out[t, ok] = s[ok] / wsum[ok]
        m = ~np.isnan(x[t])
        s = np.where(m, (1 - a) * s + a * np.nan_to_num(x[t]) ** 2, s)
        wsum = np.where(m, (1 - a) * wsum + a, wsum)
        n = n + m
    return out


# The vol regime multiplier lambda^2 known at each close (USE4).
def vra_path(x: pd.DataFrame, hl: int, vra_hl: int = VRA_HL) -> pd.Series:
    xt = x.mask(x.abs() < 1e-12).to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        z2 = xt**2 / ewma_var_before(xt, hl)
    ok = np.isfinite(z2)
    cs = np.where(ok, z2, 0.0).sum(1) / np.maximum(ok.sum(1), 1)
    a = 1 - 0.5 ** (1 / vra_hl)
    lam = w = 0.0
    out = np.full(len(x), np.nan)
    for t in range(len(x)):
        if ok[t].any():
            lam, w = (1 - a) * lam + a * cs[t], (1 - a) * w + a
        if w > 0:
            out[t] = lam / w
    return pd.Series(out, index=x.index)


# Top-K residual components over the 252 sessions before s0.
def residual_factors(resid: pd.DataFrame, s0, names: pd.Index, k: int = PCA_K):
    block = resid[resid.index < pd.Timestamp(s0)].tail(PCA_WINDOW).reindex(columns=names)
    x = np.nan_to_num(block.to_numpy(dtype=float))
    w = 0.5 ** (np.arange(len(x) - 1, -1, -1) / PCA_HL)
    xs = x * np.sqrt(w / w.sum())[:, None]
    _, sv, vt = np.linalg.svd(xs, full_matrices=False)
    ev = sv**2
    noise = ev[k:].mean() if len(ev) > k else 0.0
    load = vt[:k].T * np.sqrt(np.clip(ev[:k] - noise, 0, None))[None, :]
    tot = (xs**2).sum(0)
    share = np.clip(np.where(tot > 0, (load**2).sum(1) / np.where(tot > 0, tot, 1), 0), 0, 0.9)
    cols = [f"pca{j + 1}" for j in range(k)]
    return pd.DataFrame(load, index=names, columns=cols), pd.Series(share, index=names)


# The filtered two-state Markov chain on market variance.
def markov_state(r: pd.Series, window: int = 21, min_history: int = 252,
                 horizon: int = 21) -> pd.Series:  # fmt: skip
    r = r.astype(float).sort_index()
    realized = (r * r).rolling(window, min_periods=window).mean()
    threshold = realized.expanding(min_periods=min_history).median().shift(1)
    state = (realized > threshold).astype(float).where(threshold.notna()).to_numpy()
    counts, prev, out = np.ones((2, 2)), None, np.full(len(r), np.nan)
    for i, s in enumerate(state):
        if not np.isfinite(s):
            continue
        s = int(s)
        if prev is not None:
            counts[prev, s] += 1.0
        a = counts / counts.sum(axis=1, keepdims=True)
        probs = np.zeros(2)
        probs[s] = 1.0
        out[i] = (probs @ np.linalg.matrix_power(a, horizon))[1]
        prev = s
    return pd.Series(out, index=r.index, name="p_stress_21")


# Welch (2022): each excess return clipped to [-2, 4] x the market's.
def welch(stock: pd.DataFrame, market: pd.Series) -> pd.Series:
    x = market.to_numpy(dtype=float)
    y = stock.to_numpy(dtype=float)
    lo, hi = np.minimum(-2 * x, 4 * x)[:, None], np.maximum(-2 * x, 4 * x)[:, None]
    y = np.clip(y, lo, hi)
    decay = 0.5 ** (np.arange(len(x) - 1, -1, -1) / WELCH_HALF)
    weight = np.where(np.isnan(y), 0.0, decay[:, None])
    total = weight.sum(axis=0)
    safe = np.where(total > 0, total, np.nan)
    xm, ym = (weight * x[:, None]).sum(axis=0) / safe, np.nansum(weight * y, axis=0) / safe
    dx = x[:, None] - xm
    cov, var = np.nansum(weight * dx * (y - ym), axis=0), (weight * dx**2).sum(axis=0)
    enough = ((weight > 0).sum(axis=0) >= len(x) // 2) & (var > 0)
    out = np.divide(cov, var, out=np.full(len(total), np.nan), where=enough)
    return pd.Series(out, index=stock.columns)


# Dimson (1979): slopes on the market's lag, day and lead, summed.
def dimson(stock: pd.DataFrame, market: pd.Series) -> pd.Series:
    m = market.to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(m) - 2), m[:-2], m[1:-1], m[2:]])
    y = stock.iloc[1:-1].to_numpy(dtype=float)
    out = np.full(y.shape[1], np.nan)
    full = ~np.isnan(y).any(axis=0)
    if full.any():
        coef, *_ = np.linalg.lstsq(x, y[:, full], rcond=None)
        out[full] = coef[1:].sum(axis=0)
    for j in np.flatnonzero(~full):
        ok = ~np.isnan(y[:, j])
        if ok.sum() >= len(ok) // 2:
            coef, *_ = np.linalg.lstsq(x[ok], y[ok, j], rcond=None)
            out[j] = coef[1:].sum()
    return pd.Series(out, index=stock.columns)
