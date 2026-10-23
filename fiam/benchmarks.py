# Reads the pinned benchmark files; --refresh downloads them again and records where they came from.

import hashlib
import json
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fiam import paths

BENCH = Path("data/benchmarks")
SOURCES = BENCH / "sources.json"
FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"

# Federal Reserve H.10 daily rates for the global switch's currencies (finals_global.md), in
# files of 12, the most FRED returns at once.
FX = (
    "DEXCAUS", "DEXJPUS", "DEXUSEU", "DEXUSUK", "DEXUSAL", "DEXUSNZ", "DEXSZUS", "DEXCHUS",
    "DEXHKUS", "DEXINUS", "DEXKOUS", "DEXMXUS", "DEXBZUS", "DEXDNUS", "DEXNOUS", "DEXSDUS",
    "DEXSIUS", "DEXSFUS", "DEXTAUS", "DEXTHUS", "DEXMAUS", "DEXSLUS",
)  # fmt: skip
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# Every external input, keyless. A refresh is deliberate, never a side effect of a rerun.
URLS = {
    "TB3MS.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS&cosd=2015-01-01",
    "SP500.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
    "ff_factors.zip": FRENCH + "F-F_Research_Data_Factors_CSV.zip",
    "ff5_factors.zip": FRENCH + "F-F_Research_Data_5_Factors_2x3_CSV.zip",
    "ff_momentum.zip": FRENCH + "F-F_Momentum_Factor_CSV.zip",
    # Daily factors and the full T-bill history, for stress tests.
    "ff5_daily.zip": FRENCH + "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "ff_momentum_daily.zip": FRENCH + "F-F_Momentum_Factor_daily_CSV.zip",
    "TB3MS_full.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS",
}
for i in range(0, len(FX), 12):
    part = FX[i : i + 12]
    URLS[f"fx_daily_{i // 12 + 1}.csv"] = (
        FRED + ",".join(part) + "&cosd=" + ",".join(["2014-01-01"] * len(part))
    )


# A pinned file, or a clear instruction if it is missing. Nothing downloads on its own.
def pinned(name: str) -> Path:
    path = BENCH / name
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: uv run -m fiam.benchmarks --refresh {name}")
    return path


# One Ken French file as monthly decimals keyed on the month. Headers and annual rows skipped.
def french(name: str, columns: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(pinned(name)) as archive:
        raw = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    rows = [r.split(",") for r in raw if r.strip()[:6].isdigit()]
    # Annual rows share the layout but carry a four-digit year, so keep six-digit months only.
    rows = [r for r in rows if len(r) == len(columns) + 1 and len(r[0].strip()) == 6]
    frame = pd.DataFrame(rows, columns=["ym", *columns])
    frame["month"] = pd.to_datetime(frame["ym"].str.strip(), format="%Y%m")
    return frame.set_index("month")[columns].astype(float) / 100


# One Ken French daily file as decimals keyed on the trading day.
def french_daily(name: str, columns: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(pinned(name)) as archive:
        raw = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    rows = [r.split(",") for r in raw if r.strip()[:8].isdigit()]
    rows = [r for r in rows if len(r) == len(columns) + 1 and len(r[0].strip()) == 8]
    frame = pd.DataFrame(rows, columns=["ymd", *columns])
    frame["date"] = pd.to_datetime(frame["ymd"].str.strip(), format="%Y%m%d")
    return frame.set_index("date")[columns].astype(float) / 100


# The S&P 500 price index as monthly returns, month-end close to month-end close, no dividends.
def sp500() -> pd.Series:
    daily = pd.read_csv(pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    close = daily.set_index("observation_date")["SP500"].resample("ME").last()
    returns = close.pct_change().dropna()
    returns.index = returns.index.to_period("M").to_timestamp()
    return returns.rename("sp500")


# The cash rate, the S&P 500 and the CRSP market, by holding month, each in excess of cash.
def benchmarks() -> pd.DataFrame:
    tb = pd.read_csv(pinned("TB3MS.csv"), parse_dates=["observation_date"])
    tb = tb.rename(columns={"observation_date": "month", "TB3MS": "tb3ms"})
    tb["month"] = tb["month"].dt.normalize()
    tb["rf"] = tb["tb3ms"] / 100 / 12
    crsp = french("ff_factors.zip", ["mkt_rf", "smb", "hml", "rf"])["mkt_rf"].rename("mkt_rf_crsp")
    # Keep every month even where a market series has not arrived yet or does not reach back.
    out = tb[["month", "rf"]].merge(crsp.reset_index(), on="month", how="left")
    out = out.merge(sp500().rename_axis("month").reset_index(), on="month", how="left")
    out["mkt_rf"] = out.pop("sp500") - out["rf"]
    return out


# Three tries, because a slow response once should not mean a missing benchmark.
def download(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


# Downloads the named files, or all of them, and records URL, date and hash beside them.
def refresh(names: list[str]) -> None:
    BENCH.mkdir(parents=True, exist_ok=True)
    record = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    for name in names or list(URLS):
        body = download(URLS[name])
        (BENCH / name).write_bytes(body)
        record[name] = dict(
            url=URLS[name],
            retrieved_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sha256=hashlib.sha256(body).hexdigest(),
            bytes=len(body),
        )
        print(f"  {name}: {len(body):,} bytes")
    paths.write_json(SOURCES, record, rounded=False)


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        refresh([a for a in sys.argv[1:] if a in URLS])
