# The explainer, rules check and crowd study steps, without a model.

import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

from fiam.agents import crowd_aug as C
from fiam.agents import explainer as E
from fiam.agents import explainer_facts as EF
from fiam.agents import final_book as F
from fiam.agents import harness as H
from fiam.agents import rules_check as R

# The fund's hard limits as the rules check reads them.
R_HARD = dict(gross=2.0, net=0.5, name_cap=0.05, names_min=200, names_max=500, sector_net=0.2)


# One name's facts, as small as the render step accepts.
def one_fact(**over) -> dict:
    drivers = dict(
        available=True,
        formation_month_end="2026-06-30",
        forecast_z=1.2,
        forecast_percentile=88,
        stocks_scored=2000,
        regime_dial_rho=0.8,
        top_drivers_up=[
            dict(
                characteristic="Book-to-market equity",
                stock_value_z=1.5,
                stock_percentile=91,
                model_rewards="higher",
                contribution_to_forecast_z=0.42,
            )
        ],
        top_drivers_down=[],
    )
    f = dict(
        permno=10001,
        ticker="ABC",
        company="ABC CORP",
        listed_because="top-10 long in the 2026-08-31 book",
        rank_in_list=1,
        rank_basis="weight on 2026-08-31",
        side="LONG",
        spell_in_view=dict(
            which="the spell held on 2026-08-31",
            entered="2026-01-05",
            exited="2026-08-31",
            side="LONG",
            avg_weight_pct=1.5,
            stock_return_pct=12.3,
            pnl_musd=4.56,
        ),
        holding_spells=1,
        trading_days_held=160,
        first_entered="2026-01-05",
        last_held="2026-08-31",
        still_held_on_2026_08_31=False,
        pnl_musd=4.56,
        pnl_long_days_musd=4.56,
        pnl_short_days_musd=0.0,
        pnl_by_year_musd={"2026": 4.56},
        engine_ledger_price_pnl_musd=4.5,
        dividends_musd=0.1,
        trading_cost_musd=0.02,
        borrow_cost_musd=0.0,
        avg_weight_while_held_pct=1.5,
        max_abs_weight_pct=2.0,
        weight_on_2026_08_31_pct=1.9,
        stock_return_while_held_pct=12.3,
        entry_formation=dict(
            decision_date="2025-12-31",
            kind="month-end",
            model=drivers,
            forecast_points_same_way_as_trade=True,
        ),
    )
    return f | over


# Numbers trace at their precision; small ones and percents pass.
def test_explainer_number_check():
    shown = "earned 44.92 a share of 0.123 and 19,169,939 names"
    assert E.numbers("19,169,939 and -0.5") == ["19169939", "-0.5"]
    assert E.unsupported("$44.92 million, 12.3%, 44.9, 0.7 and 19,169,939", shown) == []
    assert E.unsupported("It made $45.1 million on 7 names", shown) == ["45.1", "7"]


# Ordinals, money words and the answer key read as the record shows.
def test_explainer_words():
    assert [E.nth(n) for n in (1, 2, 3, 11, 12, 13, 21, 43, 100)] == [
        "1st", "2nd", "3rd", "11th", "12th", "13th", "21st", "43rd", "100th"
    ]  # fmt: skip
    assert E.money(-3.2) == "lost $3.2 million" and E.money(0.0) == "earned $0.0 million"
    assert E.key_of(one_fact()) == "10001_2026-01-05_LONG"


# The render step pairs each answer with its facts and flags a bad one.
def test_explainer_render(tmp_path, monkeypatch):
    good, bad = one_fact(), one_fact(permno=10002, ticker="XYZ", company="XYZ INC")
    monkeypatch.setattr(E, "FACTS", tmp_path / "facts.json")
    monkeypatch.setattr(E, "RAW", tmp_path / "raw.json")
    E.FACTS.write_text(json.dumps(dict(names=[good, bad], fund={})))
    raw = {
        E.key_of(good): dict(why="Held for value.", numbers_supported=True, unsupported_numbers=[]),
        E.key_of(bad): dict(why="Made 9.9.", numbers_supported=False, unsupported_numbers=["9.9"]),
    }
    E.RAW.write_text(json.dumps(raw))
    items = E.render(tmp_path / "out.json", tmp_path / "out.md")
    assert list(items[0])[:3] == ["list", "rank", "rank_basis"]
    assert [i["explanation"] for i in items] == ["Held for value.", "Made 9.9."]
    md = (tmp_path / "out.md").read_text()
    assert "### 1. ABC Abc Corp (LONG)" in md and "NO, unsupported ['9.9']" in md
    assert "Book-to-market equity (stock z 1.5, model rewards higher, +0.42)" in md
    meta = json.loads((tmp_path / "out.json").read_text())["meta"]
    assert meta["fund"] == "QUARCC Purple (run bw_fresh_lag)"


# What the model sees drops bookkeeping and names every list it is on.
def test_explainer_facts_shown():
    rows = [one_fact(), one_fact(listed_because="top-10 positive contributor 2021-2026")]
    f = E.explainer_facts(rows)
    assert f["listed_because"][1] == "top-10 positive contributor 2021-2026 (#1)"
    assert "permno" not in f and "rank_basis" not in f and f["units"] == E.UNITS
    text = E.readable(f)
    assert "high Book-to-market equity (91st percentile), which raised" in text
    assert "pointed the same way as the trade" in text


# A side flip starts a new spell, and a gap ends one.
def test_spells_split_on_flips_and_gaps():
    days = pd.date_range("2026-01-01", periods=7)
    v = pd.Series([0, 5, 5, -3, 0, 2, 2], index=days, dtype=float)
    got = [(a.day, b.day) for a, b in EF.spells(v)]
    assert got == [(2, 3), (4, 4), (6, 7)]


# A quote finds its page whatever the PDF does to dashes and spaces.
def test_rules_quote_page_and_compare():
    pages = ["Intro", "Net within −50% to +50%\nat all times", "Gross 2×"]
    assert R.page_of("Net within -50% to +50% at all times", pages) == 2
    assert R.page_of("gross 2x", pages) == 3 and R.page_of("absent", pages) is None
    limits = R.fund_limits(dict(gross=2.0, sector_cap=None), R_HARD)
    assert R.compare("gross", 2, limits)["agreeing"] == ["finals_2026.json gross", "HARD gross"]
    assert R.compare("sector", 0.2, limits)["agreeing"] == ["HARD sector_net"]
    assert R.compare("net", 0.5, limits) == dict(status="no_fund_limit", fund=None)
    assert R.compare("long_only", True, limits)["status"] == "mismatch"


# The fact-sheet line names a misfiled band only when the limits hold.
def test_rules_lines():
    assert R.lines(15, 15, True, True)["fund_fact_line"] == "15 rules read, all match"
    assert R.lines(15, 13, False, True)["headline"].endswith("after one misfiled net band")
    assert R.lines(15, 13, False, False)["fund_fact_line"] == "15 rules read, 13 match"


# Weighted crowd percentiles skip names the crowd did not score.
def test_crowd_snapshot():
    w = pd.Series([0.02, 0.01, -0.01, -0.03], index=[1, 2, 3, 4])
    month = pd.DataFrame(dict(permno=[1, 2, 3], pct=[0.95, 0.5, 0.05]))
    s = C.snapshot(w, month)
    assert (s["longs"], s["shorts"], s["unscored"]) == (2, 2, 1)
    assert np.isclose(s["long_mean_pct"], (0.02 * 0.95 + 0.01 * 0.5) / 0.03)
    assert np.isclose(s["long_in_top_decile"], 2 / 3) and s["short_in_bottom_decile"] == 1.0
    assert np.isnan(C.wmean(pd.Series([np.nan]), pd.Series([1.0])))


# Each step writes its record under finals/ai, the rest under cache/.
def test_record_and_work_paths():
    for out in (E.OUT_JSON, E.OUT_MD, R.OUT, C.OUT):
        assert out.is_relative_to(F.PACK)
    for work in (E.WORK, R.WORK, C.RUNS):
        probe = work / "crowdlab_retail.jsonl"
        ignored = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=H.ROOT)
        assert ignored.returncode == 0, work
    assert R.LOCKED == H.ROOT / "frozen" / "vfinal" / "finals_2026.json"


# Loading these steps leaves the older panel reader out of blind mode.
def test_steps_leave_blind_mode_off():
    env = {k: v for k, v in os.environ.items() if k != "FIAM_BLIND"}
    code = (
        "import os\n"
        "from fiam.agents import crowd_aug, explainer, rules_check\n"
        "print(os.environ.get('FIAM_BLIND'))\n"
    )
    run = subprocess.run(
        [sys.executable, "-c", code], cwd=H.ROOT, env=env, capture_output=True, text=True
    )
    assert run.stdout.strip() == "None", run.stderr
