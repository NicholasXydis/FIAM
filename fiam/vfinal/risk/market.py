# Daily inputs from our tables: returns, ADV, vol, spreads, price.

import numpy as np
import pandas as pd

from fiam.vfinal import config, data
from fiam.vfinal.construct import costs as our_costs

# The windows: ADV 126, vol 63, spread 21 sessions.
ADV_DAYS, VOL_DAYS, SPREAD_DAYS = 126, 63, 21
# A missing quote is charged 50 bp; no quote is cheaper than 1 bp.
SPREAD_MISSING, SPREAD_FLOOR = 0.005, 0.0001
# Bad ticks are clipped before they reach a vol or a beta.
CLIP = 0.5
NAMES = ("ret", "adv", "sigma", "half_spread", "price")


# One year of CRSP daily rows as wide frames on the sessions.
def crsp_year(permnos, days) -> dict:
    cols = ["ret", "prc", "vol", "bid", "ask", "delflg"]
    c = data.table("crsp_daily", cols, where={"permno": set(permnos), "date": (days[0], days[-1])})
    # A delisting row is no trade; its return is the exits table's.
    c = c[c["delflg"] != "Y"]
    c = c.assign(dollars=c["prc"].abs() * c["vol"], px=c["prc"].abs())
    half = (c["ask"] - c["bid"]) / (c["ask"] + c["bid"])
    c["half"] = half.where((half > 0) & (half < 0.5))
    return {k: data.matrix(c, k, days, permnos) for k in ("ret", "dollars", "half", "px")}


# The dsf's price-only returns as a wide frame on the sessions.
def dsf_returns(permnos, days) -> pd.DataFrame:
    d = data.table("dsf", ["ret"], where={"permno": set(permnos), "date": (days[0], days[-1])})
    return data.matrix(d, "ret", days, permnos)


# Panel values at each session's last public month end, wide.
def panel_daily(permnos, days, column: str) -> pd.DataFrame:
    ends = pd.Series([data.month_end_at(d) for d in days], index=days)
    p = data.table("panel", [column], where={"permno": set(permnos),
                                             "eom": (ends.min(), ends.max())})  # fmt: skip
    wide = p.pivot_table(index="eom", columns="permno", values=column, aggfunc="first")
    wide = wide.reindex(columns=sorted(set(permnos)))
    return pd.DataFrame(wide.reindex(ends.to_numpy()).to_numpy(), index=days, columns=wide.columns)


# 2026 half spreads: the panel's high-low times our TAQ ratio by size.
def late_spreads(permnos, days) -> pd.DataFrame:
    out = pd.DataFrame(np.nan, index=days, columns=sorted(set(permnos)))
    for eom in sorted({data.month_end_at(d) for d in days}):
        p = data.table("panel", ["me", "bidaskhl_21d"], where={"permno": set(permnos),
                                                               "eom": (eom, eom)})  # fmt: skip
        p = p.set_index("permno").assign(eom=eom)
        on = [d for d in days if data.month_end_at(d) == eom]
        if len(p):
            out.loc[on, p.index] = our_costs.half_spread(p).to_numpy()[None, :]
    return out


# Every wide daily frame, built once and cached as parquet.
def build(permnos) -> dict:
    permnos = sorted(set(int(p) for p in permnos))
    days = data.sessions(config.START, config.END)
    crsp_days = days[days <= data.CRSP_END]
    late = days[days > data.CRSP_END]
    years = sorted(set(crsp_days.year))
    parts = [crsp_year(permnos, crsp_days[crsp_days.year == y]) for y in years]
    raw = {k: pd.concat([p[k] for p in parts]) for k in parts[0]}
    ret = pd.concat([raw["ret"], dsf_returns(permnos, late)])
    adv = raw["dollars"].rolling(ADV_DAYS, min_periods=ADV_DAYS // 2).mean()
    adv = pd.concat([adv, panel_daily(permnos, late, "dolvol_126d")])
    sigma = ret.clip(-CLIP, CLIP).rolling(VOL_DAYS, min_periods=VOL_DAYS // 3).std()
    spread = raw["half"].rolling(SPREAD_DAYS, min_periods=5).median()
    spread = pd.concat([spread, late_spreads(permnos, late)]).clip(lower=SPREAD_FLOOR)
    price = pd.concat([raw["px"].ffill(limit=5), panel_daily(permnos, late, "prc").abs()])
    out = {"ret": ret, "adv": adv, "sigma": sigma, "half_spread": spread.fillna(SPREAD_MISSING),
           "price": price}  # fmt: skip
    config.CACHE.mkdir(parents=True, exist_ok=True)
    for k, v in out.items():
        v = v.reindex(columns=permnos)
        v.columns = [str(c) for c in v.columns]
        v.rename_axis("date").reset_index().to_parquet(config.CACHE / f"market_{k}.parquet")
    return load()


# The cached frames, columns back to int permnos.
def load() -> dict:
    out = {}
    for k in NAMES:
        f = pd.read_parquet(config.CACHE / f"market_{k}.parquet").set_index("date")
        f.columns = [int(c) for c in f.columns]
        out[k] = f
    return out


# Daily rf, the market's return and its excess, on the sessions.
def market(days) -> pd.DataFrame:
    rf = data.rf_daily(days)
    mkt = data.market_daily(days)
    return pd.DataFrame({"rf": rf, "mkt": mkt, "mkt_rf": mkt - rf})
