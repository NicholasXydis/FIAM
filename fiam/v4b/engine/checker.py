# The finals rules checked on executed, drifted books (R§2).

import numpy as np
import pandas as pd

from fiam.v4b.engine.mandate import Final

# Weights below this are treated as no position.
EPS = 1e-9
# Room for float rounding on a limit, as a share of NAV.
TOL = 1e-6


# Market cap for the short floor: min(me, me_company), USD m.
def floor_cap(panel: pd.DataFrame) -> pd.Series:
    return panel[["me", "me_company"]].min(axis=1, skipna=False)


def short_floor_formation(weights: pd.Series, month: pd.DataFrame, floor: float) -> bool:
    """Check each formation short's dated market cap; absent data fails closed."""
    shorts = weights.index[weights < -EPS]
    if shorts.empty:
        return True
    if not {"me", "me_company"}.issubset(month.columns) or not month.index.is_unique:
        return False
    cap = floor_cap(month.reindex(shorts))
    return bool(cap.ge(floor).all())


# Each (date, permno)'s floor cap at the last eom before date.
def caps_at(pairs: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    p = panel.assign(cap=floor_cap(panel))[["permno", "eom", "cap"]].dropna().copy()
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    p = p.sort_values("eom")
    q = pairs[["date", "permno"]].reset_index().copy()
    q["date"] = pd.to_datetime(q["date"]).astype("datetime64[ns]")
    q = q.sort_values("date")
    # Strictly before: a panel row is public after its own eom close.
    got = pd.merge_asof(
        q, p, left_on="date", right_on="eom", by="permno", allow_exact_matches=False
    )
    return got.set_index("index")["cap"].reindex(pairs.index)


# One breach row per date, rule and name; empty means compliant.
def check(
    positions: pd.DataFrame, panel: pd.DataFrame, m: Final, ramp_days: int = 0, sessions=None
):
    h = m.hard
    held = positions[positions["w"].abs() > EPS]
    by = held.groupby("date")["w"]
    days = pd.DataFrame(
        {
            "names": by.size(),
            "gross": by.apply(lambda w: w.abs().sum()),
            "net": by.sum(),
            "largest": by.apply(lambda w: w.abs().max()),
        }
    )
    calendar = pd.DatetimeIndex(
        sorted(positions["date"].unique()) if sessions is None else sessions
    )
    days = days.reindex(calendar, fill_value=0)
    ramp = set(calendar[:ramp_days])
    rows = []
    for date, d in days.iterrows():
        if not h.names_min <= d["names"] <= h.names_max and date not in ramp:
            limit = h.names_min if d["names"] < h.names_min else h.names_max
            rows.append((date, "names", None, d["names"], limit))
        if d["gross"] > h.gross_max + TOL:
            rows.append((date, "gross", None, d["gross"], h.gross_max))
        if abs(d["net"]) > h.net_band + TOL:
            rows.append((date, "net", None, d["net"], h.net_band))
        if d["largest"] > h.name_cap + TOL:
            rows.append((date, "name_cap", None, d["largest"], h.name_cap))
    rows += _short_floor(positions, panel, h.short_floor_musd)
    if "adv_days" in held:
        exit_days = held["adv_days"] / m.policy.participation
        bad = held[~(exit_days <= m.policy.days_to_exit_max + TOL)]
        rows += [
            (r.date, "liquidation_days", int(r.permno), exit_days.loc[i], m.policy.days_to_exit_max)
            for i, r in bad.iterrows()
        ]
    if {"trade_dollars", "adv_dollars"} <= set(positions):
        traded = positions[positions["trade_dollars"].abs() > EPS]
        ratio = traded["trade_dollars"].abs() / traded["adv_dollars"]
        bad = traded[~(ratio <= m.policy.participation + TOL)]
        rows += [
            (r.date, "participation", int(r.permno), ratio.loc[i], m.policy.participation)
            for i, r in bad.iterrows()
        ]
    breaches = pd.DataFrame(rows, columns=["date", "rule", "permno", "value", "limit"])
    return breaches, days


# Shorts held at a rebalance, or added by any trade, need the floor.
def _short_floor(positions: pd.DataFrame, panel: pd.DataFrame, floor: float) -> list:
    short = positions["w"] < -EPS
    added = (
        positions["trade_dollars"] < -EPS
        if "trade_dollars" in positions
        else positions["w"] < positions["w_pre"] - TOL
    )
    need = short & (positions["rebalance"] | added)
    todo = positions[need]
    if todo.empty:
        return []
    cap = caps_at(todo, panel)
    bad = todo[~(cap >= floor).to_numpy()]
    return [
        (r[0], "short_floor", int(r[1]), c, floor)
        for r, c in zip(
            bad[["date", "permno"]].itertuples(index=False, name=None), cap[bad.index].to_numpy()
        )
    ]


# NAV ledger checks: compounding and the return's parts add up.
def policy_diagnostics(positions: pd.DataFrame, dated: pd.DataFrame, m: Final) -> pd.DataFrame:
    q = positions.loc[positions["w"].abs() > EPS, ["date", "permno", "w"]].copy()
    p = dated.copy()
    q["date"] = pd.to_datetime(q["date"]).astype("datetime64[ns]")
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    joined = pd.merge_asof(
        q.sort_values("date"),
        p.sort_values("eom"),
        left_on="date",
        right_on="eom",
        by="permno",
        allow_exact_matches=False,
    )
    joined["beta_w"] = joined["w"] * joined["beta"]
    joined["size_w"] = joined["w"] * joined["size"]
    groups = joined.groupby("date")
    days = groups.agg(
        beta=("beta_w", "sum"), size=("size_w", "sum"), size_band=("size_band", "first")
    )
    days["sector_max"] = joined.groupby(["date", "sector"])["w"].sum().abs().groupby("date").max()
    missing = joined[["beta", "size", "sector", "size_band"]].isna().any(axis=1)
    days["missing_exposures"] = missing.groupby(joined["date"]).sum()
    days["violated"] = (
        (days["beta"].abs() > m.policy.beta_band + TOL)
        | (days["size"].abs() > days["size_band"] + TOL)
        | (days["sector_max"] > m.policy.sector_band + TOL)
        | (days["missing_exposures"] > 0)
    )
    return days


# NAV ledger checks: compounding and the return's parts add up.
def reconcile(ledger: pd.DataFrame, tol: float = 1e-9) -> list[str]:
    out = []
    nav = ledger["nav"].to_numpy()
    grown = nav[:-1] * (1 + ledger["ret"].to_numpy()[1:])
    gap = np.abs(grown - nav[1:]) / nav[:-1]
    if (gap > tol).any():
        out.append(f"NAV does not compound on {int((gap > tol).sum())} days")
    parts = ["pnl", "interest", "spread", "impact", "fees", "borrow"]
    if set(parts) <= set(ledger.columns):
        total = ledger["pnl"] + ledger["interest"] - ledger[parts[2:]].sum(axis=1)
        prev = ledger["nav"].shift(1)
        miss = (total / prev - ledger["ret"]).abs().iloc[1:]
        if (miss > tol).any():
            out.append(f"return parts do not sum on {int((miss > tol).sum())} days")
    return out
