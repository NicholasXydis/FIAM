# Judges the rolling E-LASSO runs (D11): mean model vs the left/right-tail score.
#
# Candidates (registered in D11 before any 2021+ number was computed):
#   mean  - Elasso_<w> of the `ret` run (D6);
#   tail  - Elasso_<w>(up) - Elasso_<w>(down), the QUARCC-Black dual-head score.
# Each is judged on the monthly excess return `ret_exc_lead1m` by formation eom.
# Legs: decile returns are equal-weight and relative to the month's mean, so a
# leg is "right" when the long decile is above and the short decile below it.
# Shorts are also judged inside the >= $500m pool the mandate lets us short.
#
# Usage: python -m fiam.v4b.elasso.rolling_judge valid|oos

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.elasso.rolling import BASE

OLD = BASE.parent / "run"
WINDOWS = {
    "valid": ("2016-12-31", "2020-11-30"),
    "oos": ("2020-12-31", "2026-07-31"),
}
SHORT_FLOOR = 500.0


def _load(kind: str, run: Path | None = None) -> pd.DataFrame:
    f = pd.read_parquet((run or BASE / kind / "run") / "forecastElasso.parquet")
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    return f


# Scores by eom/permno with the realised label and the short-floor flag.
def scores(window: str) -> pd.DataFrame:
    lo, hi = (pd.Timestamp(x) for x in WINDOWS[window])
    m, up, dn = (_load(k) for k in ("ret", "up", "down"))
    key = ["eom", "permno"]
    out = m[key + ["me", "ret"]].rename(columns={"ret": "y"})
    out["y"] = out["y"] / 100.0
    for w in ("MaInf", "Ma1"):
        out[f"mean_{w}"] = m[w].to_numpy()
        t = up[key + [w]].merge(dn[key + [w]], on=key, suffixes=("_up", "_dn"))
        out = out.merge(t.assign(**{f"tail_{w}": t[f"{w}_up"] - t[f"{w}_dn"]})[key + [f"tail_{w}"]], on=key)
        out = out.merge(up[key + [w]].rename(columns={w: f"up_{w}"}), on=key)
        out = out.merge(dn[key + [w]].rename(columns={w: f"down_{w}"}), on=key)
    out = out[out["eom"].between(lo, hi)]
    # me in the authors' frame is eom t-1 market equity in USD m.
    out["short_ok"] = out["me"] >= SHORT_FLOOR
    return out.reset_index(drop=True)


def _t(s: pd.Series) -> dict:
    s = s.dropna()
    return {"mean": float(s.mean()), "t": float(s.mean() / s.std() * np.sqrt(len(s))), "n": int(len(s))}


def _ic(f: pd.DataFrame, col: str) -> pd.Series:
    return f.groupby("eom").apply(lambda g: g[col].rank().corr(g["y"].rank()), include_groups=False)


# Decile returns relative to the month's equal-weight mean, by eom.
def _deciles(f: pd.DataFrame, col: str) -> pd.DataFrame:
    d = f.groupby("eom")[col].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    rel = f["y"] - f.groupby("eom")["y"].transform("mean")
    return rel.groupby([f["eom"], d]).mean().unstack()


def judge(f: pd.DataFrame, col: str) -> dict:
    ic = _ic(f, col)
    dec = _deciles(f, col)
    s = f[f["short_ok"]]
    sdec = _deciles(s, col)
    spread = dec[9] - dec[0]
    years = {}
    for y, g in spread.groupby(spread.index.year):
        years[int(y)] = {
            "ic": float(ic[ic.index.year == y].mean()),
            "spread": float(g.mean()),
            "long_d9": float(dec[9][dec.index.year == y].mean()),
            "short_d0_500m": float(sdec[0][sdec.index.year == y].mean()),
        }
    return {
        "ic": _t(ic),
        "spread_d9_d0": _t(spread),
        "long_d9": _t(dec[9]),
        "long_d8": _t(dec[8]),
        "short_d0": _t(dec[0]),
        "short_d1": _t(dec[1]),
        "short_d0_500m": _t(sdec[0]),
        "short_d1_500m": _t(sdec[1]),
        "spread_500m": _t(sdec[9] - sdec[0]),
        "deciles": {int(k): float(v) for k, v in dec.mean().items()},
        "years": years,
    }


# The rolling `ret` run must reproduce the original pre-2021 forecasts.
def reproduce() -> dict:
    new, old = _load("ret"), _load("ret", OLD)
    key = ["eom", "permno"]
    j = old[key + ["MaInf", "Ma1"]].merge(new[key + ["MaInf", "Ma1"]], on=key, suffixes=("_old", "_new"))
    j = j[j["eom"] <= pd.Timestamp("2020-11-30")]
    return {
        "rows": int(len(j)),
        "old_rows": int((old["eom"] <= pd.Timestamp("2020-11-30")).sum()),
        "max_abs_MaInf": float((j["MaInf_old"] - j["MaInf_new"]).abs().max()),
        "max_abs_Ma1": float((j["Ma1_old"] - j["Ma1_new"]).abs().max()),
    }


def main(window: str) -> dict:
    f = scores(window)
    cols = [c for c in f.columns if c.split("_")[0] in ("mean", "tail", "up", "down")]
    rep = {"window": WINDOWS[window], "months": int(f["eom"].nunique()), "rows": int(len(f))}
    if window == "valid":
        rep["reproduce"] = reproduce()
    # The down model ranks by probability of a loss, so it is judged negated.
    rep["scores"] = {c: judge(f.assign(**{c: -f[c]}) if c.startswith("down") else f, c) for c in cols}
    (BASE / f"judge_{window}.json").write_text(json.dumps(rep, indent=2))
    return rep


if __name__ == "__main__":
    r = main(sys.argv[1])
    print(json.dumps({k: v for k, v in r.items() if k != "scores"}, indent=2))
    for c, v in r["scores"].items():
        print(f"{c:12s} IC {v['ic']['mean']:+.4f} (t {v['ic']['t']:+.2f})  spread {v['spread_d9_d0']['mean']*100:+.2f}% "
              f"(t {v['spread_d9_d0']['t']:+.2f})  D9 {v['long_d9']['mean']*100:+.2f}% (t {v['long_d9']['t']:+.2f})  "
              f"D0 {v['short_d0']['mean']*100:+.2f}% (t {v['short_d0']['t']:+.2f})  D0>=500m {v['short_d0_500m']['mean']*100:+.2f}% "
              f"(t {v['short_d0_500m']['t']:+.2f})  D1>=500m {v['short_d1_500m']['mean']*100:+.2f}%  spread500 {v['spread_500m']['mean']*100:+.2f}% (t {v['spread_500m']['t']:+.2f})")
