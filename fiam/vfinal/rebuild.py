# The as-filed SYY rebuild and the Compustat gap.

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import compustat, data, links, universe

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "vfinal" / "rebuild"
# The rebuild's span and the gap's span.
REBUILD = (pd.Timestamp("2015-01-31"), pd.Timestamp("2020-12-31"))
GAP = (pd.Timestamp("2011-01-01"), pd.Timestamp("2020-12-31"))
# Each Compustat-style item and the XBRL tags that give it, first first.
TAGS = {
    "at": ["Assets"],
    "lt": ["Liabilities"],
    "lse": ["LiabilitiesAndStockholdersEquity"],
    "act": ["AssetsCurrent"],
    "lct": ["LiabilitiesCurrent"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "ib": ["IncomeLossFromContinuingOperations",
           "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"],
    "sale": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
             "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
             "RegulatedAndUnregulatedOperatingRevenue", "SalesRevenueServicesNet"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
             "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
             "CostOfServices"],
    "gp": ["GrossProfit"],
    "oancf": ["NetCashProvidedByUsedInOperatingActivities",
              "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "che": ["CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
    "dltt": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "dlc": ["DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtCurrent"],
    "debt_total": ["LongTermDebt"],
    "ceq": ["StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "mib": ["MinorityInterest"],
    "pstk": ["PreferredStockValue"],
    "ppegt": ["PropertyPlantAndEquipmentGross",
              "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization"],
    "invt": ["InventoryNet"],
    "sstk": ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity"],
    "prstkc": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    "pi": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "dp": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation"],
}  # fmt: skip
# Balance-sheet items are instants; the rest are flows over a period.
STOCKS = {
    "at",
    "lt",
    "lse",
    "act",
    "lct",
    "che",
    "dltt",
    "dlc",
    "ceq",
    "mib",
    "pstk",
    "ppegt",
    "invt",
}
# SEC's total long-term debt, current part included, is a stock too.
STOCKS |= {"debt_total"}
# Annual flows run 350-380 days, quarters 80-125, nine months 250-290.
YEAR, QUARTER, AGO, NINE = (350, 380), (80, 125), (350, 380), (250, 290)
# The SYY-10 accounting parts the rebuild covers (two are market data).
ACCOUNTING = ("o_score", "eqnetis_at", "oaccruals_at", "noa_at", "gp_at", "at_gr1", "niq_at",
              "ppeinv_gr1a")  # fmt: skip
# The agreement bar: monthly Spearman with the panel's own values.
BAR = 0.95
# June, September and December: the latest 10-Q or 10-K is in by then.
SETTLED = {6, 9, 12}
# Compustat and as-filed agree on an item within 1%.
GAP_TOLERANCE = 0.01


# The SEC dollar facts, earliest report per stock, item and period.
def facts() -> pd.DataFrame:
    tags = {t: item for item, ts in TAGS.items() for t in ts}
    order = {t: i for ts in TAGS.values() for i, t in enumerate(ts)}
    cols = ["tag", "start", "end", "val", "filed", "days"]
    f = data.table("sec_facts", cols, where={"unit": {"USD"}, "tag": set(tags)})
    f = f.assign(item=f["tag"].map(tags), order=f["tag"].map(order))
    # Across a stock's SEC ids, the earliest filing of each period wins.
    f = f.sort_values(["filed", "accn", "order"])
    return f.drop_duplicates(["permno", "item", "start", "end"])


# Each item's latest fiscal-year value public by T, and a year before.
def annual_at(f: pd.DataFrame, T) -> pd.DataFrame:
    seen = f[f["first_close"] <= T]
    flows = seen[~seen["item"].isin(STOCKS) & seen["days"].between(*YEAR)]
    # The fiscal year end: the latest annual flow period any item reports.
    ends = flows.groupby("permno")["end"].max().rename("fy_end")
    x = seen.merge(ends, on="permno")
    gap = (x["fy_end"] - x["end"]).dt.days
    annual_flow = ~x["item"].isin(STOCKS) & x["days"].between(*YEAR)
    stock = x["item"].isin(STOCKS) & x["start"].isna()
    now = x[(gap == 0) & (annual_flow | stock)]
    ago = x[gap.between(*AGO) & (annual_flow | stock)]
    wide = now.pivot_table(index="permno", columns="item", values="val", aggfunc="first")
    lag = ago.sort_values("end").pivot_table(
        index="permno", columns="item", values="val", aggfunc="last"
    )
    return wide.join(lag.add_suffix("_lag"), how="left").join(ends)


# The latest quarter's net income and assets public by T (niq_at).
def quarter_at(f: pd.DataFrame, T) -> pd.DataFrame:
    seen = f[f["first_close"] <= T]
    ni = seen[(seen["item"] == "ni") & seen["days"].between(*QUARTER)]
    ni = ni.sort_values("end").drop_duplicates("permno", keep="last")
    assets = seen[(seen["item"] == "at") & seen["start"].isna()][["permno", "end", "val"]]
    both = ni[["permno", "end", "val"]].merge(assets, on=["permno", "end"], suffixes=("", "_at"))
    return both.set_index("permno").rename(columns={"val": "niq", "val_at": "atq"})


# One item's column, all missing when no stock reported it.
def item(a: pd.DataFrame, c: str) -> pd.Series:
    return a[c] if c in a else pd.Series(np.nan, index=a.index)


# The eight accounting parts from one set of annual and quarterly items.
def parts(a: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    # An item as reported, missing where the filing gave none.
    def g(c):
        return item(a, c)

    # Optional items such as minority interest count as 0 when missing.
    def z(c):
        return item(a, c).fillna(0.0)

    at, lt = g("at"), g("lt").fillna(g("at") - g("ceq") - z("mib"))
    gp = g("gp").fillna(g("sale") - g("cogs"))
    out = pd.DataFrame(index=a.index)
    out["gp_at"] = gp / at
    out["at_gr1"] = at / g("at_lag") - 1
    # Income before extraordinary items where reported, as JKP use it.
    out["oaccruals_at"] = (g("ib").fillna(g("ni")) - g("oancf")) / at
    operating_assets = at - z("che")
    debt = total_debt(g("dltt"), g("dlc"), g("debt_total"))
    operating_liabilities = at - debt.fillna(0.0) - z("mib") - z("pstk") - g("ceq")
    out["noa_at"] = (operating_assets - operating_liabilities) / g("at_lag")
    out["ppeinv_gr1a"] = (g("ppegt") - g("ppegt_lag") + z("invt") - z("invt_lag")) / g("at_lag")
    issued = g("sstk").fillna(0.0) - g("prstkc").fillna(0.0)
    out["eqnetis_at"] = issued.where(g("sstk").notna() | g("prstkc").notna()) / at
    nix, lag = g("ni"), g("ni_lag")
    out["o_score"] = o_score(at, lt, debt, g("act"), g("lct"), nix, lag, g("pi"), g("dp"))
    # niq_at is a quarterly part in JKP; the annual form never gives it.
    out["niq_at"] = np.nan
    return out.replace([np.inf, -np.inf], np.nan)


# JKP's Ohlson O-score (char_macros.sas `ohlson_o`): debt over assets.
def o_score(at, lt, debt, ca, cl, nix, nix_lag, pi, dp) -> pd.Series:
    # JKP: missing where assets, current assets or liabilities are not > 0.
    at, ca, lt = at.where(at > 0), ca.where(ca > 0), lt.where(lt > 0)
    both_neg = ((nix < 0) & (nix_lag < 0)).astype(float).where(nix.notna() & nix_lag.notna())
    above = (lt > at).astype(float).where(lt.notna() & at.notna())
    change = (nix - nix_lag) / (nix.abs() + nix_lag.abs())
    return (
        -1.32 - 0.407 * np.log(at.where(at > 0)) + 6.03 * debt / at - 1.43 * (ca - cl) / at
        + 0.076 * cl / ca - 1.72 * above - 2.37 * nix / at - 1.83 * (pi + dp) / lt
        + 0.285 * both_neg - 0.52 * change
    )  # fmt: skip


# JKP's debt_x, sum(dltt, dlc), else SEC's total; missing if none is.
def total_debt(dltt: pd.Series, dlc: pd.Series, total=None) -> pd.Series:
    debt = dltt.fillna(0.0) + dlc.fillna(0.0).where(dltt.notna() | dlc.notna())
    return debt if total is None else debt.fillna(total)


# Monthly Spearman of each rebuilt part against the panel's own value.
def compare(start=REBUILD[0], end=REBUILD[1]) -> dict:
    f = facts()
    x = asfiled_frame(f)
    rows = []
    for eom in data.month_ends(start, end):
        T = data.eom_session([eom]).iloc[0]
        m = universe.members(eom)
        ids = set(m.loc[m["new_long"], "permno"])
        a = annual_at(f[f["permno"].isin(ids)], T)
        q = quarter_at(f[f["permno"].isin(ids)], T)
        keys = pd.DataFrame({"permno": sorted(ids), "T": T}).reset_index(names="row")
        lat = latest_public(x, keys, "permno", "end").set_index("permno")
        built = parts_public(lat, T).fillna(parts(a, q).drop(columns=["niq_at"]))
        panel = data.table("panel", list(ACCOUNTING), where={"eom": (eom, eom)})
        panel = panel.set_index("permno").reindex(sorted(ids))
        for c in ACCOUNTING:
            both = pd.concat([built[c], panel[c]], axis=1, keys=["built", "panel"]).dropna()
            rho = both["built"].rank().corr(both["panel"].rank()) if len(both) > 30 else np.nan
            rows.append({"eom": eom, "part": c, "rho": rho, "n": len(both), "universe": len(ids)})
    r = pd.DataFrame(rows)
    summary = r.groupby("part").agg(
        rho=("rho", "mean"), worst=("rho", "min"), n=("n", "mean"), universe=("universe", "mean")
    )
    summary["passes"] = summary["rho"] >= BAR
    # Settled months, every latest filing in: the values, not the timing.
    settled = r[r["eom"].dt.month.isin(SETTLED)].groupby("part")["rho"].mean().round(4)
    summary["settled_rho"] = settled
    return {"by_part": summary.round(4).to_dict(orient="index"), "bar": BAR,
            "settled_months": sorted(SETTLED)}  # fmt: skip


# Compustat's quarter against the as-filed first report, item by item.
def gap() -> dict:
    cols = ["datadate", "atq", "saleq", "niq", "epspxq"]
    q = data.table("compustat_quarterly", cols, purpose="gap")
    q = q[(q["datadate"] >= GAP[0]) & (q["datadate"] <= GAP[1])]
    lk = data.table("links", None)
    q = q.assign(permno=links.permno_at(lk, "gvkey", q["gvkey"], q["datadate"]).to_numpy())
    q = q.dropna(subset=["permno"]).astype({"permno": "int64"})
    f = facts()
    # EPS against the quarter's first report, the SUE table's own value.
    eps = data.table("sue", ["val", "basis"], purpose="gap")
    eps = eps[eps["basis"] == "quarter"][["permno", "end", "val"]]
    pairs = {"atq": ("at", None), "saleq": ("sale", QUARTER), "niq": ("ni", QUARTER)}
    out = {}
    for cs, (name, span) in pairs.items():
        af = f[f["item"] == name]
        af = af[af["start"].isna()] if span is None else af[af["days"].between(*span)]
        # Compustat holds dollars in millions; the SEC facts in dollars.
        af = af.assign(val=af["val"] / 1e6)
        out[cs] = share_off(q[["permno", "datadate", cs]], af[["permno", "end", "val"]], cs)
    out["epspxq"] = share_off(q[["permno", "datadate", "epspxq"]], eps, "epspxq")
    return out


# The share of matched quarters whose two values differ by over 1%.
def share_off(cs: pd.DataFrame, af: pd.DataFrame, col: str) -> dict:
    left = cs.dropna(subset=[col]).sort_values("datadate")
    right = af.dropna(subset=["val"]).sort_values("end")
    m = pd.merge_asof(left, right, left_on="datadate", right_on="end", by="permno",
                      direction="nearest", tolerance=pd.Timedelta(days=7))  # fmt: skip
    m = m.dropna(subset=["val"])
    scale = m["val"].abs().where(m["val"].abs() > 0, 1.0)
    off = (m[col] - m["val"]).abs() / scale > GAP_TOLERANCE
    by_year = off.groupby(m["datadate"].dt.year).mean().round(4)
    return {"matched": len(m), "share_off": round(float(off.mean()), 4),
            "by_year": {int(k): float(v) for k, v in by_year.items()}}  # fmt: skip


# The eight parts from the latest quarter and trailing-year flows (JKP).
def parts_quarterly(x: pd.DataFrame) -> pd.DataFrame:
    # An item as reported, missing where none is.
    def g(c):
        return item(x, c)

    # Optional items count as 0 when missing.
    def z(c):
        return item(x, c).fillna(0.0)

    at = g("at")
    out = pd.DataFrame(index=x.index)
    out["at_gr1"] = at / g("at_l4") - 1
    # JKP: quarterly income before extraordinary items over lagged assets.
    out["niq_at"] = item(x, "ib").fillna(g("niq")) / g("at_l1")
    debt = total_debt(g("dltt"), g("dlc"), g("debt_total"))
    operating = (at - z("che")) - (at - debt.fillna(0.0) - z("mib") - z("pstk") - g("ceq"))
    out["noa_at"] = operating / g("at_l4")
    out["gp_at"] = (g("sale_ttm") - g("cogs_ttm")) / at
    out["oaccruals_at"] = (g("ib_ttm") - g("oancf_ttm")) / at
    out["ppeinv_gr1a"] = (g("ppegt") - g("ppegt_l4") + z("invt") - z("invt_l4")) / g("at_l4")
    issued = item(x, "sstk_ttm").fillna(0.0) - item(x, "prstkc_ttm").fillna(0.0)
    out["eqnetis_at"] = issued / at
    out["o_score"] = o_score(at, g("lt"), debt, g("act"), g("lct"), g("ni_ttm"), g("ni_ttm_l4"),
                             g("pi_ttm"), g("dp_ttm"))  # fmt: skip
    return out.replace([np.inf, -np.inf], np.nan)


# Quarterly parts first; the annual form where no quarter gives one.
def jkp_parts(x: pd.DataFrame, a: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    return parts_quarterly(x).fillna(parts(a, q).drop(columns=["niq_at"]))


# Flows to a quarter: 3-month facts, else Q4 as annual less nine months.
def quarter_flows(f: pd.DataFrame, items: list[str]) -> pd.DataFrame:
    flows = f[f["item"].isin(items)]
    q = flows[flows["days"].between(*QUARTER)]
    year = flows[flows["days"].between(*YEAR)]
    nine = flows[flows["days"].between(*NINE)]
    both = year.merge(nine, on=["permno", "item", "start"], suffixes=("", "_nine"))
    both = both[(both["end"] - both["end_nine"]).dt.days.between(*QUARTER)]
    q4 = both.assign(val=both["val"] - both["val_nine"])
    q4["first_close"] = q4[["first_close", "first_close_nine"]].max(axis=1)
    cols = ["permno", "item", "end", "val", "first_close"]
    # The first public value of each quarter: a 3-month fact or the Q4 sum.
    out = pd.concat([q[cols], q4[cols]]).sort_values("first_close")
    return out.drop_duplicates(["permno", "item", "end"])


# Year-to-date cash flows to a trailing year: ytd + prior year - ago.
def trailing_year(f: pd.DataFrame, items: list[str]) -> pd.DataFrame:
    flows = f[f["item"].isin(items) & f["days"].between(QUARTER[0], YEAR[1])]
    year = flows[flows["days"].between(*YEAR)]
    ytd = flows[~flows["days"].between(*YEAR)].copy()
    ytd["prior_end"] = ytd["start"] - pd.Timedelta(days=1)
    prior = year.rename(columns={"end": "prior_end", "val": "prior", "first_close": "fc_prior"})
    got = pd.merge_asof(
        ytd.sort_values("prior_end"), prior[["permno", "item", "prior_end", "prior", "fc_prior"]]
        .sort_values("prior_end"), on="prior_end", by=["permno", "item"], direction="nearest",
        tolerance=pd.Timedelta(days=7),
    )  # fmt: skip
    got["ago_end"] = got["end"] - pd.Timedelta(days=365)
    ago = ytd.rename(columns={"end": "ago_end", "val": "ago", "days": "ago_days",
                              "first_close": "fc_ago"})  # fmt: skip
    got = pd.merge_asof(
        got.sort_values("ago_end"), ago[["permno", "item", "ago_end", "ago", "ago_days", "fc_ago"]]
        .sort_values("ago_end"), on="ago_end", by=["permno", "item"], direction="nearest",
        tolerance=pd.Timedelta(days=15),
    )  # fmt: skip
    same = (got["days"] - got["ago_days"]).abs() <= 10
    got["val"] = (got["val"] + got["prior"] - got["ago"]).where(same)
    # A trailing year is public once its three pieces are.
    got["first_close"] = got[["first_close", "fc_prior", "fc_ago"]].max(axis=1)
    cols = ["permno", "item", "end", "val", "first_close"]
    out = pd.concat([year[cols], got[cols]]).dropna(subset=["val"])
    return out.drop_duplicates(["permno", "item", "end"])


# The as-filed JKP frame: values, each item's clock, and lags of both.
def asfiled_frame(f: pd.DataFrame) -> pd.DataFrame:
    stocks = f[f["item"].isin(STOCKS) & f["start"].isna()][["permno", "item", "end", "val",
                                                              "first_close"]]  # fmt: skip
    q = quarter_flows(f, ["ni", "ib", "sale", "cogs", "pi", "dp"])
    t = trailing_year(f, ["oancf", "sstk", "prstkc"])
    long = pd.concat([stocks, q, t.assign(item=t["item"] + "_ttm")])
    keys = ["permno", "end"]
    wide = long.pivot_table(index=keys, columns="item", values="val", aggfunc="first")
    clocks = long.pivot_table(index=keys, columns="item", values="first_close", aggfunc="min")
    x = wide.join(clocks.add_prefix("c_")).reset_index().sort_values(keys).reset_index(drop=True)
    flows = ["ni", "ib", "sale", "cogs", "pi", "dp"]
    items = [*flows, "at", "ppegt", "invt", "lt", "lse", "ceq", "mib", "che", "dltt", "dlc"]
    items += ["debt_total", "pstk", "act", "lct", "oancf_ttm", "sstk_ttm", "prstkc_ttm"]
    for c in items:
        for col in (c, f"c_{c}"):
            if col not in x:
                x[col] = np.nan if col == c else pd.NaT
    lagged = [*flows, "at", "ppegt", "invt"]
    for k in (1, 2, 3, 4):
        cols = [*lagged, *(f"c_{c}" for c in lagged)]
        x = x.join(compustat.quarters_back(x, k, cols, "permno", "end"))
    # A trailing sum needs its four quarters, and is public with the last.
    for c in flows:
        x[f"{c}_ttm"] = x[c] + x[f"{c}_l1"] + x[f"{c}_l2"] + x[f"{c}_l3"]
        quarters = [x[f"c_{c}"], *(x[f"c_{c}_l{k}"] for k in (1, 2, 3))]
        x[f"c_{c}_ttm"] = pd.concat(quarters, axis=1).max(axis=1).where(x[f"{c}_ttm"].notna())
    x["niq"], x["c_niq"] = x["ni"], x["c_ni"]
    # Without its own tag, income before extraordinary items is net income.
    no_ib = x["ib_ttm"].isna()
    x["ib_ttm"] = x["ib_ttm"].fillna(x["ni_ttm"])
    x["c_ib_ttm"] = x["c_ib_ttm"].where(~no_ib, x["c_ni_ttm"])
    # Liabilities, if untagged, are liabilities and equity less equity.
    x["lt"] = x["lt"].fillna(x["lse"] - x["ceq"] - x["mib"].fillna(0.0))
    x = x.join(compustat.quarters_back(x, 4, ["ni_ttm", "c_ni_ttm"], "permno", "end"))
    # A quarter is chosen by its balance sheet's own filing.
    others = x[[c for c in x if c.startswith("c_") and "_l" not in c]].min(axis=1)
    return x.assign(first_close=x["c_at"].fillna(others))


# Each quarterly part's inputs: it counts only once all are public by T.
PART_INPUTS = {
    "at_gr1": ["at", "at_l4"],
    "niq_at": ["ib", "niq", "at_l1"],
    "noa_at": ["at", "che", "dltt", "dlc", "debt_total", "mib", "pstk", "ceq", "at_l4"],
    "gp_at": ["sale_ttm", "cogs_ttm", "at"],
    "oaccruals_at": ["ib_ttm", "oancf_ttm", "at"],
    "ppeinv_gr1a": ["ppegt", "ppegt_l4", "invt", "invt_l4", "at_l4"],
    "eqnetis_at": ["sstk_ttm", "prstkc_ttm", "at"],
    "o_score": ["at", "lt", "lse", "ceq", "mib", "dltt", "dlc", "debt_total", "act", "lct",
                "ni_ttm", "ni_ttm_l4", "pi_ttm", "dp_ttm"],
}  # fmt: skip


# Quarterly parts whose inputs are all public by T; the rest missing.
def parts_public(lat: pd.DataFrame, T) -> pd.DataFrame:
    out = parts_quarterly(lat)
    for part, inputs in PART_INPUTS.items():
        cols = [f"c_{c}" for c in inputs if f"c_{c}" in lat]
        latest = lat[cols].apply(pd.to_datetime).max(axis=1)
        out.loc[(latest > pd.Timestamp(T)).to_numpy(), part] = np.nan
    return out


# The latest row public by each T, per firm; never an older restatement.
def latest_public(table: pd.DataFrame, keys: pd.DataFrame, key="gvkey", date="datadate"):
    t = table.sort_values("first_close").copy()
    # Only rows that move a firm's latest period forward can be latest.
    newest = t.groupby(key)[date].cummax()
    t = t[t[date] >= newest].rename(columns={"first_close": "seen"})
    # One time unit on both sides, so the as-of join compares like.
    t["seen"] = pd.to_datetime(t["seen"]).astype("datetime64[ns]")
    left = keys.assign(T=pd.to_datetime(keys["T"]).astype("datetime64[ns]")).sort_values("T")
    t = t.dropna(subset=["seen"])
    got = pd.merge_asof(left, t, left_on="T", right_on="seen", by=key, direction="backward")
    return got.set_index("row")


# Writes the rebuild and the gap: uv run python -m fiam.vfinal.rebuild
def main() -> dict:
    report = {"syy_asfiled": compare(), "compustat_gap": gap()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rebuild.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# The command line entry: prints the report it wrote.
if __name__ == "__main__":
    print(json.dumps(main(), default=str))
