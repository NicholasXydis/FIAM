# Shared seal window, ticker links and SEC quarterly sales, alt tools.

import numpy as np
import pandas as pd

from fiam.vfinal import sources

# The last day a sealed run may read.
CUTOFF = pd.Timestamp("2020-12-31")
# The one line a run past the cutoff prints while the seal holds.
WAITS = "Waits for the unseal, a run past 2020-12-31 is refused while the data stay sealed"
# The credit Carbon Arc's terms ask for.
CREDIT = "Based in part on Carbon Arc data"
# A quarter is 80 to 125 days, a year 350 to 380, nine months 250-290.
QUARTER, YEAR, NINE = (80, 125), (350, 380), (250, 290)
# Net sales tags first, then total revenue, as a retailer files them.
SALES_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
# Total revenue first, the headline figure a company reports.
REVENUE_TAGS = ("Revenues",) + tuple(t for t in SALES_TAGS if t != "Revenues")


# The run's last day: the cutoff, or later only once unsealed.
def run_end(end=None, opened: bool | None = None) -> pd.Timestamp | None:
    opened = sources.unsealed() if opened is None else opened
    last = CUTOFF if end is None else pd.Timestamp(end)
    # Past the cutoff while sealed, the run is refused with one line.
    if last > CUTOFF and not opened:
        print(WAITS)
        return None
    return last


# Rows dated on or before the end, and how many later rows were dropped.
def drop_after(frame: pd.DataFrame, end: pd.Timestamp, col: str = "date") -> tuple:
    keep = pd.to_datetime(frame[col]) <= end
    return frame[keep].reset_index(drop=True), int((~keep).sum())


# Fiscal year and quarter of each date, the year ending in last_month.
def fiscal_quarter(dates, last_month: int) -> pd.DataFrame:
    d = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    offset = (d.dt.month - last_month - 1) % 12
    year = d.dt.year + (d.dt.month > last_month).astype(int)
    return pd.DataFrame({"fiscal_year": year.astype(int), "quarter": (offset // 3 + 1).astype(int)})


# Growth on the same fiscal quarter a year before, NaN without one.
def yoy(frame: pd.DataFrame, value: str) -> pd.Series:
    known = frame.set_index(["fiscal_year", "quarter"])[value]
    known = known[~known.index.duplicated()]
    keys = pd.MultiIndex.from_arrays([frame["fiscal_year"] - 1, frame["quarter"]])
    before = known.reindex(keys).to_numpy(dtype=float)
    now = frame[value].to_numpy(dtype=float)
    # A missing or zero base gives NaN, never a warning or infinity.
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(before > 0, now / before - 1, np.nan)
    return pd.Series(out, index=frame.index)


# A share as a rounded float, or None when there is nothing to share.
def share(part, whole) -> float | None:
    return round(float(part) / float(whole), 4) if whole else None


# Pearson correlation and count over pairs present in both, or None.
def correlation(x, y, least: int = 3) -> dict:
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = ~np.isnan(a) & ~np.isnan(b)
    n = int(ok.sum())
    # Under three pairs a correlation says nothing, so none is given.
    if n < least or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return {"r": None, "n": n}
    return {"r": round(float(np.corrcoef(a[ok], b[ok])[0, 1]), 4), "n": n}


# Tickers to PERMNO on each date through the sealed dated links.
def permnos(tickers, dates) -> pd.Series:
    from fiam.vfinal import data, links

    return links.permno_by_symbol(data.table("links", None), tickers, dates)


# Positive quarter facts; Q4 is the year less nine months if not filed.
def quarter_facts(facts: pd.DataFrame, tags=SALES_TAGS, first_only: bool = True) -> pd.DataFrame:
    f = facts[facts["tag"].isin(tags)].copy()
    f["start"], f["end"] = pd.to_datetime(f["start"]), pd.to_datetime(f["end"])
    f["days"] = (f["end"] - f["start"]).dt.days
    keep = ["permno", "tag", "start", "end", "val", "filed"]
    direct = f[f["days"].between(*QUARTER)][keep].assign(basis="quarter")
    years = f[f["days"].between(*YEAR)][keep]
    nines = f[f["days"].between(*NINE)][keep]
    both = years.merge(nines, on=["permno", "tag", "start"], suffixes=("", "_nine"))
    q4 = pd.DataFrame(
        {
            "permno": both["permno"],
            "tag": both["tag"],
            "start": both["end_nine"] + pd.Timedelta(days=1),
            "end": both["end"],
            "val": both["val"] - both["val_nine"],
            "filed": both[["filed", "filed_nine"]].max(axis=1),
            "basis": "year_less_nine",
        }
    )
    # The subtraction fills only quarters with no filed three-month fact.
    have = set(zip(direct["permno"], direct["tag"], direct["end"]))
    q4 = q4[[k not in have for k in zip(q4["permno"], q4["tag"], q4["end"])]]
    out = pd.concat([direct, q4], ignore_index=True)
    out = out[out["val"] > 0]
    # Earliest filing first, a filed figure before a derived one, then tag.
    out["rank"] = out["tag"].map({t: i for i, t in enumerate(tags)})
    out["derived"] = (out["basis"] != "quarter").astype(int)
    out = out.sort_values(["permno", "end", "filed", "derived", "rank"])
    out = out.drop_duplicates(["permno", "tag", "end"])
    # One figure per quarter, the first in that order.
    if first_only:
        out = out.drop_duplicates(["permno", "end"])
    return out.drop(columns=["rank", "derived"]).reset_index(drop=True)


# Quarterly sales as filed for these stocks, on the sealed reader.
def sec_quarters(stocks, tags=SALES_TAGS, first_only: bool = True) -> pd.DataFrame:
    from fiam.vfinal import data

    cols = ["cik", "tag", "unit", "start", "end", "val", "accn", "form", "filed"]
    where = {"permno": {int(p) for p in stocks}, "unit": {"USD"}, "tag": set(tags)}
    facts = data.table("sec_facts", cols, where=where)
    return quarter_facts(facts, tags, first_only)
