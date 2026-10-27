# FEMA's county clock and its Federal Register back-dating check.

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEMA = ROOT / "data" / "fema"
REGISTER = FEMA / "federal_register"
CARDS = ROOT / "data" / "v4" / "cards"
# The bars set before the check ran.
LATE_DAYS, LATE_SHARE, MAX_UNMATCHED = 30, 0.05, 20
DAMAGE = ("IA", "IH", "IFG", "HA", "DH", "DUA", "CC", "PA")
SUFFIX = re.compile(r"\s*\((County|Parish|Borough|Census Area|Municipio)\)\s*$")
ALL_AREAS = re.compile(r"\ball\b[^.]*\b(counties|parishes|areas|municipalities|boroughs)\b", re.I)
ASSISTANCE = re.compile(r"\b(individual|public) assistance\b", re.I)


# Check 1: designations dated before their disaster's declaration.
def check_order() -> dict:
    s = pd.read_csv(
        FEMA / "DisasterDeclarationsSummaries.csv",
        usecols=["disasterNumber", "declarationType", "declarationDate"],
    )
    s = s[s["declarationType"] == "DR"]
    declared = pd.to_datetime(s["declarationDate"], utc=True).dt.tz_localize(None)
    first = declared.groupby(s["disasterNumber"]).min()
    cols = ["disasterNumber", "placeName", "designatedDate", "programTypeCode"]
    a = pd.read_csv(FEMA / "FemaWebDeclarationAreas.csv", usecols=cols)
    a = a[
        a["disasterNumber"].isin(first.index)
        & a["programTypeCode"].str.startswith(DAMAGE, na=False)
    ]
    when = pd.to_datetime(a["designatedDate"], utc=True).dt.tz_localize(None).dt.normalize()
    early = when < a["disasterNumber"].map(first).dt.normalize()
    return {"designations": len(a), "before_declaration": int(early.sum())}


# A notice names the county as a whole word, or all areas for IA or PA.
def names_county(text: str, county: str) -> bool:
    if re.search(rf"\b{re.escape(county)}\b", text, re.I):
        return True
    sentences = re.split(r"(?<=[.;])\s+", text)
    return any(
        ALL_AREAS.search(s) and ASSISTANCE.search(s) and "mitigation" not in s.lower()
        for s in sentences
    )


# The first notice for a disaster naming the county, or all its areas.
def notice_date(number: int, county: str) -> pd.Timestamp | None:
    path = REGISTER / f"FEMA-{number}-DR.json"
    if not path.exists():
        return None
    docs = json.loads(path.read_text()).get("results", [])
    for doc in sorted(docs, key=lambda d: d["publication_date"]):
        text_path = REGISTER / f"{doc['document_number']}.txt"
        if text_path.exists() and names_county(text_path.read_text(errors="replace"), county):
            return pd.Timestamp(doc["publication_date"])
    return None


# Check 2: the sample's gaps between FEMA's date and the notice date.
def check_notices() -> dict:
    sample = pd.read_csv(REGISTER / "sample.csv", parse_dates=["designatedDate"])
    rows = []
    for r in sample.itertuples():
        county = SUFFIX.sub("", r.placeName)
        found = notice_date(int(r.disasterNumber), county)
        gap = None if found is None else int((found - r.designatedDate.normalize()).days)
        rows.append(
            {
                "disaster": int(r.disasterNumber),
                "state": r.stateCode,
                "county": county,
                "fema": str(r.designatedDate.date()),
                "notice": None if found is None else str(found.date()),
                "gap_days": gap,
            }
        )
    table = pd.DataFrame(rows)
    matched = table.dropna(subset=["gap_days"])
    late = float((matched["gap_days"] > LATE_DAYS).mean()) if len(matched) else float("nan")
    out = {
        "sample": len(table),
        "matched": len(matched),
        "unmatched": int(table["gap_days"].isna().sum()),
    }
    out |= {
        "late_share": round(late, 4),
        "gap_days_median": float(matched["gap_days"].median()) if len(matched) else None,
    }
    out["gap_days_quantiles"] = (
        matched["gap_days"].quantile([0.05, 0.25, 0.75, 0.95]).round(1).to_dict()
        if len(matched)
        else {}
    )
    out["rows"] = rows
    return out


# Both checks and the rule's outcome, written to the FEMA card.
def run() -> dict:
    report = {"order": check_order(), "notices": check_notices()}
    n = report["notices"]
    if n["unmatched"] > MAX_UNMATCHED:
        verdict = "inconclusive: FEMA is not the fast clock; NOAA's event month + 4 months applies"
    elif n["late_share"] > LATE_SHARE:
        verdict = "late: notice dates replace FEMA dates where one exists"
    else:
        verdict = "pass: FEMA counts from the end of its date, county by county"
    report["verdict"] = verdict
    CARDS.mkdir(parents=True, exist_ok=True)
    (CARDS / "fema_check.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# Runs the back-dating check: uv run python -m fiam.vfinal.fema
if __name__ == "__main__":
    r = run()
    n = {k: v for k, v in r["notices"].items() if k != "rows"}
    print(
        json.dumps(
            {"order": r["order"], "notices": n, "verdict": r["verdict"]}, indent=1, default=str
        )
    )
