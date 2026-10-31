# Where the final fund sits in the AI crowd, Jan 2021 to Aug 2026.

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.agents import crowd_lab as L
from fiam.agents import crowd_study as X
from fiam.agents import final_book as F
from fiam.agents import harness as H

# The saved crowd logs the August run extends, read and never written.
SAVED_LOGS = H.RUNS
# August's logs, which hold licensed values: gitignored, never in git.
RUNS = Path(os.environ.get("FIAM_CROWD_RUNS", str(H.ROOT / "cache" / "agents" / "crowd_aug")))
OUT = F.PACK / "crowd_aug" / "crowd_where_we_sit.json"
# The crowd model's saved scores and the saved live consensus.
SAVED = H.ROOT / "out" / "research"
# The book's run folder; FIAM_VFINAL_OUT moves it, as for the engine.
BOOK = Path(os.environ.get("FIAM_VFINAL_OUT", str(H.ROOT / "out" / "vfinal"))) / "bw_fresh_lag"
CROWDS = ("retail", "copycat")
MONTH = "2026-08-31"
LIVE_FROM = pd.Timestamp("2025-01-31")
FINAL = pd.Timestamp(MONTH)
WHAT = (
    "Where the final fund sits in the AI crowd, month ends 2021-01 to 2026-08, final "
    "book (2026-08-31) included. 2021 to 2024 is the crowd model (a frozen ridge of "
    "the AI crowd's consensus on the 147 characteristics, no AI calls). 2025 to 2026 "
    "is the live AI crowd (Gemma 4 26B, 30 retail and 30 copycat agents, 9 cards of 40 "
    "anonymous stocks a month each). Percentiles are within that month's screened "
    "universe; chance is 0.5 for the mean, 0.1 for each decile share and 0.5 for the "
    "share above random books. Weights are shares of each leg's gross."
)
FLOOR_NOTE = (
    "The live retail crowd gives about half the names the same lowest vote (no "
    "pick), so its lowest in-month percentile sits far above 0.1 and a bottom "
    "decile does not exist. Bottom decile shares are left empty in any month where "
    "that happens, and averages skip those months."
)
RUN_NOTE = (
    "August 2026 was asked on the PC's Gemma with 4 parallel slots, temperature 0 "
    "and seed 42. Batched requests are not bit-repeatable. In a replay check of 7 "
    "August cards the picks were identical on 3 or 4 of 7, so August's live "
    "numbers carry that answer noise. Months before August are the saved answers."
)


# Copies the saved crowd log once, so the resume skips its months.
def seed_log(log: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    target = RUNS / f"{log}.jsonl"
    if not target.exists():
        shutil.copy2(SAVED_LOGS / f"{log}.jsonl", target)
        before = RUNS / f"{log}.manifest_before.json"
        shutil.copy2(SAVED_LOGS / f"{log}.manifest.json", before)


# The cards a resume would ask, each as (agent, month, card).
def pending(log: str, agents: list[dict]) -> list[tuple]:
    frame = L.universe()
    saved = [json.loads(x) for x in (RUNS / f"{log}.jsonl").read_text("utf-8").splitlines()]
    done = {(r["agent"], r["eom"], r["card"]) for r in saved}
    out = []
    for month in sorted(frame["eom"].unique()):
        rows = frame[frame["eom"] == month]
        for agent in agents:
            for number, _ in enumerate(L.cards(rows, agent["seed"], month)):
                if (agent["id"], f"{month:%Y-%m-%d}", number) not in done:
                    out.append((agent["id"], f"{month:%Y-%m-%d}", number))
    return out


# Asks one crowd for August 2026 by the lab's loop, every call logged.
def ask(crowd: str) -> None:
    log = f"crowdlab_{crowd}"
    agents = L.retail_agents() if crowd == "retail" else L.copycat_agents()
    H.RUNS = RUNS
    seed_log(log)
    todo = pending(log, agents)
    months = sorted({m for _, m, _ in todo})
    print(f"{log}: {len(todo)} cards to ask, months {months}", flush=True)
    if months and months != [MONTH]:
        raise SystemExit(f"resume would ask other months: {months}")
    calls = (RUNS / f"calls_{crowd}.jsonl").open("a", encoding="utf-8", newline="\n")
    where = {}
    chat, lab_ask = H.Server.chat, L.ask

    # Notes which agent and card the next call answers.
    def logged_ask(server, agent, card, number, month, names):
        where.update(agent=agent["id"], eom=f"{month:%Y-%m-%d}", card=number)
        return lab_ask(server, agent, card, number, month, names)

    # Keeps the full prompt, schema and raw reply of each call.
    def logged_chat(self, messages, tools=None, schema=None, **kw):
        start = time.time()
        reply = chat(self, messages, tools=tools, schema=schema, **kw)
        row = dict(crowd=crowd, **where, messages=messages, schema=schema, reply=reply)
        row |= dict(seconds=round(time.time() - start, 2), url=self.url)
        calls.write(json.dumps(row) + "\n")
        calls.flush()
        return reply

    L.ask, H.Server.chat = logged_ask, logged_chat
    try:
        L.run_crowd(log, agents)
    finally:
        L.ask, H.Server.chat = lab_ask, chat
        calls.close()
    print(f"{log}: {len(pending(log, agents))} cards left after the run", flush=True)


# Crowd-model score and percentile for every screened stock-month.
def scores() -> pd.DataFrame:
    frame = X.ranks(first="2020-12-31", last=MONTH)
    out = frame[["permno", "eom", "ret_exc_lead1m", "vol_raw", "dolvol_raw"]].copy()
    out["crowd_score"] = X.crowd_score(frame)
    out["pct"] = out.groupby("eom")["crowd_score"].rank(pct=True)
    return out


# Live crowd picks from the August logs, all months included.
def live_picks(runs: Path = RUNS) -> dict:
    saved, H.RUNS = H.RUNS, runs
    try:
        return {c: L.picks(f"crowdlab_{c}") for c in CROWDS}
    finally:
        H.RUNS = saved


# Live consensus per stock-month, as score and in-month percentile.
def live_scores(picks: dict) -> dict:
    out = {}
    for crowd, p in picks.items():
        c = X.consensus(p)
        c["crowd_score"] = c["consensus"]
        c["pct"] = c.groupby("eom")["consensus"].rank(pct=True)
        out[crowd] = c
    return out


# Daily dollar positions and NAV.
def book(folder: Path = BOOK):
    p = pd.read_parquet(folder / "positions.parquet")
    p["date"] = pd.to_datetime(p["date"])
    v = p.pivot(index="date", columns="permno", values="value").fillna(0.0)
    nav = pd.read_parquet(folder / "daily.parquet")["nav"].reindex(v.index)
    return v, nav


# The book on each month's last session, as weights of NAV.
def month_ends(v: pd.DataFrame, nav: pd.Series) -> dict:
    last = v.groupby(v.index.to_period("M")).tail(1)
    out = {}
    for day, row in last.iterrows():
        w = (row / nav.loc[day]).loc[lambda s: s != 0]
        out[(day + pd.offsets.MonthEnd(0)).normalize()] = w
    return out


# Weighted mean, ignoring names the crowd did not score.
def wmean(x: pd.Series, wt: pd.Series) -> float:
    ok = x.notna()
    return float((x[ok] * wt[ok]).sum() / wt[ok].sum()) if ok.any() else np.nan


# Long and short weight against the crowd that month, one snapshot.
def snapshot(w: pd.Series, month: pd.DataFrame) -> dict:
    pct = month.set_index("permno")["pct"].reindex(w.index)
    long, short = w[w > 0], -w[w < 0]
    lp, sp = pct[w > 0], pct[w < 0]
    seen_l, seen_s = long[lp.notna()], short[sp.notna()]
    return dict(
        longs=int(len(long)),
        shorts=int(len(short)),
        unscored=int(pct.isna().sum()),
        long_mean_pct=wmean(lp, long),
        short_mean_pct=wmean(sp, short),
        long_in_top_decile=float(seen_l[lp.dropna() >= 0.9].sum() / seen_l.sum()),
        long_in_bottom_decile=float(seen_l[lp.dropna() <= 0.1].sum() / seen_l.sum()),
        short_in_top_decile=float(seen_s[sp.dropna() >= 0.9].sum() / seen_s.sum()),
        short_in_bottom_decile=float(seen_s[sp.dropna() <= 0.1].sum() / seen_s.sum()),
    )


# Share of random books whose long-short crowd score is below ours.
def above_random(w: pd.Series, month: pd.DataFrame, rng, draws: int = 500) -> float:
    s = month.set_index("permno")["crowd_score"]
    x = s.reindex(w.index).fillna(s.mean())
    ours = x[w > 0].mean() - x[w < 0].mean()
    vals = s.to_numpy()
    nl, ns = int((w > 0).sum()), int((w < 0).sum())
    fake = [rng.choice(vals, nl).mean() - rng.choice(vals, ns).mean() for _ in range(draws)]
    return float((np.array(fake) < ours).mean())


# One crowd's snapshots and random-book shares over a set of months.
def measure(months: dict, scored: pd.DataFrame, keep) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    snaps, idx = {}, {}
    for eom, w in months.items():
        month = scored[scored["eom"] == eom]
        if not keep(eom) or month.empty:
            continue
        snaps[f"{eom:%Y-%m}"] = snapshot(w, month)
        idx[f"{eom:%Y-%m}"] = above_random(w, month, rng)
    s = pd.DataFrame(snaps).T
    s["above_random"] = pd.Series(idx)
    return s


# Averages, by year and the final book for one monthly table.
def summary(s: pd.DataFrame) -> dict:
    return dict(
        months=len(s),
        first=s.index.min(),
        last=s.index.max(),
        average=s.mean().to_dict(),
        by_year=s.groupby(s.index.str[:4]).mean().to_dict(orient="index"),
        final_book_2026_08=s.loc["2026-08"].to_dict() if "2026-08" in s.index else None,
    )


# Live crowd against the crowd model: monthly Spearman of the scores.
def agreement_with_model(live: pd.DataFrame, sc: pd.DataFrame) -> dict:
    both = sc[["permno", "eom", "crowd_score"]].merge(
        live[["permno", "eom", "consensus"]], on=["permno", "eom"]
    )
    rho = both.groupby("eom")[["crowd_score", "consensus"]].apply(
        lambda g: g.corr(method="spearman").iloc[0, 1]
    )
    return dict(
        spearman_mean=float(rho.mean()),
        spearman_2026_08=float(rho.get(FINAL, np.nan)),
        months=int(rho.notna().sum()),
        names_2026_08=int((both["eom"] == FINAL).sum()),
    )


# Herding on the live logs: all months, before August, and August.
def herding(picks: pd.DataFrame) -> dict:
    out = {}
    parts = (
        ("all_months", picks),
        ("to_2026_07", picks[picks["eom"] < FINAL]),
        ("2026_08", picks[picks["eom"] == FINAL]),
    )
    for label, p in parts:
        h, a = X.lsv(p), X.agreement(p)
        out[label] = dict(
            effective_voters=a["effective_voters"],
            mean_correlation=a["mean_correlation"],
            agents=a["agents"],
            lsv=h["lsv"],
            lsv_t=h["lsv_t"],
            cells=h["cells"],
        )
    return out


# The share of NAV a crowd sell-off of its top decile costs the book.
def sell_offs(w: pd.Series, month: pd.DataFrame, nav: float) -> dict:
    return {f"{b / 1e9:.0f}bn": X.sell_off(w * nav, month, b) / nav for b in X.CROWD_SIZES}


# A whole number with its English ordinal ending, 57 to 57th.
def nth(n: int) -> str:
    end = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{end}"


# Months where ties at the lowest vote leave no bottom decile.
def floors(live: dict, tabs: dict) -> dict:
    out = {}
    for c in live:
        low = live[c].groupby("eom")["consensus"].transform("min")
        tied = (live[c]["consensus"] == low).groupby(live[c]["eom"]).mean()
        lowest = live[c].groupby("eom")["pct"].min()
        none = [f"{e:%Y-%m}" for e in lowest.index[lowest > 0.1] if f"{e:%Y-%m}" in tabs[c].index]
        out[c] = dict(
            share_of_names_at_lowest_vote_mean=float(tied.mean()),
            lowest_percentile_mean=float(lowest.mean()),
            months_without_bottom_decile=len(none),
        )
        tabs[c].loc[none, ["long_in_bottom_decile", "short_in_bottom_decile"]] = np.nan
    return out


# The slide's rounded numbers, its fact-sheet line and its headline.
def headline(sp: dict, beta: dict, sell: dict, retail: dict) -> dict:
    fb = sp["final_book_2026_08"]
    r = dict(
        long_pct=round(fb["long_mean_pct"] * 100),
        short_pct=round(fb["short_mean_pct"] * 100),
        avg_long_pct=round(sp["average"]["long_mean_pct"] * 100),
        avg_short_pct=round(sp["average"]["short_mean_pct"] * 100),
        beta=round(beta["beta"], 2),
        sell_10bn_pct=round(sell["crowd_model"]["10bn"] * 100, 2),
        voters=round(retail["effective_voters"], 1),
        lsv=round(retail["lsv"], 3),
    )
    fact = f"Our longs sit at the AI crowd's {nth(r['long_pct'])} percentile, "
    fact += f"crowd beta {r['beta']}"
    head = (
        f"Our longs average the AI crowd's {nth(r['avg_long_pct'])} percentile and shorts the "
        f"{nth(r['avg_short_pct'])}, yet crowd beta is only {r['beta']}"
    )
    assert len(fact) <= 76 and len(head) <= 120
    assert not any(ch in fact + head for ch in ":;–—")
    return dict(round=r, fund_fact_line=fact, headline=head)


# Everything for the slide and fact sheet, as one dict.
def study(runs: Path = RUNS) -> tuple[dict, pd.DataFrame]:
    sc = scores()
    old = pd.read_parquet(SAVED / "crowd_scores.parquet")
    chk = sc.merge(old, on=["permno", "eom"], suffixes=("", "_old"))
    picks = live_picks(runs)
    live = live_scores(picks)
    cons_old = pd.read_parquet(SAVED / "crowd_consensus.parquet")
    v, nav = book()
    months = month_ends(v, nav)
    model_all = measure(months, sc, lambda e: e >= pd.Timestamp("2021-01-31"))
    model_early = measure(months, sc, lambda e: pd.Timestamp("2021-01-31") <= e < LIVE_FROM)
    live_tabs = {c: measure(months, live[c], lambda e: e >= LIVE_FROM) for c in live}
    floor = floors(live, live_tabs)
    spliced = {c: pd.concat([model_early, live_tabs[c]]) for c in live}
    # Crowd factor from the model and the book's beta to it, monthly.
    factor = X.crowd_factor(sc)
    rets = pd.read_csv(BOOK / "returns_monthly.csv")
    rets.index = pd.PeriodIndex(rets["month"], freq="M").to_timestamp()
    beta = X.crowding_beta(rets["return"], factor)
    # Sell-off on the final book, from the model's and the live top decile.
    last = v.index.max()
    w_final = months[FINAL]
    final_month = sc[sc["eom"] == FINAL]
    sell = dict(crowd_model=sell_offs(w_final, final_month, float(nav.loc[last])))
    for c in live:
        lm = live[c][live[c]["eom"] == FINAL].merge(
            final_month[["permno", "vol_raw", "dolvol_raw"]], on="permno"
        )
        sell[f"live_{c}"] = sell_offs(w_final, lm, float(nav.loc[last]))
    # Saved consensus for the months before August must match the logs.
    match = {}
    for c in live:
        a = cons_old[cons_old["crowd"] == c].merge(live[c], on=["eom", "permno"], how="outer")
        a = a[a["eom"] < FINAL]
        match[c] = float((a["consensus_x"] - a["consensus_y"]).abs().max())
    aug = {c: live[c][live[c]["eom"] == FINAL] for c in live}
    sp = summary(spliced["retail"])
    checks = dict(
        crowd_model_recompute_max_abs_diff_vs_saved=float(
            (chk["crowd_score"] - chk["crowd_score_old"]).abs().max()
        ),
        crowd_model_rows_compared=len(chk),
        crowd_model_names_2026_08=int((sc["eom"] == FINAL).sum()),
        live_consensus_max_abs_diff_vs_saved_before_2026_08=match,
        live_answers={c: int(p.groupby(["agent", "eom"]).ngroups) for c, p in picks.items()},
        live_cards_2026_08={
            c: int(p[p["eom"] == FINAL].groupby(["agent", "eom"]).size().sum() // L.STOCKS)
            for c, p in picks.items()
        },
        live_names_scored_2026_08={c: len(a) for c, a in aug.items()},
    )
    manifests = {c: json.loads((runs / f"crowdlab_{c}.manifest.json").read_text()) for c in live}
    out = dict(
        what=WHAT,
        segments=dict(
            crowd_model="2021-01 to 2024-12 (48 month ends)",
            live_crowd="2025-01 to 2026-08 (20 month ends), August 2026 asked live",
        ),
        checks=checks,
        live_bottom_decile=dict(note=FLOOR_NOTE, **floor),
        live_run=dict(
            manifests=manifests,
            calls_logs=[f"calls_{c}.jsonl" for c in CROWDS],
            note=RUN_NOTE,
        ),
        spliced_retail=sp,
        spliced_copycat=summary(spliced["copycat"]),
        crowd_model_2021_2026=summary(model_all),
        crowd_model_2021_2024=summary(model_early),
        live_retail_2025_2026=summary(live_tabs["retail"]),
        live_copycat_2025_2026=summary(live_tabs["copycat"]),
        crowd_factor_beta=beta,
        crowd_factor_months=dict(first=str(factor.index.min()), last=str(factor.index.max())),
        crowd_factor_note="Top minus bottom decile of the crowd model, equal weight, monthly.",
        sell_off_final_book_share_of_nav=sell,
        sell_off_note="The crowd sells its top decile over 5 days, square-root impact.",
        live_agreement_with_crowd_model={c: agreement_with_model(live[c], sc) for c in live},
        herding={c: herding(p) for c, p in picks.items()},
    )
    out |= headline(sp, beta, sell, out["herding"]["retail"]["all_months"])
    # The small table: one row a month, the spliced retail series.
    tab = spliced["retail"].copy()
    tab.insert(0, "source", ["crowd_model" if k < "2025" else "live_retail" for k in tab.index])
    tab.index.name = "month"
    return out, tab


# Writes the record and, beside the logs, its monthly table.
def write(path: Path = OUT, runs: Path = RUNS) -> dict:
    out, tab = study(runs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    tab.to_csv(runs / "crowd_where_we_sit.csv", float_format="%.4f")
    print(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    # uv run python -m fiam.agents.crowd_aug ask retail|copycat, or study
    step, *rest = sys.argv[1:] or [""]
    if step == "ask" and rest and rest[0] in CROWDS:
        ask(rest[0])
    elif step == "study":
        write()
    else:
        sys.exit("usage: python -m fiam.agents.crowd_aug ask retail|copycat | study")
