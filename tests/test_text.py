# The filing text rules on small texts.

import pandas as pd

from fiam.vfinal import text

BODY = "The following risks could hurt us. " * 30
DOC = (
    "Table of contents ITEM 1A. RISK FACTORS 29 ITEM 1B. UNRESOLVED STAFF COMMENTS 62 "
    'As described in Item 1A, "Risk Factors" of this report, we face risks. '
    f"ITEM 1A. RISK FACTORS {BODY} ITEM 1B. UNRESOLVED STAFF COMMENTS None. "
    "ITEM 2. PROPERTIES Our offices are in Texas and Ohio. ITEM 3. LEGAL PROCEEDINGS None."
)


# The real section wins over the table of contents and cross-references.
def test_section_skips_contents_and_cross_references():
    got = text.section(DOC, "1a")
    assert got.startswith("ITEM 1A. RISK FACTORS The following")
    assert got.rstrip().endswith("hurt us.")
    assert text.section("ITEM 1A. RISK FACTORS Not applicable. ITEM 1B. None", "1a") is None


# Safe-harbour sentences go; the rest stays.
def test_strip_boilerplate_drops_forward_looking_sentences():
    raw = "Sales rose. These forward-looking statements are uncertain. Costs fell."
    assert text.strip_boilerplate(raw) == "Sales rose. Costs fell."


# A CEO leaving counts; an appointment does not; a dispute counts.
def test_departure_502_rule():
    assert text.departure_502("Jane Doe resigned as Chief Executive Officer.")["ceo_cfo_leaving"]
    assert not text.departure_502("John Roe was appointed Chief Financial Officer.")[
        "ceo_cfo_leaving"
    ]
    dispute = text.departure_502("The director resigned due to a disagreement with the board.")
    assert dispute["director_disagreement"]


# The cover page address gives the state and ZIP; Item 2 gives states.
def test_headquarters_and_property_states():
    cover = "One Main Street, Austin, Texas 78701 (Address of principal executive offices) "
    assert text.headquarters(cover) == ("TX", "78701")
    assert text.property_states(DOC) == ["TX", "OH"]


# Customers at 10% or more are kept with their share and kind.
def test_customers_need_ten_percent():
    found = text.customers(
        "Sales to Wal-Mart Stores, Inc. accounted for approximately 23% of our net sales. "
        "Target represented 5% of revenue from customers."
    )
    assert found == [("Wal-Mart Stores, Inc.", 23.0, "named", False)]
    more = text.customers(
        "Sales to the U.S. Government represented 40% of revenue. "
        "One customer accounted for 11% of sales."
    )
    assert more == [
        ("U.S. Government", 40.0, "government", False),
        ("One customer", 11.0, "unnamed", False),
    ]


# A list of names takes its shares in order; one name, the latest year.
def test_customer_lists_and_years():
    listed = text.customers(
        "Sales to McKesson Corporation, AmerisourceBergen Corporation and Cardinal Health, "
        "Inc. accounted for 30%, 25% and 20% of revenues, respectively."
    )
    assert [(n, s) for n, s, *_ in listed] == [
        ("McKesson Corporation", 30.0),
        ("AmerisourceBergen Corporation", 25.0),
        ("Cardinal Health", 20.0),
    ]
    years = text.customers(
        "Sales to Walmart accounted for 21%, 23% and 25% of net sales in 2017, 2018 and 2019."
    )
    assert years == [("Walmart", 25.0, "named", False)]
    # Two shares, one name and no years printed: which year is unknown.
    assert text.customers("Sales to Walmart accounted for 25% and 23% of net sales.") == []


# A product line, a region or a joint share is never one named firm.
def test_customer_kinds_exclude_products_and_regions():
    assert text.customers("Humira accounted for 60% of net revenues.") == []
    assert text.customers("Sales to France and Germany represented 12% of sales.") == []
    joint = text.customers("Sales to Lowe's and Home Depot accounted for 43% of net sales.")
    assert joint == [("Lowe's and Home Depot", 43.0, "joint", False)]
    segment = "Sales to Target accounted for 17% of the Innerwear segment's net sales."
    assert text.customers(segment) == []
    product = "Sales of CryoPatch SG accounted for 64% of revenues from customers."
    assert text.customers(product) == []
    floor = text.customers("Sales to Verizon accounted for more than 10% of our revenue.")
    assert floor == [("Verizon", 10.0, "named", True)]


# Names match the CRSP name in force, never the filer, ambiguity none.
def test_match_customers_by_dated_name():
    names = pd.DataFrame(
        {
            "permno": [1, 2, 3, 4],
            "value": ["WAL MART STORES INC", "WALMART INC", "ACME CORP", "ACME CO"],
            "valid_from": pd.to_datetime(["1972-01-01", "2018-02-01", "2000-01-01", "2000-01-01"]),
            "valid_to": pd.to_datetime(["2018-01-31", None, None, None]),
        }
    )
    found = pd.DataFrame(
        {
            "customer": ["Wal-Mart Stores, Inc.", "Walmart", "Acme", "Wal-Mart Stores"],
            "permno": [9, 9, 9, 1],
            "filing_date": pd.to_datetime(["2015-03-01", "2019-03-01", "2019-03-01", "2015-03-01"]),
        }
    )
    got = text.match_customers(found, names)
    assert got["customer_permno"].tolist()[:2] == [1, 2]
    assert got["match"].tolist() == ["exact", "exact", "none", "none"]


# The 5.02 title, a denied dispute and pay terms are no departure.
def test_502_rule_ignores_title_denials_and_terms():
    title = "Item 5.02 Departure of Directors or Certain Officers. Jane Roe was named CEO."
    assert not text.departure_502(title)["ceo_cfo_leaving"]
    denied = "His resignation was not the result of any disagreement with the directors."
    assert not text.departure_502(denied)["director_disagreement"]
    terms = "If the Chief Executive Officer's employment is terminated, he receives one year."
    assert not text.departure_502(terms)["ceo_cfo_leaving"]


# The cover state may sit before the label, with the ZIP after it.
def test_headquarters_label_between_state_and_zip():
    cover = "500 North Field Drive Lake Forest, IL (Address of principal executive offices) 60045"
    assert text.headquarters(cover) == ("IL", "60045")
    shout = "3500 COLLEGE BOULEVARD LEAWOOD, KANSAS 66211 (Address of principal executive offices)"
    assert text.headquarters(shout) == ("KS", "66211")
    tagged = '<ix:nonNumeric name="dei:EntityAddressStateOrProvince">Minnesota</ix:nonNumeric>'
    assert text.headquarters("", tagged) == ("MN", None)


# A section ends at the next item's heading, not at a mention of it.
def test_section_ends_at_next_heading_not_a_mention():
    doc = (
        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS Read this with the statements in Item 8. "
        + "Sales rose. " * 60
        + "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA Balance sheet."
    )
    got = text.section(doc, "7")
    assert got is not None and got.rstrip().endswith("Sales rose.")


# Headings start their own block; a sentence's cross-reference never.
def test_section_needs_a_heading_that_starts_its_block():
    lines = ["Cover"] * 25
    body = "Sales rose and costs fell this year. " * 20
    doc = "\n".join(
        lines
        + [
            "As noted in Part II and Item 7. Management's Discussion and Analysis of results.",
            "Item 7.",
            "Management's Discussion and Analysis",
            body,
            "Item 7A.",
            "Market risk text.",
        ]
    )
    got = text.section(doc, "7")
    assert got is not None and got.startswith("Item 7.\nManagement")


# HTML source newlines are spaces; block tags end a line.
def test_html_text_reads_source_newlines_as_spaces():
    raw = "<p>Mr. Fine will resign, including his\npositions as Chief Financial Officer.</p><p>Next"
    assert text.html_text(raw) == (
        "Mr. Fine will resign, including his positions as Chief Financial Officer.\nNext"
    )
    assert text.flat("a\nb  c") == "a b c"


# Sentences never break after an initial or "Mr.", always at a block.
def test_sentences_keep_initials_and_titles():
    got = text.sentences(
        "The Company terminated Michael S. Bartusek, its CFO. Mr. Roe stays.\nNext"
    )
    assert got == ["The Company terminated Michael S. Bartusek, its CFO.", "Mr. Roe stays.", "Next"]


# Reported speech counts; another firm's CEO role does not.
def test_502_reported_speech_and_other_firms():
    said = "Mr. Schmitt notified the Company that he would retire as Chief Executive Officer."
    assert text.departure_502(said)["ceo_cfo_leaving"]
    other = (
        "He intends to leave Sabre to accept a position as Chief Executive Officer of a SaaS firm."
    )
    assert not text.departure_502(other)["ceo_cfo_leaving"]
    moved = "Richard Hart, our Chief Financial Officer, will transition to a new role of strategy."
    assert text.departure_502(moved)["ceo_cfo_leaving"]


# Item 2 states by name and by code after a comma or before a ZIP only.
def test_property_states_read_names_and_codes():
    doc = (
        "Item 2. Properties\nPlants in River Falls, WI; Evansville, IN and Gulfport, MS. "
        "Offices in Austin, Texas and Dallas, TX 75201. A plant IN the US. ALL ARE OK.\n"
        "Item 3. Legal Proceedings\nNone."
    )
    assert text.property_states(doc) == ["WI", "IN", "MS", "TX"]


# Boilerplate is stripped in any spelling of "forward-looking".
def test_boilerplate_catches_spelling_variants():
    for line in (
        "These forward looking statements are risky.",
        "Forward\u2011looking information.",
    ):
        assert text.strip_boilerplate(line + " Sales rose.") == "Sales rose."
