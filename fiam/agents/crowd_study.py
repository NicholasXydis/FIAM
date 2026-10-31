# The AI crowd study: herding, agreement, the crowd score and its risk.

import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from fiam import stocks as S
from fiam.paths import FROZEN

# The crowd model, a ridge fitted to the agents' picks and kept frozen.
EMULATOR = FROZEN / "agents" / "crowd_emulator.json"
CROWD_SIZES = (10e9, 50e9, 100e9)


# LSV herding (Lakonishok et al. 1992) on stock-months 3+ agents saw.
def lsv(picks: pd.DataFrame) -> dict:
    g = picks.groupby(["eom", "permno"])["picked"].agg(["sum", "count"])
    g = g[g["count"] >= 3]
    g["p"] = g["sum"] / g["count"]
    p_bar = g.groupby(level="eom")["p"].transform("mean")
    expected = [
        sum(st.binom.pmf(k, n, pb) * abs(k / n - pb) for k in range(n + 1))
        for n, pb in zip(g["count"], p_bar)
    ]
    h = (g["p"] - p_bar).abs() - np.array(expected)
    return dict(
        lsv=float(h.mean()), lsv_t=float(h.mean() / h.std() * np.sqrt(len(h))), cells=len(h)
    )


# Mean pairwise pick correlation on shared stocks, and effective voters.
def agreement(picks: pd.DataFrame, agents: list | None = None) -> dict:
    wide = picks.pivot_table(
        index=["eom", "permno"], columns="agent", values="picked", aggfunc="max"
    )
    if agents is not None:
        wide = wide[[a for a in agents if a in wide]]
    corr = wide.astype(float).corr(min_periods=30)
    n = corr.shape[0]
    rho = float(np.nanmean(corr.where(~np.eye(n, dtype=bool)).to_numpy()))
    eig = np.linalg.eigvalsh(np.nan_to_num(corr.to_numpy(), nan=0.0) + np.eye(n) * 0)
    return dict(
        agents=n,
        mean_correlation=rho,
        effective_voters=float(n / (1 + (n - 1) * rho)) if rho > -1 / max(n - 1, 1) else float(n),
        first_eigen_share=float(eig.max() / max(eig.sum(), 1e-12)),
    )


# Buy share per stock-month: share of those who saw it that picked it.
def consensus(picks: pd.DataFrame) -> pd.DataFrame:
    vote = picks["picked"].astype(float) - picks.get("shorted", False)
    g = vote.groupby([picks["eom"], picks["permno"]]).mean().rename("consensus").reset_index()
    return g


# The 147 as 0-1 ranks for the crowd model, screened months 2015-2026.
def ranks(first: str = "2015-01-31", last: str = "2026-07-31") -> pd.DataFrame:
    chars = S.characteristics()
    frame = S.screen(S.load_panel(tuple(c for c in chars if c not in S.SIGNALS)), first, last)
    # Raw volatility and volume kept for the sell-off, as both get ranked.
    frame["vol_raw"], frame["dolvol_raw"] = frame["rvol_21d"], frame["dolvol_126d"]
    for col in chars:
        frame[col] = frame.groupby("eom")[col].rank(pct=True).fillna(0.5)
    return frame


# Scores rows with a frozen ridge, centred on its saved means.
def predict(model: dict, x: np.ndarray) -> np.ndarray:
    return model["intercept"] + (x - np.array(model["mean"])) @ np.array(model["coef"])


# Crowd score for any frame with the 147 as 0-1 ranks: level 0, no GPU.
def crowd_score(frame: pd.DataFrame) -> pd.Series:
    model = json.loads(EMULATOR.read_text(encoding="utf-8"))
    return pd.Series(predict(model, frame[model["columns"]].to_numpy()), index=frame.index)


# Monthly return of the crowd's top minus bottom decile, equal weight.
def crowd_factor(scored: pd.DataFrame) -> pd.Series:
    rows = {}
    for eom, g in scored.dropna(subset=["ret_exc_lead1m"]).groupby("eom"):
        top = g["crowd_score"] >= g["crowd_score"].quantile(0.9)
        bottom = g["crowd_score"] <= g["crowd_score"].quantile(0.1)
        rows[(eom + pd.offsets.MonthBegin(1)).normalize()] = (
            g.loc[top, "ret_exc_lead1m"].mean() - g.loc[bottom, "ret_exc_lead1m"].mean()
        )
    return pd.Series(rows).sort_index()


# A book's beta to the crowd factor, with its Newey-West t.
def crowding_beta(net: pd.Series, factor: pd.Series) -> dict:
    both = pd.concat([net.rename("r"), factor.rename("f")], axis=1).dropna()
    fit = sm.OLS(both["r"], sm.add_constant(both["f"])).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return dict(beta=float(fit.params["f"]), t=float(fit.tvalues["f"]), months=len(both))


# A book's loss if the crowd sells favourites over 5 days, sqrt impact.
def sell_off(held_month: pd.Series, month: pd.DataFrame, crowd_size: float) -> float:
    top = month[month["crowd_score"] >= month["crowd_score"].quantile(0.9)].set_index("permno")
    sold = crowd_size / len(top) / 5
    sigma = top["vol_raw"].fillna(top["vol_raw"].median())
    dollars = top["dolvol_raw"].fillna(top["dolvol_raw"].median())
    drop = np.minimum(sigma * np.sqrt(sold / dollars) * np.sqrt(5), 1.0)
    return float(-(held_month.reindex(drop.index).fillna(0.0) * drop).sum())
