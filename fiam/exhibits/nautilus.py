# An independent accounting check: NautilusTrader replays each month of a book in whole shares.

import json
import sys
from decimal import Decimal

import numpy as np
import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.config import (
    BacktestEngineConfig,
    LoggingConfig,
    RiskEngineConfig,
    SimulationModuleConfig,
)
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from fiam import data, v2

VENUE = Venue("REPLAY")
CLOCK = InstrumentId.from_str("CLOCK.REPLAY")
PRECISION, NAV = 6, 10_000_000.0
# Windows' build caps a quantity near 1.8e10, so bar volume stays well below it.
VOLUME = Quantity(10**10, 0)
FIRST, LAST = "2020-12-31", "2025-12-31"
OUT = v2.OUT / "nautilus"


# One stock as a Nautilus instrument priced in whole shares.
def equity(instrument_id: InstrumentId) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.symbol,
        currency=USD,
        price_precision=PRECISION,
        price_increment=Price(10**-PRECISION, PRECISION),
        lot_size=Quantity(1, 0),
        margin_init=Decimal("0.5"),
        margin_maint=Decimal("0.25"),
        ts_event=0,
        ts_init=0,
    )


# Costs reach the account as cash on the trade day, so no fill pays a fee of its own.
class NoFees(FeeModel):
    def get_commission(self, order, fill_qty, fill_px, instrument):
        return Money(0, USD)


# Each month's modelled costs as a share of the NAV it traded at, debited the next trading day,
# inside the holding month as the ledger books them.
class Costs(SimulationModule):
    def __init__(self, schedule: dict, strategy):
        super().__init__(SimulationModuleConfig())
        self.schedule, self.strategy, self.seen = schedule, strategy, set()

    def process(self, ts_now):
        if ts_now in self.schedule and ts_now not in self.seen:
            share, traded_at = self.schedule[ts_now]
            nav = self.strategy.traded_nav.get(traded_at, NAV)
            self.exchange.adjust_account(Money(-share * nav, USD))
            self.seen.add(ts_now)

    def log_diagnostics(self, logger):
        pass

    def reset(self):
        self.seen.clear()


# Trades to each month's target weights at the decision close, and samples NAV every month end.
class Rebalance(Strategy):
    def __init__(self, targets: dict, bar_types: list, month_ends: set):
        super().__init__()
        self.targets, self.bar_types, self.month_ends = targets, bar_types, month_ends
        self.marks, self.navs, self.traded_nav = {}, {}, {}

    def on_start(self):
        for bar_type in self.bar_types:
            self.subscribe_bars(bar_type)

    def nav(self) -> float:
        account = self.portfolio.account(VENUE)
        open_ = self.cache.positions_open()
        pnl = sum(p.unrealized_pnl(self.marks[p.instrument_id]).as_double() for p in open_)
        return account.balance_total(USD).as_double() + pnl

    def on_bar(self, bar):
        instrument = bar.bar_type.instrument_id
        if instrument != CLOCK:
            self.marks[instrument] = bar.close
            return
        stamp = bar.ts_event - 1_000_000_000
        if stamp in self.month_ends:
            self.navs[stamp] = self.nav()
        if stamp in self.targets:
            self.traded_nav[stamp] = self.nav()
            self.trade(self.targets[stamp], self.traded_nav[stamp])

    def trade(self, weights: dict, nav: float) -> None:
        held = {p.instrument_id: int(p.signed_qty) for p in self.cache.positions_open()}
        for instrument in sorted(set(held) | set(weights), key=str):
            price = self.marks.get(instrument)
            if price is None:
                continue
            want = int(np.rint(weights.get(instrument, 0.0) * nav / price.as_double()))
            change = want - held.get(instrument, 0)
            if change:
                side = OrderSide.BUY if change > 0 else OrderSide.SELL
                order = self.order_factory.market(instrument, side, Quantity(abs(change), 0))
                self.submit_order(order)


# A synthetic total-return price per stock: dividends and splits are inside, never added again.
def prices(permnos: list) -> pd.DataFrame:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    daily = daily[daily["permno"].isin(permnos) & daily["date"].between(FIRST, LAST)]
    wide = daily.pivot_table(index="date", columns="permno", values="total_return")
    return 100 * (1 + wide.fillna(0.0)).cumprod()


# One book's monthly replay against its own ledger; the protocol's tolerances decide the check.
def replay(name: str) -> dict:
    folder = v2.OUT / name / "record"
    held = data.read(folder / "holdings.parquet")
    held = held[held["eom"].between(FIRST, "2025-11-30")]
    book = pd.read_csv(folder / "returns.csv", parse_dates=["holding_month", "forecast_eom"])
    px = prices(sorted(held["permno"].unique()))
    days = px.index
    stamp = {d: int(pd.Timestamp(d).value) for d in days}
    trade_day = {eom: days[days <= eom][-1] for eom in held["eom"].unique()}
    month_ends = {
        stamp[d] for d in pd.Series(days).groupby(pd.Series(days).dt.to_period("M")).max()
    }

    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggingConfig(bypass_logging=True),
            risk_engine=RiskEngineConfig(max_order_submit_rate="100000/00:00:01"),
        )
    )
    costs = {}
    following = dict(zip(days[:-1], days[1:]))
    for eom, g in book.groupby("forecast_eom"):
        if eom in trade_day and trade_day[eom] in following:
            when = stamp[following[trade_day[eom]]]
            costs[when] = (float(g["cost"].iloc[0]), stamp[trade_day[eom]])
    strategy = Rebalance({}, [], month_ends)
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(NAV, USD)],
        base_currency=USD,
        default_leverage=Decimal(1),
        fee_model=NoFees(),
        modules=[Costs(costs, strategy)],
    )
    bar_types, targets = [], {}
    for permno in px.columns:
        instrument = InstrumentId.from_str(f"P{permno}.REPLAY")
        engine.add_instrument(equity(instrument))
        bar_type = BarType.from_str(f"{instrument}-1-DAY-LAST-EXTERNAL")
        bar_types.append(bar_type)
        series = px[permno].dropna()
        bars = []
        for day, value in series.items():
            p = Price(float(value), PRECISION)
            bars.append(Bar(bar_type, p, p, p, p, VOLUME, stamp[day], stamp[day]))
        engine.add_data(bars)
    engine.add_instrument(equity(CLOCK))
    clock_type = BarType.from_str(f"{CLOCK}-1-DAY-LAST-EXTERNAL")
    one = Price(1, PRECISION)
    ticks = [stamp[d] + 1_000_000_000 for d in days]
    engine.add_data([Bar(clock_type, one, one, one, one, Quantity(1, 0), t, t) for t in ticks])
    for eom, g in held.groupby("eom"):
        weights = {
            InstrumentId.from_str(f"P{p}.REPLAY"): w for p, w in zip(g["permno"], g["weight"])
        }
        targets[stamp[trade_day[eom]]] = weights
    strategy.targets, strategy.bar_types = targets, [*bar_types, clock_type]
    engine.add_strategy(strategy)
    engine.run()

    navs = pd.Series(strategy.navs).sort_index()
    navs.index = pd.to_datetime(navs.index).to_period("M").to_timestamp()
    theirs = navs.pct_change().dropna()
    ours = book.set_index("holding_month")["net"].reindex(theirs.index)
    gap = (theirs - ours).dropna()
    cumulative = float((1 + theirs.loc[gap.index]).prod() - (1 + ours.loc[gap.index]).prod())
    OUT.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(
        dict(
            nautilus=theirs,
            ledger_net=ours,
            ledger_gross=book.set_index("holding_month")["gross"].reindex(theirs.index),
            ledger_cost=book.set_index("holding_month")["cost"].reindex(theirs.index),
        )
    )
    table.to_csv(OUT / f"{name}_monthly.csv")
    create_tearsheet(engine, str(OUT / f"tearsheet_{name}.html"), title=f"{name}: Nautilus replay")
    engine.dispose()
    return dict(
        months=len(gap),
        mean_abs_gap=float(gap.abs().mean()),
        cumulative_gap=cumulative,
        months_over_5bp={f"{m:%Y-%m}": float(g) for m, g in gap.items() if abs(g) > 0.0005},
        passed=bool(gap.abs().mean() <= 0.0001 and abs(cumulative) <= 0.001),
    )


# Replays the named runs (v1 and v2 at $10M by default), kept beside earlier replays.
def main(names: list[str]) -> None:
    path = OUT / "check.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report |= {name: replay(name) for name in names or ["v1@1e7", "v2@1e7"]}
    path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
