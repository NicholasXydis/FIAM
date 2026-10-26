"""Blind split-adjusted price units and cash distributions for Nautilus."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from fiam.v4b.engine import inputs


@dataclass
class Feed:
    prices: pd.DataFrame
    dividends: pd.DataFrame  # cash per adjusted share; never reinvested
    tradable: pd.DataFrame
    adv: pd.DataFrame
    sigma: pd.DataFrame
    half_spread: pd.DataFrame | float
    borrow: pd.DataFrame | float
    rf: pd.Series
    unverified_gaps: pd.DataFrame | None = None
    # Raw close (actual shares) for per-share fees; None -> fees.PRICE_MISSING.
    raw_close: pd.DataFrame | None = None


def from_world(world):
    cut = pd.Timestamp(getattr(world, "cut", world.m.policy.blind_until))
    mk = world.market
    dates = mk["returns"].index
    path = getattr(world, "daily_path", None) or inputs.DAILY
    d = pd.read_parquet(
        path,
        columns=["permno", "date", "close", "price_return", "total_return", "volume"],
        filters=[("date", ">=", dates[0]), ("date", "<=", cut)],
    )
    feed = build_feed(d, mk, world.borrow, world.rf)
    if "price" in mk:
        feed.raw_close = mk["price"].reindex(index=feed.prices.index, columns=feed.prices.columns)
    return feed


def build_feed(d, mk, borrow, rf):
    dates, names = mk["returns"].index, mk["returns"].columns
    d = d.drop_duplicates(["date", "permno"])

    def grid(column):
        return (
            d.pivot(index="date", columns="permno", values=column)
            .reindex(index=dates, columns=names)
            .astype(float)
        )

    close, retx, ret, volume = (
        grid(c) for c in ("close", "price_return", "total_return", "volume")
    )
    raw, rx, rt = close.abs().to_numpy(), retx.to_numpy(), ret.to_numpy()
    px, div = np.full_like(raw, np.nan), np.zeros_like(raw)
    scale = np.ones(len(names))
    last_raw = np.full(len(names), np.nan)
    last_px = np.full(len(names), np.nan)
    previous_seen = np.zeros(len(names), dtype=bool)
    uncertain = np.zeros(len(names), dtype=bool)
    gaps = np.zeros_like(raw, dtype=bool)
    for k in range(len(dates)):
        observed = np.isfinite(raw[k]) & (raw[k] > 0)
        contiguous = observed & previous_seen & np.isfinite(rx[k]) & (rx[k] >= -1)
        # Retx and raw-price ratio identify splits on contiguous observations.
        scale = np.where(contiguous, scale * (1 + rx[k]) * last_raw / raw[k], scale)
        current = raw[k] * scale
        reopened = observed & np.isfinite(last_px) & ~previous_seen
        uncertain |= reopened
        div[k] = np.where(contiguous & np.isfinite(rt[k]), last_px * (rt[k] - rx[k]), 0.0)
        px[k] = np.where(observed, current, np.nan)
        last_raw = np.where(observed, raw[k], last_raw)
        last_px = np.where(observed, current, last_px)
        previous_seen = observed
        gaps[k] = uncertain
    prices = pd.DataFrame(px, index=dates, columns=names)
    tradable = prices.gt(0) & volume.gt(0)
    return Feed(
        prices,
        pd.DataFrame(div, index=dates, columns=names),
        tradable,
        mk["adv"],
        mk["sigma"],
        mk["half_spread"],
        borrow,
        rf,
        pd.DataFrame(gaps, index=dates, columns=names),
    )
