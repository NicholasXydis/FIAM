# After the commit, in stages: the tests, the exam's designs, the brake.

import hashlib
import json
import os
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam.v4 import agreement, daily_book, data, gates, labels, ranks
from fiam.v4.construct import book, execution, optimizer, risk, settings, simulate
from fiam.v4.signals import edgar_flags, insiders

OUT = book.OUT
# The cadence and overlay horizons in sessions (PLAN §8.7).
HORIZONS, EARLY_SHARE, EARLY_T = (5, 10, 21), 0.60, 2.0
# The brake: 21-day returns' autocorrelation, Newey-West with 21 lags.
BRAKE_DAYS, BRAKE_T = 21, 2.0
# The hurdle: the bill plus 4% a year (PDF p6), and the exam's end.
PREMIUM, END = 0.04, pd.Timestamp("2020-12-31")
# Tie order: SYY-10 alone, then neutral before capped, broad before few.
SIMPLER = (4, 6, 3, 1, 7, 2, 8, 5, 14, 9, 13, 11, 10, 12, 15)
# Design 2's name cap: every ridge gave 480 names (reading 14).
CONCENTRATED = 275
# The risk ladder: designs at a fraction of the derived risk aversion.
RISK = {9: 0.5, 10: 0.25, 11: 0.5, 12: 0.25, 14: 0.5}
# The cost-light design: the derived monthly cost budget, halved.
COST = {13: 0.5}
# The jump-screened design: design 1 with reading 23 (m)'s screen.
JUMP = {15}
# The exam's halves, reported beside it and never deciding (reading 20).
PERIODS = {"2017-2018": ("2017-01", "2018-12"), "2019-2020": ("2018-12", "2020-12")}
# The styles the neutral designs hold at zero (reading 17).
TILTS = ("high_ivol", "liquidity")
# Each run: forecast, name cap, styles at 0 (design 3 is 1's book).
DESIGNS = {1: ("z", 480, ()), 2: ("z", CONCENTRATED, ()), 5: ("z", 220, ()),
           6: ("z", 480, TILTS), 7: ("z", CONCENTRATED, TILTS), 8: ("z", 220, TILTS),
           9: ("z", 480, ()), 10: ("z", 480, ()), 11: ("z", 220, ()),
           12: ("z", 220, ()), 13: ("z", 480, ()), 14: ("z", 480, TILTS),
           15: ("z", 480, ()), 4: ("z_syy", 480, ())}  # fmt: skip
# Events and returns: overlays 2015 on; returns read from 2014-12.
EVENTS_FROM, RETURNS_FROM = pd.Timestamp("2015-02-01"), pd.Timestamp("2014-12-01")
# The stages, each once per commit; the brake needs the designs' days.
STAGES, NEEDS = ("tests", "designs", "brake"), {"brake": "designs"}
# Designs at a time (FIAM_WORKERS), each worker holding one context.
WORKERS = int(os.environ.get("FIAM_WORKERS", "2"))
# The exam's commit, pinned once it has run; later stages read it.
EXAM_AT = None
# Tables beyond the gates' stamp that step 7 reads.
TABLES = ("taq_daily", "options_daily", "crsp_daily", "crsp_monthly", "dsf", "panel",
          "short_interest", "sec_13f", "sec_13f_reports", "events", "sec_insiders")  # fmt: skip


# k-session residual returns after a day, regressed as the labels are.
def residual_after(ids, day, k: int, returns: pd.DataFrame, eom) -> pd.Series:
    start = returns.index.searchsorted(pd.Timestamp(day), side="right")
    window = returns.iloc[start : start + k].reindex(columns=ids)
    if len(window) < k or window.index[-1] > END:
        return pd.Series(dtype=float)
    growth = (1 + window.fillna(0.0)).prod() - 1
    me = data.panel(ids, eom, eom, ("me",)).set_index("permno")["me"].reindex(ids)
    z = labels.exposures(ids, eom, data.eom_session([eom]).iloc[0], me)
    design = pd.get_dummies(z["sector"], dtype=float).join(z[list(labels.EXPOSURES)].fillna(0.0))
    ok = (growth.notna() & me.notna()).reindex(design.index, fill_value=False)
    keep = ok.index[ok.to_numpy()]
    return ranks.wls_residuals(growth[keep], design.loc[keep], np.sqrt(me[keep].to_numpy()))


# The early-arrival test: 60% of the 21-day mean within 5, t over 2.
def early(series: dict, sign: int) -> dict:
    means = {k: float(np.nanmean(v)) for k, v in series.items()}
    t5 = agreement.nw_t(pd.Series(series[5]))
    share = means[5] / means[21] if means[21] else np.nan
    keep = sign * means[21] > 0 and share >= EARLY_SHARE and sign * t5 > EARLY_T
    return {"means": means, "t5": t5, "share_in_5": share, "passes": bool(keep)}


# Cadence: the forecast's top-minus-bottom quintile spread at 5, 10, 21.
def cadence(f: pd.DataFrame, returns: pd.DataFrame) -> dict:
    spreads = {k: [] for k in HORIZONS}
    for eom, g in f.groupby("eom"):
        T1 = data.shift([data.eom_session([eom]).iloc[0]], 1).iloc[0]
        q = g.set_index("permno")["z"].rank(pct=True)
        for k in HORIZONS:
            r = residual_after(list(q.index), T1, k, returns, eom)
            if len(r):
                top, bottom = r.reindex(q.index[q > 0.8]), r.reindex(q.index[q <= 0.2])
                spreads[k].append(float(top.mean() - bottom.mean()))
    return early(spreads, 1) | {"weekly": early(spreads, 1)["passes"]}


# Each month's mean event residual 5, 10 and 21 sessions after acting.
def event_test(events: pd.DataFrame, sign: int, returns: pd.DataFrame) -> dict:
    rows = []
    for day, g in events.groupby("first_close"):
        eom = data.month_end_at(day)
        # The overlay acts at the close after first_close and earns after it.
        act = data.shift([day], 1).iloc[0]
        for k in HORIZONS:
            r = residual_after(list(g["permno"]), act, k, returns, eom).dropna()
            rows += [(eom, k, v) for v in r.to_numpy()]
    # Events of one month share shocks: one mean a month, as the cadence.
    frame = pd.DataFrame(rows, columns=["eom", "k", "r"])
    means = frame.groupby(["k", "eom"])["r"].mean()
    series = {k: list(means.loc[k].to_numpy()) if k in means.index.levels[0] else []
              for k in HORIZONS}  # fmt: skip
    return early(series, sign) | {"events": len(events), "months": len(series[5])}


# The overlays' events as the signals read them: flags and insider buys.
def overlay_events(first, last) -> dict:
    ev = data.table("events", ["red_flag"])
    flags = ev[ev["red_flag"].astype(bool) & ev["first_close"].between(first, last)]
    cols = ["trans_date", "trans_code", "relationship", "owner_cik", "common_stock"]
    t = data.table("sec_insiders", [*cols, "superseded_at"])
    t = t[t["trans_code"].isin(insiders.CODES) & t["common_stock"].astype(bool)]
    kinds = insiders.classes(t)
    # Officers and directors, opportunistic, as the signal (PLAN §7.3).
    role = t["relationship"].fillna("").str.contains("Director|Officer", case=False)
    t = t[role].assign(year=t["trans_date"].dt.year).merge(kinds, on=["owner_cik", "year"])
    t = t[t["routine"].eq(False) & t["trans_code"].eq("P") & t["first_close"].between(first, last)]
    # A line a 4/A replaced by its own first close never counts.
    close = data.calendar().reindex(t["first_close"]).to_numpy()
    t = t[t["superseded_at"].isna().to_numpy() | (t["superseded_at"].to_numpy() >= close)]
    keep = ["permno", "first_close"]
    return {"long": flags.drop_duplicates(keep)[keep], "short": t.drop_duplicates(keep)[keep]}


# Overlay decay tests: red flags cut longs, insider buys cut shorts.
def overlays(returns: pd.DataFrame) -> dict:
    ev = overlay_events(EVENTS_FROM, book.LAST)
    return {"red_flags": event_test(ev["long"], edgar_flags.SIGN, returns),
            "insider_buys": event_test(ev["short"], insiders.SIGN, returns)}  # fmt: skip


# An overlay's events by first close, as the engine hook reads them.
def by_day(events: pd.DataFrame) -> dict:
    return {d: set(g["permno"]) for d, g in events.groupby("first_close")}


# The brake gate: 21-day returns' autocorrelation, t >= 2 (NW 21).
def brake(daily: pd.DataFrame) -> dict:
    r = (1 + daily["ret"]).rolling(BRAKE_DAYS).apply(np.prod, raw=True) - 1
    pairs = pd.DataFrame({"now": r, "next": r.shift(-BRAKE_DAYS)}).dropna()
    fit = sm.OLS(pairs["next"], sm.add_constant(pairs["now"])).fit(
        cov_type="HAC", cov_kwds={"maxlags": BRAKE_DAYS}
    )
    return {"slope": float(fit.params["now"]), "t": float(fit.tvalues["now"]),
            "kept": bool(fit.params["now"] > 0 and fit.tvalues["now"] >= BRAKE_T)}  # fmt: skip


# IR against the bill plus 4% and Sharpe, from the engine's days.
def scores(daily: pd.DataFrame, after: str = "2017-01", last: str | None = None) -> dict:
    m = daily_book.monthly(daily)
    m = m[m.index > pd.Period(after)]
    if last is not None:
        m = m[m.index <= pd.Period(last)]
    active = m["ret"] - m["rf"] - PREMIUM / 12
    excess = m["ret"] - m["rf"]
    return {"months": len(m), "ir": float(active.mean() / active.std() * np.sqrt(12)),
            "sharpe": float(excess.mean() / excess.std() * np.sqrt(12)),
            "mean_active": float(active.mean() * 12)}  # fmt: skip


# Each half of the exam, reported only: 2019-2020 chose the model.
def by_period(daily: pd.DataFrame) -> dict:
    return {name: scores(daily, after, last) for name, (after, last) in PERIODS.items()}


# The derived settings at margin d: gross C_t - d, lever A4's speed.
def derived(s: dict, **kw):
    base = {k: v for k, v in s["settings"].items() if k not in ("gross", "norm")}
    base |= {"speed": s["a4_rate"]} | kw
    return lambda eom, x, cap: optimizer.Settings(**(base | {"gross": cap - s["margin"]}))


# One design's books planned live through the engine, scored and kept.
def design(settings_at, z: str = "z", keep_as=None, neutral=()) -> dict:
    result, plans = simulate.run(book.Context(z=z, neutral=neutral), settings_at, END,
                                 hook_class=execution.Recording)  # fmt: skip
    # Step 8 replays this run: its formations, frames, costs and book.
    if keep_as is not None:
        with (OUT / f"exam_plans_{keep_as}.pkl").open("wb") as fh:
            pickle.dump({"made": result.hook.made, "kept": result.hook.kept,
                         "hooks": result.hooks}, fh)  # fmt: skip
        result.positions.to_parquet(OUT / f"exam_positions_{keep_as}.parquet")
    found = daily_book.breaches(result)
    # A day breaking a PDF limit is recorded; that design cannot win.
    first = None if found.empty else f"{found.index[0]:%Y-%m-%d}"
    keep = ["nav", "ret", "rf", "cost", "borrow", "gross", "net", "n_long", "n_short", "turnover"]
    return scores(result.daily) | {"by_period": by_period(result.daily),
                                   "breach_days": int(len(found)), "first_breach": first,
                                   "plans": plans, "daily": result.daily[keep]}  # fmt: skip


# One design in a worker; a design finished at this commit is reused.
def design_job(k: int, s: dict, head: str) -> tuple:
    done = OUT / f"exam_design_{k}_{head[:12]}.json"
    sha = hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()
    # Reused only when it was made from these very settings.
    if done.exists() and json.loads(done.read_text()).get("settings_sha256") == sha:
        return k, json.loads(done.read_text())
    z, _, neutral = DESIGNS[k]
    out = design(settings_for(k, s), z, f"{k}_{head[:12]}", neutral) | {"settings_sha256": sha}
    out.pop("daily").to_parquet(OUT / f"exam_daily_{k}_{head[:12]}.parquet")
    # Written last and whole, so a stopped run never leaves half a design.
    part = done.with_suffix(".tmp")
    part.write_text(json.dumps(out, default=str))
    part.replace(done)
    print(f"design {k} done", flush=True)
    return k, json.loads(done.read_text())


# A design's settings: name cap, held styles, risk aversion, cost cap.
def settings_for(k: int, s: dict):
    _, cap, neutral = DESIGNS[k]
    kw = {"risk_lambda": s["settings"]["risk_lambda"] * RISK.get(k, 1.0)}
    if k in COST:
        kw["cost_budget"] = s["settings"]["cost_budget"] * COST[k]
    if k in JUMP:
        kw["jump_screen"] = True
    return derived(s, names_max=cap, neutral_styles=neutral, **kw)


# The highest IR among designs with no breach; a tie to the simpler.
def winner(results: dict) -> int | None:
    clean = [k for k in results if results[k].get("breach_days", 0) == 0]
    if not clean:
        return None
    return max(clean, key=lambda k: (round(results[k]["ir"], 12), -SIMPLER.index(k)))


# The design whose days test the brake: the winner, 3 as 1's book.
def governed(won) -> int:
    return 1 if won in (None, 3) else int(won)


# The gates' stamp plus the settings, the forecasts and step 7's tables.
def stamp(head: str, raw: bytes) -> dict:
    out = gates.stamp(head, {})
    out["settings_sha256"] = hashlib.sha256(raw).hexdigest()
    out["forecasts_sha256"] = hashlib.sha256(book.FORECASTS.read_bytes()).hexdigest()
    out["step7_cards_sha256"] = {t: data.card_sha(t) for t in TABLES}
    return out


# PLAN §8.9's reading of the winner's IR and Sharpe.
def reading(best: dict) -> str:
    if best["ir"] >= 0:
        return "freeze and run"
    if best["sharpe"] > 0:
        return "freeze anyway, IR and Sharpe side by side"
    return "stop: report to the leader before the freeze"


# python -m fiam.v4.construct.exam tests | designs | brake, in order.
if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage not in STAGES:
        raise SystemExit(f"name a stage: {' | '.join(STAGES)}")
    head = gates.commit()
    path = OUT / f"exam_{stage}_{head[:12]}.json"
    # Each stage runs once per commit, after the one before it.
    if path.exists():
        raise SystemExit(f"{path.name} exists: each stage runs once per commit")
    need = NEEDS.get(stage)
    if need and not (OUT / f"exam_{need}_{head[:12]}.json").exists():
        raise SystemExit(f"run the {need} stage first at this commit")
    raw = settings.SETTINGS.read_bytes()
    s = json.loads(raw)
    out = {"stage": stage, "stamp": stamp(head, raw)}
    if stage == "tests":
        f = book.forecasts()
        rets = risk.daily(sorted(f["permno"].unique()), RETURNS_FROM, END)
        out |= {"cadence": cadence(f, rets), "overlays": overlays(rets)}
    elif stage == "designs":
        with ProcessPoolExecutor(WORKERS) as pool:
            runs = dict(pool.map(design_job, list(DESIGNS), [s] * len(DESIGNS),
                                 [head] * len(DESIGNS)))  # fmt: skip
        runs[3] = runs[1]
        out["designs"] = runs
        out["winner"] = winner(runs)
        best = runs.get(out["winner"])
        out["reading"] = "stop: every design broke a limit" if best is None else reading(best)
    else:
        won = json.loads((OUT / f"exam_designs_{head[:12]}.json").read_text())["winner"]
        k = governed(won)
        days = pd.read_parquet(OUT / f"exam_daily_{k}_{head[:12]}.parquet")
        out["brake"] = brake(days) | {"design": k}
    path.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("designs", "stamp")},
                     indent=1, default=str))  # fmt: skip
    sys.exit(0)
