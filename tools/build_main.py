# Builds MAIN.py, the brief's one file: build_main.py [--with-edgar].

import base64
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What git ships except tests, tools, the site and the two plan files.
LEAVE_OUT = (
    "tests/",
    "tools/",
    ".github/",
    "site/",
    ".gitattributes",
    ".gitignore",
    ".env.example",
    "docs/PLAN.md",
    "docs/TEAM.md",
)
# Deck builders, so run.py --finals-pack works from MAIN.py alone.
CARRIED_TOOLS = {"tools/build_deck.py", "tools/build_deck_finals.py", "tools/motion.py"}
BUILT = {"MAIN.py"}
LARGE = {"data/edgar_cache.zip"}
# Ignores later packages, so a new release never changes a judge's run.
EXCLUDE_NEWER = "2026-10-14T00:00:00Z"

LAUNCHER = """
import base64
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


# Writes each carried file that is missing. A file already there is left as it is.
def unpack() -> int:
    written = 0
    for name, (kind, body) in FILES.items():
        path = HERE / name
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(body) if kind == "b64" else body.encode("utf-8")
        path.write_bytes(data)
        written += 1
    return written


# Every carried file already on disk that differs from what MAIN.py holds.
def changed() -> list:
    out = []
    for name, (kind, body) in FILES.items():
        path = HERE / name
        data = base64.b64decode(body) if kind == "b64" else body.encode("utf-8")
        if path.exists() and path.read_bytes() != data:
            out.append(name)
    return out


# Unpacks what is missing, then runs run.py with the same arguments; --check only compares.
def main() -> int:
    if sys.version_info < (3, 14):
        print("MAIN.py needs Python 3.14. Run it with uv, which brings it:  uv run MAIN.py")
        return 1
    if "--check" in sys.argv:
        differ = changed()
        print(f"{len(FILES) - len(differ)} of {len(FILES)} carried files match MAIN.py.")
        for name in differ[:20]:
            print(f"  differs: {name}")
        return 1 if differ else 0
    written = unpack()
    if written:
        print(f"Unpacked {written} files next to MAIN.py.", flush=True)
    os.chdir(HERE)
    return subprocess.run([sys.executable, "run.py", *sys.argv[1:]]).returncode


"""


# uv's script header for Python and the packages, from pyproject.toml.
def script_header() -> str:
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requires = re.search(r'requires-python = "([^"]+)"', toml).group(1)
    deps = re.search(r"dependencies = \[(.*?)\n\]", toml, re.S).group(1)
    deps = [d.strip().rstrip(",") for d in deps.splitlines() if d.strip().startswith('"')]
    source = re.search(r"\[tool\.uv\.sources\]\n(.*?)\n\n", toml, re.S).group(1)
    index = re.search(r"\[\[tool\.uv\.index\]\]\n(.*?)(\n\n|$)", toml, re.S).group(1)
    lines = [
        "/// script",
        f'requires-python = "{requires}"',
        "dependencies = [",
        *[f"    {d}," for d in deps],
        "]",
        "[tool.uv]",
        f'exclude-newer = "{EXCLUDE_NEWER}"',
        "[tool.uv.sources]",
        source,
        "[[tool.uv.index]]",
        index,
        "///",
    ]
    return "\n".join(f"# {line}".rstrip() for text in lines for line in text.splitlines())


# The process, in the words run.py already uses for each step.
def description() -> str:
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    usage = run.split('HELP = """')[1].split('"""')[0]
    header = "\n".join(f"#   {line}" for line in usage.splitlines())
    step = r'\("(fiam\.[\w.]+)[^"]*", "([^"]+)"\)'
    blocks = [
        ("with --agents", "CROWD_STEPS = ["),
        ("with --ml", "ML_STEPS = ["),
        ("with --ml", "RESEARCH_STEPS = ["),
        ("", "STEPS = ["),
        ("with --agents", "AGENT_STEPS = ["),
        ("", "REPORT = ["),
    ]
    listed = []
    for flag, start in blocks:
        block = run[run.index(start) : run.index("]\n\n", run.index(start))]
        for script, what in re.findall(step, block):
            listed.append(f"#   {what:<66} {script}" + (f"  ({flag})" if flag else ""))
    return (
        "# MAIN.py: McGill-FIAM Asset Management Hackathon 2026, market-neutral US equity book.\n"
        "#\n# Run:  pip install uv, then  uv run MAIN.py   (uv brings Python and the packages)\n"
        "#   With nothing beside it: checks our holdings and returns against the brief.\n"
        "#   With the organizer's three data files beside it: rebuilds the book, a few minutes.\n"
        "#   Run it from the folder that holds MAIN.py. On Windows, if uv is not found:\n"
        "#   py -m uv run MAIN.py\n"
        "#   It writes the project's code beside itself to run. It holds no organizer data\n"
        "#   and no raw WRDS data. It does carry our own outputs (holdings, returns, exhibits,\n"
        "#   the learned betas and borrow tiers the book reads) and public FRED and Kenneth\n"
        "#   French series, so every number can be checked offline.\n"
        "#\n" + header + "\n#\n# The steps, in order:\n" + "\n".join(listed) + "\n"
    )


# Tracked files as text or base64. --with-new adds unignored new ones.
def carried(with_edgar: bool, with_new: bool = False) -> dict[str, tuple[str, str]]:
    names = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            *(["--cached", "--others", "--exclude-standard"] if with_new else []),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    files = {}
    for name in sorted(names):
        path = ROOT / name
        left_out = name.startswith(LEAVE_OUT) and name not in CARRIED_TOOLS
        if not name or name in BUILT or left_out or not path.is_file():
            continue
        if name in LARGE and not with_edgar:
            continue
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
            files[name] = ("text", text) if "\r" not in text else ("b64", "")
        except UnicodeDecodeError:
            files[name] = ("b64", "")
        if files[name][0] == "b64":
            files[name] = ("b64", base64.b64encode(data).decode("ascii"))
    return files


# Writes MAIN.py: the header, the steps, the launcher and every file.
def main() -> None:
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else ROOT / "MAIN.py"
    files = carried("--with-edgar" in args, "--with-new" in args)
    body = [script_header(), "", description(), LAUNCHER.strip(), "", ""]
    body.append("# Every file of the repo MAIN.py was built from, written out by unpack().")
    body.append("FILES = {")
    for name, (kind, content) in files.items():
        body.append(f"    {name!r}: ({kind!r}, {content!r}),")
    body += ["}", "", "", 'if __name__ == "__main__":', "    sys.exit(main())", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body), encoding="utf-8", newline="\n")
    print(f"wrote {out}: {len(files)} files, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
