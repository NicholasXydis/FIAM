# Version recipes match the code, and closed versions never change.

import json

from fiam import versions


# Each recipe on disk is what the code builds from today's files.
def test_recipes_match_the_code_and_closed_files_are_unchanged():
    for name in versions.VERSIONS:
        on_disk = json.loads((versions.FOLDER / name / "version.json").read_text(encoding="utf-8"))
        assert on_disk == versions.recipe(name), f"{name} changed: rerun only if intended"


# Every closed version is fingerprinted; every recipe on disk is listed.
def test_closed_versions_are_fingerprinted_and_recipes_are_listed():
    for name, spec in versions.VERSIONS.items():
        if spec["status"] == "closed":
            assert versions.recipe(name)["fingerprints"], name
    found = {p.parent.name for p in versions.FOLDER.glob("*/version.json")}
    assert found == set(versions.VERSIONS)
