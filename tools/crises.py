# One run's last holdings replayed through the crises and scenarios.

import json
import sys
from pathlib import Path

import pandas as pd

from fiam import book as P
from fiam.exhibits import september as S
from fiam.exhibits import stress
from tools import exhibits


# The book's weights on its last day, by permno, as shares of NAV.
def last_weights(folder: Path, stem: str) -> tuple[pd.Timestamp, pd.Series]:
    daily = pd.read_parquet(folder / f"daily_{stem}.parquet")
    positions = pd.read_parquet(folder / f"positions_{stem}.parquet")
    day = positions["date"].max()
    held = positions[positions["date"] == day].groupby("permno")["value"].sum()
    return day, held / float(daily.loc[day, "nav"])


# Every crisis and scenario on one set of weights, beside the market.
def replay_all(weights: pd.Series, panel, factors: pd.DataFrame, info) -> dict:
    b = stress.loadings(weights, factors)
    out = {"loadings": b.to_dict(), "crises": {}, "scenarios": {}}
    for kind, episodes in (("crises", stress.CRISES), ("scenarios", stress.SCENARIOS)):
        for label, (first, last) in episodes.items():
            moves = factors.loc[first:last]
            row = {"market": float(moves["mktrf"].sum()), "factor_proxy": float(b @ moves.sum())}
            if panel is not None:
                row |= stress.replay(weights, panel, first, last, info)
            out[kind][label] = row
    return out | {"reverse_stress": stress.reverse_stress(b)}


# The worst and average crisis loss, from the replay where it ran.
def summary(crises: dict) -> dict:
    losses = [c["loss"] for c in crises.values() if c.get("loss") is not None]
    if not losses:
        return {"crises_replayed": 0}
    return {"crises_replayed": len(losses), "worst": min(losses),
            "mean": sum(losses) / len(losses), "best": max(losses)}  # fmt: skip


# The replay of one run, written beside its other result files.
def run(folder: Path, head: str) -> dict:
    day, weights = last_weights(folder, exhibits.stem_of(folder, head))
    panel = P.load_panel(("sic",))
    panel = panel[panel["eom"] == S.DECISION]
    info = panel.drop_duplicates("permno").set_index("permno")
    out = {"date": f"{day:%Y-%m-%d}", "names": int((weights != 0).sum()),
           "gross": float(weights.abs().sum())}  # fmt: skip
    out |= replay_all(weights, stress.episode_returns(), stress.factor_daily(), info)
    out["summary"] = summary(out["crises"])
    (folder / f"crises_{head[:12]}.json").write_text(json.dumps(out, indent=1, default=float))
    return {k: out[k] for k in ("date", "names", "gross", "summary")}


# uv run python -m tools.crises <run folder> <commit>
if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("uv run python -m tools.crises <run folder> <commit>")
    print(json.dumps(run(Path(sys.argv[1]), sys.argv[2]), indent=1, default=float))
