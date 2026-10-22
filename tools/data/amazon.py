# Amazon Reviews 2023 (UCSD) as product-month tables; raw is deleted.

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from _shared import ROOT, check, data_root, fingerprint, receipts, stamp

OUT = ROOT / "data" / "amazon"
HUB = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023"
TREE = "https://huggingface.co/api/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main"
RATINGS, META = "benchmark/0core/rating_only", "raw/meta_categories"
USAGE = "uv run run.py --data amazon list | fetch [category ...] | verify | official"
# Snapshot fields computed in 2023, like average_rating, are never kept.
ITEM_COLUMNS = {"parent_asin": "VARCHAR", "store": "VARCHAR", "main_category": "VARCHAR"}


# One Hugging Face request, retried with waits when the server is busy.
def open_url(url: str, headers: dict | None = None):
    last = None
    for wait in (0, 10, 30, 90):
        time.sleep(wait)
        try:
            sent = {"User-Agent": "FIAM research"} | (headers or {})
            request = urllib.request.Request(url, headers=sent)
            return urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as err:
            if err.code in (404, 416):
                raise
            last = err
        except OSError as err:
            last = err
    raise last


# Every category listed, with its ratings and metadata sizes.
def categories() -> dict[str, dict]:
    found = {}
    for folder, key in ((RATINGS, "ratings"), (META, "meta")):
        with open_url(f"{TREE}/{folder}") as r:
            for entry in json.load(r):
                name = entry["path"].rsplit("/", 1)[1]
                size = (entry.get("lfs") or {}).get("size") or entry.get("size") or 0
                if key == "ratings" and name.endswith(".csv") and name.count(".") == 1:
                    found.setdefault(name[:-4], {})["ratings"] = size
                if key == "meta" and name.startswith("meta_") and name.endswith(".jsonl"):
                    found.setdefault(name[5:-6], {})["meta"] = size
    return {k: v for k, v in sorted(found.items()) if "ratings" in v and "meta" in v}


# Streams one file to disk, resuming a part, and returns its SHA-256.
def download(path: str, target: Path) -> tuple[int, str]:
    part = target.with_suffix(target.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        response = open_url(f"{HUB}/resolve/main/{path}", headers)
    except urllib.error.HTTPError as err:
        if err.code != 416:
            raise
        part.unlink()
        return download(path, target)
    with response, part.open("ab" if have and response.status == 206 else "wb") as fh:
        while chunk := response.read(1 << 22):
            fh.write(chunk)
    part.replace(target)
    return target.stat().st_size, fingerprint(target)


# One category: items to store and brand, ratings to product-month sums.
def one(category: str, saved: dict) -> None:
    import duckdb

    raw, items, months = OUT / "raw", OUT / "items", OUT / "product_month"
    for folder in (raw, items, months, OUT / "tmp"):
        folder.mkdir(parents=True, exist_ok=True)
    meta_file, rating_file = raw / f"meta_{category}.jsonl", raw / f"{category}.csv"
    receipt = {"category": category}
    receipt["meta_raw"] = download(f"{META}/meta_{category}.jsonl", meta_file)
    receipt["ratings_raw"] = download(f"{RATINGS}/{category}.csv", rating_file)
    db = duckdb.connect()
    db.execute(f"SET memory_limit='6GB'; SET threads=6; SET temp_directory='{OUT / 'tmp'}'")
    columns = ITEM_COLUMNS | {"details": "JSON"}
    db.execute(
        f"""COPY (SELECT parent_asin, store, main_category,
                   json_extract_string(details, '$.Brand') AS brand
                 FROM read_json('{meta_file}', columns={columns}, format='newline_delimited',
                                ignore_errors=true))
            TO '{items / f"{category}.parquet"}' (FORMAT parquet, COMPRESSION zstd)"""
    )
    db.execute(
        f"""COPY (SELECT parent_asin,
                   date_trunc('month', make_timestamp(timestamp * 1000)) AS month,
                   count(*) AS reviews, sum(rating) AS rating_sum,
                   sum(rating * rating) AS rating_sq, min(timestamp) AS first_ms
                 FROM read_csv('{rating_file}', header=true, columns={{'user_id': 'VARCHAR',
                   'parent_asin': 'VARCHAR', 'rating': 'DOUBLE', 'timestamp': 'BIGINT'}})
                 GROUP BY ALL)
            TO '{months / f"{category}.parquet"}' (FORMAT parquet, COMPRESSION zstd)"""
    )
    for name, folder in (("items", items), ("product_month", months)):
        out = folder / f"{category}.parquet"
        count = db.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
        receipt[name] = {"rows": count, "bytes": out.stat().st_size, "sha256": fingerprint(out)}
    summary = months / f"{category}.parquet"
    reviews = db.execute(f"SELECT sum(reviews) FROM '{summary}'").fetchone()[0]
    receipt["reviews"] = int(reviews or 0)
    db.close()
    meta_file.unlink()
    rating_file.unlink()
    receipt["made_at"] = stamp()
    saved[category] = receipt


# Lists the categories with their raw sizes, downloading nothing.
def show() -> int:
    found = categories()
    for name, size in found.items():
        gb = {k: round(v / 1e9, 2) for k, v in size.items()}
        print(f"{name:32} ratings {gb['ratings']:6.2f} GB  meta {gb['meta']:6.2f} GB")
    total = sum(v["ratings"] + v["meta"] for v in found.values())
    print(f"{len(found)} categories, {total / 1e9:.1f} GB raw in all")
    return 0


# Fetches and summarises categories, skipping any already done.
def fetch(asked: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    book = OUT / "receipts.json"
    saved = receipts(book)
    names = asked or list(categories())
    failed = []
    for n, category in enumerate(names, 1):
        if category in saved:
            continue
        try:
            one(category, saved)
        except Exception as err:  # noqa: BLE001
            print(f"{category}: failed ({type(err).__name__}: {str(err)[:200]})", flush=True)
            failed.append(category)
            continue
        book.write_text(json.dumps(saved, indent=1))
        r = saved[category]
        made = f"{r['reviews']:,} reviews, {r['product_month']['rows']:,} product-months"
        print(f"{n} of {len(names)} {category}: {made}", flush=True)
    print(f"Done: {len(saved)} categories saved, {len(failed)} failed {failed}")
    return 1 if failed else 0


# Every summary table against its receipt; prints and counts mismatches.
def verify() -> int:
    saved = receipts(OUT / "receipts.json")
    bad = 0
    for kind in ("items", "product_month"):
        expected = {f"{c}.parquet": r[kind]["sha256"] for c, r in saved.items()}
        wrong = check(OUT / kind, expected)
        print(f"amazon {kind}: {len(expected)} files, {len(wrong)} wrong {wrong[:5]}")
        bad += len(wrong)
    return 1 if bad else 0


# Each raw file's SHA-256 in our receipts against Hugging Face's own.
def official() -> int:
    published = {}
    for folder in (RATINGS, META):
        with open_url(f"{TREE}/{folder}") as r:
            for entry in json.load(r):
                lfs = entry.get("lfs") or {}
                published[entry["path"].rsplit("/", 1)[1]] = (lfs.get("size"), lfs.get("oid"))
    saved, wrong = receipts(OUT / "receipts.json"), []
    for category, r in saved.items():
        pairs = ((f"meta_{category}.jsonl", "meta_raw"), (f"{category}.csv", "ratings_raw"))
        for name, key in pairs:
            if tuple(r[key]) != published.get(name):
                wrong.append(name)
    print(f"amazon raw: {2 * len(saved)} files against Hugging Face, {len(wrong)} wrong {wrong}")
    return 1 if wrong else 0


# One verb per run; --into sends the output elsewhere.
if __name__ == "__main__":
    OUT = data_root(sys.argv) / "amazon"
    verb, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if verb in ("list", "verify", "official") and not rest:
        sys.exit({"list": show, "verify": verify, "official": official}[verb]())
    if verb == "fetch":
        sys.exit(fetch(rest))
    print(f"Usage: {USAGE}")
    sys.exit(2)
