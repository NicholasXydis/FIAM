# Compares an out/ run with the committed official results, per number.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam import data, paths

OFFICIAL = Path("frozen") / "v1" / "submission"

# Keys that name the code behind a result rather than the result itself.
RUN_DETAILS = {"run", "code", "code_sha256"}

# Rewritten each run or only by agents, so never a result to compare.
SKIP = {"run_manifest.json", "reproducibility.json"}


# Every number in a JSON document by its path, run details left out.
def numbers(data, prefix: str = "") -> dict[str, float]:
    if isinstance(data, dict):
        items = ((k, v) for k, v in data.items() if k not in RUN_DETAILS)
    elif isinstance(data, list):
        items = ((str(i), v) for i, v in enumerate(data))
    else:
        is_number = isinstance(data, (int, float)) and not isinstance(data, bool)
        return {prefix: float(data)} if is_number else {}
    out = {}
    for key, value in items:
        out |= numbers(value, f"{prefix}.{key}" if prefix else key)
    return out


# Largest array gap. Missing on both sides agrees; on one, it does not.
def gap(a: np.ndarray, b: np.ndarray) -> float:
    if (np.isnan(a) != np.isnan(b)).any():
        return float("inf")
    both = ~np.isnan(a)
    return float(np.abs(a[both] - b[both]).max(initial=0.0))


# Two files' largest gap and where it is, or None if not comparable.
def difference(ours: Path, theirs: Path) -> tuple[float, str] | None:
    if ours.suffix == ".json":
        a = numbers(json.loads(ours.read_text(encoding="utf-8")))
        b = numbers(json.loads(theirs.read_text(encoding="utf-8")))
        if a.keys() != b.keys():
            return None
        gaps = {k: gap(np.array([a[k]]), np.array([b[k]])) for k in a}
    else:
        a, b = pd.read_csv(ours), pd.read_csv(theirs)
        if list(a.columns) != list(b.columns) or len(a) != len(b):
            return None
        gaps = {}
        for column in a.columns:
            if pd.api.types.is_numeric_dtype(a[column]) and pd.api.types.is_numeric_dtype(
                b[column]
            ):
                gaps[column] = gap(a[column].to_numpy(float), b[column].to_numpy(float))
            else:
                same = a[column].fillna("").astype(str).eq(b[column].fillna("").astype(str))
                gaps[column] = 0.0 if same.all() else float("inf")
    if not gaps:
        return 0.0, ""
    key = max(gaps, key=gaps.get)
    return gaps[key], key


# The headline numbers, from metrics.json.
HEADLINE = [
    ("performance", "information_ratio", "IR vs T-bill + 4%", "{:.3f}"),
    ("performance", "return_net_annual", "net return a year", "{:.1%}"),
    ("performance", "sharpe_ratio", "Sharpe", "{:.2f}"),
    ("performance", "beta_realized", "beta to the S&P 500", "{:+.3f}"),
    ("performance", "max_drawdown_total", "max drawdown", "{:.1%}"),
    ("costs", "turnover_monthly_one_way", "turnover a month", "{:.1%}"),
    ("compliance", "positions_average", "positions", "{:.0f}"),
]


# The largest gap between two files, in words.
def verdict(gap: float) -> str:
    if gap == 0:
        return "identical"
    if gap < 5e-7:
        return "same to 6 decimals"
    if gap < 5e-5:
        return "same to 4 decimals"
    return "differs"


# The headline side by side, then each result file against the official.
def main() -> int:
    if paths.OUT_ROOT.resolve() == Path(".").resolve():
        print("Official run: nothing to compare with.")
        return 0
    ours = paths.read_json(paths.METRICS)
    theirs = json.loads((OFFICIAL / "metrics.json").read_text(encoding="utf-8"))
    print(f"{'':24}{'this run':>12}{'official':>12}")
    for section, key, label, fmt in HEADLINE:
        a, b = fmt.format(ours[section][key]), fmt.format(theirs[section][key])
        print(f"{label:24}{a:>12}{b:>12}")

    names = [p.relative_to(OFFICIAL) for p in sorted(OFFICIAL.rglob("*")) if p.is_file()]
    names = [n for n in names if n.suffix in {".csv", ".json"} and n.name not in SKIP]
    names = [n for n in names if "agents" not in n.parts and (paths.SUBMISSION / n).exists()]
    verdicts = {}
    for name in names:
        found = difference(paths.SUBMISSION / name, OFFICIAL / name)
        verdicts[name.as_posix()] = "differs" if found is None else verdict(found[0])
    book = [verdicts.get(n) for n in ("holdings.csv", "returns.csv", "metrics.json")]
    differ = sorted(n for n, v in verdicts.items() if v == "differs")
    same = len(verdicts) - len(differ)

    print(
        f"\n{same} of {len(verdicts)} result files match the official ones to 4 decimals or better."
    )
    if differ:
        print("Differ: " + ", ".join(differ))
    if all(v != "differs" for v in book):
        print("The submitted book reproduces.")
    elif paths.SMOKE:
        print("A rehearsal trains small models on a slice, so its book is not the official one.")
    elif data.wrds("exits") is None:
        print("Without WRDS the book moves in the third decimal.")
    else:
        print("The book differs from the official one. Check the code and data versions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
