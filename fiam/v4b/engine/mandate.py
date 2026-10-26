# The finals rules as one file: hard limits, our policy, bans.

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL = ROOT / "fiam" / "v4b" / "config" / "final_2026.json"
# A research run may name another config (config/variant_*.json, same schema
# and checks); the headline config is untouched.
FINAL = ROOT / "fiam" / "v4b" / "config" / os.environ["FIAM_V4B_CONFIG"] if os.environ.get("FIAM_V4B_CONFIG") else FINAL
# E-LASSO output columns the config may name (DECISIONS.md D6).
FORECAST_COLUMNS = tuple(f"Elasso_Ma{w}" for w in ("1", "36", "60", "120", "Inf"))


# The organisers' limits (PDF Section 3.1); never relaxed.
@dataclass(frozen=True)
class Hard:
    names_min: int
    names_max: int
    name_cap: float
    gross_max: float
    net_band: float
    short_floor_musd: float
    nav0: float
    oos_start: str
    oos_end: str
    countries: tuple
    premium: float


# Our own stricter choices; each yields before a hard rule does.
@dataclass(frozen=True)
class Policy:
    net_target: float
    beta_band: float
    sector_band: float
    participation: float
    days_to_exit_max: int
    position_cap: float
    position_min: float
    price_min: float
    long_floor_musd: float
    max_configs: int
    impact_y: float
    spread_multipliers: tuple
    borrow_flat_large: float
    borrow_flat_other: float
    borrow_large_musd: float
    borrow_schedule: str  # "short_interest" (headline, engine/borrow.py) or "flat" (case §7 alternative)
    adv_window: int
    vol_window: int
    stub_days: int
    blind_until: str
    arcana_before_unseal: bool
    fallback_names: int
    fallback_gross: float
    # The forecaster (DECISIONS.md D6): E-LASSO, its column and alternate.
    forecaster: str
    # Run directory (under fiam/v4b) holding forecastElasso.parquet (D12).
    forecaster_run: str
    forecaster_column: str
    forecaster_alternate: str
    forecaster_decision: str
    # Frozen centred calibration scales and decay rates (elasso/freeze.py).
    forecaster_scale: float
    forecaster_alternate_scale: float
    forecaster_kappa: float
    forecaster_alternate_kappa: float
    # Controller judgements (R§5): scale, risk price, hedge sleeve, uncertainty.
    target_gross: float
    risk_aversion: float
    hedge_sleeve_max: float
    uncertainty_scale: float
    # Opposite-direction jump budgets (D12): book-weighted p_up of shorts and
    # p_dn of longs, as multiples of the pool mean (risk/jumps.py).
    jump_short_ratio: float
    jump_long_ratio: float
    # E5 objective (user, 2026-10-26: "minimize volatility, minimize beta and
    # maximize return"): quadratic price on book beta inside the hard band,
    # and the mean jump sizes behind the direction-aware jump variance
    # (lesson 63, validation means: +32% given an up-jump, -28% a down-jump).
    beta_penalty: float
    jump_up_size: float
    jump_dn_size: float
    # E5 scale: predicted annualised vol cap and the small risk price that
    # only steers composition under it ([Judgement], set without returns).
    vol_target: float
    vol_target_risk_aversion: float
    # "enhanced" = risk/enhanced.py (vra + residual PCA, lesson 88), "base" = risk/model.py.
    risk_model: str
    # Hedge beta mapped to realised beta (risk/beta_cal.py, expanding window on
    # earlier months only). User, 2026-10-26: "keep beta low so keep" - on,
    # although it failed the pre-registered accuracy rule (3 of 6 books, D14).
    beta_calibration: bool
    # Market beta in force (D20): "engine" = the risk model's hedge beta (calibrated
    # when beta_calibration); "hedge_uncal", "welch", "dimson", "welch_dimson",
    # "beta_60m" = risk/beta_candidates.py, replacing the market column of B.
    beta_source: str


# The whole mandate, loaded once per run.
@dataclass(frozen=True)
class Final:
    name: str
    hard: Hard
    policy: Policy
    banned_features: tuple
    banned_ideas: tuple


# A section's dict as its dataclass; unknown or missing keys stop the run.
def _build(cls, raw: dict, where: str):
    names = {f.name for f in fields(cls)}
    unknown, missing = sorted(set(raw) - names), sorted(names - set(raw))
    if unknown or missing:
        raise ValueError(f"{where}: unknown {unknown}, missing {missing}")
    return cls(**{k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()})


# The mandate file, checked before anything reads it.
def load(path: str | Path = FINAL) -> Final:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    final = Final(
        name=raw["name"],
        hard=_build(Hard, raw["hard"], "hard"),
        policy=_build(Policy, raw["policy"], "policy"),
        banned_features=tuple(raw["banned_features"]),
        banned_ideas=tuple(raw["banned_ideas"]),
    )
    problems = check(final)
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return final


# Rules that cannot all hold, or policy looser than the hard rule.
def check(m: Final) -> list[str]:
    h, p = m.hard, m.policy
    out = []
    if h.names_min > h.names_max:
        out.append(f"names_min {h.names_min} above names_max {h.names_max}")
    if h.names_max * h.name_cap < h.gross_max:
        out.append(f"{h.names_max} names at {h.name_cap:.0%} cannot reach the gross ceiling")
    if p.position_cap > h.name_cap:
        out.append(f"position_cap {p.position_cap:.1%} is looser than name_cap")
    if abs(p.net_target) > h.net_band:
        out.append(f"net_target {p.net_target:.0%} is outside the ±{h.net_band:.0%} band")
    if p.long_floor_musd < 0 or h.short_floor_musd <= 0:
        out.append("the cap floors must be positive")
    if not 0 < p.participation <= 0.25:
        out.append(f"participation {p.participation:.0%} is not a sensible cap")
    if h.names_min * p.position_min > h.gross_max:
        out.append("names_min at position_min already exceeds the gross ceiling")
    if p.fallback_names < h.names_min or p.fallback_names > h.names_max:
        out.append(f"fallback_names {p.fallback_names} is outside the name band")
    if not 0 < p.fallback_gross <= h.gross_max:
        out.append(f"fallback_gross {p.fallback_gross:.0%} is outside (0, gross_max]")
    if p.fallback_gross / p.fallback_names > p.position_cap:
        out.append("fallback weights would exceed position_cap")
    if p.forecaster != "elasso":
        out.append(f"forecaster {p.forecaster!r} contradicts DECISIONS.md D6 (elasso)")
    if {p.forecaster_column, p.forecaster_alternate} - set(FORECAST_COLUMNS):
        out.append("forecaster columns must be E-LASSO output columns (D6)")
    if not (0 < p.forecaster_scale <= 2 and 0 < p.forecaster_alternate_scale <= 2):
        out.append("forecaster calibration scales must lie in (0, 2]")
    if p.forecaster_kappa < 0 or p.forecaster_alternate_kappa < 0:
        out.append("forecaster decay rates (kappa) cannot be negative")
    if not h.names_min * p.position_min <= p.target_gross <= h.gross_max:
        out.append("target_gross must lie between the min-size floor and gross_max")
    if p.risk_aversion <= 0:
        out.append("risk_aversion must be positive")
    if not 0 <= p.hedge_sleeve_max <= 0.1 * p.target_gross:
        out.append("hedge_sleeve_max must lie in [0, 10% of target gross] (R§5)")
    if p.uncertainty_scale < 0:
        out.append("uncertainty_scale cannot be negative")
    if not (p.jump_short_ratio > 0 and p.jump_long_ratio > 0):
        out.append("jump budget ratios must be positive")
    if p.beta_penalty < 0 or p.jump_up_size < 0 or p.jump_dn_size < 0:
        out.append("beta penalty and jump sizes cannot be negative")
    if not (0 < p.vol_target <= 0.15 and p.vol_target_risk_aversion > 0):
        out.append("vol_target must lie in (0, 15%] and its risk price be positive")
    if p.risk_model not in ("enhanced", "base"):
        out.append("risk_model must be 'enhanced' or 'base'")
    if p.beta_calibration and p.risk_model != "enhanced":
        out.append("beta_calibration needs the enhanced risk model")
    if p.beta_source not in ("engine", "hedge_uncal", "welch", "dimson", "welch_dimson", "beta_60m"):
        out.append(f"unknown beta_source {p.beta_source!r}")
    if p.beta_source != "engine" and p.beta_calibration:
        out.append("beta_calibration applies to the engine beta only; turn it off for another beta_source")
    return out


# Fails if a feature list carries a banned column.
def assert_features(columns, m: Final) -> None:
    bad = sorted(set(columns) & set(m.banned_features))
    if bad:
        raise ValueError(f"banned features in a forecast input: {bad}")


# The mandate as plain data for the run record.
def record(m: Final) -> dict:
    return asdict(m)
