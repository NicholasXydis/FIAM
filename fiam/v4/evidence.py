# Step 9 pre-freeze evidence: trial ledger, deflated Sharpe, leak test

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from fiam import book as P

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "out" / "v4"
GATES, FORECAST, CONSTRUCT, DESK = V4 / "gates", V4 / "forecast", V4 / "construct", V4 / "desk"
OUT = V4 / "evidence"
V2_TRIALS = ROOT / "out" / "v2" / "trials.csv"
# The six gates' run (protocol "Step 6 rules") and the two late gates.
GATES_AT = "fa169bf9301a"
SIX = ("short_interest", "red_flags", "insiders", "lazy_prices", "best_ideas", "customer_momentum")
LATE = ("options_flow", "earnings_premium")
# The exam's runs (design 3 is 1's book) and the desk's arms.
DESIGNS = (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
SEEDS = range(20261800, 20261900)
ARMS = ("A0", "A1", "A2", *(f"P1_{s}" for s in SEEDS))
# The derived settings' grids (PLAN §8.3, §8.4, §8.8) as step 7 runs.
GRIDS = {"ridge": (1, 3, 10, 30, 100, 300), "style_cap": (0.05, 0.1, 0.2, 0.3, 0.5),
         "margin": (0.01, 0.03, 0.05, 0.08), "sector_band": (0.01, 0.02, 0.03)}  # fmt: skip
# The v2 ledger's columns, then ours: kind, status, days of rows.
COLUMNS = ["when", "protocol", "name", "window", "capital", "switches", "seconds",
           "information_ratio", "kind", "status", "days"]  # fmt: skip
PROTOCOL = "versions/v4/protocol.md"
NOT_RUN = "not run"
# The leak self-test's bars (PLAN §14.2, K4); each fires above its bar.
HIT, CONCENTRATION, PRE_COST_IR, IC, IDIOSYNCRATIC = 0.56, 1 / 3, 1.2, 0.10, 0.90
# The hurdle above the bill, a day's share of it, and the top-N size.
PREMIUM, YEAR, TOP = 0.04, 252, 10


# One ledger row; the information ratio of a v4 book stays empty.
def row(name: str, kind: str, window: str, when="", status="run", **kw) -> dict:
    return {"when": when, "protocol": PROTOCOL, "name": name, "window": window,
            "kind": kind, "status": status} | kw  # fmt: skip


# A file's modified time, as the ledger's date when nothing is stamped.
def stamped(path: Path) -> str:
    return pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(timespec="seconds")


# The 8 signal gates: six at the gates' commit, two late, else not run.
def gate_rows() -> list[dict]:
    rows = []
    for stage, names, files in (("gates", SIX, [GATES / f"gates_{GATES_AT}.json"]),
                                ("late", LATE, sorted(GATES.glob("late_*.json")))):  # fmt: skip
        found = set()
        for path in (p for p in files if p.exists()):
            done = json.loads(path.read_text())
            # A gate with no fit (customer momentum) still counts in the family.
            for name, res in done[stage]["gates"].items():
                status = "not built" if "failed" in res else "run"
                rows.append(row(f"gate {name}", "gate", "2015-2020", done["stamp"]["run_utc"],
                                status))  # fmt: skip
                found.add(name)
        rows += [row(f"gate {n}", "gate", "2015-2020", status=NOT_RUN) for n in names
                 if n not in found]  # fmt: skip
    return rows


# Every model-grid cell of each validation run, named by its settings.
def cell_rows() -> list[dict]:
    rows = []
    for path in sorted(FORECAST.glob("validate_*.json")):
        done = json.loads(path.read_text())
        tag = path.stem.removeprefix("validate_")
        for c in done["validate"]["cells"]:
            name = (f"cell {c['stocks']} h{c['horizon']} leaves {c['leaves']} "
                    f"children {c['children']} w {c['w_ml']} @{tag}")  # fmt: skip
            rows.append(row(name, "model", "2019-2020", done["stamp"]["run_utc"]))
    return rows


# One derivation's builds from its grids' values, never its results.
def grid_rows(log: dict | None, tag: str, status: str, when: str) -> list[dict]:
    # A log lists each grid in its keys; no log means the grids as run.
    keys = {"ridge": GRIDS["ridge"], "style_cap": GRIDS["style_cap"], "margin": GRIDS["margin"],
            "sector_band": GRIDS["sector_band"]}  # fmt: skip
    if log is not None:
        keys = {
            "ridge": log["ridge_names"],
            "style_cap": log["style_cap_shares"],
            "margin": log["margin_costs"],
            "sector_band": log["sector_band_tc"],
        }
    # The 1% band reuses the chosen style cap's build, so it is no run.
    names = ["base ridge 30"]
    for k, values in keys.items():
        names += [f"{k} {v}" for v in list(values)[1 if k == "sector_band" else 0 :]]
    return [row(f"setting {n} @{tag}", "setting", "pre-2021", when, status, capital=1e9)
            for n in names]  # fmt: skip


# Derived-setting trials: the log's builds and any void derivation's.
def setting_rows() -> list[dict]:
    path = CONSTRUCT / "settings_log.json"
    rows = []
    if path.exists():
        rows += grid_rows(json.loads(path.read_text()), "current", "run", stamped(path))
    # A void derivation's log, marked by its commit if it recorded one.
    voids = sorted(CONSTRUCT.glob("settings_log_*.json"))
    for v in voids:
        log = json.loads(v.read_text())
        rows += grid_rows(log, str(log.get("commit", v.stem)), "void", stamped(v))
    # With no void log kept, the grids as the protocol records the run.
    if not voids:
        rows += grid_rows(None, "void", "void, log not kept", "2026-10-26")
    return rows


# A parquet's row count from its footer, no value read.
def days(path: Path) -> int:
    return int(pq.ParquetFile(path).metadata.num_rows)


# The exam designs and the desk arms, by file name and day count.
def book_rows() -> list[dict]:
    rows = []
    for k in DESIGNS:
        files = sorted(CONSTRUCT.glob(f"exam_daily_{k}_*.parquet"))
        rows += [row(f"exam design {k} @{p.stem.rsplit('_', 1)[1]}", "exam", "2017-2020",
                     stamped(p), capital=1e9, days=days(p)) for p in files]  # fmt: skip
        if not files:
            rows.append(row(f"exam design {k}", "exam", "2017-2020", status=NOT_RUN))
    # Arm files are arm_<name>_<commit>; A0's days have their own name.
    seen = set()
    files = sorted(DESK.glob("a0_daily_*.parquet")) + sorted(DESK.glob("arm_*_*.parquet"))
    for p in files:
        arm, tag = ("A0", p.stem.removeprefix("a0_daily_")) if p.stem.startswith("a0_") else (
            p.stem.removeprefix("arm_").rsplit("_", 1))  # fmt: skip
        if arm != "A0_replay":
            seen.add(arm)
            rows.append(row(f"desk arm {arm} @{tag}", "desk", "2017-2020", stamped(p),
                            capital=1e9, days=days(p)))  # fmt: skip
    rows += [row(f"desk arm {a}", "desk", "2017-2020", status=NOT_RUN) for a in ARMS
             if a not in seen]  # fmt: skip
    return rows


# The v4 trial ledger, one row per configuration run, IRs left empty.
def ledger() -> pd.DataFrame:
    rows = gate_rows() + cell_rows() + setting_rows() + book_rows()
    return pd.DataFrame(rows).reindex(columns=COLUMNS)


# The three counts' inputs: v4 trials run, v1-v3 rows, and every fit.
def counts(rows: pd.DataFrame, older: int | None = None) -> dict:
    v4 = int((rows["status"] != NOT_RUN).sum())
    v13 = len(trial_names(V2_TRIALS))
    out = {"v4": v4, "v4_not_run": int((rows["status"] == NOT_RUN).sum()), "v1_v3": v13,
           "v4_v1_v3": v4 + v13}  # fmt: skip
    # Every fit: v4 plus the older count evidence.py's trial_counts holds.
    return out | ({} if older is None else {"all": v4 + older})


# Days compounded to months, as v1 to v3 counted (monthly Sharpe).
def monthly(x: pd.Series) -> pd.Series:
    if not isinstance(x.index, pd.DatetimeIndex):
        return x
    return (1 + x).groupby(x.index.to_period("M")).prod() - 1


# The deflated Sharpe at each count, by v1-v3's own helper.
def deflated(daily_net_excess: pd.Series, counts: dict) -> dict:
    x = monthly(daily_net_excess.dropna())
    out = {}
    for name, n in counts.items():
        p, sr0 = P.deflated_sharpe(x, int(n))
        out[name] = {"trials": int(n), "probability": p, "sr0_annual": sr0}
    return out


# One check: its value, its bar and whether it fired (strictly above).
def check(value, bar: float, note: str = "") -> dict:
    ok = value is not None and bool(np.isfinite(value))
    return {"value": float(value) if ok else None, "threshold": bar,
            "fired": bool(ok and value > bar), "note": note}  # fmt: skip


# A day's dollars: the pre-trade NAV is the last close's NAV.
def nav_before(daily: pd.DataFrame) -> pd.Series:
    return daily["nav"] / (1 + daily["ret"])


# The ten biggest gains' share of the total; None if total <= 0.
def top_share(pnl: pd.Series) -> float | None:
    total = float(pnl.sum())
    return float(pnl.nlargest(TOP).sum() / total) if total > 0 else None


# Each name's P&L: its value at a close times the next session's return.
def name_pnl(positions: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    held = positions.pivot_table(index="date", columns="permno", values="value", fill_value=0.0)
    after = returns.index.searchsorted(held.index, side="right")
    keep = after < len(returns)
    nxt = returns.iloc[after[keep]].reindex(columns=held.columns).fillna(0.0)
    return pd.Series((held.loc[keep].to_numpy() * nxt.to_numpy()).sum(axis=0), index=held.columns)


# Share of the active return the factors leave unexplained, 1 - R^2.
def idiosyncratic(active: pd.Series, factors: pd.DataFrame) -> float | None:
    both = pd.concat([active.rename("y"), factors], axis=1, join="inner").dropna()
    if len(both) <= factors.shape[1] + 2:
        return None
    x = np.column_stack([np.ones(len(both)), both[list(factors.columns)].to_numpy()])
    y = both["y"].to_numpy()
    resid = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
    return float(resid @ resid / ((y - y.mean()) @ (y - y.mean())))


# PLAN §14.2's leak self-test: flags only, never changes a book.
def selftest(
    daily: pd.DataFrame,
    positions: pd.DataFrame,
    ic: float | None = None,
    pnl: pd.Series | None = None,
    factors: pd.DataFrame | None = None,
) -> dict:
    days_ = daily.dropna(subset=["ret", "rf"])
    active = days_["ret"] - days_["rf"]
    # Pre-cost: costs and borrow, booked in dollars, added back to the day.
    fees = (days_["cost"] + days_["borrow"]) / nav_before(days_)
    pre = days_["ret"] + fees - days_["rf"] - PREMIUM / YEAR
    ir = float(pre.mean() / pre.std() * np.sqrt(YEAR)) if len(pre) > 1 else None
    by_day = top_share(active * nav_before(days_))
    out = {"hit_rate": check(float((active > 0).mean()), HIT, "share of days with ret > rf"),
           "top10_days": check(by_day, CONCENTRATION, "needs total P&L above 0"),
           "pre_cost_ir": check(ir, PRE_COST_IR, "against rf + 4% a year"),
           "forecast_ic": check(ic, IC, "" if ic is not None else "no IC passed")}  # fmt: skip
    # Names need P&L per name; positions alone carry no returns.
    out["top10_names"] = (check(top_share(pnl), CONCENTRATION) if pnl is not None
                          else check(None, CONCENTRATION, "needs name P&L"))  # fmt: skip
    # The idiosyncratic share needs a daily factor frame.
    share = idiosyncratic(active, factors) if factors is not None else None
    out["idiosyncratic_share"] = check(share, IDIOSYNCRATIC,
                                       "" if share is not None else "not computed")  # fmt: skip
    book = {"days": len(days_), "dates_held": int(positions["date"].nunique()),
            "names_held": int(positions["permno"].nunique())}  # fmt: skip
    fired = [k for k, v in out.items() if v["fired"]]
    return {"checks": out, "fired": fired, "any_fired": bool(fired), "book": book}


# The v2 ledger's run names, one per row, no number read.
def trial_names(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r["name"] for r in csv.DictReader(fh)]


# A file the command line names, as a frame.
def load(path: str) -> pd.DataFrame:
    return pq.ParquetFile(path).read().to_pandas()


# Every older fit as evidence.py counts them, from file names alone.
def older_fits(v2_out: Path | None = None, exp: Path | None = None) -> int:
    from fiam import stats, v2
    from fiam.exhibits import evidence as old

    v2_out, exp = v2_out or v2.OUT, exp or old.EXP
    configs = {n.split("@")[0] for n in trial_names(v2_out / "trials.csv")}
    singles = {p.stem for p in exp.glob("*.csv")}
    return stats.TRIALS_PAST + len(singles) + old.ANDREW_TRIALS + len(configs)


# The ledger to CSV with the three counts; the CLI's first command.
def run_ledger() -> dict:
    rows = ledger()
    OUT.mkdir(parents=True, exist_ok=True)
    rows.to_csv(OUT / "trials_v4.csv", index=False, lineterminator="\n")
    return counts(rows, older_fits())


# The CLI's selftest: files in, flags out (--ic --returns --factors).
def run_selftest(args: list[str]) -> dict:
    opts = dict(zip(args[2::2], args[3::2]))
    daily, positions = load(args[0]), load(args[1])
    rets = load(opts["--returns"]) if "--returns" in opts else None
    facs = load(opts["--factors"]) if "--factors" in opts else None
    ic = float(opts["--ic"]) if "--ic" in opts else None
    pnl = name_pnl(positions, rets) if rets is not None else None
    return selftest(daily, positions, ic, pnl, facs)


# python -m fiam.v4.evidence ledger | selftest <daily> <positions> [...]
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ledger":
        print(json.dumps(run_ledger(), indent=1))
    elif cmd == "selftest" and len(sys.argv) >= 4:
        print(json.dumps(run_selftest(sys.argv[2:]), indent=1))
    else:
        raise SystemExit("ledger | selftest <daily> <positions> [--ic x --returns f --factors f]")
