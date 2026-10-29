# Screen, score, neutralize, size, round and cost. Writes frozen/v1/.

from __future__ import annotations

import hashlib
import re
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

# A smoke run caches apart, so a rehearsal never overwrites a real run.
CACHE = Path("cache/smoke" if paths.SMOKE else "cache")
OUT = paths.SUBMISSION
# Ship decision and inputs, committed so anyone rebuilds untrained.
MODELS = paths.SUBMISSION / "models"

# Decide at month end, hold the next, so July 2026 is the last decision.
FIRST_FORECAST, LAST_FORECAST = "2020-12-31", "2026-07-31"
N_HOLDING_MONTHS = 68

# How many of the twelve measures a stock needs to qualify.
MIN_SIGNALS = 9

# Only matters for rounding. At $10m one pricey share is a real slice.
NAV = 10_000_000.0

# Twelve measures, each signed by theory.
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

# The book's limits; `pool` is the candidates per side.
LIMITS = dict(gross=1.6, beta=0.02, risk=0.02, sector=0.01, name=0.015, pool=200, ridge=30.0)


# Only the regression proves neutrality, so it fails the build too.
REALIZED_BETA_LIMIT = 0.20

# Named once, so a switch to the S&P 500 relabels every output at once.
MARKET_NAME = "S&P 500 price index (FRED SP500), excludes dividends"

# Shumway's performance-delisting loss, a stress on missing returns.
MISSING_STRESS = 0.30

# Panel names that SEC filer records correct: PERMNO, old, from, new.
LABEL_FIXES = [
    # EDGAR CIK 766829, a typo.
    (54199, "H20 AMERICA", "2025-05-01", "H2O AMERICA"),
    # EDGAR CIK 1502377.
    (22369, "CONTANGO ORE INC", "2026-03-30", "CONTANGO SILVER & GOLD INC"),
]

# Assumed, not measured. Deliberately pessimistic, stated in the deck.


# Loads the stock data and works out each company's sector.
def load_panel(extra: tuple[str, ...] = ()) -> pd.DataFrame:
    # Only the columns we use. Loading all 198 wastes about 2GB of memory.
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
    # Two GICS digits give 11 sectors. No sector is its own group, kept.
    panel["sector"] = panel["gics"].astype("string").str[:2].fillna("XX")
    return panel


# Narrows the list to stocks we would actually be willing to trade.
def screen(
    panel: pd.DataFrame, first: str = FIRST_FORECAST, last: str = LAST_FORECAST, wrds: bool = True
):
    # Price and size only, never a return, so failed firms stay in.
    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)
    window = panel["eom"].between(first, last)
    # wrds=False is the book anyone rebuilds from organizer data alone.
    return settle(panel[keep & window].copy()) if wrds else panel[keep & window].copy()


# Dated delistings and final-month payouts from WRDS, or None without.
@cache
def exits() -> pd.DataFrame | None:
    return data.wrds("exits")


# Drops names delisted by decision date, books next-month exit payouts.
def settle(df: pd.DataFrame) -> pd.DataFrame:
    table = exits()
    if table is None:
        return df
    # Only an exit dated by the decision is known then, so no later one.
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


# The 147 characteristics the rules name, the only source of predictors.
def characteristics() -> list[str]:
    return data.characteristics()


# Rank within the month, then z-score, so mixed units can be averaged.
def rank_z(df: pd.DataFrame, col: str) -> pd.Series:
    r = df.groupby("eom")[col].rank(pct=True)
    mu = r.groupby(df["eom"]).transform("mean")
    sd = r.groupby(df["eom"]).transform("std")
    # A month of all ties has no ranking, so missing, not infinite.
    return (r - mu) / sd.replace(0.0, np.nan)


# Takes the part of y that moves with x back out, month by month.
def residualize(df: pd.DataFrame, y: pd.Series, x: pd.Series) -> pd.Series:
    bx = x - x.groupby(df["eom"]).transform("mean")
    sy = y - y.groupby(df["eom"]).transform("mean")
    cov = (bx * sy).groupby(df["eom"]).transform("sum")
    var = (bx * bx).groupby(df["eom"]).transform("sum")
    return sy - (cov / var.replace(0.0, np.nan)).fillna(0.0) * bx


# The beta a book is neutral to: the learned one, else the 60-month one.
def hedge(df: pd.DataFrame) -> pd.Series:
    return df["hedge_beta"] if "hedge_beta" in df else df["beta_60m"]


# Every score reaching the optimizer passes here, ours and the models'.
def neutralize(df: pd.DataFrame, score: pd.Series) -> pd.Series:
    # Compare each stock to its sector, or a high score means a good sector.
    demeaned = score - score.groupby([df["eom"], df["sector"]]).transform("mean")
    # Strip out the part of the score that is really a bet on the market.
    return residualize(df, demeaned, hedge(df))


# Each signal ranked in its month and signed by theory, one column each.
def scores(df: pd.DataFrame, signals: dict) -> pd.DataFrame:
    return pd.concat([rank_z(df, col) * sign for col, sign in signals.items()], axis=1)


# A score's monthly return on demeaned returns, keyed on holding month.
def spread(df: pd.DataFrame, signal: pd.Series) -> pd.Series:
    demeaned = df["ret_exc_lead1m"] - df.groupby("eom")["ret_exc_lead1m"].transform("mean")
    monthly = (signal.fillna(0.0) * demeaned).groupby(df["eom"]).mean()
    monthly.index = (pd.DatetimeIndex(monthly.index) + pd.offsets.MonthBegin(1)).normalize()
    return monthly


# Size, value, profitability, investment, momentum: Fama-French factors.
FACTORS = ("market_equity", "be_me", "ope_be", "at_gr1", "ret_12_1")


# The twelve measures as one score per stock, unwanted bets removed.
def build_signal(
    df: pd.DataFrame, signals: dict | None = None, min_signals: int = MIN_SIGNALS
) -> pd.DataFrame:
    # Only a declared challenger passes its own set. The book uses SIGNALS.
    table = scores(df, SIGNALS if signals is None else signals)
    # Equal weight, and most measures present, so scores stay comparable.
    df["n_signals"] = table.notna().sum(axis=1)
    df["composite"] = table.mean(axis=1).where(df["n_signals"] >= min_signals)
    df = df.dropna(subset=["composite", "beta_60m", "bidaskhl_21d"]).copy()
    # Neutral to the 60-month beta until the learned hedge replaces it.
    df["hedge_beta"] = df["beta_60m"]
    df["signal"] = neutralize(df, df["composite"])

    # Each name's borrow a year, from its short-interest tier.
    df["borrow"] = C.borrow_rate(df)

    # Shunning jumpy stocks is a hidden bet the market falls. Main finding.
    parts = [
        rank_z(df, col) for col in ("ivol_capm_21d", "rvol_21d", "betadown_252d", "betabab_1260d")
    ]
    df["risk_rank"] = pd.concat(parts, axis=1).mean(axis=1).fillna(0.0)
    return df


# The shipped universe, built once per code and data version, shared.
def universe() -> pd.DataFrame:
    key = data.signature().encode() + Path(__file__).read_bytes() + Path(C.__file__).read_bytes()
    path = CACHE / f"universe_{hashlib.sha256(key).hexdigest()[:12]}.parquet"
    if path.exists():
        # Parquet keeps dates in ms, a fresh build in seconds, so restore them.
        return data.read(path)
    built = build_signal(screen(load_panel()))
    CACHE.mkdir(exist_ok=True)
    # Older versions are dead weight once their code or data has changed.
    for stale in CACHE.glob("universe_*.parquet"):
        stale.unlink()
    built.to_parquet(path)
    return built


# Teachers' learned beta and crowding, kept in the data bundle.
INPUTS = data.DIR / "models" / "book_inputs.parquet"


# The composite neutral to the teacher's daily-return beta: the book.
def hedged(universe: pd.DataFrame, inputs: pd.DataFrame | None) -> pd.DataFrame:
    if inputs is None:
        return universe
    df = universe.merge(inputs, on=["permno", "eom"], how="left")
    # Once short interest stops, the crowding teacher sets borrow tiers.
    if "crowding_hat" in df:
        df["borrow"] = C.borrow_rate(df)
    if "beta_hat" in df:
        df["hedge_beta"] = df["beta_hat"].fillna(df["beta_60m"])
    df["signal"] = neutralize(df, df["composite"])
    return df


# The universe with the learned hedge, from committed inputs if any.
def shipped(universe: pd.DataFrame) -> pd.DataFrame:
    return hedged(universe, data.read(INPUTS) if INPUTS.exists() else None)


# How much to hold in each stock for one month, inside every rule.
def optimize_month(month: pd.DataFrame, previous: pd.Series | None = None) -> pd.Series | None:
    month = month.sort_values("signal")
    # Extremes first; if no neutral full-gross book fits, reach deeper.
    for depth in (LIMITS["pool"], 2 * LIMITS["pool"], len(month)):
        pool = pd.concat([month.tail(depth), month.head(depth)]).drop_duplicates("permno")
        weights = solve(month, pool, previous)
        if weights is not None:
            return weights
    return None


# Best score from one pool inside every limit. Exactly one right answer.
def solve(month: pd.DataFrame, pool: pd.DataFrame, previous: pd.Series | None) -> pd.Series | None:
    # Held names that leave the pool stay in it, so none is force-sold.
    if previous is not None:
        held = month[month["permno"].isin(previous.index) & ~month["permno"].isin(pool["permno"])]
        if not held.empty:
            pool = pd.concat([pool, held])

    a = pool["signal"].to_numpy()
    w = cp.Variable(len(pool))
    # Good scores only bought, bad only shorted, so the book is explainable.
    side = np.where(a >= 0, 1.0, -1.0)
    cap = np.full(len(pool), LIMITS["name"])
    beta = hedge(pool).to_numpy()
    risk = pool["risk_rank"].to_numpy()
    sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)
    constraints = [
        # Dollar neutral.
        cp.sum(w) == 0,
        # Set signs make gross linear and exact; 1.5% a name means 107+ names.
        side @ w == LIMITS["gross"],
        # Per-name cap, sign matches the signal.
        w >= np.minimum(side, 0) * cap,
        w <= np.maximum(side, 0) * cap,
        # Beta neutral on the hedge beta.
        cp.abs(beta @ w) <= LIMITS["beta"],
        # And neutral on the volatility complex.
        cp.abs(risk @ w) <= LIMITS["risk"],
        cp.abs(sectors.T @ w) <= LIMITS["sector"],
    ]
    # Chase score but penalise big positions, or 144 stocks and a 43% loss.
    objective = a @ w - 0.5 * LIMITS["ridge"] * cp.sum_squares(w)
    problem = cp.Problem(cp.Maximize(objective), constraints)
    problem.solve(solver=cp.CLARABEL)
    if w.value is None:
        return None
    weights = pd.Series(w.value, index=pool["permno"].to_numpy())
    return weights[weights.abs() > 1e-5]


# Converts target position sizes into whole numbers of shares.
def to_whole_shares(weights: pd.Series, prices: pd.Series) -> pd.Series:
    # No half shares. Truncate, then the repair below adds whole ones back.
    px = prices.reindex(weights.index).astype(float)
    shares = np.trunc(weights * NAV / px)
    held = shares * px / NAV

    # Rounding shrinks both sides. Each pass adds shares to the smaller one.
    for _ in range(500):
        residual = held.sum()
        if abs(residual) < 1e-5:
            break
        # If longs exceed shorts, add to a short, and vice versa.
        side = held[held < 0] if residual > 0 else held[held > 0]
        shortfall = (weights[side.index].abs() - side.abs()).sort_values(ascending=False)
        added = False
        for name in shortfall.index:
            residual = held.sum()
            if px[name] / NAV <= abs(residual) + 1e-12:
                shares[name] += -1 if residual > 0 else 1
                held = shares * px / NAV
                added = True
        if not added:
            break
    return held[held.abs() > 1e-9]


# Cost lines of moving from last month's book, and one-way turnover.
def trading_cost(
    weights: pd.Series,
    previous: pd.Series | None,
    quotes: pd.DataFrame,
    previous_quotes: pd.DataFrame | None,
    model: C.Model = C.DEFAULT,
) -> tuple[dict, float]:
    # Both months' names, so selling out of a position counts as a trade.
    before = pd.Series(dtype=float) if previous is None else previous
    idx = weights.index.union(before.index)
    traded = weights.reindex(idx, fill_value=0.0) - before.reindex(idx, fill_value=0.0)
    # An exited name uses last month's quotes; gaps take the month median.
    known = quotes.reindex(idx)
    if previous_quotes is not None:
        known = known.combine_first(previous_quotes.reindex(idx))
    numeric = known.drop(columns="size_grp")
    known[numeric.columns] = numeric.fillna(quotes[numeric.columns].median())
    parts = C.month_costs(traded, weights, known, model)
    # Turnover is quoted one way throughout, so halve the two-way total.
    return parts, float(traded.abs().sum() / 2)


# One month of any book: optimize, round, cost. Every backtest uses it.
def rebalance(
    cross_section: pd.DataFrame,
    previous: pd.Series | None,
    previous_quotes: pd.DataFrame | None,
    optimize=optimize_month,
    round_shares: bool = True,
    model: C.Model = C.DEFAULT,
) -> tuple | None:
    weights = optimize(cross_section, previous)
    # No solution and an empty book both return None. The caller decides.
    if weights is None or not len(weights):
        return None
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


# Weights after a month of total returns, as shares of month-end NAV.
def drift(weights: pd.Series, info: pd.DataFrame, parts: dict, rf: float) -> pd.Series | None:
    if not len(weights):
        return None
    # A name with no return is cash that month, earning only the cash rate.
    returns = info["ret_exc_lead1m"].reindex(weights.index).fillna(0.0)
    net = (weights * returns).sum() - sum(parts.values())
    return weights * (1 + rf + returns) / (1 + rf + net)


# Walks any book month by month, each trading from what the last left.
def walk(
    universe: pd.DataFrame,
    optimize=optimize_month,
    round_shares: bool = True,
    model: C.Model = C.DEFAULT,
):
    rf = benchmarks().set_index("month")["rf"]
    previous, previous_quotes = None, None
    for month in sorted(universe["eom"].unique()):
        cross_section = universe[universe["eom"] == month]
        step = rebalance(cross_section, previous, previous_quotes, optimize, round_shares, model)
        # No view is an empty book that pays to exit. Skipping is survivorship.
        if step is None:
            weights, info = pd.Series(dtype=float), cross_section.set_index("permno").iloc[:0]
            quotes = cross_section.set_index("permno")[C.COLUMNS]
            parts, turnover = trading_cost(weights, previous, quotes, previous_quotes, model)
        else:
            weights, info, quotes, parts, turnover = step
        yield month, weights, info, cross_section, parts, turnover
        # An empty month carries nothing, so the next pays a full entry.
        cash = rf.get((month + pd.offsets.MonthBegin(1)).normalize(), 0.0)
        previous, previous_quotes = drift(weights, info, parts, cash), quotes


# Any score through the book, monthly: what each month earned and cost.
def backtest(
    universe: pd.DataFrame,
    optimize=optimize_month,
    round_shares: bool = True,
    model: C.Model = C.DEFAULT,
) -> pd.DataFrame:
    steps = walk(universe, optimize, round_shares, model)
    rows = [month_record(*step) for step in steps]
    book = pd.DataFrame(rows).set_index("holding_month")
    book.attrs["months_with_no_position"] = int((book["n"] == 0).sum())
    return book


# IR versus T-bill plus 4%. At zero net the T-bill cancels, leaving 4%.
def information_ratio(net: pd.Series) -> float:
    active = net - 0.04 / 12
    return float(active.mean() / active.std() * np.sqrt(12)) if active.std() else 0.0


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


# Limits every research book clears, so no variant wins by breaking one.
def assert_limits(book: pd.DataFrame) -> None:
    assert book["n"].between(100, 500).all(), "position count outside 100-500"
    assert (book["gross_exposure"] <= 2.0 + 1e-9).all(), "gross above 200%"
    assert (book["net_exposure"].abs() < 0.005).all(), "net exposure outside tolerance"


# Swaps an outside score in for the composite. The rest is shipped code.
def swap_score(universe: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    scores = scores.assign(eom=pd.to_datetime(scores["eom"]))
    merged = universe.merge(scores[["permno", "eom", "pred"]], on=["permno", "eom"], how="inner")
    # A flat month would divide by zero, so it scores flat, not dropped.
    merged["signal"] = neutralize(merged, rank_z(merged, "pred").fillna(0.0))
    return merged


# Monthly Spearman IC of a score on its target return, with its t-stat.
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


# OLS with Newey-West errors, as autocorrelation flatters plain ones.
def regress(y: pd.Series, x: pd.Series | pd.DataFrame):
    both = pd.concat([y.rename("_y"), x], axis=1, sort=True).dropna()
    exog = sm.add_constant(both.drop(columns="_y"))
    return sm.OLS(both["_y"], exog).fit(cov_type="HAC", cov_kwds={"maxlags": 6})


# A display name: SEC's state tag such as "/DE" comes off, nothing else.
def display_name(name) -> str:
    return re.sub(r"\s*[/\\]+(?:[A-Z]{2}[/\\]?)?\s*$", "", str(name)).strip()


# Blanks take the latest panel label by decision month, never later.
def fill_labels(holdings: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    known = panel.loc[panel["ticker"].notna(), ["permno", "eom", "ticker", "company_name"]]
    # merge_asof needs one time unit on both sides, each sorted on it.
    known = known.assign(eom=known["eom"].astype("datetime64[ns]")).sort_values("eom")
    known["label_month"] = known["eom"]
    book = holdings.assign(eom=holdings["eom"].astype("datetime64[ns]")).sort_values("eom")
    filled = pd.merge_asof(
        book, known, on="eom", left_by="PERMNO", right_by="permno", direction="backward"
    )
    # Kept so the label-source exhibit can name each borrowed label's month.
    filled["backfilled"] = filled["TICKER"].isna()
    filled["TICKER"] = filled["TICKER"].fillna(filled["ticker"])
    filled["COMPANY_NAME"] = filled["COMPANY_NAME"].fillna(filled["company_name"])
    # A correction applies only after SEC recorded the name, never before.
    for permno, wrong, since, right in LABEL_FIXES:
        hit = filled["PERMNO"].eq(permno) & filled["COMPANY_NAME"].eq(wrong)
        filled.loc[hit & (filled["eom"] >= since), "COMPANY_NAME"] = right
    return filled.sort_values(["Date", "PERMNO"])


# The holdings file with the rules' column names, weight in % of NAV.
def write_holdings(filled: pd.DataFrame) -> None:
    out = filled[["Date", "PERMNO", "TICKER", "COMPANY_NAME", "WEIGHT"]]
    out = out.rename(columns={"COMPANY_NAME": "COMPANY NAME"}).round({"WEIGHT": 6})
    out.to_csv(OUT / "holdings.csv", index=False, lineterminator="\n")
    # Each borrowed label and source month, for the label check's exhibit.
    borrowed = filled[filled["backfilled"]]
    CACHE.mkdir(exist_ok=True)
    borrowed[["Date", "PERMNO", "label_month"]].to_parquet(CACHE / "label_sources.parquet")


# Everything recorded about one month, read by the checks and write-up.
def month_record(
    month: pd.Timestamp,
    weights: pd.Series,
    info: pd.DataFrame,
    cross_section: pd.DataFrame,
    parts: dict,
    turnover: float,
) -> dict:
    # A missing return usually means failure: count it zero, never drop it.
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


# Runs the whole book month by month, then writes the files we hand in.
def run() -> dict:
    panel = load_panel()
    book_universe = shipped(universe())
    months = sorted(book_universe["eom"].unique())
    assert len(months) == N_HOLDING_MONTHS, f"expected {N_HOLDING_MONTHS}, got {len(months)}"

    rows, holdings = [], []
    for step in walk(book_universe):
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
    check_compliance(book)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "exhibits").mkdir(exist_ok=True)
    write_holdings(fill_labels(pd.concat(holdings), panel))
    stats = performance(book)
    beta = stats["performance"]["beta_realized"]
    assert abs(beta) <= REALIZED_BETA_LIMIT, f"realized beta {beta:+.2f} outside the neutral band"
    # Total return, not just the spread, as that is what an investor earned.
    bm = benchmarks().set_index("month")
    out = book.join(bm[["rf"]], how="left")
    out["portfolio_total_return"] = out["rf"] + out["net"]
    out["active_return"] = out["portfolio_total_return"] - (out["rf"] + 0.04 / 12)
    out.reset_index().to_csv(OUT / "returns.csv", index=False, lineterminator="\n")
    paths.write_json(OUT / "metrics.json", stats, rounded=False, default=str)
    return stats


# Checks the final book on every competition rule, stopping on a break.
def check_compliance(book: pd.DataFrame) -> None:
    # Stops rather than warns. Whole shares cannot hit a target exactly.
    assert len(book) == N_HOLDING_MONTHS, f"{len(book)} holding months"
    assert book["net_exposure"].abs().max() < 0.005, "net exposure outside band"
    assert book["gross_exposure"].max() <= 2.0, "gross above 200%"
    assert book["n"].between(100, 500).all(), "position count outside 100-500"
    assert book["beta"].abs().max() <= 0.03, "beta drift beyond tolerance"
    assert book["max_sector"].max() <= 0.015, "sector tilt beyond tolerance"
    # Rounding a 1.50% target can land above it, so test the real cap.
    assert book["max_weight"].max() <= LIMITS["name"] * 1.10, "position cap breached after rounding"


# A slow result kept under a hash of its inputs, rebuilt if one changes.
def cached(name: str, depends: list, build):
    key = hashlib.sha256(repr(depends).encode()).hexdigest()[:16]
    path = CACHE / "results" / f"{name}_{key}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    value = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Older versions of a result are dead weight once their inputs change.
    for stale in path.parent.glob(f"{name}_*.pkl"):
        stale.unlink()
    pd.to_pickle(value, path)
    return value


# One hash of code, prompts and pins. Same code, same hash, any machine.
def source_fingerprint() -> dict:
    files = [*Path("fiam").rglob("*.py"), *Path("fiam/agents/prompts").rglob("*")]
    files += [Path("run.py"), Path("requirements.txt")]
    files = sorted((f for f in files if f.is_file()), key=lambda f: f.as_posix())
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.as_posix().encode() + path.read_bytes())
    return {"code_sha256": digest.hexdigest()[:16]}


# Rounds once, just before saving; kept here so modules reach it as P.
round_floats = paths.round_floats


# Deflated Sharpe: a PROBABILITY our Sharpe beats zero, not a Sharpe.
def deflated_sharpe(excess: pd.Series, trials: int) -> tuple[float, float]:
    # How high luck alone lifts the best of many trials, then if we beat it.
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


# The return series every statistic uses, plus the market regression.
def _returns(book: pd.DataFrame):
    df = book.join(benchmarks().set_index("month"), how="left")
    if df["rf"].isna().any():
        raise RuntimeError("TB3MS does not cover the holding window")

    # Equal long and short cancels an unknown cash rate buried in the data.
    df["total"] = df["rf"] + df["net"]
    df["active"] = df["total"] - (df["rf"] + 0.04 / 12)
    df["excess"] = df["total"] - df["rf"]

    # Market data lags a month. Returns use every month, regression fewer.
    regression = df.dropna(subset=["mkt_rf"])
    return df, regression, regress(regression["excess"], regression["mkt_rf"])


# Return and risk figures, plus the market regression.
def _performance_stats(df, regression, fit) -> dict:
    # Investors hold cash too, so growth and worst loss use total return.
    cum = (1 + df["total"]).cumprod()
    cum_spread = (1 + df["net"]).cumprod()
    return {
        "return_gross_annual": df["gross"].mean() * 12,
        "return_net_annual": df["net"].mean() * 12,
        "return_total_cagr": cum.iloc[-1] ** (12 / len(df)) - 1,
        "volatility_annual": df["net"].std() * np.sqrt(12),
        "information_ratio": df["active"].mean() / df["active"].std() * np.sqrt(12),
        # The same ratio before trading costs, to compare with cost-free books.
        "information_ratio_before_costs": information_ratio(df["gross"]),
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


# What the result looks like under other assumptions.
def _robustness_stats(df: pd.DataFrame) -> dict:
    # Missing returns are zero. Stress: exits lose 30%, longs, then both.
    conservative = df["net"] - df["missing_long_weight"] * MISSING_STRESS
    symmetric = conservative + df["missing_short_weight"] * MISSING_STRESS

    # Narrow counts eligible trials, broad every fit. Both from the ledger.
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

    # The results file cannot hold comments, so it explains itself first.
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
