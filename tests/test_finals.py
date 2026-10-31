# The finals folder: the deck, the fact sheet and the numbers they show.
import json
import re
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINALS = ROOT / "finals"
NUMBERS = json.loads((FINALS / "numbers.json").read_text(encoding="utf-8"))["figures"]


# The deck's visible text, without scripts, styles or embedded images.
def deck_text() -> str:
    page = (ROOT / "tools" / "deck" / "deck.html").read_text(encoding="utf-8")
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r'src="data:[^"]*"', "", page)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", page)))


# The deck, its PDF and the fact sheet sit at the top of the repo.
def test_finals_files_are_in_the_repo():
    for name in ("QUARCC_Purple_Finals.pptx", "QUARCC_Purple_Finals.pdf"):
        assert (FINALS / name).stat().st_size > 1_000_000, name
    assert (FINALS / "QUARCC_Purple_Fact_Sheet.pdf").stat().st_size > 100_000


# Each figure is shown where numbers.json says, exactly as written.
@pytest.mark.parametrize("key", sorted(NUMBERS))
def test_figure_is_shown_as_written(key):
    pages = {"readme": (ROOT / "README.md").read_text(encoding="utf-8"), "deck": deck_text()}
    for where in NUMBERS[key]["in"]:
        assert NUMBERS[key]["shown"] in pages[where], f"{key} not shown in the {where}"


# Every shown figure rounds from its value, unless a gap is stated.
@pytest.mark.parametrize("key", sorted(NUMBERS))
def test_shown_figure_matches_its_value(key):
    n = NUMBERS[key]
    if "gap" in n or isinstance(n["value"], list):
        return
    shown = re.search(r"\d+\.?\d*", n["shown"].replace(",", "")).group()
    places = len(shown.split(".")[1]) if "." in shown else 0
    assert f"{abs(n['value']):.{places}f}" == shown, key


# Each agent the README names has its record in the repo.
def test_readme_agents_have_their_records():
    found = json.loads((FINALS / "ai" / "agents_found.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, entry in found["agents"].items():
        assert f"| {name} |" in readme, name
        assert (ROOT / entry["source"]).is_file(), entry["source"]
