# Fold 1: train on targets 2015-02..2018-12, validate 2019-01..2020-12 (R§3).
# Baseline only: the forecaster is E-LASSO (DECISIONS.md D6, v4b/elasso/).

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine.mandate import load as load_mandate
from fiam.v4b.forecast import data, evaluate, nonlinear, prep, ridge

OUT = Path(__file__).resolve().parents[1] / "out" / "forecast" / "fold1"
HORIZONS = (1, 3, 5, 10, 21, 42, 63)
BUCKETS = ((0, 1), (1, 3), (3, 5), (5, 10), (10, 21), (21, 42), (42, 63))
TRAIN = ("2015-01-31", "2018-11-30")
VALID = ("2018-12-31", "2020-11-30")
# Ridge penalty multipliers on the EB shape; three registry trials.
MULTIPLIERS = (0.25, 1.0, 4.0)
# Hurdle IC band from research/hurdle_by_size.out (N 200..500).
HURDLE_IC = (0.031, 0.039)
LABEL = "y21"


# Rows of one window by eom, inclusive.
def window(frame: pd.DataFrame, span) -> pd.Series:
    return frame["eom"].between(pd.Timestamp(span[0]), pd.Timestamp(span[1]))


# Within-month rank of a score in [-0.5, 0.5].
def mrank(eom, score) -> np.ndarray:
    s = pd.Series(score).groupby(np.asarray(eom)).rank(pct=True)
    return (s - 0.5).to_numpy()


# Within-month demeaned, winsorised label for the ridge.
def ridge_label(frame: pd.DataFrame) -> np.ndarray:
    y = prep.winsor_label(frame, LABEL)
    return (y - y.groupby(frame["eom"]).transform("mean")).to_numpy()


# Everything the fold needs, built once.
def build(dividends: bool = False):
    m = load_mandate()
    chars = data.characteristics()
    banned = set(chars) & set(m.banned_features)
    if banned:
        raise ValueError(f"banned columns in the 147: {sorted(banned)}")
    p = data.panel()
    d = data.with_dividends(data.daily()) if dividends else data.daily()
    labels = data.daily_labels(p, d, HORIZONS)
    p = p.merge(labels, on=["eom", "permno"], how="left")
    p = p.join(data.tradable(p, short_floor_musd=m.hard.short_floor_musd))
    return m, chars, p


# Runs fold 1 and writes the report; returns it.
def main() -> dict:
    m, chars, p = build()
    u = p[p["long_ok"]].reset_index(drop=True)
    x = prep.rank_features(u, chars)
    first_valid = u.loc[window(u, VALID), "s0"].min()
    train = window(u, TRAIN) & u[LABEL].notna() & (u[f"end{21}"] < first_valid)
    valid = window(u, VALID) & u[LABEL].notna()
    registry = []

    tr, va = u[train], u[valid]
    xt, xv = x[train.to_numpy()], x[valid.to_numpy()]
    w = prep.month_weights(tr)
    months = tr["eom"].nunique()
    groups = ridge.families(xt)
    s = ridge.stats(xt, ridge_label(tr), w, months)
    base = ridge.empirical_bayes(s, groups)
    ic = {}
    fits = {}
    for mult in MULTIPLIERS:
        f = ridge.scaled(s, base, mult)
        fits[mult] = f
        ic[mult] = evaluate.monthly_ic(va["eom"], xv @ f.theta, va[LABEL])
        registry.append({"config": f"ridge_m{mult}", "df": f.df})
    pick = evaluate.one_se(ic)
    gate = months / 5
    passing = [k for k in MULTIPLIERS if k >= pick and fits[k].df <= gate]
    chosen = passing[0] if passing else pick
    rfit = fits[chosen]
    r_val = xv @ rfit.theta

    yrank = mrank(tr["eom"], tr[LABEL])
    members = {"mlp": nonlinear.fit_mlp(xt, yrank, w), "gbt": nonlinear.fit_gbt(xt, yrank, w)}
    registry += [{"config": "mlp_fixed"}, {"config": "gbt_fixed"}]
    scores = {"ridge": r_val}
    for k, mem in members.items():
        scores[k] = mem.predict(xv)
    blends = {k: 0.5 * mrank(va["eom"], r_val) + 0.5 * mrank(va["eom"], scores[k]) for k in members}
    bic = {k: evaluate.monthly_ic(va["eom"], b, va[LABEL]) for k, b in blends.items()}
    duel = evaluate.paired(bic["gbt"], bic["mlp"])
    use = "gbt" if duel and duel["mean"] > duel["se"] else "mlp"
    blend = blends[use]

    report = {
        "fold": {
            "train_eom": TRAIN,
            "valid_eom": VALID,
            "label": LABEL,
            "train_months": months,
            "valid_months": int(va["eom"].nunique()),
            "train_rows": int(train.sum()),
            "valid_rows": int(valid.sum()),
            "universe": "long_ok: price>=5, dolvol_126d>=$2m",
        },
        "ridge": {
            "families": int(groups.max() + 1),
            "tau2": base.tau2.tolist(),
            "sigma2": base.sigma2,
            "df_by_multiplier": {k: f.df for k, f in fits.items()},
            "ic_by_multiplier": {k: v.mean() for k, v in ic.items()},
            "one_se_pick": pick,
            "df_gate": gate,
            "chosen": chosen,
            "df_chosen": rfit.df,
            "df_gate_pass": rfit.df <= gate,
        },
        "members": {
            k: evaluate.summary(evaluate.monthly_ic(va["eom"], v, va[LABEL]))
            for k, v in scores.items()
        },
        "blend_duel_gbt_minus_mlp": duel,
        "nonlinear_used": use,
        "blend": _blend_evidence(u, valid, blend, va, x, chars, rfit, members[use], p),
        "heterogeneity": _heterogeneity(tr, xt, w, rfit),
        "registry": registry,
    }
    report["hurdle"] = _hurdle(report["blend"]["ic"]["all"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=_plain) + "\n")
    va.assign(ridge=r_val, nonlinear=scores[use], blend=blend)[
        ["eom", "permno", "ridge", "nonlinear", "blend", LABEL, "short_ok"]
    ].to_parquet(OUT / "predictions_valid.parquet", index=False)
    pd.DataFrame(registry).to_csv(OUT / "registry.csv", index=False)
    return report


# IC, legs, baseline label, full-universe diagnostic, decay, calibration.
def _blend_evidence(u, valid, blend, va, x, chars, rfit, mem, p) -> dict:
    ic = evaluate.monthly_ic(va["eom"], blend, va[LABEL])
    short = evaluate.monthly_ic(va["eom"], blend, va[LABEL], va["short_ok"].to_numpy())
    monthly = evaluate.monthly_ic(va["eom"], blend, va["ret_exc_lead1m"])
    full = p[window(p, VALID) & p[LABEL].notna()].reset_index(drop=True)
    xf = prep.rank_features(full, chars)
    fb = 0.5 * mrank(full["eom"], xf @ rfit.theta) + 0.5 * mrank(full["eom"], mem.predict(xf))
    full_ic = evaluate.monthly_ic(full["eom"], fb, full[LABEL])
    frame = va.assign(score=blend)
    decay = evaluate.decay_fit(evaluate.decay_slopes(frame, "score", BUCKETS), BUCKETS)
    z = frame.groupby("eom")["score"].transform(lambda s: (s - s.mean()) / s.std())
    yd = frame[LABEL] - frame.groupby("eom")[LABEL].transform("mean")
    slope = float(
        (z * yd).groupby(frame["eom"]).mean().sum() / (z**2).groupby(frame["eom"]).mean().sum()
    )
    return {
        "ic": evaluate.summary(ic),
        "ic_short_eligible": evaluate.summary(short),
        "ic_monthly_label": evaluate.summary(monthly),
        "ic_full_universe_diagnostic": evaluate.summary(full_ic),
        "decay": decay,
        "calibration_per_unit_z_21d": slope,
    }


# Large vs small slopes with the chosen penalties (08 M3 gate).
def _heterogeneity(tr, xt, w, rfit) -> dict:
    big = (tr["me"] >= tr.groupby("eom")["me"].transform("median")).to_numpy()
    out = {}
    for name, part in (("large", big), ("small", ~big)):
        sub = tr[part]
        s = ridge.stats(xt[part], ridge_label(sub), prep.month_weights(sub), sub["eom"].nunique())
        out[name] = ridge.solve(s, rfit.lam, rfit.groups).theta
    a, b = out["large"], out["small"]
    big_coef = np.abs(rfit.theta) >= np.median(np.abs(rfit.theta))
    return {
        "theta_corr": float(np.corrcoef(a, b)[0, 1]),
        "sign_agreement_top_half": float(np.mean(np.sign(a[big_coef]) == np.sign(b[big_coef]))),
    }


# Measured validation IC against the hurdle band.
def _hurdle(ic: dict | None) -> dict:
    if ic is None:
        return {"status": "n/a"}
    return {
        "valid_ic": ic["mean"],
        "needed_ic": HURDLE_IC,
        "gap_to_low_end": ic["mean"] - HURDLE_IC[0],
        "clears": ic["mean"] >= HURDLE_IC[0],
    }


# JSON for numpy and pandas scalars.
def _plain(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


if __name__ == "__main__":
    r = main()
    print(
        json.dumps(
            {k: r[k] for k in ("ridge", "nonlinear_used", "hurdle")}, indent=2, default=_plain
        )
    )
