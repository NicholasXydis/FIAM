# D19 gates for E6 on window W: the first two D18 formations, each book held
# (drifting daily) from the session after its signal day to the next signal
# day, the second to 2017-02-28. Gates and margins are fixed in DECISIONS D19.
#
#   G0 signal      frozen walk-forward calibration slope, lo90 > 0 (no new look)
#   G1 structure   first rung optimal, floor, beta slack, hard rules, two-sided sectors
#   G2 risk        sd(daily return / predicted daily vol), 90% chi2 CI in [2/3, 3/2]
#   G3 beta        (a) slope of realised on predicted beta across candidates, 95% CI in
#                  [0.5, 1.5]; (b) book realised beta, 90% CI in [-0.2, 0.2]
#                  (5-day block bootstrap over days, 1,000 draws, seed 42)
#   G4 step 2      var(E6) < var(HHRZ reference), raw and S&P-hedged at its predicted
#                  beta; one-sided Pitman-Morgan p < 0.05
# Each statistical gate reports its ex-ante half-width or expected t from the risk
# model and trailing S&P variance; an underpowered gate fails. G5 (Nautilus smoke) is
# separate: e6_gates.g5(out_dir).
#
# Missing daily returns count as 0 (the share of weight affected is reported).
# Usage: FIAM_V4B_CONFIG=variant_betamatch.json python -m fiam.v4b.research.e6_gates
#        on Modal: modal run fiam/v4b/gpu/modal_book.py::gates

import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from fiam.v4b.engine import checker, inputs, ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.elasso import forecaster
from fiam.v4b.elasso.walkforward import ROOT
from fiam.v4b.research.twostep_screen import score_mu
from fiam.v4b.risk import model as risk_model

V4B = Path(__file__).resolve().parents[1]
OUT = V4B / "out" / "e6_gates"
EOMS = (pd.Timestamp("2016-12-31"), pd.Timestamp("2017-01-31"))
W_END = pd.Timestamp("2017-02-28")
SCORES = ("raw", "raw_s6", "betamatch", "betamatch_s6")
WEIGHTINGS = ("vw", "ew")
RISK_BAND, BOOK_BETA, SLOPE_BAND = (2 / 3, 3 / 2), 0.2, (0.5, 1.5)
BLOCK, DRAWS, SEED, ALPHA = 5, 1000, 42, 0.05
HB_BAND = 0.10
HARD_RULES = ("names", "gross", "net", "name_cap", "short_floor")


def g0() -> dict:
    out = {}
    for s in SCORES:
        c = json.loads((ROOT / "month" / s / "frozen.json").read_text())["Elasso_MaInf"]["calibration_y21"]
        out[s] = {"slope": c["slope"], "t": c["slope"] / c["se"], "lo90": c["lo90"], "pass": c["lo90"] > 0}
    return out


# Daily returns of a book that drifts with its names. missing="zero" counts an
# unobserved return as 0 (D19); "legs" (D21 Amendment 2) scales each leg's observed
# P&L by leg weight / observed leg weight. The unobserved weight share per day
# is in .attrs["unobserved"].
def path(w: pd.Series, rets: pd.DataFrame, missing: str = "zero") -> pd.Series:
    r = rets.reindex(columns=w.index).to_numpy(dtype=float)
    cur, out, gone = w.to_numpy(dtype=float).copy(), [], []
    for row in r:
        seen = np.isfinite(row)
        x = np.where(seen, row, 0.0)
        if missing == "legs":
            pnl = 0.0
            for side in (cur > 0, cur < 0):
                tot, obs = np.abs(cur[side]).sum(), np.abs(cur[side & seen]).sum()
                pnl += float(cur[side & seen] @ x[side & seen]) * (tot / obs) if obs > 0 else 0.0
            out.append(pnl)
        else:
            out.append(float(cur @ x))
        gone.append(float(np.abs(cur[~seen]).sum() / max(np.abs(cur).sum(), 1e-12)))
        cur = cur * (1 + x)
    s = pd.Series(out, index=rets.index)
    s.attrs["unobserved"] = gone
    return s


# One day's book return with missing returns handled per leg (D21 Amendment 2).
def leg_return(w: np.ndarray, r: np.ndarray) -> np.ndarray:
    seen = np.isfinite(r)
    x = np.where(seen, r, 0.0)
    out = np.zeros(r.shape[0])
    for side in (w > 0, w < 0):
        tot = np.abs(w[side]).sum()
        obs = seen[:, side] @ np.abs(w[side])
        out += np.where(obs > 0, (x[:, side] @ w[side]) * tot / np.where(obs > 0, obs, 1.0), 0.0)
    return out


def blocks(n: int, rng) -> np.ndarray:
    starts = rng.integers(0, n, size=int(np.ceil(n / BLOCK)))
    return (starts[:, None] + np.arange(BLOCK)).ravel()[:n] % n


def ols_beta(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    xc = x - x.mean()
    return (xc @ (y - y.mean(axis=0))) / (xc @ xc)


# Gate HB (D21): realised book beta on the market over pooled sessions; its
# 90% interval must lie inside [-band, band]. Pooled OLS weights each day by its
# market move, so stressed windows count most. Interval methods (D21 Amendment 1):
#   "block"  5-day circular blocks over the pooled sessions (failed phase 0a)
#   "strat"  5-day circular blocks within each window (window labels needed)
#   "hc3"    OLS slope, HC3 standard error, t(n-2) interval
#   "wild"   Rademacher signs on 5-day blocks of OLS residuals
def book_beta_gate(book, mkt, band: float = HB_BAND, draws: int = DRAWS, seed: int = SEED,
                   method: str = "block", window=None) -> dict:
    book, mkt = np.asarray(book, dtype=float), np.asarray(mkt, dtype=float)
    win = np.zeros(len(book), dtype=int) if window is None else np.asarray(window)
    ok = np.isfinite(book) & np.isfinite(mkt)
    book, mkt, win = book[ok], mkt[ok], win[ok]
    n = len(book)
    beta = float(ols_beta(book, mkt))
    rng = np.random.default_rng(seed)

    def slopes(x, y):
        xc = x - x.mean(axis=1, keepdims=True)
        return (xc * (y - y.mean(axis=1, keepdims=True))).sum(axis=1) / (xc ** 2).sum(axis=1)

    if method == "hc3":
        xc = mkt - mkt.mean()
        e = book - book.mean() - beta * xc
        h = 1 / n + xc ** 2 / (xc @ xc)
        se = float(np.sqrt((xc ** 2 * e ** 2 / (1 - h) ** 2).sum()) / (xc @ xc))
        q = stats.t.ppf(0.95, n - 2)
        lo, hi = beta - q * se, beta + q * se
    else:
        if method == "block":
            idx = np.stack([blocks(n, rng) for _ in range(draws)])
            bb = slopes(mkt[idx], book[idx])
        elif method == "strat":
            pos = [np.flatnonzero(win == k) for k in np.unique(win)]
            idx = np.stack([np.concatenate([p[blocks(len(p), rng)] for p in pos]) for _ in range(draws)])
            bb = slopes(mkt[idx], book[idx])
        elif method == "wild":
            xc = mkt - mkt.mean()
            fit = book.mean() + beta * xc
            e = book - fit
            nb = int(np.ceil(n / BLOCK))
            sign = rng.choice([-1.0, 1.0], size=(draws, nb)).repeat(BLOCK, axis=1)[:, :n]
            bb = slopes(np.broadcast_to(mkt, (draws, n)), fit + sign * e)
        else:
            raise ValueError(method)
        lo, hi = np.quantile(bb, [0.05, 0.95])
    return {"beta": beta, "ci90": [float(lo), float(hi)], "sessions": int(n), "method": method,
            "pass": bool(-band <= lo and hi <= band)}


def pitman_morgan(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    r = float(np.corrcoef(x + y, x - y)[0, 1])
    n = len(x)
    t = r * np.sqrt(n - 2) / np.sqrt(1 - r * r)
    return t, float(stats.t.cdf(t, n - 2))  # one-sided: var(x) < var(y)


# Daily covariance of two books under the formation's risk model.
def cov(snap: dict, a: pd.Series, b: pd.Series) -> float:
    B, F1, d = snap["B"], snap["F1"], snap["d"]
    ba = (B.reindex(a.index).fillna(0.0).T @ a).to_numpy()
    bb = (B.reindex(b.index).fillna(0.0).T @ b).to_numpy()
    common = a.index.intersection(b.index)
    return float(ba @ F1.reindex(index=B.columns, columns=B.columns).to_numpy() @ bb
                 + (d.reindex(common).fillna(0.0) * a.loc[common] * b.loc[common]).sum())


def run(variants: list) -> dict:
    m = load()
    world = ladder.World(m)
    sessions = world.sessions
    rets = world.market["returns"]
    days = [world.signal_day(e) for e in EOMS] + [W_END]
    periods = [sessions[(sessions > days[k]) & (sessions <= days[k + 1])] for k in range(len(EOMS))]
    w_days = periods[0].append(periods[1])
    sp = inputs.market_returns(sessions[(sessions >= days[0] - pd.Timedelta(days=100)) & (sessions <= W_END)])
    sp_w = sp.reindex(w_days).to_numpy()
    pre = sp[sp.index <= days[0]].dropna().iloc[-63:]
    var_m = float(pre.var())  # ex-ante market variance: 63 sessions before W
    n = len(w_days)
    kappa = forecaster.kappa_for(m, "Elasso_MaInf")
    bases = {e: world.formation(e, "Elasso_MaInf", pd.Series(dtype=float)) for e in EOMS}
    mus = {s: score_mu(m, s) for s in {s for s, _ in variants}}
    steps = {wt: ladder.steps(n_e3=250)["E6" if wt == "vw" else "E6_ew"] for wt in WEIGHTINGS}
    rep = {"window": [str(w_days[0].date()), str(w_days[-1].date())], "sessions": n,
           "var_m_daily_exante": var_m, "g0": g0(), "variants": {}}

    # G3a is a property of the beta model at the first formation: one test for all variants.
    f0 = bases[EOMS[0]]
    cand = optimize._candidates(f0, m, steps["vw"]).index
    R = rets.reindex(index=w_days, columns=cand)
    R = R.loc[:, R.notna().all()]
    b_pred = f0.snap["beta"].reindex(R.columns).to_numpy()
    ok = np.isfinite(b_pred) & np.isfinite(sp_w).all()
    R, b_pred = R.loc[:, ok], b_pred[ok]
    Y = R.to_numpy()

    def slope_of(idx):
        b_real = ols_beta(Y[idx], sp_w[idx])
        return float(ols_beta(b_real, b_pred))

    rng = np.random.default_rng(SEED)
    boot = np.array([slope_of(blocks(n, rng)) for _ in range(DRAWS)])
    bc = b_pred - b_pred.mean()
    d0 = f0.snap["d"].reindex(R.columns).fillna(f0.snap["d"].median()).to_numpy()
    se0 = float(np.sqrt((bc ** 2 * d0 / (n * var_m)).sum()) / (bc @ bc))  # idiosyncratic only: a lower bound
    lo, hi = np.quantile(boot, [0.025, 0.975])
    rep["g3a"] = {"names": int(len(b_pred)), "slope": slope_of(np.arange(n)), "ci95": [float(lo), float(hi)],
                  "exante_halfwidth_lower_bound": 1.96 * se0,
                  "pass": bool(SLOPE_BAND[0] <= lo and hi <= SLOPE_BAND[1])}

    for s, wt in variants:
        step = steps[wt]
        mu_s = {e: g.set_index("permno")["mu"] for e, g in mus[s].groupby("eom")}
        w_pre = pd.Series(dtype=float)
        g1, series, exante = [], {"book": [], "long": [], "short": [], "ref": [], "ref_h": []}, []
        z = {"book": [], "long": [], "short": []}
        for k, e in enumerate(EOMS):
            base = bases[e]
            if k:
                w_pre = optimize.drift(w_pre, rets.loc[(rets.index > days[k - 1]) & (rets.index <= days[k])])
            hscale = forecaster.horizon_scale(0, base.horizon, kappa)
            f = dataclasses.replace(base, mu=mu_s.get(e, pd.Series(dtype=float)) * hscale, w_pre=w_pre)
            w, log = optimize.build_book(f, m, step)
            if w is None:
                g1.append({"eom": str(e.date()), "pass": False, "status": log.get("status"),
                           "attempts": log.get("attempts")})
                break
            c, dec = optimize.hhrz_deciles(optimize._candidates(f, m, step), f.nyse_me, wt)
            ref = optimize.hhrz_reference(c, dec, wt, float(log["ladder_gross"]))
            beta_ref = float(f.snap["beta"].reindex(ref.index).fillna(1.0) @ ref)
            side = f.snap["month"]["sector"].reindex(w.index)
            first = (log["attempts"] or [{}])[0]
            chk = {
                "first_rung_optimal": bool(first.get("ok") and first.get("status") == "optimal"
                                           and log["rho"] == 0.9 and log["ladder_gross"] == m.policy.target_gross),
                "floor": log["mu_w"] >= 0.9 * log["mu_ref"] - 1e-9,
                "beta_slack": (log.get("slacks") or {}).get("beta", 0.0) <= 1e-6,
                "names": m.hard.names_min <= len(w) <= m.hard.names_max,
                "name_cap": float(w.abs().max()) <= m.hard.name_cap + 1e-9,
                "gross": float(w.abs().sum()) <= m.hard.gross_max + 1e-9,
                "net": abs(float(w.sum())) <= m.hard.net_band + 1e-9,
                "short_floor": checker.short_floor_formation(w, f.snap["month"], m.hard.short_floor_musd),
                "short_gross_research": float(-w[w < 0].sum()) * m.hard.nav0 / 1e6 >= m.hard.short_floor_musd - 1e-6,
                "sectors_two_sided": set(side[w > 0]) == set(side[w < 0]),
                "union_fits": bool(log.get("union_fits", True)),
            }
            g1.append({"eom": str(e.date()), "pass": all(chk.values()), **chk,
                       "status": first.get("status"), "rho": log["rho"], "gross": log["ladder_gross"],
                       "names_n": int(len(w)), "pred_vol": log["pred_vol"], "pred_beta": log["pred_beta"],
                       "ref_names": int(len(ref)), "ref_pred_beta": beta_ref,
                       "missing_ret_weight": float(w.abs()[rets.reindex(index=periods[k], columns=w.index)
                                                           .isna().any().to_numpy()].sum() / w.abs().sum())})
            r = rets.loc[periods[k]]
            legs = {"book": w, "long": w[w > 0], "short": w[w < 0]}
            for name, x in legs.items():
                p = path(x, r)
                series[name].append(p)
                z[name].append(p / (risk_model.vol(f.snap, x) / np.sqrt(252)))
            pr = path(ref, r)
            series["ref"].append(pr)
            series["ref_h"].append(pr - beta_ref * sp.reindex(periods[k]).fillna(0.0))
            v_w, v_r = cov(f.snap, w, w), cov(f.snap, ref, ref)
            c_wr = cov(f.snap, w, ref)
            v_rh = max(v_r - beta_ref ** 2 * var_m, 1e-12)
            exante.append({"w": v_w, "ref": v_r, "c": c_wr, "ref_h": v_rh, "c_h": c_wr,
                           "len": len(periods[k])})
            w_pre = w
        res = {"g1": g1}
        if all(x["pass"] for x in g1) and len(g1) == len(EOMS):
            g2 = {}
            q_lo = np.sqrt((n - 1) / stats.chi2.ppf(0.95, n - 1))
            q_hi = np.sqrt((n - 1) / stats.chi2.ppf(0.05, n - 1))
            for name in z:
                sd = float(pd.concat(z[name]).std(ddof=1))
                g2[name] = {"s": sd, "ci90": [sd * q_lo, sd * q_hi],
                            "pass": bool(RISK_BAND[0] <= sd * q_lo and sd * q_hi <= RISK_BAND[1])}
            g2["exante_ci90_at_s1"] = [float(q_lo), float(q_hi)]
            g2["powered"] = bool(RISK_BAND[0] <= q_lo and q_hi <= RISK_BAND[1])
            g2["pass"] = g2["powered"] and all(g2[k]["pass"] for k in z)
            book = pd.concat(series["book"]).reindex(w_days).to_numpy()
            rng = np.random.default_rng(SEED)
            bb = np.array([ols_beta(book[i], sp_w[i]) for i in (blocks(n, rng) for _ in range(DRAWS))])
            lo, hi = np.quantile(bb, [0.05, 0.95])
            v_book = np.mean([x["w"] for x in exante])
            hw = float(stats.norm.ppf(0.95) * np.sqrt(v_book / (n * var_m)))
            g3b = {"beta": float(ols_beta(book, sp_w)), "ci90": [float(lo), float(hi)],
                   "exante_halfwidth": hw, "powered": hw < BOOK_BETA}
            g3b["pass"] = bool(g3b["powered"] and -BOOK_BETA <= lo and hi <= BOOK_BETA)
            g4 = {}
            for key, vk, ck in (("ref", "ref", "c"), ("ref_h", "ref_h", "c_h")):
                y = pd.concat(series[key]).reindex(w_days).to_numpy()
                t, p = pitman_morgan(book, y)
                vx, vy = np.mean([x["w"] for x in exante]), np.mean([x[vk] for x in exante])
                cxy = np.mean([x[ck] for x in exante])
                r_exp = (vx - vy) / np.sqrt(max((vx + vy) ** 2 - 4 * cxy ** 2, 1e-24))
                t_exp = r_exp * np.sqrt(n - 2) / np.sqrt(max(1 - r_exp ** 2, 1e-12))
                powered = t_exp < stats.t.ppf(ALPHA, n - 2)
                g4[key] = {"vol_e6": float(book.std(ddof=1) * np.sqrt(252)),
                           "vol_other": float(y.std(ddof=1) * np.sqrt(252)),
                           "t": float(t), "p": p, "t_exante": float(t_exp), "powered": bool(powered),
                           "pass": bool(powered and p < ALPHA)}
            g4["pass"] = all(g4[k]["pass"] for k in ("ref", "ref_h"))
            res |= {"g2": g2, "g3b": g3b, "g4": g4}
        res["pass_g0_g4"] = bool(rep["g0"][s]["pass"] and all(x["pass"] for x in g1) and len(g1) == len(EOMS)
                                 and rep["g3a"]["pass"] and res.get("g2", {}).get("pass")
                                 and res.get("g3b", {}).get("pass") and res.get("g4", {}).get("pass"))
        rep["variants"][f"{s}|{wt}"] = res
        print(s, wt, "G1", [x["pass"] for x in g1], "pass_g0_g4", res["pass_g0_g4"], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gates.json").write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


# G5: executed holdings of a Nautilus smoke over W, zero hard-rule breaches.
def g5(out_dir: Path, step: str) -> dict:
    b = pd.read_parquet(Path(out_dir) / step / "breaches.parquet")
    b = b[pd.to_datetime(b["date"]) <= W_END]
    hard = b[b["rule"].isin(HARD_RULES)]
    return {"hard_breaches": int(len(hard)), "by_rule": b.groupby("rule").size().to_dict(),
            "pass": len(hard) == 0}


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("--variants", default="", help="score:weighting,... (default: G0 passers x vw, ew)")
    args = a.parse_args()
    vs = [tuple(x.split(":")) for x in args.variants.split(",")] if args.variants else \
        [(s, wt) for s, g in g0().items() if g["pass"] for wt in WEIGHTINGS]
    print(json.dumps(run(vs), indent=1, default=float))
