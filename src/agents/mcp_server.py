# Serves the agents' read-only tools to Hermes over MCP stdio; in a scored run, logs every call.

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import auditor
import critic
import discovery
import harness as H

# The protocol revision we answer with when the client does not name one.
PROTOCOL = "2025-06-18"

# Each agent's tools for a scored run, built from the options the harness wrote.
SESSIONS = {"discovery": discovery.session, "critic": critic.session, "auditor": auditor.session}


# Builds its object on first use, so Hermes can list the tools before the panel is loaded.
class Lazy:
    def __init__(self, build):
        self._build, self._value = build, None

    def __getattr__(self, name: str):
        if self._value is None:
            self._value = self._build()
        return getattr(self._value, name)


# One agent's tools plus final_answer in a scored run, or every read-only tool for research.
class Toolbox:
    def __init__(self):
        self.run = json.loads(H.RUN_FILE.read_text()) if H.RUN_FILE.exists() else None
        if self.run:
            tools = SESSIONS[self.run["agent"]](self.run)
        else:
            sandbox = Lazy(lambda: discovery.Sandbox(discovery.load(), anonymous=False))
            tools = discovery.tools(sandbox) + critic.tools(critic.Evidence())
            tools += auditor.tools(auditor.Repo(H.ROOT / "src"))
            tools = [t for t in tools if t.name != "final_answer"]
        self.tools, self.used = {t.name: t for t in tools}, 0
        if self.run:
            schemas = [dict(name=t.name, parameters=t.parameters) for t in tools]
            digest = hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest()
            self.write(dict(tools=list(self.tools), tools_sha256=digest))

    def write(self, record: dict) -> None:
        with open(self.run["log"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    # Runs one tool. A failure goes back to the model as an error result, never up the stack.
    def call(self, name: str, arguments: dict) -> dict:
        left = self.run["budget"] - self.used if self.run else None
        try:
            if name not in self.tools:
                raise KeyError(f"no tool named {name}")
            # Near the end of the budget only the answer is accepted, so a run always closes.
            if left is not None and left <= H.WARN_AT and name != "final_answer":
                raise RuntimeError(f"{max(left, 0)} calls left: call final_answer now")
            text, failed = json.dumps(self.tools[name].run(**arguments), default=str), False
        except Exception as exc:
            text, failed = json.dumps(dict(error=f"{type(exc).__name__}: {exc}")), True
        text = text[: H.RESULT_CHARS]
        if self.run:
            self.used += 1
            digest = hashlib.sha256(text.encode()).hexdigest()
            self.write(
                dict(
                    tool=name, arguments=arguments, result=text, result_sha256=digest, error=failed
                )
            )
        return dict(content=[dict(type="text", text=text)], isError=failed)

    def listing(self) -> list[dict]:
        return [
            dict(
                name=t.name,
                description=t.description,
                inputSchema=t.parameters,
                annotations=dict(readOnlyHint=True),
            )
            for t in self.tools.values()
        ]


# One JSON-RPC request in, one response out. Notifications carry no id and get no reply.
def respond(message: dict, box: Toolbox) -> dict | None:
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params") or {}
    if method == "initialize":
        result = dict(
            protocolVersion=params.get("protocolVersion", PROTOCOL),
            capabilities=dict(tools={}),
            serverInfo=dict(name="fiam", version="2"),
        )
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = dict(tools=box.listing())
    elif method == "tools/call":
        result = box.call(params.get("name"), params.get("arguments") or {})
    else:
        error = dict(code=-32601, message=f"method not found: {method}")
        return dict(jsonrpc="2.0", id=message["id"], error=error)
    return dict(jsonrpc="2.0", id=message["id"], result=result)


# Every agent's tools exactly as the model sees them, for the appendix the rules ask for.
def export() -> None:
    sandbox = Lazy(lambda: discovery.Sandbox(discovery.load(), anonymous=False))
    agents = dict(
        discovery=discovery.tools(sandbox),
        critic=critic.tools(critic.Evidence()),
        auditor=auditor.tools(auditor.Repo(H.ROOT / "src")),
    )
    out = {
        name: [dict(name=t.name, description=t.description, parameters=t.parameters) for t in tools]
        for name, tools in agents.items()
    }
    H.TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    (H.TRANSCRIPTS / "tools.json").write_text(json.dumps(out, indent=2))
    print(f"tool definitions for {len(out)} agents written")


def main() -> None:
    # The tools read data/ and submission/ by relative path, like every script here.
    os.chdir(H.ROOT)
    if "--export" in sys.argv:
        export()
        return
    # stdout carries the protocol, so anything a tool prints is sent to stderr instead.
    channel, sys.stdout = sys.stdout.buffer, sys.stderr
    box = Toolbox()
    for line in sys.stdin.buffer:
        if line.strip():
            reply = respond(json.loads(line), box)
            if reply is not None:
                channel.write(json.dumps(reply).encode() + b"\n")
                channel.flush()


if __name__ == "__main__":
    main()
