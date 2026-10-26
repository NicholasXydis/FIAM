# Blind inputs for the forecaster: organisers' panel and daily file only.

from pathlib import Path

import exchange_calendars as xc
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

ROOT = Path(__file__).resolve().parents[3]
ORG = ROOT / "data" / "finals_2026"
PANEL = ORG / "chars_final_with_names.parquet"
DSF = ORG / "dsf_mini_from_2014.csv"
CHARS = ORG / "factor_char_list.csv"
TB3MS = ROOT / "data" / "benchmarks" / "TB3MS.csv"
CACHE = ROOT / "fiam" / "v4b" / "cache"
# No label may end after this day before the freeze (R§1.3).
BLIND = pd.Timestamp("2020-12-31")
# Columns the forecaster may read besides the 147 (never as inputs).
AUX = ["permno", "eom", "me", "me_company", "prc", "dolvol_126d", "gics", "ret_exc_lead1m"]


# The 147 characteristic names, in the organisers' order.
def characteristics() -> list[str]:
    return pd.read_csv(CHARS)["variable"].tolist()


# NYSE sessions, midnight-stamped, between two dates.
def sessions(start, end) -> pd.DatetimeIndex:
    cal = xc.get_calendar("XNYS", start=pd.Timestamp(start), end=pd.Timestamp(end))
    return pd.DatetimeIndex(cal.sessions).tz_localize(None).normalize()


# Panel rows to the cutoff; the monthly label is blanked if it ends later.
def panel(cut: pd.Timestamp = BLIND) -> pd.DataFrame:
    cols = list(dict.fromkeys(AUX + characteristics()))
    p = pd.read_parquet(PANEL, columns=cols, filters=[("eom", "<=", cut)])
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    late = (p["eom"] + pd.offsets.MonthEnd(1)) > cut
    p.loc[late, "ret_exc_lead1m"] = np.nan
    return p.sort_values(["eom", "permno"], ignore_index=True)


# Daily returns to the cutoff, cached as parquet after the first read.
def daily(cut: pd.Timestamp = BLIND) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"dsf_to_{cut:%Y%m%d}.parquet"
    if not path.exists():
        types = {
            "permno": pa.int64(),
            "date": pa.int64(),
            "prc": pa.float64(),
            "daily_return": pa.float64(),
        }
        t = pacsv.read_csv(DSF, convert_options=pacsv.ConvertOptions(column_types=types))
        d = t.to_pandas()
        d = d[d["date"] <= int(f"{cut:%Y%m%d}")]
        d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d")
        d[["permno", "date", "daily_return"]].to_parquet(path, index=False)
    d = pd.read_parquet(path)
    if d["date"].max() > cut:
        raise AssertionError("daily rows past the blind cutoff")
    return d


# Adds each month's missing dividend back, spread over its sessions (H5).
def with_dividends(d: pd.DataFrame, cut: pd.Timestamp = BLIND, cap: float = 0.05):
    # Outcome-only: the panel's total return is a label input, never a feature.
    p = pd.read_parquet(PANEL, columns=["permno", "eom", "ret"], filters=[("eom", "<=", cut)])
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    d = d.assign(eom=d["date"] + pd.offsets.MonthEnd(0))
    logs = np.log1p(d["daily_return"].clip(lower=-0.999999)).groupby([d["permno"], d["eom"]])
    month = pd.DataFrame({"comp": np.expm1(logs.sum()), "n": logs.size()})
    month = month.reset_index().merge(p, on=["permno", "eom"], how="left")
    month["delta"] = ((month["ret"] - month["comp"]).clip(0, cap) / month["n"]).fillna(0.0)
    d = d.merge(month[["permno", "eom", "delta"]], on=["permno", "eom"], how="left")
    d["daily_return"] = d["daily_return"] + d["delta"].fillna(0.0)
    return d.drop(columns=["eom", "delta"])


# Daily cash rate per session from TB3MS, percent a year / 252.
def cash_rate(days: pd.DatetimeIndex) -> pd.Series:
    t = pd.read_csv(TB3MS, parse_dates=["observation_date"])
    month = t.set_index(t["observation_date"].dt.to_period("M"))["TB3MS"]
    return pd.Series(days.to_period("M").map(month).to_numpy() / 25200, index=days)


# Each eom's formation session: the first session after the eom.
def formation_days(eoms, days: pd.DatetimeIndex) -> pd.Series:
    when = pd.DatetimeIndex(pd.to_datetime(eoms))
    pos = days.searchsorted(when, side="right")
    ok = pos < len(days)
    out = pd.Series(pd.NaT, index=range(len(when)), dtype="datetime64[ns]")
    out[ok] = days[pos[ok]]
    return out


# Excess return earned from close s0 over the next H sessions, per eom.
def daily_labels(p: pd.DataFrame, d: pd.DataFrame, horizons, cut: pd.Timestamp = BLIND):
    days = sessions("2014-01-01", cut)
    wide = d.pivot(index="date", columns="permno", values="daily_return").reindex(days)
    rf = cash_rate(days).to_numpy()
    excess = wide.sub(rf, axis=0)
    growth = np.log1p(excess.clip(lower=-0.999999))
    cum = growth.fillna(0.0).cumsum()
    seen = excess.notna().cumsum()
    eoms = pd.DatetimeIndex(sorted(p["eom"].unique()))
    s0 = formation_days(eoms, days)
    out = []
    for eom, start in zip(eoms, s0):
        if pd.isna(start):
            continue
        k0 = days.get_loc(start)
        rows = {"eom": eom, "s0": start}
        names = p.loc[p["eom"] == eom, "permno"].to_numpy()
        names = names[np.isin(names, wide.columns)]
        block = pd.DataFrame({"eom": eom, "permno": names})
        for h in horizons:
            k1 = k0 + h
            if k1 >= len(days) or days[k1] > cut:
                block[f"y{h}"] = np.nan
                continue
            gain = cum.iloc[k1][names].to_numpy() - cum.iloc[k0][names].to_numpy()
            obs = seen.iloc[k1][names].to_numpy() - seen.iloc[k0][names].to_numpy()
            # A name with no daily row in the window has no label.
            block[f"y{h}"] = np.where(obs > 0, np.expm1(gain), np.nan)
            block[f"end{h}"] = days[k1]
        block["s0"] = rows["s0"]
        out.append(block)
    return pd.concat(out, ignore_index=True)


# Tradable flags per row: long-eligible, short-eligible (R§3, R§2).
def tradable(
    p: pd.DataFrame,
    adv_min_usd: float = 2e6,
    price_min: float = 5.0,
    short_floor_musd: float = 500.0,
) -> pd.DataFrame:
    cap = p[["me", "me_company"]].min(axis=1, skipna=False)
    long_ok = (p["prc"].abs() >= price_min) & (p["dolvol_126d"] >= adv_min_usd)
    return pd.DataFrame(
        {"long_ok": long_ok, "short_ok": long_ok & (cap >= short_floor_musd)}, index=p.index
    )
