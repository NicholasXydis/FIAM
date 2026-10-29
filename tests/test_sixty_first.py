# The 61st Investor: growth, release reading, votes, seal and cards.

import html
import re
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fiam.alt import sixty_first as S


# One revenue fact row as SEC's company facts gives it.
def fact(start, end, val, accn, filed, tag="Revenues"):
    return dict(tag=tag, start=start, end=end, val=val, accn=accn, form="10-Q", filed=filed)


# Two years of quarters with a 10-K year and nine months for Q4.
@pytest.fixture
def facts():
    rows = [
        fact("2024-01-01", "2024-03-31", 100, "a1", "2024-05-01"),
        fact("2024-04-01", "2024-06-30", 110, "a2", "2024-08-01"),
        fact("2024-07-01", "2024-09-30", 120, "a3", "2024-11-01"),
        fact("2024-01-01", "2024-09-30", 330, "a3", "2024-11-01"),
        fact("2024-01-01", "2024-12-31", 460, "k1", "2025-02-01"),
        fact("2025-01-01", "2025-03-31", 110, "b1", "2025-05-01"),
        fact("2024-01-01", "2024-03-31", 101, "b1", "2025-05-01"),
        fact("2025-04-01", "2025-06-30", 132, "b2", "2025-08-01"),
        fact("2024-04-01", "2024-06-30", 110, "b2", "2025-08-01"),
    ]
    return pd.DataFrame(rows)


# Q4 is the year less nine months; growth uses the same filing first.
def test_quarters_and_growth(facts):
    q = S.revenue(facts)
    by_end = q.set_index(q["end"].dt.strftime("%Y-%m-%d"))
    assert by_end.loc["2024-12-31", "val"] == 130
    assert by_end.loc["2024-12-31", "basis"] == "year_less_nine"
    # The comparative printed in the same 10-Q (101), not the first (100).
    assert by_end.loc["2025-03-31", "growth"] == pytest.approx(110 / 101 - 1)
    assert by_end.loc["2025-06-30", "growth"] == pytest.approx(0.2)


# The last two growth figures and the quarter about to be reported.
def test_history(facts):
    h = S.history(S.revenue(facts), as_of=pd.Timestamp("2025-10-01"))
    assert h["reason"] == ""
    assert h["last_end"] == "2025-06-30" and h["target_end"] == "2025-09-30"
    assert h["growth_last"] == pytest.approx(0.2)
    assert h["target_ago"] == 120
    stale = S.history(S.revenue(facts), as_of=pd.Timestamp("2026-06-01"))
    assert "missing" in stale["reason"]


# Facts filed on or after the build day are never read.
def test_revenue_ignores_later_filings(facts):
    q = S.revenue(facts, before="2025-07-01")
    assert q["end"].max() == pd.Timestamp("2025-03-31")


# Quarter ends roll forward by calendar month or by 13 weeks.
def test_next_end():
    assert S.next_end(pd.Timestamp("2026-06-30")) == pd.Timestamp("2026-09-30")
    assert S.next_end(pd.Timestamp("2026-06-27")) == pd.Timestamp("2026-09-26")


# Table cells become numbers; text, dashes and percents do not.
def test_number():
    assert S.number("$ 1,234.5") == 1234.5
    assert S.number("(12)") == -12
    assert S.number("12.5 %") is None
    assert S.number("—") is None and S.number("Revenue") is None


RELEASE = """
<html><body><p>Results</p>
<table>
<tr><td></td><td>Three months ended</td><td></td><td>Nine months ended</td></tr>
<tr><td>Revenue growth</td><td>12%</td><td>10%</td></tr>
<tr><td>Total revenues</td><td>$</td><td>1,250.0</td><td>$</td><td>1,100.0</td>
<td>$</td><td>3,600.0</td><td>$</td><td>3,200.0</td></tr>
<tr><td>Cost of revenues</td><td>500</td><td>450</td></tr>
</table></body></html>
"""


# The quarter's revenue sits beside the year-ago figure filed in XBRL.
def test_extract_pairs():
    got = S.extract(RELEASE, 1_100_000_000)
    assert got["current"] == pytest.approx(1_250_000_000)
    assert got["scale"] == 1e6 and got["match"] == "tight"
    assert got["label"] == "Total revenues"


# A sequential column between them still gives the first column.
def test_extract_sequential():
    text = "<table><tr><td>Net sales</td><td>5,300</td><td>5,100</td><td>4,800</td></tr></table>"
    got = S.extract(text, 4_800_000)
    assert got["current"] == pytest.approx(5_300_000)


# Release layouts: prior first, trend, constant currency, a repeat.
@pytest.mark.parametrize(
    "rows, year_ago, want",
    [
        ([[96428, 119796], [84742, 96428, 95997], [96428, 119796, 186662, 229692]], 96428, 119796),
        ([[3284, 3446, 3955, 4036, 4454, 36, 10], [3284, 4454, 6316, 8490]], 3284, 4454),
        ([[8856, 8524, 4], [8856, 548, 9404, 8524, 4, 10], [8856, 8524, 17360, 16432]], 8524, 8856),
        ([[9947, 10365, 9947, 10365], [10365, 10365]], 10365, 9947),
    ],
)
def test_extract_layouts(rows, year_ago, want):
    body = "".join(
        "<tr><td>Total revenues</td>" + "".join(f"<td>{v:,}</td>" for v in r) + "</tr>"
        for r in rows
    )
    got = S.extract(f"<table>{body}</table>", year_ago * 1e6)
    assert got["current"] == pytest.approx(want * 1e6)


# Statements laid out without table tags are read from the text.
def test_extract_text_rows():
    text = "<div>Three Months Ended</div><div>Revenue</div><div>$1,469</div><div>$1,081</div>"
    got = S.extract(text, 1_081_000_000)
    assert got["current"] == pytest.approx(1_469_000_000)


# No year-ago match means no reading, never a guess.
def test_extract_none():
    assert S.extract(RELEASE, 7_777_000) is None


# A month series of levels for the Carbon Arc rule.
def series_rows(metric, levels: dict) -> pd.DataFrame:
    rows = [
        dict(ticker="X", metric=metric, kind="level", month=m, value=v, quarterly=False)
        for m, v in levels.items()
    ]
    return pd.DataFrame(rows)


# Monthly levels with set growth in the quarter and the one before.
def levels(now: float, before: float) -> dict:
    out = {}
    for m in pd.period_range("2025-04", "2025-09", freq="M"):
        out[str(m)] = 100.0
    for m in pd.period_range("2026-04", "2026-06", freq="M"):
        out[str(m)] = 100.0 * (1 + before)
    for m in pd.period_range("2026-07", "2026-09", freq="M"):
        out[str(m)] = 100.0 * (1 + now)
    return out


# Two points up speeds up, two down slows down, in between abstains.
def test_ca_rule():
    up = S.ca_vote_one(series_rows("card_spend", levels(0.10, 0.05)), "2026-09-30")
    assert up["ca"] == S.UP and up["metric"] == "card_spend"
    down = S.ca_vote_one(series_rows("card_spend", levels(0.02, 0.05)), "2026-09-30")
    assert down["ca"] == S.DOWN
    flat = S.ca_vote_one(series_rows("card_spend", levels(0.06, 0.05)), "2026-09-30")
    assert flat["ca"] == S.ABSTAIN


# Card spend first; web traffic decides only when card spend cannot.
def test_ca_order():
    web = series_rows("web_traffic", levels(0.10, 0.0))
    thin = series_rows("card_spend", {"2026-09": 5.0})
    got = S.ca_vote_one(pd.concat([thin, web]), "2026-09-30")
    assert got["metric"] == "web_traffic" and got["ca"] == S.UP
    assert S.ca_vote_one(thin, "2026-09-30")["ca"] == S.ABSTAIN


# Ballots of a small crowd for the tally and the views.
def crowd_votes(patterns: dict) -> pd.DataFrame:
    rows = []
    for agent, words in patterns.items():
        for i, w in enumerate(words):
            rows.append(dict(agent=agent, kind="retail", round="event", ticker=f"T{i:02d}", vote=w))
    return pd.DataFrame(rows)


# A tie abstains; counts are kept per side of the vote.
def test_tally():
    votes = crowd_votes({0: [S.UP, S.UP], 1: [S.DOWN, S.UP]})
    t = S.tally(votes).set_index("ticker")
    assert t.loc["T00", "crowd"] == S.ABSTAIN
    assert t.loc["T01", "crowd"] == S.UP and t.loc["T01", "up"] == 2


# Copies count as one view; independent voters count as many.
def test_views():
    rng = np.random.default_rng(0)
    base = rng.choice([S.UP, S.DOWN], 40).tolist()
    same = S.views(crowd_votes({a: base for a in range(10)}))
    assert same["distinct_vote_patterns"] == 1
    free = {a: rng.choice([S.UP, S.DOWN], 40).tolist() for a in range(10)}
    out = S.views(crowd_votes(free))
    assert out["effective_voters"] > 5 and out["distinct_vote_patterns"] == 10


# Every investor sees every name once, in its own repeatable order.
def test_batches():
    frame = pd.DataFrame({"ticker": [f"T{i:02d}" for i in range(19)]})
    agent = dict(seed=3)
    one = S.batches(agent, frame, "event")
    assert [len(b) for b in one] == [8, 8, 3]
    flat = [t for b in one for t in b["ticker"]]
    assert sorted(flat) == sorted(frame["ticker"])
    assert flat == [t for b in S.batches(agent, frame, "event") for t in b["ticker"]]
    assert flat != [t for b in S.batches(dict(seed=4), frame, "event") for t in b["ticker"]]


# The schema asks one of the two words for each ticker.
def test_schema():
    s = S.answer_schema(["AAA", "BBB"])
    assert s["required"] == ["AAA", "BBB"]
    assert s["properties"]["AAA"]["enum"] == [S.UP, S.DOWN]


# The 60 investors: 30 retail and 30 copycats, ids 0 to 59.
def test_agents():
    crowd = S.agents()
    assert len(crowd) == 60 and sorted(a["id"] for a in crowd) == list(range(60))
    assert sum(a["kind"] == "retail" for a in crowd) == 30
    assert all(S.QUESTION in a["system"] for a in crowd)


# The question shows growth only: no price, return or Carbon Arc.
def test_question_inputs():
    rows = pd.DataFrame(
        [dict(ticker="AAA", name="Alpha", sector="Industrials", prev_end="2026-03-31",
              growth_prev=0.05, last_end="2026-06-30", growth_last=0.07)]
    )  # fmt: skip
    text = S.question(rows)
    assert "+5.0%" in text and "+7.0%" in text
    for word in ("price", "return", "Carbon", "consensus"):
        assert word not in text and word not in S.QUESTION


# Energy and commodity sectors are out; the rest stay in.
def test_commodity():
    assert S.commodity("G10") and S.commodity("G15") and S.commodity("S13")
    assert not S.commodity("G25") and not S.commodity("S58")
    assert S.sector_name("G45") == "Information Technology"


# The coin is set by the seal hash; marks keep abstains.
def test_coin_and_mark():
    assert S.coin("abc", "AAA") == S.coin("abc", "AAA")
    calls = {S.coin(f"h{i}", "AAA") for i in range(20)}
    assert calls == {S.UP, S.DOWN}
    assert S.mark(S.UP, S.UP) == "hit" and S.mark(S.DOWN, S.UP) == "miss"
    assert S.mark(S.ABSTAIN, S.UP) == "abstain" and S.mark(S.UP, None) == ""


# A card's visible copy has no colons, semicolons or long dashes.
def test_card_copy():
    r = SimpleNamespace(
        ticker="AAA", name="Alpha Inc", side="long", weight=0.012, sector="Industrials",
        projected="2026-10-29", prev_end="2026-03-31", growth_prev=0.05,
        last_end="2026-06-30", growth_last=0.07, card_spend=True, web_traffic=False,
    )  # fmt: skip
    crowd_row = pd.Series(dict(crowd=S.UP, up=40, down=20))
    ca_row = pd.Series(dict(ca=S.ABSTAIN, metric="card_spend"))
    page = S.card_html(r, crowd_row, ca_row, None, 4.2, "2026-10-28 hash abc")
    visible = html.unescape(re.sub(r"<[^>]+>", " ", page))
    assert not re.search(r"[:;–—]", visible)
    assert "About 4" in visible and S.CREDIT in visible


# The seal's file list hashes the same twice and changes with a file.
def test_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SF", tmp_path)
    monkeypatch.setattr(S, "ROOT", tmp_path)
    (tmp_path / "RULES.md").write_text("rules")
    names = pd.DataFrame([dict(ticker="AAA", cik=1, target_end="2026-09-30", in_contest=True)])
    for label in ("event", "twoweeks"):
        names.to_csv(tmp_path / f"names_{label}.csv", index=False)
    first = S.seal(offline=True)
    again = S.seal(offline=True)
    assert first["sha256"] == again["sha256"]
    (tmp_path / "RULES.md").write_text("other rules")
    assert S.seal(offline=True)["sha256"] != first["sha256"]
    text = (tmp_path / "SEAL.txt").read_text()
    assert text.startswith("SHA-256 ") and "UTC " in text and "SF/RULES.md" in text


# A name is judged by the first seal that hashed its votes.
def test_live_at_first_seal_with(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SF", tmp_path)
    seals = tmp_path / "seals"
    seals.mkdir()
    (seals / "SEAL_20261028T100000Z.txt").write_text("x\n\nfiles\nab  SF/votes/event.jsonl\n")
    (seals / "SEAL_20261028T220000Z.txt").write_text("y\n\nfiles\ncd  SF/votes/extra.jsonl\n")
    pd.DataFrame({"ticker": ["AAA", "BBB"]}).to_csv(seals / "contest_20261028T100000Z.csv")
    pd.DataFrame({"ticker": ["AAA"]}).to_csv(seals / "contest_20261028T220000Z.csv")
    assert S.live_at_first_seal_with("votes/event.jsonl") == {"AAA", "BBB"}
    assert S.live_at_first_seal_with("votes/extra.jsonl") == {"AAA"}
    assert S.live_at_first_seal_with("votes/other.jsonl") is None
