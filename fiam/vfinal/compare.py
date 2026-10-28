# A rerun's headline outputs against the locked run, file by file.

import json
import pickle
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import lock

ROOT = lock.ROOT
# JSON keys that name a time, a commit or a path, never a result.
IGNORED = {"commit", "run_utc", "made_at", "headline", "path", "folder"}
# Rows listed for each table that differs.
SHOWN = 5


# A commit's full name from git, or the name as given.
def resolve(commit: str, root: Path = ROOT) -> str:
    got = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return got.stdout.strip() if got.returncode == 0 else commit


# Two tables: equal, else each column's largest gap and the rows.
def tables(a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    if a.shape == b.shape and list(a.columns) == list(b.columns) and a.equals(b):
        return []
    if list(a.columns) != list(b.columns):
        return [f"columns differ: {list(a.columns)} vs {list(b.columns)}"]
    out = []
    if len(a) != len(b):
        out.append(f"rows {len(a)} locked, {len(b)} rerun")
    n = min(len(a), len(b))
    a, b = a.iloc[:n], b.iloc[:n]
    if not a.index.equals(b.index):
        out.append("the row labels differ")
    rows = np.zeros(n, dtype=bool)
    for col in a.columns:
        x, y = a[col].to_numpy(), b[col].to_numpy()
        if pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
            x, y = x.astype(float), y.astype(float)
            both = np.isnan(x) & np.isnan(y)
            off = ~both & ~(x == y)
            if off.any():
                gap = np.abs(x - y)[off]
                worst = np.nanmax(gap) if np.isfinite(gap).any() else np.inf
                out.append(f"{col}: {off.sum()} rows differ, largest gap {worst:.6g}")
        else:
            off = ~(pd.Series(x).astype(str).to_numpy() == pd.Series(y).astype(str).to_numpy())
            if off.any():
                out.append(f"{col}: {off.sum()} rows differ")
        rows |= off
    if rows.any():
        labels = [str(i) for i in a.index[rows][:SHOWN]]
        out.append(f"{rows.sum()} rows differ, first {', '.join(labels)}")
    return out or ["equal values, different types or layout"]


# A JSON value with times, commits and paths left out, commits masked.
def scrub(value, names: tuple[str, ...]):
    if isinstance(value, dict):
        return {k: scrub(v, names) for k, v in value.items() if k not in IGNORED}
    if isinstance(value, list):
        return [scrub(v, names) for v in value]
    if isinstance(value, str):
        for name in names:
            value = value.replace(name, "<commit>")
    return value


# Every path where two JSON values differ, with both values.
def walk(a, b, at: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{at}/{k}: only in the {'rerun' if k in b else 'locked run'}")
            else:
                out += walk(a[k], b[k], f"{at}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in walk(x, y, f"{at}/{i}")]
    return [] if a == b else [f"{at or '/'}: {a!r} vs {b!r}"]


# Two objects the same in content: tables, arrays, maps and lists.
def same(a, b) -> bool:
    if isinstance(a, (pd.DataFrame, pd.Series)):
        return type(a) is type(b) and a.equals(b)
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    return bool(a == b)


# One pair of files by content; the gaps found, none when the same.
def files(a: Path, b: Path, names: tuple[str, ...]) -> list[str]:
    if not b.is_file():
        return ["missing in the rerun"]
    if a.read_bytes() == b.read_bytes():
        return []
    if a.suffix == ".parquet":
        return tables(pd.read_parquet(a), pd.read_parquet(b))
    if a.suffix == ".csv":
        return tables(pd.read_csv(a), pd.read_csv(b))
    if a.suffix == ".json":
        x, y = (scrub(json.loads(p.read_text()), names) for p in (a, b))
        return walk(x, y)
    if a.suffix == ".pkl":
        return pickles(a, b, names)
    return ["the bytes differ"]


# Two pickles: the same bytes once commit names are masked, else loaded.
def pickles(a: Path, b: Path, names: tuple[str, ...]) -> list[str]:
    x, y = a.read_bytes(), b.read_bytes()
    for name in names:
        x, y = (z.replace(name.encode(), b"#" * len(name)) for z in (x, y))
    if x == y:
        return []
    try:
        with a.open("rb") as fa, b.open("rb") as fb:
            loaded = same(pickle.load(fa), pickle.load(fb))
    except Exception as err:
        return [f"the bytes differ, and they do not load here ({type(err).__name__})"]
    return [] if loaded else ["the pickled plans differ"]


# The locked headline cell of row 23 and the rerun's, if both exist.
def ir_cells(pairs: dict) -> tuple[str, str] | None:
    hit = [(a, b) for a, b in pairs.values() if a.name.startswith("table_9_1_") and b.is_file()]
    if not hit:
        return None
    a, b = (pd.read_csv(p).set_index("row").loc[23, "strategy"] for p in hit[0])
    return a, b


# The gap summary: positions, NAV and the net IR.
def summary(pairs: dict) -> list[str]:
    out = []
    for stem, what in (("positions_7_", "positions"), ("daily_7_", "NAV")):
        hit = [(a, b) for a, b in pairs.values() if a.name.startswith(stem)]
        if not hit or not hit[0][1].is_file():
            out.append(f"  {what}: no rerun file")
            continue
        a, b = (pd.read_parquet(p) for p in hit[0])
        if stem == "daily_7_":
            gap = (a["nav"] - b["nav"].reindex(a.index)).abs().max()
            ends = f"ending {a['nav'].iloc[-1]:,.2f} locked, {b['nav'].iloc[-1]:,.2f} rerun"
            out.append(f"  NAV: largest daily gap ${gap:,.2f}; {ends}")
        else:
            keys = ["date", "permno"]
            both = a.merge(b, on=keys, how="outer", suffixes=("_a", "_b"), indicator=True)
            only = int((both["_merge"] != "both").sum())
            gap = (both["value_a"] - both["value_b"]).abs().max()
            out.append(f"  positions: {only} rows in one run only, largest value gap ${gap:,.2f}")
    cells = ir_cells(pairs)
    ir = [c.split(";")[0] for c in cells] if cells else None
    out.append(f"  IR net: {ir[0]} locked, {ir[1]} rerun" if ir else "  IR net: no table")
    return out


# Compares the rerun at a commit with the locked run; 1 if they differ.
def compare(commit: str = "HEAD", root: Path = ROOT, record: Path = lock.OUTPUTS) -> int:
    locked = json.loads(record.read_text())
    full = resolve(commit, root)
    base, at = locked["run_at"], full[:12]
    # Longer names first, so a full commit is masked whole.
    names = tuple(sorted({base, resolve(base, root), at, full}, key=len, reverse=True))
    print(f"Rerun {at} against the locked run {base}, {len(locked['files'])} files")
    pairs, gaps = {}, 0
    for name in sorted(locked["files"]):
        a = root / name
        b = a.with_name(a.name.replace(f"_{base}", f"_{at}"))
        pairs[name] = (a, b)
        found = files(a, b, names) if a.is_file() else ["the locked file is not here"]
        gaps += bool(found)
        print(f"  {'same   ' if not found else 'differs'} {name.replace(base, '<at>')}")
        for line in found[:8]:
            print(f"            {line}")
    if not gaps:
        print("identical")
        return 0
    print(f"{gaps} of {len(pairs)} files differ. Gap summary:")
    print("\n".join(summary(pairs)))
    return 1
