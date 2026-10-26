# The strategy's forecaster (DECISIONS.md D6): E-LASSO, read for the engine.
#
# The engine reads expected returns only through this module. Forecasts come from
# the authors' unchanged R code (external/elasso/, run by run_elasso.R); a month's
# forecast is keyed by its formation eom (the characteristics month) and permno.
#
# Raw forecasts carry a large market-level intercept (monthly medians swing
# several percent against ~0.5% cross-sectional dispersion). A dollar-neutral
# book earns only the dispersion, so the engine-facing forecast is centred
# (median subtracted within eom, R§3) and multiplied by the frozen centred
# calibration scale from elasso/freeze.py or elasso/tail.py (the run directory's frozen.json, copied
# into config). Horizon conversion uses the frozen decay rate kappa:
# a 21-session forecast held `hold` sessions starting `age` sessions after
# formation keeps the share exp(-k*age)*(1-exp(-k*hold))/(1-exp(-21*k)).
#
# Formations before BURNIN_BEFORE average fewer than 21 monthly regressions
# (MaInf is then close to Ma1 and unstable month to month). They may warm up
# holdings but must not be judged as validation evidence.

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine.mandate import Final
from fiam.v4b.engine.mandate import load as load_mandate

V4B = Path(__file__).resolve().parents[1]
# The frozen-coefficient-era run (D6/D7); the engine reads policy.forecaster_run.
RUN = V4B / "out" / "elasso" / "run"
SOURCES = {"Elasso": "forecastElasso", "Slasso": "forecastSlasso"}
# Sessions in the forecast's own horizon (one month of trading days).
REFERENCE_DAYS = 21
# First formation eom with a full averaging history (the judge window).
BURNIN_BEFORE = pd.Timestamp("2016-12-31")


# Fails unless the pristine authors' files match their recorded checksums.
def verify_code() -> None:
    import hashlib

    root = Path(__file__).resolve().parents[1] / "external" / "elasso"
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        got = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if got != digest:
            raise AssertionError(f"E-LASSO code changed: {name}")


# The run directory the mandate names (D12: the rolling tail run).
def run_dir(m: Final | None = None) -> Path:
    m = m or load_mandate()
    return V4B / m.policy.forecaster_run


# Expected next-month excess returns (decimal) for one column, by eom and permno.
def expected_returns(
    m: Final | None = None, column: str | None = None, source: Path | None = None
) -> pd.DataFrame:
    m = m or load_mandate()
    column = column or m.policy.forecaster_column
    family, window = column.split("_", 1)
    path = source or (run_dir(m) / f"{SOURCES[family]}.parquet")
    f = pd.read_parquet(path, columns=["date", "permno", window])
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    # The code works in percent per month; the engine works in decimals.
    f["mu"] = f[window] / 100.0
    return f[["eom", "permno", "mu"]].dropna().sort_values(["eom", "permno"], ignore_index=True)


# The frozen calibration scale for a column (alternate gets its own).
def scale_for(m: Final, column: str) -> float:
    if column == m.policy.forecaster_column:
        return m.policy.forecaster_scale
    if column == m.policy.forecaster_alternate:
        return m.policy.forecaster_alternate_scale
    raise ValueError(f"no frozen calibration scale for {column!r}")


# The frozen decay rate kappa (per session) for a column.
def kappa_for(m: Final, column: str) -> float:
    if column == m.policy.forecaster_column:
        return m.policy.forecaster_kappa
    if column == m.policy.forecaster_alternate:
        return m.policy.forecaster_alternate_kappa
    raise ValueError(f"no frozen kappa for {column!r}")


# Centred, calibrated 21-session expected returns: what the optimiser reads.
def centred_returns(
    m: Final | None = None, column: str | None = None, source: Path | None = None
) -> pd.DataFrame:
    m = m or load_mandate()
    column = column or m.policy.forecaster_column
    f = expected_returns(m, column, source=source)
    f["mu"] = scale_for(m, column) * (f["mu"] - f.groupby("eom")["mu"].transform("median"))
    return f


# Share of the 21-session alpha earned over `hold` sessions at age `age`.
def horizon_scale(age: float, hold: float, kappa: float) -> float:
    if hold <= 0:
        return 0.0
    if kappa <= 0:
        return hold / REFERENCE_DAYS
    return float(
        np.exp(-kappa * age) * (1 - np.exp(-kappa * hold)) / (1 - np.exp(-kappa * REFERENCE_DAYS))
    )


# Centred forecasts converted to a holding horizon and staleness (sessions).
def horizon_returns(
    m: Final | None = None,
    column: str | None = None,
    age: float = 0.0,
    hold: float = 21.0,
    source: Path | None = None,
) -> pd.DataFrame:
    m = m or load_mandate()
    column = column or m.policy.forecaster_column
    f = centred_returns(m, column, source=source)
    f["mu"] = f["mu"] * horizon_scale(age, hold, kappa_for(m, column))
    return f
