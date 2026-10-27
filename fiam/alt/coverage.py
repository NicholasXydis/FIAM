# How many trading-universe stocks each Carbon Arc insight covers.

import json
from pathlib import Path

import pandas as pd

from fiam.vfinal.links import entity_key, plain_symbol

ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT / "data" / "carbon_arc" / "access" / "insight_entities_full"
OUT = ROOT / "out" / "alt" / "coverage"
# Each insight we own or priced: its dataset and what it measures.
INSIGHTS = {
    626: ("CA0056", "card spend"),
    45862: ("CA0060", "foot traffic"),
    379: ("CA0030", "web traffic"),
    634: ("CA0052", "star rating"),
    635: ("CA0052", "review count"),
    11676: ("CA0043B", "company links"),
    347: ("CA0028", "card spend, detailed panel"),
    385: ("CA0029", "convenience store sales"),
    544: ("CA0047", "supermarket sales"),
    343: ("CA0038", "net sales"),
    245: ("CA009", "ad spend"),
    17610: ("CA0043C", "software customers by company"),
    17611: ("CA0043C", "software customers by brand"),
    450: ("CA0043D", "product launches"),
    461: ("CA0035", "insider news"),
    497: ("CA0035", "offerings"),
    501: ("CA0035", "deals"),
}
# The blind window: universe months and the exits that count as dead.
START, LAST = pd.Timestamp("2015-01-31"), pd.Timestamp("2020-12-31")
# Brand forms that can carry a firm's name; categories and places never.
BRANDS = {"retailer", "service", "product", "website", "vehiclemake"}
# Shorter name keys ("GE", "3M") match too much to count.
MIN_KEY = 3


# Sorted words run together, so "PENNEY J C" meets "JCPenney".
def compact(name) -> str:
    return entity_key(name).replace(" ", "")


# Carbon Arc entities as keys: US tickers, company and brand names.
def carc_keys(entities: list[dict]) -> pd.DataFrame:
    rows = pd.DataFrame(entities, columns=["carc_id", "carc_name", "entity_representation_name"])
    rows = rows.rename(columns={"carc_name": "label", "entity_representation_name": "rep"})
    tick = rows[(rows["rep"] == "ticker") & ~rows["label"].str.contains(" ")]
    tick = tick.assign(how="ticker", key=plain_symbol(tick["label"]).to_numpy())
    named = rows[rows["rep"].isin(BRANDS | {"company"})].copy()
    named["how"] = named["rep"].map(lambda r: "name" if r == "company" else "brand")
    named["key"] = named["label"].map(compact)
    named = named[named["key"].str.len() >= MIN_KEY]
    return pd.concat([tick, named])[["carc_id", "rep", "label", "how", "key"]]


# Each stock's 2015-2020 tickers (latest holder only) and names as keys.
def stock_keys(links: pd.DataFrame, permnos) -> pd.DataFrame:
    live = links[
        (links["valid_to"].isna() | (links["valid_to"] >= START - pd.offsets.MonthBegin()))
    ]
    live = live[live["valid_from"] <= LAST]
    tick = links[links["kind"].isin(["ticker", "symbol"])].assign(
        key=lambda f: plain_symbol(f["value"]).to_numpy()
    )
    # A reused ticker goes to its latest holder by 2020, not the dead one.
    owner = tick.sort_values("valid_from").groupby("key")["permno"].last()
    mine = tick[tick.index.isin(live.index)]
    mine = mine[mine["permno"].to_numpy() == mine["key"].map(owner).to_numpy()]
    names = live[live["kind"] == "name"].assign(key=lambda f: f["value"].map(compact))
    names = names[names["key"].str.len() >= MIN_KEY]
    out = pd.concat([mine.assign(how="ticker"), names.assign(how="name")])
    out = out[out["permno"].isin(set(permnos))]
    return out[["permno", "how", "key"]].drop_duplicates()


# Stocks whose 2015-2020 CRSP name is a Carbon Arc company name too.
def name_agrees(links: pd.DataFrame, permnos, carc_entities: list[dict]) -> set:
    carc = carc_keys(carc_entities)
    named = set(carc.loc[carc["how"] == "name", "key"])
    keys = stock_keys(links, [int(p) for p in permnos])
    return set(keys.loc[(keys["how"] == "name") & keys["key"].isin(named), "permno"])


# Per stock, whether a ticker, company name or brand name matches.
def flags(stocks: pd.DataFrame, carc: pd.DataFrame) -> pd.DataFrame:
    pairs = stocks.merge(carc, on="key", suffixes=("", "_carc"))
    pairs = pairs[(pairs["how"] == "ticker") == (pairs["how_carc"] == "ticker")]
    out = pd.DataFrame(index=pd.Index(sorted(stocks["permno"].unique()), name="permno"))
    for how in ("ticker", "name", "brand"):
        out[how] = out.index.isin(pairs.loc[pairs["how_carc"] == how, "permno"])
    out["covered"] = out["ticker"] | out["name"]
    return out.reset_index()


# Universe stocks over the months, and whether each is in the last.
def universe(eoms) -> pd.DataFrame:
    from fiam.vfinal import universe as v4

    rows = []
    for eom in eoms:
        m = v4.members(eom)
        rows.append(m.loc[m["new_long"], ["permno"]].assign(eom=pd.Timestamp(eom)))
    seen = pd.concat(rows)
    out = seen.groupby("permno")["eom"].agg(months="count", last_eom="max").reset_index()
    return out.assign(in_last=out["last_eom"] == pd.Timestamp(eoms[-1]))


# Listed at 2020-12 or delisted 2015-2020 with its group; dates only.
def status(permnos, exits: pd.DataFrame) -> pd.DataFrame:
    gone = exits[
        (exits["exit_date"] >= START - pd.offsets.MonthBegin()) & (exits["exit_date"] <= LAST)
    ]
    gone = gone.sort_values("exit_date").drop_duplicates("permno", keep="last")
    out = pd.DataFrame({"permno": sorted(set(permnos))}).merge(
        gone[["permno", "exit_date", "group"]], on="permno", how="left"
    )
    out["status"] = out["exit_date"].notna().map({True: "delisted", False: "listed"})
    return out


# One insight's counts: covered, by route, listed against delisted.
def summary(flag: pd.DataFrame, stat: pd.DataFrame, last: set) -> dict:
    f = flag.merge(stat, on="permno")
    dead, alive = f[f["status"] == "delisted"], f[f["status"] == "listed"]
    out = {"universe": len(f), "covered": int(f["covered"].sum())}
    out |= {f"by_{h}": int(f[h].sum()) for h in ("ticker", "name", "brand")}
    out["ticker_and_name"] = int((f["ticker"] & f["name"]).sum())
    out["brand_only"] = int((f["brand"] & ~f["covered"]).sum())
    out |= {"listed": len(alive), "listed_covered": int(alive["covered"].sum())}
    out |= {"delisted": len(dead), "delisted_covered": int(dead["covered"].sum())}
    for group in ("failure", "merger_or_exchange"):
        part = dead[dead["group"] == group]
        out |= {
            f"delisted_{group}": len(part),
            f"delisted_{group}_covered": int(part["covered"].sum()),
        }
    out["listed_share"] = round(out["listed_covered"] / max(out["listed"], 1), 4)
    out["delisted_share"] = round(out["delisted_covered"] / max(out["delisted"], 1), 4)
    now = f[f["permno"].isin(last)]
    out |= {"last_month": len(now), "last_month_covered": int(now["covered"].sum())}
    return out


# A saved full entity list for one insight.
def entities(insight: int) -> list[dict]:
    return json.loads((FULL / f"{insight}.json").read_text(encoding="utf-8"))["entities"]


# Every insight's per-stock flags over the 2015-2020 universe.
def stock_flags(eoms=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from fiam.vfinal import data

    eoms = list(eoms if eoms is not None else pd.date_range(START, LAST, freq="ME"))
    uni = universe(eoms)
    keys = stock_keys(data.table("links", None), uni["permno"])
    stat = status(uni["permno"], data.table("exits", ["exit_date", "category", "group"]))
    found = [
        flags(keys, carc_keys(entities(i))).assign(insight=i)
        for i in INSIGHTS
        if (FULL / f"{i}.json").exists()
    ]
    return pd.concat(found), uni, stat


# The table: one row per insight, written as CSV and JSON.
def main() -> int:
    found, uni, stat = stock_flags()
    last = set(uni.loc[uni["in_last"], "permno"])
    rows = []
    for insight, flag in found.groupby("insight", sort=False):
        dataset, what = INSIGHTS[insight]
        rows.append(
            {"insight": insight, "dataset": dataset, "measures": what} | summary(flag, stat, last)
        )
    table = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "coverage.csv", index=False)
    meta = {
        "universe": "fiam.vfinal.universe.members new_long, every month end 2015-01 to 2020-12",
        "match": "CRSP dated tickers (latest holder) and compact entity_key names, 2015-2020",
        "covered": "a ticker or company-name match; brand matches counted apart",
        "status": "delisted means a CRSP or SEC exit dated 2015-2020 (exits table, dates only)",
        "entity_lists": "data/carbon_arc/access/insight_entities_full, pulled 2026-10-26",
    }
    (OUT / "coverage.json").write_text(json.dumps({"about": meta, "rows": rows}, indent=1))
    print(table[["insight", "dataset", "universe", "covered", "listed_share", "delisted_share"]])
    return 0


# Run with uv run python -m fiam.alt.coverage
if __name__ == "__main__":
    raise SystemExit(main())
