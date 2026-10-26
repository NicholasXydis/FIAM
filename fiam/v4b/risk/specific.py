# Specific variance D: HAR on residual vol vs EWMA, judged by QLIKE (R§4).
#
# The repo's frozen HAR winner forecasts total vol; here the same HAR design
# (log RMS over 5/21/63 sessions, pooled walk-forward OLS) is retargeted at
# factor residuals, because D must not double-count factor variance already
# in BFB'. EWMA of squared residuals (half-lives 84/168) is the alternative.
# Selection is pre-OOS only: QLIKE against the next month's realised residual
# variance at 2017-2020 formations, Diebold-Mariano on monthly mean losses.
# Afterwards: 25% shrink to the sector median [Judgement], floor at the 5th
# cross-sectional percentile so no name looks spuriously riskless.

import numpy as np
import pandas as pd

WINDOWS = (5, 21, 63)
EWMA_HALF_LIVES = (84, 168)
SHRINK = 0.25  # [Judgement] weight on the sector median.
FLOOR_Q = 0.05


# Log RMS residual vol over trailing windows ending on/before each eom.
def har_features(resid: pd.DataFrame, eoms) -> pd.DataFrame:
    sq = resid**2
    means = {n: sq.rolling(n, min_periods=max(n // 2, 2)).mean() for n in WINDOWS}
    rows = []
    days = resid.index
    for eom in eoms:
        pos = days.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < max(WINDOWS):
            continue
        part = pd.DataFrame(
            {f"har_{n}": np.log(np.sqrt(means[n].iloc[pos])) for n in WINDOWS}
        ).replace([np.inf, -np.inf], np.nan)
        part["eom"] = pd.Timestamp(eom)
        rows.append(part.reset_index(names="permno"))
    return pd.concat(rows, ignore_index=True)


# Realised daily residual variance over (eom, next eom] sessions.
def realised_next(resid: pd.DataFrame, eoms) -> pd.DataFrame:
    ordered = sorted(pd.Timestamp(e) for e in eoms)
    rows = []
    for a, b in zip(ordered[:-1], ordered[1:]):
        block = resid[(resid.index > a) & (resid.index <= b)]
        if len(block) < 10:
            continue
        var = (block**2).mean()
        rows.append(pd.DataFrame({"eom": a, "permno": var.index, "realised_var": var.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


# EWMA of squared residuals sampled at each eom (sessions on/before eom).
def ewma_at(resid: pd.DataFrame, eoms, half_life: int) -> pd.DataFrame:
    alpha = 1 - 0.5 ** (1 / half_life)
    ew = (resid**2).ewm(alpha=alpha, min_periods=21, ignore_na=True).mean()
    days = resid.index
    rows = []
    for eom in eoms:
        pos = days.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 0:
            continue
        s = ew.iloc[pos]
        rows.append(
            pd.DataFrame(
                {"eom": pd.Timestamp(eom), "permno": s.index, f"ewma{half_life}": s.to_numpy()}
            )
        )
    return pd.concat(rows, ignore_index=True)


# QLIKE loss on variances (lower is better).
def qlike(realised: pd.Series, forecast: pd.Series) -> pd.Series:
    ratio = realised / forecast
    return ratio - np.log(ratio) - 1


def choose_ewma_asof(losses: pd.DataFrame, asof) -> dict:
    """Choose from paired, fully observed losses whose labels have completed.

    This D26 selector is a standalone research mechanism; the current risk
    model does not use it until a separate experiment registers integration.
    """
    required = ["formation", "label_end", "ewma84", "ewma168"]
    data = losses[required].copy()
    data["formation"] = pd.to_datetime(data["formation"], errors="coerce")
    data["label_end"] = pd.to_datetime(data["label_end"], errors="coerce")
    for col in ("ewma84", "ewma168"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    cutoff = pd.Timestamp(asof)
    finite = np.isfinite(data["ewma84"]) & np.isfinite(data["ewma168"])
    eligible = data[finite & (data["formation"] <= cutoff) & (data["label_end"] <= cutoff)
                    & (data["label_end"] >= data["formation"])].copy()
    monthly = eligible.groupby("formation")[["ewma84", "ewma168"]].mean().sort_index().tail(60)
    used = eligible[eligible["formation"].isin(monthly.index)]
    latest = used["label_end"].max() if not used.empty else None
    winner = "ewma84"
    if len(monthly) >= 12 and monthly["ewma168"].mean() < monthly["ewma84"].mean():
        winner = "ewma168"
    return {"winner": winner, "formations": int(len(monthly)), "latest_label_end": latest}


# Diebold-Mariano t on monthly mean loss differences (negative favours a).
def diebold_mariano(diff: pd.Series, lags: int = 3) -> float:
    d = diff.dropna().to_numpy(dtype=float)
    n, mean = len(d), d.mean()
    centred = d - mean
    var = float(centred @ centred) / n
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * float(centred[lag:] @ centred[:-lag]) / n
    return float(mean / np.sqrt(var / n))


# QLIKE race 2017-2020: HAR vs each EWMA; returns losses and DM statistics.
def race(resid: pd.DataFrame, eoms, years=(2017, 2018, 2019, 2020)) -> dict:
    feats = har_features(resid, eoms)
    realised = realised_next(resid, eoms)
    table = har_forecast(feats, realised).merge(realised, on=["eom", "permno"], how="inner")
    for hl in EWMA_HALF_LIVES:
        table = table.merge(ewma_at(resid, eoms, hl), on=["eom", "permno"], how="left")
    scored = table[table["eom"].dt.year.isin(years)].dropna(
        subset=["realised_var", "har_var", *[f"ewma{h}" for h in EWMA_HALF_LIVES]]
    )
    out = {"rows": int(len(scored)), "qlike": {}, "dm_har_vs": {}}
    losses = {}
    for col in ("har_var", *[f"ewma{h}" for h in EWMA_HALF_LIVES]):
        losses[col] = qlike(scored["realised_var"], scored[col].clip(lower=1e-10))
        out["qlike"][col] = float(losses[col].mean())
    for hl in EWMA_HALF_LIVES:
        monthly = (losses["har_var"] - losses[f"ewma{hl}"]).groupby(scored["eom"]).mean()
        out["dm_har_vs"][f"ewma{hl}"] = diebold_mariano(monthly)
    best_ewma = min((f"ewma{h}" for h in EWMA_HALF_LIVES), key=lambda c: out["qlike"][c])
    har_wins = (
        out["qlike"]["har_var"] < out["qlike"][best_ewma] and out["dm_har_vs"][best_ewma] < -2
    )
    out["winner"] = "har_var" if har_wins else best_ewma
    return out


# Shrink toward the sector median and floor; missing takes the sector median.
def shrink_floor(table: pd.DataFrame, var_col: str, sectors: pd.DataFrame) -> pd.Series:
    f = table.merge(sectors, on=["eom", "permno"], how="left")
    med = f.groupby(["eom", "sector"])[var_col].transform("median")
    shrunk = (1 - SHRINK) * f[var_col] + SHRINK * med
    shrunk = shrunk.fillna(med)
    floor = shrunk.groupby(f["eom"]).transform(lambda s: s.quantile(FLOOR_Q))
    return pd.Series(np.maximum(shrunk.to_numpy(), floor.to_numpy()), index=table.index)


# Walk-forward HAR variances at each eom (fit on earlier formation years).
def har_forecast(feats: pd.DataFrame, realised: pd.DataFrame) -> pd.DataFrame:
    f = feats.merge(realised, on=["eom", "permno"], how="left")
    names = [f"har_{n}" for n in WINDOWS]
    f["har_var"] = np.nan
    f["log_var"] = np.log(f["realised_var"].clip(lower=1e-10)) / 2  # log vol target
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
