# SEC as-filed facts, first reports and the SUE labels.

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import data

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
# Basic EPS before discontinued items first (Livnat-Mendenhall 2006).
EPS_TAGS = (
    "IncomeLossFromContinuingOperationsPerBasicShare",
    "EarningsPerShareBasic",
    "EarningsPerShareBasicAndDiluted",
    "EarningsPerShareDiluted",
)
# The dollar tags the as-filed SYY rebuild and the Compustat gap read.
USD_TAGS = (
    "Assets", "Liabilities", "AssetsCurrent", "LiabilitiesCurrent", "NetIncomeLoss",
    "ProfitLoss", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet", "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
    "GrossProfit", "NetCashProvidedByUsedInOperatingActivities",
    "CashAndCashEquivalentsAtCarryingValue", "LongTermDebtNoncurrent", "LongTermDebtCurrent",
    "DebtCurrent", "ShortTermBorrowings", "StockholdersEquity", "MinorityInterest",
    "PreferredStockValue", "PropertyPlantAndEquipmentGross", "InventoryNet",
    "ProceedsFromIssuanceOfCommonStock", "PaymentsForRepurchaseOfCommonStock",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
    # The tags firms use instead of the above.
    "IncomeLossFromContinuingOperations",
    "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
    "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsCurrent", "CommercialPaper",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "LiabilitiesAndStockholdersEquity", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RegulatedAndUnregulatedOperatingRevenue",
    "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "CostOfServices",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization",
    "ProceedsFromIssuanceOrSaleOfEquity", "PaymentsForRepurchaseOfEquity", "Depreciation",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)  # fmt: skip
# A quarter is 80 to 125 days; a year 350 to 380; nine months 250-290.
QUARTER, YEAR, NINE = (80, 125), (350, 380), (250, 290)
# A comparative period ends 350 to 380 days before its own period.
COMPARATIVE = (350, 380)
# The SUE's scale: the latest 8 differences ending 60-760 days before.
PRIOR_SPAN, PRIOR_MAX, PRIOR_MIN = (60, 760), 8, 6
# A Compustat quarter matches an as-filed one within 7 days.
MATCH_DAYS = 7
# A SUE over 50 in size is flagged as a likely unit error, never edited.
EXTREME = 50.0


# The SEC ids the dated links give any PERMNO, as integers.
def linked_ciks(lk: pd.DataFrame) -> set[int]:
    ids = pd.to_numeric(lk.loc[lk["kind"] == "cik", "value"], errors="coerce")
    return set(ids.dropna().astype("int64"))


# Every wanted fact of the linked filers, as filed; frame, fy, fp never.
def extract(path: Path, ciks: set[int], log: dict) -> pd.DataFrame:
    want = {t: "USD/shares" for t in EPS_TAGS} | {t: "USD" for t in USD_TAGS}
    rows, files = [], 0
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("CIK") or int(name[3:13]) not in ciks:
                continue
            files += 1
            body = json.loads(zf.read(name))
            gaap = body.get("facts", {}).get("us-gaap", {})
            for tag, unit in want.items():
                for f in gaap.get(tag, {}).get("units", {}).get(unit, []):
                    rows.append(
                        (int(body["cik"]), tag, unit, f.get("start"), f.get("end"),
                         f.get("val"), f.get("accn"), f.get("form"), f.get("filed"))
                    )  # fmt: skip
    log["filers_read"] = files
    cols = ["cik", "tag", "unit", "start", "end", "val", "accn", "form", "filed"]
    return pd.DataFrame(rows, columns=cols)


# The cleaning rules: dated, one value per filing, first reports only.
def clean(f: pd.DataFrame, log: dict) -> pd.DataFrame:
    # A typed date outside 1990-2030 (a year "202") drops its fact, counted.
    wrong = pd.Series(False, index=f.index)
    for col in ("start", "end", "filed"):
        when = pd.to_datetime(f[col], format="%Y-%m-%d", errors="coerce")
        bad = (when.notna() & ~when.dt.year.between(1990, 2030)) | (f[col].notna() & when.isna())
        log[f"{col}_out_of_range"] = int(bad.sum())
        wrong |= bad
        f[col] = when.where(~bad).astype("datetime64[ns]")
    f["val"] = pd.to_numeric(f["val"], errors="coerce")
    bad = wrong | f["end"].isna() | f["filed"].isna() | f["accn"].isna() | f["val"].isna()
    log["facts_with_a_bad_date_or_missing_value_dropped"] = int(bad.sum())
    f = f[~bad]
    key = ["cik", "tag", "unit", "start", "end", "accn"]
    # A filing with two values for one tag and period gives none for it.
    two = f.groupby(key, dropna=False)["val"].transform("nunique") > 1
    log["facts_with_two_values_in_one_filing"] = int(two.sum())
    f = f[~two].drop_duplicates(key)
    early = f["filed"] < f["end"]
    log["facts_filed_before_their_period_ended"] = int(early.sum())
    f = f[~early]
    # Dollar facts keep each filer's first report; EPS keeps comparatives.
    usd = f["unit"] == "USD"
    first = f[usd].sort_values(["filed", "accn"]).drop_duplicates(key[:5])
    log["dollar_later_reports_dropped"] = int(usd.sum() - len(first))
    f = pd.concat([f[~usd], first], ignore_index=True)
    f["days"] = (f["end"] - f["start"]).dt.days
    return f


# Days long: is each fact a quarter, a year or a nine-month span?
def span(days: pd.Series, bounds: tuple) -> pd.Series:
    return days.between(*bounds)


# Per stock and period, the first filing to report any EPS tag for it.
def first_reports(eps: pd.DataFrame, bounds: tuple, forms: str | None = None) -> pd.DataFrame:
    f = eps[span(eps["days"], bounds)]
    if forms is not None:
        f = f[f["form"].fillna("").str.startswith(forms)]
    f = f.sort_values(["filed", "accn"]).drop_duplicates(["permno", "start", "end"])
    return f[["permno", "start", "end", "accn", "filed"]]


# Every tag's same-filing difference: its value less its comparative.
def tag_differences(eps: pd.DataFrame, firsts: pd.DataFrame, bounds: tuple) -> pd.DataFrame:
    facts = eps[span(eps["days"], bounds)][["permno", "accn", "tag", "start", "end", "val"]]
    cur = firsts.merge(facts, on=["permno", "accn", "start", "end"])
    ago = facts.rename(columns={"start": "start_ago", "end": "end_ago", "val": "val_ago"})
    both = cur.merge(ago, on=["permno", "accn", "tag"])
    gap = (both["end"] - both["end_ago"]).dt.days
    both = both[gap.between(*COMPARATIVE)].assign(off=(gap - 365).abs())
    # One comparative per tag: the one ending nearest a year before.
    both = both.sort_values("off").drop_duplicates(["permno", "accn", "start", "end", "tag"])
    both["diff"] = both["val"] - both["val_ago"]
    both["order"] = both["tag"].map({t: i for i, t in enumerate(EPS_TAGS)})
    return both.drop(columns=["off"])


# The first tag in EPS_TAGS order that has both values, per period.
def first_tag(diffs: pd.DataFrame) -> pd.DataFrame:
    out = diffs.sort_values("order").drop_duplicates(["permno", "start", "end"])
    return out[["permno", "accn", "start", "end", "filed", "tag", "val", "val_ago", "diff"]]


# Each stock-date's cumulative CRSP share factor, prod(1 + disfacshr).
def share_basis(dist: pd.DataFrame):
    d = dist.sort_values("disexdt")[["permno", "disexdt", "disfacshr"]].copy()
    d["cum"] = (1 + d["disfacshr"].astype(float)).groupby(d["permno"]).cumprod()
    d = d.rename(columns={"disexdt": "date"})[["permno", "date", "cum"]]
    d["date"] = d["date"].astype("datetime64[ns]")

    # Distributions ex on or before each date make up its basis.
    def at(permnos, dates) -> np.ndarray:
        left = pd.DataFrame({"permno": np.asarray(permnos, dtype="int64")})
        left["date"] = pd.to_datetime(np.asarray(dates)).astype("datetime64[ns]")
        left["order"] = np.arange(len(left))
        got = pd.merge_asof(left.sort_values("date"), d.sort_values("date"), on="date",
                            by="permno", direction="backward")  # fmt: skip
        return got.sort_values("order")["cum"].fillna(1.0).to_numpy()

    # A value filed at a, onto the basis of b: 1 / prod over (a, b].
    def factor(permnos, a, b) -> np.ndarray:
        return at(permnos, a) / at(permnos, b)

    return factor


# Fiscal Q4 by annual less nine months, both pairs on the 10-K's basis.
def q4_differences(eps: pd.DataFrame, factor, log: dict) -> pd.DataFrame:
    years = tag_differences(eps, first_reports(eps, YEAR, forms="10-K"), YEAR)
    nines = tag_differences(eps, first_reports(eps, NINE), NINE)
    nines = nines[["permno", "start", "end", "tag", "filed", "val", "val_ago", "diff"]]
    # The nine months start with the year and end about a quarter early.
    both = years.merge(nines, on=["permno", "start", "tag"], suffixes=("", "_nine"))
    both = both[(both["end"] - both["end_nine"]).dt.days.between(*QUARTER)]
    both = both[both["filed_nine"] <= both["filed"]]
    adj = factor(both["permno"], both["filed_nine"], both["filed"])
    # EPS_Q4 and its comparative: the year less nine months, one basis.
    both = both.assign(
        diff=both["diff"] - both["diff_nine"] * adj,
        val=both["val"] - both["val_nine"] * adj,
        val_ago=both["val_ago"] - both["val_ago_nine"] * adj,
    )
    both = both.assign(start=both["end_nine"] + pd.Timedelta(days=1))
    out = first_tag(both).assign(basis="annual_less_nine")
    log["q4_from_annual_less_nine_months"] = len(out)
    return out


# Q4's subtraction against its 3-month fact where both exist (reported).
def q4_error(diffs: pd.DataFrame, q4: pd.DataFrame) -> dict:
    both = diffs.merge(q4, on=["permno", "end"], suffixes=("", "_sub"))
    err = (both["diff"] - both["diff_sub"]).abs()
    return {
        "q4_error_pairs": len(both),
        "q4_error_within_0_01": round(float((err <= 0.01).mean()), 4),
        "q4_error_within_0_05": round(float((err <= 0.05).mean()), 4),
        "q4_error_p99": round(float(err.quantile(0.99)), 4),
    }


# The SUE scale per row: sd of the latest 8 prior differences (>= 6).
def scales(d: pd.DataFrame, factor) -> pd.DataFrame:
    rows = []
    for permno, g in d.groupby("permno", sort=False):
        ends = g["end"].to_numpy(dtype="datetime64[D]")
        filed = g["filed"].to_numpy(dtype="datetime64[D]")
        for i, idx in enumerate(g.index):
            gap = (ends[i] - ends[:i]).astype(int)
            # Prior quarters filed no later than this one: never a later file.
            ok = (gap >= PRIOR_SPAN[0]) & (gap <= PRIOR_SPAN[1]) & (filed[:i] <= filed[i])
            pick = np.flatnonzero(ok)[-PRIOR_MAX:]
            for j in g.index[pick]:
                rows.append((idx, j, permno))
    pairs = pd.DataFrame(rows, columns=["row", "prior", "permno"])
    pairs["diff"] = d.loc[pairs["prior"], "diff"].to_numpy()
    # Each prior difference onto the share basis of this quarter's filing.
    adj = factor(pairs["permno"], d.loc[pairs["prior"], "filed"], d.loc[pairs["row"], "filed"])
    pairs["diff"] *= adj
    stats = pairs.groupby("row")["diff"].agg(["count", "std"])
    out = d.join(stats.rename(columns={"count": "n_prior", "std": "scale"}))
    out["n_prior"] = out["n_prior"].fillna(0).astype(int)
    out.loc[out["n_prior"] < PRIOR_MIN, "scale"] = np.nan
    return out


# The as-filed SUE of every stock-quarter public by the seal.
def sue(log: dict) -> pd.DataFrame:
    cols = ["cik", "tag", "unit", "start", "end", "val", "accn", "form", "filed", "days"]
    f = data.table("sec_facts", cols, where={"unit": {"USD/shares"}})
    eps = f[f["tag"].isin(EPS_TAGS)].copy()
    dist = data.table("crsp_distributions", ["disexdt", "disfacshr"])
    keep = dist["disfacshr"].notna() & (dist["disfacshr"] > -1) & (dist["disfacshr"] != 0)
    factor = share_basis(dist[keep])
    firsts = first_reports(eps, QUARTER)
    diffs = first_tag(tag_differences(eps, firsts, QUARTER)).assign(basis="quarter")
    log["quarters_first_reported"] = len(firsts)
    log["quarters_with_same_filing_comparative"] = len(diffs)
    # A fiscal Q4's 3-month fact counts only from that year's own 10-K.
    tenk = first_reports(eps, YEAR, forms="10-K").sort_values(["filed", "accn"])
    tenk = tenk.drop_duplicates(["permno", "end"]).set_index(["permno", "end"])["accn"]
    own = tenk.reindex(pd.MultiIndex.from_frame(diffs[["permno", "end"]])).to_numpy()
    late = pd.notna(own) & (diffs["accn"].to_numpy() != own)
    log["q4_3month_facts_not_from_their_10k_dropped"] = int(late.sum())
    diffs = diffs[~late]
    q4 = q4_differences(eps, factor, log)
    log |= q4_error(diffs, q4)
    # Q4 by subtraction only where no 3-month fact gives that quarter.
    known = set(zip(diffs["permno"], diffs["end"]))
    q4 = q4[[k not in known for k in zip(q4["permno"], q4["end"])]]
    d = pd.concat([diffs, q4], ignore_index=True).sort_values(["permno", "end", "filed"])
    d = d.drop_duplicates(["permno", "end"]).reset_index(drop=True)
    log["q4_filled_by_subtraction"] = int((d["basis"] == "annual_less_nine").sum())
    d = scales(d, factor)
    d["sue"] = d["diff"] / d["scale"].where(d["scale"] > 0)
    # Bad EPS units give huge values: flagged, never edited.
    d["extreme"] = d["sue"].abs() > EXTREME
    log["sue_values"] = int(d["sue"].notna().sum())
    log["sue_extreme_flagged"] = int(d["extreme"].sum())
    years = d.loc[d["sue"].isna(), "end"].dt.year.value_counts().sort_index()
    log["sue_missing_by_period_year"] = {int(k): int(v) for k, v in years.items()}
    return d


# Each quarter's announcement: Compustat's rdq within 7 days, or filed.
def announce(d: pd.DataFrame, log: dict) -> pd.DataFrame:
    from fiam.vfinal import links

    lk = data.table("links", None)
    d = d.assign(gvkey=links.value_at(lk, "gvkey", d["permno"], d["end"]).to_numpy())
    q = data.table("compustat_quarterly", ["rdq"], purpose="announce").dropna(subset=["rdq"])
    q = q[["gvkey", "datadate", "rdq"]].astype({"gvkey": str}).sort_values("datadate")
    left = d.dropna(subset=["gvkey"]).astype({"gvkey": str}).reset_index()
    got = pd.merge_asof(
        left.sort_values("end")[["index", "gvkey", "end"]],
        q,
        left_on="end",
        right_on="datadate",
        by="gvkey",
        direction="nearest",
        tolerance=pd.Timedelta(days=MATCH_DAYS),
    )
    d["rdq"] = got.set_index("index")["rdq"].reindex(d.index)
    d["announced"] = d["rdq"].fillna(d["filed"])
    d["announced_by"] = np.where(d["rdq"].notna(), "rdq", "filed")
    log["announced_by"] = d["announced_by"].value_counts().to_dict()
    return d
