# The two late signals on synthetic rows, and Holm over 8.

import pandas as pd
import pytest

from fiam.vfinal import data, gates
from fiam.vfinal.signals import base, earnings_premium, options_flow

DAY = pd.Timestamp


# The options composite: a higher IV spread and a lower skew rank up.
def test_options_flow(monkeypatch):
    days = pd.bdate_range("2019-01-21", "2019-01-31")
    rows = pd.DataFrame([(p, d, 0.3 + 0.01 * p, 0.3, 0.05 * (4 - p), d + pd.offsets.BDay(1))
                         for p in (1, 2, 3) for d in days],
                        columns=["permno", "date", "iv_CATM", "iv_PATM", "Skew_OTM",
                                 "first_close"])  # fmt: skip
    T = DAY("2019-01-31")
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [T], "T": [T]}))
    monkeypatch.setattr(data, "table", lambda *a, **k: rows)
    got = options_flow.build([T]).set_index("permno")["value"]
    assert got[3] > got[2] > got[1]


# The earnings premium: an announcement projected by the next T counts.
def test_earnings_premium(monkeypatch):
    T = DAY("2019-01-31")
    cal = pd.DataFrame({"permno": [1, 2, 3, 3], "first_close": [DAY("2019-01-10")] * 3 + [T],
                        "projected": [DAY("2019-02-15"), DAY("2019-04-20"), DAY("2019-05-01"),
                                      DAY("2019-02-10")]})  # fmt: skip
    monkeypatch.setattr(base, "formations", lambda e: pd.DataFrame({"eom": [T], "T": [T]}))
    monkeypatch.setattr(data, "table", lambda *a, **k: cal)
    monkeypatch.setattr(data, "eom_session", lambda e: pd.Series([DAY("2019-02-28")]))
    got = earnings_premium.build([T]).set_index("permno")["value"]
    assert got.to_dict() == {1: 1.0, 2: 0.0, 3: 1.0}


# Holm over 8: the bars follow the family's size, not the six's.
def test_holm_over_eight():
    p = {f"s{i}": 0.5 for i in range(6)} | {"a": 0.006, "b": 0.0071}
    bars = [gates.ALPHA / (8 - i) for i in range(8)]
    got = gates.holm(p, bars)
    assert got["a"]["passes"] and got["b"]["passes"] and got["a"]["bar"] == pytest.approx(0.05 / 8)
    assert not gates.holm({**p, "a": 0.007}, bars)["a"]["passes"]
