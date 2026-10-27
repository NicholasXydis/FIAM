# The exhibits on synthetic tables: files, punctuation, hand checks.

import math

import matplotlib
import numpy as np
import pandas as pd
import pytest

from fiam.vfinal.exhibits import common, extras, required, synthetic
from fiam.vfinal.exhibits.build import build
from fiam.vfinal.report import table_9_1

# Every exhibit's file stem: the PDF's eight, then the extras.
STEMS = [name for name, _ in required.EXHIBITS + extras.EXTRAS]
# A flat daily return for the hand checks: 3 basis points a session.
FLAT = 0.0003


# One synthetic run and its meta, built once for the module.
@pytest.fixture(scope="module")
def run():
    return synthetic.tables()


# The synthetic set written once, as the deck would read it.
@pytest.fixture(scope="module")
def written(run, tmp_path_factory):
    out = tmp_path_factory.mktemp("exhibits")
    return out, build(run[0], out, run[1])


# A copy of the run with the daily table changed by `edit`.
def edited(run, edit) -> dict:
    tables = dict(run[0])
    daily = tables["daily"].copy()
    edit(daily)
    daily["nav"] = synthetic.NAV * (1 + daily["ret"]).cumprod()
    tables["daily"] = daily
    return tables


# One exhibit drawn alone, its figure closed, its numbers returned.
def frame_of(tables: dict, meta: dict, draw) -> pd.DataFrame:
    x = common.prepare(tables, meta)
    with matplotlib.rc_context({"text.parse_math": False}):
        fig, frame = draw(x)
    matplotlib.pyplot.close(fig)
    return frame


# All eight exhibits and the extras exist as PNG, SVG and CSV.
def test_every_exhibit_is_written(written):
    out, paths = written
    for stem in STEMS:
        for suffix in (".png", ".svg", ".csv"):
            path = out / f"{stem}{suffix}"
            assert path in paths and path.stat().st_size > 0, path.name
    assert (out / "manifest.json") in paths
    assert len([s for s in STEMS if s.startswith("exhibit_")]) == 8


# No dash, colon, semicolon or Oxford comma in any title or label.
def test_no_forbidden_punctuation(run):
    x = common.prepare(*run)
    with matplotlib.rc_context({"text.parse_math": False}):
        for name, draw in required.EXHIBITS + extras.EXTRAS:
            fig, _ = draw(x)
            fig.canvas.draw()
            titles = [fig.get_suptitle()] + [ax.get_title(loc="left") for ax in fig.axes]
            for text in [t for t in titles if t] + common.texts(fig):
                assert not common.FORBIDDEN.search(text), (name, text)
                assert not common.OXFORD.search(text), (name, text)
            matplotlib.pyplot.close(fig)


# The guard refuses a planted colon and an Oxford comma.
@pytest.mark.parametrize("title", ["Returns: net", "Gross, net, and names", "2021 – 2026"])
def test_guard_refuses_bad_copy(title):
    fig, ax = matplotlib.pyplot.subplots()
    ax.set_title(title)
    with pytest.raises(ValueError, match="forbidden punctuation"):
        common.check_text(fig)
    matplotlib.pyplot.close(fig)


# Exhibit 1: a flat return against a zero bill, compounded by hand.
def test_active_return_by_hand(run):
    # Every session earns FLAT and the bill is zero.
    def flat(d):
        d["ret"], d["rf"] = FLAT, 0.0
        d.iloc[0, d.columns.get_loc("ret")] = 0.0

    tables = edited(run, flat)
    frame = frame_of(tables, run[1], required.active_return)
    sessions = len(frame)
    months = frame.index.to_period("M").nunique()
    want = ((1 + FLAT) ** sessions - (1 + 0.04 / 12) ** months) * 100
    assert months == 68
    assert frame["active"].iloc[-1] == pytest.approx(want, abs=1e-9)
    # The same number as the 23-row table's row 2, strategy less benchmark.
    rows = table_9_1.table(tables["daily"], tables["trades"], tables["positions"],
                           tables["bench"]).set_index("row")  # fmt: skip
    gap = rows.loc[2, "strategy"] - rows.loc[2, "benchmark"]
    assert frame["active"].iloc[-1] == pytest.approx(gap, abs=1e-9)


# Exhibit 2: a book built as 0.3 times the market has beta 0.3.
def test_rolling_beta_by_hand(run):
    sp = run[0]["bench"]

    # The book's excess return is exactly 0.3 of the market's.
    def tied(d):
        d["ret"] = d["rf"] + 0.3 * (sp.reindex(d.index).to_numpy() - d["rf"])

    frame = frame_of(edited(run, tied), run[1], required.rolling_beta)
    beta = frame["beta_252d"].dropna()
    assert len(beta) == len(frame) - 251
    assert np.allclose(beta, 0.3, atol=1e-9)


# Exhibit 4: a flat 170% gross and 430 names read back exactly.
def test_exposure_by_hand(run):
    # Gross 170% and net 2% on every close.
    def flat(d):
        d["gross"], d["net"] = 1.7, 0.02

    frame = frame_of(edited(run, flat), run[1], required.exposure)
    assert frame["gross"].mean() == pytest.approx(170.0)
    assert frame["net"].max() == pytest.approx(2.0)
    assert frame["names"].min() == frame["names"].max() == synthetic.LONGS + synthetic.SHORTS


# The fundamental law: implied IR is IC x root breadth x TC a period.
def test_fundamental_law_by_hand(written):
    out, _ = written
    k1 = pd.read_csv(out / "extra_k1_fundamental_law.csv").set_index("period")
    assert k1.loc["2017 to 2020", "implied_ir"] == pytest.approx(0.031 * np.sqrt(1900) * 0.46)


# The law is skipped and recorded when its inputs are not supplied.
def test_k1_skipped_without_inputs(run, tmp_path):
    tables = {k: v for k, v in run[0].items() if k != "k1"}
    paths = build(tables, tmp_path, run[1])
    assert not (tmp_path / "extra_k1_fundamental_law.png").exists()
    assert len([p for p in paths if p.suffix == ".png"]) == len(STEMS) - 1


# Capacity: the synthetic spill splits exactly the trades over the cap.
def test_capacity_held_back(run):
    x = common.prepare(*run)
    plan = extras.planned_trades(x)
    assert plan["held_back"].sum() > 0
    assert (plan["held_back"] == (plan["closes"] > 1)).all()


# Labels follow the ids table as of the date, state tags removed.
def test_labels_as_of(run):
    when = pd.DataFrame({"permno": [10001, 10001], "date": ["2022-01-03", "2024-01-02"]})
    got = common.labels(run[0]["ids"], when)["label"].tolist()
    assert got == ["AAA, SYNTHETIC HOLDINGS 0 INC", "AAAX, RENAMED GROUP 0 CORP"]


# 2026 compounds its own sessions only, never annualised.
def test_sub_period_compounds_2026(written, run):
    out, _ = written
    frame = pd.read_csv(out / "extra_2026_sub_period.csv", index_col=0)
    d = run[0]["daily"]
    want = ((1 + d.loc[d.index.year == 2026, "ret"]).prod() - 1) * 100
    assert frame.loc["Return (%)", "2026 Jan to Aug"] == pytest.approx(want)


# VaR the 5th percentile, CVaR the mean of the ceil(5%) worst months.
def test_cvar_tail_by_hand(run):
    x = common.prepare(*run)
    m = (1 + x.d[["ret", "rf"]]).groupby(x.d.index.to_period("M")).prod() - 1
    active = ((m["ret"] - (m["rf"] + table_9_1.PREMIUM / 12)) * 100).to_numpy()
    k = math.ceil(0.05 * len(active))
    frame = frame_of(*run, extras.cvar_tail)
    assert frame.attrs["k"] == k and frame["in_tail"].sum() == k
    assert frame.attrs["var95"] == pytest.approx(np.quantile(active, 0.05))
    assert frame.attrs["cvar95"] == pytest.approx(np.sort(active)[:k].mean())
    assert frame.attrs["worst"] <= frame.attrs["cvar95"] <= frame.attrs["var95"]
