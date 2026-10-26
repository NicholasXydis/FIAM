# Blind loaders: no return or label after blind_until is ever read.

from pathlib import Path

import exchange_calendars as xc
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PANEL = ROOT / "data" / "finals_2026" / "chars_final_with_names.parquet"
DAILY = ROOT / "data" / "fiam_v1" / "daily_market.parquet"
TB3MS = ROOT / "data" / "benchmarks" / "TB3MS.csv"
# A missing quote is charged this half-spread, never zero.
SPREAD_MISSING = 0.005
# No quote is cheaper than this half-spread.
SPREAD_FLOOR = 0.0001


# The cutoff as a timestamp; the only door is blind_until.
def _cut(blind_until) -> pd.Timestamp:
    return pd.Timestamp(blind_until)


# Panel rows up to the cutoff; labels ending later are blanked.
def panel(columns, blind_until="2020-12-31", path: Path = PANEL) -> pd.DataFrame:
    cut = _cut(blind_until)
    cols = sorted({"permno", "eom", *columns})
    p = pd.read_parquet(path, columns=cols, filters=[("eom", "<=", cut)])
    p["eom"] = pd.to_datetime(p["eom"])
    # Row eom's label is next month's return, known after the cut.
    if "ret_exc_lead1m" in p:
        late = (p["eom"] + pd.offsets.MonthEnd(1)) > cut
        p.loc[late, "ret_exc_lead1m"] = np.nan
    return p


# CRSP daily rows from start to the cutoff.
def daily(start, blind_until="2020-12-31", path: Path | None = None) -> pd.DataFrame:
    path = DAILY if path is None else path
    cut = _cut(blind_until)
    cols = ["permno", "date", "close", "total_return", "volume", "bid", "ask"]
    filt = [("date", ">=", pd.Timestamp(start)), ("date", "<=", cut)]
    d = pd.read_parquet(path, columns=cols, filters=filt)
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    return d.drop_duplicates(["permno", "date"])


# The daily cash rate per session from TB3MS (PDF §9.2 basis).
def cash_rate(sessions: pd.DatetimeIndex, path: Path = TB3MS) -> pd.Series:
    t = pd.read_csv(path, parse_dates=["observation_date"])
    month = t.set_index(t["observation_date"].dt.to_period("M"))["TB3MS"]
    return pd.Series(sessions.to_period("M").map(month).to_numpy() / 25200, index=sessions)


# Session x permno frames the simulator reads, from CRSP daily.
def market(d: pd.DataFrame, permnos, adv_window: int = 126, vol_window: int = 63) -> dict:
    d = d[d["permno"].isin(set(permnos))]
    sessions = pd.DatetimeIndex(sorted(d["date"].unique()))
    sessions = sessions.intersection(nyse_sessions(sessions[0], sessions[-1]))
    cols = pd.Index(sorted(set(permnos)), name="permno")

    def grid(values: pd.Series) -> pd.DataFrame:
        frame = d.assign(v=values).pivot(index="date", columns="permno", values="v")
        return frame.reindex(index=sessions, columns=cols)

    ret = grid(d["total_return"])
    dollars = grid(d["close"].abs() * d["volume"])
    half = grid((d["ask"] - d["bid"]) / (d["ask"] + d["bid"]))
    half = half.where((half > 0) & (half < 0.5))
    lo = adv_window // 2
    adv = dollars.rolling(adv_window, min_periods=lo).mean()
    # Bad price-return ticks (reverse splits, vendor errors) must not become
    # a 100%-daily-vol cost input. Beta already clips at the same bound.
    sigma = ret.clip(-0.5, 0.5).rolling(vol_window, min_periods=vol_window // 3).std()
    spread = half.rolling(21, min_periods=5).median().clip(lower=SPREAD_FLOOR)
    # Raw (unadjusted) close for per-share fees; carried over short gaps.
    price = grid(d["close"].abs().where(d["close"].abs() > 0)).ffill(limit=5)
    return dict(
        returns=ret,
        price=price,
        adv=adv,
        sigma=sigma,
        half_spread=spread.fillna(SPREAD_MISSING),
        sessions=sessions,
    )


# NYSE sessions between two dates, midnight-stamped.
def nyse_sessions(start, end) -> pd.DatetimeIndex:
    cal = xc.get_calendar("XNYS", start=pd.Timestamp(start), end=pd.Timestamp(end))
    return pd.DatetimeIndex(cal.sessions).tz_localize(None).normalize()


# The last session on or before each eom.
def eom_sessions(eoms, sessions: pd.DatetimeIndex) -> pd.Series:
    when = pd.DatetimeIndex(pd.to_datetime(eoms))
    pos = sessions.searchsorted(when, side="right") - 1
    return pd.Series(sessions[pos.clip(0)], index=range(len(when))).where(pos >= 0)


def market_returns(sessions, path=ROOT / "data" / "benchmarks" / "SP500.csv"):
    """Align to exchange sessions before differences; holiday rows are not observations."""
    raw = pd.read_csv(path, parse_dates=["observation_date"], na_values=["."])
    prices = raw.set_index("observation_date")["SP500"]
    return prices.reindex(pd.DatetimeIndex(sessions)).pct_change(fill_method=None)
