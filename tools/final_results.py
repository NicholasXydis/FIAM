# Writes final/ from the locked run: final_results.py [--into dir].

import csv
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fiam.vfinal.report.table_9_1 import rebalances  # noqa: E402

OUTPUTS = ROOT / "frozen" / "vfinal" / "outputs.json"
CARDS = ROOT / "data" / "v4" / "cards"
INTO = ROOT / "final"
# The input cards whose raw hashes name the organisers' files.
CARRIED_CARDS = ("dsf", "panel")
# Ledger kinds by daily column: price moves and position closes.
PRICE, EXITS = ("price",), ("exit", "stub", "true_up")
# The engine's daily marks carried beside NAV, as booked.
BOOKED = ["gross_pre", "net_pre", "max_weight_pre", "n_long", "n_short", "traded"]
# The engine's compliance marks carried beside NAV, as booked.
CHECKED = ["names_pre", "max_company_weight", "max_company_weight_pre", "short_floor_breaches"]
# The NAV identity holds to a cent each day, float sums aside.
CENT = 0.01


# The sha256 of one file, read in blocks.
def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# The locked run's record: its commit, folder and file digests.
def locked() -> dict:
    return json.loads(OUTPUTS.read_text(encoding="utf-8"))


# One locked output's path, refused unless its digest matches the lock.
def source(record: dict, name: str, base: str | None = None) -> Path:
    folder = base or record["headline"]
    rel = f"{folder}/{name}"
    path = ROOT / rel
    want = record["files"].get(rel)
    if want is None:
        raise SystemExit(f"refused: {rel} is not in {OUTPUTS.name}")
    if not path.is_file() or digest(path) != want:
        raise SystemExit(f"refused: {rel} is missing or differs from the lock")
    return path


# The run's frames by name, each read from a locked file.
def frames(record: dict) -> dict:
    at = record["run_at"]
    read = lambda stem: pd.read_parquet(source(record, f"{stem}_{at}.parquet"))  # noqa: E731
    return {k: read(f"{k}_7") for k in ("daily", "positions", "ledger", "compliance", "trades")}


# One row a day: NAV, return, the ledger's dollars and exposures.
def daily_table(f: dict) -> pd.DataFrame:
    d, led, pos = f["daily"], f["ledger"], f["positions"]
    by = led.pivot_table(index="date", columns="kind", values="dollars", aggfunc="sum")
    by = by.reindex(d.index).fillna(0.0)
    kinds = lambda names: by[[k for k in names if k in by]].sum(axis=1)  # noqa: E731
    long = pos[pos["value"] > 0].groupby("date")["value"].sum().reindex(d.index).fillna(0.0)
    short = pos[pos["value"] < 0].groupby("date")["value"].sum().reindex(d.index).fillna(0.0)
    out = pd.DataFrame(index=d.index)
    out["nav"], out["ret"], out["interest"] = d["nav"], d["ret"], d["interest"]
    out["stock_pnl"], out["dividends"], out["exits"] = kinds(PRICE), d["dividends"], kinds(EXITS)
    out["cost"], out["borrow"] = d["cost"], d["borrow"]
    out["long_usd"], out["short_usd"] = long, short
    out["gross_usd"], out["net_usd"] = long - short, long + short
    out = out.join(d[BOOKED]).join(f["compliance"][CHECKED])
    # Each formation's date on its first trade day, as the table counts.
    first = rebalances(f["trades"])
    formed = pd.DatetimeIndex(first.index).strftime("%Y-%m-%d")
    out["formed"] = pd.Series(formed, index=first.to_numpy()).reindex(out.index).fillna("")
    # Every NAV move is the ledger's dollars, interest and fees.
    move = out["nav"].diff().iloc[1:]
    parts = out[["interest", "stock_pnl", "dividends", "exits"]].sum(axis=1)
    gap = (move - (parts - out["cost"] - out["borrow"]).iloc[1:]).abs().max()
    if not gap < CENT:
        raise SystemExit(f"refused: the NAV moves differ from the ledger by ${gap:.4f}")
    out.index = out.index.strftime("%Y-%m-%d")
    return out.rename_axis("date")


# Every day's closing weights by permno, the gzip stamped with no time.
def positions_gz(f: dict) -> bytes:
    pos = f["positions"].sort_values(["date", "permno"], kind="stable")
    w = pos["value"] / pos["date"].map(f["daily"]["nav"])
    table = pd.DataFrame(
        {"date": pos["date"].dt.strftime("%Y-%m-%d"), "permno": pos["permno"], "weight": w}
    )
    raw = table.to_csv(index=False, lineterminator="\n").encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    return buffer.getvalue()


# The monthly holdings from the Arcana file, checked against its lock.
def holdings(record: dict) -> str:
    at = record["run_at"]
    name = f"arcana_weights_monthly_{at}.csv"
    plain = source(record, name).read_text(encoding="utf-8")
    own = (ROOT / record["headline"] / name.replace(".csv", "_own.csv")).read_text("utf-8")
    plain_rows, own_rows = list(csv.reader(io.StringIO(plain))), list(csv.reader(io.StringIO(own)))
    width = len(plain_rows[0])
    if [r[:width] for r in own_rows] != plain_rows:
        raise SystemExit(f"refused: the _own copy of {name} differs from the locked file")
    head = own_rows[0]
    at_col = {c: head.index(c) for c in ("Date", "PERMNO", "Ticker", "Name", "Weights")}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["date", "permno", "ticker", "company_name", "weight"])
    for row in own_rows[1:]:
        ticker = row[at_col["Ticker"]].removesuffix(" US Equity")
        cells = [row[at_col[c]] for c in ("Date", "PERMNO")]
        writer.writerow([*cells, ticker, row[at_col["Name"]], row[at_col["Weights"]]])
    return out.getvalue()


# The 23 rows as written, the report's headline and the book's breaches.
def metrics(record: dict, cards: dict) -> str:
    at = record["run_at"]
    table = source(record, f"table_9_1_{at}.csv").read_text(encoding="utf-8")
    report = json.loads(source(record, f"report_{at}.json").read_text(encoding="utf-8"))
    book = json.loads(source(record, f"book_{at}.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(io.StringIO(table)))
    stamp = report["stamp"]
    keep = ("cadence", "limits", "headline_arm", "rows", "daily_rows", "monthly_rows")
    used = [f"{k}_7_{at}.parquet" for k in ("daily", "positions", "ledger", "compliance", "trades")]
    used += [f"table_9_1_{at}.csv", f"report_{at}.json", f"book_{at}.json"]
    used += [f"arcana_weights_monthly_{at}.csv"]
    names = [f"{record['headline']}/{n}" for n in used]
    files = {n: record["files"][n] for n in names}
    body = {
        "run_at": at,
        "commit": stamp["commit"],
        "headline": record["headline"],
        "table_9_1": rows,
        "report": {k: report[k] for k in keep},
        "book": {k: book[k] for k in ("breach_days", "first_breach", "formations", "design")},
        "input_cards_sha256": {k: stamp["input_cards_sha256"][k] for k in cards},
        "char_list_sha256": stamp["char_list_sha256"],
        "sources": files,
    }
    return json.dumps(body, indent=1) + "\n"


# The input cards, each refused unless the report's stamp names it.
def cards(record: dict) -> dict[str, bytes]:
    at = record["run_at"]
    report = json.loads(source(record, f"report_{at}.json").read_text(encoding="utf-8"))
    want = report["stamp"]["input_cards_sha256"]
    out = {}
    for name in CARRIED_CARDS:
        raw = (CARDS / f"{name}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != want[name]:
            raise SystemExit(f"refused: the {name} card differs from the locked report's stamp")
        out[name] = raw
    return out


# Writes every carried file into a folder and returns their paths.
def build(into: Path = INTO) -> list[Path]:
    record = locked()
    f = frames(record)
    made = cards(record)
    files = {
        "holdings.csv": holdings(record).encode(),
        "daily.csv": daily_table(f).to_csv(lineterminator="\n").encode(),
        "metrics.json": metrics(record, made).encode(),
        "positions_daily.csv.gz": positions_gz(f),
        **{f"cards/{k}.json": v for k, v in made.items()},
    }
    written = []
    for name, raw in files.items():
        path = into / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        written.append(path)
    return written


# Builds final/ or the folder given, then prints each file's size.
if __name__ == "__main__":
    args = sys.argv[1:]
    into = Path(args[args.index("--into") + 1]).resolve() if "--into" in args else INTO
    paths = build(into)
    for path in paths:
        print(f"{path.stat().st_size / 1e6:8.2f} MB  {path.relative_to(into).as_posix()}")
    print(f"{sum(p.stat().st_size for p in paths) / 1e6:8.2f} MB  in {into}")
