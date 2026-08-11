from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from awe_tracegate.adapters import (
    evaluation_bundle_from_manifest,
    import_generic_evaluation,
)
from awe_tracegate.cli import main as cli_main
from awe_tracegate.compiler import compile_traces
from awe_tracegate.contracts import (
    ExperimentQualityEvidence,
    QualityPolicy,
    SensitivityPolicy,
    canonical_digest,
)
from awe_tracegate.evaluation import (
    compare_experiments,
    verify_comparison_receipt_inputs,
)
from awe_tracegate.explain import explain_receipt
from awe_tracegate.gate import (
    gate_evidence_v2,
    validate_gate_v2_receipt_inputs,
)
from awe_tracegate.quality import assess_experiment_quality
from awe_tracegate.sensitivity import assess_sensitivity

ROOT = Path(__file__).parents[1]


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _traces() -> tuple[object, ...]:
    from awe_tracegate.contracts import ExecutionTrace

    lines = (
        (ROOT / "examples/repo_analysis/traces.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    return tuple(ExecutionTrace.model_validate_json(line) for line in lines if line)


def _manifest(
    label: str,
    subject_digest: str,
    commit_character: str,
    outcome: Callable[[int, int], bool],
    *,
    environment_character: str = "5",
) -> object:
    return import_generic_evaluation(
        {
            "experiment_id": f"quality-{label}",
            "repository_uri": "https://github.com/example/synthetic-agent",
            "commit_sha": commit_character * 40,
            "subject_digest": subject_digest,
            "dataset_digest": _digest("1"),
            "dataset_split_digest": _digest("2"),
            "harness_name": "synthetic.harness",
            "harness_version": "1.0.0",
            "harness_digest": _digest("3"),
            "strategy_name": "synthetic_strategy",
            "strategy_digest": _digest("6"),
            "model_provider": "synthetic",
            "model_name": "deterministic-test-double",
            "model_config_digest": _digest("4"),
            "environment_digest": _digest(environment_character),
            "grader_digest": _digest("7"),
            "trials": [
                {
                    "trial_id": f"{label}-case-{case_id}-seed-{seed}",
                    "case_id": f"case-{case_id}",
                    "succeeded": outcome(case_id, seed),
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


def _quality(manifest: object, *, outcome: str, votes: bool = False) -> object:
    trials = []
    for trial in sorted(manifest.trials, key=lambda item: item.trial_id):
        entry: dict[str, object] = {
            "trial_id": trial.trial_id,
            "terminal_outcome": outcome,
            "judge_votes": [],
            "human_verdict": None,
        }
        if votes:
            entry["judge_votes"] = [
                {
                    "judge_id": "judge_a",
                    "judge_digest": _digest("9"),
                    "verdict": "pass" if trial.succeeded else "fail",
                },
                {
                    "judge_id": "judge_b",
                    "judge_digest": _digest("a"),
                    "verdict": "pass" if trial.succeeded else "fail",
                },
            ]
            entry["human_verdict"] = {
                "actor_id": "reviewer_1",
                "verdict": "pass" if trial.succeeded else "fail",
            }
        trials.append(entry)
    payload = {
        "schema_version": "awe.experiment-quality-evidence.v1",
        "manifest_digest": manifest.manifest_digest,
        "trials": trials,
    }
    return ExperimentQualityEvidence.model_validate(
        {**payload, "evidence_digest": canonical_digest(payload)}
    )


def _gate_v2_inputs() -> tuple[object, object, object, object, object, object]:
    traces = _traces()
    compiled = compile_traces(traces)
    assert compiled.candidate is not None
    baseline = _manifest("baseline", _digest("b"), "a", lambda _case, _seed: False)
    candidate = _manifest(
        "candidate",
        compiled.candidate.candidate_digest,
        "b",
        lambda _case, _seed: True,
    )
    comparison = compare_experiments(baseline, candidate)
    return (
        traces,
        baseline,
        candidate,
        comparison,
        _quality(baseline, outcome="failure", votes=True),
        _quality(candidate, outcome="success", votes=True),
    )


def test_verifies_comparison_against_held_inputs_and_rejects_tampering() -> None:
    _, baseline, candidate, comparison, _, _ = _gate_v2_inputs()

    valid = verify_comparison_receipt_inputs(comparison, baseline, candidate)
    changed_candidate = _manifest(
        "changed", candidate.subject_digest, "b", lambda case, _seed: case < 10
    )
    invalid = verify_comparison_receipt_inputs(comparison, baseline, changed_candidate)

    assert valid.status == "valid"
    assert invalid.status == "invalid"
    assert invalid.reasons == ("comparison_exact_input_replay_mismatch",)


def test_gate_v2_composes_v1_comparison_and_quality_without_mutating_v1() -> None:
    traces, baseline, candidate, comparison, baseline_quality, candidate_quality = (
        _gate_v2_inputs()
    )
    receipt = gate_evidence_v2(
        traces,
        evaluation_bundle_from_manifest(baseline),
        evaluation_bundle_from_manifest(candidate),
        None,
        comparison,
        baseline,
        candidate,
        baseline_quality_evidence=baseline_quality,
        candidate_quality_evidence=candidate_quality,
        quality_policy=QualityPolicy(
            minimum_judge_coverage_bps=10_000,
            maximum_judge_disagreement_bps=0,
            minimum_human_calibration_samples=20,
            minimum_human_judge_agreement_bps=10_000,
        ),
    )

    assert receipt.schema_version == "awe.gate-receipt.v2"
    assert receipt.status == "PASS"
    assert receipt.v1_gate.schema_version == "awe.gate-receipt.v1"
    assert receipt.comparison_verification.status == "valid"
    assert (
        validate_gate_v2_receipt_inputs(
            receipt,
            traces,
            evaluation_bundle_from_manifest(baseline),
            evaluation_bundle_from_manifest(candidate),
            None,
            baseline,
            candidate,
            baseline_quality_evidence=baseline_quality,
            candidate_quality_evidence=candidate_quality,
            quality_policy=QualityPolicy(
                minimum_judge_coverage_bps=10_000,
                maximum_judge_disagreement_bps=0,
                minimum_human_calibration_samples=20,
                minimum_human_judge_agreement_bps=10_000,
            ),
        )
        is receipt
    )


def test_quality_reports_typed_terminal_outcomes_and_mismatch_fail_closed() -> None:
    _, baseline, _, _, _, _ = _gate_v2_inputs()
    timed_out = _quality(baseline, outcome="timeout")
    receipt = assess_experiment_quality(baseline, timed_out)
    assert receipt.status == "review"
    assert receipt.terminal_outcomes.timeout_count == 40
    assert "terminal_timeout_rate_exceeded" in receipt.reasons

    invalid = _quality(baseline, outcome="success")
    blocked = assess_experiment_quality(baseline, invalid)
    assert blocked.status == "block"
    assert "terminal_outcome_success_mismatch" in blocked.reasons


def test_sensitivity_scopes_environment_and_seed_results_to_held_manifests() -> None:
    baseline = _manifest("stable_a", _digest("a"), "a", lambda _case, _seed: True)
    same = _manifest(
        "stable_b",
        _digest("a"),
        "a",
        lambda _case, _seed: True,
        environment_character="e",
    )
    unstable = _manifest(
        "unstable",
        _digest("a"),
        "a",
        lambda _case, seed: seed == 1,
        environment_character="f",
    )

    stable_receipt = assess_sensitivity((baseline, same))
    unstable_receipt = assess_sensitivity(
        (baseline, unstable),
        SensitivityPolicy(maximum_environment_success_range_bps=100),
    )

    assert stable_receipt.status == "pass"
    assert stable_receipt.environment_success_range_bps == 0
    assert unstable_receipt.status == "review"
    assert "sensitivity_environment_range_exceeded" in unstable_receipt.reasons


def test_explain_gate_v2_emits_a_stable_graph_and_limitations() -> None:
    traces, baseline, candidate, comparison, baseline_quality, candidate_quality = (
        _gate_v2_inputs()
    )
    receipt = gate_evidence_v2(
        traces,
        evaluation_bundle_from_manifest(baseline),
        evaluation_bundle_from_manifest(candidate),
        None,
        comparison,
        baseline,
        candidate,
        baseline_quality_evidence=baseline_quality,
        candidate_quality_evidence=candidate_quality,
    )
    explanation = explain_receipt(receipt)

    assert explanation.decision == "PASS"
    assert {node.node_id for node in explanation.nodes} >= {
        "gate_v1",
        "comparison",
        "comparison_verification",
        "gate_v2",
    }
    assert "no_live_model_or_tool_reconstruction" in explanation.limitations


def test_cli_replays_comparison_gates_v2_and_explains_from_held_inputs(
    tmp_path: Path,
) -> None:
    _, baseline, candidate, comparison, baseline_quality, candidate_quality = (
        _gate_v2_inputs()
    )
    paths = {
        "baseline_manifest": tmp_path / "baseline-manifest.json",
        "candidate_manifest": tmp_path / "candidate-manifest.json",
        "comparison": tmp_path / "comparison.json",
        "baseline_quality": tmp_path / "baseline-quality.json",
        "candidate_quality": tmp_path / "candidate-quality.json",
        "baseline_evaluation": tmp_path / "baseline-evaluation.json",
        "candidate_evaluation": tmp_path / "candidate-evaluation.json",
    }
    for key, value in (
        ("baseline_manifest", baseline),
        ("candidate_manifest", candidate),
        ("comparison", comparison),
        ("baseline_quality", baseline_quality),
        ("candidate_quality", candidate_quality),
        ("baseline_evaluation", evaluation_bundle_from_manifest(baseline)),
        ("candidate_evaluation", evaluation_bundle_from_manifest(candidate)),
    ):
        paths[key].write_text(value.model_dump_json(indent=2), encoding="utf-8")
    verification_path = tmp_path / "comparison-verification.json"
    gate_path = tmp_path / "gate-v2.json"
    explanation_path = tmp_path / "explanation.json"

    assert (
        cli_main(
            [
                "verify-comparison",
                "--receipt",
                str(paths["comparison"]),
                "--baseline",
                str(paths["baseline_manifest"]),
                "--candidate",
                str(paths["candidate_manifest"]),
                "--out",
                str(verification_path),
            ]
        )
        == 0
    )
    assert (
        json.loads(verification_path.read_text(encoding="utf-8"))["status"] == "valid"
    )
    assert (
        cli_main(
            [
                "gate-v2",
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--baseline",
                str(paths["baseline_evaluation"]),
                "--candidate",
                str(paths["candidate_evaluation"]),
                "--comparison",
                str(paths["comparison"]),
                "--baseline-experiment",
                str(paths["baseline_manifest"]),
                "--candidate-experiment",
                str(paths["candidate_manifest"]),
                "--baseline-quality",
                str(paths["baseline_quality"]),
                "--candidate-quality",
                str(paths["candidate_quality"]),
                "--out",
                str(gate_path),
            ]
        )
        == 0
    )
    assert json.loads(gate_path.read_text(encoding="utf-8"))["status"] == "PASS"
    assert (
        cli_main(
            ["explain", "--receipt", str(gate_path), "--out", str(explanation_path)]
        )
        == 0
    )
    assert (
        json.loads(explanation_path.read_text(encoding="utf-8"))["decision"] == "PASS"
    )


def test_quality_evidence_requires_canonical_trial_order() -> None:
    _, baseline, _, _, _, _ = _gate_v2_inputs()
    evidence = _quality(baseline, outcome="failure")
    payload = evidence.model_dump(mode="json", exclude={"evidence_digest"})
    payload["trials"] = list(reversed(payload["trials"]))

    with pytest.raises(ValueError, match="sorted"):
        ExperimentQualityEvidence.model_validate(
            {**payload, "evidence_digest": canonical_digest(payload)}
        )
