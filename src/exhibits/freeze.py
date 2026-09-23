# Pins the baseline the research exhibits are measured against, and their pass marks.

import hashlib
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipeline as P

DATA = Path("data")
OUT = Path("submission/exhibits")

# One pass mark per exhibit, written here instead of decided once we saw the answer.
ACCEPTANCE = {
    "nn3_seeds": "Reporting only. Report every seed, never average them into a model.",
    "constraint_survival": "Descriptive, no pass mark. Universe, months and parameters fixed.",
    "permutation_null": "Shipped result above the null's 95th percentile, null gross near zero.",
    "inversion": "Gross lands near minus the baseline gross, not near zero.",
    "stale_scores": "Degraded, but not necessarily to zero.",
}

# Rules we got wrong. Kept, because swapping one after a failed result is the sin here.
AMENDMENTS = {
    "permutation_null": {
        "original": "The null's net IR should centre near zero.",
        "why_wrong": "A shuffled ranking re-sorts the book monthly, so it churns at about "
        "179% turnover and pays our real cost rates. Its net IR centres near -2.",
        "now": "Tested on gross return, which is the only place a null can be zero.",
    },
}


# Hashes the data too. Knowing which code ran says nothing about what it ran on.
def data_hashes() -> dict:
    out = {}
    for path in sorted(DATA.rglob("*")):
        if not path.is_file() or path.suffix not in {".parquet", ".csv", ".zip"}:
            continue
        digest = hashlib.sha256()
        # Chunked, the panel is too large to hold twice in memory.
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        out[path.as_posix()] = dict(sha256=digest.hexdigest()[:16], bytes=path.stat().st_size)
    return out


def main() -> None:
    metrics = json.loads(Path("submission/metrics.json").read_text())
    perf, comp = metrics["performance"], metrics["compliance"]
    frozen = dict(
        what="The baseline the pre-WRDS research exhibits are measured against.",
        code=P.source_fingerprint(),
        data=data_hashes(),
        environment=dict(
            python=platform.python_version(),
            platform=platform.platform(),
            requirements_sha256=hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest()[
                :16
            ],
        ),
        baseline=dict(
            information_ratio=perf["information_ratio"],
            sharpe_ratio=perf["sharpe_ratio"],
            return_gross_annual=perf["return_gross_annual"],
            return_net_annual=perf["return_net_annual"],
            max_drawdown_total=perf["max_drawdown_total"],
            beta_realized=perf["beta_realized"],
            turnover_monthly_one_way=metrics["costs"]["turnover_monthly_one_way"],
            positions_average=comp["positions_average"],
        ),
        # Whole-share rounding happens after the optimizer. This is how far it pushes.
        rounding_drift=dict(
            net_exposure_max_abs=comp["net_exposure_max_abs"],
            sector_tilt_max=comp["sector_tilt_max"],
            position_weight_max=comp["position_weight_max"],
        ),
        acceptance_rules=ACCEPTANCE,
        amended_rules=AMENDMENTS,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "freeze.json").write_text(json.dumps(frozen, indent=2))
    print(f"frozen at src {frozen['code']['src_sha256']}, IR {perf['information_ratio']:.6f}")
    print(f"{len(frozen['data'])} data files hashed")


if __name__ == "__main__":
    main()
