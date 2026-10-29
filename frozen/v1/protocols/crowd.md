# AI Crowd Lab

## Question
As investors use AI tools, part of the crowd becomes AI. How does an AI crowd pick stocks, how much
does it herd, how much of our book does it already own, and what would ignoring it, trading with it
or betting against it have done? Everything here is an exhibit or a what-if; no crowd output ever
sets a v1 or v2 position.

## Crowds (fixed before the first run)
- **Retail (a):** 30 Gemma agents = 6 personas x 5 information sets.
  Personas, one system prompt each: attention and news chaser (Barber and Odean 2008); lottery
  seeker, cheap and volatile stocks (Kumar 2009); momentum follower; contrarian dip buyer (Kaniel,
  Saar and Titman 2008); income seeker; familiar large-company buyer (Huberman 2001). Popular-stock
  behaviour follows Barber, Huang, Odean and Schwarz (2020).
  Information sets: 5 draws of 40 of the 147 characteristics, seed 42, drawn once and saved.
- **Copycat (b):** 30 Gemma "mini quant funds", 10 per strategy text: our v1 strategy in plain
  English; the 2026 first-round brief (what every competing team was asked to build); the 2025
  final case. Texts are written into `mandates/` before the first copycat run. Each agent sees the
  measures its text names plus a random fill to 40 columns (seed 42). Each card: buy 8, and short 8
  when the text allows shorting.
- **Historical (c):** the existing 265,590 picks, 2016-2020 (Gemma and Qwen), unchanged.
- Cards: anonymous (codes, no names or tickers), percentile ranks within the month (within country
  outside the US), 40 stocks per card, as in `fiam/agents/crowd.py`. Retail picks 8 of 40.
- Months: decisions 2025-01-31 to 2026-07-31 (holding 2025-02..2026-08), the clean window after
  Gemma's January 2025 cutoff. Universe: v1's eligible universe that month.
- Budget: each agent sees 13 cards a month, drawn from the universe with seed (agent, month), so
  about 14,800 calls in all. If S1 timing shows this exceeds 24 GPU hours (the crowd's share of
  ~30), cards per agent are cut evenly for every agent and month; months are never dropped or chosen.

## Measures
1. **Herding:** LSV measure (Lakonishok, Shleifer and Vishny 1992) on each stock-month seen by at
   least 3 agents; effective voters N/(1 + (N - 1) rho), rho = mean pairwise correlation of agents'
   pick indicators on shared stocks; first-eigenvalue share of the agent x stock pick matrix.
   Headline: "N AI investors vote like M independent ones".
2. **Diversity:** herding among the 6 personas sharing one information set vs the 5 information
   sets sharing one persona: does what agents see or who they are drive herding?
3. **Memorization:** 10% of cards re-asked with every percentile moved by a random +/-10 points;
   reported: pick agreement against the size of the change.
4. **Crowd model:** ridge regression of crowd consensus (buy share) on the 147 ranks, fitted on
   crowds (a) and (c), penalty chosen by year-block cross-validation; R^2 by block. Saved as
   `fiam/agents/crowd_emulator.json`. The Crowding Index of a book = its long-minus-short average
   crowd score, shown as a percentile against 1,000 random books with the same size and sides.
5. **Without, with and against the crowd:** same optimizer, costs and limits, on v1 and on v2:
   as is; score + k x crowd rank (trade with it); score - k x crowd rank (bet against it); and the
   crowd alone as a long-short. k = the weight of one extra (13th) signal, fixed here. Crowds (a)
   and (b) on the clean window (19 months, exploratory); crowd (c) on 2016-2020, labelled "models
   may know this period". Reported: IR, drawdown, turnover, overlap with v1. No pass or fail. Each
   book here is a trial in the ledger.
6. **Crowd as a risk factor:** crowd factor = equal-weighted top minus bottom decile of crowd score
   (from the crowd model, so it exists for every month 2016-2026; labelled "emulated" outside the
   crowds' own months); AI crowding beta = slope of the book's monthly return on it (HAC t).
   Overlap of v1 and v2 with each crowd and between crowds. Signature chart: crowd consensus vs
   our book, month by month.
7. **AI-crowd sell-off:** the crowd's top decile is sold over 5 days; price impact by the square-root
   law, impact = sigma_daily x sqrt(Q/ADV) (Almgren et al. 2005); crowd size grid $10B, $50B,
   $100B. Reported: cost to v1 and v2 through their holdings of those names.
8. **AI vs short sellers:** in each crowd's own months, Spearman correlation between crowd
   consensus and short interest / shares outstanding (Compustat via `gvkey`, known 8 trading days
   after settlement); share of the crowd's top decile in the top short-interest decile against 10%
   by chance. Two-sided, HAC t; no prior sign.
9. **Carbon Arc on cards (when the data arrives):** the same agents and cards re-asked with Carbon
   Arc columns added; herding and picks compared with and without. Level 1 budget (15-30 minutes).

## Finals
New universe or rules: level 0 = crowd model on CPU (seconds); level 1 = `--crowd-quick` on a GPU
(15-30 minutes, 6 personas x 1 information set, last 3 months); level 2 = full re-run overnight.
Level 0 numbers are labelled "emulated crowd".
