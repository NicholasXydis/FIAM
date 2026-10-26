# Leg-level read of a Nautilus run (D12): long and short leg returns, realised
# daily and monthly beta, cost lines as % NAV a year, and compliance counts.
#
# Leg return on day t = sum of w_{t-1} * r_t over that leg's names (contribution
# to NAV, before costs), with w the executed end-of-day weight. Beta is the
# OLS slope of the strategy's daily (or monthly compounded) excess return on
# the S&P 500's, the case's §9.1 exhibit.

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine import inputs

YEAR = 252


def _t(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def _slope(y: pd.Series, x: pd.Series) -> float:
    b = pd.concat([y, x], axis=1).dropna()
    return float(np.polyfit(b.iloc[:, 1], b.iloc[:, 0], 1)[0])


def report(run_dir: Path, daily_path: Path | None = None) -> dict:
    h = pd.read_parquet(run_dir / "daily_holdings.parquet", columns=["date", "permno", "w"])
    led = pd.read_parquet(run_dir / "daily_nav.parquet")
    if "date" in led:
        led = led.set_index("date")
    days = pd.DatetimeIndex(sorted(h["date"].unique()))
    d = inputs.daily(days[0], blind_until=days[-1], path=daily_path)
    r = d.pivot(index="date", columns="permno", values="total_return").reindex(days)
    w = h.pivot_table(index="date", columns="permno", values="w", aggfunc="sum").reindex(days).fillna(0.0)
    prev = w.shift(1).reindex(columns=r.columns.union(w.columns)).fillna(0.0)
    rr = r.reindex(columns=prev.columns).fillna(0.0)
    legs = pd.DataFrame({
        "long": (prev.clip(lower=0) * rr).sum(axis=1),
        "short": (prev.clip(upper=0) * rr).sum(axis=1),
    }).iloc[1:]
    gross_long = prev.clip(lower=0).sum(axis=1).iloc[1:]
    gross_short = -prev.clip(upper=0).sum(axis=1).iloc[1:]
    rf = inputs.cash_rate(days).iloc[1:]
    mkt = inputs.market_returns(days).iloc[1:]
    ret = led["ret"].reindex(days).iloc[1:]
    out = {"window": [str(days[0].date()), str(days[-1].date())], "sessions": int(len(legs))}
    for leg in ("long", "short"):
        x = legs[leg]
        g = gross_long if leg == "long" else gross_short
        # Leg excess over the market leg it is matched against (per unit gross).
        per_unit = x / g.replace(0, np.nan)
        out[leg] = {
            "ann_contribution": float(x.mean() * YEAR),
            "t": _t(x),
            "ann_vol": float(x.std() * np.sqrt(YEAR)),
            "avg_gross": float(g.mean()),
            "per_unit_gross_ann": float(per_unit.mean() * YEAR),
            "beta_daily": _slope(x, mkt),
            "alpha_vs_mkt_ann": float((x - _slope(x, mkt) * mkt).mean() * YEAR),
            "alpha_t": _t(x - _slope(x, mkt) * mkt),
            "alpha_by_year": {int(y): float(v) for y, v in
                              (x - _slope(x, mkt) * mkt).groupby(x.index.year).sum().items()},
            "by_year": {int(y): float(v) for y, v in x.groupby(x.index.year).sum().items()},
        }
    exc = ret - rf
    m_exc = (1 + exc).groupby(exc.index.to_period("M")).prod() - 1
    m_mkt = (1 + mkt - rf).groupby(mkt.index.to_period("M")).prod() - 1
    out["beta_daily"] = _slope(exc, mkt - rf)
    out["beta_monthly"] = _slope(m_exc, m_mkt)
    out["ann_ret"] = float((1 + ret).prod() ** (YEAR / len(ret)) - 1)
    out["ann_vol"] = float(ret.std() * np.sqrt(YEAR))
    nav = led["nav"].reindex(days)
    out["max_drawdown"] = float((nav / nav.cummax() - 1).min())
    for c in ("spread", "impact", "fees", "borrow"):
        if c in led:
            out[f"{c}_pct_nav_yr"] = float((led[c].reindex(days) / nav.shift(1)).iloc[1:].mean() * YEAR)
    out["gross_before_costs_ann"] = float(
        ((led[["spread", "impact", "fees", "borrow"]].reindex(days).sum(axis=1) / nav.shift(1)).iloc[1:]
         + ret).mean() * YEAR
    )
    s = json.loads((run_dir / "summary.json").read_text())
    out["compliance"] = {k: s.get(k) for k in (
        "avg_names", "min_names", "avg_gross", "max_gross", "breaches", "policy_breach_days",
        "max_abs_hedge_beta", "max_abs_sector", "net_ir_daily", "turnover_annualised")}
    b = pd.read_parquet(run_dir / "breaches.parquet")
    out["compliance"]["breaches_by_rule"] = b.groupby("rule").size().to_dict()
    return out


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("run_dir", type=Path)
    a.add_argument("--daily", type=Path)
    args = a.parse_args()
    rep = report(args.run_dir, args.daily)
    (args.run_dir / "legs.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep, indent=1))
