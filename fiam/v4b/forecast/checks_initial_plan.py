# Follow-up checks on the initial-plan run: sector-neutral IC, GBT vs MLP.

import json

import pandas as pd

from fiam.v4b.forecast import data, evaluate, initial_plan, targets

OUT = initial_plan.OUT


# Writes checks.json beside the initial-plan report.
def main() -> dict:
    h = pd.read_parquet(OUT / "predictions_heldout.parquet")
    g = pd.read_parquet(
        data.PANEL, columns=["permno", "eom", "gics"], filters=[("eom", "<=", data.BLIND)]
    )
    g["eom"] = pd.to_datetime(g["eom"]).astype("datetime64[ns]")
    h = h.merge(g, on=["permno", "eom"], how="left")
    h["y21_sector"] = targets.sector_demeaned(h, "y21")
    names = [c for c in initial_plan.CONFIGS if c in h]
    out = {"ic_within_sector": {}, "spread10_within_sector": {}, "spread10_by_year": {}}
    for n in names:
        ic = evaluate.monthly_ic(h["eom"], h[n], h["y21_sector"])
        sp = initial_plan.spread(h["eom"], h[n], h["y21_sector"])
        raw = initial_plan.spread(h["eom"], h[n], h["y21"])
        out["ic_within_sector"][n] = evaluate.summary(ic)["all"]
        out["spread10_within_sector"][n] = evaluate.mean_t(sp)
        out["spread10_by_year"][n] = {
            str(y): float(v.mean()) for y, v in raw.groupby(raw.index.year)
        }
    ics = {n: evaluate.monthly_ic(h["eom"], h[n], h["y21"]) for n in ("G1_gbt", "M1_mlp")}
    sps = {n: initial_plan.spread(h["eom"], h[n], h["y21"]) for n in ("G1_gbt", "M1_mlp")}
    out["gbt_minus_mlp"] = {
        "ic": evaluate.paired(ics["G1_gbt"], ics["M1_mlp"]),
        "spread10": evaluate.paired(sps["G1_gbt"], sps["M1_mlp"]),
    }
    (OUT / "checks.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


if __name__ == "__main__":
    r = main()
    for n, v in r["ic_within_sector"].items():
        s = r["spread10_within_sector"][n]
        print(
            f"{n:20s} sectorIC {v['mean']:+.4f} t {v['t']:+.2f}",
            f"| sectorSpread {s['mean'] * 100:+.2f}% t {s['t']:+.2f} | by year",
            {k: round(x * 100, 2) for k, x in r["spread10_by_year"][n].items()},
        )
    print("GBT-MLP", r["gbt_minus_mlp"])
