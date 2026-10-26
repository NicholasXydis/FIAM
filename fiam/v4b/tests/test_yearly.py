import pandas as pd
import pytest

from fiam.v4b.engine.yearly import performance


def test_yearly_return_and_drawdown_include_opening_capital():
    dates = pd.to_datetime(["2019-12-31", "2020-01-02", "2020-01-03"])
    ledger = pd.DataFrame(
        {
            "nav": [100.0, 90.0, 99.0],
            "ret": [0.0, -0.1, 0.1],
            **{c: [0.0, 0.0, 0.0] for c in ("spread", "impact", "fees", "borrow")},
        },
        index=dates,
    )
    table = performance(ledger, pd.Series(0.0, index=dates), premium=0.0)
    assert table.year.tolist() == [2020]
    row = table.iloc[0]
    assert row.net_return == pytest.approx(-0.01)
    assert row.max_drawdown == pytest.approx(-0.1)
    assert row.start_nav == 100.0
    assert row.end_nav == 99.0
    assert row.sessions == 2
