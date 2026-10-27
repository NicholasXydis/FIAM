# The FEMA notice rule: county names, statewide aid, never mitigation.

from fiam.vfinal import fema


# A county counts as a whole word, never inside another name.
def test_county_matches_whole_words_only():
    text = "the following areas: Lake, Union, and Clay Counties for Public Assistance."
    assert fema.names_county(text, "Lake")
    assert not fema.names_county("Lakewood Parish for Public Assistance.", "Lake")


# Statewide aid counts, the statewide hazard mitigation line does not.
def test_statewide_aid_counts_but_mitigation_does_not():
    aid = "All counties in the State of Iowa are eligible for Public Assistance."
    hm = (
        "All areas within the State of Iowa are eligible for assistance under the Hazard "
        "Mitigation Grant Program."
    )
    assert fema.names_county(aid, "Polk")
    assert not fema.names_county(hm, "Polk")
