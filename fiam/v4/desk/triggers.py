# The desk's triggers (PLAN §10.2, step 8 rules): past-only, in code.

import numpy as np
import pandas as pd

from fiam.v4 import data

# Earnings within 5 sessions; a loss beyond 3 sigma; vol over its 99th.
EARNINGS_DAYS, LOSS_SIGMA, JUMP_PCT, JUMP_DAYS = 5, 3.0, 0.99, 5
# OptionMetrics ends here; realised vol stands in after (PLAN §6.5).
OPTIONS_END = pd.Timestamp("2025-08-31")


# Names whose next earnings, as projected by d, fall in 5 sessions.
def earnings(ids, d, calendar: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict:
    d = pd.Timestamp(d)
    seen = calendar[(calendar["first_close"] <= d) & (calendar["projected"] > d)]
    seen = seen[seen["permno"].isin(set(ids))]
    data.assert_public_by(seen["first_close"], d, "earnings projections")
    nxt = seen.groupby("permno")["projected"].min()
    ahead = sessions[sessions > d]
    days = pd.Series(ahead.searchsorted(nxt.to_numpy(), side="left") + 1, index=nxt.index)
    return days[days <= EARNINGS_DAYS].astype(int).to_dict()


# A name's signed loss today in units of its daily vol, beyond -3.
def losses(w: pd.Series, r: pd.Series, sigma_d: pd.Series) -> dict:
    move = np.sign(w) * r.reindex(w.index) / sigma_d.reindex(w.index)
    return move[move < -LOSS_SIGMA].round(2).to_dict()


# Vol jumps: 5-session log change, against every earlier day's 99th.
class Jumps:
    # Each stock-day's change, dated by the close it became public.
    def __init__(self, vol: pd.DataFrame):
        change = np.log(vol).diff(JUMP_DAYS)
        self.change = change
        flat = change.stack().dropna()
        self.days = flat.index.get_level_values(0)
        self.values, self.cuts = flat.to_numpy(), {}

    # The past-only cut, refreshed each month from every day before it.
    def cut(self, d) -> float:
        start = pd.Timestamp(d).to_period("M").start_time
        if start not in self.cuts:
            past = self.values[self.days < start]
            self.cuts[start] = float(np.quantile(past, JUMP_PCT)) if len(past) else np.inf
        return self.cuts[start]

    # Held names whose latest change public by d is past the cut.
    def at(self, d, ids) -> dict:
        rows = self.change.loc[: pd.Timestamp(d)]
        if rows.empty:
            return {}
        last = rows.iloc[-1].reindex(list(ids))
        cut = self.cut(rows.index[-1])
        return last[last > cut].round(2).to_dict()
