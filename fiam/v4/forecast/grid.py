# The models' runner: validation, walk-forward forecasts, noise trap.

import hashlib
import json
import sys

import numpy as np
import pandas as pd

from fiam.v4 import agreement, data, gates, ranks, sources
from fiam.v4.forecast import dataset, models

OUT = gates.ROOT / "out" / "v4" / "forecast"
# The stages in order; walk and trap need validate at the same HEAD.
STAGES = ("check", "validate", "walk", "trap")
# Validation: one fit on rows public by 2018-12, forecasts to 2020-10.
VALID_FIRST, VALID_LAST = pd.Timestamp("2018-12-31"), pd.Timestamp("2020-10-31")
# The SUE gate's formations, so every outcome is public by 2020-12-31.
SUE_FIRST, SUE_LAST = pd.Timestamp("2019-01-31"), pd.Timestamp("2020-08-31")
# Yearly refits: year Y fits on rows public by the prior December's T.
SUE_YEARS, RETURN_YEARS = range(2016, 2022), range(2017, 2022)
WEIGHTS, HORIZONS = (0.25, 0.5, 0.75, 1.0), (1, 3)
# The noise trap's seeds; its column must stay under chance importance.
TRAP_SEEDS = range(20261600, 20261620)
LABEL = "resid_rank_universe_h1"


# The table and each training set's ranked inputs, built once.
class Table:
    # Rows and each set's ranked characteristics and SYY-10.
    def __init__(self, chars: list[str]):
        self.chars = chars
        self.x = dataset.build(chars)
        self.feats = {}
        for s in dataset.STOCKS:
            f = dataset.ranked(self.x, [*chars, "syy_raw"], s).astype(np.float32)
            self.feats[s] = f.rename(columns={"syy_raw": "syy"})

    # Rows of a set whose formation lies in a span.
    def rows(self, stocks: str, first, last, universe_only: bool = False) -> pd.Index:
        x = self.x.loc[self.feats[stocks].index, ["eom", "in_universe"]]
        keep = x["eom"].between(first, last)
        if universe_only:
            keep &= x["in_universe"]
        return x.index[keep.to_numpy()]


# A formation's T, the close the fit's rows must be public by.
def close_of(eom) -> pd.Timestamp:
    return data.eom_session([pd.Timestamp(eom)]).iloc[0]


# A score ranked within each month among universe rows, to [-1, 1].
def month_rank(t: Table, values: pd.Series) -> pd.Series:
    eom = t.x.loc[values.index, "eom"]
    return values.groupby(eom).transform(ranks.unit_rank)


# Pooled Spearman of a within-month ranked score with the label rank.
def pooled_ic(t: Table, score: pd.Series) -> float:
    both = pd.concat([score, t.x.loc[score.index, LABEL]], axis=1).dropna()
    return float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank()))


# A score for choosing: a missing one never wins.
def finite(score: float) -> float:
    return round(score, 12) if np.isfinite(score) else -np.inf


# The SUE model's out-of-sample column: one fit a year, as walk-forward.
def sue_column(t: Table, stocks: str, leaves: int, children: int) -> pd.Series:
    f = t.feats[stocks][t.chars]
    x = t.x.loc[f.index, ["eom", "sue_target", "sue_public"]]
    out = pd.Series(np.nan, index=f.index)
    for year in SUE_YEARS:
        cut = close_of(f"{year - 1}-12-31")
        fit = x["sue_target"].notna().to_numpy() & dataset.public_by(x, "sue_public", cut)
        if fit.sum() < children:
            continue
        # The target is ranked among the fit's rows only, all public by the cut.
        y = x[fit].groupby("eom")["sue_target"].transform(ranks.unit_rank)
        model = models.lgbm(f[fit], y.to_numpy(), leaves, children, mono=False)
        rows = t.rows(stocks, f"{year - 1}-12-31", f"{year}-11-30")
        out.loc[rows] = models.predict(model, f.loc[rows])
    return out


# The SUE model's grid and gate on 2019-01..2020-08 universe months.
def sue_model(t: Table) -> dict:
    out = {}
    for s in dataset.STOCKS:
        cells = []
        for leaves in models.LEAVES:
            for children in models.CHILDREN:
                col = sue_column(t, s, leaves, children)
                rows = t.rows(s, SUE_FIRST, SUE_LAST, universe_only=True)
                frame = t.x.loc[rows, ["eom", "sue_target"]].assign(f=col.loc[rows])
                ic = (
                    frame.dropna()
                    .groupby("eom")
                    .apply(lambda g: g["f"].rank().corr(g["sue_target"].rank()))
                )
                cells.append(
                    {
                        "leaves": leaves,
                        "children": children,
                        "mean_ic": float(ic.mean()),
                        "nw_t": agreement.nw_t(ic),
                        "months": len(ic),
                        "column": col,
                    }
                )
        # Highest mean IC; ties to fewer leaves, then larger leaves' size.
        key = lambda c: (-finite(c["mean_ic"]), c["leaves"], -c["children"])  # noqa: E731
        best = sorted(cells, key=key)[0]
        out[s] = {
            "cells": [{k: v for k, v in c.items() if k != "column"} for c in cells],
            "chosen": {k: v for k, v in best.items() if k != "column"},
            "passes": best["mean_ic"] > 0,
            "column": best["column"],
        }
    return out


# One set's input matrix: the 147, SYY-10 and, if it passed, the SUE.
def inputs(t: Table, stocks: str, sue: dict) -> pd.DataFrame:
    f = t.feats[stocks]
    cols = [*t.chars, "syy"]
    if sue[stocks]["passes"]:
        col = sue[stocks]["column"]
        frame = t.x.loc[f.index, ["eom", "in_universe"]].assign(sue_forecast=col)
        ranked = dataset.ranked(frame, ["sue_forecast"], stocks).astype(np.float32)
        f = f.assign(sue_forecast=ranked["sue_forecast"])
        cols.append("sue_forecast")
    return f[cols]


# Rows of a set with a label public by a cut, for one horizon.
def training_rows(t: Table, stocks: str, horizon: int, cut) -> pd.Index:
    label, clock = dataset.label_column(horizon, stocks), f"month_available_h{horizon}"
    x = t.x.loc[t.feats[stocks].index, [label, clock]]
    ok = x[label].notna().to_numpy() & dataset.public_by(x, clock, cut)
    return x.index[ok]


# Every member fitted at one cut, forecasting the given rows.
def fit_members(t, f, stocks, horizon, cut, rows, cells) -> dict:
    dataset.check_inputs(list(f.columns), t.chars)
    train = training_rows(t, stocks, horizon, cut)
    y = t.x.loc[train, dataset.label_column(horizon, stocks)].to_numpy()
    out = {}
    for kind, setting in cells:
        if kind == "lgbm":
            model = models.lgbm(f.loc[train], y, *setting)
        elif kind == "enet":
            model = models.enet(f.loc[train], y, *setting)
        else:
            model = models.nn3(f.loc[train], y, setting)
        out[(kind, setting)] = pd.Series(models.predict(model, f.loc[rows]), index=rows)
    return out


# The blend: (1 - w) z(1/N) + w z(ML), re-standardised, sector-demeaned.
def blend(t: Table, ml: pd.Series, w: float) -> pd.Series:
    x = t.x.loc[ml.index, ["eom", "sector"]]
    syy = t.feats["universe"].loc[ml.index, "syy"]

    # A within-month z-score.
    def z(v):
        return v.groupby(x["eom"]).transform(lambda g: (g - g.mean()) / g.std(ddof=0))

    mixed = z((1 - w) * z(syy) + w * z(ml))
    return mixed - mixed.groupby([x["eom"], x["sector"]]).transform("mean")


# The ML forecast: the mean of the three members' within-month ranks.
def ensemble(t: Table, parts: list[pd.Series]) -> pd.Series:
    return pd.concat([month_rank(t, p) for p in parts], axis=1).mean(axis=1)


# Validation: members first, then the 96 cells on the final blend.
def validate(t: Table) -> dict:
    sue = sue_model(t)
    cut = close_of(VALID_FIRST)
    rows = t.rows("universe", VALID_FIRST, VALID_LAST, universe_only=True)
    cells, members = [], {}
    for s in dataset.STOCKS:
        f = inputs(t, s, sue)
        for h in HORIZONS:
            grid = [("enet", c) for c in models.ENET] + [("nn", l1) for l1 in models.NN_L1]
            grid += [("lgbm", (lv, ch)) for lv in models.LEAVES for ch in models.CHILDREN]
            fits = fit_members(t, f, s, h, cut, rows, grid)
            scores = {k: pooled_ic(t, month_rank(t, v)) for k, v in fits.items()}
            # Each member's best by its own IC; ties to more regularisation.
            enet = max(models.ENET, key=lambda c: (finite(scores[("enet", c)]), c))
            nn = max(models.NN_L1, key=lambda c: (finite(scores[("nn", c)]), c))
            members[(s, h)] = {
                "enet": enet,
                "nn": nn,
                "scores": {f"{k[0]} {k[1]}": v for k, v in scores.items()},
            }
            for lv in models.LEAVES:
                for ch in models.CHILDREN:
                    parts = [fits[("lgbm", (lv, ch))], fits[("enet", enet)], fits[("nn", nn)]]
                    ml = ensemble(t, parts)
                    for w in WEIGHTS:
                        cells.append(
                            {
                                "leaves": lv,
                                "children": ch,
                                "w_ml": w,
                                "horizon": h,
                                "stocks": s,
                                "ic": pooled_ic(t, blend(t, ml, w)),
                            }
                        )
    # Best IC; ties: leaves, size, w near 0.5 then smaller, h1, universe.
    chosen = sorted(
        cells,
        key=lambda c: (
            -finite(c["ic"]),
            c["leaves"],
            -c["children"],
            abs(c["w_ml"] - 0.5),
            c["w_ml"],
            c["horizon"],
            c["stocks"] != "universe",
        ),
    )[0]
    if not np.isfinite(chosen["ic"]):
        raise RuntimeError("no grid cell has a validation IC")
    sue_out = {s: {k: v for k, v in r.items() if k != "column"} for s, r in sue.items()}
    return {
        "cells": cells,
        "chosen": chosen,
        "sue_model": sue_out,
        "rows": len(rows),
        "members": {f"{s} h{h}": m for (s, h), m in members.items()},
    }


# Walk-forward forecasts of the chosen design, refit each January.
def walk(t: Table, chosen: dict, members: dict) -> pd.DataFrame:
    s, h = chosen["stocks"], chosen["horizon"]
    sue = sue_model_at(t, s, members["sue"])
    f = inputs(t, s, sue)
    m = members[f"{s} h{h}"]
    cells = [
        ("lgbm", (chosen["leaves"], chosen["children"])),
        ("enet", tuple(m["enet"])),
        ("nn", m["nn"]),
    ]
    out = []
    for year in RETURN_YEARS:
        rows = t.rows("universe", f"{year - 1}-12-31", f"{year}-11-30", universe_only=True)
        if len(rows) == 0:
            continue
        fits = fit_members(t, f, s, h, close_of(f"{year - 1}-12-31"), rows, cells)
        parts = [fits[c] for c in cells]
        ml = ensemble(t, parts)
        ranked = pd.concat([month_rank(t, p) for p in parts], axis=1)
        frame = t.x.loc[rows, ["permno", "eom"]].assign(
            lgbm=parts[0],
            enet=parts[1],
            nn=parts[2],
            ml=ml,
            spread=ranked.std(axis=1, ddof=0),
            z=blend(t, ml, chosen["w_ml"]),
            z_syy=blend(t, ml, 0.0),
            fit_year=year,
        )
        out.append(frame)
    out = pd.concat(out, ignore_index=True)
    assert out["z"].notna().all(), "a universe stock has no forecast"
    return out


# The chosen SUE settings' column for one set, or none if it failed.
def sue_model_at(t: Table, stocks: str, sue: dict) -> dict:
    other = {s: {"passes": False} for s in dataset.STOCKS}
    if not sue[stocks]["passes"]:
        return other
    c = sue[stocks]["chosen"]
    return other | {
        stocks: {"passes": True, "column": sue_column(t, stocks, c["leaves"], c["children"])}
    }


# The noise trap: a pure-noise input's SHAP share stays under chance.
def trap(t: Table, chosen: dict, members: dict) -> dict:
    s, h = chosen["stocks"], chosen["horizon"]
    f = inputs(t, s, sue_model_at(t, s, members["sue"]))
    train = training_rows(t, s, h, close_of(VALID_FIRST))
    rows = t.rows("universe", VALID_FIRST, VALID_LAST, universe_only=True)
    y = t.x.loc[train, dataset.label_column(h, s)].to_numpy()
    shares = []
    for seed in TRAP_SEEDS:
        rng = np.random.default_rng(seed)
        noise = pd.Series(rng.standard_normal(len(f)), index=f.index)
        g = f.assign(noise=noise.groupby(t.x.loc[f.index, "eom"]).transform(ranks.unit_rank))
        model = models.lgbm(g.loc[train], y, chosen["leaves"], chosen["children"])
        contrib = np.abs(model.predict(g.loc[rows].to_numpy(np.float32), pred_contrib=True))
        mean = contrib[:, :-1].mean(axis=0)
        shares.append(float(mean[list(g.columns).index("noise")] / mean.sum()))
    chance = 1.0 / g.shape[1]
    top = float(np.quantile(shares, 0.95))
    return {"shares": shares, "p95": top, "chance": chance, "passes": top < chance}


# Counts only: rows, labels and SUE targets per set and year.
def check(t: Table) -> dict:
    out = {}
    for s in dataset.STOCKS:
        x = t.x.loc[t.feats[s].index]
        year = x["eom"].dt.year
        out[s] = {
            "rows": len(x),
            "labels_h1": x.groupby(year)[dataset.label_column(1, s)].count().to_dict(),
            "labels_h3": x.groupby(year)[dataset.label_column(3, s)].count().to_dict(),
            "sue_targets": x.groupby(year)["sue_target"].count().to_dict(),
        }
    return out


# A stage's result file at a commit; one run each, never overwritten.
def result_path(stage: str, head: str):
    return OUT / f"{stage}_{head[:12]}.json"


# Writes a stage's result with the gates' stamp and library versions.
def write(stage: str, result: dict, head: str) -> None:
    import lightgbm
    import sklearn
    import torch

    if gates.commit() != head:
        raise RuntimeError("HEAD moved during the run")
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = {"nn": [models.NN_SEEDS.start, models.NN_SEEDS.stop - 1], "lgbm": 42,
             "trap": [TRAP_SEEDS.start, TRAP_SEEDS.stop - 1]}  # fmt: skip
    stamp = gates.stamp(head, seeds) | {
        "libraries": {
            "lightgbm": lightgbm.__version__,
            "torch": torch.__version__,
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        }  # fmt: skip
    }
    path = result_path(stage, head)
    path.write_text(json.dumps({"stamp": stamp, stage: result}, indent=1, default=str))
    print(path)


# The validation file at this commit, needed by walk and trap.
def chosen_at(head: str) -> dict:
    path = result_path("validate", head)
    if not path.exists():
        raise SystemExit(f"run the validate stage first at this commit ({path.name})")
    done = json.loads(path.read_text())
    sha = hashlib.sha256(gates.PROTOCOL.read_bytes()).hexdigest()
    if done["stamp"]["commit"] != head or done["stamp"]["protocol_sha256"] != sha:
        raise SystemExit(f"{path.name} is from another commit or protocol")
    v = done["validate"]
    sue = {s: {"passes": r["passes"], "chosen": r["chosen"]} for s, r in v["sue_model"].items()}
    return {"chosen": v["chosen"], "members": v["members"] | {"sue": sue}}


# python -m fiam.v4.forecast.grid check | validate | walk | trap
if __name__ == "__main__":
    asked = sys.argv[1:] or ["check"]
    for stage in asked:
        if stage not in STAGES:
            raise SystemExit(f"unknown stage {stage}: {', '.join(STAGES)}")
    head = None if asked == ["check"] else gates.commit()
    for stage in asked:
        if stage != "check" and result_path(stage, head).exists():
            raise SystemExit(f"{stage} already ran at this commit: one run each")
    table = Table(sources.characteristics())
    for stage in asked:
        if stage == "check":
            print(json.dumps(check(table), indent=1, default=str))
        elif stage == "validate":
            write("validate", validate(table), head)
        elif stage == "walk":
            c = chosen_at(head)
            frame = walk(table, c["chosen"], c["members"])
            frame.to_parquet(OUT / f"forecasts_{head[:12]}.parquet", index=False)
            write("walk", {"rows": len(frame), "formations": frame["eom"].nunique()}, head)
        else:
            c = chosen_at(head)
            write("trap", trap(table, c["chosen"], c["members"]), head)
