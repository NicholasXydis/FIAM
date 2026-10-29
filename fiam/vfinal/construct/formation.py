# One review's optimiser inputs, all known by that close.

import numpy as np
import pandas as pd

from fiam.vfinal import config, data
from fiam.vfinal.construct import inputs as construct
from fiam.vfinal.construct.optimize import Formation
from fiam.vfinal.risk import market
from fiam.vfinal.risk import model as risk
from fiam.vfinal.signals import short_interest

# The horizon the forecaster's alpha is quoted over (forecaster.py).
REFERENCE_DAYS = 21


# Every formation's month ends from 2020-12 to 2026-07.
def eoms() -> list:
    return list(data.month_ends(config.FIRST_EOM, config.LAST_EOM))


# The first session on or after the 15th of each eom's next month.
def mid_months(ends) -> dict:
    out = {}
    for e in ends:
        days = data.sessions(e + pd.Timedelta(days=15), e + pd.offsets.MonthEnd(1))
        if len(days) and days[0] <= pd.Timestamp(config.END):
            out[e] = days[0]
    return out


# el_plus at each eom as mu: centred on the median, times rho.
def mu21(p: config.Policy) -> pd.Series:
    path = config.FORECAST / "elasso_rho.parquet"
    h = pd.read_parquet(path, columns=["permno", "eom", "mainf", "rho", "z"])
    h["eom"] = pd.to_datetime(h["eom"]) + pd.offsets.MonthEnd(0)
    raw = p.forecaster_scale * h["mainf"] / 100.0
    mu = (raw - raw.groupby(h["eom"]).transform("median")) * h["rho"]
    return h[["permno", "eom"]].assign(mu=mu)


# The mid-month refreshed forecast as mu, by T.
def mid_mu(p: config.Policy) -> pd.Series:
    f = pd.read_parquet(config.FORECAST / "mid_month.parquet")
    raw = p.forecaster_scale * f["mainf"] / 100.0
    mu = (raw - raw.groupby(f["T"]).transform("median")) * f["rho"]
    return f[["T", "permno"]].assign(mu=mu).set_index(["T", "permno"])["mu"]


# Share of the 21-session alpha earned over a hold (forecaster.py).
def horizon_scale(hold: float, kappa: float) -> float:
    if kappa <= 0:
        return hold / REFERENCE_DAYS
    return float((1 - np.exp(-kappa * hold)) / (1 - np.exp(-kappa * REFERENCE_DAYS)))


# Share of the 147 characteristics present, by eom and permno.
def coverage(ends) -> dict:
    path = config.CACHE / "coverage.parquet"
    if path.exists():
        f = pd.read_parquet(path)
    else:
        chars = pd.read_csv(config.CHARS)["variable"].tolist()
        rows = []
        for eom in ends:
            p = data.table("panel", chars, where={"eom": (eom, eom)}).set_index("permno")
            share = p[chars].notna().mean(axis=1).to_numpy()
            rows.append(pd.DataFrame({"eom": eom, "permno": p.index, "share": share}))
            data._CACHE.clear()
        f = pd.concat(rows, ignore_index=True)
        f.to_parquet(path, index=False)
    return {e: g.set_index("permno")["share"] for e, g in f.groupby("eom")}


# The inputs shared by every formation of one book.
class World:
    # Risk estimates, daily frames, borrow; forecasts when it solves.
    def __init__(self, policy: config.Policy, solves: bool):
        self.p, self.step = policy, config.Step()
        self.m = risk.load()
        self.frames = market.load()
        self.eoms = eoms()
        self.signal = {e: data.eom_session([e]).iloc[0] for e in self.eoms}
        si = short_interest.build(self.eoms)
        self.short_ratio = si.set_index(["eom", "permno"])["value"]
        # Review closes: each eom's, and the mid-month's.
        self.reviews = {T: (e, None) for e, T in self.signal.items()}
        self.reviews |= {T: (e, T) for e, T in mid_months(self.eoms).items()}
        self.mu = self.mu_mid = self.coverage = None
        if solves:
            mu = mu21(self.p)
            self.mu = mu[mu["eom"].isin(self.eoms)].set_index(["eom", "permno"])["mu"]
            self.coverage = coverage(self.eoms)
            self.mu_mid = mid_mu(self.p)

    # Sessions from this review's close to the next review's close.
    def horizon(self, eom, at=None) -> int:
        start = at if at is not None else self.signal[eom]
        later = [T for T in self.reviews if T > start]
        nxt = min(later) if later else data.eom_session([pd.Timestamp(config.END)]).iloc[0]
        return len(data.sessions(start, nxt)) - 1

    # Annual borrow by short-interest tier; no report is the cheapest.
    def borrow(self, eom, names) -> pd.Series:
        try:
            ratio = self.short_ratio.loc[eom].reindex(names)
        except KeyError:
            ratio = pd.Series(np.nan, index=names)
        return construct.borrow_tier(ratio.fillna(0.0))

    # Mid-month: a short needs its cap at that close (eom cap, grown).
    def short_floor_now(self, month: pd.DataFrame, eom, at) -> pd.DataFrame:
        ret = self.frames["ret"]
        span = ret.loc[(ret.index > self.signal[eom]) & (ret.index <= pd.Timestamp(at))]
        growth = (1 + span.reindex(columns=month.index).fillna(0.0)).prod()
        month = month.copy()
        month["short_ok"] &= (month["me"] * growth.to_numpy()) >= risk.SHORT_FLOOR
        return month

    # The formation at eom (or mid-month at) from the book at its close.
    def formation(self, eom, w_pre: pd.Series, nav: float, at=None) -> Formation:
        eom = pd.Timestamp(eom)
        H = self.horizon(eom, at)
        snap = risk.cached_snapshot(self.m, eom, H, at)
        T = self.signal[eom] if at is None else at
        mu = self.mu_mid.loc[T] if at is not None else self.mu.loc[eom]
        mu = mu * horizon_scale(H, self.p.forecaster_kappa)
        if at is not None:
            snap = snap | {"month": self.short_floor_now(snap["month"], eom, at)}
        row = {k: self.frames[k].loc[T] for k in ("adv", "sigma", "half_spread", "price")}
        names = snap["B"].index
        return Formation(eom=eom, mu=mu, snap=snap, adv=row["adv"], half_spread=row["half_spread"],
                         borrow=self.borrow(eom, names), coverage=self.coverage.get(eom),
                         sigma=row["sigma"], price=row["price"], w_pre=w_pre, nav=nav,
                         horizon=H)  # fmt: skip
