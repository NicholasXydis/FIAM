# OpenFEMA declarations and the Federal Register sample, receipted.

import hashlib
import io
import json
import sys
import urllib.error
import urllib.parse

import pandas as pd
from _shared import ROOT, fetch, receipts, stamp

OUT = ROOT / "data" / "fema"
USAGE = "uv run run.py --data fema fetch | federal | notices | verify"
API = "https://www.fema.gov/api/open"
DATASETS = {
    "DisasterDeclarationsSummaries": "v2",
    "FemaWebDeclarationAreas": "v1",
}
REGISTER = "https://www.federalregister.gov/api/v1/documents.json"
# The sample, set before the check ran.
SEED, SIZE, FIRST, LAST = 20261023, 100, "1994-01-01", "2020-12-31"
# Notices for every major disaster the exhibit and live flags can use.
NOTICES_FROM = "2012-01-01"
COUNTY_TYPES = ("(County)", "(Parish)", "(Borough)", "(Census Area)", "(Municipio)")
# Individual and Public Assistance programs: a county the disaster hit.
DAMAGE = ("IA", "IH", "IFG", "HA", "DH", "DUA", "CC", "PA")
PACE = 0.5


# One file saved with its receipt in the folder's receipts book.
def keep(folder, name: str, url: str, body: bytes, extra: dict | None = None) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f"{name}.part"
    part.write_bytes(body)
    part.replace(folder / name)
    entry = {"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    return entry | {"pulled_at": stamp()} | (extra or {})


# Both OpenFEMA datasets in full, with each one's refresh date.
def get_datasets() -> int:
    book = OUT / "receipts.json"
    saved = receipts(book)
    names = " or ".join(f"name eq '{n}'" for n in DATASETS)
    query = urllib.parse.quote(names)
    meta = json.loads(
        fetch(f"{API}/v1/DataSets?$filter={query}&$select=name,lastRefresh,recordCount")
    )
    refresh = {d["name"]: d for d in meta["DataSets"]}
    for name, version in DATASETS.items():
        url = f"{API}/{version}/{name}.csv"
        body = fetch(url, pace=PACE)
        rows = len(pd.read_csv(io.BytesIO(body), usecols=[0]))
        extra = {"rows": rows, "last_refresh": refresh.get(name, {}).get("lastRefresh")}
        saved[f"{name}.csv"] = keep(OUT, f"{name}.csv", url, body, extra)
        book.write_text(json.dumps(saved, indent=1))
        print(f"{name}: {rows:,} rows, {len(body) >> 20} MB", flush=True)
    return 0


# The seeded sample of 100 county designations of major disasters.
def sample() -> pd.DataFrame:
    s = pd.read_csv(
        OUT / "DisasterDeclarationsSummaries.csv", usecols=["disasterNumber", "declarationType"]
    )
    major = set(s.loc[s["declarationType"] == "DR", "disasterNumber"])
    cols = ["disasterNumber", "stateCode", "placeName", "designatedDate", "programTypeCode"]
    a = pd.read_csv(OUT / "FemaWebDeclarationAreas.csv", usecols=cols)
    a = a[a["disasterNumber"].isin(major) & a["placeName"].str.endswith(COUNTY_TYPES, na=False)]
    # Damage programs only, never the statewide hazard mitigation one.
    a = a[a["programTypeCode"].str.startswith(DAMAGE, na=False)]
    a["designatedDate"] = pd.to_datetime(a["designatedDate"], utc=True).dt.tz_localize(None)
    first = a.groupby(["disasterNumber", "stateCode", "placeName"], as_index=False)[
        "designatedDate"
    ].min()
    inside = first[first["designatedDate"].between(FIRST, LAST)]
    return inside.sample(SIZE, random_state=SEED).sort_values("designatedDate")


# One disaster's Federal Register documents, every page, and their text.
def register(number: int, folder, saved: dict, book) -> int:
    name = f"FEMA-{number}-DR.json"
    if name not in saved:
        results, page = [], 1
        while True:
            params = {
                "per_page": 100,
                "page": page,
                "order": "oldest",
                "conditions[agencies][]": "federal-emergency-management-agency",
                "conditions[term]": f'"FEMA-{number}-DR"',
                "fields[]": ["publication_date", "document_number", "title", "raw_text_url"],
            }
            url = f"{REGISTER}?{urllib.parse.urlencode(params, doseq=True)}"
            found = json.loads(fetch(url, pace=PACE))
            results += found.get("results", [])
            if len(results) >= found.get("count", 0) or not found.get("results"):
                break
            page += 1
        body = json.dumps({"count": found.get("count", 0), "results": results}).encode()
        saved[name] = keep(folder, name, url, body)
        book.write_text(json.dumps(saved, indent=1))
    docs = json.loads((folder / name).read_text()).get("results", [])
    for doc in docs:
        text = f"{doc['document_number']}.txt"
        if text in saved or not doc.get("raw_text_url"):
            continue
        # A document with no text copy is recorded as absent, not fatal.
        try:
            body = fetch(doc["raw_text_url"], pace=PACE)
        except urllib.error.HTTPError as err:
            if err.code != 404:
                raise
            saved[text] = {"url": doc["raw_text_url"], "absent": True, "pulled_at": stamp()}
        else:
            saved[text] = keep(folder, text, doc["raw_text_url"], body)
        book.write_text(json.dumps(saved, indent=1))
    return len(docs)


# Each sampled disaster's Federal Register documents and their text.
def federal() -> int:
    picked = sample()
    folder = OUT / "federal_register"
    folder.mkdir(parents=True, exist_ok=True)
    picked.to_csv(folder / "sample.csv", index=False)
    book = folder / "receipts.json"
    saved = receipts(book)
    for number in sorted(picked["disasterNumber"].unique()):
        print(
            f"FEMA-{number}-DR: {register(int(number), folder, saved, book)} documents", flush=True
        )
    print(f"Done: {picked['disasterNumber'].nunique()} disasters, {len(saved)} files")
    return 0


# Every major disaster's notices from 2012 on, the notice rule's clock.
def notices() -> int:
    s = pd.read_csv(
        OUT / "DisasterDeclarationsSummaries.csv",
        usecols=["disasterNumber", "declarationType", "declarationDate"],
    )
    s = s[(s["declarationType"] == "DR") & (s["declarationDate"] >= NOTICES_FROM)]
    folder = OUT / "federal_register"
    book = folder / "receipts.json"
    saved = receipts(book)
    numbers = sorted(s["disasterNumber"].unique())
    for n, number in enumerate(numbers, 1):
        count = register(int(number), folder, saved, book)
        if n % 50 == 0:
            print(f"{n} of {len(numbers)} disasters (FEMA-{number}-DR: {count})", flush=True)
    print(f"Done: {len(numbers)} disasters, {len(saved)} files")
    return 0


# Every saved file against its receipt, both folders.
def verify() -> int:
    bad = []
    for folder in (OUT, OUT / "federal_register"):
        for name, entry in receipts(folder / "receipts.json").items():
            if entry.get("absent"):
                continue
            path = folder / name
            ok = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
            bad += [] if ok else [name]
    print(f"fema: {len(bad)} differ {bad[:3]}")
    return 1 if bad else 0


# One verb per run.
if __name__ == "__main__":
    verbs = {"fetch": get_datasets, "federal": federal, "notices": notices, "verify": verify}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(verbs[verb]())
