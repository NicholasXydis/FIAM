# Three tests that try to break the strategy. Writes exhibits/placebo_lab.json.

from __future__ import annotations

import json
import sys
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


# IR against T-bill plus 4%. The T-bill cancels, so only the 4% comes off.
def information_ratio(net: pd.Series) -> float:
    active = net - 0.04 / 12
    return float(active.mean() / active.std() * np.sqrt(12)) if active.std() else 0.0


# Runs the real book on whatever is in the signal column. Each test is a different score.
def run(universe: pd.DataFrame) -> pd.DataFrame:
    rows, previous, previous_spreads = [], None, None
    for month in sorted(universe["eom"].unique()):
        cross = universe[universe["eom"] == month]
        weights = P.optimize_month(cross, previous)
        if weights is None or not len(weights):
            continue
        info = cross.set_index("permno").loc[weights.index]
        weights = P.to_whole_shares(weights, info["prc"].abs())
        if not len(weights):
            continue
        info = info.loc[weights.index]
        spreads = cross.set_index("permno")["bidaskhl_21d"]
        cost, turnover = P.trading_cost(weights, previous, info, spreads, previous_spreads)
        gross = float((weights * info["ret_exc_lead1m"].fillna(0.0)).sum())
        rows.append(dict(gross=gross, cost=cost, net=gross - cost, turnover=turnover))
        previous, previous_spreads = weights, spreads
    return pd.DataFrame(rows)


# One summary for any book, so the tests and the real thing are described the same way.
def summarise(book: pd.DataFrame) -> dict:
    return dict(
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(book["net"].mean() * 12),
        net_ir=information_ratio(book["net"]),
        gross_ir=information_ratio(book["gross"]),
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


def main() -> None:
    panel = P.load_panel()
    universe = P.build_signal(P.screen(panel))
    rng = np.random.default_rng(RNG_SEED)

    shipped_book = run(universe)
    real = summarise(shipped_book)
    print(f"shipped book: net IR {real['net_ir']:+.3f}, net {real['net_annual'] * 100:+.1f}%/yr")

    # Test 1, the shuffle. Cuts score from return. This one should come out near zero.
    null_irs, null_gross, null_turnover = [], [], []
    for draw in range(DRAWS):
        shuffled = universe.assign(signal=permute(universe, rng))
        book = run(shuffled)
        null_irs.append(information_ratio(book["net"]))
        # Gross is the fair test. After costs it cannot be zero, a shuffle still churns.
        null_gross.append(float(book["gross"].mean() * 12))
        null_turnover.append(float(book["turnover"].mean()))
        if (draw + 1) % 25 == 0:
            print(
                f"  permutation {draw + 1}/{DRAWS}, gross {np.mean(null_gross) * 100:+.2f}%/yr, "
                f"net IR {np.mean(null_irs):+.3f}"
            )
    null = np.array(null_irs)
    gross = np.array(null_gross)
    # Where our result lands among the 200. Not near the top would be a finding.
    percentile = float((null < real["net_ir"]).mean() * 100)

    # Test 2, flip the sign. Should lose about what we make, not land near zero.
    inverted = summarise(run(universe.assign(signal=-universe["signal"])))
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
    stale = summarise(run(lagged.dropna(subset=["stale"]).assign(signal=lambda d: d["stale"])))
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
            baseline_net_ir_matched=information_ratio(shipped_book["net"].iloc[1:]),
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
