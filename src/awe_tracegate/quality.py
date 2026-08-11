"""Deterministic terminal-outcome and judge-calibration assessments.

This module consumes a sidecar rather than changing ``ExperimentManifest`` v1.
That keeps historical manifests and ComparisonReceipt v1 parsers stable while
allowing a stricter Gate v2 policy to require richer operational evidence.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from .contracts import (
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExperimentQualityReceipt,
    JudgeCalibration,
    QualityPolicy,
    TerminalOutcomeSummary,
    canonical_digest,
)


def _rate_bps(numerator: int, denominator: int) -> int:
    """Return a nearest-integer basis-point rate without floating point."""

    return (numerator * 10_000 + denominator // 2) // denominator


def assess_experiment_quality(
    manifest: ExperimentManifest,
    evidence: ExperimentQualityEvidence,
    policy: QualityPolicy | None = None,
) -> ExperimentQualityReceipt:
    """Assess typed terminal outcomes and asserted judge calibration.

    The evidence is strictly bound to one manifest and each supplied trial ID.
    Missing sidecar entries are reported as *unreported*, not silently treated
    as successful execution. The verifier does not run a grader, model, or
    external service; vote identity and labels remain asserted evidence.
    """

    active_policy = policy or QualityPolicy()
    manifest_trials = {trial.trial_id: trial for trial in manifest.trials}
    evidence_trials = {trial.trial_id: trial for trial in evidence.trials}
    block_reasons: list[str] = []
    review_reasons: list[str] = []

    if evidence.manifest_digest != manifest.manifest_digest:
        block_reasons.append("quality_manifest_digest_mismatch")
    unknown_trials = set(evidence_trials) - set(manifest_trials)
    if unknown_trials:
        block_reasons.append("quality_unknown_trial_id")

    counts: Counter[str] = Counter()
    judge_covered = 0
    multi_judge = 0
    disagreeing = 0
    abstaining_votes = 0
    calibration_samples = 0
    calibration_agree = 0

    for trial_id, trial in manifest_trials.items():
        quality = evidence_trials.get(trial_id)
        if quality is None:
            counts["unreported"] += 1
            continue

        if quality.terminal_outcome == "success" and not trial.succeeded:
            block_reasons.append("terminal_outcome_success_mismatch")
        elif quality.terminal_outcome != "success" and trial.succeeded:
            block_reasons.append("terminal_outcome_failure_mismatch")
        counts[quality.terminal_outcome] += 1

        votes = quality.judge_votes
        if not votes:
            continue
        judge_covered += 1
        abstaining_votes += sum(vote.verdict == "abstain" for vote in votes)
        non_abstaining = {vote.verdict for vote in votes if vote.verdict != "abstain"}
        if len(votes) > 1:
            multi_judge += 1
        if len(non_abstaining) > 1:
            disagreeing += 1
        if (
            quality.human_verdict is not None
            and quality.human_verdict.verdict != "abstain"
            and len(non_abstaining) == 1
        ):
            calibration_samples += 1
            if quality.human_verdict.verdict in non_abstaining:
                calibration_agree += 1

    trial_count = len(manifest.trials)
    summary = TerminalOutcomeSummary(
        trial_count=trial_count,
        success_count=counts["success"],
        failure_count=counts["failure"],
        timeout_count=counts["timeout"],
        refusal_count=counts["refusal"],
        infrastructure_failure_count=counts["infrastructure_error"],
        missing_trial_count=counts["missing"],
        unreported_trial_count=counts["unreported"],
    )
    calibration = JudgeCalibration(
        trial_count=trial_count,
        judge_covered_trial_count=judge_covered,
        multi_judge_trial_count=multi_judge,
        disagreeing_trial_count=disagreeing,
        abstaining_vote_count=abstaining_votes,
        human_calibration_sample_count=calibration_samples,
        human_judge_agree_count=calibration_agree,
        judge_coverage_bps=_rate_bps(judge_covered, trial_count),
        judge_disagreement_bps=(
            _rate_bps(disagreeing, multi_judge) if multi_judge else 0
        ),
        human_judge_agreement_bps=(
            _rate_bps(calibration_agree, calibration_samples)
            if calibration_samples
            else None
        ),
    )

    if (
        active_policy.require_complete_terminal_outcomes
        and summary.unreported_trial_count
    ):
        review_reasons.append("terminal_outcome_unreported")
    rate_checks = (
        (
            "terminal_timeout_rate_exceeded",
            summary.timeout_count,
            active_policy.maximum_timeout_rate_bps,
        ),
        (
            "terminal_refusal_rate_exceeded",
            summary.refusal_count,
            active_policy.maximum_refusal_rate_bps,
        ),
        (
            "terminal_infrastructure_failure_rate_exceeded",
            summary.infrastructure_failure_count,
            active_policy.maximum_infrastructure_failure_rate_bps,
        ),
        (
            "terminal_missing_trial_rate_exceeded",
            summary.missing_trial_count,
            active_policy.maximum_missing_trial_rate_bps,
        ),
    )
    review_reasons.extend(
        reason
        for reason, count, maximum in rate_checks
        if count * 10_000 > maximum * trial_count
    )
    if calibration.judge_coverage_bps < active_policy.minimum_judge_coverage_bps:
        review_reasons.append("judge_coverage_below_minimum")
    if (
        calibration.judge_disagreement_bps
        > active_policy.maximum_judge_disagreement_bps
    ):
        review_reasons.append("judge_disagreement_exceeded")
    if (
        calibration.human_calibration_sample_count
        < active_policy.minimum_human_calibration_samples
    ):
        review_reasons.append("human_calibration_insufficient")
    elif (
        calibration.human_judge_agreement_bps is None
        or calibration.human_judge_agreement_bps
        < active_policy.minimum_human_judge_agreement_bps
    ):
        review_reasons.append("human_judge_agreement_below_minimum")

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

    payload = {
        "schema_version": "awe.experiment-quality-receipt.v1",
        "manifest_digest": manifest.manifest_digest,
        "quality_evidence_digest": evidence.evidence_digest,
        "policy_digest": canonical_digest(active_policy),
        "status": status,
        "reasons": reasons,
        "terminal_outcomes": summary.model_dump(mode="json"),
        "judge_calibration": calibration.model_dump(mode="json"),
    }
    return ExperimentQualityReceipt.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )
