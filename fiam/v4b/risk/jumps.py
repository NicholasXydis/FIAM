# Jump probabilities as a risk metric (LESSONS 57-61; exploration, not yet frozen).
#
# The short leg loses to a few large upward jumps (one name-month in twenty
# averages +43-56%), which a variance number treats like any 3-sigma move.
# This module measures each name's jump history from daily returns and models
# the probability that next month's relative return is a jump, separately for
# the direction that hurts a short (up) and a long (down).
#
# Daily jumps (Lee-Mykland style): e_d = r_d - market_d (equal-weight mean of
#   the day's names); a jump is |e_d| > C * sqrt(BV_d), where BV_d is bipower
#   variation (pi/2) * mean(|e||e_-1|) over the previous 63 sessions. Bipower
#   variation is robust to the jumps it is used to find.
# Source: the organisers' dsf_mini daily returns for every year, so both
#   windows use one file. A stock-month's daily returns are kept only if they
#   compound to the panel's monthly total return within RECONCILE; that drops
#   unadjusted splits (the 2026 defect) using only month-t data.
# Features at eom t use sessions <= t only. Labels: next month's return
#   relative to the shortable pool's equal-weight mean, >= +JUMP (up) or
#   <= -JUMP (down). Models: logistic regression, refit each January on an
#   expanding window of realised labels (case §8.1: refit on a schedule).

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from fiam.v4b.forecast import data

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
OUT = ROOT / "out" / "risk" / "jumps"
CUT = pd.Timestamp("2026-08-31")
C = 4.0
BV_WINDOW = 63
RECONCILE = 0.02
JUMP = 0.20
SHORT_FLOOR = 500.0
# Pre-specified features (no search): jump history, volatility shape, size,
# price, recent move, sector and recent 8-K activity.
FEATURES = [
    "up_jumps_252", "dn_jumps_252", "jump_share_63", "max_up_jump_252", "max_dn_jump_252",
    "log_ivol", "rmax1_21d", "iskew_capm_21d", "log_me", "log_prc", "ret_1_0",
    "turnover_126d", "healthcare", "filings_30d", "deal_8k_30d",
]
# 8-K items for agreements and acquisitions (1.01, 2.01) and other events (8.01).
DEAL_ITEMS = {"1.01", "2.01", "8.01"}


# Daily returns from the organisers' file, kept only where they reconcile.
def daily() -> pd.DataFrame:
    path = CACHE / "jumps_daily.parquet"
    if path.exists():
        return pd.read_parquet(path)
    d = pd.read_csv(data.DSF, usecols=["permno", "date", "daily_return"],
                    dtype={"permno": "int64", "date": "int64", "daily_return": "float64"})
    d = d[d["date"] <= int(f"{CUT:%Y%m%d}")].dropna()
    d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d")
    d["eom"] = d["date"] + pd.offsets.MonthEnd(0)
    comp = np.expm1(np.log1p(d["daily_return"].clip(lower=-0.999)).groupby([d["permno"], d["eom"]]).sum())
    p = pd.read_parquet(data.PANEL, columns=["permno", "eom", "ret"], filters=[("eom", "<=", CUT)])
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    chk = comp.rename("comp").reset_index().merge(p, on=["permno", "eom"], how="left")
    chk["ok"] = (chk["comp"] - chk["ret"]).abs() <= RECONCILE
    d = d.merge(chk[["permno", "eom", "ok"]], on=["permno", "eom"], how="left")
    d = d[d["ok"].fillna(False)].drop(columns="ok")
    CACHE.mkdir(parents=True, exist_ok=True)
    d.to_parquet(path, index=False)
    return d


# Daily jump flags from market-adjusted returns and lagged bipower variation.
def flags(d: pd.DataFrame) -> pd.DataFrame:
    wide = d.pivot(index="date", columns="permno", values="daily_return").sort_index()
    e = wide.sub(wide.mean(axis=1), axis=0)
    a = e.abs()
    bv = (np.pi / 2) * (a * a.shift(1)).rolling(BV_WINDOW, min_periods=BV_WINDOW // 2).mean().shift(1)
    rv = (e**2).rolling(BV_WINDOW, min_periods=BV_WINDOW // 2).mean()
    bv_now = (np.pi / 2) * (a * a.shift(1)).rolling(BV_WINDOW, min_periods=BV_WINDOW // 2).mean()
    thr = C * np.sqrt(bv)
    up = (e > thr) & thr.notna()
    dn = (e < -thr) & thr.notna()
    return dict(e=e, up=up, dn=dn, share=((rv - bv_now) / rv).clip(lower=0.0))


# Jump features at each eom from sessions <= eom.
def jump_features(d: pd.DataFrame) -> pd.DataFrame:
    f = flags(d)
    e, up, dn = f["e"], f["up"], f["dn"]
    win = 252
    out = {
        "up_jumps_252": up.astype(float).rolling(win, min_periods=63).sum(),
        "dn_jumps_252": dn.astype(float).rolling(win, min_periods=63).sum(),
        "max_up_jump_252": e.where(up, 0.0).rolling(win, min_periods=63).max(),
        "max_dn_jump_252": (-e).where(dn, 0.0).rolling(win, min_periods=63).max(),
        "jump_share_63": f["share"],
    }
    eoms = pd.Series(e.index, index=e.index).groupby(e.index + pd.offsets.MonthEnd(0)).max()
    rows = []
    for name, frame in out.items():
        s = frame.loc[eoms.to_numpy()]
        s.index = eoms.index
        rows.append(s.stack().rename(name))
    feats = pd.concat(rows, axis=1).reset_index()
    feats.columns = ["eom", "permno", *out.keys()]
    feats["eom"] = feats["eom"].astype("datetime64[ns]")
    return feats


# 8-K counts in the 30 days before each eom (filing date <= eom).
def filing_features(keys: pd.DataFrame) -> pd.DataFrame:
    f = pd.read_parquet(ROOT.parents[1] / "data" / "fiam_v1" / "filings.parquet",
                        columns=["permno", "filing_date", "items"])
    f["filing_date"] = pd.to_datetime(f["filing_date"])
    f["deal"] = f["items"].map(lambda xs: bool(DEAL_ITEMS & set(map(str, xs))) if xs is not None else False)
    # Filings dated in calendar month t (all within ~30 days of eom t).
    f["eom"] = f["filing_date"] + pd.offsets.MonthEnd(0)
    cur = f.groupby(["permno", "eom"]).agg(filings_30d=("deal", "size"), deal_8k_30d=("deal", "sum"))
    out = keys.merge(cur.reset_index(), on=["permno", "eom"], how="left")
    out[["filings_30d", "deal_8k_30d"]] = out[["filings_30d", "deal_8k_30d"]].fillna(0.0)
    return out


# The modelling frame: shortable pool, features at eom t, relative label for t+1.
def frame() -> pd.DataFrame:
    path = CACHE / "jumps_frame.parquet"
    if path.exists():
        return pd.read_parquet(path)
    p = data.panel(cut=CUT)
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & (p["me"] >= SHORT_FLOOR)].copy()
    cols = ["permno", "eom", "me", "prc", "gics", "ivol_capm_252d", "rmax1_21d", "iskew_capm_21d",
            "ret_1_0", "turnover_126d", "ret_exc_lead1m"]
    p = p[cols]
    p["rel"] = p["ret_exc_lead1m"] - p.groupby("eom")["ret_exc_lead1m"].transform("mean")
    p["y_up"] = (p["rel"] >= JUMP).astype(float).where(p["rel"].notna())
    p["y_dn"] = (p["rel"] <= -JUMP).astype(float).where(p["rel"].notna())
    p["log_ivol"] = np.log(p["ivol_capm_252d"].clip(lower=1e-4))
    p["log_me"] = np.log(p["me"])
    p["log_prc"] = np.log(p["prc"].abs().clip(lower=0.01))
    p["healthcare"] = p["gics"].astype(str).str[:2].eq("35").astype(float)
    p = p.merge(jump_features(daily()), on=["eom", "permno"], how="left")
    p = filing_features(p)
    p.to_parquet(path, index=False)
    return p


# Within-month rank-gauss so a pooled model reads relative standing, not levels.
def _x(f: pd.DataFrame, cols: list[str]) -> np.ndarray:
    from scipy.stats import norm

    r = f.groupby("eom")[cols].rank(pct=True)
    r = r.fillna(0.5).clip(0.001, 0.999)
    x = norm.ppf(r.to_numpy())
    if "healthcare" in cols:
        x[:, cols.index("healthcare")] = f["healthcare"].to_numpy()
    return x


# Annual expanding refits: formations in year Y use labels realised by eom Y-1 Dec.
def predict(f: pd.DataFrame, label: str, cols: list[str]) -> pd.Series:
    out = pd.Series(np.nan, index=f.index)
    years = sorted(f["eom"].dt.year.unique())
    for y in years:
        last_label_eom = pd.Timestamp(f"{y - 1}-11-30")  # label month ends by Dec Y-1
        train = f[(f["eom"] <= last_label_eom) & f[label].notna()]
        test = f["eom"].dt.year == y
        if train["eom"].nunique() < 12 or not test.any():
            continue
        m = LogisticRegression(C=1.0, max_iter=2000)
        m.fit(_x(train, cols), train[label].to_numpy())
        out[test] = m.predict_proba(_x(f[test], cols))[:, 1]
    return out


def _skill(y: np.ndarray, p: np.ndarray, base: float) -> dict:
    ok = np.isfinite(p) & np.isfinite(y)
    y, p = y[ok], p[ok]
    b = brier_score_loss(y, p)
    b0 = brier_score_loss(y, np.full_like(p, base))
    return {"n": int(len(y)), "rate": float(y.mean()), "auc": float(roc_auc_score(y, p)),
            "brier_skill": float(1 - b / b0)}


# Calibration and skill by window; the full model against ivol-only.
def evaluate() -> dict:
    f = frame()
    rep = {}
    for label in ("y_up", "y_dn"):
        full = predict(f, label, FEATURES)
        ivol = predict(f, label, ["log_ivol"])
        f[f"p_{label}"] = full
        f[f"p_{label}_ivol"] = ivol
        for w, (lo, hi) in {"valid": ("2016-12-31", "2020-11-30"), "oos": ("2020-12-31", "2026-07-31")}.items():
            k = f["eom"].between(pd.Timestamp(lo), pd.Timestamp(hi)) & f[label].notna()
            base = float(f.loc[f["eom"] < pd.Timestamp(lo), label].mean())
            y = f.loc[k, label].to_numpy()
            dec = pd.qcut(f.loc[k, f"p_{label}"].rank(method="first"), 10, labels=False)
            cal = pd.DataFrame({"p": f.loc[k, f"p_{label}"], "y": y}).groupby(dec.to_numpy()).mean()
            rep[f"{label}_{w}"] = {
                "full": _skill(y, f.loc[k, f"p_{label}"].to_numpy(), base),
                "ivol_only": _skill(y, f.loc[k, f"p_{label}_ivol"].to_numpy(), base),
                "calibration_by_decile": {int(i): [float(r.p), float(r.y)] for i, r in cal.iterrows()},
            }
    f[["permno", "eom", "p_y_up", "p_y_dn", "p_y_up_ivol", "p_y_dn_ivol"]].to_parquet(OUT / "probabilities.parquet", index=False)
    # Coefficients of the last fit, for reading (rank-gauss units).
    last = f[f["y_up"].notna()]
    for label in ("y_up", "y_dn"):
        m = LogisticRegression(C=1.0, max_iter=2000).fit(_x(last, FEATURES), last[label].to_numpy())
        rep[f"{label}_coef_full_sample_for_reading_only"] = dict(zip(FEATURES, np.round(m.coef_[0], 3).tolist()))
    return rep


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    r = evaluate()
    (OUT / "evaluation.json").write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=1))
