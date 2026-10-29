# python -m fiam.vfinal run [stage ...] | verify | compare [folder]

import json
import time

import pandas as pd

from fiam.vfinal import book, config, lock, unseal
from fiam.vfinal.construct import formation
from fiam.vfinal.forecast import build as forecast
from fiam.vfinal.report import fund as report
from fiam.vfinal.risk import market
from fiam.vfinal.risk import model as risk

USAGE = "uv run python -m fiam.vfinal run [--lock] [stage ...] | verify | compare [folder]"


# The base walk-forward and its rho.
def stage_forecast() -> dict:
    out = {"inputs": forecast.base_inputs(), "base": forecast.walkforward("base")}
    out["rho"] = forecast.rho()
    forecast.base_forecast()
    return out


# The el_plus extras, rows and walk-forward, then its forecast.
def stage_plus() -> dict:
    with unseal.opened():
        forecast.plus_inputs()
    out = {"plus": forecast.walkforward("plus")}
    f = forecast.plus_forecast()
    return out | {"rows": len(f), "months": int(f["eom"].nunique())}


# The risk model, the market frames and the coverage.
def stage_risk() -> dict:
    with unseal.opened():
        m = risk.build()
        formation.coverage(formation.eoms())
    return {k: list(getattr(v, "shape", ())) for k, v in m.items()}


# The mid-month fresh inputs and their el_plus forecasts.
def stage_mid() -> dict:
    with unseal.opened():
        mids = formation.mid_months(formation.eoms())
        got = forecast.mid_month(market.load()["ret"], mids)
    return {"rows": len(got), "closes": int(got["T"].nunique())}


# The core book, then the scaled book from its targets.
def stage_books() -> dict:
    with unseal.opened():
        return {name: book.run(name) for name in config.RUNS}


# Both books' scores; the book's flat run, files and finals check.
def stage_report() -> dict:
    name = config.BOOK.name
    with unseal.opened():
        res = {n: report.score(n) for n in config.RUNS}
        res["flat"] = report.flat(name)
        res["upload"] = report.upload(name)
        res["holdings"] = report.holdings_file(name)
        res["monthly"] = report.monthly_file(name)
        check = report.compliance(name)
    res["compliance"] = {"breaches": check["breaches"], "violations": check["violations"]}
    return res


STAGES = {"forecast": stage_forecast, "plus": stage_plus, "risk": stage_risk, "mid": stage_mid,
          "books": stage_books, "report": stage_report}  # fmt: skip


# Runs the stages asked (all by default), timing each; --lock locks.
def run(args: list[str]) -> dict:
    do_lock = "--lock" in args
    names = [a for a in args if a != "--lock"] or list(STAGES)
    unknown = [n for n in names if n not in STAGES]
    if unknown:
        raise SystemExit(f"unknown stage {unknown}: {list(STAGES)}")
    for folder in (config.LOGS, config.CACHE, config.FORECAST):
        folder.mkdir(parents=True, exist_ok=True)
    timing, got = {}, {}
    with lock.traced() as seen:
        for n in names:
            t0 = time.time()
            got[n] = STAGES[n]()
            timing[n] = round((time.time() - t0) / 60, 2)
            print(json.dumps({n: timing[n], "minutes": True}), flush=True)
    stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    inputs = lock.data_inputs(seen)
    body = {"stages": names, "minutes": timing, "results": got, "inputs": inputs}
    (config.LOGS / f"run_{stamp}.json").write_text(json.dumps(body, indent=1, default=str))
    if do_lock:
        lock.lock(inputs)
    return body


# The command line: run, verify or compare.
def main(argv: list[str]) -> int:
    verb, rest = (argv[0] if argv else ""), argv[1:]
    if verb == "run":
        body = run(rest)
        print(json.dumps({"minutes": body["minutes"], "inputs": len(body["inputs"])}))
        return 0
    if verb == "verify" and not rest:
        bad = lock.verify()
        print("\n".join(bad) if bad else f"{lock.rel(lock.SHA)} verifies")
        return 1 if bad else 0
    if verb == "compare" and len(rest) <= 1:
        folder = config.ROOT / rest[0] if rest else config.OUT
        changed, absent, n = lock.compare(folder)
        for line in [*changed, *(f"{a}: absent" for a in absent)]:
            print(line)
        print(f"{n - len(absent) - len([c for c in changed if 'not in the lock' not in c])} "
              f"of {n} locked outputs match in {lock.rel(folder)}")  # fmt: skip
        return 1 if changed or absent else 0
    raise SystemExit(USAGE)
