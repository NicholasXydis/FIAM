# The rules reader, honesty test, mandate checks and film helpers.

import json
from pathlib import Path

import pandas as pd
import pytest

from fiam import mandate as M
from fiam.agents import honesty, rules_reader


# Impossible mandates are named, and an unknown rule field is refused.
def test_mandate_check_names_impossible_rules(tmp_path):
    assert M.check(M.Mandate()) == []
    bad = M.Mandate(long_only=True, net=1.6, gross=1.6, names_max=10, name_cap=0.05)
    problems = " ".join(M.check(bad))
    assert "beta neutral" in problems and "cannot reach" in problems
    path = tmp_path / "m.json"
    path.write_text(json.dumps(dict(name="x", leverage=2)), encoding="utf-8")
    with pytest.raises(ValueError):
        M.load(path)


# A rule survives only with a word-for-word quote.
def test_rules_reader_keeps_only_verbatim_quotes():
    text = "Leverage is 150/50.\n\nNo single stock may exceed 10%."
    answer = dict(
        gross=2.0,
        gross_quote="Leverage is 150/50.",
        name_cap=0.1,
        name_cap_quote="No stock may exceed ten percent.",
    )
    assert list(rules_reader.verified(answer, text)) == ["gross"]


# A 150/50 draft drops neutral sector and beta limits; neutral keeps.
def test_directional_draft_drops_neutral_limits():
    rules = dict(gross=dict(value=2.0, quote="q"), net=dict(value=1.0, quote="q"))
    draft = rules_reader.drafted(rules, "t")
    assert draft["sector"] is None and draft["beta"] is None
    assert M.check(M.Mandate(**draft)) == []
    assert "sector" not in rules_reader.drafted(dict(gross=dict(value=2.0, quote="q")), "t")


# The reversed text swaps direction words and flips percent signs.
def test_honesty_reversal_flips_words_and_signs():
    row = pd.Series(
        dict(
            excerpt="[COMPANY] said revenue increased 12% and costs fell.",
            company_name="Acme",
            filing_date=pd.Timestamp("2024-05-01"),
        )
    )
    texts = honesty.conditions(row)
    assert texts["reversed"] == "[COMPANY] said revenue decreased -12% and costs rose."
    assert texts["named"].startswith("Acme said")


# The film's easing stays in bounds; the deck's Morph XML is valid.
def test_film_easing_and_deck_motion():
    import sys
    from types import SimpleNamespace

    from lxml import etree

    from fiam.report import animation

    assert animation.ease(-1) == 0 and animation.ease(2) == 1
    assert animation.fade(0.4, 0.0) < animation.fade(0.6, 0.0)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import motion

    assert etree.fromstring(motion.MORPH) is not None
    shapes = [SimpleNamespace(shape_id=i, has_text_frame=i % 2 == 0) for i in (2, 3, 4)]
    steps = motion.stagger(shapes, "zoom") + [(shapes[0], "wipe", 900)]
    film = SimpleNamespace(shape_id=9)
    timing = etree.fromstring(motion.timeline(steps, film))
    tags = timing.findall(".//{%s}cTn[@presetClass]" % motion.P)
    assert [t.get("presetClass") for t in tags].count("entr") == 4
    assert [t.get("presetClass") for t in tags].count("mediacall") == 1
