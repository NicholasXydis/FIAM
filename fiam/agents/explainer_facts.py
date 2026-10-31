# The explainer's facts table, from the fund's own outputs only.

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.agents import harness as H

# The fund's outputs; FIAM_VFINAL_OUT moves them, as for the engine.
FUND = Path(os.environ.get("FIAM_VFINAL_OUT", str(H.ROOT / "out" / "vfinal")))
# The book's run folder, its market cache and the forecast it traded.
BOOK, CACHE, FORECAST = FUND / "bw_fresh_lag", FUND / "cache", FUND / "forecast"
# Plain words for each characteristic code, frozen in git.
LABEL_FILE = H.ROOT / "frozen" / "agents" / "characteristic_labels.json"
# Codes the frozen labels lack, written out by hand.
EXTRA_LABELS = {
    "syy": "SYY-10 mispricing score",
    "sue_forecast": "forecast of the next earnings surprise",
    "short_ratio": "short interest relative to shares",
}
TOP = 10
LAST_DAY = pd.Timestamp("2026-08-31")
LATEST_REFIT = pd.Timestamp("2026-07-31")
BOOK_LISTS = ("top-10 long", "top-10 short")


# Each characteristic code in words, so nothing is guessed.
def labels() -> dict:
    return json.loads(LABEL_FILE.read_text(encoding="utf-8")) | EXTRA_LABELS


# Daily dollar positions, NAV and the lagged-position P&L per name.
def book(folder: Path = BOOK, cache: Path = CACHE):
    p = pd.read_parquet(folder / "positions.parquet")
    V = p.pivot(index="date", columns="permno", values="value").fillna(0.0)
    nav = pd.read_parquet(folder / "daily.parquet")["nav"].reindex(V.index)
    r = pd.read_parquet(cache / "market_ret.parquet").set_index("date")
    r = r.reindex(index=V.index, columns=[str(c) for c in V.columns])
    r.columns = V.columns
    held = V.shift(1).fillna(0.0)
    pnl = held * r.fillna(0.0)
    led = pd.read_parquet(folder / "ledger.parquet")
    led = led.pivot_table(index="permno", columns="kind", values="dollars", aggfunc="sum")
    return V, nav, r, held, pnl, led


# Names and tickers as the book reported them last.
def names(folder: Path = BOOK) -> pd.DataFrame:
    h = pd.read_csv(folder / "holdings_every_rebalance.csv")
    h = h.sort_values("decision_close").groupby("permno").last()
    return h[["Ticker", "Name"]].assign(Ticker=lambda d: d["Ticker"].str.replace(" US Equity", ""))


# Per-refit E-LASSO weights and the month's z-scored features.
class Model:
    # Loads the el_plus features, scores and mid-month scores once.
    def __init__(self, forecast: Path = FORECAST):
        self.forecast = forecast
        self.labels = labels()
        f = pd.read_parquet(forecast / "plus" / "features.parquet")
        f["date"] = pd.to_datetime(f["date"]).astype("datetime64[ns]")
        self.feats = f
        er = pd.read_parquet(forecast / "elasso_rho.parquet")
        er["eom"] = pd.to_datetime(er["eom"]).astype("datetime64[ns]")
        self.er = er
        self.cache = {}
        mm = pd.read_parquet(forecast / "mid_month.parquet")
        g = mm.groupby("T")["mainf"]
        mm["z"] = (mm["mainf"] - g.transform("mean")) / g.transform("std") * mm["rho"]
        self.mid = mm.set_index(["T", "permno"])["z"]

    # The mid-month score, z-scored and dialled like the month-end one.
    def mid_z(self, permno: int, T: pd.Timestamp):
        key = (T, permno)
        return round(float(self.mid.loc[key]), 2) if key in self.mid.index else None

    # Each characteristic's share of MaInf, cross-section demeaned.
    def contributions(self, eom: pd.Timestamp):
        if eom in self.cache:
            return self.cache[eom]
        refits = self.forecast / "plus" / "refits_wf"
        b = pd.read_parquet(refits / f"weights_{eom:%Y%m%d}.parquet").set_index("block")
        chars = [c for c in b.columns if c not in ("intercept", "enc", "refit")]
        rows = self.feats[self.feats["date"] == eom + pd.offsets.MonthEnd(1)]
        z = rows[chars].fillna(0.0).to_numpy(float)
        e = float(b.loc["s_MaInf", "enc"])
        sel = np.nan_to_num(b.loc["gr", chars].to_numpy(float)) != 0.0
        slope = np.nan_to_num(b.loc["uni_slope", chars].to_numpy(float))
        eff = (1 - e) * np.nan_to_num(b.loc["s_MaInf", chars].to_numpy(float))
        eff = eff + e * np.where(sel, slope, 0.0) / max(sel.sum(), 1)
        # Rebuilds MaInf to prove the split adds up to the forecast.
        uni = b.loc["uni_int", chars].to_numpy(float) + z * b.loc["uni_slope", chars].to_numpy(
            float
        )
        c = np.nan_to_num(uni[:, sel]).mean(1) if sel.any() else 0.0
        s = b.loc["s_MaInf", "intercept"] + z @ np.nan_to_num(
            b.loc["s_MaInf", chars].to_numpy(float)
        )
        mainf = (1 - e) * s + e * c
        sd = mainf.std(ddof=1)
        contrib = (z - z.mean(0)) * eff / sd
        pct = pd.DataFrame(z, columns=chars).rank(pct=True).to_numpy()
        out = dict(
            permnos=rows["permno"].to_numpy(),
            chars=chars,
            z=z,
            pct=pct,
            contrib=contrib,
            mainf=mainf,
            eff=eff,
            sd=sd,
        )
        er = self.er[self.er["eom"] == eom].set_index("permno")
        got = pd.Series(mainf, index=rows["permno"].to_numpy())
        assert np.allclose(got.reindex(er.index), er["mainf"], atol=1e-8), eom
        self.cache[eom] = out
        return out

    # The forecast and its top drivers for one name at one formation.
    def drivers(self, permno: int, eom: pd.Timestamp, k: int = 4) -> dict:
        m = self.contributions(eom)
        idx = np.flatnonzero(m["permnos"] == permno)
        er = self.er[(self.er["eom"] == eom) & (self.er["permno"] == permno)]
        if not len(idx) or not len(er):
            return dict(formation_month_end=str(eom.date()), available=False)
        i = idx[0]
        c = m["contrib"][i]
        order = np.argsort(c)

        # One driver in words and numbers, so nothing is guessed.
        def one(j):
            return dict(
                characteristic=self.labels.get(m["chars"][j], m["chars"][j]),
                code=m["chars"][j],
                stock_value_z=round(float(m["z"][i, j]), 2),
                stock_percentile=int(round(100 * m["pct"][i, j])),
                model_rewards="higher" if m["eff"][j] > 0 else "lower",
                contribution_to_forecast_z=round(float(c[j]), 2),
            )

        allz = self.er[self.er["eom"] == eom]["z"]
        z = float(er["z"].iloc[0])
        return dict(
            formation_month_end=str(eom.date()),
            available=True,
            forecast_z=round(z, 2),
            forecast_percentile=int(round(100 * (allz < z).mean())),
            regime_dial_rho=round(float(er["rho"].iloc[0]), 2),
            stocks_scored=int(len(allz)),
            top_drivers_up=[one(j) for j in order[::-1][:k] if c[j] > 0],
            top_drivers_down=[one(j) for j in order[:k] if c[j] < 0],
        )


# Held spells as (first day, last day); a side flip starts a new one.
def spells(v: pd.Series) -> list[tuple]:
    sg = np.sign(v)
    on = sg != 0
    starts = on & (sg != sg.shift(1, fill_value=0))
    ends = on & (sg != sg.shift(-1, fill_value=0))
    return list(zip(v.index[starts], v.index[ends]))


# The last formation before a spell's first day held.
def entry_formation(targets: pd.DataFrame, permno: int, first_day: pd.Timestamp) -> dict:
    t = targets[(targets["permno"] == permno) & (targets["T"] < first_day)]
    if not len(t):
        return {}
    row = t.sort_values("T").iloc[-1]
    return dict(eom=pd.Timestamp(row["eom"]), T=pd.Timestamp(row["T"]))


# Every fact about one name, from positions, returns and the ledger.
def facts(permno, V, nav, r, held, pnl, led, nm, targets, model, why) -> dict:
    v = V[permno]
    w = v / nav
    sp = spells(v)
    on = v != 0
    side_days = w[on]
    hd = held[permno] != 0
    stock_ret = float(np.prod(1 + r[permno][hd].fillna(0.0)) - 1)
    p = pnl[permno]
    long_pnl = float(p[held[permno] > 0].sum())
    short_pnl = float(p[held[permno] < 0].sum())
    lg = led.loc[permno] if permno in led.index else pd.Series(dtype=float)
    yearly = p.groupby(p.index.year).sum()
    first = sp[0][0]
    last = sp[-1][1]
    # The spell in view: the current one for the book, else the biggest.
    current = why.startswith(BOOK_LISTS)
    biggest = max(sp, key=lambda s: V[permno].loc[s[0] : s[1]].abs().sum())
    main = sp[-1] if current else biggest
    # The stock's own return over the spell's holding days.
    i0, i1 = r.index.get_loc(main[0]), r.index.get_loc(main[1])
    spell_r = r[permno].iloc[i0 + 1 : i1 + 2]
    ent = entry_formation(targets, permno, main[0])
    spell_pnl = p.iloc[p.index.get_loc(main[0]) : p.index.get_loc(main[1]) + 2].sum()
    out = dict(
        permno=int(permno),
        ticker=str(nm.loc[permno, "Ticker"]) if permno in nm.index else "",
        company=str(nm.loc[permno, "Name"]) if permno in nm.index else "",
        listed_because=why,
        side="LONG" if side_days.mean() > 0 else "SHORT",
        average_side_while_held="LONG" if side_days.mean() > 0 else "SHORT",
        side_on_2026_08_31={1: "LONG", -1: "SHORT", 0: "not held"}[int(np.sign(v.loc[LAST_DAY]))],
        flipped_sides=bool((side_days > 0).any() and (side_days < 0).any()),
        first_entered=str(first.date()),
        last_held=str(last.date()),
        still_held_on_2026_08_31=bool(v.loc[LAST_DAY] != 0),
        holding_spells=len(sp),
        trading_days_held=int(on.sum()),
        spell_in_view=dict(
            which="the spell held on 2026-08-31" if current else "the largest spell by dollars",
            entered=str(main[0].date()),
            exited=str(main[1].date()),
            side="LONG" if v.loc[main[0] : main[1]].mean() > 0 else "SHORT",
            avg_weight_pct=round(float(w.loc[main[0] : main[1]].mean() * 100), 3),
            stock_return_pct=round(float(np.prod(1 + spell_r.fillna(0.0)) - 1) * 100, 1),
            pnl_musd=round(float(spell_pnl) / 1e6, 2),
        ),
        avg_weight_while_held_pct=round(float(side_days.mean() * 100), 3),
        max_abs_weight_pct=round(float(side_days.abs().max() * 100), 3),
        weight_on_2026_08_31_pct=round(float(w.loc[LAST_DAY] * 100), 3),
        stock_return_while_held_pct=round(stock_ret * 100, 1),
        pnl_musd=round(float(p.sum()) / 1e6, 2),
        pnl_long_days_musd=round(long_pnl / 1e6, 2),
        pnl_short_days_musd=round(short_pnl / 1e6, 2),
        pnl_by_year_musd={int(y): round(float(x) / 1e6, 2) for y, x in yearly.items() if x != 0},
        engine_ledger_price_pnl_musd=round(float(np.nan_to_num(lg.get("price", 0.0))) / 1e6, 2),
        dividends_musd=round(float(np.nan_to_num(lg.get("dividend", 0.0))) / 1e6, 2),
        trading_cost_musd=round(float(np.nan_to_num(lg.get("cost", 0.0))) / 1e6, 2),
        borrow_cost_musd=round(float(np.nan_to_num(lg.get("borrow", 0.0))) / 1e6, 2),
    )
    # Whether the forecast at entry pointed the same way as the trade.
    if ent:
        mid = not (ent["T"] == ent["eom"] or ent["T"].day > 25)
        out["entry_formation"] = dict(
            decision_date=str(ent["T"].date()),
            kind="mid-month review" if mid else "month-end",
            model=model.drivers(permno, ent["eom"]),
        )
        fz = out["entry_formation"]["model"].get("forecast_z")
        sgn = 1 if out["spell_in_view"]["side"] == "LONG" else -1
        out["entry_formation"]["forecast_points_same_way_as_trade"] = (
            None if fz is None else bool(fz * sgn > 0)
        )
        # A mid-month entry also gets its own refreshed forecast score.
        if mid:
            out["entry_formation"]["mid_month_forecast_z"] = model.mid_z(permno, ent["T"])
    # The latest month-end view, for names still in the book.
    if out["still_held_on_2026_08_31"]:
        out["latest_formation"] = model.drivers(permno, LATEST_REFIT)
        lz = out["latest_formation"].get("forecast_z")
        now = 1 if v.loc[LAST_DAY] > 0 else -1
        out["latest_formation"]["forecast_points_same_way_as_trade"] = (
            None if lz is None else bool(lz * now > 0)
        )
    return out


# Share of a side's target gross whose forecast pointed the other way.
def wrong_share(x: pd.DataFrame, side: str, col: str = "z") -> float:
    wrong = (x[col] < 0) if side == "long" else (x[col] > 0)
    return round(100 * float(x.loc[wrong, "target"].abs().sum() / x["target"].abs().sum()), 1)


# Forecast against side at every formation, in two frames.
def agreement(targets: pd.DataFrame, model: Model) -> dict:
    t = targets[targets["target"] != 0].copy()
    me = model.er.set_index(["eom", "permno"])["z"]
    mid = (t["T"] != t["eom"]) & (t["T"].dt.day <= 25)
    zm = me.reindex(pd.MultiIndex.from_frame(t[["eom", "permno"]])).to_numpy()
    zd = model.mid.reindex(pd.MultiIndex.from_frame(t[["T", "permno"]])).to_numpy()
    t["z"] = np.where(mid, zd, zm)
    t = t.dropna(subset=["z"])
    out = {}
    for side, sel in (("long", t["target"] > 0), ("short", t["target"] < 0)):
        x = t[sel]
        key = f"{side}_gross_share_with_forecast_pointing_the_other_way_pct"
        out[key] = wrong_share(x, side)
        out[f"{side}_mean_forecast_z_weighted_by_target"] = round(
            float((x["z"] * x["target"].abs()).sum() / x["target"].abs().sum()), 2
        )
    last = t[t["T"] == t["T"].max()]
    for side, sel in (("long", last["target"] > 0), ("short", last["target"] < 0)):
        key = f"last_decision_{side}_gross_share_pointing_the_other_way_pct"
        out[key] = wrong_share(last[sel], side)
    # The fairer frame: against the median of stocks worth $3bn or more.
    me = model.feats[["date", "permno", "me"]].assign(
        eom=lambda d: (d["date"] - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    )
    er = model.er.merge(me[["eom", "permno", "me"]], on=["eom", "permno"], how="left")
    med = er[er["me"] >= 3000].groupby("eom")["z"].median()
    m = t[~mid.reindex(t.index)].copy()
    m["zr"] = m["z"] - m["eom"].map(med)
    for side, sel in (("long", m["target"] > 0), ("short", m["target"] < 0)):
        x = m[sel]
        w = x["target"].abs()
        key = f"month_end_{side}_gross_share_on_wrong_side_of_3bn_plus_median_pct"
        out[key] = wrong_share(x, side, "zr")
        out[f"month_end_{side}_mean_forecast_z_minus_3bn_plus_median"] = round(
            float((x["zr"] * w).sum() / w.sum()), 2
        )
    out["last_decision_date"] = str(t["T"].max().date())
    out["formations_counted"] = int(t.groupby(["eom", "T"]).ngroups)
    return out


# The 40 names and the fund-level facts, as one dict for facts.json.
def build(folder: Path = BOOK, cache: Path = CACHE, forecast: Path = FORECAST) -> dict:
    V, nav, r, held, pnl, led = book(folder, cache)
    nm = names(folder)
    targets = pd.read_parquet(folder / "targets.parquet")
    targets["eom"] = pd.to_datetime(targets["eom"]).astype("datetime64[ns]")
    model = Model(forecast)
    last = V.loc[LAST_DAY] / nav.loc[LAST_DAY]
    tot = pnl.sum()
    picks = [(p, "top-10 long in the 2026-08-31 book") for p in last.nlargest(TOP).index]
    picks += [(p, "top-10 short in the 2026-08-31 book") for p in last.nsmallest(TOP).index]
    picks += [(p, "top-10 positive contributor 2021-2026") for p in tot.nlargest(TOP).index]
    picks += [(p, "top-10 negative contributor 2021-2026") for p in tot.nsmallest(TOP).index]
    rows = []
    for p, why in picks:
        f = facts(p, V, nav, r, held, pnl, led, nm, targets, model, why)
        f["rank_in_list"] = sum(1 for x in rows if x["listed_because"] == why) + 1
        if why.startswith(BOOK_LISTS):
            f["rank_basis"] = "weight on 2026-08-31"
            f["side"] = f["side_on_2026_08_31"]
        else:
            f["rank_basis"] = "total P&L 2021-01-04 to 2026-08-31"
        rows.append(f)
    # Fund-level numbers, all from the fund's files.
    yearly = pnl.sum(1).groupby(pnl.index.year).sum() / 1e6
    gross = pd.read_parquet(folder / "daily.parquet")["gross"]
    gy = gross.groupby(gross.index.year).mean() * 100
    sidep = pnl.where(held > 0, 0.0).sum().sum(), pnl.where(held < 0, 0.0).sum().sum()
    cum = tot.sort_values(ascending=False)
    fund = dict(
        label=(folder / "LABEL.txt").read_text().strip(),
        result=json.loads((folder / "result.json").read_text()),
        stock_pnl_by_year_musd_positions_x_returns={int(y): round(x, 1) for y, x in yearly.items()},
        average_gross_by_year_pct={int(y): round(x, 1) for y, x in gy.items()},
        long_side_pnl_musd=round(sidep[0] / 1e6, 1),
        short_side_pnl_musd=round(sidep[1] / 1e6, 1),
        names_ever_held=int((V != 0).any().sum()),
        top10_winners_share_of_total_pnl_pct=round(100 * cum.head(10).sum() / tot.sum(), 1),
        top10_losers_musd=round(cum.tail(10).sum() / 1e6, 1),
        top10_winners_musd=round(cum.head(10).sum() / 1e6, 1),
        total_pnl_positions_x_returns_musd=round(tot.sum() / 1e6, 1),
        total_pnl_engine_ledger_price_musd=round(float(led.get("price").sum()) / 1e6, 1),
        names_on_2026_08_31=dict(long=int((last > 0).sum()), short=int((last < 0).sum())),
    )
    fund["forecast_vs_side_at_every_formation"] = agreement(targets, model)
    return dict(names=rows, fund=fund)


# Writes facts.json as the explainer reads it.
def write(path: Path) -> dict:
    out = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str))
    return out
