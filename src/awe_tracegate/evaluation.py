"""Deterministic, keyless baseline-versus-candidate evaluation policy."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from .contracts import (
    PENDING_SHA256_DIGEST,
    EvaluationBundle,
    EvaluationMetrics,
    EvaluationPolicy,
    EvaluationReceipt,
    canonical_digest,
)


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    rank = max(1, (95 * len(ordered) + 99) // 100)
    return ordered[rank - 1]


def _metrics(bundle: EvaluationBundle) -> EvaluationMetrics:
    success_count = sum(1 for trial in bundle.trials if trial.succeeded)
    return EvaluationMetrics(
        trial_count=len(bundle.trials),
        success_count=success_count,
        success_rate_bps=(success_count * 10_000) // len(bundle.trials),
        safety_violations=sum(trial.safety_violations for trial in bundle.trials),
        p95_latency_ms=_p95([trial.latency_ms for trial in bundle.trials]),
        total_cost_microusd=sum(trial.cost_microusd for trial in bundle.trials),
    )


def _increase_bps(baseline: int, candidate: int) -> int | None:
    if baseline == 0:
        return None if candidate > 0 else 0
    return max(0, ((candidate - baseline) * 10_000) // baseline)


def _receipt_payload(receipt: EvaluationReceipt) -> dict[str, object]:
    return receipt.model_dump(mode="json", exclude={"receipt_hash"})


def evaluate_candidate(
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    policy: EvaluationPolicy | None = None,
) -> EvaluationReceipt:
    """Apply hard safety gates, quality non-regression, then efficiency review."""

    active_policy = policy or EvaluationPolicy()
    baseline_metrics = _metrics(baseline)
    candidate_metrics = _metrics(candidate)
    block_reasons: list[str] = []
    review_reasons: list[str] = []

    if baseline.dataset_digest != candidate.dataset_digest:
        block_reasons.append("dataset_digest_mismatch")

    baseline_cases = Counter(trial.case_id for trial in baseline.trials)
    candidate_cases = Counter(trial.case_id for trial in candidate.trials)
    if baseline_cases != candidate_cases:
        block_reasons.append("evaluation_case_coverage_mismatch")

    if (
        len(baseline.trials) < active_policy.minimum_trials
        or len(candidate.trials) < active_policy.minimum_trials
    ):
        review_reasons.append("insufficient_trials")

    if (
        active_policy.require_zero_safety_violations
        and candidate_metrics.safety_violations > 0
    ):
        block_reasons.append("candidate_safety_violation")

    success_regression = (
        baseline_metrics.success_rate_bps - candidate_metrics.success_rate_bps
    )
    if success_regression > active_policy.maximum_success_regression_bps:
        block_reasons.append("success_rate_regression")

    latency_increase = _increase_bps(
        baseline_metrics.p95_latency_ms,
        candidate_metrics.p95_latency_ms,
    )
    if latency_increase is None:
        review_reasons.append("latency_baseline_zero")
    elif latency_increase > active_policy.maximum_latency_increase_bps:
        review_reasons.append("p95_latency_regression")

    cost_increase = _increase_bps(
        baseline_metrics.total_cost_microusd,
        candidate_metrics.total_cost_microusd,
    )
    if cost_increase is None:
        review_reasons.append("cost_baseline_zero")
    elif cost_increase > active_policy.maximum_cost_increase_bps:
        review_reasons.append("total_cost_regression")

    status: Literal["pass", "review", "block"]
    if block_reasons:
        status = "block"
        reasons = tuple(sorted(set(block_reasons + review_reasons)))
    elif review_reasons:
        status = "review"
        reasons = tuple(sorted(set(review_reasons)))
    else:
        status = "pass"
        reasons = ()

    receipt = EvaluationReceipt(
        baseline_digest=baseline.subject_digest,
        candidate_digest=candidate.subject_digest,
        dataset_digest=candidate.dataset_digest,
        policy_digest=canonical_digest(active_policy),
        status=status,
        reasons=reasons,
        baseline=baseline_metrics,
        candidate=candidate_metrics,
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    return receipt.model_copy(
        update={"receipt_hash": canonical_digest(_receipt_payload(receipt))}
    )
