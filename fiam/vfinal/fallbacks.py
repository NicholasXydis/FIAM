# The 2026 fallbacks' checks: FINRA short interest and volume.

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import links as link_table

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CLEAN = DATA / "v4" / "clean"
# The bars set before these checks ran.
FLOOR_MUSD = 600
SPIKE, WINDOW, MIN_DAYS = 5.0, 126, 63
PRECISION, RECALL, COVERAGE = 0.8, 0.8, 0.95
TOLERANCE, MIN_SHARES = 0.01, 100
TEST = ("2015-01-01", "2020-12-31")
AGREE = ("2021-06-01", "2025-12-31")


# Each FINRA symbol and date to PERMNO, as the registry maps them.
def map_symbols(lk: pd.DataFrame, symbols, dates) -> pd.Series:
    return link_table.permno_by_symbol(lk, symbols, dates)


# One WRDS short interest extract on PERMNO by its dated gvkey and iid.
def wrds_series(name: str, lk: pd.DataFrame) -> pd.DataFrame:
    cols = ["gvkey", "iid", "datadate", "shortint"]
    w = pd.read_parquet(DATA / "v4" / "extracts" / f"{name}.parquet", columns=cols)
    w = w.dropna(subset=["gvkey"]).rename(columns={"datadate": "settlement"})
    w["settlement"] = pd.to_datetime(w["settlement"])
    w = w[w["settlement"].between(*AGREE)]
    ids = w["gvkey"].astype(str) + ":" + w["iid"].astype(str)
    w["permno"] = link_table.permno_at(lk, "gvkey_iid", ids, w["settlement"]).to_numpy()
    return w.dropna(subset=["permno"]).astype({"permno": "int64"})


# Universe names on each date: panel me at least $600m at the last eom.
def universe(dates) -> pd.DataFrame:
    p = pd.read_parquet(CLEAN / "panel.parquet", columns=["permno", "eom", "me"])
    p = p[p["me"] >= FLOOR_MUSD][["permno", "eom"]].sort_values("eom")
    days = pd.DataFrame({"date": pd.to_datetime(pd.Series(dates).unique())}).sort_values("date")
    eoms = pd.Series(p["eom"].unique()).sort_values()
    days["eom"] = eoms.searchsorted(days["date"], side="left") - 1
    days = days[days["eom"] >= 0]
    days["eom"] = eoms.to_numpy()[days["eom"]]
    return days.merge(p, on="eom")[["date", "permno"]]


# FINRA short interest: coverage from 2021-06 and both WRDS agreements.
def short_interest(lk: pd.DataFrame) -> dict:
    si = pd.read_parquet(DATA / "finra" / "short_interest.parquet")
    si["permno"] = map_symbols(lk, si["symbol"], si["settlement"]).to_numpy()
    report = {"rows": len(si), "mapped_share": round(float(si["permno"].notna().mean()), 4)}
    mapped = si.dropna(subset=["permno"]).astype({"permno": "int64"})
    names = universe(mapped["settlement"]).rename(columns={"date": "settlement"})
    # Coverage of the rows the backtest reads, the clean table (H1).
    clean = pd.read_parquet(CLEAN / "short_interest.parquet", columns=["permno", "settlement"])
    held = clean[clean["settlement"] >= AGREE[0]].drop_duplicates()
    seen = names.merge(held, how="left", indicator=True)
    by_day = (seen["_merge"] == "both").groupby(seen["settlement"]).mean()
    late = by_day[by_day.index >= "2026-01-01"]
    report["coverage_2026"] = {str(d.date()): round(float(v), 4) for d, v in late.items()}
    report["coverage_2026_pass"] = bool(len(late)) and bool((late >= COVERAGE).all())
    report["coverage_min_from_2021_06"] = round(float(by_day.min()), 4)
    report["coverage_dates_from_2021_06"] = len(by_day)
    report["coverage_pass_from_2021_06"] = bool((by_day >= COVERAGE).all())
    # Agreement counts with each WRDS file on the overlap.
    for name in ("short_interest_legacy", "short_interest"):
        both = mapped.merge(wrds_series(name, lk), on=["permno", "settlement"])
        gap = (both["short"] - both["shortint"]).abs()
        agree = gap <= np.maximum(TOLERANCE * both["shortint"].abs(), MIN_SHARES)
        share = round(float(agree.mean()), 4) if len(both) else None
        report[f"agreement_{name}"] = {"pairs": len(both), "share": share}
    return report


# A split-safe spike flag: volume over 5 times its past 126-day mean.
def flags(frame: pd.DataFrame, volume: str, splits: pd.DataFrame | None = None) -> pd.Series:
    f = frame.sort_values(["permno", "date"]).copy()
    f["segment"] = 0
    if splits is not None and not splits.empty:
        marks = splits.assign(mark=1).drop_duplicates(["permno", "date"])
        f = f.merge(marks[["permno", "date", "mark"]], on=["permno", "date"], how="left")
        f["segment"] = f["mark"].fillna(0).groupby(f["permno"]).cumsum()
    past = f.groupby(["permno", "segment"])[volume].transform(
        lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_DAYS).mean()
    )
    out = pd.Series(np.where(past.notna(), f[volume] > SPIKE * past, np.nan), index=f.index)
    return pd.DataFrame({"permno": f["permno"], "date": f["date"], "flag": out})


# CRSP splits with a share factor, as dates that reset FINRA's window.
def crsp_splits() -> pd.DataFrame:
    d = pd.read_parquet(
        CLEAN / "crsp_distributions.parquet", columns=["permno", "disexdt", "disfacshr"]
    )
    d = d[pd.to_numeric(d["disfacshr"], errors="coerce") > 0]
    return d.rename(columns={"disexdt": "date"})[["permno", "date"]]


# FINRA volume against CRSP's on 2015-2020 universe stock-days.
def volume(lk: pd.DataFrame) -> dict:
    v = pd.read_parquet(DATA / "finra" / "volume.parquet")
    v["permno"] = map_symbols(lk, v["symbol"], v["date"]).to_numpy()
    v = v.dropna(subset=["permno"]).astype({"permno": "int64"})
    v = v.groupby(["permno", "date"], as_index=False)["total_volume"].sum()
    test = v[(v["date"] >= TEST[0]) & (v["date"] <= TEST[1])]
    cols = ["permno", "date", "prc", "vol"]
    crsp = pd.read_parquet(
        CLEAN / "crsp_daily",
        columns=cols,
        filters=[("date", ">=", pd.Timestamp(TEST[0])), ("date", "<=", pd.Timestamp(TEST[1]))],
    )
    crsp["dollar"] = crsp["prc"].abs() * crsp["vol"]
    names = universe(crsp["date"])
    ours = flags(crsp, "dollar").merge(names, on=["permno", "date"])
    theirs = flags(test, "total_volume", crsp_splits())
    both = ours.merge(theirs, on=["permno", "date"], suffixes=("_crsp", "_finra")).dropna()
    hit = (both["flag_crsp"] == 1) & (both["flag_finra"] == 1)
    precision = hit.sum() / max(1, (both["flag_finra"] == 1).sum())
    recall = hit.sum() / max(1, (both["flag_crsp"] == 1).sum())
    late = v[v["date"] >= "2026-01-01"]
    names_26 = universe(late["date"])
    seen = names_26.merge(late[["permno", "date"]], how="left", indicator=True)
    by_day = (seen["_merge"] == "both").groupby(seen["date"]).mean()
    report = {
        "test_stock_days": len(both),
        "crsp_flags": int((both["flag_crsp"] == 1).sum()),
        "finra_flags": int((both["flag_finra"] == 1).sum()),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "coverage_2026_min": round(float(by_day.min()), 4) if len(by_day) else None,
    }
    report["pass"] = bool(
        precision >= PRECISION and recall >= RECALL and len(by_day) and by_day.min() >= COVERAGE
    )
    return report


# Runs both checks and writes the fallbacks card.
def run() -> dict:
    lk = pd.read_parquet(DATA / "v4" / "links.parquet")
    report = {"short_interest": short_interest(lk), "volume": volume(lk)}
    report["volume_source_2026"] = "finra" if report["volume"]["pass"] else "off"
    (DATA / "v4" / "cards" / "fallbacks.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# Runs the fallback checks: uv run python -m fiam.vfinal.fallbacks
if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
