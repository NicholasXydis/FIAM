# The data gate on scratch git repos: the record, the lock, blind books.

import json
import shutil
import subprocess

import pandas as pd
import pytest

from fiam.vfinal import headline, lock, sources
from fiam.vfinal.construct import book, exam

AT = "c" * 12
PINS = ("out/vfinal/forecast/forecasts_x.parquet", "out/vfinal/final/labels_sealed.parquet")
RECORD = {"window": "2021-01-01 to 2026-08-31", "first_freeze": "a" * 40, "first_opened": "b" * 40}


# One git command in a scratch repo.
def git(root, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)  # fmt: skip


# Writes a file under the scratch root, text or bytes.
def put(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body if isinstance(body, bytes) else body.encode())
    return path


# Points every gate path at a root, the pins and the picks faked.
def point(monkeypatch, root):
    frozen = root / "frozen" / "vfinal"
    for name, value in {"ROOT": root, "FROZEN": frozen, "OPENED": frozen / "opened.json",
                        "SHA": frozen / "vfinal.sha256",
                        "OUTPUTS": frozen / "outputs.json"}.items():  # fmt: skip
        monkeypatch.setattr(lock, name, value)
    monkeypatch.setattr(lock, "pins", lambda: list(PINS))
    run = root / "out" / "vfinal" / "final"
    monkeypatch.setattr(lock, "final_picks", lambda: {AT: run / "revised_quarterly_loose"})
    monkeypatch.setattr(headline, "BASE", run)
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)


# A pushed scratch repo with code, settings, pins and one headline run.
@pytest.fixture
def repo(tmp_path, monkeypatch):
    root, remote = tmp_path / "work", tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(tmp_path, "init", "-q", str(root))
    put(root, ".gitignore", "out/\n")
    put(root, "fiam/vfinal/a.py", "A = 1\n")
    put(root, "fiam/vfinal/sub/b.py", "B = 2\n")
    put(root, "fiam/agents/harness.py", "MODELS = {}\n")
    put(root, "versions/vfinal/settings.json", json.dumps({"alpha_scale": 0.5}))
    put(root, "versions/vfinal/config.json", json.dumps({"headline": {"arm": "A0"}}))
    for name in PINS:
        put(root, name, b"pinned bytes")
    put(root, f"out/vfinal/final/pick_{AT}.json", json.dumps({"final": True}))
    put(root, f"out/vfinal/final/revised_quarterly_loose/daily_7_{AT}.parquet", b"daily")
    put(root, "out/vfinal/final/revised_quarterly_loose/daily_7_ffffffffffff.parquet", b"x")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "code")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(root, "fetch", "-q", "origin")
    point(monkeypatch, root)
    return root


# Commits and pushes everything in the scratch repo.
def push(root):
    git(root, "add", "-A")
    git(root, "commit", "-qm", "more")
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(root, "fetch", "-q", "origin")


# The gate's answer afresh, the process cache cleared first.
def gate(monkeypatch) -> bool:
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    return sources.unsealed()


# A clean pushed tree without the record stays sealed.
def test_sealed_without_the_record(repo, monkeypatch):
    assert not lock.OPENED.exists()
    assert gate(monkeypatch) is False
    assert sources.seal_at() == sources.SEAL


# The record opens only when HEAD tracks it in a clean pushed tree.
def test_record_opens_only_when_tracked_clean_and_pushed(repo, monkeypatch):
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD))
    # Untracked: the tree is dirty, so sealed.
    assert gate(monkeypatch) is False
    # Ignored, so the tree is clean, but HEAD does not hold it: sealed.
    put(repo, ".git/info/exclude", "frozen/\n")
    assert gate(monkeypatch) is False
    put(repo, ".git/info/exclude", "")
    # Committed but not pushed: sealed.
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "record")
    assert gate(monkeypatch) is False
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(repo, "fetch", "-q", "origin")
    assert gate(monkeypatch) is True
    assert sources.seal_at() == sources.OPENED
    # A dirty tree seals it again.
    put(repo, "fiam/vfinal/a.py", "A = 2\n")
    assert gate(monkeypatch) is False
    put(repo, "fiam/vfinal/a.py", "A = 1\n")
    assert gate(monkeypatch) is True
    # A record missing a field never opens it.
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD | {"first_opened": ""}))
    push(repo)
    assert gate(monkeypatch) is False


# The lock opens the gate on a copy with no git at all.
def test_lock_opens_without_git(repo, monkeypatch, tmp_path):
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD))
    lines = lock.lock()
    names = [line.split("  ", 1)[1] for line in lines]
    assert names == sorted(names)
    assert set(names) == {"fiam/vfinal/a.py", "fiam/vfinal/sub/b.py", "fiam/agents/harness.py",
                          "versions/vfinal/settings.json", "versions/vfinal/config.json",
                          "frozen/vfinal/opened.json", "frozen/vfinal/outputs.json",
                          *PINS}  # fmt: skip
    made = json.loads(lock.OUTPUTS.read_text())
    assert made["run_at"] == AT
    assert list(made["files"]) == [
        f"out/vfinal/final/pick_{AT}.json",
        f"out/vfinal/final/revised_quarterly_loose/daily_7_{AT}.parquet",
    ]
    assert lock.verify() == []
    # An offline copy: no .git folder, the tree dirty by git's standard.
    copy = tmp_path / "offline"
    shutil.copytree(repo, copy, ignore=shutil.ignore_patterns(".git"))
    point(monkeypatch, copy)
    assert not (copy / ".git").exists()
    assert gate(monkeypatch) is True
    assert lock.compare() == ([], [])


# One changed byte in any hashed file, or a new code file, reseals.
def test_one_changed_byte_reseals(repo, monkeypatch):
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD))
    lock.lock()
    assert gate(monkeypatch) is True
    for name in ("fiam/vfinal/sub/b.py", PINS[0], "versions/vfinal/config.json",
                 "frozen/vfinal/outputs.json", "frozen/vfinal/opened.json"):  # fmt: skip
        path = repo / name
        body = path.read_bytes()
        path.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))
        assert gate(monkeypatch) is False, name
        assert lock.verify() == [f"{name}: changed"]
        path.write_bytes(body)
        assert gate(monkeypatch) is True
    put(repo, "fiam/vfinal/c.py", "C = 3\n")
    assert lock.verify() == ["fiam/vfinal/c.py: not in the lock"]
    assert gate(monkeypatch) is False
    (repo / "fiam" / "vfinal" / "c.py").unlink()
    (repo / PINS[1]).unlink()
    assert lock.verify() == [f"{PINS[1]}: missing"]
    assert gate(monkeypatch) is False


# The lock refuses without the record, a pin or a single final pick.
def test_lock_refuses_when_incomplete(repo, monkeypatch):
    with pytest.raises(SystemExit, match="opened.json"):
        lock.lock()
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD))
    (repo / PINS[0]).unlink()
    with pytest.raises(SystemExit, match="pinned files missing"):
        lock.lock()
    put(repo, PINS[0], b"pinned bytes")
    monkeypatch.setattr(lock, "final_picks", lambda: {AT: repo, "d" * 12: repo})
    with pytest.raises(SystemExit, match="2 final picks"):
        lock.lock()
    with pytest.raises(SystemExit, match="no final pick"):
        lock.lock("e" * 12)
    assert not lock.SHA.exists()


# A changed recorded output shows in compare, never in the gate.
def test_compare_reports_changed_outputs(repo, monkeypatch):
    put(repo, "frozen/vfinal/opened.json", json.dumps(RECORD))
    lock.lock()
    put(repo, f"out/vfinal/final/pick_{AT}.json", "{}")
    (repo / f"out/vfinal/final/revised_quarterly_loose/daily_7_{AT}.parquet").unlink()
    changed, absent = lock.compare()
    assert changed == [f"out/vfinal/final/pick_{AT}.json: changed"]
    assert absent == [f"out/vfinal/final/revised_quarterly_loose/daily_7_{AT}.parquet"]
    assert gate(monkeypatch) is True


# The 2017-2020 books run blind under sealed(), even with the gate open.
def test_early_books_stay_blind(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "UNSEAL_CACHE", True)
    seen = {}

    # The exam's book, recording the seal it ran under.
    def design(settings_at, z, neutral=()):
        seen["seal"], seen["open"] = sources.seal_at(), sources.unsealed()
        return {"plans": [], "daily": pd.DataFrame({"ret": [0.0]}), "ir": 0.1}

    monkeypatch.setattr(headline, "design", lambda: (7, {}))
    monkeypatch.setattr(headline, "install_settings", lambda loose: None)
    monkeypatch.setattr(headline, "BASE", tmp_path)
    monkeypatch.setattr(exam, "design", design)
    monkeypatch.setattr(exam, "settings_for", lambda k, s: None)
    monkeypatch.setattr(book, "FORECASTS", book.FORECASTS)
    got = headline.early("f" * 40, "quarterly", "loose")
    assert seen == {"seal": sources.SEAL, "open": False}
    assert got["ir"] == 0.1 and sources.unsealed() is True
    # The alpha scale reads pre-2021 rows only, blind as well.
    monkeypatch.setattr(book, "alpha_scale", lambda f: (sources.unsealed(), f["eom"].max()))
    f = pd.DataFrame({"eom": pd.to_datetime(["2020-12-31", "2021-01-31"])})
    assert headline.scale_of(f) == (False, pd.Timestamp("2020-12-31"))
    assert sources.seal_at() == sources.OPENED


# The real repo's gate: the record is committed and well formed.
def test_real_record_is_well_formed():
    body = json.loads((lock.ROOT / "frozen" / "vfinal" / "opened.json").read_text())
    assert all(body[k] for k in lock.FIELDS)
    assert body["first_freeze"].startswith("c5ef879")
    assert body["first_opened"].startswith("512e4bd")
