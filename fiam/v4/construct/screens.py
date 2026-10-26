# Entry screens at a formation: squeeze (PLAN §8.6), crowding (C3).

import numpy as np
import pandas as pd

from fiam.v4 import data

# No new short above these (PLAN §8.6); percentiles over the universe.
SHORT_RATIO, DTC_PCT, BORROW_TIER, RUN_UP, SPIKE = 0.20, 0.90, 0.03, 0.50, 5.0
# Days for days-to-cover volume, the run-up and the volume baseline.
DTC_DAYS, RUN_DAYS, BASE_DAYS = 20, 20, 126
# Option skew and TAQ buy imbalance over all past stock-days' 99th.
EXTREME = 0.99
# The latest option or TAQ day public by T is looked for in this window.
LOOKBACK = pd.Timedelta(days=10)


# TAQ's signed volume: buys less sells over their sum, per stock-day.
def imbalance(rows: pd.DataFrame) -> pd.Series:
    total = rows["BuyVol_LR"] + rows["SellVol_LR"]
    return (rows["BuyVol_LR"] - rows["SellVol_LR"]) / total.where(total > 0)


# Every stock-day's skew and buy imbalance, read once with its clock.
class History:
    # Both histories from 2000, each value with its first close.
    def __init__(self, last):
        span = {"date": (pd.Timestamp("2000-01-01"), pd.Timestamp(last))}
        o = data.table("options_daily", ["Skew_OTM"], where=span)
        t = data.table("taq_daily", ["BuyVol_LR", "SellVol_LR"], where=span)
        self.skew = o[["first_close", "Skew_OTM"]].dropna().sort_values("first_close")
        t = t.assign(imb=imbalance(t))[["first_close", "imb"]].dropna()
        self.imb = t.sort_values("first_close")

    # The 99th percentiles over every stock-day public before T.
    def cuts(self, T) -> dict:
        T = pd.Timestamp(T)
        skew = self.skew.loc[self.skew["first_close"] < T, "Skew_OTM"].to_numpy()
        imb = self.imb.loc[self.imb["first_close"] < T, "imb"].to_numpy()
        return {"skew": float(np.quantile(skew, EXTREME)),
                "imbalance": float(np.quantile(imb, EXTREME))}  # fmt: skip


# Daily CRSP rows for these stocks over the window that ends at T.
def daily_rows(permnos, T, days: int) -> pd.DataFrame:
    sessions = data.sessions(pd.Timestamp(T) - pd.Timedelta(days=days * 2), T)[-days:]
    where = {"permno": set(int(p) for p in permnos), "date": (sessions[0], sessions[-1])}
    rows = data.table("crsp_daily", ["ret", "prc", "vol", "shrout_k", "delflg"], where=where)
    rows = rows[(rows["delflg"] != "Y") & (rows["date"] <= data.CRSP_END)]
    # After 2025 the dsf's returns only: the volume screens are off (§6.5).
    if sessions[-1] > data.CRSP_END:
        start = max(sessions[0], data.CRSP_END + pd.Timedelta(days=1))
        late = data.table("dsf", ["ret"], where=where | {"date": (start, sessions[-1])})
        rows = pd.concat([rows, late], ignore_index=True)
    data.assert_public_by(rows["first_close"], T, "screen rows")
    return rows


# The latest row of a daily table public by T, per stock.
def latest(table: str, columns: list[str], ids, T) -> pd.DataFrame:
    where = {"permno": set(int(p) for p in ids), "date": (pd.Timestamp(T) - LOOKBACK, T)}
    rows = data.table(table, columns, where=where)
    rows = rows[rows["first_close"] <= pd.Timestamp(T)].sort_values("date")
    # The whole latest row per stock, so its columns share one day.
    return rows.drop_duplicates("permno", keep="last").set_index("permno")


# Each candidate's squeeze flags at T; any flag blocks a new short.
def squeeze(x: pd.DataFrame, T, cuts: dict) -> pd.DataFrame:
    ids = list(x.index)
    d = daily_rows(ids, T, BASE_DAYS + 1)
    d["dollars"] = d["prc"].abs() * d["vol"]
    day = d["date"].max()
    last = d[d["date"] == day].set_index("permno")
    edge = np.sort(d["date"].unique())[-DTC_DAYS]
    recent = d[d["date"] >= edge]
    out = pd.DataFrame(index=x.index)
    out["short_ratio"] = x["short_ratio"] > SHORT_RATIO
    # Days to cover: shares short over the 20-day average share volume.
    short_shares = x["short_ratio"] * last["shrout_k"].reindex(x.index) * 1000
    dtc = short_shares / recent.groupby("permno")["vol"].mean().reindex(x.index)
    out["days_to_cover"] = dtc > dtc.quantile(DTC_PCT)
    out["borrow"] = x["borrow"] >= BORROW_TIER
    growth = (1 + recent.pivot_table(index="date", columns="permno", values="ret")).prod()
    out["run_up"] = (growth - 1).reindex(x.index) > RUN_UP
    # Split-safe: dollar volume on T against its 126-day average before.
    base = d[d["date"] < day].groupby("permno")["dollars"].mean()
    out["volume_spike"] = (last["dollars"] / base).reindex(x.index) > SPIKE
    skew = latest("options_daily", ["Skew_OTM"], ids, T)["Skew_OTM"]
    taq = latest("taq_daily", ["BuyVol_LR", "SellVol_LR"], ids, T)
    out["skew"] = skew.reindex(x.index) > cuts["skew"]
    out["buy_imbalance"] = imbalance(taq).reindex(x.index) > cuts["imbalance"]
    out = out.fillna(False).astype(bool)
    out["squeezed"] = out.any(axis=1)
    return out
