# Site data matches the final fund's result files, number for number.

import ast
import json

import pytest

from tools import build_site

SITE = build_site.OUT


# The site's bundled data, loaded once per module; skips if not built.
@pytest.fixture(scope="module")
def site():
    if not SITE.exists():
        pytest.skip("no site data; uv run tools/build_site.py writes it")
    return json.loads(SITE.read_text(encoding="utf-8"))


# The pick named by the bundle's own code, else a skip.
@pytest.fixture(scope="module")
def picked(site):
    pick = build_site.V4 / f"pick_{site['code']}.json"
    if not pick.exists():
        pytest.skip("no final pick; the vfinal results are not here")
    folder, commit = build_site.headline_folder(pick)
    return folder, commit


# Rebuilt from the result files, the data is what the site bundles.
def test_site_data_is_the_final_fund(site, picked):
    if not build_site.PANEL.exists():
        pytest.skip("no organisers' panel")
    folder, commit = picked
    pick = json.loads((build_site.V4 / f"pick_{site['code']}.json").read_text())
    made = build_site.v4(site, folder, commit, build_site.sp500())
    made = build_site.final(made, folder, commit, pick)
    assert json.loads(json.dumps(made, separators=(",", ":"))) == site


# The headline figures are the table's rows, rounded and nothing else.
def test_headline_matches_the_table(site, picked):
    folder, commit = picked
    t = build_site.table_rows(folder / f"table_9_1_{commit}.csv")
    assert site["headline"]["ir"] == build_site.first(t[23]["strategy"])
    assert site["headline"]["beta"] == build_site.with_se(t[7]["strategy"])[0]
    assert site["headline"]["beta_monthly"] == build_site.with_se(t[6]["strategy"])[0]
    assert site["headline"]["drawdown"] == pytest.approx(float(t[11]["strategy"]) / 100, abs=5e-5)


# $1 grows to the cumulative return, and the months line up.
def test_growth_ends_at_the_cumulative_return(site):
    race = site["race"]
    assert len(race["book"]) == len(site["months"]) + 1
    assert race["book"][-1] - 1 == pytest.approx(site["headline"]["cumulative"], abs=1e-3)
    assert len(site["stocks"]["book"]) == len(site["months"])


# The ten measures and their signs are SYY-10's own.
def test_signals_are_syy_parts(site):
    path = build_site.ROOT / "fiam" / "vfinal" / "signals" / "syy.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parts = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PARTS"
    )
    assert {s["code"]: s["sign"] for s in site["signals"]} == parts


# Each month's book nets within the daily net range the table reports.
def test_each_month_nets_within_the_table(site, picked):
    folder, commit = picked
    cell = build_site.table_rows(folder / f"table_9_1_{commit}.csv")[16]["strategy"]
    low, high = build_site.labelled(cell, "min"), build_site.labelled(cell, "max")
    for flat in site["stocks"]["book"]:
        net = sum(flat[1::2]) / 1000
        assert low - 1 <= net <= high + 1


# The honesty scene's ledger adds up to its own totals.
def test_attempts_add_up(site):
    honesty = site["honesty"]
    assert sum(f["attempts"] for f in honesty["families"]) == honesty["attempts"]
    assert sum(f["attempts"] for f in honesty["families"] if f["eligible"]) == honesty["eligible"]
    assert honesty["ideas"] == 8 and honesty["ideas_passed"] == 0


# The book shown now is the one the X-ray and the crises replay.
def test_book_now_is_the_replayed_book(site, picked):
    folder, commit = picked
    replay = json.loads((folder / f"crises_{commit}.json").read_text())
    weights = [w / 1e5 for _, _, w in site["september"]["book"]]
    assert len(weights) == replay["names"] == site["september"]["xray"]["names"]
    assert sum(abs(w) for w in weights) == pytest.approx(replay["gross"], abs=1e-3)


# Ad crashes: the stress windows and the final book's replays.
def test_crashes_match_the_stress_test(picked):
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    from fiam.exhibits.stress import CRISES

    crashes = json.loads(build_site.CRASHES.read_text(encoding="utf-8"))
    assert [(c["name"], c["first"], c["last"]) for c in crashes] == [
        (name, first, last) for name, (first, last) in CRISES.items()
    ]
    folder, commit = picked
    replay = json.loads((folder / f"crises_{commit}.json").read_text())["crises"]
    for c in crashes:
        assert c["book"] == pytest.approx(replay[c["name"]]["loss"], abs=5e-5)
        assert c["market"] == pytest.approx(replay[c["name"]]["market"], abs=5e-5)
    covid = next(c for c in crashes if c["name"].startswith("Covid"))
    assert covid["market"] < -0.3 < covid["book"]


# The ad's voice matches its data: agents, filings, investors, crises.
def test_ad_voice_matches_the_data(site):
    if not build_site.CRASHES.exists():
        pytest.skip("no crash data; uv run tools/build_site.py writes it")
    data = site | {"crashes": json.loads(build_site.CRASHES.read_text(encoding="utf-8"))}
    lines = json.loads((build_site.ROOT / "site" / "ad" / "voice" / "lines.json").read_text())
    said = {key: " ".join(text) for key, text in lines.items()}
    assert len(data["agents"]) == 8 and said["agents"].startswith("Eight AI agents")
    filings = next(v for k, v in data["agents"][1]["facts"] if k == "Filings labelled")
    assert int(filings.replace(",", "")) >= 2000 and "thousands of filings" in said["agents"]
    crowd = data["crowd"]
    assert crowd["agents"] + crowd["copycats"] == 60 and "sixty AI investors" in said["crowd"]
    assert crowd["agents"] == 30 and round(crowd["effective_voters"]) == 4
    assert "Thirty of them think like four" in said["crowd"]
    assert len(data["crashes"]) == 17 and "seventeen replayed crises" in said["crises"]
