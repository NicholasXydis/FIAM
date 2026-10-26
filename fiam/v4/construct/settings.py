# Step 7's derived settings in the order the checklist fixes.

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import numpy as np
import pandas as pd

from fiam.v4 import data, gates
from fiam.v4.construct import book, costs, optimizer

OUT = book.OUT
# The derived settings the exam reads, committed with the code.
SETTINGS = gates.ROOT / "versions" / "v4" / "settings.json"
# The grids (PLAN §8.3, §8.4, §8.8) and the bars that choose from them.
RIDGES, STYLE_CAPS = (1, 3, 10, 30, 100, 300), (0.05, 0.10, 0.20, 0.30, 0.50)
MARGINS, BANDS = (0.01, 0.03, 0.05, 0.08), (0.01, 0.02, 0.03)
NAMES_TARGET, SHARE_BAR, TC_STEP, A4_RANGE = 425, 0.35, 0.03, (0.2, 1.0)
# Derivations run at base gross C_t - 0.05; later settings start here.
BASE_MARGIN = 0.05
START = {"ridge": 30.0, "risk_lambda": 0.52, "style_cap": 0.50}
# Parallel builds at once: each holds about 7 GB of 24.
WORKERS = 2


# A settings function: gross C_t less the margin, the rest fixed.
def at(margin: float, **kw):
    return lambda eom, x, cap: optimizer.Settings(gross=cap - margin, **kw)


# One build's month table, run in its own process.
def run(kw: dict, diagnostics: bool = False) -> pd.DataFrame:
    log: dict = {}
    book.build(at(BASE_MARGIN, **kw), book.Context(), log, diagnostics)
    return pd.DataFrame(log["months"])


# Several builds in parallel, keyed by their setting.
def grid(name: str, values, base: dict, diagnostics: bool = False) -> dict:
    jobs = {v: base | {name: v} for v in values}
    with ProcessPoolExecutor(WORKERS) as pool:
        futures = {v: pool.submit(run, kw, diagnostics) for v, kw in jobs.items()}
        return {v: fut.result() for v, fut in futures.items()}


# One margin's live books through the engine: mean monthly trading cost.
def margin_cost(d: float, kw: dict) -> dict:
    from fiam.v4 import daily_book
    from fiam.v4.construct import simulate

    result, _ = simulate.run(book.Context(), at(d, **kw), book.LAST + pd.offsets.MonthEnd(1))
    # Each close's cost over its own pre-trade NAV; no return is read.
    daily = result.daily
    share = (daily["cost"] / daily["nav_pre"]).groupby(daily.index.to_period("M")).sum()
    # The first build's month is exempt, as the budget's own months were.
    share = share[share.index > pd.Period(book.FIRST, "M") + 1]
    return {"cost": float(share.mean()), "breach_days": int(len(daily_book.breaches(result)))}


# Lever A4: 1 minus the mean month-to-month Spearman of z.
def a4_rate(f: pd.DataFrame) -> float:
    wide = f.pivot_table(index="permno", columns="eom", values="z")
    pairs = [wide.iloc[:, i].corr(wide.iloc[:, i + 1], method="spearman")
             for i in range(wide.shape[1] - 1)]  # fmt: skip
    return float(np.clip(1 - np.nanmean(pairs), *A4_RANGE))


# Every derivation before the commit in the checklist's order, logged.
def derive() -> dict:
    out: dict = {}
    # Shared caches built once here, so no two workers write one file.
    book.factor_returns()
    costs.spread_ratios()
    data._CACHE.clear()
    # The main process stays light: every build runs in its own worker.
    f = book.forecasts()
    out["alpha_scale"] = book.alpha_scale(f)
    base = grid("ridge", [START["ridge"]], START)[START["ridge"]]
    out["cost_budget"] = float(base["cost"].iloc[1:].mean())
    out["base"] = base.to_dict("records")
    kw = START | {"cost_budget": out["cost_budget"]}
    ridges = grid("ridge", RIDGES, kw)
    names = {r: float(m["names"].median()) for r, m in ridges.items()}
    # Closest median name count to 425; ties to v1's starting ridge 30.
    tie = START["ridge"]
    out["ridge"] = min(RIDGES, key=lambda r: (abs(names[r] - NAMES_TARGET), abs(r - tie)))
    out["ridge_names"] = names
    m = ridges[out["ridge"]]
    early = m[pd.to_datetime(m["eom"]).dt.year == 2017]
    # v2's rule: the risk penalty matches the ridge's on the 2017 books.
    penalty = float((out["ridge"] * early["norm"] * early["w2"]).sum())
    out["risk_lambda"] = penalty / float(early["risk"].sum())
    kw |= {"ridge": out["ridge"], "risk_lambda": out["risk_lambda"]}
    caps = grid("style_cap", STYLE_CAPS, kw, diagnostics=True)
    shares = {b: (float(m["share_ours"].median()), float(m["share_ff"].median()))
              for b, m in caps.items()}  # fmt: skip
    fits = [b for b in STYLE_CAPS if max(shares[b]) <= SHARE_BAR]
    out["style_cap"] = max(fits) if fits else min(STYLE_CAPS)
    out["style_cap_shares"] = {str(b): v for b, v in shares.items()}
    kw |= {"style_cap": out["style_cap"]}
    # d: the smallest margin whose live books' costs fit the budget.
    with ProcessPoolExecutor(WORKERS) as pool:
        spent = dict(zip(MARGINS, pool.map(margin_cost, MARGINS, [kw] * len(MARGINS))))
    fit = [d for d in MARGINS if spent[d]["cost"] <= out["cost_budget"]]
    out["margin"] = min(fit) if fit else max(MARGINS)
    out["margin_costs"] = {str(d): c for d, c in spent.items()}
    # The band: 1% is the chosen b's build; wider only for +0.03 TC each.
    bands = {BANDS[0]: caps[out["style_cap"]]}
    bands |= grid("sector_band", BANDS[1:], kw, diagnostics=True)
    tc = {b: float(m["tc"].median()) for b, m in bands.items()}
    band = BANDS[0]
    for wider in BANDS[1:]:
        if tc[wider] - tc[band] >= TC_STEP:
            band = wider
        else:
            break
    out["sector_band"], out["sector_band_tc"] = band, {str(b): v for b, v in tc.items()}
    out["a4_rate"] = a4_rate(f)
    final = optimizer.Settings(gross=0.0, **kw, sector_band=band, speed=out["a4_rate"])
    out["settings"] = asdict(final)
    return out


# python -m fiam.v4.construct.settings: every derivation, written out.
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = derive()
    (OUT / "settings_log.json").write_text(json.dumps(result, indent=1, default=str))
    summary = {k: v for k, v in result.items() if k != "base"}
    SETTINGS.write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(json.dumps(summary, indent=1, default=str))
    sys.exit(0)
