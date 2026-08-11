"""Deterministic environment and seed sensitivity checks over frozen runs."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from .contracts import (
    ExperimentManifest,
    SensitivityPolicy,
    SensitivityReceipt,
    canonical_digest,
)


def _rate_bps(success_count: int, trial_count: int) -> int:
    return (success_count * 10_000 + trial_count // 2) // trial_count


def _range(values: list[int]) -> int | None:
    return max(values) - min(values) if values else None


def assess_sensitivity(
    manifests: tuple[ExperimentManifest, ...],
    policy: SensitivityPolicy | None = None,
) -> SensitivityReceipt:
    """Assess empirical stability across supplied frozen environment/seed runs.

    This is a bounded diagnostic, not a claim that a hosted provider replayed
    deterministically or that results generalize to environments not supplied.
    Every run must keep execution controls fixed except ``environment_digest``.
    """

    if len(manifests) < 2:
        raise ValueError("sensitivity assessment requires at least two manifests")
    active_policy = policy or SensitivityPolicy()
    ordered = tuple(sorted(manifests, key=lambda item: item.manifest_digest))
    baseline = ordered[0]
    block_reasons: list[str] = []
    review_reasons: list[str] = []
    controls = (
        "repository_uri",
        "commit_sha",
        "subject_digest",
        "dataset_digest",
        "dataset_split_digest",
        "harness_name",
        "harness_version",
        "harness_digest",
        "strategy_name",
        "strategy_digest",
        "model_provider",
        "model_name",
        "model_config_digest",
        "grader_digest",
        "source_format",
        "source_revision",
    )
    for manifest in ordered[1:]:
        for control in controls:
            if getattr(manifest, control) != getattr(baseline, control):
                block_reasons.append(f"sensitivity_control_mismatch_{control}")

    environment_trials: dict[str, list[bool]] = defaultdict(list)
    seed_trials: dict[int, list[bool]] = defaultdict(list)
    seed_missing = False
    for manifest in ordered:
        for trial in manifest.trials:
            environment_trials[manifest.environment_digest].append(trial.succeeded)
            if trial.seed is None:
                seed_missing = True
            else:
                seed_trials[trial.seed].append(trial.succeeded)

    environment_rates = [
        _rate_bps(sum(outcomes), len(outcomes))
        for _, outcomes in sorted(environment_trials.items())
    ]
    environment_range = _range(environment_rates)
    seed_range: int | None = None
    if seed_missing:
        review_reasons.append("sensitivity_seed_missing")
    else:
        seed_rates = [
            _rate_bps(sum(outcomes), len(outcomes))
            for _, outcomes in sorted(seed_trials.items())
        ]
        seed_range = _range(seed_rates)

    if len(environment_trials) < active_policy.minimum_environment_count:
        review_reasons.append("sensitivity_environment_count_insufficient")
    if len(seed_trials) < active_policy.minimum_seed_count:
        review_reasons.append("sensitivity_seed_count_insufficient")
    if (
        environment_range is not None
        and environment_range > active_policy.maximum_environment_success_range_bps
    ):
        review_reasons.append("sensitivity_environment_range_exceeded")
    if (
        seed_range is not None
        and seed_range > active_policy.maximum_seed_success_range_bps
    ):
        review_reasons.append("sensitivity_seed_range_exceeded")

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
        "schema_version": "awe.sensitivity-receipt.v1",
        "subject_digest": baseline.subject_digest,
        "dataset_digest": baseline.dataset_digest,
        "dataset_split_digest": baseline.dataset_split_digest,
        "manifest_digests": tuple(item.manifest_digest for item in ordered),
        "environment_digests": tuple(sorted(environment_trials)),
        "policy_digest": canonical_digest(active_policy),
        "status": status,
        "reasons": reasons,
        "environment_success_range_bps": environment_range,
        "seed_success_range_bps": seed_range,
    }
    return SensitivityReceipt.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )
