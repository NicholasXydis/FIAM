# Dated broker and regulatory fee schedule (Final case §7, §9.1), one place.
#
# Constants are copied from fiam/costs.py with their sources, so v4b reads no
# code outside its folder. The case asks for a current schedule with its date
# and a flat alternative; the flat alternative is borrow_flat_large/other in
# config (50bp large, 5% other) and is reported beside this one.
#
# Per order:
#   commission = clip(0.005 * shares, $1, 1% of value)           (IBKR Pro fixed)
#   CAT        = 0.000003 * shares                                (every trade)
#   sales add  SEC 27.80e-6 * value + min(0.000195 * shares, $9.79) (FINRA TAF)
# Shares are actual (unadjusted) shares: dollars / raw close.
# The optimizer sees the convex part per dollar traded; minimums and caps are
# left out there (the $1 minimum is immaterial at $1bn order sizes) and are
# charged exactly by the execution backend.

import numpy as np

SCHEDULE_DATE = "2026-09-30"
# IBKR Pro fixed, US stocks: interactivebrokers.com/en/pricing/commissions-stocks.php, 2026-09-30.
COMMISSION_PER_SHARE, COMMISSION_MIN, COMMISSION_MAX = 0.005, 1.00, 0.01
# SEC Section 31 on sales at its highest rate in 2021-2026, $27.80 a million from May 2024.
SEC_RATE = 27.80e-6
# FINRA Trading Activity Fee on shares sold at its 2026 high, capped per trade.
TAF_PER_SHARE, TAF_MAX = 0.000195, 9.79
# FINRA Consolidated Audit Trail fee on every share bought or sold.
CAT_PER_SHARE = 0.000003
# A missing or bad price is charged as a $10 share (5bp commission a side).
PRICE_MISSING = 10.0


def _price(price) -> np.ndarray:
    p = np.abs(np.asarray(price, dtype=float))
    return np.where(np.isfinite(p) & (p > 0.5), p, PRICE_MISSING)


# Fee per dollar traded, either side (commission + CAT), convex optimizer form.
def per_dollar(price) -> np.ndarray:
    return (COMMISSION_PER_SHARE + CAT_PER_SHARE) / _price(price)


# Extra fee per dollar sold (SEC + TAF), convex optimizer form.
def per_dollar_sold(price) -> np.ndarray:
    return SEC_RATE + TAF_PER_SHARE / _price(price)


# Exact fees in dollars for one order of `dollars` at raw price `price`.
def order(dollars: float, price: float, sell: bool) -> float:
    dollars = abs(float(dollars))
    if dollars <= 0:
        return 0.0
    shares = dollars / float(_price(price))
    fee = min(max(COMMISSION_PER_SHARE * shares, COMMISSION_MIN), COMMISSION_MAX * dollars)
    fee += CAT_PER_SHARE * shares
    if sell:
        fee += SEC_RATE * dollars + min(TAF_PER_SHARE * shares, TAF_MAX)
    return fee
