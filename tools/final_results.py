# Writes frozen/vfinal/final/ from the locked run: [--into dir].

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

FROZEN = ROOT / "frozen" / "vfinal"
OUTPUTS, INPUTS = FROZEN / "outputs.json", FROZEN / "inputs.json"
INTO = ROOT / "frozen" / "vfinal" / "final"
# The headline book's folder inside the locked output folder.
BOOK = "bw_fresh_lag"
# The input cards whose raw hashes name the organisers' files.
CARRIED_CARDS = ("dsf", "panel")
CARDS, CHAR_LIST = "data/v4/cards", "data/organisers/factor_char_list.csv"
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


# The locked outputs: their folder and every file's digest.
def locked() -> dict:
    return json.loads(OUTPUTS.read_text(encoding="utf-8"))


# The locked run's name: the first 12 of its outputs' tree hash.
def tree(record: dict) -> str:
    return hashlib.sha256(json.dumps(record["files"], sort_keys=True).encode()).hexdigest()


# One book file's path, refused unless its digest matches the lock.
def source(record: dict, name: str) -> Path:
    key = f"{BOOK}/{name}"
    path = ROOT / record["folder"] / key
    want = record["files"].get(key)
    if want is None:
        raise SystemExit(f"refused: {key} is not in {OUTPUTS.name}")
    if not path.is_file() or digest(path) != want:
        raise SystemExit(f"refused: {record['folder']}/{key} is missing or differs from the lock")
    return path


# The book's frames by name, each read from a locked file.
def frames(record: dict) -> dict:
    parts = ("daily", "positions", "ledger", "compliance", "trades")
    return {k: pd.read_parquet(source(record, f"{k}.parquet")) for k in parts}


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
    # Each decision close on its first trade day, as the table counts.
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
    name = "arcana_weights_monthly.csv"
    plain = source(record, name).read_text(encoding="utf-8")
    own = source(record, name.replace(".csv", "_own.csv")).read_text(encoding="utf-8")
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


# The 23 rows as written, the book's checks and its sources' digests.
def metrics(record: dict, inputs: dict) -> str:
    table = source(record, "table_9_1.csv").read_text(encoding="utf-8")
    result = json.loads(source(record, "result.json").read_text(encoding="utf-8"))
    check = json.loads(source(record, "compliance_check.json").read_text(encoding="utf-8"))
    used = [f"{k}.parquet" for k in ("daily", "positions", "ledger", "compliance", "trades")]
    used += ["table_9_1.csv", "result.json", "compliance_check.json"]
    used += ["arcana_weights_monthly.csv", "arcana_weights_monthly_own.csv"]
    body = {
        "run_at": tree(record)[:12],
        "tree_sha256": tree(record),
        "headline": f"{record['folder']}/{BOOK}",
        "table_9_1": list(csv.DictReader(io.StringIO(table))),
        "book": {k: result[k] for k in ("breach_days", "names_min", "names_max", "gross_max")},
        "finals_check": {k: check[k] for k in ("breaches", "violations", "rebalances")},
        "input_cards_sha256": {k: inputs[f"{CARDS}/{k}.json"] for k in CARRIED_CARDS},
        "char_list_sha256": inputs[CHAR_LIST],
        "sources": {f"{BOOK}/{n}": record["files"][f"{BOOK}/{n}"] for n in used},
    }
    return json.dumps(body, indent=1) + "\n"


# The input cards, each refused unless the locked inputs name it.
def cards(inputs: dict) -> dict[str, bytes]:
    out = {}
    for name in CARRIED_CARDS:
        raw = (ROOT / CARDS / f"{name}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != inputs[f"{CARDS}/{name}.json"]:
            raise SystemExit(f"refused: the {name} card differs from the locked inputs")
        out[name] = raw
    return out


# Writes every carried file into a folder and returns their paths.
def build(into: Path = INTO) -> list[Path]:
    record = locked()
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))["files"]
    f = frames(record)
    made = cards(inputs)
    files = {
        "holdings.csv": holdings(record).encode(),
        "daily.csv": daily_table(f).to_csv(lineterminator="\n").encode(),
        "metrics.json": metrics(record, inputs).encode(),
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


# Builds frozen/vfinal/final/ or a folder, then prints each size.
if __name__ == "__main__":
    args = sys.argv[1:]
    into = Path(args[args.index("--into") + 1]).resolve() if "--into" in args else INTO
    paths = build(into)
    for path in paths:
        print(f"{path.stat().st_size / 1e6:8.2f} MB  {path.relative_to(into).as_posix()}")
    print(f"{sum(p.stat().st_size for p in paths) / 1e6:8.2f} MB  in {into}")
