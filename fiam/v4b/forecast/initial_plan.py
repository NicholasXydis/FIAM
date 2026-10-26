# The initial plan's forecaster tested as written: nested walk-forward 2017-2020.
# Baseline only: the forecaster is E-LASSO (DECISIONS.md D6, v4b/elasso/).

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.forecast import evaluate, nonlinear, prep, ridge, run, targets

OUT = Path(__file__).resolve().parents[1] / "out" / "forecast" / "initial_plan"
TEST_YEARS = (2017, 2018, 2019, 2020)
# Ridge scale path, times the mean diagonal of X'WX; six registry trials each.
PATH = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
# A characteristic gets a missingness indicator above this training share.
MISSING_MIN = 0.05
EVAL = "y21"
# Each config: model, label, and the plan's optional pieces.
CONFIGS = {
    "R1_ridge": dict(model="ridge", hier=False, label="y21"),
    "R2_hier": dict(model="ridge", hier=True, label="y21"),
    "R3_hier_sector": dict(model="ridge", hier=True, label="y21", sector=True),
    "R4_hier_missing": dict(model="ridge", hier=True, label="y21", missing=True),
    "R5_hier_monthly": dict(model="ridge", hier=True, label="ret_exc_lead1m"),
    "R6_hier_sector_dm": dict(model="ridge", hier=True, label="y21_sector"),
    "R7_hier_residual": dict(model="ridge", hier=True, label="y21_res"),
    "R8_hier_sqrt_adv": dict(model="ridge", hier=True, label="y21", weights="sqrt_adv"),
    "R9_hier_lag1": dict(model="ridge", hier=True, label="y21", lag=True),
    "G1_gbt": dict(model="gbt", label="y21"),
    "G2_gbt_residual": dict(model="gbt", label="y21_res"),
    "M1_mlp": dict(model="mlp", label="y21"),
}


# Labels, features and controls for the tradable universe, built once.
def prepare():
    _, chars, p = run.build(dividends=True)
    u = p[p["long_ok"]].reset_index(drop=True)
    u["y21_sector"] = targets.sector_demeaned(u, "y21")
    u["y21_res"], factors = targets.residual(u, "y21")
    u["ym_end"] = u["eom"] + pd.offsets.MonthEnd(1)
    x = prep.rank_features(u, chars)
    miss = u[chars].isna().astype(np.float32)
    miss = (miss - miss.groupby(u["eom"]).transform("mean")).to_numpy(dtype=np.float32)
    sect = pd.get_dummies(targets.sector(u), dtype=np.float32)
    sect = (sect - sect.groupby(u["eom"]).transform("mean")).to_numpy(dtype=np.float32)
    return u, x, _lagged(u, x), miss, sect, factors, chars


# Last month's feature row for the same stock; zeros if not consecutive.
def _lagged(u: pd.DataFrame, x: np.ndarray) -> np.ndarray:
    key = pd.Series(np.arange(len(u)), index=pd.MultiIndex.from_frame(u[["permno", "eom"]]))
    prev = pd.MultiIndex.from_arrays([u["permno"], u["eom"] - pd.offsets.MonthEnd(1)])
    pos = key.reindex(prev).to_numpy()
    out = np.zeros_like(x)
    ok = ~np.isnan(pos)
    out[ok] = x[pos[ok].astype(int)]
    return out


# Train rows (label ended before the test start) and test rows for one year.
def split(u: pd.DataFrame, year: int, end_col: str, within=None):
    test = u["eom"].between(pd.Timestamp(f"{year - 1}-12-31"), pd.Timestamp(f"{year}-11-30"))
    start = u.loc[test, "s0"].min()
    train = u[end_col] < start
    if within is not None:
        train, test = train & within, test & within
    return train.to_numpy(), test.to_numpy()


# The ridge's design for a config on given rows, with S fitted on train rows.
def design(cfg, x, xl, miss, sect, rows, s=None, keep=None):
    base = xl if cfg.get("lag") else x
    parts = [ridge.hierarchical(base[rows], s) if cfg.get("hier") else base[rows]]
    if cfg.get("sector"):
        parts.append(sect[rows])
    if cfg.get("missing"):
        parts.append(miss[rows][:, keep])
    return np.hstack(parts)


# The ridge label: winsorised within month, then demeaned.
def ridge_label(u: pd.DataFrame, rows, col: str) -> np.ndarray:
    f = u.loc[rows, ["eom", col]]
    y = prep.winsor_label(f, col)
    return (y - y.groupby(f["eom"]).transform("mean")).to_numpy()


# Fits one ridge config on train rows at one scale; returns a predictor.
def fit_ridge(cfg, u, x, xl, miss, sect, train, scale):
    base = xl if cfg.get("lag") else x
    groups = ridge.families(base[train])
    s = ridge.loadings(groups, ridge.orientations(base[train], groups))
    keep = None
    if cfg.get("missing"):
        share = u.loc[train, run.data.characteristics()].isna().mean() > MISSING_MIN
        keep = np.flatnonzero(share.to_numpy())
    z = design(cfg, x, xl, miss, sect, train, s, keep)
    ok = ~np.isnan(u.loc[train, cfg["label"]].to_numpy())
    rows = np.flatnonzero(train)[ok]
    frame = u.loc[rows]
    w = prep.month_weights(frame, cfg.get("weights", "equal"))
    st = ridge.stats(z[ok], ridge_label(u, rows, cfg["label"]), w, frame["eom"].nunique())
    unit = float(np.mean(np.diag(st.xx)))
    fams, feats = groups.max() + 1, base.shape[1]
    extras = z.shape[1] - (fams + feats if cfg.get("hier") else feats)
    if cfg.get("hier"):
        lam = ridge.penalties(scale * unit, fams, feats, extras)
    else:
        lam = np.concatenate([np.full(feats, scale * unit), np.full(extras, scale * unit * 1e-3)])
    a = st.xx + np.diag(lam)
    theta = np.linalg.solve(a, st.xy)
    df = float(np.trace(np.linalg.solve(a, st.xx)))
    return (lambda rows_: design(cfg, x, xl, miss, sect, rows_, s, keep) @ theta), df


# One config's held-out predictions for every test year, with its choices.
def walk(name, cfg, u, x, xl, miss, sect):
    end_col = "ym_end" if cfg["label"] == "ret_exc_lead1m" else "end21"
    preds, picks = [], {}
    for year in TEST_YEARS:
        train, test = split(u, year, end_col)
        if cfg["model"] == "ridge":
            itrain, ival = split(u, year - 1, end_col, within=pd.Series(train))
            ics = {}
            for c in PATH:
                f, _ = fit_ridge(cfg, u, x, xl, miss, sect, itrain, c)
                v = u.loc[ival]
                ics[c] = evaluate.monthly_ic(v["eom"], f(ival), v[cfg["label"]])
            c = evaluate.one_se(ics)
            f, df = fit_ridge(cfg, u, x, xl, miss, sect, train, c)
            score = f(test)
            picks[year] = {"scale": c, "df": df, "inner_ic": {k: v.mean() for k, v in ics.items()}}
        else:
            ok = train & u[cfg["label"]].notna().to_numpy()
            frame = u.loc[ok]
            y = run.mrank(frame["eom"], frame[cfg["label"]])
            w = prep.month_weights(frame)
            fit = nonlinear.fit_gbt if cfg["model"] == "gbt" else nonlinear.fit_mlp
            score = fit(x[ok], y, w).predict(x[test])
            picks[year] = {"train_months": int(frame["eom"].nunique())}
        preds.append(pd.DataFrame({"row": np.flatnonzero(test), name: score}))
    return pd.concat(preds).set_index("row")[name], picks


# Top-minus-bottom 10% mean of a label per month.
def spread(eom, score, label, q: float = 0.1) -> pd.Series:
    f = pd.DataFrame({"eom": eom, "s": score, "y": label}).dropna()

    def one(g):
        r = g["s"].rank(pct=True)
        return g["y"][r > 1 - q].mean() - g["y"][r <= q].mean()

    return f.groupby("eom").apply(one, include_groups=False)


# Intercept of a monthly series on factor returns, Newey-West t (3 lags).
def factor_alpha(series: pd.Series, factors: pd.DataFrame) -> dict | None:
    both = pd.concat([series.rename("y"), factors], axis=1, join="inner").dropna()
    if len(both) < evaluate.MIN_MONTHS + factors.shape[1]:
        return None
    x = np.column_stack([np.ones(len(both)), both[factors.columns].to_numpy()])
    y = both["y"].to_numpy()
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    e = y - x @ coef
    xe = x * e[:, None]
    s = xe.T @ xe
    for k in range(1, 4):
        g = xe[k:].T @ xe[:-k]
        s += (1 - k / 4) * (g + g.T)
    inv = np.linalg.inv(x.T @ x)
    se = float(np.sqrt((inv @ s @ inv)[0, 0]))
    return {
        "n": len(both),
        "alpha": float(coef[0]),
        "t": float(coef[0] / se),
        "loadings": dict(zip(factors.columns, coef[1:].tolist())),
    }


# Date-balanced slope of the demeaned label on the demeaned score.
def calibration(eom, score, label) -> float:
    f = pd.DataFrame({"eom": eom, "s": score, "y": label}).dropna()
    s = f["s"] - f.groupby("eom")["s"].transform("mean")
    y = f["y"] - f.groupby("eom")["y"].transform("mean")
    return float((s * y).groupby(f["eom"]).mean().sum() / (s**2).groupby(f["eom"]).mean().sum())


# Month-to-month rank correlation of the score and top-decile churn.
def persistence(eom, permno, score) -> dict:
    f = pd.DataFrame({"eom": eom, "permno": permno, "s": score}).dropna()
    f["r"] = f.groupby("eom")["s"].rank(pct=True)
    wide = f.pivot(index="eom", columns="permno", values="r")
    corr = [wide.iloc[i].corr(wide.iloc[i - 1]) for i in range(1, len(wide))]
    top = wide > 0.9
    churn = [
        1 - (top.iloc[i] & top.iloc[i - 1]).sum() / max(top.iloc[i].sum(), 1)
        for i in range(1, len(top))
    ]
    return {"rank_autocorr": float(np.nanmean(corr)), "top_decile_churn": float(np.mean(churn))}


# Mean and sd over months of the score's correlation with each exposure.
def exposures(u: pd.DataFrame, rows, score) -> dict:
    f = u.loc[rows, ["eom"]].assign(s=score)
    out = {}
    for k, col in targets.EXPOSURES.items():
        f["z"] = targets.zrank(u.loc[rows], col).to_numpy()
        c = f.groupby("eom").apply(lambda g: g["s"].corr(g["z"]), include_groups=False)
        out[k] = {"mean": float(c.mean()), "sd": float(c.std())}
    return out


# Everything one config is judged on, over the held-out months.
def judge(u, factors, score: pd.Series) -> dict:
    rows = score.index.to_numpy()
    f = u.loc[rows]
    s = score.to_numpy()
    ic = evaluate.monthly_ic(f["eom"], s, f[EVAL])
    big = (f["dolvol_126d"] >= f.groupby("eom")["dolvol_126d"].transform("median")).to_numpy()
    sp = spread(f["eom"], s, f[EVAL])
    halves = {
        "2017-18": sp[sp.index.year <= 2018].mean() if len(sp) else None,
        "2019-20": sp[sp.index.year >= 2019].mean() if len(sp) else None,
    }
    return {
        "ic": evaluate.summary(ic),
        "ic_short_eligible": evaluate.summary(
            evaluate.monthly_ic(f["eom"], s, f[EVAL], f["short_ok"].to_numpy())
        ),
        "ic_liquid_half": evaluate.summary(evaluate.monthly_ic(f["eom"], s, f[EVAL], big)),
        "ic_illiquid_half": evaluate.summary(evaluate.monthly_ic(f["eom"], s, f[EVAL], ~big)),
        "ic_residual_label": evaluate.summary(evaluate.monthly_ic(f["eom"], s, f["y21_res"])),
        "ic_monthly_label": evaluate.summary(evaluate.monthly_ic(f["eom"], s, f["ret_exc_lead1m"])),
        "spread10": {
            "all": evaluate.mean_t(sp),
            "halves": halves,
            "by_year": {str(y): float(v.mean()) for y, v in sp.groupby(sp.index.year)},
        },
        "spread10_factor_alpha": factor_alpha(sp, factors),
        "calibration_slope": calibration(f["eom"], s, f[EVAL]),
        "persistence": persistence(f["eom"], f["permno"], s),
        "exposures": exposures(u, rows, s),
    }


# Runs every config, writes predictions, report and registry.
def main(only=None) -> dict:
    u, x, xl, miss, sect, factors, _ = prepare()
    names = [n for n in CONFIGS if only is None or n in only]
    scores, picks, report, registry = {}, {}, {}, []
    for name in names:
        cfg = CONFIGS[name]
        scores[name], picks[name] = walk(name, cfg, u, x, xl, miss, sect)
        report[name] = judge(u, factors, scores[name]) | {"choices": picks[name]}
        trials = len(PATH) if cfg["model"] == "ridge" else 1
        registry.append({"config": name, **cfg, "trials": trials})
        print(
            name,
            "IC",
            round(report[name]["ic"]["all"]["mean"], 4),
            "spread",
            round(report[name]["spread10"]["all"]["mean"] * 100, 2),
            flush=True,
        )
    both = pd.concat(scores, axis=1)
    ics = {
        n: evaluate.monthly_ic(u.loc[both.index, "eom"], both[n], u.loc[both.index, EVAL])
        for n in names
    }
    sps = {n: spread(u.loc[both.index, "eom"], both[n], u.loc[both.index, EVAL]) for n in names}
    ref = "R2_hier"
    if ref in names:
        report["paired_vs_R2_hier"] = {
            n: {
                "ic": evaluate.paired(ics[n], ics[ref]),
                "spread10": evaluate.paired(sps[n], sps[ref]),
            }
            for n in names
            if n != ref
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=run._plain) + "\n")
    both.join(u[["eom", "permno", EVAL, "y21_res", "short_ok"]]).to_parquet(
        OUT / "predictions_heldout.parquet"
    )
    factors.to_csv(OUT / "factor_returns_21d.csv")
    pd.DataFrame(registry).to_csv(OUT / "registry.csv", index=False)
    return report


if __name__ == "__main__":
    main()
