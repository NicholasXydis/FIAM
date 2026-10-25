# Extra datasets joined to the panel only as known at each decision.

from pathlib import Path

import pandas as pd

from fiam import data

ROOT = Path("data/fiam_v1/layers")


# One layer file, or None without the bundle, so callers skip cleanly.
def load(name: str, columns: list[str] | None = None) -> pd.DataFrame | None:
    path = ROOT / f"{name}.parquet"
    return data.read(path, columns) if path.exists() else None


# Each stock's latest value known at month end, at most ttl days old.
def as_of(
    frame: pd.DataFrame, layer: pd.DataFrame, known: str, columns: list[str], ttl: int
) -> pd.DataFrame:
    if "ret_exc_lead1m" in columns:
        raise ValueError("a layer may not carry the label")
    left = frame[data.KEYS].drop_duplicates().sort_values("eom")
    right = layer[["permno", known, *columns]].dropna(subset=[known]).sort_values(known)
    right[known] = pd.to_datetime(right[known]).astype(left["eom"].dtype)
    out = pd.merge_asof(
        left,
        right,
        left_on="eom",
        right_on=known,
        by="permno",
        direction="backward",
        tolerance=pd.Timedelta(days=ttl),
    )
    assert (out[known].dropna() <= out.loc[out[known].notna(), "eom"]).all(), "a value after eom"
    out = out.drop(columns=known)
    merged = frame.merge(out, on=data.KEYS, how="left")
    assert len(merged) == len(frame), "the join changed the row count"
    return merged
