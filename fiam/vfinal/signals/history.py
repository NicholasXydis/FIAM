# The history twin: SYY-10 rebuilt from CRSP and Compustat.

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import agreement, asfiled, clock, compustat, data, links, ranks, rebuild
from fiam.vfinal.signals import syy

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "audit" / "engine" / "history"
# The twin runs 2000-2020; 2015-2020 only to measure it on the panel.
SPAN = (pd.Timestamp("2000-01-31"), pd.Timestamp("2020-12-31"))
PANEL_FROM = pd.Timestamp("2015-01-31")
# A part matching the panel ranks under 0.95 is missing early.
BAR = 0.95
# The panel-like universe of the gate rules, dated from CRSP.
EXCHANGES = {"N", "A", "Q"}
MIN_CAP, MIN_PRICE = 600.0, 5.0
# Momentum: months t-11 to t-1, all eleven present (JKP's 12-1).
MOMENTUM_MONTHS = 11
# Compustat items the eight accounting parts read, with their year-ago.
ANNUAL = ["at", "lt", "act", "lct", "ni", "ib", "sale", "cogs", "gp", "oancf", "che", "dltt",
          "dlc", "ceq", "mib", "pstk", "ppegt", "invt", "sstk", "prstkc", "pi", "dp"]  # fmt: skip
LAGGED = ["at", "ppegt", "invt", "ni"]


# CRSP's monthly rows with the twin's flags, and the universe months.
def crsp_months() -> pd.DataFrame:
    cols = ["ret", "prc", "cap_musd", "shrout_k", "sharetype", "securitytype", "primaryexch"]
    cols += ["usincflg", "issuertype"]
    start = SPAN[0] - pd.DateOffset(months=13)
    m = data.table("crsp_monthly", cols, where={"date": (start, SPAN[1])})
    m["eom"] = (m["date"] + pd.offsets.MonthEnd(0)).dt.normalize()
    m["universe"] = (
        (m["sharetype"] == "NS") & (m["securitytype"] == "EQTY")
        & m["primaryexch"].isin(EXCHANGES) & (m["usincflg"] == "Y") & (m["issuertype"] == "CORP")
        & (m["cap_musd"] >= MIN_CAP) & (m["prc"].abs() >= MIN_PRICE)
    )  # fmt: skip
    return m


# ret_12_1 and chcsho_12m from CRSP, per stock and month end.
def market_parts(m: pd.DataFrame) -> pd.DataFrame:
    m = m.sort_values(["permno", "eom"]).set_index(["permno", "eom"])
    g = m.groupby(level="permno")
    # Months t-11..t-1: the eleven before t, each one present.
    log1 = np.log1p(m["ret"].astype(float))
    past = log1.groupby(level="permno").transform(
        lambda s: s.shift(1).rolling(MOMENTUM_MONTHS, min_periods=MOMENTUM_MONTHS).sum()
    )
    out = pd.DataFrame({"ret_12_1": np.expm1(past)}, index=m.index)
    # Shares a year ago, put on today's basis by CRSP's split factors.
    ago = g["shrout_k"].shift(12)
    dist = data.table("crsp_distributions", ["disexdt", "disfacshr"])
    dist = dist[dist["disfacshr"].notna() & (dist["disfacshr"] > -1) & (dist["disfacshr"] != 0)]
    factor = asfiled.share_basis(dist)
    keys = m.index.to_frame(index=False)
    then = keys["eom"] - pd.DateOffset(months=12)
    adj = factor(keys["permno"], then, keys["eom"])
    out["chcsho_12m"] = m["shrout_k"].to_numpy() * adj / ago.to_numpy() - 1
    return out


# Each universe month: its gvkey, one PERMNO per gvkey (share classes).
def gvkeys(u: pd.DataFrame, log: dict) -> pd.DataFrame:
    lk = data.table("links", None)
    u = u.assign(gvkey=links.value_at(lk, "gvkey", u["permno"], u["eom"]).to_numpy())
    # A month with no gvkey stays in the universe, uncovered.
    log["universe_months_without_gvkey"] = int(u["gvkey"].isna().sum())
    none, u = u[u["gvkey"].isna()], u.dropna(subset=["gvkey"]).astype({"gvkey": str})
    # The panel's 2015 stock of each gvkey, the class it kept.
    p = data.table("panel", ["gvkey"], where={"eom": (PANEL_FROM, PANEL_FROM)})
    first = set(zip(p["gvkey"].astype(str), p["permno"]))
    # From 2015 the panel's class wins; before it, the larger cap alone.
    pick = [(g, s) in first for g, s in zip(u["gvkey"], u["permno"])]
    u["panel_pick"] = np.array(pick, dtype=bool) & (u["eom"] >= PANEL_FROM).to_numpy()
    u["prior_cap"] = u["prior_cap"].fillna(u["cap_musd"])
    u = u.sort_values(["panel_pick", "prior_cap"], ascending=False)
    shared = u.duplicated(["gvkey", "eom"], keep=False)
    log["share_class_months_dropped"] = int(u.duplicated(["gvkey", "eom"]).sum())
    log["gvkey_months_with_two_stocks"] = int(shared.sum())
    return pd.concat([u.drop_duplicates(["gvkey", "eom"]), none], ignore_index=True)


# The latest row public by each T, per gvkey, from a Compustat table.
def latest(table: pd.DataFrame, keys: pd.DataFrame, key="gvkey", date="datadate"):
    return rebuild.latest_public(table, keys, key, date)


# The eight accounting parts at each universe month, from Compustat.
def accounting_parts(u: pd.DataFrame) -> pd.DataFrame:
    a = data.table("compustat_annual", ANNUAL, purpose="twin").astype({"gvkey": str})
    a = a.join(compustat.year_ago(a, [*LAGGED, "first_close"]))
    a = a.rename(columns=lambda c: c.replace("_ago", "_lag"))
    # A year counts once its year-ago row is public too.
    a["first_close"] = a[["first_close", "first_close_lag"]].max(axis=1)
    cols = [*compustat.STOCKS, *compustat.FLOWS, *compustat.YEAR_TO_DATE, "fqtr", "results_at"]
    q = data.table("compustat_quarterly", cols, purpose="twin").astype({"gvkey": str})
    x = compustat.jkp_frame(q.sort_values(["gvkey", "datadate"]).reset_index(drop=True))
    keys = u[["gvkey", "T"]].reset_index(names="row")
    ann = latest(a, keys).reindex(u.index)
    qtr = latest(x, keys).reindex(u.index)
    # JKP's form: the latest quarter, the annual row only where missing.
    built = rebuild.jkp_parts(qtr, ann, qtr.rename(columns={"at": "atq"})[["niq", "atq"]])
    # niq_at: income at rdq + 1, once last quarter's 10-Q is out.
    released = clock.first_close(x["results_at"], data.calendar())
    when = pd.concat([pd.Series(released.to_numpy()), x["row_close_l1"]], axis=1).max(axis=1)
    results = latest(x.assign(first_close=when.to_numpy()), keys).reindex(u.index)
    niq_at = results["ib"].fillna(results["niq"]) / results["at_l1"]
    built["niq_at"] = niq_at.replace([np.inf, -np.inf], np.nan)
    built["annual_datadate"], built["quarter_datadate"] = ann["datadate"], qtr["datadate"]
    return built


# The twin's parts, SYY-10 and coverage at every universe month.
def build(log: dict) -> pd.DataFrame:
    m = crsp_months()
    market = market_parts(m)
    # The prior month end's CRSP cap, from every month, picks a share class.
    m["prior_cap"] = m.sort_values("eom").groupby("permno")["cap_musd"].shift(1)
    u = m[m["universe"] & m["eom"].between(*SPAN)].reset_index(drop=True)
    log["universe_months"] = len(u)
    u = gvkeys(u, log).reset_index(drop=True)
    u["T"] = data.eom_session(u["eom"]).to_numpy()
    keyed = u["gvkey"].notna()
    parts = accounting_parts(u[keyed]).reindex(u.index)
    keys = pd.MultiIndex.from_frame(u[["permno", "eom"]])
    for c in ("ret_12_1", "chcsho_12m"):
        parts[c] = market[c].reindex(keys).to_numpy()
    twin = pd.concat([u[["permno", "eom", "T", "gvkey", "cap_musd", "ret"]], parts], axis=1)
    twin["covered"] = twin["annual_datadate"].notna() | twin["quarter_datadate"].notna()
    return composite(twin)


# SYY-10 over the twin's universe each month, and the books' score.
def composite(twin: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, g in twin.groupby("eom"):
        combined = syy.combine(g.set_index("permno")[list(syy.PARTS)])
        g = g.assign(syy_raw=combined["raw"].to_numpy(), present=combined["present"].to_numpy())
        g = g.assign(syy=ranks.unit_rank(g["syy_raw"]).to_numpy())
        # Uncovered stocks hold a neutral 0: the twin's control.
        out.append(g.assign(syy_book=g["syy"].fillna(0.0)))
    return pd.concat(out, ignore_index=True)


# One month's rank correlation of two columns, over 30 stocks or none.
def spearman(g: pd.DataFrame) -> float:
    g = g.dropna()
    return g.iloc[:, 0].rank().corr(g.iloc[:, 1].rank()) if len(g) > 30 else np.nan


# The twin against the panel, per part, on 2015-2020 months.
def b17(twin: pd.DataFrame) -> dict:
    late = twin[twin["eom"] >= PANEL_FROM]
    p = data.table("panel", list(syy.PARTS), where={"eom": (PANEL_FROM, SPAN[1])})
    both = late.merge(p, on=["permno", "eom"], suffixes=("", "_panel"))
    out = {}
    for c in syy.PARTS:
        rho = both.groupby("eom")[[c, f"{c}_panel"]].apply(spearman)
        out[c] = {"mean_rho": round(float(rho.mean()), 4), "worst": round(float(rho.min()), 4),
                  "months": int(rho.notna().sum()), "passes": bool(rho.mean() >= BAR)}  # fmt: skip
    return out


# The PDF test on the twin, every universe month counted; 2000 warms up.
def survivorship(twin: pd.DataFrame) -> dict:
    dead = data.table("crsp_delistings", ["delistingdt"])
    gone = set(dead.loc[dead["delistingdt"] <= PANEL_FROM, "permno"])
    out = {}
    for start in ("2000-01-01", "2001-01-01"):
        early = twin[(twin["eom"] < PANEL_FROM) & (twin["eom"] >= start)]
        rows = early.assign(leaver=early["permno"].isin(gone), month=early["eom"].dt.to_period("M"))
        rows = rows.rename(columns={"ret": "MthRet"})
        # Covered as the gate rules say: the month carries the signal.
        signal = rows.assign(covered=rows["syy"].notna())
        last = signal[signal["leaver"]].sort_values("eom").drop_duplicates("permno", keep="last")
        out[f"from_{start[:4]}"] = {
            "any_compustat_row": agreement.early_gap(rows),
            "carries_the_signal": agreement.early_gap(signal),
            "leavers_final_month_with_signal": round(float(last["covered"].mean()), 4),
        }
    return out


# A part failing the match is missing before 2015; the composite redone.
def apply_b17(twin: pd.DataFrame, table: dict) -> pd.DataFrame:
    early = twin["eom"] < PANEL_FROM
    failed = [c for c, r in table.items() if not r["passes"]]
    twin.loc[early, failed] = np.nan
    return composite(twin)


# Builds the twin, its match table and its PDF test (robustness only).
def main() -> dict:
    log: dict = {}
    twin = build(log)
    table = b17(twin)
    twin = apply_b17(twin, table)
    early = twin[twin["eom"] < PANEL_FROM]
    log["early_months_with_syy"] = int(early["syy"].notna().sum())
    log["early_parts_kept"] = [c for c, r in table.items() if r["passes"]]
    test = survivorship(twin)
    log["coverage_control"] = "uncovered universe stocks at a neutral SYY-10 of 0 (syy_book)"
    report = {"build": log, "b17": table, "survivorship_2000_2014": test}
    OUT.mkdir(parents=True, exist_ok=True)
    twin.to_parquet(OUT / "twin.parquet", index=False)
    (OUT / "history.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# Builds the twin: uv run python -m fiam.vfinal.signals.history
if __name__ == "__main__":
    print(json.dumps(main(), default=str))
