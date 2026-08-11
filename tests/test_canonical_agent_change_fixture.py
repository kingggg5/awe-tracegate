from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from awe_tracegate.contracts import (
    ComparisonPolicy,
    EvaluationBundle,
    EvaluationPolicy,
    ExecutionTrace,
    ExperimentManifest,
    ExperimentQualityEvidence,
    GateReceiptV2,
    QualityPolicy,
)
from awe_tracegate.explain import explain_receipt
from awe_tracegate.gate import validate_gate_v2_receipt_inputs

ROOT = Path(__file__).parents[1]
FIXTURE_DIRECTORY = ROOT / "examples" / "canonical-agent-change"


def test_canonical_fixture_is_reproducible_and_replays_the_full_v2_chain(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_canonical_fixture.py"),
            "--out",
            str(tmp_path),
        ],
        check=True,
        cwd=ROOT,
    )
    generated_paths = tuple(sorted(tmp_path.iterdir()))
    expected_paths = tuple(
        sorted(path for path in FIXTURE_DIRECTORY.iterdir() if path.name != "README.md")
    )

    assert tuple(path.name for path in generated_paths) == tuple(
        path.name for path in expected_paths
    )
    for generated_path, expected_path in zip(
        generated_paths, expected_paths, strict=True
    ):
        assert generated_path.read_bytes() == expected_path.read_bytes()

    metadata = json.loads(
        (FIXTURE_DIRECTORY / "fixture.json").read_text(encoding="utf-8")
    )
    receipt = GateReceiptV2.model_validate_json(
        (FIXTURE_DIRECTORY / "gate-v2.json").read_text(encoding="utf-8")
    )
    assert metadata["classification"] == "synthetic_offline_contract_fixture"
    assert metadata["expected"]["gate_v2_status"] == "PASS"
    assert receipt.status == "PASS"
    assert receipt.receipt_hash == metadata["expected"]["gate_v2_receipt_hash"]
    assert (
        explain_receipt(receipt).explanation_hash
        == metadata["expected"]["explanation_hash"]
    )

    traces = tuple(
        ExecutionTrace.model_validate_json(line)
        for line in (FIXTURE_DIRECTORY / "traces.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    baseline = ExperimentManifest.model_validate_json(
        (FIXTURE_DIRECTORY / "baseline-manifest.json").read_text(encoding="utf-8")
    )
    candidate = ExperimentManifest.model_validate_json(
        (FIXTURE_DIRECTORY / "candidate-manifest.json").read_text(encoding="utf-8")
    )
    comparison_policy = ComparisonPolicy.model_validate_json(
        (FIXTURE_DIRECTORY / "comparison-policy.json").read_text(encoding="utf-8")
    )
    evaluation_policy = EvaluationPolicy.model_validate_json(
        (FIXTURE_DIRECTORY / "evaluation-policy.json").read_text(encoding="utf-8")
    )
    quality_policy = QualityPolicy.model_validate_json(
        (FIXTURE_DIRECTORY / "quality-policy.json").read_text(encoding="utf-8")
    )
    baseline_quality = ExperimentQualityEvidence.model_validate_json(
        (FIXTURE_DIRECTORY / "baseline-quality.json").read_text(encoding="utf-8")
    )
    candidate_quality = ExperimentQualityEvidence.model_validate_json(
        (FIXTURE_DIRECTORY / "candidate-quality.json").read_text(encoding="utf-8")
    )
    replayed = validate_gate_v2_receipt_inputs(
        receipt,
        traces,
        EvaluationBundle.model_validate_json(
            (FIXTURE_DIRECTORY / "baseline-evaluation.json").read_text(encoding="utf-8")
        ),
        EvaluationBundle.model_validate_json(
            (FIXTURE_DIRECTORY / "candidate-evaluation.json").read_text(
                encoding="utf-8"
            )
        ),
        evaluation_policy,
        baseline,
        candidate,
        comparison_policy,
        baseline_quality_evidence=baseline_quality,
        candidate_quality_evidence=candidate_quality,
        quality_policy=quality_policy,
    )
    assert replayed is receipt
