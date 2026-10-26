# The v4 engine (PLAN §18 step 5): the book, universe, betas, inputs.

import numpy as np
import pandas as pd
import pytest

from fiam.v4 import betas, clock, daily_book, data, inputs, sources, universe

RULES = dict(names_min=1, names_max=500, gross=2.0, net_band=0.5, name_cap=0.6)
RULES |= dict(short_min_market_cap=500.0, nav_start=1e9, lag_days=1)


# A small registry stand-in: sessions, dsf, CRSP, panel and exits.
class Fake:
    # Weekday sessions with a flat bill rate and no stocks yet.
    def __init__(self, start="2019-01-01", end="2019-04-30", rf=0.0):
        self.days = pd.bdate_range(start, end).as_unit("ns")
        self.rf = rf
        self.dsf_rows, self.crsp_rows, self.panel_rows, self.exit_rows = [], [], [], []

    # One stock: daily price returns, days the dsf or CRSP lack, its cap.
    def stock(self, permno, ret=0.0, no_dsf=(), no_crsp=(), me=1000.0, crsp_ret=None):
        r = pd.Series(ret, index=self.days, dtype=float)
        total = r.copy() if crsp_ret is None else pd.Series(crsp_ret, index=self.days)
        no_dsf, no_crsp = pd.DatetimeIndex(no_dsf), pd.DatetimeIndex(no_crsp)
        price = 10 * (1 + r).cumprod()
        for d in self.days:
            if d not in no_dsf:
                self.dsf_rows.append((permno, d, r[d], False, price[d]))
            if d not in no_crsp:
                self.crsp_rows.append((permno, d, total[d], r[d]))
        # The panel's monthly total return is CRSP's, public at month end.
        for month, g in total.groupby(self.days.to_period("M")):
            eom = month.to_timestamp(how="end").normalize()
            row = (permno, eom, float(np.prod(1 + g) - 1), me, 1e8, g.index[-1])
            self.panel_rows.append(row)

    # An exit row as the exits table holds it.
    def exit(self, permno, day, delret, category="merger", known=None, source="crsp_delistings"):
        group = "merger_or_exchange" if category == "merger" else "failure"
        first = pd.Timestamp(known or day)
        self.exit_rows.append((permno, pd.Timestamp(day), category, group, delret, first, source))

    # The book's data calls answered from the rows above.
    def install(self, monkeypatch):
        dsf = pd.DataFrame(self.dsf_rows, columns=["permno", "date", "ret", "ret_null", "prc"])
        crsp = pd.DataFrame(self.crsp_rows, columns=["permno", "date", "ret", "retx"])
        cols = ["permno", "eom", "ret", "me", "dolvol_126d", "first_close"]
        panel = pd.DataFrame(self.panel_rows, columns=cols)
        cols = ["permno", "exit_date", "category", "group", "delret", "first_close", "source"]
        exits = pd.DataFrame(self.exit_rows, columns=cols)
        cal = pd.Series(self.days + pd.Timedelta(hours=21), index=self.days)

        # Rows for these stocks between two days.
        def pick(frame, key, permnos, start, end):
            ok = frame["permno"].isin(set(int(p) for p in permnos))
            ok &= (frame[key] >= pd.Timestamp(start)) & (frame[key] <= pd.Timestamp(end))
            return frame[ok].copy()

        monkeypatch.setattr(data, "calendar", lambda: cal)
        monkeypatch.setattr(data, "dsf", lambda p, s, e, prices=False: pick(dsf, "date", p, s, e))
        monkeypatch.setattr(data, "market_daily", lambda days: pd.Series(0.0, index=days))
        monkeypatch.setattr(data, "crsp_daily", lambda p, s, e: pick(crsp, "date", p, s, e))
        monkeypatch.setattr(
            data, "panel", lambda p, s, e, columns=None: pick(panel, "eom", p, s, e)
        )
        monkeypatch.setattr(data, "exits", lambda p: exits[exits["permno"].isin(set(p))])
        monkeypatch.setattr(
            data,
            "rf_daily",
            lambda days, by=None: pd.Series(self.rf, index=pd.DatetimeIndex(days)),
        )
        monkeypatch.setattr(inputs, "sp500", lambda days: pd.Series(0.0, index=days))
        # The fake holds no sealed row, so its 2026 runs may open.
        monkeypatch.setattr(sources, "unsealed", lambda: True)
        monkeypatch.setattr(
            data, "permcos", lambda p, d: pd.Series(pd.Series(p).to_numpy(), dtype=float)
        )


# A run of the fake market with the test rules.
def book(fake, monkeypatch, targets, lag=1, end="2019-04-30", **kw):
    fake.install(monkeypatch)
    kw.setdefault("same_day", lag == 0)
    kw.setdefault("strict", False)
    targets = {pd.Timestamp(k): pd.Series(v, dtype=float) for k, v in targets.items()}
    return daily_book.run(targets, fake.days[0], end, lag=lag, rules=RULES, **kw)


# t+1: formed at the close of T, bought at T+1, first return T+1 to T+2.
def test_t_plus_one_trades_the_next_session(monkeypatch):
    fake = Fake()
    fake.stock(1, ret=0.01)
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}})
    assert out.trades["date"].tolist() == [pd.Timestamp("2019-02-01")]
    assert out.daily.loc["2019-02-01", "ret"] == pytest.approx(0.0)
    assert out.daily.loc["2019-02-04", "ret"] == pytest.approx(0.005)
    same = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}}, lag=0)
    assert same.trades["date"].tolist() == [pd.Timestamp("2019-01-31")]
    assert same.daily.loc["2019-02-01", "ret"] == pytest.approx(0.005)


# A weekend month end maps to its last session before the lag.
def test_weekend_month_end_maps_to_its_session_first(monkeypatch):
    fake = Fake()
    fake.stock(1)
    out = book(fake, monkeypatch, {"2019-03-31": {1: 0.5}})
    assert out.trades["date"].tolist() == [pd.Timestamp("2019-04-01")]
    same = book(fake, monkeypatch, {"2019-03-31": {1: 0.5}}, lag=0)
    assert same.trades["date"].tolist() == [pd.Timestamp("2019-03-29")]


# Cash, short proceeds included, compounds at the daily bill rate.
def test_cash_and_short_proceeds_earn_the_bill(monkeypatch):
    fake = Fake(rf=0.0001)
    fake.stock(1)
    out = book(fake, monkeypatch, {"2019-01-31": {1: -0.3}}, lag=0, end="2019-02-28")
    k = int((out.daily.index <= "2019-01-31").sum())
    m = len(out.daily) - k
    # Day 0 is the endowment's close, so it earns no bill.
    nav = 1e9 * 1.0001 ** (k - 1)
    assert out.daily["nav"].iloc[-1] == pytest.approx(1.3 * nav * 1.0001**m - 0.3 * nav)


# δ restores the month's total: CRSP's day through 2025, else month end.
def test_delta_books_the_month_total(monkeypatch):
    fake = Fake()
    ex = pd.Timestamp("2019-02-15")
    price = pd.Series(0.0, index=fake.days)
    price[ex] = -0.02
    fake.stock(1, ret=price, crsp_ret=0.0)
    for weight in (0.5, -0.5):
        out = book(fake, monkeypatch, {"2019-01-31": {1: weight}}, lag=0, end="2019-03-29")
        feb = out.daily.loc["2019-02-01":"2019-02-28"]
        assert feb["nav"].iloc[-1] == pytest.approx(1e9)
        # CRSP's dividend on its own day, trued up to δ at the month end.
        assert feb.loc[ex, "dividends"] == pytest.approx(weight * 1e9 * 0.02)
        assert abs(feb["delta_true_up"].sum()) < 1e-3 * abs(weight) * 1e9
        late = book(fake, monkeypatch, {"2019-01-31": {1: weight}}, lag=0, ex_days="dsf")
        feb = late.daily.loc["2019-02-01":"2019-02-28"]
        assert feb["dividends"].iloc[-1] == pytest.approx(weight * 1e9 * 0.02)
        assert feb["dividends"].iloc[:-1].abs().sum() == 0
    flat = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}}, lag=0, dividends="none")
    assert flat.daily["dividends"].abs().sum() == 0


# δ goes to the holding at its ex-day's open, not a later purchase.
def test_delta_is_paid_on_the_holding_at_the_ex_day_open(monkeypatch):
    fake = Fake()
    ex = pd.Timestamp("2019-03-01")
    price = pd.Series(0.0, index=fake.days)
    price[ex] = -0.5
    fake.stock(1, ret=price, crsp_ret=0.0)
    targets = {"2019-01-31": {1: 0.2}, "2019-02-28": {1: 0.4}}
    for rule in ("crsp", "dsf"):
        out = book(fake, monkeypatch, targets, ex_days=rule)
        # The 0.2 held at the open of 1 March is owed the spin-off's value.
        march = out.daily.loc["2019-03-01":"2019-03-29", "dividends"].sum()
        assert march == pytest.approx(0.2e9 * 0.5, rel=1e-3)
    # The month-end rule would pay it on shares bought after the ex-day.
    late = book(fake, monkeypatch, targets, ex_days="month_end")
    assert late.daily.loc["2019-03-29", "dividends"] == pytest.approx(0.4e9, rel=1e-3)


# Rule B pays a large δ on the month's least good holding for us.
def test_rule_b_pays_the_least_good_holding(monkeypatch):
    fake = Fake()
    price = pd.Series(0.0, index=fake.days)
    price[pd.Timestamp("2019-03-08")] = -0.5
    fake.stock(1, ret=price, crsp_ret=0.0)
    targets = {"2019-01-31": {1: 0.2}, "2019-02-28": {1: 0.4}}
    # The spin-off comes after the day-1 purchase: A pays 0.4, B pays 0.2.
    a = book(fake, monkeypatch, targets, ex_days="dsf").daily.loc["2019-03-29", "dividends"]
    b = book(fake, monkeypatch, targets, ex_days="bound").daily.loc["2019-03-29", "dividends"]
    assert a == pytest.approx(0.4e9 * 0.5, rel=1e-2) and b == pytest.approx(0.2e9 * 0.5, rel=1e-2)
    # Through 2025 the robustness run keeps CRSP's exact day.
    exact = book(fake, monkeypatch, targets, ex_days="crsp_bound").daily
    assert exact.loc["2019-03-01":"2019-03-29", "dividends"].sum() == pytest.approx(
        0.4e9 * 0.5, rel=1e-2
    )


# Missing a session, a month takes CRSP's daily dividends instead.
def test_incomplete_month_uses_crsp_dividends(monkeypatch):
    fake = Fake()
    total = pd.Series(0.0, index=fake.days)
    total[pd.Timestamp("2019-02-15")] = 0.01
    fake.stock(1, no_dsf=["2019-02-20"], crsp_ret=total)
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}}, lag=0, end="2019-02-28")
    assert out.daily.loc["2019-02-15", "dividends"] == pytest.approx(0.5e9 * 0.01)
    assert out.daily.loc["2019-02-28", "dividends"] == 0


# No δ in an exit month: the delisting return carries that month.
def test_no_delta_in_an_exit_month(monkeypatch):
    fake = Fake()
    fake.stock(1, crsp_ret=0.0)
    fake.exit(1, "2019-02-12", 0.0)
    fake.install(monkeypatch)
    m = daily_book.Market([1], fake.days)
    assert (1, pd.Period("2019-02", "M")) not in m.delta
    assert (1, pd.Period("2019-03", "M")) in m.delta


# Five missing sessions write a long off at -30%; the exit trues it up.
def test_stub_on_the_fifth_missing_day_then_true_up(monkeypatch):
    fake = Fake()
    gone = fake.days[(fake.days > "2019-02-15")]
    fake.stock(1, no_dsf=gone, no_crsp=gone)
    fake.exit(1, "2019-02-15", -0.5, category="dropped", known="2019-03-11")
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}}, lag=0)
    ev = out.events.set_index("kind")
    assert ev.loc["stub", "date"] == fake.days[fake.days > "2019-02-15"][4]
    assert ev.loc["stub", "value"] == daily_book.STUB_LONG
    assert ev.loc["true_up", "date"] == pd.Timestamp("2019-03-11")
    assert out.daily["nav"].iloc[-1] == pytest.approx(0.5e9 + 0.5e9 * 0.5)
    log = daily_book.logs(out)["stubs_by_year"].set_index(["leg", "kind"])["count"]
    assert log[("long", "stub")] == 1 and log[("long", "true_up")] == 1


# A long failure with no delisting return takes the panel's month.
def test_crsp_failure_without_a_return_takes_the_panel_month(monkeypatch):
    fake = Fake()
    gone = fake.days[(fake.days > "2019-02-15")]
    total = pd.Series(0.0, index=fake.days)
    total[pd.Timestamp("2019-02-19")] = -0.4
    fake.stock(1, no_dsf=gone, no_crsp=gone, crsp_ret=total)
    fake.exit(1, "2019-02-15", float("nan"), category="dropped", known="2019-03-11")
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.2}}, lag=0)
    assert {"stub", "true_up"} <= set(out.events["kind"])
    assert out.daily["nav"].iloc[-1] == pytest.approx(1e9 + 0.2e9 * -0.4)
    short = book(fake, monkeypatch, {"2019-01-31": {1: -0.2}}, lag=0)
    assert "stub_kept" in set(short.events["kind"])
    assert short.daily["nav"].iloc[-1] == pytest.approx(1e9 - 0.2e9 * daily_book.STUB_SHORT)


# A short owes 10% more; a 2026 failure with no final return keeps it.
def test_short_stub_and_a_2026_failure_keep_the_stub(monkeypatch):
    fake = Fake("2026-01-01", "2026-04-30")
    gone = fake.days[(fake.days > "2026-02-13")]
    fake.stock(1, no_dsf=gone, no_crsp=fake.days)
    fake.exit(1, "2026-02-13", float("nan"), "bankruptcy", "2026-03-11", "sec_forms_2026")
    targets = {"2026-01-30": {1: -0.2}}
    out = book(fake, monkeypatch, targets, lag=0, end="2026-04-30", unsealed=True)
    kinds = set(out.events["kind"])
    assert {"stub", "stub_kept"} <= kinds and "true_up" not in kinds
    assert out.daily["nav"].iloc[-1] == pytest.approx(1e9 - 0.2e9 * daily_book.STUB_SHORT)
    assert set(daily_book.logs(out)["stubs"]["leg"]) == {"short"}


# A 2026 merger closes at its last trade; a data gap at its last price.
def test_2026_merger_and_data_gap_close_at_the_last_price(monkeypatch):
    fake = Fake("2026-01-01", "2026-04-30")
    gone = fake.days[(fake.days > "2026-02-13")]
    fake.stock(1, no_dsf=gone, no_crsp=fake.days)
    fake.stock(2, no_dsf=gone, no_crsp=fake.days)
    fake.exit(1, "2026-02-13", float("nan"), "merger", "2026-03-11", "sec_forms_2026")
    fake.exit(2, "2026-02-13", float("nan"), "data_gap", None, "sec_forms_2026")
    targets = {"2026-01-30": {1: 0.2, 2: 0.2}}
    out = book(fake, monkeypatch, targets, lag=0, end="2026-04-30", unsealed=True)
    ev = out.events
    gap = ev[(ev["permno"] == 2) & (ev["kind"] == "exit")]
    assert gap["date"].tolist() == [fake.days[fake.days > "2026-02-13"][0]]
    merger = ev.loc[ev["permno"] == 1, "kind"].tolist()
    assert "stub" in merger and merger[-1] == "true_up"
    assert out.daily["nav"].iloc[-1] == pytest.approx(1e9)


# A halt that resumes never trues its stub up: the stub stands.
def test_a_resumed_halt_keeps_its_stub(monkeypatch):
    fake = Fake()
    gap = fake.days[(fake.days > "2019-02-15") & (fake.days < "2019-03-15")]
    fake.stock(1, no_dsf=gap, no_crsp=gap)
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}}, lag=0)
    assert "true_up" not in set(out.events["kind"]) and "stub_kept" in set(out.events["kind"])
    assert out.daily["nav"].iloc[-1] == pytest.approx(1e9 - 0.5e9 * 0.3)
    assert len(daily_book.logs(out)["halts"]) == 1


# The dsf drops a stock CRSP trades: marked on CRSP, sold next, no stub.
def test_crsp_marks_and_sells_a_stock_the_dsf_drops(monkeypatch):
    fake = Fake()
    gone = fake.days[fake.days > "2019-02-15"]
    fake.stock(1, ret=0.001, no_dsf=gone)
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.1}, "2019-02-28": {1: 0.1}}, lag=0)
    kinds = out.events["kind"].tolist()
    assert kinds.count("crsp_mark") == 1 and "stub" not in kinds
    sold = out.trades[out.trades["date"] == pd.Timestamp("2019-02-28")]
    assert sold["after"].tolist() == [0.0]
    assert out.positions[out.positions["date"] > "2019-02-28"].empty


# A sale CRSP cannot fill waits for the next formation.
def test_an_unfilled_sale_waits_for_the_next_formation(monkeypatch):
    fake = Fake()
    gone = fake.days[fake.days > "2019-02-15"]
    fake.stock(1, no_dsf=gone, no_crsp=["2019-02-28"])
    targets = {"2019-01-31": {1: 0.1}, "2019-02-28": {1: 0.1}, "2019-03-31": {1: 0.1}}
    out = book(fake, monkeypatch, targets, lag=0)
    assert "unfilled" in set(out.events["kind"])
    assert out.trades["date"].iloc[-1] == pd.Timestamp("2019-03-29")
    assert out.trades["after"].iloc[-1] == 0.0


# Compliance flags names, gross, net, the cap and the short floor.
def test_compliance_flags_each_rule(monkeypatch):
    fake = Fake()
    fake.stock(1)
    fake.stock(2, me=400.0)
    rules = RULES | dict(names_min=3, name_cap=0.05)
    fake.install(monkeypatch)
    targets = {pd.Timestamp("2019-01-31"): pd.Series({1: 1.4, 2: -0.7})}
    out = daily_book.run(targets, fake.days[0], "2019-02-28", lag=0, rules=rules, same_day=True)
    day = out.compliance.loc["2019-02-05"]
    assert not day["names_ok"] and not day["gross_ok"] and not day["net_ok"]
    assert not day["cap_ok"]
    assert out.compliance.loc["2019-01-31", "short_floor_breaches"] == 1


# The company cap counts before a day's trades as well as after.
def test_company_cap_counts_before_the_trades(monkeypatch):
    fake = Fake()
    jump = pd.Series(0.0, index=fake.days)
    jump.loc["2019-02-28"] = 0.10
    fake.stock(1, ret=jump)
    fake.stock(2)
    fake.install(monkeypatch)
    monkeypatch.setattr(data, "permcos", lambda p, d: pd.Series(np.ones(len(p))))
    targets = {
        pd.Timestamp("2019-01-31"): pd.Series({1: 0.04, 2: 0.008}),
        pd.Timestamp("2019-02-28"): pd.Series({1: 0.03, 2: 0.008}),
    }
    rules = RULES | dict(name_cap=0.05)
    out = daily_book.run(targets, fake.days[0], "2019-03-29", lag=0, rules=rules, same_day=True)
    c = out.compliance
    assert c.loc["2019-02-27", "cap_ok"] and c.loc["2019-02-28", "max_company_weight"] < 0.05
    assert c.loc["2019-02-28", "max_company_weight_pre"] > 0.05
    assert not c.loc["2019-02-28", "cap_ok"]


# Names count before a day's trades too: an exit can leave too few.
def test_names_count_before_the_trades(monkeypatch):
    fake = Fake()
    for permno in (1, 2, 4):
        fake.stock(permno, crsp_ret=0.0)
    gone = fake.days[fake.days > "2019-02-27"]
    fake.stock(3, no_dsf=gone, no_crsp=gone, crsp_ret=0.0)
    fake.exit(3, "2019-02-27", 0.0)
    fake.install(monkeypatch)
    targets = {
        pd.Timestamp("2019-01-31"): pd.Series({1: 0.1, 2: 0.1, 3: -0.1}),
        pd.Timestamp("2019-02-28"): pd.Series({1: 0.1, 2: 0.1, 4: -0.1}),
    }
    rules = RULES | dict(names_min=3)
    out = daily_book.run(targets, fake.days[0], "2019-03-29", lag=0, rules=rules, same_day=True)
    c = out.compliance
    assert c.loc["2019-02-28", "names"] == 3 and c.loc["2019-02-28", "names_pre"] == 2
    assert not c.loc["2019-02-28", "names_ok"] and c.loc["2019-03-01", "names_ok"]


# A formation trades on its own session; two on one day are refused.
def test_formations_keep_their_own_day(monkeypatch):
    fake = Fake()
    fake.stock(1)
    out = book(fake, monkeypatch, {"2019-02-08": {1: 0.1}, "2019-02-15": {1: 0.2}})
    assert out.trades["date"].tolist() == [pd.Timestamp("2019-02-11"), pd.Timestamp("2019-02-18")]
    with pytest.raises(ValueError, match="two formations"):
        book(fake, monkeypatch, {"2019-02-16": {1: 0.1}, "2019-02-17": {1: 0.2}})


# Orders are sized on the previous close's NAV (PLAN §9.1).
def test_orders_are_sized_on_the_previous_close(monkeypatch):
    fake = Fake()
    fake.stock(1, ret=0.01)
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.5}, "2019-02-28": {1: 0.5}})
    second = out.trades[out.trades["date"] == pd.Timestamp("2019-03-01")]
    assert second["after"].iloc[0] == pytest.approx(0.5 * out.daily.loc["2019-02-28", "nav"])


# An event-day rule no layer enforces yet stops the run.
def test_unenforced_event_day_rules_are_refused(monkeypatch):
    fake = Fake()
    fake.stock(1)
    fake.install(monkeypatch)
    targets = {pd.Timestamp("2019-01-31"): pd.Series({1: 0.1})}
    with pytest.raises(NotImplementedError, match="beta_cap"):
        daily_book.run(targets, fake.days[0], "2019-02-28", rules=RULES | dict(beta_cap=0.1))


# CRSP's delisting rows are no trade: the reader drops them.
def test_crsp_reader_drops_delisting_rows(monkeypatch):
    rows = pd.DataFrame(
        {
            "permno": [1, 1],
            "date": pd.to_datetime(["2019-02-14", "2019-02-15"]),
            "ret": [0.01, 0.2],
            "retx": [0.01, 0.2],
            "delflg": ["N", "Y"],
        }
    )
    monkeypatch.setattr(data, "table", lambda *a, **k: rows.copy())
    got = data.crsp_daily([1], "2019-02-01", "2019-02-28")
    assert got["date"].tolist() == [pd.Timestamp("2019-02-14")]


# A row filter on a banned or restricted field is refused like a column.
@pytest.mark.skipif(not (sources.DATA / "v4" / "clean").exists(), reason="no data folder")
def test_row_filters_obey_the_bans():
    day = (pd.Timestamp("2019-06-03"), pd.Timestamp("2019-06-03"))
    with pytest.raises(sources.BannedField):
        sources.read("dsf", ["ret"], where={"date": day, "prc": (0.0, 1.0)})
    with pytest.raises(sources.BannedField):
        sources.read("panel", ["me"], where={"company_name": {"APPLE INC"}})


# Every short held after a formation counts against the floor (PDF p4).
def test_short_floor_counts_held_shorts_at_each_formation(monkeypatch):
    fake = Fake()
    fake.stock(1)
    fake.stock(2, me=400.0)
    targets = {"2019-01-31": {1: 0.2, 2: -0.1}, "2019-02-28": {1: 0.2, 2: -0.1}}
    out = book(fake, monkeypatch, targets, lag=0)
    floor = out.compliance["short_floor_breaches"]
    assert floor.loc["2019-01-31"] == 1 and floor.loc["2019-02-28"] == 1
    assert floor.sum() == 2 and out.compliance.loc["2019-01-02", "names_ok"]


# A failure's residual is against CRSP's total: a dividend counts once.
def test_exit_residual_counts_a_dividend_once(monkeypatch):
    fake = Fake()
    gone = fake.days[(fake.days > "2019-02-15")]
    total = pd.Series(0.0, index=fake.days)
    total[pd.Timestamp("2019-02-05")] = 0.01
    total[pd.Timestamp("2019-02-19")] = -0.4
    fake.stock(1, no_dsf=gone, no_crsp=gone, crsp_ret=total)
    fake.exit(1, "2019-02-15", float("nan"), category="dropped", known="2019-03-11")
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.2}}, lag=0)
    # Cash keeps the dividend; the position takes the residual -40%.
    assert out.daily["nav"].iloc[-1] == pytest.approx(1e9 + 0.2e9 * 0.01 - 0.2e9 * 0.4)


# A CRSP-marked name stranded when CRSP ends closes at its mark.
def test_crsp_mark_held_past_crsp_closes_at_its_mark(monkeypatch):
    fake = Fake("2025-11-03", "2026-02-27")
    gone = fake.days[fake.days > "2025-12-15"]
    fake.stock(1, no_dsf=gone, no_crsp=fake.days[fake.days > "2025-12-31"])
    targets = {"2025-11-28": {1: 0.1}, "2025-12-31": {1: 0.1}}
    out = book(fake, monkeypatch, targets, end="2026-02-27", unsealed=True)
    kinds = out.events["kind"].tolist()
    assert "crsp_end_close" in kinds and "stub" not in kinds


# A gap ratio starts from the holding's own fill price.
def test_gap_ratio_starts_from_the_fill_price(monkeypatch):
    fake = Fake()
    fake.stock(1, ret=0.01)
    day = fake.days[fake.days > "2019-03-01"][0]
    fake.dsf_rows = [
        (p, d, float("nan") if d == day else r, n, x) for p, d, r, n, x in fake.dsf_rows
    ]
    targets = {"2019-01-31": {1: 0.1}, "2019-02-15": {1: 0.0}, "2019-02-28": {1: 0.1}}
    out = book(fake, monkeypatch, targets, lag=0)
    ratio = out.events[out.events["kind"] == "gap_ratio"]["value"]
    assert ratio.tolist() == [pytest.approx(0.01, rel=1e-6)]


# A target with a missing weight or trading outside the run stops.
def test_bad_targets_are_refused(monkeypatch):
    fake = Fake()
    fake.stock(1)
    with pytest.raises(ValueError, match="missing weight"):
        book(fake, monkeypatch, {"2019-01-31": {1: float("nan")}})
    with pytest.raises(ValueError, match="outside the run"):
        book(fake, monkeypatch, {"2019-04-30": {1: 0.1}})


# The universe refuses a mid-month date, so no later row is ever read.
def test_universe_refuses_a_mid_month_date(monkeypatch):
    Fake().install(monkeypatch)
    with pytest.raises(ValueError, match="month-end"):
        universe.members("2019-02-14")


# A set and a range on one column never share the reader's cache.
def test_reader_cache_keeps_sets_and_ranges_apart(monkeypatch):
    calls = []
    monkeypatch.setattr(data, "_CACHE", {})
    monkeypatch.setattr(sources, "read", lambda *a, **k: calls.append(k) or pd.DataFrame())
    data.table("nothing", where={"permno": {1, 2}})
    data.table("nothing", where={"permno": (1, 2)})
    assert len(calls) == 2


# A sealed month takes the last public bill rate, never the first.
def test_sealed_month_takes_the_last_public_bill(monkeypatch):
    bills = pd.DataFrame(
        {"month": pd.to_datetime(["1934-01-01", "2020-11-01"]), "tb3ms": [0.0072, 0.0009]}
    )
    monkeypatch.setattr(data, "table", lambda *a, **k: bills.copy())
    got = data.rf_daily(pd.bdate_range("2020-12-01", "2020-12-04"))
    assert got.tolist() == [pytest.approx(0.0009 / 252)] * 4


# Each bill month gets the close after FRED's next-business-day post.
def test_bill_months_carry_their_first_close(tmp_path):
    (tmp_path / "benchmarks").mkdir()
    rows = "observation_date,TB3MS\n2019-05-01,2.40\n2019-06-01,2.22\n"
    (tmp_path / "benchmarks" / "TB3MS_full.csv").write_text(rows)
    cal = clock.calendar(clock.xnys_sessions("2019-05-01", "2019-07-31"))
    got = sources.load_tb3ms(tmp_path, cal, {})
    want = pd.to_datetime(["2019-06-04", "2019-07-02"])
    assert pd.DatetimeIndex(got["first_close"]).equals(want)


# Betas at T read only bill rates public by T; a row with none is out.
def test_bill_rates_by_T_skip_unpublished_months(monkeypatch):
    bills = pd.DataFrame(
        {
            "month": pd.to_datetime(["2019-04-01", "2019-05-01", "2019-06-01"]),
            "tb3ms": [0.0243, 0.0240, 0.0222],
            "first_close": pd.to_datetime([None, "2019-06-04", "2019-07-02"]),
        }
    )
    monkeypatch.setattr(data, "table", lambda *a, **k: bills.copy())
    june = pd.bdate_range("2019-06-03", "2019-06-28")
    got = data.rf_daily(june, by="2019-06-28")
    assert got.notna().all() and got.eq(0.0240 / 252).all()
    assert data.rf_daily(june).eq(0.0222 / 252).all()


# On the real data the betas at a 2019 close are all finite.
@pytest.mark.skipif(
    not (sources.DATA / "v4" / "clean" / "dsf.parquet").exists(), reason="no data folder"
)
def test_betas_run_on_the_real_data():
    got = betas.at("2019-06-28", [14593, 10107, 12490])
    assert got[["welch", "dimson", "trigger"]].notna().all(axis=None)


# A missing market day drops out of the betas, never voids them.
def test_betas_skip_a_missing_market_day(monkeypatch):
    fake = Fake("2018-01-01", "2019-12-31")
    rng = np.random.default_rng(1)
    fake.stock(1, ret=pd.Series(rng.normal(0, 0.01, len(fake.days)), index=fake.days))
    fake.install(monkeypatch)
    market = pd.Series(rng.normal(0, 0.01, len(fake.days)), index=fake.days)
    market.iloc[-10] = np.nan
    monkeypatch.setattr(data, "market_daily", lambda days: market.reindex(days))
    got = betas.at("2019-06-28", [1])
    assert got[["welch", "dimson", "trigger"]].notna().all(axis=None)


# Rule B's 2026 run books a large δ for a long, a short and a small one.
def test_rule_b_runs_in_2026(monkeypatch):
    fake = Fake("2026-01-01", "2026-04-30")
    price = pd.Series(0.0, index=fake.days)
    price[pd.Timestamp("2026-03-10")] = -0.5
    small = pd.Series(0.0, index=fake.days)
    small[pd.Timestamp("2026-03-10")] = -0.01
    fake.stock(1, ret=price, crsp_ret=0.0)
    fake.stock(2, ret=small, crsp_ret=0.0)
    targets = {"2026-01-30": {1: 0.2, 2: 0.1}, "2026-02-27": {1: -0.1, 2: 0.1}}
    for rule in ("crsp", "crsp_bound"):
        out = book(fake, monkeypatch, targets, end="2026-04-30", unsealed=True, ex_days=rule)
        march = out.ledger[(out.ledger["kind"] == "delta") & (out.ledger["date"] == "2026-03-31")]
        paid = march.set_index("permno")["dollars"]
        # The short owes the spin-off; a small δ goes to the month-end book.
        assert paid[1] < 0 and paid[2] == pytest.approx(0.1e9 * 0.99 * (1 / 0.99 - 1), rel=1e-3)
    flags = out.events[out.events["kind"] == "delta_large"]
    assert flags["permno"].tolist() == [1]


# The floor binds at the decision close; the trade close is reported.
def test_short_floor_is_checked_on_the_trade_day_too(monkeypatch):
    fake = Fake()
    fall = pd.Series(0.0, index=fake.days)
    fall[pd.Timestamp("2019-02-01")] = -0.25
    fake.stock(1, ret=fall, me=600.0)
    out = book(fake, monkeypatch, {"2019-01-31": {1: -0.1}})
    row = out.compliance.loc["2019-02-01"]
    assert row["floor_at_formation"] == 0 and row["floor_at_trade"] == 1
    assert row["short_floor_breaches"] == 0


# Marks before a day's trades count too (PDF p4 "at all times").
def test_marks_before_the_trade_count(monkeypatch):
    fake = Fake()
    jump = pd.Series(0.0, index=fake.days)
    jump[pd.Timestamp("2019-02-01")] = 1.5
    fake.stock(1, ret=jump)
    fake.stock(2)
    targets = {"2019-01-31": {1: 0.3, 2: 0.1}, "2019-02-28": {1: 0.3, 2: 0.1}}
    out = book(fake, monkeypatch, targets, lag=0)
    day = out.daily.loc["2019-02-28"]
    assert day["net_pre"] > 0.5 >= day["net"]
    assert not out.compliance.loc["2019-02-28", "net_ok"]


# A same-day book, or an unsealed one while sealed, is refused.
def test_same_day_and_sealed_runs_are_refused(monkeypatch):
    fake = Fake()
    fake.stock(1)
    with pytest.raises(ValueError, match="PDF p15"):
        book(fake, monkeypatch, {"2019-01-31": {1: 0.1}}, lag=0, same_day=False)
    fake.install(monkeypatch)
    monkeypatch.setattr(sources, "unsealed", lambda: False)
    with pytest.raises(clock.SealedWindow, match="still sealed"):
        daily_book.run({}, fake.days[0], "2019-04-30", rules=RULES, unsealed=True)
    with pytest.raises(NotImplementedError, match="compounds"):
        daily_book.run({}, fake.days[0], "2019-04-30", rules=RULES | dict(compound=False))


# Turnover is the PDF's ½ Σ |weight after - weight carried in| (p20).
def test_turnover_follows_the_pdf_formula(monkeypatch):
    fake = Fake()
    fake.stock(1, ret=0.01)
    fake.stock(2, ret=-0.01)
    targets = {"2019-01-31": {1: 0.3, 2: -0.3}, "2019-02-28": {1: 0.1, 2: -0.2}}
    out = book(fake, monkeypatch, targets)
    t = out.trades[out.trades["date"] == pd.Timestamp("2019-03-01")]
    want = 0.5 * (t["w_after"] - t["w_before"]).abs().sum()
    assert out.daily.loc["2019-03-01", "turnover"] == pytest.approx(want)


# Every dollar a name earns or costs is in the ledger: it rebuilds NAV.
def test_ledger_rebuilds_nav(monkeypatch):
    fake = Fake(rf=0.0001)
    fake.stock(1, ret=0.002, crsp_ret=0.003)
    fake.stock(2, ret=-0.001)
    targets = {"2019-01-31": {1: 0.3, 2: -0.2}, "2019-02-28": {1: 0.2, 2: -0.2}}
    out = book(fake, monkeypatch, targets, costs=lambda d, m: 1e-4 * m.abs())
    gained = out.ledger["dollars"].sum() + out.daily["interest"].sum()
    assert gained == pytest.approx(out.daily["nav"].iloc[-1] - 1e9, rel=1e-9)
    totals = daily_book.contributions(out)
    assert {"price", "dividend", "cost"} <= set(totals.columns)


# Past the seal a breach stops the build; the δ guard zeroes a negative.
def test_strict_runs_stop_on_a_breach_and_delta_is_guarded(monkeypatch):
    fake = Fake()
    fake.stock(1)
    with pytest.raises(daily_book.Breach):
        book(fake, monkeypatch, {"2019-01-31": {1: 0.7}}, strict=True)
    odd = Fake()
    odd.stock(1, crsp_ret=0.0)
    odd.panel_rows = [
        (p, e, -0.02 if e == pd.Timestamp("2019-02-28") else r, m, a, f)
        for p, e, r, m, a, f in odd.panel_rows
    ]
    out = book(odd, monkeypatch, {"2019-01-31": {1: 0.2}}, ex_days="dsf")
    assert "delta_negative_zeroed" in set(out.events["kind"])
    assert out.ledger[out.ledger["kind"] == "delta"]["dollars"].abs().sum() == 0


# The finals run starts at the endowment's close and ends in its window.
def test_finals_window_is_enforced(monkeypatch):
    # A weekday calendar, so the test needs no data folder (CI has none).
    Fake("2020-12-01", "2026-09-30").install(monkeypatch)
    rules = dict(window=["2021-01-01", "2026-08-31"])
    days = data.sessions("2020-12-31", "2026-08-31")
    daily_book.finals_window(rules, days)
    with pytest.raises(ValueError, match="finals run"):
        daily_book.finals_window(rules, data.sessions("2021-01-04", "2026-08-31"))


# A failure's panel residual waits until the panel's row is public.
def test_exit_residual_waits_for_its_panel_row(monkeypatch):
    fake = Fake()
    gone = fake.days[(fake.days > "2019-02-08")]
    total = pd.Series(0.0, index=fake.days)
    total[pd.Timestamp("2019-02-11")] = -0.4
    fake.stock(1, no_dsf=gone, no_crsp=gone, crsp_ret=total)
    fake.exit(1, "2019-02-08", float("nan"), category="dropped", known="2019-02-12")
    out = book(fake, monkeypatch, {"2019-01-31": {1: 0.2}}, lag=0)
    ev = out.events.set_index("kind")["date"]
    assert ev["stub"] == pd.Timestamp("2019-02-15")
    assert ev["true_up"] == pd.Timestamp("2019-02-28")


# The rules block refuses a key it does not know; the PDF's values load.
def test_mandate_refuses_unknown_keys_and_holds_the_pdf_rules(tmp_path):
    rules = daily_book.mandate()
    assert (rules["names_min"], rules["names_max"], rules["gross"]) == (200, 500, 2.0)
    assert (rules["net_band"], rules["name_cap"], rules["lag_days"]) == (0.5, 0.05, 1)
    assert rules["short_min_market_cap"] == 500.0
    assert set(rules["quotes"]) <= set(rules) and "lag_days" in rules["quotes"]
    assert rules["benchmark_premium"] == 0.04
    bad = tmp_path / "bad.json"
    bad.write_text('{"name": "x", "turnover_cap": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="turnover_cap"):
        daily_book.mandate(bad)


# Blind mode refuses a book that ends after 2020-12-31.
def test_book_refuses_a_window_past_the_seal():
    with pytest.raises(clock.SealedWindow):
        daily_book.run({}, "2020-12-31", "2021-01-04")
    with pytest.raises(ValueError):
        daily_book.run({}, "2020-01-01", "2020-02-01", dividends="gross")


# Welch clips each return to [-2, 4] x the market's; Dimson is a sum.
def test_welch_clips_and_dimson_sums_lag_day_and_lead():
    rng = np.random.default_rng(0)
    m = pd.Series(rng.normal(0, 0.01, 300))
    stocks = pd.DataFrame({"steep": 10 * m, "plain": 1.5 * m})
    got = betas.welch(stocks, m)
    assert got["steep"] == pytest.approx(4.0) and got["plain"] == pytest.approx(1.5)
    lagged = pd.DataFrame({"slow": m.shift(1).fillna(0.0)})
    assert betas.dimson(lagged, m)["slow"] == pytest.approx(1.0, abs=1e-6)
    # The stock's own last day is never in the regression: no lead past T.
    moved = lagged.copy()
    moved.iloc[-1] = 5.0
    assert betas.dimson(moved, m)["slow"] == pytest.approx(betas.dimson(lagged, m)["slow"])


# Betas at T read no day after T.
def test_betas_read_nothing_after_t(monkeypatch):
    fake = Fake("2018-01-01", "2019-12-31")
    fake.stock(1, ret=0.001)
    fake.install(monkeypatch)
    seen = []
    real = data.dsf

    # Every day the betas ask for, recorded.
    def spy(p, s, e, prices=False):
        assert not prices
        seen.append(pd.Timestamp(e))
        return real(p, s, e)

    monkeypatch.setattr(data, "dsf", spy)
    monkeypatch.setattr(data, "market_daily", lambda days: pd.Series(0.001, index=days))
    betas.at("2019-06-28", [1])
    assert max(seen) <= pd.Timestamp("2019-06-28")


# The universe: $600m to enter, $500m to stay, $5 traded, a trade on T.
def test_universe_rules(monkeypatch):
    eom = pd.Timestamp("2019-06-30")
    panel = pd.DataFrame(
        {
            "permno": [1, 2, 3, 4, 5],
            "eom": eom,
            "me": [700.0, 550.0, 550.0, 700.0, 700.0],
            "prc": [10.0, 10.0, -10.0, 4.0, 10.0],
        }
    )
    day = pd.DataFrame({"permno": [1, 2, 3, 4, 5], "ret": [0.0, 0.0, 0.0, 0.0, None]})
    panel["first_close"] = day["first_close"] = pd.Timestamp("2019-06-28")
    tables = {"panel": panel, "dsf": day}
    monkeypatch.setattr(data, "table", lambda name, *a, **k: tables[name].copy())
    monkeypatch.setattr(
        data, "eom_session", lambda e: pd.Series([pd.Timestamp("2019-06-28")] * len(e))
    )
    got = universe.members(eom, held_long=[3]).set_index("permno")
    assert got["new_long"].tolist() == [True, False, False, False, False]
    assert got["keep_long"].tolist() == [False, False, True, False, False]
    assert got["eligible"].tolist() == [True, False, True, False, False]


HAVE_DATA = (sources.DATA / "v4" / "clean" / "dsf.parquet").exists()


# A delisting return is booked once: on the exit, never as a CRSP mark.
@pytest.mark.skipif(not HAVE_DATA, reason="no data folder")
def test_real_delisting_is_booked_once():
    targets = {pd.Timestamp("2015-12-31"): pd.Series({88516: 0.05})}
    out = daily_book.run(targets, "2015-12-31", "2016-02-10", lag=0, rules=RULES, same_day=True)
    kinds = out.events.loc[out.events["permno"] == 88516, "kind"].tolist()
    assert kinds.count("exit") == 1 and "crsp_mark" not in kinds


# Counts only (§1.3): no 2021+ glitch or long gap on a universe stock.
@pytest.mark.skipif(not HAVE_DATA, reason="no data folder")
def test_real_2021_on_glitches_miss_the_universe():
    import pyarrow.dataset as ds

    since = ds.field("date") >= pd.Timestamp("2021-01-01")
    d = ds.dataset(sources.CLEAN / "dsf.parquet").to_table(
        columns=["permno", "date", "prc"], filter=since
    )
    d = d.to_pandas()
    panel = pd.read_parquet(sources.CLEAN / "panel.parquet", columns=["permno", "eom", "me", "prc"])
    big = panel[(panel["me"] >= 500) & (panel["prc"].abs() >= 5)][["permno", "eom"]]
    d["eom"] = (d["date"] - pd.offsets.MonthEnd(1)).dt.normalize()
    tiny = d[d["prc"].abs() < 0.01].merge(big, on=["permno", "eom"])
    assert tiny.empty
    # Five or more missing sessions that then resume, on a $500m stock.
    cal = pd.Series(range(len(data.calendar())), index=data.calendar().index)
    d = d.sort_values(["permno", "date"])
    d["k"] = d["date"].map(cal)
    before = d.groupby("permno")["k"].shift()
    starts = d.loc[d["k"] - before - 1 >= daily_book.STUB_DAYS, ["permno"]]
    first = before[starts.index].astype(int) + 1
    starts["eom"] = (cal.index[first] - pd.offsets.MonthEnd(1)).normalize()
    assert starts.merge(big, on=["permno", "eom"]).empty


# The stocks the dsf drops while CRSP trades, and IB's gap (2015-2020).
DROPPED = {
    69550: "2015-03-02", 12894: "2015-03-25", 77649: "2015-11-03", 15719: "2016-01-04",
    31974: "2016-01-04", 79564: "2016-01-05", 92457: "2016-07-01", 13429: "2017-01-03",
    14686: "2017-01-11", 86996: "2017-01-17", 93189: "2017-07-24", 93429: "2018-09-17",
    92043: "2018-10-05", 17920: "2020-08-31",
}  # fmt: skip


# Each named stock is marked on CRSP and sold at the next formation.
@pytest.mark.skipif(not HAVE_DATA, reason="no data folder")
@pytest.mark.parametrize("permno", sorted(DROPPED))
def test_real_dropped_stocks_are_marked_and_sold(permno):
    first = pd.Timestamp(DROPPED[permno])
    before = (first - pd.offsets.MonthEnd(1)).normalize()
    after = (first + pd.offsets.MonthEnd(0)).normalize()
    targets = {before: pd.Series({permno: 0.01}), after: pd.Series({permno: 0.01})}
    start = data.eom_session([before]).iloc[0]
    end = data.shift([data.eom_session([after]).iloc[0]], 3).iloc[0]
    out = daily_book.run(targets, start, end, lag=0, rules=RULES, same_day=True)
    kinds = out.events.loc[out.events["permno"] == permno, "kind"].tolist()
    assert "crsp_mark" in kinds and "stub" not in kinds
    assert out.positions[out.positions["date"] == end].empty


# v3's stored 2016-2020 holdings replay within tolerance, same day.
@pytest.mark.skipif(not HAVE_DATA, reason="no data folder")
def test_real_v3_replay_within_tolerance():
    from fiam.v4 import replay

    if not (replay.V3 / "holdings.parquet").exists():
        pytest.skip("no v3 check holdings")
    # Only v3's 2016-2020 check folder, never its 2021+ record.
    assert replay.V3.name == "check" and max(replay.targets()) <= pd.Timestamp("2020-11-30")
    summary, both, _ = replay.compare(0)
    assert summary["months"] == 60
    assert summary["within_bar"] and summary["judged"]


# Each 2026 input agrees with its CRSP original on 2019-06.
@pytest.mark.skipif(not HAVE_DATA, reason="no data folder")
def test_real_2026_inputs_agree_on_2019_06():
    from fiam.v4 import inputs

    assert inputs.check()["passes"]
