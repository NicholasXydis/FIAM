# Comment rule checker: one comment line, 72 chars, above each def.

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 72
# Tool directives, not prose, so they never count as a comment line.
DIRECTIVES = ("# fmt:", "# noqa", "# type:", "# pragma", "# ruff:")
# Generated files carry their sources' comments and are checked there.
SKIP = {"MAIN.py"}
# Comments describe the code as it is now, never its history.
BANNED = {
    "a history word": r"\b(?:bugs?|fixed|mistakes?|wrong|was|earlier)\b",
}
# External names that look banned: URLs, code spans, fixed-b.
ALLOWED = (
    r"https?://\S+",
    r"`[^`]*`",
    r"\bfixed-b\b",
    r"\bIBKR Pro Fixed\b",
)


# Whether a stripped line is prose, not a shebang or a directive.
def is_comment(line: str) -> bool:
    return line.startswith("#") and not line.startswith("#!") and not line.startswith(DIRECTIVES)


# Each kind of banned word in one comment, external names left out.
def banned(comment: str) -> list[str]:
    text = comment
    for pattern in ALLOWED:
        text = re.sub(pattern, " ", text)
    flags = {"a person": re.IGNORECASE, "a history word": re.IGNORECASE}
    return [what for what, rx in BANNED.items() if re.search(rx, text, flags.get(what, 0))]


# Lines that hold only a prose comment, from Python's own tokens.
def comment_lines(source: str) -> dict[int, str]:
    lines = source.splitlines()
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and not lines[tok.start[0] - 1][: tok.start[1]].strip():
            out[tok.start[0]] = tok.string.strip()
    return out


# Prose comments that follow code on their line, from Python's tokens.
def trailing(source: str) -> dict[int, str]:
    lines = source.splitlines()
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        text = tok.string.strip()
        if tok.type == tokenize.COMMENT and lines[tok.start[0] - 1][: tok.start[1]].strip():
            if is_comment(text):
                out[tok.start[0]] = text
    return out


# Every rule break in one file's source, as (line, what) pairs.
def problems(source: str) -> list[tuple[int, str]]:
    notes = comment_lines(source)
    found = []
    metadata = False
    for n in sorted(notes):
        s = notes[n]
        # A "# /// script" block is uv's inline metadata, not prose.
        if s == "# /// script" or (metadata and s == "# ///"):
            metadata = s == "# /// script"
            continue
        if metadata or not is_comment(s):
            continue
        if len(s) > LIMIT:
            found.append((n, f"comment of {len(s)} characters"))
        found += [(n, f"{what} in a comment") for what in banned(s)]
        above = notes.get(n - 1, "")
        if is_comment(above) and above != "# ///":
            found.append((n, "a second comment line stacked under another"))
    for n, s in trailing(source).items():
        found += [(n, f"{what} in a comment") for what in banned(s)]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            if first < 2 or not is_comment(notes.get(first - 1, "")):
                found.append((first, f"no comment above {node.name}"))
    return sorted(found)


# The repository's Python files, tracked or new, except generated ones.
def python_files() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    ).stdout.split()
    keep = [n for n in sorted(set(names)) if n not in SKIP]
    return [ROOT / n for n in keep if (ROOT / n).exists()]


# Lists every break: uv run tools/comments.py [paths]
if __name__ == "__main__":
    paths = [Path(p).resolve() for p in sys.argv[1:]] or python_files()
    total = 0
    for path in paths:
        for n, what in problems(path.read_text(encoding="utf-8")):
            print(f"{path.relative_to(ROOT)}:{n}: {what}")
            total += 1
    print(f"{total} problems in {len(paths)} files")
    sys.exit(1 if total else 0)
