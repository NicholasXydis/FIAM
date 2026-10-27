# The finals kit on a tiny fake repo: export, setup, break-it cases.

import json
import sys
import zipfile
from pathlib import Path

import pytest

from fiam import kit as results
from fiam.vfinal import kit

FILES = {
    "data/organisers/readme.md": b"organisers",
    "data/edgar/docs/1/a.gz": b"\x1f\x8b" + bytes(range(256)) * 40,
    "data/v4/extracts/t.parquet": bytes(range(256)) * 400,
    "models/tiny.gguf": b"weights" * 100,
    "docs/PLAN.md": b"plan",
    "NOTES.md": b"rules",
    "frozen/x.json": b"{}",
}


# A fake repo in a folder with spaces, wired into the kit module.
@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "my repo"
    for name, body in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(body)
    local = root / "out" / "kit"
    monkeypatch.setattr(kit, "ROOT", root)
    monkeypatch.setattr(kit, "LOCAL", local)
    monkeypatch.setattr(kit, "HASHES", local / "hashes.json")
    monkeypatch.setattr(kit, "RECORD", root / "data" / "KIT.json")
    monkeypatch.setattr(kit, "hf_home", lambda: tmp_path / "hf")
    monkeypatch.setattr(results, "PARTS", ("frozen",))
    monkeypatch.setattr(kit, "main_py", lambda folder: (folder / "MAIN.py").write_text("x"))
    return root


# Exports the fake repo and returns the kit folder.
def exported(repo: Path) -> Path:
    folder = repo.parent / "USB drive" / kit.NAME
    assert kit.export(folder) == 0
    return folder


# A fresh machine gets every file back, byte for byte.
def test_export_then_setup_restores_every_file(repo):
    folder = exported(repo)
    fresh = repo.parent / "fresh machine"
    assert kit.setup(folder, root=fresh) == 0
    for name, body in FILES.items():
        assert (fresh / name).read_bytes() == body
    record = json.loads((fresh / "data" / "KIT.json").read_text())
    assert set(record["files"]) == set(FILES)
    assert (folder / "LICENSES.md").exists() and (folder / "README.txt").exists()


# Files in the kit folder that are not the kit's are named, untouched.
def test_export_reports_foreign_files(repo, capsys):
    folder = exported(repo)
    (folder / "old.zip").write_text("old")
    capsys.readouterr()
    assert kit.export(folder) == 0
    assert "left alone: old.zip" in capsys.readouterr().out
    assert (folder / "old.zip").read_text() == "old"


# A second setup changes nothing and restores nothing.
def test_setup_twice_changes_nothing(repo, capsys):
    folder, fresh = exported(repo), repo.parent / "fresh"
    kit.setup(folder, root=fresh)
    times = {n: (fresh / n).stat().st_mtime_ns for n in FILES}
    capsys.readouterr()
    assert kit.setup(folder, root=fresh) == 0
    assert "restored 0" in capsys.readouterr().out
    assert times == {n: (fresh / n).stat().st_mtime_ns for n in FILES}


# A setup stopped halfway leaves a part file; the next run finishes.
def test_setup_killed_halfway_picks_up(repo):
    folder, fresh = exported(repo), repo.parent / "fresh"
    kit.setup(folder, root=fresh)
    victim = fresh / "data/v4/extracts/t.parquet"
    victim.unlink()
    victim.with_name(victim.name + ".part").write_bytes(b"half")
    assert kit.setup(folder, root=fresh) == 0
    assert victim.read_bytes() == FILES["data/v4/extracts/t.parquet"]
    assert not victim.with_name(victim.name + ".part").exists()


# A damaged zip is caught, reported and never restored.
def test_a_damaged_kit_is_refused(repo, capsys):
    folder, fresh = exported(repo), repo.parent / "fresh"
    zipped = folder / "parts" / "data-stock.zip"
    raw = bytearray(zipped.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    zipped.write_bytes(bytes(raw))
    assert kit.setup(folder, root=fresh) == 1
    assert not (fresh / "data/v4/extracts/t.parquet").exists()
    assert "damaged on the kit" in capsys.readouterr().out


# A mismatched hash in the manifest is caught the same way.
def test_a_hash_mismatch_is_refused(repo):
    folder, fresh = exported(repo), repo.parent / "fresh"
    state = json.loads((folder / kit.MANIFEST).read_text())
    state["files"]["docs/PLAN.md"]["sha256"] = "0" * 64
    (folder / kit.MANIFEST).write_text(json.dumps(state))
    assert kit.setup(folder, root=fresh) == 1
    assert not (fresh / "docs/PLAN.md").exists()


# A file already here is kept, even when it differs from the kit.
def test_setup_never_overwrites_a_file(repo, capsys):
    folder, fresh = exported(repo), repo.parent / "fresh"
    (fresh / "docs").mkdir(parents=True)
    (fresh / "docs/PLAN.md").write_text("my edits")
    assert kit.setup(folder, root=fresh) == 0
    assert (fresh / "docs/PLAN.md").read_text() == "my edits"
    assert "kept yours: docs/PLAN.md" in capsys.readouterr().out


# A second export rewrites only the part whose files changed.
def test_export_rewrites_only_changed_parts(repo, capsys):
    folder = exported(repo)
    zips = {p.name: p.stat().st_mtime_ns for p in (folder / "parts").glob("*.zip")}
    (repo / "docs/PLAN.md").write_text("new plan")
    capsys.readouterr()
    assert kit.export(folder) == 0
    out = capsys.readouterr().out
    assert "docs: writing" in out and "data-stock: unchanged" in out
    after = {p.name: p.stat().st_mtime_ns for p in (folder / "parts").glob("*.zip")}
    assert [n for n in zips if zips[n] != after[n]] == ["docs.zip"]


# Too little room stops the export before anything is written.
def test_export_stops_when_the_drive_is_full(repo, monkeypatch):
    folder = repo.parent / "small"
    usage = type("Usage", (), {"free": 10, "total": 10})
    monkeypatch.setattr(kit.shutil, "disk_usage", lambda _: usage)
    assert kit.export(folder) == 1
    assert not (folder / "parts").exists()


# Names that would escape the repo or break Windows are refused.
def test_unsafe_names_are_refused(repo, monkeypatch):
    for name in ("../x", "/etc/x", "a/../../x", "data/a:b", "data/con.txt", "data/x "):
        with pytest.raises(ValueError):
            kit.destination(name, repo)
    assert kit.destination("huggingface/hub/m/x", repo).is_relative_to(kit.hf_home())
    # Windows cannot even create aux.txt, so the walk reports the name.
    bad = repo / "data/organisers/readme.md"
    monkeypatch.setattr(kit, "walk", lambda source, dest: [(bad, "data/aux.txt")])
    with pytest.raises(SystemExit):
        kit.plan()


# Every file in a part's zip is named exactly as the manifest says.
def test_manifest_matches_the_zips(repo):
    folder = exported(repo)
    state = json.loads((folder / kit.MANIFEST).read_text())
    for part, entry in state["parts"].items():
        with zipfile.ZipFile(folder / entry["zip"]) as zf:
            named = {n for n, e in state["files"].items() if e["part"] == part}
            assert set(zf.namelist()) == named


# The command line: verb, one folder and the parts to skip.
def test_options_parse_folder_and_skip():
    assert kit.options(["setup", "--skip", "a,b", "E:/fiam finals"]) == (
        "setup",
        "E:/fiam finals",
        {"a", "b"},
    )
    assert kit.options(["doctor", "--deep"]) == ("doctor", None, set())


# Doctor flags a missing package and an AI server that does not answer.
def test_doctor_checks_packages_and_the_ai_link(monkeypatch):
    assert kit.packages(["surely-not-installed-pkg==1.0"])[0][1] == "uv sync"
    assert kit.packages(["pytest>=1"]) == []
    monkeypatch.delenv("FIAM_LLM_URL", raising=False)
    assert "replays saved answers" in kit.llm()[0][0]
    monkeypatch.setenv("FIAM_LLM_URL", "http://127.0.0.1:9")
    assert "not answering" in kit.llm()[0][0]


# Building caches never points pnpm at the real site or runs scripts.
def test_caches_leave_the_site_alone(repo, monkeypatch):
    (repo / "site").mkdir()
    (repo / "site/package.json").write_text("{}")
    (repo / "site/pnpm-lock.yaml").write_text("lockfileVersion: '9.0'")
    ran = []
    monkeypatch.setattr(kit.subprocess, "run", lambda step, **_: ran.append(step))
    monkeypatch.setattr(kit, "kit_uv", lambda _: "uv")
    monkeypatch.setattr(kit.shutil, "which", lambda name: name)
    monkeypatch.setenv("SystemDrive", str(repo.parent))
    assert kit.caches() == 0
    pnpm = next(step for step in ran if step[0] == "pnpm")
    folder = Path(pnpm[pnpm.index("--dir") + 1])
    assert folder != repo / "site" and "--config.ignore-scripts=true" in pnpm
    assert (repo / "out/kit/caches" / f"{kit.os_tag()}.zip").exists()
    assert not (repo / "site/node_modules").exists()


# The kit leaves out exactly what the data status calls Mac-only.
def test_kit_and_status_agree_on_what_stays_home():
    import importlib.util

    tools = Path(__file__).resolve().parent.parent / "tools" / "data"
    sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("status", tools / "status.py")
    status = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(status)
    home = {f"data/{part}" + ("" if part.endswith(".zip") else "/") for part in status.OFF_USB}
    assert home == set(kit.SKIP)


# Doctor says how to get LightGBM's OpenMP runtime when it is missing.
def test_doctor_names_the_openmp_fix(monkeypatch):
    import builtins

    real = builtins.__import__

    # Fails the lightgbm import the way a missing libgomp does.
    def broken(name, *args, **kwargs):
        if name == "lightgbm":
            raise OSError("libgomp.so.1: cannot open shared object file")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    monkeypatch.delitem(sys.modules, "lightgbm", raising=False)
    problem = kit.openmp()[0]
    assert "lightgbm cannot load" in problem[0] and problem[1]


# A Windows CRLF checkout of a small text file matches its kit entry.
def test_crlf_text_matches_its_lf_kit_entry(tmp_path):
    lf = b'{\n "a": 1\n}\n'
    path = tmp_path / "x.json"
    path.write_bytes(lf.replace(b"\n", b"\r\n"))
    entry = {"size": len(lf), "sha256": kit.hashlib.sha256(lf).hexdigest()}
    assert kit.matches(path, entry) and kit.matches(path, entry, deep=True)
    path.write_bytes(b'{\r\n "a": 2\r\n}\r\n')
    assert not kit.matches(path, entry, deep=True)


# A data folder no part holds is named, never dropped quietly.
def test_left_out_names_data_no_part_holds(tmp_path):
    (tmp_path / "data" / "kept").mkdir(parents=True)
    (tmp_path / "data" / "kept" / "a.csv").write_text("1")
    (tmp_path / "data" / "new").mkdir()
    (tmp_path / "data" / "new" / "b.csv").write_text("2")
    assert kit.left_out([tmp_path / "data" / "kept"], tmp_path) == {"data/new": 1}
