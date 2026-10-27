# The step 10 freeze and the one unseal (PLAN §13.2, §13.3).

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fiam.v4 import gates, sources
from fiam.v4.construct import book
from fiam.v4.desk import run as desk

ROOT = gates.ROOT
FROZEN = ROOT / "frozen" / "v4"
CONFIG, DECISIONS = FROZEN / "config.json", FROZEN / "decisions.json"
SHA, LOG = FROZEN / "v4.sha256", FROZEN / "unseal.log"
OUT = ROOT / "out" / "v4"
PROTOCOL = ROOT / "versions" / "v4" / "protocol.md"
SETTINGS = ROOT / "versions" / "v4" / "settings.json"
FORECASTS = book.FORECASTS
# Each result's file: the six gates' commit pinned, the rest exact.
FINDERS = {
    "gates": lambda at: OUT / "gates" / f"gates_{gates.SIX}.json",
    "late": lambda at: latest(OUT / "gates", "late", at),
    "controls": lambda at: OUT / "gates" / f"controls_{gates.SIX}.json",
    "power": lambda at: OUT / "gates" / f"power_{gates.SIX}.json",
    "validate": lambda at: OUT / "forecast" / f"validate_{FORECASTS.stem.split('_')[-1]}.json",
    "settings": lambda at: SETTINGS,
    "tests": lambda at: OUT / "construct" / f"exam_tests_{exam_at(at)}.json",
    "designs": lambda at: OUT / "construct" / f"exam_designs_{exam_at(at)}.json",
    "brake": lambda at: OUT / "construct" / f"exam_brake_{exam_at(at)}.json",
    "history": lambda at: OUT / "history" / "history.json",
    "fallbacks": lambda at: ROOT / "data" / "v4" / "cards" / "fallbacks.json",
    "decide": lambda at: latest(OUT / "desk", "decide", at),
}
# PLAN §13.2's list: name, source kind, keys (none: the whole file).
ITEMS = [
    ("every gate result and the Holm table", "gates", ("gates", "holm", "kiefer_vogelsang")),
    ("the late gates (options flow, earnings premium)", "late", ("late",)),
    ("the gates' controls", "controls", ("controls",)),
    ("the gates' power check", "power", ("power",)),
    ("ancillary results (K2) and the SUE gate", "gates", ("ancillaries",)),
    ("grid cell, w_ML, target and training stocks (levers C2, D1)", "validate", ("chosen",)),
    ("ensemble and confidence settings", "validate", ("members",)),
    ("the re-derived alpha scale and cost budget", "settings", ("alpha_scale", "cost_budget")),
    ("C at 2020-12-31 (lever A2)", None, ()),
    ("m and d (lever A2)", "settings", ("margin", "margin_costs")),
    ("the sector band (lever B1)", "settings", ("sector_band", "sector_band_tc")),
    ("lever A4's rate", "settings", ("a4_rate",)),
    ("ridge for both name targets", "settings", ("ridge", "ridge_names", "ridge_concentrated")),
    ("b (the style cap)", "settings", ("style_cap", "style_cap_shares")),
    ("the French vintage result and crash control kept or not", None, ()),
    ("brake kept or not", "brake", ("brake",)),
    ("cadence", "tests", ("cadence",)),
    ("each overlay on or off (lever E5)", "tests", ("overlays",)),
    ("the crowding screen's pre-2021 cost (lever C3)", None, ()),
    ("the mid-cap cap's pre-2021 cost", None, ()),
    ("B17", "history", ("b17",)),
    ("B23's L or current vintage", None, ()),
    ("FINRA short-interest coverage", "fallbacks", ("short_interest",)),
    ("the 2026 volume source (CA0065S, FINRA or off) with its test results", "fallbacks",
     ("volume", "volume_source_2026")),
    ("the return basis (lever D3)", None, ()),
    ("the exam's results and the chosen design (lever E1)", "designs",
     ("designs", "winner", "reading")),
    ("the headline AI arm and its inputs", "decide", ()),
    ("v3's fifteen choices as re-decided (B2)", None, ()),
]  # fmt: skip


# A path as the repository root names it.
def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# The sha256 of one file, read in blocks.
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# HEAD of a clean, pushed tree, else a refusal (gates.commit's rule).
def head() -> str:
    try:
        return gates.commit()
    except RuntimeError as err:
        raise SystemExit(f"refused: {err}") from err


# The 12 characters of the exam's commit: the pinned one, else HEAD.
def exam_at(at: str) -> str:
    return (desk.EXAM_AT or at)[:12]


# A stage's result at this commit, else its only one; never a guess.
def latest(folder: Path, stage: str, at: str) -> Path:
    exact = folder / f"{stage}_{at[:12]}.json"
    if exact.exists():
        return exact
    found = sorted(folder.glob(f"{stage}_*.json"))
    if len(found) > 1:
        raise SystemExit(f"refused: {len(found)} {stage} results and none at HEAD; pin one")
    return found[0] if found else exact


# Files git tracks under fiam/v4/ and the model pins, as repo paths.
def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "fiam/v4", "fiam/agents/harness.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return sorted(n for n in out.split("\0") if n)


# What the freeze hashes: its own files, the pins and every code file.
def hashed() -> list[str]:
    own = [CONFIG, DECISIONS, PROTOCOL, SETTINGS, FORECASTS]
    return sorted({*(rel(p) for p in own), *tracked()})


# One decision's record, from its source file or marked not built.
def record(name: str, kind: str | None, keys: tuple, at: str) -> dict:
    path = FINDERS[kind](at) if kind else None
    if path is None:
        return {"status": "not built", "source": f"no result file in out/v4/ for {name}"}
    if not path.is_file():
        return {"status": "not built", "source": rel(path)}
    body = json.loads(path.read_text())
    # A stage's file holds its result under its own name, beside a stamp.
    inner = body.get(kind)
    if isinstance(inner, dict) and keys and all(k in inner for k in keys):
        body = inner | {"stamp": body.get("stamp")}
    gone = [k for k in keys if k not in body]
    if gone:
        return {"status": "not built", "source": f"{rel(path)} key {', '.join(gone)}"}
    return {"status": "recorded", "source": rel(path), "source_sha256": digest(path),
            "stamp": body.get("stamp"),
            "value": {k: body[k] for k in keys} if keys else body}  # fmt: skip


# The time-cutoff model's name, found from the desk's pinned build.
def cutoff_model() -> dict:
    sha = desk.CUTOFF_META["model_sha"]
    name = next(k for k, v in desk.harness.MODELS.items() if v[2] == sha)
    value = {"name": name, "cutoff": desk.CUTOFF_META["cutoff"], "model_sha": sha}
    return {"status": "recorded", "source": "fiam/v4/desk/run.py CUTOFF_META", "value": value}


# Every item PLAN §13.2 lists, from files that exist, else not built.
def decisions(at: str) -> dict:
    items = {name: record(name, kind, keys, at) for name, kind, keys in ITEMS}
    items["the time-cutoff model's name"] = cutoff_model()
    return {"commit": at, "items": items}


# The headline arm: the desk's decision, else A0 (reading 16).
def headline(at: str) -> dict:
    path = FINDERS["decide"](at)
    got = json.loads(path.read_text()) if path.is_file() else {}
    if "headline" not in got:
        return {"arm": "A0", "reason": "desk not finished"}
    return {"arm": got["headline"], "source": rel(path), "source_sha256": digest(path)}


# The frozen configuration: commit, settings, forecasts, design, arm.
def config(at: str) -> dict:
    designs = FINDERS["designs"](at)
    if not designs.is_file():
        raise SystemExit(f"refused: {rel(designs)} is missing, run the exam designs first")
    if not FORECASTS.is_file():
        raise SystemExit(f"refused: {rel(FORECASTS)} is missing")
    made = json.loads(designs.read_text())
    if made.get("winner") is None:
        raise SystemExit("refused: the exam has no winning design, tell the leader")
    return {"commit": at, "settings": json.loads(SETTINGS.read_text()),
            "forecasts": {"file": FORECASTS.name, "sha256": digest(FORECASTS)},
            "exam_design": {"winner": made["winner"], "reading": made.get("reading"),
                            "source": rel(designs), "source_sha256": digest(designs)},
            "headline": headline(at)}  # fmt: skip


# Writes the three files, then the sorted sha256 list; returns it.
def freeze() -> list[str]:
    if LOG.exists():
        raise SystemExit("refused: the unseal log exists, nothing refreezes")
    at = head()
    made = config(at), decisions(at)
    FROZEN.mkdir(parents=True, exist_ok=True)
    for path, body in zip((CONFIG, DECISIONS), made):
        path.write_text(json.dumps(body, indent=1, default=str) + "\n")
    lines = [f"{digest(ROOT / name)}  {name}" for name in hashed()]
    SHA.write_text("\n".join(lines) + "\n")
    return lines


# Every hash in v4.sha256 recomputed: the mismatches, none if sound.
def verify() -> list[str]:
    if not SHA.is_file():
        return [f"{rel(SHA)}: missing"]
    bad, listed = [], set()
    for line in SHA.read_text().splitlines():
        want, _, name = line.partition("  ")
        listed.add(name)
        path = ROOT / name
        if not name or not path.is_file():
            bad.append(f"{name}: missing")
        elif digest(path) != want:
            bad.append(f"{name}: changed")
    # The pins and the code must all be listed; a new code file counts.
    must = {rel(p) for p in (CONFIG, DECISIONS, PROTOCOL, SETTINGS, FORECASTS)}
    bad += [f"{n}: not in the freeze" for n in sorted((must | set(tracked())) - listed)]
    # Every result decisions.json records must still be the file it hashed.
    if DECISIONS.is_file():
        for name, r in json.loads(DECISIONS.read_text())["items"].items():
            path = ROOT / r.get("source", "")
            if "source_sha256" in r and (not path.is_file() or digest(path) != r["source_sha256"]):
                bad.append(f"{r['source']}: changed since the freeze ({name})")
    return bad


# Whether v4.sha256 is tracked by git at HEAD (clean tree: the index).
def sha_tracked() -> bool:
    got = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel(SHA)],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    return got.returncode == 0


# Whether a commit holds this hash list and is pushed and under HEAD.
def committed(commit: str, sha: str) -> bool:
    # One git command's result in the repository.
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)

    shown = git("show", f"{commit}:{rel(SHA)}")
    if shown.returncode or hashlib.sha256(shown.stdout).hexdigest() != sha:
        return False
    if git("merge-base", "--is-ancestor", commit, "HEAD").returncode:
        return False
    return bool(git("branch", "-r", "--contains", commit).stdout.strip())


# The one unseal: refuses unless sound, then logs time, HEAD, v4.sha256.
def unseal() -> str:
    if LOG.exists():
        raise SystemExit("refused: one unseal only, the log exists")
    at = head()
    if not sha_tracked():
        raise SystemExit(f"refused: {rel(SHA)} is not tracked by git, commit it first")
    if not committed(at, digest(SHA)):
        raise SystemExit(f"refused: HEAD's committed {rel(SHA)} differs or is not pushed")
    bad = verify()
    if bad:
        raise SystemExit("refused: the freeze does not verify\n  " + "\n  ".join(bad))
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{when} {at} {digest(SHA)}"
    # Exclusive create: a second unseal can never overwrite the first.
    with LOG.open("x") as fh:
        fh.write(line + "\n")
    sources.UNSEAL_CACHE = None
    return line


# True only for one log line whose pushed commit holds v4.sha256.
def opened() -> bool:
    if not LOG.is_file() or not SHA.is_file():
        return False
    lines = LOG.read_text().splitlines()
    parts = lines[0].split() if len(lines) == 1 else []
    try:
        sound = len(parts) == 3 and parts[2] == digest(SHA)
        return sound and committed(parts[1], parts[2]) and not verify()
    except OSError, subprocess.CalledProcessError:
        return False


# python -m fiam.v4.freeze freeze | verify | unseal
if __name__ == "__main__":
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb == "freeze":
        done = freeze()
        print(f"wrote {rel(SHA)}: {len(done)} files hashed. Commit and push, then unseal.")
    elif verb == "verify":
        problems = verify()
        print("\n".join(problems) if problems else f"{rel(SHA)} verifies")
        sys.exit(1 if problems else 0)
    elif verb == "unseal":
        print(unseal())
    else:
        raise SystemExit("python -m fiam.v4.freeze freeze | verify | unseal")
