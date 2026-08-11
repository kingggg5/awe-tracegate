from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from awe_tracegate.adapters import import_generic_evaluation
from awe_tracegate.cli import main
from awe_tracegate.schemas import SCHEMA_MODELS

ROOT = Path(__file__).parents[1]


def test_cli_starts_loopback_review_workspace() -> None:
    with patch("uvicorn.run") as run_server:
        assert main(["serve", "--host", "127.0.0.1", "--port", "8765"]) == 0

    run_server.assert_called_once_with(
        "awe_tracegate.api:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )


def test_cli_usage_errors_return_malformed_input_exit_one() -> None:
    assert main(["gate"]) == 1
    assert (
        main(
            [
                "gate",
                "--traces",
                "traces.jsonl",
                "--baseline",
                "baseline.json",
                "--candidate",
                "candidate.json",
                "--minimum-provenance",
                "attested",
            ]
        )
        == 1
    )


def test_cli_reserves_exit_two_for_typed_block_receipt(tmp_path: Path) -> None:
    candidate = json.loads(
        (ROOT / "examples/evaluation/candidate.json").read_text(encoding="utf-8")
    )
    candidate["trials"][0]["safety_violations"] = 1
    candidate_path = tmp_path / "blocked-candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    receipt_path = tmp_path / "blocked-gate.json"

    assert (
        main(
            [
                "gate",
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--baseline",
                str(ROOT / "examples/evaluation/baseline.json"),
                "--candidate",
                str(candidate_path),
                "--out",
                str(receipt_path),
            ]
        )
        == 2
    )
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "BLOCK"


def test_cli_release_flow(tmp_path: Path) -> None:
    compilation = tmp_path / "compilation.json"
    verification = tmp_path / "verification.json"
    evaluation = tmp_path / "evaluation.json"
    promotion = tmp_path / "promotion.json"
    schemas = tmp_path / "schemas"

    assert (
        main(
            [
                "compile",
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--out",
                str(compilation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify",
                "--receipt",
                str(compilation),
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--out",
                str(verification),
            ]
        )
        == 0
    )
    assert json.loads(verification.read_text(encoding="utf-8"))["status"] == "valid"

    assert (
        main(
            [
                "evaluate",
                "--baseline",
                str(ROOT / "examples/evaluation/baseline.json"),
                "--candidate",
                str(ROOT / "examples/evaluation/candidate.json"),
                "--policy",
                str(ROOT / "examples/evaluation/policy.json"),
                "--out",
                str(evaluation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "promote",
                "--compilation",
                str(compilation),
                "--verification",
                str(verification),
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--evaluation",
                str(evaluation),
                "--decision",
                "approved",
                "--actor",
                "maintainer@example.com",
                "--commit-sha",
                "a" * 40,
                "--issued-at",
                "2026-08-08T00:00:00Z",
                "--rationale",
                "Reviewed frozen evaluation evidence.",
                "--out",
                str(promotion),
            ]
        )
        == 0
    )
    promotion_payload = json.loads(promotion.read_text(encoding="utf-8"))
    assert promotion_payload["decision"] == "approved"
    assert promotion_payload["verification_status"] == "valid"
    assert promotion_payload["traces_verified"] is True

    assert main(["schema", "--out-dir", str(schemas)]) == 0
    assert len(list(schemas.glob("*.schema.json"))) == len(SCHEMA_MODELS)


def test_cli_runs_atomic_gate_and_exposes_capabilities(tmp_path: Path) -> None:
    receipt = tmp_path / "gate.json"
    skill = tmp_path / "synthetic-review"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: synthetic-review\ndescription: Review evidence.\n---\n",
        encoding="utf-8",
    )
    skill_bom = tmp_path / "skill-bom.json"
    assert (
        main(
            [
                "skill",
                "inspect",
                "--path",
                str(skill),
                "--out",
                str(skill_bom),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "gate",
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--baseline",
                str(ROOT / "examples/evaluation/baseline.json"),
                "--candidate",
                str(ROOT / "examples/evaluation/candidate.json"),
                "--policy",
                str(ROOT / "examples/evaluation/policy.json"),
                "--skill-bom",
                str(skill_bom),
                "--out",
                str(receipt),
            ]
        )
        == 0
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "awe.gate-receipt.v1"
    assert payload["status"] == "PASS"
    assert payload["verification"]["traces_verified"] is True
    assert payload["skill_bom_digest"].startswith("sha256:")

    assert main(["capabilities", "--json"]) == 0


def test_cli_redacts_before_export(tmp_path: Path) -> None:
    output = tmp_path / "redacted.json"
    summary = tmp_path / "summary.json"

    assert (
        main(
            [
                "redact",
                "--input",
                str(ROOT / "examples/redaction/evidence.json"),
                "--out",
                str(output),
                "--summary",
                str(summary),
            ]
        )
        == 0
    )
    rendered = output.read_text(encoding="utf-8")
    assert "engineer@example.com" not in rendered
    assert "demo-placeholder" not in rendered
    assert json.loads(summary.read_text(encoding="utf-8"))["replacements"] == 2


def test_cli_imports_generic_experiment_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    evaluation = tmp_path / "evaluation.json"

    assert (
        main(
            [
                "import-experiment",
                "--format",
                "generic",
                "--input",
                str(ROOT / "examples/evaluation/experiment.json"),
                "--out",
                str(manifest),
                "--evaluation-out",
                str(evaluation),
            ]
        )
        == 0
    )
    assert json.loads(manifest.read_text(encoding="utf-8"))["source_format"] == (
        "awe.generic-evaluation"
    )
    assert len(json.loads(evaluation.read_text(encoding="utf-8"))["trials"]) == 3


def test_cli_compare_emits_a_typed_fail_closed_receipt(tmp_path: Path) -> None:
    baseline_payload = json.loads(
        (ROOT / "examples/evaluation/experiment.json").read_text(encoding="utf-8")
    )
    candidate_payload = deepcopy(baseline_payload)
    candidate_payload["experiment_id"] = "synthetic-comparison-candidate"
    candidate_payload["commit_sha"] = "b" * 40
    candidate_payload["subject_digest"] = "sha256:" + "6" * 64
    baseline = import_generic_evaluation(baseline_payload)
    candidate = import_generic_evaluation(candidate_payload)
    baseline_path = tmp_path / "baseline-manifest.json"
    candidate_path = tmp_path / "candidate-manifest.json"
    receipt_path = tmp_path / "comparison-receipt.json"
    baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
    candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            "compare",
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--out",
            str(receipt_path),
        ]
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert receipt["schema_version"] == "awe.comparison-receipt.v1"
    assert receipt["status"] == "review"
    assert "insufficient_paired_cases" in receipt["reasons"]


def test_cli_signs_and_verifies_against_trusted_key(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    artifact = ROOT / "examples/evaluation/experiment.json"
    signed = tmp_path / "signed.json"
    verified = tmp_path / "signature-verification.json"
    repository = "https://github.com/example/synthetic-agent"
    commit = "a" * 40

    assert (
        main(
            [
                "sign",
                "--artifact",
                str(artifact),
                "--kind",
                "experiment",
                "--private-key",
                str(private_path),
                "--signer",
                "maintainer@example.com",
                "--repository",
                repository,
                "--commit-sha",
                commit,
                "--issued-at",
                "2026-08-09T00:00:00Z",
                "--out",
                str(signed),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-signature",
                "--bundle",
                str(signed),
                "--public-key",
                str(public_path),
                "--signer",
                "maintainer@example.com",
                "--repository",
                repository,
                "--commit-sha",
                commit,
                "--out",
                str(verified),
            ]
        )
        == 0
    )
    assert json.loads(verified.read_text(encoding="utf-8"))["status"] == "valid"
