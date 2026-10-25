# The data bundle, data/fiam_v1 or FIAM_DATA_DIR, the only data source.

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DIR = Path(os.environ.get("FIAM_DATA_DIR") or ROOT / "data" / "fiam_v1").expanduser()
FEATURES = DIR / "features_monthly.parquet"
LABELS = DIR / "labels_monthly.parquet"
FILINGS = DIR / "filings.parquet"
MANIFEST = DIR / "manifest.json"
WRDS = DIR / "wrds"
# Our WRDS extracts (tools/data/stock_data.py), never the raw archive.
EXTRACTS = ROOT / "data" / "v4" / "extracts"

# What every step needs. Judges will not have WRDS or research layers.
CORE = (FEATURES, LABELS, FILINGS, MANIFEST)
KEYS = ["permno", "eom"]
TARGET = "ret_exc_lead1m"
# v4 runs set FIAM_BLIND=1, so this reader seals 2021+ too (PLAN §1.3).
SEAL_EOM = pd.Timestamp("2020-12-31")

# The organizer readme's SHA-256s. The manifest records what was built.
PUBLISHED = {
    "chars_final_with_names.parquet": (
        "797c01ebd59f7a14585cb2e0290aa0b2c43b9188b7ac16384762d3df615215ca"
    ),
    "8k_20150101_20260831_identified.parquet": (
        "f333cd02076485ec3380e73d78c5d9bcc689b30827e7332ed6f699f58ab0cd07"
    ),
}


# The bundle's manifest: files, rows and checksums.
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# The 147 characteristics the rules name, the only list for predictors.
def characteristics() -> list[str]:
    return manifest()["organizer_characteristics"]


# Dates in whole seconds, the organizer panel's unit, so joins line up.
def read(path: Path, columns: list[str] | None = None, filters=None) -> pd.DataFrame:
    frame = pq.read_table(path, columns=columns, filters=filters).to_pandas()
    for column in ("eom", "holding_month"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column]).astype("datetime64[s]")
    if blind() and "eom" in frame:
        frame = frame[frame["eom"] <= SEAL_EOM].reset_index(drop=True)
    return frame


# Whether this is a v4 run under blind mode (set by its entry point).
def blind() -> bool:
    return os.environ.get("FIAM_BLIND") == "1"


# Predictors only. The label lives in its own file, never read here.
def features(columns: list[str]) -> pd.DataFrame:
    assert TARGET not in columns, f"{TARGET} is a label, read it with panel()"
    return read(FEATURES, sorted({*KEYS, *columns}))


# Predictors with next month's return, for backtests and training only.
def panel(columns: list[str]) -> pd.DataFrame:
    wanted = sorted({*KEYS, *columns})
    frame = features([c for c in wanted if c != TARGET])
    if TARGET in wanted:
        label = read(LABELS, [*KEYS, "next_month_excess_return"])
        label = label.rename(columns={"next_month_excess_return": TARGET})
        frame = frame.merge(label, on=KEYS, how="left", validate="one_to_one")
        # December 2020's label is January 2021: its row drops, never cut.
        if blind():
            frame = frame[frame["eom"] < SEAL_EOM - pd.offsets.MonthBegin(1)]
    return frame[wanted]


# One row per 8-K: dates, identifiers and item codes, no text.
def filings(columns: list[str] | None = None) -> pd.DataFrame:
    return read(FILINGS, columns)


# A converted WRDS table, or None on a run without WRDS.
def wrds(name: str, columns: list[str] | None = None) -> pd.DataFrame | None:
    path = WRDS / f"{name}.parquet"
    return pd.read_parquet(path, columns=columns) if path.exists() else None


# A research layer, which stops in 2025, or None if the bundle lacks it.
def research(name: str, columns: list[str] | None = None, filters=None) -> pd.DataFrame | None:
    path = DIR / f"{name}.parquet"
    return read(path, columns, filters) if path.exists() else None


# Size and date of each input file, so a cache key moves with the data.
def signature() -> str:
    files = [*CORE, WRDS / "exits.parquet"]
    return "".join(f"{p.name}{p.stat().st_size}{p.stat().st_mtime_ns}" for p in files if p.exists())


# The organizer files whose recorded SHA-256 differs from the published.
def checksum_mismatches() -> list[str]:
    sources = manifest().get("sources", {})
    return [n for n, digest in PUBLISHED.items() if sources.get(n, {}).get("sha256") != digest]


# Stops with the fix if the bundle is incomplete, labelled or misdated.
def validate() -> dict:
    missing = [p.name for p in CORE if not p.is_file()]
    if missing:
        raise SystemExit(f"{DIR} is missing {missing}. Rebuild: uv run -m fiam.build_data <folder>")
    names = pq.ParquetFile(FEATURES).schema_arrow.names
    assert TARGET not in names and "next_month_excess_return" not in names, "label in features"
    keys, labels = read(FEATURES, KEYS), read(LABELS, KEYS)
    assert not keys.duplicated().any() and keys.equals(labels), "features and labels misaligned"
    months = (str(keys["eom"].min().date()), str(keys["eom"].max().date()))
    assert months == ("2015-01-31", "2026-08-31"), f"months {months}"
    listed = characteristics()
    assert len(listed) == 147 and set(listed) <= set(names), "characteristic list incomplete"
    extras = sorted(p.stem for p in DIR.glob("*.parquet") if p not in CORE)
    return dict(
        bundle=str(DIR),
        stock_months=len(keys),
        months=f"{months[0]} to {months[1]}",
        organizer_checksums=checksum_mismatches() or "match the published values",
        wrds=sorted(p.stem for p in WRDS.glob("*.parquet")) or "none, so provisional",
        other_layers=extras,
    )


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
    sys.exit(1 if checksum_mismatches() else 0)
