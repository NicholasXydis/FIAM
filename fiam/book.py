# Screen, score, neutralize, size, round to whole shares, charge fees. Writes submission/.

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import kurtosis, norm, skew

from fiam import costs as C
from fiam import data, paths
from fiam.benchmarks import benchmarks
from fiam.exhibits import config_log

# A smoke run keeps its small results apart, so a rehearsal never overwrites a real one.
CACHE = Path("cache/smoke" if paths.SMOKE else "cache")
OUT = paths.SUBMISSION
# The ship decision and its model inputs, committed so anyone rebuilds the same book untrained.
MODELS = paths.SUBMISSION / "models"

# We decide at month end and hold the next, so July 2026 is the last month we can act on.
FIRST_FORECAST, LAST_FORECAST = "2020-12-31", "2026-07-31"
N_HOLDING_MONTHS = 68

# How many of the twelve a stock needs before we trade it. Demanding all twelve is worse.
MIN_SIGNALS = 9

# Only matters for rounding. At $10m, one share of an expensive stock is a real slice.
NAV = 10_000_000.0

# The twelve measures. +1 means higher is better. Signs from theory, fixed before we ran.
SIGNALS = {
    "ivol_capm_21d": -1,
    "be_me": +1,
    "qmj": +1,
    "at_gr1": -1,
    "niq_su": +1,
    "ope_be": +1,
    "chcsho_12m": -1,
    "o_score": -1,
    "ret_12_1": +1,
    "gp_at": +1,
    "noa_gr1a": -1,
    "eqnetis_at": -1,
}

# 160% gross never rose above 200% on any trading day of 2021-25; `pool` is candidates per side.
LIMITS = dict(gross=1.6, beta=0.02, risk=0.02, sector=0.01, name=0.015, pool=200, ridge=30.0)

# The rules' ceiling on names, counting both sides.
MAX_NAMES = 500

# Only the regression proves neutrality, so it fails the build too. The chart shades this band.
REALIZED_BETA_LIMIT = 0.20

# Named once, so the switch to the S&P 500 relabels every output at the same time.
MARKET_NAME = "S&P 500 price index (FRED SP500), excludes dividends"

# Shumway's average loss on performance delistings, applied to missing returns only as a stress.
MISSING_STRESS = 0.30

# Names SEC's dated filer record contradicts: PERMNO, wrong name, right from this date, right name.
LABEL_FIXES = [
    # EDGAR CIK 766829, a typo.
    (54199, "H20 AMERICA", "2025-05-01", "H2O AMERICA"),
    # EDGAR CIK 1502377.
    (22369, "CONTANGO ORE INC", "2026-03-30", "CONTANGO SILVER & GOLD INC"),
]

# Assumed, not measured. Deliberately pessimistic, and stated openly in the deck.


# Loads the stock data and works out which sector each company belongs to.
def load_panel(extra: tuple[str, ...] = ()) -> pd.DataFrame:
    # Only the columns we actually use. Loading all 198 wastes about 2GB of memory.
    cols = (
        list(SIGNALS)
        + list(extra)
        + [
            "permno",
            "eom",
            "prc",
            "me",
            "ret_exc_lead1m",
            "gics",
            "beta_60m",
            "dolvol_126d",
            "size_grp",
            "bidaskhl_21d",
            "rvol_21d",
            "betadown_252d",
            "betabab_1260d",
            "beta_dimson_21d",
            "market_equity",
            "ticker",
            "company_name",
        ]
    )
    panel = data.panel(cols)
    # First two digits give the 11 sectors. No sector gets its own group, never dropped.
    panel["sector"] = panel["gics"].astype("string").str[:2].fillna("XX")
    return panel


# Narrows the list to stocks we would actually be willing to trade.
def screen(
    panel: pd.DataFrame, first: str = FIRST_FORECAST, last: str = LAST_FORECAST, wrds: bool = True
):
    # Never filter on having a future return, that drops the companies that failed.
    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)
    window = panel["eom"].between(first, last)
    # wrds=False is the book a judge rebuilds from the organizer's data alone.
    return settle(panel[keep & window].copy()) if wrds else panel[keep & window].copy()


# Dated delistings and final-month payouts derived from WRDS, or None on a run without them.
@cache
def exits() -> pd.DataFrame | None:
    return data.wrds("exits")


# Drops names delisted by the decision date and books the payout of names that exit next month.
def settle(df: pd.DataFrame) -> pd.DataFrame:
    table = exits()
    if table is None:
        return df
    # Only an exit dated on or before the decision was known then, so no later date is used.
    dead = df["permno"].map(table["exit_date"]) <= df["eom"]
    df = df[~dead].copy()
    df.attrs["dead_at_decision"] = int(dead.sum())
    holding = (df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    final = (
        df["permno"]
        .map(table["final_return"])
        .where(df["permno"].map(table["final_month"]) == holding)
    )
    rf = holding.map(benchmarks().set_index("month")["rf"])
    df["ret_exc_lead1m"] = df["ret_exc_lead1m"].fillna(final - rf)
    return df


# The 147 characteristics the rules name, in their order. The only list a predictor may come from.
def characteristics() -> list[str]:
    return data.characteristics()


# Rank within the month, then z-score, so measures in different units can be averaged.
def rank_z(df: pd.DataFrame, col: str) -> pd.Series:
    r = df.groupby("eom")[col].rank(pct=True)
    mu = r.groupby(df["eom"]).transform("mean")
    sd = r.groupby(df["eom"]).transform("std")
    # A month where every value ties has no ranking, so it scores missing, not infinite.
    return (r - mu) / sd.replace(0.0, np.nan)


# Takes the part of y that moves with x back out, month by month.
def residualize(df: pd.DataFrame, y: pd.Series, x: pd.Series) -> pd.Series:
    bx = x - x.groupby(df["eom"]).transform("mean")
    sy = y - y.groupby(df["eom"]).transform("mean")
    cov = (bx * sy).groupby(df["eom"]).transform("sum")
    var = (bx * bx).groupby(df["eom"]).transform("sum")
    return sy - (cov / var.replace(0.0, np.nan)).fillna(0.0) * bx


# The beta a book is neutral to: the hedge's learned one where a candidate set it, else 60-month.
def hedge(df: pd.DataFrame) -> pd.Series:
    return df["hedge_beta"] if "hedge_beta" in df else df["beta_60m"]


# Every score that reaches the optimizer goes through here, ours and the models' alike.
def neutralize(df: pd.DataFrame, score: pd.Series) -> pd.Series:
    # Compare each stock to its own sector, or a high score just means "in a good sector".
    demeaned = score - score.groupby([df["eom"], df["sector"]]).transform("mean")
    # Strip out the part of the score that is really a bet on the market.
    return residualize(df, demeaned, hedge(df))


# Each signal ranked within its month and signed by theory, one column per signal.
def scores(df: pd.DataFrame, signals: dict) -> pd.DataFrame:
    return pd.concat([rank_z(df, col) * sign for col, sign in signals.items()], axis=1)


# The monthly return of a score held against the demeaned cross-section, keyed on holding month.
def spread(df: pd.DataFrame, signal: pd.Series) -> pd.Series:
    demeaned = df["ret_exc_lead1m"] - df.groupby("eom")["ret_exc_lead1m"].transform("mean")
    monthly = (signal.fillna(0.0) * demeaned).groupby(df["eom"]).mean()
    monthly.index = (pd.DatetimeIndex(monthly.index) + pd.offsets.MonthBegin(1)).normalize()
    return monthly


# How the book is built: each switch is one pre-registered rule of construction v2.
@dataclass(frozen=True)
class Design:
    # Hedge on 0.67 x the mean of the 60-month and Dimson betas, plus 0.33.
    adjusted_beta: bool = False
    # Net exposure allowed either side of zero, so the beta-weighted legs can cancel.
    net_band: float = 0.0
    # No short above 20% short interest, and short caps scaled down for volatile names.
    short_rules: bool = False
    # Every cap scaled so no name carries more impact per dollar than the median (amendment 2).
    liquidity_caps: bool = False
    # Momentum leaves the composite after two years of falling markets (Daniel & Moskowitz 2016).
    crash_protection: bool = False
    # Exposure to five Fama-French characteristics held near zero, so what is left is selection.
    factor_neutral: bool = False


# Size, value, profitability, investment and momentum, as Fama and French build their factors.
FACTORS = ("market_equity", "be_me", "ope_be", "at_gr1", "ret_12_1")

# The construction before Phase 3, and construction v2 as PREREGISTRATION.md fixes it.
CURRENT = Design()
# The factor-neutral book, amendment 4: the current construction plus the five factor limits.
NEUTRAL = Design(factor_neutral=True)
V2 = Design(
    adjusted_beta=True, net_band=0.10, short_rules=True, liquidity_caps=True, crash_protection=True
)
# The construction in force: v2 only if it passed all four of its pre-registered rules.
SHIPPED = CURRENT


# Decision months after the market fell over the past 24 months, the paper's bear-market state.
@cache
def bear_months() -> frozenset:
    bm = benchmarks().set_index("month")
    total = (bm["mkt_rf_crsp"] + bm["rf"]).dropna()
    past = (1 + total).rolling(24).apply(np.prod, raw=True) - 1
    return frozenset(m + pd.offsets.MonthEnd(0) for m, v in past.items() if v < 0)


# Turns the twelve measures into a single score per stock, with unwanted bets removed.
def build_signal(
    df: pd.DataFrame,
    signals: dict | None = None,
    min_signals: int = MIN_SIGNALS,
    design: Design = SHIPPED,
) -> pd.DataFrame:
    # Only a declared challenger passes its own set. The book always uses SIGNALS.
    table = scores(df, SIGNALS if signals is None else signals)
    if design.crash_protection and "ret_12_1" in table:
        table.loc[df["eom"].isin(bear_months()).to_numpy(), "ret_12_1"] = np.nan
    # Equal weight, and most measures present, so scores stay comparable.
    df["n_signals"] = table.notna().sum(axis=1)
    df["composite"] = table.mean(axis=1).where(df["n_signals"] >= min_signals)
    df = df.dropna(subset=["composite", "beta_60m", "bidaskhl_21d"]).copy()
    # The beta every book is neutral to: the 60-month estimate unless a candidate hedges better.
    df["hedge_beta"] = df["beta_60m"]
    if design.adjusted_beta:
        raw = df[["beta_60m", "beta_dimson_21d"]].mean(axis=1)
        df["hedge_beta"] = 0.67 * raw + 0.33
    df["signal"] = neutralize(df, df["composite"])

    # Each name's borrow a year, from its short-interest tier.
    df["borrow"] = C.borrow_rate(df)

    # Leaning away from jumpy stocks is a hidden bet the market falls. Our main finding.
    parts = [
        rank_z(df, col) for col in ("ivol_capm_21d", "rvol_21d", "betadown_252d", "betabab_1260d")
    ]
    df["risk_rank"] = pd.concat(parts, axis=1).mean(axis=1).fillna(0.0)
    if design.factor_neutral:
        for col in FACTORS:
            df[f"factor_{col}"] = rank_z(df, col).fillna(0.0)
    return df


# The shipped universe, built once per code and data version and shared by every script.
def universe() -> pd.DataFrame:
    key = data.signature().encode() + Path(__file__).read_bytes() + Path(C.__file__).read_bytes()
    path = CACHE / f"universe_{hashlib.sha256(key).hexdigest()[:12]}.parquet"
    if path.exists():
        # Parquet stores dates in milliseconds; a fresh build keeps seconds, so restore them.
        return data.read(path)
    built = build_signal(screen(load_panel()))
    CACHE.mkdir(exist_ok=True)
    # Older versions are dead weight once the code or data behind them has changed.
    for stale in CACHE.glob("universe_*.parquet"):
        stale.unlink()
    built.to_parquet(path)
    return built


# Written before any candidate was scored: the composite ships unless another beats it clearly.
HURDLE, MAX_BETA = 0.25, 0.15

# The scorer's share of the blend in each candidate, written before any candidate was scored.
BLENDS = (0.0, 0.25, 0.5)


# A candidate's name: its blend, then each learned part it adds, scorer25+hedged+traded say.
def candidate_name(blend: float, hedged: bool, traded: bool) -> str:
    parts = [f"scorer{round(blend * 100)}" if blend else "composite"]
    return "+".join(parts + ["hedged"] * hedged + ["traded"] * traded)


# The name in words for the tables: Composite + 25% scorer + hedge + trader, say.
def candidate_label(name: str) -> str:
    head, *rest = name.split("+")
    parts = ["Composite"] + ([f"{head[6:]}% scorer"] if head != "composite" else [])
    return " + ".join(parts + [dict(hedged="hedge", traded="trader")[r] for r in rest])


# The 3 x 2 x 2 grid the ship rule chooses from: each blend, with and without each learned part.
CANDIDATES = {
    candidate_name(b, h, t): dict(blend=b, hedge=h, trader=t)
    for b in BLENDS
    for h in (False, True)
    for t in (False, True)
}


# One candidate's signal: the composite, blended with the scorer, neutral to its chosen beta.
def candidate(universe: pd.DataFrame, inputs: pd.DataFrame | None, name: str) -> pd.DataFrame:
    spec = CANDIDATES[name]
    df = (
        universe.copy()
        if inputs is None
        else universe.merge(inputs, on=["permno", "eom"], how="left")
    )
    # Once short-interest reports stop, the crowding teacher sets each name's borrow tier.
    if "crowding_hat" in df:
        df["borrow"] = C.borrow_rate(df)
    if not spec["blend"] and not spec["hedge"]:
        return df
    if spec["hedge"] and "beta_hat" in df:
        df["hedge_beta"] = df["beta_hat"].fillna(df["beta_60m"])
    base = df["composite"]
    if spec["blend"] and "score" in df:
        # A name without a score keeps its composite rank, on the same scale as the blend.
        ranked, score = rank_z(df, "composite"), rank_z(df, "score")
        base = ranked.where(score.isna(), (1 - spec["blend"]) * ranked + spec["blend"] * score)
    df["signal"] = neutralize(df, base)
    return df


# The book's months as the ship rule chose them: each year's candidate and each month's trade.
def shipped(universe: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    policy = paths.read_json(MODELS / "policy.json")
    if not policy:
        return universe, None
    inputs = data.read(MODELS / "book_inputs.parquet")
    year = (universe["eom"] + pd.offsets.MonthBegin(1)).dt.year.astype(str)
    chosen = policy["by_year"]
    parts = [
        candidate(universe[year == y], inputs, chosen.get(y, "composite")) for y in year.unique()
    ]
    return pd.concat(parts, ignore_index=True), policy.get("trades")


# Works out how much to hold in each stock for one month, inside every rule.
def optimize_month(
    month: pd.DataFrame, previous: pd.Series | None = None, design: Design = SHIPPED
) -> pd.Series | None:
    month = month.sort_values("signal")
    # The extremes first; if they cannot make a neutral book at full gross, reach deeper.
    for depth in (LIMITS["pool"], 2 * LIMITS["pool"], len(month)):
        pool = pd.concat([month.tail(depth), month.head(depth)]).drop_duplicates("permno")
        weights = solve(month, pool, previous, design)
        if weights is not None:
            return weights
    return None


# Best score from one pool of candidates without breaking any limit. Exactly one right answer.
def solve(
    month: pd.DataFrame, pool: pd.DataFrame, previous: pd.Series | None, design: Design
) -> pd.Series | None:
    # Held stocks drift out of the pool and get force-sold. Adding them back cut turnover.
    if previous is not None:
        held = month[month["permno"].isin(previous.index) & ~month["permno"].isin(pool["permno"])]
        if not held.empty:
            pool = pd.concat([pool, held])

    a = pool["signal"].to_numpy()
    w = cp.Variable(len(pool))
    # Good scores can only be bought, bad ones only shorted, so the book is explainable.
    side = np.where(a >= 0, 1.0, -1.0)
    cap = caps(month, pool, side, design)
    lo, hi = np.minimum(side, 0) * cap, np.maximum(side, 0) * cap
    constraints = [
        # Dollar neutral, or inside the design's band so the beta-weighted legs can cancel.
        cp.sum(w) == 0 if not design.net_band else cp.abs(cp.sum(w)) <= design.net_band,
        # Signs are fixed, so gross is linear and exact; at 1.5% a name that means 107+ names.
        side @ w == LIMITS["gross"],
        w >= lo,
        # Per-name cap, sign matches the signal.
        w <= hi,
    ]
    beta = hedge(pool).to_numpy()
    risk = pool["risk_rank"].to_numpy()
    sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)
    constraints += [
        # Beta neutral on the hedge beta.
        cp.abs(beta @ w) <= LIMITS["beta"],
        # And neutral on the volatility complex.
        cp.abs(risk @ w) <= LIMITS["risk"],
        cp.abs(sectors.T @ w) <= LIMITS["sector"],
    ]
    # The factor-neutral design holds each Fama-French exposure inside the volatility limit.
    if design.factor_neutral:
        exposures = pool[[f"factor_{col}" for col in FACTORS]].to_numpy()
        constraints.append(cp.abs(exposures.T @ w) <= LIMITS["risk"])
    # Chase the score but penalise big positions, or we end up with 144 stocks and a 43% loss.
    objective = a @ w - 0.5 * LIMITS["ridge"] * cp.sum_squares(w)
    problem = cp.Problem(cp.Maximize(objective), constraints)
    problem.solve(solver=cp.CLARABEL)
    if w.value is None:
        return None
    weights = pd.Series(w.value, index=pool["permno"].to_numpy())
    kept = weights[weights.abs() > 1e-5]
    # Only a banded design carries its chosen net into the whole-share repair.
    if design.net_band:
        kept.attrs["net"] = float(kept.sum())
    return kept


# Each name's cap: 1.5%, scaled down by the design's liquidity and short rules; 0 where banned.
def caps(month: pd.DataFrame, pool: pd.DataFrame, side: np.ndarray, design: Design) -> np.ndarray:
    cap = np.full(len(pool), LIMITS["name"])
    if design.liquidity_caps:
        impact = (month["rvol_21d"] / np.sqrt(month["dolvol_126d"])).median()
        own = (pool["rvol_21d"] / np.sqrt(pool["dolvol_126d"])).fillna(impact).to_numpy()
        cap = cap * np.minimum(1.0, impact / own)
    if design.short_rules:
        vol = pool["rvol_21d"].fillna(month["rvol_21d"].median()).to_numpy()
        short_cap = LIMITS["name"] * np.minimum(1.0, month["rvol_21d"].median() / vol)
        banned = pool["borrow"].to_numpy() >= C.TIERS[-1][1]
        cap = np.where(side < 0, np.where(banned, 0.0, np.minimum(cap, short_cap)), cap)
    return cap


# Converts target position sizes into whole numbers of shares.
def to_whole_shares(weights: pd.Series, prices: pd.Series) -> pd.Series:
    # You cannot buy half a share. Truncate first, then the repair below adds whole shares back.
    px = prices.reindex(weights.index).astype(float)
    shares = np.trunc(weights * NAV / px)
    held = shares * px / NAV

    # Rounding shrinks both sides; each pass adds a share to every name on the smaller one.
    # A dollar-neutral book is repaired to zero; a banded one to the net its optimizer chose.
    target = weights.attrs.get("net", 0.0)
    for _ in range(500):
        residual = held.sum() - target
        if abs(residual) < 1e-5:
            break
        # If we are holding more than we are shorting, add to a short, and vice versa.
        side = held[held < 0] if residual > 0 else held[held > 0]
        shortfall = (weights[side.index].abs() - side.abs()).sort_values(ascending=False)
        added = False
        for name in shortfall.index:
            residual = held.sum() - target
            if px[name] / NAV <= abs(residual) + 1e-12:
                shares[name] += -1 if residual > 0 else 1
                held = shares * px / NAV
                added = True
        if not added:
            break
    return held[held.abs() > 1e-9]


# Each cost line of moving from last month's book to this one, and one-way turnover.
def trading_cost(
    weights: pd.Series,
    previous: pd.Series | None,
    quotes: pd.DataFrame,
    previous_quotes: pd.DataFrame | None,
    model: C.Model = C.DEFAULT,
) -> tuple[dict, float]:
    # Both months' names, so selling out of a position still counts as a trade.
    before = pd.Series(dtype=float) if previous is None else previous
    idx = weights.index.union(before.index)
    traded = weights.reindex(idx, fill_value=0.0) - before.reindex(idx, fill_value=0.0)
    # A name we are exiting is priced on last month's quotes; any gap takes the month's median.
    known = quotes.reindex(idx)
    if previous_quotes is not None:
        known = known.combine_first(previous_quotes.reindex(idx))
    numeric = known.drop(columns="size_grp")
    known[numeric.columns] = numeric.fillna(quotes[numeric.columns].median())
    parts = C.month_costs(traded, weights, known, model)
    # Turnover is quoted one way throughout, so halve the two-way total.
    return parts, float(traded.abs().sum() / 2)


# Part of the way from last month's book to the target, at the trader's gross, still neutral.
def blend(
    target: pd.Series, previous: pd.Series, listed: pd.Index, rate: float, gross: float
) -> pd.Series:
    # A held name that left the tradable list is sold in full; the rest move part of the way.
    kept = previous[previous.index.isin(listed)].reindex(target.index.union(previous.index))
    kept = kept.fillna(0.0)
    scaled = target.reindex(kept.index).fillna(0.0) * gross / LIMITS["gross"]
    mixed = (1 - rate) * kept + rate * scaled
    # Crumbs under five basis points are sold, and the book never passes the rules' 500 names.
    mixed = mixed[mixed.abs() >= 5e-4]
    mixed = mixed.loc[mixed.abs().nlargest(MAX_NAMES).index]
    # Each side back to half the gross, no name past the cap, the larger side trimmed to match.
    longs, shorts = fill(mixed.clip(lower=0), gross / 2), -fill(-mixed.clip(upper=0), gross / 2)
    side = min(longs.sum(), -shorts.sum())
    return (longs * side / longs.sum()).add(shorts * side / -shorts.sum(), fill_value=0.0)


# Scales one side to its total with no name past the cap, spreading what capped names cannot take.
def fill(side: pd.Series, total: float) -> pd.Series:
    side, cap = side[side > 0], LIMITS["name"]
    for _ in range(50):
        capped = side >= cap - 1e-15
        room = total - cap * capped.sum()
        free = side[~capped]
        if room <= 0 or free.empty or abs(side.sum() - total) < 1e-12:
            break
        side = side.where(capped, free * room / free.sum()).clip(upper=cap)
    return side


# One month of any book: optimize, round to whole shares, charge costs. Every backtest uses it.
def rebalance(
    cross_section: pd.DataFrame,
    previous: pd.Series | None,
    previous_quotes: pd.DataFrame | None,
    optimize=optimize_month,
    round_shares: bool = True,
    trade: tuple[float, float] | None = None,
    model: C.Model = C.DEFAULT,
) -> tuple | None:
    weights = optimize(cross_section, previous)
    # No solution and an empty book both come back as None. The caller decides what that means.
    if weights is None or not len(weights):
        return None
    if trade is not None and previous is not None:
        weights = blend(weights, previous, pd.Index(cross_section["permno"]), *trade)
    info = cross_section.set_index("permno").loc[weights.index]
    if round_shares:
        weights = to_whole_shares(weights, info["prc"].abs())
        # Rounding can drop a stock entirely, so re-sync.
        info = info.loc[weights.index]
        if not len(weights):
            return None
    quotes = cross_section.set_index("permno")[C.COLUMNS]
    parts, turnover = trading_cost(weights, previous, quotes, previous_quotes, model)
    return weights, info, quotes, parts, turnover


# Weights after a month of total returns, as a share of the NAV that month left behind.
def drift(weights: pd.Series, info: pd.DataFrame, parts: dict, rf: float) -> pd.Series | None:
    if not len(weights):
        return None
    # A name with no return is cash for the month, so it earns the cash rate and nothing else.
    returns = info["ret_exc_lead1m"].reindex(weights.index).fillna(0.0)
    net = (weights * returns).sum() - sum(parts.values())
    return weights * (1 + rf + returns) / (1 + rf + net)


# Walks any book through its months, trading each month from the book the last one left behind.
def walk(
    universe: pd.DataFrame,
    optimize=optimize_month,
    round_shares: bool = True,
    trades: dict | None = None,
    model: C.Model = C.DEFAULT,
):
    rf = benchmarks().set_index("month")["rf"]
    previous, previous_quotes = None, None
    for month in sorted(universe["eom"].unique()):
        cross_section = universe[universe["eom"] == month]
        trade = (trades or {}).get(pd.Timestamp(month).strftime("%Y-%m-%d"))
        step = rebalance(
            cross_section, previous, previous_quotes, optimize, round_shares, trade, model
        )
        # No view means an empty book that pays to exit. Dropping the month would be survivorship.
        if step is None:
            weights, info = pd.Series(dtype=float), cross_section.set_index("permno").iloc[:0]
            quotes = cross_section.set_index("permno")[C.COLUMNS]
            parts, turnover = trading_cost(weights, previous, quotes, previous_quotes, model)
        else:
            weights, info, quotes, parts, turnover = step
        yield month, weights, info, cross_section, parts, turnover
        # An empty month leaves nothing to carry, so the next one is charged as a full entry.
        cash = rf.get((month + pd.offsets.MonthBegin(1)).normalize(), 0.0)
        previous, previous_quotes = drift(weights, info, parts, cash), quotes


# Any score through the book, month by month. Returns what each month earned and cost.
def backtest(
    universe: pd.DataFrame,
    optimize=optimize_month,
    round_shares: bool = True,
    trades: dict | None = None,
    model: C.Model = C.DEFAULT,
) -> pd.DataFrame:
    steps = walk(universe, optimize, round_shares, trades, model)
    rows = [month_record(*step) for step in steps]
    book = pd.DataFrame(rows).set_index("holding_month")
    book.attrs["months_with_no_position"] = int((book["n"] == 0).sum())
    return book


# IR against T-bill plus 4%. At zero net exposure the T-bill cancels, so only the 4% comes off.
def information_ratio(net: pd.Series) -> float:
    active = net - 0.04 / 12
    return float(active.mean() / active.std() * np.sqrt(12)) if active.std() else 0.0


# IR and beta over a window of holding months: what the ship rule reads for each candidate.
def judge(net: pd.Series, first: str, last: str) -> dict:
    part = net.loc[first:last]
    fit = regress(part, benchmarks().set_index("month")["mkt_rf"].reindex(part.index))
    return dict(information_ratio=information_ratio(part), beta=float(fit.params.iloc[1]))


# Each year's book: the composite, unless an alternative beat it on the two years before.
def choose(books: dict, year: int) -> tuple[str, dict]:
    first, last = f"{year - 2}-01-01", f"{year - 1}-12-01"
    scores = {name: judge(b["net"], first, last) for name, b in books.items()}
    base = scores["composite"]["information_ratio"]
    fit = {
        n: s
        for n, s in scores.items()
        if n != "composite"
        and s["information_ratio"] >= base + HURDLE
        and abs(s["beta"]) <= MAX_BETA
    }
    best = max(fit, key=lambda n: fit[n]["information_ratio"]) if fit else "composite"
    # The hedge follows neutrality: the twin with the other beta ships if its beta sat nearer zero.
    spec = CANDIDATES[best]
    twin = candidate_name(spec["blend"], not spec["hedge"], spec["trader"])
    if twin in scores and abs(scores[twin]["beta"]) < abs(scores[best]["beta"]):
        best = twin
    return best, scores


# The figures every research book is compared on, computed one way.
def book_stats(book: pd.DataFrame) -> dict:
    return dict(
        information_ratio=information_ratio(book["net"]),
        gross_annual=float(book["gross"].mean() * 12),
        net_annual=float(book["net"].mean() * 12),
        cost_annual=float(book["cost"].mean() * 12),
        turnover=float(book["turnover"].mean()),
        positions=float(book["n"].mean()),
        months=int(len(book)),
    )


# The limits every research book clears, so no variant wins by breaking one.
def assert_limits(book: pd.DataFrame) -> None:
    assert book["n"].between(100, 500).all(), "position count outside 100-500"
    assert (book["gross_exposure"] <= 2.0 + 1e-9).all(), "gross above 200%"
    assert (book["net_exposure"].abs() < 0.005).all(), "net exposure outside tolerance"


# Puts an outside score where the composite was. Everything after it is the shipped code.
def swap_score(universe: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    scores = scores.assign(eom=pd.to_datetime(scores["eom"]))
    merged = universe.merge(scores[["permno", "eom", "pred"]], on=["permno", "eom"], how="inner")
    # A flat month would divide by zero, so it scores flat rather than being dropped.
    merged["signal"] = neutralize(merged, rank_z(merged, "pred").fillna(0.0))
    return merged


# Monthly Spearman IC of a score against the return it predicts, with its t-statistic.
def information_coefficient(
    frame: pd.DataFrame, score: str = "pred", actual: str = "actual", month: str = "holding_month"
) -> dict:
    scored = frame.dropna(subset=[actual])
    ic = (
        scored.groupby(month)
        .apply(lambda g: g[score].corr(g[actual], method="spearman"), include_groups=False)
        .dropna()
    )
    t = float(ic.mean() / ic.std() * np.sqrt(len(ic))) if ic.std() else 0.0
    return dict(ic_mean=float(ic.mean()), ic_t=t, months=int(len(ic)))


# OLS with Newey-West errors. Monthly returns are autocorrelated, so plain errors flatter.
def regress(y: pd.Series, x: pd.Series | pd.DataFrame):
    both = pd.concat([y.rename("_y"), x], axis=1, sort=True).dropna()
    exog = sm.add_constant(both.drop(columns="_y"))
    return sm.OLS(both["_y"], exog).fit(cov_type="HAC", cov_kwds={"maxlags": 6})


# A name for display: SEC's state-of-incorporation tag such as "/DE" comes off, nothing else.
def display_name(name) -> str:
    return re.sub(r"\s*[/\\]+(?:[A-Z]{2}[/\\]?)?\s*$", "", str(name)).strip()


# Blank labels take the stock's latest panel label on or before the decision month, never later.
def fill_labels(holdings: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    known = panel.loc[panel["ticker"].notna(), ["permno", "eom", "ticker", "company_name"]]
    # merge_asof needs the same time unit on both sides and both sorted on it.
    known = known.assign(eom=known["eom"].astype("datetime64[ns]")).sort_values("eom")
    known["label_month"] = known["eom"]
    book = holdings.assign(eom=holdings["eom"].astype("datetime64[ns]")).sort_values("eom")
    filled = pd.merge_asof(
        book, known, on="eom", left_by="PERMNO", right_by="permno", direction="backward"
    )
    # Kept so the label-source exhibit can say which month each borrowed label came from.
    filled["backfilled"] = filled["TICKER"].isna()
    filled["TICKER"] = filled["TICKER"].fillna(filled["ticker"])
    filled["COMPANY_NAME"] = filled["COMPANY_NAME"].fillna(filled["company_name"])
    # A fix applies only to decisions made after SEC recorded the name, so none reads ahead.
    for permno, wrong, since, right in LABEL_FIXES:
        hit = filled["PERMNO"].eq(permno) & filled["COMPANY_NAME"].eq(wrong)
        filled.loc[hit & (filled["eom"] >= since), "COMPANY_NAME"] = right
    return filled.sort_values(["Date", "PERMNO"])


# The holdings file exactly as the rules name its columns, weight in % of NAV.
def write_holdings(filled: pd.DataFrame) -> None:
    out = filled[["Date", "PERMNO", "TICKER", "COMPANY_NAME", "WEIGHT"]]
    out = out.rename(columns={"COMPANY_NAME": "COMPANY NAME"}).round({"WEIGHT": 6})
    out.to_csv(OUT / "holdings.csv", index=False, lineterminator="\n")
    # Every borrowed label with its source month. The label check folds it into its exhibit.
    borrowed = filled[filled["backfilled"]]
    CACHE.mkdir(exist_ok=True)
    borrowed[["Date", "PERMNO", "label_month"]].to_parquet(CACHE / "label_sources.parquet")


# Everything we record about one month. The checks and the write-up read these numbers.
def month_record(
    month: pd.Timestamp,
    weights: pd.Series,
    info: pd.DataFrame,
    cross_section: pd.DataFrame,
    parts: dict,
    turnover: float,
) -> dict:
    # A missing return usually means the company failed, so count it zero, never drop it.
    missing = info["ret_exc_lead1m"].isna()
    shorts = weights[weights < 0]
    # Hard to borrow means a tier of 3% a year or more.
    htb_weight = shorts[info.loc[shorts.index, "borrow"].to_numpy() >= 0.03].abs().sum()
    gross_ret = (weights * info["ret_exc_lead1m"].fillna(0.0)).sum()
    cost = sum(parts.values())
    return dict(
        forecast_eom=month,
        holding_month=(month + pd.offsets.MonthBegin(1)).normalize(),
        gross=gross_ret,
        cost=cost,
        net=gross_ret - cost,
        **parts,
        turnover=turnover,
        beta=(weights * hedge(info)).sum(),
        net_exposure=weights.sum(),
        gross_exposure=weights.abs().sum(),
        n=len(weights),
        max_sector=weights.groupby(info["sector"].to_numpy()).sum().abs().max(),
        max_weight=weights.abs().max(),
        htb_share=htb_weight / max(shorts.abs().sum(), 1e-12),
        missing_long_weight=weights[missing & (weights > 0)].sum(),
        missing_short_weight=weights[missing & (weights < 0)].abs().sum(),
        min_signals=cross_section["n_signals"].min(),
    )


# Runs the whole thing, one month at a time, then writes the files we hand in.
def run() -> dict:
    panel = load_panel()
    book_universe, trades = shipped(universe())
    months = sorted(book_universe["eom"].unique())
    assert len(months) == N_HOLDING_MONTHS, f"expected {N_HOLDING_MONTHS}, got {len(months)}"

    rows, holdings = [], []
    for step in walk(book_universe, trades=trades):
        month, weights, info = step[:3]
        if not len(weights):
            raise RuntimeError(f"optimizer failed for {month:%Y-%m}")
        record = month_record(*step)
        rows.append(record)
        holdings.append(
            pd.DataFrame(
                dict(
                    Date=record["holding_month"],
                    PERMNO=weights.index,
                    TICKER=info["ticker"].to_numpy(),
                    COMPANY_NAME=info["company_name"].to_numpy(),
                    WEIGHT=weights.to_numpy() * 100,
                    eom=month,
                )
            )
        )

    book = pd.DataFrame(rows).set_index("holding_month")
    check_compliance(book, traded=bool(trades))
    OUT.mkdir(exist_ok=True)
    (OUT / "exhibits").mkdir(exist_ok=True)
    write_holdings(fill_labels(pd.concat(holdings), panel))
    stats = performance(book)
    beta = stats["performance"]["beta_realized"]
    assert abs(beta) <= REALIZED_BETA_LIMIT, f"realized beta {beta:+.2f} outside the neutral band"
    # Total return, not just the spread, because that is what an investor earned.
    bm = benchmarks().set_index("month")
    out = book.join(bm[["rf"]], how="left")
    out["portfolio_total_return"] = out["rf"] + out["net"]
    out["active_return"] = out["portfolio_total_return"] - (out["rf"] + 0.04 / 12)
    out.reset_index().to_csv(OUT / "returns.csv", index=False, lineterminator="\n")
    paths.write_json(OUT / "metrics.json", stats, rounded=False, default=str)
    return stats


# Checks the finished portfolio against every competition rule and stops if one is broken.
def check_compliance(book: pd.DataFrame, traded: bool = False) -> None:
    # Stops the run rather than warning. Whole shares cannot hit a target exactly.
    assert len(book) == N_HOLDING_MONTHS, f"{len(book)} holding months"
    assert book["net_exposure"].abs().max() < SHIPPED.net_band + 0.005, "net exposure outside band"
    assert book["gross_exposure"].max() <= 2.0, "gross above 200%"
    assert book["n"].between(100, 500).all(), "position count outside 100-500"
    # A traded month keeps part of last month's book, so its tilts are looser but still small.
    assert book["beta"].abs().max() <= (0.10 if traded else 0.03), "beta drift beyond tolerance"
    assert book["max_sector"].max() <= (0.05 if traded else 0.015), "sector tilt beyond tolerance"
    # Rounding a 1.50% target can land above it, so state the real cap, not the target.
    assert book["max_weight"].max() <= LIMITS["name"] * 1.10, "position cap breached after rounding"


# A slow result kept under a hash of everything it depends on, rebuilt only when one changes.
def cached(name: str, depends: list, build):
    key = hashlib.sha256(repr(depends).encode()).hexdigest()[:16]
    path = CACHE / "results" / f"{name}_{key}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    value = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Older versions of the same result are dead weight once their inputs have changed.
    for stale in path.parent.glob(f"{name}_*.pkl"):
        stale.unlink()
    pd.to_pickle(value, path)
    return value


# One hash of the code, prompts and pins. Same code, same hash, on any machine.
def source_fingerprint() -> dict:
    files = [*Path("fiam").rglob("*.py"), *Path("prompts").rglob("*")]
    files += [Path("run.py"), Path("requirements.txt")]
    files = sorted((f for f in files if f.is_file()), key=lambda f: f.as_posix())
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.as_posix().encode() + path.read_bytes())
    return {"code_sha256": digest.hexdigest()[:16]}


# Rounds the numbers once, just before saving; kept here so every module can reach it as P.
round_floats = paths.round_floats


# Deflated Sharpe. Returns a PROBABILITY our Sharpe beats zero, not a Sharpe ratio.
def deflated_sharpe(excess: pd.Series, trials: int) -> tuple[float, float]:
    # Works out how high luck alone pushes the best of many tries, then if we beat it.
    n = len(excess)
    # Monthly, scaled to a year only at the end.
    sr = excess.mean() / excess.std()
    g3, g4 = skew(excess), kurtosis(excess, fisher=False)
    euler = 0.5772156649
    sr0 = np.sqrt(1 / n) * (
        (1 - euler) * norm.ppf(1 - 1 / trials) + euler * norm.ppf(1 - 1 / (trials * np.e))
    )
    z = ((sr - sr0) * np.sqrt(n - 1)) / np.sqrt(1 - g3 * sr + ((g4 - 1) / 4) * sr**2)
    return float(norm.cdf(z)), float(sr0 * np.sqrt(12))


# Adds the return series every statistic is built from. Returns the frame and the regression.
def _returns(book: pd.DataFrame):
    df = book.join(benchmarks().set_index("month"), how="left")
    if df["rf"].isna().any():
        raise RuntimeError("TB3MS does not cover the holding window")

    # Equal long and short cancels an unknown cash rate buried in the data.
    df["total"] = df["rf"] + df["net"]
    df["active"] = df["total"] - (df["rf"] + 0.04 / 12)
    df["excess"] = df["total"] - df["rf"]

    # Market data lags a month. Returns use every month, the comparison uses fewer.
    regression = df.dropna(subset=["mkt_rf"])
    return df, regression, regress(regression["excess"], regression["mkt_rf"])


# Return and risk figures, plus the market regression.
def _performance_stats(df, regression, fit) -> dict:
    # An investor holds the cash too, so growth and worst-loss use total return.
    cum = (1 + df["total"]).cumprod()
    cum_spread = (1 + df["net"]).cumprod()
    return {
        "return_gross_annual": df["gross"].mean() * 12,
        "return_net_annual": df["net"].mean() * 12,
        "return_total_cagr": cum.iloc[-1] ** (12 / len(df)) - 1,
        "volatility_annual": df["net"].std() * np.sqrt(12),
        "information_ratio": df["active"].mean() / df["active"].std() * np.sqrt(12),
        "sharpe_ratio": df["excess"].mean() / df["excess"].std() * np.sqrt(12),
        "max_drawdown_total": (cum / cum.cummax() - 1).min(),
        "max_drawdown_spread": (cum_spread / cum_spread.cummax() - 1).min(),
        "hit_rate_positive_active_months": (df["active"] > 0).mean(),
        "alpha_annual": fit.params.iloc[0] * 12,
        "alpha_tstat": fit.tvalues.iloc[0],
        "alpha_stderr_annual": fit.bse.iloc[0] * 12,
        "beta_realized": fit.params.iloc[1],
        "beta_stderr": fit.bse.iloc[1],
        "correlation_with_market": regression["excess"].corr(regression["mkt_rf"]),
    }


# What the result looks like if our assumptions are wrong.
def _robustness_stats(df: pd.DataFrame) -> dict:
    # Missing returns are booked at zero. Stress: exits lose 30%, only when long, then both sides.
    conservative = df["net"] - df["missing_long_weight"] * MISSING_STRESS
    symmetric = conservative + df["missing_short_weight"] * MISSING_STRESS

    # Narrow count is attempts that could have shipped, broad is every fit. Both from the ledger.
    eligible, everything = config_log.attempts()
    dsr_eligible, luck_eligible = deflated_sharpe(df["excess"], eligible)
    dsr_all, luck_all = deflated_sharpe(df["excess"], everything)
    return {
        "attempts_eligible": eligible,
        "attempts_all": everything,
        "deflated_sharpe_probability_eligible": dsr_eligible,
        "deflated_sharpe_probability_all": dsr_all,
        "sharpe_luck_alone_eligible": luck_eligible,
        "sharpe_luck_alone_all": luck_all,
        "ir_missing_returns_conservative": information_ratio(conservative),
        "ir_missing_returns_symmetric": information_ratio(symmetric),
        "missing_long_weight_monthly": df["missing_long_weight"].mean(),
        "missing_short_weight_monthly": df["missing_short_weight"].mean(),
    }


# Every statistic we report, from the finished portfolio.
def performance(book: pd.DataFrame) -> dict:
    df, regression, fit = _returns(book)

    # The results file cannot hold comments, so it starts by explaining itself.
    stats = {
        "_about": {
            "what": "One run of fiam/book.py. The source of truth for every number.",
            "regenerate": "uv run run.py --official",
            "sections": {
                "run": "which code made it, and over which months",
                "performance": "returns, risk, and the market regression",
                "costs": "what trading and borrowing took out",
                "compliance": "competition limits, measured after rounding to whole shares",
                "robustness": "what happens if our assumptions are wrong",
                "notes": "caveats that belong next to the numbers",
                "basis": "IR and Sharpe on excess return. CAGR and drawdown on total return.",
            },
            "rounding": "6 decimals, applied once on write. Maths runs at full precision.",
        },
        "run": {
            **source_fingerprint(),
            "holding_months": len(df),
            "window": f"{df.index.min():%Y-%m} to {df.index.max():%Y-%m}",
        },
        "performance": _performance_stats(df, regression, fit),
        "costs": {
            "cost_annual": df["cost"].mean() * 12,
            "cost_share_of_gross": df["cost"].sum() / df["gross"].sum(),
            "turnover_monthly_one_way": df["turnover"].mean(),
            "hard_to_borrow_share_of_short_book": df["htb_share"].mean(),
        },
        "compliance": {
            "positions_average": df["n"].mean(),
            "net_exposure_max_abs": df["net_exposure"].abs().max(),
            "gross_exposure_max": df["gross_exposure"].max(),
            "sector_tilt_max": df["max_sector"].max(),
            "position_weight_max": df["max_weight"].max(),
            "beta_exante_weighted_mean": df["beta"].mean(),
        },
        "robustness": _robustness_stats(df),
        "notes": {
            "market_series": MARKET_NAME,
            "tradable_universe": "screened on dated WRDS exits, final-month payouts booked"
            if exits() is not None
            else "PROVISIONAL: no WRDS exits file, delisted names not screened",
            "regression_months": len(regression),
            "status": "research backtest; the same code and data give the same numbers anywhere",
        },
    }
    return round_floats(stats)


if __name__ == "__main__":
    for k, v in run().items():
        print(f"{k:24s} {v}")
