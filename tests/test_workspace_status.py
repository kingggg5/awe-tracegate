from __future__ import annotations

import json
from pathlib import Path

import pytest

from awe_tracegate.cli import main
from awe_tracegate.contracts import canonical_digest
from awe_tracegate.demo import generate_demo
from awe_tracegate.recipes import RecipeScaffoldManifest, initialize_evidence_workspace
from awe_tracegate.workspace_status import inspect_workspace_status


def test_recipe_workspace_reports_real_inputs_as_action_required(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "comparison"
    initialize_evidence_workspace(workspace, "controlled_comparison")

    report = inspect_workspace_status(workspace)

    assert report.state == "ACTION_REQUIRED"
    assert report.scope == "recipe"
    assert report.recipe_id == "controlled_comparison"
    assert {check.check_id: check.status for check in report.checks} == {
        "catalog_version": "pass",
        "real_inputs": "warn",
        "scaffold_definition": "pass",
        "scaffold_integrity": "pass",
    }
    assert "Supply the real inputs" in report.next_actions[0]


def test_recipe_workspace_detects_managed_file_tampering(tmp_path: Path) -> None:
    workspace = tmp_path / "gate"
    initialize_evidence_workspace(workspace, "ci_gate")
    (workspace / "evaluation-policy.json").write_text("{}\n", encoding="utf-8")

    report = inspect_workspace_status(workspace)

    assert report.state == "INVALID"
    assert any(
        check.check_id == "scaffold_integrity" and check.status == "fail"
        for check in report.checks
    )


def test_modified_manifest_cannot_redirect_status_outside_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gate"
    initialize_evidence_workspace(workspace, "ci_gate")
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    payload = json.loads((workspace / "awe-recipe.json").read_text(encoding="utf-8"))
    payload["files"][0]["path"] = "../outside.txt"
    payload["manifest_hash"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "manifest_hash"}
    )
    RecipeScaffoldManifest.model_validate_json(json.dumps(payload))
    (workspace / "awe-recipe.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    report = inspect_workspace_status(workspace)

    assert report.state == "INVALID"
    assert any(
        check.check_id == "scaffold_definition" and check.status == "fail"
        for check in report.checks
    )


def test_complete_demo_is_a_ready_review_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"
    generate_demo(workspace)

    report = inspect_workspace_status(workspace)

    assert report.state == "READY"
    assert report.scope == "review_bundle"
    assert report.decision == "PASS"
    assert report.receipt_hash is not None
    assert all(check.status == "pass" for check in report.checks)


def test_unknown_layout_never_claims_readiness(tmp_path: Path) -> None:
    report = inspect_workspace_status(tmp_path)

    assert report.state == "ACTION_REQUIRED"
    assert report.scope == "unknown"
    assert report.decision is None


def test_cli_emits_typed_status_and_preserves_exit_semantics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "comparison"
    initialize_evidence_workspace(workspace, "controlled_comparison")

    assert main(["status", str(workspace), "--json"]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "awe.workspace-status.v1"
    assert payload["state"] == "ACTION_REQUIRED"
