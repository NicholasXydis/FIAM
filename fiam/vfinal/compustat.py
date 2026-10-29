# Cleaned Compustat for the twin and the as-filed gap.

import pandas as pd

from fiam.vfinal import clock

# The allow-list: keys, dates and the twin and gap items (no ajexq).
KEYS_Q = ["gvkey", "datadate", "fyr", "fyearq", "fqtr", "datacqtr", "datafqtr", "curcdq"]
DATES_Q = ["rdq", "fdateq"]
ITEMS_Q = [
    "atq", "ltq", "actq", "lctq", "niq", "ibq", "saleq", "cogsq", "cheq", "dlttq",
    "dlcq", "ceqq", "pstkq", "mibq", "ppegtq", "invtq", "oancfy", "sstky", "prstkcy", "piq",
    "dpq", "cshoq", "epspxq", "epspiq",
]  # fmt: skip
KEYS_A = ["gvkey", "datadate", "fyr", "fyear", "curcd"]
ITEMS_A = [
    "at", "lt", "act", "lct", "ni", "ib", "sale", "cogs", "gp", "che", "dltt", "dlc",
    "ceq", "pstk", "mib", "ppegt", "invt", "oancf", "sstk", "prstkc", "pi", "dp", "csho", "epspx",
]  # fmt: skip
# A quarter's EPS, sales and income are public the day after rdq.
RESULTS_Q = {"epspxq", "epspiq", "saleq", "niq", "ibq"}
# Without a report date, a quarter waits four months after its end.
NO_RDQ_WAIT = pd.DateOffset(months=4)
# A year-ago quarter ends 350 to 380 days before, by datadate alone.
YEAR_AGO = (350, 380)


# The quarterly extract on the allow-list with both clocks.
def quarterly(path, log: dict) -> pd.DataFrame:
    q = pd.read_parquet(path, columns=KEYS_Q + DATES_Q + ITEMS_Q)
    # The extract keeps the fiscal labels as text; they are numbers.
    for col in ("fyr", "fyearq", "fqtr"):
        q[col] = pd.to_numeric(q[col], errors="coerce")
    for col in ("datadate", *DATES_Q):
        q[col] = pd.to_datetime(q[col], errors="coerce").astype("datetime64[ns]")
    # A report date before the period ended is missing.
    early = q["rdq"] < q["datadate"]
    log["rdq_before_datadate_set_missing"] = int(early.sum())
    q.loc[early, "rdq"] = pd.NaT
    q = two_calendars(q, log)
    results = clock.end_of_day(q["rdq"] + pd.Timedelta(days=1))
    filed = clock.end_of_day(q["fdateq"])
    # No report date: 4 months on, or its 10-Q's day if later (never early).
    waited = clock.end_of_day(q["datadate"] + NO_RDQ_WAIT)
    log["without_rdq_waiting_for_a_later_filing"] = int((q["rdq"].isna() & (filed > waited)).sum())
    waited = filed.where(filed > waited, waited)
    # Other items: the later of the results and the filing, else 4 months.
    items = filed.where(q["fdateq"].notna(), waited)
    items = items.where(items > results, results).where(q["rdq"].notna(), waited)
    q["results_at"] = results.where(q["rdq"].notna(), waited).dt.tz_convert("UTC").to_numpy()
    q["items_at"] = items.dt.tz_convert("UTC").to_numpy()
    log["rows"], log["without_rdq"] = len(q), int(q["rdq"].isna().sum())
    return q


# Two fiscal calendars on one datadate: the first rdq, else datacqtr.
def two_calendars(q: pd.DataFrame, log: dict) -> pd.DataFrame:
    pair = q.duplicated(["gvkey", "datadate"], keep=False)
    log["two_calendar_pairs"] = int(pair.sum() // 2)
    rest, pairs = q[~pair], q[pair].copy()
    rdq = pairs.groupby(["gvkey", "datadate"])["rdq"]
    differ = (rdq.transform("nunique") == 2) & (rdq.transform("count") == 2)
    by_rdq = pairs[differ].sort_values("rdq").drop_duplicates(["gvkey", "datadate"])
    tied = pairs[~differ]
    by_cal = tied[tied["datacqtr"].notna()].drop_duplicates(["gvkey", "datadate"])
    log["pairs_kept_by_earlier_rdq"] = len(by_rdq)
    log["pairs_kept_by_datacqtr"] = len(by_cal)
    log["pairs_left_unresolved"] = int(
        pairs[["gvkey", "datadate"]].drop_duplicates().shape[0] - len(by_rdq) - len(by_cal)
    )
    return pd.concat([rest, by_rdq, by_cal], ignore_index=True)


# The annual extract on the allow-list, on its fiscal Q4's clock.
def annual(path, q: pd.DataFrame, log: dict) -> pd.DataFrame:
    a = pd.read_parquet(path, columns=KEYS_A + ITEMS_A)
    a["fyr"], a["fyear"] = pd.to_numeric(a["fyr"]), pd.to_numeric(a["fyear"])
    a["datadate"] = pd.to_datetime(a["datadate"]).astype("datetime64[ns]")
    q4 = q[q["fqtr"] == 4][["gvkey", "datadate", "items_at"]].drop_duplicates(["gvkey", "datadate"])
    a = a.merge(q4, on=["gvkey", "datadate"], how="left")
    waited = clock.end_of_day(a["datadate"] + NO_RDQ_WAIT).dt.tz_convert("UTC")
    log["annual_rows_on_q4_clock"] = int(a["items_at"].notna().sum())
    a["items_at"] = pd.to_datetime(a["items_at"], utc=True).fillna(waited)
    log["rows"] = len(a)
    return a


# Each row's year-ago row of the same gvkey, by datadate 350-380 days.
def year_ago(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    left = frame[["gvkey", "datadate"]].reset_index()
    left["target"] = left["datadate"] - pd.Timedelta(days=365)
    right = frame[["gvkey", "datadate", *cols]].rename(columns={"datadate": "ago"})
    # The nearest prior row to a year back, kept only inside 350-380 days.
    both = pd.merge_asof(
        left.sort_values("target"),
        right.sort_values("ago"),
        left_on="target",
        right_on="ago",
        by="gvkey",
        direction="nearest",
        tolerance=pd.Timedelta(days=15),
    )
    gap = (both["datadate"] - both["ago"]).dt.days
    both = both[gap.between(*YEAR_AGO)].set_index("index")
    return both[cols].reindex(frame.index).add_suffix("_ago")


# Quarter lags by datadate: k quarters back is 91k days, within 20.
QUARTER_DAYS, LAG_TOLERANCE = 91, 20
# Quarterly names to the parts' names: balance sheet, flows, to date.
STOCKS = {"atq": "at", "ltq": "lt", "actq": "act", "lctq": "lct", "cheq": "che", "dlttq": "dltt",
          "dlcq": "dlc", "ceqq": "ceq", "mibq": "mib", "pstkq": "pstk", "ppegtq": "ppegt",
          "invtq": "invt"}  # fmt: skip
FLOWS = {"niq": "ni", "ibq": "ib", "saleq": "sale", "cogsq": "cogs", "piq": "pi", "dpq": "dp"}
YEAR_TO_DATE = {"oancfy": "oancf", "sstky": "sstk", "prstkcy": "prstkc"}


# Each row's values k quarters before, of the same gvkey, by datadate.
def quarters_back(q: pd.DataFrame, k: int, cols: list[str], key="gvkey", date="datadate"):
    left = q[[key, date]].reset_index()
    left["target"] = left[date] - pd.Timedelta(days=QUARTER_DAYS * k)
    right = q[[key, date, *cols]].rename(columns={date: "then"})
    got = pd.merge_asof(
        left.sort_values("target"),
        right.sort_values("then"),
        left_on="target",
        right_on="then",
        by=key,
        direction="nearest",
        tolerance=pd.Timedelta(days=LAG_TOLERANCE),
    )
    return got.set_index("index")[cols].reindex(q.index).add_suffix(f"_l{k}")


# The JKP frame: latest balance sheet, trailing-year flows and lags.
def jkp_frame(q: pd.DataFrame) -> pd.DataFrame:
    x = q.rename(columns={**STOCKS, **FLOWS, **YEAR_TO_DATE}).copy()
    x["niq"] = q["niq"].to_numpy()
    x["row_close"] = pd.to_datetime(x["first_close"])
    flows, ytd = list(FLOWS.values()), list(YEAR_TO_DATE.values())
    for k in (1, 2, 3, 4):
        cols = [*flows, *ytd, "fqtr", "at", "ppegt", "invt", "row_close"]
        x = x.join(quarters_back(x, k, cols))
    # Four quarters summed, every one of them present.
    for f in flows:
        x[f"{f}_ttm"] = x[f] + x[f"{f}_l1"] + x[f"{f}_l2"] + x[f"{f}_l3"]
    # Year to date to a trailing year: Q4 is the year; else add last Q4.
    q4 = [x[f"fqtr_l{k}"] == 4 for k in (1, 2, 3)]
    one_q4 = sum(m.astype(int) for m in q4) == 1
    for y in ytd:
        last = sum(x[f"{y}_l{k}"].where(m, 0.0) for k, m in zip((1, 2, 3), q4))
        rolled = (x[y] + last - x[f"{y}_l4"]).where(one_q4)
        x[f"{y}_ttm"] = x[y].where(x["fqtr"] == 4, rolled)
    return strict_clock(x)


# A row counts once it and every prior quarter it uses are public.
def strict_clock(x: pd.DataFrame, key="gvkey", date="datadate") -> pd.DataFrame:
    # A missing prior quarter adds no data, so it sets no clock either.
    lags = [x["row_close"], *(x[f"row_close_l{k}"] for k in (1, 2, 3, 4))]
    x["inputs_close"] = pd.concat(lags, axis=1).max(axis=1)
    x = x.join(quarters_back(x, 4, ["ni_ttm", "inputs_close"], key, date))
    # ni_ttm a year back brings its own quarters' clocks in.
    both = pd.concat([x["inputs_close"], x["inputs_close_l4"]], axis=1).max(axis=1)
    return x.assign(first_close=both.where(x["inputs_close"].notna()))
