# The v4 daily book (PLAN §6.4, §9; the protocol's step 5 rules).

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4 import clock, data, inputs, sources

ROOT = Path(__file__).resolve().parents[2]
MANDATE = ROOT / "mandates" / "finals_2026.json"
# The fifth straight missing day writes a held name off (PLAN §6.4).
STUB_DAYS = 5
# Shumway (1997): a long loses 30%, a short owes 10% more.
STUB_LONG, STUB_SHORT = -0.30, 0.10
# A held day's move this large is listed beside the panel, never edited.
BIG_MOVE = 0.50
# δ as the rule, CRSP's dividends alone as a check, or price only.
DIVIDENDS = ("delta", "crsp", "none")
# A δ this large is a distribution the dsf prices as a fall.
BIG_DELTA = 0.05
# A δ below this is a data mismatch, not a dividend: set to 0, logged.
DELTA_FLOOR = -1e-4
# δ's ex-day: CRSP's, then 2026 rule A or B; the others are checks.
EX_DAYS = ("crsp", "crsp_bound", "dsf", "bound", "month_end")
# A dsf price return this far from CRSP's is a distribution it missed.
MISSED = 1e-4
# Event-day keys: until a layer enforces them, a set one stops a run.
EVENT_KEYS = (
    "turnover_annual", "turnover_monthly", "participation", "style_cap", "sector_cap",
    "beta_cap", "liquidity_floor", "adv_days", "exclude_sectors", "min_market_cap",
)  # fmt: skip
# Keys the organisers' rules block may hold; any other key stops a run.
RULE_KEYS = {
    "name", "source", "nav_start", "compound", "names_min", "names_max", "gross",
    "net_band", "name_cap", "short_min_market_cap", "lag_days", "window",
    "benchmark_path", "benchmark_premium", "holdings_spec", "units", "quotes", *EVENT_KEYS,
}  # fmt: skip
# The book's beta on the S&P 500 over the PDF's 252-session window.
BETA_DAYS = 252


# A run that breaks a PDF limit where the build must stop (PLAN §9.3).
class Breach(AssertionError):
    pass


# The organisers' rules as a dict, refusing a key it does not know.
def mandate(path: Path = MANDATE) -> dict:
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = set(rules) - RULE_KEYS
    if unknown:
        raise ValueError(f"unknown mandate keys: {sorted(unknown)}")
    return rules


# What one run hands back: days, positions, trades, events, ledger.
@dataclass
class Result:
    daily: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame
    events: pd.DataFrame
    compliance: pd.DataFrame
    ledger: pd.DataFrame


# The market data one run needs, read once through the registry.
class Market:
    # Every input for these stocks and days, as session-by-stock arrays.
    def __init__(self, permnos, days, dividends: str = "delta", ex_days: str = "crsp"):
        self.days, self.permnos = days, sorted(set(int(p) for p in permnos))
        self.dividends, self.ex_source = dividends, ex_days
        self.col = {p: j for j, p in enumerate(self.permnos)}
        self.ends = {}
        d = data.dsf(self.permnos, days[0], days[-1], prices=True)
        grid = data.matrix(d.assign(one=1.0), "one", days, self.permnos)
        self.has_row = grid.notna().to_numpy()
        self.ret = data.matrix(d, "ret", days, self.permnos).to_numpy()
        self.prc = data.matrix(d, "prc", days, self.permnos).abs().to_numpy()
        c = data.crsp_daily(self.permnos, days[0], days[-1])
        self.crsp_ret = data.matrix(c, "ret", days, self.permnos).to_numpy()
        self.crsp_retx = data.matrix(c, "retx", days, self.permnos).to_numpy()
        self.rf = data.rf_daily(days).to_numpy()
        self.sp500 = inputs.sp500(days).to_numpy()
        first = days[0] - pd.offsets.MonthEnd(2)
        p = data.panel(self.permnos, first, days[-1], ("ret", "me", "dolvol_126d"))
        self.panel = p.set_index(["permno", "eom"]).sort_index()
        keys = list(self.panel.index)
        self.me = dict(zip(keys, self.panel["me"].to_numpy()))
        self.seen = dict(zip(keys, pd.to_datetime(self.panel["first_close"]).to_numpy()))
        self.month = days.to_period("M")
        last = pd.Series(range(len(days)), index=self.month).groupby(level=0).max()
        self.last_of_month = set(last.to_numpy().tolist())
        self.month_close = {m: days[i] for m, i in last.items()}
        self.exits = self.exit_rows()
        self.flags = {}
        self.delta = self.dividend_terms(d) if dividends == "delta" else {}
        self.exday, self.after = self.ex_days(ex_days)
        self.residual = self.exit_residuals(c)

    # Each stock's dated exits as plain rows, earliest known first.
    def exit_rows(self) -> dict:
        cols = ["exit_date", "category", "group", "delret", "source", "first_close"]
        e = data.exits(self.permnos).sort_values("first_close")
        return {int(k): g[cols].to_dict("records") for k, g in e.groupby("permno")}

    # δ per stock-month: complete dsf months, never an exit month (§6.4).
    def dividend_terms(self, d: pd.DataFrame) -> dict:
        cal = data.calendar().index.to_period("M").value_counts()
        f = d.assign(month=d["date"].dt.to_period("M"), growth=1 + d["ret"])
        g = f.groupby(["permno", "month"]).agg(
            rows=("date", "size"), full=("ret", "count"), growth=("growth", "prod")
        )
        # Every session of the month read and none null; a partial month fails.
        g = g[(g["rows"] == g.index.get_level_values("month").map(cal)) & (g["full"] == g["rows"])]
        g = g.reset_index()
        g["eom"] = g["month"].dt.end_time.dt.normalize()
        panel = self.panel[["ret", "first_close"]].reset_index()
        g = g.merge(panel, on=["permno", "eom"]).dropna(subset=["ret"])
        # The panel's month return is booked at that month's last close.
        data.assert_public_by(g["first_close"], g["month"].map(self.month_close), "δ panel rows")
        out = {}
        for permno, month, growth, total in g[["permno", "month", "growth", "ret"]].itertuples(
            index=False
        ):
            if self.exit_month(int(permno), month):
                continue
            key, delta = (int(permno), month), float((1 + total) / growth - 1)
            # A negative δ is a mismatch, never a dividend (fourth set).
            if delta < DELTA_FLOOR:
                self.flags[key] = ("delta_negative_zeroed", delta)
                delta = 0.0
            elif delta > BIG_DELTA:
                self.flags[key] = ("delta_large", delta)
            out[key] = delta
        return out

    # Each δ's ex-day and the dsf growth from that day's open to month end.
    def ex_days(self, source: str) -> tuple[dict, dict]:
        sessions = {}
        for i, month in enumerate(self.month):
            sessions.setdefault(month, []).append(i)
        exday, after = {}, {}
        self.bound, self.bound_by_month = {}, {}
        for (permno, month), delta in self.delta.items():
            rows, j = np.array(sessions[month]), self.col[permno]
            r = self.ret[rows, j]
            crsp = self.crsp_ret[rows, j] - r
            # A large δ with no dated ex-day: the holding least good for us.
            dated = source.startswith("crsp") and self.days[rows[-1]] <= data.CRSP_END
            bound = source == "bound" or (source == "crsp_bound" and not dated)
            if bound and delta > BIG_DELTA:
                growth = np.cumprod((1 + r)[::-1])[::-1]
                self.bound[(permno, month)] = dict(zip(rows.tolist(), growth.tolist()))
                self.bound_by_month.setdefault(month, []).append((permno, month))
                continue
            # Through 2025 CRSP dates it: the day the dsf misses the most.
            if dated:
                k = int(np.nanargmax(crsp)) if np.nanmax(crsp, initial=0.0) > 1e-6 else -1
            # In 2026 a large δ goes ex on the month's sharpest dsf fall.
            elif source != "month_end":
                k = int(np.argmin(r)) if delta > BIG_DELTA else -1
            # The approved rule as first written: the month-end holding.
            else:
                k = -1
            exday[(permno, month)] = int(rows[k])
            after[(permno, month)] = float(np.prod(1 + r[k:])) if k != -1 else float(1 + r[-1])
        return exday, after

    # A month holding a stock's exit date by the exits table.
    def exit_month(self, permno: int, month) -> bool:
        return any(r["exit_date"].to_period("M") == month for r in self.exits.get(permno, []))

    # Through 2025, a missing delisting return from the panel's exit month.
    def exit_residuals(self, c: pd.DataFrame) -> dict:
        out = {}
        for permno, rows in self.exits.items():
            for r in rows:
                month = r["exit_date"].to_period("M")
                if pd.notna(r["delret"]) or r["source"] != "crsp_delistings":
                    continue
                if not self.month[0] <= month <= self.month[-1]:
                    continue
                key = (permno, month.to_timestamp(how="end").normalize())
                total = self.panel["ret"].get(key, np.nan)
                # Against CRSP's total return, so its dividends count once.
                seen = c[(c["permno"] == permno) & (c["date"].dt.to_period("M") == month)]
                if pd.notna(total) and len(seen) and seen["ret"].notna().all():
                    value = float((1 + total) / np.prod(1 + seen["ret"]) - 1)
                    out[(permno, r["exit_date"])] = (value, pd.Timestamp(self.seen[key]))
        return out

    # The first exit of a held stock known by day d, if any.
    def exit_known(self, permno: int, d: pd.Timestamp, opened: pd.Timestamp):
        for r in self.exits.get(permno, []):
            if r["exit_date"] < opened:
                continue
            # A data gap closes at its last price once its rows stop (2B).
            if r["category"] == "data_gap" and d > r["exit_date"]:
                return r
            if pd.isna(r["first_close"]) or r["first_close"] > d:
                continue
            # A residual from the panel waits until that row is public.
            residual = self.residual.get((permno, r["exit_date"]))
            if residual is not None and residual[1] > d:
                continue
            return r
        return None

    # An exit's final return; NaN keeps the stub (PLAN §6.4, A12, A13).
    def exit_return(self, permno: int, r: dict, short: bool) -> float:
        if r["category"] == "data_gap":
            return 0.0
        if pd.notna(r["delret"]):
            return float(r["delret"])
        # 2026 mergers close at the last trade; failures keep the stub.
        if r["source"] != "crsp_delistings":
            return 0.0 if r["group"] == "merger_or_exchange" else np.nan
        # A short never gains from the panel's filled failure return.
        if short and r["group"] == "failure":
            return np.nan
        return self.residual.get((permno, r["exit_date"]), (np.nan, None))[0]

    # A stock's cap in $m at a close: last month end x dsf drift (§6.4).
    def cap_at(self, permno: int, day: pd.Timestamp) -> float:
        if day not in self.ends:
            eom = data.month_end_at(day)
            since = data.eom_session([eom]).iloc[0]
            lo = int(self.days.searchsorted(since, side="right"))
            self.ends[day] = (eom, lo, int(self.days.searchsorted(day, side="right")))
        eom, lo, hi = self.ends[day]
        key = (permno, eom)
        if key not in self.me:
            return np.nan
        data.assert_public_by([self.seen[key]], day, "formation cap")
        return self.me[key] * float(np.prod(1 + np.nan_to_num(self.ret[lo:hi, self.col[permno]])))


# Runs a book from start to end; targets map formation days to weights.
def run(
    targets: dict,
    start,
    end,
    *,
    lag: int | None = None,
    nav: float | None = None,
    costs=None,
    borrow=None,
    rules: dict | None = None,
    unsealed: bool = False,
    dividends: str = "delta",
    ex_days: str = "crsp",
    same_day: bool = False,
    strict: bool | None = None,
) -> Result:
    end = pd.Timestamp(end)
    rules = rules or mandate()
    strict = unsealed if strict is None else strict
    # A dividend basis the engine does not know stops the run.
    if dividends not in DIVIDENDS or ex_days not in EX_DAYS:
        raise ValueError(f"dividends in {DIVIDENDS}, ex_days in {EX_DAYS}")
    # Blind mode refuses a window past the seal; it never truncates one.
    if end > clock.LAST_LABEL_DAY and not unsealed:
        raise clock.SealedWindow(f"the book ends {end:%Y-%m-%d}, after 2020-12-31")
    # Only the hash-checked unseal opens the registry's 2021+ rows.
    if unsealed and not sources.unsealed():
        raise clock.SealedWindow("the registry is still sealed (§13.3)")
    # The mandate compounds; a rules block that does not is refused.
    if not rules.get("compound", True):
        raise NotImplementedError("the engine always compounds (PDF p4)")
    # A target with a missing weight stops the run, never a NaN NAV.
    if any(w.isna().any() for w in targets.values()):
        raise ValueError("a target holds a missing weight")
    # A rule set for event day that no layer enforces yet is refused.
    pending = [k for k in EVENT_KEYS if rules.get(k) not in (None, [], {})]
    if pending:
        raise NotImplementedError(f"rules not yet enforced by the engine: {pending}")
    lag = rules["lag_days"] if lag is None else lag
    nav = rules["nav_start"] if nav is None else nav
    # A same-day book is v3's convention, for its replay only (PDF p15).
    if lag < rules["lag_days"] and not same_day:
        raise ValueError(f"lag {lag} is under the rules' {rules['lag_days']} (PDF p15)")
    days = data.sessions(start, end)
    # The run past the seal is the finals run, in its window only.
    if unsealed and strict:
        finals_window(rules, days)
    on_days, orders = set(days), {}
    for formed, weights in targets.items():
        # Information at the formation close trades lag sessions later.
        session = data.eom_session([pd.Timestamp(formed)]).iloc[0]
        day = pd.Timestamp(data.shift([session], lag).iloc[0] if lag else session)
        if day in orders:
            raise ValueError(f"two formations trade on {day:%Y-%m-%d}")
        # A formation that trades outside the run is refused, never dropped.
        if pd.isna(day) or day not in on_days:
            raise ValueError(
                f"the formation of {pd.Timestamp(formed):%Y-%m-%d} trades outside the run"
            )
        orders[day] = (session, weights[weights != 0].astype(float))
    permnos = set().union(*(set(w.index) for _, w in orders.values()))
    market = Market(permnos, days, dividends, ex_days)
    book = Book(market, nav, costs, borrow, rules)
    for i, d in enumerate(days):
        book.step(i, d, orders.get(d))
    result = book.result()
    # Past the seal any PDF limit breach stops the build (PLAN §9.3).
    if strict:
        found = breaches(result)
        if len(found):
            raise Breach(f"{len(found)} days break a PDF limit, first {found.index[0]:%Y-%m-%d}")
    return result


# The finals run: endowed at the close before the window, never past it.
def finals_window(rules: dict, days: pd.DatetimeIndex) -> None:
    first, last = (pd.Timestamp(x) for x in rules["window"])
    endowed = data.eom_session([first - pd.Timedelta(days=1)]).iloc[0]
    if days[0] != endowed or days[-1] > last + pd.offsets.MonthEnd(0):
        raise ValueError(f"the finals run starts {endowed:%Y-%m-%d} and ends by {last:%Y-%m}")


# The running state of one book, one session at a time.
class Book:
    # An all-cash book endowed at the close of the first session.
    def __init__(self, market: Market, nav: float, costs, borrow, rules: dict):
        self.m, self.rules = market, rules
        self.cash, self.values, self.opened = float(nav), {}, {}
        self.costs, self.borrow = costs, borrow
        self.missing, self.last_price, self.stubs, self.sell_next = {}, {}, {}, set()
        self.entitled, self.accrued, self.trued, self.formations = {}, {}, 0.0, []
        self.lowest, self.pre_positions = {}, []
        self.rows, self.positions, self.trades, self.events, self.ledger = [], [], [], [], []
        self.nav_before = float(nav)

    # One session: interest, returns, exits, dividends, borrow, trades.
    def step(self, i: int, d: pd.Timestamp, order):
        m = self.m
        # Yesterday's closing cash earns today's bill; day 0 is the endowment.
        interest = self.cash * m.rf[i] if i else 0.0
        self.cash += interest
        month = m.month[i]
        dividends = borrowed = cost = turnover = 0.0
        # Each open's holding, carried to month end; the least good one counts.
        for key in m.bound_by_month.get(month, ()):
            seen = self.values.get(key[0], 0.0) * m.bound[key][i]
            self.lowest[key] = min(self.lowest.get(key, np.inf), seen)
        for permno in list(self.values):
            value = self.values[permno]
            j = m.col[permno]
            # The holding at its ex-day's open is what δ is paid on.
            if m.exday.get((permno, month)) == i:
                self.entitled[(permno, month)] = value
            r, how = self.day_return(i, j, permno, d)
            if how == "missing":
                self.handle_missing(permno, d, value)
                continue
            self.values[permno] = value * (1 + r)
            self.book(d, permno, "price", value * r)
            if abs(r) > BIG_MOVE:
                self.event(d, permno, "big_move", r)
            # Outside δ's months CRSP's dividends; in them, if CRSP dates δ.
            key = (permno, month)
            if key not in m.delta:
                dividends += self.crsp_dividend(i, j, permno, d, value, r, how)
            elif m.ex_source.startswith("crsp") and key in m.exday:
                paid = self.crsp_dividend(i, j, permno, d, value, r, how)
                self.accrued[key] = self.accrued.get(key, 0.0) + paid
                dividends += paid
        self.true_ups(i, d)
        if i in m.last_of_month:
            dividends += self.month_dividends(d, month)
        self.cash += dividends
        shorts = pd.Series({p: -v for p, v in self.values.items() if v < 0}, dtype=float)
        if self.borrow is not None and len(shorts):
            fee = self.borrow(d, shorts)
            borrowed = self.spread(d, "borrow", fee, shorts)
            self.cash -= borrowed
        nav = self.cash + sum(self.values.values())
        pre = self.marks(nav)
        # Orders are sized on the previous close's NAV (PLAN §9.1).
        if order is not None:
            self.formations.append((d, order[0]))
            before, start = dict(self.values), len(self.trades)
            self.pre_positions.extend((d, p, v) for p, v in before.items())
            cost = self.trade(i, d, order[0], order[1], self.nav_before)
            nav = self.cash + sum(self.values.values())
            turnover = self.turnover(before, pre["nav"], nav, start)
        self.record(i, d, nav, interest, dividends, borrowed, cost, turnover, pre, order)

    # A held stock's return today, and where it came from.
    def day_return(self, i: int, j: int, permno: int, d: pd.Timestamp):
        m = self.m
        if m.has_row[i, j]:
            r, price = m.ret[i, j], m.prc[i, j]
            if np.isnan(r):
                # After a gap, the price ratio if finite, else 0, flagged.
                last = self.last_price.get(permno)
                ok = last is not None and last > 0 and np.isfinite(price) and price > 0
                r = price / last - 1 if ok else 0.0
                self.event(d, permno, "gap_ratio" if ok else "null_return_zero", r)
            if np.isfinite(price) and price > 0:
                self.last_price[permno] = price
            self.missing.pop(permno, None)
            return float(r), "dsf"
        if d <= data.CRSP_END and not np.isnan(m.crsp_retx[i, j]):
            # The dsf lost a stock CRSP still trades: marked, sold next (2B).
            r = float(m.crsp_retx[i, j])
            self.missing.pop(permno, None)
            if permno in self.last_price:
                self.last_price[permno] *= 1 + r
            if permno not in self.sell_next:
                self.event(d, permno, "crsp_mark", r)
            self.sell_next.add(permno)
            return r, "crsp"
        return 0.0, "missing"

    # A missing day: hold, book a known exit, or stub on the fifth day.
    def handle_missing(self, permno: int, d: pd.Timestamp, value: float):
        streak = self.missing.get(permno, 0) + 1
        self.missing[permno] = streak
        # A CRSP-marked name still held when CRSP ends closes at its mark.
        if permno in self.sell_next and d > data.CRSP_END:
            self.close(permno, value, d, "crsp_end_close", 0.0)
            return
        known = self.m.exit_known(permno, d, self.opened[permno])
        if known is not None:
            ret = self.m.exit_return(permno, known, value < 0)
            kind = "exit"
            if np.isnan(ret):
                ret, kind = self.stub_return(value), "exit_stub"
            self.close(permno, value * (1 + ret), d, kind, ret)
        elif streak >= STUB_DAYS:
            stub = self.stub_return(value)
            self.stubs[permno] = (value, value * (1 + stub), self.opened[permno])
            self.close(permno, value * (1 + stub), d, "stub", stub)
        else:
            self.event(d, permno, "halt_day", streak)

    # The stub's provisional return on a long or a short.
    @staticmethod
    def stub_return(value: float) -> float:
        return STUB_LONG if value > 0 else STUB_SHORT

    # A stub trued up once its exit's final return is known (PLAN §6.4).
    def true_ups(self, i: int, d: pd.Timestamp):
        m = self.m
        for permno, (before, booked, opened) in list(self.stubs.items()):
            # A halt that resumes keeps its stub; a later exit never moves it.
            if m.has_row[i, m.col[permno]]:
                del self.stubs[permno]
                self.event(d, permno, "stub_kept", booked - before)
                continue
            known = m.exit_known(permno, d, opened)
            if known is None:
                continue
            ret = m.exit_return(permno, known, before < 0)
            del self.stubs[permno]
            # A failure with no final return keeps its stub (A12).
            if np.isnan(ret):
                self.event(d, permno, "stub_kept", booked - before)
                continue
            final = before * (1 + ret)
            self.cash += final - booked
            self.book(d, permno, "true_up", final - booked)
            self.event(d, permno, "true_up", final - booked)

    # A position ends: its value goes to cash and is logged.
    def close(self, permno: int, value: float, d: pd.Timestamp, kind: str, ret: float):
        self.book(d, permno, kind, value - self.values[permno])
        self.cash += value
        del self.values[permno]
        self.opened.pop(permno, None)
        self.missing.pop(permno, None)
        self.event(d, permno, kind, ret)

    # CRSP's dividend, `ret` less `retx`, on its own days through 2025.
    def crsp_dividend(self, i, j, permno, d, value: float, r: float, how: str) -> float:
        m = self.m
        if m.dividends == "none" or d > data.CRSP_END:
            return 0.0
        tot, px = m.crsp_ret[i, j], m.crsp_retx[i, j]
        if np.isnan(tot) or np.isnan(px):
            return 0.0
        paid = tot - px
        # A spin-off the dsf prices as a fall: the value it missed that day.
        if how == "dsf" and not np.isnan(m.ret[i, j]) and abs(px - r) > MISSED:
            paid += px - r
            self.event(d, permno, "dsf_distribution", px - r)
        self.book(d, permno, "dividend", value * paid)
        return value * paid

    # δ on the month's last session to the holders at its ex-day's open.
    def month_dividends(self, d: pd.Timestamp, month) -> float:
        m, total = self.m, 0.0
        for key in sorted(k for k in self.lowest if k[1] == month):
            owed = self.lowest.pop(key) * m.delta[key]
            self.book(d, key[0], "delta", owed)
            total += owed
        keys = {k for k in self.entitled if k[1] == month} | {
            k for k in self.accrued if k[1] == month
        }
        for key in sorted(keys):
            owed = self.entitled.pop(key, 0.0) * m.after[key] * m.delta[key]
            # CRSP's dividends already paid this month are trued up to δ.
            paid = self.accrued.pop(key, 0.0)
            self.trued += owed - paid
            self.book(d, key[0], "delta", owed - paid)
            total += owed - paid
        # The δ guard's flags, logged on the day the month is booked.
        for key in sorted(k for k in m.flags if k[1] == month):
            self.event(d, key[0], *m.flags[key])
        return total

    # Trades at the close toward the target weights, where a stock trades.
    def trade(self, i: int, d: pd.Timestamp, formed, target: pd.Series, nav: float) -> float:
        m = self.m
        want = target.copy()
        for permno in self.sell_next:
            want[permno] = 0.0
        moves = {}
        for permno in sorted(set(want.index) | set(self.values)):
            j = m.col.get(permno)
            goal = float(want.get(permno, 0.0)) * nav
            have = self.values.get(permno, 0.0)
            if abs(goal - have) < 1e-6:
                continue
            ok = j is not None and m.has_row[i, j] and not np.isnan(m.ret[i, j])
            crsp = j is not None and d <= data.CRSP_END and not np.isnan(m.crsp_retx[i, j])
            # A sale may use CRSP's close; a purchase needs the dsf's (2B).
            if not ok and not (goal == 0.0 and crsp):
                self.event(d, permno, "unfilled", goal - have)
                continue
            moves[permno] = goal - have
        moved = pd.Series(moves, dtype=float)
        cost = self.spread(d, "cost", self.costs(d, moved), moved) if self.costs and moves else 0.0
        for permno, move in moves.items():
            new = self.values.get(permno, 0.0) + move
            self.cash -= move
            if abs(new) < 1e-6:
                self.values.pop(permno, None)
                self.opened.pop(permno, None)
            else:
                self.opened.setdefault(permno, d)
                self.values[permno] = new
            # A fill sets the price a later gap ratio starts from.
            j = m.col.get(permno)
            if j is not None and np.isfinite(m.prc[i, j]) and m.prc[i, j] > 0:
                self.last_price[permno] = float(m.prc[i, j])
            self.trades.append([d, formed, permno, move, new])
        self.cash -= cost
        # A sale that could not fill waits for the next formation.
        self.sell_next = {p for p in self.sell_next if p in self.values}
        return cost

    # A cost or fee booked per name: its own split, else by size (§9.1).
    def spread(self, d, kind: str, fee, sizes: pd.Series) -> float:
        if isinstance(fee, pd.Series):
            parts = fee.reindex(sizes.index).fillna(0.0)
        else:
            weights = sizes.abs() / sizes.abs().sum()
            parts = weights * float(fee)
        for permno, dollars in parts.items():
            self.book(d, permno, kind, -float(dollars))
        return float(parts.sum())

    # PDF p20 turnover: ½ Σ |weight after - weight carried in|, one close.
    def turnover(self, before: dict, nav_pre: float, nav_post: float, start: int) -> float:
        names = set(before) | set(self.values)
        for row in self.trades[start:]:
            row += [before.get(row[2], 0.0) / nav_pre, self.values.get(row[2], 0.0) / nav_post]
        return 0.5 * sum(
            abs(self.values.get(p, 0.0) / nav_post - before.get(p, 0.0) / nav_pre) for p in names
        )

    # The book's weights before any trade (PDF p4 "at all times").
    def marks(self, nav: float) -> dict:
        w = np.array(list(self.values.values()), dtype=float) / nav
        top = float(np.abs(w).max()) if len(w) else 0.0
        return dict(nav=nav, gross=float(np.abs(w).sum()), net=float(w.sum()), top=top)

    # One row of the daily table and the day's closing positions.
    def record(self, i, d, nav, interest, dividends, borrowed, cost, turnover, pre, order):
        ret = nav / self.nav_before - 1
        self.nav_before = nav
        w = np.array(list(self.values.values()), dtype=float) / nav
        self.rows.append(
            dict(
                date=d,
                nav=nav,
                ret=ret,
                rf=float(self.m.rf[i]),
                interest=interest,
                dividends=dividends,
                delta_true_up=self.take_true_up(),
                borrow=borrowed,
                cost=cost,
                turnover=turnover,
                traded=order is not None,
                gross=float(np.abs(w).sum()),
                net=float(w.sum()),
                nav_pre=pre["nav"],
                gross_pre=pre["gross"],
                net_pre=pre["net"],
                max_weight_pre=pre["top"],
                n_long=int((w > 0).sum()),
                n_short=int((w < 0).sum()),
                max_weight=float(np.abs(w).max()) if len(w) else 0.0,
            )
        )
        self.positions.extend((d, p, v) for p, v in self.values.items())

    # The δ true-up booked since the last row, then reset.
    def take_true_up(self) -> float:
        out, self.trued = self.trued, 0.0
        return out

    # One dollar line of the per-name ledger (PDF p21, p24).
    def book(self, d, permno, kind: str, dollars: float):
        if dollars:
            self.ledger.append((d, int(permno), kind, float(dollars)))

    # One logged event: a halt day, a stub, a true-up, a CRSP mark.
    def event(self, d, permno, kind, value):
        self.events.append((d, permno, kind, value))

    # The run's tables, with compliance against the rules.
    def result(self) -> Result:
        daily = pd.DataFrame(self.rows).set_index("date")
        positions = pd.DataFrame(self.positions, columns=["date", "permno", "value"])
        cols = ["date", "formed", "permno", "dollars", "after", "w_before", "w_after"]
        trades = pd.DataFrame(self.trades, columns=cols)
        events = pd.DataFrame(self.events, columns=["date", "permno", "kind", "value"])
        ledger = pd.DataFrame(self.ledger, columns=["date", "permno", "kind", "dollars"])
        check = compliance(daily, positions, self)
        return Result(daily, positions, trades, events, check, ledger)


# Daily checks: names by stock and company, gross, net, caps, floor.
def compliance(daily, positions, book: Book) -> pd.DataFrame:
    rules = book.rules
    pre = pd.DataFrame(book.pre_positions, columns=["date", "permno", "value"])
    both = pd.concat([positions.assign(pre=False), pre.assign(pre=True)], ignore_index=True)
    both = both.sort_values(["date", "pre"], kind="stable", ignore_index=True)
    nav = np.where(both["pre"], both["date"].map(daily["nav_pre"]), both["date"].map(daily["nav"]))
    both["size"] = both["value"].abs() / nav
    both["permco"] = data.permcos(both["permno"], both["date"]).to_numpy()
    # A link that ends at the last trade keeps the stock's last company.
    both["permco"] = both.groupby("permno")["permco"].ffill().fillna(-both["permno"])
    pos = both[~both["pre"]].assign(weight=lambda f: f["value"] / f["date"].map(daily["nav"]))
    out = pd.DataFrame(index=daily.index)
    after, before = held(pos, out.index), held(both[both["pre"]], out.index)
    out = out.join(after).fillna(0).join(before.add_suffix("_pre"))
    # Every trade day after the first holds names before its trades.
    days = sorted({d for d, _ in book.formations})[1:]
    cols = ["names_pre", "companies_pre", "max_company_weight_pre"]
    out.loc[out.index.isin(days), cols] = out.loc[out.index.isin(days), cols].fillna(0)
    out["gross"], out["net"] = daily["gross"], daily["net"]
    out["max_weight"] = daily["max_weight"]
    lo, hi = rules["names_min"], rules["names_max"]
    counts = out[["names", "companies"]].join(out[["names_pre", "companies_pre"]])
    out["names_ok"] = (counts.isna() | ((counts >= lo) & (counts <= hi))).all(axis=1)
    # Marks before and after each day's trades both count (PDF p4).
    gross = daily[["gross", "gross_pre"]].max(axis=1)
    net = daily[["net", "net_pre"]].abs().max(axis=1)
    out["gross_ok"] = gross <= rules["gross"] + 1e-12
    out["net_ok"] = net <= rules["net_band"] + 1e-12
    caps = ["max_weight", "max_company_weight", "max_company_weight_pre"]
    worst = pd.concat([out[caps], daily["max_weight_pre"]], axis=1)
    out["cap_ok"] = worst.max(axis=1) <= rules["name_cap"] + 1e-12
    floor = short_floor(positions, book, rules)
    out = out.join(floor).fillna({c: 0 for c in floor.columns})
    out["short_floor_breaches"] = out[["floor_at_formation", "floor_at_trade"]].max(axis=1)
    # Before the first trade the book is cash: no name rule applies yet.
    first = min((d for d, _ in book.formations), default=out.index[-1])
    out["invested"] = out.index >= first
    out.loc[~out["invested"], "names_ok"] = True
    out["days_of_adv_max"] = days_of_adv(pos, book)
    out["beta_sp500_252d"] = book_beta(daily, book)
    return out


# Names, companies and the largest company weight on each day.
def held(pos: pd.DataFrame, index) -> pd.DataFrame:
    by_co = pos.groupby(["date", "permco"])["size"].sum()
    out = pd.DataFrame(
        {
            "names": pos.groupby("date")["permno"].nunique(),
            "companies": pos.groupby("date")["permco"].nunique(),
            "max_company_weight": by_co.groupby(level=0).max(),
        }
    )
    return out.reindex(index)


# Days that break a PDF limit once the book is invested (PLAN §9.3).
def breaches(result: Result) -> pd.DataFrame:
    c = result.compliance
    bad = c["invested"] & (
        ~c["names_ok"] | ~c["gross_ok"] | ~c["net_ok"] | ~c["cap_ok"]
        | (c["short_floor_breaches"] > 0)
    )  # fmt: skip
    return c[bad]


# The largest position in days of ADV, at the last month end's ADV.
def days_of_adv(pos: pd.DataFrame, book: Book) -> pd.Series:
    if pos.empty:
        return pd.Series(dtype=float)
    ends = {d: data.month_end_at(d) for d in pos["date"].unique()}
    adv = book.m.panel["dolvol_126d"]
    keys = list(zip(pos["permno"], pos["date"].map(ends)))
    size = pos["value"].abs().to_numpy() / adv.reindex(keys).to_numpy()
    return pd.Series(size, index=pos["date"].to_numpy()).groupby(level=0).max()


# The book's 252-session OLS beta on the S&P 500, excess of the bill.
def book_beta(daily: pd.DataFrame, book: Book) -> pd.Series:
    y = daily["ret"] - daily["rf"]
    x = pd.Series(book.m.sp500, index=daily.index) - daily["rf"]
    return y.rolling(BETA_DAYS).cov(x) / x.rolling(BETA_DAYS).var()


# Shorts held under the floor at the decision close or the trade close.
def short_floor(positions: pd.DataFrame, book: Book, rules: dict) -> pd.DataFrame:
    rows = {}
    held = positions[positions["value"] < 0]
    floor = rules["short_min_market_cap"]
    # Every short held after a formation's trades, on both days (set 4).
    for d, formed in book.formations:
        names = held.loc[held["date"] == d, "permno"]
        at_t = np.array([book.m.cap_at(p, formed) for p in names], dtype=float)
        at_trade = np.array([book.m.cap_at(p, d) for p in names], dtype=float)
        rows[d] = (int((~(at_t >= floor)).sum()), int((~(at_trade >= floor)).sum()))
    return pd.DataFrame.from_dict(
        rows, orient="index", columns=["floor_at_formation", "floor_at_trade"]
    )


# Each name's dollars over a run by kind: price, dividends, costs.
def contributions(result: Result) -> pd.DataFrame:
    led = result.ledger
    return led.pivot_table(
        index="permno", columns="kind", values="dollars", aggfunc="sum", fill_value=0.0
    ).assign(total=lambda t: t.sum(axis=1))


# The stub log by year and leg and the halt log (PLAN §4.3, §6.4).
def logs(result: Result) -> dict:
    ev = result.events
    stubs = ev[ev["kind"].isin(["stub", "exit_stub", "true_up", "stub_kept"])].copy()
    # The leg is the stub's own sign; its true-up inherits it.
    written = stubs["kind"].isin(["stub", "exit_stub"])
    stubs["leg"] = np.where(written, np.where(stubs["value"] < 0, "long", "short"), None)
    stubs["leg"] = stubs.groupby("permno")["leg"].ffill()
    stubs["year"] = stubs["date"].dt.year
    by_year = stubs.groupby(["year", "leg", "kind"]).size().rename("count").reset_index()
    # Each halt runs from a streak of 1 to its last missing day.
    days = ev[ev["kind"] == "halt_day"].copy()
    days["halt"] = (days["value"] == 1).groupby(days["permno"]).cumsum()
    halts = days.groupby(["permno", "halt"])["date"].agg(["min", "max", "size"])
    return {"stubs": stubs, "stubs_by_year": by_year, "halts": halts.reset_index()}


# Calendar-month returns of a run, compounded from its daily rows.
def monthly(daily: pd.DataFrame) -> pd.DataFrame:
    g = (1 + daily[["ret", "rf"]]).groupby(daily.index.to_period("M")).prod() - 1
    g["excess"] = g["ret"] - g["rf"]
    return g
