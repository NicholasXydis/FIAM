# The compare verb on a tiny synthetic locked run and its rerun.

import json

import pandas as pd

from fiam.vfinal import compare

A, B = "a" * 12, "b" * 12


# Writes one run's files under root, suffixed by its commit name.
def write_run(root, at: str, nav_end: float = 1.2e9, utc: str = "2026-10-27T00:00:00") -> list:
    folder = root / "out" / "h"
    folder.mkdir(parents=True, exist_ok=True)
    days = pd.DatetimeIndex(["2021-01-04", "2021-01-05"])
    pd.DataFrame({"nav": [1e9, nav_end], "ret": [0.0, nav_end / 1e9 - 1]}, index=days).to_parquet(
        folder / f"daily_7_{at}.parquet"
    )
    pos = pd.DataFrame({"date": days, "permno": [1, 1], "value": [1e7, 1.1e7]})
    pos.to_parquet(folder / f"positions_7_{at}.parquet")
    table = pd.DataFrame(
        {"row": [23], "name": ["IR net of all costs"], "strategy": ["0.50 (0.40)"]}
    )
    table.to_csv(folder / f"table_9_1_{at}.csv", index=False)
    report = {"stamp": {"commit": at + "c" * 28, "run_utc": utc}, "rows": 23, "file": f"x_{at}"}
    (folder / f"report_{at}.json").write_text(json.dumps(report))
    return sorted(p for p in folder.iterdir() if at in p.name)


# Writes the lock's record of run A.
def record(root, files: list) -> object:
    path = root / "outputs.json"
    files = {p.relative_to(root).as_posix(): "x" for p in files}
    path.write_text(json.dumps({"run_at": A, "headline": "out/h", "files": files}))
    return path


# Same content with other commits and times reads as identical.
def test_identical_rerun(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(compare, "resolve", lambda commit, root=None: commit)
    path = record(tmp_path, write_run(tmp_path, A))
    write_run(tmp_path, B, utc="2026-10-30T09:00:00")
    assert compare.compare(B, tmp_path, path) == 0
    assert capsys.readouterr().out.strip().endswith("identical")


# A changed NAV is found, with the gap summary of positions, NAV and IR.
def test_a_different_rerun(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(compare, "resolve", lambda commit, root=None: commit)
    path = record(tmp_path, write_run(tmp_path, A))
    write_run(tmp_path, B, nav_end=1.25e9)
    assert compare.compare(B, tmp_path, path) == 1
    out = capsys.readouterr().out
    assert "differs out/h/daily_7_<at>.parquet" in out and "nav: 1 rows differ" in out
    assert "same    out/h/report_<at>.json" in out
    assert "NAV: largest daily gap $50,000,000.00" in out
    assert "positions: 0 rows in one run only" in out and "IR net: 0.50 (0.40) locked" in out


# A missing rerun file and a changed JSON value are both reported.
def test_missing_and_json_gaps(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(compare, "resolve", lambda commit, root=None: commit)
    path = record(tmp_path, write_run(tmp_path, A))
    write_run(tmp_path, B)
    (tmp_path / "out" / "h" / f"positions_7_{B}.parquet").unlink()
    report = tmp_path / "out" / "h" / f"report_{B}.json"
    report.write_text(report.read_text().replace('"rows": 23', '"rows": 22'))
    assert compare.compare(B, tmp_path, path) == 1
    out = capsys.readouterr().out
    assert "missing in the rerun" in out and "/rows: 23 vs 22" in out
