# Walk-forward 2017-2020 books: alpha, risk and the optimiser.

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4 import data, gates, sources
from fiam.v4.construct import costs, crowding, inputs, jumps, optimizer, risk, screens

OUT = Path(__file__).resolve().parents[3] / "out" / "v4" / "construct"
# The first book needs 24 months of factor returns (PLAN §8.4).
FIRST, LAST = pd.Timestamp("2017-01-31"), pd.Timestamp("2020-11-30")
# The confidence map's multipliers by cross-model spread tercile.
CONFIDENCE, CONFIDENCE_MONTHS = (1.0, 0.9, 0.75), 12
# A missing beta takes the month's median; a missing ADV the 5th pct.
ADV_FLOOR_PCT = 0.05
# What the engine's hooks read from each formation's frame.
FRAME_COLS = ["prc", "half_spread", "sigma_d", "adv_cost", "borrow", "welch", "dimson"]
# The crash-day cap's history starts here (lever A2).
CAP_FROM = pd.Timestamp("2000-01-03")


# Lever A2 at each session: 2 / (1 + the largest two-day rise before).
def crash_caps(end) -> pd.Series:
    days = data.sessions(CAP_FROM, pd.Timestamp(end))
    r = data.market_daily(days)
    two = ((1 + r) * (1 + r.shift(1)) - 1).cummax().ffill()
    return 2.0 / (1.0 + two.shift(1))


# Lever A2's C_t at one decision close T.
def crash_cap(T) -> float:
    return float(crash_caps(T).iloc[-1])


# The walk-forward forecasts the models wrote at step 6's commit.
FORECASTS = gates.ROOT / "out" / "v4" / "forecast" / "forecasts_9f47207c568b.parquet"


# The pinned forecasts file, never "the latest one".
def forecasts() -> pd.DataFrame:
    return pd.read_parquet(FORECASTS)


# The alpha scale: pooled IC of z with the one-month residual label.
def alpha_scale(f: pd.DataFrame) -> float:
    lab = sources.read("labels", ["resid_rank_universe"], purpose="label")
    lab = lab[lab["horizon"] == 1][["permno", "eom", "resid_rank_universe"]]
    both = f.merge(lab, on=["permno", "eom"]).dropna(subset=["z", "resid_rank_universe"])
    ic = float(both["z"].rank().corr(both["resid_rank_universe"].rank()))
    assert ic > 0, "the alpha scale must be positive (PLAN §8.2)"
    return ic


# Universe frames 2015 on, for the factor returns; cached by its styles.
def factor_returns() -> pd.DataFrame:
    key = json.dumps([inputs.STYLES, inputs.CAPPED, "2015-01-31", str(LAST)])
    path = OUT / f"factor_returns_{hashlib.sha256(key.encode()).hexdigest()[:12]}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    frames = {e: inputs.formation(e) for e in data.month_ends("2015-01-31", LAST)}
    out = risk.factor_returns(frames)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path)
    return out


# Each name's confidence multiplier from past cross-model spreads.
def confidence(f: pd.DataFrame, eom) -> pd.Series:
    now = f[f["eom"] == eom].set_index("permno")["spread"]
    past = f[f["eom"] < eom]
    if past["eom"].nunique() < CONFIDENCE_MONTHS:
        return pd.Series(1.0, index=now.index)
    lo, hi = past["spread"].quantile([1 / 3, 2 / 3])
    return pd.Series(np.select([now <= lo, now <= hi], CONFIDENCE[:2], CONFIDENCE[2]),
                     index=now.index)  # fmt: skip


# Alpha aligned with every exposure the optimiser holds at zero (C1).
def align(alpha: pd.Series, x: pd.DataFrame, neutral=()) -> pd.Series:
    design = pd.get_dummies(x["sector"], dtype=float)
    design = design.join(x[[*inputs.NEUTRAL, *neutral, "welch", "dimson", "beta_60m"]])
    coef, *_ = np.linalg.lstsq(design.to_numpy(), alpha.to_numpy(), rcond=None)
    return alpha - design.to_numpy() @ coef


# One formation's frame with risk, cost inputs, screens and alpha.
def month(eom, prev, f, fr, scale: float, returns, history=None, holdings=None, z="z",
          neutral=(), late=None):  # fmt: skip
    held_long, held_short = prev.index[prev > 0], prev.index[prev < 0]
    x = inputs.formation(eom, held_long, held_short)
    T = x["T"].iloc[0]
    # Betas on CRSP total returns, so a spin-off is no crash (Step 7 rules).
    x = x.join(risk.total_betas(returns, T, x.index))
    # Screens off: no name is flagged, so every column is always there.
    x["squeezed"] = False if history is None else screens.squeeze(x, T, history.cuts(T))["squeezed"]
    # The crowding level too, for step 8's card; the flag as before.
    c = None if holdings is None else crowding.crowding(holdings, T).reindex(x.index)
    x["crowding"] = 0.0 if c is None else c.fillna(0.0)
    x["crowded"] = False if c is None else crowding.crowded(x.index, holdings, T, c)
    for b in ("welch", "dimson", "beta_60m"):
        x[b] = x[b].fillna(x[b].median())
    # Jumps on returns known at T: after 2025 the dsf's raw ones (23 (m)).
    known = returns.loc[returns.index <= T].iloc[-(jumps.YEAR + jumps.WINDOW + 1) :]
    if late is not None and not late.empty:
        raw = late.loc[(late.index > data.CRSP_END) & (late.index <= T)]
        known = pd.concat([known.loc[known.index <= data.CRSP_END], raw])
    x = x.join(jumps.flags(jumps.counts(known, data.market_daily(known.index), T, x.index)))
    cov = risk.covariance(fr, eom)
    loadings = risk.design(x).reindex(columns=cov.columns, fill_value=0.0)
    vol = risk.har(returns, x["T"].iloc[0]).reindex(x.index)
    vol = vol.fillna(vol.median())
    spec = risk.specific(vol, loadings, cov)
    floor = x["dolvol_126d"].quantile(ADV_FLOOR_PCT)
    x = x.assign(sigma_d=vol / np.sqrt(21), adv_cost=x["dolvol_126d"].fillna(floor))
    x["half_spread"] = costs.half_spread(x)
    z = f[f["eom"] == eom].set_index("permno")[z].reindex(x.index).fillna(0.0)
    alpha = scale * np.sqrt(spec) * z * confidence(f, eom).reindex(x.index).fillna(1.0)
    return x, align(alpha, x, neutral), loadings, cov, spec


# Lever A4: the drifted book plus r of the move, inside the rules.
def partial(w: pd.Series, prev: pd.Series, x: pd.DataFrame, s, alpha) -> pd.Series:
    if s.speed >= 1 or prev.empty:
        return w
    names, gross = x.index, float(w.abs().sum())
    move = w.reindex(names).fillna(0.0) - prev.reindex(names).fillna(0.0)
    blend = prev.reindex(names).fillna(0.0) + s.speed * move
    # Every rule enforced on the blend (reading 12); else scaled and capped.
    out = optimizer.project(blend, x, alpha, prev, replace(s, gross=gross))
    if out is not None:
        return out
    blend = blend[blend.abs() >= optimizer.MIN_WEIGHT]
    blend = blend[blend.abs().nlargest(s.names_max).index]
    long_cap, short_cap = optimizer.caps(x["adv_cost"].reindex(blend.index), s.nav)
    cap = np.where(blend > 0, long_cap, short_cap)
    return optimizer.rescale(blend, gross).clip(-cap, cap)


# Drift: weights carried from the trade day to the next formation's T.
def drift(w: pd.Series, returns: pd.DataFrame, start, end) -> pd.Series:
    window = returns.loc[(returns.index > start) & (returns.index <= end), w.index]
    growth = (1 + window.fillna(0.0)).prod()
    nav = 1 + float((w * (growth - 1)).sum())
    return w * growth / nav


# What every build reads once: forecasts, risk history and screens.
class Context:
    # Loaded once and shared by every build of a derivation.
    def __init__(self, months=None, screened: bool = True, z: str = "z", neutral=()):
        self.months = data.month_ends(FIRST, LAST) if months is None else months
        # The forecast column (z, or SYY-10 alone) and styles held at 0.
        self.z, self.neutral = z, tuple(neutral)
        self.f, self.fr = forecasts(), factor_returns()
        self.scale = alpha_scale(self.f)
        ids = sorted(self.f["permno"].unique())
        end = self.months[-1] + pd.offsets.MonthEnd(1)
        self.returns = risk.daily(ids, "2014-10-01", end)
        # 2026's raw returns, for days before their month's δ is known.
        self.late = risk.late(ids, end)
        last = self.months[-1]
        self.history = screens.History(last) if screened else None
        first = self.months[0] - pd.DateOffset(months=18)
        self.holdings = crowding.Holdings(first, last) if screened else None
        ends = data.eom_session(self.months)
        caps = crash_caps(ends.iloc[-1])
        self.caps = {e: float(caps.loc[T]) for e, T in zip(self.months, ends)}
        # The reader's cache holds every query; nothing above is read again.
        data._CACHE.clear()


# Books over every formation at given settings; one row a formation.
def build(settings_at, ctx: "Context", log=None, diagnostics: bool = False, frames=None) -> dict:
    f, fr, scale, returns = ctx.f, ctx.fr, ctx.scale, ctx.returns
    prev, books, info = pd.Series(dtype=float), {}, []
    for k, eom in enumerate(ctx.months):
        x, alpha, loadings, cov, spec = month(eom, prev, f, fr, scale, returns, ctx.history,
                                              ctx.holdings, ctx.z, ctx.neutral,
                                              ctx.late)  # fmt: skip
        s = settings_at(eom, x, ctx.caps[eom])
        # The ridge acts on alpha in z units: alpha over scale x median vol.
        s = replace(s, norm=scale * float(np.sqrt(spec).median()))
        chol = np.linalg.cholesky(cov.to_numpy() + 1e-12 * np.eye(len(cov)))
        w, step, used = optimizer.optimise(x, alpha, loadings, chol, spec.to_numpy(),
                                           prev, s, initial=(k == 0))  # fmt: skip
        # No answer: the drifted book is held as it is, never blended.
        if w is None:
            w, step = prev, "held"
        else:
            w = partial(w, prev, x, used, alpha)
        books[eom] = w
        # The engine's per-name inputs for this formation, kept if asked.
        if frames is not None:
            frames[eom] = (x[FRAME_COLS].copy(), ctx.caps[eom])
        trade = (w.reindex(x.index).fillna(0.0) - prev.reindex(x.index).fillna(0.0)).to_numpy()
        cost = costs.share_of_nav(trade, x, s.nav)
        f_w = loadings.to_numpy().T @ w.reindex(x.index).fillna(0.0).to_numpy()
        risk_w = float(
            f_w @ cov.to_numpy() @ f_w + (spec * w.reindex(x.index).fillna(0.0) ** 2).sum()
        )
        row = {"eom": eom, "names": len(w), "step": step, "gross": float(w.abs().sum()),
               "norm": s.norm, "risk": risk_w, "w2": float((w**2).sum()),
               "cost": cost, "turnover": float(np.abs(trade).sum() / 2), "cap": ctx.caps[eom],
               "squeezed": int(x["squeezed"].sum()),
               "crowded": int(x["crowded"].sum())}  # fmt: skip
        if diagnostics and len(w):
            row["share_ours"] = risk.factor_share(w, loadings, cov.to_numpy(), spec)
            ffl, ffc, ffs = risk.ff_model(returns, x["T"].iloc[0], list(w.index))
            row["share_ff"] = risk.factor_share(w, ffl, ffc, ffs)
            row["tc"] = risk.transfer(alpha, w, loadings, cov, spec)
        info.append(row)  # fmt: skip
        T = x["T"].iloc[0]
        nxt = data.eom_session([eom + pd.offsets.MonthEnd(1)]).iloc[0]
        prev = drift(w, returns, data.shift([T], 1).iloc[0], nxt)
        # Each month's reads are its own: freed before the next month.
        data._CACHE.clear()
    if log is not None:
        log["scale"], log["months"] = scale, info
    return books


# Saves a run's books and its log beside each other.
def save(name: str, books: dict, log: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [w.rename("weight").rename_axis("permno").reset_index().assign(eom=e)
            for e, w in books.items()]  # fmt: skip
    pd.concat(rows).to_parquet(OUT / f"books_{name}.parquet", index=False)
    (OUT / f"books_{name}.json").write_text(json.dumps(log, indent=1, default=str))
