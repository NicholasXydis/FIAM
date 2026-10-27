# Site data matches the final book's pack, so no number can drift.

import json

import pytest

from fiam import book
from tools import build_site

SITE = build_site.OUT


# The site's bundled data, loaded once per module; skips if not built.
@pytest.fixture(scope="module")
def site():
    if not SITE.exists():
        pytest.skip("no site data; python3 tools/build_site.py writes it")
    return json.loads(SITE.read_text(encoding="utf-8"))


# Rebuilt from the pack, the data is exactly what the site bundles.
def test_site_data_is_the_pack_as_exported(site):
    if not build_site.PACK.is_dir():
        pytest.skip("no final v3 pack; uv run run.py --import fiam_results.zip")
    assert json.loads(json.dumps(build_site.build(), separators=(",", ":"))) == site


# The headline figures are the pack's metrics, rounded and nothing else.
def test_headline_matches_metrics(site):
    if not build_site.PACK.is_dir():
        pytest.skip("no final v3 pack")
    perf = json.loads((build_site.PACK / "metrics.json").read_text())["performance"]
    assert site["headline"]["ir"] == pytest.approx(perf["information_ratio"], abs=5e-4)
    assert site["headline"]["net"] == pytest.approx(perf["return_net_annual"], abs=5e-5)
    assert site["headline"]["beta"] == pytest.approx(perf["beta_realized"], abs=5e-4)


# $1 grows to the pack's own cumulative return, and the months line up.
def test_growth_ends_at_the_cumulative_return(site):
    race = site["race"]
    assert len(race["book"]) == len(site["months"]) + 1
    assert race["book"][-1] - 1 == pytest.approx(site["headline"]["cumulative"], abs=1e-3)
    assert len(site["stocks"]["book"]) == len(site["months"])


# The twelve measures and their signs are the book's own.
def test_signals_are_the_books(site):
    assert {s["code"]: s["sign"] for s in site["signals"]} == book.SIGNALS


# Each month's holdings net to about zero, as the book does.
def test_each_month_is_market_neutral_in_dollars(site):
    for flat in site["stocks"]["book"]:
        net = sum(flat[1::2]) / 1000 / 100
        assert abs(net) < 0.005


# The honesty scene's ledger adds up to the metrics' trial count.
def test_attempts_add_up(site):
    honesty = site["honesty"]
    assert sum(f["attempts"] for f in honesty["families"]) == honesty["attempts"]
    assert sum(f["attempts"] for f in honesty["families"] if f["eligible"]) == honesty["eligible"]


# The September book shown is frozen: dollar neutral at 160% gross.
def test_september_book_is_neutral(site):
    weights = [w / 1e5 for _, _, w in site["september"]["book"]]
    assert abs(sum(weights)) < 1e-3
    assert sum(abs(w) for w in weights) == pytest.approx(1.6, abs=0.01)
    assert {e["ticker"] for e in site["explained"]} <= {t for t, _, _ in site["september"]["book"]}


# Ad crashes: the stress windows and replays, with a market move each.
def test_crashes_match_the_stress_test():
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    from fiam.exhibits.stress import CRISES

    crashes = json.loads(build_site.CRASHES.read_text(encoding="utf-8"))
    assert [(c["name"], c["first"], c["last"]) for c in crashes] == [
        (name, first, last) for name, (first, last) in CRISES.items()
    ]
    stress = build_site.V2 / "stress.json"
    if stress.exists():
        replay = json.loads(stress.read_text())["final v3"]["crises"]
        for c in crashes:
            assert c["book"] == pytest.approx(replay[c["name"]]["loss"], abs=5e-5)
    covid = next(c for c in crashes if c["name"].startswith("Covid"))
    assert covid["market"] < -0.3 < covid["book"]


# The ad's voice matches its data: agents, filings, investors, crises.
def test_ad_voice_matches_the_data(site):
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    data = site | {"crashes": json.loads(build_site.CRASHES.read_text(encoding="utf-8"))}
    lines = json.loads((build_site.ROOT / "site" / "ad" / "voice" / "lines.json").read_text())
    said = {key: " ".join(text) for key, text in lines.items()}
    assert len(data["agents"]) == 7 and said["agents"].startswith("Seven AI agents")
    filings = next(v for k, v in data["agents"][1]["facts"] if k == "Filings labelled")
    assert int(filings.replace(",", "")) >= 2000 and "thousands of filings" in said["agents"]
    crowd = data["crowd"]
    assert crowd["agents"] + crowd["copycats"] == 60 and "sixty AI investors" in said["crowd"]
    assert crowd["agents"] == 30 and round(crowd["effective_voters"]) == 4
    assert "Thirty of them think like four" in said["crowd"]
    assert len(data["crashes"]) == 17 and "seventeen replayed crises" in said["crises"]
