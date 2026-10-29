# The risk desk: flags on the final book set by code, worded by a model.

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from fiam.agents import desk as D
from fiam.agents import final_book as F
from fiam.agents import harness as H
from fiam.vfinal import config as C

PANEL = H.ROOT / "data" / "organisers" / "chars_final_with_names.parquet"
RETURNS = D.PACK / "src" / "cache" / "market_ret.parquet"
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
# Sessions of history for the book's beta and its volatility.
BETA_DAYS, VOL_DAYS = 252, 63
# The desk's own thresholds where the finals PDF sets no limit.
DESK = dict(
    beta_alert=0.10,
    crowd_t_watch=2.0,
    top10_long_share_watch=0.5,
    exit_sessions_watch_share=0.8,
    limit_watch_share=0.75,
)
SYSTEM = (
    "You are the risk desk of a market-neutral US equity fund. You write a short risk note on "
    "today's book for the investment committee. You only write. You never trade, never set or "
    "change a weight, and never advise anyone to buy, sell, cover, trim, cut, add or hedge. "
    "Each flag's level is set by code; you explain it, you never change it. Use only the facts "
    "given. Every number you write is checked by code, and a sentence with a number not in "
    "the facts is deleted."
)


PROMPT_NUMBER = 3


# The reply's shape: a summary and one reason per flag id given.
def schema(ids: list[str]) -> dict:
    reason = dict(
        type="object",
        properties=dict(id=dict(type="string", enum=ids), reason=dict(type="string")),
        required=["id", "reason"],
    )
    return dict(
        type="object",
        properties=dict(
            summary=dict(type="string"),
            reasons=dict(type="array", items=reason, minItems=len(ids), maxItems=len(ids)),
        ),
        required=["summary", "reasons"],
    )


# Each held name's GICS sector on the book's date, from the panel.
def sectors(permnos: pd.Series) -> pd.Series:
    panel = pd.read_parquet(PANEL, columns=["permno", "eom", "gics"])
    panel = panel[pd.to_datetime(panel["eom"]) <= pd.Timestamp(F.AS_OF)].dropna(subset=["gics"])
    last = panel.sort_values("eom").groupby("permno")["gics"].last()
    code = permnos.map(last).astype("Int64").astype(str).str[:2]
    return code.map(GICS).fillna("Unknown")


# Beta and volatility of today's weights over past daily returns.
def history_risk(book: pd.DataFrame) -> dict:
    wide = pd.read_parquet(RETURNS).set_index("date")
    wide = wide.loc[: pd.Timestamp(F.AS_OF)]
    cols = [str(p) for p in book["permno"]]
    missing = [c for c in cols if c not in wide.columns]
    have = [c for c in cols if c in wide.columns]
    rets = wide[have].tail(BETA_DAYS)
    paths = pd.read_csv(D.DATA / "daily_paths.csv", parse_dates=["date"]).set_index("date")
    market = paths["sp500_ret"].reindex(rets.index)
    betas = rets.apply(lambda s: s.cov(market) / market.var())
    w = pd.Series(book["w"].to_numpy(), index=cols)[have]
    daily = rets.fillna(0.0) @ w
    return dict(
        beta=float((w * betas).sum()),
        beta_long=float((w[w > 0] * betas[w > 0]).sum()),
        beta_short=float((w[w < 0] * betas[w < 0]).sum()),
        vol_pct=float(daily.tail(VOL_DAYS).std() * np.sqrt(252) * 100),
        first_day=str(rets.index.min().date()),
        last_day=str(rets.index.max().date()),
        names_without_returns=len(missing),
        realised_beta_252d=float(paths["beta252"].iloc[-1]),
        realised_vol_63d_pct=float(paths["vol63_pct"].iloc[-1]),
    )


# Days of volume to exit each name on the book's date.
def liquidity() -> dict:
    adv = pd.read_csv(D.DATA / "days_of_adv.csv", parse_dates=["date"])
    day = adv[adv["date"] == adv["date"].max()]
    rate = C.BOOK.execution.participation
    sessions = day["days_adv"] / rate
    limit = C.BOOK.policy.days_to_exit_max
    return dict(
        date=str(day["date"].max().date()),
        names=int(len(day)),
        days_of_volume_max=float(day["days_adv"].max()),
        days_of_volume_median=float(day["days_adv"].median()),
        participation=rate,
        sessions_to_exit_max=float(sessions.max()),
        sessions_limit=limit,
        names_over_limit=int((sessions > limit).sum()),
    )


# The AI crowd's view of the book, live August run when present.
def crowd() -> dict:
    live = D.load(D.CROWD_LIVE)
    if live:
        sell = live["sell_off_final_book_share_of_nav"]
        worst = min((v, k, s) for k, case in sell.items() for s, v in case.items())
        return dict(
            source=str(D.CROWD_LIVE),
            long_percentile=live["round"]["long_pct"],
            short_percentile=live["round"]["short_pct"],
            crowd_beta=live["crowd_factor_beta"]["beta"],
            crowd_beta_t=live["crowd_factor_beta"]["t"],
            sell_off_worst_pct_nav=worst[0] * 100,
            sell_off_worst_case=f"{worst[1].replace('_', ' ')} selling ${worst[2]}",
            sell_off_note=live.get("sell_off_note"),
        )
    old = D.load(D.CROWD)
    sell = old["sell_off_final_book_pct_nav"] if "sell_off_final_book_pct_nav" in old else {}
    worst = min(sell.items(), key=lambda kv: kv[1]) if sell else ("none", 0.0)
    return dict(
        source=str(D.CROWD),
        long_percentile=round(old["final_book_2026_08"]["long_mean_pct"] * 100),
        short_percentile=round(old["final_book_2026_08"]["short_mean_pct"] * 100),
        crowd_beta=old["crowd_factor_beta"]["beta"],
        crowd_beta_t=old["crowd_factor_beta"]["t"],
        sell_off_worst_pct_nav=worst[1] * 100,
        sell_off_worst_case=f"crowd model selling ${worst[0]}",
        sell_off_note=None,
    )


# The Carbon Arc map as counts and aggregates, never one name's figure.
def carbon_arc() -> dict:
    card = D.load(D.HYPE)["card"]
    flags = card["flags"]
    lvs = card["longs_vs_shorts"]
    fav = card["crowd_favourites"]
    return dict(
        source=str(D.HYPE),
        longs_with_growth=card["coverage"]["with_growth_book_longs"],
        shorts_with_growth=card["coverage"]["with_growth_book_shorts"],
        long_spend_growth_pct=lvs["long_wmean"] * 100,
        short_spend_growth_pct=lvs["short_wmean"] * 100,
        split_p_value=lvs["permutation_p_two_sided"],
        longs_in_hype=sum(f["flag"] == "long in Hype" for f in flags),
        longs_in_hype_strong=sum(f["flag"] == "long in Hype" and f["strong"] for f in flags),
        shorts_in_hidden_gems=sum(f["flag"] == "short in Hidden gems" for f in flags),
        shorts_in_hidden_gems_strong=sum(
            f["flag"] == "short in Hidden gems" and f["strong"] for f in flags
        ),
        crowd_favourites_with_growth=fav["favourites_with_growth"],
        crowd_favourites_in_hype=fav["in_hype"],
        never_an_input="Carbon Arc is never an input to the fund, its weights or its backtest",
    )


# Every fact the desk reads about the final book.
def book_facts() -> dict:
    book = pd.read_csv(F.BOOK)
    w = book["w"]
    gross = float(w.abs().sum())
    longs, shorts = book[w > 0], book[w < 0]
    top_long = longs.loc[longs["w"].idxmax()]
    top_short = shorts.loc[shorts["w"].idxmin()]
    book["sector"] = sectors(book["permno"])
    nets = book.groupby("sector")["w"].sum().drop("Unknown", errors="ignore") * 100
    share = w.abs() / gross
    return dict(
        date=F.AS_OF,
        source=str(F.BOOK),
        names=int(len(book)),
        longs=int(len(longs)),
        shorts=int(len(shorts)),
        gross_pct=gross * 100,
        net_pct=float(w.sum()) * 100,
        largest_long=dict(ticker=top_long["ticker"], weight_pct=top_long["w"] * 100),
        largest_short=dict(ticker=top_short["ticker"], weight_pct=top_short["w"] * 100),
        top10_long_share_of_long_gross=float(longs["w"].nlargest(10).sum() / longs["w"].sum()),
        top10_short_share_of_short_gross=float(shorts["w"].nsmallest(10).sum() / shorts["w"].sum()),
        effective_names=float(1 / (share**2).sum()),
        sector_net_pct={k: float(v) for k, v in nets.sort_values().items()},
        sector_net_max=dict(sector=nets.abs().idxmax(), net_pct=float(nets[nets.abs().idxmax()])),
        sectors_held=int(book.loc[book["sector"] != "Unknown", "sector"].nunique()),
        unknown_sector_names=int((book["sector"] == "Unknown").sum()),
        history=history_risk(book),
        liquidity=liquidity(),
        crowd=crowd(),
        carbon_arc=carbon_arc(),
    )


# A level from how much of a limit a value uses.
def against(value: float, limit: float, guard: float | None = None) -> str:
    if abs(value) > limit:
        return "alert"
    if guard is not None and abs(value) > guard:
        return "watch"
    return "watch" if abs(value) >= DESK["limit_watch_share"] * limit else "ok"


# Above or below a limit, by size, worked out by code for the model.
def side(value: float, limit: float) -> str:
    return "above" if abs(value) > limit else "below"


# The flags, each a level, the number behind it and the rule it meets.
def flags(f: dict) -> list[dict]:
    hard, ex, pol = C.HARD, C.BOOK.execution, C.BOOK.policy
    h, liq, cr, ca = f["history"], f["liquidity"], f["crowd"], f["carbon_arc"]
    names_level = "ok" if hard["names_min"] <= f["names"] <= hard["names_max"] else "alert"
    beta = h["beta"]
    beta_level = (
        "alert"
        if abs(beta) > DESK["beta_alert"]
        else "watch"
        if abs(beta) > pol.beta_band
        else "ok"
    )
    exit_level = (
        "alert"
        if liq["sessions_to_exit_max"] > liq["sessions_limit"]
        else "watch"
        if liq["sessions_to_exit_max"] > DESK["exit_sessions_watch_share"] * liq["sessions_limit"]
        else "ok"
    )
    loss, worst_month = abs(cr["sell_off_worst_pct_nav"]), abs(f["worst_month_pct"])
    top_long, top_short = f["largest_long"]["weight_pct"], f["largest_short"]["weight_pct"]
    top10, sector = f["top10_long_share_of_long_gross"] * 100, f["sector_net_max"]["net_pct"]
    return [
        dict(
            id="gross",
            level=against(f["gross_pct"], hard["gross"] * 100, ex.gross_guard * 100),
            measure="gross exposure, % of capital",
            value=round(f["gross_pct"], 2),
            rule=f"{side(f['gross_pct'], hard['gross'] * 100)} the finals PDF limit of "
            f"{hard['gross'] * 100:.0f}%, {side(f['gross_pct'], ex.gross_guard * 100)} the "
            f"fund guard of {ex.gross_guard * 100:.0f}%, above which the fund trims gross back "
            f"to {ex.gross_trim_to * 100:.0f}%, so the book uses "
            f"{f['gross_pct'] / hard['gross']:.0f}% of the PDF limit",
        ),
        dict(
            id="net",
            level=against(f["net_pct"], hard["net"] * 100),
            measure="net exposure, % of capital",
            value=round(f["net_pct"], 2),
            rule=f"{'inside' if abs(f['net_pct']) <= hard['net'] * 100 else 'outside'} the "
            f"finals PDF band of minus {hard['net'] * 100:.0f}% to plus {hard['net'] * 100:.0f}%",
        ),
        dict(
            id="names",
            level=names_level,
            measure="names held, longs and shorts",
            value=f["names"],
            rule=f"{'inside' if names_level == 'ok' else 'outside'} the finals PDF range of "
            f"{hard['names_min']} to {hard['names_max']} names",
        ),
        dict(
            id="largest_long",
            level=against(
                f["largest_long"]["weight_pct"], hard["name_cap"] * 100, pol.position_cap * 100
            ),
            measure=f"largest long ({f['largest_long']['ticker']}), % of capital",
            value=round(f["largest_long"]["weight_pct"], 2),
            rule=f"{side(top_long, hard['name_cap'] * 100)} the finals PDF cap of "
            f"{hard['name_cap'] * 100:.0f}%, {side(top_long, pol.position_cap * 100)} the "
            f"fund's {pol.position_cap * 100:.1f}% cap that applies when the book is set, "
            f"{side(top_long, ex.trim_at * 100)} the {ex.trim_at * 100:.1f}% level at which "
            "the fund trims a long back",
        ),
        dict(
            id="largest_short",
            level=against(
                f["largest_short"]["weight_pct"],
                hard["name_cap"] * 100,
                pol.position_cap_short * 100,
            ),
            measure=f"largest short ({f['largest_short']['ticker']}), % of capital",
            value=round(f["largest_short"]["weight_pct"], 2),
            rule=f"{side(top_short, hard['name_cap'] * 100)} the finals PDF cap of "
            f"{hard['name_cap'] * 100:.0f}%, {side(top_short, pol.position_cap_short * 100)} "
            f"the fund's {pol.position_cap_short * 100:.2f}% short cap that applies when the "
            "book is set",
        ),
        dict(
            id="concentration",
            level="watch"
            if f["top10_long_share_of_long_gross"] > DESK["top10_long_share_watch"]
            else "ok",
            measure="ten largest longs, share of long gross %",
            value=round(f["top10_long_share_of_long_gross"] * 100, 1),
            rule=f"{side(top10, DESK['top10_long_share_watch'] * 100)} the desk's watch "
            f"level of {DESK['top10_long_share_watch'] * 100:.0f}%, the book is as spread as "
            f"{f['effective_names']:.0f} equal names",
        ),
        dict(
            id="sector_net",
            level=against(f["sector_net_max"]["net_pct"], hard["sector_net"] * 100),
            measure=f"largest sector net ({f['sector_net_max']['sector']}), % of capital",
            value=round(f["sector_net_max"]["net_pct"], 2),
            rule=f"{side(sector, hard['sector_net'] * 100)} the finals PDF limit of "
            f"{hard['sector_net'] * 100:.0f}%, {side(sector, pol.sector_band * 100)} the "
            f"fund's {pol.sector_band * 100:.0f}% band that applies when the book is set, "
            f"{f['sectors_held']} sectors held where the PDF asks for at least "
            f"{hard['sectors_min']}",
        ),
        dict(
            id="beta",
            level=beta_level,
            measure=f"beta to the S&P 500 of today's weights, {BETA_DAYS} sessions",
            value=round(beta, 3),
            rule=f"{side(beta, pol.beta_band)} the fund's band of {pol.beta_band} that applies "
            f"when the book is set, {side(beta, DESK['beta_alert'])} the desk's alert level "
            f"of {DESK['beta_alert']}, while the fund's own returns over the same "
            f"{BETA_DAYS} sessions show a beta of {h['realised_beta_252d']:.3f}",
        ),
        dict(
            id="volatility",
            level=against(h["realised_vol_63d_pct"], hard["vol"] * 100),
            measure=f"realised volatility, {VOL_DAYS} sessions, % a year",
            value=round(h["realised_vol_63d_pct"], 2),
            rule=f"{side(h['realised_vol_63d_pct'], hard['vol'] * 100)} the finals PDF "
            f"ceiling of {hard['vol'] * 100:.0f}%, and today's weights on past returns give "
            f"{h['vol_pct']:.2f}%",
        ),
        dict(
            id="liquidity",
            level=exit_level,
            measure=f"most sessions to exit one name at {liq['participation'] * 100:.0f}% "
            "of volume",
            value=round(liq["sessions_to_exit_max"], 2),
            rule=f"{side(liq['sessions_to_exit_max'], liq['sessions_limit'])} the fund's "
            f"limit of {liq['sessions_limit']} sessions, the largest holding is "
            f"{liq['days_of_volume_max']:.2f} days of volume",
        ),
        dict(
            id="crowd_exposure",
            level="watch" if cr["crowd_beta_t"] > DESK["crowd_t_watch"] else "ok",
            measure="return loading on the AI crowd factor",
            value=round(cr["crowd_beta"], 2),
            rule=f"small but measurable, its t statistic of {cr['crowd_beta_t']:.2f} is "
            f"{side(cr['crowd_beta_t'], DESK['crowd_t_watch'])} the desk's watch level of "
            f"{DESK['crowd_t_watch']:.0f}, longs sit at the crowd's "
            f"{D.nth(cr['long_percentile'])} percentile and shorts at the "
            f"{D.nth(cr['short_percentile'])}",
        ),
        dict(
            id="crowd_sell_off",
            level="ok" if loss < worst_month / 2 else "watch" if loss < worst_month else "alert",
            measure="loss if the AI crowd dumps its favourites, % of capital",
            value=round(cr["sell_off_worst_pct_nav"], 2),
            rule=f"worst of the tests ({cr['sell_off_worst_case']}), "
            f"{'less' if loss < worst_month / 2 else 'more'} than half the record's worst "
            f"month of minus {worst_month:.2f}%",
        ),
        dict(
            id="carbon_arc",
            level="info",
            measure="longs in Hype and shorts in Hidden gems on card spend, names",
            value=f"{ca['longs_in_hype']} and {ca['shorts_in_hidden_gems']}",
            rule=f"counts only, card spend of {ca['longs_with_growth']} longs grew "
            f"{ca['long_spend_growth_pct']:.2f}% and of {ca['shorts_with_growth']} shorts "
            f"{ca['short_spend_growth_pct']:.2f}%, {ca['crowd_favourites_in_hype']} of "
            f"{ca['crowd_favourites_with_growth']} crowd favourites in Hype, never a fund input",
        ),
    ]


# One flag as a plain sentence, written by code from its facts.
def says(x: dict, f: dict) -> str:
    v = x["value"]
    size = abs(v) if isinstance(v, (int, float)) else v
    lead = {
        "gross": f"Gross exposure is {v}% of capital",
        "net": f"Net exposure is {v}% of capital",
        "names": f"The book holds {v} names",
        "largest_long": f"The largest long, {f['largest_long']['ticker']}, is {v}% of capital",
        "largest_short": f"The largest short, {f['largest_short']['ticker']}, is {size}% of "
        "capital",
        "concentration": f"The ten largest longs are {v}% of the long side",
        "sector_net": f"The largest sector net, {f['sector_net_max']['sector']}, is {v}% of "
        "capital",
        "beta": f"Today's weights carry a beta of {v} to the S&P 500 over {BETA_DAYS} sessions",
        "volatility": f"Realised volatility over {VOL_DAYS} sessions is {v}% a year",
        "liquidity": f"The slowest name takes {v} sessions to exit at 10% of daily volume",
        "crowd_exposure": f"The fund's return loads {v} on the AI crowd factor",
        "crowd_sell_off": f"If the AI crowd dumped its favourites the book would lose {size}% "
        "of capital",
        "carbon_arc": f"On card spend {f['carbon_arc']['longs_in_hype']} longs sit in Hype and "
        f"{f['carbon_arc']['shorts_in_hidden_gems']} shorts in Hidden gems",
    }[x["id"]]
    return D.plain(f"{lead}, {x['rule']}.")


# The note as markdown: summary, then a table of the flags.
def markdown(out: dict) -> str:
    lines = ["# Risk note on the final book, 31 August 2026", "", out["summary"], ""]
    lines += ["| Level | Flag | Number | Reason |", "|---|---|---|---|"]
    for f in out["flags"]:
        lines.append(f"| {f['level']} | {f['measure']} | {f['value']} | {f['reason']} |")
    c = out["check"]
    lines += [
        "",
        f"Levels are set by code. {out['model']} wrote the words, and code dropped "
        f"{c['sentences_dropped']} {'sentence' if c['sentences_dropped'] == 1 else 'sentences'} "
        "whose numbers did not trace, put a number on the other side of a limit or gave "
        "advice. "
        "The desk only writes. It sets no weight and suggests no trade.",
    ]
    return "\n".join(lines)


# Writes risk_note.json and risk_note.md from the book and one call.
def run() -> dict:
    n = D.load(D.NUMBERS)
    f = book_facts()
    f["worst_month_pct"] = n["headline"]["max_one_month_loss_pct"]
    flagged = flags(f)
    for x in flagged:
        x["says"] = says(x, f)
    shown = dict(book_date=F.AS_OF, flags=flagged)
    source = json.dumps(shown, indent=1, default=str)
    words = "\n".join(f"{x['id']} ({x['level']}): {x['says']}" for x in flagged)
    values = D.shown(source)
    ids = [x["id"] for x in flagged]
    user = (
        "Write the risk note on the final book for an investment committee. summary, 2 or 3 "
        "plain sentences, the watch and alert flags first and what they mean together. "
        "reasons, one sentence per flag id in your own words, saying why that number matters "
        "or why it does not, using the number as printed in the READABLE block. Each READABLE "
        "line already says whether a number is above or below each limit; keep that and never "
        "reverse it. Never quote field names. Never advise a trade or a weight. Answer in JSON "
        "with the keys summary and reasons.\n\nREADABLE\n" + words + "\n\nFACTS\n" + source
    )
    with F.Asker(D.LOG, SYSTEM, schema(ids)) as asker:
        key = f"risk_note_2026-08-31_p{PROMPT_NUMBER}"
        got = D.ask_checked(asker, key, user, ["summary"], values)
        account = asker.accounting([], 0)
    answer = got["answer"]
    summary, dropped = D.check(str(answer.get("summary", "")), values, advice=True, sides=True)
    said = {r.get("id"): r.get("reason", "") for r in answer.get("reasons", [])}
    for x in flagged:
        kept, lost = D.check(said.get(x["id"], ""), values, advice=True, sides=True)
        dropped += [dict(flag=x["id"], **d) for d in lost]
        x["reason"] = kept or x["says"]
        x["reason_by"] = "model" if kept else "code, the model's words were dropped"
    levels = {k: sum(x["level"] == k for x in flagged) for k in ("alert", "watch", "ok", "info")}
    out = dict(
        what="The risk desk's note on the final book. Code computed every number and set every "
        "level. A local model wrote the summary and reasons, and code kept a sentence only if "
        "its numbers trace to the facts and it gives no trade or weight advice. The desk "
        "never changes or suggests a weight.",
        as_of=F.AS_OF,
        model=f"Gemma 4 26B ({account['model_file']})",
        settings=dict(temperature=account["temperature"], seed=account["seed"]),
        calls_log=str(D.LOG),
        calls=got["calls"],
        prompt_number=PROMPT_NUMBER,
        earlier_prompts_note="prompt 1 gave each rule without saying above or below, and its "
        "answer called a 1.75% sector net within a 1% band. Prompt 2 parroted field names and "
        "set a 0.09 loading above a t level of 2. Both stay in the log, unused",
        summary=summary or "No summary sentence passed the checks.",
        levels=levels,
        flags=flagged,
        desk_thresholds=DESK,
        check=dict(sentences_dropped=len(dropped), dropped=dropped),
        facts=f,
    )
    D.write_json(D.DESK / "risk_note.json", out)
    D.write_text(D.DESK / "risk_note.md", markdown(out))
    print(f"risk note: {levels}, {len(dropped)} sentences dropped", flush=True)
    return out
