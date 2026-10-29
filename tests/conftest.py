# Shared test setup: every test starts in blind mode.

import pytest

from fiam.vfinal import sources


# Blind mode on unless a test turns it off, whatever the repo holds.
@pytest.fixture(autouse=True)
def sealed(monkeypatch):
    monkeypatch.setattr(sources, "UNSEAL_CACHE", False)
