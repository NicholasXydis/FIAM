# Version recipes match the code, and closed versions never change.

import json

from fiam import v2, versions


# Each recipe on disk is what the code builds from today's files.
def test_recipes_match_the_code_and_closed_files_are_unchanged():
    for name in versions.VERSIONS:
        on_disk = json.loads((versions.FOLDER / name / "recipe.json").read_text(encoding="utf-8"))
        assert on_disk == versions.recipe(name), f"{name} changed: rerun only if intended"


# v3's switches exist, and every closed version is fingerprinted.
def test_v3_switches_exist_and_closed_versions_are_fingerprinted():
    known = {*v2.MEMBERS, *v2.OTHERS, *v2.CROWD, *v2.CROWDS, *v2.PARTS, *v2.FINAL, *v2.EXHIBIT}
    assert set(versions.V3_SWITCHES) <= known
    for name, spec in versions.VERSIONS.items():
        if spec["status"] == "closed":
            assert versions.recipe(name)["fingerprints"], name
