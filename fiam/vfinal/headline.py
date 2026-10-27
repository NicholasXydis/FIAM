# The headline: the final run's stages with their changes, by stage.

import json
import shutil
import sys
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd

from fiam.vfinal import data, final, gates, sources
from fiam.vfinal import inputs as engine
from fiam.vfinal.construct import book, exam, optimizer, settings
from fiam.vfinal.construct import inputs as construct
from fiam.vfinal.forecast import dataset, grid, models
from fiam.vfinal.report import table_9_1
from fiam.vfinal.signals import short_interest

# Full speed: each month trades all the way to the optimum.
SPEED = 1.0
# The loose limits tried against the tight ones on 2017-2020.
SECTOR_BAND, STYLE_TIMES = 0.05, 4
# Refits from 2017; formations to 2020-12 keep their sealed targets.
YEARS, SEALED_LAST = range(2017, 2027), pd.Timestamp("2020-12-31")
SI = "short_interest"
BASE = final.OUT
SUE_BACKUP = BASE / "sue_sealed.parquet"
CARD_BACKUP = BASE / "sue_card_sealed.json"
CARD = sources.CARDS / "sue.json"
PINNED = BASE / "sue_targets_sealed.parquet"
# Months between refits for each cadence, and the two sets of limits.
CADENCES = {"yearly": 12, "quarterly": 3}
LIMITS = ("tight", "loose")
# Each stage's arguments and the stages it reads.
ARGS = {"labels": 0, "forecasts": 1, "early": 2, "book": 2, "report": 2, "pick": 0}
NEEDS = {
    "forecasts": lambda a: [("labels", ())],
    "early": lambda a: [("forecasts", a[:1])],
    "book": lambda a: [("forecasts", a[:1])],
    "report": lambda a: [("book", a)],
}
USAGE = (
    "uv run python -m fiam.vfinal.headline labels | forecasts <cadence> | early <cadence> <limits>"
    " | book <cadence> <limits> | report <cadence> <limits> | pick"
)


# One cadence and limits' folder for its 2021-2026 book and report.
def folder(cadence: str, limits: str):
    return BASE / f"revised_{cadence}_{limits}"


# A stage's file: shared ones in the base folder, books in their own.
def where(stage: str, args: tuple, head: str, suffix: str = "json"):
    if stage in ("book", "report"):
        return folder(*args) / f"{stage}_{head[:12]}.{suffix}"
    return BASE / f"{'_'.join((stage, *args))}_{head[:12]}.{suffix}"


# What this run changes, as every stage file records it.
def changes() -> dict:
    return {
        "sue_table": "as-filed SUE table rebuilt to 2026-08; the SUE model refits each year",
        "sue_rows_by_2020": "rows public by 2020 kept exactly as sealed; later rows added",
        "sue_before_2021": "formations to 2020-12 keep their sealed SUE targets",
        "short_interest": "short interest over shares as a model input, monotone negative",
        "refits": "return models refit from 2017; alpha scale on pre-2021 rows, blind",
        "cadence": "yearly or quarterly, both run whatever the results; the higher step 6 "
        "IC on 2017-2020 wins, ties yearly, and the pick is final",
        "limits": f"tight, or loose (sectors {SECTOR_BAND}, style caps x{STYLE_TIMES}, "
        "size and value capped) if its 2017-2020 IR is higher with no breach day",
        "speed": SPEED,
        "hurdle": "TB3MS / 1200 + 0.04 / 12 a month (PDF p20)",
        "sp500": "the report reads fiam.v4.inputs.sp500",
    }


# Blind mode for a block: no row public after 2020 is read.
@contextmanager
def sealed():
    keep = sources.UNSEAL_CACHE
    sources.UNSEAL_CACHE = False
    data._CACHE.clear()
    try:
        yield
    finally:
        sources.UNSEAL_CACHE = keep
        data._CACHE.clear()


# The sealed SUE table and card back in place, saved once first.
def restore_sue() -> None:
    clean, card = sources.CLEAN / "sue.parquet", sources.CARDS / "sue.json"
    for live, kept in ((clean, SUE_BACKUP), (card, CARD_BACKUP)):
        if not kept.exists():
            shutil.copyfile(live, kept)
        shutil.copyfile(kept, live)
    data._CACHE.clear()


# Each formation's SUE target as blind mode built it, to 2020-12.
def pin_targets() -> dict:
    with sealed():
        got = dataset.sue_targets(data.month_ends(dataset.FIRST, SEALED_LAST))
    got.to_parquet(PINNED, index=False)
    return {"sue_targets_pinned": len(got)}


# Whether every row public by the seal is as the sealed table had it.
def same_before(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    keys = ["permno", "end"]
    seen = pd.to_datetime(new["available_at"], utc=True)
    early = new[(seen <= sources.SEAL).to_numpy()].sort_values(keys, ignore_index=True)
    old = old.sort_values(keys, ignore_index=True)
    same = len(early) == len(old) and early[old.columns].equals(old)
    return {"sue_rows_before_2021": len(old), "sue_unchanged_before_2021": bool(same)}


# Sealed rows as they were, plus every rebuilt row public after 2020.
def joined(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    keys = ["permno", "end"]
    seen = pd.to_datetime(new["available_at"], utc=True)
    later = new[(seen > sources.SEAL).to_numpy()]
    known = pd.MultiIndex.from_frame(later[keys]).isin(pd.MultiIndex.from_frame(old[keys]))
    out = pd.concat([old, later.loc[~known, old.columns]], ignore_index=True)
    return out.sort_values(keys, ignore_index=True)


# The labels as the final run builds them, then the SUE table to 2026.
def labels(head: str) -> dict:
    restore_sue()
    out = pin_targets()
    clean, old = sources.CLEAN / "sue.parquet", pd.read_parquet(SUE_BACKUP)
    with final.opened():
        out |= final.labels(head)
        made = sources.convert("sue")
    rebuilt = pd.read_parquet(clean)
    table = joined(old, rebuilt)
    table.to_parquet(clean, index=False)
    data._CACHE.clear()
    # The card states the joined table, the one every later stage reads.
    card = json.loads(CARD.read_text())
    CARD.write_text(json.dumps(card | {"rows_out": len(table)}, indent=1))
    out["sue_rebuild"] = {"rows": made["rows_out"]} | same_before(old, rebuilt)
    return out | {"sue_rows": len(table)} | same_before(old, table)


# Rows to 2020-12 take the pinned SUE target and its public close.
def pin_rows(x: pd.DataFrame, pinned: pd.DataFrame) -> pd.DataFrame:
    early = (x["eom"] <= SEALED_LAST).to_numpy()
    keys = pd.MultiIndex.from_frame(x.loc[early, ["permno", "eom"]])
    got = pinned.set_index(["permno", "eom"]).reindex(keys)
    x.loc[early, "sue_target"] = got["sue_target"].to_numpy()
    x.loc[early, "sue_public"] = got["sue_public"].to_numpy()
    return x


# The forecast table with pinned SUE targets and short interest ranked.
def install_table(pinned: pd.DataFrame) -> None:
    build = grid.Table.__init__

    # The original table, then its two changes.
    def init(self, chars):
        build(self, chars)
        self.x = pin_rows(self.x, pinned)
        si = short_interest.build(sorted(self.x["eom"].unique())).set_index(["permno", "eom"])
        keys = pd.MultiIndex.from_frame(self.x[["permno", "eom"]])
        frame = self.x[["eom", "in_universe"]].assign(**{SI: si["value"].reindex(keys).to_numpy()})
        for s in dataset.STOCKS:
            ranked = dataset.ranked(frame, [SI], s).astype(np.float32)
            self.feats[s] = self.feats[s].assign(**{SI: ranked[SI]})

    grid.Table.__init__ = init


# Short interest joins the inputs, allowed and monotone negative.
def install_inputs() -> None:
    frozen, mono = grid.inputs, models.monotone
    grid.inputs = lambda t, stocks, sue: frozen(t, stocks, sue).join(t.feats[stocks][[SI]])
    models.monotone = lambda cols: [-1 if c == SI else m for c, m in zip(cols, mono(cols))]
    dataset.EXTRA = (*dataset.EXTRA, SI)


# Refit blocks from 2016-12: a year runs December to November.
def blocks(months: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    firsts = pd.date_range(f"{YEARS[0] - 1}-12-31", f"{YEARS[-1]}-09-30", freq=f"{months}ME")
    return [(a, a + pd.offsets.MonthEnd(months - 1)) for a in firsts]


# The walk-forward forecast, refitted at each block's first formation.
def walk(t, chosen: dict, members: dict, spans) -> pd.DataFrame:
    s, h = chosen["stocks"], chosen["horizon"]
    f = grid.inputs(t, s, grid.sue_model_at(t, s, members["sue"]))
    m = members[f"{s} h{h}"]
    cells = [
        ("lgbm", (chosen["leaves"], chosen["children"])),
        ("enet", tuple(m["enet"])),
        ("nn", m["nn"]),
    ]
    out = []
    for first, last in spans:
        rows = t.rows("universe", first, last, universe_only=True)
        if len(rows) == 0:
            continue
        fits = grid.fit_members(t, f, s, h, grid.close_of(first), rows, cells)
        parts = [fits[c] for c in cells]
        ml = grid.ensemble(t, parts)
        ranked = pd.concat([grid.month_rank(t, p) for p in parts], axis=1)
        year = first.year + (first.month == 12)
        out.append(t.x.loc[rows, ["permno", "eom"]].assign(
            lgbm=parts[0], enet=parts[1], nn=parts[2], ml=ml,
            spread=ranked.std(axis=1, ddof=0), z=grid.blend(t, ml, chosen["w_ml"]),
            z_syy=grid.blend(t, ml, 0.0), fit_year=year, fit_at=first,
        ))  # fmt: skip
    out = pd.concat(out)
    assert out["z"].notna().all(), "a universe stock has no forecast"
    return out


# The pooled IC of z on rows whose label is public by 2020.
def ic_before_2021(t, f: pd.DataFrame) -> dict:
    x = t.x.loc[f.index]
    seen = dataset.public_by(x, "month_available_h1", grid.close_of(SEALED_LAST))
    keep = f.index[seen & (x["eom"] <= SEALED_LAST).to_numpy()]
    z, year = f.loc[keep, "z"], x.loc[keep, "eom"].dt.year
    by_year = {int(y): grid.pooled_ic(t, grid.month_rank(t, g)) for y, g in z.groupby(year)}
    return {"ic_2017_2020": grid.pooled_ic(t, grid.month_rank(t, z)), "ic_by_year": by_year}


# One cadence's forecasts 2016-12 to 2026-07 and their pre-2021 IC.
def forecasts(head: str, cadence: str) -> dict:
    built = json.loads(where("labels", (), head).read_text())
    if not (built["unchanged_before_2021"] and built["sue_unchanged_before_2021"]):
        raise SystemExit("a rebuilt table changed rows public by 2020: stop and report")
    install_table(pd.read_parquet(PINNED))
    install_inputs()
    with final.opened():
        t = grid.Table(sources.characteristics())
        c = final.choices()
        f = walk(t, c["chosen"], c["members"], blocks(CADENCES[cadence]))
        out = ic_before_2021(t, f)
    f.reset_index(drop=True).to_parquet(where("forecasts", (cadence,), head, "parquet"))
    span = f"{f['eom'].min():%Y-%m-%d} to {f['eom'].max():%Y-%m-%d}"
    return out | {"rows": len(f), "formations": int(f["eom"].nunique()), "span": span}


# The cadence with the higher pre-2021 IC; a tie goes to yearly.
def picked(ic: dict) -> str:
    return "quarterly" if ic["quarterly"] > ic["yearly"] else "yearly"


# Loose limits win only with no breach day and a higher IR (exam rule).
def loose_wins(tight: dict, loose: dict) -> bool:
    if loose["breach_days"] > 0:
        return False
    return tight["breach_days"] > 0 or loose["ir"] > tight["ir"]


# One formation's settings at full speed, the limits loosened if chosen.
def changed(s: optimizer.Settings, loose: bool) -> optimizer.Settings:
    if not loose:
        return replace(s, speed=SPEED)
    return replace(s, speed=SPEED, sector_band=SECTOR_BAND, style_cap=STYLE_TIMES * s.style_cap)


# The design's settings with the changes, the limits' code if loose.
def install_settings(loose: bool) -> None:
    frozen = exam.settings_for

    # The design's settings for each formation, then changed.
    def settings_for(k, s):
        at = frozen(k, s)
        return lambda eom, x, cap: changed(at(eom, x, cap), loose)

    exam.settings_for = settings_for
    if loose:
        install_limits()


# Size and value capped as styles; no relax step tightens sectors.
def install_limits() -> None:
    optimizer.inputs = SimpleNamespace(NEUTRAL=(), CAPPED=(*construct.CAPPED, *construct.NEUTRAL))
    frozen = optimizer.ladder
    wider = lambda t, s: replace(t, sector_band=max(t.sector_band, s.sector_band))  # noqa: E731
    optimizer.ladder = lambda s, initial: [(n, wider(t, s)) for n, t in frozen(s, initial)]
    book.align = align_betas


# Alpha aligned only with what stays at zero: betas and held styles.
def align_betas(alpha: pd.Series, x: pd.DataFrame, neutral=()) -> pd.Series:
    design = x[[*neutral, "welch", "dimson", "beta_60m"]].assign(one=1.0).to_numpy()
    coef, *_ = np.linalg.lstsq(design, alpha.to_numpy(), rcond=None)
    return alpha - design @ coef


# The exam's winning design and its settings file.
def design() -> tuple[int, dict]:
    picked_k = json.loads((book.OUT / f"exam_designs_{exam.EXAM_AT}.json").read_text())["winner"]
    return (1 if picked_k == 3 else int(picked_k)), json.loads(settings.SETTINGS.read_bytes())


# One cadence and limits on 2017-2020, blind, scored as the exam.
def early(head: str, cadence: str, limits: str) -> dict:
    k, s = design()
    z, _, neutral = exam.DESIGNS[k]
    install_settings(limits == "loose")
    book.FORECASTS = where("forecasts", (cadence,), head, "parquet")
    with sealed():
        got = exam.design(exam.settings_for(k, s), z, neutral=neutral)
    got.pop("plans")
    got.pop("daily").to_parquet(where("early", (cadence, limits), head, "parquet"))
    return {"design": k, "cadence": cadence, "limits": limits} | got


# The alpha scale by its formula on pre-2021 rows, as blind mode reads.
def scale_of(f: pd.DataFrame) -> float:
    with sealed():
        return book.alpha_scale(f[f["eom"] <= SEALED_LAST])


# The final run's files go to this cadence and limits' own folder.
def enter(cadence: str, limits: str) -> None:
    final.OUT = folder(cadence, limits)
    final.OUT.mkdir(parents=True, exist_ok=True)


# One cadence and limits on 2021-2026 at the pre-2021 alpha scale.
def run_book(head: str, cadence: str, limits: str) -> dict:
    enter(cadence, limits)
    file = where("forecasts", (cadence,), head, "parquet")
    shutil.copyfile(file, final.path("forecasts", head, "parquet"))
    cache = BASE / f"factor_returns_to_{final.LAST:%Y-%m}.parquet"
    if cache.exists():
        shutil.copyfile(cache, final.OUT / cache.name)
    scale = scale_of(pd.read_parquet(file))
    install_settings(limits == "loose")
    frozen = final.Context
    final.Context = lambda f, _, z, neutral=(): frozen(f, scale, z, neutral)
    with final.opened():
        made = final.final_book(head)
    return {"cadence": cadence, "limits": limits, "alpha_scale": scale} | made


# The month's bill as TB3MS / 1200, from the engine's daily rate.
def monthly_rate(rf_daily: pd.Series) -> pd.Series:
    month = pd.DatetimeIndex(rf_daily.index).to_period("M")
    return (rf_daily * 252 / 12).groupby(month).first()


# The 23 rows and Arcana's files, the hurdle as the PDF computes it.
def report(head: str, cadence: str, limits: str) -> dict:
    enter(cadence, limits)
    construct.sp500 = engine.sp500
    frozen = table_9_1.table

    # The original table given the PDF's monthly bill.
    def table(daily, *args, **kw):
        return frozen(daily, *args, rf_monthly=monthly_rate(data.rf_daily(daily.index)), **kw)

    table_9_1.table = table
    with final.opened():
        return {"cadence": cadence, "limits": limits} | final.report(head)


# The headline by the two pre-2021 rules, from what has run so far.
def pick(head: str) -> dict:
    done = lambda stage, args: where(stage, args, head).exists()  # noqa: E731
    load = lambda stage, args: json.loads(where(stage, args, head).read_text())  # noqa: E731
    ic = {c: load("forecasts", (c,))["ic_2017_2020"] for c in CADENCES if done("forecasts", (c,))}
    todo = [f"forecasts {c}" for c in CADENCES if c not in ic]
    cadence = picked(ic) if len(ic) == len(CADENCES) else "yearly"
    early_runs = {
        lim: load("early", (cadence, lim)) for lim in LIMITS if done("early", (cadence, lim))
    }
    todo += [f"early {cadence} {lim}" for lim in LIMITS if lim not in early_runs]
    loose = len(early_runs) == len(LIMITS) and loose_wins(early_runs["tight"], early_runs["loose"])
    limits = "loose" if loose else "tight"
    todo += [
        f"{s} {cadence} {limits}" for s in ("book", "report") if not done(s, (cadence, limits))
    ]
    return {
        "ic_2017_2020": ic,
        "early_ir": {lim: e["ir"] for lim, e in early_runs.items()},
        "cadence": cadence,
        "limits": limits,
        "headline": str(folder(cadence, limits)),
        "final": not todo,
        "next": todo,
    }


WORK = {"labels": labels, "forecasts": forecasts, "early": early, "book": run_book,
        "report": report, "pick": pick}  # fmt: skip


# The stage and its arguments, checked against the usage line.
def parse(argv: list[str]) -> tuple[str, tuple]:
    stage, args = (argv[0] if argv else ""), tuple(argv[1:])
    ok = stage in ARGS and len(args) == ARGS[stage]
    ok = ok and (not args or args[0] in CADENCES) and (len(args) < 2 or args[1] in LIMITS)
    if not ok:
        raise SystemExit(USAGE)
    return stage, args


# Runs one stage once per commit; pick may run again as results land.
if __name__ == "__main__":
    stage, args = parse(sys.argv[1:])
    head = gates.commit()
    target = where(stage, args, head)
    if target.exists() and stage != "pick":
        raise SystemExit(f"{target.name} exists: each stage runs once per commit")
    for need, need_args in NEEDS.get(stage, lambda a: [])(args):
        if not where(need, need_args, head).exists():
            raise SystemExit(f"run {need} {' '.join(need_args)} first at this commit")
    target.parent.mkdir(parents=True, exist_ok=True)
    # The stamp names the forecasts file these stages read.
    if stage in ("early", "book", "report"):
        book.FORECASTS = where("forecasts", args[:1], head, "parquet")
    out = {"stage": stage, "args": list(args)}
    out |= {"stamp": exam.stamp(head, settings.SETTINGS.read_bytes()), "changes": changes()}
    out |= WORK[stage](head, *args)
    target.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "stamp"}, indent=1, default=str))
    # A broken PDF limit ends the run with exit code 1.
    sys.exit(1 if out.get("breach_days") else 0)
