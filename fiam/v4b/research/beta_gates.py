# D20 step A: which market-beta forecast predicts the beta a name realises
# over a short window? Windows W17..W20 = first formation Dec 31, held to the
# end of February. Realised beta: daily OLS on the S&P 500 over the window
# (the D19 G3a measure). Per candidate and window: the 95% 5-day-block
# bootstrap interval of the realised-on-predicted slope across the first
# formation's candidates must lie inside [0.5, 1.5]. Pass = all four windows;
# pick = the passer with the smallest mean |slope - 1|.
#
# Usage: FIAM_V4B_CONFIG=variant_betamatch.json python -m fiam.v4b.research.beta_gates
#        on Modal: modal run fiam/v4b/gpu/modal_book.py::beta_gates

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from fiam.v4b.engine import inputs, ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.research.e6_gates import BLOCK, DRAWS, SEED, SLOPE_BAND, blocks, ols_beta
from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk import beta_candidates as bc

V4B = Path(__file__).resolve().parents[1]
OUT = V4B / "out" / "beta_gates"
WINDOWS = {f"W{y % 100}": (pd.Timestamp(f"{y - 1}-12-31"), pd.Timestamp(f"{y}-02-01") + pd.offsets.MonthEnd(1))
           for y in (2017, 2018, 2019, 2020)}


def window_test(Y: np.ndarray, sp: np.ndarray, pred: pd.DataFrame) -> dict:
    n = len(sp)
    rng = np.random.default_rng(SEED)
    idx = [np.arange(n)] + [blocks(n, rng) for _ in range(DRAWS)]
    real = np.array([ols_beta(Y[i], sp[i]) for i in idx])  # (1 + DRAWS) x names
    out = {}
    for c in pred:
        p = pred[c].to_numpy()
        ok = np.isfinite(p)
        slopes = np.array([ols_beta(r[ok], p[ok]) for r in real])
        lo, hi = np.quantile(slopes[1:], [0.025, 0.975])
        out[c] = {"slope": float(slopes[0]), "ci95": [float(lo), float(hi)], "names": int(ok.sum()),
                  "spearman": float(stats.spearmanr(p[ok], real[0][ok]).statistic),
                  "mean_pred": float(p[ok].mean()), "mean_real": float(real[0][ok].mean()),
                  "pass": bool(SLOPE_BAND[0] <= lo and hi <= SLOPE_BAND[1])}
    return out


def run() -> dict:
    m = load()
    world = ladder.World(m)
    excess, mk = beta_mod.excess_wide(cut=world.rm.cut)
    rets, sessions = world.market["returns"], world.sessions
    step = ladder.steps(n_e3=250)["E6"]
    rep = {"band": SLOPE_BAND, "block": BLOCK, "draws": DRAWS, "windows": {}}
    for key, (eom, end) in WINDOWS.items():
        f = world.formation(eom, "Elasso_MaInf", pd.Series(dtype=float))
        days = sessions[(sessions > world.signal_day(eom)) & (sessions <= end)]
        sp = inputs.market_returns(sessions[(sessions >= days[0] - pd.Timedelta(days=10)) & (sessions <= end)])
        sp = sp.reindex(days).to_numpy()
        names = optimize._candidates(f, m, step).index
        R = rets.reindex(index=days, columns=names)
        R = R.loc[:, R.notna().all()]
        pred = bc.at(world.rm, f.snap, excess, mk["mkt_rf"], eom, R.columns)
        res = window_test(R.to_numpy(), sp, pred)
        res["_meta"] = {"eom": str(eom.date()), "first": str(days[0].date()), "last": str(days[-1].date()),
                        "sessions": int(len(days)), "beta_map": f.snap.get("beta_map"),
                        "corr": pred.corr().round(3).to_dict()}
        rep["windows"][key] = res
        print(key, {c: (round(res[c]["slope"], 2), res[c]["pass"]) for c in bc.NAMES}, flush=True)
    summ = {}
    for c in bc.NAMES:
        s = [rep["windows"][k][c]["slope"] for k in WINDOWS]
        summ[c] = {"slopes": s, "mean_abs_err": float(np.mean(np.abs(np.array(s) - 1))),
                   "pass": all(rep["windows"][k][c]["pass"] for k in WINDOWS)}
    rep["summary"] = summ
    passers = [c for c in bc.NAMES if summ[c]["pass"]]
    rep["pick"] = min(passers, key=lambda c: summ[c]["mean_abs_err"]) if passers else None
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "beta_gates.json").write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


if __name__ == "__main__":
    r = run()
    for c, s in r["summary"].items():
        print(c, s)
    print("pick", r["pick"])
