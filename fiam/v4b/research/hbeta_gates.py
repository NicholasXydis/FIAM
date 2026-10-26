# D21 phase 1: H-beta on W17..W20 (each window: formations Dec 31 and Jan 31,
# held to the end of February, a fresh book per window). Beta in force = the
# uncalibrated engine beta (B1); E6 adds Welch+Dimson and beta_60m bands and
# style bands at 0.25 (config variant_e6_<score>_hb.json). H-ref = the HHRZ
# reference book with legs scaled to B1 beta 0 at gross 1.8, no optimiser.
#
# Gates (pooled over the four windows' sessions):
#   G1  every formation: E6 = D19 checks; H-ref = hard rules, reported not repaired
#   G2  sd(daily return / predicted daily vol), 90% chi2 CI in [2/3, 3/2]: book, legs
#   HB  realised book beta on the S&P 500, HC3 90% CI in [-0.10, 0.10]
#   G4  (E6) var(E6) < var(HHRZ reference), raw and S&P-hedged at predicted beta,
#       one-sided Pitman-Morgan p < 0.05, powered ex ante
#   G5  waits for the execution audit (0c)
# Reported, not gates: per-window HB; paired directions (long, short, book, adverse =
# top-minus-bottom B1 quintile) realised vs predicted beta under B1 and B0; variance
# ratios under the factor model, diagonal, single index and Ledoit-Wolf, calm (W17,
# W19) vs stressed (W18, W20). Missing returns: per-leg renormalisation (Amendment 2).
#
# Usage: FIAM_V4B_CONFIG=variant_e6_betamatch_hb.json python -m fiam.v4b.research.hbeta_gates
#        on Modal: modal run fiam/v4b/gpu/modal_book.py::hbeta

import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from fiam.v4b.elasso import forecaster
from fiam.v4b.engine import checker, inputs, ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.research.beta_gates import WINDOWS
from fiam.v4b.research.e6_gates import (ALPHA, RISK_BAND, book_beta_gate, cov, ols_beta, path,
                                        pitman_morgan)
from fiam.v4b.research.twostep_screen import score_mu
from fiam.v4b.risk import beta_cal
from fiam.v4b.risk import model as risk_model

V4B = Path(__file__).resolve().parents[1]
OUT = V4B / "out" / "hbeta_gates"
SCORES, WEIGHTINGS = ("betamatch", "betamatch_s6"), ("vw", "ew")
STRESSED = ("W18", "W20")
HIST, MIN_HIST = 252, 200


# Daily covariance models on prior sessions for a set of names: diagonal, single
# index (S&P) and Ledoit-Wolf (2003) shrinkage of the sample toward that index.
def alt_covs(hist: pd.DataFrame, m: pd.Series) -> dict:
    X = hist.to_numpy(dtype=float)
    X = X - np.nanmean(X, axis=0)
    X = np.nan_to_num(X)
    T = X.shape[0]
    xm = (m.to_numpy(dtype=float) - np.nanmean(m))
    xm = np.nan_to_num(xm)
    S = X.T @ X / T
    smm = xm @ xm / T
    sim = X.T @ xm / T
    beta = sim / smm
    resid = np.maximum(np.diag(S) - beta ** 2 * smm, 0.1 * np.diag(S))
    F = np.outer(beta, beta) * smm
    np.fill_diagonal(F, np.diag(S))
    single = np.outer(beta, beta) * smm + np.diag(resid)
    # Ledoit-Wolf (2003) intensity: kappa = (pi - rho) / gamma, delta = clip(kappa / T).
    X2 = X ** 2
    pi_mat = X2.T @ X2 / T - S ** 2
    pi = pi_mat.sum()
    A = (X2 * xm[:, None]).T @ X / T  # A_ij = mean(x_i^2 x_j x_m)
    C = (X * xm[:, None]).T @ (X * xm[:, None]) / T  # C_ij = mean(x_m^2 x_i x_j)
    sj, si = sim[None, :], sim[:, None]
    r_mat = (sj * smm * A + si * smm * A.T - si * sj * C) / smm ** 2 - F * S
    np.fill_diagonal(r_mat, np.diag(pi_mat))
    rho = r_mat.sum()
    gamma = ((F - S) ** 2).sum()
    delta = float(np.clip((pi - rho) / gamma / T, 0.0, 1.0)) if gamma > 0 else 1.0
    lw = delta * F + (1 - delta) * S
    return {"diagonal": np.diag(np.diag(S)), "single_index": single, "ledoit_wolf": lw, "lw_delta": delta}


def hc3_beta(y: np.ndarray, x: np.ndarray) -> dict:
    g = book_beta_gate(y, x, method="hc3")
    return {"beta": g["beta"], "ci90": g["ci90"], "sessions": g["sessions"]}


# H-ref: the paper's reference legs, scaled so B1 book beta is 0 at gross 1.8.
def href_book(c, dec, wt, beta, gross):
    ref = optimize.hhrz_reference(c, dec, wt, gross)
    b = beta.reindex(ref.index).fillna(beta.median())
    bl, bs = float(b[ref > 0] @ ref[ref > 0]), float(b[ref < 0] @ ref[ref < 0])
    if bl <= 0 or bs >= 0:
        return None, {"long_beta": bl, "short_beta": bs}
    r = -bs / bl
    w = ref.copy()
    w[w > 0] *= 2 * r / (1 + r)
    w[w < 0] *= 2 / (1 + r)
    return w, {"long_scale": 2 * r / (1 + r), "short_scale": 2 / (1 + r)}


def hard_checks(w: pd.Series, f, m) -> dict:
    side = f.snap["month"]["sector"].reindex(w.index)
    return {
        "names": m.hard.names_min <= len(w) <= m.hard.names_max,
        "name_cap": float(w.abs().max()) <= m.hard.name_cap + 1e-9,
        "gross": float(w.abs().sum()) <= m.hard.gross_max + 1e-9,
        "net": abs(float(w.sum())) <= m.hard.net_band + 1e-9,
        "short_floor": checker.short_floor_formation(w, f.snap["month"], m.hard.short_floor_musd),
        "short_gross_research": float(-w[w < 0].sum()) * m.hard.nav0 / 1e6 >= m.hard.short_floor_musd - 1e-6,
        "sectors_two_sided": set(side[w > 0]) == set(side[w < 0]),
    }


def run() -> dict:
    m = load()
    assert not m.policy.beta_calibration and m.policy.beta_source == "engine" and m.policy.beta_bands_extra
    world = ladder.World(m)
    maps = beta_cal.monthly_maps(world.rm)  # for B0 = the calibrated beta, reported only
    rets, sessions = world.market["returns"], world.sessions
    sp_all = inputs.market_returns(sessions)
    kappa = forecaster.kappa_for(m, "Elasso_MaInf")
    mus = {s: score_mu(m, s) for s in SCORES}
    mus = {s: {e: g.set_index("permno")["mu"] for e, g in f.groupby("eom")} for s, f in mus.items()}
    steps = {wt: dataclasses.replace(ladder.steps(n_e3=250)["E6" if wt == "vw" else "E6_ew"]) for wt in WEIGHTINGS}
    variants = [(kind, s, wt) for kind in ("E6", "Href") for s in SCORES for wt in WEIGHTINGS]
    acc = {v: {"g1": [], "z": {"book": [], "long": [], "short": []}, "alt": [], "book": [], "ref": [],
               "ref_h": [], "mkt": [], "win": [], "exante": [], "dirs": {}} for v in variants}
    adverse = []
    for key, (eom0, end) in WINDOWS.items():
        eoms = [eom0, eom0 + pd.offsets.MonthEnd(1)]
        days_sig = [world.signal_day(e) for e in eoms] + [end]
        periods = [sessions[(sessions > days_sig[k]) & (sessions <= days_sig[k + 1])] for k in range(2)]
        state = {v: pd.Series(dtype=float) for v in variants}
        for k, e in enumerate(eoms):
            base = world.formation(e, "Elasso_MaInf", pd.Series(dtype=float))
            snap = base.snap
            b1 = snap["beta"]
            ab = beta_cal.map_at(maps, snap["s0"])
            b0 = (ab[0] + ab[1] * b1) if ab else b1
            r = rets.reindex(index=periods[k])
            mk = sp_all.reindex(periods[k]).to_numpy()
            hscale = forecaster.horizon_scale(0, base.horizon, kappa)
            hist_days = sessions[sessions <= days_sig[k]][-HIST:]
            sp_hist = sp_all.reindex(hist_days)
            # Adverse direction: top-minus-bottom B1 quintile of the candidates, equal weight.
            cand = optimize._candidates(base, m, steps["vw"]).index.intersection(b1.index)
            q = pd.qcut(b1.loc[cand], 5, labels=False)
            top, bot = cand[(q == 4).to_numpy()], cand[(q == 0).to_numpy()]
            adv = pd.concat([pd.Series(0.5 / len(top), index=top), pd.Series(-0.5 / len(bot), index=bot)])
            pa = path(adv, r, missing="legs")
            adverse.append({"window": key, "eom": str(e.date()), "real": hc3_beta(pa.to_numpy(), mk),
                            "pred_b1": float(b1.reindex(adv.index) @ adv), "pred_b0": float(b0.reindex(adv.index) @ adv),
                            "ret": pa.tolist(), "mkt": mk.tolist()})
            for v in variants:
                kind, s, wt = v
                a = acc[v]
                w_pre = state[v]
                if k and not w_pre.empty:
                    w_pre = optimize.drift(w_pre, rets.loc[(rets.index > days_sig[0]) & (rets.index <= days_sig[1])])
                f = dataclasses.replace(base, mu=mus[s].get(e, pd.Series(dtype=float)) * hscale, w_pre=w_pre)
                c, dec = optimize.hhrz_deciles(optimize._candidates(f, m, steps[wt]), f.nyse_me, wt)
                if kind == "E6":
                    w, log = optimize.build_book(f, m, steps[wt])
                    if w is None:
                        a["g1"].append({"window": key, "eom": str(e.date()), "pass": False, "status": log.get("status")})
                        state[v] = w_pre
                        continue
                    first = (log["attempts"] or [{}])[0]
                    chk = {"first_rung_optimal": bool(first.get("ok") and first.get("status") == "optimal"
                                                      and log["rho"] == 0.9 and log["ladder_gross"] == m.policy.target_gross),
                           "floor": log["mu_w"] >= 0.9 * log["mu_ref"] - 1e-9,
                           "beta_slack": (log.get("slacks") or {}).get("beta", 0.0) <= 1e-6,
                           "union_fits": bool(log.get("union_fits", True)), **hard_checks(w, f, m)}
                    extra = {"beta_extra_slack": (log.get("slacks") or {}).get("beta_extra_max"),
                             "rho": log["rho"], "gross": log["ladder_gross"]}
                    gross = float(log["ladder_gross"])
                else:
                    w, info = href_book(c, dec, wt, b1, m.policy.target_gross)
                    if w is None:
                        a["g1"].append({"window": key, "eom": str(e.date()), "pass": False, **info})
                        state[v] = w_pre
                        continue
                    chk, extra, gross = hard_checks(w, f, m), info, m.policy.target_gross
                ex_b = snap.get("beta_extra")
                a["g1"].append({"window": key, "eom": str(e.date()), "pass": all(chk.values()), **chk, **extra,
                                "names_n": int(len(w)), "net_value": float(w.sum()),
                                "pred_beta_b1": float(b1.reindex(w.index).fillna(b1.median()) @ w),
                                "pred_beta_extra": ({col: float(ex_b[col].reindex(w.index).fillna(ex_b[col].median()) @ w)
                                                     for col in ex_b.columns} if ex_b is not None else {})})
                legs = {"book": w, "long": w[w > 0], "short": w[w < 0]}
                rows_alt = {}
                hist = rets.reindex(index=hist_days, columns=w.index)
                okh = hist.notna().sum() >= MIN_HIST
                covs = alt_covs(hist.loc[:, okh], sp_hist)
                for name, x in legs.items():
                    p = path(x, r, missing="legs")
                    sig = risk_model.vol(f.snap, x) / np.sqrt(252)
                    a["z"][name].append(p / sig)
                    xh = x.reindex(okh.index[okh]).fillna(0.0).to_numpy()
                    rows_alt[name] = {"real": p.tolist(), "factor": sig, "excluded_weight": float(x[~okh.reindex(x.index).fillna(False)].abs().sum() / x.abs().sum()),
                                      **{mdl: float(np.sqrt(xh @ covs[mdl] @ xh)) for mdl in ("diagonal", "single_index", "ledoit_wolf")}}
                    d = a["dirs"].setdefault(name, [])
                    d.append({"window": key, "real": hc3_beta(p.to_numpy(), mk),
                              "pred_b1": float(b1.reindex(x.index).fillna(b1.median()) @ x),
                              "pred_b0": float(b0.reindex(x.index).fillna(b0.median()) @ x),
                              "ret": p.tolist(), "mkt": mk.tolist()})
                a["alt"].append({"window": key, "lw_delta": covs["lw_delta"], **rows_alt})
                pb = path(w, r, missing="legs")
                a["book"].append(pb)
                a["mkt"].append(pd.Series(mk, index=periods[k]))
                a["win"] += [key] * len(pb)
                a["unobserved_max"] = max(a.get("unobserved_max", 0.0), max(pb.attrs["unobserved"], default=0.0))
                if kind == "E6":
                    ref = optimize.hhrz_reference(c, dec, wt, gross)
                    beta_ref = float(b1.reindex(ref.index).fillna(b1.median()) @ ref)
                    pr = path(ref, r, missing="legs")
                    a["ref"].append(pr)
                    a["ref_h"].append(pr - beta_ref * pd.Series(np.nan_to_num(mk), index=periods[k]))
                    v_m = float(np.nanvar(sp_hist.to_numpy(), ddof=1))
                    v_w, v_r, c_wr = cov(f.snap, w, w), cov(f.snap, ref, ref), cov(f.snap, w, ref)
                    a["exante"].append({"w": v_w, "ref": v_r, "c": c_wr, "ref_h": max(v_r - beta_ref ** 2 * v_m, 1e-12),
                                        "len": len(periods[k])})
                state[v] = w
        print(key, "done", flush=True)

    rep = {"windows": {k: [str(a.date()), str(b.date())] for k, (a, b) in WINDOWS.items()}, "variants": {}}
    for v in variants:
        kind, s, wt = v
        a = acc[v]
        res = {"g1": a["g1"], "g1_pass": bool(a["g1"]) and all(x["pass"] for x in a["g1"]) and len(a["g1"]) == 8}
        if a["book"]:
            book = pd.concat(a["book"]).to_numpy()
            mk = pd.concat(a["mkt"]).to_numpy()
            win = np.array(a["win"])
            hb = book_beta_gate(book, mk, method="hc3")
            hb["by_window"] = {k: book_beta_gate(book[win == k], mk[win == k], method="hc3") for k in WINDOWS}
            n = int(np.isfinite(book).sum())
            q_lo = np.sqrt((n - 1) / stats.chi2.ppf(0.95, n - 1))
            q_hi = np.sqrt((n - 1) / stats.chi2.ppf(0.05, n - 1))
            g2 = {}
            for name, zs in a["z"].items():
                z = pd.concat(zs).to_numpy()
                sd = float(np.nanstd(z, ddof=1))
                g2[name] = {"s": sd, "ci90": [sd * q_lo, sd * q_hi],
                            "pass": bool(RISK_BAND[0] <= sd * q_lo and sd * q_hi <= RISK_BAND[1])}
            g2["pass"] = all(g2[x]["pass"] for x in a["z"])
            res |= {"hb": hb, "g2": g2, "sessions": n, "unobserved_max": a.get("unobserved_max")}
            # Variance diagnostics: realised / predicted vol by model, calm vs stressed.
            var = {}
            for name in ("book", "long", "short"):
                for grp, keys in (("calm", ("W17", "W19")), ("stressed", STRESSED)):
                    rows = [x for x in a["alt"] if x["window"] in keys]
                    var.setdefault(name, {})[grp] = {
                        mdl: float(np.nanstd(np.concatenate([np.array(x[name]["real"]) / x[name][mdl] for x in rows]),
                                             ddof=1)) for mdl in ("factor", "diagonal", "single_index", "ledoit_wolf")}
                var[name]["excluded_weight_max"] = max(x[name]["excluded_weight"] for x in a["alt"])
            res["variance_ratio"] = var
            # Paired directions: pooled realised vs mean predicted beta, and per-formation errors.
            dirs = {}
            for name, rows in a["dirs"].items():
                yy, xx = np.concatenate([x["ret"] for x in rows]), np.concatenate([x["mkt"] for x in rows])
                err1 = [x["real"]["beta"] - x["pred_b1"] for x in rows]
                err0 = [x["real"]["beta"] - x["pred_b0"] for x in rows]
                dirs[name] = {"pooled_real": hc3_beta(yy, xx), "mean_pred_b1": float(np.mean([x["pred_b1"] for x in rows])),
                              "mean_pred_b0": float(np.mean([x["pred_b0"] for x in rows])),
                              "err_b1": {"mean": float(np.mean(err1)), "mae": float(np.mean(np.abs(err1))),
                                         "sq_hedge_loss": float(np.mean(np.square(err1)))},
                              "err_b0": {"mean": float(np.mean(err0)), "mae": float(np.mean(np.abs(err0))),
                                         "sq_hedge_loss": float(np.mean(np.square(err0)))},
                              "formations": len(rows)}
            res["directions"] = dirs
            if kind == "E6":
                g4 = {}
                n_d = np.isfinite(book) & np.isfinite(pd.concat(a["ref"]).to_numpy())
                for kk in ("ref", "ref_h"):
                    y = pd.concat(a[kk]).to_numpy()
                    ok = n_d & np.isfinite(y)
                    t, pval = pitman_morgan(book[ok], y[ok])
                    L = np.array([x["len"] for x in a["exante"]], dtype=float)
                    vx = float(np.average([x["w"] for x in a["exante"]], weights=L))
                    vy = float(np.average([x[kk] for x in a["exante"]], weights=L))
                    cxy = float(np.average([x["c"] for x in a["exante"]], weights=L))
                    r_exp = (vx - vy) / np.sqrt(max((vx + vy) ** 2 - 4 * cxy ** 2, 1e-24))
                    t_exp = r_exp * np.sqrt(ok.sum() - 2) / np.sqrt(max(1 - r_exp ** 2, 1e-12))
                    powered = bool(t_exp < stats.t.ppf(ALPHA, ok.sum() - 2))
                    g4[kk] = {"vol_e6": float(np.std(book[ok], ddof=1) * np.sqrt(252)),
                              "vol_other": float(np.std(y[ok], ddof=1) * np.sqrt(252)), "t": float(t), "p": pval,
                              "t_exante": float(t_exp), "powered": powered, "pass": bool(powered and pval < ALPHA)}
                g4["pass"] = g4["ref"]["pass"] and g4["ref_h"]["pass"]
                res["g4"] = g4
            res["pass_before_g5"] = bool(res["g1_pass"] and g2["pass"] and hb["pass"]
                                         and (res["g4"]["pass"] if kind == "E6" else True))
        rep["variants"][f"{kind}|{s}|{wt}"] = res
    # Adverse direction (variant-free).
    yy = np.concatenate([x["ret"] for x in adverse])
    xx = np.concatenate([x["mkt"] for x in adverse])
    rep["adverse"] = {"pooled_real": hc3_beta(yy, xx),
                      "mean_pred_b1": float(np.mean([x["pred_b1"] for x in adverse])),
                      "mean_pred_b0": float(np.mean([x["pred_b0"] for x in adverse])),
                      "by_formation": [{k: x[k] for k in ("window", "eom", "real", "pred_b1", "pred_b0")} for x in adverse]}
    rep["survivors_before_g5"] = [k for k, v in rep["variants"].items() if v.get("pass_before_g5")]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hbeta_gates.json").write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


if __name__ == "__main__":
    print(json.dumps(run()["survivors_before_g5"]))
