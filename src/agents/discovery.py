# Signal-discovery agent: searches 2015-2020 with real, then coded names; scored once on 2021-2026.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import harness as H

import pipeline as P

ROOT = H.ROOT
PROMPT = ROOT / "prompts" / "agents" / "discovery.md"
OUT = ROOT / "submission" / "exhibits"

# What the agent may see, and the sealed period it never sees.
DESIGN_END = "2021-01-01"
BACKTESTS = 30
MAX_TERMS = 12

# The control gets the same budget and window. The agent must beat chance, not zero.
CONTROL_DRAWS = BACKTESTS
CONTROL_TERMS = 5
SEED = 42


# The panel with every characteristic, read the way the book reads it.
def load() -> pd.DataFrame:
    return P.load_panel(extra=tuple(P.characteristics()))


# The research sandbox. Every number the agent sees comes from holding months before 2021.
class Sandbox:
    def __init__(self, panel: pd.DataFrame, anonymous: bool):
        self.names = P.characteristics()
        # Coded names are shuffled once with a fixed seed, so the code says nothing either.
        order = np.random.default_rng(SEED).permutation(len(self.names))
        codes = {self.names[i]: f"x{k:03d}" for k, i in enumerate(order)}
        self.to_real = {c: n for n, c in codes.items()} if anonymous else {n: n for n in self.names}
        self.shown = sorted(self.to_real)
        df = P.screen(panel, "2015-01-31", P.LAST_FORECAST)
        df = df.dropna(subset=["ret_exc_lead1m", "beta_60m"]).copy()
        df["holding_month"] = (df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
        self.design = df[df["holding_month"] < DESIGN_END].copy()
        self.used = 0
        self.log: list[dict] = []

    # Turns the agent's formula into real names, refusing anything outside the menu.
    def parse(self, terms: list[dict]) -> dict[str, int]:
        if not 1 <= len(terms) <= MAX_TERMS:
            raise ValueError(f"a formula needs 1 to {MAX_TERMS} terms")
        out = {}
        for term in terms:
            name, sign = term["name"], int(term["sign"])
            if name not in self.to_real or sign not in (-1, 1):
                raise ValueError(f"unknown characteristic or sign: {term}")
            out[self.to_real[name]] = sign
        return out

    # Neutralized spread of an equal-weight signed formula on the design window only.
    def spread(self, formula: dict[str, int], frame: pd.DataFrame) -> pd.Series:
        return P.spread(frame, P.neutralize(frame, P.scores(frame, formula).mean(axis=1)))

    # The menu, real names or codes depending on the run.
    def list_characteristics(self) -> dict:
        return dict(characteristics=self.shown, count=len(self.shown))

    # How complete and how related a characteristic is, before 2021 only.
    def describe(self, name: str) -> dict:
        real = self.to_real[name]
        d = self.design
        return dict(
            name=name,
            coverage=round(float(d[real].notna().mean()), 3),
            t_stat_of_spread_before_2021=round(self.t(self.spread({real: 1}, d)), 2),
        )

    # One scored formula against the budget. The log keeps the real names behind a coded run.
    def backtest(self, terms: list[dict]) -> dict:
        if self.used >= BACKTESTS:
            return dict(error="backtest budget spent; call final_answer")
        formula = self.parse(terms)
        self.used += 1
        s = self.spread(formula, self.design)
        result = dict(
            window="holding months 2015-02 to 2020-12",
            spread_ir=round(float(s.mean() / s.std() * np.sqrt(12)), 3),
            t_stat=round(self.t(s), 2),
            months=int(len(s)),
            backtests_left=BACKTESTS - self.used,
        )
        self.log.append(dict(formula=formula, **result))
        return result

    # Mean over standard error, the number a researcher would look at first.
    @staticmethod
    def t(s: pd.Series) -> float:
        return float(s.mean() / s.std() * np.sqrt(len(s))) if s.std() else 0.0


# The pick, scored once on 2021-2026 through the real book with its costs.
def sealed_score(panel: pd.DataFrame, formula: dict[str, int]) -> dict:
    # The book asks for 9 of its 12 signals. A shorter formula gets the same three-quarters.
    minimum = max(1, int(np.ceil(0.75 * len(formula))))
    return P.book_stats(P.backtest(P.build_signal(P.screen(panel), formula, minimum)))


# A random search with the agent's budget, window and scoring. The bar the agent must clear.
def control(sandbox: Sandbox, panel: pd.DataFrame) -> dict:
    rng = np.random.default_rng(SEED)
    best, best_ir = None, -np.inf
    for _ in range(CONTROL_DRAWS):
        picks = rng.choice(len(sandbox.names), size=CONTROL_TERMS, replace=False)
        formula = {sandbox.names[i]: int(rng.choice([-1, 1])) for i in picks}
        s = sandbox.spread(formula, sandbox.design)
        ir = float(s.mean() / s.std() * np.sqrt(12))
        if ir > best_ir:
            best, best_ir = formula, ir
    return dict(formula=best, design_spread_ir=best_ir, sealed=sealed_score(panel, best))


# The four tools the agent may call. Nothing reaches data after 2020 except final scoring.
def tools(sandbox: Sandbox) -> list[H.Tool]:
    term = dict(
        type="object",
        properties=dict(
            name=dict(type="string", description="a characteristic from list_characteristics"),
            sign=dict(type="integer", enum=[-1, 1], description="+1 buy high, -1 buy low"),
        ),
        required=["name", "sign"],
    )
    formula = dict(type="array", items=term, minItems=1, maxItems=MAX_TERMS)
    return [
        H.Tool(
            "list_characteristics",
            "The characteristics you may use.",
            dict(type="object", properties={}),
            lambda: sandbox.list_characteristics(),
        ),
        H.Tool(
            "describe",
            "Coverage and the before-2021 t-statistic of one characteristic on its own.",
            dict(type="object", properties=dict(name=dict(type="string")), required=["name"]),
            lambda name: sandbox.describe(name),
        ),
        H.Tool(
            "backtest",
            f"Scores an equal-weight signed formula on 2015-2020, neutralized like the book. "
            f"You have {BACKTESTS} in total.",
            dict(type="object", properties=dict(terms=formula), required=["terms"]),
            lambda terms: sandbox.backtest(terms),
        ),
        H.Tool(
            "final_answer",
            "Commit to one formula and say why it should keep working after 2020.",
            dict(
                type="object",
                properties=dict(terms=formula, hypothesis=dict(type="string")),
                required=["terms", "hypothesis"],
            ),
            lambda terms, hypothesis: dict(accepted=True, terms=len(sandbox.parse(terms))),
        ),
    ]


# The discovery tools inside the MCP server, on real or coded names as the run asks.
def session(run: dict) -> list[H.Tool]:
    return tools(Sandbox(load(), anonymous=run["anonymous"]))


def main() -> None:
    panel = load()
    system = PROMPT.read_text(encoding="utf-8")
    out = dict(
        what="An LLM agent proposes and backtests signal formulas on 2015-2020, commits to one, "
        "and the harness scores it once on 2021-2026 through the real book. Research only.",
        budget=BACKTESTS,
        runs={},
    )
    with H.Server("qwen") as server:
        for tag, anonymous in (("named", False), ("coded", True)):
            sandbox = Sandbox(panel, anonymous)
            names = "coded, so what you know about them cannot help" if anonymous else "real"
            task = (
                f"Find the formula most likely to keep predicting returns after 2020. You have "
                f"{BACKTESTS} backtests on 2015-2020. The names are {names}."
            )
            run = H.Run("discovery", "qwen", system, task, 60, tag, dict(anonymous=anonymous))
            result = H.run_agent(server, run)
            answer = result["answer"]
            pick = sandbox.parse(answer["terms"]) if answer else None
            # Every scored backtest, read back from the server's log of what the agent was shown.
            scored = [json.loads(c["result"]) for c in result["calls"] if c["tool"] == "backtest"]
            scored = [r for r in scored if "spread_ir" in r]
            out["runs"][tag] = dict(
                status=result["status"],
                steps=result["steps"],
                plan_revisions=len(result["plans"]),
                backtests_used=len(scored),
                pick=pick,
                hypothesis=answer.get("hypothesis") if answer else None,
                best_design_ir_seen=max((r["spread_ir"] for r in scored), default=None),
                sealed=sealed_score(panel, pick) if pick else None,
                transcript=result["transcript"].relative_to(ROOT).as_posix(),
            )
        out["random_search_control"] = control(Sandbox(panel, False), panel)
    book = json.loads((ROOT / "submission" / "metrics.json").read_text())
    out["shipped_book_ir"] = book["performance"]["information_ratio"]
    (OUT / "discovery.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: v for k, v in out["runs"].items()}, indent=2, default=str)[:3000])


if __name__ == "__main__":
    main()
