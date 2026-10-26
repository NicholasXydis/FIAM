# Binding decisions stay enforced in config and code (DECISIONS.md).

import json
from pathlib import Path

import pytest

from fiam.v4b.engine import mandate

ROOT = Path(__file__).resolve().parents[1]


# D6: the config names E-LASSO, MaInf primary, Ma1 alternate.
def test_forecaster_is_elasso():
    m = mandate.load()
    assert m.policy.forecaster == "elasso"
    assert m.policy.forecaster_column == "Elasso_MaInf"
    assert m.policy.forecaster_alternate == "Elasso_Ma1"


# D6: a config naming another forecaster is refused at load.
def test_other_forecaster_is_refused(tmp_path):
    raw = json.loads(mandate.FINAL.read_text())
    raw["policy"]["forecaster"] = "mlp"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="D6"):
        mandate.load(path)


# D6: the authors' code is unchanged (checksums).
def test_elasso_code_unchanged():
    from fiam.v4b.elasso import forecaster

    forecaster.verify_code()


# D6 is written in every governing document.
@pytest.mark.parametrize(
    "doc",
    [
        "DECISIONS.md",
        "REVISED_PLAN.md",
        "CONTINUATION_PLAN.md",
        "LESSONS.md",
        "README.md",
        "EVALUATION.md",
    ],
)
def test_documents_record_the_decision(doc):
    assert "E-LASSO" in (ROOT / doc).read_text()
