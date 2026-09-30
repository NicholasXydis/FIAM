# Reproducibility agent, scored on bugs planted in a copy of fiam/ and false alarms in a clean one.

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from fiam import paths
from fiam.agents import harness as H

ROOT = H.ROOT
PROMPT = ROOT / "prompts" / "agents" / "auditor.md"
OUT = ROOT / paths.EXHIBITS

# A finding counts if it names the right file within this many lines of the planted bug.
TOLERANCE = 6

# (file, text to replace, replacement, what is wrong). The first three are bugs we really had.
PLANTED = [
    (
        "ml/dataset.py",
        "test_start = pd.Timestamp(year=test_year, month=1, day=1)",
        "test_start = pd.Timestamp(year=test_year, month=2, day=1)",
        "test folds run February to January, off the calendar year the rules prescribe",
    ),
    (
        "book.py",
        'left_by="PERMNO", right_by="permno", direction="backward"',
        'left_by="PERMNO", right_by="permno", direction="nearest"',
        "blank labels can be filled from a later month",
    ),
    (
        "book.py",
        '    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)',
        '    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)\n'
        '    keep &= panel["ret_exc_lead1m"].notna()',
        "the universe is filtered on having a next-month return, which drops failures",
    ),
    (
        "book.py",
        "    panel = data.panel(cols)\n",
        "    panel = data.panel(cols)\n"
        '    panel["ret_exc_lead1m"] = panel.groupby("permno")["ret_exc_lead1m"].shift(-1)\n',
        "the target, already next month's return, is shifted a second time",
    ),
    (
        "book.py",
        '    "eqnetis_at": -1,\n}',
        '    "eqnetis_at": -1,\n    "source_crsp": +1,\n}',
        "a provenance column that separates 2026 perfectly is used as a signal",
    ),
    (
        "ml/dataset.py",
        '        out[col] = out[col].fillna(g.transform("median"))',
        "        out[col] = out[col].fillna(out[col].median())",
        "gaps are filled with a median over the whole sample, including future months",
    ),
    (
        "ml/dataset.py",
        "            validate=df[(m >= val_start) & (m < test_start)],",
        "            validate=df[(m >= val_start) & (m < test_end)],",
        "the validation window overlaps the test year",
    ),
    (
        "ml/teachers.py",
        "        train = (year < test_year) & target.notna()",
        "        train = (year <= test_year) & target.notna()",
        "a teacher trains on the very year it then predicts",
    ),
    (
        "ml/scorer.py",
        "    validate = D.labelled(frame[(m >= val_start) & (m < start)])",
        "    validate = D.labelled(frame[(m >= val_start) & (m < start + pd.DateOffset(years=1))])",
        "the scorer stops early on the test year it is scored on",
    ),
    (
        "book.py",
        '    first, last = f"{year - 2}-01-01", f"{year - 1}-12-01"',
        '    first, last = f"{year - 1}-01-01", f"{year}-12-01"',
        "the ship rule picks a year's book on that same year's returns",
    ),
    (
        "ml/ship.py",
        "        policy = TR.train_deep(tensors, z, np.arange(i), policy)",
        "        policy = TR.train_deep(tensors, z, np.arange(i + 1), policy)",
        "the trader trains on the month it then trades",
    ),
]


# A copy of fiam/, optionally with the bugs planted. Returns where each bug landed.
def make_copy(where: Path, plant: bool) -> list[dict]:
    shutil.copytree(ROOT / "fiam", where, ignore=shutil.ignore_patterns("__pycache__", "agents"))
    planted = PLANTED if plant else []
    for file, old, new, _ in planted:
        path = where / file
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise RuntimeError(f"could not plant in {file}: the code it targets has moved")
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    # Located after every plant is in, since a later one shifts the lines of an earlier one.
    landed = []
    for file, _, new, what in planted:
        text = (where / file).read_text(encoding="utf-8")
        line = text[: text.index(new)].count(chr(10)) + 1
        landed.append(dict(file=file, line=line, bug=what))
    return landed


# Read-only views of the copy. Paths are resolved inside it and nowhere else.
class Repo:
    # The copy of fiam/ the agent reads, and what it has opened so far.
    def __init__(self, root: Path):
        self.root = root

    # Refuses any path that climbs out of the copy.
    def resolve(self, path: str) -> Path:
        full = (self.root / path).resolve()
        if self.root.resolve() not in full.parents and full != self.root.resolve():
            raise ValueError("outside the repository")
        return full

    # Every Python file, relative to the copy's root.
    def list_files(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*.py"))

    # Numbered lines, capped so one read cannot fill the context. The default runs on from start.
    def read_file(self, path: str, start: int = 1, end: int | None = None) -> dict:
        lines = self.resolve(path).read_text(encoding="utf-8").splitlines()
        end = min(end or start + 119, start + 150, len(lines))
        body = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(start, end + 1))
        return dict(path=path, lines=f"{start}-{end} of {len(lines)}", text=body)

    # Matches across every file, capped at sixty.
    def grep(self, pattern: str) -> list[str]:
        hits = []
        for path in self.list_files():
            for i, line in enumerate(self.resolve(path).read_text(encoding="utf-8").splitlines()):
                if re.search(pattern, line):
                    hits.append(f"{path}:{i + 1}: {line.strip()}")
        return hits[:60]


# Four tools and the answer. The agent can read and search, never write or run anything.
def tools(repo: Repo) -> list[H.Tool]:
    finding = dict(
        type="object",
        properties=dict(
            file=dict(type="string"),
            line=dict(type="integer"),
            problem=dict(type="string"),
        ),
        required=["file", "line", "problem"],
    )
    return [
        H.Tool(
            "list_files",
            "Every Python file in the repository.",
            dict(type="object", properties={}),
            lambda: repo.list_files(),
        ),
        H.Tool(
            "read_file",
            "Lines of one file, numbered, at most 150 at a time.",
            dict(
                type="object",
                properties=dict(
                    path=dict(type="string"), start=dict(type="integer"), end=dict(type="integer")
                ),
                required=["path"],
            ),
            lambda path, start=1, end=None: repo.read_file(path, start, end),
        ),
        H.Tool(
            "grep",
            "Lines matching a regular expression, across every file.",
            dict(type="object", properties=dict(pattern=dict(type="string")), required=["pattern"]),
            lambda pattern: repo.grep(pattern),
        ),
        H.Tool(
            "final_answer",
            "Every look-ahead, leakage or survivorship problem you found, with file and line.",
            dict(
                type="object",
                properties=dict(findings=dict(type="array", items=finding)),
                required=["findings"],
            ),
            lambda findings: dict(accepted=True, count=len(findings)),
        ),
    ]


# Recall on the planted copy: a bug is found when a finding names its file near its line.
def score(findings: list[dict], landed: list[dict]) -> dict:
    found = [
        any(
            f.get("file", "").endswith(b["file"])
            and abs(int(f.get("line", -99)) - b["line"]) <= TOLERANCE
            for f in findings
        )
        for b in landed
    ]
    return dict(
        planted=len(landed),
        found=int(sum(found)),
        which=[b["bug"] for b, ok in zip(landed, found) if ok],
    )


# Runs the planted copy, then the clean one, and scores both.
def main() -> None:
    system = PROMPT.read_text(encoding="utf-8")
    task = (
        "Audit this monthly equity backtest for look-ahead bias, leakage and survivorship before "
        "it is submitted. The target is ret_exc_lead1m, next month's excess return."
    )
    out = dict(
        what="Reproducibility agent. Judged on planted bugs it finds and false alarms in a clean "
        "copy. Findings are reviewed by hand; none change the code on their own.",
        runs={},
    )
    with tempfile.TemporaryDirectory() as tmp, H.Server("qwen") as server:
        for tag, plant in (("planted", True), ("clean", False)):
            where = Path(tmp) / tag
            landed = make_copy(where, plant)
            budget = 6 if paths.SMOKE else 60
            run = H.Run("auditor", "qwen", system, task, budget, tag, dict(repo=str(where)))
            result = H.run_agent(server, run, tools(Repo(where)))
            findings = (result["answer"] or {}).get("findings", [])
            out["runs"][tag] = dict(
                status=result["status"],
                steps=result["steps"],
                plan_revisions=len(result["plans"]),
                findings=findings,
                score=score(findings, landed) if plant else dict(false_alarms=len(findings)),
                transcript=result["transcript"].relative_to(ROOT).as_posix(),
            )
    (OUT / "auditor.json").write_text(json.dumps(out, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: v["score"] for k, v in out["runs"].items()}, indent=2))


if __name__ == "__main__":
    main()
