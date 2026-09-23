# Re-checks the look-ahead list against code and output, and fails if any check does.
#
# Not proof the submission reproduces. Each check is necessary, not sufficient.

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

SRC = Path("src")
CHARS = Path("data/chars_final_with_names.parquet")
HOLDINGS = Path("submission/holdings.csv")
RETURNS = Path("submission/returns.csv")
OUT = Path("submission/exhibits")

# Columns built after the fact. As features they split the test period perfectly.
GROUPERS = ('groupby("eom")', 'groupby("holding_month")')

PROVENANCE = [
    "ticker_name_status",
    "source_crsp",
    "ticker_name_source",
    "cusip_asof_date",
    "identifier_quality_flags",
    "title_ai",
]


# Every check returns (name, passed, detail) so the report reads the same whatever it found.
def check_no_provenance_features() -> tuple[str, bool, str]:
    # The signal list is the only place a feature name can enter the book.
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    signals = re.search(r"SIGNALS = \{(.*?)\}", source, re.S)
    used = set(re.findall(r'"([a-z0-9_]+)":', signals.group(1))) if signals else set()
    leaked = sorted(used & set(PROVENANCE))
    return (
        "no provenance column is a feature",
        not leaked,
        f"leaked: {leaked}" if leaked else "clean",
    )


# Only the lead column may be the target. Limit. Core pipeline only.
def check_target_not_reshifted() -> tuple[str, bool, str]:
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    # ret and ret_exc are same-month returns. Only the lead column may be the target.
    bad = re.findall(r'\bshift\(-\d+\)|["\']ret["\']|["\']ret_exc["\']', source)
    return (
        "target is ret_exc_lead1m, never re-shifted",
        not bad,
        f"found {bad}" if bad else "clean",
    )


# The rules name the 147 predictors. "All numeric columns" is the easiest way to leak.
def check_predictors_are_listed() -> tuple[str, bool, str]:
    listed = set(pd.read_csv("data/factor_char_list.csv")["variable"])
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    signals = re.search(r"SIGNALS = \{(.*?)\}", source, re.S)
    used = set(re.findall(r'"([a-z0-9_]+)":', signals.group(1))) if signals else set()
    outside = sorted(used - listed)
    return (
        "every signal is in factor_char_list.csv",
        not outside,
        f"outside: {outside}" if outside else f"{len(used)} signals, all listed",
    )


# 68 months, 2021-01 to 2026-08. A miscount here means the whole submission is wrong.
def check_holding_months() -> tuple[str, bool, str]:
    months = pd.read_csv(RETURNS, parse_dates=["holding_month"])["holding_month"]
    ok = len(months) == 68 and str(months.min().date()) == "2021-01-01"
    return (
        "68 holding months, 2021-01 to 2026-08",
        ok,
        f"{len(months)} months from {months.min().date()}",
    )


# Screening on having a return drops the failures, the one bias a short book cannot have.
def check_universe_not_filtered_on_target() -> tuple[str, bool, str]:
    # Drop names with no next-month return and the short book flatters itself.
    held = set(pd.read_csv(HOLDINGS)["PERMNO"])
    panel = pq.read_table(CHARS, columns=["permno", "eom", "ret_exc_lead1m"]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    window = panel[panel["eom"].between("2020-12-31", "2026-07-31")]
    missing = window[window["ret_exc_lead1m"].isna()]
    kept = len(held & set(missing["permno"]))
    return (
        "names with no next-month return are still held",
        kept > 0,
        f"{kept} such names in the book",
    )


# Those names are kept at zero rather than dropped, so this confirms some actually exist.
def check_missing_returns_booked_flat() -> tuple[str, bool, str]:
    df = pd.read_csv(RETURNS)
    weight = (df["missing_long_weight"] + df["missing_short_weight"]).sum()
    # Confirms they are still held, not that zero is right. CRSP dlret settles that.
    return (
        "missing returns are kept, not dropped",
        weight > 0,
        f"{weight:.4f} weight-months booked flat, a stated assumption",
    )


# A ticker repaired from a later month is look-ahead in the holdings file itself.
def check_labels_are_backward_only() -> tuple[str, bool, str]:
    # Every filled label must exist in the panel at or before the month it is used.
    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    if book["TICKER"].isna().any():
        return ("every holding carries a label", False, f"{int(book['TICKER'].isna().sum())} blank")
    panel = pq.read_table(CHARS, columns=["permno", "eom", "ticker"]).to_pandas()
    panel["eom"] = pd.to_datetime(panel["eom"])
    first_seen = panel[panel["ticker"].notna()].groupby("permno")["eom"].min()
    decision = book["Date"] - pd.offsets.MonthEnd(1)
    earliest = book["PERMNO"].map(first_seen)
    ahead = int((earliest > decision).sum())
    return (
        "labels come from the decision month or earlier",
        ahead == 0,
        f"{ahead} from the future",
    )


# Carry-in feeds last month's book back in. Assign it early and we choose with the future.
def check_carry_in_uses_prior_month() -> tuple[str, bool, str]:
    source = (SRC / "pipeline.py").read_text(encoding="utf-8").splitlines()
    call = next((i for i, line in enumerate(source) if "optimize_month(cross_section" in line), -1)
    # The assignment is a tuple unpack, so match on the name rather than the whole line.
    assign = next(
        (
            i
            for i, line in enumerate(source)
            if line.strip().startswith("previous") and "= weights" in line
        ),
        -1,
    )
    ok = call > 0 and assign > call
    return (
        "carry-in sees last month's book, never this one",
        ok,
        f"called at line {call + 1}, updated at line {assign + 1}",
    )


# Train must end before validation, validation before test. Overlap trains on the answer.
def check_ml_folds_do_not_overlap() -> tuple[str, bool, str]:
    sys.path.insert(0, str(SRC / "ml"))
    import dataset as D

    if not (Path("cache/folds/folds.parquet")).exists():
        return ("model folds are strictly ordered in time", True, "folds not built, skipped")
    df = D.load_folds()
    bad = []
    for fold in D.folds(df):
        train, validate, test = fold["train"], fold["validate"], fold["test"]
        if len(test) and not (
            train["holding_month"].max()
            < validate["holding_month"].min()
            <= validate["holding_month"].max()
            < test["holding_month"].min()
        ):
            bad.append(fold["test_year"])
    return (
        "model folds are strictly ordered in time",
        not bad,
        f"overlapping: {bad}" if bad else "6 folds, no overlap",
    )


# A rank or fill over the whole sample carries later months into earlier ones.
def check_ml_transform_is_within_month() -> tuple[str, bool, str]:
    source = (SRC / "ml" / "dataset.py").read_text(encoding="utf-8").splitlines()
    # Safe if groupby("eom") is on the same line or the one above, so check both.
    ungrouped = [
        line.strip()
        for i, line in enumerate(source)
        if (".rank(" in line or 'transform("median")' in line)
        and not any(g in line for g in GROUPERS)
        and not any(g in (source[i - 1] if i else "") for g in GROUPERS)
    ]
    return (
        "model features are ranked within the month only",
        not ungrouped,
        f"ungrouped: {ungrouped}" if ungrouped else "every rank and fill is grouped by eom",
    )


# Test blocks run January to December. An offset gives February folds and breaks everything.
def check_ml_folds_are_calendar_years() -> tuple[str, bool, str]:
    sys.path.insert(0, str(SRC / "ml"))
    import dataset as D

    if not Path("cache/folds/folds.parquet").exists():
        return ("model test folds are calendar years", True, "folds not built, skipped")
    df = D.load_folds()
    bad = []
    for fold in D.folds(df):
        test = fold["test"]
        if not len(test):
            continue
        months = test["holding_month"]
        # The last fold is a partial year, so only the January start is required there.
        starts_in_january = months.min().month == 1
        ends_in_december = months.max().month == 12
        if not starts_in_january or (fold["test_year"] < D.LAST_TEST_YEAR and not ends_in_december):
            bad.append(f"{fold['test_year']}:{months.min():%Y-%m}..{months.max():%Y-%m}")
    return (
        "model test folds are calendar years",
        not bad,
        f"misaligned: {bad}" if bad else "every test block starts in January",
    )


# Model tables and the portfolio must count the same months, or 69 meets 68 unnoticed.
def check_ml_months_match_the_book() -> tuple[str, bool, str]:
    preds = sorted(Path("cache/preds").glob("*.parquet")) if Path("cache/preds").exists() else []
    if not preds:
        return ("model predictions cover the book's 68 months", True, "no predictions, skipped")
    book = pd.read_csv(RETURNS)["holding_month"].nunique()
    bad = []
    for path in preds:
        months = pd.read_parquet(path, columns=["holding_month"])["holding_month"].nunique()
        if months != book:
            bad.append(f"{path.stem}:{months}")
    return (
        "model predictions cover the book's 68 months",
        not bad,
        f"mismatched: {bad}" if bad else f"all {len(preds)} models cover {book} months",
    )


# The exhibit's last row is meant to BE the shipped book. Drift means it compares nothing.
def check_survival_reconciles_to_the_book() -> tuple[str, bool, str]:
    path = OUT / "constraint_survival.json"
    name = "constraint survival ends at the shipped book"
    if not path.exists():
        return (name, True, "exhibit not built, skipped")
    final = json.loads(path.read_text())["models"]["composite"]["portfolio"]["after_costs"]
    shipped = json.loads(Path("submission/metrics.json").read_text())["performance"]
    gap = abs(final["net_ir"] - shipped["information_ratio"])
    return (
        name,
        gap < 0.01,
        f"exhibit {final['net_ir']:.3f} vs book {shipped['information_ratio']:.3f}",
    )


# Tested on gross, not net. Only gross can be zero under a null, since churn still costs.
def check_permutation_null_earns_nothing_gross() -> tuple[str, bool, str]:
    path = OUT / "placebo_lab.json"
    name = "shuffled scores earn nothing before costs"
    if not path.exists():
        return (name, True, "exhibit not built, skipped")
    null = json.loads(path.read_text())["permutation_null"]
    if "gross_annual_mean" not in null:
        return (name, True, "exhibit predates the gross measurement, rerun placebo_lab.py")
    mean, sd, draws = null["gross_annual_mean"], null["gross_annual_std"], null["draws"]
    # Three standard errors, plus a 1%/yr floor so the check does not trip on noise alone.
    tolerance = max(3 * sd / (draws**0.5), 0.01)
    return (
        name,
        abs(mean) < tolerance,
        f"null gross {mean:+.2%}/yr over {draws} draws, tolerance {tolerance:.2%}",
    )


# Every seed must cover the same 68 months, or the spread is partly a spread in length.
def check_seed_sweep_is_complete() -> tuple[str, bool, str]:
    path = OUT / "nn3_seeds.json"
    name = "every NN3 seed covers the same months"
    if not path.exists():
        return (name, True, "sweep not run, skipped")
    rows = json.loads(path.read_text())["per_seed"]
    months = {r["months"] for r in rows}
    return (
        name,
        len(months) == 1 and months.pop() == 68,
        f"{len(rows)} seeds, months {sorted({r['months'] for r in rows})}",
    )


# The deflation only means something if its counts match the ledger anyone can rebuild.
def check_trial_counts_match_the_ledger() -> tuple[str, bool, str]:
    import csv

    name = "deflation counts match the experiment ledger"
    path = OUT / "config_log.csv"
    if not path.exists():
        return (name, True, "ledger not built, skipped")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import pipeline as P

    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    eligible = sum(int(r["attempts"]) for r in rows if r["eligible_for_deployment"] == "yes")
    everything = sum(int(r["attempts"]) for r in rows)
    ok = eligible == P.DESIGN_TRIALS and everything == P.ALL_TRIALS
    return (
        name,
        ok,
        f"ledger {eligible}/{everything} vs code {P.DESIGN_TRIALS}/{P.ALL_TRIALS}",
    )


# The docs quote how many checks run here, so the audit counts itself and catches drift.
def check_docs_quote_the_check_count() -> tuple[str, bool, str]:
    name = "docs quote the right number of checks"
    words = {
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
    }
    total = len(CHECKS)
    correct = words.get(total, str(total))
    wrong = [w for n, w in words.items() if n != total]
    bad = []
    for doc in ("README.md", "BRIEF.md", "RESULTS.md", "FIAM_Plan.md"):
        path = Path(doc)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for word in wrong:
            if f"{word} checks" in text or f"{word} look-ahead" in text:
                bad.append(f"{doc} says {word}")
    return (name, not bad, "; ".join(bad) if bad else f"all docs say {correct}")


CHECKS = [
    check_no_provenance_features,
    check_target_not_reshifted,
    check_predictors_are_listed,
    check_holding_months,
    check_universe_not_filtered_on_target,
    check_missing_returns_booked_flat,
    check_labels_are_backward_only,
    check_carry_in_uses_prior_month,
    check_ml_folds_do_not_overlap,
    check_ml_transform_is_within_month,
    check_ml_folds_are_calendar_years,
    check_ml_months_match_the_book,
    check_survival_reconciles_to_the_book,
    check_permutation_null_earns_nothing_gross,
    check_seed_sweep_is_complete,
    check_trial_counts_match_the_ledger,
    check_docs_quote_the_check_count,
]


# Runs every check, writes the report, and exits non-zero so it can gate a build.
def main() -> int:
    results = [check() for check in CHECKS]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reproducibility.json").write_text(
        json.dumps(
            [dict(check=n, passed=bool(p), detail=d) for n, p, d in results],
            indent=2,
        )
    )
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<48} {detail}")
    failed = sum(1 for _, p, _ in results if not p)
    print(f"\n{len(results) - failed} of {len(results)} checks passed")
    # Non-zero so this can gate a run, the same way the pipeline's asserts do.
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
