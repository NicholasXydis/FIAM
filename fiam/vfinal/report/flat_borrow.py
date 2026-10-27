# The same trades with borrow re-priced flat, as the PDF's line.

import json
import pickle
import sys
from pathlib import Path

import pandas as pd

from fiam.vfinal import daily_book, data, final, headline, inputs
from fiam.vfinal.exhibits import build as exhibits
from fiam.vfinal.report import table_9_1

# Large caps borrow at 0.5% a year, others at 5%; caps in US$ millions.
LARGE, CHEAP, DEAR = 10_000.0, 0.005, 0.05


# Each name's flat borrow rate from its market cap at the trade day.
def flat_rate(caps: pd.Series) -> pd.Series:
    return pd.Series(DEAR, index=caps.index).where(~(caps >= LARGE), CHEAP)


# Each session's flat borrow, scaled to the borrow the engine booked.
def flat(daily: pd.DataFrame, positions: pd.DataFrame, hooks, market) -> pd.Series:
    keys = sorted(hooks.frames)
    short = positions[positions["value"] < 0]
    held = short.pivot(index="date", columns="permno", values="value").reindex(daily.index)
    base = (-held.shift(1)).fillna(0.0)
    out = pd.Series(0.0, index=daily.index)
    for i, k in enumerate(keys):
        end = keys[i + 1] if i + 1 < len(keys) else daily.index[-1] + pd.Timedelta(days=1)
        days = daily.index[(daily.index >= k) & (daily.index < end)]
        tier = hooks.frames[k]["borrow"].reindex(base.columns)
        tier = tier.fillna(hooks.frames[k]["borrow"].max())
        t = data.shift([k], -1).iloc[0]
        caps = pd.Series([market.cap_at(int(p), t) for p in base.columns], index=base.columns)
        rate = flat_rate(caps)
        # Each day's booked borrow re-priced at the flat rates.
        for d in days:
            v = base.loc[d]
            booked = float((v * tier).sum())
            if booked > 0 and daily.at[d, "borrow"] > 0:
                out[d] = daily.at[d, "borrow"] * float((v * rate).sum()) / booked
    return out


# The 23 rows again with flat borrow, written beside the run's own.
def table(folder: Path, head: str) -> dict:
    stem = exhibits.stem_of(folder, head)
    with final.opened():
        daily = pd.read_parquet(folder / f"daily_{stem}.parquet")
        positions = pd.read_parquet(folder / f"positions_{stem}.parquet")
        trades = pd.read_parquet(folder / f"trades_{stem}.parquet")
        with (folder / f"plans_{stem}.pkl").open("rb") as fh:
            hooks = pickle.load(fh)["hooks"]
        shorts = sorted(positions.loc[positions["value"] < 0, "permno"].unique())
        market = daily_book.Market(shorts, daily.index)
        caps = exhibits.short_caps(positions, daily.index)
        b_flat = flat(daily, positions, hooks, market)
        prev = daily["nav"].shift(1)
        alt = daily.assign(borrow=b_flat)
        alt["ret"] = daily["ret"] + ((daily["borrow"] - b_flat) / prev).fillna(0.0)
        bill = headline.monthly_rate(data.rf_daily(daily.index))
        rows = table_9_1.table(alt, trades, positions, inputs.sp500(daily.index),
                               rf_monthly=bill, caps=caps)  # fmt: skip
    rows.to_csv(folder / f"table_9_1_flat_borrow_{head[:12]}.csv", index=False)
    years = (len(daily) - 1) / 252
    return {
        "booked_pct_nav_year": float((daily["borrow"] / prev).iloc[1:].sum() / years * 100),
        "flat_pct_nav_year": float((b_flat / prev).iloc[1:].sum() / years * 100),
        "rows": rows[rows["row"].isin([1, 3, 8, 9, 22, 23])].to_dict("records"),
    }


# uv run python -m fiam.vfinal.report.flat_borrow <run folder> <commit>
if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("uv run python -m fiam.vfinal.report.flat_borrow <run folder> <commit>")
    print(json.dumps(table(Path(sys.argv[1]), sys.argv[2]), indent=1, default=str))
