# The PDF's exhibits and the extras, drawn from one run's result files.

import json
import pickle
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from fiam.exhibits_v4 import common, extras, required
from fiam.exhibits_v4.build import build
from fiam.v4 import daily_book, data, final, inputs
from fiam.v4.report import holdings


# The design and commit part of a run's file names, from its daily file.
def stem_of(folder: Path, head: str) -> str:
    found = sorted(folder.glob(f"daily_*_{head[:12]}.parquet"))
    if len(found) != 1:
        raise SystemExit(f"expected one daily file for {head[:12]} in {folder}")
    return found[0].stem.removeprefix("daily_")


# Every short row's market cap on its own day, as the report reads it.
def short_caps(positions: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    shorts = positions[positions["value"] < 0]
    market = daily_book.Market(sorted(shorts["permno"].unique()), days)
    me = [market.cap_at(int(p), d) for p, d in zip(shorts["permno"], shorts["date"])]
    return shorts[["date", "permno"]].assign(me=me).reset_index(drop=True)


# Month-end sessions of the run with every name held on them.
def month_end_rows(positions: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    ends = sorted({data.eom_session([data.month_end_at(d)]).iloc[0] for d in days})
    ends = [e for e in ends if days[0] <= e <= days[-1]]
    return positions[positions["date"].isin(ends)][["date", "permno"]]


# Each formation's ADV from its kept frame, dated by its trade day.
def adv_of(kept: dict) -> pd.DataFrame:
    rows = [f["adv_cost"].rename("adv").rename_axis("permno").reset_index().assign(date=day)
            for day, f in kept.items()]  # fmt: skip
    return pd.concat(rows, ignore_index=True)[["date", "permno", "adv"]]


# The tables the exhibits read, from a run's folder and file stem.
def tables(folder: Path, stem: str) -> dict:
    out = {p: pd.read_parquet(folder / f"{p}_{stem}.parquet") for p in final.PARTS
           if (folder / f"{p}_{stem}.parquet").exists()}  # fmt: skip
    days = out["daily"].index
    with (folder / f"plans_{stem}.pkl").open("rb") as fh:
        kept = pickle.load(fh)["kept"]
    held = month_end_rows(out["positions"], days)
    ids = holdings.identifiers(held["permno"], held["date"])
    out |= {"bench": inputs.sp500(days), "caps": short_caps(out["positions"], days)}
    return out | {"adv": adv_of(kept), "ids": ids[["permno", "date", "ticker", "name"]]}


# Each exhibit alone, so one that fails leaves the others drawn.
def one_by_one(t: dict, out: Path, meta: dict) -> list:
    x = common.prepare(t, meta)
    out.mkdir(parents=True, exist_ok=True)
    written, failed = [], {}
    for name, draw in required.EXHIBITS + extras.EXTRAS:
        if name == "extra_k1_fundamental_law" and x.k1 is None:
            continue
        try:
            with matplotlib.rc_context({"text.parse_math": False}):
                fig, frame = draw(x)
                written += common.save(fig, frame, out, name)
        except Exception as err:
            failed[name] = repr(err)[:300]
            plt.close("all")
    (out / "failed.json").write_text(json.dumps(failed, indent=1))
    return written


# Every exhibit of one run into a folder; one by one if the set fails.
def draw(folder: Path, head: str, target: Path) -> list:
    stem = stem_of(folder, head)
    with final.opened():
        t = tables(folder, stem)
        days = t["daily"].index
        meta = {"window": (f"{days[1]:%Y-%m-%d}", f"{days[-1]:%Y-%m-%d}"), "arm": "A0",
                "notes_2026": []}  # fmt: skip
        try:
            return build(t, target, meta)
        except Exception as err:
            print("set stopped, drawing one by one:", repr(err), flush=True)
            return one_by_one(t, target, meta)


# uv run python -m tools.exhibits <run folder> <commit> <output folder>
if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("uv run python -m tools.exhibits <run folder> <commit> <output folder>")
    paths = draw(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
    print(json.dumps([str(p) for p in paths], indent=0))
