# Current-vintage checks against archived copies (B23, protocol.md).

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
ARCHIVE = DATA / "benchmarks" / "french_archive"
CARDS = DATA / "v4" / "cards"
# The bar and the use rule fixed in protocol.md before the check ran.
BAR, STEP, MAX_LAG = 0.99, 0.01, 21
SERIES = {"five": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"], "mom": ["Mom"]}
TODAY = {"five": "ff5_daily.zip", "mom": "ff_momentum_daily.zip"}
NAMES = {
    "five": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "F-F_Momentum_Factor_daily_CSV.zip",
}


# One French daily file's table as printed: percent, two decimals.
def printed(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(","))
    body = []
    for line in lines[start:]:
        if line.strip() == "" and body:
            break
        body.append(line)
    t = pd.read_csv(io.StringIO("\n".join(body)))
    t = t.rename(columns={t.columns[0]: "date"})
    t.columns = [c.strip() for c in t.columns]
    t["date"] = pd.to_datetime(t["date"].astype(str).str.strip(), format="%Y%m%d")
    return t.set_index("date").astype(float)


# Archived and today's values side by side, with each value's age.
def overlap(kind: str, capture: str) -> pd.DataFrame:
    old = printed(ARCHIVE / f"{capture}_{NAMES[kind]}")
    new = printed(DATA / "benchmarks" / TODAY[kind])
    both = old[SERIES[kind]].join(new[SERIES[kind]], how="inner", lsuffix="_old", rsuffix="_new")
    # Age in sessions: French's own dates up to the capture day.
    days = new.index[new.index <= pd.Timestamp(capture[:8])]
    both["age"] = len(days) - days.searchsorted(both.index, side="right")
    return both


# Share of values matching within one rounding step, by minimum age.
def by_age(both: pd.DataFrame, series: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=both.index)
    for s in series:
        out[s] = (both[f"{s}_old"] - both[f"{s}_new"]).abs() <= STEP + 1e-9
    out["age"] = both["age"]
    ordered = out.sort_values("age", ascending=False)
    share = ordered[series].cumsum().div(np.arange(1, len(ordered) + 1), axis=0)
    share["age"] = ordered["age"].to_numpy()
    # Each age's share over all values at least that old.
    return share.groupby("age").last().sort_index()


# L: the first age from which the bar holds at every older age, or None.
def smallest_age(holds: pd.Series) -> int | None:
    tail = holds.sort_index()[::-1].cummin()[::-1]
    return int(tail[tail].index.min()) if tail.any() else None


# L for one pair of captures: the smallest age where every series holds.
def lag(five: str, mom: str) -> dict:
    tables = {"five": overlap("five", five), "mom": overlap("mom", mom)}
    shares = by_age(tables["five"], SERIES["five"]).join(
        by_age(tables["mom"], SERIES["mom"]), how="inner"
    )
    holds = (shares[SERIES["five"] + SERIES["mom"]] >= BAR).all(axis=1)
    lag_sessions = smallest_age(holds)
    picks = [0, 21, 63, 252, 1260, 2520, 5040]
    near = {
        a: {s: round(float(shares[s].loc[shares.index >= a].iloc[0]), 4) for s in shares.columns}
        for a in picks
        if (shares.index >= a).any()
    }
    years = {}
    for kind, t in tables.items():
        for s in SERIES[kind]:
            ok = (t[f"{s}_old"] - t[f"{s}_new"]).abs() <= STEP + 1e-9
            years[s] = {
                int(y): round(float(v), 4) for y, v in ok.groupby(t.index.year).mean().items()
            }
    return {
        "captures": {"five": five, "mom": mom},
        "overlap_days": {k: len(t) for k, t in tables.items()},
        "L_sessions": lag_sessions,
        "share_at_least_this_old": near,
        "share_by_value_year": years,
    }


# The B23 French check: the newest pre-2021 pair decides, others beside.
def french() -> dict:
    book = json.loads((ARCHIVE / "receipts.json").read_text())
    stamps = {
        k: sorted(e["captured"] for n, e in book.items() if n.endswith(NAMES[k])) for k in NAMES
    }
    report = {"bar": BAR, "step_percent": STEP, "max_lag_sessions": MAX_LAG}
    report["deciding"] = lag(stamps["five"][-1], stamps["mom"][-1])
    found = report["deciding"]["L_sessions"]
    report["crash_control_allowed"] = found is not None and found <= MAX_LAG
    # Older captures, paired by nearest date, reported and never deciding.
    beside = []
    for five in stamps["five"][:-1]:
        mom = min(stamps["mom"], key=lambda m: abs(int(m[:8]) - int(five[:8])))
        beside.append(lag(five, mom))
    report["beside"] = beside
    CARDS.mkdir(parents=True, exist_ok=True)
    (CARDS / "french_vintage.json").write_text(json.dumps(report, indent=1, default=str))
    return report


NOAA = DATA / "noaa"
# NOAA's bars fixed in protocol.md: counts equal, climate within 0.1.
NOAA_BAR, CLIMATE_STEP, NOAA_MAX_MONTHS = 0.99, 0.1, 12
SENTINELS = (-99.9, -9.99, -99.99, -9999.0)


# One climdiv state file as (state, month) values, sentinels dropped.
def climate(path: Path) -> pd.Series:
    rows = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 13:
            continue
        head = parts[0]
        state, year = head[:3], int(head[6:10])
        for month, value in enumerate(parts[1:13], 1):
            v = float(value)
            if not any(abs(v - s) < 1e-6 for s in SENTINELS):
                rows[(state, pd.Period(f"{year}-{month:02d}", "M"))] = v
    return pd.Series(rows)


# Storm events per county and event month from one details file.
def storm_counts(path: Path) -> pd.Series:
    cols = ["STATE_FIPS", "CZ_FIPS", "CZ_TYPE", "BEGIN_YEARMONTH"]
    t = pd.read_csv(path, usecols=cols, dtype={"CZ_TYPE": str}, encoding="latin-1")
    t = t[t["CZ_TYPE"] == "C"]
    month = pd.PeriodIndex(t["BEGIN_YEARMONTH"].astype(str), freq="M")
    return t.groupby([t["STATE_FIPS"], t["CZ_FIPS"], month]).size()


# Archived and today's values: match flags and each one's age in months.
def compare(old: pd.Series, new: pd.Series, captured: str, same) -> pd.DataFrame:
    month = pd.Period(captured[:6], "M")
    old = old[old.index.get_level_values(-1) <= month]
    new = new[new.index.get_level_values(-1) <= old.index.get_level_values(-1).max()]
    both = pd.concat([old.rename("old"), new.rename("new")], axis=1)
    when = both.index.get_level_values(-1)
    out = pd.DataFrame({"ok": same(both["old"], both["new"])}, index=both.index)
    out["age"] = [(month - p).n for p in when]
    return out


# Share unchanged among values at least a months old, for each age.
def shares_by_age(frames: list[pd.DataFrame]) -> pd.Series:
    t = pd.concat(frames, ignore_index=True).sort_values("age", ascending=False)
    share = t["ok"].cumsum() / np.arange(1, len(t) + 1)
    return pd.Series(share.to_numpy(), index=t["age"].to_numpy()).groupby(level=0).last()


# The B23 NOAA check: newest pre-2021 copies decide (protocol.md).
def noaa() -> dict:
    book = json.loads((NOAA / "archive" / "receipts.json").read_text())
    today = {
        p.name.split("_c")[0]: p for p in (NOAA / "storms").glob("StormEvents_details*.csv.gz")
    }
    newest_storm, newest_climate = {}, {}
    for key, entry in book.items():
        name = key.split("_", 1)[1]
        if name.startswith("StormEvents"):
            base = name.split("_c")[0]
            if base not in newest_storm or entry["captured"] > newest_storm[base][0]:
                newest_storm[base] = (entry["captured"], key)
        else:
            kind = name.split("-")[1]
            if kind not in newest_climate or entry["captured"] > newest_climate[kind][0]:
                newest_climate[kind] = (entry["captured"], key)
    storms = []
    for base, (captured, key) in sorted(newest_storm.items()):
        old = storm_counts(NOAA / "archive" / key)
        new = storm_counts(today[base])
        storms.append(compare(old, new, captured, lambda a, b: a.fillna(0) == b.fillna(0)))
    series = {"storm_county_months": shares_by_age(storms)}
    for kind, (captured, key) in sorted(newest_climate.items()):
        now = next((NOAA / "climdiv").glob(f"climdiv-{kind}-v*"))
        frame = compare(
            climate(NOAA / "archive" / key),
            climate(now),
            captured,
            lambda a, b: (a - b).abs() <= CLIMATE_STEP + 1e-9,
        )
        series[kind] = shares_by_age([frame.dropna()])
    # A missing age takes the next older age's share; past a series' oldest
    # value nothing is left to check, so that age passes for it.
    table = pd.DataFrame(series).sort_index().bfill().fillna(1.0)
    holds = (table >= NOAA_BAR).all(axis=1)
    lag_months = smallest_age(holds)
    picks = [0, 4, 6, 12, 24, 60, 120]
    report = {
        "storm_files": len(newest_storm),
        "climate_files": {k: v[1] for k, v in newest_climate.items()},
        "values_compared": {"storm_county_months": int(sum(len(s) for s in storms))},
        "L_months": lag_months,
        "share_at_least_this_old": {
            a: {c: round(float(table[c].loc[table.index >= a].iloc[0]), 4) for c in table}
            for a in picks
            if (table.index >= a).any()
        },
    }
    report["exhibits"] = (
        f"count from {lag_months} months"
        if lag_months is not None and lag_months <= NOAA_MAX_MONTHS
        else "current vintage: exhibits labelled so, desk flags live only"
    )
    report["beside"] = noaa_beside(book, today, newest_storm, newest_climate)
    (CARDS / "noaa_vintage.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# Older captures, grouped by capture month, reported and never deciding.
def noaa_beside(book: dict, today: dict, storm_used: dict, climate_used: dict) -> list:
    used = {k for _, k in storm_used.values()} | {k for _, k in climate_used.values()}
    groups: dict[str, list[str]] = {}
    for key, entry in book.items():
        if key not in used:
            groups.setdefault(entry["captured"][:6], []).append(key)
    out = []
    for month, keys in sorted(groups.items()):
        frames, climate_frames = [], {}
        for key in keys:
            name = key.split("_", 1)[1]
            captured = book[key]["captured"]
            if name.startswith("StormEvents"):
                old, new = (
                    storm_counts(NOAA / "archive" / key),
                    storm_counts(today[name.split("_c")[0]]),
                )
                frames.append(compare(old, new, captured, lambda a, b: a.fillna(0) == b.fillna(0)))
            else:
                kind = name.split("-")[1]
                now = next((NOAA / "climdiv").glob(f"climdiv-{kind}-v*"))
                same = lambda a, b: (a - b).abs() <= CLIMATE_STEP + 1e-9  # noqa: E731
                climate_frames[kind] = compare(
                    climate(NOAA / "archive" / key), climate(now), captured, same
                ).dropna()
        row = {"capture_month": month, "files": len(keys)}
        for label, frame in [("storm_county_months", frames)] + [
            (k, [f]) for k, f in climate_frames.items()
        ]:
            if frame:
                s = shares_by_age(frame)
                row[label] = round(float(s.iloc[0]), 4)
        out.append(row)
    return out


# Runs a check: uv run python -m fiam.v4.vintage [french | noaa]
if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["noaa"]:
        print(json.dumps(noaa(), indent=1, default=str))
    else:
        out = french()
        d = out["deciding"]
        print(json.dumps({k: d[k] for k in ("captures", "overlap_days", "L_sessions")}, indent=1))
        print("crash control allowed:", out["crash_control_allowed"])
