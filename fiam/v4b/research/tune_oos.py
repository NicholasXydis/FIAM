# STOPPED, NOT ADOPTED (user, 2026-10-26: "no i want to keep 2021-now window
# prresentable"). Ran once before that message: 144 configs scored on 2021-24, the
# pick and the baseline on 2025-26; no config had both legs > 0, the pick lost
# 5.3%/yr on 2025-26. Kept only as the record of that disclosed look (D16).
#
# Portfolio-construction tuning ON 2021-2024 (user, 2026-10-26: "before running
# a full oos backtest i want you to tune and adjust the model so that it
# actually make the strategy perfom better than current strategy oos").
# DISCLOSED: every choice made here sees 2021-2024 returns, so 2021-2024 is
# in-sample for the result. Formations 2025-01..2026-07 are held out: they are
# scored once, for the chosen configuration and the baseline, after the choice.
#
# Fast monthly simulator (not the Nautilus engine):
#   pool     walkforward.holdable names at each eom (the book can hold them)
#   score    the walk-forward E-LASSO MaInf (training universe `all` or
#            `holdable`), ranked in the pool; transform raw | volneut (within
#            ivol terciles) | betamatch (within beta_60m quintiles); optionally
#            the mean of the last `smooth` months' ranks (past only)
#   legs     long the top `q` of the pool, short the bottom `q`, after dropping
#            the outer `trim` share at each end; equal or inverse-ivol weights
#   beta     gross G = 1.6 split so long gross x beta_L = short gross x beta_S
#            (beta_60m, ex-ante), net capped at +-0.5
#   return   sum w x ret_exc_lead1m (missing = 0, delisted names kept), less
#            36 bp per dollar traded (the E5 2021-26 book's realised spread +
#            impact + fees per dollar traded) and 0.33%/yr borrow on short gross
#   pick     highest net Sharpe on 2021-2024 with both legs' alpha (vs the
#            cap-weighted pool) > 0; baseline = all / volneut / q 0.1 / trim 0 /
#            smooth 1 / equal (the shape of the current book's score)
# Returns are monthly, excess of cash (the real book also earns cash interest).
# Usage: python -m fiam.v4b.research.tune_oos

import itertools
import json

import numpy as np
import pandas as pd

from fiam.v4b.elasso.walkforward import ROOT, holdable
from fiam.v4b.forecast import data

OUT = ROOT / "tune_oos.json"
TUNE = ("2020-12-31", "2024-11-30")  # formations whose returns land in 2021-2024
HOLD = ("2024-12-31", "2026-07-31")
GROSS, NET_MAX, COST, BORROW = 1.6, 0.5, 0.0036, 0.0033
RUNS = {"all": ROOT / "month" / "forecastElasso_raw.parquet",
        "holdable": ROOT / "month_holdable" / "forecastElasso_raw.parquet"}
GRID = dict(train=("all", "holdable"), transform=("raw", "volneut", "betamatch"), q=(0.1, 0.2, 0.33),
            trim=(0.0, 0.05), smooth=(1, 3), weight=("equal", "invvol"))
BASELINE = dict(train="all", transform="volneut", q=0.1, trim=0.0, smooth=1, weight="equal")


def panel() -> pd.DataFrame:
    p = data.panel(cut=pd.Timestamp("2026-08-31"))
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & (p["me"] > 0) & (p["eom"] >= "2020-06-30")]
    p = p[holdable(p)][["permno", "eom", "me", "beta_60m", "ivol_capm_252d", "ret_exc_lead1m"]].copy()
    for name, path in RUNS.items():
        f = pd.read_parquet(path, columns=["date", "permno", "MaInf"])
        f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
        p = p.merge(f[["eom", "permno", "MaInf"]].rename(columns={"MaInf": name}), on=["eom", "permno"], how="left")
    p = p.dropna(subset=list(RUNS))
    p["r"] = p["ret_exc_lead1m"].fillna(0.0)
    p["beta"] = p["beta_60m"].fillna(p.groupby("eom")["beta_60m"].transform("median")).clip(0.2, 3.0)
    p["iv"] = p["ivol_capm_252d"].fillna(p.groupby("eom")["ivol_capm_252d"].transform("median"))
    g = p.groupby("eom")
    p["ivt"] = g["iv"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
    p["bq"] = g["beta"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    mkt = (p["r"] * p["me"]).groupby(p["eom"]).sum() / p["me"].groupby(p["eom"]).sum()
    p.attrs["mkt"] = mkt
    return p


def scored(p: pd.DataFrame, train: str, transform: str, smooth: int) -> pd.Series:
    keys = {"raw": ["eom"], "volneut": ["eom", "ivt"], "betamatch": ["eom", "bq"]}[transform]
    s = p.groupby(keys)[train].rank(pct=True)
    if smooth > 1:  # mean of this and the previous months' ranks for the same name (past only)
        w = s.groupby([p["permno"]]).transform(lambda x: x.rolling(smooth, min_periods=1).mean())
        s = w.groupby(p["eom"]).rank(pct=True)
    return s


def weights(p: pd.DataFrame, s: pd.Series, q: float, trim: float, weight: str) -> pd.Series:
    side = pd.Series(0.0, index=p.index)
    side[(s > 1 - q - trim) & (s <= 1 - trim)] = 1.0
    side[(s >= trim) & (s < q + trim)] = -1.0
    raw = side / (p["iv"] if weight == "invvol" else 1.0)
    w = pd.Series(0.0, index=p.index)
    for eom, idx in p.groupby("eom").groups.items():
        r = raw.loc[idx]
        L, S = r[r > 0], -r[r < 0]
        if L.empty or S.empty:
            continue
        bl = (L / L.sum() * p.loc[L.index, "beta"]).sum()
        bs = (S / S.sum() * p.loc[S.index, "beta"]).sum()
        gl = GROSS * bs / (bl + bs)  # gl * bl = gs * bs, gl + gs = GROSS
        gl = float(np.clip(gl, (GROSS - NET_MAX) / 2, (GROSS + NET_MAX) / 2))
        w.loc[L.index] = gl * L / L.sum()
        w.loc[S.index] = -(GROSS - gl) * S / S.sum()
    return w


def simulate(p: pd.DataFrame, w: pd.Series) -> pd.DataFrame:
    d = pd.DataFrame({"eom": p["eom"], "permno": p["permno"], "w": w, "r": p["r"]})
    d = d[d["w"] != 0]
    wide = d.pivot_table(index="eom", columns="permno", values="w", aggfunc="sum").fillna(0.0)
    rw = d.pivot_table(index="eom", columns="permno", values="r", aggfunc="sum").reindex_like(wide).fillna(0.0)
    drift = (wide * (1 + rw)).shift(1).fillna(0.0)  # last month's book after its returns
    trade = (wide - drift.div((1 + (wide * rw).sum(1)).shift(1).fillna(1.0), axis=0)).abs().sum(1)
    long = (wide.clip(lower=0) * rw).sum(1)
    short = (wide.clip(upper=0) * rw).sum(1)
    out = pd.DataFrame({"long": long, "short": short, "trade": trade,
                        "cost": COST * trade + BORROW / 12 * (-wide.clip(upper=0)).sum(1)})
    out["net"] = out["long"] + out["short"] - out["cost"]
    out["mkt"] = p.attrs["mkt"].reindex(out.index)
    return out


def stats(m: pd.DataFrame) -> dict:
    ann = lambda x: float(x.mean() * 12)
    sr = lambda x: float(x.mean() / x.std() * np.sqrt(12)) if x.std() > 0 else 0.0
    t = lambda x: float(x.mean() / x.std() * np.sqrt(len(x))) if x.std() > 0 else 0.0
    out = {"net": ann(m["net"]), "sharpe": sr(m["net"]), "vol": float(m["net"].std() * np.sqrt(12)),
           "turnover_yr": ann(m["trade"]), "cost_yr": ann(m["cost"]),
           "beta": float(np.polyfit(m["mkt"], m["long"] + m["short"], 1)[0])}
    for leg in ("long", "short"):
        b = np.polyfit(m["mkt"], m[leg], 1)[0]
        a = m[leg] - b * m["mkt"]
        out[f"{leg}_alpha"], out[f"{leg}_t"] = ann(a), t(a)
    return out


def run(p: pd.DataFrame, cfg: dict) -> dict:
    w = weights(p, scored(p, cfg["train"], cfg["transform"], cfg["smooth"]), cfg["q"], cfg["trim"], cfg["weight"])
    m = simulate(p, w)
    return {win: stats(m[(m.index >= lo) & (m.index <= hi)]) for win, (lo, hi) in (("tune", TUNE), ("hold", HOLD))}


def main() -> dict:
    p = panel()
    rows = []
    for vals in itertools.product(*GRID.values()):
        cfg = dict(zip(GRID, vals))
        rows.append(cfg | {"tune": run(p, cfg)["tune"]})
    ok = [r for r in rows if r["tune"]["long_alpha"] > 0 and r["tune"]["short_alpha"] > 0]
    best = max(ok or rows, key=lambda r: r["tune"]["sharpe"])
    pick = {k: best[k] for k in GRID}
    rep = {"grid_size": len(rows), "qualified": len(ok), "pick": pick,
           "pick_result": run(p, pick), "baseline": BASELINE, "baseline_result": run(p, BASELINE),
           "top10_tune": sorted(rows, key=lambda r: -r["tune"]["sharpe"])[:10]}
    OUT.write_text(json.dumps(rep, indent=1, default=float) + "\n")
    return rep


if __name__ == "__main__":
    r = main()
    f = lambda s: (f"net {s['net']*100:+.1f}%/yr SR {s['sharpe']:+.2f} vol {s['vol']*100:.1f} beta {s['beta']:+.2f} "
                   f"long a {s['long_alpha']*100:+.1f} (t {s['long_t']:+.1f}) short a {s['short_alpha']*100:+.1f} "
                   f"(t {s['short_t']:+.1f}) turnover {s['turnover_yr']:.1f}x cost {s['cost_yr']*100:.1f}%")
    print(f"grid {r['grid_size']} configs, {r['qualified']} with both legs > 0 on 2021-24")
    print("top 10 on 2021-24 (in-sample):")
    for x in r["top10_tune"]:
        print("  ", {k: x[k] for k in GRID}, "|", f(x["tune"]))
    for name in ("baseline", "pick"):
        print(f"== {name} {r[name]}")
        for win in ("tune", "hold"):
            print(f"   {win} {'2021-24 (in-sample)' if win == 'tune' else '2025-26 (held out)'}: {f(r[name + '_result'][win])}")
