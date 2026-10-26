# The 2026 inputs, each beside its 2019-06 check (protocol Medium 5).

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4 import data, universe

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "v4" / "engine"
# The month each 2026 input is checked against its CRSP original.
CHECK = pd.Timestamp("2019-06-30")
# The agreement bars written before the checks ran (protocol, step 5).
BARS = dict(shares=0.01, adv=0.02, market=0.99, sp500=0.999)
# ADV's window in sessions, as the panel's `dolvol_126d`.
ADV_DAYS = 126
# The panel's first month; before it ADV is CRSP's own (Medium 5).
PANEL_FROM = pd.Timestamp("2015-01-31")


# The month end whose panel row is public by the day's close.
def last_eom(day) -> pd.Timestamp:
    return data.month_end_at(day)


# Shares outstanding: CRSP's through 2025, then panel cap over price.
def shares(permnos, day) -> pd.Series:
    if pd.Timestamp(day) <= data.CRSP_END:
        return crsp_shares(permnos, day)
    return panel_shares(permnos, day)


# CRSP's shares on its last row on or before the day.
def crsp_shares(permnos, day) -> pd.Series:
    day = pd.Timestamp(day)
    where = {"permno": set(int(p) for p in permnos), "date": (day - pd.Timedelta(days=10), day)}
    rows = data.table("crsp_daily", ["shrout_k", "delflg"], where=where).sort_values("date")
    # A delisting row is no trade, so it never sets the count.
    rows = rows[rows["delflg"] != "Y"]
    return rows.groupby("permno")["shrout_k"].last().mul(1000.0).reindex(sorted(where["permno"]))


# Shares on each session: CRSP's through 2025, then the panel's.
def shares_on(sessions) -> pd.DataFrame:
    days = pd.DatetimeIndex(sorted(set(pd.to_datetime(pd.Series(sessions)))))
    out = []
    early = days[days <= data.CRSP_END]
    if len(early):
        c = data.table("crsp_daily", ["shrout_k"], where={"date": set(early)})
        out.append(pd.DataFrame({"permno": c["permno"], "session": c["date"],
                                 "shares": c["shrout_k"] * 1000.0,
                                 "shares_close": c["first_close"]}))  # fmt: skip
    # After 2025 the last public month end's cap over price (Medium 5).
    for day in days[days > data.CRSP_END]:
        eom = last_eom(day)
        p = data.table("panel", ["me", "prc"], where={"eom": (eom, eom)})
        out.append(pd.DataFrame({"permno": p["permno"], "session": day,
                                 "shares": p["me"] * 1e6 / p["prc"].abs(),
                                 "shares_close": p["first_close"]}))  # fmt: skip
    if not out:
        empty = pd.Series(dtype="datetime64[ns]")
        return pd.DataFrame({"permno": pd.Series(dtype="int64"), "session": empty,
                             "shares": pd.Series(dtype=float), "shares_close": empty})  # fmt: skip
    return pd.concat(out, ignore_index=True)


# Panel cap ($m) over |price| at the last month end, in shares.
def panel_shares(permnos, day) -> pd.Series:
    eom = last_eom(day)
    where = {"permno": set(int(p) for p in permnos), "eom": (eom, eom)}
    rows = data.table("panel", ["me", "prc"], where=where).set_index("permno")
    data.assert_public_by(rows["first_close"], day, "shares panel rows")
    return (rows["me"] * 1e6 / rows["prc"].abs()).reindex(sorted(where["permno"]))


# Average daily dollar volume: the panel's, CRSP's before 2015.
def adv(permnos, day) -> pd.Series:
    if last_eom(day) < PANEL_FROM:
        return crsp_adv(permnos, day)
    eom = last_eom(day)
    where = {"permno": set(int(p) for p in permnos), "eom": (eom, eom)}
    rows = data.table("panel", ["dolvol_126d"], where=where).set_index("permno")
    data.assert_public_by(rows["first_close"], day, "ADV panel rows")
    return rows["dolvol_126d"].reindex(sorted(where["permno"]))


# CRSP's mean |price| x volume over the 126 sessions to the day.
def crsp_adv(permnos, day) -> pd.Series:
    days = data.sessions(pd.Timestamp(day) - pd.Timedelta(days=200), day)[-ADV_DAYS:]
    where = {"permno": set(int(p) for p in permnos), "date": (days[0], days[-1])}
    rows = data.table("crsp_daily", ["prc", "vol", "delflg"], where=where)
    rows = rows[rows["delflg"] != "Y"]
    dollars = rows["prc"].abs() * rows["vol"]
    return dollars.groupby(rows["permno"]).mean().reindex(sorted(where["permno"]))


# The market's daily return: CRSP's through 2025, then the dsf's.
def market(days) -> pd.Series:
    return data.market_daily(days)


# The S&P 500's daily return: CRSP `sprtrn`, then FRED's SP500.
def sp500(days) -> pd.Series:
    days = pd.DatetimeIndex(days)
    crsp = data.table("crsp_market_daily", ["sprtrn"]).set_index("date")["sprtrn"]
    fred = data.table("sp500", ["ret"]).set_index("date")["ret"]
    out = pd.Series(crsp.reindex(days).to_numpy(), index=days)
    late = days[days > data.CRSP_END]
    out.loc[late] = fred.reindex(late).to_numpy()
    return out


# GICS-2, else the last CRSP SICCD as its own two-digit group.
def sector(permnos, eom) -> pd.Series:
    eom = last_eom(eom)
    ids = set(int(p) for p in permnos)
    gics = data.table("panel", ["gics"], where={"permno": ids, "eom": (eom, eom)})
    gics = gics.set_index("permno")["gics"].astype("string").str[:2]
    # After 2025 the last CRSP code is carried forward.
    upto = min(eom, data.CRSP_END)
    sic = data.table("crsp_monthly", ["siccd"], where={"permno": ids, "date": (None, upto)})
    sic = sic.dropna(subset=["siccd"]).sort_values("date").groupby("permno")["siccd"].last()
    two = sic.astype(int).astype(str).str.zfill(4).str[:2]
    out = ("G" + gics).reindex(sorted(ids))
    return out.fillna(("S" + two).reindex(sorted(ids))).fillna("XX")


# Every 2026 input against its CRSP original on 2019-06, asserted.
def check() -> dict:
    names = universe.members(CHECK)
    names = names.loc[names["new_long"], "permno"].tolist()
    t = data.eom_session([CHECK]).iloc[0]
    days = data.sessions(CHECK.replace(day=1), CHECK)
    ratio_shares = (crsp_shares(names, t) / panel_shares(names, CHECK)).dropna()
    ratio_adv = (adv(names, CHECK) / crsp_adv(names, t)).dropna()
    fred = data.table("sp500", ["ret"]).set_index("date")["ret"].reindex(days)
    crsp_sp = data.table("crsp_market_daily", ["sprtrn"]).set_index("date")["sprtrn"]
    vw = data.market_daily(days)
    sectors = sector(names, CHECK)
    out = dict(
        month=f"{CHECK:%Y-%m}",
        names=len(names),
        shares_median_ratio=float(ratio_shares.median()),
        shares_compared=int(len(ratio_shares)),
        adv_median_ratio=float(ratio_adv.median()),
        adv_compared=int(len(ratio_adv)),
        market_corr=float(np.corrcoef(vw, data.dsf_market(days).reindex(days))[0, 1]),
        sp500_corr=float(np.corrcoef(crsp_sp.reindex(days), fred)[0, 1]),
        sector_gics_share=float(sectors.str.startswith("G").mean()),
        sector_covered=float((sectors != "XX").mean()),
        bars=BARS,
    )
    out["passes"] = bool(
        abs(out["shares_median_ratio"] - 1) <= BARS["shares"]
        and abs(out["adv_median_ratio"] - 1) <= BARS["adv"]
        and out["market_corr"] > BARS["market"]
        and out["sp500_corr"] > BARS["sp500"]
        and out["sector_covered"] == 1.0
    )
    return out


# The checks written to out/v4/engine/inputs_check.json.
def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    out = check()
    (OUT / "inputs_check.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    sys.exit(0 if main()["passes"] else 1)
