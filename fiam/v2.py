# The shipped engine plus switches, each judged alone.

import json
import os
import sys
import time
from dataclasses import dataclass, field, replace
from functools import cache, partial
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from fiam import book as P
from fiam import costs as C
from fiam import data, layers, stats
from fiam import mandate as M
from fiam.freeze import FROZEN

# The five core switches, and others reported beside them, never inside.
MEMBERS = ("costs", "persistence", "beta", "shorts", "liquidity")
# `grinold` is `costs` on cross-sectional IC, never both.
OTHERS = ("institutional", "aligned", "industry", "risk", "carbon", "grinold")
COSTED = frozenset({"costs", "grinold"})
# Risk parts, each tested alone; `final` adds the ones that pass.
PARTS = ("size", "lowvol", "voltarget", "brake")
# The gross a risk target may set; the brake cuts to the lower end.
GROSS_RANGE = (1.0, 1.8)
# The `final` set: two rules always on, two switches tested.
RULES, TESTED = ("zerobeta", "target10"), ("riskcap", "adaptive")
FINAL = RULES + TESTED
STEERED = frozenset(PARTS) | frozenset(FINAL)
# Exhibit switch: the `final` set on the 500 largest stocks only.
EXHIBIT = ("top500",)
# The finals' global book, each country capped.
WORLD = ("global",)
# The zero-beta band, the yearly risk target and forecast error decay.
ZERO_BETA, TARGET_VOL, BIAS_DECAY = 0.005, 0.10, 0.5 ** (1 / 12)
# What-ifs only, never in a shipped book: the AI crowd's score.
CROWD = ("crowd_with", "crowd_against", "crowd_alone")
CROWDS = ("retail", "copycat", "historical")
RECORD = (P.FIRST_FORECAST, P.LAST_FORECAST)
CHECK = ("2015-12-31", "2020-11-30")
# Live crowd months, after the models' training cutoff: 19 decisions.
CLEAN = ("2025-01-31", "2026-07-31")
WINDOWS = {RECORD: "record", CHECK: "check", CLEAN: "clean"}
CAPITALS = (1e6, 1e7, 1e8, 5e8, 1e9, 5e9)
PARAMS = FROZEN / "v2_params.json"
BETAS = FROZEN / "v2_beta.parquet"
OUT = Path("out") / "v2"
# Extra columns: residual vol for return scale, ff49 for industry ranks.
EXTRA = ("ivol_capm_252d", "ff49")


# One run's choices: switches on, capital, and the rules it runs under.
@dataclass(frozen=True)
class Settings:
    on: frozenset = frozenset()
    capital: float = C.DEFAULT.nav
    mandate: M.Mandate = field(default_factory=M.Mandate)

    # The run's folder name: its switches (v2, v2a), capital and mandate.
    @property
    def name(self) -> str:
        label = "+".join(sorted(self.on)) or "v1"
        if self.on >= set(MEMBERS):
            label = "+".join(["v2", *sorted(self.on - set(MEMBERS))])
        elif self.on >= V2A:
            label = "+".join(["v2a", *sorted(self.on - V2A)])
        name = f"{label}@{self.capital:.0e}".replace("+0", "")
        named = self.mandate.name in ("v1", label)
        return name if named else f"{self.mandate.name}_{name}"


V2 = frozenset(MEMBERS)
V2A = (V2 - {"costs"}) | {"grinold"}


# Numbers fitted on pre-2021 data (fiam.freeze), empty until frozen.
def params() -> dict:
    return json.loads(PARAMS.read_text(encoding="utf-8")) if PARAMS.exists() else {}


# The twelve signals, weighted by persistence when that switch is on.
def signals(settings: Settings, fixed: dict) -> dict:
    if "persistence" not in settings.on:
        return P.SIGNALS
    weights = fixed["persistence_weights"]
    return {col: sign * weights[col] for col, sign in P.SIGNALS.items()}


# Each signal ranked within its ff49 industry, not across the market.
def industry_composite(df: pd.DataFrame, table: dict) -> pd.Series:
    groups = [df["eom"], df["ff49"].fillna(-1)]
    parts = []
    for col, sign in table.items():
        r = df.groupby(groups)[col].rank(pct=True)
        z = (r - r.groupby(groups).transform("mean")) / r.groupby(groups).transform("std")
        parts.append(z * sign)
    return pd.concat(parts, axis=1).mean(axis=1)


# The score with beta, the vol complex and size taken out, each month.
def aligned(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=df.index)
    x_cols = ["hedge_beta", "risk_rank", "log_me"]
    frame = df.assign(log_me=np.log(df["me"].clip(lower=1e-6)))
    for _, g in frame.groupby("eom"):
        x = np.column_stack([np.ones(len(g)), g[x_cols].fillna(g[x_cols].median()).to_numpy()])
        coef, *_ = np.linalg.lstsq(x, g["signal"].to_numpy(), rcond=None)
        out[g.index] = g["signal"].to_numpy() - x @ coef
    return out


# 8-K items barring a new short for 30 days (3.02 is not in our 8-Ks).
EVENTS = ["item_101_contract", "item_201_acquisition", "item_801_other_event"]


# No new shorts: tiny, costly to borrow, options-flagged or mid-event.
def short_ban(df: pd.DataFrame) -> pd.Series:
    ban = df["size_grp"].isin(["micro", "nano"]) | (df["borrow"] >= 0.03)
    options = layers.load("options/summary", ["permno", "date", "Parity_VSpread"])
    if options is not None:
        joined = layers.as_of(df, options, "date", ["Parity_VSpread"], ttl=31)
        spread = joined["Parity_VSpread"]
        low = spread <= spread.groupby(joined["eom"]).transform("quantile", 0.05)
        ban |= low.to_numpy()
    filings = data.filings(["permno", "filing_date", *EVENTS])
    events = filings[filings[EVENTS].fillna(0).sum(axis=1) > 0].assign(event=True)
    joined = layers.as_of(df, events, "filing_date", ["event"], ttl=30)
    ban |= joined["event"].eq(True).to_numpy()
    return ban


# The composite plus the AI crowd's score, either sign, or it alone.
def with_crowd(df: pd.DataFrame, settings: Settings) -> pd.Series:
    label = next((c for c in CROWDS if c in settings.on), "retail")
    votes = data.read(OUT / "crowd_consensus.parquet")
    votes = votes[votes["crowd"] == label].drop(columns="crowd")
    crowd = df[data.KEYS].merge(votes, on=data.KEYS, how="left")["consensus"].to_numpy()
    z = P.rank_z(df.assign(crowd=crowd), "crowd").fillna(0.0)
    if "crowd_alone" in settings.on:
        return z
    sign = 1.0 if "crowd_with" in settings.on else -1.0
    n = len(P.SIGNALS)
    return (n * df["composite"] + sign * z) / (n + 1)


# Carbon Arc: a 13th signal, only once its test passed.
def with_carbon(df: pd.DataFrame) -> pd.Series:
    report = json.loads((OUT / "carbon_arc" / "report.json").read_text(encoding="utf-8"))
    if not report["test"]["passed"]:
        raise SystemExit("the Carbon Arc test did not pass, so its switch stays off")
    growth = data.read(OUT / "carbon_arc" / "signal.parquet")
    found = df[data.KEYS].merge(growth, on=data.KEYS, how="left")
    found = found.merge(data.features(["saleq_gr1"]), on=data.KEYS, how="left")
    z = P.rank_z(
        df.assign(carbon=(found["spend_growth"] - found["saleq_gr1"]).to_numpy()), "carbon"
    )
    n = len(P.SIGNALS)
    return (n * df["composite"] + z.fillna(0.0)) / (n + 1)


# The hedge beta with the `beta` switch on, frozen before 2021.
def frozen_beta(df: pd.DataFrame) -> pd.Series:
    table = data.read(BETAS).set_index(data.KEYS)["beta"]
    found = table.reindex(pd.MultiIndex.from_frame(df[data.KEYS])).to_numpy()
    fallback = df["beta_60m"].fillna(df["beta_dimson_21d"])
    return pd.Series(found, index=df.index).fillna(fallback)


# Half weight if a signal's last 12 realized months (6+) sum below 0.
def halved(paid: pd.DataFrame, decisions: list) -> pd.DataFrame:
    rows = {}
    for eom in decisions:
        recent = paid[paid.index <= eom - pd.offsets.MonthBegin(1)].tail(12)
        failing = (len(recent) >= 6) & (recent.sum() < 0)
        rows[eom] = np.where(failing, 0.5, 1.0)
    return pd.DataFrame.from_dict(rows, orient="index", columns=paid.columns)


# Weights for each decision to `last`, from paid returns since 2015.
@cache
def adaptive_weights(last: str) -> pd.DataFrame:
    from fiam.freeze import FIT

    history = P.build_signal(P.screen(P.load_panel(), FIT[0], last))
    table = P.scores(history, P.SIGNALS).set_axis(list(P.SIGNALS), axis=1)
    paid = pd.DataFrame({col: P.spread(history, table[col]) for col in P.SIGNALS})
    return halved(paid, sorted(history["eom"].unique()))


# Composite at each month's signal weights; all 1 gives the plain one.
def adaptive_composite(df: pd.DataFrame, table: pd.DataFrame, last: str) -> pd.Series:
    weights = adaptive_weights(last).reindex(df["eom"]).fillna(1.0).to_numpy()
    z = table.to_numpy()
    w = np.where(np.isnan(z), 0.0, weights)
    return pd.Series(np.nansum(z * w, axis=1) / w.sum(axis=1), index=df.index)


# The mandate's entry rules: a smallest market cap and excluded sectors.
def admitted(df: pd.DataFrame, m: M.Mandate) -> pd.DataFrame:
    keep = pd.Series(True, index=df.index)
    if m.min_market_cap is not None:
        keep &= df["me"] >= m.min_market_cap
    if m.exclude_sectors:
        keep &= ~df["sector"].isin(m.exclude_sectors)
    return df if keep.all() else df[keep].copy()


# The cross-section traded, built as the shipped book's unless switched.
def universe(window: tuple, settings: Settings, fixed: dict) -> pd.DataFrame:
    worldwide = "global" in settings.on
    if worldwide and "country" not in pq.read_schema(data.FEATURES).names:
        raise SystemExit("the global switch needs a bundle with countries: run.py --world <folder>")
    df = P.screen(P.load_panel(EXTRA + (("country",) if worldwide else ())), *window)
    if worldwide:
        df = df[df["country"].isin(settings.mandate.countries)].copy()
    df = admitted(df, settings.mandate)
    if "institutional" in settings.on:
        df = df[df["me"] >= 1000.0].copy()
    # The 500 largest by market value each month, our S&P 500 stand-in.
    if "top500" in settings.on:
        df = df[df.groupby("eom")["me"].rank(ascending=False, method="first") <= 500].copy()
    screened = df
    df = P.build_signal(df, signals(settings, fixed))
    # Ahead of the learned hedge, which renumbers rows and neutralizes this.
    if "adaptive" in settings.on:
        table = P.scores(screened, P.SIGNALS).set_axis(list(P.SIGNALS), axis=1)
        df["composite"] = adaptive_composite(df, table.loc[df.index], window[1])
        df["signal"] = P.neutralize(df, df["composite"])
    # Record months carry the learned hedge and borrow, as the shipped book.
    if window[0] >= P.FIRST_FORECAST:
        df = P.shipped(df)
    if "industry" in settings.on:
        df["composite"] = industry_composite(df, signals(settings, fixed))
        df["signal"] = P.residualize(df, df["composite"], P.hedge(df))
    if "beta" in settings.on:
        df["hedge_beta"] = frozen_beta(df)
        if "industry" not in settings.on:
            df["signal"] = P.neutralize(df, df["composite"])
    if "carbon" in settings.on:
        df["composite"] = with_carbon(df)
        df["signal"] = P.neutralize(df, df["composite"])
    if settings.on & set(CROWD):
        df["composite"] = with_crowd(df, settings)
        df["signal"] = P.neutralize(df, df["composite"])
    if "aligned" in settings.on:
        df["signal"] = aligned(df)
    if "shorts" in settings.on:
        df["ban_short"] = short_ban(df).to_numpy()
    if "lowvol" in settings.on:
        df["low_vol"] = P.rank_z(df, "ivol_capm_252d").fillna(0.0)
    # A name's cap shrinks with its specific vol over the median, to 1/3.
    if "riskcap" in settings.on:
        from fiam import vol as V

        spec = V.forecast(df)
        df["vol_scale"] = (spec.groupby(df["eom"]).transform("median") / spec).clip(1 / 3, 1.0)
        df["vol_scale"] = df["vol_scale"].fillna(1.0)
    # Score to monthly return: IC times the month's median residual vol.
    vol = df["ivol_capm_252d"] * np.sqrt(21)
    ic = fixed.get("ic_monthly" if "grinold" in settings.on else "ic", 0.0)
    df["scale"] = ic * vol.groupby(df["eom"]).transform("median")
    if settings.on & {"risk", "voltarget"} or settings.mandate.vol_budget is not None:
        from fiam import risk
        from fiam import vol as V

        for name, col in risk.STYLES.items():
            df[name] = P.rank_z(df, col).fillna(0.0)
        df["spec_vol"] = V.forecast(df)
        # Grinold (1994): a stock's alpha = IC x its residual vol x its score.
        df["risk_alpha"] = ic * vol.fillna(vol.median()) * df["signal"]
    return df.dropna(subset=["signal"])


# The frozen factor returns of fiam.risk, read once.
@cache
def factor_returns() -> pd.DataFrame | None:
    from fiam import risk

    return data.read(risk.FACTORS).set_index("eom") if risk.FACTORS.exists() else None


# The pool's risk as loadings B and specific variances, None before 24m.
def risk_terms(pool: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    from fiam import risk

    returns = factor_returns()
    cov = None if returns is None else risk.covariance(returns, pool["eom"].iloc[0])
    if cov is None:
        return None
    x = risk.design(pool.reset_index(drop=True)).reindex(columns=cov.columns, fill_value=0.0)
    values, vectors = np.linalg.eigh(cov.to_numpy())
    loadings = x.to_numpy() @ (vectors * np.sqrt(np.clip(values, 0.0, None)))
    spec = pool["spec_vol"].fillna(pool["spec_vol"].median()).to_numpy() ** 2
    return loadings, spec


# The book's variance for the solver, |B'w|^2 plus specific risk.
def variance(w, terms: tuple[np.ndarray, np.ndarray]):
    loadings, spec = terms
    return cp.sum_squares(loadings.T @ w) + spec @ cp.square(w)


# The same variance for fixed weights, as a monthly volatility.
def predicted_vol(w: np.ndarray, terms: tuple[np.ndarray, np.ndarray]) -> float:
    loadings, spec = terms
    return float(np.sqrt(((loadings.T @ w) ** 2).sum() + spec @ w**2))


# Per-name NAV costs a month: linear, sales, square-root impact, borrow.
def cost_terms(pool: pd.DataFrame, nav: float) -> tuple[np.ndarray, ...]:
    quotes = pool[C.COLUMNS].copy()
    # A gap takes the pool's median, as the shipped cost lines do.
    numeric = quotes.columns.drop("size_grp")
    quotes[numeric] = quotes[numeric].fillna(quotes[numeric].median())
    price = quotes["prc"].abs().to_numpy()
    linear = C.half_spread(quotes).to_numpy() + (C.COMMISSION_PER_SHARE + C.CAT_PER_SHARE) / price
    selling = C.SEC_RATE + C.TAF_PER_SHARE / price
    dolvol = quotes["dolvol_126d"].to_numpy()
    impact = C.IMPACT_Y * quotes["rvol_21d"].to_numpy() * np.sqrt(nav / dolvol)
    return linear, selling, impact, quotes["borrow"].to_numpy() / 12


# The convex cost of trading prev to w: spread, fees and impact.
def trading_cost(w, prev: np.ndarray, pool: pd.DataFrame, nav: float):
    linear, selling, impact, _ = cost_terms(pool, nav)
    trade = w - prev
    return linear @ cp.abs(trade) + selling @ cp.pos(-trade) + impact @ cp.power(cp.abs(trade), 1.5)


# The convex part of every cost line from prev to w, minimums left out.
def convex_cost(w, prev: np.ndarray, pool: pd.DataFrame, nav: float):
    borrow = cost_terms(pool, nav)[3]
    return trading_cost(w, prev, pool, nav) + borrow @ cp.pos(-w)


# The pool with held names added back, drifted weights in pool order.
def with_held(month, pool, previous) -> tuple[pd.DataFrame, np.ndarray]:
    if previous is not None:
        held = month[month["permno"].isin(previous.index) & ~month["permno"].isin(pool["permno"])]
        if not held.empty:
            pool = pd.concat([pool, held])
    prev = np.zeros(len(pool)) if previous is None else previous.reindex(pool["permno"]).fillna(0.0)
    return pool, np.asarray(prev, dtype=float)


# The hedge-beta band: the mandate's, or near zero under `zerobeta`.
def beta_band(settings: Settings) -> float:
    return ZERO_BETA if "zerobeta" in settings.on else settings.mandate.beta


# Every rule but gross: neutrality, sides, caps, bans and bands.
def rules(w, pool: pd.DataFrame, prev: np.ndarray, settings: Settings, relax=1.0) -> tuple:
    m = settings.mandate
    side = np.where(pool["signal"].to_numpy() >= 0, 1.0, -1.0)
    sized = "size" in settings.on
    # Under the size part a held name keeps its side and may not grow.
    turned = sized & (prev != 0) & (np.sign(prev) != side)
    side = np.where(turned, np.sign(prev), side)
    cap = np.full(len(pool), m.name_cap)
    if "liquidity" in settings.on or sized:
        dolvol = pool["dolvol_126d"].fillna(pool["dolvol_126d"].median()).to_numpy()
        cap = np.minimum(cap, 0.4 * dolvol / settings.capital)
    if "riskcap" in settings.on:
        cap = np.minimum(cap, m.name_cap * pool["vol_scale"].to_numpy())
    cap = np.where(turned, np.minimum(cap, np.abs(prev)), cap)
    lower = np.zeros(len(pool)) if m.long_only else np.minimum(side, 0) * cap
    if "shorts" in settings.on:
        banned = pool["ban_short"].to_numpy(dtype=bool)
        lower = np.where(banned, np.maximum(lower, np.minimum(prev, 0.0)), lower)
    upper = np.maximum(side, 0) * cap
    # Under a turnover budget a held name may stay rather than trade.
    if m.turnover is not None:
        lower, upper = np.minimum(lower, np.minimum(prev, 0)), np.maximum(upper, prev)
    constraints = [cp.sum(w) == m.net, w >= lower, w <= upper]
    if m.beta is not None:
        constraints.append(cp.abs(P.hedge(pool).to_numpy() @ w) <= beta_band(settings))
    if m.risk is not None:
        constraints.append(cp.abs(pool["risk_rank"].to_numpy() @ w) <= m.risk)
    if m.sector is not None:
        sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)
        constraints.append(cp.abs(sectors.T @ w) <= m.sector)
    names = ["net", "lower", "upper", "beta", "risk", "sector"]
    names = [n for n in names if n not in ("beta", "risk", "sector") or getattr(m, n) is not None]
    for constraint, name in zip(constraints, names):
        constraint.rule = name
    if m.turnover is not None and prev.any():
        constraints.append(cp.sum(cp.abs(w - prev)) / 2 <= m.turnover)
        constraints[-1].rule = "turnover"
    # Each country's gross within its cap of book gross, linear in w.
    if "global" in settings.on and m.country_cap is not None:
        for country in pool["country"].dropna().unique():
            inside = side * pool["country"].eq(country).to_numpy()
            constraints.append(inside @ w <= m.country_cap * (side @ w))
            constraints[-1].rule = "country"
    terms = risk_terms(pool) if m.vol_budget is not None else None
    if terms is not None:
        constraints.append(variance(w, terms) <= m.vol_budget**2 / 12)
        constraints[-1].rule = "vol_budget"
    # Long-horizon vol style held as the shipped book holds its 21-day one.
    if "lowvol" in settings.on:
        constraints.append(cp.abs(pool["low_vol"].to_numpy() @ w) <= P.LIMITS["risk"])
        constraints[-1].rule = "lowvol"
    # One NAV share spent trading each month at any size, first build free.
    if sized and relax is not None and prev.any():
        budget = params()["cost_budget"] * relax
        constraints.append(trading_cost(w, prev, pool, settings.capital) <= budget)
        constraints[-1].rule = "budget"
    return constraints, side @ w, (lower, upper)


# One pool solved at a fixed gross; the shipped solve with all off.
def solve(month, pool, previous, settings: Settings, gross: float, relax=1.0) -> pd.Series | None:
    pool, prev = with_held(month, pool, previous)
    w = cp.Variable(len(pool))
    constraints, exposure, bounds = rules(w, pool, prev, settings, relax)
    constraints.append(exposure == gross)
    objective = pool["signal"].to_numpy() @ w - 0.5 * settings.mandate.ridge * cp.sum_squares(w)
    terms = risk_terms(pool) if "risk" in settings.on else None
    if terms is not None:
        penalty = params().get("risk_lambda", 0.0) * variance(w, terms)
        objective = (pool["risk_alpha"].to_numpy() @ w - penalty) / float(pool["scale"].iloc[0])
    if settings.on & COSTED:
        # scale x score - cost, over scale: same optimum, solver-friendly.
        scale = float(pool["scale"].iloc[0])
        objective = objective - convex_cost(w, prev, pool, settings.capital) / scale
    problem = cp.Problem(cp.Maximize(objective), constraints)
    # CLARABEL, then SCS; an answer counts only if every rule holds to 1e-3.
    for solver, options in SOLVERS:
        # SCS only if the rules are feasible, else the search goes deeper.
        if solver is cp.SCS and not feasible(constraints):
            return None
        try:
            problem.solve(solver=solver, **options)
        except cp.error.SolverError:
            continue
        if w.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
            continue
        if max(float(np.max(c.violation())) for c in problem.constraints) <= 1e-3:
            # What each rule costs the objective at the optimum, its shadow price.
            LAST.clear()
            LAST["status"], LAST["solver"] = problem.status, solver
            for c in constraints:
                dual = np.abs(np.atleast_1d(c.dual_value)) if c.dual_value is not None else [0]
                LAST[f"dual_{getattr(c, 'rule', 'gross')}"] = float(np.sum(dual))
            # The size part's caps hold exactly, not to the solver's tolerance.
            values = np.clip(w.value, *bounds) if "size" in settings.on else w.value
            weights = pd.Series(values, index=pool["permno"].to_numpy())
            return weights[weights.abs() > 1e-5]
    return None


# The most gross the rules allow, when liquidity caps cannot carry it.
def largest_gross(month, pool, previous, settings: Settings) -> float:
    pool, prev = with_held(month, pool, previous)
    w = cp.Variable(len(pool))
    constraints, exposure, _ = rules(w, pool, prev, settings, None)
    problem = cp.Problem(cp.Maximize(exposure), [*constraints, exposure <= settings.mandate.gross])
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.error.SolverError:
        return 0.0
    return float(problem.value) if problem.value is not None else 0.0


# Too many names: re-solved on the largest, kept if the rules hold.
def fewer(month, weights: pd.Series, previous, settings: Settings, gross: float, relax=1.0):
    m = settings.mandate
    if len(weights) <= m.names_max:
        return weights
    keep = month[month["permno"].isin(weights.abs().nlargest(m.names_max).index)]
    smaller = solve(keep, keep, previous, settings, gross, relax)
    return weights if smaller is None else smaller


# The drawdown brake's record of the book's path, kept by walk().
BRAKE: dict = {}


# On 5% off peak, off at half regained, on at new lows, reset at peaks.
def track(net: float) -> None:
    b = BRAKE
    b["nav"] = b.get("nav", 1.0) * (1 + net)
    peak = b.setdefault("peak", 1.0)
    if b["nav"] > peak:
        b.update(peak=b["nav"], low=None, on=False)
    elif b.get("low") is None:
        if b["nav"] <= 0.95 * peak:
            b.update(low=b["nav"], on=True)
    elif b["nav"] < b["low"]:
        b.update(low=b["nav"], on=True)
    elif b["nav"] >= b["low"] + 0.5 * (peak - b["low"]):
        b["on"] = False


# Risk-model monthly vol of the book without size or risk parts.
def book_vol(month: pd.DataFrame, previous, settings: Settings) -> float | None:
    plain = replace(settings, on=settings.on - {"size", "voltarget", "brake"})
    weights = search(month, previous, plain)
    if weights is None:
        return None
    pool = month.set_index("permno").loc[weights.index].reset_index()
    terms = risk_terms(pool)
    return None if terms is None else predicted_vol(weights.to_numpy(), terms)


# The risk forecast and its error, kept by walk() as months end.
RISK: dict = {}


# The forecast error starts from the frozen 2017-2020 value.
def reset() -> None:
    BRAKE.clear()
    RISK.clear()
    RISK["error"] = params().get("vol_bias", 1.0) ** 2


# Folds a month's squared vol miss into the error, 12-month half-life.
def learn(gross_return: float, gross_exposure: float, settings: Settings) -> None:
    plain = RISK.pop("plain", None)
    if plain and gross_exposure:
        predicted = plain * gross_exposure / settings.mandate.gross
        miss = (gross_return / predicted) ** 2
        RISK["error"] = BIAS_DECAY * RISK["error"] + (1 - BIAS_DECAY) * miss


# What the book's path teaches it each month: brake and risk forecast.
def observe(record: dict, settings: Settings) -> None:
    track(record["net"])
    learn(record["gross"], record["gross_exposure"], settings)


# Gross: the mandate's, risk-targeted, at the floor while braking.
def target_gross(month: pd.DataFrame, previous, settings: Settings) -> float:
    gross = settings.mandate.gross
    if "voltarget" in settings.on:
        predicted = book_vol(month, previous, settings)
        if predicted and "target10" in settings.on:
            target = (settings.mandate.vol_target or TARGET_VOL) / np.sqrt(12)
            ceiling = min(GROSS_RANGE[1], params()["gross_ceiling"])
            expected = np.sqrt(RISK.setdefault("error", 1.0)) * predicted
            gross = float(np.clip(gross * target / expected, GROSS_RANGE[0], ceiling))
            RISK["plain"] = predicted
        elif predicted:
            gross = float(np.clip(gross * params()["vol_target"] / predicted, *GROSS_RANGE))
    if "brake" in settings.on and BRAKE.get("on"):
        gross = GROSS_RANGE[0]
    return gross


# The (budget multiple, gross) pairs tried, gross easing halfway first.
def attempts(month: pd.DataFrame, previous, settings: Settings) -> list[tuple]:
    target = target_gross(month, previous, settings)
    if "size" not in settings.on:
        return [(1.0, target)]
    grosses = [target]
    if previous is not None and abs(previous.abs().sum() - target) > 0.02:
        held = float(previous.abs().sum())
        grosses += [(target + held) / 2, held]
    return [(relax, gross) for relax in (1.0, 2.0, None) for gross in grosses]


# The shipped search: extremes, then deeper pools, then the most gross.
def search(month: pd.DataFrame, previous, settings: Settings) -> pd.Series | None:
    month = month.sort_values("signal")
    m = settings.mandate
    # No convex rule can limit names, so the pool is cut to the limit.
    depth = min(m.pool, m.names_max if m.long_only else m.names_max // 2)
    for relax, gross in attempts(month, previous, settings):
        for size in (depth, 2 * depth, len(month)):
            pool = pd.concat([month.tail(size), month.head(size)]).drop_duplicates("permno")
            weights = solve(month, pool, previous, settings, gross, relax)
            if weights is not None:
                weights = fewer(month, weights, previous, settings, gross, relax)
                if settings.on & STEERED:
                    braked = "brake" in settings.on and bool(BRAKE.get("on"))
                    LAST.update(gross_target=gross, braked=braked)
                if "target10" in settings.on:
                    LAST["risk_correction"] = float(np.sqrt(RISK.get("error", 1.0)))
                if "size" in settings.on:
                    LAST["budget"] = relax or 0.0
                return weights
    if settings.on & {"liquidity", "size"}:
        reachable = largest_gross(month, month, previous, settings)
        if reachable > 1e-3:
            weights = solve(month, month, previous, settings, 0.999 * reachable, None)
            if "size" in settings.on and weights is not None:
                LAST.update(gross_target=0.999 * reachable, budget=0.0)
            return weights
    return None


# Net-target books round to whole shares here; zero-net ones later.
def optimize(month: pd.DataFrame, previous, settings: Settings) -> pd.Series | None:
    weights = search(month, previous, settings)
    budget = settings.mandate.turnover is not None
    if weights is None and (settings.on or budget) and previous is not None:
        # No solver met the rules, so last month's book is held, not cash.
        weights = previous[previous.index.isin(month["permno"])]
        LAST.clear()
        LAST["status"] = "held"
        weights = weights if len(weights) else None
    if weights is None or settings.mandate.net == 0:
        return weights
    px = month.set_index("permno")["prc"].abs().reindex(weights.index)
    held = np.rint(weights * settings.capital / px) * px / settings.capital
    return held[held.abs() > 1e-9]


# Whether the rules alone can hold: a fast check without costs.
def feasible(constraints: list) -> bool:
    check = cp.Problem(cp.Minimize(0), constraints)
    try:
        check.solve(solver=cp.CLARABEL)
    except cp.error.SolverError:
        return True
    return check.status not in ("infeasible", "infeasible_inaccurate")


# The solvers in the order tried, with their settings.
SOLVERS = (
    (cp.CLARABEL, {}),
    (cp.SCS, {}),
    (cp.SCS, dict(eps_abs=1e-7, eps_rel=1e-7, max_iters=200_000)),
)


# The last solve's status and each rule's shadow price, read by walk().
LAST: dict = {}


# Each rule rechecked on the whole-share book: the largest overshoot.
def breaches(
    weights: pd.Series, info: pd.DataFrame, settings: Settings, turnover=0.0, gross=None
) -> dict:
    m = settings.mandate
    if not len(weights):
        return dict(breach_max=0.0)
    gaps = dict(
        net=abs(weights.sum() - m.net) - 0.005,
        gross=abs(weights.abs().sum() - (m.gross if gross is None else gross)) - 0.01,
        name=weights.abs().max() - m.name_cap - 0.001,
        names=float(max(len(weights) - m.names_max, m.names_min - len(weights), 0)) - 0.5,
    )
    if m.turnover is not None:
        gaps["turnover"] = turnover - m.turnover - 0.005
    if m.beta is not None:
        exposure = abs((weights * P.hedge(info).reindex(weights.index)).sum())
        gaps["beta"] = exposure - beta_band(settings) - 0.005
    if m.sector is not None:
        gaps["sector"] = weights.groupby(info["sector"].reindex(weights.index)).sum().abs().max()
        gaps["sector"] -= m.sector + 0.002
    if "global" in settings.on and m.country_cap is not None:
        by_country = weights.abs().groupby(info["country"].reindex(weights.index)).sum()
        gaps["country"] = by_country.max() / weights.abs().sum() - m.country_cap - 0.005
    worst = max(gaps, key=gaps.get)
    return dict(
        breach_max=max(float(gaps[worst]), 0.0), breach_rule=worst if gaps[worst] > 0 else ""
    )


# Each month's record plus legs, liquidity and weights for judging.
def walk(df: pd.DataFrame, settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame]:
    model = C.Model(nav=settings.capital, impact_y=C.IMPACT_Y)
    rows, held = [], []
    rounded = settings.mandate.net == 0
    reset()
    for step in P.walk(df, partial(optimize, settings=settings), rounded, model):
        month, weights, info = step[:3]
        record = P.month_record(*step)
        # Known at the month's end, before the next decision reads it.
        observe(record, settings)
        ret = info["ret_exc_lead1m"].reindex(weights.index).fillna(0.0)
        record["short_leg"] = float((weights[weights < 0] * ret[weights < 0]).sum())
        record["long_leg"] = float((weights[weights > 0] * ret[weights > 0]).sum())
        dolvol = info["dolvol_126d"].reindex(weights.index)
        record["days_to_liquidate_max"] = float(
            (weights.abs() * settings.capital / (0.2 * dolvol)).max() if len(weights) else 0.0
        )
        built = record["turnover"] if rows else 0.0
        record |= breaches(weights, info, settings, built, LAST.get("gross_target")) | dict(LAST)
        LAST.clear()
        rows.append(record)
        held.append(pd.DataFrame(dict(eom=month, permno=weights.index, weight=weights.to_numpy())))
    return pd.DataFrame(rows).set_index("holding_month"), pd.concat(held, ignore_index=True)


# The numbers each switch is judged on, alike for every run and window.
def summary(book: pd.DataFrame, check: bool) -> dict:
    market = P.benchmarks().set_index("month")["mkt_rf_crsp" if check else "mkt_rf"]
    fit = P.regress(book["net"], market.reindex(book.index))
    out = P.book_stats(book) | dict(
        beta_realized=float(fit.params.iloc[1]),
        beta_stderr=float(fit.bse.iloc[1]),
        short_leg_worst=float(book["short_leg"].min()),
        days_to_liquidate_max=float(book["days_to_liquidate_max"].max()),
        htb_share=float(book["htb_share"].mean()),
        months_empty=int((book["n"] == 0).sum()),
        months_breaching=int((book.get("breach_max", pd.Series(0.0)) > 0).sum()),
        months_inaccurate=int((book.get("status", pd.Series("")) == "optimal_inaccurate").sum()),
        months_held=int((book.get("status", pd.Series("")) == "held").sum()),
    )
    out |= {k: float(book[k].mean()) for k in book if k.startswith("dual_")}
    out |= {k: float(book[k].mean() * 12) for k in book if k.startswith("cost_")}
    # The risk figures the risk parts are judged on.
    net = book["net"]
    out |= dict(
        volatility=float(net.std() * np.sqrt(12)),
        sharpe=float(net.mean() / net.std() * np.sqrt(12)) if net.std() else 0.0,
        max_drawdown=stats.drawdown(net),
        gross_min=float(book["gross_exposure"].min()),
        gross_mean=float(book["gross_exposure"].mean()),
        gross_max=float(book["gross_exposure"].max()),
    )
    # Steadiness: longest time under a peak, share of 12-month gains.
    out["months_underwater_max"] = stats.underwater(net)
    rolling = net.rolling(12).sum().dropna()
    out["rolling_12m_positive"] = float((rolling > 0).mean()) if len(rolling) else float("nan")
    if "budget" in book:
        out["months_over_budget"] = int((book["budget"].fillna(1.0) != 1.0).sum())
    if "braked" in book:
        out["months_braked"] = int(book["braked"].fillna(False).astype(bool).sum())
    return out


# The document name a configuration's ledger rows point to.
def protocol(on: frozenset) -> str:
    if on & set(WORLD):
        return "finals_global"
    if on & set(EXHIBIT):
        return "final_exhibits"
    if on & set(FINAL):
        return "v2_amendment_3"
    return "v2_amendment_2" if on & set(PARTS) else "v2"


# One configuration through one window, to out/v2/ and the trial ledger.
def run(settings: Settings, window: tuple, fixed: dict | None = None) -> dict:
    fixed = params() if fixed is None else fixed
    started = time.time()
    book, held = walk(universe(window, settings, fixed), settings)
    tag = WINDOWS.get(window, "finals")
    folder = OUT / settings.name / tag
    folder.mkdir(parents=True, exist_ok=True)
    book.to_csv(folder / "returns.csv", lineterminator="\n")
    held.to_parquet(folder / "holdings.parquet", index=False)
    stats = summary(book, tag == "check")
    (folder / "stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    ledger = OUT / "trials.csv"
    row = dict(
        when=pd.Timestamp.now().isoformat(timespec="seconds"),
        protocol=f"docs/protocols/{protocol(settings.on)}.md",
        name=settings.name,
        window=tag,
        capital=settings.capital,
        switches=" ".join(sorted(settings.on)),
        seconds=round(time.time() - started),
        information_ratio=stats["information_ratio"],
    )
    pd.DataFrame([row]).to_csv(
        ledger, mode="a", header=not ledger.exists(), index=False, lineterminator="\n"
    )
    return stats


# The pre-2021 verdicts, as evidence.py last wrote them.
def read_verdicts() -> dict:
    return json.loads((OUT / "evidence.json").read_text(encoding="utf-8"))["verdicts"]


# Core switches that passed their pre-2021 test, `grinold` over `costs`.
def passing(verdicts: dict | None = None) -> frozenset:
    verdicts = read_verdicts() if verdicts is None else verdicts
    passed = {k for k in (*MEMBERS, "grinold") if verdicts.get(k, {}).get("passed")}
    return frozenset(passed - {"costs"} if "grinold" in passed else passed)


# The passing core switches plus passing risk parts, or None.
def final(verdicts: dict | None = None) -> frozenset | None:
    verdicts = read_verdicts() if verdicts is None else verdicts
    if not set(PARTS) & set(verdicts):
        return None
    return passing(verdicts) | {p for p in PARTS if verdicts.get(p, {}).get("passed")}


# The `final` set plus the two tested rules, or None.
def base_three(verdicts: dict | None = None) -> frozenset | None:
    v3 = final(verdicts)
    return None if v3 is None else v3 | set(RULES)


# `base_three` plus each tested switch that passed, or None.
def final_three(verdicts: dict | None = None) -> frozenset | None:
    verdicts = read_verdicts() if verdicts is None else verdicts
    base = base_three(verdicts)
    if base is None or not set(TESTED) & set(verdicts):
        return None
    return base | {p for p in TESTED if verdicts.get(p, {}).get("passed")}


# The run grid: all off, all five, each alone by capital, then extras.
def plan() -> list[Settings]:
    institutional = M.Mandate(name="institutional", pool=480)
    out = [Settings(frozenset(on), cap) for on in ((), V2) for cap in CAPITALS]
    out += [Settings(frozenset([member]), cap) for member in MEMBERS for cap in CAPITALS]
    out += [Settings(on, cap) for on in (V2A, frozenset(["grinold"])) for cap in CAPITALS]
    out += [Settings(frozenset([name])) for name in ("aligned", "industry", "risk")]
    out += [Settings(frozenset(["institutional"]), 1e9, institutional)]
    return out


# Check: with every switch off, this engine matches the shipped book.
def prove(months=("2016-06", "2018-06", "2020-06", "2021-06", "2023-06", "2025-06")) -> float:
    rf = P.benchmarks().set_index("month")["rf"]
    worst = 0.0
    for window in (CHECK, RECORD):
        df = universe(window, Settings(), params())
        previous = None
        for month, weights, info, cross_section, parts, _ in P.walk(df):
            if f"{month:%Y-%m}" in months:
                theirs = P.optimize_month(cross_section, previous)
                mine = optimize(cross_section, previous, Settings())
                both = pd.concat([theirs, mine], axis=1).fillna(0.0)
                worst = max(worst, float((both.iloc[:, 0] - both.iloc[:, 1]).abs().max()))
            cash = rf.get((month + pd.offsets.MonthBegin(1)).normalize(), 0.0)
            previous = P.drift(weights, info, parts, cash)
    return worst


# Crowd what-ifs at $10M, all off and all five: with, against, alone.
def what_if() -> None:
    fixed = params()
    for base in (frozenset(), V2):
        runs = [(Settings(base), CLEAN)]
        for crowd, window in (("retail", CLEAN), ("copycat", CLEAN), ("historical", CHECK)):
            runs += [(Settings(base | {way, crowd}), window) for way in CROWD]
        for settings, window in runs:
            s = run(settings, window, fixed)
            print(f"{settings.name:40s} {WINDOWS[window]:6s} IR {s['information_ratio']:+.2f}")


# A finals run's months: FIAM_WINDOW "FIRST,LAST" for other dates.
def finals_window() -> tuple:
    if not os.environ.get("FIAM_WINDOW"):
        return RECORD
    ends = [pd.Timestamp(x) + pd.offsets.MonthEnd(0) for x in os.environ["FIAM_WINDOW"].split(",")]
    return tuple(f"{x:%Y-%m-%d}" for x in ends)


# A world book's report: country shares and beta to its own market.
def world_report(settings: Settings, window: tuple) -> dict:
    from fiam import world as W

    folder = OUT / settings.name / WINDOWS.get(window, "finals")
    shares = W.country_weights(pd.read_parquet(folder / "holdings.parquet"), data.DIR)
    shares.to_csv(folder / "countries.csv", lineterminator="\n")
    book = pd.read_csv(folder / "returns.csv", index_col="holding_month", parse_dates=True)
    fit = P.regress(book["net"], W.market(data.DIR, settings.mandate.countries).reindex(book.index))
    return dict(
        country_share_max=float(shares.max(axis=1).max()),
        countries_min=int((shares > 0.001).sum(axis=1).min()),
        beta_world=float(fit.params.iloc[1]),
        beta_world_stderr=float(fit.bse.iloc[1]),
    )


# The information ratio against the mandate's hurdle over the T-bill.
def hurdle_ir(settings: Settings, window: tuple) -> float:
    folder = OUT / settings.name / WINDOWS.get(window, "finals")
    active = pd.read_csv(folder / "returns.csv")["net"] - settings.mandate.hurdle / 12
    return float(active.mean() / active.std() * np.sqrt(12)) if active.std() else 0.0


# A finals mandate: refused if impossible, else run by each book.
def finals(path: Path) -> dict:
    mandate = M.load(path)
    problems = M.check(mandate)
    if problems:
        raise SystemExit(f"{path.name} cannot be met: " + "; ".join(problems))
    worldwide = "country" in pq.read_schema(data.FEATURES).names
    missing = sorted(set(mandate.countries) - {"USA"})
    if missing and not worldwide:
        print(
            f"no data loaded for {missing}: the book is all USA, so country rules cannot hold yet."
            f" Add the finals data first:  uv run run.py --world <folder> --finals {path}"
        )
    window = finals_window()
    capital = float(os.environ.get("FIAM_CAPITAL", C.DEFAULT.nav))
    extra = frozenset(WORLD) if worldwide else frozenset()
    fixed, out = params(), {}
    books = [("v1 method", frozenset()), ("v2", V2)]
    chosen = final_three() if (OUT / "evidence.json").exists() else None
    if chosen:
        # Risk targets move a directional net, so only neutral books keep them.
        steady = {"voltarget", "target10", "brake"}
        books.append(("final v3", chosen if mandate.net == 0 else chosen - steady))
    for label, on in books:
        settings = Settings(on | extra, capital, mandate)
        stats = run(settings, window, fixed)
        if worldwide:
            stats |= world_report(settings, window)
        if mandate.hurdle is not None:
            stats["information_ratio_hurdle"] = hurdle_ir(settings, window)
        # Data and rules recorded, so a fake-country rehearsal is not a result.
        stats |= dict(data=data.DIR.name, window=list(window), mandate=M.record(mandate))
        out[label] = dict(run=settings.name, **stats)
        where = f" largest country {stats['country_share_max']:.0%}" if worldwide else ""
        print(
            f"{mandate.name} {label:9s} IR {stats['information_ratio']:+.2f} "
            f"cost {stats['cost_annual']:.2%} names {stats['positions']:.0f} "
            f"breaches {stats['months_breaching']} empty {stats['months_empty']}{where}",
            flush=True,
        )
    if "final v3" in out:
        folder = (OUT / out["final v3"]["run"] / WINDOWS.get(window, "finals")).as_posix()
        world = (
            (" --world fake" if data.DIR.name == "world_fake" else " --world") if worldwide else ""
        )
        print(f"final v3's committee pack:  uv run run.py{world} --pack {folder}")
    report = OUT / "finals" / f"{mandate.name}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    return out


# Usage: uv run -m fiam.v2 [prove|all|finals FILE|grid NAME...|NAME...]
def main(args: list[str]) -> None:
    if args == ["prove"]:
        print(f"largest weight gap, v2 off vs v1: {prove():.2e}")
        return
    if args == ["crowd"]:
        what_if()
        return
    if args[:1] == ["finals"]:
        finals(Path(args[1] if len(args) > 1 else os.environ["FIAM_MANDATE"]))
        return
    grid = args[:1] == ["grid"]
    names = args[1:] if grid else args
    sets = {"v2": V2, "v2a": V2A, "pass": None, "v3": None, "base3": None, "final": None}
    if "pass" in names:
        sets["pass"] = passing()
    for name, pick in (("v3", final), ("base3", base_three), ("final", final_three)):
        if name in names:
            sets[name] = pick()
            if sets[name] is None:
                raise SystemExit(f"{name} needs verdicts first: run its parts, then evidence")
    switches = frozenset().union(*(sets.get(a) or frozenset([a]) for a in names))
    if switches >= COSTED:
        raise SystemExit("costs and grinold are two versions of one fix; switch on one")
    unknown = switches - {*MEMBERS, *OTHERS, *CROWD, *CROWDS, *PARTS, *FINAL, *EXHIBIT, *WORLD}
    if unknown and args != ["all"]:
        raise SystemExit(f"unknown switches {sorted(unknown)}; known: v2 {MEMBERS + OTHERS}")
    capital = float(os.environ.get("FIAM_CAPITAL", C.DEFAULT.nav))
    # The risk dial: FIAM_VOL sets the yearly vol target.
    rules = M.Mandate()
    if "FIAM_VOL" in os.environ:
        vol = float(os.environ["FIAM_VOL"])
        rules = M.Mandate(name=f"risk{round(vol * 100)}", vol_target=vol)
    if grid:
        runs = [Settings(switches, cap, rules) for cap in CAPITALS]
    else:
        runs = plan() if args == ["all"] else [Settings(switches, capital, rules)]
    fixed = params()
    for settings in runs:
        for window in (CHECK, RECORD):
            s = run(settings, window, fixed)
            print(
                f"{settings.name:40s} {'check' if window == CHECK else 'record':6s} "
                f"IR {s['information_ratio']:+.2f} cost {s['cost_annual']:.2%} "
                f"turn {s['turnover']:.0%} beta {s['beta_realized']:+.2f}",
                flush=True,
            )


if __name__ == "__main__":
    main(sys.argv[1:])
