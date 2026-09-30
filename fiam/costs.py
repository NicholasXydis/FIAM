# Every trading and holding cost, IBKR-style, each with its source, as PREREGISTRATION.md fixes.

import json
from dataclasses import dataclass
from functools import cache

import numpy as np
import pandas as pd

from fiam import data, paths

MODELS = paths.SUBMISSION / "models"
SPREADS, BORROW = MODELS / "spreads.json", MODELS / "borrow.parquet"

# IBKR Pro fixed, US stocks: interactivebrokers.com/en/pricing/commissions-stocks.php, 2026-09-30.
COMMISSION_PER_SHARE, COMMISSION_MIN, COMMISSION_MAX = 0.005, 1.00, 0.01
# SEC Section 31 on sales at its highest rate in 2021-2026, $27.80 a million from May 2024.
SEC_RATE = 27.80e-6
# FINRA Trading Activity Fee on shares sold at its 2026 high, capped per trade (amendment 1).
TAF_PER_SHARE, TAF_MAX = 0.000195, 9.79
# FINRA Consolidated Audit Trail fee on every share bought or sold (amendment 1).
CAT_PER_SHARE = 0.000003
# Square-root impact coefficient (Toth et al. 2011); 0.5 is reported as the sensitivity.
IMPACT_Y = 1.0
# Borrow a year by short interest over shares out (D'Avolio 2002; Drechsler & Drechsler 2016).
TIERS = ((0.05, 0.0030), (0.10, 0.0100), (0.20, 0.0300), (np.inf, 0.0800))
MICRO_FLOOR = 0.0100
# Cash and short proceeds earn the benchmark less this (IBKR Pro pays benchmark minus 0.5%).
FINANCING_SPREAD = 0.005
# The spread calibration's years: daily quotes before the record, so the record never shapes it.
CALIBRATION = ("2015-01-01", "2020-12-31")

# The columns a month's costs read, per stock.
COLUMNS = ["prc", "bidaskhl_21d", "size_grp", "rvol_21d", "dolvol_126d", "borrow"]


# The cost model's dials: capital, impact coefficient, and a multiple on every line.
@dataclass(frozen=True)
class Model:
    nav: float = 10_000_000.0
    impact_y: float = IMPACT_Y
    multiple: float = 1.0


DEFAULT = Model()


# Half the closing quoted spread over the high-low estimate, median within each size group.
def calibrate_spreads() -> dict | None:
    first, last = (pd.Timestamp(d) for d in CALIBRATION)
    daily = data.research(
        "daily_market",
        ["permno", "date", "bid", "ask"],
        [("date", ">=", first), ("date", "<=", last)],
    )
    if daily is None:
        return None
    daily = daily[(daily["bid"] > 0) & (daily["ask"] >= daily["bid"])]
    daily["half"] = (daily["ask"] - daily["bid"]) / (daily["ask"] + daily["bid"])
    daily["eom"] = daily["date"] + pd.offsets.MonthEnd(0)
    monthly = daily.groupby(["permno", "eom"])["half"].mean().reset_index()
    frame = data.features(["bidaskhl_21d", "size_grp"]).merge(monthly, on=data.KEYS)
    frame = frame[frame["bidaskhl_21d"] > 0]
    ratio = (frame["half"] / frame["bidaskhl_21d"]).groupby(frame["size_grp"]).median()
    return {str(k): float(v) for k, v in ratio.items()}


# The calibrated ratios: the committed file, built from the daily quotes the first time.
@cache
def spread_ratios() -> dict:
    if not SPREADS.exists():
        write_spreads(calibrate_spreads())
    return json.loads(SPREADS.read_text(encoding="utf-8"))["ratio_by_size_grp"]


# The calibration as a small committed file, with what it is.
def write_spreads(ratios: dict) -> None:
    body = dict(
        what="Half the CRSP closing quoted spread over bidaskhl_21d, median by size group, "
        "2015-2020 only.",
        ratio_by_size_grp=ratios,
    )
    MODELS.mkdir(parents=True, exist_ok=True)
    paths.write_json(SPREADS, body, rounded=False, end="\n")


# Each stock's half-spread as a fraction of price, from its high-low estimate and size group.
def half_spread(quotes: pd.DataFrame) -> pd.Series:
    ratios = spread_ratios()
    ratio = quotes["size_grp"].map(ratios).fillna(max(ratios.values()))
    return quotes["bidaskhl_21d"] * ratio


# Short interest over shares outstanding a month late, as it is published. None without WRDS.
@cache
def short_ratio() -> pd.Series | None:
    short = data.research(
        "short_interest_monthly_research_only", [*data.KEYS, "short_interest_adjusted"]
    )
    if short is None:
        return None
    both = short.merge(data.features(["shares"]), on=data.KEYS).dropna()
    both["ratio"] = both["short_interest_adjusted"] / (both["shares"] * 1e6)
    both["eom"] = both["eom"] + pd.offsets.MonthEnd(1)
    return both.set_index(data.KEYS)["ratio"]


# A borrow rate a year for each short-interest ratio; a name with no report pays the cheapest tier.
def tier(ratio: pd.Series) -> pd.Series:
    bounds, rates = zip(*TIERS)
    at = np.searchsorted(bounds, ratio.fillna(0.0).to_numpy(), side="right")
    return pd.Series(np.array(rates)[at], index=ratio.index)


# Each row's borrow a year: reported ratio, else its crowding percentile in the last reported month.
def borrow_rate(frame: pd.DataFrame) -> pd.Series:
    ratios = short_ratio()
    if ratios is None:
        committed = data.read(BORROW)
        found = frame[data.KEYS].merge(committed, on=data.KEYS, how="left")["borrow"]
        floor = np.where(frame["size_grp"].eq("micro"), MICRO_FLOOR, TIERS[0][1])
        return pd.Series(found.fillna(pd.Series(floor)).to_numpy(), index=frame.index)
    key = pd.MultiIndex.from_frame(frame[data.KEYS])
    ratio = pd.Series(ratios.reindex(key).to_numpy(), index=frame.index)
    last = ratios.index.get_level_values("eom").max()
    after = frame["eom"] > last
    if after.any():
        latest = ratios.xs(last, level="eom")
        if "crowding_hat" in frame:
            pct = frame.loc[after].groupby("eom")["crowding_hat"].rank(pct=True)
            known = pct.notna()
            ratio.loc[pct.index[known]] = np.quantile(latest.to_numpy(), pct[known].to_numpy())
        missing = after & ratio.isna()
        ratio[missing] = frame.loc[missing, "permno"].map(latest)
    rate = tier(ratio)
    return rate.where(~frame["size_grp"].eq("micro"), np.maximum(rate, MICRO_FLOOR))


# Per stock, a trade of x costs x * linear + x ** 1.5 * impact: the trader's view of these lines.
def unit_costs(quotes: pd.DataFrame, model: Model = DEFAULT) -> tuple[pd.Series, pd.Series]:
    price = quotes["prc"].abs()
    fees = COMMISSION_PER_SHARE / price + CAT_PER_SHARE / price + SEC_RATE / 2
    impact = model.impact_y * quotes["rvol_21d"] * np.sqrt(model.nav / quotes["dolvol_126d"])
    return (fees + half_spread(quotes)) * model.multiple, impact * model.multiple


# One month's cost lines as fractions of NAV, from each name's trade and the book after it.
def month_costs(
    traded: pd.Series, weights: pd.Series, quotes: pd.DataFrame, model: Model = DEFAULT
) -> dict:
    value = traded.abs() * model.nav
    shares = value / quotes["prc"].abs()
    commission = np.minimum(
        np.maximum(COMMISSION_PER_SHARE * shares, COMMISSION_MIN), COMMISSION_MAX * value
    ).where(value > 0, 0.0)
    sold = traded < 0
    fees = (
        SEC_RATE * value[sold].sum()
        + np.minimum(TAF_PER_SHARE * shares[sold], TAF_MAX).sum()
        + CAT_PER_SHARE * shares.sum()
    )
    impact = model.impact_y * quotes["rvol_21d"] * np.sqrt(value / quotes["dolvol_126d"]) * value
    shorts = weights[weights < 0].abs()
    parts = dict(
        cost_commission=(commission.sum() + fees) / model.nav,
        cost_spread=(value * half_spread(quotes)).sum() / model.nav,
        cost_impact=impact.sum() / model.nav,
        cost_borrow=(shorts * quotes.loc[shorts.index, "borrow"]).sum() / 12,
        cost_financing=FINANCING_SPREAD / 12 * max(1.0 - weights.sum(), 0.0),
    )
    return {k: float(v) * model.multiple for k, v in parts.items()}


# Writes both calibrations into submission/models, so a run without WRDS charges the same.
def main() -> None:
    from fiam import book as P

    ratios = calibrate_spreads()
    MODELS.mkdir(parents=True, exist_ok=True)
    if ratios is None or short_ratio() is None:
        print("no WRDS layers here, so the committed calibrations are kept")
        return
    write_spreads(ratios)
    spread_ratios.cache_clear()
    frame = P.universe()
    inputs = MODELS / "book_inputs.parquet"
    if inputs.exists():
        taught = data.read(inputs, [*data.KEYS, "crowding_hat"])
        frame = frame.merge(taught, on=data.KEYS, how="left")
    frame = frame[frame["eom"] >= P.FIRST_FORECAST]
    out = frame[data.KEYS].assign(borrow=borrow_rate(frame).to_numpy()).sort_values(data.KEYS)
    out.to_parquet(BORROW, index=False)
    print(f"spread ratios {ratios}; borrow for {len(out):,} stock-months")


if __name__ == "__main__":
    main()
