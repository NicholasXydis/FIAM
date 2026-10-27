# The risk model: sector and style factors, HAR specific risk.

import numpy as np
import pandas as pd

from fiam.vfinal import betas, data
from fiam.vfinal.construct import inputs

# Factor covariance: half-life 36 months, at least 24.
HALF_LIFE, MIN_MONTHS = 36, 24
FACTORS = (*inputs.STYLES, "mid_cap")
# HAR windows in sessions; a month of realized vol needs 15 sessions.
HAR_DAYS, MIN_DAYS, HAR_MONTHS = (5, 21, 63), 15, 24
# Specific variance is at least a quarter of the stock's total.
SPECIFIC_FLOOR = 0.25


# A month's design: GICS-2 or SIC-2 sector dummies and the styles.
def design(frame: pd.DataFrame) -> pd.DataFrame:
    sectors = pd.get_dummies(frame["sector"], prefix="sec", dtype=float)
    return sectors.join(frame[list(FACTORS)])


# Factor returns of each month from the prior month end's exposures.
def factor_returns(frames: dict) -> pd.DataFrame:
    rows = {}
    for eom, frame in sorted(frames.items()):
        nxt = eom + pd.offsets.MonthEnd(1)
        ret = data.panel(frame.index, nxt, nxt, ("ret",)).set_index("permno")["ret"]
        y = ret.reindex(frame.index)
        ok = y.notna().to_numpy()
        if ok.sum() < 100:
            continue
        x = design(frame)[ok]
        w = np.sqrt(np.sqrt(frame["me"].clip(lower=1.0).to_numpy()[ok]))
        coef, *_ = np.linalg.lstsq(x.to_numpy() * w[:, None], y.to_numpy()[ok] * w, rcond=None)
        rows[nxt] = pd.Series(coef, index=x.columns)
    return pd.DataFrame(rows).T.sort_index()


# The factor covariance known at a formation: returns realized by then.
def covariance(returns: pd.DataFrame, eom) -> pd.DataFrame | None:
    known = returns[returns.index <= pd.Timestamp(eom)].fillna(0.0)
    if len(known) < MIN_MONTHS:
        return None
    w = 0.5 ** (np.arange(len(known))[::-1] / HALF_LIFE)
    w /= w.sum()
    centred = known - (known * w[:, None]).sum()
    return (centred * w[:, None]).T @ centred


# Daily total returns for these stocks: CRSP through 2025, then the dsf.
def daily(permnos, start, end) -> pd.DataFrame:
    days = data.sessions(start, end)
    crsp = data.crsp_daily(permnos, start, end)
    wide = data.matrix(crsp, "ret", days, permnos)
    if pd.Timestamp(end) > data.CRSP_END:
        late = data.dsf(permnos, data.CRSP_END + pd.Timedelta(days=1), end)
        raw = data.matrix(late, "ret", days, permnos)
        wide = wide.combine_first(with_delta(raw.loc[raw.index > data.CRSP_END]))
    return wide


# The dsf's raw returns after 2025, for days inside an open month.
def late(permnos, end) -> pd.DataFrame:
    if pd.Timestamp(end) <= data.CRSP_END:
        return pd.DataFrame()
    days = data.sessions(data.CRSP_END + pd.Timedelta(days=1), end)
    rows = data.dsf(permnos, days[0], days[-1])
    return data.matrix(rows, "ret", days, permnos)


# Each complete month's δ on its ex-day by the engine's rule A (2026).
def with_delta(raw: pd.DataFrame) -> pd.DataFrame:
    from fiam.vfinal import daily_book

    out = raw.copy()
    months = raw.index.to_period("M")
    full = data.calendar().index.to_period("M").value_counts()
    p = data.panel(raw.columns, raw.index.min(), raw.index.max(), ("ret",))
    p = p.assign(month=pd.to_datetime(p["eom"]).dt.to_period("M"))
    gone = data.exits(raw.columns).assign(month=lambda e: e["exit_date"].dt.to_period("M"))
    for month, rows in raw.groupby(months):
        total = p[p["month"] == month].set_index("permno")["ret"].reindex(raw.columns)
        close = rows.index[-1]
        data.assert_public_by(p.loc[p["month"] == month, "first_close"], close, "δ panel rows")
        # Every session read, none null, no exit that month.
        ok = (len(rows) == full.get(month, -1)) & rows.notna().all()
        ok &= ~raw.columns.isin(gone.loc[gone["month"] == month, "permno"])
        delta = (1 + total) / (1 + rows).prod() - 1
        delta = delta.where(delta >= daily_book.DELTA_FLOOR, 0.0)
        for permno in delta.index[ok & (delta > 0)]:
            d = float(delta[permno])
            # A large δ goes ex on the sharpest fall, a small one at month end.
            day = rows[permno].idxmin() if d > daily_book.BIG_DELTA else close
            out.loc[day, permno] = (1 + out.loc[day, permno]) * (1 + d) - 1
    return out


# Log realized monthly vol over the last n sessions to a day.
def log_vol(returns: pd.DataFrame, day, n: int) -> pd.Series:
    window = returns.loc[:day].tail(n)
    sd = window.std().where(window.count() >= min(n, MIN_DAYS) * 0.6)
    return np.log(sd * np.sqrt(21))


# The 24 month ends before T's month, each once.
def har_ends(T) -> list:
    end = pd.Timestamp(T) + pd.offsets.MonthEnd(0)
    return [end - pd.offsets.MonthEnd(k) for k in range(HAR_MONTHS, 0, -1)]


# HAR total vol a month ahead, fitted on the 24 months known by T.
def har(returns: pd.DataFrame, T) -> pd.Series:
    T = pd.Timestamp(T)
    xs, ys = [], []
    for end in har_ends(T):
        last = data.eom_session([end]).iloc[0]
        nxt = returns.loc[last:].iloc[1:]
        nxt = nxt[nxt.index <= data.eom_session([end + pd.offsets.MonthEnd(1)]).iloc[0]]
        if nxt.index.max() > T:
            continue
        target = np.log(nxt.std() * np.sqrt(21)).where(nxt.count() >= MIN_DAYS)
        feats = pd.DataFrame({n: log_vol(returns, last, n) for n in HAR_DAYS})
        both = feats.assign(y=target).replace([np.inf, -np.inf], np.nan).dropna()
        xs.append(both[list(HAR_DAYS)])
        ys.append(both["y"])
    x = pd.concat(xs)
    a = np.column_stack([np.ones(len(x)), x.to_numpy()])
    y = pd.concat(ys).to_numpy()
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    # A log forecast's mean in levels needs half the residual variance.
    half_var = 0.5 * float(np.var(y - a @ coef))
    now = pd.DataFrame({n: log_vol(returns, T, n) for n in HAR_DAYS})
    fit = coef[0] + now.to_numpy() @ coef[1:] + half_var
    return pd.Series(np.exp(fit), index=now.index, name="vol")


# Specific variance: total less the factor part, floored at a quarter.
def specific(total_vol: pd.Series, loadings: pd.DataFrame, cov: pd.DataFrame) -> pd.Series:
    b = loadings.reindex(columns=cov.columns, fill_value=0.0)
    factor = np.einsum("ij,jk,ik->i", b.to_numpy(), cov.to_numpy(), b.to_numpy())
    total = total_vol.reindex(b.index) ** 2
    floor = SPECIFIC_FLOOR * total
    return pd.Series(np.maximum(total.to_numpy() - factor, floor.to_numpy()), index=b.index)


# The FF5+UMD model's daily factors, as public by T (French's lag).
FF = ("mktrf", "smb", "hml", "rmw", "cma", "umd")
FF_DAYS = 252


# FF5+UMD loadings, monthly factor covariance and specific variance.
def ff_model(returns: pd.DataFrame, T, ids) -> tuple:
    f = data.table("french", [*FF, "rf"]).set_index("date")
    f = f[f["first_close"] <= pd.Timestamp(T)][[*FF, "rf"]].dropna().tail(FF_DAYS)
    r = returns.reindex(index=f.index, columns=ids).sub(f["rf"], axis=0)
    x = np.column_stack([np.ones(len(f)), f[list(FF)].to_numpy()])
    y = r.to_numpy()
    ok = ~np.isnan(y)
    b, spec = np.full((len(ids), len(FF)), np.nan), np.full(len(ids), np.nan)
    for j in range(len(ids)):
        m = ok[:, j]
        if m.sum() < FF_DAYS // 2:
            continue
        coef, *_ = np.linalg.lstsq(x[m], y[m, j], rcond=None)
        b[j], spec[j] = coef[1:], np.var(y[m, j] - x[m] @ coef) * 21
    cov = np.cov(f[list(FF)].to_numpy(), rowvar=False) * 21
    loadings = pd.DataFrame(b, index=ids, columns=list(FF)).fillna(0.0)
    return loadings, cov, pd.Series(spec, index=ids).fillna(np.nanmedian(spec))


# The factor share of a book's ex-ante variance: w'BFB'w over w'Σw.
def factor_share(w: pd.Series, loadings: pd.DataFrame, cov, spec: pd.Series) -> float:
    b = loadings.reindex(w.index).fillna(0.0).to_numpy()
    f = b.T @ w.to_numpy()
    factor = float(f @ np.asarray(cov) @ f)
    return factor / (factor + float((spec.reindex(w.index).to_numpy() * w.to_numpy() ** 2).sum()))


# Ex-ante transfer coefficient: a'w over sqrt(a'Σ^-1 a w'Σw) (Woodbury).
def transfer(alpha: pd.Series, w: pd.Series, loadings, cov, spec: pd.Series) -> float:
    b, d = loadings.to_numpy(), spec.reindex(alpha.index).to_numpy()
    a, ww = alpha.to_numpy(), w.reindex(alpha.index).fillna(0.0).to_numpy()
    dinv_a, dinv_b = a / d, b / d[:, None]
    # (F^-1 + B'D^-1 B)^-1 as F (I + B'D^-1 B F)^-1: F may be singular.
    f_cov = np.asarray(cov)
    inner = f_cov @ np.linalg.inv(np.eye(len(f_cov)) + (b.T @ dinv_b) @ f_cov)
    sinv_a = dinv_a - dinv_b @ (inner @ (b.T @ dinv_a))
    f = b.T @ ww
    var_w = float(f @ np.asarray(cov) @ f + (d * ww**2).sum())
    return float(a @ ww / np.sqrt(float(a @ sinv_a) * var_w))


# Welch and Dimson betas at T on total returns, not dsf.
def total_betas(returns: pd.DataFrame, T, ids) -> pd.DataFrame:
    days = returns.index[returns.index <= pd.Timestamp(T)][-betas.WELCH_DAYS :]
    rf = data.rf_daily(days, by=T)
    stock = returns.reindex(index=days, columns=list(ids)).sub(rf, axis=0)
    market = data.market_daily(days) - rf
    keep = market.notna().to_numpy()
    stock, market = stock[keep], market[keep]
    window = betas.DIMSON_DAYS + 2
    welch = betas.welch(stock, market)
    dimson = betas.dimson(stock.iloc[-window:], market.iloc[-window:])
    return pd.DataFrame({"welch": welch, "dimson": dimson})
