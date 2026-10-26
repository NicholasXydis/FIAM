# Where does the forecast's edge go between the score and the book?
# (user, 2026-10-26: "find out the structural causes because this forecaster
# had a real edge"). Diagnostic on 2021-2026 (already opened by the single E5
# run, lesson 95) with 2017-2020 alongside; nothing here selects anything.
#
# Every portfolio is scored on the same next-month return: ret_exc_lead1m less
# a cross-sectional beta_60m + GICS-sector fit (tournament.judged), over the
# long_ok universe. Legs are reported per unit of gross, + = profit for that
# leg (short profit = - residual), %/month with t.
#   ew_raw      equal-weighted D9 / D0 of the raw walk-forward resrank score,
#               shortable pool (short_ok)
#   ew_volneut  same, volneut score (what the book reads)
#   vw_volneut  same deciles, cap-weighted
#   big_volneut volneut deciles within cap >= $2bn
#   target      the E5 target book at each formation (execution intents:
#               target_qty x price at the signal), each side scaled to 1
# Exposures: mean cross-sectional percentile of ivol, size (me), beta and of
# the volneut score itself, gross-weighted, for each leg.
# Usage: python -m fiam.v4b.research.oos_causes

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.forecast import data

ROOT = Path(__file__).resolve().parents[1] / "out"
WF = ROOT / "elasso" / "walkforward" / "month"
BOOKS = {"valid": ROOT / "nautilus_e5_wf2" / "E5", "oos": ROOT / "nautilus_e5_oos" / "E5"}
WIN = {"valid": ("2016-12-31", "2020-11-30"), "oos": ("2020-12-31", "2026-07-31")}
OUT = ROOT / "oos_causes.json"


def universe() -> pd.DataFrame:
    p = data.panel(cut=pd.Timestamp("2026-08-31"))
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & p["ret_exc_lead1m"].notna()][
        ["permno", "eom", "gics", "beta_60m", "me", "ivol_capm_252d", "short_ok", "ret_exc_lead1m"]].copy()
    p["sector"] = p["gics"].astype(str).str[:2]

    def resid(d):
        b = d["beta_60m"].fillna(d["beta_60m"].median()).to_numpy()
        X = np.column_stack([b, pd.get_dummies(d["sector"]).to_numpy(float)])
        y = d["ret_exc_lead1m"].to_numpy(float)
        c, *_ = np.linalg.lstsq(X, y, rcond=None)
        return pd.Series(y - X @ c, index=d.index)

    p["res"] = p.groupby("eom", group_keys=False).apply(resid, include_groups=False)
    for c in ("ivol_capm_252d", "me", "beta_60m"):
        p[f"pct_{c}"] = p.groupby("eom")[c].rank(pct=True)
    return p


def scores() -> pd.DataFrame:
    def load(path, name):
        f = pd.read_parquet(path, columns=["date", "permno", "MaInf"])
        f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
        return f.rename(columns={"MaInf": name})[["eom", "permno", name]]

    return load(WF / "forecastElasso_raw.parquet", "raw").merge(
        load(WF / "volneut" / "forecastElasso.parquet", "volneut"), on=["eom", "permno"])


def targets(book: Path) -> pd.DataFrame:
    it = pd.read_csv(book / "execution_intents.csv", usecols=["date", "signal", "permno", "target_qty"])
    first = it.sort_values("date").groupby(["signal", "permno"], as_index=False).first()
    first = first[first["target_qty"] != 0]
    h = pd.read_parquet(book / "daily_holdings.parquet", columns=["date", "permno", "quantity", "w"])
    h = h[h["quantity"] != 0].copy()
    h["px_w"] = h["w"] / h["quantity"]  # weight per share = price / NAV, engine's own share units
    h["date"] = pd.to_datetime(h["date"]).astype("datetime64[ns]")
    first["date"] = pd.to_datetime(first["date"]).astype("datetime64[ns]")
    # Price each target at the first session on or after its first intent that holds the name.
    t = pd.merge_asof(first.sort_values("date"), h[["date", "permno", "px_w"]].sort_values("date"),
                      on="date", by="permno", direction="forward", tolerance=pd.Timedelta(days=10))
    t["w"] = t["target_qty"] * t["px_w"]
    # The signal is the last session on or before eom (a weekend eom signals on Friday).
    t["eom"] = (pd.to_datetime(t["signal"]) + pd.offsets.MonthEnd(0)).astype("datetime64[ns]")
    return t.dropna(subset=["w"])[["eom", "permno", "w"]]


def tstat(s: pd.Series) -> list:
    s = s.dropna()
    return [round(float(s.mean() * 100), 3), round(float(s.mean() / s.std() * np.sqrt(len(s))), 2), int(len(s))]


def legs(g: pd.DataFrame, wcol: str) -> dict:
    out = {}
    for side, sgn in (("long", 1), ("short", -1)):
        d = g[np.sign(g[wcol]) == sgn].copy()
        d["a"] = d[wcol].abs() / d.groupby("eom")[wcol].transform(lambda s: s.abs().sum())
        ret = (d["a"] * d["res"]).groupby(d["eom"]).sum() * sgn
        exp = {c: float((d["a"] * d[c]).groupby(d["eom"]).sum().mean())
               for c in ("pct_ivol_capm_252d", "pct_me", "pct_beta_60m", "pct_score")}
        out[side] = {"profit": tstat(ret), "names": float(d.groupby("eom").size().mean()), "exposure": exp}
    return out


def decile_book(g: pd.DataFrame, score: str, weight: str | None = None) -> pd.DataFrame:
    g = g.copy()
    dec = g.groupby("eom")[score].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    base = g["me"] if weight == "me" else 1.0
    g["wt"] = np.where(dec == 9, 1.0, np.where(dec == 0, -1.0, 0.0)) * base
    return g[g["wt"] != 0]


# Inside each tail decile (shortable pool): profit by ivol tercile and by
# size (cap >= $2bn or not), equal-weighted, + = profit for that leg.
def tails(g: pd.DataFrame, score: str) -> dict:
    g = g.copy()
    g["dec"] = g.groupby("eom")[score].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    g["ivt"] = g.groupby("eom")["ivol_capm_252d"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"]))
    g["big"] = np.where(g["me"] >= 2000, "big", "small")
    out = {}
    for side, d, sgn in (("short", 0, -1), ("long", 9, 1)):
        t = g[g["dec"] == d]
        out[side] = {f"ivol_{k}": tstat(sgn * x.groupby("eom")["res"].mean()) for k, x in t.groupby("ivt", observed=True)}
        out[side] |= {k: tstat(sgn * x.groupby("eom")["res"].mean()) for k, x in t.groupby("big")}
    return out


# Does realised alpha scale with residual vol (alpha = IC x sigma x score)?
# Within each ivol tercile of the shortable pool: rank IC of the score, the
# slope of the residual on the centred score percentile (%/month for top vs
# bottom of the tercile), and the residual sd.
def alpha_vs_vol(g: pd.DataFrame, score: str) -> dict:
    g = g.copy()
    g["ivt"] = g.groupby("eom")["ivol_capm_252d"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"]))
    out = {}
    for k, d in g.groupby("ivt", observed=True):
        d = d.copy()
        d["z"] = d.groupby("eom")[score].rank(pct=True) - 0.5
        ic = d.groupby("eom").apply(lambda x: x[score].corr(x["res"], method="spearman"), include_groups=False)
        sl = d.groupby("eom").apply(lambda x: np.polyfit(x["z"], x["res"], 1)[0], include_groups=False)
        out[k] = {"ic": tstat(ic / 100), "slope": tstat(sl), "res_sd": float(d.groupby("eom")["res"].std().mean() * 100)}
    return out


def main() -> dict:
    u, s = universe(), scores()
    g0 = u.merge(s, on=["eom", "permno"])
    g0["pct_score"] = g0.groupby("eom")["volneut"].rank(pct=True)
    rep = {}
    for win, (lo, hi) in WIN.items():
        g = g0[g0["eom"].between(pd.Timestamp(lo), pd.Timestamp(hi))]
        pool = g[g["short_ok"]]
        r = {"ew_raw": legs(decile_book(pool, "raw"), "wt"),
             "ew_volneut": legs(decile_book(pool, "volneut"), "wt"),
             "vw_volneut": legs(decile_book(pool, "volneut", "me"), "wt"),
             "big_volneut": legs(decile_book(pool[pool["me"] >= 2000], "volneut"), "wt")}
        t = targets(BOOKS[win]).merge(g, on=["eom", "permno"])
        r["target"] = legs(t, "w")
        r["target_coverage"] = float(len(t) / len(targets(BOOKS[win])))
        ic = lambda k: g.groupby("eom").apply(lambda d: d[k].corr(d["res"], method="spearman"), include_groups=False)
        r["ic"] = {k: tstat(ic(k) / 100) for k in ("raw", "volneut")}  # tstat x100 -> undo for IC
        cs = lambda a, b: float(g.groupby("eom").apply(lambda d: d[a].corr(d[b], method="spearman"),
                                                        include_groups=False).mean())
        r["score_corr"] = {f"{k}~{c}": cs(k, c) for k in ("raw", "volneut")
                           for c in ("beta_60m", "ivol_capm_252d", "me")}
        r["tails"] = {k: tails(pool, k) for k in ("raw", "volneut")}
        r["alpha_vs_vol"] = {k: alpha_vs_vol(pool, k) for k in ("raw", "volneut")}
        rep[win] = r
    OUT.write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    rep = main()
    for win, r in rep.items():
        print(f"===== {win}  (residual %/month per unit gross, t, months)")
        print("  IC", r["ic"], "target rows matched", round(r["target_coverage"], 3))
        print("  score corr", {k: round(v, 2) for k, v in r["score_corr"].items()})
        for k, v in r["alpha_vs_vol"].items():
            print(f"  alpha~vol {k:7s} " + " | ".join(f"{t}: IC {x['ic'][0]:+.3f}({x['ic'][1]:+.1f}) slope {x['slope'][0]:+.2f}({x['slope'][1]:+.1f}) sd {x['res_sd']:.1f}" for t, x in v.items()))
        for k, v in r["tails"].items():
            for side, x in v.items():
                print(f"  tail {k:7s} {side:5s} " + " ".join(f"{a} {b[0]:+.2f}({b[1]:+.1f})" for a, b in x.items()))
        for k in ("ew_raw", "ew_volneut", "vw_volneut", "big_volneut", "target"):
            x = r[k]
            print(f"  {k:12s} long {x['long']['profit']} short {x['short']['profit']} "
                  f"names {x['long']['names']:.0f}/{x['short']['names']:.0f}")
            for side in ("long", "short"):
                e = x[side]["exposure"]
                print(f"      {side:5s} pct ivol {e['pct_ivol_capm_252d']:.2f} size {e['pct_me']:.2f} "
                      f"beta {e['pct_beta_60m']:.2f} score {e['pct_score']:.2f}")
