# The fund's one recipe, every setting set in one place.

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fiam.vfinal import gates

ROOT = gates.ROOT
# Where a run writes; FIAM_VFINAL_OUT moves it (the rerun check).
OUT = Path(os.environ.get("FIAM_VFINAL_OUT", str(ROOT / "out" / "vfinal")))
CACHE, LOGS, FORECAST = OUT / "cache", OUT / "logs", OUT / "forecast"
# The data folder, repo-relative as fiam.vfinal reads it.
DATA = ROOT / "data"
ORG = DATA / "organisers"
PANEL = ORG / "chars_final_with_names.parquet"
CHARS = ORG / "factor_char_list.csv"
# The vendor daily file and French's daily factors (rho's state).
DAILY = DATA / "fiam_v1" / "daily_market.parquet"
FF5_DAILY = DATA / "benchmarks" / "ff5_daily.zip"
# The lock: hashes of code, recipe, inputs and outputs.
FROZEN = ROOT / "frozen" / "vfinal"
# Daily data starts here, as the forecaster's daily file does.
START = "2015-01-02"
# The scored window: formations 2020-12 to 2026-07, days to 2026-08-31.
FIRST_EOM, LAST_EOM, END = "2020-12-31", "2026-07-31", "2026-08-31"
# The pre-2021 years the specific-risk race may score.
RACE_YEARS = (2017, 2018, 2019, 2020)
# The E-LASSO training cut and the forecast rows it scores.
CUT, FEATURES_FROM = "2026-08-31", "2016-11-30"
# The walk-forward's workers and numba threads per worker.
WORKERS, THREADS = 6, 2


# The book's limits and trading policy, every value set here.
@dataclass(frozen=True)
class Policy:
    names_min: int = 200
    names_max: int = 500
    name_cap: float = 0.05
    net_band: float = 0.5
    nav0: float = 1e9
    premium: float = 0.04
    beta_band: float = 0.02
    sector_band: float = 0.01
    participation: float = 0.10
    days_to_exit_max: int = 5
    position_cap: float = 0.0425
    position_cap_short: float = 0.01
    position_min: float = 0.001
    impact_y: float = 1.0
    borrow_flat_other: float = 0.05
    forecaster_scale: float = 0.04841426765809828
    forecaster_kappa: float = 0.00217388862207945
    target_gross: float = 1.8
    risk_aversion: float = 1.0
    uncertainty_scale: float = 0.25
    beta_penalty: float = 10.0
    vol_target: float = 0.12
    vol_target_risk_aversion: float = 0.25
    style_band_share: float = 0.25
    beta_bands_extra: tuple = ("welch_dimson", "beta_60m")


# The E5R construction flags (ladder.steps), relax-and-round.
@dataclass(frozen=True)
class Step:
    name: str = "E5R"
    support: str = "relax"
    names: int = 300
    universe_floor_musd: float = 3000.0


# The execution: equal fifths over 5 sessions at 10% ADV, the guards.
@dataclass(frozen=True)
class Execution:
    sessions: int = 5
    participation: float = 0.10
    # Gross guard: drift above this at the last close is trimmed.
    gross_guard: float = 1.92
    gross_trim_to: float = 1.80
    # A long above trim_at at a close goes to trim_to next close.
    trim_at: float = 0.0475
    trim_to: float = 0.0425
    # A short whose cap falls under $550m is covered next close.
    short_hold_musd: float = 550.0
    # The gross guard reads the previous close (PDF p15).
    lag_guard: bool = True


# What a book reads: el_plus, mid-month fresh inputs, a scaled core.
@dataclass(frozen=True)
class Overlay:
    # The core book whose targets this book scales (scaled books only).
    core: str = "p1_d69"
    # The el_plus forecast (the core solves on it).
    plus: bool = True
    # A mid-month review too, from refreshed price inputs.
    biweekly: str = "fresh"
    # A constant scale on every core target, and its formation gross.
    scale_k: float | None = None
    scale_cap: float = 1.95

    # True when the book is the core targets scaled, not re-solved.
    @property
    def scaled(self) -> bool:
        return self.scale_k is not None


# One book: its name, overlay, execution and policy.
@dataclass(frozen=True)
class Run:
    name: str
    overlay: Overlay = field(default_factory=Overlay)
    execution: Execution = field(default_factory=Execution)
    policy: Policy = field(default_factory=Policy)

    # The run as a plain dict for its files.
    def as_dict(self) -> dict:
        return asdict(self)


# The core: the QP on el_plus, risk prices x0.5, shorts at 1%.
CORE = Run("el_plus_bwf_lag")
# The book: the core x1.08, gross <= 1.88, the g guard 1.90 to 1.85.
BOOK = Run(
    "bw_fresh_lag",
    Overlay(core="el_plus_bwf_lag", plus=False, scale_k=1.08, scale_cap=1.88),
    Execution(gross_guard=1.90, gross_trim_to=1.85, trim_at=0.044, trim_to=0.039),
    Policy(position_cap=0.039, position_cap_short=0.0108),
)
RUNS = {CORE.name: CORE, BOOK.name: BOOK}
# Overlay switches the fund leaves out, at their off values.
DROPPED = {"blend": 0.0, "stripped": False, "vol_target": None, "vol_window": 63,
           "gross_to": None, "brake_at": None, "brake_exit": None, "brake_scale": 0.5,
           "hrp": None, "sue": 0.0, "rho_floor": None, "squeeze": False,
           "squeeze_mode": "both"}  # fmt: skip
# The hard rules every day must keep (finals PDF part 2).
HARD = {"name_cap": 0.05, "gross": 2.0, "net": 0.5, "names_min": 200, "names_max": 500,
        "short_floor_musd": 500.0, "sectors_min": 5, "sector_net": 0.20,
        "vol": 0.12}  # fmt: skip
# The flat conservative alternative (PDF p17): borrow by cap.
FLAT_LARGE_MUSD, FLAT_CHEAP, FLAT_DEAR = 10_000.0, 0.005, 0.05
# The disclosure every output folder carries.
LABEL = (
    "E-LASSO ranking with a factor-risk optimiser, rebalanced at month end with a mid-month "
    "review. Costs: per-order impact law plus borrow.\n"
)


# A run's settings against a saved run dict: the keys that differ.
def mismatches(run: Run, ref: dict) -> list[str]:
    got = run.as_dict()
    got["policy"]["beta_bands_extra"] = list(got["policy"]["beta_bands_extra"])
    bad = [] if got["name"] == ref["name"] else ["name"]
    for part in ("overlay", "execution", "policy"):
        want = dict(ref[part])
        for k, v in got[part].items():
            if want.pop(k, "missing") != v:
                bad.append(f"{part}.{k}")
        # A switch the fund leaves out must be off in the saved run too.
        for k, v in want.items():
            if part != "overlay" or DROPPED.get(k, "missing") != v:
                bad.append(f"{part}.{k} (dropped)")
    return bad


# The recipe as one plain dict, the lock's recipe.json.
def recipe() -> dict:
    out = {name: r.as_dict() for name, r in RUNS.items()}
    for r in out.values():
        r["policy"]["beta_bands_extra"] = list(r["policy"]["beta_bands_extra"])
    return out | {"window": {"start": START, "first_eom": FIRST_EOM, "last_eom": LAST_EOM,
                             "end": END, "cut": CUT, "features_from": FEATURES_FROM},
                  "race_years": list(RACE_YEARS), "hard": HARD,
                  "flat": [FLAT_LARGE_MUSD, FLAT_CHEAP, FLAT_DEAR]}  # fmt: skip


# A book's own output folder.
def folder(name: str) -> Path:
    return OUT / name
