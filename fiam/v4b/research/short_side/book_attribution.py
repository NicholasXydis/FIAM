# Where the executed book loses the short edge the forecast has (lesson 75).
# Validation books only (formations 2016-12..2020-11), each with the forecast
# it was built from:
#   E3_mean - out/nautilus/E3, R mean E-LASSO MaInf (pre-2021 = frozen, L52)
#   E3_tail - out/nautilus_d12/E3, R tail score MaInf(up) - MaInf(down)
#   E5_volneut - out/nautilus_e5/E5, volneut forecast, E5 objective (D14)
# Each leg, same steps for longs and shorts, one-month hold on the formation
# eom's ret_exc_lead1m, beta + GICS-sector residual (tournament.judged):
#   decile   - forecast D0 / D9 of the shortable pool, equal weight
#   names_ew - the book's names on that side, equal weight
#   names_bw - the book's names, book weights (leg gross scaled to 1)
#   raw_bw   - the same, raw excess return (carries the beta hedge)
# plus where the leg's gross sits in the forecast (share of gross by decile;
# share on the wrong side of the median), the leg's mean pre-hedge beta and
# ivol, and the share of the leg's gross in names whose residual jumped
# (|res| >= 20%). Profit is + for that leg.
# Usage: python -m fiam.v4b.research.short_side.book_attribution

import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.forecast import data
from fiam.v4b.gpu.rolling import BASE as GPU
from fiam.v4b.research.short_side import tournament

ROOT = rj.BASE.parents[2]
BOOKS = {"E3_mean": ("nautilus/E3", "mean"), "E3_tail": ("nautilus_d12/E3", "tail"),
         "E5_volneut": ("nautilus_e5/E5", "volneut")}
OUT = GPU / "book_attribution.json"


def forecasts() -> pd.DataFrame:
    load = lambda k: rj._load(k)[["eom", "permno", "MaInf"]].rename(columns={"MaInf": k})
    f = load("ret").merge(load("up"), on=["eom", "permno"]).merge(load("down"), on=["eom", "permno"])
    f = f.assign(mean=f["ret"], tail=f["up"] - f["down"])[["eom", "permno", "mean", "tail"]]
    v = rj._load("volneut", run=GPU / "volneut" / "run")[["eom", "permno", "MaInf"]].rename(columns={"MaInf": "volneut"})
    return f.merge(v, on=["eom", "permno"], how="left")


# Post-trade weights on each rebalance session, dated by its formation eom.
def book(path: str) -> pd.DataFrame:
    h = pd.read_parquet(ROOT / "out" / path / "daily_holdings.parquet", columns=["date", "permno", "w", "rebalance"])
    h = h[h["rebalance"] & (h["w"] != 0)].copy()
    d = pd.to_datetime(h["date"])
    # The signal day is the last session on or before eom; trades go out the next session.
    h["eom"] = (d - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    h.loc[d.dt.is_month_end, "eom"] = d[d.dt.is_month_end].astype("datetime64[ns]")
    first = h.groupby("eom")["date"].transform("min")
    return h[h["date"] == first][["eom", "permno", "w"]]


def t(s: pd.Series) -> list:
    s = s.dropna()
    return [float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s))), int(len(s))]


def attribute(score: str, b: pd.DataFrame, g: pd.DataFrame) -> dict:
    g = g.copy()
    g["dec"] = g.groupby("eom")[score].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    g["above"] = g.groupby("eom")[score].transform(lambda s: s > s.median()).astype(bool)
    x = b.merge(g, on=["eom", "permno"], how="left")
    rep = {"book_gross_matched": float(x.loc[x["res"].notna(), "w"].abs().sum() / x["w"].abs().sum())}
    for side, sgn, dec in (("short", -1, 0), ("long", 1, 9)):
        side_all = x[np.sign(x["w"]) == sgn]
        leg = side_all.dropna(subset=["res"])
        wt = leg["w"].abs() / leg.groupby("eom")["w"].transform(lambda s: s.abs().sum())
        by = lambda v: (v * wt).groupby(leg["eom"]).sum()
        r = {
            "matched_gross": float(leg["w"].abs().sum() / side_all["w"].abs().sum()),
            "decile": t(sgn * g[g["dec"] == dec].groupby("eom")["res"].mean()),
            "names_ew": t(sgn * leg.groupby("eom")["res"].mean()),
            "names_bw": t(sgn * by(leg["res"])),
            "raw_bw": t(sgn * by(leg["y"])),
            "names_per_month": float(leg.groupby("eom").size().mean()),
            "gross_by_decile": {int(k): float(v) for k, v in (wt.groupby(leg["dec"]).sum() / wt.sum()).items()},
            "gross_wrong_side": float((wt * (leg["above"] if sgn < 0 else ~leg["above"])).sum() / wt.sum()),
            "gross_ge_10bn": float((wt * (leg["me"] >= 10_000)).sum() / wt.sum()),
            "beta": float((wt * leg["beta_60m"]).sum() / wt.sum()),
            "ivol": float((wt * leg["ivol"]).sum() / wt.sum()),
            "gross_in_jumps": float((wt * (leg["res"].abs() >= 0.2)).sum() / wt.sum()),
            "jump_pnl": t(sgn * by(leg["res"].where(leg["res"].abs() >= 0.2, 0.0))),
            "ex_jump_pnl": t(sgn * by(leg["res"].where(leg["res"].abs() < 0.2, 0.0))),
        }
        # The same book names, but only those the forecast puts on this side's
        # extreme 30%: does the optimizer's choice inside that set help?
        core = leg["dec"].isin([0, 1, 2] if sgn < 0 else [7, 8, 9])
        r["names_in_extreme30_bw"] = t(sgn * (leg["res"] * wt).where(core).groupby(leg["eom"]).sum()
                                       / wt.where(core).groupby(leg["eom"]).sum())
        r["names_outside_extreme30_bw"] = t(sgn * (leg["res"] * wt).where(~core).groupby(leg["eom"]).sum()
                                            / wt.where(~core).groupby(leg["eom"]).sum())
        rep[side] = r
    return rep


def main() -> dict:
    f = forecasts()
    g = tournament.judged(f, "valid")
    p = data.panel(cut=pd.Timestamp("2020-12-31"))
    iv = "ivol_capm_252d" if "ivol_capm_252d" in p.columns else None
    g = g.merge(p[["permno", "eom", iv, "me"]].rename(columns={iv: "ivol"}), on=["permno", "eom"], how="left")
    rep = {}
    for name, (path, score) in BOOKS.items():
        if not (ROOT / "out" / path / "daily_holdings.parquet").exists():
            continue
        b = book(path)
        b = b[b["eom"].between(*(pd.Timestamp(x) for x in rj.WINDOWS["valid"]))]
        rep[name] = attribute(score, b, g)
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    r = main()
    fmt = lambda v: f"{v[0]*100:+.2f} (t {v[1]:+.1f})"
    for name, v in r.items():
        print(f"== {name}: %/month residual, + = profit for that leg; matched gross {v['book_gross_matched']:.2f}")
        for side in ("short", "long"):
            s = v[side]
            print(f" {side:5s} matched {s['matched_gross']:.2f} decile {fmt(s['decile'])} | names ew {fmt(s['names_ew'])} | names bw {fmt(s['names_bw'])}"
                  f" | raw bw {fmt(s['raw_bw'])}")
            print(f"       in extreme30 {fmt(s['names_in_extreme30_bw'])} outside {fmt(s['names_outside_extreme30_bw'])}"
                  f" | names {s['names_per_month']:.0f} wrong-side gross {s['gross_wrong_side']:.2f}"
                  f" >=$10bn {s['gross_ge_10bn']:.2f} beta {s['beta']:.2f} ivol {s['ivol']:.3f}")
            print(f"       jump gross {s['gross_in_jumps']:.3f} jump pnl {fmt(s['jump_pnl'])} ex-jump {fmt(s['ex_jump_pnl'])}")
            print("       gross by decile", {k: round(x, 2) for k, x in s["gross_by_decile"].items()})
