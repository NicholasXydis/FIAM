# The desk agents' checks, flags and answers, without a model.

import json

from fiam.agents import desk as D
from fiam.agents import devil, found, memo, risk_desk


# A rounded, percent or thousands form of a shown value is supported.
def test_numbers_trace_at_their_precision():
    values = D.shown('{"ir": -0.107492, "end": 1.467074, "share": 0.0538, "hurdle": 1.508714}')
    for said in ("0.11", "1.467", "1.47", "5.38", "1,467", "1.509"):
        assert D.supported(said, values), said
    for said in ("0.12", "1.466", "5.5", "42"):
        assert not D.supported(said, values), said
    assert D.unsupported("IR −0.11 on $1.467bn, not 2.5", values) == ["2.5"]


# A sentence with an unsupported number or a banned phrase is dropped.
def test_check_drops_bad_sentences():
    values = D.shown('{"ir": -0.11, "vol": 3.96}')
    text = (
        "The IR was -0.11. Volatility was 4.2%. Results were out of sample. "
        "We should trim the largest long. Volatility was 3.96%."
    )
    kept, dropped = D.check(text, values, advice=True)
    assert kept == "The IR was -0.11. Volatility was 3.96%."
    assert [d["text"] for d in dropped] == [
        "Volatility was 4.2%.",
        "Results were out of sample.",
        "We should trim the largest long.",
    ]
    assert dropped[0]["unsupported_numbers"] == ["4.2"]
    kept, _ = D.check("We should trim the largest long.", values, advice=False)
    assert kept == "We should trim the largest long."


# Version names, tries and the selection line never pass.
def test_honesty_words_are_caught():
    for said in (
        "The vfinal book did well.",
        "Of the variants we tried this was best.",
        "It was chosen after the data.",
        "The design was fixed before 2021.",
        "The 61st Investor agrees.",
    ):
        assert D.breaks(said, advice=False), said
    assert D.breaks("The record runs from 2021 to 2026.", advice=False) == []
    assert D.breaks("The crowd sell-off test loses little.", advice=True) == []


# Audience copy loses dashes, colons, semicolons and Oxford commas.
def test_plain_copy():
    assert D.plain("Risk: low; beta — small") == "Risk, low. Beta, small"
    assert D.plain("From 2021–2026") == "From 2021 to 2026"
    assert D.plain("Longs, shorts, and cash.") == "Longs, shorts and cash."
    assert D.screen_ok("8 AI agents check and none sets a trade", 76)
    assert not D.screen_ok("Agents: 8", 76)
    assert not D.screen_ok("x" * 77, 76)
    assert [D.nth(k) for k in (1, 2, 3, 11, 51, 57)] == [
        "1st",
        "2nd",
        "3rd",
        "11th",
        "51st",
        "57th",
    ]


# Facts for the flags, small enough to read in a test.
def book(**change) -> dict:
    f = dict(
        names=326,
        gross_pct=186.0,
        net_pct=0.66,
        largest_long=dict(ticker="AAA", weight_pct=4.02),
        largest_short=dict(ticker="BBB", weight_pct=-1.16),
        top10_long_share_of_long_gross=0.354,
        effective_names=140.0,
        sector_net_max=dict(sector="Industrials", net_pct=1.75),
        sectors_held=11,
        history=dict(beta=0.025, realised_beta_252d=-0.01, realised_vol_63d_pct=5.55, vol_pct=5.2),
        liquidity=dict(
            sessions_to_exit_max=3.68,
            sessions_limit=5,
            participation=0.1,
            days_of_volume_max=0.37,
        ),
        crowd=dict(
            crowd_beta=0.09,
            crowd_beta_t=2.66,
            long_percentile=57,
            short_percentile=51,
            sell_off_worst_pct_nav=-0.34,
            sell_off_worst_case="crowd model selling $100bn",
        ),
        carbon_arc=dict(
            longs_in_hype=6,
            shorts_in_hidden_gems=21,
            longs_with_growth=31,
            shorts_with_growth=60,
            long_spend_growth_pct=5.38,
            short_spend_growth_pct=5.45,
            crowd_favourites_in_hype=10,
            crowd_favourites_with_growth=37,
        ),
        worst_month_pct=-1.43,
    )
    return f | change


# Code sets each level from the finals limits and the fund's own caps.
def test_flag_levels():
    levels = {x["id"]: x["level"] for x in risk_desk.flags(book())}
    assert levels["gross"] == "watch"
    assert levels["net"] == "ok"
    assert levels["largest_long"] == "watch"
    assert levels["beta"] == "watch"
    assert levels["volatility"] == "ok"
    assert levels["liquidity"] == "ok"
    assert levels["crowd_exposure"] == "watch"
    assert levels["crowd_sell_off"] == "ok"
    assert levels["carbon_arc"] == "info"
    worse = book(gross_pct=201.0, largest_long=dict(ticker="AAA", weight_pct=5.2), names=190)
    levels = {x["id"]: x["level"] for x in risk_desk.flags(worse)}
    assert levels["gross"] == levels["largest_long"] == levels["names"] == "alert"


# The Carbon Arc flag carries counts and aggregates, never a ticker.
def test_carbon_arc_flag_has_counts_only():
    flag = next(x for x in risk_desk.flags(book()) if x["id"] == "carbon_arc")
    assert flag["value"] == "6 and 21"
    assert "AAA" not in flag["rule"] and "BBB" not in flag["rule"]


# Evidence for the answers, built from the same small facts.
def evidence() -> dict:
    return dict(
        fund=dict(
            ending_value_billion=1.467,
            hurdle_ending_value_billion=1.509,
            shortfall_million=41.6,
            information_ratio=-0.11,
            information_ratio_standard_error=0.42,
            information_ratio_before_costs=0.0,
            information_ratio_flat_costs=-0.27,
            long_leg_million=859.0,
            short_leg_million=-601.3,
            shorted_stocks_rise_pct=73.5,
            trading_costs_million=9.5,
            borrow_million=20.6,
            costs_share_of_shortfall_pct=72,
            beta_monthly=0.012,
            worst_month_pct=-1.43,
            limit_breach_days=0,
            sharpe=0.91,
            worst_year=2025,
            worst_year_fund_pct=2.08,
            worst_year_hurdle_pct=8.37,
        ),
        book=dict(
            date="2026-08-31",
            names=326,
            longs=140,
            shorts=186,
            largest_long_pct=4.02,
            largest_short_pct=-1.16,
            top10_long_share_pct=35.4,
            beta_of_weights=0.025,
            sessions_to_exit_max=3.68,
            sessions_limit=5,
            gross_pct=185.99,
            gross_limit_pct=200,
            net_pct=0.66,
            largest_sector_net_pct=1.75,
        ),
        ai_crowd=dict(
            long_percentile_average=66,
            short_percentile_average=56,
            average_from="2021-01",
            average_to="2026-08",
            long_percentile_2026_08=57,
            short_percentile_2026_08=51,
            crowd_factor_beta=0.09,
            crowd_factor_t=2.66,
            sell_off_worst_pct_of_capital=-0.34,
            sell_off_worst_case="crowd model selling $100bn",
            pnl_where_book_agreed_with_crowd_million=550.6,
            pnl_where_book_disagreed_million=-285.3,
        ),
        carbon_arc_counts=book()["carbon_arc"]
        | dict(split_p_value=0.99, longs_in_hype_strong=1, shorts_in_hidden_gems_strong=12),
        news_8k="not ready",
        analyst_reports=dict(
            balance_by_side=dict(
                long=dict(supports=6, mixed=3, challenges=1),
                short=dict(supports=2, mixed=4, challenges=4),
            )
        ),
        rules=dict(rules_read=15, matched=13),
    )


# Every topic gets a code answer with numbers from the evidence alone.
def test_answers_come_from_the_evidence():
    ev = evidence()
    values = D.shown(json.dumps(ev))
    for topic in devil.TOPICS:
        text, verdict = devil.answer(topic, ev)
        assert verdict in ("stands", "partly stands", "does not stand", "no data"), topic
        assert D.unsupported(text, values) == [], (topic, text)
    assert devil.answer("news", ev)[1] == "no data"
    assert devil.answer("hurdle", ev)[1] == "stands"
    assert devil.answer("reports", ev)[1] == "partly stands"
    strong = dict(supports=8, mixed=2, challenges=0)
    ev["analyst_reports"]["balance_by_side"] = dict(long=strong, short=strong)
    assert devil.answer("reports", ev)[1] == "does not stand"
    assert "lost $285.3 million" in devil.answer("crowding", ev)[0]


# The letter's overlap with other texts counts shared word triplets.
def test_letter_overlap():
    assert memo.overlap("The fund made money in 2023.", []) == 0.0
    said = "The fund made money in 2023."
    assert memo.overlap(said, ["Indeed the fund made money in 2023 again."]) == 1.0


# Each finding fits the screen rules, and a missing file is pending.
def test_found_lines(tmp_path):
    crowd = dict(round=dict(long_pct=57, short_pct=51, beta=0.09))
    finding, key = found.crowd(crowd)
    assert D.screen_ok(finding, found.FINDING_CHARS)
    assert key == "crowd beta 0.09"
    risk = dict(levels=dict(alert=0, watch=5, ok=7, info=1), flags=[{}] * 13)
    finding, _ = found.risk(risk)
    assert finding.endswith("no finals limit broken")
    assert found.entry(tmp_path / "missing.json", found.crowd) == "pending"


# A sentence that puts a number on the other side of a limit is caught.
def test_wrong_sides():
    assert D.wrong_sides("The loading of 0.09 is above the watch level of 2.") == ["0.09 above 2"]
    assert D.wrong_sides("The 1.75% net is within the band of 1%.") == ["1.75 within 1"]
    assert D.wrong_sides("Its t statistic of 2.66 is above the level of 2.") == []
    assert D.wrong_sides("Net 0.66% is inside the band of minus 50% to plus 50%.") == []
    kept, dropped = D.check("A 1.75% net is within a 1% band.", [1.75, 1.0], sides=True)
    assert kept == "" and dropped[0]["broken_rules"] == ["wrong side 1.75 within 1"]


# Saying what a number suggests is not advice; telling anyone to act is.
def test_advice_is_narrow():
    assert D.breaks("A standard error of 0.42 suggests the result is noise.", advice=True) == []
    assert D.breaks("This suggests that we trim the long.", advice=True)
    assert D.breaks("The committee may consider a hedge.", advice=True)


# The attack facts trace to the evidence and skip missing agents.
def test_readable_evidence():
    ev = evidence()
    lines = devil.readable(ev)
    values = D.shown(json.dumps(ev))
    assert "news" not in lines and "reports" in lines
    for topic, text in lines.items():
        assert topic in devil.TOPICS
        assert D.unsupported(text, values) == [], (topic, text)
        assert D.screen_ok(text, 10_000), text


# The other agents' lines fit the screen and carry their number.
def test_found_lines_for_other_agents():
    side = dict(supports=7, mixed=3, challenges=0)
    finding, key = found.analyst(dict(names_read=20, balance_by_side=dict(long=side, short=side)))
    assert finding.endswith("14 support our side, 6 are mixed and 0 challenge it")
    assert key == "14 of 20"
    finding, key = found.triage(dict(share_for_our_side=0.5432, filings=dict(labelled=987)))
    assert "54%" in finding and key == "987 8-Ks"
    finding, key = found.rules(dict(rules_read=15, matched=13))
    assert key == "13 of 15"
    assert D.screen_ok(finding, found.FINDING_CHARS)
    assert D.screen_ok(found.fact_line(), found.FACT_LINE_CHARS)


# Describing a change is not advice; asking for one is.
def test_advice_needs_an_ask():
    said = "The fund is increasing its market sensitivity, with weights carrying 0.025."
    assert D.breaks(said, advice=True) == []
    assert D.breaks("The crowd would sell its favourites.", advice=True) == []
    assert D.breaks("It may be wise to cut the gross.", advice=True)
    assert D.breaks("We need to sell the short.", advice=True)


# How long a name takes to exit is a fact, not advice.
def test_exit_time_is_not_advice():
    said = "The slowest name takes 3.68 sessions to exit, below the limit of 5 sessions."
    assert D.breaks(said, advice=True) == []
