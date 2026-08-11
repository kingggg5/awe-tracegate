from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.cli import main
from awe_tracegate.recipes import (
    DecisionRecipeCatalog,
    RecipeScaffoldManifest,
    build_recipe_scaffold,
    decision_recipe_catalog,
    initialize_evidence_workspace,
)


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def test_decision_recipe_catalog_is_sorted_content_addressed_and_bounded() -> None:
    catalog = decision_recipe_catalog()

    assert catalog.schema_version == "awe.decision-recipe-catalog.v1"
    assert tuple(recipe.recipe_id for recipe in catalog.recipes) == (
        "ci_gate",
        "controlled_comparison",
        "harness_import",
        "promotion_review",
        "share_evidence",
    )
    assert all(recipe.commands for recipe in catalog.recipes)
    assert all(recipe.fail_closed_when for recipe in catalog.recipes)

    tampered = catalog.model_dump(mode="json")
    tampered["recipes"][0]["question"] = "Trust everything?"
    with pytest.raises(ValidationError, match="catalog hash is invalid"):
        DecisionRecipeCatalog.model_validate(tampered)


def test_recipe_scaffold_dry_run_never_writes_or_creates_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "planned"
    manifest = initialize_evidence_workspace(
        output,
        "promotion_review",
        dry_run=True,
    )

    assert not output.exists()
    assert manifest.creates_evidence is False
    assert tuple(file.path for file in manifest.files) == (
        "README.md",
        "comparison-policy.json",
        "evaluation-policy.json",
        "quality-policy.json",
    )


def test_recipe_scaffold_writes_only_managed_guidance_and_policy_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence"
    manifest = initialize_evidence_workspace(output, "promotion_review")

    disk_manifest = RecipeScaffoldManifest.model_validate_json(
        (output / "awe-recipe.json").read_text(encoding="utf-8")
    )
    assert disk_manifest == manifest
    for file in manifest.files:
        assert _digest((output / file.path).read_bytes()) == file.digest
    assert not any(output.glob("*receipt*.json"))
    assert not any(output.glob("*manifest.json"))
    assert not (output / "traces.jsonl").exists()
    assert "does **not** contain generated" in (output / "README.md").read_text(
        encoding="utf-8"
    )


def test_recipe_scaffold_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "user.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="must not already exist"):
        initialize_evidence_workspace(output, "ci_gate")

    assert (output / "user.txt").read_text(encoding="utf-8") == "keep"


def test_cli_lists_recipes_and_initializes_a_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["recipes", "--json"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["schema_version"] == "awe.decision-recipe-catalog.v1"

    assert main(["recipes", "--show", "ci_gate"]) == 0
    assert "CI evidence gate" in capsys.readouterr().out

    output = tmp_path / "ci"
    assert (
        main(
            [
                "init",
                "--recipe",
                "ci_gate",
                "--out",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["recipe_id"] == "ci_gate"
    assert result["creates_evidence"] is False
    assert (output / "evaluation-policy.json").is_file()


def test_scaffold_plan_matches_raw_file_hashes() -> None:
    manifest, files = build_recipe_scaffold("share_evidence")

    assert {file.path: file.digest for file in manifest.files} == {
        path: _digest(content) for path, content in files.items()
    }
