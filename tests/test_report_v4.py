# The final-run report on synthetic frames: the table and Arcana files.

import re

import numpy as np
import pandas as pd
import pytest

from fiam.v4.report import holdings, table_9_1

# Twelve daily returns, two a month from January to June 2021.
RETS = [0.10, -0.05, -0.20, 0.10, 0.05, 0.05, 0.02, 0.02, -0.03, 0.01, 0.04, -0.01]
DAYS = [f"2021-{m:02d}-{d:02d}" for m in range(1, 7) for d in (4, 5)]
START = 1e9


# The numbers in a cell such as "1.000 (0.000)" or "avg 5.5, min 4".
def nums(cell) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", str(cell))]


# The tiny run: nav, returns, costs, exposures and trade flags by day.
def tiny():
    index = pd.DatetimeIndex(["2020-12-31", *DAYS])
    ret = pd.Series([0.0, *RETS], index=index)
    nav = START * (1 + ret).cumprod()
    daily = pd.DataFrame({"nav": nav, "ret": ret}, index=index)
    daily["rf"] = 0.0
    daily["cost"] = 0.0
    daily["borrow"] = 0.0
    daily.loc["2021-01-04", "cost"] = 1e6
    daily.loc["2021-01-05", "borrow"] = 5e5
    daily["gross"] = [0.0, 1.0, 1.2, 1.4, 1.0, 1.1, 1.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    daily["net"] = [0.0, 0.1, 0.2, 0.0, 0.1, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    daily["n_long"] = [0, 3, 4, 5, 4, 3, 3, 3, 3, 3, 3, 3, 3]
    daily["n_short"] = [0, 2, 2, 1, 3, 2, 2, 2, 2, 2, 2, 2, 2]
    traded = ["2021-01-04", "2021-01-05", "2021-02-04", "2021-02-05", "2021-03-04",
              "2021-04-04", "2021-05-04", "2021-06-04"]  # fmt: skip
    daily["traded"] = daily.index.isin(pd.to_datetime(traded))
    daily["turnover"] = 0.0
    for day, t in zip(traded, [0.5, 0.02, 0.2, 0.05, 0.3, 0.1, 0.1, 0.1]):
        daily.loc[day, "turnover"] = t
    formed = ["2020-12-31", "2021-01-05", "2021-01-29", "2021-01-29", "2021-02-26",
              "2021-03-31", "2021-04-30", "2021-05-31"]  # fmt: skip
    trades = pd.DataFrame(
        {
            "date": pd.to_datetime(traded),
            "formed": pd.to_datetime(formed),
            "permno": 1,
            "dollars": 1e6,
            "after": 1e6,
        }  # fmt: skip
    )
    rows = []
    for day in DAYS:
        scale = daily.loc[day, "nav"]
        rows += [(day, 1, 0.1 * scale), (day, 2, -0.1 * scale)]
        if day in ("2021-01-04", "2021-01-05"):
            rows.append((day, 3, 0.05 * scale))
    positions = pd.DataFrame(rows, columns=["date", "permno", "value"])
    positions["date"] = pd.to_datetime(positions["date"])
    return daily, trades, positions, ret.iloc[1:].copy()


# Monthly returns and the daily NAV path as plain loops.
def by_hand():
    month = [(1 + RETS[2 * i]) * (1 + RETS[2 * i + 1]) - 1 for i in range(6)]
    path = [1.0]
    for r in RETS:
        path.append(path[-1] * (1 + r))
    return month, path


# The table's rows keyed by row number.
def rows_of(**kw):
    daily, trades, positions, bench = tiny()
    return table_9_1.table(daily, trades, positions, bench, **kw).set_index("row")


# The 23 rows come in order with the five columns.
def test_table_shape():
    t = table_9_1.table(*tiny())
    assert list(t.columns) == ["row", "name", "strategy", "benchmark", "note"]
    assert list(t["row"]) == list(range(1, 24))


# Ending value, cumulative return and the hurdle path by hand.
def test_ending_value_and_cumulative():
    t = rows_of()
    month, path = by_hand()
    assert t.loc[1, "strategy"] == pytest.approx(path[-1])
    assert t.loc[2, "strategy"] == pytest.approx((path[-1] - 1) * 100)
    hurdle = (1 + 0.04 / 12) ** 6
    assert t.loc[1, "benchmark"] == pytest.approx(hurdle)
    assert t.loc[2, "benchmark"] == pytest.approx((hurdle - 1) * 100)


# Arithmetic and CAGR in one cell, and the monthly volatility.
def test_return_and_volatility():
    t = rows_of()
    month, path = by_hand()
    arith, cagr = nums(t.loc[3, "strategy"])
    assert arith == pytest.approx(np.mean(month) * 1200, abs=0.01)
    assert cagr == pytest.approx((path[-1] ** 2 - 1) * 100, abs=0.01)
    assert t.loc[4, "strategy"] == pytest.approx(np.std(month, ddof=1) * np.sqrt(12) * 100)
    assert t.loc[4, "benchmark"] == pytest.approx(0.0, abs=1e-9)


# Sharpe is the monthly excess mean over its sd times root 12.
def test_sharpe():
    t = rows_of()
    month, _ = by_hand()
    assert t.loc[8, "strategy"] == pytest.approx(np.mean(month) / np.std(month, ddof=1) * 12**0.5)
    assert t.loc[8, "benchmark"] == "undefined, constant excess"


# Drawdown, worst month and worst day, strategy and hurdle.
def test_drawdown_and_losses():
    t = rows_of()
    month, path = by_hand()
    low = min(p / max(path[: i + 1]) - 1 for i, p in enumerate(path))
    assert low == pytest.approx(-0.24)
    assert t.loc[11, "strategy"] == pytest.approx(low * 100)
    assert t.loc[11, "benchmark"] == pytest.approx(0.0)
    assert t.loc[12, "strategy"] == pytest.approx(min(month) * 100)
    assert t.loc[12, "benchmark"] == pytest.approx(0.04 / 12 * 100)
    assert t.loc[13, "strategy"] == pytest.approx(-20.0)
    assert t.loc[13, "benchmark"] == pytest.approx(0.04 / 252 * 100)


# A book that copies the benchmark has a beta of 1 and no alpha.
def test_beta_of_a_copy_is_one():
    t = rows_of()
    for row in (6, 7):
        beta, se = nums(t.loc[row, "strategy"])
        assert beta == pytest.approx(1.0, abs=1e-6)
        assert se == pytest.approx(0.0, abs=1e-6)
    assert nums(t.loc[5, "strategy"])[0] == pytest.approx(0.0, abs=1e-6)
    assert nums(t.loc[7, "note"])[-1] == pytest.approx(1.0, abs=1e-3)


# The regression recovers a known beta and alpha with Newey-West errors.
def test_ols_known_line():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.standard_normal(200) * 0.01)
    y = 0.001 + 0.7 * x + pd.Series(rng.standard_normal(200) * 1e-4)
    a, a_se, b, b_se = table_9_1.ols(y, x, 3)
    assert a == pytest.approx(0.001, abs=1e-4)
    assert b == pytest.approx(0.7, abs=0.01)
    assert a_se > 0 and b_se > 0


# Row 9 adds the day's cost and borrow back over the last NAV.
def test_ir_before_costs_exceeds_net():
    daily, trades, positions, bench = tiny()
    t = table_9_1.table(daily, trades, positions, bench).set_index("row")
    month, _ = by_hand()
    ret = np.array(RETS)
    add = np.zeros(12)
    add[0], add[1] = 1e6 / 1e9, 5e5 / (1e9 * 1.1)
    gross = [(1 + a) * (1 + b) - 1 for a, b in zip(ret[::2] + add[::2], ret[1::2] + add[1::2])]
    active = np.array(gross) - 0.04 / 12
    assert t.loc[9, "strategy"] == pytest.approx(active.mean() / active.std(ddof=1) * 12**0.5)
    net = np.array(month) - 0.04 / 12
    assert t.loc[10, "strategy"] == pytest.approx(net.std(ddof=1) * 12**0.5 * 100)
    assert nums(t.loc[23, "strategy"])[0] == pytest.approx(
        net.mean() / net.std(ddof=1) * 12**0.5, abs=0.01
    )
    assert t.loc[9, "strategy"] > nums(t.loc[23, "strategy"])[0]


# Positions, gross and net by day, from the first trade day.
def test_exposure_rows():
    t = rows_of()
    daily, *_ = tiny()
    names = (daily["n_long"] + daily["n_short"]).iloc[1:]
    assert nums(t.loc[14, "strategy"]) == [round(names.mean(), 1), names.min(), names.max()]
    gross = daily["gross"].iloc[1:]
    assert nums(t.loc[15, "strategy"]) == [round(gross.mean() * 100, 1), gross.max() * 100]
    net = daily["net"].iloc[1:]
    assert nums(t.loc[16, "strategy"]) == [
        round(net.mean() * 100, 1),
        net.min() * 100,
        net.max() * 100,  # fmt: skip
    ]


# Each traded day goes to the rebalance before it; overlays join it.
def test_turnover_groups():
    daily, trades, *_ = tiny()
    per = table_9_1.turnover_by_rebalance(daily.iloc[1:], trades)
    assert list(per.round(4)) == [0.52, 0.25, 0.30, 0.10, 0.10, 0.10]
    firsts = table_9_1.rebalances(trades)
    assert list(firsts.index) == list(pd.to_datetime(
        ["2020-12-31", "2021-01-29", "2021-02-26", "2021-03-31", "2021-04-30", "2021-05-31"]
    ))  # fmt: skip


# Two years of monthly rebalances annualise by 12, build in or out.
def test_turnover_row_monthly():
    days = pd.bdate_range("2021-01-01", "2022-12-30")
    daily = pd.DataFrame(index=days)
    first = pd.Series(days, index=days).groupby(days.to_period("M")).first()
    daily["traded"] = days.isin(first)
    daily["turnover"] = np.where(daily["traded"], 0.1, 0.0)
    daily.loc[first.iloc[0], "turnover"] = 0.5
    ends = [first.iloc[i] - pd.offsets.BDay(1) for i in range(len(first))]
    trades = pd.DataFrame({"date": first.to_numpy(), "formed": ends})
    cell, _, note = table_9_1.turnover_cell(daily, trades, len(days) / 252)
    with_build, without, every = nums(cell)
    assert with_build == pytest.approx((0.5 + 0.1 * 23) / 24 * 12 * 100, abs=0.5)
    assert without == pytest.approx(120, abs=0.5)
    assert every == pytest.approx(2.8 / (len(days) / 252) * 100, abs=0.5)
    assert "x 12 a year" in note


# Holding runs break at a gap or a flip and weight by mean weight.
def test_holding_period():
    idx = pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07"])
    daily = pd.DataFrame({"nav": 100.0}, index=idx)
    rows = [(i, 1, 10.0) for i in idx[:4]]
    rows += [(i, 2, 10.0) for i in idx[:2]] + [(idx[3], 2, 10.0)]
    rows += [(idx[0], 3, -5.0), (idx[1], 3, -5.0), (idx[2], 3, 5.0)]
    p = pd.DataFrame(rows, columns=["date", "permno", "value"])
    held, plain = table_9_1.holding_period(p, daily)
    # Runs: 4 at .10, 2 at .10, 1 at .10, 2 at .05, 1 at .05.
    assert held == pytest.approx((4 * 0.1 + 2 * 0.1 + 1 * 0.1 + 2 * 0.05 + 1 * 0.05) / 0.4)
    assert plain == pytest.approx(10 / 5)


# Position size is the mean |value|; the short book's cap needs caps.
def test_size_and_caps():
    daily, trades, positions, bench = tiny()
    t = rows_of()
    assert t.loc[19, "strategy"] == pytest.approx(positions["value"].abs().mean() / 1e6)
    assert t.loc[20, "strategy"] == "needs caps"
    days = daily.index[daily["traded"]]
    caps = pd.DataFrame(
        {"date": days, "permno": 2, "me": [1000, 1200, 800, 900, 1100, 700, 600, 1000]}
    )
    t = table_9_1.table(daily, trades, positions, bench, caps=caps).set_index("row")
    # Every trade day holds the short, so the median runs over all of them.
    got = caps["me"]
    assert float(t.loc[20, "strategy"]) == pytest.approx(got.median(), abs=0.5)
    assert f"minimum {got.min():.0f}" in t.loc[20, "note"]


# Cost and borrow rates are the booked dollars over the last NAV.
def test_cost_and_borrow_rows():
    t = rows_of()
    assert t.loc[21, "strategy"] == pytest.approx(1e6 / 1e9 / 12 * 252 * 100)
    assert t.loc[22, "strategy"] == pytest.approx(5e5 / (1e9 * 1.1) / 12 * 252 * 100)


# The endowment row and September never enter a statistic.
def test_window_and_missing_bench():
    daily, trades, positions, bench = tiny()
    with pytest.raises(ValueError):
        table_9_1.table(daily, trades, positions, bench.iloc[:-1])
    late = daily.iloc[-1:].rename(index={daily.index[-1]: pd.Timestamp("2026-09-01")})
    bigger = pd.concat([daily, late.assign(ret=-0.5)])
    sp = pd.concat([bench, pd.Series([0.0], index=late.index)])
    base = table_9_1.table(daily, trades, positions, bench).set_index("row")
    more = table_9_1.table(bigger, trades, positions, sp).set_index("row")
    assert more.loc[13, "strategy"] == base.loc[13, "strategy"]


# The ISIN check digit on two known numbers.
def test_isin_check_digit():
    assert holdings.isin_check_digit("US037833100") == "5"
    assert holdings.isin("037833100") == "US0378331005"
    assert holdings.isin("594918104") == "US5949181045"
    assert holdings.isin(None) is None
    assert holdings.isin("1234") is None


# Bloomberg names, with a share class after a slash.
def test_bloomberg_names():
    assert holdings.bloomberg("MSFT", "MSFT", None) == "MSFT US Equity"
    assert holdings.bloomberg("BRK", "BRKA", "A") == "BRK/A US Equity"
    assert holdings.bloomberg("FB", "FB", "A") == "FB US Equity"
    assert holdings.bloomberg(None, "X", None) is None


# A small links table: one stock whose ticker changes, one with no ids.
def links_table():
    # One links row with its dates.
    def row(permno, kind, value, start, end=None):
        return (permno, kind, value, pd.Timestamp(start), pd.Timestamp(end) if end else pd.NaT)

    rows = [
        row(1, "ticker", "MSFT", "1986-03-13"), row(1, "symbol", "MSFT", "1986-03-13"),
        row(1, "cusip", "594918104", "1986-03-13"),
        row(1, "name", "MICROSOFT CORP (Last Known)", "1986-03-13"),
        row(2, "ticker", "OLD", "2000-01-01", "2021-01-31"),
        row(2, "ticker", "NEW", "2021-02-01"),
        row(2, "cusip", "037833100", "2000-01-01"), row(2, "name", "APPLE INC", "2000-01-01"),
    ]  # fmt: skip
    cols = ["permno", "kind", "value", "valid_from", "valid_to"]
    return pd.DataFrame(rows, columns=cols).astype({"valid_from": "datetime64[ns]",
                                                    "valid_to": "datetime64[ns]"})  # fmt: skip


# Identifiers follow the date, drop the last-known tag, add the ISIN.
def test_identifiers_by_date():
    ids = holdings.identifiers([1, 2, 2, 3], pd.to_datetime(
        ["2021-01-04", "2021-01-04", "2021-02-04", "2021-01-04"]), links_table())  # fmt: skip
    got = ids.set_index(["permno", "date"])
    assert got.loc[(1, pd.Timestamp("2021-01-04")), "ticker"] == "MSFT US Equity"
    assert got.loc[(1, pd.Timestamp("2021-01-04")), "isin"] == "US5949181045"
    assert got.loc[(1, pd.Timestamp("2021-01-04")), "name"] == "MICROSOFT CORP"
    assert got.loc[(2, pd.Timestamp("2021-01-04")), "ticker"] == "OLD US Equity"
    assert got.loc[(2, pd.Timestamp("2021-02-04")), "ticker"] == "NEW US Equity"
    assert pd.isna(got.loc[(3, pd.Timestamp("2021-01-04")), "ticker"])


# Weights by trade day: they sum to the net, shorts below zero.
def holdings_case():
    daily, trades, positions, _ = tiny()
    day = [pd.Timestamp(x) for x in ("2021-01-04", "2021-02-04")]
    held = positions[positions["date"].isin(day)].copy()
    held.loc[held["permno"] == 3, "permno"] = 9
    ids = holdings.identifiers(held["permno"], held["date"], links_table())
    return daily, trades, held, ids


# The weights file keeps the net, the sign, the AUM and the trade date.
def test_weights_file_sums_to_net():
    daily, trades, held, ids = holdings_case()
    file, _ = holdings.weights_file(held, daily, ids)
    assert list(file.columns[:7]) == holdings.WEIGHTS
    jan = file[file["Date"] == "2021-01-04"]
    nav = daily.loc["2021-01-04", "nav"]
    assert jan["Weights"].sum() == pytest.approx(
        held[held["date"] == "2021-01-04"]["value"].sum() / nav
    )
    assert (file.loc[file["PERMNO"] == 2, "Weights"] < 0).all()
    assert (file.loc[file["PERMNO"] == 2, "Custom Tag"] == "short").all()
    assert (file["AUM"] == file["Date"].map(daily["nav"].rename(lambda d: f"{d:%Y-%m-%d}"))).all()
    assert (file["Asset Class"] == "Equity").all()
    assert file.loc[file["PERMNO"] == 1, "ISIN"].iloc[0] == "US5949181045"


# A name with no ids stays in the file and is listed as unresolved.
def test_unresolved_name_kept():
    daily, trades, held, ids = holdings_case()
    file, bad = holdings.weights_file(held, daily, ids)
    ninth = file[file["PERMNO"] == 9]
    assert len(ninth) == 1 and ninth["Ticker"].iloc[0] == "" and ninth["ISIN"].iloc[0] == ""
    assert (bad["PERMNO"] == 9).any()
    row = bad[bad["PERMNO"] == 9].iloc[0]
    assert row["Weights"] == pytest.approx(ninth["Weights"].iloc[0])
    assert row["ticker_missing"] and row["isin_missing"]
    assert len(file) == len(held)


# The date is the trade day, never the formation day.
def test_date_convention_is_trade_day():
    daily, trades, held, ids = holdings_case()
    assert holdings.monthly_days(trades)[0] == pd.Timestamp("2021-01-04")
    assert pd.Timestamp("2020-12-31") not in holdings.trade_days(trades)
    assert list(holdings.monthly_days(trades)) == list(pd.to_datetime(
        ["2021-01-04", "2021-02-04", "2021-03-04", "2021-04-04", "2021-05-04", "2021-06-04"]
    ))  # fmt: skip
    assert len(holdings.trade_days(trades)) == 8
    file, _ = holdings.weights_file(held, daily, ids, dates=holdings.monthly_days(trades))
    assert set(file["Date"]) == {"2021-01-04", "2021-02-04"}


# The positions file: dollars held, the day's net P&L, a closed name.
def test_positions_file_pnl():
    daily, trades, held, ids = holdings_case()
    ledger = pd.DataFrame(
        [("2021-01-04", 1, "price", 5.0), ("2021-01-04", 1, "cost", -1.5),
         ("2021-01-04", 2, "borrow", -0.5), ("2021-01-04", 7, "price", 2.0)],
        columns=["date", "permno", "kind", "dollars"],
    )  # fmt: skip
    ledger["date"] = pd.to_datetime(ledger["date"])
    ids = holdings.identifiers([1, 2, 7, 9], pd.to_datetime(["2021-01-04"] * 4), links_table())
    file, bad = holdings.positions_file(held, ledger, ids, daily)
    jan = file[file["Date"] == "2021-01-04"].set_index("PERMNO")
    assert list(file.columns[:8]) == holdings.POSITIONS
    assert jan.loc[1, "PNL"] == pytest.approx(3.5)
    assert jan.loc[2, "PNL"] == pytest.approx(-0.5)
    assert jan.loc[2, "Net Invested"] < 0
    assert jan.loc[7, "Net Invested"] == 0 and jan.loc[7, "PNL"] == 2.0
    assert jan.loc[7, "Custom Tag"] == "closed"
    assert set(bad["PERMNO"]) >= {7, 9}


# The CSV carries the template's columns; our copy adds PERMNO and name.
def test_write_csv(tmp_path):
    daily, trades, held, ids = holdings_case()
    file, _ = holdings.weights_file(held, daily, ids)
    path = holdings.write_csv(file, tmp_path / "weights.csv", holdings.WEIGHTS)
    arcana = pd.read_csv(path, dtype=str, keep_default_na=False)
    own = pd.read_csv(tmp_path / "weights_own.csv", dtype=str, keep_default_na=False)
    assert list(arcana.columns) == holdings.WEIGHTS
    assert list(own.columns) == holdings.WEIGHTS + holdings.OWN
