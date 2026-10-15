# Final exhibits: is final v3's edge real, where its risk sits, and the agents on its book

Written 2026-10-15, after final v3's results (v2_amendment_3.md) had been seen, and before any run
it covers. Exhibits only: nothing here changes a position, chooses a book or tunes a parameter.
The book is final v3 at $10M, holding months 2021-01..2026-08, and its September 2026 book. Every
benchmark is reported whatever it shows, beside cash + 4% and the S&P 500.

## 1. Is the edge real: four benchmarks
Each matches final v3 month by month on gross per side, and on legs where stated; final v3 holds
132 longs and 109 shorts on average.
1. **Random large-cap books (the null).** 1,000 draws, seed 42. Each month, from the 500 largest
   stocks in our universe by market value (our panel has no S&P 500 flag), as many random longs
   and shorts as final v3 held that month, equal weights. A held name is kept while it stays among
   the 500, else replaced, and is also replaced with probability 0.1 a month (final v3 keeps a name
   10 months on average). Each draw pays final v3's cost per unit of turnover that month on its own
   turnover. Reported: final v3's percentile among the draws on net and gross IR, and the draws'
   mean and 5th and 95th percentiles. A null, not a trial.
2. **Our rule on large caps only.** Final v3 run unchanged on the 500 largest stocks each month, at
   $10M and $1B. Does the edge survive outside small caps?
3. **Our favourite names, held still.** Every name ranked by its summed |weight| over 2021-2026
   (weight x months held); the top 132 net longs and top 109 net shorts held all period at equal
   weights within each side, at final v3's gross, dropped while outside our universe. It uses
   hindsight about which names we held most, and is labelled so.
4. **Equal weights:** on our score (the top and bottom names, as many as final v3 held), and on
   final v3's own names. Do the optimizer and its sizing add value?
Benchmarks 2 to 4 run with every cost charged at $10M and $1B, in whole shares; each is a trial.

## 2. What we expect live
Projected live IR = final v3's IR x (1 - haircut), shown for two published haircuts: 26% (McLean
and Pontiff 2016, out-of-sample decay of published anomalies) and 50% (Harvey and Liu 2015, a
typical haircut for multiple testing). No number here is fitted.

## 3. Risk table
Each decision month, from `risk.py`'s covariance known at the decision and `vol.py`'s specific
risk: predicted monthly volatility, raw and times the frozen correction (`vol_bias`). Per holding:
weight, specific volatility, MCTR_i = (Sigma w)_i / sigma, CTR_i = w_i x MCTR_i, PCTR_i = CTR_i /
sigma, mismatch = PCTR_i - |w_i| / sum|w|. Book VaR and CVaR at 95% and 99% under a normal from the
corrected volatility; historical daily VaR and CVaR from the daily path (2021-2025).

## 4. Factor exposures over time
Each month, exposure per unit of gross to the risk model's five styles, and rolling 24-month
loadings on FF5 + momentum.

## 5. The agents on final v3 (methods unchanged from `honesty.md` and `crowd.md`)
The devil's advocate (critiques checked by code), the memo writer, the explainer of the ten largest
September positions, the AI-crowd overlap and copycat test on final v3's book, and the explainer's
account of section 4's yearly exposures, every number in it checked against the table.

## 6. Dendrogram
The 30 largest September positions, clustered by average linkage on 1 - Spearman correlation of
their 147 characteristic ranks at 2026-08, labelled with names known by that month.
