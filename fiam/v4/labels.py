# The t+1 labels and their residual regression (protocol step 6).

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4 import betas, clock, data, inputs, ranks, universe

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "v4" / "labels"
# Gate formations: the 2020-11 label ends 2021-01-04, so it is refused.
FIRST_FORMATION = pd.Timestamp("2015-01-31")
# The month horizons: 1 for the gates and the grid, 3 for lever C2.
HORIZONS = (1, 3)
# The residual target's exposures beside the GICS-2 dummies (§8.2).
EXPOSURES = ("size", "be_me", "welch", "gp_at", "at_gr1", "ret_12_1")
# The panel columns those exposures and the exit residual read.
PANEL_COLUMNS = ["me", "ret", "be_me", "gp_at", "at_gr1", "ret_12_1"]
# The regression samples: the trading universe, or every panel stock.
SAMPLES = ("universe", "panel")


# Formation month ends from 2015-01 whose k-month label ends by 2020.
def formations(months: int) -> pd.DatetimeIndex:
    cal, keep = data.calendar(), []
    for eom in data.month_ends(FIRST_FORMATION, clock.LAST_LABEL_DAY):
        try:
            clock.label_window(eom, months, cal)
        except clock.SealedWindow:
            break
        keep.append(eom)
    return pd.DatetimeIndex(keep)


# Each formation's window: close of T+1 to close after month t+k ends.
def windows(eoms, months: int) -> pd.DataFrame:
    cal, rows = data.calendar(), []
    for eom in pd.DatetimeIndex(eoms):
        start, end = clock.label_window(eom, months, cal)
        rows.append({"eom": eom, "T": data.eom_session([eom]).iloc[0], "start": start, "end": end})
    return pd.DataFrame(rows)


# One exit's return: CRSP's, else the panel residual, else unknown.
def exit_return(row: dict, panel: pd.DataFrame, crsp: pd.DataFrame) -> tuple:
    if row["category"] == "data_gap":
        return 0.0, row["first_close"]
    if pd.notna(row["delret"]):
        return float(row["delret"]), row["first_close"]
    if row["source"] != "crsp_delistings":
        return np.nan, row["first_close"]
    # The panel's exit-month return over CRSP's, so dividends count once.
    eom = (row["exit_date"] + pd.offsets.MonthEnd(0)).normalize()
    key = (int(row["permno"]), eom)
    if key not in panel.index or pd.isna(panel.at[key, "ret"]):
        return np.nan, row["first_close"]
    stock = crsp[crsp["permno"] == key[0]]
    month = stock[stock["date"].dt.to_period("M") == eom.to_period("M")]
    if not len(month) or month["ret"].isna().any():
        return np.nan, row["first_close"]
    value = float((1 + panel.at[key, "ret"]) / np.prod(1 + month["ret"]) - 1)
    return value, max(row["first_close"], panel.at[key, "first_close"])


# Raw k-month labels of every panel stock at each formation, counted.
def raw(eoms, months: int, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    win = windows(eoms, months)
    last = win["end"].max() + pd.offsets.MonthEnd(0)
    p = data.table("panel", PANEL_COLUMNS, where={"eom": (win["eom"].min(), last)})
    p = p.set_index(["permno", "eom"]).sort_index()
    stocks = sorted(set(p.index.get_level_values("permno")))
    days = data.sessions(win["start"].min(), win["end"].max())
    crsp = data.crsp_daily(stocks, days[0] - pd.offsets.MonthBegin(1), days[-1])
    ret = data.matrix(crsp, "ret", days, stocks)
    R, has = ret.to_numpy(), ret.notna().to_numpy()
    col = {s: j for j, s in enumerate(stocks)}
    # Each delisting return sits on the session after its last trade.
    ex = data.exits(stocks).copy()
    ex["session"] = data.shift(ex["exit_date"], 1).to_numpy()
    log["exits_off_the_calendar"] = int(ex["session"].isna().sum())
    ex = ex.dropna(subset=["session"]).sort_values(["permno", "exit_date"])
    counts = dict.fromkeys(
        ["gone_before_window", "exit_return_unknown", "no_row_on_last_session_no_exit"], 0
    )
    counts["windows_with_two_exits"] = 0
    out = []
    for w in win.itertuples(index=False):
        a, b = days.searchsorted(w.start, side="right"), days.searchsorted(w.end, side="right")
        here = p.xs(w.eom, level="eom")
        idx = [col[s] for s in here.index]
        inside_has = has[a:b][:, idx]
        frame = pd.DataFrame(
            {
                "permno": here.index.to_numpy(),
                "growth": np.prod(1 + np.nan_to_num(R[a:b][:, idx]), axis=0),
                "sessions": inside_has.sum(axis=0),
                "window_sessions": b - a,
            }
        )
        # One exit per stock and window, on its delisting session.
        inside = ex[(ex["session"] > w.start) & (ex["session"] <= w.end)]
        inside = inside[inside["permno"].isin(set(here.index))]
        counts["windows_with_two_exits"] += int(inside.duplicated("permno").sum())
        booked = {}
        for r in inside.drop_duplicates("permno").to_dict("records"):
            booked[int(r["permno"])] = exit_return(r, p, crsp)
        frame["exit_booked"] = frame["permno"].isin(set(booked))
        frame["exit_ret"] = frame["permno"].map(lambda s: booked.get(s, (np.nan, None))[0])
        known = frame["permno"].map(lambda s: booked.get(s, (None, pd.NaT))[1])
        frame["label"] = frame["growth"] * (1 + frame["exit_ret"].fillna(0.0)) - 1
        # No return in the window and no exit: the stock had already gone.
        gone = (frame["sessions"] == 0) & ~frame["exit_booked"]
        unknown = frame["exit_booked"] & frame["exit_ret"].isna()
        frame.loc[gone | unknown, "label"] = np.nan
        stops = ~inside_has[-1] & ~frame["exit_booked"].to_numpy() & ~gone.to_numpy()
        counts["gone_before_window"] += int(gone.sum())
        counts["exit_return_unknown"] += int(unknown.sum())
        counts["no_row_on_last_session_no_exit"] += int(stops.sum())
        # A label is public once its window and its exit return are.
        avail = pd.to_datetime(known).fillna(w.end)
        frame["available"] = avail.where(avail >= w.end, w.end)
        frame = frame.assign(eom=w.eom, T=w.T, start=w.start, end=w.end, horizon=months)
        out.append(frame.drop(columns=["growth"]))
    labels = pd.concat(out, ignore_index=True)
    # A label public only after the seal is refused, never truncated.
    late = labels["available"] > clock.LAST_LABEL_DAY
    log |= counts | {"refused_public_after_seal": int(late.sum())}
    labels = labels[~late].reset_index(drop=True)
    keys = pd.MultiIndex.from_frame(labels[["permno", "eom"]])
    labels["me"] = p["me"].reindex(keys).to_numpy()
    return labels


# Exposures at one formation: root-cap z-scores, missing as 0 later.
def exposures(permnos, eom, T, me: pd.Series) -> pd.DataFrame:
    ids = sorted(set(int(s) for s in permnos))
    p = data.panel(ids, eom, eom, PANEL_COLUMNS).set_index("permno").reindex(ids)
    data.assert_public_by(p["first_close"].dropna(), T, "exposure panel rows")
    raw_x = pd.DataFrame(index=ids)
    raw_x["size"] = np.log(p["me"].where(p["me"] > 0))
    for c in ("be_me", "gp_at", "at_gr1", "ret_12_1"):
        raw_x[c] = p[c]
    raw_x["welch"] = betas.at(T, ids).set_index("permno")["welch"].reindex(ids)
    w = np.sqrt(me.reindex(ids))
    z = pd.DataFrame({c: ranks.zscore(raw_x[c], w) for c in EXPOSURES}, index=ids)
    z["sector"] = inputs.sector(ids, eom).reindex(ids).to_numpy()
    z["missing"] = raw_x[list(EXPOSURES)].isna().sum(axis=1)
    return z


# The residual label: WLS on GICS-2 dummies and the six z-scores (§8.2).
def residual(labels: pd.DataFrame, sample: str = "universe", extra=None) -> pd.DataFrame:
    if sample not in SAMPLES:
        raise ValueError(f"sample in {SAMPLES}")
    out = []
    for eom, g in labels.dropna(subset=["label", "me"]).groupby("eom"):
        T = g["T"].iloc[0]
        # The gates' trading universe at t, or every panel stock (lever D1).
        if sample == "universe":
            m = universe.members(eom)
            g = g[g["permno"].isin(set(m.loc[m["new_long"], "permno"]))]
        # Rows by stock, so the design and the label align by name.
        g = g.set_index("permno").sort_index()
        z = exposures(g.index, eom, T, g["me"]).reindex(g.index)
        design = pd.get_dummies(z["sector"], prefix="sec", dtype=float)
        design = design.join(z[list(EXPOSURES)].fillna(0.0))
        # A control such as the covered dummy joins this regression only.
        if extra is not None:
            design = design.join(extra.xs(eom, level="eom").reindex(g.index).fillna(0.0))
        resid = ranks.wls_residuals(g["label"], design, np.sqrt(g["me"].to_numpy()))
        out.append(
            pd.DataFrame(
                {
                    "permno": g.index.to_numpy(),
                    "eom": eom,
                    "resid": resid.to_numpy(),
                    "resid_rank": ranks.unit_rank(resid).to_numpy(),
                    "exposures_missing": z["missing"].to_numpy(),
                    "n": len(g),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


# Both horizons and both samples in one table, with the build's counts.
def build() -> tuple[pd.DataFrame, dict]:
    log, frames = {}, []
    for months in HORIZONS:
        part: dict = {}
        lab = raw(formations(months), months, part)
        for sample in SAMPLES:
            res = residual(lab, sample)
            res = res.rename(columns=lambda c: c if c in ("permno", "eom") else f"{c}_{sample}")
            lab = lab.merge(res, on=["permno", "eom"], how="left")
        # A residual uses the month's labels: public once the last one is.
        lab["month_available"] = lab.groupby("eom")["available"].transform("max")
        part |= {"rows": len(lab), "formations": int(lab["eom"].nunique())}
        part["labels"] = int(lab["label"].notna().sum())
        part["universe_labels"] = int(lab["resid_universe"].notna().sum())
        log[f"h{months}"] = part
        frames.append(lab)
    return pd.concat(frames, ignore_index=True), log


# Builds the labels and prints their counts: python -m fiam.v4.labels
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    table, report = build()
    (OUT / "labels_build.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, default=str), file=sys.stderr)
