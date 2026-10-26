"""The finals short floor is a per-name capitalisation rule."""

import numpy as np
import pandas as pd

from fiam.v4b.engine import checker


def test_formation_short_floor_checks_each_short_and_ignores_long_market_cap():
    month = pd.DataFrame({"me": [100, 500, 700], "me_company": [100, 600, 800]},
                         index=pd.Index([1, 2, 3], name="permno"))
    assert checker.short_floor_formation(pd.Series({1: 0.7, 2: -0.2, 3: -0.2}), month, 500)
    assert not checker.short_floor_formation(pd.Series({1: -0.01, 2: -0.9}), month, 500)


def test_formation_short_floor_fails_closed_when_cap_or_name_is_missing():
    month = pd.DataFrame({"me": [700, 700], "me_company": [np.nan, 800]}, index=[1, 2])
    assert not checker.short_floor_formation(pd.Series({1: -0.2, 2: -0.7}), month, 500)
    assert not checker.short_floor_formation(pd.Series({3: -0.9}), month, 500)


def test_hbeta_gate_distinguishes_capitalization_from_short_notional():
    from types import SimpleNamespace
    from fiam.v4b.research.hbeta_gates import hard_checks

    month = pd.DataFrame({"sector": ["A", "A"], "me": [1000., 490.],
                          "me_company": [1000., 490.]}, index=[1, 2])
    f = SimpleNamespace(snap={"month": month})
    hard = SimpleNamespace(names_min=1, names_max=500, name_cap=1.0,
                           gross_max=2.0, net_band=0.5, nav0=1e9,
                           short_floor_musd=500.0)
    checks = hard_checks(pd.Series({1: 0.9, 2: -0.9}), f, SimpleNamespace(hard=hard))
    assert not checks["short_floor"]
    assert checks["short_gross_research"]
