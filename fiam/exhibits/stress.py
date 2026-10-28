# Crash windows and replays for any book: crises, scenarios, factors.

import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam import book as P
from fiam import data

# CRSP daily from our extract, one parquet file per year.
DAILY = data.EXTRACTS / "crsp_daily"
CACHE = P.CACHE / "stress_daily.parquet"
FACTORS = ["mktrf", "smb", "hml", "rmw", "cma", "umd"]

# Seventeen crises from market events, and the stress scenarios.
CRISES = {
    "Dot-com peak crash": ("2000-03-10", "2000-04-14"),
    "September 11": ("2001-09-10", "2001-09-21"),
    "Accounting scandals": ("2002-07-01", "2002-07-23"),
    "Quant unwind": ("2007-07-24", "2007-08-10"),
    "Bear Stearns": ("2008-03-03", "2008-03-17"),
    "Lehman and the crash": ("2008-09-12", "2008-10-27"),
    "Junk rally, momentum crash": ("2009-03-09", "2009-05-29"),
    "US downgrade": ("2011-07-22", "2011-08-19"),
    "Taper tantrum": ("2013-05-22", "2013-06-24"),
    "China devaluation": ("2015-08-18", "2015-08-25"),
    "Oil and high-yield sell-off": ("2016-01-04", "2016-02-11"),
    "Volatility spike": ("2018-01-26", "2018-02-08"),
    "Late-2018 sell-off": ("2018-10-03", "2018-12-24"),
    "Covid crash": ("2020-02-19", "2020-03-23"),
    "Vaccine rotation": ("2020-11-06", "2020-11-13"),
    "Rate shock": ("2022-01-03", "2022-06-16"),
    "Yen carry unwind": ("2024-07-31", "2024-08-05"),
}
SCENARIOS = {
    "Oil crash 2014-16": ("2014-06-20", "2016-02-11"),
    "Oil crash 2020": ("2020-03-06", "2020-04-21"),
    "Energy shock 2022": ("2022-02-24", "2022-06-08"),
    "Trade war, Mar 2018": ("2018-03-22", "2018-04-06"),
    "Trade war, Jun 2018": ("2018-06-15", "2018-07-06"),
    "Trade war, May 2019": ("2019-05-03", "2019-06-03"),
    "Trade war, Aug 2019": ("2019-08-01", "2019-08-23"),
}
SQUEEZE = ("2021-01-22", "2021-02-02")


# Each episode's daily stock returns, read once from the extract.
def episode_returns() -> pd.DataFrame | None:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    windows = [*CRISES.values(), *SCENARIOS.values(), SQUEEZE]
    years = {str(y) for first, last in windows for y in range(int(first[:4]), int(last[:4]) + 1)}
    files = sorted(p for p in DAILY.glob("*.parquet") if p.stem in years)
    if not files:
        print(f"warning: no CRSP daily extract in {DAILY}, replays are N/A", file=sys.stderr)
        return None
    cols = ["PERMNO", "SICCD", "DlyCalDt", "DlyRet", "DlyCap"]
    parts = []
    for path in files:
        chunk = pd.read_parquet(path, columns=cols)
        day = pd.to_datetime(chunk["DlyCalDt"])
        keep = np.zeros(len(chunk), dtype=bool)
        for first, last in windows:
            keep |= ((day >= first) & (day <= last)).to_numpy()
        part = chunk[keep].assign(date=day[keep])
        part["PERMNO"] = pd.to_numeric(part["PERMNO"]).astype("int64")
        part["ret"] = pd.to_numeric(part["DlyRet"], errors="coerce")
        parts.append(part[["PERMNO", "SICCD", "date", "ret", "DlyCap"]])
    out = pd.concat(parts, ignore_index=True).rename(
        columns={"PERMNO": "permno", "SICCD": "sic", "DlyCap": "cap"}
    )
    out["sic"] = pd.to_numeric(out["sic"], errors="coerce")
    CACHE.parent.mkdir(exist_ok=True)
    out.to_parquet(CACHE, index=False)
    return out


# One factor table from our WRDS extract; stops with how to get it.
def extract(name: str) -> pd.DataFrame:
    path = data.EXTRACTS / f"{name}.parquet"
    if not path.exists():
        raise SystemExit(f"No {path}: uv run run.py --data stock tables {name}")
    return pd.read_parquet(path)


# Daily FF5 + UMD factor returns from the extract.
def factor_daily() -> pd.DataFrame:
    table = extract("ff_daily")
    return table.assign(date=pd.to_datetime(table["date"])).set_index("date")[FACTORS]


# A book's factor loadings on its daily returns over the last 252 days.
def loadings(weights: pd.Series, factors: pd.DataFrame) -> pd.Series:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    wide = daily.pivot_table(index="date", columns="permno", values="total_return").tail(252)
    book = wide.reindex(columns=weights.index).fillna(0.0) @ weights
    both = pd.concat([book.rename("r"), factors], axis=1, join="inner").dropna()
    fit = sm.OLS(both["r"], sm.add_constant(both[FACTORS])).fit()
    return fit.params[FACTORS]


# Today's names through an episode, one not trading then uses its peers.
def replay(
    weights: pd.Series, panel: pd.DataFrame, first: str, last: str, info: pd.DataFrame
) -> dict:
    window = panel[(panel["date"] >= first) & (panel["date"] <= last)]
    if window.empty:
        return dict(loss=None, coverage=0.0)
    total = (1 + window.pivot_table(index="date", columns="permno", values="ret")).prod() - 1
    start = (
        window[window["date"] == window["date"].min()].drop_duplicates("permno").set_index("permno")
    )
    start["sic2"] = (start["sic"] // 100).astype("Int64")
    start["size"] = pd.qcut(start["cap"].rank(method="first"), 5, labels=False)
    peers = total.groupby(
        [start["sic2"].reindex(total.index), start["size"].reindex(total.index)]
    ).median()
    own = total.reindex(weights.index)
    covered = own.notna()
    sic2 = (info["sic"].reindex(weights.index) // 100).astype("Int64")
    # Our names are all above $300M, the fourth CRSP size quintile.
    size = pd.Series(3, index=weights.index)
    fill = [peers.get((s, z), np.nan) for s, z in zip(sic2, size)]
    filled = own.fillna(pd.Series(fill, index=weights.index)).fillna(0.0)
    return dict(
        loss=float((weights * filled).sum()),
        coverage=float(weights[covered].abs().sum() / weights.abs().sum()),
    )


# The likeliest factor move costing 10% of NAV, and the closest month.
def reverse_stress(b: pd.Series) -> dict:
    monthly = extract("ff_monthly")
    monthly = monthly.assign(month=pd.to_datetime(monthly["dateff"])).set_index("month")[FACTORS]
    sigma = monthly.loc[:"2020-12-31"].cov().to_numpy()
    bv = b.to_numpy()
    f_star = -0.10 * sigma @ bv / (bv @ sigma @ bv)
    inv = np.linalg.inv(sigma)
    gaps = [(d, float((r - f_star) @ inv @ (r - f_star))) for d, r in monthly.iterrows()]
    closest = min(gaps, key=lambda x: x[1])[0]
    return dict(
        move={f: float(v) for f, v in zip(FACTORS, f_star)}, closest_month=f"{closest:%Y-%m}"
    )


if __name__ == "__main__":
    episode_returns()
