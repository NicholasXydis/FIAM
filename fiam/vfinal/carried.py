# The final fund's carried results, then the organisers' files if here.

import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.vfinal import daily_book, lock
from fiam.vfinal.report import table_9_1 as table

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "frozen" / "vfinal" / "final"
BENCH = ROOT / "data" / "benchmarks"
# The organisers' files, in data/organisers/ or beside MAIN.py.
DSF, CHARS = "dsf_mini_from_2014.csv", "chars_final_with_names.parquet"
CHAR_LIST = "factor_char_list.csv"
# The engine's own slack on every limit (daily_book.compliance).
SLACK = 1e-12
# Dollar sums agree to a cent; float rounding is far below it.
CENT = 0.01
# Full-precision rows agree to this relative gap.
CLOSE = 1e-12

Check = tuple[str, bool, str]


# One line of the check list.
def mark(name: str, ok: bool, detail: str) -> Check:
    return name, bool(ok), detail


# A percentage with two places.
def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


# Dollars in millions with one place.
def musd(x: float) -> str:
    return f"${x / 1e6:,.1f}m"


# The carried files: holdings, days, daily weights and the metrics.
def load(folder: Path = FINAL) -> dict:
    blank = {c: [""] for c in ("names_pre", "max_company_weight_pre")}
    daily = pd.read_csv(
        folder / "daily.csv", parse_dates=["date"], keep_default_na=False, na_values=blank
    )
    daily = daily.set_index("date")
    with gzip.open(folder / "positions_daily.csv.gz", "rt", encoding="utf-8") as fh:
        positions = pd.read_csv(fh, parse_dates=["date"])
    holdings = pd.read_csv(folder / "holdings.csv", parse_dates=["date"], dtype={"ticker": str})
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    return dict(daily=daily, positions=positions, holdings=holdings, metrics=metrics)


# Each day's names, gross, net and largest weight from the weights.
def by_day(positions: pd.DataFrame) -> pd.DataFrame:
    w = positions.assign(size=positions["weight"].abs())
    g = w.groupby("date")
    out = {"names": g.size(), "gross": g["size"].sum(), "net": g["weight"].sum()}
    return pd.DataFrame(out | {"top": g["size"].max()})


# The session a decision's information lands on: the close it is dated.
def eom_sessions(days: pd.DatetimeIndex, formed: pd.Series) -> pd.Series:
    place = days.searchsorted(pd.DatetimeIndex(formed), side="right") - 1
    return pd.Series(place, index=formed.index)


# Every PDF limit on the carried days, each limit from the mandate.
def limits(c: dict, rules: dict) -> list[Check]:
    d, pos, hold = c["daily"], c["positions"], c["holdings"]
    lo, hi, cap = rules["names_min"], rules["names_max"], rules["name_cap"]
    gross, band, floor = rules["gross"], rules["net_band"], rules["short_min_market_cap"]
    first, last = (pd.Timestamp(x) for x in rules["window"])
    # Every session from the first trade on, a day with no names included.
    day = by_day(pos)
    day = day.reindex(d.index[d.index >= day.index[0]]).fillna(0)
    out = []
    span = f"{day.index[0]:%Y-%m-%d} to {d.index[-1]:%Y-%m-%d}, {len(day)} sessions held"
    in_window = day.index[0] >= first and d.index[-1] <= last
    out.append(mark("inside the PDF window", in_window, span))
    # The trade day of each formation, lag sessions after its month's close.
    formed = d.loc[d["formed"] != "", "formed"]
    trade_at = pd.Series(d.index.get_indexer(formed.index), index=formed.index)
    lag = trade_at - eom_sessions(d.index, pd.to_datetime(formed))
    on_time = int((lag == rules["lag_days"]).sum())
    out.append(
        mark(
            f"trades {rules['lag_days']} session after",
            on_time == len(formed),
            f"{on_time} of {len(formed)} decisions traded from the session after",
        )
    )
    names = day["names"]
    out.append(
        mark(
            f"{lo} to {hi} names at each close",
            names.between(lo, hi).all(),
            f"{names.min():.0f} to {names.max():.0f} a day",
        )
    )
    pre = d["names_pre"].dropna()
    seen = f"{pre.min():.0f} to {pre.max():.0f} on {len(pre)} trade days, as booked"
    out.append(mark(f"{lo} to {hi} names before trades", pre.between(lo, hi).all(), seen))
    top = day["top"].max()
    out.append(
        mark(
            f"at most {cap:.0%} in one name", top <= cap + SLACK, f"largest {pct(top)} at any close"
        )
    )
    booked = d[["max_weight_pre", "max_company_weight", "max_company_weight_pre"]].max().max()
    out.append(
        mark(
            f"at most {cap:.0%} before trades",
            booked <= cap + SLACK,
            f"largest {pct(booked)} by name or company, as booked",
        )
    )
    g = max(day["gross"].max(), d["gross_pre"].max())
    out.append(
        mark(
            f"gross at most {gross:.0%}",
            g <= gross + SLACK,
            f"largest {pct(g)}, closes and before trades",
        )
    )
    n = max(day["net"].abs().max(), d["net_pre"].abs().max())
    out.append(
        mark(
            f"net within +/-{band:.0%}",
            n <= band + SLACK,
            f"largest |net| {pct(n)}, closes and before trades",
        )
    )
    under = int(d["short_floor_breaches"].sum())
    out.append(
        mark(
            f"shorts at least ${floor:,.0f}m cap",
            under == 0,
            f"{under} shorts under the floor at formation, as booked",
        )
    )
    out.append(holdings_check(hold, pos))
    out += books(d, pos)
    return out


# The monthly holdings are the daily weights on their dates.
def holdings_check(hold: pd.DataFrame, pos: pd.DataFrame) -> Check:
    keys = ["date", "permno"]
    got = hold.merge(pos, on=keys, how="left", suffixes=("", "_daily"))
    same = len(got) == len(hold) and (got["weight"] == got["weight_daily"]).all()
    months = hold["date"].dt.to_period("M").nunique()
    detail = f"{len(hold)} rows over {months} months equal the daily weights"
    return mark("holdings.csv is the daily book", same, detail)


# NAV, returns and exposures agree with the ledger's dollars.
def books(d: pd.DataFrame, pos: pd.DataFrame) -> list[Check]:
    nav = d["nav"]
    ret = (nav / nav.shift(1) - 1).iloc[1:]
    ret_ok = np.allclose(ret, d["ret"].iloc[1:], rtol=0, atol=CLOSE)
    move = nav.diff().iloc[1:]
    parts = d[["interest", "stock_pnl", "dividends", "exits"]].sum(axis=1) - d["cost"] - d["borrow"]
    gap = float((move - parts.iloc[1:]).abs().max())
    value = pos["weight"] * pos["date"].map(nav)
    long = value.where(value > 0, 0.0).groupby(pos["date"]).sum().reindex(d.index).fillna(0.0)
    short = value.where(value < 0, 0.0).groupby(pos["date"]).sum().reindex(d.index).fillna(0.0)
    held = float(max((long - d["long_usd"]).abs().max(), (short - d["short_usd"]).abs().max()))
    return [
        mark("returns are NAV changes", ret_ok, f"{len(ret)} days"),
        mark("NAV moves are the ledger", gap < CENT, f"largest daily gap ${gap:.6f}"),
        mark("exposures are the weights", held < CENT, f"largest long or short gap ${held:.6f}"),
    ]


# The bill a day as the engine reads it: a month's rate once posted.
def daily_bill(days: pd.DatetimeIndex, path: Path = BENCH / "TB3MS.csv") -> pd.Series:
    t = pd.read_csv(path, parse_dates=["observation_date"]).set_index("observation_date")
    rate = pd.to_numeric(t["TB3MS"], errors="coerce").dropna() / 100
    # FRED posts a month's rate the business day after it ends.
    posted = rate[rate.index + pd.offsets.MonthEnd(0) + pd.offsets.BDay(1) <= days[-1]]
    month = days.to_period("M").to_timestamp()
    known = posted.reindex(posted.index.union(month.unique())).ffill()
    return pd.Series(known.reindex(month).to_numpy() / 252, index=days)


# FRED's S&P 500 daily return over its posted closes.
def sp500(path: Path = BENCH / "SP500.csv") -> pd.Series:
    s = pd.read_csv(path)
    level = pd.to_numeric(s["SP500"], errors="coerce")
    s = pd.DataFrame({"date": pd.to_datetime(s["observation_date"]), "level": level}).dropna()
    return pd.Series(s["level"].pct_change().to_numpy(), index=s["date"].to_numpy())


# The table's headline rows from NAV, the bill and the S&P 500 alone.
def headline(daily: pd.DataFrame, rf: pd.Series, sp: pd.Series) -> dict:
    daily = daily.assign(rf=rf)
    start = float(daily["nav"].iloc[0] / (1 + daily["ret"].iloc[0]))
    d = daily.iloc[1:].loc[: table.END]
    # The month's bill compounds the daily bill, as the 23 rows do.
    m = daily_book.monthly(d)
    m["excess"] = m["ret"] - m["rf"]
    active = m["ret"] - (m["rf"] + table.PREMIUM / 12)
    end = start * float((1 + d["ret"]).prod())
    s = sp.reindex(d.index)
    if s.isna().any():
        raise ValueError("the S&P 500 series misses a day of the run")
    _, _, b, b_se = table.ols(m["excess"], table.compound(s) - m["rf"], table.LAGS_MONTHLY)
    _, _, bd, bd_se = table.ols(d["ret"] - d["rf"], s - d["rf"], table.LAGS_DAILY)
    return {
        1: end / 1e9,
        3: table.two_returns(m["ret"], end, start),
        6: table.with_se(b, b_se, 3),
        7: table.with_se(bd, bd_se, 3),
        8: table.annual_ratio(m["excess"]),
        11: table.drawdown(d["ret"]) * 100,
        23: table.with_se(table.annual_ratio(active), table.ratio_se(active), 2),
    }


# Sharpe and IR on the PDF's monthly bill, TB3MS / 1200, as a note.
def pdf_bill(c: dict, rf: pd.Series) -> list[str]:
    d = c["daily"].assign(rf=rf).iloc[1:].loc[: table.END]
    m = daily_book.monthly(d)
    bill = (rf * 252 / 12).groupby(rf.index.to_period("M")).first().reindex(m.index)
    sharpe = table.annual_ratio(m["ret"] - bill)
    ir = table.annual_ratio(m["ret"] - bill - table.PREMIUM / 12)
    return [f"  on the PDF's monthly bill (TB3MS / 1200): Sharpe {sharpe:.3f}, IR {ir:.2f}"]


# Each recomputed row against the table carried in metrics.json.
def headline_checks(got: dict, rows: list[dict]) -> list[Check]:
    cell = {int(r["row"]): r["strategy"] for r in rows}
    out = []
    for row, label in ((1, "ending value (US$ bn)"), (8, "Sharpe ratio"), (11, "max drawdown (%)")):
        ok = abs(got[row] - float(cell[row])) <= CLOSE * max(1.0, abs(float(cell[row])))
        out.append(mark(label, ok, f"recomputed {got[row]:.6f}, table {float(cell[row]):.6f}"))
    texts = (
        (3, "annual return and CAGR", cell[3]),
        (23, "IR vs T-bill + 4%, net", cell[23].split(";")[0]),
        (6, "beta monthly (s.e.)", cell[6]),
        (7, "beta daily (s.e.)", cell[7]),
    )
    for row, label, want in texts:
        out.append(mark(label, got[row] == want, f"recomputed {got[row]}, table {want}"))
    return out


# Every hashed file present here against the lock, new code too.
def lock_checks(root: Path = lock.ROOT) -> tuple[list[Check], list[str]]:
    lines = [ln.partition("  ") for ln in lock.SHA.read_text().splitlines() if ln.strip()]
    present = [(w, n) for w, _, n in lines if (root / n).is_file()]
    absent = [n for _, _, n in lines if not (root / n).is_file()]
    changed = [n for w, n in present if lock.digest(root / n) != w]
    code = absent
    unlisted = sorted(set(lock.code()) - {n for _, _, n in lines})
    detail = f"{len(present) - len(changed)} of {len(present)} code and settings files match"
    out = [mark("code against the lock", not changed and not code, detail)]
    if unlisted:
        out.append(mark("every code file is locked", False, f"{len(unlisted)} not in the lock"))
    notes = [f"  changed since the lock: {n}" for n in changed]
    notes += [f"  missing here: {n}" for n in code]
    notes += [f"  not in the lock: {n}" for n in unlisted]
    return out, notes


# The carried files name the locked run and its file digests.
def provenance(metrics: dict) -> Check:
    record = json.loads(lock.OUTPUTS.read_text())
    tree = hashlib.sha256(json.dumps(record["files"], sort_keys=True).encode()).hexdigest()
    same = metrics["tree_sha256"] == tree
    same = same and all(record["files"].get(n) == d for n, d in metrics["sources"].items())
    detail = f"{len(metrics['sources'])} source digests of run {metrics['run_at']} match"
    return mark("frozen/vfinal/final/ is the locked run", same, detail)


# The folder holding the organisers' daily file, if any.
def organisers(root: Path = ROOT) -> Path | None:
    for folder in (root / "data" / "organisers", root):
        if (folder / DSF).is_file():
            return folder
    return None


# What the repository records for each organisers' file, by source.
def receipts(metrics: dict, folder: Path = FINAL) -> tuple[dict, list[Check]]:
    from fiam import data as bundle

    want: dict[str, dict] = {}
    out = []
    for name, sha in metrics["input_cards_sha256"].items():
        path = folder / "cards" / f"{name}.json"
        raw = path.read_bytes() if path.is_file() else b""
        ok = hashlib.sha256(raw).hexdigest() == sha
        out.append(mark(f"{name} card is the stamp's", ok, f"final/cards/{name}.json"))
        for key, digest in (json.loads(raw).get("raw", {}) if ok else {}).items():
            want.setdefault(key.removeprefix("organisers/"), {})[f"{name} card"] = digest
    for name, digest in bundle.PUBLISHED.items():
        want.setdefault(name, {})["their readme"] = digest
    want.setdefault(CHAR_LIST, {})["report stamp"] = metrics["char_list_sha256"]
    return want, out


# Each organisers' file here against every receipt for it.
def hash_checks(folder: Path, want: dict) -> tuple[list[Check], list[str]]:
    out, notes = [], []
    for name in sorted(want):
        path = folder / name
        if not path.is_file():
            notes.append(f"  not here: {name}")
            continue
        got = lock.digest(path)
        ok = set(want[name].values()) == {got}
        detail = f"sha256 {got[:12]} vs {' and '.join(sorted(want[name]))}"
        out.append(mark(name if len(name) <= 30 else name[:27] + "...", ok, detail))
    return out, notes


# The organisers' daily returns for our names and days.
def organiser_returns(path: Path, permnos, first: pd.Timestamp) -> pd.DataFrame:
    import pyarrow as pa
    import pyarrow.compute as pc
    from pyarrow import csv

    types = {"permno": pa.int64(), "date": pa.int64(), "daily_return": pa.float64()}
    keep = csv.ConvertOptions(include_columns=list(types), column_types=types)
    t = csv.read_csv(path, convert_options=keep)
    t = t.filter(pc.greater_equal(t["date"], int(first.strftime("%Y%m%d"))))
    t = t.filter(pc.is_in(t["permno"], pa.array(sorted(permnos), pa.int64())))
    f = t.to_pandas()
    f["date"] = pd.to_datetime(f["date"].astype(str), format="%Y%m%d")
    return f.rename(columns={"daily_return": "r"})


# Weights at each close times the organisers' next-session return.
def replay(daily: pd.DataFrame, positions: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    days = daily.index
    nxt = pd.Series(days[1:], index=days[:-1])
    p = positions[positions["date"].isin(nxt.index)].copy()
    p["earns"] = p["date"].map(nxt)
    p["dollars"] = p["weight"] * p["date"].map(daily["nav"])
    got = p.merge(
        rets, left_on=["earns", "permno"], right_on=["date", "permno"], how="left", indicator=True
    )
    got["no_row"] = (got["_merge"] == "left_only").astype(int)
    got["null"] = ((got["_merge"] == "both") & got["r"].isna()).astype(int)
    got["pnl"] = got["dollars"] * got["r"].fillna(0.0)
    by = got.groupby("earns").agg(
        replay=("pnl", "sum"), no_row=("no_row", "sum"), null=("null", "sum")
    )
    out = by.reindex(days[1:]).fillna(0.0)
    out["ledger"] = daily["stock_pnl"].iloc[1:]
    out["gap"] = out["replay"] - out["ledger"]
    return out


# The replay's totals, years and correlation, and a plain verdict.
def replay_report(r: pd.DataFrame) -> tuple[list[str], Check]:
    lines = [
        f"  days compared        {len(r)}",
        f"  ledger stock P&L     {musd(r['ledger'].sum())}",
        f"  organisers' replay   {musd(r['replay'].sum())}",
        f"  total gap            ${r['gap'].sum():,.2f}",
        f"  daily correlation    {r['replay'].corr(r['ledger']):.12f}",
        f"  largest daily gap    ${r['gap'].abs().max():,.2f}",
    ]
    for year, g in r.groupby(r.index.year):
        lines.append(f"  {year}  ledger {musd(g['ledger'].sum()):>10}  gap ${g['gap'].sum():,.2f}")
    unpriced = (r["no_row"] + r["null"]) > 0
    full, part = r[~unpriced], r[unpriced]
    exact = int((full["gap"].abs() < CENT).sum())
    lines.append(f"  {exact} of {len(full)} days with every held name priced agree to the cent")
    if len(part):
        lines.append(
            f"  {len(part)} days hold names their file leaves unpriced, gap there "
            f"${part['gap'].sum():,.2f}"
        )
        lines.append(
            f"    {part['no_row'].sum():.0f} name-days with no row (halts and exits, "
            "which the engine books apart)"
        )
        lines.append(
            f"    {part['null'].sum():.0f} name-days with a null return (the engine "
            "prices those from the price ratio)"
        )
    ok = exact == len(full)
    detail = f"{exact} of {len(full)} fully priced days to the cent"
    return lines, mark("stock P&L on their returns", ok, detail)


# Shorts' caps at each decision close: the panel's latest month end.
def short_caps(daily: pd.DataFrame, positions: pd.DataFrame, path: Path, floor: float) -> Check:
    import pyarrow.parquet as pq

    formed = daily.loc[daily["formed"] != "", "formed"]
    panel = pq.read_table(path, columns=["permno", "eom", "me"]).to_pandas()
    panel["eom"] = (pd.to_datetime(panel["eom"]) + pd.offsets.MonthEnd(0)).astype("datetime64[ns]")
    ends = pd.DatetimeIndex(sorted(panel["eom"].unique()))
    asof = ends[ends.searchsorted(pd.to_datetime(formed), side="right") - 1]
    eoms = pd.Series(asof, index=formed.index)
    panel = panel[panel["eom"].isin(set(eoms))]
    short = positions[(positions["weight"] < 0) & positions["date"].isin(formed.index)]
    short = short.assign(eom=short["date"].map(eoms))
    got = short.merge(panel, on=["permno", "eom"], how="left")
    under = int((~(got["me"] >= floor)).sum())
    detail = f"{len(got)} shorts at {len(formed)} formations, smallest ${got['me'].min():,.0f}m"
    return mark(f"shorts at least ${floor:,.0f}m cap", under == 0, detail + f", {under} under")


# Prints one titled list of checks and their notes.
def show(title: str, checks: list[Check], notes: list[str] = ()) -> None:
    print(f"\n{title}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<30} {detail}")
    for note in notes:
        print(note)


# The organisers' files: receipts, the P&L replay and short caps.
def with_organisers(c: dict, folder: Path, rules: dict) -> list[Check]:
    where = "data/organisers/" if folder.name == "organisers" else "beside MAIN.py"
    want, checks = receipts(c["metrics"])
    found, notes = hash_checks(folder, want)
    checks += found
    show(f"Organisers' files ({where}) against the repository's receipts", checks, notes)
    rets = organiser_returns(folder / DSF, c["positions"]["permno"].unique(), c["daily"].index[0])
    lines, verdict = replay_report(replay(c["daily"], c["positions"], rets))
    title = "Our daily stock P&L before costs, replayed on the organisers' returns"
    print(f"\n{title}\n  weights at the close of d earn the organisers' return of d+1")
    print("\n".join(lines))
    extra = [verdict]
    if (folder / CHARS).is_file():
        extra.append(
            short_caps(c["daily"], c["positions"], folder / CHARS, rules["short_min_market_cap"])
        )
    show("Verdict on the organisers' files", extra)
    return checks + extra


# Runs every check and prints PASS or FAIL for each; 1 on any FAIL.
def main(root: Path = ROOT) -> int:
    rules = daily_book.mandate()
    c = load(root / "frozen" / "vfinal" / "final")
    print("The final fund, checked from the files MAIN.py carries in frozen/vfinal/final/")
    print(f"Run {c['metrics']['run_at']}, limits from {daily_book.MANDATE.relative_to(ROOT)}")
    checks = [provenance(c["metrics"]), *limits(c, rules)]
    show("The carried book against every PDF rule", checks)
    rf = daily_bill(c["daily"].index, root / "data" / "benchmarks" / "TB3MS.csv")
    got = headline(c["daily"], rf, sp500(root / "data" / "benchmarks" / "SP500.csv"))
    head = headline_checks(got, c["metrics"]["table_9_1"])
    show("Headline recomputed from daily.csv, TB3MS.csv and SP500.csv", head, pdf_bill(c, rf))
    locked, notes = lock_checks(root)
    show("Code against frozen/vfinal/vfinal.sha256", locked, notes)
    checks = [*checks, *head, *locked]
    folder = organisers(root)
    if folder is None:
        print("\nNo organisers' files in data/organisers/ or beside MAIN.py, so only the above.")
    else:
        checks += with_organisers(c, folder, rules)
        print("\nThe fund is not rebuilt here: a rerun needs our other data (CRSP, TAQ, SEC")
        print("filings and more), which only the USB kit carries. With a clone and the kit:")
        print("  uv run fiam setup, uv run fiam verify, uv run fiam rerun, uv run fiam compare")
    failed = sum(not ok for _, ok, _ in checks)
    print(f"\n{len(checks) - failed} of {len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
