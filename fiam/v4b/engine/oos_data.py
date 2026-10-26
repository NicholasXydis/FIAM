# Build a daily execution file that runs through 2026-08.
#
# 2015-2025 is the organisers' daily_market.parquet: actual CRSP prices,
# quotes, volume and split-adjusted total returns. 2026 has only the mini
# daily file (raw prices and a raw daily_return) plus the monthly panel, so
# January-August 2026 are a deliberately labelled proxy:
#   price    = split-adjusted total-return index built from panel `ret` and
#              `prc / adjfct`, continuous across months (the mini file's raw
#              daily_return is NOT used because it is not split-adjusted)
#   ADV      = panel dolvol_126d (the panel's average daily dollar volume)
#   quote    = bidaskhl_21d * the 2015-2020 half-spread / high-low ratio by
#              size group, calibrated only on the blind years
# The proxy is for one evaluation, not a replacement for quote data. Every
# caller should label 2026 rows as proxy in its provenance.

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.engine import inputs
from fiam.v4b.forecast import data

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "fiam_v1" / "daily_market_2026.parquet"
PROXY_START = pd.Timestamp("2026-01-01")
PROXY_END = pd.Timestamp("2026-08-31")


def _spread_ratios() -> dict[str, float]:
    """Half-spread / bidaskhl_21d by size group, fitted on 2015-2020 only."""
    q = pd.read_parquet(
        inputs.DAILY,
        columns=["permno", "date", "bid", "ask"],
        filters=[
            ("date", ">=", pd.Timestamp("2015-01-01")),
            ("date", "<=", pd.Timestamp("2020-12-31")),
        ],
    )
    q = q[(q["bid"] > 0) & (q["ask"] >= q["bid"])].copy()
    q["eom"] = pd.to_datetime(q["date"]) + pd.offsets.MonthEnd(0)
    q["half"] = (q["ask"] - q["bid"]) / (q["ask"] + q["bid"])
    month = q.groupby(["permno", "eom"], observed=True)["half"].mean().reset_index()
    panel = pd.read_parquet(
        data.PANEL,
        columns=["permno", "eom", "size_grp", "bidaskhl_21d"],
        filters=[("eom", ">=", pd.Timestamp("2015-01-01")), ("eom", "<=", pd.Timestamp("2020-12-31"))],
    )
    panel["eom"] = pd.to_datetime(panel["eom"]).astype("datetime64[ns]")
    m = month.merge(panel, on=["permno", "eom"])
    m = m[(m["bidaskhl_21d"] > 0) & (m["half"] > 0)]
    ratio = (m["half"] / m["bidaskhl_21d"]).groupby(m["size_grp"]).median()
    return {str(k): float(v) for k, v in ratio.items()}


def _proxy_2026() -> pd.DataFrame:
    # The mini daily file has raw prices and a *raw* daily_return, not CRSP's
    # split-adjusted return.  Compounding it manufactures huge fake returns
    # around reverse splits (e.g. permno 17266 in July 2026).  We therefore use
    # the mini file only for its trading calendar and build a split-adjusted
    # total-return index from the monthly panel:
    #   * panel `ret` is the split-adjusted total return of month M;
    #   * panel `prc / adjfct` is the split-adjusted month-end price;
    #   * each stock-month compounds to exactly `ret` and is continuous across
    #     months, so Nautilus never sees a split jump.
    d = pd.read_csv(
        data.DSF,
        usecols=["permno", "date"],
        dtype={"permno": "int64", "date": "int64"},
    )
    d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d")
    d = d[d["date"].between(PROXY_START, PROXY_END)].drop_duplicates(["permno", "date"])
    d["eom"] = d["date"] + pd.offsets.MonthEnd(0)
    panel = pd.read_parquet(
        data.PANEL,
        columns=["permno", "eom", "ret", "prc", "adjfct", "dolvol_126d", "bidaskhl_21d", "size_grp", "me"],
        filters=[("eom", ">=", pd.Timestamp("2025-12-31")), ("eom", "<=", pd.Timestamp("2026-08-31"))],
    )
    panel["eom"] = pd.to_datetime(panel["eom"]).astype("datetime64[ns]")
    # A session in month M is traded on the characteristics known at M-1 eom.
    # `ret` is the total return of month M and is therefore merged on the
    # *current* eom; merging it on prev_eom would use last month's return and
    # manufacture a one-month-stale dividend.
    d["prev_eom"] = d["eom"] - pd.offsets.MonthEnd(1)
    lagged = panel.drop(columns=["ret", "prc", "adjfct"]).rename(columns={"eom": "prev_eom"})
    d = d.merge(lagged, on=["permno", "prev_eom"], how="left")
    current = panel.loc[:, ["permno", "eom", "ret"]]
    d = d.merge(current, on=["permno", "eom"], how="left")

    # Constant daily total return within each stock-month, so the compounded
    # monthly return is exactly panel `ret`.  A total loss is -1 on the last
    # session; a missing return is carried flat.
    counts = d.groupby(["permno", "eom"], observed=True).size().rename("n").reset_index()
    d = d.merge(counts, on=["permno", "eom"], how="left")
    r = d["ret"].to_numpy(dtype=float)
    n = d["n"].to_numpy(dtype=float)
    daily = np.where(np.isfinite(r) & (r > -1.0) & (n > 0), np.power(1.0 + r, 1.0 / n) - 1.0, 0.0)
    d["daily_ret"] = daily
    last = d["date"].eq(d.groupby(["permno", "eom"], observed=True)["date"].transform("max"))
    d.loc[last & np.isfinite(r) & (r <= -1.0), "daily_ret"] = -1.0

    # Start from the last 2025 close (or the split-adjusted panel price) and
    # compound the daily total returns.  The level is a total-return index, not
    # a quote; execution notional and all return accounting stay exact.
    old = pd.read_parquet(
        inputs.DAILY,
        columns=["permno", "date", "close"],
        filters=[("date", "==", pd.Timestamp("2025-12-31"))],
    )
    old["date"] = pd.to_datetime(old["date"]).dt.normalize()
    dec = panel[panel["eom"].eq(pd.Timestamp("2025-12-31"))].copy()
    dec["adj_prc"] = dec["prc"] / dec["adjfct"].replace(0.0, np.nan)
    start = old[["permno", "close"]].rename(columns={"close": "old_close"})
    start = start.merge(dec[["permno", "adj_prc"]], on="permno", how="outer")
    start["start_price"] = start["old_close"].where(start["old_close"] > 0, start["adj_prc"])
    start["start_price"] = start["start_price"].where(start["start_price"] > 0, 1.0)
    d = d.merge(start[["permno", "start_price"]], on="permno", how="left")
    d["start_price"] = d["start_price"].fillna(1.0)
    d = d.sort_values(["permno", "date"])
    d["cum"] = d.groupby("permno", observed=True)["daily_ret"].transform(lambda s: (1.0 + s).cumprod())
    d["close"] = d["start_price"] * d["cum"]
    d["price_return"] = d["daily_ret"]
    d["total_return"] = d["daily_ret"]

    # Same convention as inputs.market: dollar ADV is the panel's daily
    # dollar-volume average; volume is only used to recover that dollar ADV.
    d["adv"] = d["dolvol_126d"].clip(lower=0.0)
    d["volume"] = np.where(d["close"] > 0, d["adv"] / d["close"], 0.0)
    ratios = _spread_ratios()
    ratio = d["size_grp"].map(ratios).fillna(max(ratios.values())).to_numpy()
    half = d["bidaskhl_21d"].to_numpy(dtype=float) * ratio
    half = np.where(np.isfinite(half) & (half > 0), half, 0.005)
    half = np.clip(half, 1e-4, 0.5)
    d["bid"] = d["close"] * (1.0 - half)
    d["ask"] = d["close"] * (1.0 + half)
    d["market_cap"] = d["me"] * 1e6  # panel me is $m; only held for schema parity
    cols = [
        "permno",
        "date",
        "close",
        "total_return",
        "price_return",
        "volume",
        "bid",
        "ask",
        "market_cap",
    ]
    out = d[cols].copy()
    for c in ("total_return", "price_return"):
        out[c] = out[c].astype(float)
    return out


def build(force: bool = False) -> Path:
    if OUT.exists() and not force:
        return OUT
    old = pd.read_parquet(
        inputs.DAILY,
        columns=[
            "permno",
            "date",
            "close",
            "total_return",
            "price_return",
            "volume",
            "bid",
            "ask",
            "market_cap",
        ],
        filters=[("date", "<=", pd.Timestamp("2025-12-31"))],
    )
    old["date"] = pd.to_datetime(old["date"]).dt.normalize()
    new = _proxy_2026()
    combo = pd.concat([old, new], ignore_index=True).sort_values(["date", "permno"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    combo.to_parquet(OUT, index=False)
    return OUT


if __name__ == "__main__":
    path = build(force="--force" in __import__("sys").argv)
    print(path, path.stat().st_size)
