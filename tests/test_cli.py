from __future__ import annotations

import json
from pathlib import Path

from awe_tracegate.cli import main

ROOT = Path(__file__).parents[1]


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
    assert len(list(schemas.glob("*.schema.json"))) == 9


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
