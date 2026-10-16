# Runs an agent on a pinned local model, on any machine, and writes its transcript.

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fiam import paths

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "models"
TRANSCRIPTS = ROOT / paths.EXHIBITS / "agents"
# A rehearsal keeps its logs apart, so it never resumes into a real run.
RUNS = ROOT / "cache" / ("smoke/agents" if paths.SMOKE else "agents")

# The pinned llama.cpp build: one download per kind of machine, each checked against its SHA-256.
RELEASE = "https://github.com/ggml-org/llama.cpp/releases/download/b11132/"
BUILDS = {
    "windows": [
        (
            "llama-b11132-bin-win-vulkan-x64.zip",
            "4cc7ad18754d55badcd037a5b1a0e4e7d205e30a590be6adba9aea9851feb39e",
        )
    ],
    "windows-cpu": [
        (
            "llama-b11132-bin-win-cpu-x64.zip",
            "b13e12c2ca5f9e9d64376121d4aebb13f1b94cf912db640127b994e8e0e8c433",
        )
    ],
    "mac": [
        (
            "llama-b11132-bin-macos-arm64.tar.gz",
            "ef3d55c2d587abf31e0709906f0bef3211f57e30c5b9e59c0887b5e3d3d98b52",
        )
    ],
    "linux-cuda": [
        (
            "llama-b11132-bin-ubuntu-cuda-12.8-x64.tar.gz",
            "33639275c907a886c9a297b89b7595be91004019fe86932931c2127c783aca04",
        ),
        (
            "cudart-llama-b11132-bin-ubuntu-cuda-12.8-x64.tar.gz",
            "a9ced9f5fd38ee9b76a72e58518dec1cb7765582491703fca8eb8fc570815284",
        ),
    ],
    "linux-vulkan": [
        (
            "llama-b11132-bin-ubuntu-vulkan-x64.tar.gz",
            "f2854fbf02e158b9922969660a8b9f7119f064efcc448c3280ae61e41b3d10fc",
        )
    ],
    "linux-cpu": [
        (
            "llama-b11132-bin-ubuntu-x64.tar.gz",
            "17b5a1f5de3875b5747eba199c90cdf3c55aba465ca2cc30247a7537835e386c",
        )
    ],
}

# Two vendors for the real runs, so agreement means something; a tiny one for the rehearsal.
MODELS = {
    "qwen": (
        "unsloth/Qwen3.8-27B-GGUF",
        "Qwen3.8-27B-UD-IQ4_XS.gguf",
        "40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199",
    ),
    "gemma": (
        "unsloth/gemma-4-26B-A4B-it-GGUF",
        "gemma-4-26B-A4B-it-UD-IQ4_XS.gguf",
        "babd1e389d386352f71600765d37390f7dc993fbfad6725caccf996ffe34aecf",
    ),
    "tiny": (
        "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
    ),
}

# Repeatability, not correctness: the same prompt gives the same answer, right or wrong.
SEED, TEMPERATURE = 42, 0.0
CONTEXT, PORT = 65536, 8081
# A server elsewhere (a cloud GPU on finals day) serves instead of a local one; nothing downloads.
REMOTE = os.environ.get("FIAM_LLM_URL", "").rstrip("/")
# Qwen at 64K fits 16 GB only with a compressed cache; thinking off, so its plan is readable.
COMPRESSED = {"qwen": ("-fa", "on", "-ctk", "q8_0", "-ctv", "q4_0")}
NO_THINKING = ("--chat-template-kwargs", '{"enable_thinking": false}')
# Reading long cards in 2048-token steps cut Gemma's call from 9.0 s to 7.8 s on this GPU.
LONG_PROMPTS = ("-ub", "2048", "-b", "2048")

# Calls left when only final_answer is accepted, the cap on one tool result, and nudges allowed.
WARN_AT, RESULT_CHARS, NUDGES = 5, 6000, 2
NUDGE = "Continue: call a tool, or call final_answer with what you have."


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[..., object]


@dataclass
class Run:
    agent: str
    model: str
    system: str
    task: str
    budget: int
    tag: str = ""

    @property
    def name(self) -> str:
        return f"{self.agent}{'_' + self.tag if self.tag else ''}"


# Which build this machine takes; FIAM_LLAMA_BUILD picks another, windows-cpu say.
def machine() -> str:
    if os.environ.get("FIAM_LLAMA_BUILD"):
        return os.environ["FIAM_LLAMA_BUILD"]
    if platform.system() == "Windows":
        return "windows"
    if platform.system() == "Darwin":
        return "mac"
    if shutil.which("nvidia-smi"):
        return "linux-cuda"
    return "linux-vulkan" if shutil.which("vulkaninfo") else "linux-cpu"


# A model's name on this run: the rehearsal swaps every model for the tiny one.
def resolve(model: str) -> str:
    return "tiny" if paths.SMOKE else model


# Hashing 14 GB takes a while, so each file's hash is kept beside it, keyed on size and date.
def file_hash(path: Path) -> str:
    stamp = path.with_name(path.name + ".sha256.json")
    key = dict(bytes=path.stat().st_size, modified=path.stat().st_mtime)
    if stamp.exists() and json.loads(stamp.read_text(encoding="utf-8")).get("key") == key:
        return json.loads(stamp.read_text(encoding="utf-8"))["sha256"]
    value = paths.sha256(path)
    stamp.write_text(json.dumps(dict(key=key, sha256=value)), encoding="utf-8", newline="\n")
    return value


# Downloads once, resuming if broken, and refuses a file whose SHA-256 is not the pinned one.
def fetch(url: str, target: Path, sha256: str) -> Path:
    if target.exists() and file_hash(target) == sha256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    have = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("ab") as fh:
        total, shown = have + int(response.headers.get("Content-Length", 0)), -1
        while block := response.read(1 << 22):
            fh.write(block)
            percent = int(100 * fh.tell() / max(total, 1))
            if percent // 5 != shown // 5:
                print(f"  {target.name}: {percent}%", flush=True)
                shown = percent
    partial.replace(target)
    if file_hash(target) != sha256:
        target.unlink()
        raise RuntimeError(f"{target.name} does not match its pinned SHA-256; deleted, try again")
    return target


# The llama-server binary for this machine, downloaded and unpacked once.
def server_binary() -> Path:
    build = machine()
    home = MODELS_DIR / "llama.cpp" / build
    found = (
        [p for p in home.rglob("llama-server*") if p.suffix in ("", ".exe")]
        if home.exists()
        else []
    )
    if found:
        return found[0]
    for name, sha in BUILDS[build]:
        archive = fetch(RELEASE + name, MODELS_DIR / "downloads" / name, sha)
        if name.endswith(".zip"):
            paths.safe_unzip(archive, home)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(home, filter="tar")
    found = [p for p in home.rglob("llama-server*") if p.suffix in ("", ".exe")]
    found[0].chmod(found[0].stat().st_mode | 0o111)
    return found[0]


# The model file, downloaded once from Hugging Face and checked against its pinned SHA-256.
def model_file(model: str) -> Path:
    repo, name, sha = MODELS[model]
    target = MODELS_DIR / name
    if not target.exists():
        need = 30e9 if model != "tiny" else 1e9
        free = shutil.disk_usage(MODELS_DIR.parent).free
        if free < need:
            raise RuntimeError(
                f"{name} needs about {need / 1e9:.0f} GB free; {free / 1e9:.0f} GB free"
            )
        print(f"Downloading {name} once; the next run reuses it.", flush=True)
    return fetch(f"https://huggingface.co/{repo}/resolve/main/{name}", target, sha)


# One llama-server at the pinned settings, started and stopped around a block of runs.
class Server:
    # The model this server will load, resolved for a rehearsal.
    def __init__(self, model: str, extra: tuple = ()):
        self.name = resolve(model)
        self.path = None if REMOTE else model_file(self.name)
        self.url = REMOTE or f"http://127.0.0.1:{PORT}"
        self.process, self.extra = None, extra

    # What a running server reports about itself, or None if nothing answers.
    def props(self) -> dict | None:
        try:
            with urllib.request.urlopen(f"{self.url}/props", timeout=5) as r:
                p = json.loads(r.read())
        except OSError:
            return None
        settings = p.get("default_generation_settings", {})
        return dict(
            build=p.get("build_info"), model_path=p.get("model_path"), context=settings.get("n_ctx")
        )

    # Starts llama-server, or reuses one already serving this model.
    def __enter__(self) -> Server:
        running = self.props()
        if REMOTE and not running:
            raise RuntimeError(f"nothing answers at FIAM_LLM_URL={REMOTE}")
        if running:
            # The pinned file by name; a remote file's hash cannot be checked from here.
            if Path(running["model_path"]).name != MODELS[self.name][1]:
                raise RuntimeError(f"{self.url} serves another model; stop it first")
            return self
        binary = server_binary()
        args = [str(binary), "-m", str(self.path), "--alias", self.name, "-c", str(CONTEXT)]
        args += ["-np", "1", "--seed", str(SEED), "--temp", str(TEMPERATURE), "--jinja"]
        # Context checkpoints crash this build on Qwen's hybrid attention, so they stay off.
        args += ["-ctxcp", "0", "-cram", "0", "--host", "127.0.0.1", "--port", str(PORT)]
        args += [*COMPRESSED.get(self.name, ()), *NO_THINKING, *self.extra]
        if os.environ.get("LLAMA_DEVICE"):
            args += ["--device", os.environ["LLAMA_DEVICE"]]
        env = os.environ | {"LD_LIBRARY_PATH": str(binary.parent)}
        RUNS.mkdir(parents=True, exist_ok=True)
        log = (RUNS / f"server_{self.name}.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env)
        # Loading 14 GB into memory takes a minute or two. Poll until the server answers.
        for _ in range(900):
            if self.props():
                return self
            if self.process.poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError(f"llama-server did not start for {self.name}; see {log.name} in {RUNS}")

    # Stops the server this run started.
    def __exit__(self, *exc) -> None:
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=60)

    # One completion from the served model, with tools offered or a JSON shape required.
    def chat(
        self,
        messages: list,
        tools: list | None = None,
        schema: dict | None = None,
        temperature: float = TEMPERATURE,
        seed: int = SEED,
    ) -> dict:
        body = dict(model=self.name, messages=messages, temperature=temperature, seed=seed)
        body["max_tokens"] = 2048
        if tools:
            body["tools"] = tools
        if schema:
            body["response_format"] = dict(
                type="json_schema", json_schema=dict(name="answer", schema=schema)
            )
        request = urllib.request.Request(
            f"{self.url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=900) as r:
            return json.loads(r.read())["choices"][0]["message"]


# What a logged run ran on, written beside its log: model file and pinned hash, server build and
# settings, and each prompt file's hash, so any saved answer can be traced and replayed.
def stamp(server: Server, log: str, prompts: tuple = ()) -> None:
    props = server.props() or {}
    manifest = dict(
        model=server.name,
        model_file=MODELS[server.name][1],
        model_sha256=MODELS[server.name][2],
        build=props.get("build"),
        context=props.get("context"),
        temperature=TEMPERATURE,
        seed=SEED,
        server_args=list(server.extra),
        server="remote" if REMOTE else "local",
        prompts={Path(p).name: paths.sha256(Path(p)) for p in prompts},
        written=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    target = RUNS / f"{log}.manifest.json"
    target.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


# A plan is any numbered list the agent writes. Each new one is a revision, kept in order.
def plan_in(text: str) -> list[str]:
    return re.findall(r"^\s*\d+[.)]\s+(.+)$", text or "", flags=re.M)


# The oldest tool results are shortened when the conversation nears the context window.
def trim(messages: list) -> None:
    while sum(len(json.dumps(m)) for m in messages) / 3.5 > CONTEXT * 0.8:
        old = next(
            (m for m in messages if m["role"] == "tool" and m["content"] != "[trimmed]"), None
        )
        if old is None:
            return
        old["content"] = "[trimmed]"


# Runs one agent to its answer or its budget, and writes its transcript. No clock time is kept.
def run_agent(server: Server, run: Run, tools: list[Tool]) -> dict:
    offered = {t.name: t for t in tools}
    specs = [
        dict(
            type="function",
            function=dict(name=t.name, description=t.description, parameters=t.parameters),
        )
        for t in tools
    ]
    messages = [dict(role="system", content=run.system), dict(role="user", content=run.task)]
    records, calls, answers, used, nudges = [], [], [], 0, 0
    while used < run.budget + WARN_AT and nudges <= NUDGES and not answers:
        trim(messages)
        try:
            reply = server.chat(messages, specs)
        except urllib.error.HTTPError as exc:
            # A reply the server cannot parse, say bad JSON in a tool call, costs a nudge.
            nudges += 1
            reason = json.loads(exc.read() or b"{}").get("error", {}).get("message", str(exc))
            note = f"Your last reply could not be read: {reason[:300]}. Use valid JSON arguments."
            messages.append(dict(role="user", content=note))
            continue
        content, wanted = reply.get("content") or "", reply.get("tool_calls") or []
        messages.append(
            dict(role="assistant", content=content, tool_calls=wanted)
            if wanted
            else dict(role="assistant", content=content)
        )
        record = dict(step=len(records) + 1, content=content, calls=[])
        if not wanted:
            nudges += 1
            messages.append(dict(role="user", content=NUDGE))
        for tc in wanted:
            name, arguments = tc["function"]["name"], {}
            try:
                arguments = json.loads(tc["function"].get("arguments") or "{}")
                if name not in offered:
                    raise KeyError(f"no tool named {name}")
                # Near the end of the budget only the answer is accepted, so a run always closes.
                if run.budget - used <= WARN_AT and name != "final_answer":
                    raise RuntimeError(
                        f"{max(run.budget - used, 0)} calls left: call final_answer now"
                    )
                text, failed = json.dumps(offered[name].run(**arguments), default=str), False
            except Exception as exc:
                text, failed = json.dumps(dict(error=f"{type(exc).__name__}: {exc}")), True
            text = text[:RESULT_CHARS]
            used += 1
            call = dict(
                tool=name,
                arguments=arguments,
                result=text,
                result_sha256=hashlib.sha256(text.encode()).hexdigest(),
                error=failed,
            )
            calls.append(call)
            record["calls"].append(call)
            messages.append(dict(role="tool", tool_call_id=tc.get("id", name), content=text))
            if name == "final_answer" and not failed:
                answers.append(arguments)
        records.append(record)

    schemas = [dict(name=t.name, parameters=t.parameters) for t in tools]
    header = dict(
        agent=run.agent,
        tag=run.tag,
        model=server.name,
        model_file=MODELS[server.name][1],
        model_sha256=file_hash(server.path) if server.path else "remote, not checked",
        build=machine(),
        server=server.props(),
        seed=SEED,
        temperature=TEMPERATURE,
        budget=run.budget,
        system_sha256=hashlib.sha256(run.system.encode()).hexdigest(),
        task_sha256=hashlib.sha256(run.task.encode()).hexdigest(),
        tools_sha256=hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest(),
    )
    records = [r for r in records if r["content"] or r["calls"]]
    plans = [
        dict(step=r["step"], plan=plan_in(r["content"])) for r in records if plan_in(r["content"])
    ]
    status = "answered" if answers else "no answer within the budget"
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPTS / f"{run.name}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
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


# A reply's JSON answer, or an empty one when the model's reply was cut off or unreadable.
def parse(reply: dict) -> dict:
    try:
        answer = json.loads(reply.get("content") or "{}")
    except json.JSONDecodeError:
        return {}
    return answer if isinstance(answer, dict) else {}


# An agent's answers so far, keyed, and a way to save each new one at once, so a stop resumes.
@contextmanager
def answers(name: str, key):
    log = RUNS / f"{name}.jsonl"
    RUNS.mkdir(parents=True, exist_ok=True)
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    done = {key(row): row for row in map(json.loads, lines)}
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        # One answer to the log and to what is done, with a line every 50 so progress shows.
        def save(row: dict) -> None:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            done[key(row)] = row
            if len(done) % 50 == 0:
                print(f"  {name}: {len(done):,} answered", flush=True)

        yield done, save


# Two runs of one agent, compared call by call. Identical means repeatable, never correct.
def repeatable(first: Path, second: Path) -> dict:
    # Each call in a transcript as its tool and arguments.
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


# Downloads and checks every model and this machine's build, so a long run never waits on one.
def prepare() -> None:
    server_binary()
    for model in {resolve(m) for m in ("qwen", "gemma")}:
        model_file(model)
    print(f"ready: llama.cpp build {machine()}, models in {MODELS_DIR}")


# Every agent's tools exactly as the model sees them, for the appendix the rules ask for.
def export() -> None:
    from fiam.agents import critic

    agents = dict(critic=critic.tools(critic.Evidence()))
    out = {
        name: [dict(name=t.name, description=t.description, parameters=t.parameters) for t in tools]
        for name, tools in agents.items()
    }
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    paths.write_json(TRANSCRIPTS / "tools.json", out, rounded=False)
    print(f"tool definitions for {len(out)} agents written")


if __name__ == "__main__":
    # uv run -m fiam.agents.harness [prepare | export | serve qwen|gemma]
    if "prepare" in sys.argv:
        prepare()
        sys.exit()
    if "export" in sys.argv:
        export()
        sys.exit()
    name = next((a for a in sys.argv[1:] if a in MODELS), "qwen")
    with Server(name) as running:
        print(f"{running.name} at {running.url}/v1, {CONTEXT:,} tokens. Ctrl+C stops it.")
        if running.process:
            running.process.wait()
