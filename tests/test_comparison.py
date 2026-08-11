from __future__ import annotations

from collections.abc import Callable
from decimal import Inexact, localcontext
from fractions import Fraction
from math import comb as math_comb
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from awe_tracegate.adapters import import_generic_evaluation
from awe_tracegate.capabilities import describe_capabilities
from awe_tracegate.contracts import (
    ComparisonPolicy,
    ComparisonReceipt,
    ExperimentManifest,
    canonical_digest,
)
from awe_tracegate.evaluation import (
    _exact_two_sided_sign_test,
    compare_experiments,
    validate_comparison_receipt_inputs,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _experiment(
    label: str,
    subject_character: str,
    commit_character: str,
    outcome: Callable[[int, int], bool],
    *,
    strategy_character: str = "6",
    model_character: str = "4",
    seeds: tuple[int, ...] = (1, 2),
    safety_violations: int = 0,
    latency_ms: int = 100,
    cost_microusd: int = 1_000,
) -> ExperimentManifest:
    return import_generic_evaluation(
        {
            "experiment_id": f"synthetic-{label}",
            "repository_uri": "https://github.com/example/synthetic-agent",
            "commit_sha": commit_character * 40,
            "subject_digest": _digest(subject_character),
            "dataset_digest": _digest("1"),
            "dataset_split_digest": _digest("2"),
            "harness_name": "synthetic.harness",
            "harness_version": "1.0.0",
            "harness_digest": _digest("3"),
            "strategy_name": "synthetic_strategy",
            "strategy_digest": _digest(strategy_character),
            "model_provider": "synthetic",
            "model_name": "deterministic-test-double",
            "model_config_digest": _digest(model_character),
            "environment_digest": _digest("5"),
            "grader_digest": _digest("7"),
            "trials": [
                {
                    "trial_id": f"{label}-case-{case_id}-seed-{seed}",
                    "case_id": f"case-{case_id}",
                    "succeeded": outcome(case_id, seed),
                    "safety_violations": safety_violations,
                    "latency_ms": latency_ms,
                    "cost_microusd": cost_microusd,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cached_input_tokens": 0,
                    "trace_id": None,
                    "grader_result_digest": _digest("8"),
                    "seed": seed,
                }
                for case_id in range(1, 21)
                for seed in seeds
            ],
        }
    )


def test_establishes_improvement_from_controlled_paired_cases() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment("candidate", "b", "b", lambda _case, _seed: True)

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "pass"
    assert receipt.conclusion == "improvement"
    assert receipt.treatment_factors == ("agent_commit",)
    assert receipt.treatment_scope == "single_factor"
    assert receipt.reliability is not None
    assert receipt.reliability.estimand_scope == "frozen_paired_cases"
    assert receipt.reliability.paired_case_count == 20
    assert receipt.reliability.paired_trial_count == 40
    assert receipt.reliability.improved_case_count == 20
    assert receipt.reliability.sign_test_p_value_ppm == 2
    assert receipt.reliability.confidence_interval_lower_bps == 10_000
    assert receipt.reliability.evidence_strength == "high"
    assert receipt.receipt_hash == (
        "sha256:0a1d43d971b7ad64eebce495be7bcad0eb6ac94f1f6c02e9722906a6a0d2a91a"
    )


def test_reviews_an_observed_gain_when_direction_evidence_is_insufficient() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda case, _seed: case <= 5,
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "review"
    assert receipt.conclusion == "non_regression"
    assert "insufficient_discordant_cases" in receipt.reasons
    assert "improvement_not_established" in receipt.reasons
    assert receipt.reliability is not None
    assert receipt.reliability.evidence_strength == "low"


def test_reviews_flaky_case_evidence_even_when_direction_is_consistent() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, seed: seed == 1,
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "review"
    assert receipt.conclusion == "improvement"
    assert "evaluation_flakiness_exceeded" in receipt.reasons
    assert receipt.reliability is not None
    assert receipt.reliability.candidate_flaky_case_count == 20
    assert receipt.reliability.flaky_case_rate_bps == 10_000


def test_blocks_unmatched_seed_identity_without_computing_statistics() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, _seed: True,
        seeds=(1, 3),
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "block"
    assert receipt.conclusion == "incomparable"
    assert receipt.reliability is None
    assert "case_seed_coverage_mismatch" in receipt.reasons


def test_blocks_an_undeclared_second_treatment_factor() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, _seed: True,
        strategy_character="9",
    )

    blocked = compare_experiments(baseline, candidate)
    declared = compare_experiments(
        baseline,
        candidate,
        ComparisonPolicy(treatment_factors=("agent_commit", "strategy")),
    )

    assert blocked.status == "block"
    assert blocked.conclusion == "incomparable"
    assert "undeclared_treatment_factor_strategy" in blocked.reasons
    assert declared.status == "pass"
    assert declared.treatment_factors == ("agent_commit", "strategy")
    assert declared.treatment_scope == "joint_effect"


def test_blocks_a_safety_violation_despite_strong_quality_evidence() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, _seed: True,
        safety_violations=1,
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "block"
    assert "candidate_safety_violation" in receipt.reasons


def test_blocks_a_statistically_established_regression() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: True)
    candidate = _experiment("candidate", "b", "b", lambda _case, _seed: False)

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "block"
    assert receipt.conclusion == "regression"
    assert "success_regression_established" in receipt.reasons
    assert receipt.reliability is not None
    assert receipt.reliability.regressed_case_count == 20


def test_model_only_comparison_keeps_the_agent_subject_fixed() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "a",
        "a",
        lambda _case, _seed: True,
        model_character="9",
    )
    policy = ComparisonPolicy(treatment_factors=("model",))

    receipt = compare_experiments(baseline, candidate, policy)
    confounded = compare_experiments(
        baseline,
        _experiment(
            "confounded-candidate",
            "b",
            "a",
            lambda _case, _seed: True,
            model_character="9",
        ),
        policy,
    )

    assert receipt.status == "pass"
    assert receipt.treatment_factors == ("model",)
    assert confounded.status == "block"
    assert "subject_digest_changed_for_model_only_comparison" in confounded.reasons


def test_comparison_receipt_rejects_rehashed_field_tampering() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment("candidate", "b", "b", lambda _case, _seed: True)
    receipt = compare_experiments(baseline, candidate)
    tampered = receipt.model_dump(mode="json")
    tampered["reliability"]["sign_test_p_value_ppm"] = 500_000

    with pytest.raises(ValidationError, match="comparison receipt hash"):
        type(receipt).model_validate(tampered)


def test_rejects_a_rehashed_semantically_impossible_pass() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: True)
    candidate = _experiment("candidate", "b", "b", lambda _case, _seed: False)
    receipt = compare_experiments(baseline, candidate)
    tampered = receipt.model_dump(mode="json", exclude={"receipt_hash"})
    tampered["status"] = "pass"
    tampered["reasons"] = []

    with pytest.raises(ValidationError, match="favorable conclusion"):
        ComparisonReceipt.model_validate(
            {**tampered, "receipt_hash": canonical_digest(tampered)}
        )


def test_exact_replay_rejects_different_held_inputs() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment("candidate", "b", "b", lambda _case, _seed: True)
    receipt = compare_experiments(baseline, candidate)
    changed_candidate = _experiment(
        "changed-candidate",
        "b",
        "b",
        lambda case, _seed: case <= 10,
    )

    assert validate_comparison_receipt_inputs(receipt, baseline, candidate) is receipt
    with pytest.raises(ValueError, match="exact input replay"):
        validate_comparison_receipt_inputs(
            receipt,
            baseline,
            changed_candidate,
        )


def test_receipt_is_independent_of_the_process_decimal_context() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda case, _seed: case <= 15,
    )
    expected = compare_experiments(baseline, candidate)

    with localcontext() as hostile_context:
        hostile_context.prec = 6
        hostile_context.traps[Inexact] = True
        actual = compare_experiments(baseline, candidate)

    assert actual == expected


def test_large_balanced_sign_test_uses_the_constant_time_shortcut() -> None:
    with patch(
        "awe_tracegate.evaluation.comb",
        side_effect=AssertionError("balanced sign test must not expand coefficients"),
    ):
        assert _exact_two_sided_sign_test(5_000, 5_000) == (1, 1, 1_000_000)


def test_optimized_sign_test_matches_the_exact_small_sample_definition() -> None:
    for improved in range(11):
        for regressed in range(11):
            discordant = improved + regressed
            if discordant == 0:
                expected = Fraction(1)
            else:
                tail = sum(
                    math_comb(discordant, index)
                    for index in range(min(improved, regressed) + 1)
                )
                expected = min(Fraction(1), Fraction(2 * tail, 2**discordant))
            numerator, denominator, _ = _exact_two_sided_sign_test(
                improved,
                regressed,
            )
            assert Fraction(numerator, denominator) == expected


def test_capabilities_advertise_the_versioned_comparison_surface() -> None:
    capabilities = describe_capabilities("0.3.0")

    assert "compare" in capabilities.commands
    assert "paired_experiment_comparison" in capabilities.guarantees
    assert "comparison_exact_input_replay" in capabilities.guarantees


def test_reviews_quality_gain_with_unacceptable_efficiency_regression() -> None:
    baseline = _experiment("baseline", "a", "a", lambda _case, _seed: False)
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, _seed: True,
        latency_ms=100_000,
        cost_microusd=1_000_000,
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "review"
    assert receipt.conclusion == "improvement"
    assert "p95_latency_regression" in receipt.reasons
    assert "total_cost_regression" in receipt.reasons


def test_efficiency_threshold_uses_exact_cross_multiplication() -> None:
    baseline = _experiment(
        "baseline",
        "a",
        "a",
        lambda _case, _seed: False,
        latency_ms=10_001,
        cost_microusd=10_001,
    )
    candidate = _experiment(
        "candidate",
        "b",
        "b",
        lambda _case, _seed: True,
        latency_ms=12_502,
        cost_microusd=12_502,
    )

    receipt = compare_experiments(baseline, candidate)

    assert receipt.status == "review"
    assert "p95_latency_regression" in receipt.reasons
    assert "total_cost_regression" in receipt.reasons
