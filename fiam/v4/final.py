# The one final run, only after the hash-checked unseal (PLAN §13.3).

import json
import pickle
import shutil
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

from fiam.v4 import clock, daily_book, data, gates, sources
from fiam.v4.construct import (
    book,
    crowding,
    exam,
    execution,
    inputs,
    risk,
    screens,
    settings,
    simulate,
)
from fiam.v4.forecast import dataset, grid
from fiam.v4.report import holdings, table_9_1, vs_market

OUT = gates.ROOT / "out" / "v4" / "final"
# Each stage once per commit, in order, all after the unseal.
STAGES = ("labels", "forecasts", "book", "report")
NEEDS = {"forecasts": "labels", "book": "forecasts", "report": "book"}
# The engine's tables each run keeps, and the headline book's source.
PARTS = ("daily", "positions", "trades", "events", "ledger", "compliance")
# The finals' formations, 2020-12 to 2026-07, and the window's last day.
FIRST, LAST = pd.Timestamp("2020-12-31"), pd.Timestamp("2026-07-31")
END = pd.Timestamp("2026-08-31")
# The yearly refits each January on the 2019-2020 choices, no re-tune.
YEARS, SUE_YEARS = range(2021, 2027), range(2016, 2027)
# The models' commit (step 6): its choices and its blind forecasts.
MODELS_AT = book.FORECASTS.stem.removeprefix("forecasts_")


# The windows opened to the finals' end, only once unsealed; restored.
@contextmanager
def opened():
    if not sources.unsealed():
        raise SystemExit("sealed: run `uv run run.py finals --unseal` first (§13.3)")
    keep = (clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST, grid.SUE_YEARS, grid.RETURN_YEARS)
    clock.LAST_LABEL_DAY = gates.LAST_DAY = END
    dataset.LAST, grid.SUE_YEARS, grid.RETURN_YEARS = LAST, SUE_YEARS, YEARS
    data._CACHE.clear()
    try:
        yield
    finally:
        clock.LAST_LABEL_DAY, gates.LAST_DAY, dataset.LAST = keep[:3]
        grid.SUE_YEARS, grid.RETURN_YEARS = keep[3:]
        data._CACHE.clear()


# A file of a stage at this commit.
def path(stage: str, head: str, suffix: str = "json"):
    return OUT / f"{stage}_{head[:12]}.{suffix}"


# The labels to 2026-08, rebuilt; rows public by 2020 must not move.
def labels(head: str) -> dict:
    clean = sources.CLEAN / "labels.parquet"
    before = OUT / "labels_sealed.parquet"
    if not before.exists():
        shutil.copyfile(clean, before)
    made = sources.convert("labels")
    old, new = pd.read_parquet(before), pd.read_parquet(clean)
    return {"rows": made["rows_out"]} | same_before(old, new)


# Whether the rebuilt labels keep every row public by 2020 unchanged.
def same_before(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    keys = ["permno", "eom", "horizon"]
    cut = sources.SEAL.tz_convert(None).normalize()
    early = new[pd.to_datetime(new["available"]) <= cut].sort_values(keys, ignore_index=True)
    old = old.sort_values(keys, ignore_index=True)[early.columns]
    same = len(early) == len(old) and early.equals(old)
    return {"rows_before_2021": len(old), "unchanged_before_2021": bool(same)}


# The step 6 choices, read from the models' commit, never chosen again.
def choices() -> dict:
    v = json.loads((grid.OUT / f"validate_{MODELS_AT}.json").read_text())["validate"]
    sue = {s: {"passes": r["passes"], "chosen": r["chosen"]} for s, r in v["sue_model"].items()}
    return {"chosen": v["chosen"], "members": v["members"] | {"sue": sue}}


# Blind forecasts to 2020-12 kept; the yearly refits' after them.
def joined(pinned: pd.DataFrame, refit: pd.DataFrame) -> tuple:
    later = refit[refit["eom"] > pinned["eom"].max()]
    first = refit[refit["eom"] == pinned["eom"].max()].set_index("permno")["z"]
    blind = pinned[pinned["eom"] == pinned["eom"].max()].set_index("permno")["z"]
    gap = float((first - blind.reindex(first.index)).abs().max()) if len(first) else np.nan
    return pd.concat([pinned, later], ignore_index=True), gap


# The 2021-2026 forecasts: each year refitted on everything public.
def forecasts(head: str) -> dict:
    built = json.loads(path("labels", head).read_text())
    if not built["unchanged_before_2021"]:
        raise SystemExit("the rebuilt labels changed rows public by 2020: stop and report")
    c = choices()
    refit = grid.walk(grid.Table(sources.characteristics()), c["chosen"], c["members"])
    both, gap = joined(pd.read_parquet(book.FORECASTS), refit)
    # The models are exact only on the machine that fitted them (the Mac).
    if not gap == 0.0:
        raise SystemExit(f"the refit misses the blind 2020-12 forecast by {gap}: wrong machine")
    both.to_parquet(path("forecasts", head, "parquet"), index=False)
    return {"rows": len(both), "formations": int(both["eom"].nunique()),
            "last": f"{both['eom'].max():%Y-%m-%d}",
            "first_formation_gap_to_blind": gap}  # fmt: skip


# The finals' context: the frozen alpha scale, inputs to 2026-08.
class Context(book.Context):
    # As the exam's, over the finals' formations, scale from settings.
    def __init__(self, f: pd.DataFrame, scale: float, z: str, neutral=()):
        self.months = data.month_ends(FIRST, LAST)
        self.z, self.neutral = z, tuple(neutral)
        self.f, self.fr, self.scale = f, factor_returns(), scale
        ids = sorted(f["permno"].unique())
        self.returns = risk.daily(ids, "2014-10-01", END)
        self.late = risk.late(ids, END)
        self.history = screens.History(LAST)
        self.holdings = crowding.Holdings(FIRST - pd.DateOffset(months=18), LAST)
        ends = data.eom_session(self.months)
        caps = book.crash_caps(ends.iloc[-1])
        self.caps = {e: float(caps.loc[T]) for e, T in zip(self.months, ends)}
        data._CACHE.clear()


# The style factor returns from 2015 to the finals' last formation.
def factor_returns() -> pd.DataFrame:
    target = OUT / f"factor_returns_to_{LAST:%Y-%m}.parquet"
    if not target.exists():
        frames = {e: inputs.formation(e) for e in data.month_ends("2015-01-31", LAST)}
        risk.factor_returns(frames).to_parquet(target)
    return pd.read_parquet(target)


# The final book: the exam's design and switches, all limits checked.
def final_book(head: str) -> dict:
    tag = exam.EXAM_AT or head[:12]
    read = lambda stage: json.loads((book.OUT / f"exam_{stage}_{tag}.json").read_text())  # noqa: E731
    designs, tests, brake = read("designs"), read("tests"), read("brake")
    k = 1 if designs["winner"] == 3 else int(designs["winner"])
    z, _, neutral = exam.DESIGNS[k]
    s = json.loads(settings.SETTINGS.read_bytes())
    settings_at = exam.settings_for(k, s)
    on = {"long": tests["overlays"]["red_flags"]["passes"],
          "short": tests["overlays"]["insider_buys"]["passes"]}  # fmt: skip
    events = exam.overlay_events(FIRST, END) if any(on.values()) else {}
    overlays = {side: exam.by_day(events[side]) for side in on if on[side]}
    cadence = "weekly" if tests["cadence"]["weekly"] else "monthly"
    f = pd.read_parquet(path("forecasts", head, "parquet"))
    ctx = Context(f, float(s["alpha_scale"]), z, neutral)
    result, plans = simulate.run(ctx, settings_at, END, cadence=cadence, overlays=overlays,
                                 brake=bool(brake["brake"]["kept"]),
                                 hook_class=execution.Recording, unsealed=True)  # fmt: skip
    with path(f"plans_{k}", head, "pkl").open("wb") as fh:
        pickle.dump({"made": result.hook.made, "kept": result.hook.kept,
                     "hooks": result.hooks}, fh)  # fmt: skip
    for part in PARTS:
        getattr(result, part).to_parquet(path(f"{part}_{k}", head, "parquet"))
    found = daily_book.breaches(result)
    out = {"design": k, "cadence": cadence, "overlays": sorted(overlays),
           "brake": bool(brake["brake"]["kept"]), "exam_at": tag,
           "breach_days": int(len(found)),
           "first_breach": None if found.empty else f"{found.index[0]:%Y-%m-%d}",
           "formations": len(plans)}  # fmt: skip
    return out


# The frozen headline arm's book: A0's own run, else the desk's replay.
def headline_book(head: str) -> tuple:
    frozen = json.loads((gates.ROOT / "frozen" / "v4" / "config.json").read_text())
    arm = frozen["headline"]["arm"]
    k = json.loads(path("book", head).read_text())["design"]
    if arm == "A0":
        return arm, {p: pd.read_parquet(path(f"{p}_{k}", head, "parquet")) for p in PARTS}
    desk = gates.ROOT / "out" / "v4" / "desk"
    got = {p: desk / f"final_book_{arm}_{p}_{head[:12]}.parquet" for p in PARTS}
    if not all(f.exists() for f in got.values()):
        raise SystemExit(f"the headline is {arm}: run the desk's --final stages first")
    return arm, {p: pd.read_parquet(f) for p, f in got.items()}


# The PDF's 23 rows and Arcana's files from the headline book.
def report(head: str) -> dict:
    arm, b = headline_book(head)
    daily, positions = b["daily"], b["positions"]
    shorts = positions[positions["value"] < 0]
    market = daily_book.Market(sorted(shorts["permno"].unique()), daily.index)
    caps = shorts.assign(me=[market.cap_at(int(p), d)
                             for p, d in zip(shorts["permno"], shorts["date"])])  # fmt: skip
    rows = table_9_1.table(daily, b["trades"], positions, inputs.sp500(daily.index),
                           caps=caps[["date", "permno", "me"]])  # fmt: skip
    rows.to_csv(path("table_9_1", head, "csv"), index=False)
    ids = holdings.identifiers(positions["permno"], positions["date"])
    out = {"headline_arm": arm, "rows": len(rows)}
    for name, dates in (("daily", holdings.trade_days(b["trades"])),
                        ("monthly", holdings.monthly_days(b["trades"]))):  # fmt: skip
        file, lost = holdings.weights_file(positions, daily, ids, dates)
        holdings.write_csv(file, path(f"arcana_weights_{name}", head, "csv"), holdings.WEIGHTS)
        lost.to_csv(path(f"unresolved_{name}", head, "csv"), index=False)
        out[f"{name}_rows"], out[f"{name}_unresolved"] = len(file), len(lost)
    file, lost = holdings.positions_file(positions, b["ledger"], ids, daily)
    holdings.write_csv(file, path("arcana_positions", head, "csv"), holdings.POSITIONS)
    out |= {"positions_rows": len(file), "positions_unresolved": len(lost)}
    # The market table last: a missing market day is noted, never fatal.
    try:
        beside = vs_market.table(daily, inputs.sp500(daily.index),
                                 data.market_daily(daily.index))  # fmt: skip
        beside.to_csv(path("vs_market", head, "csv"), index=False)
        out["vs_market"] = "written"
    except ValueError as err:
        out["vs_market"] = f"not written: {err}"
    return out


# python -m fiam.v4.final labels | forecasts | book | report, unsealed.
if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage not in STAGES:
        raise SystemExit(f"name a stage: {' | '.join(STAGES)}")
    head = gates.commit()
    target = path(stage, head)
    if target.exists():
        raise SystemExit(f"{target.name} exists: each stage runs once per commit")
    if stage in NEEDS and not path(NEEDS[stage], head).exists():
        raise SystemExit(f"run the {NEEDS[stage]} stage first at this commit")
    OUT.mkdir(parents=True, exist_ok=True)
    work = {"labels": labels, "forecasts": forecasts, "book": final_book, "report": report}
    with opened():
        out = {"stage": stage, "stamp": exam.stamp(head, settings.SETTINGS.read_bytes())}
        out |= work[stage](head)
    target.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "stamp"}, indent=1, default=str))
    # Past the seal a broken PDF limit stops the build (PLAN §9.3).
    sys.exit(1 if out.get("breach_days") else 0)
