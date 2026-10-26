"""Known-truth tests for specific-risk model selection without future labels."""

import numpy as np
import pandas as pd

from fiam.v4b.risk import specific


def losses():
    dates = pd.date_range("2015-01-31", periods=15, freq="ME")
    return pd.DataFrame({"formation": dates, "label_end": dates + pd.Timedelta(days=20),
                         "ewma84": np.ones(15), "ewma168": np.full(15, 0.5)})


def test_specific_selector_ignores_unfinished_labels_and_future_mutations():
    data = losses()
    asof = pd.Timestamp("2016-01-20")
    original = specific.choose_ewma_asof(data, asof)
    changed = data.copy()
    changed.loc[changed.label_end > asof, ["ewma84", "ewma168"]] = [0.0, 1000.0]
    assert original == specific.choose_ewma_asof(changed, asof)
    assert original["winner"] == "ewma168"
    assert original["formations"] == 12
    assert original["latest_label_end"] <= asof


def test_specific_selector_defaults_to_84_if_too_few_or_tied():
    data = losses()
    early = specific.choose_ewma_asof(data, pd.Timestamp("2015-12-19"))
    assert early["winner"] == "ewma84"
    assert early["formations"] == 10
    data["ewma168"] = data["ewma84"]
    assert specific.choose_ewma_asof(data, pd.Timestamp("2016-04-30"))["winner"] == "ewma84"
