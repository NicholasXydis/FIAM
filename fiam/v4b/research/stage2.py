# Stage 2 of D17 (user, 2026-10-26: "clean, then tune to bat 12.8"). IN-SAMPLE:
# every choice here sees 2021-2026 returns; results are reported as in-sample,
# beside the clean D17 result, never in place of it. v4's 12.8%/yr is itself
# in-sample (its SIGNALS and LIMITS were chosen with 2021-2026 visible).
#
# Fast monthly screen (tune_oos.simulate, not the Nautilus engine) on formations
# 2020-12..2026-07, to find which score and pool can reach v4's level at all:
#   pools   holdable (ours: ADV >= $9m, cap >= $500m) | v4 (price >= $5, cap >=
#           $300m, fiam/book.screen); shorts need min(me, me_company) >= $500m
#   scores  v4 = the 12-signal composite exactly as fiam/book.build_signal
#           (rank-z, >= 9 present, sector-demeaned, beta_60m residualised);
#           el = walk-forward E-LASSO MaInf (all-name training) treated the same
#           way; blends w x el + (1 - w) x v4 in z units
#   book    top/bottom `n` per side (by the neutralised score), equal weight,
#           gross 1.6 split for ex-ante beta 0 (tune_oos.weights); also scaled
#           to 12% vol (v4's)
#   costs   per name, the engine's model (user: "revise cost too"): |trade| x
#           (half-spread + Y x sigma x sqrt(trade $ / (EXEC_DAYS x ADV)) + fees),
#           Y = 1 (engine and v4 headline), sigma = rvol_21d (daily), ADV =
#           dolvol_126d, half-spread = bidaskhl_21d x v4's quoted/high-low ratio
#           by size group (calibrated on 2015-2020, submission/models/spreads.json),
#           fees 1 bp, trades paced over 5 days at $1bn; borrow by short-interest
#           tier is approximated by 0.33%/yr on short gross (the E5 book's rate).
#           (The first run charged a flat 36 bp per dollar; D17 records it.)
# Usage: python -m fiam.v4b.research.stage2

import json

import numpy as np
import pandas as pd

from fiam import paths

from fiam.v4b.elasso.walkforward import ROOT, holdable
from fiam.v4b.forecast import data
from fiam.v4b.research import tune_oos as T

OUT = ROOT / "stage2.json"
SIGNALS = {"ivol_capm_21d": -1, "be_me": +1, "qmj": +1, "at_gr1": -1, "niq_su": +1, "ope_be": +1,
           "chcsho_12m": -1, "o_score": -1, "ret_12_1": +1, "gp_at": +1, "noa_gr1a": -1, "eqnetis_at": -1}
WIN = ("2020-12-31", "2026-07-31")
BLENDS = (0.0, 0.25, 0.5, 0.75, 1.0)
NAMES = (100, 150, 200)
VOL = 0.12
NAV, Y, EXEC_DAYS, FEES, BORROW = 1e9, 1.0, 5, 1e-4, 0.0033
RATIO = json.loads((paths.SUBMISSION / "models" / "spreads.json").read_text())["ratio_by_size_grp"]


def rank_z(p: pd.DataFrame, s: pd.Series) -> pd.Series:
    r = s.groupby(p["eom"]).rank(pct=True)
    g = r.groupby(p["eom"])
    return (r - g.transform("mean")) / g.transform("std").replace(0.0, np.nan)


def neutral(p: pd.DataFrame, s: pd.Series) -> pd.Series:
    y = s - s.groupby([p["eom"], p["sector"]]).transform("mean")
    x = p["beta"] - p["beta"].groupby(p["eom"]).transform("mean")
    y = y - y.groupby(p["eom"]).transform("mean")
    b = (x * y).groupby(p["eom"]).transform("sum") / (x * x).groupby(p["eom"]).transform("sum")
    return y - b.fillna(0.0) * x


def panel(pool: str) -> pd.DataFrame:
    p = data.panel(cut=pd.Timestamp("2026-08-31"))
    p = p[p["eom"].between(pd.Timestamp("2020-06-30"), pd.Timestamp(WIN[1])) & (p["me"] > 0)]
    keep = holdable(p) & (p["prc"].abs() >= 5.0) if pool == "holdable" else (p["prc"].abs() >= 5.0) & (p["me"] >= 300.0)
    p = p[keep].copy()
    p["short_ok"] = p[["me", "me_company"]].min(axis=1) >= 500.0
    p["sector"] = p["gics"].astype("string").str[:2].fillna("XX")
    p["beta"] = p["beta_60m"].fillna(p.groupby("eom")["beta_60m"].transform("median")).clip(0.2, 3.0)
    p["iv"] = p["ivol_capm_252d"].fillna(p.groupby("eom")["ivol_capm_252d"].transform("median"))
    p["r"] = p["ret_exc_lead1m"].fillna(0.0)
    sg = pd.read_parquet(data.PANEL, columns=["permno", "eom", "size_grp"], filters=[("eom", ">=", pd.Timestamp("2020-06-30"))])
    sg["eom"] = pd.to_datetime(sg["eom"]).astype("datetime64[ns]")
    p = p.merge(sg, on=["permno", "eom"], how="left")
    half = p["bidaskhl_21d"] * p["size_grp"].astype(str).map(RATIO)
    p["half"] = half.fillna(half.groupby(p["eom"]).transform("median")).fillna(0.005)
    p["sig"] = p["rvol_21d"].fillna(p.groupby("eom")["rvol_21d"].transform("median")).clip(upper=0.2)
    p["adv"] = p["dolvol_126d"].clip(lower=1e5)
    table = pd.concat([rank_z(p, p[c]) * s for c, s in SIGNALS.items()], axis=1)
    p["v4"] = table.mean(axis=1).where(table.notna().sum(axis=1) >= 9)
    f = pd.read_parquet(ROOT / "month" / "forecastElasso_raw.parquet", columns=["date", "permno", "MaInf"])
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    p = p.merge(f[["eom", "permno", "MaInf"]], on=["eom", "permno"], how="left")
    p = p.dropna(subset=["v4", "MaInf"]).reset_index(drop=True)
    p["v4"] = rank_z(p, neutral(p, p["v4"]))
    p["el"] = rank_z(p, neutral(p, p["MaInf"]))
    w = p["me"] * p["r"]
    p.attrs["mkt"] = w.groupby(p["eom"]).sum() / p["me"].groupby(p["eom"]).sum()
    return p


def book(p: pd.DataFrame, s: pd.Series, n: int) -> pd.Series:
    rk = s.groupby(p["eom"]).rank(ascending=False, method="first")
    srk = s.where(p["short_ok"]).groupby(p["eom"]).rank(method="first")
    q = pd.Series(0.0, index=p.index)  # tune_oos.weights reads ranks in (0, 1]: top = long, bottom = short
    q[rk <= n] = 1.0
    q[srk <= n] = 0.0
    q[(rk > n) & ~(srk <= n)] = 0.5
    return T.weights(p, q, 0.5 - 1e-9, 0.0, "equal")


# tune_oos.simulate with the per-name cost model above in place of the flat rate.
def simulate(p: pd.DataFrame, w: pd.Series) -> pd.DataFrame:
    d = p.assign(w=w)[["eom", "permno", "w", "r", "half", "sig", "adv"]]
    d = d[d["w"] != 0]
    piv = lambda c: d.pivot_table(index="eom", columns="permno", values=c, aggfunc="last")
    wide = piv("w").fillna(0.0)
    rw = piv("r").reindex_like(wide).fillna(0.0)
    drift = (wide * (1 + rw)).shift(1).fillna(0.0).div((1 + (wide * rw).sum(1)).shift(1).fillna(1.0), axis=0)
    trade = (wide - drift).abs()
    # a name sold out entirely carries no row this month: price it at last month's inputs
    cost_in = {c: piv(c).reindex_like(wide).combine_first(piv(c).reindex_like(wide).shift(1)) for c in ("half", "sig", "adv")}
    unit = (cost_in["half"].fillna(0.005) + FEES
            + Y * cost_in["sig"].fillna(0.03) * np.sqrt(trade * NAV / (EXEC_DAYS * cost_in["adv"].fillna(1e6))))
    out = pd.DataFrame({"long": (wide.clip(lower=0) * rw).sum(1), "short": (wide.clip(upper=0) * rw).sum(1),
                        "trade": trade.sum(1),
                        "cost": (trade * unit).sum(1) + BORROW / 12 * (-wide.clip(upper=0)).sum(1)})
    out["net"] = out["long"] + out["short"] - out["cost"]
    out["mkt"] = p.attrs["mkt"].reindex(out.index)
    return out


def stats(m: pd.DataFrame) -> dict:
    m = m[(m.index >= WIN[0]) & (m.index <= WIN[1])]
    out = T.stats(m)
    k = VOL / out["vol"] if out["vol"] > 0 else 0.0
    out["net_at_12vol"] = float((m["long"] + m["short"]).mean() * 12 * k - m["cost"].mean() * 12 * k)
    return out


def main() -> dict:
    rep = {}
    for pool in ("holdable", "v4"):
        p = panel(pool)
        for w in BLENDS:
            s = w * p["el"] + (1 - w) * p["v4"]
            for n in NAMES:
                rep[f"{pool}|el{w:.2f}|n{n}"] = stats(simulate(p, book(p, s, n)))
    OUT.write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    for k, s in main().items():
        print(f"{k:22s} net {s['net']*100:+5.1f}%/yr vol {s['vol']*100:4.1f} SR {s['sharpe']:+.2f} beta {s['beta']:+.2f} "
              f"long a {s['long_alpha']*100:+.1f} (t {s['long_t']:+.1f}) short a {s['short_alpha']*100:+.1f} "
              f"(t {s['short_t']:+.1f}) cost {s['cost_yr']*100:.1f}% @12%vol {s['net_at_12vol']*100:+.1f}%")
