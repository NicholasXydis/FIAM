# Builds the portfolio and writes the holdings, returns and stats. Same answer every time.
# Pick tradeable stocks, score them, strip out unwanted bets, size positions, round to whole
# shares, charge fees.

from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CHARS = Path("data/chars_final_with_names.parquet")
BENCH = Path("data/benchmarks")
OUT = Path("submission")

# We decide at month end and hold the next month, so July 2026 is the last month we can act on.
FIRST_FORECAST, LAST_FORECAST = "2020-12-31", "2026-07-31"
N_HOLDING_MONTHS = 68

# How many of the twelve a stock needs before we trade it. Demanding all twelve is worse.
MIN_SIGNALS = 9

# Only matters for rounding. At $10m one share of an expensive stock is a real slice.
NAV = 10_000_000.0

# The twelve measures. +1 means higher is better, -1 lower. Directions come from theory and
# were fixed before we ran anything, and we use all twelve so there is nothing to cherry-pick.
SIGNALS = {
    "ivol_capm_21d": -1, "be_me": +1, "qmj": +1, "at_gr1": -1,
    "niq_su": +1, "ope_be": +1, "chcsho_12m": -1, "o_score": -1,
    "ret_12_1": +1, "gp_at": +1, "noa_gr1a": -1, "eqnetis_at": -1,
}

# Our limits. Gross and position count come from the rules, the rest are ours. `risk` stops us
# leaning calm or wild, `pool` is candidates per end, `ridge` spreads us over ~250 stocks.
LIMITS = dict(gross=2.0, beta=0.02, risk=0.02, sector=0.01, name=0.015, pool=200, ridge=30.0)

# Assumed, not measured. Deliberately pessimistic, and stated openly in the deck.
COSTS = dict(commission_bps=5.0, spread_scale=0.20, borrow_gc_bps=50.0,
             borrow_htb_bps=250.0, impact_bps=8.0)


# Loads the stock data and works out which sector each company belongs to.
def load_panel() -> pd.DataFrame:
    # Only the columns we actually use. Loading all 198 wastes about 2GB of memory.
    cols = list(SIGNALS) + ["permno", "eom", "prc", "me", "ret_exc_lead1m", "gics",
                            "beta_60m", "dolvol_126d", "size_grp", "bidaskhl_21d",
                            "rvol_21d", "betadown_252d", "betabab_1260d",
                            "ticker", "company_name"]
    panel = pq.read_table(CHARS, columns=sorted(set(cols))).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    # Sector codes are nested, and the first two digits give the 11 broad sectors. Companies
    # with no sector get their own group rather than being dropped.
    panel["sector"] = panel["gics"].astype("string").str[:2].fillna("XX")
    return panel


# Narrows the list to stocks we would actually be willing to trade.
def screen(panel: pd.DataFrame) -> pd.DataFrame:
    # Never filter on whether a stock has a future return, that drops the companies that
    # failed. Under $5 or $300m shorting gets expensive. Leaves ~2,350 companies a month.
    keep = (panel["prc"].abs() >= 5.0) & (panel["me"] >= 300.0)
    window = panel["eom"].between(FIRST_FORECAST, LAST_FORECAST)
    return panel[keep & window].copy()


# Turns the twelve measures into a single score per stock, with unwanted bets removed.
def build_signal(df: pd.DataFrame) -> pd.DataFrame:
    # Rank within each month, so measures in different units can be averaged fairly.
    zs = []
    for col, sign in SIGNALS.items():
        r = df.groupby("eom")[col].rank(pct=True)
        mu = r.groupby(df["eom"]).transform("mean")
        sd = r.groupby(df["eom"]).transform("std")
        zs.append(((r - mu) / sd) * sign)
    # Equal weight. Fitting weights to past data measured worse than not fitting them.
    scores = pd.concat(zs, axis=1)
    # Require most measures present, so scores stay comparable.
    df["n_signals"] = scores.notna().sum(axis=1)
    df["composite"] = scores.mean(axis=1).where(df["n_signals"] >= MIN_SIGNALS)
    df = df.dropna(subset=["composite", "beta_60m", "bidaskhl_21d"]).copy()

    # Compare each stock to its own sector, or a high score just means "in a good sector".
    demeaned = df["composite"] - df.groupby(["eom", "sector"])["composite"].transform("mean")
    # Strip out the part of the score that is really a bet on the market.
    bx = df["beta_60m"] - df.groupby("eom")["beta_60m"].transform("mean")
    sy = demeaned - demeaned.groupby(df["eom"]).transform("mean")
    cov = (bx * sy).groupby(df["eom"]).transform("sum")
    var = (bx * bx).groupby(df["eom"]).transform("sum")
    df["signal"] = sy - (cov / var) * bx

    # Stocks expensive to borrow. An earlier version flagged 73% of shorts, so it was tightened.
    q05 = df.groupby("eom")["dolvol_126d"].transform(lambda s: s.quantile(0.05))
    df["htb"] = (df["size_grp"] == "micro") | (df["dolvol_126d"] <= q05)

    # Jumpy stocks move with the market, so leaning away from them is secretly a bet the
    # market falls. Averaging four measures of jumpiness fixes that. Our main finding.
    parts = []
    for col in ("ivol_capm_21d", "rvol_21d", "betadown_252d", "betabab_1260d"):
        r = df.groupby("eom")[col].rank(pct=True)
        mu = r.groupby(df["eom"]).transform("mean")
        sd = r.groupby(df["eom"]).transform("std")
        parts.append((r - mu) / sd)
    df["risk_rank"] = pd.concat(parts, axis=1).mean(axis=1).fillna(0.0)
    return df


# Works out how much to hold in each stock for one month, inside every rule.
def optimize_month(month: pd.DataFrame) -> pd.Series | None:
    # Best score without breaking any limit. Exactly one right answer, so not a search.
    month = month.sort_values("signal")
    pool = pd.concat([month.tail(LIMITS["pool"]), month.head(LIMITS["pool"])])
    a = pool["signal"].to_numpy()
    beta = pool["beta_60m"].to_numpy()
    risk = pool["risk_rank"].to_numpy()
    sectors = pd.get_dummies(pool["sector"]).to_numpy(dtype=float)

    w = cp.Variable(len(pool))
    # Good scores can only be bought, bad ones only shorted, so the book is explainable.
    lo = np.where(a >= 0, 0.0, -LIMITS["name"])
    hi = np.where(a >= 0, LIMITS["name"], 0.0)
    constraints = [
        cp.sum(w) == 0,                          # dollar neutral
        cp.norm1(w) <= LIMITS["gross"],          # gross <= 200%
        w >= lo, w <= hi,                        # per-name cap, sign matches the signal
        cp.abs(beta @ w) <= LIMITS["beta"],      # beta neutral (trailing estimate)
        cp.abs(risk @ w) <= LIMITS["risk"],      # and neutral on the volatility complex
        cp.abs(sectors.T @ w) <= LIMITS["sector"],
    ]
    # Chase the score but penalise big positions, or we end up with 144 stocks and a 43% loss.
    problem = cp.Problem(cp.Maximize(a @ w - 0.5 * LIMITS["ridge"] * cp.sum_squares(w)),
                         constraints)
    problem.solve(solver=cp.CLARABEL)
    if w.value is None:
        return None
    weights = pd.Series(w.value, index=pool["permno"].to_numpy())
    return weights[weights.abs() > 1e-5]


# Converts target position sizes into whole numbers of shares.
def to_whole_shares(weights: pd.Series, prices: pd.Series) -> pd.Series:
    # You cannot buy half a share. Rounding down guarantees we never exceed a limit.
    px = prices.reindex(weights.index).astype(float)
    shares = np.trunc(weights * NAV / px)
    held = shares * px / NAV

    # Rounding shrinks both sides, so add shares to the smaller one until they balance.
    for _ in range(500):
        residual = held.sum()
        if abs(residual) < 1e-5:
            break
        # If we are holding more than we are shorting, add to a short, and vice versa.
        side = held[held < 0] if residual > 0 else held[held > 0]
        if side.empty:
            break
        for name in side.abs().sort_values(ascending=False).index:
            step = px[name] / NAV
            if step <= abs(residual) + 1e-12:
                shares[name] += -1 if residual > 0 else 1
                held = shares * px / NAV
                break
        else:
            break
    return held[held.abs() > 1e-9]


# Runs the whole thing, one month at a time, then writes the files we hand in.
def run() -> dict:
    panel = load_panel()
    universe = build_signal(screen(panel))
    months = sorted(universe["eom"].unique())
    assert len(months) == N_HOLDING_MONTHS, f"expected {N_HOLDING_MONTHS}, got {len(months)}"

    rows, holdings, previous, previous_spreads = [], [], None, None
    for month in months:
        cross_section = universe[universe["eom"] == month]
        weights = optimize_month(cross_section)
        if weights is None:
            raise RuntimeError(f"optimizer failed for {month:%Y-%m}")

        info = cross_section.set_index("permno").loc[weights.index]
        weights = to_whole_shares(weights, info["prc"].abs())
        info = info.loc[weights.index]   # rounding can drop a stock entirely, so re-sync

        if previous is None:
            traded = weights.abs()          # first month, we buy the whole portfolio
        else:
            # Include stocks from both months, so selling out of one still counts as a trade.
            idx = weights.index.union(previous.index)
            traded = (weights.reindex(idx, fill_value=0.0)
                      - previous.reindex(idx, fill_value=0.0)).abs()
        turnover = traded.sum() / 2       # counted one way, the convention we use throughout

        # Fees only on what changed hands. Month one costs most because we buy everything.
        shorts = weights[weights < 0]
        htb = shorts[info.loc[shorts.index, "htb"].to_numpy()]
        # Stocks we are exiting are a third of all trading, so use each one's own cost.
        spreads = cross_section.set_index("permno")["bidaskhl_21d"]
        own = spreads.reindex(traded.index)
        if previous_spreads is not None:
            own = own.fillna(previous_spreads.reindex(traded.index))
        spread = (traded * own.fillna(spreads.median()) * COSTS["spread_scale"] / 2).sum()
        cost = (traded.sum() * COSTS["commission_bps"] / 1e4
                + spread
                + shorts.abs().sum() * COSTS["borrow_gc_bps"] / 1e4 / 12
                + htb.abs().sum() * COSTS["borrow_htb_bps"] / 1e4 / 12
                + traded.sum() * COSTS["impact_bps"] / 1e4)

        # A missing return usually means the company failed. Dropping it would remove exactly
        # the disasters a short book profits from, so we keep it and count it flat.
        missing = info["ret_exc_lead1m"].isna()
        gross_ret = (weights * info["ret_exc_lead1m"].fillna(0.0)).sum()
        holding_month = (month + pd.offsets.MonthBegin(1)).normalize()
        rows.append(dict(forecast_eom=month, holding_month=holding_month,
                         gross=gross_ret, cost=cost, net=gross_ret - cost,
                         turnover=turnover, beta=(weights * info["beta_60m"]).sum(),
                         net_exposure=weights.sum(), gross_exposure=weights.abs().sum(),
                         n=len(weights),
                         max_sector=weights.groupby(info["sector"].to_numpy()).sum().abs().max(),
                         max_weight=weights.abs().max(),
                         htb_share=htb.abs().sum() / max(shorts.abs().sum(), 1e-12),
                         missing_long_weight=weights[missing & (weights > 0)].sum(),
                         missing_short_weight=weights[missing & (weights < 0)].abs().sum(),
                         min_signals=cross_section["n_signals"].min()))
        holdings.append(pd.DataFrame(dict(
            Date=holding_month, PERMNO=weights.index,
            TICKER=info["ticker"].to_numpy(), COMPANY_NAME=info["company_name"].to_numpy(),
            WEIGHT=weights.to_numpy() * 100)))
        previous = weights
        previous_spreads = cross_section.set_index("permno")["bidaskhl_21d"]

    book = pd.DataFrame(rows).set_index("holding_month")
    check_compliance(book)
    OUT.mkdir(exist_ok=True)
    pd.concat(holdings).to_csv(OUT / "holdings.csv", index=False)
    stats = performance(book)
    # Export the total portfolio return, not just the long-short spread, so the CSV states
    # what an investor actually earned. Collateral earns the bill rate; the spread is ours.
    bm = benchmarks().set_index("month")
    out = book.join(bm[["rf"]], how="left")
    out["portfolio_total_return"] = out["rf"] + out["net"]
    out["active_return"] = out["portfolio_total_return"] - (out["rf"] + 0.04 / 12)
    out.reset_index().to_csv(OUT / "returns.csv", index=False)
    (OUT / "metrics.json").write_text(json.dumps(stats, indent=2, default=str))
    return stats


# Checks the finished portfolio against every competition rule and stops if one is broken.
def check_compliance(book: pd.DataFrame) -> None:
    # Stops the run rather than warning. The allowances exist because whole shares cannot hit
    # a target exactly.
    assert len(book) == N_HOLDING_MONTHS, f"{len(book)} holding months"
    assert book["net_exposure"].abs().max() < 0.005, "net exposure outside tolerance"
    assert book["gross_exposure"].max() <= 2.0, "gross above 200%"
    assert book["n"].between(100, 500).all(), "position count outside 100-500"
    assert book["beta"].abs().max() <= 0.03, "beta drift beyond tolerance"
    assert book["max_sector"].max() <= 0.015, "sector tilt beyond tolerance"
    # Rounding a 1.50% target up can land slightly above it, so the post-rounding cap is
    # stated explicitly rather than implied by the optimizer's limit.
    assert book["max_weight"].max() <= LIMITS["name"] * 1.10, "position cap breached after rounding"


# Loads the two things we measure ourselves against: the cash rate and the market return.
def benchmarks() -> pd.DataFrame:
    # T-bill is the required cash rate. The market series is a broad index, not the S&P 500,
    # because no free S&P series includes dividends.
    tb = pd.read_csv(BENCH / "TB3MS.csv", parse_dates=["observation_date"])
    tb = tb.rename(columns={"observation_date": "month", "TB3MS": "tb3ms"})
    tb["month"] = tb["month"].dt.normalize()
    tb["rf"] = tb["tb3ms"] / 100 / 12

    with zipfile.ZipFile(BENCH / "ff_factors.zip") as z:
        raw = z.read(z.namelist()[0]).decode("latin1").splitlines()
    recs = [l.split(",") for l in raw if l.strip()[:6].isdigit() and len(l.split(",")) == 5]
    ff = pd.DataFrame(recs, columns=["ym", "mkt_rf", "smb", "hml", "ff_rf"])
    ff["month"] = pd.to_datetime(ff["ym"].str.strip(), format="%Y%m")
    for c in ["mkt_rf", "smb", "hml", "ff_rf"]:
        ff[c] = ff[c].astype(float) / 100
    # Keep every month even where the market data has not arrived yet.
    return tb[["month", "rf"]].merge(ff[["month", "mkt_rf"]], on="month", how="left")


# Records which version of the code produced these numbers.
def source_fingerprint() -> dict:
    # A version number alone would miss uncommitted edits, so fingerprint the files.
    import hashlib
    files = sorted(Path("src").glob("*.py"))   # same order every time, so the fingerprint matches
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.read_bytes())
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"],
                                    capture_output=True, text=True, timeout=5).stdout.strip())
    except Exception:
        head, dirty = "unknown", True
    return {"git_commit": head or "unknown",
            "working_tree_dirty": dirty,
            "src_sha256": digest.hexdigest()[:16],
            "src_files": [p.name for p in files]}


# Rounds the numbers once, just before saving.
def round_floats(obj, places: int = 6):
    # Six decimals. The maths runs at full precision, only the saved file is rounded.
    if isinstance(obj, dict):
        return {k: round_floats(v, places) for k, v in obj.items()}   # step into each group
    if isinstance(obj, (float, np.floating)):
        return round(float(obj), places)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


# Adjusts our result for how many versions we tried before landing on this one.
def deflated_sharpe(excess: pd.Series, trials: int) -> tuple[float, float]:
    # Try enough versions and one looks good by luck. This works out how good the luckiest
    # would look with no skill at all, then asks whether we beat it.
    from scipy.stats import norm, skew, kurtosis
    n = len(excess)
    sr = excess.mean() / excess.std()   # monthly, scaled to a year only at the end
    g3, g4 = skew(excess), kurtosis(excess, fisher=False)
    euler = 0.5772156649
    sr0 = np.sqrt(1 / n) * ((1 - euler) * norm.ppf(1 - 1 / trials)
                            + euler * norm.ppf(1 - 1 / (trials * np.e)))
    z = ((sr - sr0) * np.sqrt(n - 1)) / np.sqrt(1 - g3 * sr + ((g4 - 1) / 4) * sr ** 2)
    return float(norm.cdf(z)), float(sr0 * np.sqrt(12))


# Adds the return series every statistic is built from. Returns the frame and the regression.
def _returns(book: pd.DataFrame):
    import statsmodels.api as sm

    df = book.join(benchmarks().set_index("month"), how="left")
    if df["rf"].isna().any():
        raise RuntimeError("TB3MS does not cover the holding window")

    # Equal long and short cancels an unknown cash rate buried in the data. Our cash earns
    # the T-bill rate and the stock picking sits on top.
    df["total"] = df["rf"] + df["net"]
    df["active"] = df["total"] - (df["rf"] + 0.04 / 12)
    df["excess"] = df["total"] - df["rf"]

    # Market data lags a month, so returns use every month and the comparison uses fewer.
    regression = df.dropna(subset=["mkt_rf"])
    # Corrects for monthly returns not being independent, which would flatter our confidence.
    fit = sm.OLS(regression["excess"], sm.add_constant(regression["mkt_rf"])).fit(
        cov_type="HAC", cov_kwds={"maxlags": 6})
    return df, regression, fit


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
        "beta_realized": fit.params.iloc[1],
        "beta_stderr": fit.bse.iloc[1],
        "correlation_with_market": regression["excess"].corr(regression["mkt_rf"]),
    }


# What the result looks like if our assumptions are wrong.
def _robustness_stats(df: pd.DataFrame) -> dict:
    # A harsher version: a stock we owned that stopped trading loses 30%, one we shorted
    # gains nothing. Charging both equally would flatter us.
    adverse = (df["net"] - df["missing_long_weight"] * 0.30) - 0.04 / 12

    # 60 counts choices that could have become the book, 860 counts everything we ever ran.
    dsr_design, _ = deflated_sharpe(df["excess"], 60)
    dsr_everything, hurdle = deflated_sharpe(df["excess"], 860)
    return {
        "deflated_sharpe_60_design_choices": dsr_design,
        "deflated_sharpe_860_all_configurations": dsr_everything,
        "sharpe_a_lucky_manager_would_post_at_860": hurdle,
        "ir_if_missing_returns_cost_30pct": adverse.mean() / adverse.std() * np.sqrt(12),
        "missing_long_weight_monthly": df["missing_long_weight"].mean(),
        "missing_short_weight_monthly": df["missing_short_weight"].mean(),
    }


# Every statistic we report, from the finished portfolio.
def performance(book: pd.DataFrame) -> dict:
    df, regression, fit = _returns(book)

    # The results file cannot hold comments, so it starts by explaining itself.
    stats = {
        "_about": {
            "what": "One run of src/pipeline.py. The source of truth for every number.",
            "regenerate": "python run.py",
            "sections": {
                "run": "when this was made, from which code",
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
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
            "market_series": "Ken French CRSP value-weighted market, NOT the S&P 500",
            "regression_months": len(regression),
            "status": "research backtest, not a sealed out-of-sample record",
        },
    }
    return round_floats(stats)


if __name__ == "__main__":
    for k, v in run().items():
        print(f"{k:24s} {v}")
