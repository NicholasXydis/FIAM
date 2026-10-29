# The one-word commands: help, the rebuild's hand-off and run.py's.

import importlib.util
import subprocess
import sys

from fiam.vfinal import cli
from fiam.vfinal import run as build


# Every verb is listed; an unknown one prints the list and fails.
def test_help_lists_every_verb(capsys):
    assert cli.main(["help"]) == 0
    out = capsys.readouterr().out
    for verb in ("check", "rerun", "compare", "verify", "export", "setup", "doctor", "help"):
        assert f"\n  {verb}" in out, verb
    for gone in ("stage", "whatif", "audit"):
        assert f"\n  {gone} " not in out, gone
    assert cli.main(["nonsense"]) == 2


# The rerun runs every stage of the fund, into the folder given.
def test_rerun_hands_the_folder_to_the_build(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "python", lambda *a, env=None: seen.append((a, env)) or 0)
    assert cli.main(["rerun", str(tmp_path)]) == 0
    args, env = seen[0]
    assert args == ("-m", "fiam.vfinal", "run")
    assert env["FIAM_VFINAL_OUT"] == str(tmp_path.resolve())
    assert cli.main(["rerun", "a", "b"]) == 2


# The stages MAIN.py lists are the ones the build runs, in order.
def test_stages_are_the_builds():
    assert tuple(build.STAGES) == cli.STAGES
    assert set(cli.WHAT) == set(cli.STAGES)


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
