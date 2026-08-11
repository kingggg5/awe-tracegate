"""Deterministic, keyless baseline-versus-candidate evaluation policy."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal, localcontext
from fractions import Fraction
from math import comb
from typing import Literal

from .contracts import (
    PENDING_SHA256_DIGEST,
    ComparisonPolicy,
    ComparisonReceipt,
    ComparisonReliability,
    ComparisonVerification,
    EvaluationBundle,
    EvaluationMetrics,
    EvaluationPolicy,
    EvaluationReceipt,
    ExperimentManifest,
    TreatmentFactor,
    canonical_digest,
)

_NORMAL_95_Z = Decimal("1.959963984540054")


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


def _increase_exceeds_policy(
    baseline: int,
    candidate: int,
    maximum_increase_bps: int,
) -> bool | None:
    """Compare an increase to policy exactly, without rounded-boundary passes."""

    if baseline == 0:
        return None if candidate > 0 else False
    if candidate <= baseline:
        return False
    return (candidate - baseline) * 10_000 > maximum_increase_bps * baseline


def _receipt_payload(receipt: EvaluationReceipt) -> dict[str, object]:
    return receipt.model_dump(mode="json", exclude={"receipt_hash"})


def _ratio_bps(numerator: int, denominator: int) -> int:
    scaled = abs(numerator) * 10_000
    rounded = (scaled + denominator // 2) // denominator
    return rounded if numerator >= 0 else -rounded


def _decimal_bps(value: Decimal) -> int:
    bounded = max(Decimal("-1"), min(Decimal("1"), value))
    return int((bounded * Decimal(10_000)).to_integral_value(rounding=ROUND_HALF_UP))


def _experiment_metrics(manifest: ExperimentManifest) -> EvaluationMetrics:
    success_count = sum(trial.succeeded for trial in manifest.trials)
    return EvaluationMetrics(
        trial_count=len(manifest.trials),
        success_count=success_count,
        success_rate_bps=(success_count * 10_000) // len(manifest.trials),
        safety_violations=sum(trial.safety_violations for trial in manifest.trials),
        p95_latency_ms=_p95([trial.latency_ms for trial in manifest.trials]),
        total_cost_microusd=sum(trial.cost_microusd for trial in manifest.trials),
    )


def _fraction_bps(value: Fraction) -> int:
    return _ratio_bps(value.numerator, value.denominator)


def _scaled_fraction(value: Fraction, scale: int) -> int:
    scaled = abs(value.numerator) * scale
    rounded = (scaled + value.denominator // 2) // value.denominator
    return rounded if value.numerator >= 0 else -rounded


def _exact_two_sided_sign_test(
    improved_case_count: int,
    regressed_case_count: int,
) -> tuple[int, int, int]:
    """Return an exact p-value fraction and a conservative ppm projection."""

    discordant = improved_case_count + regressed_case_count
    if discordant == 0:
        return 1, 1, 1_000_000
    denominator = 2**discordant
    smaller = min(improved_case_count, regressed_case_count)
    middle_term_count = discordant - (2 * smaller) - 1
    if middle_term_count <= 0:
        return 1, 1, 1_000_000
    if middle_term_count < smaller + 1:
        index = smaller + 1
        term = comb(discordant, index)
        middle = term
        for next_index in range(index + 1, discordant - smaller):
            term = term * (discordant - next_index + 1) // next_index
            middle += term
        numerator = denominator - middle
    else:
        term = 1
        tail = term
        for index in range(1, smaller + 1):
            term = term * (discordant - index + 1) // index
            tail += term
        numerator = min(denominator, 2 * tail)
    p_value_ppm = (numerator * 1_000_000 + denominator - 1) // denominator
    return numerator, denominator, p_value_ppm


def compare_experiments(
    baseline: ExperimentManifest,
    candidate: ExperimentManifest,
    policy: ComparisonPolicy | None = None,
) -> ComparisonReceipt:
    """Compare controlled experiments without discarding experiment identity.

    Cases are paired by case ID and exact seed coverage. The direction test is
    an exact two-sided sign test over case-level success-rate changes. Effect
    size uses a 95% paired-case normal approximation; v1 requires its bound and
    the exact sign test to agree before establishing improvement or regression
    on the supplied frozen cases. It does not estimate unseen-task performance.
    Identity, treatment, sample, instability, and safety checks remain hard
    prerequisites.
    """

    active_policy = policy or ComparisonPolicy()
    baseline_metrics = _experiment_metrics(baseline)
    candidate_metrics = _experiment_metrics(candidate)
    incomparable_reasons: list[str] = []

    exact_controls = (
        ("repository_uri_mismatch", baseline.repository_uri, candidate.repository_uri),
        ("dataset_digest_mismatch", baseline.dataset_digest, candidate.dataset_digest),
        (
            "dataset_split_digest_mismatch",
            baseline.dataset_split_digest,
            candidate.dataset_split_digest,
        ),
        ("harness_name_mismatch", baseline.harness_name, candidate.harness_name),
        (
            "harness_version_mismatch",
            baseline.harness_version,
            candidate.harness_version,
        ),
        (
            "harness_digest_mismatch",
            baseline.harness_digest,
            candidate.harness_digest,
        ),
        (
            "environment_digest_mismatch",
            baseline.environment_digest,
            candidate.environment_digest,
        ),
        ("grader_digest_mismatch", baseline.grader_digest, candidate.grader_digest),
        ("source_format_mismatch", baseline.source_format, candidate.source_format),
        (
            "source_revision_mismatch",
            baseline.source_revision,
            candidate.source_revision,
        ),
    )
    incomparable_reasons.extend(
        reason
        for reason, baseline_value, candidate_value in exact_controls
        if baseline_value != candidate_value
    )

    observed_treatment_factors: set[TreatmentFactor] = set()
    if baseline.commit_sha != candidate.commit_sha:
        observed_treatment_factors.add("agent_commit")
    if (
        baseline.strategy_name != candidate.strategy_name
        or baseline.strategy_digest != candidate.strategy_digest
    ):
        observed_treatment_factors.add("strategy")
    if (
        baseline.model_provider != candidate.model_provider
        or baseline.model_name != candidate.model_name
        or baseline.model_config_digest != candidate.model_config_digest
    ):
        observed_treatment_factors.add("model")
    declared_treatment_factors = set(active_policy.treatment_factors)
    incomparable_reasons.extend(
        f"undeclared_treatment_factor_{factor}"
        for factor in sorted(observed_treatment_factors - declared_treatment_factors)
    )
    incomparable_reasons.extend(
        f"declared_treatment_factor_unchanged_{factor}"
        for factor in sorted(declared_treatment_factors - observed_treatment_factors)
    )
    changes_agent_subject = bool(
        declared_treatment_factors & {"agent_commit", "strategy"}
    )
    if changes_agent_subject and baseline.subject_digest == candidate.subject_digest:
        incomparable_reasons.append("subject_digest_unchanged")
    if (
        declared_treatment_factors == {"model"}
        and baseline.subject_digest != candidate.subject_digest
    ):
        incomparable_reasons.append("subject_digest_changed_for_model_only_comparison")

    baseline_by_case = defaultdict(list)
    candidate_by_case = defaultdict(list)
    for trial in baseline.trials:
        baseline_by_case[trial.case_id].append(trial)
    for trial in candidate.trials:
        candidate_by_case[trial.case_id].append(trial)

    if set(baseline_by_case) != set(candidate_by_case):
        incomparable_reasons.append("evaluation_case_identity_mismatch")
    shared_cases = sorted(set(baseline_by_case) & set(candidate_by_case))
    if len(shared_cases) > active_policy.maximum_supported_paired_cases:
        incomparable_reasons.append("comparison_case_limit_exceeded")
    if any(
        len(baseline_by_case[case_id]) != len(candidate_by_case[case_id])
        for case_id in shared_cases
    ):
        incomparable_reasons.append("case_trial_count_mismatch")

    if any(trial.seed is None for trial in baseline.trials) or any(
        trial.seed is None for trial in candidate.trials
    ):
        incomparable_reasons.append("trial_seed_missing")
    else:
        for trials in (baseline_by_case, candidate_by_case):
            if any(
                len({trial.seed for trial in case_trials}) != len(case_trials)
                for case_trials in trials.values()
            ):
                incomparable_reasons.append("duplicate_case_seed_identity")
                break
        if set(incomparable_reasons).isdisjoint(
            {"trial_seed_missing", "duplicate_case_seed_identity"}
        ) and any(
            {trial.seed for trial in baseline_by_case[case_id]}
            != {trial.seed for trial in candidate_by_case[case_id]}
            for case_id in shared_cases
        ):
            incomparable_reasons.append("case_seed_coverage_mismatch")

    common_receipt_values = {
        "schema_version": "awe.comparison-receipt.v1",
        "comparator_version": "awe.comparator.v1",
        "baseline_subject_digest": baseline.subject_digest,
        "candidate_subject_digest": candidate.subject_digest,
        "baseline_manifest_digest": baseline.manifest_digest,
        "candidate_manifest_digest": candidate.manifest_digest,
        "baseline_dataset_digest": baseline.dataset_digest,
        "candidate_dataset_digest": candidate.dataset_digest,
        "baseline_dataset_split_digest": baseline.dataset_split_digest,
        "candidate_dataset_split_digest": candidate.dataset_split_digest,
        "treatment_factors": active_policy.treatment_factors,
        "treatment_scope": (
            "single_factor"
            if len(active_policy.treatment_factors) == 1
            else "joint_effect"
        ),
        "policy_digest": canonical_digest(active_policy),
        "baseline": baseline_metrics.model_dump(mode="json"),
        "candidate": candidate_metrics.model_dump(mode="json"),
    }
    if incomparable_reasons:
        payload = {
            **common_receipt_values,
            "status": "block",
            "conclusion": "incomparable",
            "reasons": tuple(sorted(set(incomparable_reasons))),
            "reliability": None,
        }
        return ComparisonReceipt.model_validate(
            {**payload, "receipt_hash": canonical_digest(payload)}
        )

    case_deltas: list[Fraction] = []
    baseline_flaky_cases: set[str] = set()
    candidate_flaky_cases: set[str] = set()
    repeated_case_count = 0
    for case_id in shared_cases:
        baseline_trials = baseline_by_case[case_id]
        candidate_trials = candidate_by_case[case_id]
        trial_count = len(baseline_trials)
        if trial_count >= active_policy.minimum_repetitions_per_case:
            repeated_case_count += 1
        baseline_outcomes = {trial.succeeded for trial in baseline_trials}
        candidate_outcomes = {trial.succeeded for trial in candidate_trials}
        if len(baseline_outcomes) > 1:
            baseline_flaky_cases.add(case_id)
        if len(candidate_outcomes) > 1:
            candidate_flaky_cases.add(case_id)
        baseline_successes = sum(trial.succeeded for trial in baseline_trials)
        candidate_successes = sum(trial.succeeded for trial in candidate_trials)
        case_deltas.append(
            Fraction(candidate_successes - baseline_successes, trial_count)
        )

    case_count = len(case_deltas)
    mean_delta = sum(case_deltas, start=Fraction(0)) / case_count
    if case_count > 1:
        variance = sum(
            ((delta - mean_delta) ** 2 for delta in case_deltas),
            start=Fraction(0),
        ) / (case_count - 1)
    else:
        variance = Fraction(0)
    with localcontext(
        Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999_999, Emax=999_999)
    ):
        decimal_mean = Decimal(mean_delta.numerator) / Decimal(mean_delta.denominator)
        decimal_variance = Decimal(variance.numerator) / Decimal(variance.denominator)
        standard_error = (decimal_variance / Decimal(case_count)).sqrt()
        margin = _NORMAL_95_Z * standard_error
        interval_lower_bps = _decimal_bps(decimal_mean - margin)
        interval_upper_bps = _decimal_bps(decimal_mean + margin)

    improved_case_count = sum(delta > 0 for delta in case_deltas)
    regressed_case_count = sum(delta < 0 for delta in case_deltas)
    tied_case_count = case_count - improved_case_count - regressed_case_count
    discordant_case_count = improved_case_count + regressed_case_count
    p_numerator, p_denominator, p_value_ppm = _exact_two_sided_sign_test(
        improved_case_count, regressed_case_count
    )
    sign_test_significant = (
        p_numerator * 10_000 <= active_policy.significance_level_bps * p_denominator
    )
    flaky_cases = baseline_flaky_cases | candidate_flaky_cases
    flaky_case_rate_bps = _ratio_bps(len(flaky_cases), case_count)
    interval_width_bps = interval_upper_bps - interval_lower_bps

    reliability_reasons: list[str] = []
    low_strength_reasons: list[str] = []
    if case_count < active_policy.minimum_paired_cases:
        low_strength_reasons.append("insufficient_paired_cases")
    if repeated_case_count < case_count:
        low_strength_reasons.append("insufficient_case_repetitions")
    if (
        active_policy.objective == "improvement"
        and discordant_case_count < active_policy.minimum_discordant_cases
    ):
        low_strength_reasons.append("insufficient_discordant_cases")
    reliability_reasons.extend(low_strength_reasons)
    moderate_strength_reasons: list[str] = []
    if flaky_case_rate_bps > active_policy.maximum_flaky_case_rate_bps:
        moderate_strength_reasons.append("evaluation_flakiness_exceeded")
    if interval_width_bps > active_policy.maximum_confidence_interval_width_bps:
        moderate_strength_reasons.append("confidence_interval_too_wide")
    reliability_reasons.extend(moderate_strength_reasons)

    evidence_strength: Literal["low", "moderate", "high"]
    if low_strength_reasons:
        evidence_strength = "low"
    elif moderate_strength_reasons:
        evidence_strength = "moderate"
    else:
        evidence_strength = "high"

    reliability = ComparisonReliability(
        paired_trial_count=len(baseline.trials),
        paired_case_count=case_count,
        repeated_case_count=repeated_case_count,
        improved_case_count=improved_case_count,
        regressed_case_count=regressed_case_count,
        tied_case_count=tied_case_count,
        discordant_case_count=discordant_case_count,
        observed_success_delta_bps=_fraction_bps(mean_delta),
        sign_test_p_value_ppm=p_value_ppm,
        confidence_interval_lower_bps=interval_lower_bps,
        confidence_interval_upper_bps=interval_upper_bps,
        paired_delta_variance_bps_squared=_scaled_fraction(variance, 100_000_000),
        baseline_flaky_case_count=len(baseline_flaky_cases),
        candidate_flaky_case_count=len(candidate_flaky_cases),
        flaky_case_count=len(flaky_cases),
        flaky_case_rate_bps=flaky_case_rate_bps,
        evidence_strength=evidence_strength,
    )

    block_reasons: list[str] = []
    if (
        active_policy.require_zero_safety_violations
        and candidate_metrics.safety_violations > 0
    ):
        block_reasons.append("candidate_safety_violation")

    conclusion: Literal[
        "improvement", "non_regression", "regression", "uncertain", "incomparable"
    ]
    if (
        sign_test_significant
        and regressed_case_count > improved_case_count
        and interval_upper_bps < -active_policy.maximum_success_regression_bps
    ):
        conclusion = "regression"
        block_reasons.append("success_regression_established")
    elif (
        sign_test_significant
        and improved_case_count > regressed_case_count
        and interval_lower_bps > active_policy.minimum_success_improvement_bps
    ):
        conclusion = "improvement"
    elif interval_lower_bps >= -active_policy.maximum_success_regression_bps:
        conclusion = "non_regression"
    else:
        conclusion = "uncertain"

    decision_reasons = list(reliability_reasons)
    latency_exceeded = _increase_exceeds_policy(
        baseline_metrics.p95_latency_ms,
        candidate_metrics.p95_latency_ms,
        active_policy.maximum_latency_increase_bps,
    )
    if latency_exceeded is None:
        decision_reasons.append("latency_baseline_zero")
    elif latency_exceeded:
        decision_reasons.append("p95_latency_regression")
    cost_exceeded = _increase_exceeds_policy(
        baseline_metrics.total_cost_microusd,
        candidate_metrics.total_cost_microusd,
        active_policy.maximum_cost_increase_bps,
    )
    if cost_exceeded is None:
        decision_reasons.append("cost_baseline_zero")
    elif cost_exceeded:
        decision_reasons.append("total_cost_regression")
    if active_policy.objective == "improvement" and conclusion != "improvement":
        decision_reasons.append("improvement_not_established")
    if active_policy.objective == "non_regression" and conclusion not in (
        "improvement",
        "non_regression",
    ):
        decision_reasons.append("non_regression_not_established")

    status: Literal["pass", "review", "block"]
    if block_reasons:
        status = "block"
        reasons = tuple(sorted(set(block_reasons + decision_reasons)))
    elif decision_reasons:
        status = "review"
        reasons = tuple(sorted(set(decision_reasons)))
    else:
        status = "pass"
        reasons = ()

    payload = {
        **common_receipt_values,
        "status": status,
        "conclusion": conclusion,
        "reasons": reasons,
        "reliability": reliability.model_dump(mode="json"),
    }
    return ComparisonReceipt.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )


def validate_comparison_receipt_inputs(
    receipt: ComparisonReceipt,
    baseline: ExperimentManifest,
    candidate: ExperimentManifest,
    policy: ComparisonPolicy | None = None,
) -> ComparisonReceipt:
    """Require an exact local replay before trusting a comparison receipt."""

    replayed = compare_experiments(baseline, candidate, policy)
    if replayed.receipt_hash != receipt.receipt_hash:
        raise ValueError("comparison receipt does not match exact input replay")
    return receipt


def verify_comparison_receipt_inputs(
    receipt: ComparisonReceipt,
    baseline: ExperimentManifest,
    candidate: ExperimentManifest,
    policy: ComparisonPolicy | None = None,
) -> ComparisonVerification:
    """Emit a typed held-input comparison verification result.

    This boundary intentionally converts an untrusted receipt mismatch into a
    machine-readable ``invalid`` record. It does not execute a model, grader,
    trace, or provider API: it only replays deterministic comparison math over
    the three supplied frozen JSON artifacts.
    """

    active_policy = policy or ComparisonPolicy()
    reasons: tuple[str, ...] = ()
    status: Literal["valid", "invalid"] = "valid"
    try:
        validate_comparison_receipt_inputs(receipt, baseline, candidate, active_policy)
    except ValueError:
        status = "invalid"
        reasons = ("comparison_exact_input_replay_mismatch",)
    payload = {
        "schema_version": "awe.comparison-verification.v1",
        "status": status,
        "receipt_hash": receipt.receipt_hash,
        "baseline_manifest_digest": baseline.manifest_digest,
        "candidate_manifest_digest": candidate.manifest_digest,
        "policy_digest": canonical_digest(active_policy),
        "reasons": reasons,
    }
    return ComparisonVerification.model_validate(
        {**payload, "verification_hash": canonical_digest(payload)}
    )


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
