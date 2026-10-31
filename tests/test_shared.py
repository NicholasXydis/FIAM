# The shared modules: the stock screen, file helpers and run.py.

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiam import paths
from fiam import stocks as S

ROOT = Path(__file__).resolve().parents[1]


# Tiny panel and exits: one name dead by decision, one exits next month.
def test_settle_screens_dead_names_and_books_payouts(monkeypatch):
    eom = pd.Timestamp("2024-03-31")
    panel = pd.DataFrame(
        dict(permno=[1, 2, 3], eom=[eom] * 3, ret_exc_lead1m=[0.01, np.nan, np.nan])
    )
    exits = pd.DataFrame(
        dict(
            exit_date=pd.to_datetime(["2024-03-15", "2024-04-10"]),
            final_month=pd.to_datetime(["2024-03-01", "2024-04-01"]),
            final_return=[0.02, 0.05],
            source=["CRSP delisting MER CASH"] * 2,
        ),
        index=pd.Index([2, 3], name="permno"),
    )
    cash = pd.DataFrame(dict(month=[pd.Timestamp("2024-04-01")], rf=[0.004]))
    monkeypatch.setattr(S, "exits", lambda: exits)
    monkeypatch.setattr(S, "benchmarks", lambda: cash)
    settled = S.settle(panel).set_index("permno")["ret_exc_lead1m"]
    assert list(settled.index) == [1, 3]
    assert settled[1] == pytest.approx(0.01)
    assert settled[3] == pytest.approx(0.05 - 0.004)


# With no exits table the universe is left as it is.
def test_settle_changes_nothing_without_wrds(monkeypatch):
    panel = pd.DataFrame(
        dict(permno=[1], eom=[pd.Timestamp("2024-03-31")], ret_exc_lead1m=[np.nan])
    )
    monkeypatch.setattr(S, "exits", lambda: None)
    pd.testing.assert_frame_equal(S.settle(panel), panel)


# Importing a module must not run or write, so a bundler can take code.
def test_every_module_imports_without_side_effects(tmp_path):
    files = sorted((ROOT / "fiam").rglob("*.py"))
    names = [".".join(p.relative_to(ROOT).with_suffix("").parts) for p in files]
    script = f"import sys; sys.path[:0] = [{str(ROOT)!r}]\nfor n in {names!r}: __import__(n)"
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True, timeout=300)
    assert not any(tmp_path.iterdir()), "an import wrote a file"


# A missing benchmark file stops the run instead of downloading.
def test_benchmarks_refuse_to_download_on_their_own(tmp_path, monkeypatch):
    benchmarks = importlib.import_module("fiam.benchmarks")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="--refresh"):
        benchmarks.pinned("SP500.csv")


# Rounding for JSON keeps True and False as they are.
def test_saved_numbers_keep_booleans():
    assert paths.round_floats(dict(passed=True, share=0.1234567)) == dict(
        passed=True, share=0.123457
    )


# --import copies the organizer's files by name and leaves a CV alone.
def test_import_takes_only_organizer_files(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("run", ROOT / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "factor_char_list.csv").write_text("variable\nbe_me\n")
    (downloads / "Someone_CV.pdf").write_bytes(b"%PDF")
    (downloads / "notes.csv").write_text("a,b\n1,2\n")
    monkeypatch.chdir(tmp_path)
    run.import_from(downloads)
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["factor_char_list.csv"]
