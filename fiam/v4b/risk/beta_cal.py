# Calibration of the hedge beta to the beta a book actually realises.
# risk/accuracy.py (pre-2021): realised next-21-session book beta exceeded the
# predicted one by +0.149 on the volneut decile book (long leg +0.067, short
# leg +0.082): low predicted betas realise higher, high ones lower, i.e. the
# Vasicek + 60m blend shrinks too little. Map, re-estimated every formation
# on earlier months only (expanding window, >= 12 months, none before):
#   realised_i = a_t + b_t * predicted_i   cross-sectional OLS each eom t over
#   the liquid universe, realised = OLS slope of the next 21 sessions' daily
#   excess return on the market (returns clipped at +-50% as in beta.py,
#   realised betas winsorised 1/99% within month);
#   calibrated beta at eom e = mean(a_t) + mean(b_t) * predicted, over t whose
#   21-session window ended before e's formation session.
# Torch for the per-name window regressions (GPU when present).

import numpy as np
import pandas as pd
import torch

from fiam.v4b.risk import beta as beta_mod
from fiam.v4b.risk.enhanced import DEV, _t

HORIZON, MIN_MONTHS = 21, 12


def realised_forward(excess: pd.DataFrame, mkt: pd.Series, eom) -> tuple[pd.Series, pd.Timestamp | None]:
    pos = excess.index.searchsorted(pd.Timestamp(eom), side="right")
    block = excess.iloc[pos: pos + HORIZON]
    if len(block) < HORIZON:
        return pd.Series(dtype=float), None
    r = _t(block.clip(-beta_mod.CLIP, beta_mod.CLIP).to_numpy())
    m = _t(mkt.reindex(block.index).to_numpy())
    ok = ~torch.isnan(r)
    n = ok.sum(0)
    mm = torch.where(ok, m[:, None], torch.zeros_like(r))
    rr = torch.nan_to_num(r)
    mbar, rbar = mm.sum(0) / n.clamp(min=1), rr.sum(0) / n.clamp(min=1)
    cov = (torch.where(ok, (mm - mbar) * (rr - rbar), torch.zeros_like(r))).sum(0)
    var = (torch.where(ok, (mm - mbar) ** 2, torch.zeros_like(r))).sum(0)
    b = torch.where((n >= 15) & (var > 0), cov / var, torch.full_like(cov, float("nan")))
    return pd.Series(b.cpu().numpy(), index=block.columns), block.index[-1]


def monthly_maps(rm) -> pd.DataFrame:
    excess, mk = beta_mod.excess_wide(cut=rm.cut)
    rows = []
    for eom, g in rm.betas.groupby("eom"):
        live = rm.exp[(rm.exp["eom"] == eom) & rm.exp["long_ok"]]["permno"]
        pred = g.set_index("permno")["beta_hedge"].reindex(live).dropna()
        real, end = realised_forward(excess, mk["mkt_rf"], eom)
        both = pd.concat([pred.rename("p"), real.reindex(pred.index).rename("r")], axis=1).dropna()
        if end is None or len(both) < 200:
            continue
        lo, hi = both["r"].quantile([0.01, 0.99])
        both["r"] = both["r"].clip(lo, hi)
        b, a = np.polyfit(both["p"], both["r"], 1)
        rows.append({"eom": pd.Timestamp(eom), "end": end, "a": a, "b": b, "n": len(both)})
    return pd.DataFrame(rows)


# (a, b) in force at a formation whose first session is s0; None before MIN_MONTHS.
def map_at(maps: pd.DataFrame, s0) -> tuple[float, float] | None:
    known = maps[maps["end"] < pd.Timestamp(s0)]
    if len(known) < MIN_MONTHS:
        return None
    return float(known["a"].mean()), float(known["b"].mean())
