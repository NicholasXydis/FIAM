# Carbon Arc access; run through uv run run.py --data carbon <verb>.

import gzip
import hashlib
import json
import math
import sys
import time
from collections.abc import Callable
from pathlib import Path

from _shared import ROOT, data_root, receipts, setting, stamp
from _shared import check as check_files

OUT = ROOT / "data" / "carbon_arc" / "catalogue"
SNAPSHOTS = ROOT / "data" / "carbon_arc"
USAGE = (
    "uv run run.py --data carbon check | catalogue [first N] | entities | verify"
    " | refetch <snapshot> | plan <spec.json> | buy <plan.json> <cap> | rebuy <from> <to> <cap>"
)
# A fresh quote may sit at most this far above the planned price.
DRIFT = 1.02


# The token from the environment or .env, never printed or logged.
def token() -> str:
    return setting("API_AUTH_TOKEN")


# Every SDK request gets a time limit, since a stalled reply never ends.
def patience(seconds: int = 120) -> None:
    import requests

    send = requests.Session.request

    # The original request, given a timeout unless the caller set one.
    def limited(self, *args, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return send(self, *args, **kwargs)

    requests.Session.request = limited


# Free, read-only calls that prove the token works and spend nothing.
def check() -> int:
    key = token()
    if not key:
        print("No API_AUTH_TOKEN yet: paste your Carbon Arc API key into .env.")
        return 1
    from carbonarc import CarbonArcClient

    client = CarbonArcClient(key)
    print(f"Token found ({len(key)} characters, not shown).")
    calls = {
        "Balance": client.client.get_balance,
        "Past orders": client.client.get_order_history,
        "Datasets": client.data.get_datasets,
        "Ontology version": client.ontology.get_ontology_version,
    }
    failed = 0
    for name, call in calls.items():
        try:
            print(f"{name}:", summary(call()))
        except Exception as err:  # noqa: BLE001
            print(f"{name}: refused ({type(err).__name__}: {err})")
            failed += 1
    print("Nothing was bought and MCP was not used.")
    return 1 if failed else 0


# A short view of a reply: counts for long lists, the value otherwise.
def summary(reply: object) -> str:
    if isinstance(reply, dict):
        parts = [
            f"{k} {len(v)} items" if isinstance(v, list) else f"{k} {v}"
            for k, v in reply.items()
            if isinstance(v, list | str | int | float | bool | type(None))
        ]
        return ", ".join(parts)[:300]
    text = str(reply)
    return text if len(text) <= 300 else text[:300] + " ..."


# Saves one free reply as JSON once, retrying busy replies, noting 404s.
def save(path: Path, call: Callable[[], object], manifest: dict) -> None:
    if path.exists():
        return
    reply, last = None, None
    for wait in (0.2, 5, 15, 45):
        time.sleep(wait)
        try:
            reply = call()
            break
        except Exception as err:  # noqa: BLE001
            last = err
            if "404" in str(err):
                reply = {"missing": str(err)}
                break
    if reply is None:
        manifest["errors"].append(f"{path.relative_to(OUT)}: {last}")
        return
    text = json.dumps(reply, default=str, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    manifest["files"][path.relative_to(OUT).as_posix()] = hashlib.sha256(text.encode()).hexdigest()


# Every dataset's metadata and the ontology, free, with receipts.
def catalogue(limit: int | None = None) -> int:
    key = token()
    if not key:
        print("No API_AUTH_TOKEN yet: paste your Carbon Arc API key into .env.")
        return 1
    from carbonarc import CarbonArcClient

    patience()
    client, receipt = CarbonArcClient(key), OUT / "manifest.json"
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(receipt.read_text()) if receipt.exists() else {"files": {}}
    manifest["errors"] = []
    listing = client.data.get_datasets()
    (OUT / "datasets.json").write_text(json.dumps(listing, default=str, indent=1))
    ids = sorted({i for d in listing["datasources"] for i in d.get("dataset_id") or []})
    data = client.data
    calls = {
        "information": data.get_dataset_information,
        "dictionary": data.get_data_dictionary,
        "sample": data.get_data_sample,
        "schedule": data.get_dataset_schedule,
        "insights": lambda d: every_insight(data, d),
    }
    for n, ds in enumerate(ids[:limit], 1):
        # Insight lists saved before paging was fixed are fetched again.
        stale = OUT / ds / "insights.json"
        if stale.exists():
            old = json.loads(stale.read_text(encoding="utf-8"))
            if old.get("total", 0) > len(old.get("items", [])):
                stale.unlink()
        for name, call in calls.items():
            save(OUT / ds / f"{name}.json", lambda c=call, d=ds: c(d), manifest)
        print(f"{n} of {len(ids[:limit])} {ds}", flush=True)
    onto = client.ontology
    maps = {
        "version": onto.get_ontology_version,
        "versions": onto.get_ontology_versions,
        "tree": onto.get_ontology_tree,
        "insight_map": onto.get_insight_map,
        "entity_map": onto.get_entity_map,
        "subjects": onto.get_subjects,
        "topics": onto.get_topics,
    }
    for name, call in maps.items():
        save(OUT / "ontology" / f"{name}.json", call, manifest)
    manifest |= {"pulled_at": stamp(), "sdk": "carbonarc 1.1.19"}
    manifest["datasets"] = len(ids)
    receipt.write_text(json.dumps(manifest, indent=1))
    print(f"Saved {len(manifest['files'])} files, {len(manifest['errors'])} errors, to {OUT}")
    print("Nothing was bought and MCP was not used.")
    return 0


# Carbon Arc's free company list in every name form, for PERMNO links.
def entities() -> int:
    key = token()
    if not key:
        print("No API_AUTH_TOKEN yet: paste your Carbon Arc API key into .env.")
        return 1
    from carbonarc import CarbonArcClient

    patience()
    onto, folder = CarbonArcClient(key).ontology, OUT / "entities"
    receipt = folder / "manifest.json"
    manifest = {"files": {}, "errors": []}
    page = pages = 1
    while page <= pages:
        path = folder / f"page_{page:03d}.json"
        listing = lambda p=page: onto.get_entities(entity=["company"], page=p, size=1000)  # noqa: E731
        save(path, listing, manifest)
        if path.exists():
            pages = json.loads(path.read_text(encoding="utf-8")).get("pages", pages)
        print(f"page {page} of {pages}", flush=True)
        page += 1
    rows = []
    for path in sorted(folder.glob("page_*.json")):
        rows += json.loads(path.read_text(encoding="utf-8")).get("entities", [])
    keep = ["entity_id", "label", "representation", "entity_domain", "figi_code"]
    slim = [{k: row.get(k) for k in keep} for row in rows]
    (folder / "companies.json").write_text(json.dumps(slim, indent=0), encoding="utf-8")
    manifest |= {"pulled_at": stamp(), "sdk": "carbonarc 1.1.19"}
    manifest["companies"] = len(slim)
    receipt.write_text(json.dumps(manifest, indent=1))
    forms = {}
    for row in slim:
        forms[row["representation"]] = forms.get(row["representation"], 0) + 1
    print(f"Saved {len(slim)} company entries {forms}, {len(manifest['errors'])} errors")
    print("Nothing was bought and MCP was not used.")
    return 0


# A dataset's insights, every page, since the SDK call stops at 25.
def every_insight(data, ds: str) -> dict:
    url = f"{data.base_data_url}/data/{ds}/insights"
    first = data._get(url, params={"page": 1, "size": 100})
    items, page = list(first.get("items", [])), 1
    while len(items) < first.get("total", 0):
        page += 1
        more = data._get(url, params={"page": page, "size": 100}).get("items", [])
        if not more:
            break
        items += more
    return first | {"items": items, "size": len(items), "pages": 1}


# Tokens rounded up to the cent, so a printed cap always covers the sum.
def cents(amount: float) -> float:
    return math.ceil(round(amount * 100, 6)) / 100


# True for a real positive price; 0.0 means Carbon Arc cannot fill it.
def priced(price: object) -> bool:
    number = isinstance(price, int | float) and not isinstance(price, bool)
    return number and price > 0


# Every value stored under one key anywhere inside a reply.
def find(reply: object, key: str) -> list:
    if isinstance(reply, dict):
        found = [reply[key]] if key in reply else []
        return found + [v for item in reply.values() for v in find(item, key)]
    if isinstance(reply, list):
        return [v for item in reply for v in find(item, key)]
    return []


# The framework ids an order reply names: a plain list, or nested keys.
def bought(order: object) -> list[str]:
    listed = order.get("frameworks", []) if isinstance(order, dict) else []
    ids = {str(i) for i in listed if isinstance(i, str)}
    return sorted(ids or {str(i) for i in find(order, "framework_id")})


# Rows in a data reply, whether it holds records or columns.
def rows(reply: object) -> int:
    data = reply.get("data") if isinstance(reply, dict) else reply
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and data:
        return len(next(iter(data.values())))
    return 0


# Carbon Arc ids for named tickers, from the free company list.
def tickers(names: list[str]) -> list[dict]:
    listing = json.loads((OUT / "entities" / "companies.json").read_text(encoding="utf-8"))
    ids = {r["label"]: r["entity_id"] for r in listing if r["representation"] == "ticker"}
    missing = [n for n in names if n not in ids]
    if missing:
        raise KeyError(f"not in Carbon Arc's ticker list: {missing}")
    return [{"carc_id": ids[n], "representation": "ticker"} for n in names]


# One item's request: its entities, full history to today, its area.
def request(explorer, item: dict) -> dict:
    entities = item.get("entities") or tickers(item["tickers"])
    draft = explorer.build_framework(entities=entities, insight=item["insight"], filters={})
    chosen = {}
    for offer in explorer.collect_framework_filters(draft).get("filters", []):
        options = [o.get("key") for o in offer.get("option_values") or []]
        if offer["key"] == "date_resolution":
            step = item.get("step", "month")
            chosen["date_resolution"] = step if step in options else offer.get("default_value")
        # US when offered, else the one area offered ("ww" for some).
        elif offer["key"] == "location_resolution":
            area = "us" if "us" in options else offer.get("default_value")
            # No area offered and no default leaves the filter unset.
            if area is not None:
                chosen["location_resolution"] = area
        # The full range, never past today: a future end quotes 0.0.
        elif offer.get("select_type") == "date-range" and offer.get("table_earliest_date"):
            span = {"start_date": offer["table_earliest_date"][:10]}
            end = min(offer["table_latest_date"][:10], stamp()[:10])
            chosen[offer["key"]] = span | {"end_date": end}
    aggregate = item.get("aggregate")
    return explorer.build_framework(entities, item["insight"], chosen, aggregate)


# The Carbon Arc client with its time limit, or None without a token.
def connect(seconds: int = 300):
    key = token()
    if not key:
        print("No API_AUTH_TOKEN yet: paste your Carbon Arc API key into .env.")
        return None
    from carbonarc import CarbonArcClient

    patience(seconds)
    return CarbonArcClient(key)


# Prices a spec's items into a plan file for the leader, buying nothing.
def plan(spec_path: str, client=None) -> int:
    client = client or connect()
    if client is None:
        return 1
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    items = []
    for item in spec["items"]:
        row = dict(item)
        try:
            row["framework"] = request(client.explorer, item)
            row["price"] = client.explorer.check_framework_price(row["framework"])
        except Exception as err:  # noqa: BLE001
            row["error"] = f"{type(err).__name__}: {str(err)[:200]}"
        items.append(row)
        shown = row.get("error") or row["price"]
        if "error" not in row and not priced(row["price"]):
            shown = "0.0, Carbon Arc cannot fill this request"
        print(f"{item['name']:44} {shown}", flush=True)
        time.sleep(1)
    good = [r for r in items if priced(r.get("price"))]
    total = cents(sum(r["price"] for r in good))
    target = Path(spec_path).with_suffix(".plan.json")
    book = {"snapshot": spec["snapshot"], "planned_at": stamp()}
    book |= {"total": total, "items": items}
    target.write_text(json.dumps(book, default=str, indent=1), encoding="utf-8")
    print(f"{len(good)} priced, {total} tokens in all, {len(items) - len(good)} not buyable.")
    print(f"Nothing was bought. To buy: uv run run.py --data carbon buy {target} {total}")
    return 0


# Saves a bought framework's data into its receipt; downloads are free.
def keep(explorer, fid: str, target: Path, receipt: dict) -> None:
    reply = explorer.get_framework_data(fid, fetch_all=True)
    body = json.dumps(reply, default=str).encode()
    part = target.with_suffix(".part")
    part.write_bytes(gzip.compress(body))
    part.replace(target)
    receipt |= {"framework_id": fid, "rows": rows(reply), "bytes": len(body)}
    receipt["sha256"] = hashlib.sha256(body).hexdigest()
    receipt["metadata"] = explorer.get_framework_metadata(fid)
    receipt["pulled_at"] = stamp()


# Buys a plan's priced items, one order each, and never past the cap.
def buy(plan_path: str, cap: float, client=None) -> int:
    book = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    folder = SNAPSHOTS / book["snapshot"]
    folder.mkdir(parents=True, exist_ok=True)
    # The cap covers this run only: items already saved are not counted.
    items = [r for r in book["items"] if priced(r.get("price"))]
    items = [r for r in items if not (folder / f"{r['name']}.json.gz").exists()]
    if cents(sum(r["price"] for r in items)) > cap:
        print(f"The unbought items total more than the cap of {cap}; nothing bought.")
        return 1
    client = client or connect(600)
    if client is None:
        return 1
    balance = client.client.get_balance
    start = balance()["total_balance"]
    spent = 0.0
    print(f"Balance before: {start}. Cap: {cap}.", flush=True)
    for item in items:
        name = item["name"]
        target = folder / f"{name}.json.gz"
        if target.exists():
            continue
        # A fresh quote must stay near the plan and inside the cap.
        price = client.explorer.check_framework_price(item["framework"])
        over = not priced(price) or price > item["price"] * DRIFT
        if over or cents(spent + price) > cap:
            print(f"STOP before {name}: quote {price}, planned {item['price']}, spent {spent}")
            return 1
        order = client.explorer.buy_frameworks([item["framework"]])
        now = balance()["total_balance"]
        spent = round(start - now, 6)
        receipt = {"item": item, "price_at_buy": price, "order": order, "balance_after": now}
        book_path = folder / f"{name}.receipt.json"
        book_path.write_text(json.dumps(receipt, default=str, indent=1))
        if cents(spent) > cap:
            print(f"STOP: spent {spent}, above the cap of {cap}; see {book_path}")
            return 1
        ids = bought(order)
        if len(ids) != 1:
            print(f"STOP: {name} order names {len(ids)} frameworks; see {book_path}")
            return 1
        keep(client.explorer, ids[0], target, receipt)
        book_path.write_text(json.dumps(receipt, default=str, indent=1))
        print(f"{name}: {receipt['rows']:,} rows, cost {price}, spent {spent} of {cap}")
        time.sleep(1)
    history = client.client.get_order_history()
    (folder / "orders.json").write_text(json.dumps(history, default=str, indent=1))
    end = balance()["total_balance"]
    print(f"Done. Balance {start} before, {end} after, {round(start - end, 2)} spent.")
    return 0


# Buys a snapshot's frameworks again, for the revision check.
def rebuy(source: str, target: str, cap: float, client=None) -> int:
    client = client or connect(600)
    if client is None:
        return 1
    items = []
    for path in sorted((SNAPSHOTS / source).glob("*.receipt.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        payload = (receipt.get("metadata") or {}).get("payload")
        if not payload:
            continue
        framework = {k: v for k, v in payload.items() if v is not None}
        name = path.name.removesuffix(".receipt.json")
        price = client.explorer.check_framework_price(framework)
        items.append({"name": name, "framework": framework, "price": price})
        print(f"{name:44} quote {price}", flush=True)
    folder = SNAPSHOTS / target
    folder.mkdir(parents=True, exist_ok=True)
    book = {"snapshot": target, "planned_at": stamp(), "items": items}
    plan_path = folder / "rebuy.plan.json"
    plan_path.write_text(json.dumps(book, default=str, indent=1), encoding="utf-8")
    return buy(str(plan_path), cap, client)


# Every saved file against its receipt: catalogue, companies, snapshots.
def verify() -> int:
    bad = 0
    for book in (OUT / "manifest.json", OUT / "entities" / "manifest.json"):
        files = receipts(book).get("files", {})
        wrong = check_files(OUT, files)
        print(f"carbon {book.parent.name}: {len(files)} files, {len(wrong)} wrong {wrong[:5]}")
        bad += len(wrong)
    for folder in sorted(p for p in SNAPSHOTS.glob("snapshot_*") if p.is_dir()):
        wrong, count = [], 0
        for book in sorted(folder.glob("*.receipt.json")):
            digest = receipts(book).get("sha256")
            data = book.with_name(book.name.replace(".receipt.json", ".json.gz"))
            if not digest:
                continue
            count += 1
            body = gzip.decompress(data.read_bytes()) if data.exists() else b""
            if hashlib.sha256(body).hexdigest() != digest:
                wrong.append(data.name)
        print(f"carbon {folder.name}: {count} files, {len(wrong)} wrong {wrong[:5]}")
        bad += len(wrong)
    return 1 if bad else 0


# Downloads owned frameworks again (free) and compares them with ours.
def refetch(snapshot: str, client=None) -> int:
    client = client or connect(600)
    if client is None:
        return 1
    source = ROOT / "data" / "carbon_arc" / snapshot
    target = SNAPSHOTS / f"{snapshot}_refetch"
    target.mkdir(parents=True, exist_ok=True)
    start = client.client.get_balance()["total_balance"]
    changed = 0
    for book in sorted(source.glob("*.receipt.json")):
        saved = receipts(book)
        if not saved.get("framework_id"):
            continue
        reply = client.explorer.get_framework_data(saved["framework_id"], fetch_all=True)
        body = json.dumps(reply, default=str).encode()
        name = book.name.replace(".receipt.json", ".json.gz")
        (target / name).write_bytes(gzip.compress(body))
        same = hashlib.sha256(body).hexdigest() == saved.get("sha256")
        changed += not same
        print(f"{name}: {'same' if same else 'CHANGED'} ({rows(reply):,} rows)", flush=True)
    end = client.client.get_balance()["total_balance"]
    print(f"{changed} changed since purchase. Balance {start} before, {end} after; MCP not used.")
    return 0 if end == start else 1


# One verb per run, with the arguments its usage line names.
if __name__ == "__main__":
    root = data_root(sys.argv)
    OUT, SNAPSHOTS = root / "carbon_arc" / "catalogue", root / "carbon_arc"
    verb, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if verb == "catalogue":
        sys.exit(catalogue(int(rest[0]) if rest else None))
    if verb in ("check", "entities", "verify") and not rest:
        sys.exit({"check": check, "entities": entities, "verify": verify}[verb]())
    if verb == "refetch" and len(rest) == 1:
        sys.exit(refetch(rest[0]))
    if verb == "plan" and len(rest) == 1:
        sys.exit(plan(rest[0]))
    if verb == "buy" and len(rest) == 2:
        sys.exit(buy(rest[0], float(rest[1])))
    if verb == "rebuy" and len(rest) == 3:
        sys.exit(rebuy(rest[0], rest[1], float(rest[2])))
    print(f"Usage: {USAGE}")
    sys.exit(2)
