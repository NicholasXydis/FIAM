# Builds MAIN.py, the brief's one file: build_main.py [--with-edgar].

import base64
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What git ships except tests, tools, the site and two docs files.
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
    "finals/",
)
# The fund's own test file, which the lock hashes beside its code.
CARRIED_TESTS = {"tests/test_vfinal.py"}
BUILT = {"MAIN.py"}
LARGE = {"data/edgar_cache.zip"}
# Tables derived from WRDS data, which MAIN.py never carries.
NEVER = {"book_inputs.parquet", "borrow.parquet"}
# Ignores later packages, so a new release never changes a rerun.
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


# The four ways to check the final fund, in MAIN.py's header.
WAYS = """#   1. MAIN.py alone:  uv run MAIN.py
#      checks every PDF rule on every day of the carried book in frozen/vfinal/final/,
#      recomputes the headline (IR, Sharpe, beta, drawdown, CAGR, ending value) from its
#      daily.csv and the public FRED series, and checks the code against the lock in
#      frozen/vfinal/. Seconds.
#   2. MAIN.py with the organisers' files in data/organisers/ (or beside MAIN.py):  uv run MAIN.py
#      does the same, then checks their SHA-256 against our receipts, replays our daily stock
#      P&L on their daily returns and checks the shorts' market caps at each formation. It does
#      not rebuild the fund, which needs our other data, carried only by the USB kit.
#   3. A clone and the USB kit:  git clone <the repository> FIAM, or offline
#      git clone <USB>/fiam_finals/repo.bundle FIAM, then in FIAM
#      uv run fiam setup     restores the kit's data and results, then doctor
#      uv run fiam verify    the lock, then every headline output it records
#   4. A clone and the USB kit, rebuilt from the data:
#      uv run fiam rerun     every stage of the fund from the data, in the order below
#      uv run fiam compare   the rebuild against the locked outputs, file by file"""


# The header: the fund, the four ways, run.py's help and the stages.
def description() -> str:
    sys.path.insert(0, str(ROOT))
    from fiam.vfinal import cli

    run = (ROOT / "run.py").read_text(encoding="utf-8")
    usage = run.split('HELP = """')[1].split('"""')[0]
    header = "\n".join(f"#   {line}" for line in usage.splitlines())
    listed = [f"#   {name:<10} {cli.WHAT[name]}" for name in cli.STAGES]
    return (
        "# MAIN.py: McGill-FIAM Asset Management Hackathon 2026, QUARCC Purple's final fund,\n"
        "# vfinal: market-neutral US equities from US$1bn, compounding, 2021-01 to 2026-08.\n"
        "#\n# Run:  pip install uv, then  uv run MAIN.py   (uv brings Python and the packages)\n"
        "#   Run it from the folder that holds MAIN.py. On Windows, if uv is not found:\n"
        "#   py -m uv run MAIN.py\n"
        "#   It writes the code and our carried results (frozen/vfinal/final/) beside it, then\n"
        "#   runs run.py with the same arguments. It holds no organisers' data and no raw WRDS\n"
        "#   data. It does carry the public FRED and Kenneth French series, so every number\n"
        "#   can be checked offline.\n"
        "#\n# Four ways to check the fund:\n" + WAYS + "\n"
        "#\n# run.py's options, the same for MAIN.py:\n" + header + "\n"
        "#\n# The stages uv run fiam rerun runs, in order (fiam/vfinal/run.py):\n"
        + "\n".join(listed)
        + "\n"
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
        left_out = name.startswith(LEAVE_OUT) and name not in CARRIED_TESTS
        if not name or name in BUILT or left_out or not path.is_file():
            continue
        if Path(name).name in NEVER:
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
