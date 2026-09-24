# Earnings timing from 8-K Item 2.02, decided on 2016-2020 before 2021-2026 is ever computed.

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
import benchmarks as B
import pipeline as P

FILINGS = Path("data/8k_20150101_20260831_identified.parquet")
OUT = Path("submission/exhibits")

DESIGN = ("2015-12-31", "2020-11-30")
TEST = (P.FIRST_FORECAST, P.LAST_FORECAST)

# Written before stage one ran: +0.10 IR on 2016-2020, beta inside 0.15, both tails rising.
RULE = dict(min_ir_gain=0.10, max_abs_beta=0.15, monotone_tails=True)

# Signals judged on the book's accounting side. Lagged in the availability stress test.
ACCOUNTING = [
    "be_me",
    "qmj",
    "at_gr1",
    "niq_su",
    "ope_be",
    "o_score",
    "gp_at",
    "noa_gr1a",
    "eqnetis_at",
]

# The three declared variants. Each changes one thing and keeps everything else shipped.
WITHOUT_NIQ = {k: v for k, v in P.SIGNALS.items() if k != "niq_su"}
VARIANTS = {
    # Firms expected to announce next month earn a premium (Frazzini-Lamont 2007).
    "announcement_premium": {**P.SIGNALS, "eap": +1},
    # Earnings and revenue surprise together (Jegadeesh-Livnat 2006) in place of earnings alone.
    "combined_surprise": {**WITHOUT_NIQ, "surprise": +1},
    # The earnings surprise only while it is fresh, the months drift is documented to be strong.
    "fresh_surprise": {**WITHOUT_NIQ, "niq_su_fresh": +1},
}


# Months in which each stock filed an Item 2.02, the earnings release.
def release_months() -> set:
    table = pq.read_table(FILINGS, columns=["permno", "filing_date", "items"]).to_pandas()
    table = table[table["items"].apply(lambda x: x is not None and "2.02" in list(x))]
    months = pd.to_datetime(table["filing_date"]).dt.to_period("M")
    return set(zip(table["permno"].astype(int), months))


# The three earnings features, each built only from what was known at month end.
def features(panel: pd.DataFrame, releases: set) -> pd.DataFrame:
    panel = panel.sort_values(["permno", "eom"]).copy()
    month = panel["eom"].dt.to_period("M")
    keys = list(zip(panel["permno"].astype(int), month))

    # A release two months ago (quarterly) or eleven (annual) means one is due next month.
    def released(lag: int) -> np.ndarray:
        return np.array([(p, m - lag) in releases for p, m in keys])

    # Stocks with no release in the past year have no calendar to read, so they score missing.
    history = np.column_stack([released(k) for k in range(0, 13)]).any(axis=1)
    expected = released(2) | released(11)
    panel["eap"] = np.where(history, expected.astype(float), np.nan)

    # Earnings and revenue surprise, ranked within the month and averaged.
    panel["surprise"] = pd.concat(
        [P.rank_z(panel, "niq_su"), P.rank_z(panel, "saleq_su")], axis=1
    ).mean(axis=1)

    # Fresh: the surprise counts only in the three months after it last changed.
    changed = (
        panel["niq_su"].ne(panel.groupby("permno")["niq_su"].shift(1)) & panel["niq_su"].notna()
    )
    index = panel["eom"].dt.year * 12 + panel["eom"].dt.month
    age = index - index.where(changed).groupby(panel["permno"]).ffill()
    panel["niq_su_fresh"] = panel["niq_su"].where(age <= 2)
    return panel


# The statistics every variant is judged on, the same way for each window.
def judge(universe: pd.DataFrame, market: pd.Series) -> dict:
    book = P.backtest(universe)
    fit = P.regress(book["net"], market)
    return dict(
        **P.book_stats(book),
        beta_realized=float(fit.params.iloc[1]),
        beta_stderr=float(fit.bse.iloc[1]),
        tails_monotone=tails(universe),
    )


# Does the score rise through both tails? The book trades the tails, not the middle.
def tails(universe: pd.DataFrame) -> bool:
    s = universe.dropna(subset=["ret_exc_lead1m"])
    buckets = s.groupby("eom")["signal"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 10, labels=False)
    )
    dm = s["ret_exc_lead1m"] - s.groupby("eom")["ret_exc_lead1m"].transform("mean")
    by = dm.groupby([s["eom"], buckets]).mean().groupby(level=1).mean()
    return bool(by[9] > by[8] and by[0] < by[1])


# One window, one signal set, the shipped code for everything else.
def build(panel: pd.DataFrame, window: tuple, signals: dict | None) -> pd.DataFrame:
    return P.build_signal(P.screen(panel, *window), signals)


# Stage one. Only 2016-2020, and the decision goes to disk before anything later is computed.
def design_stage(panel: pd.DataFrame, market: pd.Series) -> dict:
    frozen = judge(build(panel, DESIGN, None), market)
    variants = {name: judge(build(panel, DESIGN, sig), market) for name, sig in VARIANTS.items()}
    best = max(variants, key=lambda k: variants[k]["information_ratio"])
    b = variants[best]
    ship = (
        b["information_ratio"] - frozen["information_ratio"] >= RULE["min_ir_gain"]
        and abs(b["beta_realized"]) <= RULE["max_abs_beta"]
        and b["tails_monotone"]
    )
    path = OUT / "earnings_decision.json"
    earlier = json.loads(path.read_text()) if path.exists() else {}
    # When it was decided is the evidence, so a rerun reaching the same decision keeps that date.
    same = earlier.get("ship") == bool(ship) and earlier.get("best_variant") == best
    decision = dict(
        what="Stage one of the earnings module. Written before 2021-2026 was computed.",
        rule=RULE,
        window="holding months 2016-01 to 2020-12",
        decided_utc=earlier["decided_utc"]
        if same
        else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        frozen_book=frozen,
        variants=variants,
        best_variant=best,
        ship=bool(ship),
    )
    path.write_text(json.dumps(decision, indent=2))
    return decision


# Reads the release calendar the panel's earnings updates follow. No returns involved.
def availability_audit(panel: pd.DataFrame, releases: set) -> dict:
    p = panel.sort_values(["permno", "eom"])
    prev = p.groupby("permno")["niq_su"].shift(1)
    changes = p[p["niq_su"].notna() & prev.notna() & p["niq_su"].ne(prev)]
    regular = pd.Series([k[0] for k in releases]).value_counts()
    changes = changes[changes["permno"].isin(regular[regular >= 8].index)]
    month = changes["eom"].dt.to_period("M")
    keys = list(zip(changes["permno"].astype(int), month))
    same = np.array([(k, m) in releases for k, m in keys])
    before = np.array([(k, m) not in releases and (k, m + 1) in releases for k, m in keys])
    return dict(
        updates_checked=int(len(keys)),
        same_month_as_release=float(same.mean()),
        month_before_release=float(before.mean()),
        note="An update in the month before its 2.02 filing is a release in the last days of a "
        "month filed early the next, within the four business days the rules describe.",
    )


# The book with every accounting signal made months staler than the panel says.
def lag_stress(panel: pd.DataFrame, market: pd.Series) -> dict:
    out = {}
    for months in (3, 6):
        stale = panel.sort_values(["permno", "eom"]).copy()
        stale[ACCOUNTING] = stale.groupby("permno")[ACCOUNTING].shift(months)
        out[f"lag_{months}m"] = judge(build(stale, TEST, None), market)
    return out


# Stock splits, as an event study. A control only: splits are rare and adjfct is auxiliary.
def splits(panel: pd.DataFrame) -> dict:
    p = panel.sort_values(["permno", "eom"]).copy()
    ratio = p["shares"] / p.groupby("permno")["shares"].shift(1)
    factor_moved = p["adjfct"].ne(p.groupby("permno")["adjfct"].shift(1))
    screened = (p["prc"].abs() >= 5.0) & (p["me"] >= 300.0)
    p["dm"] = p["ret_exc_lead1m"] - p.groupby("eom")["ret_exc_lead1m"].transform("mean")
    out = {}
    for name, hit in (("forward", ratio >= 1.4), ("reverse", ratio <= 0.7)):
        events = p[hit & factor_moved & screened]
        # The next six months of return against the cross-section, one month at a time.
        path = []
        for k in range(6):
            nxt = p.groupby("permno")["dm"].shift(-k).loc[events.index].dropna()
            path.append(dict(month=k + 1, mean=float(nxt.mean()), n=int(len(nxt))))
        out[name] = dict(events=int(len(events)), path=path)
    return out


def main() -> None:
    panel = P.load_panel(extra=("saleq_su", "adjfct", "shares"))
    releases = release_months()
    panel = features(panel, releases)
    # The decision was judged against the CRSP market, and FRED's S&P 500 misses early 2016.
    market = B.benchmarks().set_index("month")["mkt_rf_crsp"]
    OUT.mkdir(parents=True, exist_ok=True)

    decision = design_stage(panel, market)
    print(f"stage one: best {decision['best_variant']}, ship = {decision['ship']}")

    # Stage two. Everything reported, nothing re-decided.
    screened = P.screen(panel)
    result = dict(
        what="Stage two. 2021-2026 for the frozen book and every variant, after the decision.",
        decision_file="earnings_decision.json",
        ship=decision["ship"],
        availability=availability_audit(panel, releases),
        coverage=dict(
            has_release_calendar=float(screened["eap"].notna().mean()),
            expected_next_month=float((screened["eap"] == 1).mean()),
            fresh_surprise=float(screened["niq_su_fresh"].notna().mean()),
        ),
        frozen_book=judge(build(panel, TEST, None), market),
        variants={name: judge(build(panel, TEST, sig), market) for name, sig in VARIANTS.items()},
        accounting_lag_stress=lag_stress(panel, market),
        stock_splits=splits(panel),
        code=P.source_fingerprint(),
    )
    (OUT / "earnings_module.json").write_text(json.dumps(result, indent=2))
    for name, s in result["variants"].items():
        print(f"  2021-26 {name}: IR {s['information_ratio']:+.2f}")


if __name__ == "__main__":
    main()
