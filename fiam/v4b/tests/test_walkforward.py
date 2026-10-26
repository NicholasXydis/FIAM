# Walk-forward E-LASSO (D15): a refit at r must not move when anything dated
# after r changes, and the forecast for the next month must depend only on the
# weights frozen at r and that month's characteristics.

import numpy as np
import pandas as pd

from fiam.v4b.elasso import walkforward
from fiam.v4b.gpu import elasso


def _panel(months: int = 18, names: int = 60, chars: int = 4, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-31", periods=months, freq="ME")
    rows = []
    for d in dates:
        z = rng.standard_normal((names, chars))
        ret = 0.01 * z[:, 0] + 0.05 * rng.standard_normal(names)
        rows.append(pd.DataFrame({"date": d.date(), "permno": np.arange(names), "exchcd": 1.0,
                                  "me": rng.uniform(1, 10, names), "ret": ret,
                                  **{f"c{j}": z[:, j] for j in range(chars)}}))
    return pd.concat(rows, ignore_index=True)


def _refit(data: pd.DataFrame, r: pd.Timestamp) -> pd.DataFrame:
    train = data[pd.to_datetime(data["date"]) <= r]
    return walkforward.frozen_weights(elasso.run(train), r)


def test_refit_ignores_everything_after_the_refit_date():
    data = _panel()
    r = pd.Timestamp("2016-01-31")
    later = pd.to_datetime(data["date"]) > r
    noisy = data.copy()
    rng = np.random.default_rng(1)
    for c in ("ret", "c0", "c1", "c2", "c3"):
        noisy.loc[later, c] = rng.standard_normal(int(later.sum()))
    a, b = _refit(data, r), _refit(noisy, r)
    num = [c for c in a.columns if c not in ("block", "refit")]
    assert np.allclose(a[num].to_numpy(float), b[num].to_numpy(float), equal_nan=True)


def test_forecast_uses_only_frozen_weights_and_that_months_characteristics():
    data = _panel()
    r = pd.Timestamp("2016-01-31")
    fw = _refit(data, r)
    nxt = data[pd.to_datetime(data["date"]) == pd.Timestamp("2016-02-29")].copy()
    f1 = walkforward.apply(fw, nxt)
    nxt["ret"] = 99.0  # the month's own realised return must not enter its forecast
    f2 = walkforward.apply(fw, nxt)
    assert np.allclose(f1[["MaInf", "Ma1"]], f2[["MaInf", "Ma1"]])
    assert f1["MaInf"].notna().all()


def test_monthly_refits_cover_validation_and_oos_without_gaps():
    rs = walkforward.refits("month")
    assert rs[0] == pd.Timestamp("2016-12-31") and rs[-1] == pd.Timestamp("2026-07-31")
    assert len(rs) == len(pd.date_range(rs[0], rs[-1], freq="ME"))
