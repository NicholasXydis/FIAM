# Three tests that try to break the strategy. Writes exhibits/placebo_lab.json.

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

OUT = Path("submission/exhibits")

# 200 runs, which places our result to half a percent. Finer than we ever claim.
DRAWS = 200

# Fixed, so anyone re-running this gets the same 200 shuffles we did.
RNG_SEED = 20260921

# Each worker loads the universe once, so only the shuffled scores cross between processes.
WORKER_UNIVERSE: pd.DataFrame | None = None


# One summary for any book, so the tests and the real thing are described the same way.
def summarise(book: pd.DataFrame) -> dict:
    return dict(
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(book["net"].mean() * 12),
        net_ir=P.information_ratio(book["net"]),
        gross_ir=P.information_ratio(book["gross"]),
        turnover=float(book["turnover"].mean()),
        months=int(len(book)),
    )


# Shuffles within sector and liquidity only, so the constraints keep something to act on.
def permute(universe: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    buckets = universe.groupby("eom")["dolvol_126d"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop")
    )
    key = [universe["eom"], universe["sector"], buckets.fillna(-1)]
    return universe.groupby(key, observed=True)["signal"].transform(
        lambda s: s.to_numpy()[rng.permutation(len(s))]
    )


# Loads the shared universe into a worker process before it takes any shuffle.
def start_worker() -> None:
    global WORKER_UNIVERSE
    WORKER_UNIVERSE = P.universe()


# One shuffled book: net IR, gross a year, turnover. Gross is the fair test, costs still churn.
def null_book(signal: np.ndarray) -> tuple[float, float, float]:
    book = P.backtest(WORKER_UNIVERSE.assign(signal=signal))
    return P.information_ratio(book["net"]), book["gross"].mean() * 12, book["turnover"].mean()


def main() -> None:
    universe = P.universe()
    rng = np.random.default_rng(RNG_SEED)

    shipped_book = P.backtest(universe)
    real = summarise(shipped_book)
    print(f"shipped book: net IR {real['net_ir']:+.3f}, net {real['net_annual'] * 100:+.1f}%/yr")

    # Test 1, the shuffle. Drawn in order from one generator, then run in parallel.
    shuffles = [permute(universe, rng).to_numpy() for _ in range(DRAWS)]
    workers = min(8, os.cpu_count() or 1)
    with ProcessPoolExecutor(workers, initializer=start_worker) as pool:
        results = list(pool.map(null_book, shuffles, chunksize=5))
    null, gross, null_turnover = (np.array(column, dtype=float) for column in zip(*results))
    print(f"  {DRAWS} shuffles: gross {gross.mean():+.2%}/yr, net IR {null.mean():+.3f}")
    # Where our result lands among the 200. Not near the top would be a finding.
    percentile = float((null < real["net_ir"]).mean() * 100)

    # Test 2, flip the sign. Should lose about what we make, not land near zero.
    inverted = summarise(P.backtest(universe.assign(signal=-universe["signal"])))
    print(
        f"inverted: gross {inverted['gross_annual'] * 100:+.1f}%/yr, "
        f"net IR {inverted['net_ir']:+.2f}"
    )

    # Test 3, last month's ranking traded this month. Shifted on the calendar, not by row.
    lagged = universe.copy()
    lagged["prev_eom"] = lagged["eom"] - pd.offsets.MonthEnd(1)
    stale_scores = lagged[["permno", "eom", "signal"]].rename(
        columns={"eom": "prev_eom", "signal": "stale"}
    )
    lagged = lagged.merge(stale_scores, on=["permno", "prev_eom"], how="left")
    stale = summarise(
        P.backtest(lagged.dropna(subset=["stale"]).assign(signal=lambda d: d["stale"]))
    )
    print(f"stale scores: net IR {stale['net_ir']:+.2f}")

    out = dict(
        what="Three controls, each a different question. Named separately because they "
        "predict different things: only the permutation null should centre on zero.",
        draws=DRAWS,
        rng_seed=RNG_SEED,
        code=P.source_fingerprint(),
        shipped=real,
        permutation_null=dict(
            expectation="gross return centres near zero; net IR does not, because a random "
            "ranking churns the book and pays real costs to do it",
            gross_annual_mean=float(gross.mean()),
            gross_annual_std=float(gross.std()),
            gross_annual_p5=float(np.percentile(gross, 5)),
            gross_annual_p95=float(np.percentile(gross, 95)),
            turnover_mean=float(np.mean(null_turnover)),
            shipped_gross_annual=real["gross_annual"],
            mean=float(null.mean()),
            median=float(np.median(null)),
            std=float(null.std()),
            p5=float(np.percentile(null, 5)),
            p95=float(np.percentile(null, 95)),
            min=float(null.min()),
            max=float(null.max()),
            shipped_percentile=percentile,
            shipped_beats_p95=bool(real["net_ir"] > np.percentile(null, 95)),
            shipped_gross_beats_p95=bool(real["gross_annual"] > np.percentile(gross, 95)),
            draws=int(len(null)),
            all_irs=[float(x) for x in null],
            all_gross=[float(x) for x in gross],
        ),
        inversion=dict(
            expectation="gross near minus the baseline gross, never near zero",
            baseline_gross_annual=real["gross_annual"],
            **inverted,
        ),
        stale_scores=dict(
            expectation="degraded, not necessarily zero",
            baseline_net_ir=real["net_ir"],
            # No prior score in month one, so this is 67 months and so is the baseline.
            baseline_net_ir_matched=P.information_ratio(shipped_book["net"].iloc[1:]),
            **stale,
        ),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "placebo_lab.json").write_text(json.dumps(out, indent=2))
    print(
        f"\nnull mean {null.mean():+.3f} (sd {null.std():.3f}), "
        f"shipped at the {percentile:.1f}th percentile"
    )


if __name__ == "__main__":
    main()
