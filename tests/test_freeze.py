# The step 10 freeze and unseal, on a scratch git repo with fake paths.

import hashlib
import json
import subprocess

import pytest

from fiam.v4 import freeze, gates, sources

HEAD = "a" * 40
FORECAST = "out/v4/forecast/forecasts_0123456789ab.parquet"
DESIGNS = f"out/v4/construct/exam_designs_{HEAD[:12]}.json"


# One git command in the scratch repo.
def git(root, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True,
                   capture_output=True)  # fmt: skip


# Writes a file under the scratch root, text or bytes.
def put(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body if isinstance(body, bytes) else body.encode())
    return path


# Commits the frozen folder, as the leader does before the unseal.
def commit_frozen(root):
    git(root, "add", "frozen")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "freeze")


# A scratch repo with code, pins and an exam; every freeze path moved.
@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    put(tmp_path, "fiam/v4/a.py", "A = 1\n")
    put(tmp_path, "fiam/v4/b.py", "B = 2\n")
    put(tmp_path, "run.py", "print('run')\n")
    put(tmp_path, "versions/v4/protocol.md", "protocol\n")
    put(tmp_path, "versions/v4/settings.json", json.dumps({"alpha_scale": 0.5, "ridge": 30}))
    put(tmp_path, FORECAST, b"forecast bytes")
    put(tmp_path, DESIGNS, json.dumps({"winner": 2, "reading": "freeze and run"}))
    git(tmp_path, "add", "fiam", "run.py", "versions")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "code")
    frozen = tmp_path / "frozen" / "v4"
    names = {"ROOT": tmp_path, "FROZEN": frozen, "CONFIG": frozen / "config.json",
             "DECISIONS": frozen / "decisions.json", "SHA": frozen / "v4.sha256",
             "LOG": frozen / "unseal.log", "OUT": tmp_path / "out" / "v4",
             "PROTOCOL": tmp_path / "versions" / "v4" / "protocol.md",
             "SETTINGS": tmp_path / "versions" / "v4" / "settings.json",
             "FORECASTS": tmp_path / FORECAST}  # fmt: skip
    for name, value in names.items():
        monkeypatch.setattr(freeze, name, value)
    monkeypatch.setattr(freeze.desk, "EXAM_AT", None)
    monkeypatch.setattr(gates, "commit", lambda: HEAD)
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    # The fake HEAD is no real commit; the git check is tested on its own.
    monkeypatch.setattr(freeze, "committed", lambda commit, sha: True)
    return tmp_path


# The freeze writes config, decisions and the sorted hash list.
def test_freeze_writes_the_files(repo):
    lines = freeze.freeze()
    for path in (freeze.CONFIG, freeze.DECISIONS, freeze.SHA):
        assert path.is_file()
    paths = [line.split("  ")[1] for line in lines]
    assert paths == sorted(paths)
    assert set(paths) == {"frozen/v4/config.json", "frozen/v4/decisions.json", FORECAST,
                          "versions/v4/protocol.md", "versions/v4/settings.json",
                          "fiam/v4/a.py", "fiam/v4/b.py"}  # fmt: skip
    for line in lines:
        want, name = line.split("  ")
        assert want == hashlib.sha256((repo / name).read_bytes()).hexdigest()
    assert freeze.SHA.read_text() == "\n".join(lines) + "\n"
    config = json.loads(freeze.CONFIG.read_text())
    assert config["commit"] == HEAD
    assert config["settings"] == {"alpha_scale": 0.5, "ridge": 30}
    sha = hashlib.sha256(b"forecast bytes").hexdigest()
    assert config["forecasts"] == {"file": "forecasts_0123456789ab.parquet", "sha256": sha}
    assert config["exam_design"]["winner"] == 2
    assert config["headline"] == {"arm": "A0", "reason": "desk not finished"}
    assert freeze.verify() == []


# The desk's decision sets the headline arm when it exists.
def test_headline_from_the_desk(repo):
    put(repo, "out/v4/desk/decide_bbbbbbbbbbbb.json", json.dumps({"headline": "A1"}))
    freeze.freeze()
    arm = json.loads(freeze.CONFIG.read_text())["headline"]
    assert arm["arm"] == "A1" and arm["source"] == "out/v4/desk/decide_bbbbbbbbbbbb.json"


# The exam's commit, when pinned, picks the designs file.
def test_pinned_exam_commit(repo, monkeypatch):
    put(repo, "out/v4/construct/exam_designs_cccccccccccc.json", json.dumps({"winner": 5}))
    monkeypatch.setattr(freeze.desk, "EXAM_AT", "c" * 12)
    freeze.freeze()
    assert json.loads(freeze.CONFIG.read_text())["exam_design"]["winner"] == 5


# A dirty or unpushed tree, a missing exam or a logged unseal refuses.
def test_freeze_refuses(repo, monkeypatch):
    # The same refusal gates.commit gives for a dirty tree.
    def dirty():
        raise RuntimeError("the tree is not clean")

    monkeypatch.setattr(gates, "commit", dirty)
    with pytest.raises(SystemExit, match="not clean"):
        freeze.freeze()
    monkeypatch.setattr(gates, "commit", lambda: HEAD)
    (repo / DESIGNS).unlink()
    with pytest.raises(SystemExit, match="exam designs"):
        freeze.freeze()
    assert not freeze.FROZEN.exists()
    put(repo, DESIGNS, json.dumps({"winner": None}))
    with pytest.raises(SystemExit, match="no winning design"):
        freeze.freeze()
    put(repo, "frozen/v4/unseal.log", "x\n")
    with pytest.raises(SystemExit, match="nothing refreezes"):
        freeze.freeze()


# Decisions mark a missing source "not built", never a made-up value.
def test_decisions_mark_missing_sources(repo):
    got = freeze.decisions(HEAD)["items"]
    gone = got["every gate result and the Holm table"]
    assert gone == {"status": "not built", "source": f"out/v4/gates/gates_{gates.SIX}.json"}
    assert got["the headline AI arm and its inputs"]["status"] == "not built"
    assert got["B23's L or current vintage"]["status"] == "not built"
    # A file with a key missing is not built, naming the key.
    put(repo, "out/v4/construct/exam_tests_" + HEAD[:12] + ".json", json.dumps({"cadence": 1}))
    got = freeze.decisions(HEAD)["items"]
    assert got["cadence"]["value"] == {"cadence": 1}
    assert got["each overlay on or off (lever E5)"]["source"].endswith("key overlays")
    # The time-cutoff model's name comes from the desk's pinned build.
    assert got["the time-cutoff model's name"]["value"]["name"] in freeze.desk.harness.MODELS


# A recorded item carries its source, its hash and its nested value.
def test_decisions_record_found_sources(repo):
    inner = {"gates": {"s": 9}, "holm": {"s": 2}, "kiefer_vogelsang": {}, "ancillaries": {}}
    put(repo, f"out/v4/gates/gates_{gates.SIX}.json",
        json.dumps({"stamp": {"commit": "x"}, "gates": inner}))  # fmt: skip
    got = freeze.decisions(HEAD)["items"]["every gate result and the Holm table"]
    assert got["status"] == "recorded" and got["source"].endswith(f"gates_{gates.SIX}.json")
    assert got["value"]["gates"] == {"s": 9} and got["stamp"] == {"commit": "x"}
    assert got["source_sha256"]


# A stage run at another commit is used only if it is the only one.
def test_latest_never_guesses(repo):
    folder = repo / "out" / "v4" / "gates"
    put(repo, "out/v4/gates/late_dddddddddddd.json", "{}")
    assert freeze.latest(folder, "late", HEAD).name == "late_dddddddddddd.json"
    put(repo, "out/v4/gates/late_eeeeeeeeeeee.json", "{}")
    with pytest.raises(SystemExit, match="pin one"):
        freeze.latest(folder, "late", HEAD)
    put(repo, f"out/v4/gates/late_{HEAD[:12]}.json", "{}")
    assert freeze.latest(folder, "late", HEAD).name == f"late_{HEAD[:12]}.json"


# One changed byte, a missing file or a new code file is reported.
def test_verify_catches_changes(repo):
    freeze.freeze()
    assert freeze.verify() == []
    code = repo / "fiam" / "v4" / "a.py"
    code.write_bytes(b"A = 2\n")
    assert freeze.verify() == ["fiam/v4/a.py: changed"]
    code.write_bytes(b"A = 1\n")
    (repo / FORECAST).unlink()
    assert freeze.verify() == [f"{FORECAST}: missing"]
    put(repo, FORECAST, b"forecast bytes")
    put(repo, "fiam/v4/c.py", "C = 3\n")
    git(repo, "add", "fiam")
    assert freeze.verify() == ["fiam/v4/c.py: not in the freeze"]


# A sha list that omits a pin or is missing is never sound.
def test_verify_needs_the_pins(repo):
    assert freeze.verify() == ["frozen/v4/v4.sha256: missing"]
    freeze.freeze()
    lines = freeze.SHA.read_text().splitlines()
    freeze.SHA.write_text("\n".join(x for x in lines if "protocol" not in x) + "\n")
    assert freeze.verify() == ["versions/v4/protocol.md: not in the freeze"]


# The unseal refuses a mismatch, an untracked list and a second try.
def test_unseal_refusals(repo):
    freeze.freeze()
    with pytest.raises(SystemExit, match="not tracked"):
        freeze.unseal()
    commit_frozen(repo)
    (repo / "fiam/v4/a.py").write_bytes(b"x = 2\n")
    with pytest.raises(SystemExit, match="a.py: changed"):
        freeze.unseal()
    assert not freeze.LOG.exists()
    (repo / "fiam/v4/a.py").write_bytes(b"A = 1\n")
    line = freeze.unseal()
    when, head, sha = line.split()
    assert head == HEAD and sha == hashlib.sha256(freeze.SHA.read_bytes()).hexdigest()
    assert when.endswith("Z") and when[4] == "-"
    assert freeze.LOG.read_text() == line + "\n"
    with pytest.raises(SystemExit, match="one unseal only"):
        freeze.unseal()
    assert freeze.LOG.read_text() == line + "\n"


# A dirty or unpushed tree stops the unseal, as the freeze.
def test_unseal_needs_a_pushed_tree(repo, monkeypatch):
    freeze.freeze()
    commit_frozen(repo)

    # The refusal gates.commit gives for a branch no remote holds.
    def unpushed():
        raise RuntimeError("no remote branch holds HEAD")

    monkeypatch.setattr(gates, "commit", unpushed)
    with pytest.raises(SystemExit, match="no remote branch"):
        freeze.unseal()
    assert not freeze.LOG.exists()


# Blind mode lifts only for a one-line log matching the sound list.
def test_unsealed_follows_the_log(repo, monkeypatch):
    assert sources.unsealed() is False
    freeze.freeze()
    commit_frozen(repo)
    # An unseal in this process clears the cached answer.
    sources.UNSEAL_CACHE = False
    freeze.unseal()
    assert sources.UNSEAL_CACHE is None
    assert sources.unsealed() is True
    # The answer is kept for the process, so a change shows after a clear.
    (repo / "fiam" / "v4" / "a.py").write_bytes(b"A = 2\n")
    assert sources.unsealed() is True
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    assert sources.unsealed() is False
    (repo / "fiam" / "v4" / "a.py").write_bytes(b"A = 1\n")
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    assert sources.unsealed() is True
    # A second line, or a log for another list, never opens it.
    freeze.LOG.write_text(freeze.LOG.read_text() * 2)
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    assert sources.unsealed() is False
    freeze.LOG.write_text("2026-10-27T00:00:00Z " + HEAD + " " + "0" * 64 + "\n")
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    assert sources.unsealed() is False


# On the real repo's paths blind mode is on: no unseal log exists.
def test_real_repo_is_sealed(monkeypatch):
    monkeypatch.setattr(sources, "UNSEAL_CACHE", None)
    assert not (freeze.ROOT / "frozen" / "v4" / "unseal.log").exists()
    assert sources.unsealed() is False


# run.py finals --unseal calls the unseal and reports a refusal.
def test_run_py_finals_verb(repo, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_cli", freeze.gates.ROOT / "run.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.finals([]) == 1
    assert cli.finals(["--unseal"]) == 1
    assert "refused" in capsys.readouterr().out
    monkeypatch.setattr(freeze, "unseal", lambda: "the log line")
    assert cli.finals(["--unseal"]) == 0
    assert "the final run is the next command" in capsys.readouterr().out.lower()


# The unseal's commit must hold the hash list, pushed, under HEAD.
def test_committed_needs_a_pushed_commit_holding_the_list(tmp_path, monkeypatch):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(tmp_path, "init", "-q", str(work))
    sha = put(work, "frozen/v4/v4.sha256", "abc  fiam/v4/a.py\n")
    monkeypatch.setattr(freeze, "ROOT", work)
    monkeypatch.setattr(freeze, "SHA", sha)
    git(work, "add", "frozen")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "freeze")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True,
                          text=True, check=True).stdout.strip()  # fmt: skip
    digest = hashlib.sha256(sha.read_bytes()).hexdigest()
    # Not pushed yet: refused; a forged digest is refused too.
    assert not freeze.committed(head, digest)
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    assert freeze.committed(head, digest)
    assert not freeze.committed(head, "0" * 64)
    assert not freeze.committed("f" * 40, digest)
