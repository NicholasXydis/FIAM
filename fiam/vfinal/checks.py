# Every finals rule, from the engine's gates and the raw daily files.

import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import config, daily_book, data
from fiam.vfinal import inputs as engine
from fiam.vfinal.report import table_9_1

# Words no fund module may hold: the banned fields, Carbon Arc.
BANNED_WORDS = ("adjfct", "carbon", "shortintadj")
# The fund's own modules, the scan's scope; the shared engine is not.
FUND = ("__init__.py", "__main__.py", "book.py", "checks.py", "config.py", "lock.py", "run.py",
        "unseal.py", "construct/__init__.py", "construct/formation.py", "construct/optimize.py",
        "execution/__init__.py", "execution/costs.py", "execution/hook.py",
        "forecast/__init__.py", "forecast/build.py",
        "forecast/data.py", "forecast/elasso.py", "forecast/extras.py", "forecast/glmnet.py",
        "forecast/inputs.py", "forecast/midmonth.py", "forecast/pool.py", "forecast/regime.py",
        "forecast/walkforward.py", "report/fund.py", "risk/__init__.py", "risk/market.py",
        "risk/model.py", "risk/parts.py")  # fmt: skip
# The files that name the banned words to check for them.
DECLARE = {"fiam/vfinal/checks.py", "fiam/vfinal/forecast/data.py"}
# The scored days of the finals window (PDF part 2, 2.1).
FIRST_DAY, LAST_DAY = "2021-01-04", "2026-08-31"


# Each held name's sector on each day, from the month end before it.
def sectors(positions: pd.DataFrame) -> pd.Series:
    ends = {d: data.month_end_at(d) for d in positions["date"].unique()}
    month = positions["date"].map(ends)
    out = pd.Series(index=positions.index, dtype=object)
    for eom, idx in positions.groupby(month).groups.items():
        names = positions.loc[idx, "permno"]
        out[idx] = names.map(engine.sector(names.unique(), eom)).to_numpy()
    return out


# Each day's sectors held and largest absolute sector net weight.
def sector_days(positions: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    p = positions.assign(sector=sectors(positions))
    p["w"] = p["value"] / daily["nav"].reindex(p["date"]).to_numpy()
    net = p.groupby(["date", "sector"])["w"].sum()
    out = pd.DataFrame({"sectors_held": p.groupby("date")["sector"].nunique(),
                        "sector_net_max": net.abs().groupby(level=0).max()})  # fmt: skip
    bad = (out["sectors_held"] < config.HARD["sectors_min"]) | (
        out["sector_net_max"] > config.HARD["sector_net"] + 1e-12
    )
    return out.assign(sector_ok=~bad)


# Realised vol, daily and monthly, over the scored window.
def vols(daily: pd.DataFrame) -> dict:
    d = daily.iloc[1:]
    return {"vol_daily": float(d["ret"].std() * np.sqrt(252)),
            "vol_monthly": float(daily_book.monthly(d)["ret"].std() * np.sqrt(12))}  # fmt: skip


# Every breach day: the engine's gates plus sectors; vol over the run.
def breaches(compliance: pd.DataFrame, positions, daily) -> dict:
    c = compliance
    engine_bad = c["invested"] & (~c["names_ok"] | ~c["gross_ok"] | ~c["net_ok"] | ~c["cap_ok"]
                                  | (c["short_floor_breaches"] > 0))  # fmt: skip
    s = sector_days(positions, daily)
    bad = engine_bad.reindex(c.index, fill_value=False) | ~s["sector_ok"].reindex(
        c.index, fill_value=True
    )
    v = vols(daily)
    cap = c[["max_weight", "max_company_weight", "max_company_weight_pre"]].max(axis=1)
    cap = pd.concat([cap, daily["max_weight_pre"]], axis=1).max(axis=1)
    return {"breach_days": int(bad.sum()), "engine_breach_days": int(engine_bad.sum()),
            "cap_breach_days": int((~c["cap_ok"]).sum()),
            "names_breach_days": int((c["invested"] & ~c["names_ok"]).sum()),
            "sector_breach_days": int((~s["sector_ok"]).sum()),
            "vol_ok": bool(max(v.values()) <= config.HARD["vol"]),
            "max_weight": float(cap.max()), "gross_max": float(c["gross"].max()),
            "gross_pre_max": float(daily["gross_pre"].max()),
            "names_min": int(c.loc[c["invested"], "names"].min()),
            "names_max": int(c.loc[c["invested"], "names"].max()),
            "sectors_held_min": int(s["sectors_held"].min()),
            "sector_net_max": float(s["sector_net_max"].max()),
            "short_floor_breaches": int(c["short_floor_breaches"].sum())} | v  # fmt: skip


# The bill's monthly rate: each month's first daily rate x 252 / 12.
def monthly_rate(rf_daily: pd.Series) -> pd.Series:
    month = pd.DatetimeIndex(rf_daily.index).to_period("M")
    return (rf_daily * 252 / 12).groupby(month).first()


# The leading number of a 23-row cell such as "-0.82 (0.43); ...".
def lead(cell) -> float:
    return float(re.search(r"-?\d+\.?\d*", str(cell)).group())


# A run's headline numbers from its days and its 23 rows.
def scores(daily: pd.DataFrame, rows: pd.DataFrame) -> dict:
    d = daily.iloc[1:]
    m = daily_book.monthly(d)
    m["rf"] = table_9_1.monthly_bill(m, monthly_rate(data.rf_daily(daily.index)))
    active = m["ret"] - m["rf"] - table_9_1.PREMIUM / 12
    r = rows.set_index("row")["strategy"]
    years = len(m) / 12
    return {"ir": table_9_1.annual_ratio(active), "ir_se": table_9_1.ratio_se(active),
            "sharpe": float(r[8]), "cagr": float((1 + m["ret"]).prod() ** (1 / years) - 1),
            "vol": float(r[4]) / 100, "max_drawdown": float(r[11]) / 100,
            "beta_monthly": lead(r[6]), "beta_daily": lead(r[7]),
            "trading_cost": float(r[21]) / 100, "borrow": float(r[22]) / 100,
            "gross_mean": float(d.loc[d["gross"] > 0, "gross"].mean()),
            "ending_bn": float(r[1])}  # fmt: skip


# Stock P&L before costs: every ledger line but trading cost and borrow.
def stock_pnl(ledger: pd.DataFrame, daily: pd.DataFrame) -> dict:
    stock = ledger.loc[~ledger["kind"].isin(["cost", "borrow"]), "dollars"].sum()
    return {"stock_pnl_musd": float(stock) / 1e6,
            "cost_musd": float(daily["cost"].sum()) / 1e6,
            "borrow_musd": float(daily["borrow"].sum()) / 1e6,
            "interest_musd": float(daily["interest"].sum()) / 1e6}  # fmt: skip


# Daily end-of-day weights and pre-trade marks from yesterday's book.
def weights(positions, daily, ret) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = positions.assign(date=pd.to_datetime(positions["date"]))
    v = p.pivot_table(index="date", columns="permno", values="value", aggfunc="sum").fillna(0)
    v = v.reindex(daily.index).fillna(0)
    w = v.div(daily["nav"], axis=0)
    marked = v.shift(1) * (1 + ret.reindex(daily.index)[v.columns].fillna(0))
    w_pre = marked.div(marked.sum(axis=1) * 0 + daily["nav_pre"], axis=0)
    keep = (daily.index >= FIRST_DAY) & (daily.index <= LAST_DAY)
    return w[keep], w_pre[keep], daily[keep]


# Each name's GICS sector (2 digits) and size at the latest month end.
def panel_asof(panel: pd.DataFrame, dates, names) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = panel[panel["permno"].isin(names)]
    two = c["gics"].astype("Int64").astype(str).str[:2]
    sec = c.assign(s=two).pivot_table(index="eom", columns="permno", values="s",
                                      aggfunc="first")  # fmt: skip
    me = c.pivot_table(index="eom", columns="permno", values="me", aggfunc="first")
    idx = sec.index.union(dates)
    return (sec.reindex(idx).ffill().reindex(dates),
            me.reindex(idx).ffill().reindex(dates))  # fmt: skip


# Sector count and largest absolute sector net on each given row.
def sector_rows(w: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dt, row in w.iterrows():
        held = row[row != 0]
        s = sec.loc[dt].reindex(held.index).fillna("NA")
        net = held.groupby(s.values).sum()
        known = net.drop("NA", errors="ignore")
        # A sector counts as held if any name in it is held.
        held_in = int(pd.Series(s.values)[s.values != "NA"].nunique())
        rows.append({"date": dt, "sectors": held_in,
                     "max_abs_net": float(known.abs().max()) if len(known) else 0.0,
                     "unknown_weight": float(held[s.values == "NA"].abs().sum())})  # fmt: skip
    return pd.DataFrame(rows).set_index("date")


# The fund's own modules that hold a banned word.
def banned_code() -> dict:
    code = [str(config.ROOT / "fiam" / "vfinal" / f) for f in FUND]
    out = {}
    for word in BANNED_WORDS:
        hit = subprocess.run(["grep", "-Il", word, *code],
                             capture_output=True, text=True).stdout.split()  # fmt: skip
        out[word] = sorted(str(Path(h).relative_to(config.ROOT)) for h in hit)
    return out


# The independent check from a book's frames: every rule, counted.
def finals(positions, daily, targets, trades, caps, ret, panel) -> dict:
    w, w_pre, d = weights(positions, daily, ret)
    hard, res = config.HARD, {}
    names = (w != 0).sum(axis=1)
    res["names_min_max"] = [int(names.min()), int(names.max())]
    res["days_names_out_of_200_500"] = int(((names < hard["names_min"])
                                            | (names > hard["names_max"])).sum())  # fmt: skip
    res["max_weight_post"] = float(w.abs().max().max())
    res["max_weight_pre"] = float(w_pre.abs().max().max())
    over = (w.abs() > hard["name_cap"]).any(axis=1) | (w_pre.abs() > hard["name_cap"]).any(axis=1)
    res["days_any_name_over_5pct"] = int(over.sum())
    gross, gross_pre = w.abs().sum(axis=1), w_pre.abs().sum(axis=1)
    res["gross_max_post_pre"] = [float(gross.max()), float(gross_pre.max())]
    res["days_gross_over_200"] = int(((gross > hard["gross"]) | (gross_pre > hard["gross"])).sum())
    net = w.sum(axis=1)
    res["net_min_max"] = [float(net.min()), float(net.max())]
    res["days_net_outside_50"] = int((net.abs() > hard["net"]).sum())
    t = targets.assign(T=pd.to_datetime(targets["T"]))
    t = t[t["target"] != 0]
    dts = pd.DatetimeIndex(sorted(t["T"].unique()))
    sec_t, me_t = panel_asof(panel, dts, t["permno"].unique())
    shorts = t[t["target"] < 0]
    cap = [me_t.at[r.T, r.permno] if r.permno in me_t.columns else np.nan
           for r in shorts.itertuples()]  # fmt: skip
    cap = pd.Series(cap, dtype=float)
    res["short_targets"] = int(len(shorts))
    res["short_targets_cap_under_500m_monthly_panel"] = int((cap < hard["short_floor_musd"]).sum())
    res["short_targets_cap_missing_monthly_panel"] = int(cap.isna().sum())
    res["short_daily_cap_min_musd_engine"] = float(caps["me"].min()) if len(caps) else np.nan
    tw = t.pivot_table(index="T", columns="permno", values="target", aggfunc="sum").fillna(0)
    st = sector_rows(tw, sec_t)
    res["rebalances"] = int(len(tw))
    res["rebalance_sectors_min"] = int(st["sectors"].min())
    res["rebalance_sector_net_max"] = float(st["max_abs_net"].max())
    res["rebalance_unknown_sector_weight_max"] = float(st["unknown_weight"].max())
    starts = pd.DatetimeIndex([w.index[w.index > T][0] for T in dts if (w.index > T).any()])
    sec_d, _ = panel_asof(panel, starts, w.columns)
    sd = sector_rows(w.loc[starts], sec_d)
    res["held_on_trade_start_sectors_min"] = int(sd["sectors"].min())
    res["held_on_trade_start_sector_net_max"] = float(sd["max_abs_net"].max())
    m = d["nav"].resample("ME").last().pct_change().dropna()
    res["vol_monthly_ann"] = float(m.std() * 12**0.5)
    res["vol_daily_ann"] = float(d["ret"].std() * 252**0.5)
    tr = trades.assign(date=pd.to_datetime(trades["date"]), formed=pd.to_datetime(trades["formed"]))
    res["trades"] = int(len(tr))
    res["trades_on_or_before_their_decision_close"] = int((tr["date"] <= tr["formed"]).sum())
    res["first_trade_date"] = str(tr["date"].min().date())
    res["last_position_date"] = str(w.index.max().date())
    res["start_nav"] = float(daily["nav"].iloc[0])
    res["violations"] = violations(res)
    res["breaches"] = len(res["violations"])
    return res


# The rules an independent check found broken, by name.
def violations(r: dict) -> list[str]:
    hard = config.HARD
    tests = {
        "names": r["days_names_out_of_200_500"] > 0,
        "single_position": r["days_any_name_over_5pct"] > 0,
        "gross": r["days_gross_over_200"] > 0,
        "net": r["days_net_outside_50"] > 0,
        "short_floor_formation": r["short_targets_cap_under_500m_monthly_panel"] > 0,
        "short_floor_held": not r["short_daily_cap_min_musd_engine"] >= hard["short_floor_musd"],
        "sector_breadth": min(r["rebalance_sectors_min"],
                              r["held_on_trade_start_sectors_min"]) < hard["sectors_min"],
        "sector_net": max(r["rebalance_sector_net_max"],
                          r["held_on_trade_start_sector_net_max"]) > hard["sector_net"],
        "volatility": max(r["vol_monthly_ann"], r["vol_daily_ann"]) > hard["vol"],
        "look_ahead": r["trades_on_or_before_their_decision_close"] > 0,
        "window": r["first_trade_date"] < FIRST_DAY or r["last_position_date"] > LAST_DAY,
        "capital": r["start_nav"] != config.Policy().nav0,
    }  # fmt: skip
    return [k for k, bad in tests.items() if bad]


# The independent check on a book's folder, the organisers' panel.
def finals_on(folder) -> dict:
    f = {p: pd.read_parquet(folder / f"{p}.parquet")
         for p in ("positions", "daily", "targets", "trades", "short_caps")}  # fmt: skip
    r = pd.read_parquet(config.CACHE / "market_ret.parquet").set_index("date")
    r.index, r.columns = pd.to_datetime(r.index), r.columns.astype(int)
    panel = pd.read_parquet(config.PANEL, columns=["permno", "eom", "gics", "sic", "me"])
    panel["eom"] = pd.to_datetime(panel["eom"]) + pd.offsets.MonthEnd(0)
    res = finals(f["positions"], f["daily"], f["targets"], f["trades"], f["short_caps"], r,
                 panel)  # fmt: skip
    res["code_files_mentioning"] = found = banned_code()
    # Only the two files that declare the banned words may name them.
    if any(set(v) - DECLARE for v in found.values()):
        res["violations"].append("banned_field_in_code")
        res["breaches"] = len(res["violations"])
    return res
