# Carbon Arc coverage: each insight's full entity list and free quotes.

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carbon_arc as ca  # noqa: E402
from _shared import stamp  # noqa: E402

FULL = ca.SNAPSHOTS / "access" / "insight_entities_full"
USAGE = "python -m tools.data.carbon_coverage entities [insight ...] | quote <spec.json>"
# Owned and candidate insights; 461, 497 and 501 are the Benzinga buys.
INSIGHTS = [626, 45862, 379, 634, 635, 11676, 347, 385, 544, 343, 245]
INSIGHTS += [17610, 17611, 450, 461, 497, 501]
# Rows per page; the old files hold only the endpoint's default 25.
PAGE = 1000


# Every entity the insight accepts, paged past the default 25 (free).
def every_entity(onto, insight: int) -> tuple[list[dict], int]:
    url = f"{onto.base_ontology_url}/insight/{insight}/entities"
    seen, page = {}, 1
    while True:
        rows = onto._get(url, params={"page": page, "size": PAGE}).get("entities", [])
        for row in rows:
            seen[(row["carc_id"], row["entity_representation_name"])] = row
        # A short page is the last one.
        if len(rows) < PAGE:
            return list(seen.values()), page
        page += 1


# Saves each insight's full list once, with its time, count and hash.
def entities(insights: list[int], client=None) -> int:
    client = client or ca.connect()
    if client is None:
        return 1
    FULL.mkdir(parents=True, exist_ok=True)
    for insight in insights:
        path = FULL / f"{insight}.json"
        if path.exists():
            print(f"{insight}: kept {path.name}")
            continue
        rows, pages = every_entity(client.ontology, insight)
        # The filtered ontology search's own total, as a cross-check.
        total = client.ontology.get_entities(insight_id=insight, page=1, size=1).get("total")
        body = json.dumps({"insight": insight, "entities": rows}, indent=0)
        receipt = {"insight": insight, "pulled_at": stamp(), "count": len(rows), "pages": pages}
        receipt |= {"search_total": total, "sha256": hashlib.sha256(body.encode()).hexdigest()}
        receipt["route"] = "GET ontology/insight/{id}/entities?page&size (free)"
        path.write_text(body, encoding="utf-8")
        path.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=1))
        print(f"{insight}: {len(rows)} entities in {pages} pages, search total {total}")
    print("Nothing bought, MCP not used.")
    return 0


# carbon_arc.plan for entity specs: free prices, nothing bought.
def quote(spec_path: str, client=None) -> int:
    return ca.plan(spec_path, client)


# One verb per run.
if __name__ == "__main__":
    verb, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if verb == "entities":
        sys.exit(entities([int(i) for i in rest] or INSIGHTS))
    if verb == "quote" and len(rest) == 1:
        sys.exit(quote(rest[0]))
    print(f"Usage: {USAGE}")
    sys.exit(2)
