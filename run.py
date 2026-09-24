# Runs everything in order. --ml adds models, --agents the agents, --official the WRDS gate.

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

STEPS = [
    (["src/pipeline.py"], "building the portfolio"),
    (["src/exhibits/pack.py"], "sub-periods, costs, risk and signal attribution"),
    (["src/controls/wrds_checks.py"], "checking exits, returns, market and report dates on WRDS"),
    (["src/exhibits/confirmation.py"], "running the frozen book on 2016-2020"),
    (["src/exhibits/live_forecast.py"], "building and hashing the live September 2026 book"),
    (["src/exhibits/live_score.py"], "scoring the live book on cached public prices"),
    (["src/exhibits/config_log.py"], "writing the configuration ledger"),
    (["src/exhibits/labels.py"], "checking every label against CRSP, 8-K filings and EDGAR"),
    (["src/agents/mcp_server.py", "--export"], "writing the agents' tool definitions"),
    (["src/charts.py"], "drawing the performance charts"),
    (["src/research_charts.py"], "drawing the research charts"),
    (["src/docs.py"], "filling RESULTS.md and BRIEF.md, then checking nothing is stale"),
    (["src/provenance.py"], "pinning the baseline and recording which run wrote each artifact"),
    (["src/controls/reproducibility.py"], "auditing for look-ahead and survivorship"),
]

# Model comparison and research controls, about 20 minutes from scratch. Each step reads the last.
ML_STEPS = [
    (["src/ml/dataset.py"], "building the training folds"),
    (["src/ml/train.py"], "fitting ElasticNet, LightGBM and NN3, then scoring each into a book"),
    (["src/controls/selection.py"], "subset sweep, budgeted search and the 147-signal atlas"),
    (["src/ml/summary.py"], "decile tables and the model numbers"),
    (["src/ml/nn3_seeds.py"], "refitting the neural net on five seeds"),
    (["src/ml/oos_r2.py"], "measuring out-of-sample R-squared for every method"),
    (["src/exhibits/earnings.py"], "the earnings module, decided on 2016-2020 first"),
    (["src/exhibits/placebo_lab.py"], "running the permutation and falsification controls"),
    (["src/exhibits/constraint_survival.py"], "tracing where prediction becomes tradeable"),
]

# Through Hermes on the local models, grouped so each loads once. No submitted number uses them.
AGENT_STEPS = [
    (["src/agents/discovery.py"], "signal-discovery agent, named and coded runs"),
    (["src/agents/auditor.py"], "reproducibility agent on planted and clean copies"),
    (["src/agents/critic.py"], "devil's-advocate agent on the second vendor's model"),
    (["src/agents/critic.py", "--repeat"], "the devil's advocate again, to prove the run repeats"),
]

SRC, STAMPS = Path("src"), Path("cache/steps.json")

# Data any step may read. Large files are keyed on size and date, small ones on their bytes.
DATA = [
    "data/chars_final_with_names.parquet",
    "data/factor_char_list.csv",
    "data/wrds/exits.parquet",
    "data/benchmarks/sources.json",
]

# What an agent reads beyond its code: its prompt, its model, and the exhibits it argues about.
AGENT_READS = {
    "src/agents/discovery.py": ["prompts/agents/discovery.md", "submission/metrics.json"],
    "src/agents/critic.py": [
        "prompts/agents/critic.md",
        "submission/holdings.csv",
        "submission/metrics.json",
        "submission/exhibits/pack.json",
        "submission/exhibits/confirmation.json",
        "submission/exhibits/discovery.json",
    ],
    "src/agents/auditor.py": [
        "prompts/agents/auditor.md",
        *sorted(p.as_posix() for p in SRC.rglob("*.py") if "agents" not in p.parts),
    ],
}


# Every local module a script imports, followed through, so a change anywhere it reaches reruns it.
def closure(script: Path) -> list[Path]:
    local = {p.stem: p for p in SRC.rglob("*.py")}
    seen, todo = set(), [script]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            todo += [local[n.split(".")[0]] for n in names if n.split(".")[0] in local]
    return sorted(seen)


# A hash of everything a step depends on. Equal to last time means its outputs are still right.
def stamp(command: list[str]) -> str:
    digest = hashlib.sha256(" ".join(command).encode())
    reads = [
        *closure(Path(command[0])),
        *map(Path, DATA),
        *map(Path, AGENT_READS.get(command[0], [])),
    ]
    if command[0].startswith("src/agents/"):
        reads += [Path("models/MANIFEST.txt"), *sorted(Path("models").glob("*.sha256.json"))]
    for path in reads:
        if not path.exists():
            digest.update(f"{path} missing".encode())
        elif path.stat().st_size > 50_000_000:
            digest.update(f"{path} {path.stat().st_size} {path.stat().st_mtime_ns}".encode())
        else:
            digest.update(path.read_bytes())
    return digest.hexdigest()


# Runs each step in order and stops at the first failure, or a later step reads half-written output.
def main() -> int:
    ml, agents, fresh = ("--ml" in sys.argv, "--agents" in sys.argv, "--fresh" in sys.argv)
    # An official run refuses to call results final unless the WRDS exits are in place.
    env = os.environ | ({"FIAM_OFFICIAL": "1"} if "--official" in sys.argv else {})
    # Models first; agents after the exhibits they read and before the charts and docs show them.
    charts = STEPS.index((["src/charts.py"], "drawing the performance charts"))
    steps = (
        (ML_STEPS if ml else []) + STEPS[:charts] + (AGENT_STEPS if agents else []) + STEPS[charts:]
    )
    groups = {tuple(c): "ml" for c, _ in ML_STEPS} | {tuple(c): "agents" for c, _ in AGENT_STEPS}
    stamps = json.loads(STAMPS.read_text()) if STAMPS.exists() else {}
    reran = set()
    for command, doing in steps:
        group, key = groups.get(tuple(command)), " ".join(command)
        if group:
            current = stamp(command)
            # Skipped only if nothing it reads changed and no earlier step in its group reran.
            if not fresh and group not in reran and stamps.get(key) == current:
                print(f"\n[{doing}] unchanged, skipped", flush=True)
                continue
            reran.add(group)
        print(f"\n[{doing}]", flush=True)
        # The manifest records the model section only on a run that rebuilt it.
        flags = ["--ml"] if ml and command == ["src/provenance.py"] else []
        if subprocess.run([sys.executable, *command, *flags], env=env).returncode != 0:
            print(f"\n{command[0]} failed, stopping here.")
            return 1
        if group:
            stamps[key] = current
            STAMPS.parent.mkdir(exist_ok=True)
            STAMPS.write_text(json.dumps(stamps, indent=2))
    print("\nDone. submission/ and RESULTS.md are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
