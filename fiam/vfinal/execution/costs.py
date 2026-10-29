# The per-child-order cost law, borrow tiers and the flat variant.

import numpy as np
import pandas as pd

from fiam.vfinal import config, daily_book
from fiam.vfinal.construct import optimize

# Sessions in a year, for daily accruals of yearly rates.
YEAR = 252


# The daily inputs, each day reading the previous session's row.
class Law:
    # The cached daily frames and the formations' borrow schedule.
    def __init__(self, frames: dict, world, impact_y: float = 1.0):
        self.f, self.world, self.y = frames, world, impact_y
        self.days = frames["adv"].index

    # The previous session's row of one frame for these names.
    def known(self, name: str, d, names) -> pd.Series:
        pos = self.days.searchsorted(pd.Timestamp(d), side="left") - 1
        return self.f[name].iloc[max(pos, 0)].reindex(names)

    # A name with no input pays dear values, never zero.
    def inputs(self, d, names) -> pd.DataFrame:
        x = pd.DataFrame({k: self.known(k, d, names)
                          for k in ("adv", "sigma", "half_spread", "price")})  # fmt: skip
        row = self.known("adv", d, self.f["adv"].columns)
        x["adv"] = x["adv"].where(x["adv"] > 0).fillna(float(row.quantile(0.05)))
        return x.fillna({"sigma": 0.02, "half_spread": 0.005})

    # A day's costs per name: spread, child-order impact, exact fees.
    def costs(self, d, moved: pd.Series, whole: pd.Series | None = None) -> pd.Series:
        x = self.inputs(d, moved.index)
        q = moved.abs()
        size = q if whole is None else whole.reindex(q.index).fillna(q).clip(lower=q)
        impact = self.y * x["sigma"] * q * np.sqrt(size / x["adv"])
        fees = [optimize.order_fee(v, px, v < 0) for v, px in zip(moved, x["price"])]
        return (x["half_spread"] * q + impact + pd.Series(fees, index=q.index)).fillna(0.0)

    # The tier schedule of the last formation eom before the day.
    def rate(self, d, names) -> pd.Series:
        ends = [e for e in self.world.eoms if e < pd.Timestamp(d)]
        return self.world.borrow(ends[-1] if ends else self.world.eoms[0], names)

    # A session's borrow on each short's value at its tier.
    def borrow(self, d, shorts: pd.Series) -> pd.Series:
        return shorts * self.rate(d, shorts.index) / YEAR


# Each day's costs again with impact on each formation's whole trade.
def whole_trade(daily: pd.DataFrame, trades: pd.DataFrame, law: Law) -> pd.Series:
    t = trades.assign(q=trades["dollars"].abs())
    t["whole"] = t.groupby(["formed", "permno"])["q"].transform("sum")
    out = {}
    for d, g in t.groupby("date"):
        moved = g.groupby("permno")["dollars"].sum()
        out[d] = float(law.costs(d, moved, g.groupby("permno")["whole"].max()).sum())
    return pd.Series(out).reindex(daily.index).fillna(0.0)


# Flat borrow: 0.5% a year at $10bn and up, 5% for the rest.
def flat_borrow(daily: pd.DataFrame, positions: pd.DataFrame) -> pd.Series:
    shorts = positions[positions["value"] < 0]
    m = daily_book.Market(sorted(shorts["permno"].unique()), daily.index)
    cap = np.array([m.cap_at(int(p), d) for p, d in zip(shorts["permno"], shorts["date"])])
    rate = np.where(cap >= config.FLAT_LARGE_MUSD, config.FLAT_CHEAP, config.FLAT_DEAR)
    # Borrow accrues on the shorts held at the previous close.
    fee = -shorts["value"].to_numpy() * rate / YEAR
    by_day = pd.Series(fee, index=shorts["date"].to_numpy()).groupby(level=0).sum()
    days = daily.index
    return by_day.reindex(days).shift(1).fillna(0.0)


# The flat alternative's days, and its re-cost checks.
def flat(daily, positions, trades, law: Law) -> tuple[pd.DataFrame, dict]:
    by_day = {d: float(law.costs(d, g.groupby("permno")["dollars"].sum()).sum())
              for d, g in trades.groupby("date")}  # fmt: skip
    child = pd.Series(by_day).reindex(daily.index).fillna(0.0)
    whole = whole_trade(daily, trades, law)
    borrow = flat_borrow(daily, positions)
    extra = (whole - daily["cost"]) + (borrow - daily["borrow"])
    alt = daily.assign(cost=whole, borrow=borrow)
    # The extra cost compounds: each day's NAV path is rebuilt.
    ret = daily["ret"] - (extra / daily["nav"].shift(1)).fillna(0.0)
    alt["ret"] = ret
    alt["nav"] = daily["nav"].iloc[0] * (1 + ret).cumprod()
    check = {"child_recomputed_over_booked": float(child.sum() / daily["cost"].sum()),
             "whole_over_booked": float(whole.sum() / daily["cost"].sum()),
             "flat_borrow_over_booked": float(borrow.sum() / daily["borrow"].sum())}  # fmt: skip
    return alt, check
