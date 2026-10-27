# v4 trading costs and borrow (PLAN §8.5, protocol "Step 7 rules").

import json
from functools import cache
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd

from fiam.v4 import data

OUT = Path(__file__).resolve().parents[3] / "out" / "v4" / "construct"
# The fee schedule in force at 2020-12-31 (PLAN §8.5), sales only.
SEC_FEE, TAF, TAF_CAP = 22.10 / 1e6, 0.000119, 5.95
# Commissions: 0.5 US cents a share on every trade (Step 7 rules).
COMMISSION = 0.005
# Impact Y sigma_d sqrt(Q / ADV), Y = 1, on the whole monthly trade.
IMPACT_Y = 1.0
# The spread calibration's years: TAQ effective spread, 2015-2020.
CALIBRATION = (pd.Timestamp("2015-01-01"), pd.Timestamp("2020-12-31"))
# JKP size groups by NYSE market-cap percentiles at the month end.
GROUPS = ((0.8, "mega"), (0.5, "large"), (0.2, "small"), (0.01, "micro"), (0.0, "nano"))
# Sessions a year for borrow accrual on each session's short value.
SESSIONS = 252


# Each stock's JKP size group from that month's NYSE cap percentiles.
def size_group(me: pd.Series, eom) -> pd.Series:
    # After 2025 the last CRSP month's breakpoints are carried forward.
    eom = min(pd.Timestamp(eom) + pd.offsets.MonthEnd(0), data.CRSP_END)
    m = data.table("crsp_monthly", ["cap_musd", "primaryexch", "sharetype", "securitytype"],
                   where={"date": (eom - pd.Timedelta(days=6), eom)})  # fmt: skip
    nyse = m[(m["primaryexch"] == "N") & (m["sharetype"] == "NS") & (m["securitytype"] == "EQTY")]
    cut = {name: float(nyse["cap_musd"].quantile(q)) for q, name in GROUPS}
    out = pd.Series("nano", index=me.index)
    for q, name in reversed(GROUPS[:-1]):
        out[me >= cut[name]] = name
    return out


# What the spread ratios are computed from; a changed key rebuilds them.
RATIO_KEY = {"calibration": [str(d.date()) for d in CALIBRATION], "groups": GROUPS,
             "ratio": "half TAQ EffectiveSpread_Percent_DW / bidaskhl_21d, me >= 500"}  # fmt: skip


# Half the TAQ effective spread over the panel's high-low, by group.
@cache
def spread_ratios() -> dict:
    path = OUT / "spread_ratios.json"
    if path.exists():
        body = json.loads(path.read_text())
        if body.get("key") == json.loads(json.dumps(RATIO_KEY)):
            return body["ratio_by_size_group"]
    rows = []
    for eom in data.month_ends(*CALIBRATION):
        p = data.table("panel", ["me", "bidaskhl_21d"], where={"eom": (eom, eom)})
        p = p[(p["me"] >= 500) & (p["bidaskhl_21d"] > 0)].set_index("permno")
        start = eom - pd.offsets.MonthBegin(1)
        t = data.table("taq_daily", ["EffectiveSpread_Percent_DW"],
                       where={"date": (start, eom), "permno": set(p.index)})  # fmt: skip
        half = t.groupby("permno")["EffectiveSpread_Percent_DW"].mean() / 2
        both = p.join(half.rename("half"), how="inner").dropna()
        both["group"] = size_group(both["me"], eom)
        rows.append(both.assign(ratio=both["half"] / both["bidaskhl_21d"]))
    frame = pd.concat(rows)
    ratios = frame.groupby("group")["ratio"].median().to_dict()
    OUT.mkdir(parents=True, exist_ok=True)
    body = {"what": "median of half the TAQ dollar-weighted effective spread over the panel's "
                    "bidaskhl_21d, universe stock-months of $500m+, by JKP size group, 2015-2020",
            "key": RATIO_KEY, "ratio_by_size_group": ratios,
            "rows": {k: int(v) for k, v in frame.groupby("group").size().items()}}  # fmt: skip
    path.write_text(json.dumps(body, indent=1))
    return ratios


# Each name's half spread: its high-low times its group's ratio.
def half_spread(x: pd.DataFrame) -> pd.Series:
    ratios = spread_ratios()
    ratio = size_group(x["me"], x["eom"].iloc[0]).map(ratios).fillna(max(ratios.values()))
    hl = x["bidaskhl_21d"].fillna(x["bidaskhl_21d"].median())
    return hl * ratio


# A trade's cost per unit of NAV: linear, sales fees and impact terms.
def coefficients(x: pd.DataFrame, nav: float) -> tuple:
    price = x["prc"].abs().to_numpy(dtype=float)
    linear = COMMISSION / price + x["half_spread"].to_numpy(dtype=float)
    adv = x["adv_cost"].to_numpy(dtype=float)
    impact = IMPACT_Y * x["sigma_d"].to_numpy(dtype=float) * np.sqrt(nav / adv)
    return linear, SEC_FEE + TAF / price, impact


# The optimiser's convex cost of a trade, as a share of NAV.
def convex(trade, x: pd.DataFrame, nav: float):
    linear, sells, impact = coefficients(x, nav)
    return (linear @ cp.abs(trade) + sells @ cp.neg(trade)
            + impact @ cp.power(cp.abs(trade), 1.5))  # fmt: skip


# The same cost in numbers: a month's trade as a share of NAV.
def share_of_nav(trade: np.ndarray, x: pd.DataFrame, nav: float) -> float:
    linear, sells, impact = coefficients(x, nav)
    t = np.abs(trade)
    return float(linear @ t + sells @ np.clip(-trade, 0, None) + impact @ t**1.5)


# A trade's dollar costs per name: fees, commission, spread, impact.
def dollars(moved: pd.Series, x: pd.DataFrame, month_trade: pd.Series) -> pd.Series:
    x = x.reindex(moved.index)
    q = moved.abs()
    shares = q / x["prc"].abs()
    sold = moved < 0
    fees = (SEC_FEE * q + np.minimum(TAF * shares, TAF_CAP)).where(sold, 0.0)
    whole = month_trade.reindex(moved.index).abs().fillna(q).clip(lower=q)
    impact = IMPACT_Y * x["sigma_d"] * np.sqrt(whole / x["adv_cost"]) * q
    return (fees + COMMISSION * shares + x["half_spread"] * q + impact).fillna(0.0)


# A name not in the frame (an exit) at costly values, never free.
def conservative(x: pd.DataFrame, names) -> pd.DataFrame:
    fill = {"prc": x["prc"].abs().median(), "half_spread": x["half_spread"].max(),
            "sigma_d": x["sigma_d"].quantile(0.9), "adv_cost": x["adv_cost"].quantile(0.05),
            "borrow": x["borrow"].max()}  # fmt: skip
    out = x.reindex(x.index.union(pd.Index(names)))
    return out.fillna({k: v for k, v in fill.items() if k in out})


# The engine's hooks: each trade day's costs and each session's borrow.
class Hooks:
    # Inputs by trade day, planned trades, and each name's last known row.
    def __init__(self):
        self.frames, self.planned, self.known = {}, {}, None

    # A formation's inputs and planned monthly trade, from its trade day.
    def add(self, day, x: pd.DataFrame, planned: pd.Series) -> None:
        self.frames[pd.Timestamp(day)] = x
        self.planned[pd.Timestamp(day)] = planned
        old = self.known if self.known is not None else x.iloc[:0]
        self.known = pd.concat([old[~old.index.isin(x.index)], x])

    # The frame in force on a day: the latest formation's.
    def at(self, d) -> tuple:
        keys = [k for k in self.frames if k <= pd.Timestamp(d)]
        k = max(keys)
        return self.frames[k], self.planned[k]

    # A day's moves in dollars; a name out of the frame uses its last row.
    def costs(self, d, moved: pd.Series) -> pd.Series:
        x, planned = self.at(d)
        gone = moved.index[~moved.index.isin(x.index)].intersection(self.known.index)
        x = pd.concat([x, self.known.loc[gone]])
        return dollars(moved, conservative(x, moved.index), planned)

    # A session's borrow on each short's value at its formation's tier.
    def borrow(self, d, shorts: pd.Series) -> pd.Series:
        x, _ = self.at(d)
        rate = x["borrow"].reindex(shorts.index).fillna(x["borrow"].max())
        return shorts * rate / SESSIONS


# A finished run's hooks replayed: each close sees only its known rows.
class Replay(Hooks):
    # The finished hooks, added back one formation at a time.
    def __init__(self, done: Hooks):
        super().__init__()
        self.done = done

    # Formations through the next session, as the live run had them.
    def upto(self, d) -> None:
        nxt = data.shift([d], 1).iloc[0]
        for k in sorted(self.done.frames):
            if k <= nxt and k not in self.frames:
                self.add(k, self.done.frames[k], self.done.planned[k])

    # A day's costs from the rows known by that close.
    def costs(self, d, moved: pd.Series) -> pd.Series:
        self.upto(d)
        return super().costs(d, moved)

    # A session's borrow from the formation in force that day.
    def borrow(self, d, shorts: pd.Series) -> pd.Series:
        self.upto(d)
        return super().borrow(d, shorts)
