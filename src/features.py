# Joins extra data onto the stock panel without rebuilding it. Each batch is its own file
# keyed by stock and month, so adding one is just a join. Rules p.16 asks finalists for this.

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

KEY = ["permno", "eom"]
BLOCKS = Path("data/features")


# Saves a new batch of data, after checking it is safe to use.
def register(name: str, frame: pd.DataFrame) -> Path:
    # Reject anything we cannot label by stock and month, or that we are not allowed to use.
    missing = set(KEY) - set(frame.columns)
    if missing:  # no key, no join
        raise ValueError(f"{name}: missing key columns {missing}")
    if frame.duplicated(KEY).any():  # the same stock twice would double-count
        raise ValueError(f"{name}: not unique on {KEY}")
    banned = {
        "ret_exc_lead1m",
        "ticker_name_status",
        "source_crsp",
        "ticker_name_source",
        "cusip_asof_date",
        "identifier_quality_flags",
        "title_ai",
    }
    leaked = banned & set(frame.columns)
    if leaked:
        raise ValueError(f"{name}: provenance/target columns are never features: {leaked}")

    BLOCKS.mkdir(parents=True, exist_ok=True)
    out = BLOCKS / f"{name}.parquet"  # one file per batch, named after it
    frame.assign(eom=pd.to_datetime(frame["eom"])).to_parquet(out, index=False)
    return out


# Joins every saved batch onto the stock panel and returns one table.
def load(names: list[str] | None = None) -> pd.DataFrame:
    # Keep every stock even where a batch has no data, or adding one would shrink the universe.
    spine = base_panel()
    # Alphabetical, so the columns come out in the same order on everyone's machine.
    for path in sorted(BLOCKS.glob("*.parquet")):
        if names is not None and path.stem not in names:
            continue
        block = pd.read_parquet(path)
        block["eom"] = pd.to_datetime(block["eom"])
        # Duplicate column names get silently renamed _x and _y, so stop instead.
        overlap = (set(block.columns) - set(KEY)) & set(spine.columns)
        if overlap:
            raise ValueError(f"{path.stem}: column names collide with the spine: {overlap}")
        spine = spine.merge(block, on=KEY, how="left", validate="one_to_one")
    return spine


# The base table everything joins onto. None of these columns are used to pick stocks.
def base_panel(chars: str = "data/chars_final_with_names.parquet") -> pd.DataFrame:
    cols = [
        "permno",
        "eom",
        "date",
        "prc",
        "me",
        "ret_exc_lead1m",
        "gics",
        "ff49",
        "size_grp",
        "dolvol_126d",
        "bidaskhl_21d",
        "beta_60m",
        "ticker",
        "company_name",
    ]
    panel = pq.read_table(chars, columns=cols).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    # First two digits give the 11 broad sectors. No sector gets its own group, never dropped.
    panel["sector"] = panel["gics"].astype("string").str[:2].fillna("XX")
    return panel


# Cuts the list down to stocks we would actually be willing to trade.
def screened(panel: pd.DataFrame, min_price: float = 5.0, min_me: float = 300.0) -> pd.DataFrame:
    # Never filter on whether a stock has a future return, that drops the companies that failed.
    return panel[(panel["prc"].abs() >= min_price) & (panel["me"] >= min_me)]
