# Portfolio-level accuracy of the risk model variants (risk/enhanced.py).
# Rule fixed before any run (2026-10-26):
#   window   formations eom 2016-12..2020-11 (pre-2021 only)
#   books    resrank volneut decile book (long D9 / short D0, 0.5 a side),
#            its long leg alone and short leg alone, the frozen fallback,
#            and the executed E3 books (mean, tail) at each rebalance
#   vol      z = realised 21-session fixed-weight excess / predicted vol;
#            bias = sd(z) (target 1, band +-sqrt(2/n)); also mean z and by year
#   beta     realised book beta = OLS slope of the book's daily excess on the
#            market over the same 21 sessions; error = realised - predicted
#   variants base, vra, pca, vra+pca (parameters fixed in enhanced.py);
#            vra+pca+betacal added after the beta errors were seen (beta_cal.py)
#   adopt    a component is adopted if it lowers pooled |bias - 1| on at least
#            4 of the 6 books and raises it by more than 0.05 on none; beta
#            errors are reported, not gated for vra/pca (beta unchanged there);
#            betacal is adopted if it lowers |mean beta error| on at least 4
#            of the 6 books and raises beta RMSE on none by more than 0.01
# Usage: python -m fiam.v4b.risk.accuracy [--months N]

import argparse
import json
import time

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data
from fiam.v4b.research.short_side import book_attribution, tournament
from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk import enhanced, model, validate

OUT = validate.OUT / "accuracy.json"
VARIANTS = {"base": (False, 0, False), "vra": (True, 0, False), "pca": (False, enhanced.PCA_K, False),
            "vra+pca": (True, enhanced.PCA_K, False), "vra+pca+betacal": (True, enhanced.PCA_K, True)}


def strategy_books() -> dict:
    f = tournament.scores()
    g = tournament.judged(f, "valid")
    g = g.merge(data.panel(cut=pd.Timestamp("2020-12-31"))[["permno", "eom", "ivol_capm_252d"]],
                on=["permno", "eom"], how="left")
    iv = g["ivol_capm_252d"].fillna(g.groupby("eom")["ivol_capm_252d"].transform("median"))
    g["ivt"] = iv.groupby(g["eom"]).transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
    dec = g.groupby(["eom", "ivt"])["resrank"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    books = {"volneut": {}, "volneut_long": {}, "volneut_short": {}}
    for eom, d in g.assign(dec=dec).groupby("eom"):
        lo, hi = d[d["dec"] == 0]["permno"], d[d["dec"] == 9]["permno"]
        wl = pd.Series(0.5 / len(hi), index=hi.to_numpy())
        ws = pd.Series(-0.5 / len(lo), index=lo.to_numpy())
        books["volneut"][eom] = pd.concat([wl, ws]).groupby(level=0).sum()
        books["volneut_long"][eom], books["volneut_short"][eom] = wl, ws
    return books


def executed_books() -> dict:
    out = {}
    for name, (path, _) in book_attribution.BOOKS.items():
        b = book_attribution.book(path)
        out[name] = {e: g.set_index("permno")["w"] for e, g in b.groupby("eom")
                     if validate.WINDOW[0] <= e <= validate.WINDOW[1]}
    return out


def realised_beta(excess: pd.DataFrame, mkt: pd.Series, eom, w: pd.Series) -> float:
    pos = excess.index.searchsorted(pd.Timestamp(eom), side="right")
    block = excess.iloc[pos: pos + validate.HORIZON]
    if len(block) < validate.HORIZON:
        return float("nan")
    cols = w.index.intersection(block.columns)
    r = block[cols].fillna(0.0).to_numpy() @ w.loc[cols].to_numpy()
    m = mkt.reindex(block.index).to_numpy()
    mc = m - m.mean()
    return float(((r - r.mean()) * mc).sum() / (mc**2).sum())


def evaluate(rm, books: dict, excess, mkt, months) -> dict:
    out, snaps = {}, {}
    for name, book in books.items():
        z, berr, years = {}, {}, {}
        for eom, w in sorted(book.items())[:months]:
            if eom not in snaps:
                snaps[eom] = rm.snapshot(eom, validate.HORIZON)
            snap = snaps[eom]
            if snap["F"] is None:
                continue
            pred = float(np.sqrt(model.variance(snap, w)[0]))
            got = validate.realised(excess, eom, w)
            if np.isfinite(got) and pred > 0:
                z[pd.Timestamp(eom)] = got / pred
            bp = float(snap["beta"].reindex(w.index).fillna(0.0).to_numpy() @ w.to_numpy())
            berr[pd.Timestamp(eom)] = realised_beta(excess, mkt, eom, w) - bp
        z, berr = pd.Series(z).sort_index(), pd.Series(berr).sort_index().dropna()
        out[name] = {"n": int(len(z)), "bias": float(z.std()), "band": float(np.sqrt(2 / max(len(z), 1))),
                     "mean_z": float(z.mean()), "abs_bias_err": float(abs(z.std() - 1)),
                     "bias_by_year": {str(y): float(v.std()) for y, v in z.groupby(z.index.year) if len(v) > 2},
                     "beta_err_mean": float(berr.mean()), "beta_err_rmse": float(np.sqrt((berr**2).mean()))}
    return out


def main(months: int | None = None) -> dict:
    t0 = time.time()
    rm = enhanced.EnhancedRiskModel(vra=True, pca=enhanced.PCA_K)
    excess, mk = beta_mod.excess_wide()
    mkt = mk["mkt_rf"]
    books = strategy_books() | {"fallback": validate.fallback_books()} | executed_books()
    rep = {"build_s": round(time.time() - t0, 1), "device": str(enhanced.DEV)}
    for v, (vra, pca, bcal) in VARIANTS.items():
        rm.vra, rm.pca, rm.beta_cal = vra, pca, bcal
        rep[v] = evaluate(rm, books, excess, mkt, months)
    base = rep["base"]
    rep["adopt"] = {}
    for v in ("vra", "pca", "vra+pca"):
        d = {b: rep[v][b]["abs_bias_err"] - base[b]["abs_bias_err"] for b in base}
        rep["adopt"][v] = {"better_on": int(sum(x < 0 for x in d.values())),
                           "worst_increase": float(max(d.values())),
                           "adopted": sum(x < 0 for x in d.values()) >= 4 and max(d.values()) <= 0.05}
    d = {b: abs(rep["vra+pca+betacal"][b]["beta_err_mean"]) - abs(rep["vra+pca"][b]["beta_err_mean"]) for b in base}
    r = {b: rep["vra+pca+betacal"][b]["beta_err_rmse"] - rep["vra+pca"][b]["beta_err_rmse"] for b in base}
    rep["adopt"]["betacal"] = {"better_on": int(sum(x < 0 for x in d.values())), "worst_rmse_increase": float(max(r.values())),
                               "adopted": sum(x < 0 for x in d.values()) >= 4 and max(r.values()) <= 0.01}
    if months is None:
        OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int)
    a = ap.parse_args()
    r = main(a.months)
    print("build", r["build_s"], "s on", r["device"])
    for v in VARIANTS:
        print(f"== {v}")
        for b, x in r[v].items():
            print(f"  {b:14s} n {x['n']:2d} bias {x['bias']:.2f} (±{x['band']:.2f}) mean z {x['mean_z']:+.2f} "
                  f"by year {', '.join(f'{k} {u:.2f}' for k, u in x['bias_by_year'].items())} | "
                  f"beta err {x['beta_err_mean']:+.3f} rmse {x['beta_err_rmse']:.3f}")
    print("adopt:", r["adopt"])
