# Runs an agent through Hermes on the pinned local model and writes its transcript.

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPTS = ROOT / "submission" / "exhibits" / "agents"
RUNS = ROOT / "cache" / "agents"
# The MCP server reads this on start: present means a scored run, absent means research.
RUN_FILE = RUNS / "run.json"

# The Windows Vulkan binary, or the Linux build setup_lightning.sh makes. Either can be overridden.
BUILDS = [
    ROOT / "models/llama.cpp/llama-server.exe",
    ROOT / "models/llama.cpp-src/build/bin/llama-server",
]
SERVER = Path(os.environ.get("LLAMA_SERVER") or next((b for b in BUILDS if b.exists()), BUILDS[0]))
DEVICE = os.environ.get("LLAMA_DEVICE") or ("Vulkan0" if os.name == "nt" else "CUDA0")
HERMES = (
    os.environ.get("HERMES")
    or shutil.which("hermes")
    or str(Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "bin" / "hermes.exe")
)

# Two vendors on purpose. Agreement between two models of one lineage says nothing.
MODELS = {
    "qwen": ROOT / "models" / "Qwen3.8-27B-UD-IQ4_XS.gguf",
    "gemma": ROOT / "models" / "gemma-4-26B-A4B-it-UD-IQ4_XS.gguf",
}

# Repeatability, not correctness: the same prompt gives the same answer, right or wrong.
SEED, TEMPERATURE = 42, 0.0
# Hermes refuses a window under 64K, and on 16 GB Qwen only fits that with a compressed cache.
CONTEXT, PORT = 65536, 8081
COMPRESSED = {"qwen": ("-fa", "on", "-ctk", "q8_0", "-ctv", "q4_0")}
# Thinking off on the server, so the plan the agent writes is the plan we can read.
NO_THINKING = ("--chat-template-kwargs", '{"enable_thinking": false}')

# Calls left when only final_answer is accepted, or a run reads files until its budget is gone.
WARN_AT = 5
# A tool result longer than this is cut, so one call cannot flood the context.
RESULT_CHARS = 6000
# Times a run that stops talking without an answer is asked once more to finish.
NUDGES = 2
NUDGE = "Continue: call a tool, or call final_answer with what you have."


# Read in blocks, so a 14 GB weights file never has to fit in memory.
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


# Hashing 14 GB takes a while, so each file's hash is kept beside it, keyed on size and date.
def model_hash(path: Path) -> str:
    stamp = path.with_suffix(".sha256.json")
    key = dict(bytes=path.stat().st_size, modified=path.stat().st_mtime)
    if stamp.exists() and json.loads(stamp.read_text()).get("key") == key:
        return json.loads(stamp.read_text())["sha256"]
    value = sha256(path)
    stamp.write_text(json.dumps(dict(key=key, sha256=value)))
    return value


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[..., object]


# One llama-server at the pinned settings. One already serving the same model is reused.
class Server:
    def __init__(self, model: str):
        self.name, self.path, self.process = model, MODELS[model], None

    def props(self) -> dict | None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/props", timeout=5) as r:
                p = json.loads(r.read())
        except OSError:
            return None
        return dict(
            build=p.get("build_info"),
            model_path=p.get("model_path"),
            context=p.get("default_generation_settings", {}).get("n_ctx"),
        )

    def __enter__(self) -> Server:
        running = self.props()
        if running:
            if Path(running["model_path"]).name != self.path.name or running["context"] != CONTEXT:
                raise RuntimeError(f"port {PORT} serves another model or context; stop it first")
            return self
        args = [str(SERVER), "-m", str(self.path), "--alias", self.name, "--device", DEVICE]
        args += ["-c", str(CONTEXT), "-np", "1", "--seed", str(SEED), "--temp", str(TEMPERATURE)]
        # Checkpoints crash this build on hybrid attention. Off costs seconds, not correctness.
        args += ["--jinja", "-ctxcp", "0", "-cram", "0", "--host", "127.0.0.1", "--port", str(PORT)]
        args += [*COMPRESSED.get(self.name, ()), *NO_THINKING]
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Loading 14 GB onto the card takes a minute. Poll until the server answers.
        for _ in range(600):
            if self.props():
                return self
            time.sleep(1)
        raise RuntimeError(f"llama-server did not start for {self.name}")

    def __exit__(self, *exc) -> None:
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=60)


@dataclass
class Run:
    agent: str
    model: str
    system: str
    task: str
    budget: int
    tag: str = ""
    options: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.agent}{'_' + self.tag if self.tag else ''}"


# A plan is any numbered list the agent writes. Each new one is a revision, kept in order.
def plan_in(text: str) -> list[str]:
    return re.findall(r"^\s*\d+[.)]\s+(.+)$", text or "", flags=re.M)


# One Hermes turn, one-shot, only our tools, events as JSON lines.
def hermes(query: Path, run: Run, session: str | None) -> list[dict]:
    args = [HERMES, "chat", "--query-file", str(query), "--oneshot", "--format", "stream-json"]
    args += ["-t", "fiam", "--ignore-rules", "--source", "fiam", "--reasoning", "none"]
    # A nudge only needs room to answer, so a stuck run cannot spend a second budget.
    turns = WARN_AT if session else run.budget + WARN_AT
    args += ["--provider", "llamacpp", "-m", run.model, "--max-turns", str(turns)]
    args += ["--resume", session] if session else []
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    return [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]


# Hermes's reply text in order, each tool call filled from the server's full log of it.
def steps(events: list[dict], calls: list[dict]) -> list[dict]:
    records, pending = [dict(content="", calls=[])], iter(calls)
    for event in events:
        if event["type"] == "text":
            if records[-1]["calls"]:
                records.append(dict(content="", calls=[]))
            records[-1]["content"] += event["text"]
        elif event["type"] == "tool_use":
            records[-1]["calls"].append(next(pending, dict(tool=event["name"], unlogged=True)))
    return [dict(step=i, **r) for i, r in enumerate(records, 1) if r["content"] or r["calls"]]


# Runs one agent to its answer or its budget. Returns the answer, the calls and the transcript.
def run_agent(server: Server, run: Run) -> dict:
    RUNS.mkdir(parents=True, exist_ok=True)
    log, query = RUNS / f"{run.name}.calls.jsonl", RUNS / f"{run.name}.query.md"
    log.unlink(missing_ok=True)
    query.write_text(f"{run.system}\n\n{run.task}", encoding="utf-8")
    RUN_FILE.write_text(
        json.dumps(dict(agent=run.agent, budget=run.budget, log=str(log), **run.options))
    )
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    events, sessions = [], []
    try:
        for attempt in range(NUDGES + 1):
            if attempt:
                query.write_text(NUDGE, encoding="utf-8")
            events += hermes(query, run, sessions[-1] if sessions else None)
            sessions += [e["session_id"] for e in events[-1:] if e.get("type") == "result"]
            if any(e["type"] == "tool_use" and e["name"].endswith("final_answer") for e in events):
                break
    finally:
        RUN_FILE.unlink(missing_ok=True)

    lines = (
        [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    tools, calls = (lines[0], lines[1:]) if lines else ({}, [])
    answers = [c["arguments"] for c in calls if c["tool"] == "final_answer" and not c["error"]]
    header = dict(
        agent=run.agent,
        tag=run.tag,
        started_utc=started,
        model=run.model,
        model_file=server.path.name,
        model_sha256=model_hash(server.path),
        server=server.props(),
        runner=subprocess.run(
            [HERMES, "--version"], capture_output=True, encoding="utf-8"
        ).stdout.split("\n")[0],
        hermes_sessions=sessions,
        seed=SEED,
        temperature=TEMPERATURE,
        budget=run.budget,
        system_sha256=hashlib.sha256(run.system.encode()).hexdigest(),
        task_sha256=hashlib.sha256(run.task.encode()).hexdigest(),
        tools_sha256=tools.get("tools_sha256"),
    )
    records = steps(events, calls)
    plans = [
        dict(step=r["step"], plan=plan_in(r["content"])) for r in records if plan_in(r["content"])
    ]
    status = "answered" if answers else "no answer within the budget"
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPTS / f"{run.name}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(header=header, plans=plans, status=status)) + "\n")
        for record in records:
            fh.write(json.dumps(record, default=str) + "\n")
    return dict(
        answer=answers[-1] if answers else None,
        status=status,
        steps=len(records),
        plans=plans,
        calls=calls,
        seen=[c["result"] for c in calls],
        transcript=path,
    )


# Two runs of one agent, compared call by call. Identical means repeatable, never correct.
def repeatable(first: Path, second: Path) -> dict:
    def calls(path: Path) -> list:
        lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()[1:]]
        return [
            (c["tool"], json.dumps(c.get("arguments"), sort_keys=True))
            for r in lines
            for c in r["calls"]
        ]

    a, b = calls(first), calls(second)
    same = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return dict(calls_first=len(a), calls_second=len(b), identical_prefix=same, identical=a == b)


# Settings every machine needs: our server as the model, and every tool offered directly.
SETTINGS = {
    "model.provider": "llamacpp",
    "model.base_url": f"http://127.0.0.1:{PORT}/v1",
    "model.default": "qwen",
    "tools.tool_search.enabled": "off",
    "mcp_servers.fiam.timeout": "900",
}


# Points this machine's Hermes at our tool server and model, so a teammate needs one command.
def register() -> None:
    subprocess.run([HERMES, "mcp", "remove", "fiam"], capture_output=True, stdin=subprocess.DEVNULL)
    add = [HERMES, "mcp", "add", "fiam", "--command", sys.executable, "--connect-timeout", "120"]
    add += ["--args", (ROOT / "src" / "agents" / "mcp_server.py").as_posix()]
    # Hermes asks whether to enable the tools it found; the answer is always all of them.
    subprocess.run(add, input="Y\n", text=True, check=True)
    for key, value in SETTINGS.items():
        subprocess.run([HERMES, "config", "set", key, value], check=True, stdin=subprocess.DEVNULL)
    print("Hermes is set up. Start a model with: python src/agents/harness.py serve qwen")


# Each model file against the SHA-256 the manifest pins, before any run can use it.
def verify() -> bool:
    manifest = (ROOT / "models" / "MANIFEST.txt").read_text(encoding="utf-8")
    pinned = dict(re.findall(r"file\s+(\S+\.gguf).*?sha256\s+([0-9a-f]{64})", manifest, re.S))
    ok = True
    for name, expected in pinned.items():
        path = ROOT / "models" / name
        actual = model_hash(path) if path.exists() else "missing"
        ok &= actual == expected
        print(f"  {name}: {'ok' if actual == expected else actual}")
    return ok


if __name__ == "__main__":
    if "register" in sys.argv:
        register()
        sys.exit()
    if "verify" in sys.argv:
        sys.exit(0 if verify() else 1)
    # python src/agents/harness.py serve [qwen|gemma] keeps one model up for the Hermes app.
    name = next((a for a in sys.argv[1:] if a in MODELS), "qwen")
    with Server(name) as running:
        print(f"{name} at http://127.0.0.1:{PORT}/v1, {CONTEXT:,} tokens. Ctrl+C stops it.")
        if running.process:
            running.process.wait()
