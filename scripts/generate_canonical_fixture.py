"""Generate the checked-in, synthetic end-to-end Gate v2 fixture.

The fixture is deliberately not a benchmark or external-adopter result. It is
small public evidence that exercises the complete offline path with no model,
network, credential, or project-code execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from awe_tracegate.adapters import (
    evaluation_bundle_from_manifest,
    import_generic_evaluation,
)
from awe_tracegate.compiler import compile_traces
from awe_tracegate.contracts import (
    ComparisonPolicy,
    ExecutionTrace,
    ExperimentQualityEvidence,
    QualityPolicy,
    canonical_digest,
)
from awe_tracegate.evaluation import (
    compare_experiments,
    verify_comparison_receipt_inputs,
)
from awe_tracegate.explain import explain_receipt
from awe_tracegate.gate import gate_evidence_v2
from awe_tracegate.quality import assess_experiment_quality

ROOT = Path(__file__).parents[1]
SOURCE_TRACES = ROOT / "examples" / "repo_analysis" / "traces.jsonl"
FIXTURE_ID = "synthetic-agent-change-v1"


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _manifest(
    label: str,
    subject_digest: str,
    commit_character: str,
    *,
    succeeded: bool,
) -> object:
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


def _quality(manifest: object, *, terminal_outcome: str) -> object:
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
                "human_verdict": {"actor_id": "fixture_reviewer", "verdict": verdict},
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


def generate_fixture(output_directory: Path) -> tuple[Path, ...]:
    """Build every checked-in fixture artifact and return its sorted paths."""

    output_directory.mkdir(parents=True, exist_ok=True)
    traces = tuple(
        ExecutionTrace.model_validate_json(line)
        for line in SOURCE_TRACES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    compilation = compile_traces(traces)
    if compilation.candidate is None:
        raise ValueError("fixture source traces must compile a candidate")

    baseline = _manifest("baseline", _digest("b"), "a", succeeded=False)
    candidate = _manifest(
        "candidate",
        compilation.candidate.candidate_digest,
        "b",
        succeeded=True,
    )
    comparison_policy = ComparisonPolicy()
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
        None,
        comparison,
        baseline,
        candidate,
        comparison_policy,
        baseline_quality_evidence=baseline_quality,
        candidate_quality_evidence=candidate_quality,
        quality_policy=quality_policy,
    )
    if gate.status != "PASS":
        raise ValueError(
            f"canonical fixture must pass, got {gate.status}: {gate.reasons}"
        )

    explanation = explain_receipt(gate)
    artifacts = {
        "baseline-manifest.json": baseline,
        "candidate-manifest.json": candidate,
        "baseline-evaluation.json": evaluation_bundle_from_manifest(baseline),
        "candidate-evaluation.json": evaluation_bundle_from_manifest(candidate),
        "comparison-policy.json": comparison_policy,
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
    traces_path.write_bytes(SOURCE_TRACES.read_bytes())
    output_paths.append(traces_path)
    for filename, artifact in artifacts.items():
        path = output_directory / filename
        _write_json(path, artifact.model_dump(mode="json"))
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    for path in generate_fixture(_parse_args().out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
