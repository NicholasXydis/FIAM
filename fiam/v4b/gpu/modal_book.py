# Modal runner for the Nautilus validation book (research/run_nautilus.py) on a
# large-memory CPU machine; the local 15 GB box gets reaped mid-run. The book is
# QP solves (cvxpy/clarabel) and Nautilus fills, so no GPU: the torch parts of
# the risk model (risk/enhanced.py) run on CPU here.
#
# Only v4b code goes into the image (*.py, config, the authors' E-LASSO R files
# whose hashes forecaster.verify_code checks). The private inputs live in the
# user's volume `fiam-v4b` under /repo, laid out as in the repo, and are linked
# into /root at start so every module path resolves unchanged:
#   /repo/data/{fiam_v1,finals_2026,benchmarks}/...
#   /repo/fiam/v4b/out/{elasso/gpu/volneut/run,risk}/...   (results land here too)
#   /repo/fiam/v4b/cache/risk_{factors,resid}_to_20201231.parquet
#
# Usage (from the repo root):
#   modal run fiam/v4b/gpu/modal_book.py --months 2                 (smoke: first 2 formations)
#   modal run --detach fiam/v4b/gpu/modal_book.py --steps E5        (full 2016-12..2020-11 book)
#   modal run --detach fiam/v4b/gpu/modal_book.py --steps E5 --oos  (single 2021-2026 run, D12)
#   modal volume get fiam-v4b /repo/fiam/v4b/out/nautilus_e5 fiam/v4b/out/

from pathlib import Path

import modal

app = modal.App("fiam-v4b-book")
vol = modal.Volume.from_name("fiam-v4b", create_if_missing=True)

SKIP_DIRS = {"out", "cache", "inputs", "tests", "audit", "__pycache__"}


def _skip(p: Path) -> bool:
    p = Path(p)
    if SKIP_DIRS.intersection(p.parts):
        return True
    if "config" in p.parts or ("external" in p.parts and "elasso" in p.parts) or p.suffix == ".py":
        return False
    return bool(p.suffix) or p.name.startswith(".")  # suffixless = a directory: descend


image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install_from_requirements("fiam/v4b/gpu/requirements_book.txt")
    .pip_install("torch==2.14.1", extra_index_url="https://download.pytorch.org/whl/cpu")
    .env({"PYTHONPATH": "/root"})
    .add_local_file("fiam/__init__.py", "/root/fiam/__init__.py")
    # research/stage2.py (the D18 screen's cost model) reads v4's spread ratios via fiam.paths
    .add_local_file("fiam/paths.py", "/root/fiam/paths.py")
    .add_local_file("submission/models/spreads.json", "/root/submission/models/spreads.json")
    .add_local_dir("fiam/v4b", "/root/fiam/v4b", ignore=_skip)
)


def _link():
    import os

    for local, remote in (("/root/data", "/vol/repo/data"),
                          ("/root/fiam/v4b/out", "/vol/repo/fiam/v4b/out"),
                          ("/root/fiam/v4b/cache", "/vol/repo/fiam/v4b/cache")):
        Path(remote).mkdir(parents=True, exist_ok=True)
        if not os.path.lexists(local):
            os.symlink(remote, local)


# 2017-2020 peaked at 63 GB; 2021-2026 is ~1.4x the sessions.
@app.function(image=image, volumes={"/vol": vol}, cpu=8, memory=131072, timeout=10 * 3600)
def book(steps: str = "E5", out: str = "fiam/v4b/out/nautilus_e5", months: int = 0, oos: bool = False,
         config: str = "") -> str:
    import json
    import os

    if config:  # read by engine/mandate.py at import
        os.environ["FIAM_V4B_CONFIG"] = config
    import resource
    import time

    import pandas as pd

    _link()
    os.chdir("/root")
    private = [p for p in Path("/root/fiam/v4b").rglob("*.parquet") if "out" not in p.parts and "cache" not in p.parts]
    if private:
        raise RuntimeError(f"private files baked into the image: {private[:3]}")
    from fiam.v4b.engine import ladder
    from fiam.v4b.research import run_nautilus

    if months:  # smoke: the first `months` formations only
        start = run_nautilus.OOS_WINDOW[0] if oos else ladder.WINDOW[0]
        eoms = pd.date_range(start, periods=months, freq="ME")
        if oos:
            run_nautilus.OOS_WINDOW = (eoms[0], eoms[-1])
        else:
            ladder.WINDOW = (eoms[0], eoms[-1])
    t0 = time.time()
    rep = run_nautilus.main(steps.split(","), out_dir=out, oos=oos)
    vol.commit()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    res = {"wall_s": round(time.time() - t0), "peak_rss_gb": round(peak, 1)}
    if not months:  # a smoke holds its last book to the window's end: no metrics (and no OOS peek)
        res["summary"] = {k: {x: v.get(x) for x in list(v)[:25]} for k, v in rep.items()}
    return json.dumps(res, default=str)


@app.local_entrypoint()
def main(steps: str = "E5", out: str = "", months: int = 0, oos: bool = False, config: str = ""):
    tag = steps.split(",")[0].lower() + ("_oos" if oos else "")
    out = out or ("fiam/v4b/out/modal_smoke" if months else f"fiam/v4b/out/nautilus_{tag}")
    print(book.remote(steps, out, months, oos, config))


# D18 screen (research/twostep_screen.py): one container per (score, weighting)
# variant, then one summary call. Targets and logs land in the volume under
# /repo/fiam/v4b/out/twostep_screen.
#   modal run fiam/v4b/gpu/modal_book.py::screen [--months 2]
@app.function(image=image, volumes={"/vol": vol}, cpu=4, memory=65536, timeout=4 * 3600)
def screen_variant(score: str, weighting: str, months: int = 0) -> str:
    import os
    import time

    os.environ["FIAM_V4B_CONFIG"] = "variant_betamatch.json"
    _link()
    os.chdir("/root")
    from fiam.v4b.research import twostep_screen

    t0 = time.time()
    twostep_screen.build([(score, weighting)], months)
    vol.commit()
    return f"{score}|{weighting} {time.time() - t0:.0f}s"


@app.function(image=image, volumes={"/vol": vol}, cpu=4, memory=65536, timeout=3600)
def screen_summary(months: int = 0) -> str:
    import json
    import os

    os.environ["FIAM_V4B_CONFIG"] = "variant_betamatch.json"
    _link()
    os.chdir("/root")
    vol.reload()
    from fiam.v4b.research import twostep_screen

    rep = twostep_screen.summarize(months)
    vol.commit()
    return json.dumps(rep, default=float)


@app.local_entrypoint()
def screen(months: int = 0):
    import json

    scores, weightings = ("raw", "raw_s6", "betamatch", "betamatch_s6"), ("vw", "ew")  # = twostep_screen's
    args = [(s, wt, months) for s in scores for wt in weightings]
    for msg in screen_variant.starmap(args):
        print(msg, flush=True)
    rep = json.loads(screen_summary.remote(months))
    keys = ("net", "sharpe", "vol", "beta", "long_alpha", "long_t", "short_alpha", "short_t", "cost_yr", "gross",
            "names", "pred_vol", "failed")
    for k, v in {**rep["variants"], "D17 yardstick": rep.get("yardstick_d17_e5", {})}.items():
        print(k, {x: round(v[x], 4) if isinstance(v.get(x), float) else v.get(x) for x in keys} if "net" in v else v)
    print("qualified", rep["qualified"], "pick", rep["pick"])


# D20 step A (research/beta_gates.py): beta candidates on W17..W20.
#   modal run fiam/v4b/gpu/modal_book.py::beta_gates
@app.function(image=image, volumes={"/vol": vol}, cpu=4, memory=65536, timeout=3600)
def beta_gates_run() -> str:
    import json
    import os

    os.environ["FIAM_V4B_CONFIG"] = "variant_betamatch.json"
    _link()
    os.chdir("/root")
    from fiam.v4b.research import beta_gates as bg

    rep = bg.run()
    vol.commit()
    return json.dumps(rep, default=float)


@app.local_entrypoint()
def beta_gates():
    import json

    rep = json.loads(beta_gates_run.remote())
    for k, w in rep["windows"].items():
        print(k, w["_meta"]["first"], w["_meta"]["last"], w["_meta"]["sessions"], "map", w["_meta"]["beta_map"])
        for c, v in w.items():
            if c != "_meta":
                print("  ", c, json.dumps(v))
    for c, s in rep["summary"].items():
        print(c, json.dumps(s))
    print("pick", rep["pick"])


# D19 gates (research/e6_gates.py): G0-G4 for the G0 passers in one container,
# then G5 = a Nautilus E6 smoke over W for each variant that passed G0-G4.
#   modal run fiam/v4b/gpu/modal_book.py::gates
@app.function(image=image, volumes={"/vol": vol}, cpu=4, memory=65536, timeout=3600)
def gates_g0_g4() -> str:
    import json
    import os

    os.environ["FIAM_V4B_CONFIG"] = "variant_betamatch.json"
    _link()
    os.chdir("/root")
    from fiam.v4b.research import e6_gates

    vs = [(s, wt) for s, g in e6_gates.g0().items() if g["pass"] for wt in e6_gates.WEIGHTINGS]
    rep = e6_gates.run(vs)
    vol.commit()
    return json.dumps(rep, default=float)


@app.function(image=image, volumes={"/vol": vol}, cpu=4, memory=32768, timeout=600)
def gates_g5(out: str, step: str) -> str:
    import json
    import os

    _link()
    os.chdir("/root")
    vol.reload()
    from fiam.v4b.research import e6_gates

    return json.dumps(e6_gates.g5(Path("/root") / out, step))


@app.local_entrypoint()
def gates():
    import json

    rep = json.loads(gates_g0_g4.remote())
    print("G0", {s: (round(g["t"], 2), g["pass"]) for s, g in rep["g0"].items()})
    print("G3a", {k: v for k, v in rep["g3a"].items()})
    passed = []
    for k, v in rep["variants"].items():
        print(k, json.dumps(v, default=float))
        if v["pass_g0_g4"]:
            passed.append(tuple(k.split("|")))
    runs = [(f"E6{'' if wt == 'vw' else '_ew'}", f"fiam/v4b/out/e6_g5_{s}", 0, False, f"variant_e6_{s}.json")
            for s, wt in passed]
    args = [(st, out, 2, False, cfg) for st, out, _, _, cfg in runs]
    for (st, out, *_), msg in zip(args, book.starmap(args)):
        print("G5 smoke", st, out, msg)
        print("G5", st, out, gates_g5.remote(out, st))
    print("survivors", passed if passed else "none")


# The v4b test suite on Modal (user, 2026-10-26: "only do on modal").
#   modal run fiam/v4b/gpu/modal_book.py::tests [--k twostep]
test_image = image.add_local_dir("fiam/v4b/tests", "/root/fiam/v4b/tests",
                                 ignore=lambda p: "__pycache__" in Path(p).parts)


@app.function(image=test_image, volumes={"/vol": vol}, cpu=4, memory=32768, timeout=3600)
def run_tests(k: str = "") -> str:
    import os
    import subprocess

    _link()
    os.chdir("/root")
    cmd = ["python", "-m", "pytest", "fiam/v4b/tests", "-q", "-p", "no:cacheprovider"] + (["-k", k] if k else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout[-6000:] + r.stderr[-2000:]


@app.local_entrypoint()
def tests(k: str = ""):
    print(run_tests.remote(k))
