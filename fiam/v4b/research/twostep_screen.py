# D18 screen: the E6 two-step construction on formations 2016-12..2020-11 only
# (D16: nothing here reads 2021+). Rule and variants were fixed in DECISIONS D18
# before this ran.
#
# Targets come from the engine itself: ladder.World formation inputs (enhanced
# risk model with beta calibration, per-name spread/ADV/sigma/borrow, jump
# probabilities) and optimize.two_step_book. Each variant carries its own book:
# the previous target drifts by realised daily returns to the next signal day
# and is the next formation's w_pre (hysteresis, union room and trading costs
# all read it). Returns and costs: stage2.simulate (monthly ret_exc_lead1m,
# per-name half-spread + sqrt impact over 5 days + fees, borrow 0.33%/yr), legs
# against the cap-weighted holdable pool (tune_oos.stats). Excess of cash.
#
#   score      raw | raw_s6 | betamatch | betamatch_s6 (walkforward/month)
#   weighting  vw | ew (HHRZ 2018 sec. 2.5)
# Pick: highest net Sharpe among |beta| <= 0.05 and both legs' alpha > 0.
# Yardstick (not a variant): the D17 winner's executed E5 holdings a week after
# each formation, through the same simulator.
#
# Usage: FIAM_V4B_CONFIG=variant_betamatch.json python -m fiam.v4b.research.twostep_screen
#            [--months N] [--variants raw:vw,...] [--summarize]
#        on Modal, one container per variant: modal run fiam/v4b/gpu/modal_book.py::screen

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.elasso import forecaster
from fiam.v4b.elasso.walkforward import ROOT, holdable
from fiam.v4b.engine import ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.forecast import data
from fiam.v4b.research import stage2 as S2
from fiam.v4b.research import tune_oos as T

V4B = Path(__file__).resolve().parents[1]
OUT = V4B / "out" / "twostep_screen"
SCORES = ("raw", "raw_s6", "betamatch", "betamatch_s6")
WEIGHTINGS = ("vw", "ew")
YARDSTICK = V4B / "out" / "nautilus_var_betamatch" / "E5" / "daily_holdings.parquet"


def score_mu(m, name: str) -> pd.DataFrame:
    src = ROOT / "month" / name / "forecastElasso.parquet"
    return forecaster.horizon_returns(m, "Elasso_MaInf", source=src)


def eval_panel(lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    p = data.panel(cut=pd.Timestamp("2020-12-31"))
    p = p[p["eom"].between(lo, hi) & (p["me"] > 0)].copy()
    sg = pd.read_parquet(data.PANEL, columns=["permno", "eom", "size_grp"],
                         filters=[("eom", ">=", lo), ("eom", "<=", hi)])
    sg["eom"] = pd.to_datetime(sg["eom"]).astype("datetime64[ns]")
    p = p.merge(sg, on=["permno", "eom"], how="left")
    half = p["bidaskhl_21d"] * p["size_grp"].astype(str).map(S2.RATIO)
    p["half"] = half.fillna(half.groupby(p["eom"]).transform("median")).fillna(0.005)
    p["sig"] = p["rvol_21d"].fillna(p.groupby("eom")["rvol_21d"].transform("median")).clip(upper=0.2)
    p["adv"] = p["dolvol_126d"].clip(lower=1e5)
    p["r"] = p["ret_exc_lead1m"].fillna(0.0)
    pool = holdable(p) & (p["prc"].abs() >= 5.0)
    mk = p[pool]
    out = p[["eom", "permno", "r", "half", "sig", "adv"]].reset_index(drop=True)
    out.attrs["mkt"] = (mk["me"] * mk["r"]).groupby(mk["eom"]).sum() / mk["me"].groupby(mk["eom"]).sum()
    return out


# Target weights (eom, permno, w) -> the panel-aligned series stage2.simulate reads.
def evaluate(p: pd.DataFrame, targets: pd.DataFrame) -> dict:
    key = pd.MultiIndex.from_frame(p[["eom", "permno"]])
    w = targets.set_index(["eom", "permno"])["w"].groupby(level=[0, 1]).sum()
    missing = float(w[~w.index.isin(key)].abs().sum() / max(w.abs().sum(), 1e-12))
    s = pd.Series(w.reindex(key).fillna(0.0).to_numpy(), index=p.index)
    mo = S2.simulate(p, s)
    out = T.stats(mo)
    out["gross"] = float(targets.groupby("eom")["w"].apply(lambda x: x.abs().sum()).mean())
    out["names"] = float(targets.groupby("eom").size().mean())
    out["weight_outside_panel"] = missing
    out["by_year"] = {str(y): float(g["net"].sum()) for y, g in mo.groupby(mo.index.year + (mo.index.month == 12))}
    return out


def yardstick(eoms: list) -> pd.DataFrame:
    h = pd.read_parquet(YARDSTICK, columns=["date", "permno", "w"])
    days = pd.DatetimeIndex(sorted(h["date"].unique()))
    rows = []
    for eom in eoms:
        after = days[days > eom]
        if len(after) < 6:
            continue
        x = h[h["date"] == after[5]]
        rows.append(pd.DataFrame({"eom": eom, "permno": x["permno"].to_numpy(), "w": x["w"].to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def window_eoms(world=None, months: int = 0) -> list:
    if world is not None:
        e = sorted(world.rm.exp.eom.unique())
    else:
        e = pd.date_range(ladder.WINDOW[0], ladder.WINDOW[1], freq="ME")
    eoms = [pd.Timestamp(x) for x in e if ladder.WINDOW[0] <= x <= ladder.WINDOW[1]]
    return eoms[:months] if months else eoms


# Targets and logs for the given (score, weighting) variants, one book each.
def build(variants: list, months: int = 0) -> None:
    m = load()
    t0 = time.time()
    world = ladder.World(m)
    print(f"world built in {time.time() - t0:.0f}s", flush=True)
    eoms = window_eoms(world, months)
    rets = world.market["returns"]
    mus = {s: score_mu(m, s) for s in {s for s, _ in variants}}
    mus = {s: {e: g.set_index("permno")["mu"] for e, g in f.groupby("eom")} for s, f in mus.items()}
    steps = {wt: ladder.steps(n_e3=250)["E6" if wt == "vw" else "E6_ew"] for wt in WEIGHTINGS}
    kappa = forecaster.kappa_for(m, "Elasso_MaInf")
    state = {v: pd.Series(dtype=float) for v in variants}
    targets = {v: [] for v in variants}
    logs = {v: [] for v in variants}
    prev_day = None
    for eom in eoms:
        day = world.signal_day(eom)
        base = world.formation(eom, "Elasso_MaInf", pd.Series(dtype=float))
        hscale = forecaster.horizon_scale(0, base.horizon, kappa)
        for v in variants:
            s, wt = v
            w_pre = state[v]
            if prev_day is not None and not w_pre.empty:
                w_pre = optimize.drift(w_pre, rets.loc[(rets.index > prev_day) & (rets.index <= day)])
            f = dataclasses.replace(base, mu=mus[s].get(eom, pd.Series(dtype=float)) * hscale, w_pre=w_pre)
            w, log = optimize.build_book(f, m, steps[wt])
            if w is None:
                print(f"{s}/{wt} {eom.date()} FAILED {log.get('status')}", flush=True)
                w = w_pre  # hold the drifted book; logged
            state[v] = w
            targets[v].append(pd.DataFrame({"eom": eom, "permno": w.index, "w": w.to_numpy()}))
            logs[v].append({k: x for k, x in log.items() if k != "shadows"})
        prev_day = day
        print(f"{eom.date()} {time.time() - t0:.0f}s " + " ".join(
            f"{s}/{wt}:{len(state[(s, wt)])}n,g{state[(s, wt)].abs().sum():.2f},"
            f"v{logs[(s, wt)][-1].get('pred_vol', float('nan')):.3f},rho{logs[(s, wt)][-1].get('rho')}"
            for s, wt in variants), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for s, wt in variants:
        pd.concat(targets[(s, wt)], ignore_index=True).to_parquet(OUT / f"targets_{s}_{wt}.parquet", index=False)
        (OUT / f"logs_{s}_{wt}.json").write_text(json.dumps(logs[(s, wt)], default=str) + "\n")


# Stats for every variant whose targets exist, the yardstick, and the D18 pick.
def summarize(months: int = 0) -> dict:
    eoms = window_eoms(None, months)
    p = eval_panel(eoms[0], eoms[-1])
    rep = {"window_eom": [str(eoms[0].date()), str(eoms[-1].date())], "variants": {}}
    for s in SCORES:
        for wt in WEIGHTINGS:
            path = OUT / f"targets_{s}_{wt}.parquet"
            if not path.exists():
                continue
            tg = pd.read_parquet(path)
            if tg.groupby("eom").size().size < 3:  # an empty or near-empty book is reported, not scored
                rep["variants"][f"{s}|{wt}"] = {"empty_months": int(len(window_eoms(None, months)) - tg["eom"].nunique())}
                continue
            st = evaluate(p, tg)
            lg = json.loads((OUT / f"logs_{s}_{wt}.json").read_text())
            ok = [x for x in lg if "pred_vol" in x]
            st |= {"pred_vol": float(np.mean([x["pred_vol"] for x in ok])) if ok else None,
                   "pred_beta_abs": float(np.mean([abs(x["pred_beta"]) for x in ok])) if ok else None,
                   "rho_below_0.9": int(sum(x["rho"] < 0.9 for x in ok)), "failed": len(lg) - len(ok),
                   "union_misses": int(sum(not x.get("union_fits", True) for x in ok)),
                   "sector_slack_max": float(max(((x.get("slacks") or {}).get("sector_max", 0.0) for x in ok),
                                                 default=0.0))}
            rep["variants"][f"{s}|{wt}"] = st
    if YARDSTICK.exists():
        rep["yardstick_d17_e5"] = evaluate(p, yardstick(eoms))
    scored = {k: v for k, v in rep["variants"].items() if "net" in v}
    ok = {k: v for k, v in scored.items()
          if abs(v["beta"]) <= 0.05 and v["long_alpha"] > 0 and v["short_alpha"] > 0}
    rep["qualified"] = sorted(ok)
    pool = ok or scored
    rep["pick"] = max(pool, key=lambda k: pool[k]["sharpe"]) if pool else None
    (OUT / "screen.json").write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


def line(k: str, s: dict) -> str:
    return (f"{k:20s} net {s['net']*100:+5.1f}%/yr SR {s['sharpe']:+.2f} vol {s['vol']*100:4.1f} beta {s['beta']:+.3f} "
            f"long a {s['long_alpha']*100:+.1f} (t {s['long_t']:+.1f}) short a {s['short_alpha']*100:+.1f} "
            f"(t {s['short_t']:+.1f}) turn {s['turnover_yr']:.1f}x cost {s['cost_yr']*100:.1f}% "
            f"gross {s['gross']:.2f} names {s['names']:.0f}")


def report(r: dict) -> None:
    for k, s in r["variants"].items():
        if "net" not in s:
            print(k, s)
            continue
        print(line(k, s), f"| predvol {s['pred_vol']}, rho<0.9 {s['rho_below_0.9']}, failed {s['failed']}")
    if "yardstick_d17_e5" in r:
        print(line("D17 E5 yardstick", r["yardstick_d17_e5"]))
    print("qualified", r["qualified"], "pick", r["pick"])


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--months", type=int, default=0)
    a.add_argument("--variants", default="", help="score:weighting,... (default: all 8)")
    a.add_argument("--summarize", action="store_true")
    args = a.parse_args()
    if not args.summarize:
        vs = [tuple(x.split(":")) for x in args.variants.split(",")] if args.variants else \
            [(s, wt) for s in SCORES for wt in WEIGHTINGS]
        build(vs, args.months)
    report(summarize(args.months))
