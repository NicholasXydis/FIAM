# Carbon Arc CA0038 retail net sales against SEC as-filed quarters.

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from fiam.alt import common, passport
from fiam.v4 import sources

ROOT = sources.ROOT
FILE = sources.DATA / "carbon_arc" / "snapshot_2" / "CA0038_343_ten_retail.json.gz"
OUT = ROOT / "out" / "alt" / "retailers"
# A Carbon Arc date meets an SEC period end within this many days.
MATCH_DAYS = 7
# The two closeness bands the check reports, as shares of SEC sales.
TIGHT, LOOSE = 0.005, 0.02
# Largest misses listed per company and overall.
MISSES = 3


# The set's rows, its value column and its receipt, as saved.
def load(path: Path = FILE) -> tuple[pd.DataFrame, str, dict]:
    rows, value = passport.load(path)
    receipt = json.loads(path.with_name(path.name.replace(".json.gz", ".receipt.json")).read_text())
    rows = rows.assign(date=pd.to_datetime(rows["date"]), value=rows[value].astype(float))
    return rows.rename(columns={"entity_name": "ticker"}), value, receipt


# Ticker to PERMNO by date, else the ticker's later PERMNO if listed.
def map_permnos(rows: pd.DataFrame, links: pd.DataFrame, dated: pd.Series) -> pd.DataFrame:
    out = rows.assign(permno=pd.array(dated, dtype="Int64"), how="dated ticker")
    later = out.dropna(subset=["permno"]).sort_values("date").groupby("ticker")["permno"].first()
    span = links.groupby("permno").agg(lo=("valid_from", "min"), hi=("valid_to", "max"))
    gap = out["permno"].isna() & out["ticker"].isin(later.index)
    # Each gap tries the PERMNO its ticker maps to on a later date.
    for i in out.index[gap]:
        p = int(later[out.at[i, "ticker"]])
        lo, hi = span.loc[p] if p in span.index else (pd.NaT, pd.NaT)
        # Listed on the date: CRSP's first link is on or before it.
        if pd.notna(lo) and lo <= out.at[i, "date"] and (pd.isna(hi) or out.at[i, "date"] <= hi):
            out.at[i, "permno"], out.at[i, "how"] = p, "same ticker's later PERMNO"
    out.loc[out["permno"].isna(), "how"] = "no PERMNO on the date"
    return out


# Each row's nearest SEC quarter within the window, with its gap.
def match(rows: pd.DataFrame, sec: pd.DataFrame, days: int = MATCH_DAYS) -> pd.DataFrame:
    left = rows.reset_index(drop=True).assign(rid=lambda f: f.index)
    have = left.dropna(subset=["permno"]).astype({"permno": "int64"})
    pairs = have[["rid", "permno", "date"]].merge(sec, on="permno")
    pairs["offset"] = (pairs["end"] - pairs["date"]).dt.days
    pairs = pairs[pairs["offset"].abs() <= days]
    pairs = pairs.assign(gap=pairs["offset"].abs()).sort_values(["rid", "gap", "filed"])
    best = pairs.drop_duplicates("rid").set_index("rid")
    cols = ["end", "val", "tag", "basis", "filed", "offset"]
    out = left.join(best[cols].rename(columns={"val": "sec"}))
    out["matched"] = out["sec"].notna()
    out["diff"] = out["value"] - out["sec"]
    out["rel"] = out["diff"] / out["sec"].abs()
    return out.drop(columns="rid")


# The closest SEC figure under any sales tag for each matched row.
def any_tag(matched: pd.DataFrame, every: pd.DataFrame) -> pd.Series:
    hit = matched[matched["matched"]].reset_index()
    pairs = hit[["index", "permno", "end", "value"]].astype({"permno": "int64"})
    pairs = pairs.merge(every[["permno", "end", "val"]], on=["permno", "end"])
    pairs["rel"] = (pairs["value"] - pairs["val"]).abs() / pairs["val"].abs()
    return pairs.groupby("index")["rel"].min().reindex(matched.index)


# Counts, closeness shares, median gap and the largest misses.
def summary(part: pd.DataFrame, misses: int = MISSES) -> dict:
    hit = part[part["matched"]]
    rel = hit["rel"].abs()
    out = {"rows": len(part), "mapped": int(part["permno"].notna().sum()), "matched": len(hit)}
    out["within_0_5pct"] = int((rel <= TIGHT).sum())
    out["within_2pct"] = int((rel <= LOOSE).sum())
    out["share_within_0_5pct"] = common_share(out["within_0_5pct"], len(hit))
    out["share_within_2pct"] = common_share(out["within_2pct"], len(hit))
    out["median_abs_rel_diff"] = None if hit.empty else round(float(rel.median()), 6)
    out["median_abs_diff_usd"] = None if hit.empty else round(float(hit["diff"].abs().median()))
    # The best of every sales tag, to tell a tag choice from a real miss.
    if "rel_any_tag" in hit:
        out["share_within_0_5pct_any_tag"] = common_share(
            int((hit["rel_any_tag"] <= TIGHT).sum()), len(hit)
        )
    worst = hit.assign(size=rel).sort_values("size", ascending=False).head(misses)
    out["largest_misses"] = [
        {
            "ticker": r["ticker"],
            "carbon_arc_date": str(r["date"].date()),
            "sec_period_end": str(r["end"].date()),
            "rel_diff": round(float(r["rel"]), 6),
            "sec_tag": r["tag"],
            "sec_basis": r["basis"],
        }
        for _, r in worst.iterrows()
    ]
    return out


# Mapped rows left without an SEC quarter, with their dates and reason.
def unmatched(part: pd.DataFrame) -> list[dict]:
    late = "no SEC quarter public by the seal ends within the window"
    miss = part[~part["matched"]]
    why = miss["how"].where(miss["permno"].isna(), late)
    days = miss["date"].dt.strftime("%Y-%m-%d")
    return [{"ticker": t, "date": d, "why": w} for t, d, w in zip(miss["ticker"], days, why)]


# Every matched row further than 0.5% from the SEC figure.
def misses(part: pd.DataFrame) -> list[dict]:
    hit = part[part["matched"] & (part["rel"].abs() > TIGHT)].sort_values(["ticker", "date"])
    out = []
    # Each miss with whether any other sales tag would have met it.
    for _, r in hit.iterrows():
        row = {"ticker": r["ticker"], "date": str(r["date"].date())}
        row |= {"rel_diff": round(float(r["rel"]), 6), "sec_tag": r["tag"]}
        row["any_tag_within_0_5pct"] = bool(r["rel_any_tag"] <= TIGHT)
        out.append(row)
    return out


# A share as a rounded float, or None when there is nothing to share.
def common_share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


# Days from the table's last data date to the pull, overall and by firm.
def staleness(rows: pd.DataFrame, receipt: dict) -> dict:
    pulled = pd.Timestamp(receipt["pulled_at"]).tz_convert("UTC").tz_localize(None).normalize()
    top = pd.Timestamp(receipt["metadata"]["table_max_date"]).normalize()
    last = rows.groupby("ticker")["date"].max()
    return {
        "pulled_at": receipt["pulled_at"],
        "table_max_date": str(top.date()),
        "last_row_date": str(rows["date"].max().date()),
        "pull_minus_table_max_days": int((pulled - top).days),
        "pull_minus_last_row_days": int((pulled - rows["date"].max()).days),
        "pull_minus_last_row_days_by_ticker": {t: int((pulled - d).days) for t, d in last.items()},
    }


# What the file holds, read from its own rows and receipt.
def inspect(rows: pd.DataFrame, value: str, receipt: dict) -> dict:
    payload = receipt["metadata"]["payload"]
    return {
        "value_column": value,
        "dataset": receipt["item"]["dataset"],
        "insight": receipt["item"]["insight"],
        "resolution": payload["filters"]["date_resolution"],
        "aggregate": payload.get("aggregate"),
        "rows": len(rows),
        "tickers": sorted(rows["ticker"].unique()),
        "first_date": str(rows["date"].min().date()),
        "duplicate_ticker_dates": int(rows.duplicated(["ticker", "date"]).sum()),
        "weekday_counts": {
            str(k): int(v) for k, v in rows["date"].dt.day_name().value_counts().items()
        },
    }


# The full check on the sealed window; None when the run is refused.
def build(end=None, path: Path = FILE, out: Path = OUT) -> dict | None:
    from fiam.v4 import data

    last = common.run_end(end)
    # A run past the cutoff while sealed stops before reading anything.
    if last is None:
        return None
    every, value, receipt = load(path)
    rows, dropped = common.drop_after(every, last)
    links = data.table("links", None)
    dated = common.permnos(rows["ticker"], rows["date"])
    rows = map_permnos(rows, links, dated)
    stocks = rows["permno"].dropna().astype("int64").unique()
    done = match(rows, common.sec_quarters(stocks))
    done["rel_any_tag"] = any_tag(done, common.sec_quarters(stocks, first_only=False))
    hit = done[done["matched"]]
    report = {
        "about": "Carbon Arc CA0038 net sales against SEC as-filed quarterly sales",
        "credit": common.CREDIT,
        "seal": {
            "unsealed": sources.unsealed(),
            "run_end": str(last.date()),
            "rows_in_file": len(every),
            "rows_after_end_dropped": dropped,
            "statement": (
                f"The default run ends {last.date()}. {dropped} of {len(every)} rows dated "
                "later were dropped before any comparison, and SEC facts are read through "
                "the sealed reader, so only filings public by then count"
            ),
        },
        "file": inspect(every, value, receipt),
        "rule": (
            f"a row matches the SEC three-month figure of the same PERMNO whose period ends "
            f"within {MATCH_DAYS} days of its date; a fiscal Q4 with no three-month fact is "
            "the year less nine months; net sales tags are tried before total revenue"
        ),
        "mapping": done["how"].value_counts().to_dict(),
        "date_offset_days": {
            int(k): int(v) for k, v in hit["offset"].value_counts().sort_index().items()
        },
        "sec_tags_used": hit["tag"].value_counts().to_dict(),
        "sec_basis_used": hit["basis"].value_counts().to_dict(),
        "overall": summary(done, MISSES * 2),
        "by_ticker": {t: summary(p) for t, p in done.groupby("ticker")},
        "misses_over_0_5pct": misses(done),
        "unmatched": unmatched(done),
        "staleness": staleness(every, receipt),
    }
    found = report["date_offset_days"]
    same = found.get(0, 0)
    report["file"]["finding"] = (
        f"{value} is one quarterly figure per ticker, dated at the fiscal period end: "
        f"{same} of {len(hit)} matched rows carry the SEC period end date itself"
    )
    out.mkdir(parents=True, exist_ok=True)
    keep = ["ticker", "date", "permno", "how", "value", "end", "sec", "tag", "basis", "rel"]
    done[keep].to_csv(out / "retailers.csv", index=False)
    (out / "retailers.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# uv run python -m fiam.alt.retailers [--end YYYY-MM-DD]
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CA0038 net sales against SEC filings")
    parser.add_argument("--end", default=None, help="last date read, 2020-12-31 while sealed")
    args = parser.parse_args(argv)
    report = build(args.end)
    # A refused run has printed its one line already.
    if report is None:
        return 1
    o = report["overall"]
    print(report["seal"]["statement"])
    print(report["file"]["finding"])
    print(
        f"matched {o['matched']} of {o['rows']}, within 0.5% {o['share_within_0_5pct']}, "
        f"within 2% {o['share_within_2pct']}, median abs {o['median_abs_rel_diff']}"
    )
    # One line per company: matched rows and the two closeness shares.
    for t, s in report["by_ticker"].items():
        print(t, s["matched"], s["share_within_0_5pct"], s["share_within_2pct"])
    print(json.dumps(report["staleness"], indent=1))
    return 0


# Run with uv run python -m fiam.alt.retailers
if __name__ == "__main__":
    sys.exit(main())
