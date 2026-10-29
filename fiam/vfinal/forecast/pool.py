# The monthly walk-forward refits, spread over worker processes.

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from fiam.vfinal import config

_STATE: dict = {}


# Worker start: limit numba threads, load the two input files once.
def _init(work: str, threads: int) -> None:
    os.environ["NUMBA_NUM_THREADS"] = str(threads)
    import pandas as pd

    d = pd.read_parquet(Path(work) / "input.parquet")
    _STATE["data"] = d
    _STATE["dates"] = pd.to_datetime(d["date"])
    f = pd.read_parquet(Path(work) / "features.parquet")
    f["date"] = pd.to_datetime(f["date"]).astype("datetime64[ns]")
    _STATE["feats"] = f
    _STATE["parts"] = Path(work) / "refits_wf"


# One refit: fit on rows dated <= r, freeze, forecast the next block.
def fit_one(r_str: str, end_str: str) -> dict:
    import numpy as np
    import pandas as pd

    from fiam.vfinal.forecast import elasso, walkforward

    r, end = pd.Timestamp(r_str), pd.Timestamp(end_str)
    t0 = time.time()
    data, dates, feats = _STATE["data"], _STATE["dates"], _STATE["feats"]
    train = data[dates <= r]
    assert pd.to_datetime(train["date"]).max() <= r
    out = elasso.run(train)
    fw = walkforward.frozen_weights(out, r)
    rows = feats[(feats["date"] > r) & (feats["date"] <= end)]
    blk = walkforward.apply(fw, rows).assign(refit=r)
    tag, parts = f"{r:%Y%m%d}", _STATE["parts"]
    fw.to_parquet(parts / f"weights_{tag}.parquet", index=False)
    blk.to_parquet(parts / f"forecast_{tag}.parquet", index=False)
    g = fw.set_index("block").loc["gr"].drop(["intercept", "enc", "refit"]).to_numpy(float)
    return {"refit": str(r.date()), "train_months": int(train["date"].nunique()),
            "train_rows": int(len(train)), "forecast_rows": int(len(rows)),
            "selected_univariate": int((np.nan_to_num(g) != 0).sum()),
            "encompass_MaInf": float(fw.set_index("block").loc["s_MaInf", "enc"]),
            "seconds": round(time.time() - t0, 1)}  # fmt: skip


# Runs every refit not yet on disk under work/, largest fits first.
def run(work: Path, workers: int = config.WORKERS, threads: int = config.THREADS) -> dict:
    from fiam.vfinal.forecast import walkforward

    parts = work / "refits_wf"
    parts.mkdir(parents=True, exist_ok=True)
    rs = walkforward.refits()
    jobs = []
    for i, r in enumerate(rs):
        end = rs[i + 1] if i + 1 < len(rs) else walkforward.LAST_ROW
        if not (parts / f"forecast_{r:%Y%m%d}.parquet").exists():
            jobs.append((str(r.date()), str(end.date())))
    jobs.sort(reverse=True)
    t0 = time.time()
    rep = {}
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(str(work), threads)) as ex:
        futs = [ex.submit(fit_one, *j) for j in jobs]
        for f in as_completed(futs):
            x = f.result()
            rep[x["refit"]] = x
            (parts / f"report_{x['refit']}.json").write_text(json.dumps(x))
    return {"refits": len(jobs), "wall_seconds": round(time.time() - t0, 1)}
