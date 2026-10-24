# The survivorship test (PDF p11) and cross-source agreement (PLAN §6.7).

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam.v4 import links as link_table

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CLEAN = DATA / "v4" / "clean"
OUT = ROOT / "out" / "audit"
FLOOR_MUSD = 600
TEST = (pd.Timestamp("2015-01-01"), pd.Timestamp("2020-12-31"))
# The PDF's six named failures (p11), found by name in the panel.
NAMED = {
    "Sears": "SEARS HOLDINGS",
    "Bon-Ton": "BON TON",
    "Pier 1": "PIER 1",
    "GNC": "GNC HOLDINGS",
    "Ascena": "ASCENA",
    "J.C. Penney": "PENNEY",
}


# The panel's stock-months 2015-2020 with me, ret and the trading flag.
def panel_months() -> pd.DataFrame:
    p = pd.read_parquet(CLEAN / "panel.parquet", columns=["permno", "eom", "me", "ret"])
    p = p[(p["eom"] >= TEST[0]) & (p["eom"] <= TEST[1])].copy()
    p["month"] = p["eom"].dt.to_period("M")
    p["trading"] = p["me"] >= FLOOR_MUSD
    return p


# Months each source holds a row for a stock (its coverage), by source.
def coverage_sets() -> dict[str, set]:
    sets = {}
    for name, date in (("dsf", "date"), ("crsp_monthly", "date"), ("short_interest", "settlement")):
        t = pd.read_parquet(CLEAN / f"{name}.parquet", columns=["permno", date])
        sets[name] = set(zip(t["permno"], t[date].dt.to_period("M")))
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    p = panel_months()
    have = link_table.value_at(lk, "cik", p["permno"], p["eom"]).notna().to_numpy()
    sets["edgar_filings"] = set(zip(p.loc[have, "permno"], p.loc[have, "month"]))
    # A month is covered when a projected release known by then is ahead.
    e = pd.read_parquet(
        CLEAN / "earnings_calendar.parquet", columns=["permno", "known_from", "projected"]
    )
    e = e.merge(p[["permno", "eom", "month"]], on="permno")
    ahead = (e["known_from"] <= e["eom"]) & (e["projected"] > e["eom"])
    sets["earnings_calendar"] = set(zip(e.loc[ahead, "permno"], e.loc[ahead, "month"]))
    k = pd.read_parquet(CLEAN / "key_developments.parquet", columns=["permno", "first_close"])
    k["month"] = pd.to_datetime(k["first_close"]).dt.to_period("M")
    months = k.dropna().drop_duplicates(["permno", "month"])
    window = {(r.permno, r.month + i) for r in months.itertuples() for i in range(12)}
    sets["key_developments"] = window
    return sets


# The leavers to resolve: the six named and 2017-2020 delistings of $500m+.
def leavers() -> pd.DataFrame:
    p = pd.read_parquet(CLEAN / "panel.parquet", columns=["permno", "eom", "me", "company_name"])
    last = p.sort_values("eom").groupby("permno").tail(1)
    named = []
    # Names on any row, letters and digits only ("G N C" is GNC) (M3).
    squash = p["company_name"].fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    for label, text in NAMED.items():
        key = "".join(ch for ch in text if ch.isalnum())
        rows = p[squash.str.contains(key, regex=False)]
        hit = last[last["permno"].isin(rows["permno"])]
        named += [(int(r.permno), r.eom, label) for r in hit.itertuples()]
    ex = pd.read_parquet(CLEAN / "exits.parquet", columns=["permno", "exit_date", "source"])
    ex = ex[
        (ex["source"] == "crsp_delistings") & ex["exit_date"].between("2017-01-01", "2020-12-31")
    ]
    big = last[last["me"] >= 500][["permno", "eom"]].merge(ex[["permno"]], on="permno")
    rows = [(int(r.permno), r.eom, "delisting") for r in big.itertuples()]
    out = pd.DataFrame(named + rows, columns=["permno", "eom", "why"])
    return out.drop_duplicates("permno")


# Newey-West t of a monthly series' mean, 6 lags (PLAN §6.8).
def nw_t(series: pd.Series) -> float:
    y = series.dropna().to_numpy()
    if len(y) < 12:
        return float("nan")
    fit = sm.OLS(y, np.ones(len(y))).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return float(fit.tvalues[0])


# The PDF's survivorship test per firm-keyed source (§6.8).
def survivorship() -> dict:
    p = panel_months()
    sets = coverage_sets()
    gone = leavers()
    report = {
        "leavers": len(gone),
        "named_found": sorted(gone.loc[gone["why"] != "delisting", "why"]),
    }
    for name, have in sets.items():
        before = gone.assign(month=gone["eom"].dt.to_period("M"))
        resolved = np.mean([(r.permno, r.month) in have for r in before.itertuples()])
        trade = p[p["trading"]].copy()
        trade["covered"] = [(a, b) in have for a, b in zip(trade["permno"], trade["month"])]
        means = trade.groupby(["month", "covered"])["ret"].mean().unstack()
        gap = means.get(True, pd.Series(dtype=float)) - means.get(False, pd.Series(dtype=float))
        # Robustness: coverage at m against the next month's return, any
        # panel row, so a name leaving the universe still counts.
        ahead = trade[trade["month"] < TEST[1].to_period("M")]
        nxt = ahead.merge(
            p[["permno", "month", "ret"]].assign(month=p["month"] - 1),
            on=["permno", "month"],
            suffixes=("", "_next"),
        )
        lead = nxt.groupby(["month", "covered"])["ret_next"].mean().unstack()
        gap_next = lead.get(True, pd.Series(dtype=float)) - lead.get(False, pd.Series(dtype=float))
        share = float(trade["covered"].mean())
        cls = "universe-level" if resolved < 0.5 else "crosswalk-only"
        report[name] = {
            "class": cls,
            "leavers_resolved": round(float(resolved), 4),
            "covered_share_of_trading_months": round(share, 4),
            "gap_months": int(gap.notna().sum()),
            "gap_mean_monthly": round(float(gap.mean()), 5) if gap.notna().any() else None,
            "gap_nw_t": round(nw_t(gap), 2),
            "gap_next_month_nw_t": round(nw_t(gap_next), 2),
        }
        report[name]["needs_written_control"] = bool(abs(report[name]["gap_nw_t"]) > 2)
    report["immune"] = ["crsp_market_daily", "vix", "french", "tb3ms"]
    return report


# Share of rows within a tolerance, the bar and the verdict.
def share_within(diff: pd.Series, tolerance: float, bar: float) -> dict:
    ok = diff.dropna().abs() <= tolerance
    share = float(ok.mean()) if len(ok) else float("nan")
    return {"rows": int(len(ok)), "share": round(share, 4), "bar": bar, "pass": share >= bar}


# The cross-source agreement exhibit on 2015-2020 (protocol data section).
def agreement() -> dict:
    p = panel_months()
    m = pd.read_parquet(
        CLEAN / "crsp_monthly.parquet", columns=["permno", "date", "ret", "retx", "cap_musd"]
    )
    m["month"] = m["date"].dt.to_period("M")
    both = p.merge(m, on=["permno", "month"], suffixes=("", "_crsp"))
    report = {
        "panel_ret_vs_crsp": share_within(both["ret"] - both["ret_crsp"], 1e-6, 0.99),
        "panel_me_vs_crsp_cap": share_within(both["me"] / both["cap_musd"] - 1, 0.005, 0.99),
    }
    d = pd.read_parquet(CLEAN / "dsf.parquet", columns=["permno", "date", "ret"])
    d = d[(d["date"] >= TEST[0]) & (d["date"] <= TEST[1])]
    d["month"] = d["date"].dt.to_period("M")
    comp = (1 + d["ret"]).groupby([d["permno"], d["month"]]).prod() - 1
    comp = (
        comp.rename("dsf")
        .reset_index()
        .merge(m[["permno", "month", "retx"]], on=["permno", "month"])
    )
    report["dsf_compounded_vs_crsp_retx"] = share_within(comp["dsf"] - comp["retx"], 1e-4, 0.99)
    last = (
        pd.read_parquet(CLEAN / "panel.parquet", columns=["permno", "eom"])
        .groupby("permno")["eom"]
        .max()
    )
    left = last[(last >= TEST[0]) & (last < pd.Timestamp("2020-12-01"))]
    ex = pd.read_parquet(CLEAN / "exits.parquet", columns=["permno"])
    later = m.groupby("permno")["date"].max()
    known = left.index.isin(ex["permno"]) | (later.reindex(left.index) > left).to_numpy()
    report["panel_exits_vs_crsp"] = {
        "leavers": int(len(left)),
        "share": round(float(np.mean(known)), 4),
        "bar": 0.99,
        "pass": bool(np.mean(known) >= 0.99),
    }
    firms = pd.read_parquet(DATA / "edgar" / "cik_map.parquet")
    report["compustat_cik_vs_8k_pairs"] = {
        "both_agree": int(
            (firms["cik_compustat"].notna() & firms["cik_8k"].notna() & ~firms["conflict"]).sum()
        ),
        "conflicts_settled": int(firms["conflict"].sum()),
        "one_source": int((firms["cik_compustat"].isna() ^ firms["cik_8k"].isna()).sum()),
        "none": int((firms["cik_compustat"].isna() & firms["cik_8k"].isna()).sum()),
    }
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    scores = {}
    for kind in ("ibes", "secid", "taq"):
        sub = lk[lk["kind"] == kind]
        scores[kind] = sub["score"].value_counts(dropna=False).sort_index().to_dict()
    report["link_scores"] = {k: {str(s): int(n) for s, n in v.items()} for k, v in scores.items()}
    report["pending"] = {
        "ca0065s": "not orderable (2026-10-23)",
        "13f": "step 6",
        "insiders": "step 3b",
    }
    return report


# Runs both and writes out/audit: uv run python -m fiam.v4.agreement
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    s = survivorship()
    (OUT / "survivorship.json").write_text(json.dumps(s, indent=1, default=str))
    a = agreement()
    (OUT / "agreement.json").write_text(json.dumps(a, indent=1, default=str))
    print(json.dumps({"survivorship": s, "agreement": a}, indent=1, default=str))
