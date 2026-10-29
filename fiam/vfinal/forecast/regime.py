# Regime rho: the past ICs in the current market-state cell.

import io
import re
import zipfile

import numpy as np
import pandas as pd
from scipy import stats

from fiam.vfinal import config

N0 = 12.0
MIN_PAST = 36


# Ken French daily five factors from the zip, as decimals.
def ff_daily() -> pd.DataFrame:
    zf = zipfile.ZipFile(config.FF5_DAILY)
    txt = zf.read(zf.namelist()[0]).decode("utf8", "ignore")
    rows = [ln for ln in txt.splitlines() if re.match(r"^\s*\d{8},", ln)]
    df = pd.read_csv(io.StringIO("\n".join(rows)), header=None,
                     names=["ymd", "MktRF", "SMB", "HML", "RMW", "CMA", "RF"])  # fmt: skip
    df["date"] = pd.to_datetime(df["ymd"].astype(str).str.strip(), format="%Y%m%d")
    for c in ["MktRF", "SMB", "HML", "RMW", "CMA", "RF"]:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    return df.set_index("date").sort_index()


# Trailing-only market state at each formation eom (corr_share, hml12).
def market_state(eoms: list[pd.Timestamp]) -> pd.DataFrame:
    d = pd.read_parquet(config.DAILY, columns=["permno", "date", "total_return"])
    d = d.rename(columns={"total_return": "ret"})
    # Bad ticks in the vendor file.
    d = d[d["ret"].between(-0.9, 2.0)]
    d["date"] = pd.to_datetime(d["date"])
    d = d[(d["date"] >= "2014-06-01") & (d["date"] <= config.CUT)].dropna(subset=["ret"])
    wide = d.pivot_table(index="date", columns="permno", values="ret", aggfunc="last")
    sessions = wide.index
    ff = ff_daily()
    out = {}
    # The equal-weighted market's daily return (panel universe).
    ew = wide.mean(axis=1)
    for eom in eoms:
        pos = sessions.searchsorted(pd.Timestamp(eom), side="right") - 1
        if pos < 260:
            continue
        mkt = ew.iloc[: pos + 1]
        # Correlation share: EW-index variance over mean stock variance (63d).
        single = max(wide.iloc[pos - 62 : pos + 1].var().mean(), 1e-12)
        row = {"corr_share": float(mkt.iloc[-63:].var() / single), "last_session": sessions[pos]}
        fsub = ff.loc[: pd.Timestamp(eom)]
        for c in ("HML",):
            row[f"{c.lower()}12"] = float((1 + fsub[c].iloc[-252:]).prod() - 1)
        row["ff_last"] = fsub.index[-1]
        out[pd.Timestamp(eom)] = row
    return pd.DataFrame(out).T.sort_index()


# Monthly rank IC of the score on the $3bn pool vs demeaned next return.
def monthly_ic(score: pd.DataFrame) -> pd.Series:
    p = pd.read_parquet(
        config.PANEL, columns=["permno", "eom", "ret_exc_lead1m", "me", "me_company"],
        filters=[("eom", ">=", pd.Timestamp("2016-12-31").date()),
                 ("eom", "<=", pd.Timestamp(config.LAST_EOM).date())])  # fmt: skip
    p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
    p["cap"] = p[["me", "me_company"]].min(axis=1, skipna=False)
    p["r"] = p["ret_exc_lead1m"] - p.groupby("eom")["ret_exc_lead1m"].transform("mean")
    f = score[["date", "permno", "MaInf"]].copy()
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    d = f.merge(p[["permno", "eom", "r", "cap"]], on=["permno", "eom"],
                how="inner").dropna(subset=["r"])  # fmt: skip
    d = d[d["cap"] >= 3000]
    return pd.Series({e: stats.spearmanr(g["MaInf"], g["r"]).statistic
                      for e, g in d.groupby("eom") if len(g) > 50}).sort_index()  # fmt: skip


# Rho per formation from past formations whose label month has closed.
def rho_series(ic: pd.Series, state: pd.DataFrame) -> pd.DataFrame:
    j = ic.rename("ic").to_frame().join(state[["corr_share", "hml12"]], how="inner")
    j["corr_share"] = j["corr_share"].astype(float)
    j["hml12"] = j["hml12"].astype(float)
    months = list(j.index)
    rows = []
    for i, t in enumerate(months):
        # Past formations whose label month has closed by formation t.
        past = j.iloc[: max(i - 1, 0)]
        if len(past) < MIN_PAST:
            rows.append({"eom": t, "rho": 1.0, "ic_cell": np.nan, "ic_all": np.nan,
                         "n_cell": 0, "cell": "warmup"})  # fmt: skip
            continue
        cuts = np.quantile(past["corr_share"].to_numpy(), [1 / 3, 2 / 3])

        # State cell: corr_share tercile by past cuts, sign of trailing HML.
        def cell(row: pd.Series) -> str:
            terc = int(np.searchsorted(cuts, row["corr_share"]))
            return f"c{terc}h{int(row['hml12'] > 0)}"

        c_now = cell(j.loc[t])
        in_cell = past[[cell(r) == c_now for _, r in past.iterrows()]]["ic"]
        ic_all = float(past["ic"].mean())
        ic_cell_raw = float(in_cell.mean()) if len(in_cell) else ic_all
        ic_cell = (len(in_cell) * ic_cell_raw + N0 * ic_all) / (len(in_cell) + N0)
        rho = float(np.clip(ic_cell / ic_all, 0.0, 1.5)) if ic_all > 0.005 else 1.0
        rows.append({"eom": t, "rho": rho, "ic_cell": ic_cell, "ic_all": ic_all,
                     "n_cell": int(len(in_cell)), "cell": c_now})  # fmt: skip
    return pd.DataFrame(rows).set_index("eom").sort_index()
