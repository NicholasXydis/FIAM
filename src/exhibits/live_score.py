# Scores the sealed live book on public prices as each month closes. Writes live_score.json.

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import benchmarks as B
import pipeline as P

EXHIBITS = Path("submission/exhibits")
BOOKS = {
    "sealed": EXHIBITS / "live_forecast_2026-09.csv",
    "current_code": EXHIBITS / "live_forecast_2026-09_corrected.csv",
}
OUT = EXHIBITS / "live_score.json"
PRICES = P.CACHE / "prices"

# The last 2025 close, so January 2026 has a starting price for the check against the panel.
START = "2025-12-31"
MONTHS = ("2026-09", "2026-10")

# Tiingo's free tier allows 50 requests an hour; this spacing never trips it.
PAUSE = 75

# A month counts as priced from Tiingo when its return is within this of the panel's.
TOLERANCE = 0.005


# The Tiingo key from the environment or .env, or a clear instruction if there is none.
def token() -> str:
    lines = Path(".env").read_text().splitlines() if Path(".env").exists() else []
    found = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    key = os.environ.get("TIINGO_API_KEY") or found.get("TIINGO_API_KEY", "").split("#")[0].strip()
    if not key:
        raise SystemExit("set TIINGO_API_KEY in .env, a free key from tiingo.com")
    return key


# One ticker's adjusted daily closes, from Tiingo once and then from cache. Classes may take a dash.
def fetch(ticker: str, end: str) -> None:
    path = PRICES / f"{ticker}.json"
    if path.exists() and json.loads(path.read_text()).get("end", "") >= end:
        return
    body = []
    for symbol in dict.fromkeys(
        [ticker, f"{ticker[:-1]}-{ticker[-1]}" if len(ticker) > 2 else ticker]
    ):
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?startDate={START}&endDate={end}"
        headers = {"Authorization": f"Token {token()}", "Content-Type": "application/json"}
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=60
            ) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(PAUSE)
        if body:
            break
    PRICES.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(ticker=ticker, end=end, rows=body)))


# Month-end-to-month-end returns per PERMNO from whatever prices are cached.
def monthly(book: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    series, digest = {}, hashlib.sha256()
    for permno, ticker in zip(book["PERMNO"], book["TICKER"]):
        path = PRICES / f"{ticker}.json"
        if not path.exists():
            continue
        digest.update(path.read_bytes())
        rows = json.loads(path.read_text())["rows"]
        if rows:
            close = pd.Series({pd.Timestamp(r["date"][:10]): r["adjClose"] for r in rows})
            series[permno] = close.sort_index().resample("ME").last().pct_change()
    table = pd.DataFrame(series)
    if not table.empty:
        table.index = table.index.to_period("M").astype(str)
    return table, digest.hexdigest()


# The panel's 2026 returns against the prices: checks the data and each ticker's identity at once.
def check(prices: pd.DataFrame) -> tuple[dict, set]:
    panel = pq.read_table(P.CHARS, columns=["permno", "eom", "ret_exc_lead1m"]).to_pandas()
    panel["month"] = (pd.to_datetime(panel["eom"]) + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m")
    rf = B.benchmarks().assign(month=lambda d: d["month"].dt.strftime("%Y-%m")).set_index("month")
    panel = panel[
        panel["month"].between("2026-01", "2026-08") & panel["permno"].isin(prices.columns)
    ]
    panel["public"] = [prices[p].get(m) for p, m in zip(panel["permno"], panel["month"])]
    panel["gap"] = (panel["ret_exc_lead1m"] + panel["month"].map(rf["rf"]) - panel["public"]).abs()
    pairs = panel.dropna(subset=["gap"])
    # A ticker is trusted when three quarters of its months agree with the panel.
    agree = pairs.groupby("permno")["gap"].apply(lambda g: (g < TOLERANCE).mean() >= 0.75)
    verified = set(agree[agree].index)
    return (
        dict(
            names_priced=int(len(prices.columns)),
            name_months_compared=int(len(pairs)),
            share_within_half_percent=float((pairs["gap"] < TOLERANCE).mean())
            if len(pairs)
            else None,
            median_abs_gap=float(pairs["gap"].median()) if len(pairs) else None,
            names_verified=len(verified),
        ),
        verified,
    )


# The cash rate and the S&P 500 for a month, and how far into the month the prices reach.
def market(month: str) -> dict:
    daily = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    close = daily.set_index("observation_date")["SP500"]
    start = close[: pd.Period(month).start_time - pd.Timedelta(days=1)].iloc[-1]
    inside = close[pd.Period(month).start_time : pd.Period(month).end_time]
    bench = B.benchmarks().set_index("month")["rf"].dropna()
    known = bench[: pd.Period(month).start_time]
    return dict(
        rf=float(known.iloc[-1]),
        rf_month=f"{known.index[-1]:%Y-%m}",
        sp500=float(inside.iloc[-1] / start - 1) if len(inside) else None,
        sp500_through=f"{inside.index[-1]:%Y-%m-%d}" if len(inside) else None,
    )


# One month of the book: gross on held weights, missing names at zero with the stresses beside.
def score(weights: pd.Series, returns: pd.Series, cost: float, month: str) -> dict:
    missing = returns.isna()
    gross = float((weights * returns.fillna(0.0)).sum())
    m = market(month)
    # The book is self-financing, so capital earns cash and the net weight carries cash's return.
    total = m["rf"] + gross - float(weights.sum()) * m["rf"] - cost
    long_missing = float(weights[missing & (weights > 0)].sum())
    short_missing = float(-weights[missing & (weights < 0)].sum())
    return dict(
        gross=gross,
        cost=cost,
        total_return=total,
        active_return=total - (m["rf"] + 0.04 / 12),
        missing_long_weight=long_missing,
        missing_short_weight=short_missing,
        total_if_missing_longs_lose_30pct=total - long_missing * P.MISSING_STRESS,
        **m,
    )


def main() -> None:
    books = {n: pd.read_csv(p) for n, p in BOOKS.items() if p.exists()}
    if "--fetch" in sys.argv:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tickers = sorted(set().union(*(set(b["TICKER"].dropna()) for b in books.values())))
        for i, ticker in enumerate(tickers, 1):
            fetch(ticker, today)
            print(f"  {i}/{len(tickers)} {ticker}", flush=True)
    record = json.loads(OUT.read_text()) if OUT.exists() else {}
    record.setdefault(
        "rule", "Report whatever it says. A closed month is final and never rewritten."
    )
    for name, book in books.items():
        prices, digest = monthly(book)
        if prices.empty:
            print(f"{name}: no prices cached, run with --fetch")
            continue
        found, verified = check(prices)
        entry = record.setdefault(name, {"months": {}})
        entry["check_2026"] = found
        weights = book.set_index("PERMNO")["WEIGHT"] / 100
        cost = json.loads((EXHIBITS / "live_forecast.json").read_text())
        cost = cost["expected_cost"] if name == "sealed" else cost["current_code"]["expected_cost"]
        for month in MONTHS:
            if month not in prices.index:
                continue
            # A name whose prices never matched the panel is treated as unpriced, never trusted.
            returns = prices.loc[month].reindex(weights.index).where(weights.index.isin(verified))
            result = score(weights, returns, cost if month == MONTHS[0] else 0.0, month)
            # Final once prices reach the month's last business day; before that it is to date.
            last = (pd.Period(month).start_time + pd.offsets.BMonthEnd(0)).strftime("%Y-%m-%d")
            final = (result["sp500_through"] or "") >= last
            if not entry["months"].get(month, {}).get("final"):
                entry["months"][month] = dict(final=final, prices_sha256=digest, **result)
                print(f"{name} {month}: active {result['active_return']:+.2%}, final {final}")
            # October holds September's book as it drifted, with no trades in between.
            weights = weights * (1 + returns.fillna(0.0)) / (1 + result["gross"])
    if any(isinstance(v, dict) for v in record.values()):
        OUT.write_text(json.dumps(P.round_floats(record), indent=2))


if __name__ == "__main__":
    main()
