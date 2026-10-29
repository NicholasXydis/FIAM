# The final book's triage and analyst checks, without a model.

import pandas as pd

from fiam.agents import analyst, triage
from fiam.agents import final_book as F


# Numbers are read as printed, commas and trailing zeros made plain.
def test_numbers_are_normalised():
    said = "Revenue rose to $1,234.50 million, up 12.0% from 7 in Q2 2026."
    assert F.numbers(said) == ["1234.5", "12", "7", "2026"]


# A point quoting a number the source never prints is dropped.
def test_number_check_drops_unsupported_points():
    source = "Net revenues were $2,345 million, up 14.8% on 2025."
    kept, dropped = F.number_check(["Revenue grew 14.8%.", "Revenue grew 15%."], source)
    assert kept == ["Revenue grew 14.8%."]
    assert dropped == [dict(text="Revenue grew 15%.", unsupported_numbers=["15"])]


# Acceptance after the book's last minute, Eastern time, is left out.
def test_public_by_cuts_at_the_end_of_the_book_day():
    accepted = ["2026-08-31T21:59:00.000Z", "2026-09-01T00:35:08.000Z"]
    seen = F.public_by(accepted, ["2026-08-31", "2026-08-31"])
    assert seen.tolist() == [True, False]


# The triage format check names a missing field or a bad value.
def test_triage_format_check():
    good = dict(event_type="earnings_results", tone="good", materiality="high", summary="Beat.")
    assert triage.format_check(good) is None
    assert "tone" in triage.format_check(good | dict(tone="great"))
    assert "fields" in triage.format_check({k: v for k, v in good.items() if k != "summary"})
    assert triage.format_check(good | dict(summary=" ")) is not None


# Labels agree with item codes only where an item has a usual event.
def test_items_agree():
    assert triage.items_agree("2.02,9.01", "earnings_results") is True
    assert triage.items_agree("5.07", "earnings_results") is False
    assert triage.items_agree("8.01", "other") is None


# Side counts, shares and the top events by materiality then size.
def test_final_summary_counts_and_ranks():
    rows = [
        ("A", "long", 0.04, "good", "high"),
        ("B", "long", 0.01, "bad", "high"),
        ("C", "short", -0.01, "bad", "medium"),
        ("D", "short", -0.02, "neutral", "low"),
    ]
    labels = pd.DataFrame(
        [
            dict(
                permno=i,
                ticker=t,
                company_name=t,
                side=s,
                w=w,
                tone=tone,
                materiality=m,
                event_type="other",
                summary="x",
                filing_date="2026-07-01",
                accepted="2026-07-01T10:00:00.000Z",
                accession=f"0-{i}",
                items="8.01",
                document="d.htm",
                cik=i,
                items_agree=None,
                check=None,
            )
            for i, (t, s, w, tone, m) in enumerate(rows)
        ]
    )
    held = labels[["ticker", "side"]]
    out = triage.final_summary(labels, held)
    assert out["by_side"]["long"]["share_good"] == 0.5
    assert out["by_side"]["short"]["share_bad"] == 0.5
    assert [t["ticker"] for t in out["top_five"]] == ["A", "B", "C", "D"]
    assert out["top_five"][0]["for_our_side"] is True
    assert out["share_for_our_side"] == round(2 / 3, 4)


# Quarterly MD&A and risk factors are cut at the next item heading.
def test_quarterly_sections():
    filler = "The business did well this quarter and costs were steady.\n" * 20
    text = (
        "PART I\nItem 2. Management's Discussion and Analysis of Financial Condition\n"
        + filler
        + "Item 3. Quantitative and Qualitative Disclosures About Market Risk\nRates.\n"
        + "PART II\nItem 1A. Risk Factors\n"
        + filler
        + "Item 2. Unregistered Sales of Equity Securities\nNone.\n"
    )
    mdna = analyst.quarterly_section(text, "mdna")
    risk = analyst.quarterly_section(text, "risk")
    assert mdna.startswith("Item 2. Management") and "Quantitative" not in mdna
    assert risk.startswith("Item 1A. Risk") and "Unregistered" not in risk


# The analyst check refuses a bad shape and drops unsupported numbers.
def test_analyst_checked():
    source = "Revenue was $5.2 billion, up 9%."
    answer = dict(
        supports=["Revenue was $5.2 billion.", "Revenue rose 11%."],
        challenges=[],
        balance="supports",
        summary="Revenue grew 9%.",
    )
    result, problem = analyst.checked(answer, source)
    assert problem is None
    assert result["supports"] == ["Revenue was $5.2 billion."]
    assert result["dropped"][0]["unsupported_numbers"] == ["11"]
    assert analyst.checked(answer | dict(balance="great"), source)[1] is not None


# A percentage must be printed as one, brackets of a table allowed.
def test_number_check_wants_percent_as_percent():
    source = "Sales fell (37.2) % to 15 stores."
    kept, dropped = F.number_check(["Sales fell 37.2%.", "Sales fell 15%."], source)
    assert kept == ["Sales fell 37.2%."]
    assert dropped[0]["unsupported_numbers"] == ["15%"]
