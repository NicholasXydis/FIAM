# Why is the tail score weakest on the short side? (LESSONS 57+)
#
# Diagnostics only: nothing here selects a model or a threshold. Both windows
# are reported side by side; a mechanism counts only if it shows in validation
# (2016-12..2020-11) as well as in 2021+.
# Universe: the shortable pool (eom t-1 me >= $500m) of the rolling tail run.
# Returns are monthly excess, relative to the pool's equal-weight mean.

import json
import sys

import numpy as np
import pandas as pd

from fiam.v4b.elasso import rolling_judge as rj
from fiam.v4b.elasso.rolling import BASE, CUT
from fiam.v4b.forecast import data

COL = "MaInf"
PROFILE = ["ivol_capm_252d", "beta_60m", "betadown_252d", "me", "prc", "ret_12_1", "ret_1_0",
           "rmax1_21d", "iskew_capm_21d", "turnover_126d", "o_score", "gp_at", "be_me"]


def frame(window: str) -> pd.DataFrame:
    f = rj.scores(window)
    f = f[f["short_ok"]].copy()
    p = data.panel(cut=CUT)[["permno", "eom", "gics", *[c for c in PROFILE if c != "me"]]]
    chars = data.characteristics()
    cov = pd.read_parquet(data.PANEL, columns=["permno", "eom", *chars],
                          filters=[("eom", ">=", f["eom"].min()), ("eom", "<=", f["eom"].max())])
    cov["eom"] = pd.to_datetime(cov["eom"]).astype("datetime64[ns]")
    cov["coverage"] = cov[chars].notna().mean(axis=1)
    f = f.merge(p, on=["permno", "eom"], how="left").merge(cov[["permno", "eom", "coverage"]], on=["permno", "eom"], how="left")
    f["rel"] = f["y"] - f.groupby("eom")["y"].transform("mean")
    g = f.groupby("eom")
    f["dec"] = g["tail_" + COL].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    f["r_up"] = g["up_" + COL].rank(pct=True)
    f["r_dn"] = g["down_" + COL].rank(pct=True)
    f["sector"] = f["gics"].astype(str).str[:2]
    # Month-by-month cross-sectional beta adjustment: residual of rel on beta_60m.
    def resid(d):
        b = d["beta_60m"].fillna(d["beta_60m"].median())
        X = np.column_stack([np.ones(len(d)), b])
        coef, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        return pd.Series(d["y"].to_numpy() - X @ coef, index=d.index)
    f["resid_beta"] = f.groupby("eom", group_keys=False).apply(resid, include_groups=False)
    vw = f.groupby("eom").apply(lambda d: np.average(d["y"], weights=d["me"]), include_groups=False)
    f["mkt"] = f["eom"].map(vw)
    return f


def _mt(s: pd.Series) -> dict:
    return {"mean": float(s.mean()), "t": float(s.mean() / s.std() * np.sqrt(len(s)))}


def diagnose(window: str) -> dict:
    f = frame(window)
    out = {}
    # 1. Who sits in each tail.
    prof = f.groupby("dec")[PROFILE + ["coverage", "r_up", "r_dn"]].median()
    out["profile"] = prof.loc[[0, 1, 5, 8, 9]].round(4).to_dict(orient="index")
    out["corr_up_down"] = float(f.groupby("eom").apply(lambda d: d["up_" + COL].corr(d["down_" + COL]), include_groups=False).mean())
    # 2. Return shape of the short decile (name-month level).
    d0 = f[f["dec"] == 0]
    top5 = d0["rel"] > d0["rel"].quantile(0.95)
    out["d0_shape"] = {
        "mean": float(d0["rel"].mean()), "median": float(d0["rel"].median()),
        "share_up": float((d0["rel"] > 0).mean()),
        "mean_ex_top5pct": float(d0.loc[~top5, "rel"].mean()),
        "top5pct_mean": float(d0.loc[top5, "rel"].mean()),
        "skew": float(d0["rel"].skew()),
        "d9_mean": float(f.loc[f["dec"] == 9, "rel"].mean()), "d9_median": float(f.loc[f["dec"] == 9, "rel"].median()),
    }
    # 3. Beta: monthly decile means of raw-relative vs beta-residual returns.
    by = f.groupby(["eom", "dec"])
    raw, res = by["rel"].mean().unstack(), by["resid_beta"].mean().unstack()
    mkt = f.groupby("eom")["mkt"].first()
    up = mkt > mkt.median()
    out["beta_adjust"] = {
        "d0_raw": _mt(raw[0]), "d0_resid": _mt(res[0]), "d9_raw": _mt(raw[9]), "d9_resid": _mt(res[9]),
        "d0_raw_strong_mkt": float(raw[0][up].mean()), "d0_raw_weak_mkt": float(raw[0][~up].mean()),
        "d9_raw_strong_mkt": float(raw[9][up].mean()), "d9_raw_weak_mkt": float(raw[9][~up].mean()),
        "corr_d0_mkt": float(raw[0].corr(mkt)), "corr_d9_mkt": float(raw[9].corr(mkt)),
    }
    # 4. Opposite-direction tail: shorts split by their own p_up, longs by p_down.
    def split(sel, key):
        s = f[sel].copy()
        s["hi"] = s.groupby("eom")[key].transform(lambda x: x > x.median())
        m = s.groupby(["eom", "hi"])["rel"].mean().unstack()
        return {"high_opposite": _mt(m[True]), "low_opposite": _mt(m[False]), "diff": _mt(m[True] - m[False])}
    out["opposite_tail"] = {"shorts_by_p_up": split(f["dec"] <= 1, "r_up"), "longs_by_p_down": split(f["dec"] >= 8, "r_dn")}
    # 5. Size buckets inside the shortable pool: rank IC and short-half vs long-half.
    f["size"] = pd.cut(f["me"], [500, 2000, 10000, np.inf], labels=["0.5-2bn", "2-10bn", ">10bn"])
    sz = {}
    for b, d in f.groupby("size", observed=True):
        ic = d.groupby("eom").apply(lambda x: x["tail_" + COL].rank().corr(x["y"].rank()), include_groups=False)
        lo = d.groupby("eom").apply(lambda x: x.loc[x["tail_" + COL] <= x["tail_" + COL].quantile(0.2), "rel"].mean(), include_groups=False)
        hi = d.groupby("eom").apply(lambda x: x.loc[x["tail_" + COL] >= x["tail_" + COL].quantile(0.8), "rel"].mean(), include_groups=False)
        sz[str(b)] = {"names": int(d.groupby("eom").size().median()), "ic": _mt(ic), "bottom20": _mt(lo), "top20": _mt(hi)}
    out["size"] = sz
    # 6. Sector concentration of the short decile vs the pool.
    share = d0["sector"].value_counts(normalize=True)
    pool = f["sector"].value_counts(normalize=True)
    out["d0_sector_overweight"] = (share - pool).sort_values(ascending=False).head(4).round(3).to_dict()
    # 7. By year: short decile raw, beta-residual, and the opposite-tail split.
    yrs = {}
    for y in sorted(set(raw.index.year)):
        k = raw.index.year == y
        yrs[int(y)] = {"d0_raw": float(raw[0][k].mean()), "d0_resid": float(res[0][k].mean()),
                       "d9_raw": float(raw[9][k].mean()), "mkt": float(mkt[k].mean())}
    out["years"] = yrs
    # 8. Healthcare (GICS 35) inside the short decile vs the rest.
    hc = d0.assign(hc=d0["sector"] == "35").groupby(["eom", "hc"])["rel"].mean().unstack()
    out["d0_healthcare"] = {
        "share": float((d0["sector"] == "35").mean()),
        "healthcare": _mt(hc[True].dropna()), "other": _mt(hc[False].dropna()),
        "healthcare_median": float(d0.loc[d0["sector"] == "35", "rel"].median()),
        "healthcare_top5pct_mean": float(d0.loc[d0["sector"] == "35", "rel"].quantile(0.95)),
    }
    # 9. Short decile split by upside-risk proxies (terciles within the decile).
    upside = {}
    for c in ("ivol_capm_252d", "rmax1_21d", "iskew_capm_21d", "ret_1_0"):
        s = d0.copy()
        s["t3"] = s.groupby("eom")[c].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
        m = s.groupby(["eom", "t3"])["rel"].mean().unstack()
        upside[c] = {"low": _mt(m[0]), "mid": _mt(m[1]), "high": _mt(m[2]),
                     "median_low": float(s.loc[s["t3"] == 0, "rel"].median()),
                     "median_high": float(s.loc[s["t3"] == 2, "rel"].median())}
    out["d0_by_upside_proxy"] = upside
    # 10. Mechanism checks (diagnostic constructions, not candidates): the short
    # decile when ranked within sector, and when the score is divided by ivol.
    alt = {}
    for name, score in (
        ("within_sector", f.groupby(["eom", "sector"])["tail_" + COL].rank(pct=True)),
        ("score_over_ivol", f["tail_" + COL] / f["ivol_capm_252d"].clip(lower=0.005)),
    ):
        g2 = f.assign(s=score).groupby("eom")
        dec = g2["s"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
        m = f["rel"].groupby([f["eom"], dec]).mean().unstack()
        alt[name] = {"d0": _mt(m[0]), "d9": _mt(m[9]), "spread": _mt(m[9] - m[0])}
    out["mechanism_checks"] = alt
    return out


if __name__ == "__main__":
    rep = {w: diagnose(w) for w in (sys.argv[1:] or ["valid", "oos"])}
    (BASE / "short_diagnosis.json").write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=1, default=str))
