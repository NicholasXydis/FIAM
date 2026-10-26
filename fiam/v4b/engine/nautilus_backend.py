"""NautilusTrader quantity/account backtest. No legacy simulated fills are used."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.config import (
    BacktestEngineConfig,
    CacheConfig,
    LoggingConfig,
    RiskEngineConfig,
    SimulationModuleConfig,
)
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from fiam.v4b.engine import fees as fee_schedule
from fiam.v4b.engine.nautilus_data import Feed
from fiam.v4b.engine.sim import Setup

VENUE = Venue("V4B")
CLOCK = InstrumentId.from_str("CLOCK.V4B")
PRECISION = 8


def equity(iid):
    return Equity(
        instrument_id=iid,
        raw_symbol=iid.symbol,
        currency=USD,
        price_precision=PRECISION,
        price_increment=Price(1e-8, PRECISION),
        lot_size=Quantity(1, 0),
        margin_init=Decimal(".5"),
        margin_maint=Decimal(".25"),
        ts_event=0,
        ts_init=0,
    )


def row(value, k, n, default=0.0):
    if isinstance(value, pd.DataFrame):
        return np.nan_to_num(value.iloc[k].to_numpy(dtype=float), nan=default)
    return np.full(n, float(value))


class Funding(SimulationModule):
    def __init__(self):
        super().__init__(SimulationModuleConfig())

    def process(self, ts_now):
        pass

    def log_diagnostics(self, logger):
        pass

    def reset(self):
        pass

    def adjust(self, value):
        amount = Money(value, USD)
        self.exchange.adjust_account(amount)
        return amount.as_double()


# Spread and impact as before; fees from the dated schedule (engine/fees.py),
# per order on actual shares. A settlement of a stale quote (see run) pays the
# half-spread and fees but no impact: there is no volume to impact.
class Costs(FeeModel):
    def __init__(self, feed, setup, index):
        super().__init__()
        self.feed, self.setup, self.index = feed, setup, index
        self.k = 0
        self.lines = []
        self.settling = set()

    def get_commission(self, order, fill_qty, fill_px, instrument):
        j = self.index[instrument.id]
        dollars = fill_qty.as_double() * fill_px.as_double()
        n = len(self.index)
        spread = dollars * row(self.feed.half_spread, self.k - 1, n, 0.005)[j]
        if j in self.settling:
            impact = 0.0
        else:
            adv = float(self.feed.adv.iloc[self.k - 1, j])
            sigma = float(self.feed.sigma.iloc[self.k - 1, j])
            sigma = sigma if np.isfinite(sigma) else 0.02
            impact = self.setup.impact_y * sigma * dollars * np.sqrt(dollars / adv)
        sell = order.side == OrderSide.SELL
        if self.setup.fee_schedule == "flat":
            fees = dollars * (self.setup.commission + (self.setup.sec_rate if sell else 0.0))
        else:
            raw = self.feed.raw_close
            px = float(raw.iloc[self.k - 1, j]) if raw is not None else np.nan
            fees = fee_schedule.order(dollars, px, sell)
        money = Money(spread + impact + fees, USD)
        fees += money.as_double() - spread - impact - fees
        self.lines.append((self.k, spread, impact, fees))
        return money


@dataclass
class Result:
    ledger: pd.DataFrame
    positions: pd.DataFrame
    intents: pd.DataFrame
    native_orders: pd.DataFrame
    native_fills: pd.DataFrame
    native_positions: pd.DataFrame
    native_accounts: pd.DataFrame


class Controller(Strategy):
    def __init__(self, targets, feed, setup, instruments, costs, funding):
        super().__init__()
        self.targets, self.feed, self.setup = targets, feed, setup
        self.instruments, self.costs, self.funding = instruments, costs, funding
        self.names = list(feed.prices.columns)
        self.lookup = {iid: j for j, iid in enumerate(instruments)}
        self.marks = {}
        self.k = 0
        self.pending = None
        self.execution = {feed.prices.index[feed.prices.index.get_loc(d) + 1]: d for d in targets}
        self.wanted = {}
        self.left = 0
        self.signal = None
        self.ledger = []
        self.books = []
        self.intents = []
        self.prev_nav = setup.nav0
        self.missing = np.zeros(len(self.names), dtype=int)
        self.prev_values = np.zeros(len(self.names))

    def on_start(self):
        for iid in [*self.instruments, CLOCK]:
            self.subscribe_quote_ticks(iid)

    def quantities(self):
        out = np.zeros(len(self.names), dtype=np.int64)
        for p in self.cache.positions_open():
            if p.instrument_id in self.lookup:
                out[self.lookup[p.instrument_id]] += int(p.signed_qty)
        return out

    def nav(self):
        account = self.portfolio.account(VENUE)
        value = account.balance_total(USD).as_double()
        for p in self.cache.positions_open():
            if p.instrument_id in self.marks:
                value += p.unrealized_pnl(self.marks[p.instrument_id]).as_double()
        return value

    def on_quote_tick(self, tick):
        if tick.instrument_id == CLOCK:
            self.close()
        else:
            self.marks[tick.instrument_id] = tick.bid_price

    def close(self):
        k = self.k
        day = self.feed.prices.index[k]
        n = len(self.names)
        quantities = self.quantities()
        marks = np.array(
            [self.marks[i].as_double() if i in self.marks else np.nan for i in self.instruments]
        )
        values = quantities * np.nan_to_num(marks)
        observed = self.observed
        self.missing = np.where(observed, 0, self.missing + 1)
        before = self.nav()
        price_pnl = 0.0 if not self.ledger else before - self.prev_nav
        interest = borrow = distributions = 0.0
        if self.ledger:
            cash = self.prev_nav - self.prev_values.sum()
            rate = float(self.feed.rf.iloc[k]) + (
                self.setup.debit_spread / 252 if cash < 0 else 0.0
            )
            interest = self.funding.adjust(cash * rate)
            distributions = self.funding.adjust(
                float(quantities @ self.feed.dividends.iloc[k].fillna(0).to_numpy())
            )
            borrow = -self.funding.adjust(
                -float((-np.minimum(values, 0)) @ row(self.feed.borrow, k, n)) / 252
            )
        pre_nav = self.nav()
        pre = values.copy()
        rebal = day in self.execution
        if rebal:
            if self.left > 0:
                self.record_intents("SUPERSEDED", quantities)
            self.signal = self.execution[day]
            desired = self.pending.reindex(self.names).fillna(0).to_numpy()
            self.wanted = {}
            for j, w in enumerate(desired):
                if w == 0 and quantities[j] == 0:
                    continue
                if w == 0:
                    self.wanted[j] = 0
                elif np.isfinite(marks[j]) and marks[j] > 0:
                    self.wanted[j] = int(np.trunc(w * pre_nav / marks[j]))
                else:
                    self.wanted[j] = int(quantities[j])
            self.left = self.setup.spill_days + 1
        start = len(self.costs.lines)
        self.costs.k = k
        settled = np.zeros(n)
        for j in sorted(self.costs.settling):
            if quantities[j] == 0:
                continue
            settled[j] = -quantities[j] * marks[j]
            self.submit_order(
                self.order_factory.market(
                    self.instruments[j],
                    OrderSide.SELL if quantities[j] > 0 else OrderSide.BUY,
                    Quantity(abs(int(quantities[j])), 0),
                    time_in_force=TimeInForce.IOC,
                )
            )
            self.wanted.pop(j, None)
        if self.left > 0:
            adv = self.feed.adv.iloc[k - 1].to_numpy(dtype=float)
            allowed = self.feed.tradable.iloc[k].to_numpy(dtype=bool)
            for j in sorted(self.wanted):
                change = self.wanted[j] - int(quantities[j])
                if (
                    not change
                    or not allowed[j]
                    or not np.isfinite(adv[j])
                    or adv[j] <= 0
                    or not np.isfinite(marks[j])
                    or marks[j] <= 0
                ):
                    continue
                cap = int(np.floor(self.setup.participation * adv[j] / marks[j]))
                # Even pacing over the remaining execution days, the schedule
                # the optimizer's impact term assumes (EXEC_DAYS); front-loading
                # to the participation cap costs up to sqrt(5) more impact.
                slice_ = int(np.ceil(abs(change) / self.left)) if self.setup.paced else abs(change)
                amount = min(slice_, cap)
                if amount <= 0:
                    continue
                order = self.order_factory.market(
                    self.instruments[j],
                    OrderSide.BUY if change > 0 else OrderSide.SELL,
                    Quantity(amount, 0),
                    time_in_force=TimeInForce.IOC,
                )
                self.submit_order(order)
            self.left -= 1
            self.record_intents("EXPIRED" if self.left == 0 else "WORKING", self.quantities())
        after_q = self.quantities()
        after_values = after_q * np.nan_to_num(marks)
        nav = self.nav()
        charges = self.costs.lines[start:]
        spread = sum(x[1] for x in charges)
        impact = sum(x[2] for x in charges)
        fees = sum(x[3] for x in charges)
        trade = (after_q - quantities) * np.nan_to_num(marks)
        self.ledger.append(
            dict(
                date=day,
                nav=nav,
                ret=0.0 if not self.ledger else nav / self.prev_nav - 1,
                pnl=price_pnl + distributions,
                interest=interest,
                spread=spread,
                impact=impact,
                fees=fees,
                borrow=borrow,
                distributions=distributions,
                turnover=0.5 * np.abs(trade).sum() / pre_nav,
                stub=0.0,
            )
        )
        live = (after_q != 0) | (quantities != 0)
        if live.any():
            known_adv = self.feed.adv.iloc[max(k - 1, 0)].to_numpy(dtype=float)
            self.books.append(
                pd.DataFrame(
                    dict(
                        date=day,
                        permno=np.asarray(self.names)[live],
                        quantity=after_q[live],
                        w=after_values[live] / nav,
                        w_pre=pre[live] / pre_nav,
                        rebalance=rebal,
                        trade_dollars=trade[live],
                        synthetic_exit_dollars=settled[live],
                        adv_dollars=known_adv[live],
                        adv_days=np.abs(after_values[live]) / known_adv[live],
                        missing_sessions=self.missing[live],
                        unverified_gap=(
                            self.feed.unverified_gaps.iloc[k].to_numpy()[live]
                            if self.feed.unverified_gaps is not None
                            else False
                        ),
                    )
                )
            )
        self.prev_nav = nav
        self.prev_values = after_values
        if day in self.targets:
            target = self.targets[day]
            weights = pd.Series(after_values / nav, index=self.names)
            self.pending = (
                target(weights[weights.abs() > 1e-12], nav) if callable(target) else target
            )

    def record_intents(self, status, held):
        for j, want in self.wanted.items():
            remaining = int(want - held[j])
            self.intents.append(
                dict(
                    date=self.feed.prices.index[self.k],
                    signal=self.signal,
                    permno=self.names[j],
                    target_qty=want,
                    remaining_qty=remaining,
                    status="COMPLETE" if remaining == 0 else status,
                )
            )


def run(
    targets,
    feed: Feed,
    setup=Setup(),
    report_dir: Path | None = None,
    native_reports: bool = True,
):
    first = feed.prices.index.get_loc(min(targets))
    if first == len(feed.prices) - 1:
        raise ValueError("signal has no next execution session")
    instruments = [InstrumentId.from_str(f"P{p}.V4B") for p in feed.prices.columns]
    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggingConfig(bypass_logging=True),
            cache=CacheConfig(tick_capacity=1),
            risk_engine=RiskEngineConfig(max_order_submit_rate="100000/00:00:01"),
        )
    )
    funding = Funding()
    costs = Costs(feed, setup, {iid: j for j, iid in enumerate(instruments)})
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(setup.nav0, USD)],
        base_currency=USD,
        default_leverage=Decimal(1),
        fee_model=costs,
        modules=[funding],
        use_message_queue=False,
    )
    for iid in [*instruments, CLOCK]:
        engine.add_instrument(equity(iid))
    controller = Controller(targets, feed, setup, instruments, costs, funding)
    engine.add_strategy(controller)
    for k in range(first, len(feed.prices)):
        controller.k = k
        costs.k = k
        stamp = int(pd.Timestamp(feed.prices.index[k]).value) + 21 * 3600 * 10**9
        batch = []
        controller.observed = np.zeros(len(instruments), dtype=bool)
        held_before = controller.quantities()
        costs.settling = set()
        for j, value in enumerate(feed.prices.iloc[k].to_numpy(dtype=float)):
            if not np.isfinite(value) or value < 0 or (value == 0 and held_before[j] < 0):
                # A position unquoted for stub_days sessions is settled at its
                # last mark (both sides). For >= $500m names the panel's
                # month return after the last quote averages -0.06% (93% within
                # 2%), so the last mark is the delisting value; LESSONS 66.
                # Only past quotes are used: a later reappearance is not known.
                mark = controller.marks.get(instruments[j])
                if (
                    held_before[j] != 0
                    and controller.missing[j] + 1 >= setup.stub_days
                    and mark is not None
                ):
                    costs.settling.add(j)
                    batch.append(QuoteTick(instruments[j], mark, mark, Quantity(10**9, 0),
                                           Quantity(10**9, 0), stamp, stamp))
                continue
            controller.observed[j] = True
            price = Price(float(value), PRECISION)
            qty = Quantity(10**9, 0)
            batch.append(QuoteTick(instruments[j], price, price, qty, qty, stamp, stamp))
        one = Price(1.0, PRECISION)
        qty = Quantity(1, 0)
        batch.append(QuoteTick(CLOCK, one, one, qty, qty, stamp + 1, stamp + 1))
        engine.add_data(batch)
        engine.run(streaming=True)
        engine.clear_data()
    engine.end()
    result = Result(
        pd.DataFrame(controller.ledger).set_index("date"),
        pd.concat(controller.books, ignore_index=True) if controller.books else pd.DataFrame(),
        pd.DataFrame(controller.intents),
        engine.trader.generate_orders_report() if native_reports else pd.DataFrame(),
        engine.trader.generate_fills_report() if native_reports else pd.DataFrame(),
        engine.trader.generate_positions_report() if native_reports else pd.DataFrame(),
        engine.trader.generate_account_report(VENUE) if native_reports else pd.DataFrame(),
    )
    if report_dir is not None:
        from fiam.v4b.engine.nautilus_reports import save

        save(engine, result, Path(report_dir))
    engine.dispose()
    return result
