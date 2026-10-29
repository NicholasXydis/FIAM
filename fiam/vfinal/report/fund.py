# The book's reports: 23 rows, flat costs, Arcana, holdings, months.

import io
import json

import numpy as np
import pandas as pd

from fiam.vfinal import book, checks, config, daily_book, data
from fiam.vfinal import inputs as engine
from fiam.vfinal.construct import formation
from fiam.vfinal.execution import costs
from fiam.vfinal.report import holdings, table_9_1

# The upload's columns, as Arcana's guide names them.
UPLOAD = ["Date", "Ticker", "Weights", "Asset Class", "ISIN", "AUM", "Custom Tag"]
# The first day the book holds anything (the build's first trades).
FIRST_HOLD = "2021-01-04"


# Each short's cap on each day it is held, for the 23 rows.
def short_caps(positions: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    shorts = positions[positions["value"] < 0]
    m = daily_book.Market(sorted(shorts["permno"].unique()), daily.index)
    caps = [m.cap_at(int(p), d) for p, d in zip(shorts["permno"], shorts["date"])]
    return shorts.assign(me=caps)[["date", "permno", "me"]]


# Row 17: turnover per rebalance x the book's rebalances a year.
def turnover_cell(d: pd.DataFrame, trades: pd.DataFrame, years: float) -> tuple:
    per = table_9_1.turnover_by_rebalance(d, trades)
    months = len(daily_book.monthly(d))
    k = len(per) * 12 / months
    after = per.iloc[1:].mean() * k * 100 if len(per) > 1 else np.nan
    cell = f"with build {per.mean() * k * 100:.0f}, without {after:.0f}; "
    cell += f"all trade days {d['turnover'].sum() / years * 100:.0f}"
    note = (
        f"half the sum of |w - w carried| a day; each traded day goes to the last rebalance "
        f"formed before it (spills and trades between rebalances added); {len(per)} "
        f"rebalances in {months} months, {per.mean() * 100:.1f}% each, x {k:g} a year; "
        "first one is the build"
    )
    return cell, table_9_1.NA, note


# The 23 rows, row 17 annualised by the book's own cadence.
def table(daily, trades, positions, caps, rf_monthly=None) -> pd.DataFrame:
    rows = table_9_1.table(daily, trades, positions, engine.sp500(daily.index),
                           rf_monthly=rf_monthly, caps=caps)  # fmt: skip
    d = daily.iloc[1:].loc[: table_9_1.END]
    cell, bench, note = turnover_cell(d, trades, len(d) / 252)
    at = rows.index[rows["row"] == 17][0]
    rows.loc[at, ["strategy", "benchmark", "note"]] = [cell, bench, note]
    return rows


# A built book's gates, scores, 23 rows and daily Arcana files.
def score(name: str) -> dict:
    out = config.folder(name)
    t = book.tables(name)
    daily, positions = t["daily"], t["positions"]
    caps = short_caps(positions, daily)
    caps.to_parquet(out / "short_caps.parquet", index=False)
    rows = table(daily, t["trades"], positions, caps)
    rows.to_csv(out / "table_9_1.csv", index=False)
    res = {"run": name}
    res |= checks.breaches(t["compliance"], positions, daily)
    res |= checks.scores(daily, rows) | checks.stock_pnl(t["ledger"], daily)
    ids = holdings.identifiers(positions["permno"], positions["date"])
    for kind, dates in (("daily", holdings.trade_days(t["trades"])),
                        ("monthly", holdings.monthly_days(t["trades"]))):  # fmt: skip
        file, lost = holdings.weights_file(positions, daily, ids, dates)
        holdings.write_csv(file, out / f"arcana_weights_{kind}.csv", holdings.WEIGHTS)
        res[f"arcana_{kind}_rows"], res[f"arcana_{kind}_unresolved"] = len(file), len(lost)
    book.write(out / "result.json", res)
    return res


# The book again with flat borrow and impact on each whole trade.
def flat(name: str) -> dict:
    out = config.folder(name)
    t = book.tables(name)
    world = formation.World(config.RUNS[name].policy, solves=False)
    alt, check = costs.flat(t["daily"], t["positions"], t["trades"],
                            costs.Law(world.frames, world))  # fmt: skip
    caps = pd.read_parquet(out / "short_caps.parquet")
    bill = checks.monthly_rate(data.rf_daily(alt.index))
    rows = table(alt, t["trades"], t["positions"], caps, rf_monthly=bill)
    rows.to_csv(out / "table_9_1_flat_costs.csv", index=False)
    res = {"run": name, "check": check} | checks.scores(alt, rows)
    book.write(out / "flat.json", res)
    return res


# The close each rebalance finished trading: the 5th session after T.
def done_days(daily: pd.DataFrame, targets: pd.DataFrame) -> list:
    days = daily.index[(daily.index >= FIRST_HOLD) & (daily.index <= config.END)]
    Ts = sorted(pd.to_datetime(targets["T"]).unique())
    return sorted({days[days > T][4] for T in Ts if (days > T).sum() >= 5})


# Upload rows for some days: weight, ticker, ISIN, AUM, side.
def upload_rows(p: pd.DataFrame, daily: pd.DataFrame, ids: pd.DataFrame) -> pd.DataFrame:
    nav = daily["nav"].reindex(p["date"].values).values
    p = p.assign(Weights=p["value"].values / nav)
    p = p[p["Weights"] != 0].join(ids, on="permno")
    miss = p["Ticker"].isna()
    out = pd.DataFrame({"Date": p["date"].dt.strftime("%Y-%m-%d"), "Ticker": p["Ticker"],
                        "Weights": p["Weights"], "Asset Class": "Equity", "ISIN": p["ISIN"],
                        "AUM": daily["nav"].reindex(p["date"].values).values,
                        "Custom Tag": np.where(p["Weights"] > 0, "long", "short")})  # fmt: skip
    return out[~miss.values]


# The Arcana upload in vfinal.csv's exact bytes.
def upload(name: str) -> dict:
    out = config.folder(name)
    d = pd.read_parquet(out / "daily.parquet")
    p = pd.read_parquet(out / "positions.parquet")
    p["date"] = pd.to_datetime(p["date"])
    own = pd.read_csv(out / "arcana_weights_daily_own.csv", usecols=["Ticker", "ISIN", "PERMNO"])
    ids = own.dropna(subset=["Ticker"]).drop_duplicates("PERMNO").set_index("PERMNO")
    t = pd.read_parquet(out / "targets.parquet")
    done = done_days(d, t)
    later = upload_rows(p[p["date"].isin(done)].copy(), d, ids)
    buf = io.StringIO()
    later.to_csv(buf, index=False)
    later = pd.read_csv(io.StringIO(buf.getvalue()))
    first = upload_rows(p[p["date"] == pd.Timestamp(FIRST_HOLD)].copy(), d, ids)
    full = pd.concat([first, later], ignore_index=True)[UPLOAD]
    path = out / "arcana_upload.csv"
    full.to_csv(path, index=False)
    return {"rows": len(full), "dates": int(full["Date"].nunique()), "file": str(path)}


# Every rebalance: decision close T and its first trade session.
def rebalances(days: pd.DatetimeIndex, targets: pd.DataFrame) -> pd.DataFrame:
    t = targets.assign(T=pd.to_datetime(targets["T"]))
    first = {T: days[days > T][0] for T in t["T"].unique() if (days > T).any()}
    t["trade_start"] = t["T"].map(first)
    return t[t["target"] != 0].dropna(subset=["trade_start"])


# The holdings file: target weight of every name at every rebalance.
def holdings_file(name: str) -> dict:
    out = config.folder(name)
    d = pd.read_parquet(out / "daily.parquet")
    t = rebalances(d.index, pd.read_parquet(out / "targets.parquet"))
    cols = ["Ticker", "ISIN", "PERMNO", "Name"]
    own = pd.read_csv(out / "arcana_weights_daily_own.csv", usecols=cols)
    own = own.drop_duplicates("PERMNO")
    h = t.merge(own, left_on="permno", right_on="PERMNO", how="left")
    h["side"] = h["target"].map(lambda w: "long" if w > 0 else "short")
    h = h.rename(columns={"T": "decision_close", "target": "target_weight"})
    cols = ["decision_close", "trade_start", "permno", "Ticker", "ISIN", "Name", "side",
            "target_weight"]  # fmt: skip
    h = h[cols].sort_values(["decision_close", "permno"])
    h.to_csv(out / "holdings_every_rebalance.csv", index=False, float_format="%.8f")
    return {"rows": len(h), "rebalances": int(h["decision_close"].nunique())}


# Monthly NAV, return and the profit lines, in US dollars.
def monthly_file(name: str) -> dict:
    out = config.folder(name)
    d = pd.read_parquet(out / "daily.parquet")
    d = d[d.index >= "2020-12-31"].copy()
    d["stock_pnl"] = (d.nav.diff() - d.dividends - d.interest + d.cost + d.borrow).fillna(0)
    d["names"] = d.n_long + d.n_short
    live = d.index >= "2021-01-01"
    g = d[live].groupby(d.index[live].to_period("M"))
    nav = d.nav.resample("ME").last()
    m = pd.DataFrame({"nav_end_usd": g.nav.last(), "stock_pnl_usd": g.stock_pnl.sum(),
                      "dividends_usd": g.dividends.sum(), "interest_usd": g.interest.sum(),
                      "trading_cost_usd": g.cost.sum(), "borrow_usd": g.borrow.sum(),
                      "avg_gross": g.gross.mean(), "positions_end": g.names.last()})  # fmt: skip
    ret = nav.pct_change()
    ret.index = ret.index.to_period("M")
    m.insert(1, "return", ret.reindex(m.index))
    m.insert(2, "cumulative_return", (1 + m["return"]).cumprod() - 1)
    m.index = m.index.astype(str)
    m.index.name = "month"
    m = m[m.index <= "2026-08"]
    m.to_csv(out / "returns_monthly.csv", float_format="%.6f")
    return {"months": len(m)}


# The independent finals check, written beside the book.
def compliance(name: str) -> dict:
    res = checks.finals_on(config.folder(name))
    (config.folder(name) / "compliance_check.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n"
    )
    return res
