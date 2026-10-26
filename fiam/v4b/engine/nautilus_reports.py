"""Native nautilus_trader reports with an explicit marked-equity return adapter.

Pinned 1.230's margin account balance excludes unrealized P&L. Its default
analyzer balance returns are therefore not the portfolio equity series.
Only the analyzer copy used for presentation is replaced; account and trade
state remain native and their unmodified reports are exported alongside it.
"""

import copy
import json
from types import SimpleNamespace

import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet


class EngineView:
    def __init__(self, engine, analyzer):
        self.engine = engine
        self.portfolio = SimpleNamespace(analyzer=analyzer)

    def __getattr__(self, name):
        return getattr(self.engine, name)


def save(engine, result, directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in [
        ("orders", result.native_orders),
        ("fills", result.native_fills),
        ("positions", result.native_positions),
        ("accounts", result.native_accounts),
    ]:
        if frame is not None and not frame.empty:
            frame.to_csv(directory / f"{name}.csv")
    result.ledger.to_parquet(directory / "daily_nav.parquet")
    result.positions.to_parquet(directory / "daily_holdings.parquet", index=False)
    result.intents.to_csv(directory / "execution_intents.csv", index=False)
    returns = result.ledger.ret.iloc[1:].copy()
    returns.index = pd.DatetimeIndex(returns.index).tz_localize("UTC")
    returns.to_frame("net_return").to_parquet(directory / "tearsheet_returns.parquet")
    # Native reports are optional for the large OOS book.  When they are
    # suppressed, the ledger/holdings are still built from native fills; only
    # the expensive tearsheet/report rendering is skipped.
    if result.native_accounts is not None and not result.native_accounts.empty:
        analyzer = copy.copy(engine.portfolio.analyzer)
        # Version-specific adapter, covered by an open-position equity regression.
        analyzer._portfolio_returns = returns
        analyzer._sync_returns_alias()
        view = EngineView(engine, analyzer)
        create_tearsheet(
            view,
            str(directory / "tearsheet.html"),
            title="v4b Nautilus — marked equity after costs",
        )
    (directory / "report_provenance.json").write_text(
        json.dumps(
            {
                "engine": "nautilus_trader",
                "native_reports": ["orders", "fills", "positions", "accounts"],
                "return_basis": (
                    "Native margin balance plus native open-position unrealized P&L at daily marks"
                ),
                "account_balance_is_not_equity": True,
                "tearsheet_adapter": (
                    "1.230 analyzer copy uses observed marked-equity returns; "
                    "native state unmodified"
                ),
            },
            indent=2,
        )
        + "\n"
    )
