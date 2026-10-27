# The network map: hidden concentration in any book (live).

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt import coverage

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "alt" / "network"
BOOK = ROOT / "frozen" / "september_final.csv"
# The September book is formed at the August close.
BOOK_DATE = pd.Timestamp("2026-08-31")
CA0043B = ROOT / "data" / "carbon_arc" / "snapshot_1" / "CA0043B_11676.json.gz"
# CA0043B's insight, whose free entity list holds its company names.
INSIGHT = 11676
# CA0043B's link kinds kept and what each is called on the map.
EDGE_TYPES = {"vendor": "supplier", "partner": "partner"}
# Churn over a filer's last four quarters; the top third are short.
QUARTERS, SHORT_HORIZON = 4, 1 / 3
# Consecutive 13F periods at most this many days apart pair up.
PAIR_DAYS = 100
# A median holder's share ratio outside this band reads as a split.
SPLIT_BAND, SPLIT_HOLDERS = 1.4, 5
# A 13F edge needs two shared owners and the top 2% of pair overlap.
MIN_SHARED, TOP_PAIRS = 2, 0.02
# A hidden cluster has at least three names over two or more sectors.
MIN_CLUSTER, MIN_SECTORS = 3, 2
# The hidden clusters listed and charted.
TOP_CLUSTERS = 10
SECTORS = {
    "10": "Energy",
    "15": "Materials",
    "20": "Industrials",
    "25": "Consumer Discretionary",
    "30": "Consumer Staples",
    "35": "Health Care",
    "40": "Financials",
    "45": "Information Technology",
    "50": "Communication Services",
    "55": "Utilities",
    "60": "Real Estate",
}


# A positions file as permno, weight and ticker, one row per name.
def read_book(path: Path, date=None) -> tuple[pd.DataFrame, pd.Timestamp]:
    raw = pd.read_csv(path)
    # A dated book keeps its latest date on or before the date asked.
    if "date" in raw.columns:
        raw["date"] = pd.to_datetime(raw["date"])
        if date is not None:
            raw = raw[raw["date"] <= pd.Timestamp(date)]
        if raw.empty:
            raise ValueError("no positions dated on or before the date asked")
        day = raw["date"].max()
        raw = raw[raw["date"] == day]
    else:
        day = pd.Timestamp(date) if date is not None else BOOK_DATE
    # Values without weights become shares of the book's gross.
    if "weight" in raw.columns:
        w, basis = raw["weight"].astype(float), "weight"
    else:
        w, basis = raw["value"].astype(float) / raw["value"].abs().sum(), "value"
    ticker = raw["ticker"] if "ticker" in raw.columns else pd.Series(pd.NA, index=raw.index)
    book = pd.DataFrame({"permno": raw["permno"].astype("int64"), "weight": w, "ticker": ticker})
    book = book.groupby("permno", as_index=False).agg(
        weight=("weight", "sum"), ticker=("ticker", "first")
    )
    book = book.sort_values("permno").reset_index(drop=True)
    book.attrs["basis"] = basis
    return book, day


# The book's own tickers, else the last pre-seal CRSP ticker, labelled.
def fill_tickers(book: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    t = links[(links["kind"] == "ticker") & links["valid_to"].isna()]
    t = t.sort_values("valid_from").drop_duplicates("permno", keep="last")
    crsp = t.set_index("permno")["value"].astype(str)
    out = book.copy()
    own = out["ticker"].notna() & (out["ticker"].astype(str).str.strip() != "")
    out["ticker_source"] = np.where(own, "book", "crsp_pre_seal")
    out.loc[~own, "ticker"] = out.loc[~own, "permno"].map(crsp)
    out.loc[out["ticker"].isna(), "ticker_source"] = "none"
    out["ticker"] = out["ticker"].astype("string").str.strip().str.upper()
    return out


# A pre-seal ticker reaches Carbon Arc only if a company name agrees.
def name_check(book: pd.DataFrame, links: pd.DataFrame, ents: list, carc) -> tuple:
    out = book.copy()
    crsp = out["ticker_source"].eq("crsp_pre_seal").to_numpy()
    ok = coverage.name_agrees(links, out.loc[crsp, "permno"], ents)
    refused = crsp & ~out["permno"].isin(ok).to_numpy()
    out["carc_match"] = out["ticker"].notna().to_numpy() & ~refused
    hit = refused & out["ticker"].isin(set(carc)).to_numpy()
    return out, int(hit.sum())


# CA0043B links between two book names, typed, one row per pair.
def carbon_edges(rows: pd.DataFrame, book: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    tick = book[book["carc_match"]] if "carc_match" in book else book
    tick = tick.dropna(subset=["ticker"])
    owners = tick.groupby("ticker")["permno"].agg(["nunique", "first"])
    sole = owners[owners["nunique"] == 1]["first"]
    kept = rows[rows["relationship_filter"].isin(EDGE_TYPES)].copy()
    kept["a"] = kept["entity_name"].str.upper().map(sole)
    kept["b"] = kept["affiliated_entity_name"].str.upper().map(sole)
    both = kept.dropna(subset=["a", "b"])
    both = both[both["a"] != both["b"]]
    lo = np.minimum(both["a"], both["b"]).astype("int64")
    hi = np.maximum(both["a"], both["b"]).astype("int64")
    e = pd.DataFrame({"a": lo, "b": hi, "type": both["relationship_filter"].map(EDGE_TYPES)})
    e = e.drop_duplicates().reset_index(drop=True)
    log = {
        "rows": len(rows),
        "rows_by_kind": {k: int(v) for k, v in rows["relationship_filter"].value_counts().items()},
        "rows_kept_kinds": len(kept),
        "rows_between_book_names": len(both),
        "book_tickers_shared_by_two_names_left_out": int((owners["nunique"] > 1).sum()),
        "edges": len(e),
    }
    return e, log


# The live CA0043B file: undated company connections, never traded.
def read_ca0043b(path: Path = CA0043B) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    cols = ["entity_name", "relationship_filter", "affiliated_entity_name"]
    return pd.DataFrame(payload["data"])[cols]


# Each filer's 13F holdings per period, the latest version by T.
def thirteen_f(T: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    from fiam.v4 import data
    from fiam.v4.signals import best_ideas

    quarters = pd.date_range(end=T, periods=QUARTERS + 3, freq="QE")
    first = quarters[quarters <= T][-(QUARTERS + 2)]
    cols = ["filer_cik", "period", "form", "amendmenttype", "units"]
    r = data.table("sec_13f_reports", cols, where={"period": (first, T)})
    log: dict = {}
    v = best_ideas.versions(r, log)
    v = v[v["since"] <= T].sort_values(["period", "since"], kind="stable")
    v = v.drop_duplicates(["filer_cik", "period"], keep="last")
    parts = v.assign(accession=[(b, *a) for b, a in zip(v["base"], v["adds"])])
    parts = parts.explode("accession")[["filer_cik", "period", "accession"]]
    lines = data.table(
        "sec_13f",
        ["value_usd", "shares", "shares_sole"],
        where={"accession": set(parts["accession"])},
    )
    held = parts.merge(lines[["accession", "permno", "value_usd", "shares", "shares_sole"]])
    held = held.groupby(["filer_cik", "period", "permno"], as_index=False)[
        ["value_usd", "shares", "shares_sole"]
    ].sum(min_count=1)
    log |= {"reports": len(r), "filer_periods": len(v), "lines": len(lines)}
    log["periods"] = [str(p.date()) for p in sorted(v["period"].unique())]
    return held, log


# The two latest calendar quarter-ends on or before T.
def recent_quarters(T: pd.Timestamp) -> set:
    q = pd.date_range(end=T, periods=3, freq="QE")
    return set(q[q <= T][-2:])


# Each filer's period ranks, latest first, for filers still reporting.
def ranked_periods(held: pd.DataFrame, T: pd.Timestamp) -> pd.DataFrame:
    per = held[["filer_cik", "period"]].drop_duplicates().sort_values(["filer_cik", "period"])
    per["rank"] = per.groupby("filer_cik").cumcount(ascending=False)
    live = per[(per["rank"] == 0) & per["period"].isin(recent_quarters(T))]["filer_cik"]
    return per[per["filer_cik"].isin(live) & (per["rank"] <= QUARTERS)]


# GMM churn in shares at each period's own 13F price; no return read.
def churn(held: pd.DataFrame, T: pd.Timestamp) -> pd.Series:
    per = ranked_periods(held, T)
    before = per.assign(rank=per["rank"] - 1)
    pairs = per[per["rank"] < QUARTERS].merge(before, on=["filer_cik", "rank"], suffixes=("", "_b"))
    pairs = pairs[(pairs["period"] - pairs["period_b"]).dt.days <= PAIR_DAYS]
    h = held[["filer_cik", "period", "permno", "value_usd", "shares"]]
    key = ["filer_cik", "period", "period_b"]
    a = pairs[key].merge(h, on=["filer_cik", "period"])
    b = pairs[key].merge(h.rename(columns={"period": "period_b"}), on=["filer_cik", "period_b"])
    both = a.merge(b, on=[*key, "permno"], how="outer", suffixes=("_t", "_b"))
    for c in ["value_usd_t", "value_usd_b", "shares_t", "shares_b"]:
        both[c] = both[c].fillna(0.0)
    # One price per stock and period: the median holder's value per share.
    ok = (held["shares"] > 0) & (held["value_usd"] > 0)
    px = (
        (held["value_usd"] / held["shares"])[ok]
        .groupby([held["period"][ok], held["permno"][ok]])
        .median()
    )
    px = px.rename("price_t").rename_axis(["period", "permno"]).reset_index()
    # A split moves every holder's count: the median ratio undoes it.
    held2 = both[(both["shares_t"] > 0) & (both["shares_b"] > 0)]
    ratio = (held2["shares_t"] / held2["shares_b"]).groupby([held2["period"], held2["permno"]])
    split = pd.DataFrame({"r": ratio.median(), "n": ratio.size()}).reset_index()
    far = (split["r"] > SPLIT_BAND) | (split["r"] < 1 / SPLIT_BAND)
    split["s"] = np.where(far & (split["n"] >= SPLIT_HOLDERS), split["r"], 1.0)
    both = both.merge(px, on=["period", "permno"], how="left")
    both = both.merge(split[["period", "permno", "s"]], on=["period", "permno"], how="left")
    s = both["s"].fillna(1.0)
    own = (both["value_usd_t"] / both["shares_t"]).where(both["shares_t"] > 0)
    old = (both["value_usd_b"] / (s * both["shares_b"])).where(both["shares_b"] > 0)
    p = own.fillna(both["price_t"]).fillna(old)
    both["moved"] = (both["shares_t"] - s * both["shares_b"]).abs() * p
    both["mean"] = (both["value_usd_t"] + both["value_usd_b"]) / 2
    q = both.groupby(["filer_cik", "period"])[["moved", "mean"]].sum()
    return (q["moved"] / q["mean"].where(q["mean"] > 0)).groupby("filer_cik").mean().dropna()


# Short-horizon filers' latest sole-discretion value in each stock.
def short_owners(held: pd.DataFrame, rate: pd.Series, T: pd.Timestamp) -> pd.DataFrame:
    short = rate[rate >= rate.quantile(1 - SHORT_HORIZON)].index
    per = ranked_periods(held, T)
    latest = per[(per["rank"] == 0) & per["filer_cik"].isin(short)]
    own = latest[["filer_cik", "period"]].merge(held, on=["filer_cik", "period"])
    frac = (own["shares_sole"] / own["shares"]).where(own["shares"] > 0).clip(0, 1)
    own["value_sole"] = own["value_usd"] * frac.fillna(0.0)
    return own[own["value_sole"] > 0][["filer_cik", "permno", "value_sole"]]


# Anton-Polk overlap: common short owners' value over both caps.
def overlap(own: pd.DataFrame, caps: pd.Series, permnos) -> pd.DataFrame:
    ids = [p for p in permnos if p in set(own["permno"]) and pd.notna(caps.get(p))]
    o = own[own["permno"].isin(ids)]
    if len(ids) < 2 or o.empty:
        return pd.DataFrame(columns=["a", "b", "fcap", "shared"])
    W = o.pivot_table(index="filer_cik", columns="permno", values="value_sole", aggfunc="sum")
    W = W.reindex(columns=ids).fillna(0.0).to_numpy()
    H = (W > 0).astype(float)
    common = W.T @ H + H.T @ W
    shared = H.T @ H
    me = caps.reindex(ids).to_numpy() * 1e6
    fcap = common / (me[:, None] + me[None, :])
    i, j = np.triu_indices(len(ids), k=1)
    pairs = pd.DataFrame(
        {"a": np.array(ids)[i], "b": np.array(ids)[j], "fcap": fcap[i, j], "shared": shared[i, j]}
    )
    return pairs[pairs["shared"] > 0].reset_index(drop=True)


# 13F edges: two shared owners and the top share of positive overlap.
def owner_edges(pairs: pd.DataFrame) -> pd.DataFrame:
    if pairs.empty:
        return pairs.assign(type=pd.Series(dtype=str))
    cut = pairs["fcap"].quantile(1 - TOP_PAIRS)
    keep = pairs[(pairs["shared"] >= MIN_SHARED) & (pairs["fcap"] >= cut)]
    return keep.assign(type="shared_13f_owners").reset_index(drop=True)


# Each stock's CRSP cap in $m at its last month end by T, three back.
def caps_at(T: pd.Timestamp) -> pd.Series:
    from fiam.v4 import data

    m = data.table("crsp_monthly", ["cap_musd"], where={"date": (T - pd.DateOffset(months=3), T)})
    return (
        m.sort_values("date").drop_duplicates("permno", keep="last").set_index("permno")["cap_musd"]
    )


# Labels 0..k-1 in order of first appearance, so runs are stable.
def relabel(labels: np.ndarray) -> np.ndarray:
    _, first = np.unique(labels, return_index=True)
    order = np.argsort(first)
    rank = np.empty(len(order), dtype=int)
    rank[order] = np.arange(len(order))
    return rank[np.unique(labels, return_inverse=True)[1]]


# Louvain's local moves: each node joins the best community by gain.
def one_level(a: np.ndarray) -> np.ndarray:
    n = len(a)
    k = a.sum(axis=1)
    m2 = k.sum()
    comm = np.arange(n)
    if m2 == 0:
        return comm
    tot = k.copy()
    moved = True
    while moved:
        moved = False
        for i in range(n):
            ci = comm[i]
            tot[ci] -= k[i]
            w = np.bincount(comm, weights=a[i], minlength=n)
            w[ci] -= a[i, i]
            gain = w - tot * k[i] / m2
            cand = np.union1d(np.unique(comm[a[i] > 0]), [ci])
            best = int(cand[np.argmax(gain[cand])])
            if gain[best] <= gain[ci] + 1e-12:
                best = ci
            comm[i] = best
            tot[best] += k[i]
            moved |= best != ci
    return relabel(comm)


# Louvain communities on a symmetric weight matrix, fixed node order.
def louvain(adj: np.ndarray) -> np.ndarray:
    a = np.asarray(adj, dtype=float)
    labels = np.arange(len(a))
    while True:
        part = one_level(a)
        labels = part[labels]
        k = part.max() + 1 if len(part) else 0
        if k == len(a):
            return relabel(labels)
        onehot = np.zeros((len(a), k))
        onehot[np.arange(len(a)), part] = 1.0
        a = onehot.T @ a @ onehot


# Modularity of a split, the standard Newman-Girvan Q.
def modularity(adj: np.ndarray, labels: np.ndarray) -> float:
    a = np.asarray(adj, dtype=float)
    k = a.sum(axis=1)
    m2 = k.sum()
    if m2 == 0:
        return 0.0
    same = labels[:, None] == labels[None, :]
    return float(((a - np.outer(k, k) / m2) * same).sum() / m2)


# Connected components by union-find, labelled in node order.
def components(n: int, edges) -> np.ndarray:
    parent = list(range(n))

    # The root of a node, halving the path as it climbs.
    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in edges:
        ri, rj = root(int(i)), root(int(j))
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return relabel(np.array([root(i) for i in range(n)]))


# One undirected edge per pair: its types, overlap and weight.
def merge_edges(parts: list[pd.DataFrame]) -> pd.DataFrame:
    cols = ["a", "b", "type", "fcap", "shared"]
    frames = [p.reindex(columns=cols) for p in parts if len(p)]
    if not frames:
        return pd.DataFrame(columns=["a", "b", "types", "fcap", "shared", "weight"])
    e = pd.concat(frames, ignore_index=True)
    e["source"] = np.where(e["type"] == "shared_13f_owners", "13f", "carbon_arc")
    g = e.groupby(["a", "b"])
    out = pd.DataFrame(
        {
            "types": g["type"].agg(lambda s: sorted(set(s))),
            "fcap": g["fcap"].max(),
            "shared": g["shared"].max(),
            "weight": g["source"].nunique().astype(float),
        }
    ).reset_index()
    return out


# Per cluster: names, gross, net, sides, sectors and link types.
def cluster_table(nodes: pd.DataFrame, edges: pd.DataFrame, gross: float) -> pd.DataFrame:
    rows = []
    where = nodes.set_index("permno")["cluster"]
    for c, g in nodes.groupby("cluster"):
        if len(g) < 2:
            continue
        inside = edges[edges["a"].map(where).eq(c) & edges["b"].map(where).eq(c)]
        kinds = pd.Series([t for ts in inside["types"] for t in ts]).value_counts()
        known = g["sector"].dropna()
        abs_w = g["weight"].abs()
        top = abs_w.groupby(g["sector"]).sum()
        rows.append(
            {
                "cluster": int(c),
                "names": len(g),
                "longs": int((g["weight"] > 0).sum()),
                "shorts": int((g["weight"] < 0).sum()),
                "long_weight": float(g["weight"].clip(lower=0).sum()),
                "short_weight": float(g["weight"].clip(upper=0).sum()),
                "net": float(g["weight"].sum()),
                "gross": float(abs_w.sum()),
                "share_of_book_gross": float(abs_w.sum() / gross) if gross else 0.0,
                "sectors": int(known.nunique()),
                "sector_unknown": int(g["sector"].isna().sum()),
                "top_sector": None if top.empty else str(top.idxmax()),
                "top_sector_share_of_gross": (
                    None if top.empty else float(top.max() / abs_w.sum())
                ),
                "edges": len(inside),
                "edge_types": {k: int(v) for k, v in kinds.items()},
                "largest_names": g.reindex(abs_w.sort_values(ascending=False).index)["ticker"]
                .fillna("")
                .head(5)
                .tolist(),
            }
        )
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    t["hidden"] = (t["names"] >= MIN_CLUSTER) & (t["sectors"] >= MIN_SECTORS)
    t["abs_net"] = t["net"].abs()
    return t.sort_values(["abs_net", "cluster"], ascending=[False, True]).reset_index(drop=True)


# The map for one book: nodes, typed edges, clusters and exposure.
def build(
    book: pd.DataFrame,
    carbon: pd.DataFrame,
    owner: pd.DataFrame,
    sectors: pd.Series,
) -> dict:
    nodes = book.copy().reset_index(drop=True)
    nodes["side"] = np.where(
        nodes["weight"] > 0, "long", np.where(nodes["weight"] < 0, "short", "flat")
    )
    nodes["sector"] = nodes["permno"].map(sectors)
    edges = merge_edges([carbon, owner])
    index = {p: i for i, p in enumerate(nodes["permno"])}
    n = len(nodes)
    adj = np.zeros((n, n))
    for a, b, w in edges[["a", "b", "weight"]].itertuples(index=False):
        adj[index[a], index[b]] = adj[index[b], index[a]] = w
    nodes["cluster"] = louvain(adj)
    nodes["component"] = components(n, [(index[a], index[b]) for a, b in edges[["a", "b"]].values])
    nodes["degree"] = (adj > 0).sum(axis=1)
    gross = float(nodes["weight"].abs().sum())
    clusters = cluster_table(nodes, edges, gross)
    comp = nodes["component"].value_counts()
    return {
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "modularity": modularity(adj, nodes["cluster"].to_numpy()),
        "component_sizes": sorted([int(x) for x in comp[comp > 1]], reverse=True),
        "isolated": int((comp == 1).sum()),
    }


# Stale GICS sector names: the panel's last month by T (sealed 2020).
def sectors_at(T: pd.Timestamp, permnos) -> pd.Series:
    from fiam.v4 import data

    p = data.table(
        "panel", ["gics"], where={"eom": (T - pd.DateOffset(months=12), T), "permno": set(permnos)}
    )
    p = p.dropna(subset=["gics"]).sort_values("eom").drop_duplicates("permno", keep="last")
    return p.set_index("permno")["gics"].astype(str).str[:2].map(SECTORS)


# The weight axis as the book gives it: NAV weights or gross shares.
AXIS = {"weight": "Percent of NAV", "value": "Percent of book gross"}


# One chart: long and short weight per hidden cluster, net marked.
def chart(
    clusters: pd.DataFrame, title: str, note: str, path: Path, axis: str = AXIS["weight"]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = clusters[clusters["hidden"]].head(TOP_CLUSTERS).iloc[::-1]
    ink, muted, long_c, short_c = "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
    fig, ax = plt.subplots(figsize=(10, 0.55 * max(len(top), 3) + 2.2), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    y = np.arange(len(top))
    ax.barh(y, top["long_weight"] * 100, color=long_c, height=0.6, label="Long weight")
    ax.barh(y, top["short_weight"] * 100, color=short_c, height=0.6, label="Short weight")
    ax.scatter(top["net"] * 100, y, color=ink, s=40, zorder=3, label="Net weight")
    names = [
        f"{' '.join(t for t in r.largest_names[:3] if t)}  "
        f"{int(r.names)} names in {int(r.sectors)} sectors"
        for r in top.itertuples()
    ]
    ax.set_yticks(y, names, color=muted, fontsize=9)
    ax.axvline(0, color=muted, lw=0.8)
    ax.set_xlabel(axis, color=muted)
    ax.grid(axis="x", color="#e4e3df", lw=0.6)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=muted)
    ax.set_title(title, loc="left", color=ink, fontsize=12)
    ax.legend(frameon=False, loc="lower right", fontsize=9, labelcolor=muted)
    fig.text(0.01, 0.01, note, color=muted, fontsize=8)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


# Runs the map: python -m fiam.alt.network [book] [--date] [--label]
def main(argv=None) -> dict:
    from fiam.v4 import data, sources

    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", default=str(BOOK))
    ap.add_argument("--date", default=None)
    ap.add_argument("--label", default=None)
    args = ap.parse_args(argv)
    path = Path(args.book)
    book, day = read_book(path, args.date)
    basis = book.attrs.get("basis", "weight")
    is_v3 = path.resolve() == BOOK.resolve()
    label = args.label or (
        "v3 September book (frozen/september_final.csv), not the v4 book" if is_v3 else path.stem
    )
    # The seal is the end of 2020-12-31 in New York: that day is T's cap.
    seal = sources.seal_at().tz_convert("America/New_York").tz_localize(None).normalize()
    T = min(day, seal)
    stale = day > seal
    links = data.table("links", None)
    ca = read_ca0043b()
    carc = set(ca["entity_name"]) | set(ca["affiliated_entity_name"])
    book = fill_tickers(book, links)
    book, refused = name_check(book, links, coverage.entities(INSIGHT), carc)
    carbon, carbon_log = carbon_edges(ca, book)
    held, f_log = thirteen_f(T)
    rate = churn(held, T)
    own = short_owners(held, rate, T)
    caps = caps_at(T)
    pairs = overlap(own, caps, book["permno"].tolist())
    owner = owner_edges(pairs)
    res = build(book, carbon, owner, sectors_at(T, book["permno"]))
    nodes, edges, clusters = res["nodes"], res["edges"], res["clusters"]
    hidden = clusters[clusters["hidden"]] if len(clusters) else clusters
    by_type = pd.Series([t for ts in edges["types"] for t in ts]).value_counts()
    summary = {
        "piece": "3, the network map (PLAN §12.4), live use only, never traded",
        "book": label,
        "book_date": str(day.date()),
        "names": len(nodes),
        "longs": int((nodes["weight"] > 0).sum()),
        "shorts": int((nodes["weight"] < 0).sum()),
        "gross": float(nodes["weight"].abs().sum()),
        "net": float(nodes["weight"].sum()),
        "weights": "as given, share of NAV"
        if basis == "weight"
        else "values as shares of the book's gross",
        "returns_used": "none",
        "tickers_by_source": {k: int(v) for k, v in nodes["ticker_source"].value_counts().items()},
        "carbon_arc": carbon_log
        | {
            "source": "CA0043B company connections, current vintage, undated, live only",
            "kinds_as_edges": EDGE_TYPES,
            "pre_seal_ticker_matches_refused_name_mismatch": refused,
            "name_rule": "a book name's last pre-seal CRSP ticker is used only if one of its "
            "2015-2020 CRSP names equals a company name in CA0043B's entity list (compact "
            "entity_key); Carbon Arc gives no company name per ticker, and a ticker changed "
            "after 2020 is not recovered",
            "credit": "Based in part on Carbon Arc data",
        },
        "thirteen_f": f_log
        | {
            "known_by": str(T.date()),
            "stale": bool(stale),
            "stale_note": (
                f"latest 13F filings public by {T.date()} (the seal), for a {day.date()} book"
                if stale
                else "filings public by the book date"
            ),
            "filers_with_churn": len(rate),
            "short_horizon_filers": int(own["filer_cik"].nunique()),
            "book_names_with_short_owner": int(
                own.loc[own["permno"].isin(nodes["permno"]), "permno"].nunique()
            ),
            "pairs_with_shared_owner": len(pairs),
            "edges": len(owner),
            "edge_rule": f"at least {MIN_SHARED} shared owners and overlap in the top "
            f"{TOP_PAIRS:.0%} of the book's pairs",
        },
        "edges_by_type": {k: int(v) for k, v in by_type.items()},
        "edges": len(edges),
        "components_over_one_name": res["component_sizes"],
        "isolated_names": res["isolated"],
        "clusters_over_one_name": int(len(clusters)),
        "cluster_sizes": clusters["names"].tolist() if len(clusters) else [],
        "modularity": res["modularity"],
        "hidden_clusters": int(len(hidden)),
        "sectors_note": "GICS sectors from the panel's last month by the seal (stale for 2026)",
    }
    out = {
        "summary": summary,
        "top_hidden_clusters": hidden.head(TOP_CLUSTERS)
        .drop(columns=["abs_net"])
        .to_dict("records"),
        "clusters": clusters.drop(columns=["abs_net"]).to_dict("records") if len(clusters) else [],
        "nodes": nodes[
            [
                "permno",
                "ticker",
                "ticker_source",
                "carc_match",
                "weight",
                "side",
                "sector",
                "cluster",
                "component",
                "degree",
            ]
        ].to_dict("records"),  # fmt: skip
        "edges": edges.assign(a=edges["a"].astype(int), b=edges["b"].astype(int)).to_dict(
            "records"
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stem = "v3_september" if is_v3 else path.stem
    (OUT / f"network_{stem}.json").write_text(json.dumps(out, indent=1, default=str))
    title = "Hidden clusters in the v3 September book" if is_v3 else f"Hidden clusters in {label}"
    note = (
        "Links from Carbon Arc company connections (live) and shared short horizon 13F owners "
        f"(filings public by {T.date()}). No returns used. Based in part on Carbon Arc data."
    )
    if len(hidden):
        chart(clusters, title, note, OUT / f"network_{stem}.png", AXIS[basis])
    print(json.dumps(summary, indent=1, default=str))
    print(json.dumps(out["top_hidden_clusters"], indent=1, default=str))
    return out


if __name__ == "__main__":
    main()
