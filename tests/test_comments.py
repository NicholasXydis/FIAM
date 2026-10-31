# The comment rule on every Python file: one short comment line each.

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "comments.py"
spec = importlib.util.spec_from_file_location("comments", TOOL)
comments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comments)


# No file stacks comments, runs past 72 characters or skips a def.
def test_every_file_keeps_one_short_comment_line():
    found = [
        f"{path.name}:{n}: {what}"
        for path in comments.python_files()
        for n, what in comments.problems(path.read_text(encoding="utf-8"))
    ]
    assert found == []


# The checker sees stacked, long and missing comments, never strings.
def test_checker_finds_each_break():
    source = (
        "# One.\n# Two.\n"
        "def f():\n    return 1\n\n\n"
        "def g():\n    return '''\n# not a comment\n# still not\n'''\n"
        "# " + "x" * 80 + "\n"
    )
    whats = [what for _, what in comments.problems(source)]
    assert "a second comment line stacked under another" in whats
    assert "no comment above g" in whats
    assert any(w.startswith("comment of") for w in whats)
    assert len(whats) == 3


# History words fail; outside names that look like them pass.
def test_checker_finds_banned_words():
    bad = {
        "# A bug fixed here.": "a history word",
        "# It was slow.": "a history word",
        "x = 1  # the earlier rule": "a history word",
    }
    for line, what in bad.items():
        whats = [w for _, w in comments.problems(line + "\n")]
        assert f"{what} in a comment" in whats, line
    good = (
        "# OpenFEMA v2 serves the designations.\n"
        "x = 1  # GET https://example.com/was/items for each page.\n"
        "y = 2  # Run `was_run` first.\n"
        "v = 5  # Kiefer-Vogelsang fixed-b values.\n"
    )
    assert comments.problems(good) == []
