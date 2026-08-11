"""Self-contained synthetic demo and review-bundle readiness checks.

The demo is deliberately generated from typed local values. It does not call a
model, a tool provider, the network, or project code.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .adapters import evaluation_bundle_from_manifest, import_generic_evaluation
from .compiler import compile_traces
from .contracts import (
    ComparisonPolicy,
    ComparisonReceipt,
    EvaluationBundle,
    EvaluationPolicy,
    ExecutionTrace,
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExplanationReceipt,
    GateReceiptV2,
    QualityPolicy,
    ReviewBundleCheck,
    ReviewBundleReport,
    canonical_digest,
)
from .evaluation import compare_experiments, verify_comparison_receipt_inputs
from .explain import explain_receipt
from .gate import gate_evidence_v2, validate_gate_v2_receipt_inputs
from .quality import assess_experiment_quality

FIXTURE_ID = "synthetic-agent-change-v1"
REVIEW_BUNDLE_FILES = (
    "baseline-evaluation.json",
    "baseline-manifest.json",
    "baseline-quality.json",
    "candidate-evaluation.json",
    "candidate-manifest.json",
    "candidate-quality.json",
    "comparison-policy.json",
    "comparison.json",
    "evaluation-policy.json",
    "explanation.json",
    "gate-v2.json",
    "quality-policy.json",
    "traces.jsonl",
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _trace(
    trace_number: int,
    repository: str,
    diff: str,
    head_sha: str,
    changes: str,
    risk_score: str,
    reasons: str,
) -> ExecutionTrace:
    """Create one deterministic, read-only synthetic source trace."""

    return ExecutionTrace.model_validate(
        {
            "schema_version": "awe.trace.v1",
            "trace_id": f"repo_analysis_{trace_number:03d}",
            "intent": "repo_analysis",
            "succeeded": True,
            "workflow_inputs": [
                {"field": "/repository", "value_digest": _digest(repository)}
            ],
            "steps": [
                {
                    "node_id": "read_diff",
                    "tool": "repo.read_diff",
                    "tool_version": "1.0.0",
                    "effect": "read",
                    "inputs": [
                        {
                            "input_name": "repository",
                            "source_kind": "workflow_input",
                            "source_field": "/repository",
                            "observed_value_digest": _digest(repository),
                            "source_node": None,
                        }
                    ],
                    "outputs": [
                        {"field": "/diff", "value_digest": _digest(diff)},
                        {"field": "/head_sha", "value_digest": _digest(head_sha)},
                    ],
                },
                {
                    "node_id": "detect_dependencies",
                    "tool": "repo.detect_dependencies",
                    "tool_version": "1.0.0",
                    "effect": "read",
                    "inputs": [
                        {
                            "input_name": "diff",
                            "source_kind": "step_output",
                            "source_field": "/diff",
                            "observed_value_digest": _digest(diff),
                            "source_node": "read_diff",
                        }
                    ],
                    "outputs": [
                        {"field": "/changes", "value_digest": _digest(changes)}
                    ],
                },
                {
                    "node_id": "score_release_risk",
                    "tool": "risk.score",
                    "tool_version": "1.0.0",
                    "effect": "pure",
                    "inputs": [
                        {
                            "input_name": "changes",
                            "source_kind": "step_output",
                            "source_field": "/changes",
                            "observed_value_digest": _digest(changes),
                            "source_node": "detect_dependencies",
                        },
                        {
                            "input_name": "head_sha",
                            "source_kind": "step_output",
                            "source_field": "/head_sha",
                            "observed_value_digest": _digest(head_sha),
                            "source_node": "read_diff",
                        },
                    ],
                    "outputs": [
                        {
                            "field": "/risk_score",
                            "value_digest": _digest(risk_score),
                        },
                        {"field": "/reasons", "value_digest": _digest(reasons)},
                    ],
                },
            ],
        }
    )


def _source_traces() -> tuple[ExecutionTrace, ...]:
    return (
        _trace(1, "1", "2", "3", "4", "5", "6"),
        _trace(2, "7", "8", "9", "a", "b", "c"),
    )


def _manifest(
    label: str,
    subject_digest: str,
    commit_character: str,
    *,
    succeeded: bool,
) -> ExperimentManifest:
    """Return one fully declared, frozen synthetic experiment manifest."""

    return import_generic_evaluation(
        {
            "experiment_id": f"{FIXTURE_ID}-{label}",
            "repository_uri": "https://example.invalid/awe-tracegate-fixture",
            "commit_sha": commit_character * 40,
            "subject_digest": subject_digest,
            "dataset_digest": _digest("1"),
            "dataset_split_digest": _digest("2"),
            "harness_name": "awe.synthetic-harness",
            "harness_version": "1.0.0",
            "harness_digest": _digest("3"),
            "strategy_name": "read_only_repo_analysis",
            "strategy_digest": _digest("4"),
            "model_provider": "fixture",
            "model_name": "deterministic-test-double",
            "model_config_digest": _digest("5"),
            "environment_digest": _digest("6"),
            "grader_digest": _digest("7"),
            "trials": [
                {
                    "trial_id": f"{label}-case-{case_id}-seed-{seed}",
                    "case_id": f"case-{case_id}",
                    "succeeded": succeeded,
                    "safety_violations": 0,
                    "latency_ms": 100,
                    "cost_microusd": 1_000,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cached_input_tokens": 0,
                    "trace_id": None,
                    "grader_result_digest": _digest("8"),
                    "seed": seed,
                }
                for case_id in range(1, 21)
                for seed in (1, 2)
            ],
        }
    )


def _quality(
    manifest: ExperimentManifest, *, terminal_outcome: str
) -> ExperimentQualityEvidence:
    """Create complete asserted quality sidecar data for a frozen manifest."""

    trials = []
    for trial in sorted(manifest.trials, key=lambda item: item.trial_id):
        verdict = "pass" if trial.succeeded else "fail"
        trials.append(
            {
                "trial_id": trial.trial_id,
                "terminal_outcome": terminal_outcome,
                "judge_votes": [
                    {
                        "judge_id": "fixture_judge_a",
                        "judge_digest": _digest("9"),
                        "verdict": verdict,
                    },
                    {
                        "judge_id": "fixture_judge_b",
                        "judge_digest": _digest("a"),
                        "verdict": verdict,
                    },
                ],
                "human_verdict": {
                    "actor_id": "fixture_reviewer",
                    "verdict": verdict,
                },
            }
        )
    payload = {
        "schema_version": "awe.experiment-quality-evidence.v1",
        "manifest_digest": manifest.manifest_digest,
        "trials": trials,
    }
    return ExperimentQualityEvidence.model_validate(
        {**payload, "evidence_digest": canonical_digest(payload)}
    )


def _write_json(path: Path, value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate_demo(
    output_directory: Path, *, replace_managed_files: bool = False
) -> tuple[Path, ...]:
    """Generate a complete offline Gate v2 demo into an empty directory."""

    if (
        not replace_managed_files
        and output_directory.exists()
        and any(output_directory.iterdir())
    ):
        raise ValueError("demo output directory must be empty")
    output_directory.mkdir(parents=True, exist_ok=True)
    traces = _source_traces()
    compilation = compile_traces(traces)
    if compilation.candidate is None:
        raise ValueError("demo traces must compile a candidate")

    baseline = _manifest("baseline", _digest("b"), "a", succeeded=False)
    candidate = _manifest(
        "candidate", compilation.candidate.candidate_digest, "b", succeeded=True
    )
    comparison_policy = ComparisonPolicy()
    evaluation_policy = EvaluationPolicy()
    quality_policy = QualityPolicy(
        minimum_judge_coverage_bps=10_000,
        maximum_judge_disagreement_bps=0,
        minimum_human_calibration_samples=20,
        minimum_human_judge_agreement_bps=10_000,
    )
    comparison = compare_experiments(baseline, candidate, comparison_policy)
    baseline_quality = _quality(baseline, terminal_outcome="failure")
    candidate_quality = _quality(candidate, terminal_outcome="success")
    verification = verify_comparison_receipt_inputs(
        comparison, baseline, candidate, comparison_policy
    )
    gate = gate_evidence_v2(
        traces,
        evaluation_bundle_from_manifest(baseline),
        evaluation_bundle_from_manifest(candidate),
        evaluation_policy,
        comparison,
        baseline,
        candidate,
        comparison_policy,
        baseline_quality_evidence=baseline_quality,
        candidate_quality_evidence=candidate_quality,
        quality_policy=quality_policy,
    )
    if gate.status != "PASS":
        raise ValueError(f"demo must pass, got {gate.status}: {gate.reasons}")

    explanation = explain_receipt(gate)
    artifacts: dict[str, object] = {
        "baseline-manifest.json": baseline,
        "candidate-manifest.json": candidate,
        "baseline-evaluation.json": evaluation_bundle_from_manifest(baseline),
        "candidate-evaluation.json": evaluation_bundle_from_manifest(candidate),
        "comparison-policy.json": comparison_policy,
        "evaluation-policy.json": evaluation_policy,
        "quality-policy.json": quality_policy,
        "comparison.json": comparison,
        "comparison-verification.json": verification,
        "baseline-quality.json": baseline_quality,
        "candidate-quality.json": candidate_quality,
        "gate-v2.json": gate,
        "explanation.json": explanation,
    }
    output_paths: list[Path] = []
    traces_path = output_directory / "traces.jsonl"
    traces_path.write_bytes(
        "".join(f"{trace.model_dump_json()}\n" for trace in traces).encode("utf-8")
    )
    output_paths.append(traces_path)
    for filename, artifact in artifacts.items():
        path = output_directory / filename
        _write_json(path, artifact)
        output_paths.append(path)

    metadata = {
        "schema_version": "awe.canonical-fixture.v1",
        "fixture_id": FIXTURE_ID,
        "classification": "synthetic_offline_contract_fixture",
        "repository_uri": baseline.repository_uri,
        "baseline_commit_sha": baseline.commit_sha,
        "candidate_commit_sha": candidate.commit_sha,
        "source_traces_digest": compilation.input_bundle_digest,
        "expected": {
            "comparison_status": comparison.status,
            "comparison_verification_status": verification.status,
            "baseline_quality_status": assess_experiment_quality(
                baseline, baseline_quality, quality_policy
            ).status,
            "candidate_quality_status": assess_experiment_quality(
                candidate, candidate_quality, quality_policy
            ).status,
            "gate_v2_status": gate.status,
            "gate_v2_receipt_hash": gate.receipt_hash,
            "explanation_hash": explanation.explanation_hash,
        },
        "limitations": [
            "Synthetic fixtures do not demonstrate an external adopter or real "
            "model performance.",
            "The verifier replays supplied artifacts; it does not reconstruct "
            "model or tool calls.",
            "Judge and human labels are asserted fixture data, not authenticated "
            "identities.",
        ],
    }
    metadata_path = output_directory / "fixture.json"
    _write_json(metadata_path, metadata)
    output_paths.append(metadata_path)
    return tuple(sorted(output_paths))


def _report(
    status: str,
    checks: list[ReviewBundleCheck],
    *,
    next_actions: tuple[str, ...] = (),
    gate: GateReceiptV2 | None = None,
    explanation: ExplanationReceipt | None = None,
) -> ReviewBundleReport:
    payload = {
        "schema_version": "awe.review-bundle-report.v1",
        "status": status,
        "checks": tuple(
            item.model_dump(mode="json")
            for item in sorted(checks, key=lambda item: item.check_id)
        ),
        "next_actions": next_actions,
        "gate_v2_status": gate.status if gate is not None else None,
        "gate_v2_receipt_hash": gate.receipt_hash if gate is not None else None,
        "explanation_hash": (
            explanation.explanation_hash if explanation is not None else None
        ),
    }
    return ReviewBundleReport.model_validate(
        {**payload, "report_hash": canonical_digest(payload)}
    )


def inspect_review_bundle(directory: Path) -> ReviewBundleReport:
    """Replay every decision-bearing link in the standard local bundle layout."""

    missing = tuple(
        filename
        for filename in REVIEW_BUNDLE_FILES
        if not (directory / filename).is_file()
    )
    if missing:
        return _report(
            "INCOMPLETE",
            [
                ReviewBundleCheck(
                    check_id="required_files",
                    status="fail",
                    detail=f"missing required files: {', '.join(missing)}",
                )
            ],
            next_actions=("Add the missing held inputs before making a decision.",),
        )

    checks: list[ReviewBundleCheck] = []
    try:
        traces = tuple(
            ExecutionTrace.model_validate_json(line)
            for line in (directory / "traces.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        baseline = ExperimentManifest.model_validate_json(
            (directory / "baseline-manifest.json").read_text(encoding="utf-8")
        )
        candidate = ExperimentManifest.model_validate_json(
            (directory / "candidate-manifest.json").read_text(encoding="utf-8")
        )
        baseline_evaluation = EvaluationBundle.model_validate_json(
            (directory / "baseline-evaluation.json").read_text(encoding="utf-8")
        )
        candidate_evaluation = EvaluationBundle.model_validate_json(
            (directory / "candidate-evaluation.json").read_text(encoding="utf-8")
        )
        comparison_policy = ComparisonPolicy.model_validate_json(
            (directory / "comparison-policy.json").read_text(encoding="utf-8")
        )
        evaluation_policy = EvaluationPolicy.model_validate_json(
            (directory / "evaluation-policy.json").read_text(encoding="utf-8")
        )
        quality_policy = QualityPolicy.model_validate_json(
            (directory / "quality-policy.json").read_text(encoding="utf-8")
        )
        comparison = ComparisonReceipt.model_validate_json(
            (directory / "comparison.json").read_text(encoding="utf-8")
        )
        baseline_quality = ExperimentQualityEvidence.model_validate_json(
            (directory / "baseline-quality.json").read_text(encoding="utf-8")
        )
        candidate_quality = ExperimentQualityEvidence.model_validate_json(
            (directory / "candidate-quality.json").read_text(encoding="utf-8")
        )
        gate = GateReceiptV2.model_validate_json(
            (directory / "gate-v2.json").read_text(encoding="utf-8")
        )
        explanation = ExplanationReceipt.model_validate_json(
            (directory / "explanation.json").read_text(encoding="utf-8")
        )
        checks.append(
            ReviewBundleCheck(
                check_id="typed_contracts",
                status="pass",
                detail="all required artifacts match strict versioned contracts",
            )
        )

        comparison_verification = verify_comparison_receipt_inputs(
            comparison, baseline, candidate, comparison_policy
        )
        if comparison_verification.status != "valid":
            raise ValueError("comparison does not match held inputs")
        checks.append(
            ReviewBundleCheck(
                check_id="comparison_replay",
                status="pass",
                detail="comparison receipt matches baseline, candidate, and policy",
            )
        )

        validate_gate_v2_receipt_inputs(
            gate,
            traces,
            baseline_evaluation,
            candidate_evaluation,
            evaluation_policy,
            baseline,
            candidate,
            comparison_policy,
            baseline_quality_evidence=baseline_quality,
            candidate_quality_evidence=candidate_quality,
            quality_policy=quality_policy,
        )
        checks.append(
            ReviewBundleCheck(
                check_id="gate_replay",
                status="pass",
                detail="Gate v2 receipt matches every supplied decision input",
            )
        )

        replayed_explanation = explain_receipt(gate)
        if replayed_explanation.explanation_hash != explanation.explanation_hash:
            raise ValueError("explanation does not match Gate v2 receipt")
        checks.append(
            ReviewBundleCheck(
                check_id="explanation_replay",
                status="pass",
                detail="evidence graph matches the verified Gate v2 receipt",
            )
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        detail = f"bundle replay failed: {error}"[:512]
        checks.append(
            ReviewBundleCheck(check_id="replay_integrity", status="fail", detail=detail)
        )
        return _report(
            "INVALID",
            checks,
            next_actions=(
                "Regenerate the affected receipt from the separately held inputs.",
            ),
        )

    return _report("READY", checks, gate=gate, explanation=explanation)
