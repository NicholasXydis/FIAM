# The one-word commands: help, the rerun's order and run.py's hand-off.

import importlib.util
import json
import subprocess
import sys

from fiam.vfinal import cli, gates, headline

HEAD = "a" * 40
# Pre-2021 results as the headline's rules read them.
RESULTS = {
    ("forecasts", "quarterly"): {"ic_2017_2020": 0.0233},
    ("forecasts", "yearly"): {"ic_2017_2020": 0.0180},
    ("early", "quarterly", "loose"): {"ir": -0.093, "breach_days": 0},
    ("early", "quarterly", "tight"): {"ir": -0.241, "breach_days": 0},
}


# A stand-in stage: writes its file from the results, pick by its rules.
def fake_stage(ran: list, results: dict):
    # One stage's file, written where the headline looks for it.
    def stage(args):
        ran.append(tuple(args))
        name, rest = args[0], tuple(args[1:])
        body = headline.pick(HEAD) if name == "pick" else results.get(tuple(args), {})
        path = headline.where(name, rest, HEAD)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
        return 0

    return stage


# Every verb is listed; an unknown one prints the list and fails.
def test_help_lists_every_verb(capsys):
    assert cli.main(["help"]) == 0
    out = capsys.readouterr().out
    for verb in ("check", "rerun", "stage", "whatif", "lock", "verify", "audit", "export",
                 "setup", "doctor", "help"):  # fmt: skip
        assert f"\n  {verb}" in out, verb
    assert cli.main(["nonsense"]) == 2


# The rerun runs the headline stages, then only what pick still needs.
def test_rerun_satisfies_pick(tmp_path, monkeypatch):
    monkeypatch.setattr(headline, "BASE", tmp_path)
    monkeypatch.setattr(gates, "commit", lambda: HEAD)
    ran = []
    monkeypatch.setattr(cli, "stage", fake_stage(ran, RESULTS))
    assert cli.rerun() == 0
    assert ran == [
        ("labels",),
        ("forecasts", "quarterly"),
        ("early", "quarterly", "loose"),
        ("book", "quarterly", "loose"),
        ("report", "quarterly", "loose"),
        ("forecasts", "yearly"),
        ("early", "quarterly", "tight"),
        ("pick",),
    ]
    got = json.loads(headline.where("pick", (), HEAD).read_text())
    assert got["final"] and (got["cadence"], got["limits"]) == cli.HEADLINE
    # A second rerun at the same commit skips every stage done.
    ran.clear()
    assert cli.rerun() == 0
    assert ran == [("pick",)]


# A pick that names another headline stops the rerun with a failure.
def test_rerun_stops_when_pick_differs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(headline, "BASE", tmp_path)
    monkeypatch.setattr(gates, "commit", lambda: HEAD)
    flipped = RESULTS | {("forecasts", "yearly"): {"ic_2017_2020": 0.03}}
    ran = []
    monkeypatch.setattr(cli, "stage", fake_stage(ran, flipped))
    assert cli.rerun() == 1
    assert ("early", "yearly", "tight") not in ran
    assert "did not reproduce" in capsys.readouterr().out


# A dirty or unpushed tree stops the rerun before any stage.
def test_rerun_refuses_a_dirty_tree(monkeypatch, capsys):
    # The tree check's refusal, as gates.commit raises it.
    def refuse():
        raise RuntimeError("the tree is not clean")

    monkeypatch.setattr(gates, "commit", refuse)
    monkeypatch.setattr(cli, "stage", lambda args: 1 / 0)
    assert cli.rerun() == 1
    assert "refused" in capsys.readouterr().out


# The folder runs as a program, as uv run fiam does, from the root.
def test_fiam_folder_runs_help():
    got = subprocess.run([sys.executable, "fiam", "help"], cwd=cli.ROOT, capture_output=True,
                         text=True, timeout=120)  # fmt: skip
    assert got.returncode == 0 and "uv run fiam <verb>" in got.stdout


# run.py hands each final verb to the same commands.
def test_run_py_hands_over_the_final_verbs():
    spec = importlib.util.spec_from_file_location("run_cli", cli.ROOT / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    for verb in run.FINAL_VERBS:
        assert f"\n  {verb}" in cli.HELP, verb
