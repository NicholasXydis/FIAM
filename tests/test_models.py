# Models, hedge and agent plumbing on tiny inputs, no data, no network.

import importlib
from operator import itemgetter

import numpy as np
import pandas as pd

from fiam import book as P


# Crowd cards: codes, percentiles and filings, no name, ticker or date.
def test_crowd_cards_carry_no_names_or_dates():
    crowd = importlib.import_module("fiam.agents.crowd")
    C = importlib.import_module("fiam.ml.crowd")
    batch = pd.DataFrame(
        [
            dict(
                permno=12490,
                eom=pd.Timestamp("2016-03-31"),
                **{c: 50 for c in C.CARD},
                **{e: 0 for e in C.EVENTS},
            )
        ]
    )
    text = crowd.table(batch, ["S01"])
    assert "12490" not in text and "2016" not in text
    assert text.splitlines()[1].startswith("S01")


# The rehearsal uses the tiny model; a machine can be chosen by hand.
def test_harness_resolves_models_and_machines(monkeypatch):
    harness = importlib.import_module("fiam.agents.harness")
    monkeypatch.setattr(harness.paths, "SMOKE", True)
    assert harness.resolve("qwen") == "tiny"
    monkeypatch.setenv("FIAM_LLAMA_BUILD", "linux-cpu")
    assert harness.machine() == "linux-cpu"
    assert all(len(sha) == 64 for builds in harness.BUILDS.values() for _, sha in builds)


# Text components fit on training rows only; test rows cannot move them.
def test_text_components_fit_on_training_rows_only():
    text = importlib.import_module("fiam.ml.text")
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(800, text.WIDTH)).astype(np.float32)
    matrix[700:, 0] = np.nan
    train = np.arange(800) < 500
    first = text.components(matrix, train)
    shifted = matrix.copy()
    shifted[500:700] += 100.0
    second = text.components(shifted, train)
    assert np.allclose(first[:500], second[:500], atol=1e-4)
    assert np.isnan(first[700:]).all()


# The answer log resumes: a second session sees what the first saved.
def test_agent_answers_resume(tmp_path, monkeypatch):
    harness = importlib.import_module("fiam.agents.harness")
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    with harness.answers("demo", itemgetter("id")) as (done, save):
        save(dict(id="a", label="good"))
    with harness.answers("demo", itemgetter("id")) as (done, _):
        assert done == {"a": dict(id="a", label="good")}


# Only analyst verdicts before the evaluation's first decision teach.
def test_analyst_verdicts_from_the_evaluation_never_teach():
    learned = importlib.import_module("fiam.ml.analyst")
    eom = pd.to_datetime(["2020-10-31", "2020-11-30", "2020-12-31", "2023-05-31"])
    verdicts = pd.DataFrame(dict(permno=1, eom=eom, analyst_conviction=[1.0, np.nan, 2.0, -1.0]))
    assert learned.taught(verdicts)["eom"].tolist() == [pd.Timestamp("2020-10-31")]


# A toy month with one sector and one beta, so neutralizing keeps order.
def toy_month(n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        dict(
            eom=pd.Timestamp("2022-06-30"),
            permno=range(n),
            composite=rng.normal(size=n),
            score=rng.normal(size=n),
            sector="10",
            beta_60m=1.0,
            rvol_21d=rng.uniform(0.01, 0.04, n),
            dolvol_126d=rng.uniform(1e6, 1e8, n),
        )
    )


# The shipped book hedges on the teacher's beta, else the 60-month beta.
def test_shipped_book_hedges_on_the_learned_beta():
    month = toy_month(4)
    month["hedge_beta"] = month["beta_60m"]
    inputs = month[["permno", "eom"]].assign(beta_hat=[0.5, None, 1.5, 0.9])
    out = P.hedged(month, inputs)
    assert out["hedge_beta"].tolist() == [0.5, 1.0, 1.5, 0.9]
    assert P.hedged(month, None) is month
