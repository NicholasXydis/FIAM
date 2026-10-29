# The 61st Investor: the AI crowd and Carbon Arc call revenue growth.

import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
# Outputs live outside the repo; FIAM_SF moves them.
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-nicholas-Code-Forkfiam/"
    "ec81f6cc-ab00-43dd-9116-2a36d1c36dac/scratchpad/sixty_first"
)
SF = Path(os.environ.get("FIAM_SF", str(SCRATCH)))
# The book the contest is sealed on, copied from final/holdings.csv.
HOLDINGS = ROOT / "out" / "sixty_first" / "holdings_at_seal.csv"
CALENDAR = ROOT / "data" / "v4" / "clean" / "earnings_calendar.parquet"
ENTITIES = ROOT / "data" / "carbon_arc" / "access" / "insight_entities_full"
# The prepared Carbon Arc kit, reused for reading saved MCP answers.
CA_KIT = Path(os.environ.get("FIAM_CA_KIT", str(SCRATCH.parent / "carbon_arc")))
# The day the lists are built; nothing filed on or after it is read.
AS_OF = pd.Timestamp(os.environ.get("FIAM_SF_AS_OF", "2026-10-28"))
EVENT = (pd.Timestamp("2026-10-28"), pd.Timestamp("2026-10-30"))
TWO_WEEKS = (pd.Timestamp("2026-10-28"), pd.Timestamp("2026-11-14"))
# The panel month whose sector codes label the book.
SECTOR_MONTH = pd.Timestamp("2026-08-31")
# Saved free entity lists by series; app users has none saved.
COVER = {"card_spend": 626, "web_traffic": 379, "foot_traffic": 45862}
APP_INSIGHT = 258
# GICS sectors by their two-digit code.
GICS = {
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
# Energy and commodity sectors, where card spend does not drive sales.
EXCLUDED_GICS = {"10", "15"}
EXCLUDED_SIC = {"10", "11", "12", "13", "14", "29"}
# Total revenue first, then the net sales tags.
REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
# A quarter is 80 to 125 days, a year 350 to 380, nine months 250-290.
QUARTER, YEAR, NINE = (80, 125), (350, 380), (250, 290)
UP, DOWN, ABSTAIN = "speeds up", "slows down", "abstain"
# Names per crowd call and the seed behind every draw.
BATCH, SEED = 8, 42
ROUNDS = {"event": 1, "extra": 2}
# The Carbon Arc rule: two points either way, card spend first.
BAND = 0.02
ORDER = ("card_spend", "web_traffic", "app_users")
# Release tables match the filed year-ago revenue within this bound.
TIGHT = 0.005
# A vote sealed after the name's report, which never counts.
LATE = "sealed after the report"
CREDIT = "Based in part on Carbon Arc data"
NOT_TRADED = "Today's Carbon Arc data, not used in any trade"

RULES = f"""# The 61st Investor, rules written before any vote or data

Question. For each holding of the final book (final/holdings.csv, last date) that
reports earnings in the window, does this quarter's revenue growth, year on year,
speed up or slow down against last quarter's?

Names. Projected report dates from earnings_calendar.parquet with known_from on or
before {AS_OF.date()}. Event list {EVENT[0].date()} to {EVENT[1].date()}. Day-2 list
{TWO_WEEKS[0].date()} to {TWO_WEEKS[1].date()}. Energy and commodity names are
excluded by sector (GICS {sorted(EXCLUDED_GICS)}, or SIC two-digit
{sorted(EXCLUDED_SIC)} without GICS), since consumer spend does not drive their
revenue. A name needs its last two quarters of revenue growth in SEC XBRL company
facts filed before {AS_OF.date()}; otherwise it is out with that reason. A name
whose quarter due in the window already sits in XBRL before {AS_OF.date()} has
reported and is out.

Last quarter's growth. SEC XBRL company facts, the first tag with the latest quarter
in this order {", ".join(REVENUE_TAGS)}. Growth is the quarter against the same
quarter a year before, from the same filing when it carries both, else first filed.
A fourth quarter not filed alone is the year less nine months.

The AI crowd. The 60 AI Crowd Lab investors (30 retail personas, 30 copycat funds)
on the PC's Gemma at temperature 0, seed {SEED}. Each sees name, sector and the last
two quarters of revenue growth only. No price, return, consensus or Carbon Arc data.
{BATCH} names a call in a seeded order per investor. The crowd's vote is the majority;
a tie abstains. Views are the AI Crowd Lab's effective voters n / (1 + (n - 1) rho).

The 61st investor. Carbon Arc MCP real-customer data (card spend, then web traffic,
then app users), pulled by hand in the morning. For the quarter being reported and
the quarter before, growth is the sum of its months against the same months a year
before, using months present in both years, at least 2 of 3. Up {BAND * 100:.0f} points or
more votes "{UP}", down {BAND * 100:.0f} points or more "{DOWN}", otherwise "{ABSTAIN}". The first
series with both quarters decides. Carbon Arc is never used in a trade.

Seal. SHA-256 of these rules, the name lists, the crowd votes, the Carbon Arc votes
and the code, with the UTC time, before any result. A name whose 8-K item 2.02 for
the quarter is accepted by SEC before the seal is dropped.

Truth. Revenue from the company's own 8-K item 2.02 exhibit 99.1, matched to the
year-ago quarter in XBRL within {TIGHT * 100:.1f}%, or the 10-Q in XBRL once it lands,
which then replaces the release reading. Speeds up when this quarter's growth is
above last quarter's. The I/B/E/S consensus is never read.

Score. The crowd, Carbon Arc and a coin seeded by the seal hash. Abstains are
shown, never dropped.
"""


# The book on its last date, with side and weight.
def book(path: Path = HOLDINGS) -> pd.DataFrame:
    raw = pd.read_csv(path)
    last = raw[raw["date"] == raw["date"].max()].copy()
    last["side"] = np.where(last["weight"] > 0, "long", "short")
    return last.reset_index(drop=True)


# Each holding's first projected report date inside the window.
def reports(permnos, first, last, as_of=AS_OF, path: Path = CALENDAR) -> pd.DataFrame:
    cal = pd.read_parquet(path)
    cal = cal[cal["permno"].isin(set(permnos)) & (cal["known_from"] <= as_of)]
    cal = cal[(cal["projected"] >= first) & (cal["projected"] <= last)]
    cal = cal.sort_values(["permno", "projected"]).drop_duplicates("permno")
    return cal[["permno", "projected", "basis", "fyearq", "fqtr"]].reset_index(drop=True)


# A sector code's name: GICS, else the SIC two-digit group.
def sector_name(code: str) -> str:
    if code.startswith("G"):
        return GICS.get(code[1:], "Other")
    return f"SIC group {code[1:]}" if code.startswith("S") else "Unknown"


# Whether a sector code is energy or commodities.
def commodity(code: str) -> bool:
    if code.startswith("G"):
        return code[1:] in EXCLUDED_GICS
    return code.startswith("S") and code[1:] in EXCLUDED_SIC


# Tickers one saved free entity list names.
def entity_tickers(insight: int, folder: Path = ENTITIES) -> set:
    path = folder / f"{insight}.json"
    if not path.exists():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8"))["entities"]
    return {r["carc_name"] for r in rows if r.get("entity_representation_name") == "ticker"}


# Quarter rows of one tag: filed three-month facts, then derived Q4.
def tag_quarters(facts: pd.DataFrame, tag: str) -> pd.DataFrame:
    f = facts[facts["tag"] == tag].copy()
    f["start"], f["end"] = pd.to_datetime(f["start"]), pd.to_datetime(f["end"])
    f["filed"] = pd.to_datetime(f["filed"])
    f["days"] = (f["end"] - f["start"]).dt.days
    three = f[f["days"].between(*QUARTER)]
    first = three.sort_values("filed").drop_duplicates("end").assign(basis="quarter")
    years = f[f["days"].between(*YEAR)].sort_values("filed").drop_duplicates(["start", "end"])
    nines = f[f["days"].between(*NINE)].sort_values("filed").drop_duplicates(["start", "end"])
    both = years.merge(nines, on="start", suffixes=("", "_nine"))
    q4 = pd.DataFrame(
        {
            "end": both["end"],
            "val": both["val"] - both["val_nine"],
            "accn": both["accn"],
            "filed": both[["filed", "filed_nine"]].max(axis=1),
            "basis": "year_less_nine",
        }
    )
    # A derived quarter fills only a quarter with no filed one.
    q4 = q4[~q4["end"].isin(first["end"])]
    out = pd.concat([first[["end", "val", "accn", "filed", "basis"]], q4], ignore_index=True)
    out = out[out["val"] > 0].sort_values(["end", "filed"]).drop_duplicates("end")
    # The same filing's year-ago figure, the comparative it printed.
    ago = []
    for _, row in out.iterrows():
        same = three[
            (three["accn"] == row["accn"])
            & ((three["end"] - (row["end"] - pd.DateOffset(years=1))).abs().dt.days <= 15)
        ]
        ago.append(float(same["val"].iloc[0]) if len(same) else np.nan)
    out["ago_same"] = ago
    return out.reset_index(drop=True).assign(tag=tag)


# Growth on a year before: the same filing first, else first filed.
def growth(quarters: pd.DataFrame) -> pd.DataFrame:
    out = quarters.copy()
    ago = []
    for _, row in out.iterrows():
        near = (out["end"] - (row["end"] - pd.DateOffset(years=1))).abs().dt.days <= 15
        first = float(out.loc[near, "val"].iloc[0]) if near.any() else np.nan
        ago.append(row["ago_same"] if row["ago_same"] > 0 else first)
    out["ago"] = ago
    with np.errstate(divide="ignore", invalid="ignore"):
        out["growth"] = np.where(out["ago"] > 0, out["val"] / out["ago"] - 1, np.nan)
    return out


# Every revenue tag's quarters for one company, filed before a day.
def all_quarters(facts: pd.DataFrame, before=None) -> dict:
    facts = facts[facts["tag"].isin(REVENUE_TAGS)]
    if before is not None:
        facts = facts[pd.to_datetime(facts["filed"]) < pd.Timestamp(before)]
    series = {t: tag_quarters(facts, t) for t in REVENUE_TAGS if (facts["tag"] == t).any()}
    return {t: s for t, s in series.items() if len(s)}


# One company's revenue quarters on the first tag holding the latest.
def revenue(facts: pd.DataFrame, before=None) -> pd.DataFrame:
    series = all_quarters(facts, before)
    if not series:
        return pd.DataFrame(columns=["end", "val", "growth", "tag"])
    latest = max(s["end"].max() for s in series.values())
    tag = next(t for t in REVENUE_TAGS if t in series and series[t]["end"].max() == latest)
    return growth(series[tag])


# A quarter's revenue on any tag, the chosen tag first.
def any_tag(series: dict, end, first: str | None = None) -> float:
    for tag in sorted(series, key=lambda t: t != first):
        q = series[tag]
        near = (q["end"] - pd.Timestamp(end)).abs().dt.days <= 15
        if near.any():
            return float(q.loc[near, "val"].iloc[0])
    return np.nan


# The quarter after a quarter end: month ends stay month ends.
def next_end(end: pd.Timestamp) -> pd.Timestamp:
    if end == end + pd.offsets.MonthEnd(0):
        return end + pd.offsets.MonthEnd(3)
    return end + pd.Timedelta(days=91)


# Last two quarters' growth and the quarter about to be reported.
def history(quarters: pd.DataFrame, as_of=AS_OF) -> dict:
    known = quarters.dropna(subset=["growth"])
    if len(known) < 2:
        return {"reason": "fewer than two quarters of revenue growth in XBRL"}
    last, prev = known.iloc[-1], known.iloc[-2]
    if (as_of - last["end"]).days > 200:
        return {"reason": "latest quarter missing from XBRL company facts"}
    target = next_end(last["end"])
    near = (quarters["end"] - (target - pd.DateOffset(years=1))).abs().dt.days <= 15
    return {
        "tag": last["tag"],
        "prev_end": prev["end"].date().isoformat(),
        "growth_prev": round(float(prev["growth"]), 6),
        "last_end": last["end"].date().isoformat(),
        "growth_last": round(float(last["growth"]), 6),
        "last_revenue": float(last["val"]),
        "target_end": target.date().isoformat(),
        "target_ago": float(quarters.loc[near, "val"].iloc[0]) if near.any() else np.nan,
        "reason": "",
    }


# Each stock's CIK: the local PERMNO map, else SEC's ticker list.
def ciks(frame: pd.DataFrame) -> pd.Series:
    path = ROOT / "data" / "edgar" / "cik_map.parquet"
    known = pd.read_parquet(path, columns=["permno", "cik"]).dropna().drop_duplicates("permno")
    out = frame["permno"].map(known.set_index("permno")["cik"])
    if out.isna().any():
        listed = sec_json("https://www.sec.gov/files/company_tickers.json")
        by_ticker = {v["ticker"]: v["cik_str"] for v in listed.values()}
        out = out.fillna(frame["ticker"].map(by_ticker))
    return out.astype("Int64")


# Revenue facts filed before the build day, saved so the inputs replay.
def revenue_facts(cik_list, before=AS_OF) -> pd.DataFrame:
    frames = [live_facts(int(c)).assign(cik=int(c)) for c in sorted(set(cik_list))]
    out = pd.concat(frames, ignore_index=True)
    out = out[pd.to_datetime(out["filed"]) < pd.Timestamp(before)]
    out.to_csv(SF / "facts_revenue.csv", index=False)
    return out


# CIKs of every holding reporting in the day-2 window.
def held_ciks() -> list[int]:
    held = book()
    when = held.merge(reports(held["permno"], *TWO_WEEKS), on="permno")
    return [int(c) for c in ciks(when).dropna()]


# Every candidate name: window, sector, coverage and revenue history.
def candidates(first, last) -> pd.DataFrame:
    from fiam.book import display_name
    from fiam.vfinal import inputs

    held = book()
    when = reports(held["permno"], first, last)
    out = held.merge(when, on="permno")
    codes = inputs.sector(out["permno"], SECTOR_MONTH)
    out["sector_code"] = out["permno"].map(codes).astype(str)
    out["sector"] = out["sector_code"].map(sector_name)
    out["name"] = out["company_name"].map(display_name).str.title()
    for metric, insight in COVER.items():
        out[metric] = out["ticker"].isin(entity_tickers(insight))
    # No app users list is saved; free discovery fills it.
    out["app_users"] = "unknown"
    out["cik"] = ciks(out)
    path = SF / "facts_revenue.csv"
    facts = pd.read_csv(path) if path.exists() else revenue_facts(held_ciks())
    rows = []
    for cik in out["cik"]:
        mine = facts[facts["cik"] == cik] if not pd.isna(cik) else facts.iloc[:0]
        if not len(mine):
            rows.append({"reason": "no XBRL revenue"})
            continue
        found = history(revenue(mine, AS_OF))
        # A year-ago figure missing on the chosen tag comes from another.
        if found["reason"] == "" and pd.isna(found["target_ago"]):
            ago = pd.Timestamp(found["target_end"]) - pd.DateOffset(years=1)
            found["target_ago"] = any_tag(all_quarters(mine, AS_OF), ago, found["tag"])
        rows.append(found)
    out = pd.concat([out.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    # A quarter ending after its projected report date is already out.
    late = pd.to_datetime(out["target_end"]) >= pd.to_datetime(out["projected"])
    out.loc[late & out["reason"].eq(""), "reason"] = "reported this quarter before the build"
    out["excluded"] = out["sector_code"].map(commodity)
    out.loc[out["excluded"], "reason"] = "energy or commodity sector"
    out["reason"] = out["reason"].fillna("")
    # An earnings 8-K already at SEC means the quarter is out too.
    open_ = out[out["reason"] == ""]
    gone = reported_before(open_, pd.Timestamp.now(tz="UTC"))
    out.loc[out["ticker"].isin(gone["ticker"]), "reason"] = "earnings 8-K at SEC before the build"
    out["in_contest"] = out["reason"] == ""
    keep = [
        "ticker", "permno", "cik", "name", "sector", "sector_code", "side", "weight",
        "projected", "basis", "fyearq", "fqtr", "card_spend", "web_traffic",
        "foot_traffic", "app_users", "tag", "prev_end", "growth_prev", "last_end",
        "growth_last", "last_revenue", "target_end", "target_ago", "excluded",
        "reason", "in_contest",
    ]  # fmt: skip
    out["projected"] = out["projected"].dt.date
    return out[keep].sort_values(["projected", "ticker"]).reset_index(drop=True)


# Writes the event and day-2 lists with their counts.
def names() -> dict:
    SF.mkdir(parents=True, exist_ok=True)
    (SF / "RULES.md").write_text(RULES, encoding="utf-8")
    summary = {}
    for label, (first, last) in (("event", EVENT), ("twoweeks", TWO_WEEKS)):
        frame = candidates(first, last)
        frame.to_csv(SF / f"names_{label}.csv", index=False)
        summary[label] = counts(frame)
    (SF / "names_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return summary


# Name counts by side, contest and Carbon Arc series.
def counts(frame: pd.DataFrame) -> dict:
    live = frame[frame["in_contest"]]
    out = {"names": len(frame), "in_contest": len(live)}
    out["by_side"] = live["side"].value_counts().to_dict()
    out["out_by_reason"] = frame.loc[~frame["in_contest"], "reason"].value_counts().to_dict()
    for metric in COVER:
        out[metric] = int(live[metric].sum())
    out["card_or_web"] = int((live["card_spend"] | live["web_traffic"]).sum())
    out["by_date"] = {
        str(k): int(v) for k, v in live["projected"].value_counts().sort_index().items()
    }
    return out


# The persona texts from the AI Crowd Lab prompt file.
def personas() -> dict:
    from fiam.agents import crowd_lab as L

    text = L.PROMPT.read_text(encoding="utf-8")
    _, *sections = text.split("\n## ")
    return {s.split("\n", 1)[0].strip(): " ".join(s.split("\n", 1)[1].split()) for s in sections}


QUESTION = (
    "For each company below you see its ticker, name and sector and how fast its revenue grew "
    "in its last two reported quarters, each against the same quarter a year before. The "
    "company reports its next quarter in the coming days. For each company, say whether that "
    f'quarter\'s revenue growth, year on year, will "{UP}" or "{DOWN}" compared with the last '
    "quarter shown. Answer for every ticker."
)


# The 60 AI Crowd Lab investors, each with its question-mode prompt.
def agents() -> list[dict]:
    from fiam import mandate as M
    from fiam.agents import crowd_lab as L

    found, out = personas(), []
    # The 30 retail investors: 6 personas by 5 information sets.
    for agent in range(len(L.PERSONAS) * L.N_SETS):
        persona = L.PERSONAS[agent // L.N_SETS]
        system = (
            f"You are an AI assistant who answers for one retail investor. {found[persona]}"
            f"\n\n{QUESTION}"
        )
        tags = {"kind": "retail", "persona": persona, "info_set": agent % L.N_SETS}
        out.append({"id": agent, "seed": agent, "system": system} | tags)
    # The 30 copycat funds: 10 per strategy text, seeds 100 to 129.
    for t, name in enumerate(("v1", "brief_2026", "case_2025")):
        strategy = M.load(M.TEMPLATES / f"{name}.json").strategy_text
        system = (
            "You are an AI agent that runs a small quant fund for one investor. The investor "
            f'described the strategy in plain English:\n\n"{strategy}"\n\n{QUESTION}'
        )
        for j in range(10):
            seed = 100 + 10 * t + j
            tags = {"kind": "copycat", "strategy": name}
            out.append({"id": 30 + 10 * t + j, "seed": seed, "system": system} | tags)
    return out


# A growth rate as signed percent text.
def pct(x, digits: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{100 * float(x):+.{digits}f}%"


# One call's companies as rows of plain text.
def question(rows: pd.DataFrame) -> str:
    lines = ["ticker | company | sector | growth, earlier quarter | growth, last quarter"]
    for r in rows.itertuples():
        lines.append(
            f"{r.ticker} | {r.name} | {r.sector} | quarter ended {r.prev_end} "
            f"{pct(r.growth_prev)} | quarter ended {r.last_end} {pct(r.growth_last)}"
        )
    return "\n".join(lines)


# The JSON every answer takes: one of the two words per ticker.
def answer_schema(tickers: list[str]) -> dict:
    word = {"type": "string", "enum": [UP, DOWN]}
    props = {t: word for t in tickers}
    return {"type": "object", "properties": props, "required": list(tickers)}


# One investor's calls this round: its own seeded order, in batches.
def batches(agent: dict, frame: pd.DataFrame, round_: str) -> list[pd.DataFrame]:
    frame = frame.sort_values("ticker").reset_index(drop=True)
    rng = np.random.default_rng([SEED, agent["seed"], ROUNDS[round_]])
    order = frame.iloc[rng.permutation(len(frame))]
    return [order.iloc[i : i + BATCH] for i in range(0, len(order), BATCH)]


# One investor's answer to one batch, as the row the log keeps.
def ask(server, agent: dict, rows: pd.DataFrame, round_: str, number: int) -> dict:
    from fiam.agents import harness as H

    text, tickers = question(rows), rows["ticker"].tolist()
    messages = [{"role": "system", "content": agent["system"]}, {"role": "user", "content": text}]
    reply = server.chat(messages, schema=answer_schema(tickers))
    answer = H.parse(reply)
    votes = {t: answer.get(t) if answer.get(t) in (UP, DOWN) else None for t in tickers}
    row = {"agent": agent["id"], "kind": agent["kind"], "round": round_, "batch": number}
    row |= {k: agent[k] for k in ("persona", "info_set", "strategy") if k in agent}
    row |= {"tickers": tickers, "votes": votes, "raw": reply.get("content")}
    row["prompt_sha256"] = hashlib.sha256((agent["system"] + text).encode()).hexdigest()
    return row


# Saved log rows, one JSON object a line.
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# The names a round asks about: event list, or the day-2 extras.
def round_names(round_: str) -> pd.DataFrame:
    event = pd.read_csv(SF / "names_event.csv")
    event = event[event["in_contest"]]
    if round_ == "event":
        return event
    two = pd.read_csv(SF / "names_twoweeks.csv")
    two = two[two["in_contest"]]
    return two[~two["ticker"].isin(event["ticker"])]


# The model, server and prompt hashes behind a round, for replay.
def manifest(server, round_: str) -> None:
    from fiam.agents import harness as H

    props = server.props() or {}
    out = {
        "round": round_,
        "model": server.name,
        "model_file": H.MODELS[server.name][1],
        "model_sha256": H.MODELS[server.name][2],
        "served_file": props.get("model_path"),
        "build": props.get("build"),
        "context": props.get("context"),
        "temperature": H.TEMPERATURE,
        "seed": H.SEED,
        "server_args": list(server.extra),
        "server": "remote" if H.REMOTE else "local",
        "question_sha256": hashlib.sha256(QUESTION.encode()).hexdigest(),
        "written_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (SF / "votes" / f"{round_}.manifest.json").write_text(json.dumps(out, indent=1))


# Every investor through every batch of a round, resuming a stop.
def vote(round_: str) -> int:
    from fiam.agents import harness as H

    frame = round_names(round_)
    (SF / "votes").mkdir(parents=True, exist_ok=True)
    log = SF / "votes" / f"{round_}.jsonl"
    done = {(r["agent"], r["batch"]) for r in read_jsonl(log)}
    crowd, asked = agents(), 0
    with H.Server("gemma", H.LONG_PROMPTS) as server, log.open("a", encoding="utf-8") as fh:
        manifest(server, round_)
        for agent in crowd:
            for number, rows in enumerate(batches(agent, frame, round_)):
                if (agent["id"], number) in done:
                    continue
                row = ask(server, agent, rows, round_, number)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                asked += 1
                if asked % 25 == 0:
                    print(f"  {round_}: {asked} calls this run", flush=True)
    print(f"{round_}: {len(frame)} names, {asked} new calls, log {log}")
    return 0


# Each investor's vote per ticker, from the round logs.
def ballots(rounds=("event", "extra")) -> pd.DataFrame:
    rows = []
    for round_ in rounds:
        for r in read_jsonl(SF / "votes" / f"{round_}.jsonl"):
            for t, v in r["votes"].items():
                rows.append((r["agent"], r["kind"], round_, t, v))
    return pd.DataFrame(rows, columns=["agent", "kind", "round", "ticker", "vote"])


# The majority per ticker with its counts; a tie abstains.
def tally(votes: pd.DataFrame) -> pd.DataFrame:
    g = votes.groupby("ticker")["vote"]
    out = pd.DataFrame(
        {
            "up": g.apply(lambda s: int((s == UP).sum())),
            "down": g.apply(lambda s: int((s == DOWN).sum())),
            "missing": g.apply(lambda s: int(s.isna().sum())),
        }
    )
    for kind in ("retail", "copycat"):
        part = votes[votes["kind"] == kind].groupby("ticker")["vote"]
        out[f"{kind}_up"] = part.apply(lambda s: int((s == UP).sum()))
        out[f"{kind}_down"] = part.apply(lambda s: int((s == DOWN).sum()))
    out["crowd"] = np.select(
        [out["up"] > out["down"], out["down"] > out["up"]], [UP, DOWN], ABSTAIN
    )
    out["share_up"] = (out["up"] / (out["up"] + out["down"]).replace(0, np.nan)).round(4)
    return out.reset_index()


# Effective independent views, the AI Crowd Lab's effective voters.
def views(votes: pd.DataFrame, least: int = 10) -> dict:
    wide = votes.assign(x=(votes["vote"] == UP).astype(float).where(votes["vote"].notna()))
    wide = wide.pivot_table(index="ticker", columns="agent", values="x", aggfunc="max")
    varied = wide.loc[:, wide.std() > 0]
    corr = varied.corr(min_periods=least)
    n = corr.shape[0]
    rho = float(np.nanmean(corr.where(~np.eye(n, dtype=bool)).to_numpy())) if n > 1 else np.nan
    eig = np.linalg.eigvalsh(np.nan_to_num(corr.to_numpy(), nan=0.0)) if n else np.array([1.0])
    patterns = wide.fillna(-1).T.drop_duplicates()
    out = {
        "agents": int(wide.shape[1]),
        "names": int(wide.shape[0]),
        "agents_with_one_answer_for_all": int(wide.shape[1] - n),
        "mean_correlation": round(rho, 4) if not np.isnan(rho) else None,
        "effective_voters": None,
        "first_eigen_share": round(float(eig.max() / max(eig.sum(), 1e-12)), 4),
        "participation_ratio": round(float(eig.sum() ** 2 / max((eig**2).sum(), 1e-12)), 2),
        "distinct_vote_patterns": int(len(patterns)),
    }
    if not np.isnan(rho):
        eff = n / (1 + (n - 1) * rho) if rho > -1 / max(n - 1, 1) else float(n)
        out["effective_voters"] = round(float(eff), 2)
    return out


# The crowd's majority and views for both lists, written as tables.
def crowd() -> dict:
    out = {}
    for label, rounds in (("event", ("event",)), ("twoweeks", ("event", "extra"))):
        frame = pd.read_csv(SF / f"names_{label}.csv")
        live = frame.loc[frame["in_contest"], "ticker"]
        votes = ballots(rounds)
        votes = votes[votes["ticker"].isin(set(live))]
        if votes.empty:
            continue
        table = tally(votes)
        table.to_csv(SF / f"crowd_{label}.csv", index=False)
        # How often the crowd just extends the last two quarters' trend.
        shown = frame.set_index("ticker").loc[table["ticker"]]
        trend = np.where(shown["growth_last"] > shown["growth_prev"], UP, DOWN)
        same_as_trend = int((table["crowd"].to_numpy() == trend).sum())
        out[label] = views(votes) | {
            "names_voted": int(table["ticker"].nunique()),
            "names_in_list": int(len(live)),
            "ballots": int(len(votes)),
            "missing_ballots": int(votes["vote"].isna().sum()),
            "crowd_says": table["crowd"].value_counts().to_dict(),
            "same_as_trend_of_last_two_quarters": same_as_trend,
            "unanimous_names": int(((table["up"] == 60) | (table["down"] == 60)).sum()),
        }
        for kind in ("retail", "copycat"):
            out[label][kind] = views(votes[votes["kind"] == kind])
    (SF / "crowd_views.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


# Replay: a seeded share of saved calls asked again live, compared.
def replay(round_: str = "event", share: float = 0.02, least: int = 6) -> dict:
    from fiam.agents import harness as H

    saved = read_jsonl(SF / "votes" / f"{round_}.jsonl")
    rng = np.random.default_rng(SEED + 7)
    size = min(len(saved), max(least, int(share * len(saved))))
    chosen = sorted(rng.choice(len(saved), size, replace=False).tolist())
    frame, by_id = round_names(round_).set_index("ticker"), {a["id"]: a for a in agents()}
    rows = []
    with H.Server("gemma", H.LONG_PROMPTS) as server:
        for i in chosen:
            old = saved[i]
            batch = frame.loc[old["tickers"]].reset_index()
            new = ask(server, by_id[old["agent"]], batch, round_, old["batch"])
            rows.append(
                {
                    "agent": old["agent"],
                    "batch": old["batch"],
                    "same_prompt": new["prompt_sha256"] == old["prompt_sha256"],
                    "same_votes": new["votes"] == old["votes"],
                }
            )
    path = SF / "votes" / f"{round_}_replay.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = {
        "round": round_,
        "replayed": len(rows),
        "same_prompt": sum(r["same_prompt"] for r in rows),
        "same_votes": sum(r["same_votes"] for r in rows),
    }
    print(json.dumps(out))
    return out


# The repo's SEC fetcher, paced under SEC's ten a second, with contact.
def edgar():
    folder = ROOT / "tools" / "data"
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    import edgar as E

    return E


# One SEC JSON document, cached for the run.
def sec_json(url: str, cache: dict = {}) -> dict:  # noqa: B006
    if url not in cache:
        cache[url] = json.loads(edgar().fetch(url))
    return cache[url]


# Recent filings of one company from SEC's submissions API.
def filings(cik: int) -> pd.DataFrame:
    recent = sec_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    recent = recent["filings"]["recent"]
    cols = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "items"]
    out = pd.DataFrame({c: recent.get(c, []) for c in cols})
    out["accepted"] = pd.to_datetime(out["acceptanceDateTime"], utc=True)
    return out


# A time in UTC; a date without a zone counts as UTC.
def utc(when) -> pd.Timestamp:
    t = pd.Timestamp(when)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


# Earnings 8-Ks (item 2.02) accepted after a quarter end.
def releases(cik: int, after, before=None) -> pd.DataFrame:
    f = filings(cik)
    f = f[f["form"].isin(["8-K", "8-K/A"]) & f["items"].fillna("").str.contains("2.02")]
    f = f[f["accepted"] > utc(after)]
    if before is not None:
        f = f[f["accepted"] < utc(before)]
    return f.sort_values("accepted").reset_index(drop=True)


# Plain text of one cell, spaces squeezed.
def squeeze(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


# HTML tables as lists of rows of cell text, standard library only.
class Tables(HTMLParser):
    # An empty parser.
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.row, self.cell = [], [], None, None

    # Opens a table, row or cell.
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in ("br", "p", "div") and self.cell is not None:
            self.cell.append(" ")

    # Closes a cell, row or table, keeping what it held.
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(squeeze("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.stack:
            self.stack[-1].append(self.row)
            self.row = None
        elif tag == "table" and self.stack:
            self.tables.append(self.stack.pop())

    # Text inside a cell.
    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


# Every table in a document.
def tables(text: str) -> list[list[list[str]]]:
    parser = Tables()
    parser.feed(text)
    return parser.tables


NUMBER = re.compile(r"^\(?-?\d[\d,]*(\.\d+)?\)?$")
# Revenue lines, and words that mark a line as something else.
REVENUE_LINE = re.compile(r"\b(revenues?|net sales|sales)\b", re.I)
NOT_REVENUE = re.compile(
    r"cost|expense|deferred|unearned|receivable|per |%|percent|growth|margin|tax|backlog"
    r"|days|ratio|excluding|constant|organic|adjusted|non-gaap|change|increase|decrease",
    re.I,
)


# A table cell as a number, or None for text, dashes and percents.
def number(cell: str):
    s = cell.replace("$", "").replace(" ", "").strip()
    if "%" in s or not s:
        return None
    negative = s.startswith("(")
    s = s.strip("()")
    if not NUMBER.match(s):
        return None
    value = float(s.replace(",", ""))
    return -value if negative else value


# Rows whose label reads as revenue, with their numbers in order.
def revenue_rows(found: list) -> list[tuple[str, list[float]]]:
    out = []
    for table in found:
        for row in table:
            label = next((c for c in row if re.search(r"[A-Za-z]", c)), "")
            if not REVENUE_LINE.search(label) or NOT_REVENUE.search(label):
                continue
            values = [v for v in (number(c) for c in row if c != label) if v is not None]
            if values:
                out.append((label, values))
    return out


# Label and number runs from plain text, for tables without tags.
def text_rows(text: str) -> list[tuple[str, list[float]]]:
    flat = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\u200b", " ")
    out, label, values = [], [], []
    for token in flat.split():
        value = None if token == "$" else number(token)
        if token == "$":
            continue
        if value is not None:
            values.append(value)
            continue
        if values:
            out.append((" ".join(label[-12:]), values))
            label, values = [], []
        label.append(token)
    if values:
        out.append((" ".join(label[-12:]), values))
    return out


# Rows that read as revenue, from tables first, then the plain text.
def revenue_lines(text: str) -> list[tuple[str, list[float]]]:
    rows = revenue_rows(tables(text))
    for label, values in text_rows(text):
        tail = re.split(r"[.:;]", label)[-1]
        if REVENUE_LINE.search(tail) and not NOT_REVENUE.search(tail) and len(values) >= 2:
            rows.append((tail.strip(), values))
    return rows


# Quarter revenue beside the printed year-ago figure matching XBRL.
def extract(text: str, year_ago: float) -> dict | None:
    found = []
    for row, (label, values) in enumerate(revenue_lines(text)):
        for scale in (1.0, 1e3, 1e6, 1e9):
            gaps = [abs(v * scale - year_ago) / year_ago if v > 0 else 1.0 for v in values]
            # Only the closest figure in a row is the year-ago one.
            i = int(np.argmin(gaps))
            if gaps[i] <= TIGHT:
                v = values[i]
                # Five quarter-sized figures from the anchor are a trend row.
                trend = values[i : i + 5]
                trend = len(trend) == 5 and all(0.5 < w / v < 1.95 for w in trend)
                j = i + 4 if trend else (i - 1 if i % 2 else (0 if i else 1))
                # Identical figures in both columns are a repeat, not a pair.
                if j >= len(values) or values[j] == v or not 0.2 < values[j] / v < 5:
                    continue
                found.append(
                    {
                        "label": label,
                        "current": values[j] * scale,
                        "year_ago": v * scale,
                        "scale": scale,
                        "match": "tight",
                        "pair": i == 1,
                        "row": row,
                    }
                )
    if not found:
        return None
    # The figure printed most often wins; then the plain pair, then size.
    seen = pd.DataFrame(found).groupby("current")["row"].nunique()
    return min(found, key=lambda f: (-seen[f["current"]], not f["pair"], -f["current"]))


# The exhibit 99 documents of one filing, from its index page.
def exhibits(cik: int, accn: str) -> list[str]:
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"
    page = edgar().fetch(f"{base}/{accn}-index.htm").decode("utf-8", "replace")
    out = []
    for row in (r for t in tables(page) for r in t):
        kinds = [c for c in row if re.fullmatch(r"EX-99(\.0?1)?\S*", c)]
        docs = [c.split()[0] for c in row if re.search(r"\.html?\b", c)]
        if kinds and docs:
            out.append((kinds[0], f"{base}/{docs[0]}"))
    # Exhibit 99.1 first, then any other exhibit 99.
    out.sort(key=lambda k: (not re.fullmatch(r"EX-99\.0?1", k[0]), k[0]))
    return [url for _, url in out]


# The release's quarter revenue, anchored on the filed year-ago figure.
def from_release(cik: int, accn: str, year_ago: float) -> dict | None:
    for url in exhibits(cik, accn):
        text = edgar().fetch(url).decode("utf-8", "replace")
        found = extract(text, year_ago)
        if found:
            return found | {"url": url, "accn": accn}
    return None


# Live XBRL company facts for one company as a flat table.
def live_facts(cik: int) -> pd.DataFrame:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    # Large documents, read once and never cached.
    try:
        raw = json.loads(edgar().fetch(url))
    except Exception as err:
        print(f"  no company facts for CIK {cik}: {err}", flush=True)
        return pd.DataFrame(columns=["tag", "start", "end", "val", "accn", "form", "filed"])
    rows = []
    for tag in REVENUE_TAGS:
        for f in (
            raw.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
        ):
            if "start" in f:
                rows.append((tag, f["start"], f["end"], f["val"], f["accn"], f["form"], f["filed"]))
    return pd.DataFrame(rows, columns=["tag", "start", "end", "val", "accn", "form", "filed"])


# A quarter in a company's series near a date, or None.
def quarter_at(quarters: pd.DataFrame, end) -> pd.Series | None:
    near = (quarters["end"] - pd.Timestamp(end)).abs().dt.days <= 15
    return quarters[near].iloc[0] if near.any() else None


# The release reader against each name's last 10-Q figure in XBRL.
def validate(least: int = 5, held_out: bool = False, fresh: bool = False) -> dict:
    frame = pd.read_csv(SF / "names_event.csv")
    frame = frame[frame["in_contest"]].sort_values("weight", key=abs, ascending=False)
    # Held out: the day-2 names, not used to tune the reader.
    if held_out:
        frame = round_names("extra").sort_values("weight", key=abs, ascending=False)
    # Fresh: the rest of the book, read only by the final reader.
    if fresh:
        held = book()
        held = held[~held["ticker"].isin(pd.read_csv(SF / "names_twoweeks.csv")["ticker"])]
        frame = held.assign(cik=ciks(held), last_end=None).dropna(subset=["cik"])
        frame = frame.sort_values("weight", key=abs, ascending=False)
    tag = "_held_out" if held_out else "_fresh" if fresh else ""
    rows = []
    for r in frame.itertuples():
        quarters = revenue(live_facts(r.cik), AS_OF)
        if r.last_end is None:
            if quarters.empty:
                rows.append({"ticker": r.ticker, "status": "no XBRL quarter"})
                continue
            r = r._replace(last_end=quarters["end"].max().date().isoformat())
        last = quarter_at(quarters, r.last_end)
        ago = quarter_at(quarters, pd.Timestamp(r.last_end) - pd.DateOffset(years=1))
        row = {"ticker": r.ticker, "quarter_end": r.last_end, "xbrl_revenue": None}
        if last is None or ago is None:
            rows.append(row | {"status": "no XBRL quarter"})
            continue
        row["xbrl_revenue"] = float(last["val"])
        found = releases(r.cik, r.last_end, pd.Timestamp(r.last_end) + pd.Timedelta(days=80))
        if found.empty:
            rows.append(row | {"status": "no 8-K 2.02 release"})
            continue
        # Every earnings 8-K in the window, as the scorer reads them.
        got = None
        for accn in found["accessionNumber"]:
            got = got or from_release(r.cik, accn, float(ago["val"]))
        if not got:
            rows.append(row | {"status": "not extracted", "accn": found.iloc[0]["accessionNumber"]})
            continue
        gap = got["current"] / float(last["val"]) - 1
        g_release = got["current"] / got["year_ago"] - 1
        row |= {
            "release_revenue": got["current"],
            "gap": round(gap, 6),
            "growth_release": round(g_release, 6),
            "growth_xbrl": round(float(last["growth"]), 6),
            "match": got["match"],
            "label": got["label"],
            "url": got["url"],
        }
        rows.append(row | {"status": "agrees" if abs(gap) <= TIGHT else "disagrees"})
    table = pd.DataFrame(rows)
    table.to_csv(SF / f"validation{tag}.csv", index=False)
    tried = table[table["status"].isin(["agrees", "disagrees", "not extracted"])]
    lead = tried.head(least)
    out = {
        "first_five": lead[["ticker", "quarter_end", "status"]].to_dict("records"),
        "first_five_agree": int((lead["status"] == "agrees").sum()),
        "all_tried": len(tried),
        "all_agree": int((tried["status"] == "agrees").sum()),
        "all_disagree": int((tried["status"] == "disagrees").sum()),
        "all_not_extracted": int((tried["status"] == "not extracted").sum()),
        "skipped": table.loc[~table.index.isin(tried.index), "status"].value_counts().to_dict(),
        "growth_within_0.1_points": int(
            ((tried["growth_release"] - tried["growth_xbrl"]).abs() <= 0.001).sum()
        )
        if "growth_release" in tried
        else 0,
    }
    (SF / f"validation{tag}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    return out


# The kit's answer reader, loaded from its folder with app users added.
def ca_kit():
    spec = importlib.util.spec_from_file_location("ca_ingest", CA_KIT / "ingest.py")
    kit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit)
    kit.METRICS["app_users"] = {"dataset": "CA0013", "insight": APP_INSIGHT, "column": "app_users"}
    return kit


# Months of a quarter ending at a date, latest last.
def quarter_months(end) -> list[pd.Period]:
    last = pd.Period(pd.Timestamp(end) - pd.Timedelta(days=7), "M")
    return [last - 2, last - 1, last]


# Growth over a quarter's months present in both years, or None.
def months_growth(series: pd.Series, months: list[pd.Period], kind: str) -> float | None:
    if kind == "yoy":
        have = [series[m] for m in months if m in series.index]
        return float(np.mean(have)) if len(have) >= 2 else None
    pairs = [
        (series[m], series[m - 12]) for m in months if m in series.index and m - 12 in series.index
    ]
    if len(pairs) < 2 or sum(b for _, b in pairs) <= 0:
        return None
    return sum(a for a, _ in pairs) / sum(b for _, b in pairs) - 1


# The Carbon Arc vote for one name from its cleaned monthly rows.
def ca_vote_one(rows: pd.DataFrame, target_end) -> dict:
    this = quarter_months(target_end)
    before = [m - 3 for m in this]
    for metric in ORDER:
        part = rows[(rows["metric"] == metric) & ~rows["quarterly"].astype(bool)]
        for kind in ("level", "yoy"):
            mine = part[part["kind"] == kind]
            if mine.empty:
                continue
            series = mine.set_index(pd.PeriodIndex(mine["month"], freq="M"))["value"]
            now, then = months_growth(series, this, kind), months_growth(series, before, kind)
            if now is None or then is None:
                continue
            change = now - then
            word = UP if change >= BAND else DOWN if change <= -BAND else ABSTAIN
            return {"ca": word, "metric": metric, "growth_now": now, "growth_before": then,
                    "change": change}  # fmt: skip
    return {"ca": ABSTAIN, "metric": "", "growth_now": None, "growth_before": None,
            "change": None, "note": "no series with both quarters"}  # fmt: skip


# Carbon Arc votes for every contest name from saved answers.
def ca_votes(answers: Path | None = None) -> pd.DataFrame:
    kit = ca_kit()
    answers = answers or SF / "ca_answers"
    frame = pd.read_csv(SF / "names_twoweeks.csv")
    frame = frame[frame["in_contest"]]
    clean, report = kit.ingest(answers, frame[["ticker"]], None)
    rows = []
    for r in frame.itertuples():
        got = ca_vote_one(clean[clean["ticker"] == r.ticker], r.target_end)
        rows.append({"ticker": r.ticker, "target_end": r.target_end} | got)
    out = pd.DataFrame(rows)
    out.to_csv(SF / "carbon_arc_votes.csv", index=False)
    (SF / "carbon_arc_ingest.json").write_text(json.dumps(report, indent=1, default=str))
    print(out["ca"].value_counts().to_string())
    return out


# Each file's SHA-256.
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Contest names whose earnings 8-K reached SEC before a time.
def reported_before(frame: pd.DataFrame, when: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for r in frame.itertuples():
        found = releases(r.cik, r.target_end, when)
        if not found.empty:
            first = found.iloc[0]
            rows.append({"ticker": r.ticker, "accn": first["accessionNumber"],
                         "accepted": first["accepted"].isoformat()})  # fmt: skip
    return pd.DataFrame(rows, columns=["ticker", "accn", "accepted"])


# The seal: drops names already reported, then hashes every input.
def seal(offline: bool = False) -> dict:
    now = pd.Timestamp.now(tz="UTC").floor("s")
    contest = []
    for label in ("event", "twoweeks"):
        frame = pd.read_csv(SF / f"names_{label}.csv")
        frame = frame[frame["in_contest"]]
        gone = reported_before(frame, now) if not offline else pd.DataFrame(columns=["ticker"])
        gone.to_csv(SF / f"dropped_at_seal_{label}.csv", index=False)
        keep = frame[~frame["ticker"].isin(gone["ticker"])].assign(list=label)
        contest.append(keep)
    pd.concat(contest).to_csv(SF / "contest.csv", index=False)
    files = [SF / "RULES.md", SF / "CHANGES.md", SF / "names_event.csv", SF / "names_twoweeks.csv"]
    files += sorted((SF / "votes").glob("*.jsonl")) + sorted((SF / "votes").glob("*.json"))
    files += [SF / n for n in ("crowd_event.csv", "crowd_twoweeks.csv", "crowd_views.json")]
    files += [SF / n for n in ("dropped_at_seal_event.csv", "dropped_at_seal_twoweeks.csv")]
    files += [SF / "contest.csv", SF / "carbon_arc_votes.csv"]
    files += sorted((SF / "ca_answers").glob("*")) if (SF / "ca_answers").exists() else []
    files += [ROOT / "fiam" / "alt" / "sixty_first.py", ROOT / "tests" / "test_sixty_first.py"]
    files = [f for f in files if f.exists() and not f.name.endswith("_replay.jsonl")]
    lines = [f"{digest(f)}  {display(f)}" for f in files]
    total = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    previous = SF / "SEAL.txt"
    before = previous.read_text().splitlines()[0] if previous.exists() else "none"
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    dropped = sum(len(pd.read_csv(SF / f"dropped_at_seal_{x}.csv")) for x in ("event", "twoweeks"))
    has_ca = "included" if (SF / "carbon_arc_votes.csv").exists() else "not yet"
    head = [f"SHA-256 {total}", f"UTC {stamp}", f"previous seal {before}"]
    head += [f"Carbon Arc votes {has_ca}", f"names dropped as already reported {dropped}"]
    text = "\n".join([*head, "", "files", *lines, ""])
    previous.write_text(text, encoding="utf-8")
    # Each seal keeps its own copy and its own contest list.
    (SF / "seals").mkdir(exist_ok=True)
    (SF / "seals" / f"SEAL_{now:%Y%m%dT%H%M%SZ}.txt").write_text(text, encoding="utf-8")
    (SF / "seals" / f"contest_{now:%Y%m%dT%H%M%SZ}.csv").write_bytes(
        (SF / "contest.csv").read_bytes()
    )
    print(text)
    return {"sha256": total, "utc": stamp, "files": len(files)}


# A path shown relative to the outputs or the repo.
def display(path: Path) -> str:
    for base, tag in ((SF, "SF"), (ROOT, "repo")):
        try:
            return f"{tag}/{path.resolve().relative_to(base.resolve())}"
        except ValueError:
            continue
    return str(path)


# The coin's call for a ticker, set by the seal hash alone.
def coin(seal_hash: str, ticker: str) -> str:
    return UP if hashlib.sha256(f"{seal_hash}{ticker}".encode()).digest()[0] % 2 else DOWN


# This quarter's growth: the 10-Q in XBRL, else the release.
def truth(r) -> dict:
    quarters = revenue(live_facts(r.cik))
    filed = quarter_at(quarters, r.target_end) if len(quarters) else None
    if filed is not None and not pd.isna(filed["growth"]):
        return {"growth_now": float(filed["growth"]), "source": "10-Q XBRL",
                "accn": filed["accn"]}  # fmt: skip
    found = releases(r.cik, r.target_end)
    ago = r.target_ago if not pd.isna(r.target_ago) else None
    if found.empty or ago is None:
        return {"source": "waits for the report" if found.empty else "no year-ago figure"}
    for accn in found["accessionNumber"]:
        got = from_release(r.cik, accn, float(ago))
        if not got:
            continue
        now = got["current"] / got["year_ago"] - 1
        return {"growth_now": now, "source": "8-K exhibit 99", "accn": accn,
                "match": got["match"], "provisional": True}  # fmt: skip
    return {"source": "release not read, waits for the 10-Q"}


# A vote against the truth: hit, miss or abstain.
def mark(vote_: str, truth_: str | None) -> str:
    if truth_ is None:
        return ""
    if vote_ not in (UP, DOWN):
        return "abstain"
    return "hit" if vote_ == truth_ else "miss"


# The tickers live in the first seal that hashed a file, or None.
def live_at_first_seal_with(name: str) -> set | None:
    for path in sorted((SF / "seals").glob("SEAL_*.txt")):
        if f"  SF/{name}\n" in path.read_text():
            stamp = path.stem.removeprefix("SEAL_")
            return set(pd.read_csv(SF / "seals" / f"contest_{stamp}.csv")["ticker"])
    return None


# Scores reported names, each judged by the seal that held its votes.
def score() -> dict:
    sealed = (SF / "SEAL.txt").read_text().splitlines()[0].split()[-1]
    # The coin uses the first seal, which every report came after.
    seals = sorted((SF / "seals").glob("SEAL_*.txt"))
    first_seal = seals[0].read_text().splitlines()[0].split()[-1] if seals else sealed
    lists = sorted((SF / "seals").glob("contest_*.csv"))
    first = pd.read_csv(lists[0]) if lists else pd.read_csv(SF / "contest.csv")
    contest = first.sort_values("list").drop_duplicates("ticker")
    # Event names were sealed first, the rest with the extra round.
    event = set(contest.loc[contest["list"] == "event", "ticker"])
    extra = live_at_first_seal_with("votes/extra.jsonl") or set()
    live = (set(first["ticker"]) & event) | (extra - event)
    crowd_ = pd.read_csv(SF / "crowd_twoweeks.csv").set_index("ticker")
    path = SF / "carbon_arc_votes.csv"
    ca = pd.read_csv(path).set_index("ticker") if path.exists() else pd.DataFrame()
    rows = []
    for r in contest.itertuples():
        got = truth(r)
        now = got.get("growth_now")
        word = None if now is None else (UP if now > r.growth_last else DOWN)
        row = {"ticker": r.ticker, "list": r.list, "side": r.side, "target_end": r.target_end,
               "growth_last": r.growth_last, "growth_now": now, "truth": word} | got  # fmt: skip
        row["crowd"] = crowd_["crowd"].get(r.ticker, ABSTAIN)
        row["carbon_arc"] = ca["ca"].get(r.ticker, "not asked") if len(ca) else "not asked"
        if r.ticker not in live:
            row["crowd"] = row["carbon_arc"] = LATE
        row["coin"] = coin(first_seal, r.ticker)
        for who in ("crowd", "carbon_arc", "coin"):
            row[f"{who}_result"] = mark(row[who], word)
        for who in ("crowd", "carbon_arc"):
            if row[who] in ("not asked", LATE):
                row[f"{who}_result"] = ""
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(SF / "scores.csv", index=False)
    board = {"seal": sealed, "coin_seal": first_seal}
    board["scored_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    for label in ("event", "twoweeks"):
        part = table if label == "twoweeks" else table[table["list"] == "event"]
        done = part[part["truth"].notna()]
        board[label] = {"names": len(part), "reported": len(done)}
        for who in ("crowd", "carbon_arc", "coin"):
            res = done[f"{who}_result"].value_counts().to_dict()
            board[label][who] = {k: int(res.get(k, 0)) for k in ("hit", "miss", "abstain")}
        # The head to head: only names both sides called before the report.
        both = done[(done["carbon_arc_result"] != "") & (done["crowd_result"] != "")]
        board[label]["head_to_head_names"] = len(both)
        for who in ("crowd", "carbon_arc", "coin"):
            res = both[f"{who}_result"].value_counts().to_dict()
            board[label][f"{who}_head_to_head"] = {
                k: int(res.get(k, 0)) for k in ("hit", "miss", "abstain")
            }
    (SF / "scoreboard.json").write_text(json.dumps(board, indent=1), encoding="utf-8")
    print(json.dumps(board, indent=1))
    return board


STYLE = (
    "body{font-family:Inter,system-ui,sans-serif;margin:0;padding:28px;background:#f4f1fa;"
    "color:#16111f}.card{max-width:560px;background:#fff;border-radius:14px;padding:22px 26px;"
    "margin:0 auto 22px;box-shadow:0 1px 3px rgba(22,17,31,.12);border-top:6px solid #8f6fea}"
    "h1{font-size:22px;margin:0 0 2px}h1 span{font-weight:400;color:#7e7798;font-size:16px}"
    ".tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;color:#fff;"
    "margin:6px 6px 12px 0}.long{background:#2fa3bd}.short{background:#e0703a}"
    ".plain{background:#7e7798}table{border-collapse:collapse;width:100%;font-size:14px}"
    "th{text-align:left;font-weight:500;color:#7e7798;padding:7px 10px 7px 0;width:44%;"
    "vertical-align:top}td{padding:7px 0;border-bottom:1px solid #ede9f6}"
    "footer{font-size:11px;color:#7e7798;margin-top:12px;line-height:1.5}"
    "a{color:#8f6fea}.grid{display:flex;flex-wrap:wrap;gap:0 22px;justify-content:center}"
)


# A vote as card text with its counts.
def crowd_text(row) -> str:
    if row is None:
        return "Not asked"
    word = {UP: "Speeds up", DOWN: "Slows down", ABSTAIN: "Split, no call"}[row["crowd"]]
    return f"{word} ({int(row['up'])} up and {int(row['down'])} down of 60)"


# One name's card as HTML, plain copy without colons.
def card_html(r, crowd_row, ca_row, score_row, views_: float | None, sealed: str) -> str:
    esc = html.escape
    side = "Long" if r.side == "long" else "Short"
    ca_text = "Filled in the morning"
    if ca_row is not None:
        word = {UP: "Speeds up", DOWN: "Slows down", ABSTAIN: "No call"}[ca_row["ca"]]
        metric = str(ca_row.get("metric") or "").replace("_", " ")
        ca_text = f"{word} on {metric}" if metric else f"{word}, no Carbon Arc series"
    elif not (r.card_spend or r.web_traffic):
        ca_text = "Not covered by card spend or web traffic"
    crowd_says = crowd_text(crowd_row)
    # A name that reported before its seal shows no vote at all.
    if score_row is not None and score_row.get("crowd") == LATE:
        crowd_says = ca_text = "Reported before the seal so not counted"
    result = "Waits for the report"
    if score_row is not None and isinstance(score_row.get("truth"), str):
        grew = pct(score_row["growth_now"])
        result = f"{score_row['truth'].capitalize()} ({grew} against {pct(r.growth_last)})"
    rows = [
        ("Sector", r.sector),
        ("Reports around", str(r.projected)),
        ("Revenue growth, earlier quarter", f"{pct(r.growth_prev)} in the quarter to {r.prev_end}"),
        ("Revenue growth, last quarter", f"{pct(r.growth_last)} in the quarter to {r.last_end}"),
        ("The AI crowd", crowd_says),
        ("Independent views in the crowd", f"About {views_:.0f}" if views_ else "Not measured"),
        ("The 61st investor, Carbon Arc", ca_text),
        ("Result", result),
    ]
    body = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)
    credit = f"<br>{esc(CREDIT)}. {esc(NOT_TRADED)}." if ca_row is not None else ""
    return (
        f'<div class="card"><h1>{esc(r.name)} <span>{esc(r.ticker)}</span></h1>'
        f'<span class="tag {r.side}">{side} {abs(100 * r.weight):.2f}% of the fund</span>'
        f'<span class="tag plain">Sealed {esc(sealed)}</span><table>{body}</table>'
        f"<footer>Does this quarter's revenue growth speed up or slow down against last "
        f"quarter's? Truth from the company's own SEC filings.{credit}</footer></div>"
    )


# The X-ray cards: one page per name and one page with them all.
def cards() -> int:
    frame = pd.read_csv(SF / "names_twoweeks.csv")
    frame = frame[frame["in_contest"]]
    seal_path = SF / "SEAL.txt"
    sealed = "not yet"
    if seal_path.exists():
        lines = seal_path.read_text().splitlines()
        sealed = f"{lines[1].split()[-1][:10]} hash {lines[0].split()[-1][:12]}"
    crowd_ = pd.read_csv(SF / "crowd_twoweeks.csv").set_index("ticker")
    ca_path, sc_path = SF / "carbon_arc_votes.csv", SF / "scores.csv"
    ca = pd.read_csv(ca_path).set_index("ticker") if ca_path.exists() else None
    sc = pd.read_csv(sc_path).set_index("ticker") if sc_path.exists() else None
    views_ = json.loads((SF / "crowd_views.json").read_text())
    folder = SF / "cards"
    folder.mkdir(exist_ok=True)
    event = set(pd.read_csv(SF / "names_event.csv")["ticker"])
    pages = {"event": [], "twoweeks": []}
    for r in frame.itertuples():
        label = "event" if r.ticker in event else "twoweeks"
        eff = views_.get(label, {}).get("effective_voters")
        pick = lambda t, x: x.loc[t] if x is not None and t in x.index else None  # noqa: E731
        one = card_html(r, pick(r.ticker, crowd_), pick(r.ticker, ca), pick(r.ticker, sc), eff,
                        sealed)  # fmt: skip
        page = f'<!doctype html><meta charset="utf-8"><title>{html.escape(r.ticker)}</title>'
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", r.ticker)
        (folder / f"{safe}.html").write_text(f"{page}<style>{STYLE}</style>{one}")
        pages[label].append(one)
        if label == "event":
            pages["twoweeks"].append(one)
    for label, items in pages.items():
        head = '<!doctype html><meta charset="utf-8"><title>The 61st Investor</title>'
        head += f"<style>{STYLE}</style>"
        (folder / f"index_{label}.html").write_text(
            f'{head}<div class="grid">{"".join(items)}</div>'
        )
    print(f"{len(frame)} cards in {folder}")
    return 0


# Runs scoring now and again every few minutes until all report.
def watch(minutes: float = 30, until: str = "2026-11-21") -> int:
    while pd.Timestamp.now() < pd.Timestamp(until):
        board = score()
        cards()
        if board["twoweeks"]["reported"] >= board["twoweeks"]["names"]:
            return 0
        time.sleep(minutes * 60)
    return 0


# uv run python -m fiam.alt.sixty_first names | vote event | crowd | ...
def main(argv=None) -> int:
    task, *rest = argv if argv is not None else (sys.argv[1:] or ["names"])
    if task == "names":
        names()
    elif task == "vote":
        vote(rest[0] if rest else "event")
    elif task == "crowd":
        crowd()
    elif task == "replay":
        replay(rest[0] if rest else "event")
    elif task == "validate":
        validate(held_out="--held-out" in rest, fresh="--fresh" in rest)
    elif task == "ca":
        ca_votes(Path(rest[0]) if rest else None)
    elif task == "seal":
        seal(offline="--offline" in rest)
    elif task == "score":
        score()
    elif task == "watch":
        watch(float(rest[0]) if rest else 30)
    elif task == "cards":
        cards()
    else:
        print(__doc__ or "tasks: names vote crowd replay validate ca seal score watch cards")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
