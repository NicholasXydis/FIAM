# Rolling E-LASSO runs on the port (D13): same inputs as elasso/rolling.py,
# corrected C-LASSO, outputs where rolling_judge can read them
# (out/elasso/gpu/<kind>/run/forecastElasso.parquet).
# Usage: python -m fiam.v4b.gpu.rolling [--backend cpu|cuda] kind [kind ...]

import argparse
import time

import pandas as pd

from fiam.v4b.elasso import rolling
from fiam.v4b.gpu import elasso

BASE = rolling.BASE.parent / "gpu"


def run(kind: str, backend: str = "cpu") -> float:
    dest = BASE / kind
    inp = dest / "input" / "data.parquet"
    if not inp.exists():
        inp.parent.mkdir(parents=True, exist_ok=True)
        rolling.frame(kind).to_parquet(inp, index=False)
    t0 = time.time()
    elasso.write(elasso.run(pd.read_parquet(inp), backend=backend), dest / "run")
    return time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kinds", nargs="+")
    ap.add_argument("--backend", default="cpu", choices=["cpu", "cuda"])
    a = ap.parse_args()
    for k in a.kinds:
        print(k, f"{run(k, a.backend):.1f}s", flush=True)
