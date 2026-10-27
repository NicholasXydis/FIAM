# Rehearsal 1: the unchanged engine on synthetic 2021-2026 (protocol).

import hashlib
import json
import sys
import time
from contextlib import contextmanager

import numpy as np
import pandas as pd

from fiam.v4 import daily_book, data, evidence, gates, sources
from fiam.v4.construct import book, exam, execution, risk, settings, simulate

OUT = gates.ROOT / "out" / "v4" / "rehearsal"
# The protocol's draw: the seed and the mean block length in months.
SEED, BLOCK = 20262101, 6
# Source formations (the exam's) and the target holding months.
SOURCE = (pd.Timestamp("2017-01-31"), pd.Timestamp("2020-11-30"))
TARGET = (pd.Timestamp("2021-01-31"), pd.Timestamp("2026-08-31"))
SEAL = pd.Timestamp("2020-12-31")
# Tables the engine and its hook read on synthetic days, by date key.
DAILY = {"dsf": "date", "crsp_daily": "date", "crsp_market_daily": "date", "sp500": "date",
         "exits": "exit_date", "short_interest": "settlement"}  # fmt: skip
MONTHLY = {"panel": "eom", "tb3ms": "month"}
# Clock columns moved with their row by the same number of sessions.
CLOCKS = ("first_close", "known")
# Every output carries this mark; no tracked file may (a test).
MARK = "rehearsal-synthetic"


# Each target holding month's source formation: stationary blocks.
def months(seed: int = SEED) -> dict:
    src = list(data.month_ends(*SOURCE))
    rng = np.random.default_rng(seed)
    out, i = {}, None
    for m in data.month_ends(*TARGET):
        jump = i is None or rng.random() < 1 / BLOCK
        i = int(rng.integers(len(src))) if jump else (i + 1) % len(src)
        out[m] = src[i]
    return out


# The month after a month end, as its month end.
def after(eom) -> pd.Timestamp:
    return pd.Timestamp(eom) + pd.offsets.MonthEnd(1)


# The first day of a month end's month.
def start(eom) -> pd.Timestamp:
    return pd.Timestamp(eom).replace(day=1)


# The synthetic world: target sessions and months mapped to sources.
class World:
    # Session k of a target month is session k of its source month.
    def __init__(self, mapping: dict):
        self.mapping, self.cal = mapping, data.calendar().index
        src = data.sessions(start(after(SOURCE[0])), SEAL)
        rows = []
        for m, s in mapping.items():
            first = int(src.searchsorted(start(after(s))))
            # A longer target month runs on; past 2020 it wraps to 2017-02.
            for k, t in enumerate(data.sessions(start(m), m)):
                rows.append((t, src[(first + k) % len(src)], m))
        self.days = pd.DataFrame(rows, columns=["target", "source", "month"])
        self.source_of = dict(zip(self.days["target"], self.days["source"]))
        ends = list(mapping)
        # A decision close reads its next holding month's source formation.
        self.formation = {e - pd.offsets.MonthEnd(1): s for e, s in mapping.items()}
        self.panel_from = self.formation | {ends[-1]: after(mapping[ends[-1]])}
        self.held = {e: after(s) for e, s in mapping.items()} | {SEAL: SEAL}
        self.real, self.cache = data.table, {}

    # Whether a read reaches past the seal on a table the engine needs.
    def wants(self, name: str, where) -> bool:
        key = (DAILY | MONTHLY).get(name)
        if key is None:
            return False
        got = (where or {}).get(key)
        if got is None:
            return True
        values = list(got) if isinstance(got, (set, frozenset, list)) else [got[1]]
        edge = SEAL if name == "panel" else SEAL + pd.Timedelta(days=1)
        return any(pd.Timestamp(v) >= edge for v in values)

    # The session index of each date, the session on or before it.
    def index(self, dates) -> np.ndarray:
        d = pd.to_datetime(pd.Series(dates)).dt.normalize().to_numpy()
        return self.cal.searchsorted(d, side="right") - 1

    # Clocks moved by their lag in sessions from the old anchor.
    def move(self, frame: pd.DataFrame, old, new) -> pd.DataFrame:
        out = frame.copy()
        base, to = self.index(old), self.index(new)
        for c in CLOCKS:
            if c in out:
                ok = out[c].notna().to_numpy()
                lag = self.index(out[c].fillna(pd.Timestamp(old.iloc[0]))) - base
                pos = np.clip(to + lag, 0, len(self.cal) - 1)
                out[c] = pd.Series(np.where(ok, self.cal[pos], pd.NaT), index=out.index)
                out[c] = pd.to_datetime(out[c])
        # available_at keeps its offset from its own moved first close.
        if "available_at" in out and "first_close" in out:
            moved = pd.to_datetime(out["first_close"]) - pd.to_datetime(frame["first_close"])
            out["available_at"] = frame["available_at"] + moved.to_numpy()
        elif "available_at" in out:
            shift = pd.to_datetime(pd.Series(new).to_numpy()) - pd.to_datetime(old.to_numpy())
            out["available_at"] = out["available_at"] + pd.to_timedelta(shift)
        return out

    # A daily table's rows on mapped target sessions within the filter.
    def daily(self, name: str, columns, purpose, where) -> pd.DataFrame:
        key = DAILY[name]
        m = self.days
        got = (where or {}).get(key)
        if isinstance(got, (set, frozenset, list)):
            m = m[m["target"].isin(pd.to_datetime(list(got)))]
        elif got is not None:
            m = m[m["target"].between(pd.Timestamp(got[0]), pd.Timestamp(got[1]))]
        if m.empty:
            return pd.DataFrame()
        rest = {k: v for k, v in (where or {}).items() if k != key}
        span = (m["source"].min() - pd.Timedelta(days=7), m["source"].max())
        rows = self.real(name, columns, purpose, rest | {key: span})
        rows = rows.assign(_s=self.cal[np.maximum(self.index(rows[key]), 0)])
        # Private names, so a table's own "source" column is kept as is.
        days = m[["target", "source"]].rename(columns={"target": "_t", "source": "_src"})
        both = rows.merge(days, left_on="_s", right_on="_src")
        out = self.move(both, both["_s"], both["_t"])
        out[key] = out["_t"] + (both[key] - both["_s"])
        return out.drop(columns=["_s", "_t", "_src"])

    # Each target month end's panel: the decision close's source rows.
    def panel(self, columns, purpose, where) -> pd.DataFrame:
        rest = {k: v for k, v in (where or {}).items() if k != "eom"}
        need = sorted(set(self.panel_from.values()) | set(self.held.values()))
        rows = self.real("panel", columns, purpose, rest | {"eom": (need[0], need[-1])})
        got = (where or {}).get("eom")
        out = []
        for e, s in self.panel_from.items():
            if got is not None and not isinstance(got, (set, frozenset, list)):
                if not pd.Timestamp(got[0]) <= e <= pd.Timestamp(got[1]):
                    continue
            main = rows[rows["eom"] == s]
            back = rows[(rows["eom"] == self.held.get(e, e)) & ~rows["permno"].isin(main["permno"])]
            part = pd.concat([main, back], ignore_index=True)
            if part.empty:
                continue
            ends = dict(zip(part["eom"].unique(), data.eom_session(part["eom"].unique())))
            old = part["eom"].map(ends)
            new = pd.Series(data.eom_session([e]).iloc[0], index=part.index)
            part = self.move(part, old, new).assign(eom=e)
            if "ret" in part and e > SEAL:
                part["ret"] = part["permno"].map(self.month_returns(e, rows)).to_numpy()
            out.append(part)
        return pd.concat(out, ignore_index=True) if out else pd.DataFrame()

    # A target month's return per stock over its own mapped sessions.
    def month_returns(self, e, rows: pd.DataFrame) -> pd.Series:
        src = list(self.days.loc[self.days["month"] == e, "source"])
        h = self.held[e]
        if src == list(data.sessions(start(h), h)):
            return rows[rows["eom"] == h].set_index("permno")["ret"]
        if ("ret", e) not in self.cache:
            c = self.real("crsp_daily", ["ret", "delflg"], None, {"date": set(src)})
            c = c[c["delflg"] != "Y"]
            grown = (1 + c.set_index("permno")["ret"]).groupby(level=0).prod(min_count=1)
            self.cache[("ret", e)] = grown - 1
        return self.cache[("ret", e)]

    # The bill of each target month: its source holding month's rate.
    def bills(self, columns, purpose) -> pd.DataFrame:
        rows = self.real("tb3ms", columns, purpose).sort_values("month")
        out = []
        for m in self.mapping:
            # A month whose rate is still sealed takes the last public one.
            part = rows[rows["month"] <= start(self.held[m])].tail(1)
            old = data.eom_session([self.held[m]] * len(part)).set_axis(part.index)
            new = pd.Series(data.eom_session([m]).iloc[0], index=part.index)
            out.append(self.move(part, old, new).assign(month=start(m)))
        return pd.concat(out, ignore_index=True)

    # Held names absent from the next source month: a forced exit.
    def forced(self) -> dict:
        if "forced" in self.cache:
            return self.cache["forced"]
        lo, hi = self.days["source"].min(), SEAL
        rows = self.real("dsf", ["ret"], None, {"date": (lo - pd.Timedelta(days=7), hi)})
        there = rows.groupby("date")["permno"].agg(set).to_dict()
        was, out = there.get(SEAL, set()), {}
        for _, g in self.days.groupby("month", sort=True):
            first = g["target"].iloc[0]
            out[first] = was - there.get(self.source_of[first], set())
            was = set().union(*(there.get(s, set()) for s in g["source"]))
        self.cache["forced"] = out
        return out

    # The forced exits as exit rows: at the last price, known that day.
    def forced_rows(self) -> pd.DataFrame:
        rows = [(p, d) for d, names in self.forced().items() for p in sorted(names)]
        f = pd.DataFrame(rows, columns=["permno", "exit_date"])
        f["exit_date"] = pd.to_datetime(f["exit_date"])
        return f.assign(category="rehearsal_exit", group="rehearsal", delret=0.0,
                        known=f["exit_date"], source="rehearsal", first_close=f["exit_date"],
                        available_at=f["exit_date"].dt.tz_localize("UTC")
                        + pd.Timedelta(hours=21))  # fmt: skip

    # Synthetic rows for one read, cached by its arguments.
    def rows(self, name: str, columns, purpose, where) -> pd.DataFrame:
        frozen = tuple(sorted((k, str(v)) for k, v in (where or {}).items()))
        key = (name, None if columns is None else tuple(columns), purpose, frozen)
        if key not in self.cache:
            if name == "panel":
                out = self.panel(columns, purpose, where)
            elif name == "tb3ms":
                out = self.bills(columns, purpose)
            else:
                out = self.daily(name, columns, purpose, where)
            # A forced exit joins the exits the engine reads.
            if name == "exits":
                extra = self.forced_rows()
                if where and "permno" in where:
                    extra = extra[extra["permno"].isin(set(where["permno"]))]
                out = pd.concat([out, extra], ignore_index=True)
            self.cache[key] = out
        return self.cache[key].copy()

    # The overlays' events moved onto the target sessions.
    def overlays(self, events: dict) -> dict:
        out = {}
        for side, days in events.items():
            moved: dict = {}
            for t, s in zip(self.days["target"], self.days["source"]):
                if s in days:
                    moved.setdefault(t, set()).update(days[s])
            out[side] = moved
        return out


# The rehearsal's reader in place of the registry's, then restored.
@contextmanager
def active(world: World):
    real, permcos = data.table, data.permcos

    # Real rows to the seal; past it, the world's relabelled rows.
    def table(name, columns=None, purpose=None, where=None):
        frame = real(name, columns, purpose, where)
        if not world.wants(name, where):
            return frame
        extra = world.rows(name, columns, purpose, where)
        if name == "panel":
            frame = frame[frame["eom"] < SEAL]
        if extra.empty:
            return frame
        return pd.concat([frame, extra.reindex(columns=frame.columns)], ignore_index=True)

    # A company id on a synthetic day is the one on its source day.
    def mapped(permnos, dates):
        days = pd.to_datetime(pd.Series(dates).to_numpy())
        return permcos(permnos, [world.source_of.get(d, d) for d in days])

    table.synthetic = True
    data.table, data.permcos = table, mapped
    try:
        yield world
    finally:
        data.table, data.permcos = real, permcos
        data._CACHE.clear()


# The planner at a target close reads its source formation's inputs.
class Planner(simulate.Planner):
    # The target closes and month ends; each target eom's source.
    def __init__(self, ctx, settings_at, world: World, cadence: str, end):
        super().__init__(ctx, settings_at, True, "monthly", end)
        targets = list(world.formation)
        self.decision = simulate.decisions(targets, end, cadence)
        self.month_ends, self.world = set(data.eom_session(targets)), world
        for e, s in world.formation.items():
            ctx.caps[e] = ctx.caps[s]

    # One target month end's inputs, built at its source's close.
    def inputs(self, eom, prev):
        ctx = self.ctx
        if eom not in self.frames:
            s = self.world.formation[eom]
            self.frames = {eom: book.month(s, prev, ctx.f, ctx.fr, ctx.scale, ctx.returns,
                                           ctx.history, ctx.holdings, ctx.z,
                                           ctx.neutral, ctx.late)}  # fmt: skip
            data._CACHE.clear()
        return self.frames[eom]


# The engine hook, charging a forced exit's sale at full cost.
class Hook(execution.Execution):
    # The forced exits by day, then the usual hook's arguments.
    def __init__(self, forced: dict, *args, **kw):
        super().__init__(*args, **kw)
        self.forced, self.seen = forced, 0

    # A forced exit closed today pays its sale; then the usual day.
    def __call__(self, i, d, book, order):
        closing = {p: v for _, p, v in book.positions[self.seen :]}
        self.seen = len(book.positions)
        names = self.forced.get(d, set())
        gone = pd.Series({p: -v for p, v in closing.items()
                          if p in names and p not in book.values}, dtype=float)  # fmt: skip
        if len(gone) and book.costs is not None:
            paid = book.spread(d, "cost", book.costs(d, gone), gone)
            book.cash -= paid
            self.log.append((d, "rehearsal_exit_cost", paid))
        return super().__call__(i, d, book, order)


# The exam's chosen design, its settings and the final book's switches.
def chosen(head: str) -> dict:
    tag = exam.EXAM_AT or head[:12]
    read = lambda stage: json.loads((book.OUT / f"exam_{stage}_{tag}.json").read_text())  # noqa: E731
    designs, tests, brake = read("designs"), read("tests"), read("brake")
    k = 1 if designs["winner"] == 3 else int(designs["winner"])
    z, cap, neutral = exam.DESIGNS[k]
    on = {"long": tests["overlays"]["red_flags"]["passes"],
          "short": tests["overlays"]["insider_buys"]["passes"]}  # fmt: skip
    events = exam.overlay_events(exam.EVENTS_FROM, book.LAST) if any(on.values()) else {}
    return {"design": k, "z": z, "cap": cap, "neutral": neutral,
            "cadence": "weekly" if tests["cadence"]["weekly"] else "monthly",
            "overlays": {side: exam.by_day(events[side]) for side in on if on[side]},
            "brake": bool(brake["brake"]["kept"]), "exam_at": tag}  # fmt: skip


# One rehearsal: the chosen design's book over the synthetic years.
def rehearse(head: str, seed: int = SEED) -> tuple:
    if sources.unsealed():
        raise SystemExit("rehearsal 1 runs only while sealed: real 2021+ rows would mix in")
    pick = chosen(head)
    s = json.loads(settings.SETTINGS.read_bytes())
    settings_at = exam.settings_for(pick["design"], s)
    ctx = book.Context(z=pick["z"], neutral=pick["neutral"])
    world, end = World(months(seed)), TARGET[1]
    with active(world):
        planner = Planner(ctx, settings_at, world, pick["cadence"], end)
        ids = sorted(ctx.f["permno"].unique())
        T0 = data.eom_session([min(world.formation)]).iloc[0]
        watch = execution.SqueezeWatch(ids, T0, end)
        trigger = execution.TriggerBeta(risk.daily(ids, "2014-10-01", end), risk.late(ids, end))
        hook = Hook(world.forced(), {}, watch, planner, trigger,
                    world.overlays(pick["overlays"]), pick["brake"])  # fmt: skip
        holders = {e: pd.Series(dtype=float) for e in world.formation}
        result = daily_book.run(holders, T0, end, costs=planner.hooks.costs,
                                borrow=planner.hooks.borrow, hook=hook, permnos=ids,
                                synthetic=True)  # fmt: skip
    log = pd.DataFrame(hook.log, columns=["date", "kind", "value"])
    return result, log, planner.info, world, pick


# What a rehearsal may report: limits, rule events, names, costs.
def summary(result, log: pd.DataFrame, world: World) -> dict:
    found = daily_book.breaches(result)
    d = result.daily
    c = result.compliance
    events = pd.concat([result.events["kind"], log["kind"]]).value_counts()
    forced = log[log["kind"] == "rehearsal_exit_cost"].groupby("date")["value"].sum()
    return {"breach_days": int(len(found)),
            "first_breach": None if found.empty else f"{found.index[0]:%Y-%m-%d}",
            "breaches_by_rule": {k: int((~c.loc[found.index, k]).sum())
                                 for k in ("names_ok", "gross_ok", "net_ok", "cap_ok")}
            | {"short_floor": int((c.loc[found.index, "short_floor_breaches"] > 0).sum())},
            "sessions": int(len(d)), "formations": len(world.formation),
            "names": [int((d["n_long"] + d["n_short"]).min()),
                      int((d["n_long"] + d["n_short"]).max())],
            "gross_max": float(d["gross"].max()), "net_abs_max": float(d["net"].abs().max()),
            "max_weight": float(d["max_weight"].max()),
            "costs_share_of_nav": float(((d["cost"] + d["borrow"]) / d["nav"]).sum()
                                        + (forced / d["nav"].reindex(forced.index)).sum()),
            "forced_exits": int(sum(len(v) for v in world.forced().values())),
            "events": {str(k): int(v) for k, v in events.items()}}  # fmt: skip


# python -m fiam.v4.construct.rehearsal, once per commit, seed fixed.
if __name__ == "__main__":
    head = gates.commit()
    target = OUT / f"rehearsal_{head[:12]}.json"
    if target.exists():
        raise SystemExit(f"{target.name} exists: rehearsal 1 runs once per commit")
    began = time.time()
    result, log, info, world, pick = rehearse(head)
    mapping = {f"{t:%Y-%m}": f"{s:%Y-%m}" for t, s in world.mapping.items()}
    sha = hashlib.sha256(json.dumps([SEED, mapping]).encode()).hexdigest()
    out = {"stage": "rehearsal", "stamp": exam.stamp(head, settings.SETTINGS.read_bytes()),
           "synthetic": f"{MARK}:{sha}", "seed": SEED, "block": BLOCK, "sources": mapping,
           "design": pick["design"], "switches": {k: pick[k] for k in ("cadence", "brake")}
           | {"overlays": sorted(pick["overlays"])},
           "seconds": round(time.time() - began)} | summary(result, log, world)  # fmt: skip
    # PLAN §14.2's leak self-test: which checks fire, never their values.
    out["leak_selftest_fired"] = evidence.selftest(result.daily, result.positions)["fired"]
    OUT.mkdir(parents=True, exist_ok=True)
    keep = ["nav", "ret", "rf", "cost", "borrow", "gross", "net", "n_long", "n_short"]
    result.daily[keep].to_parquet(OUT / f"rehearsal_daily_{head[:12]}_{MARK}.parquet")
    result.positions.to_parquet(OUT / f"rehearsal_positions_{head[:12]}_{MARK}.parquet")
    target.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("stamp", "sources")}, indent=1))
    sys.exit(1 if out["breach_days"] else 0)
