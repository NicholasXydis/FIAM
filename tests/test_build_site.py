# The site's data builder on small synthetic pack files.

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import build_site as b

# The table's cells the tests read, in the formats the pack writes.
CELLS = {
    3: ("Annualised return (%)", "arithmetic 6.86, CAGR 7.00", "arithmetic 7.27, CAGR 7.52"),
    5: ("Alpha vs S&P 500 (%, s.e.)", "3.46 (1.41)", "n/a"),
    6: ("Beta monthly (s.e.)", "0.012 (0.030)", "n/a"),
    9: ("IR vs T-bill + 4%, before costs", "0.0031", "n/a"),
    14: ("Positions held", "avg 314.2, min 246, max 357", "n/a"),
    17: ("One-way turnover (%)", "with build 94, without 92; all trade days 95", "n/a"),
    21: ("Trading cost (% NAV a year)", "0.136215", "n/a"),
    22: ("Borrow cost (% NAV a year)", "0.287569", "n/a"),
}


# The table as the builder reads it, keyed by row number.
def table() -> dict[int, dict]:
    return {n: dict(row=n, name=a, strategy=s, benchmark=bm) for n, (a, s, bm) in CELLS.items()}


# Every trading day from the endowment close to the end of March 2022.
def daily_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp("2020-12-31")]).append(
        pd.bdate_range("2021-01-04", "2022-03-31")
    )
    i = np.arange(len(index))
    ret = np.where(i == 0, 0.0, 0.002 * np.sin(i))
    return pd.DataFrame(
        {"nav": 1e9 * np.cumprod(1 + ret), "ret": ret, "rf": 0.0001},
        index=pd.Index(index, name="date"),
    )


# A monthly bill of 3% a year for every month of the run.
def bills() -> pd.Series:
    months = pd.period_range("2020-12", "2022-04", freq="M")
    return pd.Series(0.03 / 12, index=months)


# Each cell gives the numbers the site reads, and only those.
def test_cells_parse():
    assert b.numbers(CELLS[17][1]) == [94.0, 92.0, 95.0]
    assert b.with_se(CELLS[5][1]) == (3.46, 1.41)
    assert b.with_se(CELLS[6][1]) == (0.012, 0.030)
    assert b.labelled(CELLS[3][1], "CAGR") == 7.00
    assert b.labelled(CELLS[3][1], "arithmetic") == 6.86
    assert b.labelled(CELLS[3][2], "arithmetic") == 7.27
    assert b.labelled(CELLS[14][1], "avg") == 314.2
    assert b.labelled(CELLS[17][1], "build") == 94.0


# Cells with no such number raise rather than guess.
def test_cells_refuse_what_is_not_there():
    with pytest.raises(ValueError):
        b.with_se("3.46")
    with pytest.raises(ValueError):
        b.labelled("avg 314.2", "CAGR")


# A rebuilt number that strays from the pack's stops the build.
def test_agree_stops_on_a_gap():
    b.agree("close", 0.0700, 0.0702)
    with pytest.raises(SystemExit, match="far"):
        b.agree("far", 0.07, 0.08)


# The hurdle is the month's bill plus 4% / 12; a missing bill stops.
def test_hurdle_is_the_bill_plus_four():
    m = b.fund_months(daily_frame(), bills())
    assert str(m.index[0]) == "2021-01" and len(m) == 15
    assert m["hurdle"].to_numpy() == pytest.approx(0.03 / 12 + 0.04 / 12)
    with pytest.raises(SystemExit, match="TB3MS"):
        b.fund_months(daily_frame(), bills().iloc[:5])


# The race compounds each series month by month from $1.
def test_race_compounds_each_month():
    daily = daily_frame()
    m = b.fund_months(daily, bills())
    market = pd.Series(0.01, index=m.index)
    race = b.race(m, market)
    assert len(race["book"]) == len(m) + 1 and race["book"][0] == 1.0
    assert race["book"][-1] == pytest.approx(daily["nav"].iloc[-1] / 1e9, abs=1e-4)
    assert race["hurdle"][-1] == pytest.approx((1 + m["hurdle"]).prod(), abs=1e-4)
    assert race["market"][-1] == pytest.approx(1.01**15, abs=1e-4)


# Each year compounds its months; active is fund less hurdle.
def test_years_compound_and_count_months():
    m = b.fund_months(daily_frame(), bills())
    got = b.years(m, pd.Series(0.01, index=m.index))
    assert got["2022"]["months"] == 3 and got["2021"]["months"] == 12
    year = got["2021"]
    assert year["active"] == pytest.approx(year["strategy"] - year["benchmark"], abs=2e-4)
    assert year["market"] == pytest.approx(1.01**12 - 1, abs=1e-4)


# Costs are rows 21 and 22, with cash and the break-even multiple.
def test_costs_from_rows_21_and_22():
    c = b.costs(table())
    assert c["parts"] == dict(trading=0.00136, borrow=0.00288)
    assert c["total"] == pytest.approx(0.00136215 + 0.00287569, abs=1e-5)
    assert (c["net"], c["hurdle"]) == (0.0686, 0.0727)
    assert c["gross"] == pytest.approx(c["net"] + c["total"], abs=1e-5)
    assert c["cash"] == pytest.approx(0.0727 - 0.04, abs=1e-5)
    even = (c["gross"] - c["hurdle"]) / c["total"]
    assert c["break_even"] == pytest.approx(even, abs=2e-3)
    assert c["turnover"] == 0.94 and c["ir_gross"] == 0.003


# Months up, the worst 12 months and the captures, checked to the pack.
def test_monthly_measures():
    index = pd.period_range("2021-01", periods=24, freq="M")
    ret = pd.Series(np.where(np.arange(24) % 4 == 0, -0.01, 0.01), index=index)
    market = pd.Series(np.where(np.arange(24) % 2 == 0, -0.02, 0.03), index=index)
    m = pd.DataFrame({"ret": ret})
    pack = dict(
        hit_rate=dict(monthly_hit_rate_pct=75.0, months=24),
        headline=dict(max_one_month_loss_pct=-1.0),
    )
    got = b.monthly(pack, m, market)
    assert got["months_up"] == 18
    assert got["worst_12"]["value"] == pytest.approx(1.01**9 * 0.99**3 - 1, abs=1e-4)
    down = ret[market < 0].mean() / market[market < 0].mean()
    up = ret[market > 0].mean() / market[market > 0].mean()
    assert (got["down_capture"], got["up_capture"]) == (round(down, 3), round(up, 3))
    pack["hit_rate"]["monthly_hit_rate_pct"] = 50.0
    with pytest.raises(SystemExit, match="months up"):
        b.monthly(pack, m, market)


# Holdings are each month's last date, named from the Arcana file.
def test_holdings_last_date_and_tickers(tmp_path):
    arcana = tmp_path / "own.csv"
    pd.DataFrame(
        dict(
            Date=["2021-01-04", "2021-06-01", "2021-01-04", "2021-01-04"],
            Ticker=["OLD US Equity", "NEW US Equity", "BRK/A US Equity", ""],
            PERMNO=[1, 1, 2, 3],
            Name=["Old Name Inc", "NEW NAME INC", "BERKSHIRE HATHAWAY INC", ""],
        )
    ).to_csv(arcana, index=False)
    known = b.names(arcana)
    assert known[1] == ("NEW", "NEW NAME INC") and known[3] == ("", "")
    daily = daily_frame()
    last = daily.index[daily.index <= "2021-01-31"][-1]
    mid = daily.index[10]
    positions = pd.DataFrame(
        [(mid, 1, 1e6), (last, 1, 2e7), (last, 2, -1e7), (last, 3, 5e6), (last, 4, 0.0)],
        columns=["date", "permno", "value"],
    )
    s = b.holdings(positions, daily["nav"], known, ["2021-01"])
    assert s["ticker"] == ["NEW", "BRK/A", ""]
    assert s["name"] == ["New Name Inc", "Berkshire Hathaway Inc", ""]
    nav = daily["nav"][last]
    assert s["book"] == [
        [0, round(2e7 / nav * 1e5), 1, round(-1e7 / nav * 1e5), 2, round(5e6 / nav * 1e5)]
    ]


# The rolling beta waits for a full window; months before show so far.
def test_beta_block_fills_the_early_months():
    daily = daily_frame()
    market = pd.Series(0.003 * np.cos(np.arange(len(daily)) * 0.7), index=daily.index)
    got = b.beta_block(daily, market)
    rolling, since = got["rolling"], got["since"]
    assert rolling and min(rolling) >= "2021-12"
    assert all(band > 0 for _, band in rolling.values())
    assert since and min(since) == "2021-01" and max(since) < min(rolling)


# The inputs are the organisers' sets and our three signals by name.
def test_signals_are_sets_and_ours(tmp_path):
    folder = tmp_path / "plus"
    folder.mkdir(parents=True)
    theirs = [f"c{i:03d}" for i in range(20)]
    cols = [*b.KEYS, *theirs, *b.OURS]
    pd.DataFrame(columns=cols, dtype=float).to_parquet(folder / "features.parquet")
    got, families = b.signals(tmp_path)
    assert sum(s["count"] for s in got) == 23
    assert [s["code"] for s in got if s["family"] == "ours"] == list(b.OURS)
    assert len([s for s in got if s["family"] == "theirs"]) == b.BUNDLES
    assert families["theirs"] == "The organisers' 20 characteristics"
    pd.DataFrame(columns=[*b.KEYS, *theirs], dtype=float).to_parquet(folder / "features.parquet")
    with pytest.raises(SystemExit, match="three signals"):
        b.signals(tmp_path)


# Writes a JSON file, making its folder first.
def put(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# A small AI folder: each agent's own output and the findings file.
def write_ai(ai: Path, rules_matched: int = 13) -> None:
    sources = {
        "rules": put(ai / "rules" / "rules_check.json", dict(matched=13, rules_read=15, m="Gemma")),
        "analyst": put(
            ai / "analyst" / "analyst_final.json",
            dict(
                balance_by_side=dict(
                    long=dict(supports=7, mixed=3, challenges=0),
                    short=dict(supports=1, mixed=9, challenges=0),
                ),
                model="gemma",
            ),
        ),
        "explainer": put(ai / "explanations.json", dict(positions=[{}] * 40)),
        "advocate": put(
            ai / "desk" / "critic_final.json",
            dict(verdicts={"stands": 3, "partly stands": 4, "does not stand": 2}, model="Gemma"),
        ),
        "desk": put(ai / "desk" / "risk_note.json", dict(levels=dict(watch=5), model="Gemma")),
        "crowd": put(
            ai / "crowd_aug" / "crowd_where_we_sit.json",
            dict(
                round=dict(beta=0.09, long_pct=57, short_pct=51),
                live_run=dict(
                    manifests=dict(
                        retail=dict(model_file="gemma-4-26B-A4B-it-UD-IQ4_XS.gguf"),
                        copycat=dict(model_file="gemma-4-26B-A4B-it-UD-IQ4_XS.gguf"),
                    )
                ),
            ),
        ),
        "triage": put(
            ai / "triage" / "triage_final.json",
            dict(filings=dict(labelled=991), share_for_our_side=0.4394, model="gemma"),
        ),
        "memo": put(ai / "desk" / "letter.json", dict(model="Gemma")),
    }
    numbers = {
        "rules": f"{rules_matched} of 15",
        "analyst": "8 of 20",
        "explainer": "40 positions",
        "advocate": "7 of 9",
        "desk": "5 watch",
        "crowd": "crowd beta 0.09",
        "memo": "IR -0.11",
        "triage": "991 8-Ks",
    }
    findings = {
        "triage": "Labelled 991 8-Ks and 44% of the non-neutral news favoured our side",
        "crowd": "On the final book our longs sit at the AI crowd's 57th percentile "
        "and shorts at the 51st, crowd beta 0.09",
    }
    found = {}
    for key, path in sources.items():
        found[b.AGENT_NAMES[key]] = dict(
            finding=findings.get(key, f"{key} found something"),
            key_number=numbers[key],
            date="2026-10-29",
            source=str(path),
        )
    put(ai / "agents_found.json", dict(agents_count=8, agents=found, pending=[]))


# The slide's eight agents as the base file holds them.
def base_agents() -> list[dict]:
    return [
        dict(
            key=k, name=n, model="old", does="does", facts=[["Tested against", "100 random desks"]]
        )
        for k, n in b.AGENT_NAMES.items()
    ]


# Each agent gets its finding, and its old facts go.
def test_agents_take_their_findings(tmp_path):
    write_ai(tmp_path)
    got = {a["key"]: a for a in b.agents(base_agents(), tmp_path)}
    assert len(got) == 8
    assert got["rules"]["finding"] == "rules found something"
    assert (got["rules"]["number"], got["rules"]["date"]) == ("13 of 15", "2026-10-29")
    assert got["triage"]["number"] == "991 8-Ks"
    assert got["memo"]["does"] == b.DOES["memo"] and got["memo"]["model"] == b.MODELS["gemma"]
    assert all("facts" not in a for a in got.values())
    assert got["crowd"]["model"] == b.MODELS["gemma"]
    assert got["triage"]["does"] == b.DOES["triage"]


# An older fact kept beside a finding needs a file that backs it.
def test_unbacked_standing_facts_stop_the_build(tmp_path, monkeypatch):
    write_ai(tmp_path)
    monkeypatch.setattr(b, "STANDING", {"desk": "desk/desk_test.json"})
    with pytest.raises(SystemExit, match="no backing file"):
        b.agents(base_agents(), tmp_path)
    put(tmp_path / "desk" / "desk_test.json", dict(random=100))
    got = {a["key"]: a for a in b.agents(base_agents(), tmp_path)}
    assert "facts" in got["desk"] and "facts" not in got["rules"]


# The crowd's model comes from its run manifests; an unknown one stops.
def test_crowd_model_from_its_manifests(tmp_path):
    write_ai(tmp_path)
    assert b.crowd_models(tmp_path) == b.MODELS["gemma"]
    path = tmp_path / "crowd_aug" / "crowd_where_we_sit.json"
    study = json.loads(path.read_text())
    study["live_run"]["manifests"]["copycat"]["model_file"] = "Qwen3.8-27B.gguf"
    put(path, study)
    with pytest.raises(SystemExit, match="cannot name"):
        b.crowd_models(tmp_path)


# Any count but eight agents, or other names, stops the build.
def test_agents_must_be_eight(tmp_path):
    write_ai(tmp_path)
    with pytest.raises(SystemExit, match="exactly 8"):
        b.agents(base_agents()[:7], tmp_path)
    path = tmp_path / "agents_found.json"
    file = json.loads(path.read_text())
    file["agents_count"] = 9
    put(path, file)
    with pytest.raises(SystemExit, match="exactly 8"):
        b.agents(base_agents(), tmp_path)


# A finding still pending stops the build; all eight must be filled.
def test_a_pending_finding_stops_the_build(tmp_path):
    write_ai(tmp_path)
    path = tmp_path / "agents_found.json"
    file = json.loads(path.read_text())
    file["agents"]["Triage"] = "pending"
    put(path, file)
    with pytest.raises(SystemExit, match="pending"):
        b.agents(base_agents(), tmp_path)


# Triage's share or the crowd's percentile drifting stops the build.
def test_findings_words_checked_against_their_files(tmp_path):
    write_ai(tmp_path)
    put(
        tmp_path / "triage" / "triage_final.json",
        dict(filings=dict(labelled=991), share_for_our_side=0.47),
    )
    with pytest.raises(SystemExit, match="Triage.*47%"):
        b.agents(base_agents(), tmp_path)
    write_ai(tmp_path / "two")
    put(
        tmp_path / "two" / "crowd_aug" / "crowd_where_we_sit.json",
        dict(round=dict(beta=0.09, long_pct=58, short_pct=51)),
    )
    with pytest.raises(SystemExit, match="AI crowd.*58th"):
        b.agents(base_agents(), tmp_path / "two")


# Ordinals read as English writes them.
def test_ordinals():
    assert [b.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 51, 57, 112)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "51st",
        "57th",
        "112th",
    ]


# A key number its own file does not back stops the build.
def test_findings_checked_against_their_files(tmp_path):
    write_ai(tmp_path, rules_matched=14)
    with pytest.raises(SystemExit, match="Rules reader"):
        b.agents(base_agents(), tmp_path)


# The crowd drops its stale numbers and takes the study's rounded ones.
def test_crowd_takes_the_rounded_study(tmp_path):
    study = dict(
        herding=dict(retail=dict(all_months=dict(agents=30))),
        round=dict(
            avg_long_pct=66, avg_short_pct=56, beta=0.09, voters=3.9, lsv=0.054, sell_10bn_pct=-0.11
        ),
        spliced_retail=dict(average=dict(long_in_top_decile=0.2577)),
    )
    path = put(tmp_path / "crowd.json", study)
    base = dict(agents=30, copycats=30, personas=[], picks=265590, crowd_beta=0.299, correlation=1)
    got = b.crowd(base, path)
    assert not set(b.STALE) & set(got)
    assert (got["long_pct"], got["short_pct"], got["beta"]) == (66, 56, 0.09)
    assert (got["effective_voters"], got["lsv"], got["sell_10bn_pct"]) == (3.9, 0.054, -0.11)
    assert got["favourites_pct"] == 26
    with pytest.raises(SystemExit, match="crowd count"):
        b.crowd(base | dict(agents=20), path)


# The hype check keeps totals only, never a ticker or a name's figure.
def test_hype_keeps_totals_only(tmp_path):
    card = dict(
        longs_vs_shorts=dict(longs=31, shorts=60, long_wmean=0.0538, short_wmean=0.0545),
        crowd_favourites=dict(favourites_with_growth=37, in_hype=10),
        flags=[dict(ticker="ABCD", growth=0.1)],
    )
    got = b.hype(put(tmp_path / "results.json", dict(card=card)))
    assert got == dict(
        long_growth=0.0538, short_growth=0.0545, longs=31, shorts=60, favourites=37, in_hype=10
    )
    assert "ABCD" not in json.dumps(got)
