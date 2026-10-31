# Site data matches the fund's numbers pack, number for number.

import json
from pathlib import Path

import pytest

from tools import build_site

SITE = build_site.OUT
PACK = build_site.PACK


# The site's bundled data, loaded once per module; skips if not built.
@pytest.fixture(scope="module")
def site():
    if not SITE.exists():
        pytest.skip("no site data; uv run tools/build_site.py writes it")
    return json.loads(SITE.read_text(encoding="utf-8"))


# The pack's numbers file, else a skip.
@pytest.fixture(scope="module")
def numbers():
    if not (PACK / "numbers.json").exists():
        pytest.skip("no numbers pack on this machine")
    return build_site.load(PACK / "numbers.json")


# Rebuilt from the pack, the data is exactly what the site bundles.
def test_site_data_is_the_pack_rebuilt(site, numbers):
    if not build_site.PANEL.exists():
        pytest.skip("no organisers' panel")
    made = build_site.build(site, PACK)
    assert json.loads(json.dumps(made, separators=(",", ":"))) == site


# The headline figures are the pack's, rounded and nothing else.
def test_headline_matches_the_pack(site, numbers):
    head, pack = site["headline"], numbers["headline"]
    assert head["cagr"] == pytest.approx(pack["cagr_pct"] / 100, abs=5e-5)
    assert head["cumulative"] == pytest.approx(pack["cumulative_return_pct"] / 100, abs=5e-5)
    assert head["sharpe"] == pytest.approx(pack["sharpe_pdf_bill"], abs=5e-4)
    assert head["drawdown"] == pytest.approx(pack["max_drawdown_pct"] / 100, abs=5e-5)
    assert head["beta"] == pytest.approx(pack["beta_monthly"], abs=5e-4)
    hits = numbers["hit_rate"]
    assert head["months_up"] / len(site["months"]) == pytest.approx(
        hits["monthly_hit_rate_pct"] / 100, abs=5e-4
    )
    assert len(site["months"]) == hits["months"]
    assert head["worst_month"]["value"] == pytest.approx(
        pack["max_one_month_loss_pct"] / 100, abs=5e-5
    )


# The months the race and the month dots read agree with the headline.
def test_monthly_returns_add_up(site):
    race, head = site["race"], site["headline"]
    assert len(race["book"]) == len(site["months"]) + 1
    assert race["book"][-1] - 1 == pytest.approx(head["cumulative"], abs=1e-3)
    assert sum(x > 0 for x in race["book_monthly"]) == head["months_up"]
    assert max(race["book_monthly"]) == pytest.approx(head["best_month"]["value"], abs=1e-4)
    assert min(race["book_monthly"]) == pytest.approx(head["worst_month"]["value"], abs=1e-4)
    assert len(site["stocks"]["book"]) == len(site["months"])


# Costs add up: before costs is after costs plus the two booked parts.
def test_costs_add_up(site, numbers):
    c = site["costs"]
    rows = numbers["table_5_1"]["recomputed"]
    assert c["parts"]["trading"] == pytest.approx(rows["21_trading_cost_pct"] / 100, abs=5e-6)
    assert c["parts"]["borrow"] == pytest.approx(rows["22_borrow_pct"] / 100, abs=5e-6)
    assert c["gross"] == pytest.approx(c["net"] + c["total"], abs=2e-5)
    assert c["cash"] == pytest.approx(c["hurdle"] - build_site.PREMIUM, abs=2e-5)
    even = (c["gross"] - c["hurdle"]) / c["total"]
    assert c["break_even"] == pytest.approx(even, abs=0.02)


# The forecast's inputs: the organisers' sets and our three, 150 in all.
def test_signals_are_theirs_and_ours(site):
    ours = [s for s in site["signals"] if s["family"] == "ours"]
    assert [s["label"] for s in ours] == list(build_site.OURS.values())
    theirs = sum(s["count"] for s in site["signals"] if s["family"] == "theirs")
    assert site["families"]["theirs"] == f"The organisers' {theirs} characteristics"
    assert theirs + len(ours) == sum(s["count"] for s in site["signals"])


# Each month's book nets within the daily net range the table reports.
def test_each_month_nets_within_the_table(site):
    path = build_site.RUN / "table_9_1.csv"
    if not path.exists():
        pytest.skip("no run table on this machine")
    cell = build_site.table_rows(path)[16]["strategy"]
    low, high = build_site.labelled(cell, "min"), build_site.labelled(cell, "max")
    for flat in site["stocks"]["book"]:
        net = sum(flat[1::2]) / 1000
        assert low - 1 <= net <= high + 1


# The book shown now is the last month's book, largest weight first.
def test_book_now_is_the_last_month(site):
    now = site["september"]
    assert now["month"] == site["months"][-1]
    flat = site["stocks"]["book"][-1]
    assert sorted(w for _, _, w in now["book"]) == sorted(flat[1::2])
    weights = [w for _, _, w in now["book"]]
    assert weights == sorted(weights, reverse=True)


# The crashes are the pack's replay with peer fill, crisis by crisis.
def test_crashes_match_the_replay(site, numbers):
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    crashes = json.loads(build_site.CRASHES.read_text(encoding="utf-8"))
    assert crashes == site["crises"]
    replay = build_site.load(PACK / "crises.json")[build_site.VARIANT]["crises"]
    assert [c["name"] for c in crashes] == [c["crisis"] for c in replay]
    for c, x in zip(crashes, replay):
        assert c["book"] == pytest.approx(x["book_pct"] / 100, abs=5e-5)
        assert c["market"] == pytest.approx(x["market_pct"] / 100, abs=5e-5)


# No internal run names in the data the site ships.
def test_data_has_no_internal_run_names():
    for path in (SITE, build_site.CRASHES):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        banned = ("vfinal", "bw_fresh")
        for word in banned:
            assert word not in text, (path.name, word)


# Eight agents, each with the finding the findings file gives it.
def test_agents_are_the_eight_findings(site):
    path = build_site.AI / "agents_found.json"
    if not path.exists():
        pytest.skip("no agent findings in finals/ai")
    file = build_site.load(path)
    found = file["agents"]
    assert len(site["agents"]) == 8 == len(found) and not file.get("pending")
    for a in site["agents"]:
        got = found[build_site.AGENT_NAMES[a["key"]]]
        assert (a["finding"], a["number"], a["date"]) == (
            got["finding"],
            got["key_number"],
            got["date"],
        )
    assert "vfinal_pack" not in json.dumps(site["agents"])
    # Each finding's source is a file in the repo, never a home folder.
    for got in found.values():
        assert not Path(got["source"]).is_absolute()
        assert (build_site.ROOT / got["source"]).exists()


# The crowd card and data are the study's round block, nothing else.
def test_crowd_is_the_round_block(site):
    crowd = site["crowd"]
    assert not set(build_site.STALE) & set(crowd)
    if not build_site.CROWD.exists():
        pytest.skip("no crowd study in finals/ai")
    study = build_site.load(build_site.CROWD)
    rounded = study["round"]
    assert (crowd["long_pct"], crowd["short_pct"]) == (
        rounded["avg_long_pct"],
        rounded["avg_short_pct"],
    )
    assert (crowd["beta"], crowd["effective_voters"]) == (rounded["beta"], rounded["voters"])
    assert (crowd["lsv"], crowd["sell_10bn_pct"]) == (rounded["lsv"], rounded["sell_10bn_pct"])
    share = study["spliced_retail"]["average"]["long_in_top_decile"]
    assert crowd["favourites_pct"] == round(share * 100)
    agent = next(a for a in site["agents"] if a["key"] == "crowd")
    assert f"AI crowd's {build_site.ordinal(rounded['long_pct'])} percentile" in agent["finding"]
    assert f"shorts at the {build_site.ordinal(rounded['short_pct'])}" in agent["finding"]
    # The crowd model's own percentiles never show, unless they match.
    final = study["crowd_model_2021_2026"]["final_book_2026_08"]
    shown = {rounded[k] for k in ("long_pct", "short_pct", "avg_long_pct", "avg_short_pct")}
    text = SITE.read_text(encoding="utf-8")
    for share in (final["long_mean_pct"], final["short_mean_pct"]):
        n = round(share * 100)
        if n not in shown:
            assert build_site.ordinal(n) not in text


# The holdings card has Carbon Arc totals only, never a ticker.
def test_hype_card_is_totals_only(site):
    hype = site["september"]["hype"]
    assert set(hype) == {"long_growth", "short_growth", "longs", "shorts", "favourites", "in_hype"}
    assert all(isinstance(v, (int, float)) for v in hype.values())
    if build_site.HYPE.exists():
        card = build_site.load(build_site.HYPE)["card"]
        assert hype["long_growth"] == card["longs_vs_shorts"]["long_wmean"]
        assert hype["in_hype"] == card["crowd_favourites"]["in_hype"]


# Agent cards carry no fact without a file; the crowd names its model.
def test_agent_cards_are_backed(site):
    assert "desk" not in site
    assert all("facts" not in a for a in site["agents"])
    crowd = next(a for a in site["agents"] if a["key"] == "crowd")
    if build_site.CROWD.exists():
        assert crowd["model"] == build_site.crowd_models()
    assert "Qwen" not in crowd["model"]


# The 2022 bars beside the 60/40 are all with dividends, as it is.
def test_2022_bars_share_the_sixty_forty_basis(site, numbers):
    year, six = site["edge"]["year_2022"], numbers["sixty_forty"]
    legs = six["legs_stats"]
    assert year["sp500"] == pytest.approx(legs["stocks"]["year_2022_pct"] / 100, abs=5e-5)
    assert year["bonds"] == pytest.approx(legs["bonds"]["year_2022_pct"] / 100, abs=5e-5)
    assert year["sixty_forty"] == pytest.approx(
        six["mixes"]["60/40"]["year_2022_pct"] / 100, abs=5e-5
    )
    # The race's yearly cards keep the price index, as the PDF's market.
    price = numbers["calendar_years"][1]["sp500_pct"] / 100
    assert site["years"]["2022"]["market"] == pytest.approx(price, abs=5e-5)


# The ad's voice matches its data: agents, investors and crises.
def test_ad_voice_matches_the_data(site):
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    data = site | {"crashes": json.loads(build_site.CRASHES.read_text(encoding="utf-8"))}
    lines = json.loads((build_site.ROOT / "site" / "ad" / "voice" / "lines.json").read_text())
    said = {key: " ".join(text) for key, text in lines.items()}
    assert len(data["agents"]) == 8 and said["agents"].startswith("Eight AI agents")
    crowd = data["crowd"]
    assert crowd["agents"] + crowd["copycats"] == 60 and "sixty AI investors" in said["crowd"]
    assert crowd["agents"] == 30 and round(crowd["effective_voters"]) == 4
    assert "Thirty of them think like four" in said["crowd"]
    assert len(data["crashes"]) == 17 and "seventeen replayed crises" in said["crises"]


# The film's "thousands of filings" rests on the triage agent's labels.
def test_film_filings_line_is_backed():
    import pandas as pd

    lines = json.loads((build_site.ROOT / "site" / "ad" / "voice" / "lines.json").read_text())
    if "thousands of filings" not in " ".join(lines["agents"]):
        return
    labels = build_site.ROOT / "frozen" / "agents" / "triage_labels.parquet"
    assert labels.exists(), "the film says thousands of filings but the labels are gone"
    assert len(pd.read_parquet(labels, columns=["document_id"])) >= 2000
