# 13F best ideas: a fund's highest-conviction stock (Cohen-Polk-Silli).

import numpy as np
import pandas as pd

from fiam.v4 import data
from fiam.v4.signals import base

# Being many funds' best idea is good news: the gate takes it as is.
SIGN = 1
# A filer counts with at least 20 matched stocks (the step 4 checklist).
MIN_STOCKS = 20
# Same-day versions apply in this order: original, restatement, adds.
ORDER = {"ORIGINAL": 0, "RESTATEMENT": 1, "NEW HOLDINGS": 2}


# A filer-period's versions: restatements replace, new holdings add.
def versions(reports: pd.DataFrame, log: dict) -> pd.DataFrame:
    r = reports.copy()
    amend = r["form"] == "13F-HR/A"
    kind = r["amendmenttype"].fillna("").str.strip().str.upper()
    log["amendments_without_a_type_left_out"] = int((amend & (kind == "")).sum())
    r = r[~amend | kind.isin(["RESTATEMENT", "NEW HOLDINGS"])]
    r = r.assign(kind=np.where(r["form"] == "13F-HR", "ORIGINAL", kind.reindex(r.index)))
    r = r.assign(order=r["kind"].map(ORDER))
    r = r.sort_values(["first_close", "order", "accession"], kind="stable")
    rows = []
    for (filer, period), g in r.groupby(["filer_cik", "period"], sort=False):
        base_acc, adds = None, []
        for acc, kind_k, seen in g[["accession", "kind", "first_close"]].itertuples(index=False):
            if kind_k in ("ORIGINAL", "RESTATEMENT") and (
                base_acc is None or kind_k == "RESTATEMENT"
            ):
                base_acc, adds = acc, []
            elif kind_k == "NEW HOLDINGS" and base_acc is not None:
                adds = [*adds, acc]
            else:
                continue
            rows.append((filer, period, seen, base_acc, tuple(adds)))
    cols = ["filer_cik", "period", "since", "base", "adds"]
    return pd.DataFrame(rows, columns=cols)


# Each version's best idea, the largest tilt; under 20 stocks, none.
def best(v: pd.DataFrame, holdings: pd.DataFrame, market: dict) -> pd.DataFrame:
    lines = {acc: g for acc, g in holdings.groupby("accession")}
    out = []
    for row in v.itertuples(index=False):
        parts = [lines[a] for a in (row.base, *row.adds) if a in lines]
        h = pd.Series(dtype=float)
        if parts:
            h = pd.concat(parts).groupby("permno")["value_usd"].sum(min_count=1).dropna()
            h = h[h > 0]
        mw = market.get(row.period)
        idea, held = -1, ()
        if len(h) >= MIN_STOCKS and mw is not None:
            tilt = h / h.sum() - mw.reindex(h.index).fillna(0.0)
            idea, held = int(tilt.idxmax()), tuple(h.index)
        out.append((row.filer_cik, row.period, row.since, idea, held))
    return pd.DataFrame(out, columns=["filer_cik", "period", "since", "best", "held"])


# Each period end's value weights of CRSP's US common stocks.
def market_weights(periods) -> dict:
    out = {}
    for period in sorted(set(periods)):
        m = data.table("crsp_monthly", ["cap_musd", "sharetype", "securitytype"],
                       where={"date": (period - pd.Timedelta(days=6), period)})  # fmt: skip
        m = m[(m["sharetype"] == "NS") & (m["securitytype"] == "EQTY")]
        m = m.sort_values("date").drop_duplicates("permno", keep="last").set_index("permno")
        out[period] = m["cap_musd"] / m["cap_musd"].sum()
    return out


# The share of a stock's 13F holders for which it is the best idea.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    cols = ["filer_cik", "period", "form", "amendmenttype", "units"]
    reports = data.table("sec_13f_reports", cols)
    v = versions(reports, log)
    holdings = data.table("sec_13f", ["value_usd"], where={"accession": set(reports["accession"])})
    ideas = best(v, holdings[["accession", "permno", "value_usd"]], market_weights(v["period"]))
    log["filer_versions_with_20_stocks"] = int((ideas["best"] >= 0).sum())
    out = []
    for eom, T in base.formations(eoms).itertuples(index=False):
        quarters = pd.date_range(end=T, periods=7, freq="QE")
        latest_two = set(quarters[quarters <= T][-2:])
        live = ideas[ideas["since"] <= T].sort_values(["period", "since"], kind="stable")
        # Each filer's latest period public by T, in its latest version.
        live = live.drop_duplicates("filer_cik", keep="last")
        data.assert_public_by(live["since"], T, "13F reports")
        # That period must be recent and hold 20 stocks, else the filer is out.
        live = live[live["period"].isin(latest_two) & (live["best"] >= 0)]
        held = live.explode("held")
        holders = held.groupby("held").size()
        ideas_n = live.groupby("best").size().reindex(holders.index).fillna(0)
        frame = pd.DataFrame({"permno": holders.index.astype(int), "eom": eom,
                              "value": (ideas_n / holders).to_numpy(),
                              "holders": holders.to_numpy()})  # fmt: skip
        out.append(frame)
    return pd.concat(out, ignore_index=True)
