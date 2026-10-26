# The final run's guards on fakes: sealed refusal, windows, joins.

import pandas as pd
import pytest

from fiam.v4 import clock, final, gates, sources
from fiam.v4.forecast import dataset, grid

DAY = pd.Timestamp


# Sealed, every final stage refuses; the windows stay as they were.
def test_opened_refuses_while_sealed(monkeypatch):
    monkeypatch.setattr(sources, "UNSEAL_CACHE", False)
    with pytest.raises(SystemExit, match="sealed"):
        with final.opened():
            pass
    assert clock.LAST_LABEL_DAY == DAY("2020-12-31")
    assert sources.seal_at() == sources.SEAL


# Unsealed, the windows reach 2026-08 inside and are restored after.
def test_opened_moves_the_windows_and_restores(monkeypatch):
    monkeypatch.setattr(sources, "UNSEAL_CACHE", True)
    before = (clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST, grid.RETURN_YEARS)
    with final.opened():
        assert clock.LAST_LABEL_DAY == gates.LAST_DAY == final.END
        assert dataset.LAST == final.LAST and list(grid.RETURN_YEARS) == list(range(2021, 2027))
        assert sources.seal_at() == sources.OPENED
    assert (clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST, grid.RETURN_YEARS) == before
    # Nothing public after the finals' last day is ever read.
    assert sources.OPENED.tz_convert(clock.EASTERN).date() == DAY("2026-08-31").date()


# Rebuilt labels must leave every row public by 2020 as it was.
def test_labels_before_2021_unchanged():
    old = pd.DataFrame({"permno": [1, 2], "eom": [DAY("2019-01-31")] * 2, "horizon": 1,
                        "label": [0.1, -0.2], "available": [DAY("2019-03-01")] * 2})  # fmt: skip
    late = pd.DataFrame({"permno": [1], "eom": [DAY("2021-01-31")], "horizon": 1,
                         "label": [0.3], "available": [DAY("2021-03-01")]})  # fmt: skip
    new = pd.concat([late, old.iloc[::-1]], ignore_index=True)
    assert final.same_before(old, new)["unchanged_before_2021"]
    moved = new.copy()
    moved.loc[moved["permno"] == 2, "label"] = -0.25
    assert not final.same_before(old, moved)["unchanged_before_2021"]


# The blind forecasts to 2020-12 are kept; refits only after them.
def test_forecasts_join_keeps_the_blind_rows():
    pinned = pd.DataFrame({"permno": [1, 2, 1, 2], "z": [0.1, -0.1, 0.5, -0.5],
                           "eom": [DAY("2020-11-30")] * 2 + [DAY("2020-12-31")] * 2})  # fmt: skip
    refit = pd.DataFrame({"permno": [1, 2, 1, 2], "z": [0.5, -0.4, 0.2, -0.2],
                          "eom": [DAY("2020-12-31")] * 2 + [DAY("2021-01-31")] * 2})  # fmt: skip
    both, gap = final.joined(pinned, refit)
    assert len(both) == 6 and both["eom"].max() == DAY("2021-01-31")
    kept = both[both["eom"] == DAY("2020-12-31")].set_index("permno")["z"]
    assert list(kept) == [0.5, -0.5]
    assert gap == pytest.approx(0.1)
