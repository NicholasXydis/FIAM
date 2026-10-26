# 13F crowding (lever C3): short-horizon filers' sole shares held.

import pandas as pd

from fiam.v4 import data
from fiam.v4.signals import best_ideas

# Churn over a filer's last four quarters; the top third are short.
QUARTERS, SHORT_HORIZON = 4, 1 / 3
# No new long in the top 1% of the formation's universe by crowding.
TOP = 0.01


# Each quarter's price return per stock from CRSP months.
def quarter_returns(periods) -> pd.DataFrame:
    first = min(periods) - pd.offsets.MonthEnd(3)
    m = data.table("crsp_monthly", ["retx", "shrout_k"], where={"date": (first, max(periods))})
    m = m.assign(month=m["date"] + pd.offsets.MonthEnd(0))
    m = m[m["month"] <= data.CRSP_END]
    # After 2025 the panel's month return and cap over price (Medium 5).
    if max(periods) > data.CRSP_END:
        after = data.CRSP_END + pd.offsets.MonthEnd(1)
        p = data.table("panel", ["ret", "me", "prc"], where={"eom": (after, max(periods))})
        p = p.assign(month=p["eom"], retx=p["ret"], shrout_k=p["me"] * 1e3 / p["prc"].abs())
        m = pd.concat([m, p[["permno", "month", "retx", "shrout_k"]]], ignore_index=True)
    out = []
    for period in sorted(set(periods)):
        span = m[(m["month"] > period - pd.offsets.MonthEnd(3)) & (m["month"] <= period)]
        growth = (1 + span.groupby("permno")["retx"].prod(min_count=1)) - 1
        shares = span[span["month"] == period].groupby("permno")["shrout_k"].last() * 1000
        out.append(pd.DataFrame({"period": period, "retx": growth, "shares_out": shares}))
    return pd.concat(out).rename_axis("permno").reset_index()


# Every version's holdings once, by filer, period and version.
class Holdings:
    # Versions of every report and their summed lines per stock.
    def __init__(self, first, last):
        cols = ["filer_cik", "period", "form", "amendmenttype", "units"]
        r = data.table("sec_13f_reports", cols)
        r = r[r["period"].between(pd.Timestamp(first), pd.Timestamp(last))]
        self.log: dict = {}
        v = best_ideas.versions(r, self.log).reset_index(drop=True)
        v["version"] = v.index
        lines = data.table("sec_13f", ["value_usd", "shares_sole"],
                           where={"accession": set(r["accession"])})  # fmt: skip
        parts = v.assign(accession=[(b, *a) for b, a in zip(v["base"], v["adds"])])
        parts = parts.explode("accession")[["version", "accession"]]
        held = parts.merge(lines[["accession", "permno", "value_usd", "shares_sole"]],
                           on="accession")  # fmt: skip
        self.held = held.groupby(["version", "permno"], as_index=False)[
            ["value_usd", "shares_sole"]
        ].sum()
        self.versions = v[["filer_cik", "period", "since", "version"]]
        self.returns = quarter_returns(v["period"].unique())

    # Each filer's version of each period public by T, the latest one.
    def at(self, T) -> pd.DataFrame:
        v = self.versions[self.versions["since"] <= pd.Timestamp(T)]
        v = v.sort_values(["period", "since"], kind="stable")
        return v.drop_duplicates(["filer_cik", "period"], keep="last")


# Crowding at T: short-horizon filers' sole shares over shares out.
def crowding(h: Holdings, T) -> pd.Series:
    quarters = pd.date_range(end=pd.Timestamp(T), periods=7, freq="QE")
    recent = set(quarters[quarters <= pd.Timestamp(T)][-2:])
    v = h.at(T).sort_values(["filer_cik", "period"])
    v["rank"] = v.groupby("filer_cik").cumcount(ascending=False)
    latest = v[(v["rank"] == 0) & v["period"].isin(recent)]
    v = v[v["filer_cik"].isin(latest["filer_cik"]) & (v["rank"] <= QUARTERS)]
    # Each of the last four periods paired with the filer's one before.
    before = v.assign(rank=v["rank"] - 1)[["filer_cik", "rank", "period", "version"]]
    pairs = v[v["rank"] < QUARTERS].merge(before, on=["filer_cik", "rank"], suffixes=("", "_b"))
    pairs = pairs[(pairs["period"] - pairs["period_b"]).dt.days <= 100]
    held = h.held[["version", "permno", "value_usd"]]
    a = pairs[["filer_cik", "period", "version"]].merge(held, on="version")
    b = pairs[["filer_cik", "period", "version_b"]].merge(
        held.rename(columns={"version": "version_b"}), on="version_b"
    )
    both = a.merge(b, on=["filer_cik", "period", "permno"], how="outer", suffixes=("_t", "_b"))
    both[["value_usd_t", "value_usd_b"]] = both[["value_usd_t", "value_usd_b"]].fillna(0.0)
    both = both.merge(h.returns[["permno", "period", "retx"]], on=["permno", "period"], how="left")
    # GMM churn in values: V_t less V_t-1 grown by the stock's return.
    grown = both["value_usd_b"] * (1 + both["retx"].fillna(0.0))
    both["moved"] = (both["value_usd_t"] - grown).abs()
    both["mean"] = (both["value_usd_t"] + both["value_usd_b"]) / 2
    q = both.groupby(["filer_cik", "period"])[["moved", "mean"]].sum()
    rate = (q["moved"] / q["mean"].where(q["mean"] > 0)).groupby("filer_cik").mean().dropna()
    short = rate[rate >= rate.quantile(1 - SHORT_HORIZON)].index
    top = latest[latest["filer_cik"].isin(short)][["version", "period"]]
    sole = top.merge(h.held[["version", "permno", "shares_sole"]], on="version")
    sole = sole.merge(h.returns[["permno", "period", "shares_out"]], on=["permno", "period"])
    return (sole["shares_sole"] / sole["shares_out"]).groupby(sole["permno"]).sum()


# The crowded flag: the top 1% of the universe by crowding at T.
def crowded(ids, h: Holdings, T, c: pd.Series | None = None) -> pd.Series:
    c = (crowding(h, T) if c is None else c).reindex(ids).fillna(0.0)
    cut = c.quantile(1 - TOP)
    # A zero cut would flag every name: then none is crowded.
    return (c >= cut) & (cut > 0)
