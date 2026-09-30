# Why nothing is chosen from history: subset sweep, budgeted search, atlas. Writes selection.json.

import itertools
import json

import numpy as np
import pandas as pd
from scipy.stats import norm

from fiam import book as P
from fiam import paths

OUT = paths.EXHIBITS
SUBSET_SIZE = 5

# The sweep's early window is decisions through 2022, so holdings through January 2023.
SWEEP_SPLIT = "2023-02-01"

# The search may look at holding months through 2023 and is judged on 2024 on.
SEARCH_END, BUDGET, SEED = "2024-01-01", 200, 42

# The atlas reads each characteristic's direction before this month and judges it after.
ATLAS_SPLIT = "2021-01-01"

# Harvey, Liu and Zhu's hurdle for a new factor once you allow for everything tried before it.
HLZ_T = 3.0


# Annualized ratio of a spread's mean to its volatility. No hurdle, it is a spread.
def ir(series: pd.Series) -> float:
    if len(series) < 6 or series.std() == 0:
        return float("nan")
    return float(series.mean() / series.std() * np.sqrt(12))


# Mean over its standard error. Too few months or no variation gives no answer, not zero.
def t_stat(series: pd.Series) -> float:
    s = series.dropna()
    return float(s.mean() / s.std() * np.sqrt(len(s))) if len(s) > 6 and s.std() else np.nan


# Every subset on both halves, and what picking the best-looking one early would have earned.
def sweep(spreads: dict, baseline: pd.Series) -> dict:
    rows = []
    for cols, s in spreads.items():
        early, late = s[s.index < SWEEP_SPLIT], s[s.index >= SWEEP_SPLIT]
        rows.append(
            dict(signals="+".join(cols), ir_early=ir(early), ir_late=ir(late), ir_full=ir(s))
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "subset_sweep.csv", index=False, lineterminator="\n")
    best = table.loc[table["ir_early"].idxmax()]
    return dict(
        n_subsets=int(len(table)),
        ir_full_min=float(table["ir_full"].min()),
        ir_full_max=float(table["ir_full"].max()),
        early_late_correlation=float(table["ir_early"].corr(table["ir_late"])),
        best_on_early_then_earned=float(best["ir_late"]),
        median_late_ir=float(table["ir_late"].median()),
        all_twelve_ir_full=ir(baseline),
    )


# A fixed budget drawn at random, the best kept, then scored once on the sealed period.
def search(spreads: dict, baseline: pd.Series) -> dict:
    subsets = list(spreads)
    picks = np.random.default_rng(SEED).choice(len(subsets), size=BUDGET, replace=False)
    rows = []
    for i in picks:
        s = spreads[subsets[i]]
        rows.append(
            dict(
                signals="+".join(subsets[i]),
                ir_search=ir(s[s.index < SEARCH_END]),
                ir_sealed=ir(s[s.index >= SEARCH_END]),
            )
        )
    table = pd.DataFrame(rows).dropna()
    chosen = table.loc[table["ir_search"].idxmax()]
    return dict(
        budget=int(len(table)),
        subset_size=SUBSET_SIZE,
        search_window=f"holding months 2021-01 to {SEARCH_END[:7]}, exclusive",
        chosen_signals=chosen["signals"],
        chosen_ir_in_search=float(chosen["ir_search"]),
        chosen_ir_in_sealed=float(chosen["ir_sealed"]),
        median_ir_in_sealed=float(table["ir_sealed"].median()),
        rank_of_chosen_in_sealed=int((table["ir_sealed"] > chosen["ir_sealed"]).sum() + 1),
        search_vs_sealed_correlation=float(table["ir_search"].corr(table["ir_sealed"])),
        all_twelve_ir_in_sealed=ir(baseline[baseline.index >= SEARCH_END]),
    )


# Top-decile minus bottom-decile return for one month. Needs ten real buckets to mean anything.
def decile(group: pd.DataFrame) -> float:
    if group["s"].nunique() < 10:
        return np.nan
    buckets = pd.qcut(group["s"].rank(method="first"), 10, labels=False)
    return float(group.loc[buckets == 9, "dm"].mean() - group.loc[buckets == 0, "dm"].mean())


# Benjamini-Hochberg: the expected share of false discoveries among everything called real.
def q_values(p: np.ndarray) -> np.ndarray:
    order = np.argsort(p)
    ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


# Every characteristic through the book's neutralization, direction from before 2021 only.
def atlas(df: pd.DataFrame, cols: list[str]) -> dict:
    df = df.assign(holding_month=(df["eom"] + pd.offsets.MonthBegin(1)).dt.normalize())
    df["dm"] = df["ret_exc_lead1m"] - df.groupby("eom")["ret_exc_lead1m"].transform("mean")
    rows = []
    for col in cols:
        signal = P.neutralize(df, P.rank_z(df, col))
        work = df.loc[df[col].notna(), ["holding_month", "dm"]].assign(s=signal.fillna(0.0))
        deciles = work.groupby("holding_month").apply(decile, include_groups=False)
        m = pd.DataFrame(dict(spread=P.spread(df, signal), decile=deciles))
        before, after = m[m.index < ATLAS_SPLIT], m[m.index >= ATLAS_SPLIT]
        t_before, t_after = t_stat(before["spread"]), t_stat(after["spread"])
        # The direction comes from the before window only, so the after window is a real test.
        direction = float(np.sign(t_before)) if np.isfinite(t_before) else 0.0
        rows.append(
            dict(
                characteristic=col,
                in_book=col in P.SIGNALS,
                theory_sign=P.SIGNALS.get(col, 0),
                coverage=float(df[col].notna().mean()),
                t_before=t_before,
                t_after=t_after,
                decile_spread_before_annual=float(before["decile"].mean() * 12),
                decile_spread_after_annual=float(after["decile"].mean() * 12),
                direction_from_before=direction,
                signed_t_after=float(direction * t_after),
            )
        )
    table = pd.DataFrame(rows)
    table["q_before"] = q_values(2 * norm.sf(table["t_before"].abs().fillna(0.0).to_numpy()))
    table.to_csv(OUT / "factor_atlas.csv", index=False, lineterminator="\n")
    valid = table.dropna(subset=["t_before", "t_after"])
    strong = valid[valid["t_before"].abs() >= HLZ_T]
    return dict(
        characteristics=int(len(table)),
        before_after_t_correlation=float(valid["t_before"].corr(valid["t_after"])),
        share_keeping_direction=float((valid["signed_t_after"] > 0).mean()),
        cleared_hlz_before=int(len(strong)),
        of_those_still_significant_after=int((strong["signed_t_after"] >= 1.96).sum()),
        discoveries_at_q_10pct_before=int((table["q_before"] <= 0.10).sum()),
        book_signals_theory_sign_matches_before=int(
            (table["in_book"] & (table["theory_sign"] == table["direction_from_before"])).sum()
        ),
        split=ATLAS_SPLIT,
        hurdle_t=HLZ_T,
    )


# The subset sweep, the budgeted search and the atlas.
def main() -> None:
    cols = P.characteristics()
    panel = P.load_panel(extra=tuple(cols))
    OUT.mkdir(parents=True, exist_ok=True)

    # Every spread computed once. The search draws from the same 792 the sweep scores.
    book = P.screen(panel).dropna(subset=["ret_exc_lead1m", "beta_60m"])
    subsets = itertools.combinations(P.SIGNALS, SUBSET_SIZE)
    composite = {c: P.scores(book, {s: P.SIGNALS[s] for s in c}).mean(axis=1) for c in subsets}
    spreads = {c: P.spread(book, P.neutralize(book, x)) for c, x in composite.items()}
    baseline = P.spread(book, P.neutralize(book, P.scores(book, P.SIGNALS).mean(axis=1)))

    history = P.screen(panel, "2015-01-31", P.LAST_FORECAST)
    out = dict(
        what="Why nothing is chosen from history. The sweep and search pick among the 12; the "
        "atlas reads all 147 with direction from 2015-2020 and judges them on 2021-2026.",
        subset_sweep=sweep(spreads, baseline),
        search_control=search(spreads, baseline),
        atlas=atlas(history.dropna(subset=["ret_exc_lead1m", "beta_60m"]), cols),
    )
    (OUT / "selection.json").write_text(json.dumps(out, indent=2), encoding="utf-8", newline="\n")
    s, c, a = out["subset_sweep"], out["search_control"], out["atlas"]
    print(f"{s['n_subsets']} subsets, IR {s['ir_full_min']:.2f} to {s['ir_full_max']:.2f}")
    looked, sealed = c["chosen_ir_in_search"], c["chosen_ir_in_sealed"]
    print(f"search: {looked:+.2f} where it looked, {sealed:+.2f} sealed")
    print(f"atlas: before-after t correlation {a['before_after_t_correlation']:+.2f}")


if __name__ == "__main__":
    main()
