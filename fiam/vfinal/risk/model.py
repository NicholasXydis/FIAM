# The enhanced_faststress risk model rebuilt on our daily returns.

import json
import pickle

import numpy as np
import pandas as pd

from fiam.vfinal import config, data
from fiam.vfinal.risk import market
from fiam.vfinal.risk import parts as rp

# The five styles (forecast/targets.EXPOSURES less beta), panel columns.
STYLES = {"size": "me", "value": "be_me", "momentum": "ret_12_1", "profitability": "gp_at",
          "investment": "at_gr1"}  # fmt: skip
# Factor EWMA half-life (risk/model.FACTOR_HL) and the regression floor.
FACTOR_HL, MIN_NAMES = 84, 200
# Long-eligible: $5 and $2m ADV; short-eligible adds a $500m cap.
PRICE_MIN, ADV_MIN, SHORT_FLOOR = 5.0, 2e6, 500.0
SNAPS = config.CACHE / "snapshots"


# Within-month z-scores of ranks; missing at 0 (targets.zrank).
def zrank(frame: pd.DataFrame, col: str) -> pd.Series:
    r = frame.groupby("eom")[col].rank(pct=True) - 0.5
    return (r / r.groupby(frame["eom"]).transform("std")).fillna(0.0)


# Monthly exposures, sectors and eligibility for every panel row.
def exposures(first, last) -> pd.DataFrame:
    cols = ["me", "prc", "dolvol_126d", "gics", "beta_60m", *list(STYLES.values())[1:]]
    p = data.table("panel", list(dict.fromkeys(cols)), where={"eom": (first, last)})
    data.assert_public_by(p["first_close"], data.eom_session(p["eom"]).to_numpy(), "exposures")
    p["long_ok"] = (p["prc"].abs() >= PRICE_MIN) & (p["dolvol_126d"] >= ADV_MIN)
    p["short_ok"] = p["long_ok"] & (p["me"] >= SHORT_FLOOR)
    g = pd.to_numeric(p["gics"], errors="coerce")
    p["sector"] = (g // 1e6).astype("Int64").astype(str).where(g.notna())
    for name, col in STYLES.items():
        p[name] = zrank(p, col)
    keep = ["eom", "permno", "sector", *STYLES, "me", "dolvol_126d", "beta_60m", "long_ok",
            "short_ok"]  # fmt: skip
    return p[keep].sort_values(["eom", "permno"], ignore_index=True)


# Sector dummies plus styles for one month's liquid rows, by permno.
def design(month: pd.DataFrame, sectors: list) -> pd.DataFrame:
    m = month[month["long_ok"] & month["sector"].notna()]
    x = pd.get_dummies(m["sector"], prefix="s", dtype=float).join(m[list(STYLES)])
    x.index = m["permno"].to_numpy()
    return x.reindex(columns=[*sectors, *STYLES], fill_value=0.0)


# Constrained WLS: min ||sqrt(W)(y - Xf)||^2 s.t. c'f = 0, by KKT.
def constrained_wls(x: np.ndarray, y: np.ndarray, w: np.ndarray, c: np.ndarray) -> np.ndarray:
    sw = np.sqrt(w)
    xw = x * sw[:, None]
    k = x.shape[1]
    kkt = np.zeros((k + 1, k + 1))
    kkt[:k, :k], kkt[:k, k], kkt[k, :k] = xw.T @ xw, c, c
    sol, *_ = np.linalg.lstsq(kkt, np.concatenate([xw.T @ (y * sw), [0.0]]), rcond=None)
    return sol[:k]


# Daily factor returns and wide residuals (risk/factors.estimate).
def factor_returns(exp, excess, grid, sectors) -> tuple[pd.DataFrame, pd.DataFrame]:
    eoms = pd.DatetimeIndex(sorted(exp["eom"].unique()))
    by_month = {e: (design(m, sectors), m.set_index("permno")) for e, m in exp.groupby("eom")}
    cols = ["mkt", *sectors, *STYLES]
    col_pos = {p: j for j, p in enumerate(excess.columns)}
    y_all, g_all = excess.to_numpy(float), grid.reindex(columns=excess.columns).to_numpy(float)
    rows, resid = {}, np.full(excess.shape, np.nan)
    for k, day in enumerate(excess.index):
        # The exposure row in force: the last month end strictly before.
        e = eoms.searchsorted(day, side="left") - 1
        if e < 0:
            continue
        x_month, month = by_month[eoms[e]]
        names = x_month.index[x_month.index.isin(col_pos)]
        j = np.array([col_pos[p] for p in names])
        y, b = y_all[k, j], g_all[k, j]
        ok = np.isfinite(y) & np.isfinite(b)
        if ok.sum() < MIN_NAMES:
            continue
        x = np.column_stack([b[ok], x_month.loc[names].to_numpy(float)[ok]])
        kept = month.loc[names[ok]]
        caps = kept["me"].groupby(kept["sector"]).sum()
        c = np.zeros(x.shape[1])
        c[1 : 1 + len(sectors)] = [caps.get(s[2:], 0.0) for s in sectors]
        me = kept["me"].clip(lower=1.0).to_numpy(float)
        f = constrained_wls(x, y[ok], np.sqrt(me), c)
        rows[day] = f
        resid[k, j[ok]] = y[ok] - x @ f
    factors = pd.DataFrame.from_dict(rows, orient="index", columns=cols).sort_index()
    return factors, pd.DataFrame(resid, index=excess.index, columns=excess.columns)


# Specific variances at every month end: the race winner, shrunk.
def specific(resid: pd.DataFrame, exp: pd.DataFrame, eoms) -> tuple[pd.Series, dict]:
    race = rp.race(resid, eoms, config.RACE_YEARS)
    winner = race["winner"]
    if winner == "har_var":
        table = rp.har_forecast(rp.har_features(resid, eoms), rp.realised_next(resid, eoms))
        # Early eoms without a HAR fit fall back to EWMA-84 (stated).
        ew = rp.ewma_at(resid, eoms, 84)
        table = table.merge(ew, on=["eom", "permno"], how="outer")
        table["spec_var"] = table["har_var"].fillna(table["ewma84"])
    else:
        table = rp.ewma_at(resid, eoms, int(winner.removeprefix("ewma")))
        table = table.rename(columns={winner: "spec_var"})
    table = table[["eom", "permno", "spec_var"]].reset_index(drop=True)
    table["spec_var"] = rp.shrink_floor(table, "spec_var", exp[["eom", "permno", "sector"]])
    return table.set_index(["eom", "permno"])["spec_var"], race


# Every estimate the snapshots read, built once and cached.
def build() -> dict:
    first = pd.Timestamp(config.START) - pd.offsets.MonthEnd(1)
    exp = exposures(first, pd.Timestamp(config.LAST_EOM))
    names = sorted(exp.loc[exp["long_ok"], "permno"].unique())
    frames = market.build(names)
    days = frames["ret"].index
    mk = market.market(days)
    excess = frames["ret"].sub(mk["rf"], axis=0).clip(-market.CLIP, market.CLIP)
    rolled = rp.rolling_beta(excess, mk["mkt_rf"])
    betas = rp.hedge_betas(exp, rolled)
    grid = rp.hedge_beta_daily(exp, rolled)
    sectors = [f"s_{s}" for s in sorted(exp["sector"].dropna().unique())]
    factors, resid = factor_returns(exp, excess, grid, sectors)
    eoms = sorted(exp["eom"].unique())
    spec, race = specific(resid, exp, eoms)
    semi = rp.directional_at(resid, eoms).set_index(["eom", "permno"])
    hl = int(race["winner"].removeprefix("ewma")) if race["winner"].startswith("ewma") else 84
    paths = pd.DataFrame(
        {
            "lam_f": rp.vra_path(factors, FACTOR_HL),
            "lam_s": rp.vra_path(resid, hl).reindex(factors.index),
            "p_stress": rp.markov_state(mk["mkt_rf"]).reindex(factors.index),
        }
    )
    out = {"exp": exp, "betas": betas, "factors": factors, "resid": resid, "spec": spec,
           "semi": semi, "paths": paths, "excess": excess, "mkt_rf": mk["mkt_rf"]}  # fmt: skip
    with (config.CACHE / "risk.pkl").open("wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    (config.CACHE / "risk_race.json").write_text(json.dumps(race, indent=1))
    return out


# The cached estimates, building them on first use.
def load() -> dict:
    path = config.CACHE / "risk.pkl"
    if not path.exists():
        return build()
    with path.open("rb") as fh:
        return pickle.load(fh)


# A block-diagonal frame: a over its columns, b over the rest.
def block(a: pd.DataFrame, b: pd.DataFrame, cols: list) -> pd.DataFrame:
    out = pd.DataFrame(0.0, index=cols, columns=cols)
    out.loc[a.index, a.columns] = a.to_numpy()
    out.loc[b.index, b.columns] = b.to_numpy()
    return out


# The 2-stress mixture (1 - p) F + p stressed(F).
def mixture(cov: pd.DataFrame, p: float) -> pd.DataFrame:
    if not np.isfinite(p) or p <= 0:
        return cov
    return (1 - p) * cov + p * rp.stressed(cov)


# The last value of a daily path strictly before s0, else 1.
def before(path: pd.Series, s0) -> float:
    got = path[path.index < pd.Timestamp(s0)].dropna()
    return float(got.iloc[-1]) if len(got) else 1.0


# Welch-Dimson and beta_60m for the snapshot names (beta_candidates).
def beta_extra(m: dict, eom, names, b60: pd.Series) -> pd.DataFrame:
    ex = m["excess"]
    hist = ex.loc[ex.index <= pd.Timestamp(eom)].reindex(columns=names)
    mk = m["mkt_rf"].reindex(hist.index)
    welch = rp.welch(hist.iloc[-rp.WELCH_DAYS :], mk.iloc[-rp.WELCH_DAYS :])
    dims = rp.dimson(hist.iloc[-(rp.DIMSON_DAYS + 2) :], mk.iloc[-(rp.DIMSON_DAYS + 2) :])
    wd = pd.concat([welch, dims], axis=1).mean(axis=1, skipna=False)
    out = pd.DataFrame({"welch_dimson": wd.reindex(names), "beta_60m": b60.reindex(names)})
    return out.fillna(out.median())


# One formation's snapshot: B, F (H sessions), F1, d, betas, month.
def snapshot(m: dict, eom, horizon: int, at=None) -> dict:
    eom = pd.Timestamp(eom)
    exp = m["exp"]
    month = exp[exp["eom"] == eom].set_index("permno")
    sectors = [f"s_{s}" for s in sorted(exp["sector"].dropna().unique())]
    x = design(month.reset_index(), sectors)
    b = m["betas"][m["betas"]["eom"] == eom].set_index("permno")["beta_hedge"]
    names = x.index.intersection(b.index)
    B = x.loc[names].copy()
    B.insert(0, "mkt", b.loc[names].to_numpy())
    fac = m["factors"]
    # A mid-month formation reads daily estimates through its own close.
    s0 = fac.index[fac.index > pd.Timestamp(at if at is not None else eom)][0]
    F = rp.factor_cov_horizon(fac, s0, FACTOR_HL, horizon)
    F1 = rp.factor_cov(fac, s0, FACTOR_HL)
    Fd = rp.factor_cov(fac, s0, FACTOR_HL, newey=False)
    d0 = m["spec"].loc[eom].reindex(names)
    d0 = d0.fillna(d0.median())
    semi = m["semi"].loc[eom].reindex(names)
    lf, ls = before(m["paths"]["lam_f"], s0), before(m["paths"]["lam_s"], s0)
    F, F1, Fd, d = F * lf, F1 * lf, Fd * lf, d0 * ls
    # Directional variances as model.snapshot, then the regime scale.
    d_down = np.maximum(semi["down_var"].fillna(d0), 0.5 * d0) * ls
    d_up = np.maximum(semi["up_var"].fillna(d0), 0.5 * d0) * ls
    load, share = rp.residual_factors(m["resid"], s0, B.index)
    keep = 1 - share.reindex(d.index).fillna(0.0)
    d, d_down, d_up = d * keep, d_down * keep, d_up * keep
    B = pd.concat([B, load], axis=1)
    cols = list(B.columns)
    eye = pd.DataFrame(np.eye(rp.PCA_K), index=load.columns, columns=load.columns)
    F = block(F, eye * horizon * ls, cols)
    F1, Fd = block(F1, eye * ls, cols), block(Fd, eye * ls, cols)
    p = before(m["paths"]["p_stress"], s0)
    F, F1, Fd = mixture(F, p), mixture(F1, p), mixture(Fd, p)
    extra = beta_extra(m, eom, names, month["beta_60m"])
    return {"eom": eom, "s0": s0, "horizon": horizon, "B": B, "F": F, "F1": F1, "F_daily": Fd,
            "d": d, "d_down": np.maximum(d_down, 0.5 * d), "d_up": np.maximum(d_up, 0.5 * d),
            "beta": b.loc[names], "month": month.loc[names], "beta_extra": extra,
            "lam_f": lf, "lam_s": ls, "stress_p": p}  # fmt: skip


# A snapshot from the cache, or built and cached (holdings-free).
def cached_snapshot(m: dict, eom, horizon: int, at=None) -> dict:
    tag = "" if at is None else f"_at{pd.Timestamp(at):%Y%m%d}"
    path = SNAPS / f"{pd.Timestamp(eom):%Y%m%d}_h{horizon}{tag}.pkl"
    if path.exists():
        with path.open("rb") as fh:
            return pickle.load(fh)
    snap = snapshot(m, eom, horizon, at)
    SNAPS.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(snap, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return snap


# Annualised predicted vol of weights w over the snapshot horizon.
def vol(snap: dict, w: pd.Series) -> float:
    B = snap["B"]
    ww = w.reindex(B.index).fillna(0.0).to_numpy(float)
    bw = B.to_numpy(float).T @ ww
    Fm = snap["F"].reindex(index=B.columns, columns=B.columns).to_numpy()
    total = float(bw @ Fm @ bw + (ww**2 * snap["d"].to_numpy()).sum() * snap["horizon"])
    return float(np.sqrt(total * 252 / snap["horizon"]))
