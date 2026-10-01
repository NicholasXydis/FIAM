# Re-checks the look-ahead list against code and output. Each check is necessary, not sufficient.

import json
import os
import re
import sys
from functools import cache
from pathlib import Path

import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import data, paths
from fiam.checks import provenance
from fiam.ml import dataset as D

PACKAGE = Path("fiam")
OUT = paths.EXHIBITS
FOLDS = Path("cache/folds/folds.parquet")

# A rank or fill is safe when grouped by one of these.
GROUPERS = ('groupby("eom")', 'groupby("holding_month")')

# Columns built after the fact. As features they split the test period perfectly.
PROVENANCE = {
    "ticker_name_status",
    "source_crsp",
    "ticker_name_source",
    "cusip_asof_date",
    "identifier_quality_flags",
    "title_ai",
}

# What a check returns when the step it reads has not run yet, or ran only on a smoke slice.
SKIPPED = (True, "not built yet, skipped")
REHEARSAL = (True, "a smoke rehearsal runs the models on a slice, skipped")

CHECKS = []


# Registers a check under the name the report prints. Each returns (passed, detail).
def check(name: str):
    # Adds the check to the list and leaves the function as it was.
    def register(function):
        CHECKS.append((name, function))
        return function

    return register


# The names in the SIGNALS block, read from source, the only place a feature enters the book.
def signal_names() -> set[str]:
    source = (PACKAGE / "book.py").read_text(encoding="utf-8")
    block = re.search(r"SIGNALS = \{(.*?)\}", source, re.S)
    return set(re.findall(r'"([a-z0-9_]+)":', block.group(1))) if block else set()


# The model folds, read once however many checks ask.
@cache
def folds() -> list[dict]:
    return list(D.folds(D.load_folds())) if FOLDS.exists() else []


@check("no provenance column is a feature")
def no_provenance_features():
    leaked = sorted(signal_names() & PROVENANCE)
    return not leaked, f"leaked: {leaked}" if leaked else "clean"


# ret and ret_exc are same-month returns, so only the lead column may be the target.
@check("target is ret_exc_lead1m, never re-shifted")
def target_not_reshifted():
    source = (PACKAGE / "book.py").read_text(encoding="utf-8")
    bad = re.findall(r'\bshift\(-\d+\)|["\']ret["\']|["\']ret_exc["\']', source)
    return not bad, f"found {bad}" if bad else "clean"


# The rules name the 147 predictors. "All numeric columns" is the easiest way to leak.
@check("every signal is in factor_char_list.csv")
def predictors_are_listed():
    used = signal_names()
    outside = sorted(used - set(P.characteristics()))
    return not outside, f"outside: {outside}" if outside else f"{len(used)} signals, all listed"


# 68 months, 2021-01 to 2026-08. A miscount here means the whole submission is wrong.
@check("68 holding months, 2021-01 to 2026-08")
def holding_months():
    months = pd.read_csv(paths.RETURNS, parse_dates=["holding_month"])["holding_month"]
    ok = len(months) == 68 and str(months.min().date()) == "2021-01-01"
    return ok, f"{len(months)} months from {months.min().date()}"


# Screening on having a return drops the failures, and the short book flatters itself.
@check("names with no next-month return are still held")
def universe_not_filtered_on_target():
    panel = data.panel(["ret_exc_lead1m"])
    window = panel[panel["eom"].between("2020-12-31", "2026-07-31")]
    missing = set(window.loc[window["ret_exc_lead1m"].isna(), "permno"])
    kept = len(set(pd.read_csv(paths.HOLDINGS)["PERMNO"]) & missing)
    return kept > 0, f"{kept} such names in the book"


# Confirms missing returns are still held at zero, not that zero is right. CRSP settles that.
@check("missing returns are kept, not dropped")
def missing_returns_booked_flat():
    df = pd.read_csv(paths.RETURNS)
    weight = (df["missing_long_weight"] + df["missing_short_weight"]).sum()
    return weight > 0, f"{weight:.4f} weight-months booked flat, a stated assumption"


# A ticker repaired from a later month is look-ahead in the holdings file itself.
@check("labels come from the decision month or earlier")
def labels_are_backward_only():
    book = paths.holdings()
    if book["TICKER"].isna().any():
        return False, f"{int(book['TICKER'].isna().sum())} holdings carry no label"
    panel = data.features(["ticker"])
    first_seen = panel[panel["ticker"].notna()].groupby("permno")["eom"].min()
    ahead = int((book["PERMNO"].map(first_seen) > book["Date"] - pd.offsets.MonthEnd(1)).sum())
    return ahead == 0, f"{ahead} from the future"


# Carry-in feeds last month's book back in. Assign it early and we choose with the future.
@check("carry-in sees last month's book, never this one")
def carry_in_uses_prior_month():
    lines = (PACKAGE / "book.py").read_text(encoding="utf-8").splitlines()
    call = next((i for i, x in enumerate(lines) if "step = rebalance(" in x), -1)
    update = "previous, previous_quotes ="
    # The update that follows the call, not the reset before the loop starts.
    assign = next((i for i, x in enumerate(lines) if i > call and x.strip().startswith(update)), -1)
    return 0 < call < assign, f"called at line {call + 1}, updated at line {assign + 1}"


# Train must end before validation, validation before test. Overlap trains on the answer.
@check("model folds are strictly ordered in time")
def ml_folds_do_not_overlap():
    if not folds():
        return SKIPPED
    bad = [
        f["test_year"]
        for f in folds()
        if len(f["test"])
        and not (
            f["train"]["holding_month"].max()
            < f["validate"]["holding_month"].min()
            <= f["validate"]["holding_month"].max()
            < f["test"]["holding_month"].min()
        )
    ]
    return not bad, f"overlapping: {bad}" if bad else f"{len(folds())} folds, no overlap"


# A rank or fill over the whole sample carries later months into earlier ones.
@check("model features are ranked within the month only")
def ml_transform_is_within_month():
    lines = (PACKAGE / "ml" / "dataset.py").read_text(encoding="utf-8").splitlines()
    # Safe if a grouper is on the same line or the one above, so check both.
    ungrouped = [
        x.strip()
        for i, x in enumerate(lines)
        if (".rank(" in x or 'transform("median")' in x)
        and not any(g in x or (i and g in lines[i - 1]) for g in GROUPERS)
    ]
    detail = f"ungrouped: {ungrouped}" if ungrouped else "every rank and fill is grouped by eom"
    return not ungrouped, detail


# Test blocks run January to December. An offset gives February folds and breaks everything.
@check("model test folds are calendar years")
def ml_folds_are_calendar_years():
    if not folds():
        return SKIPPED
    bad = []
    for f in folds():
        months = f["test"]["holding_month"]
        if not len(months):
            continue
        # The last fold is a partial year, so only the January start is required there.
        late = f["test_year"] < D.LAST_TEST_YEAR and months.max().month != 12
        if months.min().month != 1 or late:
            bad.append(f"{f['test_year']}:{months.min():%Y-%m}..{months.max():%Y-%m}")
    return not bad, f"misaligned: {bad}" if bad else "every test block starts in January"


# Model tables and the portfolio must count the same months, or 69 meets 68 unnoticed.
@check("model predictions cover the book's 68 months")
def ml_months_match_the_book():
    preds = sorted((P.CACHE / "preds").glob("*.parquet"))
    if paths.SMOKE:
        return REHEARSAL
    if not preds:
        return SKIPPED
    book = pd.read_csv(paths.RETURNS)["holding_month"].nunique()
    count = {p.stem: pd.read_parquet(p, columns=["holding_month"]).nunique().iloc[0] for p in preds}
    bad = [f"{k}:{v}" for k, v in count.items() if v != book]
    return not bad, f"mismatched: {bad}" if bad else f"all {len(preds)} models cover {book} months"


# Tested on gross, not net. Only gross can be zero under a null, since churn still costs.
@check("shuffled scores earn nothing before costs")
def permutation_null_earns_nothing_gross():
    placebo = paths.exhibit("placebo_lab.json")
    if not placebo:
        return SKIPPED
    null = placebo["permutation_null"]
    mean, draws = null["gross_annual_mean"], null["draws"]
    # Three standard errors, plus a 1%/yr floor so the check does not trip on noise alone.
    tolerance = max(3 * null["gross_annual_std"] / draws**0.5, 0.01)
    detail = f"null gross {mean:+.2%}/yr over {draws} draws, tolerance {tolerance:.2%}"
    return abs(mean) < tolerance, detail


# A clock time in a result makes two identical runs differ, so no result file may carry one.
@check("no result carries a clock time")
def results_have_no_timestamps():
    if paths.SMOKE:
        return REHEARSAL
    stamp = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
    files = [p for p in paths.SUBMISSION.rglob("*.json") if "agents" not in p.parts]
    dated = [p.name for p in files if stamp.search(p.read_text(encoding="utf-8"))]
    detail = f"timestamps in: {dated}" if dated else f"{len(files)} result files, none dated"
    return not dated, detail


# A hash that no longer matches means the file was edited or half-rewritten after its run.
@check("every artifact matches the run that wrote it")
def artifacts_match_their_run():
    manifest = paths.exhibit("run_manifest.json")
    if not manifest:
        return SKIPPED
    files = {**(manifest["book"] or {}).get("files", {}), **(manifest["ml"] or {}).get("files", {})}
    bad = [Path(f).name for f, digest in files.items() if not paths.matches(Path(f), digest)]
    return not bad, f"changed since their run: {bad}" if bad else "all hashes match"


# The model exhibits are slow, so they are rebuilt only with --ml. Stale code means stale numbers.
@check("model exhibits were built from the current code")
def model_exhibits_are_current():
    ml = (paths.exhibit("run_manifest.json") or {}).get("ml")
    if not ml:
        return True, "no --ml run recorded yet, skipped"
    ok = provenance.fingerprint(provenance.ML_CODE) == ml["code"]
    return ok, "current" if ok else "code changed since, rerun uv run run.py --official --ml"


# Every model book must span the same 68 months as ours, flat months included.
@check("every model book covers all 68 months")
def model_books_cover_68_months():
    found = (P.CACHE / "preds").glob("*_portfolio.json")
    books = {p.stem: json.loads(p.read_text(encoding="utf-8"))["months"] for p in found}
    if not books:
        return SKIPPED
    short = {k: v for k, v in books.items() if v != 68}
    return not short, f"short: {short}" if short else f"{len(books)} books, all 68"


# The organizer publishes a SHA-256 for each file. The bundle must be built from exactly those.
@check("data bundle was built from the organizer's published files")
def data_matches_the_readme():
    bad = data.checksum_mismatches()
    return not bad, f"mismatch: {bad}" if bad else "both SHA-256 match the organizer's readme"


# An exhibit no script in run.py writes cannot be regenerated, so it cannot be trusted.
@check("every exhibit is written by a step in run.py")
def every_exhibit_has_a_writer():
    modules = set(re.findall(r'"(fiam\.[\w.]+)', Path("run.py").read_text(encoding="utf-8")))
    files = [Path(*m.split(".")).with_suffix(".py") for m in modules]
    source = "".join(f.read_text(encoding="utf-8") for f in files if f.exists())
    orphans = [p.name for p in sorted(OUT.glob("*")) if p.is_file() and p.name not in source]
    return not orphans, f"no writer: {orphans}" if orphans else "all have writers"


# The rules measure beta against the S&P 500, over every holding month.
@check("market is the S&P 500, regressed over all 68 months")
def market_is_the_sp500():
    notes = paths.read_json(paths.METRICS)["notes"]
    ok = "S&P 500" in notes["market_series"] and notes["regression_months"] == 68
    return ok, f"{notes['market_series']}, {notes['regression_months']} months"


# The cost total is the five lines added up, so the breakdown can never be reverse-engineered.
@check("costs reconcile to their five lines every month")
def costs_reconcile():
    df = pd.read_csv(paths.RETURNS)
    gap = float((df["cost"] - df.filter(like="cost_").sum(axis=1)).abs().max())
    return gap < 1e-12, f"largest gap {gap:.1e}"


# Turnover rebuilt from the published holdings, each month traded from last month's drifted book.
@check("turnover recomputes from the holdings with drift")
def turnover_recomputes():
    book = paths.holdings()
    returns = paths.returns()
    universe = P.universe().set_index(["eom", "permno"])["ret_exc_lead1m"]
    previous, gaps = None, []
    for month, group in book.groupby("Date"):
        weights = group.set_index("PERMNO")["WEIGHT"] / 100
        both = weights.index.union(previous.index if previous is not None else [])
        traded = weights.reindex(both, fill_value=0.0) - (
            previous.reindex(both, fill_value=0.0) if previous is not None else 0.0
        )
        gaps.append(abs(traded.abs().sum() / 2 - returns.loc[month, "turnover"]))
        earned = universe.loc[month - pd.offsets.MonthEnd(1)].reindex(weights.index)
        costs = returns.loc[month].filter(like="cost_").to_dict()
        info = earned.to_frame("ret_exc_lead1m")
        previous = P.drift(weights, info, costs, returns.loc[month, "rf"])
    # Weights are published to six decimals of a percent, so a few millionths is rounding.
    return max(gaps) < 1e-5, f"largest monthly gap {max(gaps):.1e} over {len(gaps)} months"


# The book side is rebuilt on every run, so its artifacts must come from the code as it stands.
@check("book artifacts were built from the current code")
def book_is_current():
    manifest = paths.exhibit("run_manifest.json")
    if not manifest:
        return SKIPPED
    ok = provenance.fingerprint(["fiam", "run.py", "requirements.txt"]) == manifest["book"]["code"]
    return ok, "current" if ok else "code changed since, rerun uv run run.py --official"


# Every benchmark file is the one its recorded source says it is, byte for byte.
@check("benchmark files match their recorded sources")
def benchmarks_are_pinned():
    sources = json.loads(B.SOURCES.read_text(encoding="utf-8")) if B.SOURCES.exists() else {}
    bad = [n for n, s in sources.items() if not paths.matches(B.BENCH / n, s["sha256"])]
    missing = sorted(set(B.URLS) - set(sources))
    ok = not bad and not missing
    return ok, f"changed: {bad}, unrecorded: {missing}" if not ok else f"{len(sources)} files match"


# Final only with WRDS exits applied, no delisted name held, and the report-date rule passed.
@check("WRDS exits applied, no delisted name held, report dates respected")
def wrds_exits_applied():
    table = P.exits()
    if table is None:
        official = os.environ.get("FIAM_OFFICIAL") == "1"
        return (
            not official,
            "PROVISIONAL: no WRDS exports; add them with uv run run.py --import <folder>",
        )
    book = paths.holdings()
    decided = book["Date"] - pd.offsets.MonthEnd(1)
    dead = int((book["PERMNO"].map(table["exit_date"]) <= decided).sum())
    dates = (paths.exhibit("wrds.json") or {}).get("report_dates", {})
    ok = dead == 0 and dates.get("passed") is True
    early = dates.get("worst_early_share", float("nan"))
    return ok, f"{len(table):,} exits, {dead} delisted names held, worst early update {early:.2%}"


# Runs every check, writes the report, and exits non-zero so it can gate a build.
def main() -> int:
    results = [(name, *function()) for name, function in CHECKS]
    OUT.mkdir(parents=True, exist_ok=True)
    report = [dict(check=n, passed=bool(p), detail=d) for n, p, d in results]
    paths.write_json(OUT / "reproducibility.json", report, rounded=False)
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<48} {detail}")
    failed = sum(1 for _, p, _ in results if not p)
    print(f"\n{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
