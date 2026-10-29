# The rules reader, honesty test, mandate checks and film helpers.

import json

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


# A PDF's stray space before a comma does not drop a true quote.
def test_rules_reader_quote_ignores_pdf_spacing():
    text = "Net exposure must not exceed \n 20% of capital\n , measured at each date."
    answer = dict(sector=0.2, sector_quote="must not exceed 20% of capital, measured at each date.")
    assert list(rules_reader.verified(answer, text)) == ["sector"]


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
