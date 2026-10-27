# Customer voice (Huang 2018): an exhibit, never traded.

import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.alt.coverage import entities, name_agrees

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "alt" / "customer_voice"
SNAP = ROOT / "data" / "carbon_arc" / "snapshot_1"
CA0052_RATING = SNAP / "CA0052_634_universe.json.gz"
CA0052_COUNT = SNAP / "CA0052_635_universe.json.gz"
# CA0052's rating insight, whose free entity list holds company names.
INSIGHT = 634
# CA0052 is published T + 1 Days (catalogue), so the next session.
LAG = (
    "each month's rating is usable from the first NYSE session after its month end (CA0052 "
    "is published T + 1 Days), so it enters the next month end's formation"
)
# Thresholds: 20 reviews in the month, 100 in the 12 before.
MIN_MONTH, MIN_TRAIL, TRAIL = 20, 100, 12
# A month's Spearman needs at least ten rated names with a label.
MIN_NAMES = 10
# Windows: Amazon 2016-2020, CA0052 from the labels' first formation.
WINDOWS = {
    "amazon": ("2016-01-31", "2020-12-31"),
    "ca0052": ("2015-01-31", "2020-12-31"),
}
# CA0052 months averaging under one star are zero-coded.
ZERO_CODED = 1.0
# Legal-form words dropped from the end of a company name to match.
SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "HOLDINGS",
    "HOLDING", "HLDGS", "GROUP", "GRP", "NEW", "DEL", "THE", "SA", "NV", "AG", "INTERNATIONAL",
    "INTL", "BRANDS", "ENTERPRISES", "INDUSTRIES", "INDS",
}  # fmt: skip
# Consumer-facing GICS sectors, dated by the panel's month (Huang).
CONSUMER = {"25", "30", "45", "50"}
# Whole-name matches read by hand as another firm's brand or a word.
NOT_THE_FIRM = {
    s: "a generic word or another owner's brand, read by hand 2026-10-26"
    for s in [
        "Lee", "Lee's", "SUPERIOR", "Universal", "Match", "JASON", "Dixie", "C.C", "Oxford",
        "Harbinger", "HARRIS", "Golden", "Coffee", "Switch", "Vertex", "Drew", "Thor", "Remy",
        "Sonic", "Fox", "Fox's", "Crown", "Alpha", "Alpha Group", "Alpha Industries", "Apollo",
        "Apollo International", "Graham", "FORM", "Formé", "Majesco", "Endurance", "Emerald",
        "VECTOR", "Skyline", "Snap", "Quantum", "GOGO", "GREENSKY", "Genius", "Plexus",
        "Corning", "XCEL", "Motorola", "X-O", "Fairway", "Boulder", "Solera", "Lifetime",
        "LIFETIME", "Brunswick", "SABRE", "Dana", "Centric", "Innovo", "SHILOH", "Mastech",
        "Spectrum",
    ]
}  # fmt: skip


# A name in one spelling: upper case, no punctuation, no legal form.
def stem(name: str) -> str:
    s = re.sub(r"\(.*?\)", " ", str(name).upper()).replace("&", " AND ")
    words = re.sub(r"[^A-Z0-9 ]+", " ", s).split()
    # Runs of single letters are one word: "H P" is "HP", "S A" is "SA".
    joined: list[str] = []
    run = False
    for w in words:
        if len(w) == 1 and run:
            joined[-1] += w
        else:
            joined.append(w)
        run = len(w) == 1
    words = joined
    while words and words[0] == "THE":
        words = words[1:]
    while len(words) > 1 and words[-1] in SUFFIXES:
        words = words[:-1]
    return " ".join(words)


# Dated CRSP names of panel stocks, each as a stem.
def name_table(links: pd.DataFrame, permnos) -> pd.DataFrame:
    n = links[(links["kind"] == "name") & links["permno"].isin(set(permnos))].copy()
    n["stem"] = n["value"].map(stem)
    return n[["permno", "stem", "valid_from", "valid_to"]]


# Store to PERMNO by the whole stem; "(Author)" credits are not brands.
def match_stores(stores, names: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame({"store": sorted(set(stores))})
    s = s[~s["store"].str.contains("(", regex=False) & ~s["store"].isin(NOT_THE_FIRM)]
    s["key"] = s["store"].map(stem)
    s = s[s["key"].str.len() >= 2]
    out = s.merge(names, left_on="key", right_on="stem")
    cols = ["store", "permno", "stem", "valid_from", "valid_to"]
    return out[cols].drop_duplicates().reset_index(drop=True)


# Store-months on firm-months, kept only while the name is in force.
def to_firms(sm: pd.DataFrame, matches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    m = sm.merge(matches, on="store")
    live = (m["valid_from"] <= m["eom"]) & (
        m["valid_to"].isna() | (m["valid_to"] >= m["eom"] - pd.offsets.MonthBegin(1))
    )
    m = m[live]
    # A store naming two stocks in one month (share classes) is left out.
    many = m.groupby(["store", "eom"])["permno"].transform("nunique") > 1
    m = m[~many].drop_duplicates(["store", "eom", "permno"])
    firm = m.groupby(["permno", "eom"], as_index=False)[["reviews", "rating_sum"]].sum()
    log = {
        "store_months_matched": len(m),
        "store_months_on_two_stocks_left_out": int(many.sum()),
    }
    return firm, log


# Firm-months whose dated panel GICS sector faces consumers.
def consumer_only(sig: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    sector = panel[["permno", "eom"]].assign(sector=panel["gics"].astype(str).str[:2])
    out = sig.merge(sector, on=["permno", "eom"])
    return out[out["sector"].isin(CONSUMER)].drop(columns="sector")


# The abnormal rating: the month's mean less the trailing 12 months'.
def abnormal(firm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for permno, g in firm.groupby("permno"):
        g = g.set_index("eom").sort_index()
        full = pd.date_range(g.index.min(), g.index.max(), freq="ME")
        g = g.reindex(full).fillna({"reviews": 0, "rating_sum": 0.0})
        trail_n = g["reviews"].shift(1).rolling(TRAIL, min_periods=TRAIL).sum()
        trail_s = g["rating_sum"].shift(1).rolling(TRAIL, min_periods=TRAIL).sum()
        mean = g["rating_sum"] / g["reviews"].where(g["reviews"] > 0)
        ab = mean - trail_s / trail_n.where(trail_n > 0)
        ok = (g["reviews"] >= MIN_MONTH) & (trail_n >= MIN_TRAIL)
        rows.append(
            pd.DataFrame(
                {"permno": permno, "eom": g.index, "abnormal": ab, "reviews": g["reviews"]}
            )[ok.to_numpy()]
        )
    if not rows:
        return pd.DataFrame(columns=["permno", "eom", "abnormal", "reviews"])
    return pd.concat(rows, ignore_index=True).dropna(subset=["abnormal"])


# Monthly Spearman of the abnormal rating with next month's residual.
def monthly_ic(signal: pd.DataFrame, labels: pd.DataFrame, target: str) -> pd.DataFrame:
    j = signal.merge(labels[["permno", "eom", target]], on=["permno", "eom"]).dropna(
        subset=[target]
    )
    rows = []
    for eom, g in j.groupby("eom"):
        if len(g) >= MIN_NAMES:
            rho = g["abnormal"].rank().corr(g[target].rank())
            rows.append({"eom": eom, "ic": rho, "names": len(g)})
    return pd.DataFrame(rows, columns=["eom", "ic", "names"])


# Mean IC, its t over months, and the counts behind them.
def summarise(ic: pd.DataFrame) -> dict:
    n = len(ic)
    if n < 2:
        return {"months": n, "mean_ic": None, "t": None, "note": "too few months"}
    m, sd = float(ic["ic"].mean()), float(ic["ic"].std(ddof=1))
    return {
        "months": n,
        "first": str(ic["eom"].min().date()),
        "last": str(ic["eom"].max().date()),
        "mean_ic": m,
        "sd_ic": sd,
        "t": m / (sd / np.sqrt(n)) if sd > 0 else None,
        "share_positive": float((ic["ic"] > 0).mean()),
        "median_names": float(ic["names"].median()),
    }


# Coverage of one source: mapped names, universe names, survivors.
def coverage(
    signal: pd.DataFrame, labels: pd.DataFrame, panel_last: pd.Series, linked: set
) -> dict:
    mapped = set(signal["permno"])
    ever = set(labels.loc[labels["resid_universe"].notna(), "permno"])
    lab = labels.merge(signal[["permno", "eom"]], on=["permno", "eom"])
    uni = set(lab.loc[lab["resid_universe"].notna(), "permno"])
    leavers = set(panel_last[panel_last < panel_last.max()].index)
    stayers = set(panel_last.index) - leavers
    return {
        "stocks_linked": len(linked),
        "stocks_linked_ever_in_the_trading_universe": len(linked & ever),
        "names_with_a_qualifying_month": len(mapped),
        "of_them_in_the_trading_universe_that_month": len(uni),
        "panel_names_in_window": len(panel_last),
        "mapped_share_of_panel_leavers": len(mapped & leavers) / max(len(leavers), 1),
        "mapped_share_of_panel_stayers": len(mapped & stayers) / max(len(stayers), 1),
        "leavers_mapped": len(mapped & leavers),
        "stayers_mapped": len(mapped & stayers),
    }


# Amazon store-months for 2014 on, for the stores that ever qualify.
def amazon_firms(links: pd.DataFrame, permnos) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from fiam.vfinal import data

    lo, hi = pd.Timestamp("2014-12-01"), pd.Timestamp(WINDOWS["amazon"][1])
    busy = data.table("amazon_stores", ["reviews"], purpose="exhibit",
                      where={"month": (lo, hi), "reviews": (MIN_MONTH, None)})  # fmt: skip
    matches = match_stores(busy["store"].unique(), name_table(links, permnos))
    sm = data.table(
        "amazon_stores",
        ["reviews", "rating_sum"],
        purpose="exhibit",
        where={"month": (lo - pd.DateOffset(months=TRAIL), hi), "store": set(matches["store"])},
    )
    sm["eom"] = sm["month"] + pd.offsets.MonthEnd(0)
    firm, log = to_firms(sm, matches)
    log |= {
        "stores_with_20_reviews_in_a_month": int(busy["store"].nunique()),
        "stores_matched": int(matches["store"].nunique()),
        "stocks_matched": int(matches["permno"].nunique()),
    }
    return firm, matches, log


# The first NYSE session after each day, when T+1 data is usable.
def next_session(days: pd.Series) -> pd.Series:
    from fiam.vfinal import clock

    d = pd.to_datetime(days).dt.normalize()
    s = clock.xnys_sessions(d.min(), d.max() + pd.Timedelta(days=10))
    pos = np.searchsorted(s.asi8, d.to_numpy().astype("datetime64[ns]").astype("int64"), "right")
    return pd.Series(s[pos], index=days.index)


# CA0052 ticker-months, tickers to PERMNO by the last pre-seal ticker.
def ca0052_firms(links: pd.DataFrame, ents: list | None = None) -> tuple[pd.DataFrame, dict]:
    frames = []
    for path, col in [(CA0052_RATING, "star_rating"), (CA0052_COUNT, "review_count")]:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            d = pd.DataFrame(json.load(fh)["data"])
        frames.append(d[["entity_name", "date", col]])
    ca = frames[0].merge(frames[1], on=["entity_name", "date"])
    return ca0052_map(ca, links, entities(INSIGHT) if ents is None else ents)


# Rated months on PERMNOs at the formation where each is first usable.
def ca0052_map(ca: pd.DataFrame, links: pd.DataFrame, ents: list) -> tuple[pd.DataFrame, dict]:
    ca = ca.copy()
    month = pd.to_datetime(ca["date"]) + pd.offsets.MonthEnd(0)
    ca["usable_from"] = next_session(month)
    ca["eom"] = ca["usable_from"] + pd.offsets.MonthEnd(0)
    tickers = int(ca["entity_name"].nunique())
    zero = ca["star_rating"] < ZERO_CODED
    ca = ca[~zero].copy()
    t = links[(links["kind"] == "ticker") & links["valid_to"].isna()]
    owners = t.groupby("value")["permno"].agg(["nunique", "first"])
    sole = owners[owners["nunique"] == 1]["first"]
    ca["permno"] = ca["entity_name"].str.upper().map(sole)
    ok = name_agrees(links, ca["permno"].dropna().unique(), ents)
    # A ticker whose stock's CRSP name is no Carbon Arc company is refused.
    bad = ca["permno"].notna() & ~ca["permno"].isin(ok)
    refused = int(ca.loc[bad, "entity_name"].nunique())
    ca.loc[bad, "permno"] = np.nan
    firm = ca.dropna(subset=["permno"]).assign(permno=lambda f: f["permno"].astype("int64"))
    firm = firm.assign(
        reviews=firm["review_count"], rating_sum=firm["star_rating"] * firm["review_count"]
    )
    log = {
        "tickers": tickers,
        "zero_coded_months_left_out": int(zero.sum()),
        "ticker_matches_refused_name_mismatch": refused,
        "tickers_mapped_to_one_permno": int(firm["entity_name"].nunique()),
        "months_before_2021": int((month[~zero] <= pd.Timestamp("2020-12-31")).sum()),
        "lag": LAG,
    }
    return firm[["permno", "eom", "reviews", "rating_sum"]], log


# One chart: each source's mean monthly IC with a 95% interval.
def chart(results: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, c = "#0b0b0b", "#52514e", "#2a78d6"
    rows = [(k, v) for k, v in results.items() if v.get("mean_ic") is not None]
    fig, ax = plt.subplots(figsize=(10, 0.7 * max(len(rows), 2) + 1.8), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for i, (name, r) in enumerate(rows[::-1]):
        half = 1.96 * r["sd_ic"] / np.sqrt(r["months"])
        ax.plot([r["mean_ic"] - half, r["mean_ic"] + half], [i, i], color=c, lw=2)
        ax.scatter([r["mean_ic"]], [i], color=c, s=60, zorder=3)
        t = "n/a" if r["t"] is None else f"{r['t']:.2f}"
        text = f"t {t}, {r['months']} months, median {r['median_names']:.0f} names"
        ax.text(r["mean_ic"] + half + 0.005, i, text, va="center", color=muted, fontsize=9)
    years = [f"{n} {r['first'][:4]} to {r['last'][:4]}" for n, r in rows[::-1]]
    ax.set_yticks(range(len(rows)), years, color=muted, fontsize=9)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.axvline(0, color=muted, lw=0.8)
    ax.set_xlabel("Mean monthly rank correlation with next month residual return", color=muted)
    ax.grid(axis="x", color="#e4e3df", lw=0.6)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=muted)
    ax.set_title("Customer voice before 2021, an exhibit never traded", loc="left",
                 color=ink, fontsize=12)  # fmt: skip
    fig.text(0.01, 0.01, "Bars are 95 percent intervals. Amazon Reviews 2023 (Hou et al. 2024) "
             "and CA0052. Based in part on Carbon Arc data.", color=muted, fontsize=8)  # fmt: skip
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


# Runs the exhibit on pre-2021 data: python -m fiam.alt.customer_voice
def main() -> dict:
    from fiam.vfinal import data

    links = data.table("links", None)
    labels = data.table("labels", ["resid_panel", "resid_universe"], purpose="label",
                        where={"horizon": {1}})  # fmt: skip
    panel = data.table("panel", ["gics"], where={"eom": ("2015-01-31", "2020-12-31")})
    sources_out, ics = {}, {}
    amazon, matches, a_log = amazon_firms(links, panel["permno"].unique())
    ca, c_log = ca0052_firms(links)
    for name, firm, log in [("amazon", amazon, a_log), ("ca0052", ca, c_log)]:
        lo, hi = (pd.Timestamp(x) for x in WINDOWS[name])
        sig = abnormal(firm)
        sig = sig[sig["eom"].between(lo, hi)]
        # Amazon names count only in months their sector sells to shoppers.
        if name == "amazon":
            sig = consumer_only(sig, panel)
        p = panel[panel["eom"].between(lo, hi)]
        last = p.groupby("permno")["eom"].max()
        linked = set(firm["permno"])
        if name == "amazon":
            linked &= set(panel.loc[panel["gics"].astype(str).str[:2].isin(CONSUMER), "permno"])
        res = {"build": log, "coverage": coverage(sig, labels, last, linked)}
        for target in ["resid_panel", "resid_universe"]:
            ic = monthly_ic(sig, labels, target)
            ics[(name, target)] = ic
            res[target] = summarise(ic)
        sources_out[name] = res
    out = {
        "piece": "4, customer voice (PLAN §7.6, §12.4), an exhibit, never traded",
        "vintage": "current vintage, descriptive only (PDF p16); labels sealed at 2020-12-31",
        "rule": f"abnormal rating = month mean less the prior {TRAIL} months' mean, at least "
        f"{MIN_MONTH} reviews in the month and {MIN_TRAIL} in the {TRAIL} before; monthly "
        f"Spearman with the next month's residual return, months with {MIN_NAMES}+ names",
        "store_map": "Amazon stores to dated CRSP names of panel stocks by the whole name less "
        "its legal form, only while the name is in force, in consumer GICS sectors (25, 30, 45, "
        f"50), {len(NOT_THE_FIRM)} stores read by hand as generic words or other owners' brands "
        "left out; the Carbon Arc brand ontology is not held offline. CA0052 tickers to the "
        "last CRSP ticker in force at the seal, kept only when a 2015-2020 CRSP name of that "
        "stock equals a company name in CA0052's entity list (compact entity_key)",
        "ca0052_lag": LAG,
        "sources": sources_out,
        "matched_stores": matches.groupby("permno")["store"].apply(sorted).to_dict(),
        "credit": "Based in part on Carbon Arc data; Amazon Reviews 2023 (Hou et al. 2024)",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "customer_voice.json").write_text(json.dumps(out, indent=1, default=str))
    names = {
        "amazon": "Amazon ratings",
        "ca0052": "Software ratings CA0052",
    }
    chart({names[k]: v["resid_panel"] for k, v in sources_out.items()},
          OUT / "customer_voice.png")  # fmt: skip
    print(json.dumps({k: v for k, v in out.items() if k != "matched_stores"}, indent=1,
                     default=str))  # fmt: skip
    return out


if __name__ == "__main__":
    main()
