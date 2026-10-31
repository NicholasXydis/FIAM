# Every number of the pack from the run's files, into numbers.json.

import json

import numpy as np
import pandas as pd
import statsmodels.api as sm

from tools.pack import sources as S

# The run's folder, chart data and the window's last day.
RUN = S.RUN
DATA = S.DATA
END = pd.Timestamp("2026-08-31")
FIRST_HOLD = pd.Timestamp("2021-01-04")
PREMIUM = 0.04
NAV0 = 1e9
# GICS two-digit sector names.
GICS = {
    "10": "Energy",
    "15": "Materials",
    "20": "Industrials",
    "25": "Consumer Discretionary",
    "30": "Consumer Staples",
    "35": "Health Care",
    "40": "Financials",
    "45": "Information Technology",
    "50": "Communication Services",
    "55": "Utilities",
    "60": "Real Estate",
}
# The 60/40 mixes beside the fund: stocks, bonds, fund.
MIXES = {
    "60/40": (0.6, 0.4, 0.0),
    "60/30/10 fund": (0.6, 0.3, 0.1),
    "60/20/20 fund": (0.6, 0.2, 0.2),
    "60/0/40 fund": (0.6, 0.0, 0.4),
}
# The headline numbers the brief gave, checked against the files.
GIVEN = {
    "ir_after": -0.1075,
    "ir_before": 0.003,
    "sharpe": 0.912,
    "cagr_pct": 7.00,
    "arith_pct": 6.86,
    "vol_pct": 3.96,
    "max_dd_pct": -2.99,
    "ending_bn": 1.467,
    "hurdle_bn": 1.508,
    "alpha_pct": 3.46,
    "alpha_se": 1.41,
    "beta_m": 0.012,
    "beta_d": 0.018,
    "names_min": 246,
    "names_max": 357,
    "gross_avg_pct": 136.5,
    "gross_max_pct": 192.9,
    "gross_pre_max_pct": 194.0,
    "breaches": 0,
    "rebalances": 136,
    "turnover_row17_pct": 94,
    "flat_ir": -0.27,
    "flat_sharpe": 0.74,
    "flat_cagr_pct": 6.30,
    "flat_dd_pct": -3.03,
}
GIVEN_PNL = {2021: 72.2, 2022: -6.3, 2023: 103.8, 2024: 85.3, 2025: -26.5, 2026: 30.8}
GIVEN_GROSS = {2021: 77, 2022: 107, 2023: 125, 2024: 157, 2025: 185, 2026: 184}


# OLS with Newey-West errors: intercept, its s.e., slope, its s.e.
def ols(y, x, lags):
    fit = sm.OLS(np.asarray(y), sm.add_constant(np.asarray(x))).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags}
    )
    return float(fit.params[0]), float(fit.bse[0]), float(fit.params[1]), float(fit.bse[1])


# Daily returns compounded within calendar months.
def compound(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


# Mean over sd times root 12 of monthly returns.
def ratio(r: pd.Series) -> float:
    return float(r.mean() / r.std(ddof=1) * np.sqrt(12))


# Lo (2002) standard error of an annualised monthly ratio.
def ratio_se(r: pd.Series) -> float:
    s = r.mean() / r.std(ddof=1)
    return float(np.sqrt((1 + s**2 / 2) / len(r)) * np.sqrt(12))


# The worst fall of a compounded path that starts at 1.
def drawdown(r: pd.Series) -> float:
    w = np.concatenate([[1.0], (1 + r).cumprod().to_numpy()])
    return float((w / np.maximum.accumulate(w) - 1).min())


# The S&P 500 daily return as the engine builds it: CRSP, then FRED.
def sp500(days: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    c = pd.read_parquet(S.CRSP_MARKET, columns=["dlycaldt", "sprtrn"])
    c = c.assign(date=pd.to_datetime(c["dlycaldt"])).set_index("date")["sprtrn"]
    f = pd.read_csv(S.BENCHMARKS / "SP500.csv")
    f["SP500"] = pd.to_numeric(f["SP500"], errors="coerce")
    f = f.dropna().assign(date=lambda x: pd.to_datetime(x["observation_date"]))
    fred = f.set_index("date")["SP500"].pct_change()
    out = pd.Series(c.reindex(days).to_numpy(), index=days)
    late = days[days > pd.Timestamp("2025-12-31")]
    out.loc[late] = fred.reindex(late).to_numpy()
    return out, fred.reindex(days)


# The PDF's monthly bill, TB3MS / 1200, by month.
def bill() -> pd.Series:
    t = pd.read_csv(S.BENCHMARKS / "TB3MS.csv", parse_dates=["observation_date"])
    return pd.Series(t["TB3MS"].to_numpy() / 1200, index=t["observation_date"].dt.to_period("M"))


# PERMNO to ticker and name, from the fund's own Arcana file.
def names() -> pd.DataFrame:
    own = pd.read_csv(RUN / "arcana_weights_daily_own.csv", usecols=["PERMNO", "Ticker", "Name"])
    own = own.dropna(subset=["Ticker"]).drop_duplicates("PERMNO", keep="last")
    own["Ticker"] = own["Ticker"].str.replace(" US Equity", "", regex=False)
    return own.set_index("PERMNO")


# The days the book holds, as weights of NAV, name by column.
def weights(pos: pd.DataFrame, nav: pd.Series) -> pd.DataFrame:
    v = pos.pivot_table(index="date", columns="permno", values="value", aggfunc="sum")
    return v.reindex(nav.index).fillna(0.0).div(nav, axis=0)


# One-way turnover by rebalance, each traded day to the one before.
def turnover_by_rebalance(d, trades) -> tuple[pd.Series, pd.Series]:
    first = trades.groupby("formed")["date"].min()
    firsts = first[first.index < first].sort_values()
    days = d.index[d["traded"].astype(bool)]
    group = np.maximum(np.searchsorted(firsts.to_numpy(), days.to_numpy(), side="right") - 1, 0)
    per = d.loc[days, "turnover"].groupby(group).sum()
    per.index = firsts.index[per.index]
    return per, firsts


# Position-weighted run length in sessions, the plain mean beside it.
def holding_period(positions, daily) -> tuple[float, float]:
    place = pd.Series(range(len(daily)), index=daily.index)
    p = positions[positions["date"].isin(daily.index)].copy()
    p["i"] = p["date"].map(place)
    p = p.sort_values(["permno", "i"], kind="stable")
    side = np.sign(p["value"])
    new = (p["permno"] != p["permno"].shift()) | (p["i"].diff() != 1) | (side != side.shift())
    p["run"] = new.cumsum()
    p["w"] = p["value"].abs() / p["date"].map(daily["nav"])
    g = p.groupby("run").agg(days=("i", "size"), w=("w", "mean"))
    return float((g["days"] * g["w"]).sum() / g["w"].sum()), float(g["days"].mean())


# Each name's GICS sector and cap at the latest month end on or before.
def panel_asof(panel, dates, names_):
    c = panel[panel["permno"].isin(names_)]
    sec = c.pivot_table(index="eom", columns="permno", values="s", aggfunc="first")
    idx = sec.index.union(dates)
    return sec.reindex(idx).ffill().reindex(dates)


# A number rounded for JSON.
def r(x, k=6):
    if isinstance(x, str):
        return x
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


# A Yahoo file's monthly returns from adjusted closes over the window.
def yahoo(tk):
    j = json.loads(S.yahoo_file(tk).read_text())["chart"]["result"][0]
    ts = pd.to_datetime(j["timestamp"], unit="s").tz_localize("UTC").tz_convert("America/New_York")
    adj = pd.Series(j["indicators"]["adjclose"][0]["adjclose"], index=ts.tz_localize(None))
    adj.index = adj.index.to_period("M")
    adj = adj[~adj.index.duplicated(keep="last")]
    return adj.pct_change().loc["2021-01":"2026-08"]


# A monthly series' CAGR, vol, Sharpe, drawdown and 2022, as percents.
def stats(x, rf):
    wl = (1 + x).cumprod()
    pk = np.maximum.accumulate(np.concatenate([[1.0], wl.to_numpy()]))[1:]
    e = x - rf
    return {
        "cagr_pct": r((wl.iloc[-1] ** (12 / len(x)) - 1) * 100, 4),
        "vol_pct": r(x.std(ddof=1) * np.sqrt(12) * 100, 4),
        "sharpe": r(e.mean() / e.std(ddof=1) * np.sqrt(12), 4),
        "max_drawdown_month_end_pct": r((wl / pk - 1).min() * 100, 4),
        "worst_month_pct": r(x.min() * 100, 4),
        "year_2022_pct": r(((1 + x.loc["2022-01":"2022-12"]).prod() - 1) * 100, 4),
        "growth_of_1": r(wl.iloc[-1], 6),
    }


# The whole computation, written to numbers.json and data/*.csv.
def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out: dict = {
        "fund": "QUARCC Purple",
        "window": "2021-01-04 to 2026-08-31, 68 months, start NAV US$1bn",
        "source_folder": "out/vfinal/bw_fresh_lag",
    }
    daily = pd.read_parquet(RUN / "daily.parquet")
    pos = pd.read_parquet(RUN / "positions.parquet")
    trades = pd.read_parquet(RUN / "trades.parquet")
    targets = pd.read_parquet(RUN / "targets.parquet")
    ledger = pd.read_parquet(RUN / "ledger.parquet")
    comp = pd.read_parquet(RUN / "compliance.parquet")
    caps = pd.read_parquet(RUN / "short_caps.parquet")
    res = json.loads((RUN / "result.json").read_text())
    flat = json.loads((RUN / "flat.json").read_text())
    cc = json.loads((RUN / "compliance_check.json").read_text())
    t91 = pd.read_csv(RUN / "table_9_1.csv")
    t91f = pd.read_csv(RUN / "table_9_1_flat_costs.csv")
    nm = names()

    # The scored days and their months, the endowment row dropped.
    start = float(daily["nav"].iloc[0] / (1 + daily["ret"].iloc[0]))
    prev = daily["nav"].shift(1)
    d = daily.iloc[1:].loc[:END]
    prev = prev.loc[d.index]
    sp, sp_fred = sp500(d.index)
    m = compound(d[["ret", "rf"]]).rename(columns={"rf": "rf_daily"})
    b = bill().reindex(m.index)
    m["bill"] = b
    hurdle_m = b + PREMIUM / 12
    hurdle_m_daily_rf = m["rf_daily"] + PREMIUM / 12
    active = m["ret"] - hurdle_m
    sp_m = compound(sp)
    before_d = d["ret"] + (d["cost"] + d["borrow"]) / prev
    before_m = compound(before_d)
    years = len(m) / 12
    end_v = start * float((1 + d["ret"]).prod())
    hurdle_end = start * float((1 + hurdle_m).prod())
    hurdle_end_daily_rf = start * float((1 + hurdle_m_daily_rf).prod())

    # The headline, recomputed.
    a, a_se, bm, bm_se = ols(m["ret"] - m["rf_daily"], sp_m - m["rf_daily"], 3)
    _, _, bd, bd_se = ols(d["ret"] - d["rf"], sp - d["rf"], 5)
    _, _, bd_fred, _ = ols(d["ret"] - d["rf"], sp_fred.fillna(0) - d["rf"], 5)
    live = d[d.index >= FIRST_HOLD]
    names_n = live["n_long"] + live["n_short"]
    per, firsts = turnover_by_rebalance(d, trades)
    k = len(per) * 12 / len(m)
    held, plain = holding_period(pos, daily.loc[: d.index[-1]])
    ex = m["ret"] - m["rf_daily"]
    head = {
        "ending_value_bn": end_v / 1e9,
        "hurdle_ending_bn_pdf_bill": hurdle_end / 1e9,
        "hurdle_ending_bn_daily_bill_as_table_row1": hurdle_end_daily_rf / 1e9,
        "cumulative_return_pct": (end_v / start - 1) * 100,
        "cagr_pct": ((1 + m["ret"]).prod() ** (1 / years) - 1) * 100,
        "arithmetic_return_pct": m["ret"].mean() * 1200,
        "vol_monthly_pct": m["ret"].std(ddof=1) * np.sqrt(12) * 100,
        "vol_daily_pct": d["ret"].std() * np.sqrt(252) * 100,
        "ir_after_costs": ratio(active),
        "ir_after_costs_se": ratio_se(active),
        "ir_after_costs_daily_bill": ratio(m["ret"] - hurdle_m_daily_rf),
        "ir_before_costs": ratio(before_m - hurdle_m),
        "ir_before_costs_daily_bill_as_table_row9": ratio(before_m - hurdle_m_daily_rf),
        "tracking_error_pct": active.std(ddof=1) * np.sqrt(12) * 100,
        "sharpe": ratio(ex),
        "sharpe_pdf_bill": ratio(m["ret"] - b),
        "alpha_pct": a * 1200,
        "alpha_se_pct": a_se * 1200,
        "beta_monthly": bm,
        "beta_monthly_se": bm_se,
        "beta_daily": bd,
        "beta_daily_se": bd_se,
        "beta_daily_fred_only": bd_fred,
        "max_drawdown_pct": drawdown(d["ret"]) * 100,
        "max_one_month_loss_pct": m["ret"].min() * 100,
        "max_one_day_loss_pct": d["ret"].min() * 100,
        "names_min": int(names_n.min()),
        "names_max": int(names_n.max()),
        "names_avg": float(names_n.mean()),
        "gross_avg_pct": live["gross"].mean() * 100,
        "gross_max_pct": live["gross"].max() * 100,
        "gross_pre_trade_max_pct": daily["gross_pre"].max() * 100,
        "net_avg_pct": live["net"].mean() * 100,
        "net_min_pct": live["net"].min() * 100,
        "net_max_pct": live["net"].max() * 100,
        "breaches": int(cc["breaches"]) + int(res["breach_days"]),
        "rebalances": int(len(per)),
        "rebalances_per_year": k,
        "rebalance_cadence": "twice a month: month end and a mid-month review",
        "stock_pnl_musd": float(
            ledger.loc[~ledger["kind"].isin(["cost", "borrow"]), "dollars"].sum() / 1e6
        ),
        "trading_cost_musd": float(d["cost"].sum() / 1e6),
        "borrow_musd": float(d["borrow"].sum() / 1e6),
        "interest_musd": float(d["interest"].sum() / 1e6),
        "dividends_musd": float(d["dividends"].sum() / 1e6),
    }
    out["headline"] = {k_: r(v) for k_, v in head.items()} | {
        "rebalance_cadence": head["rebalance_cadence"]
    }

    # Each given number against the files, flagged when it differs.
    got = {
        "ir_after": head["ir_after_costs"],
        "ir_before": head["ir_before_costs"],
        "sharpe": head["sharpe"],
        "cagr_pct": head["cagr_pct"],
        "arith_pct": head["arithmetic_return_pct"],
        "vol_pct": head["vol_monthly_pct"],
        "max_dd_pct": head["max_drawdown_pct"],
        "ending_bn": head["ending_value_bn"],
        "hurdle_bn": head["hurdle_ending_bn_daily_bill_as_table_row1"],
        "alpha_pct": head["alpha_pct"],
        "alpha_se": head["alpha_se_pct"],
        "beta_m": head["beta_monthly"],
        "beta_d": head["beta_daily"],
        "names_min": head["names_min"],
        "names_max": head["names_max"],
        "gross_avg_pct": head["gross_avg_pct"],
        "gross_max_pct": head["gross_max_pct"],
        "gross_pre_max_pct": head["gross_pre_trade_max_pct"],
        "breaches": head["breaches"],
        "rebalances": head["rebalances"],
        "turnover_row17_pct": per.mean() * k * 100,
        "flat_ir": flat["ir"],
        "flat_sharpe": flat["sharpe"],
        "flat_cagr_pct": flat["cagr"] * 100,
        "flat_dd_pct": flat["max_drawdown"] * 100,
    }
    checks = {}
    for key, want in GIVEN.items():
        dec = len(str(want).split(".")[1]) if "." in str(want) else 0
        ok = round(got[key], dec) == round(want, dec) or abs(got[key] - want) < 10 ** (-dec) / 2
        checks[key] = {"given": want, "computed": r(got[key]), "match": bool(ok)}
    out["checks_against_brief"] = checks

    # The 23 rows as the run wrote them, flat-cost rows beside.
    rows = []
    for (_, x), (_, y) in zip(t91.iterrows(), t91f.iterrows()):
        rows.append(
            {
                "row": int(x["row"]),
                "name": x["name"],
                "strategy": x["strategy"],
                "benchmark": x["benchmark"],
                "flat_costs_strategy": y["strategy"],
                "flat_costs_benchmark": y["benchmark"],
                "note": "" if pd.isna(x["note"]) else x["note"],
            }
        )
    out["table_5_1"] = {
        "benchmark": "T-bill (TB3MS) + 4% a year, as PDF p20 defines the hurdle",
        "source": "out/vfinal/bw_fresh_lag/table_9_1.csv and table_9_1_flat_costs.csv",
        "rows": rows,
    }
    # Recomputed rows beside the file's; row 20 counts traded days only.
    traded = d.index[d["traded"].astype(bool)]
    sc = pos[(pos["value"] < 0) & pos["date"].isin(traded)].merge(
        caps, on=["date", "permno"], how="left"
    )
    by_day = sc.dropna(subset=["me"]).groupby("date")["me"]
    g_mean = float(d.loc[d["gross"] > 0, "gross"].mean())
    scaled = compound(d["rf"] + (d["ret"] - d["rf"]) / g_mean)
    out["table_5_1"]["recomputed"] = {
        "1_ending_bn": r(end_v / 1e9),
        "1_benchmark_bn": r(hurdle_end_daily_rf / 1e9),
        "4_vol_pct": r(head["vol_monthly_pct"]),
        "8_sharpe": r(head["sharpe"]),
        "9_ir_before": r(head["ir_before_costs_daily_bill_as_table_row9"]),
        "10_te_pct": r((m["ret"] - hurdle_m_daily_rf).std(ddof=1) * np.sqrt(12) * 100),
        "11_dd_pct": r(head["max_drawdown_pct"]),
        "12_month_pct": r(head["max_one_month_loss_pct"]),
        "13_day_pct": r(head["max_one_day_loss_pct"]),
        "17_turnover_with_build_pct": r(per.mean() * k * 100),
        "17_turnover_without_build_pct": r(per.iloc[1:].mean() * k * 100),
        "17_all_trade_days_pct": r(d["turnover"].sum() / (len(d) / 252) * 100),
        "18_holding_sessions": r(held),
        "18_plain_mean": r(plain),
        "19_avg_position_musd": r(pos[pos["date"].isin(live.index)]["value"].abs().mean() / 1e6),
        "20_short_median_cap_musd": r(by_day.median().median()),
        "20_short_min_cap_musd": r(by_day.min().min()),
        "21_trading_cost_pct": r((d["cost"] / prev).mean() * 252 * 100),
        "22_borrow_pct": r((d["borrow"] / prev).mean() * 252 * 100),
        "23_ir_net": r(ratio(m["ret"] - hurdle_m_daily_rf)),
        "23_ir_at_100_gross": r(ratio(scaled - hurdle_m_daily_rf)),
        "23_sharpe_at_100_gross": r(ratio(scaled - m["rf_daily"])),
    }

    # The flat-cost variant, from flat.json and its 23 rows.
    out["flat_costs"] = {
        k_: r(flat[k_]) if isinstance(flat[k_], float) else flat[k_] for k_ in flat
    }
    out["flat_costs"]["what"] = (
        "PDF p17 conservative costs: flat borrow and impact on each "
        "whole trade; same trades, only the cost lines change"
    )
    out["flat_costs"]["ir_before_costs"] = r(float(t91f.loc[8, "strategy"]))

    # S&P 500 over the same days, for context (price index, no dividends).
    spw = (1 + sp).cumprod()
    out["sp500_context"] = {
        "series": "S&P 500 price index: CRSP sprtrn to 2025-12-31, FRED SP500 after",
        "cumulative_return_pct": r((spw.iloc[-1] - 1) * 100),
        "cagr_pct": r(((1 + sp_m).prod() ** (1 / years) - 1) * 100),
        "vol_monthly_pct": r(sp_m.std(ddof=1) * np.sqrt(12) * 100),
        "max_drawdown_pct": r(drawdown(sp) * 100),
        "ending_bn_from_1bn": r(spw.iloc[-1]),
        "correlation_monthly_with_fund": r(m["ret"].corr(sp_m)),
        "correlation_daily_with_fund": r(d["ret"].corr(sp)),
    }

    # Calendar years before and after costs, the hurdle and the S&P 500.
    cal = []
    for y in range(2021, 2027):
        s = slice(f"{y}-01-01", f"{y}-12-31")
        ms = [p for p in m.index if p.year == y]
        cal.append(
            {
                "year": y,
                "months": len(ms),
                "fund_after_costs_pct": ((1 + d.loc[s, "ret"]).prod() - 1) * 100,
                "fund_before_costs_pct": ((1 + before_d.loc[s]).prod() - 1) * 100,
                "hurdle_pct": ((1 + hurdle_m.loc[ms]).prod() - 1) * 100,
                "sp500_pct": ((1 + sp.loc[s]).prod() - 1) * 100,
            }
        )
    cy = pd.DataFrame(cal)
    cy["after_less_hurdle_pct"] = cy["fund_after_costs_pct"] - cy["hurdle_pct"]
    cy.to_csv(DATA / "calendar_years.csv", index=False, float_format="%.4f")
    out["calendar_years"] = [
        {k_: r(v, 4) if isinstance(v, float) else v for k_, v in x.items()}
        for x in cy.to_dict("records")
    ]
    out["calendar_years_note"] = (
        "2026 is January to August only; hurdle uses TB3MS / 1200 + 4% / 12"
    )

    # Stock P&L and average gross by year, two definitions of P&L.
    led = ledger.assign(year=pd.to_datetime(ledger["date"]).dt.year)
    stock_k = ["price", "dividend", "delta", "exit", "stub"]
    by_kind = led.pivot_table(index="year", columns="kind", values="dollars", aggfunc="sum") / 1e6
    dd = daily[daily.index >= "2020-12-31"].copy()
    dd["sp_nodiv"] = (dd.nav.diff() - dd.dividends - dd.interest + dd.cost + dd.borrow).fillna(0)
    sp_nodiv = (
        dd.loc[dd.index >= "2021-01-01", "sp_nodiv"]
        .groupby(dd.index[dd.index >= "2021-01-01"].year)
        .sum()
        / 1e6
    )
    gross_y = live["gross"].groupby(live.index.year).mean() * 100
    py = pd.DataFrame(
        {
            "stock_pnl_musd": by_kind[stock_k].sum(axis=1),
            "stock_pnl_ex_dividends_musd": sp_nodiv,
            "dividends_musd": by_kind["dividend"],
            "trading_cost_musd": -by_kind["cost"],
            "borrow_musd": -by_kind["borrow"],
            "interest_musd": d["interest"].groupby(d.index.year).sum() / 1e6,
            "avg_gross_pct": gross_y,
        }
    )
    py["pnl_per_100_gross_musd"] = py["stock_pnl_musd"] / py["avg_gross_pct"] * 100
    py.index.name = "year"
    py.to_csv(DATA / "pnl_by_year.csv", float_format="%.4f")
    out["pnl_by_year"] = [
        {"year": int(y)} | {k_: r(v, 3) for k_, v in row.items()} for y, row in py.iterrows()
    ]
    out["pnl_by_year_check"] = {
        str(y): {
            "given_pnl": GIVEN_PNL[y],
            "stock_pnl_musd": r(py.loc[y, "stock_pnl_musd"], 2),
            "ex_dividends_musd": r(py.loc[y, "stock_pnl_ex_dividends_musd"], 2),
            "given_gross": GIVEN_GROSS[y],
            "avg_gross_pct": r(py.loc[y, "avg_gross_pct"], 1),
        }
        for y in GIVEN_PNL
    }

    # Long and short legs: P&L by side, per dollar, and against the S&P 500.
    v = pos.pivot_table(index="date", columns="permno", values="value", aggfunc="sum")
    v = v.reindex(daily.index).fillna(0.0)
    vprev = v.shift(1).fillna(0.0)
    sl = led[led["kind"].isin(stock_k)].copy()
    sl["date"] = pd.to_datetime(sl["date"])
    pv = vprev.stack()
    pv = pv[pv != 0]
    cv = v.stack()
    cv = cv[cv != 0]
    key = pd.MultiIndex.from_arrays([sl["date"], sl["permno"]])
    side = np.sign(pv.reindex(key).to_numpy())
    side = np.where(np.isnan(side) | (side == 0), np.sign(cv.reindex(key).to_numpy()), side)
    sl["side"] = side
    unassigned = float(sl.loc[~np.isin(sl["side"], [1, -1]), "dollars"].sum())
    leg_pnl = sl.pivot_table(index="date", columns="side", values="dollars", aggfunc="sum")
    leg_pnl = leg_pnl.reindex(d.index).fillna(0.0)
    long_x = vprev.clip(lower=0).sum(axis=1).reindex(d.index)
    short_x = -vprev.clip(upper=0).sum(axis=1).reindex(d.index)
    ok = (long_x > 0) & (short_x > 0)
    r_long = (leg_pnl[1.0] / long_x).where(ok)
    r_short_stock = (-leg_pnl[-1.0] / short_x).where(ok)
    legs = {}
    for name, rr, pnl in (("long", r_long, leg_pnl[1.0]), ("short", r_short_stock, leg_pnl[-1.0])):
        rr = rr.dropna()
        spx = sp.reindex(rr.index)
        n = len(rr) / 252
        _, _, beta, _ = ols(rr, spx, 5)
        legs[name] = {
            "pnl_musd": r(pnl.sum() / 1e6, 3),
            "pnl_by_year_musd": {
                str(y): r(x / 1e6, 3) for y, x in pnl.groupby(pnl.index.year).sum().items()
            },
            "contribution_to_nav_pct_sum": r((pnl / prev).sum() * 100, 3),
            "stocks_return_per_dollar_cagr_pct": r(((1 + rr).prod() ** (1 / n) - 1) * 100, 3),
            "stocks_return_per_dollar_cumulative_pct": r(((1 + rr).prod() - 1) * 100, 3),
            "sp500_same_days_cagr_pct": r(((1 + spx).prod() ** (1 / n) - 1) * 100, 3),
            "stocks_less_sp500_cagr_pts": r(
                (((1 + rr).prod() ** (1 / n)) - ((1 + spx).prod() ** (1 / n))) * 100, 3
            ),
            "beta_of_stocks_to_sp500_daily": r(beta, 3),
            "avg_exposure_pct_nav": r(
                ((long_x if name == "long" else short_x) / prev).loc[rr.index].mean() * 100, 2
            ),
        }
    legs["short"]["note"] = (
        "short figures are the return of the stocks shorted; the book "
        "gains when they fall, so its P&L is minus that times exposure"
    )
    legs["unassigned_pnl_usd"] = r(unassigned, 2)
    legs["method"] = (
        "ledger lines price, dividend, delta, exit and stub by name and day; "
        "side from the prior close position (else the day's); per-dollar return "
        "is the leg's P&L over its prior-close dollar exposure; days from 2021-01-05"
    )
    out["legs"] = legs
    pd.DataFrame(
        {
            "long_stock_ret": r_long,
            "short_stock_ret": r_short_stock,
            "sp500": sp,
            "long_pnl": leg_pnl[1.0],
            "short_pnl": leg_pnl[-1.0],
        }
    ).to_csv(DATA / "legs_daily.csv", float_format="%.8f")

    # Daily and monthly hit rates and the win over loss ratio.
    lr = live["ret"]
    up, dn = lr[lr > 0], lr[lr < 0]
    out["hit_rate"] = {
        "days": int(len(lr)),
        "daily_hit_rate_pct": r(len(up) / len(lr) * 100, 3),
        "daily_avg_win_pct": r(up.mean() * 100, 4),
        "daily_avg_loss_pct": r(dn.mean() * 100, 4),
        "daily_win_loss_ratio": r(up.mean() / -dn.mean(), 4),
        "daily_profit_factor": r(up.sum() / -dn.sum(), 4),
        "best_day_pct": r(lr.max() * 100, 4),
        "worst_day_pct": r(lr.min() * 100, 4),
        "monthly_hit_rate_pct": r((m["ret"] > 0).mean() * 100, 3),
        "months_beating_hurdle_pct": r((active > 0).mean() * 100, 3),
        "months_beating_hurdle": int((active > 0).sum()),
        "months": int(len(m)),
    }

    # Turnover per rebalance and per year, with the holding period.
    tv = d["turnover"]
    tv_y = tv.groupby(tv.index.year).sum() * 100
    days_y = tv.groupby(tv.index.year).size()
    per_df = pd.DataFrame(
        {
            "formed": per.index,
            "first_trade": firsts.reindex(per.index).values,
            "one_way_turnover_pct": per.to_numpy() * 100,
        }
    )
    per_df.to_csv(DATA / "turnover_by_rebalance.csv", index=False, float_format="%.4f")
    out["turnover"] = {
        "per_rebalance_mean_pct": r(per.mean() * 100, 4),
        "per_rebalance_mean_without_build_pct": r(per.iloc[1:].mean() * 100, 4),
        "per_rebalance_median_pct": r(per.median() * 100, 4),
        "build_rebalance_pct": r(per.iloc[0] * 100, 4),
        "rebalances": int(len(per)),
        "rebalances_per_year": r(k, 3),
        "annual_with_build_pct": r(per.mean() * k * 100, 3),
        "annual_without_build_pct": r(per.iloc[1:].mean() * k * 100, 3),
        "annual_all_trade_days_pct": r(tv.sum() / (len(d) / 252) * 100, 3),
        "by_calendar_year_pct": {str(y): r(x, 3) for y, x in tv_y.items()},
        "by_calendar_year_annualised_pct": {
            str(y): r(tv_y[y] / days_y[y] * 252, 3) for y in tv_y.index
        },
        "definition": "one way, half the sum of |w - w carried| a day, as table row 17",
    }
    out["holding_period"] = {
        "weighted_sessions": r(held, 3),
        "plain_mean_sessions": r(plain, 3),
        "weighted_years": r(held / 252, 3),
        "definition": "runs of one name and one side, weighted by mean weight",
    }

    # Weights of every name on every held day, and the average weight.
    w = weights(pos[pos["date"].isin(live.index)], live["nav"])
    avg = w.mean()
    held_days = (w != 0).sum()
    hold = pd.DataFrame(
        {
            "avg_weight_pct": avg * 100,
            "days_held": held_days,
            "max_abs_weight_pct": w.abs().max() * 100,
        }
    ).join(nm)
    hold.index.name = "permno"
    top = hold.sort_values("avg_weight_pct", ascending=False).head(10)
    bot = hold.sort_values("avg_weight_pct").head(10)
    pd.concat([top.assign(group="top"), bot.assign(group="bottom")]).to_csv(
        DATA / "holdings_top_bottom.csv", float_format="%.5f"
    )
    out["holdings_by_average_weight"] = {
        "definition": "mean of daily weight over all 1,421 held days, zero when not held",
        "top10": [
            {
                "permno": int(p),
                "ticker": x.Ticker,
                "name": x.Name,
                "avg_weight_pct": r(x.avg_weight_pct, 4),
                "days_held": int(x.days_held),
            }
            for p, x in top.iterrows()
        ],
        "bottom10": [
            {
                "permno": int(p),
                "ticker": x.Ticker,
                "name": x.Name,
                "avg_weight_pct": r(x.avg_weight_pct, 4),
                "days_held": int(x.days_held),
            }
            for p, x in bot.iterrows()
        ],
        "names_ever_held": int((held_days > 0).sum()),
    }

    # P&L by name: stock lines, then net of its trading cost and borrow.
    byn = led.pivot_table(index="permno", columns="kind", values="dollars", aggfunc="sum").fillna(0)
    con = pd.DataFrame(
        {
            "stock_pnl_musd": byn[[c for c in stock_k if c in byn]].sum(axis=1) / 1e6,
            "net_pnl_musd": byn.sum(axis=1) / 1e6,
        }
    ).join(nm)
    con["side_mostly"] = np.where(w.reindex(columns=con.index).sum() >= 0, "long", "short")
    con.index.name = "permno"
    con.sort_values("net_pnl_musd").to_csv(DATA / "contributors_all.csv", float_format="%.4f")
    best = con.sort_values("net_pnl_musd", ascending=False).head(10)
    worst = con.sort_values("net_pnl_musd").head(10)
    out["contributors"] = {
        "definition": "ledger P&L by name over the window, net of its own trading cost and "
        "borrow; stock_pnl is before those costs",
        "top10": [
            {
                "permno": int(p),
                "ticker": x.Ticker,
                "name": x.Name,
                "side": x.side_mostly,
                "net_pnl_musd": r(x.net_pnl_musd, 3),
                "stock_pnl_musd": r(x.stock_pnl_musd, 3),
            }
            for p, x in best.iterrows()
        ],
        "bottom10": [
            {
                "permno": int(p),
                "ticker": x.Ticker,
                "name": x.Name,
                "side": x.side_mostly,
                "net_pnl_musd": r(x.net_pnl_musd, 3),
                "stock_pnl_musd": r(x.stock_pnl_musd, 3),
            }
            for p, x in worst.iterrows()
        ],
        "top10_share_of_stock_pnl_pct": r(
            best["net_pnl_musd"].sum() / con["net_pnl_musd"].sum() * 100, 2
        ),
        "total_net_pnl_musd": r(con["net_pnl_musd"].sum(), 3),
    }

    # The short book's caps and dollar volumes, each short and day.
    adv = pd.read_parquet(S.CACHE / "market_adv.parquet").set_index("date")
    adv.index, adv.columns = pd.to_datetime(adv.index), adv.columns.astype(int)
    sh = pos[(pos["value"] < 0) & pos["date"].isin(live.index)].merge(
        caps, on=["date", "permno"], how="left"
    )
    adv_long = adv.stack()
    adv_long.index.names = ["date", "permno"]
    adv_long = adv_long.rename("adv").reset_index()
    sh = sh.merge(adv_long, on=["date", "permno"], how="left")
    sh["adv_musd"] = sh["adv"] / 1e6
    sh[["date", "permno", "value", "me", "adv_musd"]].to_csv(
        DATA / "short_book_cap_adv.csv", index=False, float_format="%.4f"
    )
    q = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0]
    out["short_book"] = {
        "position_days": int(len(sh)),
        "with_cap": int(sh["me"].notna().sum()),
        "with_adv": int(sh["adv"].notna().sum()),
        "cap_musd_quantiles": {str(x): r(sh["me"].quantile(x), 1) for x in q},
        "adv_musd_quantiles": {str(x): r(sh["adv_musd"].quantile(x), 3) for x in q},
        "share_under_1bn_cap_pct": r((sh["me"] < 1000).mean() * 100, 3),
        "under_500m_cap": int((sh["me"] < 500).sum()),
        "row20_median_of_daily_medians_musd": r(by_day.median().median(), 1),
        "floor_musd": 500,
        "cap_source": "short_caps.parquet (engine's daily cap of each short, US$ m)",
        "adv_source": "cache/market_adv.parquet (dollar ADV the engine sizes by)",
    }

    # Position size in days of ADV, long and short apart.
    allp = pos[pos["date"].isin(live.index)].merge(adv_long, on=["date", "permno"], how="left")
    allp["days_adv"] = allp["value"].abs() / allp["adv"]
    allp["side"] = np.where(allp["value"] > 0, "long", "short")
    allp[["date", "permno", "side", "value", "adv", "days_adv"]].to_csv(
        DATA / "days_of_adv.csv", index=False, float_format="%.6f"
    )
    qa = [0.5, 0.9, 0.95, 0.99, 1.0]
    out["days_of_adv"] = {
        s: {
            "position_days": int((allp["side"] == s).sum()),
            "mean": r(allp.loc[allp["side"] == s, "days_adv"].mean(), 5),
            "quantiles": {
                str(x): r(allp.loc[allp["side"] == s, "days_adv"].quantile(x), 5) for x in qa
            },
            "share_over_1_day_pct": r(
                (allp.loc[allp["side"] == s, "days_adv"] > 1).mean() * 100, 4
            ),
        }
        for s in ("long", "short")
    }
    out["days_of_adv"]["missing_adv"] = int(allp["adv"].isna().sum())
    out["days_of_adv"]["engine_daily_max_compliance"] = r(comp["days_of_adv_max"].max(), 5)

    # Sector net at every rebalance, GICS from the organisers' panel.
    panel = pd.read_parquet(S.PANEL, columns=["permno", "eom", "gics", "sic", "me"])
    panel["eom"] = pd.to_datetime(panel["eom"]) + pd.offsets.MonthEnd(0)
    panel["s"] = panel["gics"].astype("Int64").astype(str).str[:2]
    t = targets.assign(T=pd.to_datetime(targets["T"]))
    t = t[t["target"] != 0]
    tw = t.pivot_table(index="T", columns="permno", values="target", aggfunc="sum").fillna(0)
    sec = panel_asof(panel, tw.index, tw.columns)
    rows_s = []
    for dt, row in tw.iterrows():
        held_ = row[row != 0]
        s_ = sec.loc[dt].reindex(held_.index).fillna("NA")
        net = held_.groupby(s_.values).sum()
        for code, val in net.items():
            rows_s.append(
                {
                    "rebalance": dt,
                    "gics": code,
                    "sector": GICS.get(code, "Unknown"),
                    "net_pct": val * 100,
                }
            )
    secdf = pd.DataFrame(rows_s)
    secdf.to_csv(DATA / "sector_net_by_rebalance.csv", index=False, float_format="%.5f")
    known = secdf[secdf["gics"] != "NA"]
    mx = known.groupby("rebalance")["net_pct"].apply(lambda x: x.abs().max())
    out["sector_net"] = {
        "rebalances": int(secdf["rebalance"].nunique()),
        "max_abs_net_pct": r(mx.max(), 4),
        "median_of_rebalance_max_pct": r(mx.median(), 4),
        "rebalances_with_a_sector_over_1pct": int((mx > 1 + 1e-9).sum()),
        "sectors_min": int(known.groupby("rebalance")["gics"].nunique().min()),
        "limit_pct": 20,
        "band_pct": 1,
        "check_compliance_check_json_pct": r(cc["rebalance_sector_net_max"] * 100, 4),
        "max_by_sector_pct": {
            GICS[c]: r(g["net_pct"].abs().max(), 4) for c, g in known.groupby("gics")
        },
        "unknown_sector_weight": r(secdf.loc[secdf["gics"] == "NA", "net_pct"].abs().sum(), 4),
    }

    # Realised vol, rolling 63 days and full period, against 12%.
    vol63 = d["ret"].rolling(63).std() * np.sqrt(252) * 100
    out["volatility"] = {
        "full_period_monthly_pct": r(head["vol_monthly_pct"], 4),
        "full_period_daily_pct": r(head["vol_daily_pct"], 4),
        "rolling63_max_pct": r(vol63.max(), 4),
        "rolling63_min_pct": r(vol63.min(), 4),
        "rolling63_max_date": str(vol63.idxmax().date()),
        "ceiling_pct": 12,
    }

    # Rolling 252-day beta to the S&P 500 on daily excess returns.
    y_ex, x_ex = d["ret"] - d["rf"], sp - d["rf"]
    cov = y_ex.rolling(252).cov(x_ex)
    beta252 = cov / x_ex.rolling(252).var()
    out["rolling_beta"] = {
        "window_sessions": 252,
        "max": r(beta252.max(), 4),
        "min": r(beta252.min(), 4),
        "last": r(beta252.dropna().iloc[-1], 4),
        "full_period_daily_beta": r(bd, 4),
        "engine_compliance_last": r(comp["beta_sp500_252d"].dropna().iloc[-1], 4),
        "engine_compliance_max_abs": r(comp["beta_sp500_252d"].abs().max(), 4),
    }

    # Daily paths: growth of $1bn, hurdle, S&P 500, active, drawdown.
    nav_path = start * (1 + d["ret"]).cumprod()
    nsess = d.groupby(d.index.to_period("M")).size()
    h_daily = (1 + hurdle_m.reindex(d.index.to_period("M")).to_numpy()) ** (
        1 / nsess.reindex(d.index.to_period("M")).to_numpy()
    ) - 1
    h_path = start * np.cumprod(1 + h_daily)
    sp_path = start * (1 + sp).cumprod()
    wealth = (1 + d["ret"]).cumprod()
    paths = pd.DataFrame(
        {
            "fund_nav": nav_path,
            "fund_nav_file": d["nav"],
            "hurdle": h_path,
            "sp500": sp_path,
            "active_vs_hurdle_pct": (nav_path / h_path - 1) * 100,
            "fund_cum_pct": (wealth - 1) * 100,
            "hurdle_cum_pct": (h_path / start - 1) * 100,
            "sp500_cum_pct": (sp_path / start - 1) * 100,
            "drawdown_pct": (wealth / np.maximum(wealth.cummax(), 1) - 1) * 100,
            "gross_pct": d["gross"] * 100,
            "net_pct": d["net"] * 100,
            "names": d["n_long"] + d["n_short"],
            "n_long": d["n_long"],
            "n_short": d["n_short"],
            "vol63_pct": vol63,
            "beta252": beta252,
            "beta252_engine": comp["beta_sp500_252d"].reindex(d.index),
            "before_costs_ret": before_d,
            "ret": d["ret"],
            "sp500_ret": sp,
        }
    )
    paths.to_csv(DATA / "daily_paths.csv", float_format="%.8f")
    out["paths"] = {
        "active_vs_hurdle_end_pct": r(paths["active_vs_hurdle_pct"].iloc[-1], 4),
        "active_vs_hurdle_min_pct": r(paths["active_vs_hurdle_pct"].min(), 4),
        "active_vs_hurdle_max_pct": r(paths["active_vs_hurdle_pct"].max(), 4),
        "fund_end_bn": r(nav_path.iloc[-1] / 1e9),
        "hurdle_end_bn": r(h_path[-1] / 1e9),
        "sp500_end_bn": r(sp_path.iloc[-1] / 1e9),
        "max_dd_date": str(paths["drawdown_pct"].idxmin().date()),
        "nav_file_vs_compounded_max_abs_usd": r((nav_path - d["nav"]).abs().max(), 2),
    }

    # The 17 crises, from crises.json, which tools/pack/crises.py writes.
    cj = json.loads((S.OUT / "crises.json").read_text())
    out["crises"] = {
        "source": "crises.json, written by tools/pack/crises.py",
        "fill_note": cj["fill_note"],
    }
    out["crises"]["peer_fill"] = {k: v for k, v in cj["peer_fill"].items() if k != "crises"}

    # 60/40 and the mixes beside the fund.
    s_, b_, f_ = yahoo("SPY"), yahoo("AGG"), m["ret"]
    assert len(s_) == len(b_) == len(f_) == 68
    six = {
        "window": "2021-01 to 2026-08, 68 months, each mix rebalanced monthly",
        "legs": {
            "stocks": "SPY adjusted close (dividends in)",
            "bonds": "AGG adjusted close",
            "fund": "QUARCC Purple after all costs, daily returns compounded by month",
            "bill": "TB3MS / 1200",
        },
        "legs_stats": {k_: stats(x, b) for k_, x in (("stocks", s_), ("bonds", b_), ("fund", f_))},
        "mixes": {k_: stats(ws * s_ + wb * b_ + wf * f_, b) for k_, (ws, wb, wf) in MIXES.items()},
        "correlations": {
            "fund_stocks": r(f_.corr(s_), 4),
            "fund_bonds": r(f_.corr(b_), 4),
            "stocks_bonds": r(s_.corr(b_), 4),
        },
    }
    yrs = []
    for y in range(2021, 2027):
        sl_ = slice(f"{y}-01", f"{y}-12")
        mix = 0.6 * s_ + 0.4 * b_
        yrs.append(
            {"year": y}
            | {
                k_: r(((1 + x.loc[sl_]).prod() - 1) * 100, 4)
                for k_, x in (
                    ("sp500_spy", s_),
                    ("bonds_agg", b_),
                    ("sixty_forty", mix),
                    ("fund", f_),
                )
            }
        )
    six["calendar_years_pct"] = yrs
    pd.DataFrame(yrs).to_csv(DATA / "sixty_forty_years.csv", index=False, float_format="%.4f")
    out["sixty_forty"] = six

    (S.OUT / "numbers.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    bad = {k_: v_ for k_, v_ in checks.items() if not v_["match"]}
    print(json.dumps({"mismatches": bad, "pnl_check": out["pnl_by_year_check"]}, indent=1))


if __name__ == "__main__":
    main()
