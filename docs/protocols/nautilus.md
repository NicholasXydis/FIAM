# Nautilus accounting replay

## Question
Does an independent trading engine (NautilusTrader 1.230.0) reproduce our book's monthly returns
when every trade is made in whole shares? This checks accounting (positions, cash, financing,
corporate actions, delistings), not the cost model: our modelled costs are passed in as fees.

## Method
- Books: v1 and v2 `holdings.csv`, 2021-01..2025-12 (2026 excluded: daily data ends 2025-12).
- Each month: trade from the drifted book to the target in whole shares at the month-end price;
  fees = that month's `month_costs`; borrow and financing charged as cash each day.
- Prices: synthetic bars from CRSP daily total returns, so dividends and splits are already
  inside and are never added again; bar volume 1e10 (below Windows' quantity cap of ~1.8e10).
- Delistings: the delisting return closes the position on its date.

## Pass (fixed now)
- Mean absolute monthly return gap between Nautilus and our ledger <= 0.01% (1 basis point).
- Cumulative gap over the whole window <= 0.10%.
- Any single month with a gap above 0.05% is listed with its cause.

## Reported
The gaps above, Nautilus' built-in tearsheet for v1 and v2, and the run's software versions.
