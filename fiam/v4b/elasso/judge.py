# Judges the E-LASSO forecasts on the same harness and months as initial_plan.

import json
from pathlib import Path

import pandas as pd

from fiam.v4b.forecast import evaluate, initial_plan, run

RUN = Path(__file__).resolve().parents[1] / "out" / "elasso" / "run"
OUT = RUN.parent
# Held-out window shared with initial_plan: targets 2017-01..2020-12.
WINDOW = ("2016-12-31", "2020-11-30")
REFERENCES = ("M1_mlp", "G1_gbt", "R2_hier")


# Forecast columns keyed by formation eom and permno.
def forecasts(run_dir: Path = RUN) -> pd.DataFrame:
    parts = []
    for name, cols in (
        ("forecastElasso", None),
        ("forecastSlasso", None),
        ("forecastClasso", ["forecast"]),
    ):
        f = pd.read_parquet(run_dir / f"{name}.parquet")
        keep = cols or [c for c in f.columns if c.startswith("Ma")]
        tag = name.replace("forecast", "")
        f = f[["date", "permno", *keep]].rename(columns={c: f"{tag}_{c}" for c in keep})
        f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
        parts.append(f.drop(columns="date").set_index(["eom", "permno"]))
    return pd.concat(parts, axis=1).reset_index()


# Within-sector spread and IC on the sector-demeaned 21d label.
def within_sector(u, rows, score) -> dict:
    f = u.loc[rows]
    ic = evaluate.monthly_ic(f["eom"], score, f["y21_sector"])
    sp = initial_plan.spread(f["eom"], score, f["y21_sector"])
    return {"ic": evaluate.mean_t(ic), "spread10": evaluate.mean_t(sp)}


# Writes report.json: E-LASSO family vs the initial-plan references.
def main() -> dict:
    u, *_, factors, _ = initial_plan.prepare()
    fc = forecasts()
    key = u[["eom", "permno"]].reset_index().rename(columns={"index": "row"})
    fc = fc.merge(key, on=["eom", "permno"], how="inner")
    fc = fc[fc["eom"].between(pd.Timestamp(WINDOW[0]), pd.Timestamp(WINDOW[1]))]
    ref = pd.read_parquet(initial_plan.OUT / "predictions_heldout.parquet")
    ref = ref.reset_index(drop=True).merge(key, on=["eom", "permno"], how="inner")
    report, series = {}, {}
    cols = [c for c in fc.columns if c.split("_")[0] in ("Elasso", "Slasso", "Classo")]
    for name, frame in [(c, fc) for c in cols] + [(r, ref) for r in REFERENCES]:
        s = pd.Series(frame[name].to_numpy(), index=frame["row"].to_numpy()).dropna()
        report[name] = initial_plan.judge(u, factors, s) | {
            "within_sector": within_sector(u, s.index.to_numpy(), s.to_numpy())
        }
        f = u.loc[s.index]
        series[name] = (
            evaluate.monthly_ic(f["eom"], s.to_numpy(), f[run.LABEL]),
            initial_plan.spread(f["eom"], s.to_numpy(), f[run.LABEL]),
        )
    report["paired"] = {
        f"{a}_minus_{b}": {
            "ic": evaluate.paired(series[a][0], series[b][0]),
            "spread10": evaluate.paired(series[a][1], series[b][1]),
        }
        for a in cols
        for b in REFERENCES
    }
    enc = pd.read_parquet(RUN / "coefEncompass.parquet")
    report["encompassing_theta_mean"] = {
        c: float(enc[c].mean()) for c in enc.columns if c.startswith("Ma")
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=run._plain) + "\n")
    return report


# One table line per forecast, the same columns as LESSONS.
def table(r: dict) -> None:
    names = [k for k in r if k not in ("paired", "encompassing_theta_mean")]
    print(
        f"{'forecast':16s} {'IC':>7} {'t':>6} {'IC_sh':>7} {'spr%':>6} {'t':>6} "
        f"{'secSpr%':>7} {'t':>6} {'alpha%':>6} {'t':>6} {'auto':>5} {'churn':>5}"
    )
    for n in names:
        x = r[n]
        a, w, s = x["spread10_factor_alpha"], x["within_sector"]["spread10"], x["spread10"]["all"]
        print(
            f"{n:16s} {x['ic']['all']['mean']:7.4f} {x['ic']['all']['t']:6.2f} "
            f"{x['ic_short_eligible']['all']['mean']:7.4f} {s['mean'] * 100:6.2f} "
            f"{s['t']:6.2f} {w['mean'] * 100:7.2f} {w['t']:6.2f} {a['alpha'] * 100:6.2f} "
            f"{a['t']:6.2f} {x['persistence']['rank_autocorr']:5.2f} "
            f"{x['persistence']['top_decile_churn']:5.2f}"
        )
    print(
        "theta (weight on C-LASSO)",
        {k: round(v, 3) for k, v in r["encompassing_theta_mean"].items()},
    )
    for k, v in r["paired"].items():
        if k.startswith("Elasso_MaInf") or k.startswith("Elasso_Ma1_"):
            print(
                k,
                f"dIC {v['ic']['mean']:+.4f} ± {v['ic']['se']:.4f}",
                f"dSpread {v['spread10']['mean'] * 100:+.2f}% ± {v['spread10']['se'] * 100:.2f}",
            )


if __name__ == "__main__":
    table(main())
