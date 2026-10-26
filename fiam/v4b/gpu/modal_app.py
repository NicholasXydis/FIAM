# Modal runner for the E-LASSO port. The private inputs live in the user's
# Modal volume `fiam-v4b` (uploaded with `modal volume put`), never in the image.
#
#   smoke   - one label on a GPU: CPU backend vs CUDA backend on the same input,
#             max |diff| per output and wall time of each (the CPU backend is the
#             one proven against the authors' R code, D13)
#   rolling - CUDA runs for several labels, outputs written back to the volume
#
# Upload:  modal volume put fiam-v4b out/elasso/gpu/<kind>/input/data.parquet /elasso/<kind>/data.parquet
# Run from the repo root (local paths are relative to it).
# Usage:   modal run fiam/v4b/gpu/modal_app.py --kind ret [--months 24]        (smoke)
#          modal run fiam/v4b/gpu/modal_app.py::train --kinds resrank,ret     (CUDA training)
#          modal volume get fiam-v4b /elasso/<kind>/run out/elasso/modal/<kind>/

import modal

app = modal.App("fiam-v4b-elasso")
vol = modal.Volume.from_name("fiam-v4b", create_if_missing=True)
image = (
    modal.Image.from_registry("nvidia/cuda:12.6.3-devel-ubuntu24.04", add_python="3.13")
    .pip_install("numpy==2.3.5", "pandas", "pyarrow", "numba", "numba-cuda[cu12]")  # numba-cuda needs numpy < 2.4
    .env({"PYTHONPATH": "/root"})
)
# Only the port's code goes into the image: fiam/v4b holds the private data under out/.
for f in ("fiam/__init__.py", "fiam/v4b/__init__.py", "fiam/v4b/gpu/__init__.py", "fiam/v4b/gpu/glmnet.py",
          "fiam/v4b/gpu/glmnet_cuda.py", "fiam/v4b/gpu/elasso.py"):
    image = image.add_local_file(f, f"/root/{f}")


@app.function(image=image, gpu="L4", volumes={"/data": vol}, timeout=1800)
def smoke(kind: str = "ret", months: int = 0) -> dict:
    import time

    import numpy as np
    import pandas as pd

    from fiam.v4b.gpu import elasso

    data = pd.read_parquet(f"/data/elasso/{kind}/data.parquet")
    if months:
        keep = sorted(data["date"].unique())[:months]
        data = data[data["date"].isin(keep)]
    rep = {"kind": kind, "months": int(data["date"].nunique())}
    out = {}
    for b in ("cpu", "cuda", "cuda"):  # second cuda run excludes JIT time
        t0 = time.time()
        out[b] = elasso.run(data, backend=b)
        rep[f"{b}_s"] = round(time.time() - t0, 1)
    for k, a in out["cpu"].items():
        c = out["cuda"][k]
        num = a.select_dtypes("number").columns.difference(["permno"])
        rep[k] = float(np.nanmax(np.abs(a[num].to_numpy(float) - c[num].to_numpy(float))))
    return rep


@app.function(image=image, gpu="L4", volumes={"/data": vol}, timeout=3600)
def rolling(kinds: str = "resrank") -> dict:
    import time
    from pathlib import Path

    import pandas as pd

    from fiam.v4b.gpu import elasso

    rep = {}
    for kind in kinds.split(","):
        t0 = time.time()
        elasso.write(elasso.run(pd.read_parquet(f"/data/elasso/{kind}/data.parquet"), backend="cuda"),
                     Path(f"/data/elasso/{kind}/run"))
        rep[kind] = round(time.time() - t0, 1)
    vol.commit()
    return rep


@app.local_entrypoint()
def main(kind: str = "ret", months: int = 0):
    print(smoke.remote(kind, months))


@app.local_entrypoint()
def train(kinds: str = "resrank"):
    print(rolling.remote(kinds))
